"""PMO Guard UI (HTMX/Jinja) — Claude Design shell + Etki flows.

Screens: Login (`/login`), Overview (`/`), Triage (`/triyaj`, incl. Analysis),
Portfolio (`/portfoy`), Project Detail (`/projeler/{id}`), Approvals (`/onaylar` +
`/ui/casefiles/{id}` review/approve), Reports (`/raporlar` KPI), Chat (`/sohbet`).

All data shown comes from real backend sources: the project **index** (module graph,
scope items, baseline, freshness, repo/documents) and **case files** (triage decisions +
evidence chain + audit trail). Business logic lives in the `engine`/`hitl`/`kpi` layers;
this module is presentation + thin routes only.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
import uuid
from collections import Counter
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version
from pathlib import Path
from typing import Annotated, Any

from fastapi import (
    APIRouter,
    Depends,
    Form,
    HTTPException,
    Request,
    Response,
    UploadFile,
)
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from markdown_it import MarkdownIt
from markupsafe import escape
from pydantic import BaseModel, ValidationError
from starlette.concurrency import run_in_threadpool

from etki import llm_settings as llm_settings_store
from etki import projects_store
from etki.adapters.manifests import first_version, match_packages
from etki.adapters.registry import (
    available_adapters,
    build_documents,
    build_embedder,
    build_llm_client,
    build_reranker,
    build_work_items,
    options_model_for,
)
from etki.agent import ask as agent_ask
from etki.api.context import AppContext, get_context, index_project
from etki.api.security import (
    accessible_projects,
    ensure_project_access,
    require_pmo,
    require_project_access,
    require_user,
    require_writer,
)
from etki.auth import LoginRateLimiter
from etki.config import ProjectConfig, Settings
from etki.core.enums import Decision, PmoDecision
from etki.core.models import AuditEvent, CaseFile, ChatTurn, ScopeItem
from etki.domains import list_domain_profiles
from etki.extraction.parsers import parse_document
from etki.extraction.scope_extractor import HeuristicScopeExtractor
from etki.graphquery import IndexGraphQuery
from etki.hitl.ingest import derive_disputes, precedents_by_clause
from etki.hitl.service import AlreadyDecidedError
from etki.i18n import LANG_NAMES, SUPPORTED, get_locale, resolve_locale, set_locale, t
from etki.index_tools import IndexTools
from etki.indexing.engine import load_index
from etki.kpi import compute_kpis
from etki.llm_profile import build_system_preamble, wrap_untrusted
from etki.net_guard import is_metadata_url
from etki.plugin.options_store import is_secret_field
from etki.process_log import log_event, read_events
from etki.reporting.docx_report import build_case_report

logger = logging.getLogger("etki")

async def _locale_dep(request: Request) -> str:
    """Resolves the active language and writes it to the ContextVar (so text generated in
    the handler also comes out in the right language).

    MUST be async: a sync dependency runs in the threadpool and the ContextVar it sets does
    not carry over into the async handler — text generated inside the handler (pre-analysis,
    error chips) would fall back to the default 'tr'."""
    lang = resolve_locale(request, Settings())
    set_locale(lang)
    return lang


# Active language for routes; the dependency also sets the ContextVar (incl. chips/errors).
LocaleDep = Annotated[str, Depends(_locale_dep)]

router = APIRouter(dependencies=[Depends(require_user), Depends(_locale_dep)])
login_router = APIRouter(dependencies=[Depends(_locale_dep)])  # public: /login, /logout, /dil


def _locale_processor(request: Request) -> dict:
    """Injects the active language + language list into every template (Jinja context_processor)."""
    lang = resolve_locale(request, Settings())
    # also guarantee it at render time (filters/translations read the same language)
    set_locale(lang)
    return {"lang": lang, "lang_names": LANG_NAMES, "supported_langs": SUPPORTED}


templates = Jinja2Templates(
    directory=str(Path(__file__).parent / "templates"),
    context_processors=[_locale_processor],
)

# `t` is GLOBAL → reachable in every template incl. macros (imported without context); it
# reads the active language from the ContextVar (get_locale), set by the route dependency
# + context_processor.
templates.env.globals["t"] = lambda key, **kw: t(key, get_locale(), **kw)

# Version — global for all templates (sidebar alpha badge etc). From package metadata.
try:
    _APP_VERSION = _pkg_version("etki")
except PackageNotFoundError:
    _APP_VERSION = "0.1.0a1"
templates.env.globals["app_version"] = _APP_VERSION
# Stylesheet cache-buster: the version alone misses same-version CSS edits; the
# file mtime (read once at startup) changes with every deploy that touches CSS.
try:
    _CSS_STAMP = int((Path(__file__).parent / "static" / "pmo.css").stat().st_mtime)
except OSError:
    _CSS_STAMP = 0
templates.env.globals["css_stamp"] = _CSS_STAMP

_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_MAX_ITEMS = 40  # upper bound for batch triage

CtxDep = Annotated[AppContext, Depends(get_context)]

# Enum → label filters are now locale-aware (catalog + ContextVar active language).
templates.env.filters["tr_decision"] = lambda v: t(f"decision.{v}")
templates.env.filters["tr_risk"] = lambda v: t(f"risk.{v}")
templates.env.filters["tr_status"] = lambda v: t(f"status.{v}")
# Effort unit is frozen as "hour" in the evidence chain; localize at render time only.
templates.env.filters["tr_unit"] = (
    lambda v: t("common.hours_short") if v in ("hour", "hours", "h") else v
)


def fmt_hours(v: float | None) -> str:
    """Human duration for KPI tiles: sub-hour values read as minutes, not '0.03 sa'."""
    if v is None:
        return "—"
    if v < 1:
        return f"≈{max(1, round(v * 60))} {t('common.minutes_short')}"
    return f"{v:g} {t('common.hours_short')}"


templates.env.filters["fmt_hours"] = fmt_hours

_ACTION = {
    "approve": PmoDecision.APPROVE,
    "reject": PmoDecision.REJECT,
    "cr": PmoDecision.CONVERT_TO_CR,
}

# Decision/status → (text color, background color). Labels come from the catalog
# (locale-aware t()).
_DECISION_COLORS: dict[Decision, tuple[str, str]] = {
    Decision.IN_SCOPE: ("#1E7A43", "#E6F4EC"),
    Decision.OUT_OF_SCOPE: ("#C6413A", "#FBEAE8"),
    Decision.CR_CANDIDATE: ("#8F5F00", "#FBF3E2"),
    Decision.GRAY_AREA: ("#55666D", "#EEEBE4"),
    Decision.MAINTENANCE: ("#3563B0", "#EAF1FB"),
}
_STATUS_COLORS: dict[PmoDecision, tuple[str, str]] = {
    PmoDecision.PENDING: ("#8F5F00", "#FBF3E2"),
    PmoDecision.APPROVE: ("#1E7A43", "#E6F4EC"),
    PmoDecision.REJECT: ("#C6413A", "#FBEAE8"),
    PmoDecision.CONVERT_TO_CR: ("#3563B0", "#EAF1FB"),
}

def _monitor(ctx: AppContext) -> dict:
    """Real status for the top bar's 'live monitoring' badge: how many engines are ready."""
    n = len(ctx.engines)
    return {"projects": n, "ok": n > 0}


def _llm_status() -> dict:
    """AI-assistant availability for the UI — config-only check (no network call),
    mirrors the None-conditions in registry.build_llm_client."""
    s = Settings()
    provider = (s.llm_provider or "openai").lower()
    if provider == "anthropic":
        enabled = bool(s.anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY"))
        model = s.anthropic_model
    else:
        enabled = bool(s.llm_base_url)
        model = s.llm_model
    return {
        "enabled": enabled,
        "provider": provider if enabled else None,
        "model": model if enabled else None,
    }


def _freshness_days(freshness: str) -> int | None:
    """Index age in days from the freshness stamp (ISO date prefix); None if unparsable."""
    try:
        stamped = datetime.fromisoformat(freshness[:10]).date()
    except ValueError:
        return None
    return (datetime.now(UTC).date() - stamped).days


def _project_meta(ctx: AppContext, project_id: str) -> dict[str, str] | None:
    """Project {id,name} for the sidebar/header — from context (no disk access needed)."""
    for p in ctx.projects:
        if p["id"] == project_id:
            return {"id": p["id"], "name": p["name"]}
    return None


def _run_index(project: object, settings: Settings) -> None:
    # Indexing blocks (AST/subprocess); runs on a separate thread in its own event loop.
    asyncio.run(index_project(project, settings))  # type: ignore[arg-type]


async def _reindex(project_id: str) -> None:
    project = projects_store.get(project_id)
    if project is not None:
        await asyncio.to_thread(_run_index, project, Settings())
    get_context.cache_clear()  # so the new/changed project shows up in the context


def _decision_chip(d: Decision) -> dict[str, str]:
    color, bg = _DECISION_COLORS.get(d, ("#55666D", "#EEEBE4"))
    return {"label": t(f"decision.{d.value}"), "color": color, "bg": bg}


def _status_chip(s: PmoDecision) -> dict[str, str]:
    color, bg = _STATUS_COLORS.get(s, ("#55666D", "#EEEBE4"))
    return {"label": t(f"status.{s.value}"), "color": color, "bg": bg}


# LLM output / user request text (pre-analysis, chat) markdown → HTML. `html=False` makes
# markdown-it ESCAPE any raw HTML in the source (so `<img onerror=…>`/`<script>` render as
# inert text, not live nodes) — the "commonmark" preset enables html by default, which would
# be a stored-XSS sink because these fragments are emitted with Jinja `|safe`. Do NOT flip
# this back on without a sanitizer (nh3/bleach) in front of the `|safe` render.
_MD = MarkdownIt("commonmark", {"html": False, "linkify": True})

# Post-triage prompts — LANGUAGE-NEUTRAL (output language comes from the project's language
# via `agent_ask(lang=...)`).
_CHAT_PROMPT = (
    "Take the triage result below as CONTEXT; answer the user's follow-up question "
    "briefly and with justification, using this context and the project index tools.\n\n"
    "TRIAGE CONTEXT:\n{context}\n\nQUESTION: {question}"
)
# Sor screen: the deterministic graph answer is fed to the assistant as retrieval
# context (RAG) — the model grounds its answer in what the graph already found.
_ASK_PROMPT = (
    "Below is the deterministic knowledge-graph retrieval for the user's question "
    "(strategy + matched nodes). Ground your answer in it, verify with the project "
    "index tools where needed, and answer briefly with justification.\n\n"
    "GRAPH CONTEXT:\n{context}\n\nQUESTION: {question}"
)
# Developer-facing automatic pre-analysis prompt (generated at triage, saved to the case).
_DEV_ANALYSIS_PROMPT = (
    "Below is a request's automatic triage result. Write an itemized PRE-ANALYSIS for "
    "the DEVELOPER: (1) which code modules/areas are affected, (2) complexity/churn and "
    "the main factors driving effort, (3) integration/contact points and dependencies, "
    "(4) risks and things to watch, (5) to-dos (short implementation steps). Keep it "
    "short and technical; go deeper with the project tools when needed.\n\n"
    "TRIAGE RESULT:\n"
)


def _project_llm_args(project_id: str) -> dict:
    """Converts a project's LLM profile into agent_ask kwargs (domain prefix + language + pivot).

    Prompt injection protection (UNTRUSTED_GUARD) is not here — it's added unconditionally
    to EVERY agent_ask call inside `agent._build_system`; the prompts here wrap untrusted
    data in delimiters via `wrap_untrusted`."""
    project = projects_store.get(project_id)
    if project is None:
        return {"system_extra": "", "lang": "tr", "pivot_language": None}
    return {
        "system_extra": build_system_preamble(
            project.language, project.domain_profile, project.instructions
        ),
        "lang": project.language,
        "pivot_language": project.pivot_language,
    }


def _case_summary(case: CaseFile) -> str:
    """Converts a triage CaseFile into compact text to use as chat context."""
    lines = [f"Talep: {case.raw_request}", f"{len(case.decisions)} alt-ister:"]
    for sub, d in zip(case.sub_requests, case.decisions, strict=False):
        mods = ", ".join(d.evidence.impacted_modules) or "—"
        clause = ", ".join(d.evidence.contract_clauses_cited) or "—"
        lines.append(
            f"- '{sub.item}': {d.decision.value} (güven {d.confidence:.0%}), "
            f"efor {d.effort_estimate.low}-{d.effort_estimate.high}sa, "
            f"risk {d.risk.level.value}, etkilenen modüller: {mods}, madde: {clause}"
        )
    return "\n".join(lines)


def _deterministic_pre_analysis(case: CaseFile) -> str:
    """Rule-based developer pre-analysis from the evidence chain when no LLM is available
    (markdown).

    Labels come from the i18n catalog (active locale); the free text generated by the
    engine (basis/assumptions/reasoning) stays frozen in whatever language it was in
    at triage time."""
    lines = [f"**{t('pre.auto_title')}** — _{case.raw_request}_", ""]
    for sub, d in zip(case.sub_requests, case.decisions, strict=False):
        lines.append(f"### {sub.item}")
        lines.append(
            f"- **{t('ev.decision')}:** {t('decision.' + d.decision.value)} "
            f"({t('ev.confidence')} {d.confidence:.0%})"
        )
        mods = ", ".join(d.evidence.impacted_modules) or "—"
        lines.append(f"- **{t('ev.impacted_modules')}:** {mods}")
        for sig in d.evidence.impacted_signals:
            detail = t("pre.signal", loc=sig.loc, cyc=sig.cyclomatic, churn=sig.churn)
            lines.append(f"  - `{sig.id}` — {detail}")
        unit = d.effort_estimate.unit
        if unit in ("hour", "hours", "h"):
            unit = t("common.hours_short")
        lines.append(
            f"- **{t('ps.effort')}:** {d.effort_estimate.low}–{d.effort_estimate.high} {unit}"
            + (f" · _{d.effort_estimate.basis}_" if d.effort_estimate.basis else "")
        )
        clauses = ", ".join(d.evidence.contract_clauses_cited) or "—"
        lines.append(f"- **{t('pre.related_clauses')}:** {clauses}")
        lines.append(
            f"- **{t('ev.risk')}:** {t('risk.' + d.risk.level.value)}"
            + (f" · ⚠ {t('badge.escalation')}" if d.risk.escalation else "")
        )
        if d.evidence.assumptions:
            lines.append(f"- **{t('ev.assumptions')}:** " + "; ".join(d.evidence.assumptions))
        if d.evidence.reasoning:
            lines.append(f"- **{t('ev.reasoning')}:** {d.evidence.reasoning}")
        lines.append("")
    return "\n".join(lines).strip()


async def _project_graph_context(project_id: str, raw_request: str) -> str | None:
    """Compact related-context block from the graph-query layer (Faz 4 consumer):
    top-3 seeds widened by `expand(query=…)` — with a configured reranker the
    packing is relevance-ordered. Best-effort: any failure returns None (a
    retrieval hiccup must never break pre-analysis)."""
    try:
        project = projects_store.get(project_id)
        if project is None:
            return None
        index = load_index(project.resolved_index_path())
        if index is None:
            return None
        work_items = build_work_items(project.connectors.work_items)
        items = work_items.all_items() if hasattr(work_items, "all_items") else []
        settings = Settings()
        gq = IndexGraphQuery(
            index, items,
            embedder=build_embedder(settings), reranker=build_reranker(settings),
        )
        seeds = await gq.find_k_nodes(raw_request, k=3)
        if not seeds:
            return None
        sub = await gq.expand(
            [n.id for n in seeds], max_hops=2, token_budget=800, query=raw_request
        )
        lines = [f"- {n.id}: {n.text[:160]}" for n in sub.nodes]
        header = f"İLGİLİ BAĞLAM (bilgi grafiğinden, paketleme: {sub.packing}):"
        return header + "\n" + "\n".join(lines)
    except Exception:  # noqa: BLE001 — context enrichment only
        logger.warning("[%s] graf bağlamı üretilemedi", project_id, exc_info=True)
        return None


async def _generate_pre_analysis(
    project_id: str, case: CaseFile, *, use_llm: bool
) -> tuple[str, str]:
    """Developer pre-analysis: LLM if possible, otherwise deterministic from the evidence
    chain. Returns (text, source) with source 'llm' | 'deterministic' so the UI can show
    which generator actually produced it. For dependency-change requests the package
    research (version diff + usage sites + OSV) is done UP FRONT here and fed to both
    generators as input."""
    dep_context = await _dep_diff_context(project_id, case)
    if use_llm and build_llm_client(Settings()) is not None:
        try:
            prompt = _DEV_ANALYSIS_PROMPT + wrap_untrusted(_case_summary(case))
            graph_context = await _project_graph_context(project_id, case.raw_request)
            if graph_context:
                prompt += "\n" + wrap_untrusted(graph_context)
            if dep_context:
                prompt += "\n" + wrap_untrusted(dep_context)
            text = await agent_ask(
                prompt,
                _project_tools(project_id),
                **_project_llm_args(project_id),
            )
            if text and text.strip():
                return text.strip(), "llm"
        except Exception:
            logger.warning(
                "[%s] otomatik ön analiz LLM ile üretilemedi; deterministik kullanılıyor",
                project_id, exc_info=True,
            )
    text = _deterministic_pre_analysis(case)
    if dep_context:
        text += "\n\n" + dep_context
    return text, "deterministic"


def _project_tools(project_id: str) -> IndexTools | None:
    """Tool set the LLM assistant operates on: the project index + work items."""
    project = projects_store.get(project_id)
    if project is None:
        return None
    index = load_index(project.resolved_index_path())
    if index is None:
        return None
    work_items = build_work_items(project.connectors.work_items)
    items = work_items.all_items() if hasattr(work_items, "all_items") else []
    return IndexTools(index, items)


# Max files accepted in a single multipart upload (DoS guard — the per-file byte cap alone
# does not bound how many just-under-limit files a request may carry).
_MAX_UPLOAD_FILES = 50


async def _read_upload_bounded(upload: UploadFile) -> bytes | None:
    """Reads at most `max_upload_mb`+1 bytes so an oversized file is never fully materialized
    in memory. Returns None (caller rejects) when the file exceeds the cap."""
    limit = Settings().max_upload_mb * 1024 * 1024
    raw = await upload.read(limit + 1)
    if len(raw) > limit:
        return None
    return raw


def _over_upload_limit(raw: bytes) -> str | None:
    limit_mb = Settings().max_upload_mb
    if len(raw) > limit_mb * 1024 * 1024:
        return t("err.file_too_large", mb=limit_mb)
    return None


def _error_fragment(message: str) -> HTMLResponse:
    """Error box placed in the target region (200 → HTMX inserts the fragment)."""
    return HTMLResponse(f'<div class="summary err" role="alert">⚠ {message}</div>')


def _project_stats() -> list[dict]:
    """REAL statistics derived from the index, for each project."""
    rows: list[dict] = []
    for p in projects_store.load():
        idx = load_index(p.resolved_index_path())
        scope_items = idx.baseline.scope_items if idx else []
        excluded = sum(1 for s in scope_items if s.polarity.value == "EXCLUDED")
        rows.append({
            "id": p.id,
            "name": p.name,
            "contract_id": p.contract_id,
            "modules": len(idx.modules) if idx else 0,
            "clauses": len(scope_items),
            "included": len(scope_items) - excluded,
            "excluded": excluded,
            "baseline_version": idx.baseline.version if idx else 0,
            "freshness": idx.freshness if idx else "—",
            "work_items": p.connectors.work_items.adapter,
            "repos": len(p.resolved_repos()),
            "documents": len(projects_store.list_documents(p.id)),
            "indexed": idx is not None,
        })
    return rows


def _case_row(case: CaseFile, names: dict[str, str]) -> dict:
    """Reduces a case file to a summary list row."""
    seen: set[Decision] = set()
    chips: list[dict[str, str]] = []
    distinct: list[str] = []
    for d in case.decisions:
        if d.decision not in seen:
            seen.add(d.decision)
            chips.append(_decision_chip(d.decision))
            distinct.append(d.decision.value)
    color, bg = _STATUS_COLORS.get(case.status, ("#55666D", "#EEEBE4"))
    label = t(f"status.{case.status.value}")
    return {
        "id": case.request_id,
        "request": case.raw_request,
        "decisions": chips,
        "decision_values": distinct,
        "count": len(case.decisions),
        "status": {"label": label, "color": color, "bg": bg},
        "status_label": label,
        "status_color": color,
        "status_bg": bg,
        "escalated": any(d.risk.escalation for d in case.decisions),
        "project": names.get(case.project_id or "", case.project_id or "—"),
        "created_at": case.created_at.strftime("%Y-%m-%d %H:%M") if case.created_at else "—",
    }


# ---------------------------------------------------------------------------
# Authentication (public)
# ---------------------------------------------------------------------------
# One failed-login throttle for the process (startup enforces a single worker).
_login_limiter = LoginRateLimiter()


def _safe_next(next: str) -> str:
    """Login may only redirect WITHIN the site: a `next` that is absolute, scheme-relative
    (`//evil`) or backslash-mangled falls back to `/` (open-redirect guard)."""
    n = (next or "").strip()
    if not n.startswith("/") or n.startswith("//") or "://" in n or "\\" in n:
        return "/"
    return n


def _client_key(request: Request, username: str) -> str:
    host = request.client.host if request.client else "?"
    return f"{host}|{username.strip().lower()}"


@login_router.get("/login", response_class=HTMLResponse)
async def login_form(request: Request, next: str = "/") -> Response:
    next = _safe_next(next)
    if request.session.get("user"):
        return RedirectResponse(next, status_code=303)
    return templates.TemplateResponse(request, "login.html", {"next": next, "error": None})


@login_router.post("/login", response_class=HTMLResponse)
async def login_submit(
    request: Request,
    ctx: CtxDep,
    username: Annotated[str, Form()],
    password: Annotated[str, Form()],
    next: Annotated[str, Form()] = "/",
    remember: Annotated[str | None, Form()] = None,
) -> Response:
    next = _safe_next(next)
    key = _client_key(request, username)
    wait = _login_limiter.retry_after(key)
    if wait > 0:
        return templates.TemplateResponse(
            request,
            "login.html",
            {"next": next, "error": t("login.rate_limited", min=max(1, int(wait // 60) + 1))},
            status_code=429,
        )
    user = ctx.user_store.authenticate(username, password)
    if user is None:
        _login_limiter.register_failure(key)
        return templates.TemplateResponse(
            request,
            "login.html",
            {"next": next, "error": t("login.error_bad_credentials")},
            status_code=401,
        )
    _login_limiter.reset(key)
    # Session binding: `tok` invalidates live sessions on password change/deletion;
    # `exp` is the server-side lifetime — "remember me" 30 days, otherwise 8 hours.
    lifetime = 30 * 86400 if remember else 8 * 3600
    request.session["user"] = {
        "username": user.username,
        "role": user.role,
        "tok": user.token,
        "exp": time.time() + lifetime,
    }
    return RedirectResponse(next, status_code=303)


@login_router.post("/logout")
async def logout(request: Request) -> Response:
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@login_router.post("/dil")
async def set_language(request: Request, lang: Annotated[str, Form()]) -> Response:
    """Sets the UI language (session + durable cookie, so the choice survives logout).
    Redirects back to the referring page."""
    back = request.headers.get("referer") or "/"
    response: Response = RedirectResponse(back, status_code=303)
    if lang in SUPPORTED:
        request.session["lang"] = lang
        response.set_cookie(
            "etki_lang", lang, max_age=365 * 24 * 3600, httponly=True, samesite="lax"
        )
    return response


# ---------------------------------------------------------------------------
# Landing page — projects list (project-centric; old dashboard removed)
# ---------------------------------------------------------------------------
@router.get("/", response_class=HTMLResponse)
async def projects_list(
    request: Request, ctx: CtxDep, user: Annotated[dict[str, str], Depends(require_user)]
) -> HTMLResponse:
    allowed = accessible_projects(user, ctx.user_store)  # None = all (pmo-global)
    stats = [s for s in _project_stats() if allowed is None or s["id"] in allowed]
    names = {p["id"]: p["name"] for p in stats}
    cases = [
        c for c in ctx.repo.list_cases(None)
        if allowed is None or (c.project_id or "") in allowed
    ]
    # Number of requests per project (shown on the card).
    case_counts: Counter[str] = Counter(c.project_id or "" for c in cases)
    for s in stats:
        s["cases"] = case_counts.get(s["id"], 0)
    totals = {
        "projects": len(stats),
        "modules": sum(s["modules"] for s in stats),
        "clauses": sum(s["clauses"] for s in stats),
        "cases": len(cases),
    }
    return templates.TemplateResponse(
        request,
        "projects.html",
        {"projects": stats, "totals": totals, "names": names, "monitor": _monitor(ctx)},
    )


# ---------------------------------------------------------------------------
# Triage + Analysis (project-scoped)
# ---------------------------------------------------------------------------
@router.get("/projeler/{project_id}/triyaj", response_class=HTMLResponse,
            dependencies=[Depends(require_project_access)])
async def project_triyaj(request: Request, project_id: str, ctx: CtxDep) -> Response:
    project = _project_meta(ctx, project_id)
    if project is None:
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(
        request, "project_triyaj.html",
        {"project": project, "monitor": _monitor(ctx), "llm": _llm_status()}
    )


@router.post("/ui/triage", response_class=HTMLResponse)
async def ui_triage(
    request: Request,
    ctx: CtxDep,
    user: Annotated[dict[str, str], Depends(require_writer)],
    request_text: Annotated[str, Form()],
    project_id: Annotated[str | None, Form()] = None,
) -> HTMLResponse:
    pid = ctx.resolve_project(project_id)
    ensure_project_access(user, pid, ctx.user_store)
    request_id = f"REQ-{pid}-{uuid.uuid4().hex[:8]}"
    case = await ctx.engines[pid].triage(request_text, request_id=request_id)
    case.project_id = pid
    ctx.approval.record_triage(case)
    summary = _case_summary(case)
    # AUTOMATICALLY generate the developer-facing pre-analysis (LLM if available, otherwise
    # deterministic) and save it to the case. The developer can edit and re-save the result.
    pre_analysis_text, pre_source = await _generate_pre_analysis(pid, case, use_llm=True)
    case.pre_analysis = pre_analysis_text
    ctx.repo.save_case(case)
    ctx.approval.sync_wiki(case)  # pre-analysis is rendered into the wiki projection
    audit = ctx.repo.list_audit(case.request_id)
    seq = max((e.seq for e in audit), default=0) + 1
    ctx.repo.append_audit(
        AuditEvent(case_id=case.request_id, seq=seq, actor="auto", action="PRE_ANALYSIS",
                   detail={"otomatik": True, "kaynak": pre_source}, at=datetime.now(UTC))
    )
    return templates.TemplateResponse(
        request,
        "triage_result.html",
        {"case": case, "case_summary": summary, "pre_analysis_text": pre_analysis_text,
         "pre_analysis_html": _MD.render(pre_analysis_text),
         "pre_analysis_source": pre_source, "llm": _llm_status(),
         "dep_compare": _dep_compare_prefills(pid, case),
         "deps_online": Settings().deps_online,
         "case_flow": _case_sankey(pid, case)},
    )


@router.post("/ui/case-chat", response_class=HTMLResponse)
async def ui_case_chat(
    request: Request,
    ctx: CtxDep,
    user: Annotated[dict[str, str], Depends(require_writer)],
    question: Annotated[str, Form()],
    project_id: Annotated[str | None, Form()] = None,
    context: Annotated[str, Form()] = "",
    case_id: Annotated[str, Form()] = "",
) -> HTMLResponse:
    pid = ctx.resolve_project(project_id)
    ensure_project_access(user, pid, ctx.user_store)
    # Context + question are untrusted: wrapped in delimiters (UNTRUSTED_GUARD is in
    # the system prompt).
    prompt = _CHAT_PROMPT.format(
        context=wrap_untrusted(context), question=wrap_untrusted(question)
    )
    try:
        answer = await agent_ask(prompt, _project_tools(pid), **_project_llm_args(pid))
        answer_html = _MD.render(answer)
        # Save the successful turn to the case (so chat about the triage persists).
        # IDOR guard: the case must belong to the access-checked project — get_case looks up
        # by id with no project filter, so without this a scoped user could append a chat turn
        # to another project's case by passing its case_id.
        if case_id:
            case = ctx.repo.get_case(case_id)
            if case is not None and (case.project_id or "") == pid:
                case.chat_turns.append(
                    ChatTurn(question=question, answer=answer, at=datetime.now(UTC))
                )
                ctx.repo.save_case(case)
    except Exception:
        logger.warning("[%s] takip sorusu yanıtlanamadı (LLM hatası)", pid, exc_info=True)
        answer_html = f'<p class="meta">⚠ {t("err.assistant_unavailable")}</p>'
    return templates.TemplateResponse(
        request, "case_chat.html", {"question": question, "answer_html": answer_html}
    )


@router.post("/ui/analyze", response_class=HTMLResponse)
async def ui_analyze(
    request: Request,
    ctx: CtxDep,
    user: Annotated[dict[str, str], Depends(require_writer)],
    file: UploadFile,
    project_id: Annotated[str | None, Form()] = None,
    mode: Annotated[str, Form()] = "triage",
) -> HTMLResponse:
    pid = ctx.resolve_project(project_id)
    ensure_project_access(user, pid, ctx.user_store)
    raw = await _read_upload_bounded(file)
    if raw is None:
        return _error_fragment(t("err.file_too_large", mb=Settings().max_upload_mb))
    try:
        # Parsing is sync + CPU-bound (and can be heavy for a large document); run it off the
        # event loop so one upload can't block every other request on the single worker.
        full_text, items = await run_in_threadpool(
            parse_document, file.filename or "yukleme.txt", raw
        )
    except Exception:
        logger.warning("[%s] yükleme çözümlenemedi: %s", pid, file.filename, exc_info=True)
        return _error_fragment(t("err.file_unreadable"))

    if mode == "scope":
        clauses = await HeuristicScopeExtractor().extract(f"UPLOAD-{pid}", full_text)
        return templates.TemplateResponse(
            request,
            "analyze_results.html",
            {"mode": "scope", "clauses": clauses, "filename": file.filename, "project_id": pid},
        )

    truncated = len(items) > _MAX_ITEMS
    cases = []
    try:
        for i, item in enumerate(items[:_MAX_ITEMS], start=1):
            request_id = f"REQ-{pid}-up{i}-{uuid.uuid4().hex[:6]}"
            case = await ctx.engines[pid].triage(item, request_id=request_id)
            case.project_id = pid
            # Batch-triage pre-analysis is DETERMINISTIC (N LLM calls would be costly/slow).
            case.pre_analysis, _ = await _generate_pre_analysis(pid, case, use_llm=False)
            ctx.approval.record_triage(case)
            cases.append(case)
    except Exception:
        logger.warning("[%s] toplu triyaj sırasında hata", pid, exc_info=True)
        return _error_fragment(t("err.batch_triage"))
    return templates.TemplateResponse(
        request,
        "analyze_results.html",
        {"mode": "triage", "cases": cases, "filename": file.filename,
         "truncated": truncated, "total": len(items), "project_id": pid},
    )


# ---------------------------------------------------------------------------
# Pre-analysis — analysis prepared via chat over the triage output, saved to the case
# ---------------------------------------------------------------------------
@router.post("/projeler/{project_id}/triyaj/{case_id}/on-analiz", response_class=HTMLResponse,
             dependencies=[Depends(require_project_access)])
async def save_pre_analysis(
    request: Request,
    project_id: str,
    case_id: str,
    ctx: CtxDep,
    user: Annotated[dict[str, str], Depends(require_writer)],
    pre_analysis: Annotated[str, Form()],
) -> HTMLResponse:
    case = ctx.repo.get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail=t("err.case_not_found"))
    # IDOR: checked via the CASE's project, not the path (404 if the case is another project's).
    ensure_project_access(user, case.project_id, ctx.user_store)
    case.pre_analysis = pre_analysis
    ctx.repo.save_case(case)
    ctx.approval.sync_wiki(case)  # pre-analysis is rendered into the wiki projection
    audit = ctx.repo.list_audit(case_id)
    seq = max((e.seq for e in audit), default=0) + 1
    ctx.repo.append_audit(
        AuditEvent(
            case_id=case_id, seq=seq, actor=user["username"], action="PRE_ANALYSIS",
            detail={"uzunluk": len(pre_analysis)}, at=datetime.now(UTC),
        )
    )
    return templates.TemplateResponse(
        request, "pre_analysis_saved.html", {"case_id": case_id, "project_id": project_id}
    )


# ---------------------------------------------------------------------------
# Approvals — merged into History (2026-07): the PENDING queue is the
# `?filtre=bekleyen` tab of /gecmis; old links redirect there.
# ---------------------------------------------------------------------------
@router.get("/projeler/{project_id}/onaylar", response_class=HTMLResponse,
            dependencies=[Depends(require_project_access)])
async def project_onaylar(request: Request, project_id: str, ctx: CtxDep) -> Response:
    return RedirectResponse(f"/projeler/{project_id}/gecmis?filtre=bekleyen", status_code=303)


def _pre_analysis_html(case: CaseFile) -> str | None:
    """Converts the case's saved pre-analysis (markdown) to safe HTML (no XSS)."""
    return _MD.render(case.pre_analysis) if case.pre_analysis else None


def _chat_turns_html(case: CaseFile) -> list[dict[str, str]]:
    """Prepares saved pre-analysis chat turns for display (answer markdown → HTML)."""
    return [
        {"question": t.question, "answer_html": _MD.render(t.answer)}
        for t in case.chat_turns
    ]


def _dep_compare_prefills(project_id: str | None, case: CaseFile) -> list[dict | None]:
    """Per-decision prefill for the one-click version comparison on the case
    screen: package + old (best-effort from the declared spec — editable) +
    new (the request's target version). None for non-dependency decisions.
    The comparison itself runs on demand (triage stays a fast lookup)."""
    project = projects_store.get(project_id or "")
    idx = load_index(project.resolved_index_path()) if project else None
    specs = {d.name: d.raw_spec for d in (idx.dependencies if idx else [])}
    prefills: list[dict | None] = []
    for sub in case.sub_requests:
        if sub.package:
            prefills.append({
                "package": sub.package,
                "old": first_version(specs.get(sub.package, "")),
                "new": sub.target_version or "",
            })
        else:
            prefills.append(None)
    return prefills


def _dep_research_lines(
    package: str, old: str, new: str, report: dict,
    paths_by_module: dict[str, list[str]], apis_by_module: dict[str, list[str]],
    cap: int = 10,
) -> str:
    """Renders one package's version-diff report as a compact markdown block —
    each broken/changed usage annotated with the MODULES that use it (pure,
    shared by the LLM prompt and the deterministic pre-analysis)."""

    def _path_sites(path: str) -> str:
        mods = sorted(m for m, ps in paths_by_module.items() if path in ps)
        return f" → {t('pre.dep_modules')}: {', '.join(mods)}" if mods else ""

    def _symbol_sites(symbol: str) -> str:
        leaf = symbol.rsplit(".", 1)[-1]
        mods = sorted(m for m, ss in apis_by_module.items() if leaf in ss)
        return f" [{', '.join(mods)}]" if mods else ""

    c = report["counts"]
    lines = [
        f"**{t('pre.dep_research_title', package=package, old=old, new=new)}**",
        f"- {t('vd.api_summary', removed=c['removed'], added=c['added'], changed=c['changed'])}",
    ]
    your = report.get("your_code") or {}
    for b in (your.get("broken") or [])[:cap]:
        hint = f" ({t('vd.hint')}: {', '.join(b['hint'])})" if b.get("hint") else ""
        lines.append(f"- ✗ {t('pre.dep_broken')}: `{b['path']}`{hint}{_path_sites(b['path'])}")
    for ch in (your.get("changed") or [])[:cap]:
        lines.append(
            f"- ~ {t('pre.dep_changed')}: `{ch['path']}`: {ch['old']} → {ch['new']}"
            f"{_path_sites(ch['path'])}"
        )
    used = report.get("used") or {}
    for s in (used.get("removed") or [])[:cap]:
        lines.append(f"- ✗ {t('vd.removed_h')}: `{s}`{_symbol_sites(s)}")
    for ch in (used.get("changed") or [])[:cap]:
        lines.append(
            f"- ~ {t('vd.changed_h')}: `{ch['symbol']}`: {ch['old']} → {ch['new']}"
            f"{_symbol_sites(ch['symbol'])}"
        )
    vulns = report.get("vulnerabilities") or {}
    for label, version in (("old", old), ("new", new)):
        found = vulns.get(label) or []
        ids = ", ".join(v.get("id", "?") for v in found[:4]) if found else t("vd.clean")
        lines.append(f"- {t('vd.vulns')} {version}: {ids}")
    return "\n".join(lines)


async def _dep_diff_context(project_id: str | None, case: CaseFile) -> str | None:
    """Up-front package research for dependency-change sub-requests, fed as INPUT
    to the pre-analysis (LLM prompt and the deterministic fallback): declared vs
    requested version diff, the removed/changed symbols THIS project uses — with
    the modules that use them — and OSV findings. Opt-in (ETKI_DEPS_ONLINE) and
    best-effort: any failure returns None. Runs AFTER the decision is recorded,
    so it can never become a decision input."""
    settings = Settings()
    if not settings.deps_online:
        return None
    project = projects_store.get(project_id or "")
    idx = load_index(project.resolved_index_path()) if project else None
    if idx is None or not idx.dependencies:
        return None
    from etki.adapters.package_download import PackageFetcher, version_diff_report
    from etki.adapters.registry import build_package_registry

    specs = {d.name: d.raw_spec for d in idx.dependencies}
    sections: list[str] = []
    for sub in case.sub_requests:
        if not (sub.package and sub.target_version):
            continue
        old = first_version(specs.get(sub.package, ""))
        if not old or old == sub.target_version:
            continue
        impact = IndexTools(idx).dependency_impact(sub.package)
        paths_by_module: dict[str, list[str]] = impact["used_api_paths"]
        apis_by_module: dict[str, list[str]] = impact["used_apis"]
        try:
            report = await version_diff_report(
                sub.package, old, sub.target_version,
                used_paths=sorted({p for ps in paths_by_module.values() for p in ps}),
                used_symbols=sorted({s for ss in apis_by_module.values() for s in ss}),
                fetcher=PackageFetcher(
                    pypi_base_url=settings.pypi_base_url,
                    timeout=settings.deps_download_timeout,
                    max_download_mb=settings.deps_max_download_mb,
                ),
                registry=build_package_registry(settings),
            )
        except Exception:  # noqa: BLE001 — research enrichment only, never blocks
            logger.warning(
                "[%s] paket araştırması başarısız: %s", project_id, sub.package, exc_info=True
            )
            continue
        if report.get("error"):
            continue
        sections.append(
            _dep_research_lines(
                sub.package, old, sub.target_version, report, paths_by_module, apis_by_module
            )
        )
    return "\n\n".join(sections) or None


def _clause_memory(ctx: AppContext, project_id: str | None) -> dict[str, dict]:
    """Clause-keyed precedent/dispute memory for the review panel — computed from
    the DB (single source of truth), never read back from wiki files."""
    try:
        cases = ctx.repo.list_cases(project_id)
        case_ids = {c.request_id for c in cases}
        overrides = [o for o in ctx.repo.list_overrides() if o.case_id in case_ids]
        return precedents_by_clause(cases, overrides)
    except Exception:  # noqa: BLE001 — a memory failure must not break the review screen
        logger.warning("[%s] madde hafızası hesaplanamadı", project_id, exc_info=True)
        return {}


@router.get("/ui/casefiles/{case_id}", response_class=HTMLResponse)
async def ui_casefile(
    request: Request,
    case_id: str,
    ctx: CtxDep,
    user: Annotated[dict[str, str], Depends(require_user)],
) -> HTMLResponse:
    case = ctx.repo.get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail=t("err.case_not_found"))
    # IDOR: access is derived from the case's project — another project's case yields 404.
    ensure_project_access(user, case.project_id, ctx.user_store)
    audit = ctx.repo.list_audit(case_id)
    project = _project_meta(ctx, case.project_id or "")
    return templates.TemplateResponse(
        request,
        "casefile.html",
        {"case": case, "audit": audit, "project": project,
         "pre_analysis_html": _pre_analysis_html(case),
         "chat_turns_html": _chat_turns_html(case),
         "clause_memory": _clause_memory(ctx, case.project_id),
         "dep_compare": _dep_compare_prefills(case.project_id, case),
         "deps_online": Settings().deps_online,
         "case_flow": _case_sankey(case.project_id, case)},
    )


@router.post("/ui/casefiles/{case_id}/decisions/{index}/{action}", response_class=HTMLResponse)
async def ui_action(
    request: Request,
    case_id: str,
    index: int,
    action: str,
    ctx: CtxDep,
    user: Annotated[dict[str, str], Depends(require_pmo)],
) -> HTMLResponse:
    if action not in _ACTION:
        raise HTTPException(status_code=400, detail=t("err.invalid_action"))
    case = ctx.repo.get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail=t("err.case_not_found"))
    ensure_project_access(user, case.project_id, ctx.user_store)
    engine = ctx.get_engine(case.project_id)
    try:
        result = ctx.approval.decide(
            case_id, index, _ACTION[action],
            actor=user["username"], current_baseline=engine.baseline,
        )
    except AlreadyDecidedError as exc:
        raise HTTPException(status_code=409, detail=t("err.already_decided")) from exc
    except IndexError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if result.new_scope_item is not None:
        # Living baseline: engine + index.json grow together (survives a restart).
        ctx.apply_baseline_bump(case.project_id, result.new_scope_item)
    # The decision may have created/changed clause memory → refresh the engine's
    # live dict so the NEXT triage already carries the precedent note.
    ctx.refresh_precedents(ctx.resolve_project(case.project_id))
    updated = ctx.repo.get_case(case_id)
    audit = ctx.repo.list_audit(case_id)
    return templates.TemplateResponse(
        request,
        "casefile_body.html",
        {"case": updated, "audit": audit,
         "project": _project_meta(ctx, case.project_id or ""),
         "pre_analysis_html": _pre_analysis_html(updated) if updated else None,
         "chat_turns_html": _chat_turns_html(updated) if updated else [],
         "clause_memory": _clause_memory(ctx, case.project_id),
         "dep_compare": _dep_compare_prefills(case.project_id, updated) if updated else [],
         "deps_online": Settings().deps_online,
         "case_flow": _case_sankey(updated.project_id, updated) if updated else None},
    )


@router.get("/ui/casefiles/{case_id}/report.docx")
async def ui_report(
    case_id: str, ctx: CtxDep, user: Annotated[dict[str, str], Depends(require_user)]
) -> Response:
    case = ctx.repo.get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail=t("err.case_not_found"))
    ensure_project_access(user, case.project_id, ctx.user_store)
    data = build_case_report(case, ctx.repo.list_audit(case_id))
    return Response(
        content=data,
        media_type=_DOCX_MIME,
        headers={"Content-Disposition": f'attachment; filename="rapor-{case_id}.docx"'},
    )


# ---------------------------------------------------------------------------
# Project Detail (Summary/Settings) — the sidebar returns to this project
# ---------------------------------------------------------------------------
@router.get("/projeler/{project_id}", response_class=HTMLResponse,
            dependencies=[Depends(require_project_access)])
async def project_detail(request: Request, project_id: str, ctx: CtxDep) -> Response:
    project = projects_store.get(project_id)
    if project is None:
        return RedirectResponse("/", status_code=303)

    idx = load_index(project.resolved_index_path())
    scope_items = idx.baseline.scope_items if idx else []
    excluded = sum(1 for s in scope_items if s.polarity.value == "EXCLUDED")
    repos = [
        {"name": r.name, "source": r.git_url or r.src_root or "—", "engine": r.engine}
        for r in project.resolved_repos()
    ]
    # Same provider-backed view as the Dosyalar screen (uploaded + connector
    # sources) so each row carries a previewable id; degrades to the plain
    # workspace listing if the provider fails.
    try:
        documents = await _documents_view(project)
    except Exception:
        logger.warning("[%s] doküman listesi sağlayıcıdan alınamadı", project_id, exc_info=True)
        documents = projects_store.list_documents(project_id)
    names = {project_id: project.name}
    cases = [_case_row(c, names) for c in reversed(ctx.repo.list_cases(project_id))][:8]

    # Dependency card: declared manifest deps + per-package usage (query-time).
    usage = match_packages(idx.dependencies, idx.modules) if idx else {}
    dependencies = [
        {"name": d.name, "spec": d.raw_spec or "*", "ecosystem": d.ecosystem,
         "dev": d.dev, "used_by": usage.get(d.name, [])}
        for d in (idx.dependencies if idx else [])
    ]

    p = {
        "id": project.id,
        "name": project.name,
        "contract_id": project.contract_id,
        "modules": len(idx.modules) if idx else 0,
        "clauses": len(scope_items),
        "included": len(scope_items) - excluded,
        "excluded": excluded,
        "baseline_version": idx.baseline.version if idx else 0,
        "freshness": idx.freshness if idx else "—",
        "freshness_days": _freshness_days(idx.freshness) if idx else None,
        "work_items": project.connectors.work_items.adapter,
        "indexed": idx is not None,
    }
    # Reports/KPI block merged into the summary (the old Raporlar screen);
    # a project whose engine failed to load degrades to a summary without KPIs.
    engine = ctx.engines.get(project_id)
    kpis = (
        compute_kpis(ctx.repo, engine.baseline, ctx.consumed.get(project_id, {}),
                     project_id=project_id)
        if engine is not None else None
    )
    return templates.TemplateResponse(
        request,
        "project_detail.html",
        {"p": p, "project": {"id": project.id, "name": project.name},
         "scope_items": scope_items, "repos": repos, "dependencies": dependencies,
         "deps_online": Settings().deps_online, "k": kpis,
         "documents": documents, "cases": cases, "monitor": _monitor(ctx),
         "degraded": ctx.degraded_adapters(project_id)},
    )


@router.get("/projeler/{project_id}/madde/{clause_id}", response_class=HTMLResponse,
            dependencies=[Depends(require_project_access)])
async def project_clause_detail(
    request: Request, project_id: str, clause_id: str, ctx: CtxDep
) -> Response:
    """Clause detail: the frozen clause + memory strip + every decision citing it.

    The contract-dispute view: 'what has been ruled on this clause so far'."""
    project = _project_meta(ctx, project_id)
    if project is None:
        return RedirectResponse("/", status_code=303)
    # Look the clause up in the engine's LIVE baseline first (DB-reconciled,
    # includes CR bumps immediately), then in the persisted index (the Özet
    # scope list renders from it) — the two can briefly differ.
    items: list[ScopeItem] = []
    engine = ctx.engines.get(project_id)
    if engine is not None:
        items.extend(engine.baseline.scope_items)
    store_proj = projects_store.get(project_id)
    idx = load_index(store_proj.resolved_index_path()) if store_proj else None
    if idx is not None:
        seen_ids = {s.id for s in items}
        items.extend(s for s in idx.baseline.scope_items if s.id not in seen_ids)
    clause = next((s for s in items if s.id == clause_id), None)
    if clause is None:
        return RedirectResponse(f"/projeler/{project_id}", status_code=303)

    # Decisions citing this clause — by frozen clause id or its contract ref.
    refs = {clause.id}
    if clause.source_clause:
        refs.add(clause.source_clause)
    names = {project_id: project["name"]}
    rows = []
    for c in reversed(ctx.repo.list_cases(project_id)):
        cited = any(
            refs & ({ci.id for ci in d.evidence.cited_clauses}
                    | set(d.evidence.contract_clauses_cited))
            for d in c.decisions
        )
        if cited:
            rows.append(_case_row(c, names))

    memory = (ctx.precedents.get(project_id) or {}).get(clause.id)
    pool_used = (
        (ctx.consumed.get(project_id) or {}).get(clause.category)
        if clause.effort_pool_hours else None
    )
    return templates.TemplateResponse(
        request,
        "clause_detail.html",
        {"project": project, "clause": clause,
         "rows": rows, "memory": memory, "pool_used": pool_used,
         "monitor": _monitor(ctx)},
    )


@router.get("/projeler/{project_id}/sor", response_class=HTMLResponse,
            dependencies=[Depends(require_project_access)])
async def project_ask(request: Request, project_id: str, ctx: CtxDep) -> Response:
    """Instant-answer screen (generic, developer included): free-text question
    over the project's knowledge graph, plus the LLM assistant when configured."""
    project = _project_meta(ctx, project_id)
    if project is None:
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(
        request,
        "project_ask.html",
        {"project": project, "llm": _llm_status(), "monitor": _monitor(ctx)},
    )


@router.post("/ui/ask", response_class=HTMLResponse)
async def ui_ask(
    request: Request,
    ctx: CtxDep,
    user: Annotated[dict[str, str], Depends(require_user)],
    question: Annotated[str, Form()],
    project_id: Annotated[str | None, Form()] = None,
) -> HTMLResponse:
    """One chat turn (HTMX fragment): the question bubble + the labeled
    deterministic graph answer, plus — when an LLM is configured — a stub that
    auto-loads the labeled assistant answer (/ui/ask-llm). One input, two
    sources, each answer tagged with where it came from."""
    pid = ctx.resolve_project(project_id)
    ensure_project_access(user, pid, ctx.user_store)
    project = projects_store.get(pid)
    index = load_index(project.resolved_index_path()) if project else None
    result = None
    nodes = []
    error = None
    if index is None:
        error = t("ask.no_index")
    else:
        work_items = build_work_items(project.connectors.work_items) if project else None
        items_fn = getattr(work_items, "all_items", None)
        items = items_fn() if items_fn is not None else []
        settings = Settings()
        gq = IndexGraphQuery(
            index, items,
            embedder=build_embedder(settings), llm=build_llm_client(settings),
            reranker=build_reranker(settings),
        )
        try:
            result = await gq.query(question, k=5)
            # Merge seed + subgraph nodes (dedup, seed order first).
            nodes = list(result.nodes)
            seen = {n.id for n in nodes}
            if result.subgraph is not None:
                nodes.extend(n for n in result.subgraph.nodes if n.id not in seen)
        except Exception:
            logger.warning("[%s] graf sorgusu başarısız", pid, exc_info=True)
            error = t("ask.failed")
    # The deterministic answer doubles as the assistant's retrieval context.
    graph_context = ""
    if result is not None:
        lines = [f"strategy: {result.strategy}"]
        lines += [f"- {n.id}: {n.text[:160]}" for n in nodes[:10]]
        if not nodes and result.tool_result is not None:
            lines.append(json.dumps(result.tool_result, ensure_ascii=False)[:600])
        graph_context = "\n".join(lines)[:1800]
    # Process log (best-effort): question → strategy → matched nodes, auditable
    # like the triage transcript. Free text may carry personal data; the file
    # lives under .etki/ (gitignored) — see docs/KVKK.md.
    try:
        log_event("ask", pid, {
            "question": question,
            "strategy": result.strategy if result else "hata",
            "nodes": [n.id for n in nodes[:10]],
        })
    except Exception:
        logger.warning("[%s] ask olayı loglanamadı", pid, exc_info=True)
    llm = _llm_status()
    return templates.TemplateResponse(
        request,
        "ask_turn.html",
        {"question": question, "result": result, "nodes": nodes, "error": error,
         "project_id": pid, "llm_follow": bool(llm and llm.get("enabled")),
         "graph_context": graph_context},
    )


@router.post("/ui/ask-llm", response_class=HTMLResponse)
async def ui_ask_llm(
    request: Request,
    ctx: CtxDep,
    user: Annotated[dict[str, str], Depends(require_writer)],
    question: Annotated[str, Form()],
    project_id: Annotated[str | None, Form()] = None,
    context: Annotated[str, Form()] = "",
) -> HTMLResponse:
    """The AI half of an ask turn (auto-loaded after the graph answer): the
    agent gets the deterministic graph result as retrieval context and answers
    with the index tools, labeled as the LLM source."""
    pid = ctx.resolve_project(project_id)
    ensure_project_access(user, pid, ctx.user_store)
    prompt = _ASK_PROMPT.format(
        context=wrap_untrusted(context) if context else "(yok)",
        question=wrap_untrusted(question),
    )
    answer = ""
    try:
        answer = await agent_ask(prompt, _project_tools(pid), **_project_llm_args(pid))
        answer_html = _MD.render(answer)
    except Exception:
        logger.warning("[%s] Sor asistan yanıtı üretilemedi", pid, exc_info=True)
        answer_html = f'<p class="meta">⚠ {t("err.assistant_unavailable")}</p>'
    try:
        log_event("ask_llm", pid, {
            "question": question,
            "answer": answer or "(yanıt üretilemedi)",
            "grounded": bool(context),
        })
    except Exception:
        logger.warning("[%s] ask_llm olayı loglanamadı", pid, exc_info=True)
    llm = _llm_status()
    return templates.TemplateResponse(
        request,
        "ask_llm_result.html",
        {"answer_html": answer_html, "model": (llm or {}).get("model", ""),
         "grounded": bool(context)},
    )


@router.get("/projeler/{project_id}/baseline", response_class=HTMLResponse,
            dependencies=[Depends(require_project_access)])
async def project_baseline_timeline(
    request: Request, project_id: str, ctx: CtxDep
) -> Response:
    """Baseline version timeline: which approved CR added which clause, when.

    v1 is the contract itself; every bumped version is read back from the
    persisted baseline_versions history."""
    project = _project_meta(ctx, project_id)
    if project is None:
        return RedirectResponse("/", status_code=303)
    engine = ctx.engines.get(project_id)
    current = engine.baseline if engine is not None else None
    versions = ctx.repo.list_baseline_versions(current.contract_id) if current else []

    entries = []
    prev_ids: set[str] | None = None
    for b in versions:
        if prev_ids is None:
            # v1 is not stored; the first bumped version diffs against the
            # contract items — the CR-prefixed items are what CRs appended.
            added = [s for s in b.scope_items if s.id.startswith("CR-")]
        else:
            added = [s for s in b.scope_items if s.id not in prev_ids]
        # The appended CR item carries the source case in its id: CR-{case_id}-{i}.
        case_id = None
        for s in added:
            if s.id.startswith("CR-") and s.id.count("-") >= 2:
                case_id = s.id[3:].rsplit("-", 1)[0]
        entries.append({
            "version": b.version,
            "at": b.locked_at.strftime("%Y-%m-%d %H:%M") if b.locked_at else "—",
            "added": added,
            "case_id": case_id,
            "item_count": len(b.scope_items),
        })
        prev_ids = {s.id for s in b.scope_items}
    entries.reverse()  # newest first
    return templates.TemplateResponse(
        request,
        "baseline_timeline.html",
        {"project": project, "entries": entries,
         "current_version": current.version if current else 0,
         "initial_count": (
             len([s for s in current.scope_items if not s.id.startswith("CR-")])
             if current else 0
         ),
         "monitor": _monitor(ctx)},
    )


@router.get("/projeler/{project_id}/indeks-gecmisi", response_class=HTMLResponse,
            dependencies=[Depends(require_project_access)])
async def project_index_history(
    request: Request, project_id: str, ctx: CtxDep
) -> Response:
    """HTMX fragment: recent index runs of this project (from the process log)."""
    events = [
        e for e in read_events()
        if e.get("kind") == "index" and e.get("project_id") == project_id
    ][-10:]
    events.reverse()
    return templates.TemplateResponse(
        request, "index_history.html", {"events": events}
    )


@router.get("/projeler/{project_id}/havuz/{category}", response_class=HTMLResponse,
            dependencies=[Depends(require_project_access)])
async def project_pool_breakdown(
    request: Request, project_id: str, category: str, ctx: CtxDep
) -> Response:
    """HTMX fragment: which work items consumed a category's effort pool.

    Same source as refresh_pools — providers without all_items() degrade to an
    honest empty message."""
    provider = ctx.work_item_providers.get(project_id)
    items_fn = getattr(provider, "all_items", None)
    items = []
    if items_fn is not None:
        try:
            items = [
                {"id": i.id, "title": i.title, "hours": i.effort_seconds / 3600}
                for i in items_fn()
                if i.category == category and i.effort_seconds
            ]
        except Exception:
            logger.warning("[%s] havuz dökümü alınamadı", project_id, exc_info=True)
    items.sort(key=lambda i: -i["hours"])
    return templates.TemplateResponse(
        request,
        "pool_breakdown.html",
        {"items": items, "category": category,
         "total": sum(i["hours"] for i in items)},
    )


@router.get("/projeler/{project_id}/moduller", response_class=HTMLResponse,
            dependencies=[Depends(require_project_access)])
async def project_modules(
    request: Request, project_id: str, ctx: CtxDep, repo: str | None = None
) -> Response:
    """Module table: the code knowledge graph opened up — metrics, mapped
    clauses and the decisions that touched each module. ?repo= filters by the
    repo namespace on multi-repo projects (module ids are 'repo:module')."""
    project = _project_meta(ctx, project_id)
    if project is None:
        return RedirectResponse("/", status_code=303)
    store_proj = projects_store.get(project_id)
    idx = load_index(store_proj.resolved_index_path()) if store_proj else None
    modules = idx.modules if idx else []

    # Decisions per module — from each decision's frozen impacted_modules.
    names = {project_id: project["name"]}
    touched: dict[str, list[dict]] = {}
    for c in reversed(ctx.repo.list_cases(project_id)):
        mods = {m for d in c.decisions for m in d.evidence.impacted_modules}
        if not mods:
            continue
        row = _case_row(c, names)
        for m in mods:
            touched.setdefault(m, []).append(row)

    rows: list[dict[str, Any]] = [
        {
            "id": m.id, "path": m.path,
            "loc": m.complexity.loc, "cyclo": m.complexity.cyclomatic,
            "files": m.complexity.files, "churn": m.churn.commits_last_6mo,
            "deps": len(m.depends_on), "rdeps": len(m.depended_by),
            "clauses": m.mapped_scope_items, "packages": m.packages,
            "cases": touched.get(m.id, [])[:5],
            "case_count": len(touched.get(m.id, [])),
            "stale": False,
        }
        for m in modules
    ]
    # Modules cited by frozen decisions but absent from the current index
    # (e.g. removed by a re-index) still get an audit row, without metrics.
    known = {m.id for m in modules}
    for mid in sorted(set(touched) - known):
        rows.append({
            "id": mid, "path": "", "loc": 0, "cyclo": 0, "files": 0, "churn": 0,
            "deps": 0, "rdeps": 0, "clauses": [], "packages": [],
            "cases": touched[mid][:5], "case_count": len(touched[mid]),
            "stale": True,
        })
    rows.sort(key=lambda r: (-r["case_count"], -r["loc"]))
    # Repo filter is meaningful only when ids are namespaced (multi-repo).
    if repo and any(":" in r["id"] for r in rows):
        rows = [r for r in rows if r["id"].startswith(f"{repo}:")]
    else:
        repo = None
    return templates.TemplateResponse(
        request,
        "project_modules.html",
        {"project": project, "rows": rows, "repo": repo, "monitor": _monitor(ctx)},
    )


@router.get("/projeler/{project_id}/bagimliliklar/guncel", response_class=HTMLResponse,
            dependencies=[Depends(require_project_access)])
async def project_deps_online(request: Request, project_id: str, ctx: CtxDep) -> Response:
    """Click-to-load HTMX fragment: registry latest versions next to the raw
    specs. Query-time only (never persisted); off or failing registry → the
    manifest facts stand alone."""
    from etki.adapters.package_registries import enrich_dependencies
    from etki.adapters.registry import build_package_registry

    project = projects_store.get(project_id)
    idx = load_index(project.resolved_index_path()) if project else None
    provider = build_package_registry(Settings())
    if idx is None or provider is None:
        return HTMLResponse(
            f'<p class="meta" style="margin:6px 0 0;">{t("deps.online_off")}</p>'
        )
    rows = await enrich_dependencies(idx.dependencies, provider)
    return templates.TemplateResponse(request, "deps_online.html", {"rows": rows})


@router.get("/projeler/{project_id}/bagimliliklar/karsilastir", response_class=HTMLResponse,
            dependencies=[Depends(require_project_access)])
async def project_deps_compare(
    request: Request,
    project_id: str,
    ctx: CtxDep,
    package: str,
    old: str,
    new: str,
) -> Response:
    """Version-comparison fragment: your_code (this project's qualified import
    paths vs both versions' full surfaces), exact-version OSV vulnerabilities
    and the exported-API summary — the same report the MCP tool returns,
    rendered for the Bağımlılıklar card."""
    from etki.adapters.package_download import PackageFetcher, version_diff_report
    from etki.adapters.registry import build_package_registry

    settings = Settings()
    if not settings.deps_online:
        return HTMLResponse(
            f'<p class="meta" style="margin:6px 0 0;">{t("deps.online_off")}</p>'
        )
    project = projects_store.get(project_id)
    idx = load_index(project.resolved_index_path()) if project else None
    if idx is None:
        return HTMLResponse(f'<p class="meta">{t("deps.none")}</p>')
    impact = IndexTools(idx).dependency_impact(package)
    report = await version_diff_report(
        package.strip(), old.strip(), new.strip(),
        used_paths=sorted({p for ps in impact["used_api_paths"].values() for p in ps}),
        used_symbols=sorted({s for ss in impact["used_apis"].values() for s in ss}),
        fetcher=PackageFetcher(
            pypi_base_url=settings.pypi_base_url,
            timeout=settings.deps_download_timeout,
            max_download_mb=settings.deps_max_download_mb,
        ),
        registry=build_package_registry(settings),
    )
    return templates.TemplateResponse(request, "deps_diff.html", {"r": report})


# ---------------------------------------------------------------------------
# History (project-scoped: analysis + triage history; tab filters replace the
# old separate Analyses screen — approved case = analysis)
# ---------------------------------------------------------------------------
@router.get("/projeler/{project_id}/gecmis", response_class=HTMLResponse,
            dependencies=[Depends(require_project_access)])
async def project_history(
    request: Request, project_id: str, ctx: CtxDep, filtre: str | None = None,
    karar: str | None = None,
) -> Response:
    project = _project_meta(ctx, project_id)
    if project is None:
        return RedirectResponse("/", status_code=303)
    names = {project_id: project["name"]}
    rows = []
    for c in reversed(ctx.repo.list_cases(project_id)):
        row = _case_row(c, names)
        row["decisions"] = row["decision_values"]
        row["has_pre_analysis"] = bool(c.pre_analysis)
        row["is_pending"] = c.status == PmoDecision.PENDING
        row["is_analysis"] = c.status == PmoDecision.APPROVE  # approved = analysis
        rows.append(row)
    counts = {
        "all": len(rows),
        "bekleyen": sum(1 for r in rows if r["is_pending"]),
        "analiz": sum(1 for r in rows if r["is_analysis"]),
    }
    if filtre == "bekleyen":
        rows = [r for r in rows if r["is_pending"]]
    elif filtre == "analiz":
        rows = [r for r in rows if r["is_analysis"]]
    else:
        filtre = ""
    # Decision-type filter (?karar=OUT_OF_SCOPE) — the Özet distribution badges
    # link here; composes with the tab filter. Unknown values are ignored.
    if karar in {d.value for d in Decision}:
        rows = [r for r in rows if karar in r["decisions"]]
    else:
        karar = ""
    return templates.TemplateResponse(
        request,
        "project_history.html",
        {"project": project, "rows": rows, "filtre": filtre, "karar": karar,
         "counts": counts, "monitor": _monitor(ctx)},
    )


# ---------------------------------------------------------------------------
# Memory (project-scoped: decision wiki + precedents + disputed clauses)
# ---------------------------------------------------------------------------
@router.get("/projeler/{project_id}/hafiza", response_class=HTMLResponse,
            dependencies=[Depends(require_project_access)])
async def project_memory(
    request: Request,
    project_id: str,
    ctx: CtxDep,
    q: str | None = None,
) -> Response:
    """Decision-memory screen: precedents + disputed clauses come from the DB
    (single source of truth, works even with the wiki off); search runs over
    the wiki projection. The plain decision list lives under History."""
    project = _project_meta(ctx, project_id)
    if project is None:
        return RedirectResponse("/", status_code=303)
    cases = ctx.repo.list_cases(project_id)
    case_ids = {c.request_id for c in cases}
    by_request = {c.request_id: c.raw_request for c in cases}
    wiki_docs = ctx.wiki.list_decisions(project_id)[:10] if ctx.wiki is not None else []
    precedents = [
        {
            "case_id": o.case_id,
            "request": by_request.get(o.case_id, ""),
            "system": o.system_decision.value,
            "human": o.human_decision.value,
            "actor": o.actor,
            "at": o.at.strftime("%Y-%m-%d") if o.at else "",
        }
        for o in ctx.repo.list_overrides()
        if o.case_id in case_ids
    ]
    disputes = derive_disputes(cases)
    wiki = ctx.wiki
    hits = wiki.search(project_id, q) if (wiki is not None and q) else []
    return templates.TemplateResponse(
        request,
        "project_hafiza.html",
        {"project": project, "q": q or "", "hits": hits,
         "precedents": precedents, "disputes": disputes, "wiki_on": wiki is not None,
         "wiki_docs": wiki_docs, "monitor": _monitor(ctx)},
    )


_WIKI_DOC_ID = re.compile(r"DEC-[\w-]+\Z")


@router.get("/projeler/{project_id}/hafiza/dosya/{doc_id}", response_class=HTMLResponse,
            dependencies=[Depends(require_project_access)])
async def project_memory_doc(
    request: Request, project_id: str, doc_id: str, ctx: CtxDep
) -> Response:
    """One wiki decision file rendered as an HTMX fragment (projection view —
    the DB stays the source of truth). The adapter path-joins doc_id, so only
    the DEC-… shape is accepted (traversal guard)."""
    if ctx.wiki is None or not _WIKI_DOC_ID.fullmatch(doc_id):
        raise HTTPException(status_code=404, detail=t("err.case_not_found"))
    text = ctx.wiki.read_decision(project_id, doc_id)
    if text is None:
        raise HTTPException(status_code=404, detail=t("err.case_not_found"))
    # Strip the YAML frontmatter (its fields already render in the list card).
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end != -1:
            text = text[end + 5:]
    return templates.TemplateResponse(
        request, "wiki_doc.html", {"doc_id": doc_id, "html": _MD.render(text)},
    )


# ---------------------------------------------------------------------------
# Analyses — folded into History as a tab (2026-07); the old URL redirects.
# ---------------------------------------------------------------------------
@router.get("/projeler/{project_id}/analizler",
            dependencies=[Depends(require_project_access)])
async def project_analyses(project_id: str) -> Response:
    return RedirectResponse(
        f"/projeler/{project_id}/gecmis?filtre=analiz", status_code=303,
    )


# ---------------------------------------------------------------------------
# Flow (project scope: Request/Analysis → Requirement → Code interaction Sankey diagram)
# ---------------------------------------------------------------------------
_SANKEY_CASE_LIMIT = 60  # last N requests, for readability


def _short(text: str, limit: int = 46) -> str:
    return text[:limit] + ("…" if len(text) > limit else "")


def _sankey_index_maps(project_id: str) -> tuple[dict[str, tuple[str, str, str]], dict[str, str]]:
    """Clause-ref (source_clause→(id, description, polarity)) and module (id→path) maps
    from the index.

    Old/string citations (carrying only a clause ref like 'Madde 7.1') are enriched with this."""
    project = projects_store.get(project_id)
    index = load_index(project.resolved_index_path()) if project else None
    clause_by_ref: dict[str, tuple[str, str, str]] = {}
    module_label: dict[str, str] = {}
    if index is not None:
        for s in index.baseline.scope_items:
            if s.source_clause:
                clause_by_ref[s.source_clause] = (s.id, s.description, s.polarity.value)
        for m in index.modules:
            module_label[m.id] = m.path or m.id
    return clause_by_ref, module_label


def _build_sankey(
    cases: list[CaseFile],
    clause_by_ref: dict[str, tuple[str, str, str]],
    module_label: dict[str, str],
) -> dict:
    """3-layer Sankey data from the given cases: Request/Analysis → Requirement → Code module.

    Requirement nodes are labeled from the decision's **frozen full clause**
    (`evidence.cited_clauses`) — clause ref (`ref`) + full description (`full`) + the correct
    polarity color. Code links come from the actually impacted modules
    (`evidence.impacted_modules`)."""
    nodes: dict[str, dict] = {}
    links: dict[tuple[str, str], int] = {}

    def add_node(nid: str, name: str, layer: int, color: str, kind: str,
                 ref: str = "", full: str = "") -> None:
        nodes.setdefault(nid, {"id": nid, "name": name, "layer": layer, "color": color,
                               "kind": kind, "ref": ref, "full": full or name})

    def add_link(src: str, tgt: str) -> None:
        links[(src, tgt)] = links.get((src, tgt), 0) + 1

    none_clause = "c:__none__"
    for c in cases:
        rnode = f"r:{c.request_id}"
        decs = [d.decision for d in c.decisions]
        dom = Counter(decs).most_common(1)[0][0] if decs else None
        color = _DECISION_COLORS.get(dom, ("#55666D", ""))[0] if dom is not None else "#55666D"
        add_node(rnode, _short(c.raw_request), 0, color, "talep", full=c.raw_request)
        for d in c.decisions:
            modules = list(dict.fromkeys(d.evidence.impacted_modules))
            # Preference: frozen full clauses; otherwise enrich string citations from
            # the index.
            clause_specs: list[tuple[str, str, str, str]] = []  # (id, ref, desc, polarity)
            for ci in d.evidence.cited_clauses:
                clause_specs.append(
                    (ci.id, ci.source_clause or ci.id, ci.description, ci.polarity.value)
                )
            if not clause_specs:
                for ref in dict.fromkeys(d.evidence.contract_clauses_cited):
                    cid, desc, pol = clause_by_ref.get(ref, (ref, ref, "INCLUDED"))
                    clause_specs.append((cid, ref, desc, pol))

            targets = clause_specs or [("__none__", "", "(eşleşme yok)", "NONE")]
            for cid, ref, desc, pol in targets:
                cnode = none_clause if cid == "__none__" else f"c:{cid}"
                ccolor = ("#93A0A4" if pol == "NONE"
                          else "#C6413A" if pol == "EXCLUDED" else "#2E9E5B")
                label = _short(desc)
                add_node(cnode, label, 1, ccolor, "ister", ref=ref, full=desc)
                add_link(rnode, cnode)
                for mod in modules:
                    mnode = f"m:{mod}"
                    path = module_label.get(mod, mod)
                    # Label by the last path segment ("reporting/report.py" clipped to
                    # "reporting/" read as noise); the full path stays in the tooltip.
                    name = path.rstrip("/").rsplit("/", 1)[-1] or mod
                    add_node(mnode, _short(name), 2, "#3563B0", "kod", full=path)
                    add_link(cnode, mnode)

    return {
        "nodes": list(nodes.values()),
        "links": [{"source": s, "target": t, "value": v} for (s, t), v in links.items()],
    }


def _sankey_data(ctx: AppContext, project_id: str) -> dict:
    """Project-scoped Sankey (last N requests)."""
    clause_by_ref, module_label = _sankey_index_maps(project_id)
    all_cases = list(reversed(ctx.repo.list_cases(project_id)))
    data = _build_sankey(all_cases[:_SANKEY_CASE_LIMIT], clause_by_ref, module_label)
    data["truncated"] = len(all_cases) > _SANKEY_CASE_LIMIT
    data["total"] = len(all_cases)
    return data


def _case_sankey(project_id: str | None, case: CaseFile) -> dict:
    """Flow diagram data for a single triage (that case's Request→Requirement→Code flow)."""
    clause_by_ref, module_label = _sankey_index_maps(project_id or "")
    return _build_sankey([case], clause_by_ref, module_label)


@router.get("/projeler/{project_id}/akis", response_class=HTMLResponse,
            dependencies=[Depends(require_project_access)])
async def project_sankey(request: Request, project_id: str, ctx: CtxDep) -> Response:
    project = _project_meta(ctx, project_id)
    if project is None:
        return RedirectResponse("/", status_code=303)
    data = _sankey_data(ctx, project_id)
    return templates.TemplateResponse(
        request,
        "project_sankey.html",
        {"project": project, "data": data, "monitor": _monitor(ctx)},
    )


# ---------------------------------------------------------------------------
# Reports (project scope: KPI / Scorecard)
# ---------------------------------------------------------------------------
@router.get("/projeler/{project_id}/raporlar", response_class=HTMLResponse,
            dependencies=[Depends(require_project_access)])
async def project_raporlar(request: Request, project_id: str, ctx: CtxDep) -> Response:
    """The Raporlar screen was merged into the project summary (2026-07); old links redirect."""
    return RedirectResponse(f"/projeler/{project_id}", status_code=303)


# ---------------------------------------------------------------------------
# Files / Repos / Settings (project scope) — mutations are pmo-only; every change reindexes
# ---------------------------------------------------------------------------
_PREVIEW_LIMIT = 20000  # max characters shown in the preview


async def _documents_view(project: ProjectConfig) -> list[dict]:
    """ALL of the project's documents (uploaded + pulled from source) — with preview/delete
    flags.

    The document provider port (composite/filesystem) covers both doc_root uploads and
    connector sources; deletion is only available for uploaded (doc_root) files."""
    provider = build_documents(project.documents_connector())
    doc_root = str(Path(project.doc_root).resolve()) if project.doc_root else None
    out: list[dict] = []
    for d in await provider.list_documents():
        try:
            size: int | None = Path(d.path).stat().st_size
        except OSError:
            size = None
        deletable = bool(doc_root and str(Path(d.path).resolve()).startswith(doc_root))
        out.append({"id": d.id, "name": d.name, "size": size,
                    "source": d.source, "deletable": deletable})
    return out


async def _files_context(
    ctx: AppContext,
    project: ProjectConfig,
    error: str | None = None,
    attempted_adapter: str | None = None,
    attempted_opts: dict | None = None,
    attempted_intake_adapter: str | None = None,
    attempted_intake_opts: dict | None = None,
    attempted_intake_mode: str | None = None,
) -> dict:
    repos = [
        {"name": r.name, "source": r.git_url or r.src_root or "—", "engine": r.engine}
        for r in project.resolved_repos()
    ]
    wi = project.connectors.work_items
    adapter_sel = attempted_adapter or wi.adapter
    intake = project.connectors.request_intake
    intake_sel = attempted_intake_adapter or intake.adapter
    intake_mode = attempted_intake_mode or project.intake_response_mode
    # A broken documents connector must not take the settings screen down with it —
    # that is exactly the screen where the connector gets fixed.
    try:
        documents = await _documents_view(project)
    except Exception:
        logger.warning("[%s] doküman listesi sağlayıcıdan alınamadı", project.id, exc_info=True)
        documents = projects_store.list_documents(project.id)
    return {
        "project": {"id": project.id, "name": project.name},
        "documents": documents,
        "repos": repos,
        "work_items": {"adapter": adapter_sel, "options": wi.options},
        # Builtins + active plugins; "fake" is a test double, not a real choice.
        # A pre-configured adapter that is unlisted (e.g. its plugin got disabled)
        # still shows as selected — the template appends it.
        "work_item_adapters": [a for a in available_adapters("work_items") if a != "fake"],
        "intake": {"adapter": intake_sel, "mode": intake_mode},
        "intake_adapters": [a for a in available_adapters("request_intake") if a != "fake"],
        "intake_modes": ["on_decision", "on_triage", "both"],
        "degraded": ctx.degraded_adapters(project.id),
        **_wi_form_context(project, adapter_sel, attempted=attempted_opts),
        **_intake_form_context(project, intake_sel, attempted=attempted_intake_opts),
        "llm_profile": {
            "language": project.language,
            "domain_profile": project.domain_profile or "",
            "instructions": project.instructions,
            "pivot_language": project.pivot_language or "",
        },
        "available_domains": list_domain_profiles(),
        "llm": _llm_status(),
        "error": error,
        "monitor": _monitor(ctx),
    }


def _parse_options(text: str) -> dict[str, str]:
    """Converts free-form 'key: value' lines into an adapter options dict."""
    opts: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        key, _, val = line.partition(":")
        if key.strip():
            opts[key.strip()] = val.strip()
    return opts


def _schema_fields(
    model: type[BaseModel], current: dict, *, mask_secrets: bool = False
) -> list[dict]:
    """Structured form fields from an options-model JSON schema.

    Values render AS STORED: an `env:VAR` secret reference stays a reference —
    resolved values never reach a form field. With `mask_secrets` (the plugin
    defaults page), credential-named fields render as EMPTY password inputs
    (`has_stored` drives the "kayıtlı" placeholder; empty submit keeps the
    stored value — the llm.json idiom)."""
    from etki.plugin.options_store import is_secret_field

    schema = model.model_json_schema()
    required = set(schema.get("required", []))
    fields: list[dict] = []
    for name, prop in schema.get("properties", {}).items():
        ftype = prop.get("type")
        if ftype == "boolean":
            input_type = "checkbox"
        elif ftype in ("number", "integer"):
            input_type = "number"
        else:  # strings, unions (anyOf), anything exotic → plain text
            input_type = "text"
        value = current.get(name, prop.get("default", ""))
        # env: references are pointers, not secrets — they stay visible (U4 rule);
        # only LITERAL values of secret-named fields are masked.
        is_env_ref = isinstance(value, str) and value.startswith("env:")
        secret = (
            mask_secrets and input_type == "text" and is_secret_field(name) and not is_env_ref
        )
        fields.append(
            {
                "name": name,
                "input_type": "password" if secret else input_type,
                "required": name in required,
                "value": "" if (secret or value is None) else str(value),
                "checked": bool(value) if input_type == "checkbox" else False,
                "secret": secret,
                "has_stored": secret and bool(current.get(name)),
            }
        )
    return fields


def _wi_form_fields(adapter: str, current: dict) -> list[dict] | None:
    """U4 work-items form: None → no model → free-form textarea fallback."""
    model = options_model_for("work_items", adapter)
    if model is None:
        return None
    return _schema_fields(model, current, mask_secrets=True)


def _wi_form_context(
    project: ProjectConfig,
    adapter: str,
    mode: str = "auto",
    attempted: dict | None = None,
) -> dict:
    """Context for the work_items_form.html fragment. `attempted` carries the
    user's rejected values back into the form (a validation 400 must not lose
    what was typed); otherwise the STORED options prefill — only when the
    selected adapter is the configured one (switching adapters starts clean)."""
    current = project.connectors.work_items
    opts = attempted if attempted is not None else (
        current.options if adapter == current.adapter else {}
    )
    fields = None if mode == "raw" else _wi_form_fields(adapter, opts)
    return {
        "wi_fields": fields,
        "wi_raw": "".join(
            f"{k}: {'' if is_secret_field(k) and not str(v).startswith('env:') else v}\n"
            for k, v in opts.items()
        ),
    }


def _intake_form_fields(adapter: str, current: dict) -> list[dict] | None:
    """Request-intake form: None → no model → free-form textarea fallback."""
    model = options_model_for("request_intake", adapter)
    if model is None:
        return None
    return _schema_fields(model, current, mask_secrets=True)


def _intake_form_context(
    project: ProjectConfig,
    adapter: str,
    mode: str = "auto",
    attempted: dict | None = None,
) -> dict:
    """Context for the intake_form.html fragment (twin of _wi_form_context)."""
    current = project.connectors.request_intake
    opts = attempted if attempted is not None else (
        current.options if adapter == current.adapter else {}
    )
    fields = None if mode == "raw" else _intake_form_fields(adapter, opts)
    return {
        "intake_fields": fields,
        "intake_raw": "".join(
            f"{k}: {'' if is_secret_field(k) and not str(v).startswith('env:') else v}\n"
            for k, v in opts.items()
        ),
    }


@router.get("/projeler/{project_id}/dosyalar", response_class=HTMLResponse,
            dependencies=[Depends(require_project_access)])
async def project_files(request: Request, project_id: str, ctx: CtxDep) -> Response:
    project = projects_store.get(project_id)
    if project is None:
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(
        request, "project_files.html", await _files_context(ctx, project)
    )


@router.get("/projeler/{project_id}/dosyalar/onizle", response_class=HTMLResponse,
            dependencies=[Depends(require_project_access)])
async def project_file_preview(
    request: Request, project_id: str, ctx: CtxDep, doc: str
) -> HTMLResponse:
    """Previews the content of a document (uploaded or pulled from source) (HTMX fragment)."""
    project = projects_store.get(project_id)
    if project is None:
        return _error_fragment(t("err.project_not_found"))
    provider = build_documents(project.documents_connector())
    # Only ids listed by the provider are read (no arbitrary path access).
    refs = {d.id: d for d in await provider.list_documents()}
    ref = refs.get(doc)
    if ref is None:
        return _error_fragment(t("err.doc_not_found"))
    try:
        raw = await provider.fetch_content(doc)
    except Exception:
        logger.warning("[%s] belge önizlenemedi: %s", project_id, doc, exc_info=True)
        return _error_fragment(t("err.doc_unreadable"))
    text = raw.decode("utf-8", errors="replace")
    truncated = len(text) > _PREVIEW_LIMIT
    return templates.TemplateResponse(
        request,
        "document_preview.html",
        {"name": ref.name, "source": ref.source, "text": text[:_PREVIEW_LIMIT],
         "truncated": truncated},
    )


@router.post("/projeler/{project_id}/dosyalar/upload",
             dependencies=[Depends(require_pmo), Depends(require_project_access)])
async def project_files_upload(
    request: Request, project_id: str, ctx: CtxDep, files: list[UploadFile]
) -> Response:
    project = projects_store.get(project_id)
    if project is None:
        return RedirectResponse("/", status_code=303)
    if len(files) > _MAX_UPLOAD_FILES:
        err = t("err.too_many_files", n=_MAX_UPLOAD_FILES)
        return templates.TemplateResponse(
            request, "project_files.html", (await _files_context(ctx, project, error=err)),
            status_code=400,
        )
    payloads: list[tuple[str, bytes]] = []
    for f in files:
        raw = await _read_upload_bounded(f)
        if raw is None:
            return templates.TemplateResponse(
                request, "project_files.html",
                (await _files_context(
                    ctx, project, error=t("err.file_too_large", mb=Settings().max_upload_mb)
                )),
                status_code=400,
            )
        if not raw:
            continue
        payloads.append((f.filename or "yukleme.txt", raw))
    if not payloads:
        return RedirectResponse(f"/projeler/{project_id}/dosyalar", status_code=303)
    try:
        # Parse (docx/pdf) is CPU-bound sync work — off the event loop.
        await run_in_threadpool(projects_store.add_documents, project_id, payloads)
    except ValueError as exc:
        return templates.TemplateResponse(
            request, "project_files.html", (await _files_context(ctx, project, error=str(exc))),
            status_code=400,
        )
    await _reindex(project_id)
    return RedirectResponse(f"/projeler/{project_id}/dosyalar", status_code=303)


@router.post("/projeler/{project_id}/dosyalar/{filename}/sil",
             dependencies=[Depends(require_pmo), Depends(require_project_access)])
async def project_file_delete(
    request: Request, project_id: str, filename: str, ctx: CtxDep
) -> Response:
    if projects_store.get(project_id) is None:
        return RedirectResponse("/", status_code=303)
    projects_store.delete_document(project_id, filename)
    await _reindex(project_id)
    return RedirectResponse(f"/projeler/{project_id}/dosyalar", status_code=303)


@router.post("/projeler/{project_id}/repolar/ekle",
             dependencies=[Depends(require_pmo), Depends(require_project_access)])
async def project_repo_add(
    request: Request,
    project_id: str,
    ctx: CtxDep,
    name: Annotated[str, Form()],
    git_url: Annotated[str, Form()] = "",
    src_root: Annotated[str, Form()] = "",
    engine: Annotated[str, Form()] = "ast",
) -> Response:
    project = projects_store.get(project_id)
    if project is None:
        return RedirectResponse("/", status_code=303)
    try:
        # Clone runs a git subprocess (up to minutes) — keep it off the single
        # worker's event loop (health probes must stay responsive).
        await run_in_threadpool(
            projects_store.add_repo,
            project_id, name.strip(),
            git_url=git_url.strip() or None, src_root=src_root.strip() or None, engine=engine,
        )
    except Exception as exc:  # ValueError (validation) or git clone error → graceful feedback
        logger.warning("[%s] repo eklenemedi", project_id, exc_info=True)
        ctx_data = await _files_context(ctx, project, error=t("err.repo_add_failed", exc=exc))
        return templates.TemplateResponse(
            request, "project_files.html", ctx_data, status_code=400,
        )
    await _reindex(project_id)
    return RedirectResponse(f"/projeler/{project_id}/dosyalar", status_code=303)


@router.post("/projeler/{project_id}/repolar/{name}/sil",
             dependencies=[Depends(require_pmo), Depends(require_project_access)])
async def project_repo_delete(
    request: Request, project_id: str, name: str, ctx: CtxDep
) -> Response:
    if projects_store.get(project_id) is None:
        return RedirectResponse("/", status_code=303)
    projects_store.delete_repo(project_id, name)
    await _reindex(project_id)
    return RedirectResponse(f"/projeler/{project_id}/dosyalar", status_code=303)


@router.get("/projeler/{project_id}/ayarlar/work-items/form", response_class=HTMLResponse,
            dependencies=[Depends(require_project_access)])
async def project_work_items_form(
    request: Request, project_id: str, adapter: str = "", mode: str = "auto"
) -> Response:
    """Options-form fragment for the selected adapter (HTMX, read-only render).

    Typed fields come from the adapter's options_model JSON schema; no model or
    ?mode=raw → the free-form textarea. Saving still goes through the one POST."""
    project = projects_store.get(project_id)
    if project is None:
        return _error_fragment(t("err.project_not_found"))
    return templates.TemplateResponse(
        request,
        "work_items_form.html",
        {"project": {"id": project.id}, **_wi_form_context(project, adapter, mode=mode)},
    )


@router.post("/projeler/{project_id}/ayarlar/work-items",
             dependencies=[Depends(require_pmo), Depends(require_project_access)])
async def project_work_items(
    request: Request,
    project_id: str,
    ctx: CtxDep,
    adapter: Annotated[str, Form()],
    options: Annotated[str, Form()] = "",
) -> Response:
    project = projects_store.get(project_id)
    if project is None:
        return RedirectResponse("/", status_code=303)

    async def _reject(message: str, opts: dict | None = None) -> Response:
        return templates.TemplateResponse(
            request, "project_files.html",
            (await _files_context(ctx, project, error=message,
                                  attempted_adapter=adapter, attempted_opts=opts)),
            status_code=400,
        )

    # The UI form is the narrow surface: only names the registry can resolve
    # RIGHT NOW are accepted (a not-yet-installed plugin name goes in via YAML).
    if adapter not in available_adapters("work_items"):
        return await _reject(t(
            "pf.unknown_adapter", name=adapter,
            known=", ".join(a for a in available_adapters("work_items") if a != "fake"),
        ))
    form = await request.form()
    if "options" in form:  # free-form textarea (advanced mode / adapters without a model)
        opts: dict = _parse_options(options)
    else:  # typed fields; empty optionals are dropped so model defaults apply
        opts = {
            k[4:]: str(v)
            for k, v in form.items()
            if k.startswith("opt_") and str(v).strip() != ""
        }
    # Secret fields render masked/empty — an empty submit means "keep the stored
    # value", never "wipe it" (the plugin options-store idiom).
    stored_wi = project.connectors.work_items
    if adapter == stored_wi.adapter:
        for key, val in stored_wi.options.items():
            if is_secret_field(key) and not str(opts.get(key, "")).strip():
                opts[key] = val
    # Validate against the options model when one exists — WITHOUT resolving
    # env: references (whether the variable exists is the deployment's concern,
    # not the form's; string fields accept the reference as-is).
    model = options_model_for("work_items", adapter)
    if model is not None:
        try:
            model.model_validate(opts)
        except ValidationError as exc:
            msgs = "; ".join(
                f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()
            )
            return await _reject(t("pf.invalid_options", msgs=msgs), opts)
    try:
        projects_store.set_work_items(project_id, adapter, opts)
    except (ValueError, KeyError) as exc:
        return await _reject(str(exc), opts)
    await _reindex(project_id)
    return RedirectResponse(f"/projeler/{project_id}/dosyalar", status_code=303)


@router.get("/projeler/{project_id}/ayarlar/intake/form", response_class=HTMLResponse,
            dependencies=[Depends(require_project_access)])
async def project_intake_form(
    request: Request, project_id: str, adapter: str = "", mode: str = "auto"
) -> Response:
    """Options-form fragment for the selected request-intake adapter (twin of the
    work-items form). Saving goes through the one POST below."""
    project = projects_store.get(project_id)
    if project is None:
        return _error_fragment(t("err.project_not_found"))
    return templates.TemplateResponse(
        request,
        "intake_form.html",
        {"project": {"id": project.id}, **_intake_form_context(project, adapter, mode=mode)},
    )


@router.post("/projeler/{project_id}/ayarlar/intake",
             dependencies=[Depends(require_pmo), Depends(require_project_access)])
async def project_intake(
    request: Request,
    project_id: str,
    ctx: CtxDep,
    adapter: Annotated[str, Form()],
    mode: Annotated[str, Form()] = "on_decision",
    options: Annotated[str, Form()] = "",
) -> Response:
    project = projects_store.get(project_id)
    if project is None:
        return RedirectResponse("/", status_code=303)

    async def _reject(message: str, opts: dict | None = None) -> Response:
        return templates.TemplateResponse(
            request, "project_files.html",
            (await _files_context(ctx, project, error=message,
                                  attempted_intake_adapter=adapter,
                                  attempted_intake_opts=opts,
                                  attempted_intake_mode=mode)),
            status_code=400,
        )

    if adapter not in available_adapters("request_intake") and adapter != "none":
        return await _reject(t(
            "pf.unknown_adapter", name=adapter,
            known=", ".join(a for a in available_adapters("request_intake") if a != "fake"),
        ))
    if mode not in ("on_decision", "on_triage", "both"):
        return await _reject(
            t("pf.unknown_adapter", name=mode, known="on_decision, on_triage, both")
        )
    form = await request.form()
    if "options" in form:
        opts: dict = _parse_options(options)
    else:
        opts = {
            k[4:]: str(v)
            for k, v in form.items()
            if k.startswith("opt_") and str(v).strip() != ""
        }
    stored_in = project.connectors.request_intake
    if adapter == stored_in.adapter:
        for key, val in stored_in.options.items():
            if is_secret_field(key) and not str(opts.get(key, "")).strip():
                opts[key] = val
    model = options_model_for("request_intake", adapter)
    if model is not None:
        try:
            model.model_validate(opts)
        except ValidationError as exc:
            msgs = "; ".join(
                f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()
            )
            return await _reject(t("pf.invalid_options", msgs=msgs), opts)
    try:
        projects_store.set_intake(project_id, adapter, opts, mode)
    except (ValueError, KeyError) as exc:
        return await _reject(str(exc), opts)
    # Intake does not affect the index — just rebuild the context so the new
    # provider/responder bindings take effect (no _reindex).
    get_context.cache_clear()
    return RedirectResponse(f"/projeler/{project_id}/dosyalar", status_code=303)


@router.post("/projeler/{project_id}/ayarlar/llm-profili",
             dependencies=[Depends(require_pmo), Depends(require_project_access)])
async def project_llm_profile(
    request: Request,
    project_id: str,
    ctx: CtxDep,
    language: Annotated[str, Form()] = "tr",
    domain_profile: Annotated[str, Form()] = "",
    instructions: Annotated[str, Form()] = "",
    pivot_language: Annotated[str, Form()] = "",
) -> Response:
    """Project LLM profile (language + domain + pivot). The index is unchanged → only the
    context cache is cleared."""
    if projects_store.get(project_id) is None:
        return RedirectResponse("/", status_code=303)
    projects_store.set_llm_profile(
        project_id, language=language, domain_profile=domain_profile,
        instructions=instructions, pivot_language=pivot_language,
    )
    get_context.cache_clear()  # so the engine preamble/language rebuilds (NO reindex)
    return RedirectResponse(f"/projeler/{project_id}/dosyalar", status_code=303)


# ---------------------------------------------------------------------------
# Search (top bar) — real: projects + case files
# ---------------------------------------------------------------------------
@router.get("/ara", response_class=HTMLResponse)
async def search(
    request: Request,
    ctx: CtxDep,
    user: Annotated[dict[str, str], Depends(require_user)],
    q: str = "",
) -> HTMLResponse:
    query = q.strip()
    allowed = accessible_projects(user, ctx.user_store)  # None = all (pmo-global)
    project_hits: list[dict] = []
    case_hits: list[dict] = []
    if query:
        # Word-based AND match: "rapor filtre" hits a request containing both words
        # anywhere, not only the exact substring.
        tokens = [w for w in query.lower().split() if w]

        def _hits(*fields: str) -> bool:
            haystack = " ".join(f.lower() for f in fields)
            return all(tok in haystack for tok in tokens)

        for p in _project_stats():
            if allowed is not None and p["id"] not in allowed:
                continue
            if _hits(p["name"], p["contract_id"], p["id"]):
                project_hits.append(p)
        names = {p["id"]: p["name"] for p in ctx.projects}
        for case in reversed(ctx.repo.list_cases(None)):
            if allowed is not None and (case.project_id or "") not in allowed:
                continue
            if _hits(case.raw_request, case.request_id):
                case_hits.append(_case_row(case, names))
            if len(case_hits) >= 50:
                break
    return templates.TemplateResponse(
        request,
        "ara.html",
        {"q": query, "project_hits": project_hits, "case_hits": case_hits,
         "monitor": _monitor(ctx)},
    )


# ---------------------------------------------------------------------------
# New Project (top bar) — pmo: create skeleton → index → go to detail
# ---------------------------------------------------------------------------
@router.get("/yeni-proje", response_class=HTMLResponse, dependencies=[Depends(require_pmo)])
async def new_project_form(request: Request, ctx: CtxDep) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "yeni_proje.html", {"monitor": _monitor(ctx), "error": None}
    )


@router.post("/yeni-proje", response_class=HTMLResponse, dependencies=[Depends(require_pmo)])
async def new_project_create(
    request: Request,
    ctx: CtxDep,
    project_id: Annotated[str, Form()],
    name: Annotated[str, Form()],
    contract_id: Annotated[str, Form()] = "CTR-NEW",
) -> Response:
    try:
        projects_store.create_project(project_id.strip(), name.strip(), contract_id.strip())
    except ValueError as exc:
        return templates.TemplateResponse(
            request,
            "yeni_proje.html",
            {"monitor": _monitor(ctx), "error": str(exc)},
            status_code=400,
        )
    await _reindex(project_id.strip())
    return RedirectResponse(f"/projeler/{project_id.strip()}", status_code=303)


# ---------------------------------------------------------------------------
# Global settings (pmo) — UI-managed LLM provider config (.etki/llm.json overrides)
# ---------------------------------------------------------------------------
def _ayarlar_context(ctx: AppContext, *, saved: bool = False, error: str | None = None) -> dict:
    s = Settings()
    provider = (s.llm_provider or "openai").lower()
    mode = "anthropic" if provider == "anthropic" else ("openai" if s.llm_base_url else "off")
    return {
        "monitor": _monitor(ctx),
        "llm": _llm_status(),
        "saved": saved,
        "error": error,
        "form": {
            "mode": mode,
            "anthropic_model": s.anthropic_model,
            "has_anthropic_key": bool(
                s.anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY")
            ),
            "llm_base_url": s.llm_base_url or "",
            "llm_model": s.llm_model,
            "has_llm_key": bool(s.llm_api_key),
            "llm_timeout": s.llm_timeout,
        },
        "users": [
            {
                "username": u.username,
                "role": u.role,
                "projects": ", ".join(sorted(ctx.user_store.projects_for(u.username))),
            }
            for u in ctx.user_store.list_users()
        ],
        "roles": ["pmo", "engineer", "viewer"],
        "all_projects": [p["id"] for p in ctx.projects],
    }


def _parse_project_grants(raw: str) -> list[str]:
    return [p.strip() for p in raw.replace(";", ",").split(",") if p.strip()]


@router.get("/ayarlar", response_class=HTMLResponse, dependencies=[Depends(require_pmo)])
async def global_settings(request: Request, ctx: CtxDep, kaydedildi: int = 0) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "ayarlar.html", _ayarlar_context(ctx, saved=bool(kaydedildi))
    )


@router.post("/ayarlar/llm", response_class=HTMLResponse, dependencies=[Depends(require_pmo)])
async def save_llm_settings(
    request: Request,
    ctx: CtxDep,
    mode: Annotated[str, Form()],
    anthropic_api_key: Annotated[str, Form()] = "",
    anthropic_model: Annotated[str, Form()] = "",
    llm_base_url: Annotated[str, Form()] = "",
    llm_model: Annotated[str, Form()] = "",
    llm_api_key: Annotated[str, Form()] = "",
    llm_timeout: Annotated[str, Form()] = "",
    clear_keys: Annotated[str | None, Form()] = None,
) -> Response:
    updates: dict[str, object] = {}
    if mode == "anthropic":
        updates["llm_provider"] = "anthropic"
    elif mode == "openai":
        if not llm_base_url.strip():
            return templates.TemplateResponse(
                request, "ayarlar.html",
                _ayarlar_context(ctx, error=t("set.err_base_url_required")), status_code=400,
            )
        if is_metadata_url(llm_base_url):
            return templates.TemplateResponse(
                request, "ayarlar.html",
                _ayarlar_context(ctx, error=t("set.err_metadata_url")), status_code=400,
            )
        updates["llm_provider"] = "openai"
        updates["llm_base_url"] = llm_base_url.strip()
    else:  # off — the empty-string override beats an env ETKI_LLM_BASE_URL too
        updates["llm_provider"] = "openai"
        updates["llm_base_url"] = ""
    # Models/timeout: empty field = drop the override (fall back to env/default).
    updates["anthropic_model"] = anthropic_model.strip() or None
    updates["llm_model"] = llm_model.strip() or None
    if llm_timeout.strip():
        try:
            updates["llm_timeout"] = float(llm_timeout)
        except ValueError:
            return templates.TemplateResponse(
                request, "ayarlar.html",
                _ayarlar_context(ctx, error=t("set.err_bad_timeout")), status_code=400,
            )
    else:
        updates["llm_timeout"] = None
    # Secrets: empty form field = keep the stored value; "clear keys" wipes both.
    if clear_keys:
        updates["anthropic_api_key"] = None
        updates["llm_api_key"] = None
    else:
        if anthropic_api_key.strip():
            updates["anthropic_api_key"] = anthropic_api_key.strip()
        if llm_api_key.strip():
            updates["llm_api_key"] = llm_api_key.strip()
    llm_settings_store.save(updates)
    get_context.cache_clear()  # engines rebuild with the new client on the next request
    return RedirectResponse("/ayarlar?kaydedildi=1", status_code=303)


@router.post("/ayarlar/llm/test", response_class=HTMLResponse,
             dependencies=[Depends(require_pmo)])
async def test_llm_connection(request: Request) -> HTMLResponse:
    client = build_llm_client(Settings())
    if client is None:
        return HTMLResponse(
            f'<span class="meta">{t("set.test_unconfigured")}</span>'
        )
    try:
        await client.complete_json(
            system="You are a connectivity check. Reply with JSON only.",
            user='Return exactly this JSON object: {"ok": true}',
        )
    except Exception as exc:
        reason = escape(str(exc)[:180])
        return HTMLResponse(
            '<span style="color:#A83228; font-size:13px; font-weight:600;">'
            f"✗ {t('set.test_fail')}</span> "
            f'<span class="meta">{reason}</span>'
        )
    return HTMLResponse(
        '<span style="color:#9A5F23; font-size:13px; font-weight:600;">'
        f"✓ {t('set.test_ok')}</span>"
    )


# ---------------------------------------------------------------------------
# User management (pmo) — the /ayarlar "Kullanıcılar" card
# ---------------------------------------------------------------------------
def _ayarlar_error(request: Request, ctx: AppContext, message: str) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "ayarlar.html", _ayarlar_context(ctx, error=message), status_code=400
    )


@router.get(
    "/ayarlar/eklentiler", response_class=HTMLResponse, dependencies=[Depends(require_pmo)]
)
async def plugins_screen(request: Request) -> HTMLResponse:
    """Plugin visibility + enable/disable + the marketplace card. The policy
    stays env-only with NO mutating route; installing exists ONLY for the
    verified marketplace path and ONLY behind the env-only
    `ETKI_PLUGIN_UI_INSTALL` gate (2026-07-16 revision of plan rule 4 —
    git/wheel acquisition remains operator/CLI-only)."""
    from etki.adapters.plugins import get_plugin_registry
    from etki.plugin.lockfile import load_lockfile
    from etki.plugin.policy import current_policy

    registry = get_plugin_registry()
    try:
        lock = load_lockfile().plugins
        verified = {p.name for p in lock if p.verified}
        # Install source (git|local|verified) lives in the lockfile, not the
        # runtime status (PluginStatus.source is the constant "plugin").
        sources = {p.name: p.source for p in lock}
    except Exception:  # noqa: BLE001 — a corrupt lockfile shows as unverified
        verified = set()
        sources = {}
    return templates.TemplateResponse(
        request,
        "plugins.html",
        {
            "statuses": registry.statuses(),
            "stamp": registry.stamp(),
            "policy": current_policy(),
            "verified": verified,
            "sources": sources,
        },
    )


@router.post("/ayarlar/eklentiler/{name}/durum", dependencies=[Depends(require_pmo)])
async def plugin_toggle(name: str, request: Request) -> RedirectResponse:
    """Enable/disable an INSTALLED plugin (the only UI-writable plugin state).
    Takes effect on the next context build — caches are cleared here."""
    from etki.adapters.plugins import get_plugin_registry
    from etki.plugin.state import set_disabled

    registry = get_plugin_registry()
    if name not in {s.name for s in registry.statuses()}:
        raise HTTPException(status_code=404, detail="bilinmeyen plugin")
    form = await request.form()
    set_disabled(name, form.get("disabled") == "1")
    get_plugin_registry.cache_clear()
    get_context.cache_clear()
    return RedirectResponse("/ayarlar/eklentiler", status_code=303)


# Marketplace browse cache — module-level is valid because workers=1 is
# enforced at startup (same reasoning as auth.LoginRateLimiter). Errors get a
# short TTL so a transient network failure doesn't stick to the screen.
_MARKET_TTL = 900.0
_MARKET_ERROR_TTL = 60.0
_market_cache: dict[str, tuple[float, Any, str | None]] = {}


def _market_index(source: str, *, force: bool = False) -> tuple[Any, str | None]:
    """(IndexFile | None, error | None) for the marketplace fragment. Remote
    sources verify the sigstore signature (mandatory inside
    marketplace.load_index); a mirror directory follows the air-gapped
    hash-only rule. Failures degrade to a message — the settings screen must
    never 500 because the index is unreachable."""
    from etki.plugin import marketplace

    now = time.monotonic()
    cached = _market_cache.get(source)
    if cached and not force:
        ttl = _MARKET_TTL if cached[1] is not None else _MARKET_ERROR_TTL
        if now - cached[0] < ttl:
            return cached[1], cached[2]
    try:
        index, _raw = marketplace.load_index(source)
        entry: tuple[float, Any, str | None] = (now, index, None)
    except Exception as exc:  # noqa: BLE001 — UI boundary: degrade, never crash
        entry = (now, None, str(exc))
    _market_cache.clear()  # one source at a time — no unbounded growth
    _market_cache[source] = entry
    return entry[1], entry[2]


def _safe_http_url(url: str) -> str | None:
    """Only http(s) links from the index render as <a>. Defense-in-depth: the
    index is signature-pinned, but a link never gets to be a javascript: URI."""
    return url if url.startswith(("http://", "https://")) else None


def _market_is_newer(candidate: str | None, current: str | None) -> bool:
    if not candidate or not current:
        return False
    try:
        from packaging.version import Version

        return Version(candidate) > Version(current)
    except Exception:  # noqa: BLE001 — exotic version strings never break the view
        return False


def _caps_summary(caps: Any) -> str:
    """One-line, localized capability declaration (install confirm + cards)."""
    parts: list[str] = []
    if caps.network:
        parts.append(t("plugins.market_caps_network"))
    if getattr(caps, "external_write", False):
        parts.append(t("plugins.market_caps_external_write"))
    parts.append(f"{t('plugins.market_caps_fs')}: {caps.filesystem}")
    if caps.endpoints:
        parts.append(f"{t('plugins.market_caps_endpoints')}: {', '.join(caps.endpoints)}")
    return " · ".join(parts)


def _market_context(q: str, *, force: bool = False) -> dict[str, Any]:
    """Template context for market_fragment.html — shared by the browse GET
    and the install POST (which re-renders the fragment with a banner)."""
    from etki.adapters.plugins import get_plugin_registry
    from etki.plugin import marketplace, signing
    from etki_api import __version__ as api_version

    source = marketplace.index_source()
    index, error = _market_index(source, force=force)
    installed = {s.name: s.version for s in get_plugin_registry().statuses()}
    rows: list[dict[str, Any]] = []
    if index is not None:
        plugins = marketplace.search(index, q) if q.strip() else list(index.plugins)
        for plugin in plugins:
            try:
                _plugin, best = marketplace.resolve(index, plugin.name)
                version: str | None = best.version
                api_compat: str | None = best.api_compat
                released_at: str | None = best.released_at
                report: str | None = best.conformance_report
                ranges: str | None = None
            except Exception:  # noqa: BLE001 — InstallError: no compatible version
                version = api_compat = released_at = report = None
                ranges = ", ".join(v.api_compat for v in plugin.versions) or "—"
            current = installed.get(plugin.name)
            rows.append(
                {
                    "name": plugin.name,
                    "summary": plugin.summary,
                    "ports": plugin.ports,
                    "caps": plugin.capabilities,
                    "repo": _safe_http_url(plugin.source_repo),
                    "version": version,
                    "api_compat": api_compat,
                    "released_at": released_at,
                    "report": _safe_http_url(report or ""),
                    "ranges": ranges,
                    "installed": current,
                    # NOT named "update": Jinja resolves r.update to dict.update
                    # (attribute-first lookup), which is always truthy.
                    "update_available": _market_is_newer(version, current),
                    # --index only when the operator overrode the trust root: the
                    # CLI resolves the same default, and an env set on the SERVER
                    # may be absent in the operator's shell.
                    "cmd": f"python -m etki.plugin install {plugin.name}"
                    + ("" if source == marketplace.DEFAULT_INDEX_URL else f" --index {source}"),
                    "confirm": t(
                        "plugins.market_confirm_install",
                        name=plugin.name,
                        version=version or "?",
                        caps=_caps_summary(plugin.capabilities),
                    ),
                }
            )
    return {
        "q": q,
        "rows": rows,
        "error": error,
        "source": source,
        "source_is_dir": Path(source).is_dir(),
        "generated_at": index.generated_at if index is not None else "",
        "identity": signing.expected_identity()[0],
        "api_version": api_version,
        "ui_install": marketplace.ui_install_enabled(),
    }


@router.get(
    "/ayarlar/eklentiler/pazar",
    response_class=HTMLResponse,
    dependencies=[Depends(require_pmo)],
)
def market_fragment(request: Request, q: str = "", yenile: str | None = None) -> HTMLResponse:
    """Marketplace browse — a READ-ONLY projection of the SIGNED index (plan
    rule: the single source of truth is index.json). The index source is
    env-only (`ETKI_PLUGIN_INDEX_URL`), never a form field. Sync `def` on
    purpose: the fetch + signature verification runs in the threadpool
    instead of blocking the event loop."""
    return templates.TemplateResponse(
        request, "market_fragment.html", _market_context(q, force=yenile == "1")
    )


@router.post(
    "/ayarlar/eklentiler/pazar/kur",
    response_class=HTMLResponse,
)
def market_install(
    request: Request,
    user: Annotated[dict[str, str], Depends(require_pmo)],
    name: Annotated[str, Form()],
) -> HTMLResponse:
    """Verified-marketplace install from the UI — the 2026-07-16 revision of
    plan rule 4, twice-gated: pmo role AND the env-only `ETKI_PLUGIN_UI_INSTALL`
    switch (default OFF → 403). ONLY the signed-index path exists here: the
    source is env-pinned (never a form field) and resolve/signature/SHA-256 all
    run inside `marketplace.install_verified`; git/wheel targets have no UI
    route. Sync def → threadpool (network + `uv pip` subprocess)."""
    from etki import process_log
    from etki.adapters.plugins import get_plugin_registry
    from etki.plugin import marketplace

    if not marketplace.ui_install_enabled():
        raise HTTPException(
            status_code=403,
            detail="Arayüzden kurulum kapalı — operatör ETKI_PLUGIN_UI_INSTALL=true ile açar.",
        )
    source = marketplace.index_source()
    plugin_name = name.strip()
    try:
        entry = marketplace.install_verified(plugin_name, source, yes=True)
    except Exception as exc:  # noqa: BLE001 — UI boundary: banner, never a 500
        context = _market_context("")
        context["install_error"] = f"{plugin_name}: {exc}"
        return templates.TemplateResponse(request, "market_fragment.html", context)
    # New distribution in the venv: rebuild the entry-point registry + engines.
    get_plugin_registry.cache_clear()
    get_context.cache_clear()
    process_log.log_event(
        "plugin_install",
        "-",
        {
            "user": user.get("username", "?"),
            "plugin": entry.name,
            "sha256": entry.sha256,
            "source": source,
        },
    )
    context = _market_context("")
    context["flash"] = t("plugins.market_installed_flash", name=entry.name)
    return templates.TemplateResponse(request, "market_fragment.html", context)


def _plugin_detail_context(
    name: str,
    *,
    saved: bool = False,
    error: str | None = None,
    attempted: tuple[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Detail-page context: status/manifest projection + one defaults form per
    adapter the plugin provides. `attempted` re-fills a rejected form (adapter
    name, values) — secret fields are still never echoed back."""
    from etki.adapters.plugins import get_plugin_registry
    from etki.plugin import options_store
    from etki.plugin.lockfile import load_lockfile

    registry = get_plugin_registry()
    status = registry.status(name)
    if status is None:
        raise HTTPException(status_code=404, detail="bilinmeyen plugin")
    spec = registry.spec(name)
    try:
        lock = load_lockfile().get(name)
    except Exception:  # noqa: BLE001 — a corrupt lockfile shows as no entry
        lock = None
    adapters: list[dict[str, Any]] = []
    for factory in spec.adapters if spec is not None else ():
        stored = options_store.defaults_for(factory.name)
        values: dict[str, Any] = stored
        if attempted is not None and attempted[0] == factory.name:
            values = {**stored, **attempted[1]}
        adapters.append(
            {
                "port": factory.port,
                "name": factory.name,
                "fields": _schema_fields(factory.options_model, values, mask_secrets=True),
                "has_defaults": bool(stored),
            }
        )
    return {
        "status": status,
        "caps": spec.capabilities if spec is not None else None,
        "caps_line": _caps_summary(spec.capabilities) if spec is not None else "",
        "lock": lock,
        "adapters": adapters,
        "saved": saved,
        "error": error,
    }


@router.get(
    "/ayarlar/eklentiler/{name}",
    response_class=HTMLResponse,
    dependencies=[Depends(require_pmo)],
)
async def plugin_detail(
    request: Request, name: str, kaydedildi: str | None = None
) -> HTMLResponse:
    """Per-plugin page: status/manifest info + UI-managed DEFAULT options per
    adapter (API keys etc. — stored 0600 in `.etki/plugin-options.json`, merged
    UNDER project options at build time, project value wins). Registered AFTER
    /pazar, so the static segment keeps winning."""
    return templates.TemplateResponse(
        request,
        "plugin_detail.html",
        _plugin_detail_context(name, saved=kaydedildi == "1"),
    )


@router.post(
    "/ayarlar/eklentiler/{name}/secenekler",
    response_class=HTMLResponse,
    dependencies=[Depends(require_pmo)],
)
async def plugin_options_save(request: Request, name: str) -> Response:
    """Saves UI-managed DEFAULT options for one adapter of the plugin. Secret
    fields left empty KEEP the stored value (the llm.json idiom — they are
    never echoed into the form either); `env:VAR` references are stored as
    references and validation runs WITHOUT resolving them."""
    from etki.adapters.plugins import get_plugin_registry
    from etki.plugin import options_store

    registry = get_plugin_registry()
    spec = registry.spec(name)
    if registry.status(name) is None or spec is None:
        raise HTTPException(status_code=404, detail="bilinmeyen plugin")
    form = await request.form()
    adapter = str(form.get("adapter", ""))
    factory = next((f for f in spec.adapters if f.name == adapter), None)
    if factory is None:
        raise HTTPException(status_code=400, detail="bilinmeyen adaptör")
    if form.get("reset") == "1":
        # The only way to CLEAR a stored secret — empty submits keep it by design.
        options_store.save(adapter, {})
        get_context.cache_clear()
        return RedirectResponse(f"/ayarlar/eklentiler/{name}?kaydedildi=1", status_code=303)
    submitted: dict[str, Any] = {
        k[len("opt_") :]: str(v).strip()
        for k, v in form.items()
        if k.startswith("opt_") and str(v).strip() != ""
    }
    stored = options_store.defaults_for(adapter)
    for key, value in stored.items():
        if options_store.is_secret_field(key) and key not in submitted:
            submitted[key] = value
    try:
        factory.options_model.model_validate(submitted)
    except ValidationError as exc:
        msgs = "; ".join(
            f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()
        )
        context = _plugin_detail_context(
            name,
            error=t("pf.invalid_options", msgs=msgs),
            attempted=(adapter, submitted),
        )
        return templates.TemplateResponse(
            request, "plugin_detail.html", context, status_code=400
        )
    options_store.save(adapter, submitted)
    get_context.cache_clear()  # engines rebuild with the new defaults
    return RedirectResponse(f"/ayarlar/eklentiler/{name}?kaydedildi=1", status_code=303)


@router.post("/ayarlar/kullanicilar", response_class=HTMLResponse)
async def user_create(
    request: Request,
    ctx: CtxDep,
    admin: Annotated[dict[str, str], Depends(require_pmo)],
    username: Annotated[str, Form()],
    password: Annotated[str, Form()],
    role: Annotated[str, Form()],
    projects: Annotated[str, Form()] = "",
) -> Response:
    try:
        ctx.user_store.create(
            username.strip(), password, role, _parse_project_grants(projects)
        )
    except ValueError as exc:
        return _ayarlar_error(request, ctx, str(exc))
    return RedirectResponse("/ayarlar?kaydedildi=1", status_code=303)


@router.post("/ayarlar/kullanicilar/{username}/guncelle", response_class=HTMLResponse)
async def user_update(
    request: Request,
    ctx: CtxDep,
    admin: Annotated[dict[str, str], Depends(require_pmo)],
    username: str,
    role: Annotated[str, Form()],
    projects: Annotated[str, Form()] = "",
) -> Response:
    target = ctx.user_store.get(username)
    if target is None:
        raise HTTPException(status_code=404, detail=t("set.err_user_not_found"))
    # The last pmo cannot be demoted — the system must keep an approver.
    if target.role == "pmo" and role != "pmo" and ctx.user_store.count_role("pmo") <= 1:
        return _ayarlar_error(request, ctx, t("set.err_last_pmo"))
    try:
        ctx.user_store.set_role(username, role)
        ctx.user_store.set_projects(username, _parse_project_grants(projects))
    except ValueError as exc:
        return _ayarlar_error(request, ctx, str(exc))
    return RedirectResponse("/ayarlar?kaydedildi=1", status_code=303)


@router.post("/ayarlar/kullanicilar/{username}/parola", response_class=HTMLResponse)
async def user_reset_password(
    request: Request,
    ctx: CtxDep,
    admin: Annotated[dict[str, str], Depends(require_pmo)],
    username: str,
    new_password: Annotated[str, Form()],
) -> Response:
    try:
        # Rotates the session token too → the target's live sessions drop immediately.
        ctx.user_store.set_password(username, new_password)
    except ValueError as exc:
        return _ayarlar_error(request, ctx, str(exc))
    return RedirectResponse("/ayarlar?kaydedildi=1", status_code=303)


@router.post("/ayarlar/kullanicilar/{username}/sil", response_class=HTMLResponse)
async def user_delete(
    request: Request,
    ctx: CtxDep,
    admin: Annotated[dict[str, str], Depends(require_pmo)],
    username: str,
) -> Response:
    if username == admin.get("username"):
        return _ayarlar_error(request, ctx, t("set.err_self_delete"))
    target = ctx.user_store.get(username)
    if target is None:
        raise HTTPException(status_code=404, detail=t("set.err_user_not_found"))
    if target.role == "pmo" and ctx.user_store.count_role("pmo") <= 1:
        return _ayarlar_error(request, ctx, t("set.err_last_pmo"))
    ctx.user_store.delete(username)
    return RedirectResponse("/ayarlar?kaydedildi=1", status_code=303)
