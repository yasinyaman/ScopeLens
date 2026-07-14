"""FastAPI application (multi-project). Triage routes to the right engine by `project_id`;
cases/KPIs are separated per project. HITL approval (RBAC), audit trail, KPI, HTMX UI.

Authentication: signed session cookie (SessionMiddleware) + `/login`. Protected routes
require a valid session; a session-less UI request is redirected to `/login`, an API
request gets 401.
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from starlette.middleware.sessions import SessionMiddleware

from etki.api import web
from etki.api.context import AppContext, UnknownProjectError, get_context
from etki.api.schemas import ActionRequest, TriageRequest
from etki.api.security import (
    NotAuthenticated,
    accessible_projects,
    ensure_project_access,
    require_pmo,
    require_user,
)
from etki.auth import build_user_store
from etki.config import Settings
from etki.core.models import AuditEvent, CaseFile
from etki.kpi import compute_kpis
from etki.logging_config import configure_logging

logger = logging.getLogger("etki")

_DEV_SECRET = "dev-insecure-change-me"


def _bootstrap_admin(settings: Settings) -> None:
    """Creates the first PMO user only if no user exists and the env vars are set."""
    if not (settings.admin_user and settings.admin_password):
        return
    store = build_user_store(settings.db_url)
    if store.count() == 0:
        store.create(settings.admin_user, settings.admin_password, "pmo")
        logger.info("İlk PMO kullanıcısı oluşturuldu: %s", settings.admin_user)


def _enforce_single_worker() -> None:
    """The `engines` dict is process-LOCAL: with >1 worker each process carries its own
    copy of the living baseline and CR approvals diverge. With A1 the baseline became
    single-sourced in the DB, but the in-memory engines are still per-process — the
    worker count MUST be 1 (see docs/RUNBOOK.md). Fail loudly at startup instead of
    silently producing wrong decisions under a misconfiguration."""
    workers = os.environ.get("WEB_CONCURRENCY") or os.environ.get("UVICORN_WORKERS")
    if workers and workers.isdigit() and int(workers) > 1:
        raise RuntimeError(
            f"Etki tek worker ile çalışmalı (WEB_CONCURRENCY={workers} bulundu). "
            "Bellek içi proje motorları process-local'dir; çoklu worker baseline "
            "kopyalarını ayrıştırır. workers=1 kullanın (docs/RUNBOOK.md)."
        )


def _reindex_all_sync(settings: Settings) -> int:
    """Full re-index of every project (blocking; meant for a worker thread)."""
    from etki.api.context import index_project
    from etki.config import load_projects

    projects = load_projects(settings.projects_path, settings.connectors_path)
    for project in projects:
        asyncio.run(index_project(project, settings))
    return len(projects)


async def _reindex_loop(interval_hours: float) -> None:
    while True:
        await asyncio.sleep(interval_hours * 3600)
        try:
            count = await run_in_threadpool(_reindex_all_sync, Settings())
            get_context.cache_clear()  # engines rebuild from the fresh indexes
            logger.info("zamanlanmış re-index tamam (%s proje)", count)
        except Exception:
            logger.exception("zamanlanmış re-index başarısız; bir sonraki tur beklenecek")


async def _pool_refresh_loop(interval_minutes: float) -> None:
    while True:
        await asyncio.sleep(interval_minutes * 60)
        try:
            refreshed = await run_in_threadpool(lambda: get_context().refresh_pools())
            logger.info("efor havuzu tazelendi (%s proje)", refreshed)
        except Exception:
            logger.exception("efor havuzu tazeleme başarısız; bir sonraki tur beklenecek")


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
    settings = Settings()
    configure_logging(settings.log_level)
    _enforce_single_worker()
    if settings.session_secret == _DEV_SECRET:
        logger.warning(
            "GÜVENSİZ varsayılan session_secret kullanılıyor — üretimde "
            "ETKI_SESSION_SECRET ortam değişkenini ayarlayın."
        )
    _bootstrap_admin(settings)
    # Optional in-app schedulers (both OFF by default; cron stays the recommended
    # production path — see docs/RUNBOOK.md). Sleep-first loops: no startup burden.
    background: list[asyncio.Task[None]] = []
    if settings.reindex_interval_hours > 0:
        background.append(asyncio.create_task(_reindex_loop(settings.reindex_interval_hours)))
        logger.info("zamanlanmış re-index açık: her %s saat", settings.reindex_interval_hours)
    if settings.pool_refresh_minutes > 0:
        background.append(asyncio.create_task(_pool_refresh_loop(settings.pool_refresh_minutes)))
        logger.info("efor havuzu tazeleme açık: her %s dk", settings.pool_refresh_minutes)
    yield
    for task in background:
        task.cancel()


app = FastAPI(title="Etki", version="0.1.0a1", lifespan=lifespan)
# Cookie lifetime is the "remember me" MAXIMUM (30 days); the real per-session lifetime
# is enforced server-side via the session's `exp` (8h without remember-me) in current_user.
app.add_middleware(
    SessionMiddleware,
    secret_key=Settings().session_secret,
    same_site="lax",
    max_age=30 * 86400,
)
# Static assets (locally-vendored HTMX etc.) — no CDN dependency in air-gapped/KVKK
# deployments. Public.
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
app.include_router(web.login_router)  # public: /login, /logout
app.include_router(web.router)  # the router guards itself with require_user

CtxDep = Annotated[AppContext, Depends(get_context)]
UserDep = Annotated[dict[str, str], Depends(require_user)]

_MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


@app.middleware("http")
async def _csrf_guard(request: Request, call_next):  # type: ignore[no-untyped-def]
    """CSRF defense-in-depth on top of `same_site=lax` cookies: modern browsers stamp
    every request with `Sec-Fetch-Site`; a mutating request marked `cross-site` can only
    be a forged cross-origin submission → reject. Requests without the header (curl,
    API clients, old browsers) pass through — for them the lax cookie rule already
    prevents the session cookie from being attached cross-site."""
    if (
        request.method in _MUTATING_METHODS
        and request.headers.get("sec-fetch-site", "").lower() == "cross-site"
    ):
        return JSONResponse({"detail": "Cross-site istek reddedildi"}, status_code=403)
    return await call_next(request)


@app.exception_handler(NotAuthenticated)
async def _auth_required(
    request: Request, exc: NotAuthenticated
) -> JSONResponse | RedirectResponse:
    """No session: redirect browser GETs to /login, reject API requests with 401."""
    accepts_html = "text/html" in request.headers.get("accept", "")
    if request.method == "GET" and accepts_html:
        return RedirectResponse(f"/login?next={request.url.path}", status_code=303)
    return JSONResponse({"detail": "Giriş gerekli"}, status_code=401)


@app.exception_handler(UnknownProjectError)
async def _unknown_project(request: Request, exc: UnknownProjectError) -> JSONResponse:
    """Unknown project: explicit 404 instead of silently falling back to the default (A2)."""
    return JSONResponse({"detail": "Proje bulunamadı"}, status_code=404)


@app.exception_handler(Exception)
async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
    """Unexpected error: don't leak the stack trace; log it and return a plain 500."""
    logger.exception("İşlenmeyen hata: %s %s", request.method, request.url.path)
    return JSONResponse({"detail": "Sunucu hatası"}, status_code=500)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready")
async def ready() -> JSONResponse:
    """Readiness probe: can the context be built (DB + at least one engine)? Does NOT
    take get_context as a dependency → if setup blows up, a clean 503 is returned, not a 500."""
    try:
        # get_context is sync and may call asyncio.run (index build) internally → it cannot
        # be called DIRECTLY on the event loop; run it in the threadpool like a normal
        # sync dependency.
        ctx = await run_in_threadpool(get_context)
        ctx.repo.list_cases(None)  # lightweight DB query
        ok = len(ctx.engines) > 0
    except Exception:
        logger.exception("Hazırlık probu başarısız")
        ok = False
    status = "ready" if ok else "not-ready"
    return JSONResponse({"status": status}, status_code=200 if ok else 503)


@app.get("/projects")
async def projects(ctx: CtxDep, user: UserDep) -> list[dict[str, str]]:
    allowed = accessible_projects(user, ctx.user_store)  # None = all (pmo-global)
    return [p for p in ctx.projects if allowed is None or p["id"] in allowed]


@app.post("/triage")
async def triage(body: TriageRequest, ctx: CtxDep, user: UserDep) -> CaseFile:
    pid = ctx.resolve_project(body.project_id)
    ensure_project_access(user, pid, ctx.user_store)
    request_id = f"REQ-{pid}-{uuid.uuid4().hex[:8]}"
    case = await ctx.engines[pid].triage(body.request_text, request_id=request_id)
    case.project_id = pid
    ctx.approval.record_triage(case)
    return case


@app.get("/casefiles")
async def list_cases(
    ctx: CtxDep, user: UserDep, project_id: str | None = None
) -> list[CaseFile]:
    if project_id is not None:
        ensure_project_access(user, project_id, ctx.user_store)
        return ctx.repo.list_cases(project_id)
    allowed = accessible_projects(user, ctx.user_store)
    cases = ctx.repo.list_cases(None)
    if allowed is None:
        return cases
    return [c for c in cases if (c.project_id or "") in allowed]


@app.get("/casefiles/{case_id}")
async def get_case(case_id: str, ctx: CtxDep, user: UserDep) -> CaseFile:
    case = ctx.repo.get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case file bulunamadı")
    # IDOR: access is derived from the case's project (another project's case → 404).
    ensure_project_access(user, case.project_id, ctx.user_store)
    return case


@app.get("/casefiles/{case_id}/audit")
async def get_audit(case_id: str, ctx: CtxDep, user: UserDep) -> list[AuditEvent]:
    case = ctx.repo.get_case(case_id)
    if case is not None:
        ensure_project_access(user, case.project_id, ctx.user_store)
    return ctx.repo.list_audit(case_id)


@app.post("/casefiles/{case_id}/decisions/{index}/action")
async def decide(
    case_id: str,
    index: int,
    body: ActionRequest,
    ctx: CtxDep,
    user: Annotated[dict[str, str], Depends(require_pmo)],
) -> CaseFile:
    case = ctx.repo.get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case file bulunamadı")
    ensure_project_access(user, case.project_id, ctx.user_store)
    engine = ctx.get_engine(case.project_id)
    try:
        result = ctx.approval.decide(
            case_id,
            index,
            body.action,
            actor=user["username"],
            current_baseline=engine.baseline,
            override_decision=body.override_decision,
        )
    except IndexError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if result.new_scope_item is not None:
        # Living baseline: the engine + index.json grow together (survives restart).
        ctx.apply_baseline_bump(case.project_id, result.new_scope_item)
    # Clause memory may have changed → the engine's live dict sees it immediately.
    ctx.refresh_precedents(ctx.resolve_project(case.project_id))
    return result.case


@app.get("/kpi")
async def kpi(ctx: CtxDep, user: UserDep, project_id: str | None = None) -> dict:
    pid = ctx.resolve_project(project_id)
    ensure_project_access(user, pid, ctx.user_store)
    return compute_kpis(ctx.repo, ctx.engines[pid].baseline, ctx.consumed[pid], project_id=pid)
