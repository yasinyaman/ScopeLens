"""Triage engine — Faz 2 full decision tree.

The decision logic is DETERMINISTIC (auditable, reproducible for the gate). The
LLM is only for request-splitting enrichment (understanding) and impact-analysis
prose (agent); the decision itself is made by rules. Decision tree (the
architecture doc's mermaid):

  maintenance scope → negative (EXCLUDED) match → code+text match
                    → limit/quota → effort pool → IN SCOPE
"""

from __future__ import annotations

import logging
import math
import re
from datetime import UTC, datetime

from etki.core.enums import Decision, PmoDecision, Polarity, RequestType, RiskLevel
from etki.core.models import (
    Baseline,
    BestMatch,
    CaseFile,
    CodeModule,
    CrDraft,
    DeclaredDependency,
    EffortEstimate,
    EvidenceChain,
    ModuleSignal,
    Risk,
    ScopeItem,
    SourceCoverage,
    SubRequest,
    TriageDecision,
    WorkItem,
)
from etki.core.ports import (
    CodeRepositoryProvider,
    DocumentSourceProvider,
    EmbeddingProvider,
    LLMClient,
    RerankProvider,
    WorkItemProvider,
)
from etki.core.text import MIN_QUERY_TOKENS, hits, score, tokenize
from etki.engine import estimation
from etki.engine.understanding import ModuleHints, has_security_wording, split_request
from etki.i18n import t
from etki.llm_profile import UNTRUSTED_GUARD, sanitize_untrusted, wrap_untrusted

logger = logging.getLogger("etki")

# Thresholds calibrated against the eval set for the symmetric-normalized score
# (core/text.score: q_cov * sqrt(t_cov)) (B2). The old asymmetric-score thresholds
# were 0.34/0.18.
_IN_SCOPE_MIN = 0.22
_GRAY_MIN = 0.06
_POOL_WARN = 0.85
# A single-hit EXCLUDED match only excludes when it is clearly (≥20%) stronger than
# the best INCLUDED match — short exclusion clauses have a structural advantage in
# the normalized score, so a hair's-breadth lead alone is not enough evidence to
# say "out of scope".
_EXC_MARGIN = 1.2
# Semantic exclusion margin: in cosine space the exclusion must lead the best
# INCLUDED candidate by at least this much — a 0.006 coin-flip difference must not
# yield "out of scope" (embedding bands overlap; without a clear lead the decision
# stays on the lexical/gray path).
_SEM_EXC_MARGIN = 0.05

# Risk matrix: (probability, impact) -> level (the table in the architecture doc)
_RISK_MATRIX: dict[tuple[str, str], RiskLevel] = {
    ("düşük", "düşük"): RiskLevel.LOW,
    ("düşük", "orta"): RiskLevel.LOW,
    ("düşük", "yüksek"): RiskLevel.MEDIUM,
    ("orta", "düşük"): RiskLevel.LOW,
    ("orta", "orta"): RiskLevel.MEDIUM,
    ("orta", "yüksek"): RiskLevel.HIGH,
    ("yüksek", "düşük"): RiskLevel.MEDIUM,
    ("yüksek", "orta"): RiskLevel.HIGH,
    ("yüksek", "yüksek"): RiskLevel.CRITICAL,
}


class TriageEngine:
    """Takes the three ports + baseline via DI; knows no concrete adapters (Joern/GLPI...)."""

    def __init__(
        self,
        work_items: WorkItemProvider,
        code_repo: CodeRepositoryProvider,
        documents: DocumentSourceProvider,
        baseline: Baseline,
        *,
        model_version: str = "deterministic",
        index_freshness: str = "unknown",
        consumed_by_category: dict[str, float] | None = None,
        in_scope_threshold: float = _IN_SCOPE_MIN,
        gray_threshold: float = _GRAY_MIN,
        llm_client: LLMClient | None = None,
        llm_assist_mode: str = "pick",
        embedder: EmbeddingProvider | None = None,
        embed_strong: float = 0.75,
        embed_weak: float = 0.62,
        reranker: RerankProvider | None = None,
        rerank_strong: float = -6.8,
        language: str = "tr",
        system_preamble: str = "",
        pivot_language: str | None = None,
        module_hints: ModuleHints | None = None,
        estimation_params: estimation.EstimationParams | None = None,
        precedents_by_clause: dict[str, dict] | None = None,
        disputed_escalation: bool = True,
        dependencies: list[DeclaredDependency] | None = None,
    ) -> None:
        self._work_items = work_items
        self._code_repo = code_repo
        self._documents = documents
        self._baseline = baseline
        self._model_version = model_version
        self._index_freshness = index_freshness
        # Keep the CALLER's dict by reference (even when empty): the background
        # pool refresh updates it in place and the engine must see the new totals.
        self._consumed = consumed_by_category if consumed_by_category is not None else {}
        # CLAUSE MEMORY (informational, NEVER a decision signal): clause-keyed
        # precedent/dispute summary ({count, last, disputed}). Same rule as
        # consumed — the CALLER's dict is kept by reference; refreshed in place
        # after approval (AppContext.refresh_precedents) so the engine sees the
        # new memory.
        self._precedents = precedents_by_clause if precedents_by_clause is not None else {}
        self._disputed_escalation = disputed_escalation
        # Declared manifest dependencies (dependency-impact context): used only
        # for RECOGNITION (known package names in the splitter) and an
        # informational evidence note — never a decision signal.
        self._dependencies = dependencies or []
        self._in_scope_min = in_scope_threshold
        self._gray_min = gray_threshold
        # LLM ASSIST (optional, off by default → the gate stays deterministic). Asked
        # for semantic/cross-lingual matching ONLY when the deterministic match is WEAK.
        self._llm = llm_client
        # "pick" = v2 (single choice over the full list) | "judge" = v3 (candidate
        # shortlist + per-clause verdict; the new_capability verdict protects a CR
        # from gray drift).
        self._llm_mode = (
            llm_assist_mode if llm_assist_mode in ("pick", "judge", "verify") else "pick"
        )
        # EMBEDDING ASSIST (optional): when the lexical match is weak, cosine
        # similarity is bound to the SAME floor rules as the LLM assist (strong
        # INCLUDED → in-scope floor, strong EXCLUDED → exclusion path, weak → gray
        # floor). Embeddings are deterministic for a given model → the semantic score
        # stays repeatable/auditable. Clause vectors are computed in ONE batched call
        # on first use and cached; the cache refreshes when the baseline version
        # changes. Endpoint error → lexical continues.
        self._embedder = embedder
        self._embed_strong = embed_strong
        self._embed_weak = embed_weak
        self._item_vecs: dict[str, list[float]] = {}
        self._item_vecs_version: int | None = None
        # RERANKER ASSIST (v4b, optional): the cross-encoder reads the (request,
        # clause) pair JOINTLY — makes the "paraphrase of a clause (IN)" vs "new
        # capability near a clause (CR)" separation the bi-encoder can't do
        # measurable (AUC 0.975). Only grants a floor on the INCLUDED side (the
        # exclusion side measured weak: 0.838); limit/quota/pool/short-request
        # guards still apply afterwards. Deterministic for a given model; endpoint
        # error → lexical continues.
        self._reranker = reranker
        self._rerank_strong = rerank_strong
        # Per-project LLM profile: output language + domain/instruction preamble +
        # pivot (LLM-only).
        self._language = language
        self._system_preamble = system_preamble
        self._pivot_language = pivot_language
        # Module hints come from the project profile (config); None → generic
        # (_common), empty dict → no hints at all (guess_module returns None).
        self._module_hints = module_hints
        # Effort-estimation constants from config (C2); None → package defaults.
        self._est_params = estimation_params

    @property
    def baseline(self) -> Baseline:
        return self._baseline

    def extend_baseline(self, item: ScopeItem) -> int:
        """Appends the approved CR to the living baseline and returns the new version number."""
        self._baseline.scope_items.append(item)
        self._baseline.version += 1
        return self._baseline.version

    async def triage(self, raw_request: str, *, request_id: str = "REQ-LOCAL") -> CaseFile:
        sub_requests = split_request(
            raw_request, self._module_hints,
            known_packages=[d.name for d in self._dependencies],
        )
        decisions = [
            await self._decide(f"{request_id}#{i}", sub)
            for i, sub in enumerate(sub_requests, start=1)
        ]
        return CaseFile(
            request_id=request_id,
            raw_request=raw_request,
            sub_requests=sub_requests,
            decisions=decisions,
            status=PmoDecision.PENDING,
            created_at=datetime.now(UTC),
        )

    async def _decide(self, decision_id: str, sub: SubRequest) -> TriageDecision:
        query = tokenize(sub.item)
        best_inc, inc_score, best_exc, exc_hits, exc_score = self._match_scope(query)
        maint_item, maint_score = self._best_included_in_category(query, "maintenance")

        impacted = await self._code_repo.get_impacted(sub.module_hint)
        # TECHNICAL IMPACT SURFACE FOR DEPENDENCY REQUESTS: the module hint never
        # derives from a package name ("let's upgrade requests" falls into no hint
        # dictionary) — the impact is computed from the modules that ACTUALLY
        # import the package + their one-hop dependents. That way the evidence
        # chain (impacted_modules/signals) and the effort estimate (loc/churn)
        # rest on the real usage surface; not just effort — the technical impact
        # analysis also enters the case file.
        if sub.type is RequestType.DEPENDENCY_CHANGE and sub.package:
            impacted = _merge_modules(impacted, await self._package_impacted(sub.package))
        # Scope↔code bridge: also add the code modules mapped to the text-matched
        # clause to the impact (even with an empty module hint: "if you add this,
        # these modules are affected").
        scope_match = best_exc if exc_hits else (best_inc if inc_score >= self._gray_min else None)
        if scope_match is not None and scope_match.mapped_modules:
            impacted = await self._merge_scope_modules(impacted, scope_match)

        # RERANKER ASSIST (v4b): when the lexical match is weak, the cross-encoder
        # score — BEFORE embedding and LLM, because it reads the pair jointly and
        # is the only measured mechanism that makes the paraphrase-vs-new-capability
        # separation deterministically (AUC 0.975). Only grants a floor on the
        # INCLUDED side; the threshold lives in raw logit space, calibrated per
        # model (Settings.rerank_strong). Endpoint error → the layer is silently
        # skipped.
        llm_note_rr: str | None = None
        sem_no_cover = False  # v5b: reranker as NEGATIVE evidence (see _classify)
        # Gate split (measured): the include FLOOR requires exc_hits == 0 — it must
        # never overpower exclusion evidence. The NEGATIVE signal also works at
        # exc_hits == 1: a margin-failed single exclusion graze falls through to the
        # include branches anyway, and exactly those tokenizer-artifact cases (a
        # "data"/"authentication" word grazing an exclusion) were stuck in gray.
        if self._reranker is not None and exc_hits <= 1 and inc_score < self._in_scope_min:
            rr_item, rr_score = await self._rerank_best_included(sub.item)
            if rr_item is not None and rr_score >= self._rerank_strong:
                if exc_hits == 0:
                    best_inc = rr_item
                    inc_score = max(inc_score, self._in_scope_min)
                    llm_note_rr = t(
                        "engine.rerank_note", self._language,
                        ref=rr_item.source_clause or rr_item.id, score=f"{rr_score:.2f}",
                    )
            elif rr_item is not None and not _is_interrogative(sub.item):
                # Below the floor threshold the same score is negative evidence:
                # no clause reads as covering this request. A lexical gray-band
                # score then looks like a tokenizer artifact, not real ambiguity.
                # Interrogative requests are exempt: a question signals the asker
                # is unsure — that is the population the gray band exists for.
                sem_no_cover = True

        # EMBEDDING ASSIST: when the lexical match is weak, cosine similarity is
        # consulted — before the LLM, because it is cheaper AND deterministic
        # (repeatable semantic score). DELIBERATE ASYMMETRY (per the dev
        # measurement): cosine cannot separate "paraphrase of the clause (IN)"
        # from "NEW capability near the clause (CR)" — the bands overlap
        # (audit-log 0.629 ≈ spreadsheet 0.630). Hence the INCLUDED side NEVER
        # CHANGES THE DECISION (evidence note only); the exclusion side is safe
        # when there is a clear cosine lead (+_SEM_EXC_MARGIN) and counts as the
        # independent second evidence of the two-evidence rule. Paraphrase→IN
        # promotions require judgment → the guarded LLM lane's job.
        llm_note_sem: str | None = None
        if (
            self._embedder is not None
            and exc_hits == 0
            and inc_score < self._in_scope_min
        ):
            s_inc, s_inc_cos, s_exc, s_exc_cos = await self._semantic_best(sub.item)
            if (
                s_exc is not None
                and s_exc_cos >= self._embed_strong
                and s_exc_cos > s_inc_cos + _SEM_EXC_MARGIN
            ):
                best_exc, exc_hits = s_exc, 2  # independent second evidence (two-evidence rule)
                exc_score = max(exc_score, self._gray_min)
                llm_note_sem = t("engine.sem_note", self._language, cos=f"{s_exc_cos:.2f}")
            elif s_inc is not None and s_inc_cos >= self._embed_weak:
                # NO decision effect — a "semantically nearest clause" note is left for the PMO.
                llm_note_sem = t(
                    "engine.sem_hint", self._language,
                    ref=s_inc.source_clause or s_inc.id, cos=f"{s_inc_cos:.2f}",
                )

        # LLM ASSIST: when the deterministic match is weak (e.g. TR request ↔ EN
        # spec/code), semantic/cross-lingual matching is asked for. Off by default.
        # Effect rules:
        #   strong INCLUDED → score rises to the in-scope floor (IN_SCOPE possible;
        #                     limit/quota/pool/short-request guards still apply),
        #   strong EXCLUDED → exclusion path (the LLM counts as independent second
        #                     evidence → the two-hit condition is met; the
        #                     deterministic margin rule is meaningless here because
        #                     the deterministic path arrived with zero exclusion hits),
        #   weak            → gray floor only (old behavior); weak EXCLUDED is ignored.
        llm_note_veto: str | None = None
        # v7b exclusion veto: a SINGLE-hit exclusion that is about to rout via the
        # margin rule gets one focused confirmation question. The finding-#2
        # artifacts ("e-invoices…" grazing the streaming exclusion; "contact's
        # mobile number" grazing the mobile-app exclusion) are exactly one word
        # of ambient overlap — a clause-level yes/no the LLM answers reliably,
        # unlike the covers/new-capability boundary (v4a). Fail-open: any error
        # or an "excluded" verdict leaves the deterministic route untouched;
        # 2+ hit exclusions are never questioned.
        if (
            self._llm is not None
            and exc_hits == 1
            and best_exc is not None
            and exc_score > inc_score * _EXC_MARGIN
        ):
            v_verdict, v_note = await self._llm_verify_exclusion(sub.item, best_exc)
            if v_verdict == "not_excluded":
                exc_hits, exc_score = 0, 0.0
                llm_note_veto = v_note

        llm_note: str | None = None
        # v7a gate widening (mirrors the v5b reranker gate): a margin-failed single
        # exclusion graze (exc_hits == 1) falls through to the include branches
        # anyway, and exactly the exclusion-side paraphrases ("connect to our
        # Azure AD…") were stuck there UNSEEN by the assist — no local signal
        # reaches them (round-6 finding), the guarded LLM is the only lane left.
        if (
            self._llm is not None
            and exc_hits <= 1
            and inc_score < self._in_scope_min
            # A margin-passing (veto-confirmed) exclusion will rout in branch 2
            # regardless — don't burn an LLM call on an already-decided case.
            and not (exc_hits == 1 and exc_score > inc_score * _EXC_MARGIN)
        ):
            if self._llm_mode == "judge":
                assist = await self._llm_judge(sub.item, impacted)
            else:
                assist = await self._llm_match(sub.item, best_inc, inc_score, impacted)
            if assist is not None:
                a_item, a_strength, impacted, llm_note = assist
                # v4a "verify": an accepted INCLUDED pick gets one focused follow-up
                # question on that single clause — covers vs new capability. Only a
                # confident "new_capability" cancels the in-scope floor (the request
                # then falls through the deterministic tree toward CR/gray); any
                # error/ambiguity fails open to plain pick behavior.
                if (
                    self._llm_mode == "verify"
                    and a_item is not None
                    and a_item.polarity is not Polarity.EXCLUDED
                ):
                    v_verdict, v_note = await self._llm_verify(sub.item, a_item)
                    if v_verdict == "new_capability":
                        llm_note = v_note or llm_note
                        a_item = None
                if a_item is not None and a_item.polarity is Polarity.EXCLUDED:
                    if a_strength == "strong":
                        best_exc, exc_hits = a_item, 2
                        exc_score = max(exc_score, self._gray_min)
                elif a_item is not None and exc_hits == 0:
                    # The include floor keeps the STRICT gate: with any exclusion
                    # graze present, an INCLUDED pick must not lift the score —
                    # it could tip the deterministic exclusion-margin comparison.
                    best_inc = a_item
                    floor = self._in_scope_min if a_strength == "strong" else self._gray_min
                    inc_score = max(inc_score, floor)

        touches_scoped = any(m.mapped_scope_items for m in impacted)
        similar = await self._safe_find_similar(sub.item)
        # Source-fusion coverage (spec/code/history) — missing layers become assumption notes.
        covered_scope = (best_inc is not None and inc_score >= self._gray_min) or exc_hits > 0
        # The free text the engine produces (basis/reasoning/assumptions/coverage) is
        # generated in the PROJECT language and written frozen into the evidence chain
        # (audit: never translated afterwards).
        # FOR DEPENDENCY REQUESTS THE EFFORT DRIVER IS THE USAGE SURFACE, NOT MODULE
        # LOC: a version upgrade doesn't rewrite the module, it touches call sites.
        # The LOC path here produced 98–173h on a 14k-LOC project, contradicting the
        # tool's ~2h floor (the triage inconsistency); the surface path ties both ends
        # to the same reality.
        dep_surface = (
            self._dep_surface(sub.package, impacted)
            if sub.type is RequestType.DEPENDENCY_CHANGE and sub.package
            else None
        )
        estimate = estimation.estimate(
            similar, impacted, self._est_params,
            lang=self._language, dep_surface=dep_surface,
        )

        decision, confidence, matched, matched_sim, reasoning = self._classify(
            sub, best_inc, inc_score, best_exc, exc_hits, exc_score,
            touches_scoped, estimate, maint_item, maint_score,
            short_query=len(query) < MIN_QUERY_TOKENS,
            sem_no_cover=sem_no_cover,
        )
        pool_breach = self._pool_ratio(best_inc, estimate) >= _POOL_WARN
        risk = _risk(impacted, budget_breach=pool_breach, lang=self._language)
        # SECURITY-MOTIVATED DEPENDENCY: the scope decision still follows the
        # contract (if out of scope it's a CR — someone pays), but the RISK layer
        # escalates: deferring a security patch creates risk regardless of scope
        # → 24h escalation.
        dep_security = (
            sub.type is RequestType.DEPENDENCY_CHANGE and has_security_wording(sub.item)
        )
        if dep_security:
            if _RANK[risk.probability] < _RANK["yüksek"]:
                risk.probability = "yüksek"
            if risk.level in (RiskLevel.LOW, RiskLevel.MEDIUM):
                risk.level = RiskLevel.HIGH
            risk.escalation = True
            risk.signals.append(t("engine.risk.sig_security", self._language))

        clauses = [matched.source_clause] if matched and matched.source_clause else []
        assumptions = self._assumptions(
            covered_scope, bool(impacted), bool(similar), lang=self._language
        )
        if llm_note:
            assumptions = [llm_note, *assumptions]
        if llm_note_sem:
            assumptions = [llm_note_sem, *assumptions]
        if llm_note_rr:
            assumptions = [llm_note_rr, *assumptions]
        if llm_note_veto:
            assumptions = [llm_note_veto, *assumptions]
        # DEPENDENCY NOTE (informational, no decision effect): if the request was
        # recognized as a library add / version migration, the manifest reality is
        # written into the evidence chain. Decision/confidence are already
        # determined — structurally signal-free.
        if sub.type is RequestType.DEPENDENCY_CHANGE:
            declared = next(
                (d for d in self._dependencies if d.name == sub.package), None
            )
            status = (
                t("engine.dep_declared", self._language,
                  manifest=declared.manifest, spec=declared.raw_spec or "*")
                if declared is not None
                else t("engine.dep_undeclared", self._language)
            )
            note = t(
                "engine.dependency_note", self._language,
                package=sub.package or sub.item, status=status,
                version=sub.target_version or "—",
            )
            assumptions = [note, *assumptions]
            if dep_security:
                assumptions = [
                    t("engine.dep_security_note", self._language), *assumptions
                ]
            # USED API SURFACE: the concrete call sites to audit on a version
            # change (impacted already derived from package usage).
            if sub.package:
                from etki.adapters.manifests import normalize_pkg

                wanted_pkg = normalize_pkg(sub.package)
                apis = sorted({
                    s
                    for m in impacted
                    for pkg, symbols in m.package_apis.items()
                    if normalize_pkg(pkg) == wanted_pkg
                    for s in symbols
                })
                if apis:
                    shown = ", ".join(apis[:8]) + ("…" if len(apis) > 8 else "")
                    assumptions = [
                        t("engine.dep_api_note", self._language,
                          n=len(apis), apis=shown),
                        *assumptions,
                    ]
        # MEMORY NOTE: if the cited clause has a past PMO correction/dispute, an
        # informational note is added to the evidence chain. Decision and
        # confidence are ALREADY determined at this point — structurally
        # signal-free (the engine.sem_hint pattern). A DISPUTE additionally
        # escalates the RISK layer (same pattern as the security-wording rule:
        # scope decision untouched, but conflicting final rulings on the cited
        # clause mean a PMO must look before ruling again — 24h escalation).
        if matched is not None and self._precedents:
            memory = self._precedents.get(matched.id) or (
                self._precedents.get(matched.source_clause) if matched.source_clause else None
            )
            if memory and memory.get("disputed"):
                assumptions = [t("engine.disputed_note", self._language), *assumptions]
                if self._disputed_escalation:
                    risk.escalation = True
                    risk.signals.append(t("engine.risk.sig_disputed", self._language))
            if memory and memory.get("count"):
                note = t(
                    "engine.precedent_note", self._language,
                    n=memory["count"], last=memory.get("last") or "—",
                )
                assumptions = [note, *assumptions]
        evidence = EvidenceChain(
            checked_against=[item.id for item in self._baseline.scope_items],
            best_match=BestMatch(
                item=matched.id if matched else None, similarity=round(matched_sim, 3)
            ),
            impacted_modules=[m.id for m in impacted],
            impacted_signals=[
                ModuleSignal(
                    id=m.id,
                    loc=m.complexity.loc,
                    cyclomatic=m.complexity.cyclomatic,
                    churn=m.churn.commits_last_6mo,
                )
                for m in impacted
            ],
            source_coverage=self._coverage(
                covered_scope, inc_score, impacted, similar, lang=self._language
            ),
            assumptions=assumptions,
            reasoning=reasoning,
            contract_clauses_cited=clauses,
            cited_clauses=[matched.model_copy(deep=True)] if matched is not None else [],
        )
        cr_draft = None
        if decision in (Decision.OUT_OF_SCOPE, Decision.CR_CANDIDATE):
            lang = self._language
            module_ids = ", ".join(m.id for m in impacted) or t("engine.cr.no_modules", lang)
            cr_draft = CrDraft(
                impact_analysis=t(
                    "engine.cr.impact", lang,
                    modules=module_ids, risk=t(f"risk.{risk.level.value}", lang),
                ),
                cost=t(
                    "engine.cr.effort", lang,
                    low=f"{estimate.low:.0f}", high=f"{estimate.high:.0f}",
                ),
            )

        return TriageDecision(
            request_id=decision_id,
            decision=decision,
            confidence=confidence,
            evidence=evidence,
            effort_estimate=estimate,
            risk=risk,
            cr_draft=cr_draft,
            index_freshness=self._index_freshness,
            model_version=self._model_version,
            human_decision=PmoDecision.PENDING,
            decided_at=datetime.now(UTC),
        )

    @staticmethod
    def _coverage(
        covered_scope: bool,
        inc_score: float,
        impacted: list[CodeModule],
        similar: list[WorkItem],
        *,
        lang: str = "tr",
    ) -> list[SourceCoverage]:
        """Whether each of the three sources (spec/code/history) covers this request."""
        scope_detail = (
            t("engine.cov.best_clause", lang, score=f"{inc_score:.2f}")
            if covered_scope
            else t("engine.cov.no_clause", lang)
        )
        code_detail = (
            t("engine.cov.modules", lang, n=len(impacted))
            if impacted
            else t("engine.cov.no_modules", lang)
        )
        hist_detail = (
            t("engine.cov.similar", lang, n=len(similar))
            if similar
            else t("engine.cov.no_similar", lang)
        )
        return [
            SourceCoverage(
                source=t("engine.cov.spec", lang), covered=covered_scope, detail=scope_detail
            ),
            SourceCoverage(
                source=t("engine.cov.code", lang), covered=bool(impacted), detail=code_detail
            ),
            SourceCoverage(
                source=t("engine.cov.history", lang), covered=bool(similar), detail=hist_detail
            ),
        ]

    @staticmethod
    def _assumptions(
        covered_scope: bool, has_code: bool, has_history: bool, *, lang: str = "tr"
    ) -> list[str]:
        """Assumptions made for missing sources (transparency + a more accurate estimate)."""
        notes: list[str] = []
        if covered_scope and not has_code:
            notes.append(t("engine.asm.spec_no_code", lang))
        if not has_history:
            notes.append(t("engine.asm.no_history", lang))
        if not covered_scope and has_code:
            notes.append(t("engine.asm.code_no_spec", lang))
        if not covered_scope and not has_code and not has_history:
            notes.append(t("engine.asm.no_evidence", lang))
        return notes

    async def _merge_scope_modules(
        self, impacted: list[CodeModule], item: ScopeItem
    ) -> list[CodeModule]:
        """Adds the modules mapped to the matched scope clause to the impacted set (dedup).

        The scope↔code mapping produced during indexing (`mapped_modules`) is carried
        into triage here: even with an empty hint, the matched clause's code regions
        stay visible."""
        by_id = {m.id: m for m in await self._code_repo.list_modules()}
        have = {m.id for m in impacted}
        extra = [by_id[mid] for mid in item.mapped_modules if mid in by_id and mid not in have]
        return impacted + extra

    async def _llm_match(
        self,
        request: str,
        best_inc: ScopeItem | None,
        inc_score: float,
        impacted: list[CodeModule],
    ) -> tuple[ScopeItem | None, str, list[CodeModule], str] | None:
        """Semantic/cross-lingual matching via LLM (called when deterministic is weak).

        Semantically maps the request to scope clauses (INCLUDED or EXCLUDED) + code
        modules (TR request ↔ EN spec/code). The returned clause is whitelist-verified;
        `_decide` assigns its decision effect: strong INCLUDED → in-scope floor,
        strong EXCLUDED → exclusion path (LLM = independent second evidence), weak →
        gray floor only. Error / no match → None (deterministic result preserved).

        Returns: (clause|None, "strong"|"weak", impacted modules, evidence note)."""
        items = self._baseline.scope_items
        all_modules = await self._code_repo.list_modules()
        if not items and not all_modules:
            return None
        # Clause descriptions from the contract + the request text are UNTRUSTED
        # data: a poisoned document could try to steer the matching → delimiter +
        # guard (the whitelist verification below is kept as the second line of
        # defense).
        item_lines = "\n".join(
            f"- {i.id}: {sanitize_untrusted(i.description)} [{i.polarity.value}]"
            for i in items[:40]
        )
        mod_lines = "\n".join(
            f"- {m.id}: {sanitize_untrusted(', '.join(m.responsibilities) or m.path)}"
            for m in all_modules[:40]
        )
        task = (
            "You are Etki's scope-matching assistant. Match the given request "
            "SEMANTICALLY against the contract scope clauses and code modules; language-"
            "independent (the request and the clauses/code may be in different languages). "
            "Return ONLY this JSON: "
            '{"scope_item_id": <id or null>, "match_strength": "strong"|"weak", '
            '"impacted_modules": [<module-id>...], '
            f'"rationale": "<one-sentence justification — in \'{self._language}\'>"' + "}\n"
            "Rules: (1) If the request's DELIVERABLE falls within a clause's scope, return "
            "that clause's id; if the request asks for work an [EXCLUDED] clause rules out, "
            "return that exclusion clause's id. (2) If no clause covers the request or you "
            "are unsure, return scope_item_id=null — do NOT FORCE a request for a NEW "
            "capability onto an existing clause; word similarity alone is not a match. "
            '(3) match_strength: "strong" when the deliverable is the clause\'s explicit '
            'scope, "weak" for indirect/partial similarity.\n\n' + UNTRUSTED_GUARD
        )
        # A per-project domain/instruction preamble, when set, is prepended to system.
        system = f"{self._system_preamble}\n\n{task}" if self._system_preamble else task
        user = (
            f"REQUEST:\n{wrap_untrusted(request)}\n\n"
            f"SCOPE CLAUSES:\n{wrap_untrusted(item_lines)}\n\n"
            f"CODE MODULES:\n{wrap_untrusted(mod_lines)}"
        )
        try:
            payload = await self._llm.complete_json(system=system, user=user)  # type: ignore[union-attr]
        except Exception:  # noqa: BLE001
            logger.warning("LLM eşleştirme başarısız; deterministik sonuçla devam.", exc_info=True)
            return None

        by_id = {m.id: m for m in all_modules}
        have = {m.id for m in impacted}
        ids = payload.get("impacted_modules") or []
        extra = [by_id[x] for x in ids if isinstance(x, str) and x in by_id and x not in have]
        # Whitelist: only a clause id that ACTUALLY exists in the baseline is accepted
        # (polarity doesn't matter — an exclusion match is a legitimate, valuable result too).
        item = next((i for i in items if i.id == payload.get("scope_item_id")), None)
        if item is None and not extra:
            return None  # the LLM found no link either → no change
        raw_strength = str(payload.get("match_strength") or "").strip().lower()
        strength = "strong" if raw_strength == "strong" else "weak"  # unknown → cautious
        # LLM output is sanitized too (control chars / delimiter reflection) + 200 char cap.
        rationale = sanitize_untrusted(str(payload.get("rationale") or "").strip(), 200)
        note = t("engine.llm_note", self._language) + (f": {rationale}" if rationale else "")
        return item, strength, impacted + extra, note

    async def _rerank_best_included(self, request: str) -> tuple[ScopeItem | None, float]:
        """Best INCLUDED clause via cross-encoder + raw logit score. Error → (None, -inf)
        (if the layer is absent/crashes the lexical result is preserved as-is — graceful
        degradation)."""
        items = [
            i for i in self._baseline.scope_items if i.polarity is not Polarity.EXCLUDED
        ]
        if not items:
            return None, float("-inf")
        try:
            scores = await self._reranker.rerank(  # type: ignore[union-attr]
                request, [i.description for i in items]
            )
        except Exception:  # noqa: BLE001
            logger.warning("Reranker erişilemedi; sözlüksel sonuçla devam.", exc_info=True)
            return None, float("-inf")
        if len(scores) != len(items):
            return None, float("-inf")
        best_idx = max(range(len(items)), key=lambda k: scores[k])
        return items[best_idx], scores[best_idx]

    async def _llm_verify_exclusion(
        self, request: str, item: ScopeItem
    ) -> tuple[str, str | None]:
        """v7b confirmation question: does an exclusion clause grazing on a SINGLE
        word really forbid this request? "not_excluded" → the lexical hit is treated
        as an artifact, the exclusion is ignored (veto). Error/ambiguity →
        ("excluded", None): the deterministic route is preserved as-is (fail-open —
        the veto layer can never exclude on its own, it can only cancel a wrong
        exclusion)."""
        task = (
            "You are Etki's exclusion-verification assistant. You will be given a "
            "REQUEST and an EXCLUSION (out-of-scope) clause that overlaps the request "
            "on a single word. The question: is the WORK the clause excludes the same "
            "WORK the request asks for — does the clause really forbid this request? "
            "Return ONLY this JSON: "
            '{"verdict": "excluded"|"not_excluded", '
            f'"rationale": "<one sentence — in \'{self._language}\'>"' + "}\n"
            "Rules: (1) Word overlap alone is not exclusion ('mobile number field' ≠ "
            "'mobile app development'). (2) If the request asks for the excluded work "
            "itself or a part of it, answer excluded. (3) When unsure, answer "
            "excluded — the veto is only for clear artifacts.\n\n" + UNTRUSTED_GUARD
        )
        system = f"{self._system_preamble}\n\n{task}" if self._system_preamble else task
        user = (
            f"REQUEST:\n{wrap_untrusted(request)}\n\n"
            f"EXCLUSION CLAUSE ({item.id}):\n{wrap_untrusted(item.description)}"
        )
        try:
            payload = await self._llm.complete_json(system=system, user=user)  # type: ignore[union-attr]
        except Exception:  # noqa: BLE001
            logger.warning(
                "LLM dışlama doğrulaması başarısız; deterministik rota korunur.", exc_info=True
            )
            return "excluded", None
        if str(payload.get("verdict") or "").strip().lower() != "not_excluded":
            return "excluded", None
        note = t(
            "engine.exc_veto_note", self._language, ref=item.source_clause or item.id
        )
        return "not_excluded", note

    async def _llm_verify(self, request: str, item: ScopeItem) -> tuple[str, str | None]:
        """v4a verification question: does a single SELECTED INCLUDED clause cover
        the request, or is the request close to the clause but a NEW capability the
        contract doesn't grant?

        v3's lesson: the bottleneck was candidate generation — here there is no
        candidate, only the clause pick chose from the full list; only the
        covers/new_capability distinction is asked. Error or unknown verdict →
        ("covers", None), i.e. it falls back to plain v2 pick behavior (fail-open:
        the verification layer can never overturn a decision on its own, it can
        only cancel the floor)."""
        task = (
            "You are Etki's scope-verification assistant. You will be given a REQUEST "
            "and the SINGLE contract clause matched at the pick stage. The question: "
            "does the scope this clause explicitly promises COVER this request (a "
            "rephrasing / subset of the same deliverable), or is the request CLOSE to "
            "the clause but asking for a NEW capability/deliverable the clause does not "
            "grant? Return ONLY this JSON: "
            '{"verdict": "covers"|"new_capability", '
            f'"rationale": "<one sentence — in \'{self._language}\'>"' + "}\n"
            "Rules: (1) Word similarity alone is not coverage. (2) If a new deliverable/"
            "feature/automation absent from the clause is being asked for, answer "
            "new_capability. (3) When unsure, answer covers — this layer only fires on "
            "a clear new-capability case.\n\n" + UNTRUSTED_GUARD
        )
        system = f"{self._system_preamble}\n\n{task}" if self._system_preamble else task
        user = (
            f"REQUEST:\n{wrap_untrusted(request)}\n\n"
            f"CLAUSE ({item.id}):\n{wrap_untrusted(item.description)}"
        )
        try:
            payload = await self._llm.complete_json(system=system, user=user)  # type: ignore[union-attr]
        except Exception:  # noqa: BLE001
            logger.warning("LLM doğrulama başarısız; pick sonucu korunur.", exc_info=True)
            return "covers", None
        verdict = str(payload.get("verdict") or "").strip().lower()
        if verdict != "new_capability":
            return "covers", None
        rationale = sanitize_untrusted(str(payload.get("rationale") or "").strip(), 200)
        note = t("engine.llm_note", self._language) + (f": {rationale}" if rationale else "")
        return "new_capability", note

    def _judge_shortlist(self, query: set[str], text: str) -> list[ScopeItem]:
        """Candidate clauses for the judge: lexical top-2 INCLUDED + top-1 EXCLUDED
        (+ any semantic candidates are already reflected in the scores before
        _decide). With no signal at all, the first 3 clauses are given — so the
        judge can say 'unrelated'."""
        scored = [
            (score(query, tokenize(f"{i.description} {i.category}")), i)
            for i in self._baseline.scope_items
        ]
        inc = sorted((p for p in scored if p[1].polarity is not Polarity.EXCLUDED),
                     key=lambda p: p[0], reverse=True)
        exc = sorted((p for p in scored if p[1].polarity is Polarity.EXCLUDED),
                     key=lambda p: p[0], reverse=True)
        picks = [i for s, i in inc[:2] if s > 0] + [i for s, i in exc[:1] if s > 0]
        if self._item_vecs:  # with a warm semantic cache the 2 nearest clauses would qualify too
            # (vectors may have been computed in _semantic_best; without a query
            # vector, keeping the lexical order beats recomputing cosine.)
            pass
        if not picks:
            picks = [i for _, i in scored[:3]]
        seen: set[str] = set()
        out: list[ScopeItem] = []
        for i in picks:
            if i.id not in seen:
                seen.add(i.id)
                out.append(i)
        return out[:5]

    async def _llm_judge(
        self, request: str, impacted: list[CodeModule]
    ) -> tuple[ScopeItem | None, str, list[CodeModule], str] | None:
        """v3 judge mode: asks for an EXPLICIT per-clause verdict on the candidate
        shortlist — covers | new_capability | excluded | unrelated (+ strength). The
        critical difference from pick mode is `new_capability`: the verdict "a new
        capability not committed to in the contract despite word/semantic proximity"
        PROTECTS the CR answer from gray drift (v1/v2's measured weak spot).
        Whitelist + sanitation apply unchanged."""
        query = tokenize(request)
        candidates = self._judge_shortlist(query, request)
        if not candidates:
            return None
        by_id = {c.id: c for c in candidates}
        cand_lines = "\n".join(
            f"- {c.id} [{c.polarity.value}]: {sanitize_untrusted(c.description)}"
            for c in candidates
        )
        task = (
            "You are Etki's scope JUDGE. Judge the given request against each "
            "candidate clause separately and return ONLY this JSON: "
            '{"verdicts": [{"id": "<clause-id>", "verdict": '
            '"covers"|"new_capability"|"excluded"|"unrelated", '
            '"strength": "strong"|"weak"}...], '
            f'"rationale": "<one sentence — in \'{self._language}\'>"' + "}\n"
            "Rules: (1) covers = the request's DELIVERABLE is an instance/paraphrase of "
            "the clause's commitment. (2) new_capability = the request is RELATED to the "
            "clause but asks for a NEW capability not committed to in the contract — "
            "word/semantic proximity alone does NOT make covers; when in doubt say "
            "new_capability. (3) excluded = the request asks for work an [EXCLUDED]-"
            "marked clause explicitly rules out. (4) unrelated = no meaningful relation "
            "to the clause.\n\n" + UNTRUSTED_GUARD
        )
        system = f"{self._system_preamble}\n\n{task}" if self._system_preamble else task
        user = (
            f"REQUEST:\n{wrap_untrusted(request)}\n\n"
            f"CANDIDATE CLAUSES:\n{wrap_untrusted(cand_lines)}"
        )
        try:
            payload = await self._llm.complete_json(system=system, user=user)  # type: ignore[union-attr]
        except Exception:  # noqa: BLE001
            logger.warning("LLM eşleştirme başarısız; deterministik sonuçla devam.", exc_info=True)
            return None

        verdicts = payload.get("verdicts") or []
        rationale = sanitize_untrusted(str(payload.get("rationale") or "").strip(), 200)
        note = t("engine.llm_note", self._language) + (f": {rationale}" if rationale else "")
        best_cover: tuple[ScopeItem, str] | None = None
        for v in verdicts:
            if not isinstance(v, dict):
                continue
            item = by_id.get(str(v.get("id") or ""))  # whitelist: candidate ids only
            if item is None:
                continue
            verdict = str(v.get("verdict") or "").lower()
            strength = "strong" if str(v.get("strength") or "").lower() == "strong" else "weak"
            if verdict == "excluded" and item.polarity is Polarity.EXCLUDED:
                return item, strength, impacted, note  # _decide: strong→exclusion, weak→ignore
            if (
                verdict == "covers"
                and item.polarity is not Polarity.EXCLUDED
                and (best_cover is None or (strength == "strong" and best_cover[1] == "weak"))
            ):
                best_cover = (item, strength)
        if best_cover is not None:
            return best_cover[0], best_cover[1], impacted, note
        # All verdicts new_capability/unrelated → the decision DOES NOT change; the
        # note lands in the evidence (CR protection: the judge said 'new capability',
        # no gray drift).
        return None, "weak", impacted, note

    async def _safe_find_similar(self, text: str) -> list[WorkItem]:
        # If the remote PM environment (Jira/GLPI) is unreachable, triage must not
        # blow up → effort falls back to the code metric.
        try:
            return await self._work_items.find_similar(text)
        except Exception:  # noqa: BLE001
            logger.warning(
                "work_items.find_similar başarısız; benzer-iş olmadan devam.", exc_info=True
            )
            return []

    def _match_scope(
        self, query: set[str]
    ) -> tuple[ScopeItem | None, float, ScopeItem | None, int, float]:
        best_inc: ScopeItem | None = None
        best_inc_score = 0.0
        best_exc: ScopeItem | None = None
        best_exc_hits = 0
        best_exc_score = 0.0
        for item in self._baseline.scope_items:
            target = tokenize(f"{item.description} {item.category}")
            if item.polarity is Polarity.EXCLUDED:
                h = hits(query, target)
                if h > best_exc_hits:
                    best_exc, best_exc_hits, best_exc_score = item, h, score(query, target)
            else:
                s = score(query, target)
                if s > best_inc_score:
                    best_inc, best_inc_score = item, s
        return best_inc, best_inc_score, best_exc, best_exc_hits, best_exc_score

    async def _semantic_best(
        self, text: str
    ) -> tuple[ScopeItem | None, float, ScopeItem | None, float]:
        """Best INCLUDED and EXCLUDED clause by cosine similarity: (inc, cos, exc, cos).

        Clause vectors are computed lazily + batched and kept in a cache keyed to
        the baseline version. Endpoint error → (None, 0, None, 0) — the lexical
        path is unaffected (graceful degradation)."""
        if self._embedder is None or not self._baseline.scope_items:
            return None, 0.0, None, 0.0
        try:
            if self._item_vecs_version != self._baseline.version:
                texts = [f"{i.description} {i.category}" for i in self._baseline.scope_items]
                vecs = await self._embedder.embed(texts)
                self._item_vecs = {
                    i.id: v
                    for i, v in zip(self._baseline.scope_items, vecs, strict=True)
                }
                self._item_vecs_version = self._baseline.version
            qvec = (await self._embedder.embed([text], kind="query"))[0]
        except Exception:  # noqa: BLE001
            logger.warning("embedding servisi başarısız; sözlüksel eşleşmeyle devam.",
                           exc_info=True)
            return None, 0.0, None, 0.0
        best_inc: ScopeItem | None = None
        best_inc_cos = 0.0
        best_exc: ScopeItem | None = None
        best_exc_cos = 0.0
        for item in self._baseline.scope_items:
            vec = self._item_vecs.get(item.id)
            if vec is None:
                continue
            c = _cosine(qvec, vec)
            if item.polarity is Polarity.EXCLUDED:
                if c > best_exc_cos:
                    best_exc, best_exc_cos = item, c
            elif c > best_inc_cos:
                best_inc, best_inc_cos = item, c
        return best_inc, best_inc_cos, best_exc, best_exc_cos

    def _maintenance_clause(self) -> ScopeItem | None:
        """The contract's first INCLUDED maintenance clause (citation target for the
        relaxed maintenance path — independent of text overlap with the request)."""
        return next(
            (
                i
                for i in self._baseline.scope_items
                if i.polarity is Polarity.INCLUDED and i.category == "maintenance"
            ),
            None,
        )

    @staticmethod
    def _dep_surface(
        package: str, impacted: list[CodeModule]
    ) -> estimation.DependencySurface:
        """Effort surface of a dependency request: the modules that ACTUALLY import
        the package (excluding 1-hop neighbours — they stay in the impact list but
        are not effort drivers) + the used-API symbols visible in the code graph."""
        from etki.adapters.manifests import normalize_pkg

        wanted = normalize_pkg(package)
        users = [
            m for m in impacted if wanted in {normalize_pkg(p) for p in m.packages}
        ]
        apis = {
            s
            for m in users
            for pkg, symbols in m.package_apis.items()
            if normalize_pkg(pkg) == wanted
            for s in symbols
        }
        return estimation.DependencySurface(modules=len(users), apis=len(apis))

    async def _package_impacted(self, package: str) -> list[CodeModule]:
        """Usage surface of a package: modules importing it + one hop of their
        dependency neighbours (the same spread rule as `impacted_modules`)."""
        # Pure normalization helper (contains no vendor) — the import↔package-name
        # matching must use the SAME rule in the engine and the tool layer.
        from etki.adapters.manifests import normalize_pkg

        modules = await self._code_repo.list_modules()
        wanted = normalize_pkg(package)
        used = [
            m for m in modules if wanted in {normalize_pkg(p) for p in m.packages}
        ]
        by_id = {m.id: m for m in modules}
        seen = {m.id for m in used}
        out = list(used)
        for module in used:
            for neighbour in (*module.depends_on, *module.depended_by):
                if neighbour in by_id and neighbour not in seen:
                    seen.add(neighbour)
                    out.append(by_id[neighbour])
        return out

    def _best_included_in_category(
        self, query: set[str], category: str
    ) -> tuple[ScopeItem | None, float]:
        best: ScopeItem | None = None
        best_score = 0.0
        for item in self._baseline.scope_items:
            if item.polarity is Polarity.EXCLUDED or item.category != category:
                continue
            s = score(query, tokenize(f"{item.description} {item.category}"))
            if s > best_score:
                best, best_score = item, s
        return best, best_score

    def _classify(
        self,
        sub: SubRequest,
        best_inc: ScopeItem | None,
        inc_score: float,
        best_exc: ScopeItem | None,
        exc_hits: int,
        exc_score: float,
        touches_scoped: bool,
        estimate: EffortEstimate,
        maint_item: ScopeItem | None,
        maint_score: float,
        *,
        short_query: bool = False,
        sem_no_cover: bool = False,
    ) -> tuple[Decision, float, ScopeItem | None, float, str]:
        # Reasoning is produced in the project language (frozen in the evidence chain).
        lang = self._language
        # 1) Maintenance scope → maintenance flow (the maintenance clause is looked up
        # specifically). Two paths: (a) the request overlaps the maintenance clause
        # itself (classic path), or (b) a defect-type request references an INCLUDED
        # feature and hits no exclusion — a defect report naturally overlaps the
        # broken feature's clause, not the maintenance clause (e.g. EN: "report page
        # crashes with a 500"). On path (b) the citation target is independent of the
        # text score: even if the defect text shares no word with the maintenance
        # clause, it is cited as long as the contract HAS a maintenance clause.
        strong_maint = maint_item is not None and maint_score >= self._gray_min
        maint_ref = maint_item if maint_item is not None else self._maintenance_clause()
        # v5c: a defect report referencing delivered functionality proves it via
        # EITHER text overlap with an included clause OR code evidence (impacted
        # modules mapped to scoped clauses) — "the login button does nothing"
        # shares no token with the auth clause but clearly touches scoped code.
        weak_maint = (
            maint_ref is not None
            and exc_hits == 0
            and (inc_score >= self._gray_min or touches_scoped)
        )
        if sub.type is RequestType.MAINTENANCE and (strong_maint or weak_maint):
            cited = maint_item if strong_maint else maint_ref
            assert cited is not None  # strong_maint→maint_item, weak_maint→maint_ref
            return (
                Decision.MAINTENANCE,
                0.85,
                cited,
                maint_score,
                t(
                    "engine.rsn.maintenance", lang,
                    ref=cited.source_clause or cited.id,
                ),
            )
        # 1b) Dependency change (D2 — justified by measurement: dependency_crs first
        # honest run 4/14, manifest evidence never entered the decision steps).
        # A new evidence type for the two-evidence rule: the MANIFEST reality is
        # code reality.
        #   - declared package + a maintenance clause in the contract → MAINTENANCE
        #     (a version update is the natural scope of the maintenance clause)
        #   - "upgrading" an undeclared package → GRAY (conflicting evidence: the
        #     request says "it exists", the manifest says "it doesn't" → PMO
        #     escalation)
        #   - an undeclared new library → CR floor (new capability)
        # Exclusion guard: if there is ANY EXCLUDED hit this step never runs —
        # "let's add an SSO library" keeps falling into the exclusion path.
        if sub.type is RequestType.DEPENDENCY_CHANGE and exc_hits == 0:
            if sub.package is not None and maint_ref is not None:
                return (
                    Decision.MAINTENANCE,
                    0.85,
                    maint_ref,
                    maint_score,
                    t(
                        "engine.rsn.dep_maintenance", lang,
                        package=sub.package,
                        ref=maint_ref.source_clause or maint_ref.id,
                    ),
                )
            if sub.package is None:
                from etki.engine.understanding import _DEP_VERB

                upgrade_wording = any(v in sub.item.lower() for v in _DEP_VERB)
                if upgrade_wording:
                    # Says "upgrade" but the manifest doesn't know it — conflicting evidence.
                    return (
                        Decision.GRAY_AREA,
                        0.5,
                        None,
                        0.0,
                        t("engine.rsn.dep_gray", lang),
                    )
                return (
                    Decision.CR_CANDIDATE,
                    0.75,
                    None,
                    0.0,
                    t("engine.rsn.dep_new", lang),
                )
        # 2) Negative (EXCLUDED) match — the highest-confidence out-of-scope.
        # A single 'sso' hit excludes; but a generic 'entegrasyon' (also in 5.1) does
        # not: single-hit exclusion only when clearly stronger (_EXC_MARGIN) than the
        # INCLUDED match. (Tried and REVERTED: an extra coverage bar on single hits —
        # it filtered 'bulk import of customer data'-type ambient collisions but also
        # killed LEGITIMATE single-head-term exclusions like 'develop a mobile app' /
        # 'real-time streaming feed'; the golden set objected with two cases.
        # Ambient-collision artifacts are documented as EtkiBench finding #2 and
        # the semantic separation belongs to the LLM lane.)
        if best_exc is not None and exc_hits >= 1 and (
            exc_hits >= 2 or exc_score > inc_score * _EXC_MARGIN
        ):
            return (
                Decision.OUT_OF_SCOPE,
                0.9,
                best_exc,
                exc_score,
                t("engine.rsn.excluded", lang, ref=best_exc.source_clause or best_exc.id),
            )
        # 3) Positive (INCLUDED) match + two-evidence rule
        if best_inc is not None and inc_score >= self._in_scope_min:
            # 3a) limit / quota breach
            limit = best_inc.limits.quantity
            if sub.quantity is not None and limit is not None and sub.quantity > limit:
                return (
                    Decision.CR_CANDIDATE,
                    0.85,
                    best_inc,
                    inc_score,
                    t(
                        "engine.rsn.limit", lang,
                        qty=sub.quantity, limit=limit,
                        ref=best_inc.source_clause or best_inc.id,
                    ),
                )
            # 3b) effort-pool breach. (Tried and REVERTED: a short-request exemption —
            # it rescued "payments"/"usability"-type single-word gray cases, but
            # golden GS-53 expects pool-CR on the single word "entegrasyon"; two
            # answer keys give opposite labels to the same structure and the key
            # wins. The tension is documented in the EtkiBench README.)
            if best_inc.effort_pool_hours:
                consumed = self._consumed.get(best_inc.category, 0.0)
                if consumed + estimate.high > best_inc.effort_pool_hours:
                    ref = best_inc.source_clause or best_inc.id
                    return (
                        Decision.CR_CANDIDATE,
                        0.8,
                        best_inc,
                        inc_score,
                        t(
                            "engine.rsn.pool", lang,
                            consumed=f"{consumed:.0f}", high=f"{estimate.high:.0f}",
                            pool=f"{best_inc.effort_pool_hours:.0f}", ref=ref,
                        ),
                    )
            # 3c-guard) a very short request (1-2 meaningful words) can never be
            # high-confidence IN SCOPE → gray area (the PMO-escalation principle;
            # protection against score inflation).
            if short_query:
                return (
                    Decision.GRAY_AREA,
                    0.5,
                    best_inc,
                    inc_score,
                    t("engine.rsn.short_query", lang),
                )
            # 3c) in scope
            confidence = min(0.95, 0.5 + inc_score + (0.1 if touches_scoped else 0.0))
            note_key = "engine.rsn.touches_code" if touches_scoped else "engine.rsn.weak_code"
            return (
                Decision.IN_SCOPE,
                round(confidence, 3),
                best_inc,
                inc_score,
                t(
                    "engine.rsn.in_scope", lang,
                    item=best_inc.source_clause or best_inc.id, note=t(note_key, lang),
                ),
            )
        # 4) Medium similarity → gray area → PMO
        if inc_score >= self._gray_min:
            # v5b: the gray band mostly holds two very different populations —
            # genuinely vague asks (correctly GRAY) and new-capability requests
            # whose word overlap with a clause is a tokenizer artifact. When the
            # cross-encoder says NO clause covers the request, a full-sentence
            # gray-band case is the artifact kind → CR. Short/vague requests are
            # exempt (they are the population the gray band exists for).
            if sem_no_cover and not short_query:
                return (
                    Decision.CR_CANDIDATE,
                    0.55,
                    best_inc,
                    inc_score,
                    t("engine.rsn.cr_sem_no_cover", lang),
                )
            return (
                Decision.GRAY_AREA,
                0.5,
                best_inc,
                inc_score,
                t("engine.rsn.gray", lang),
            )
        # 5) No match → CR candidate. (The short-request exception is DELIBERATELY
        # absent: the golden set labels a matchless short request as CR — the
        # gray-area idea for single-word "performance"-type requests was tried and
        # contradicted the answer key.)
        return (
            Decision.CR_CANDIDATE,
            0.6,
            best_inc,
            inc_score,
            t("engine.rsn.no_match", lang),
        )

    def _pool_ratio(self, best_inc: ScopeItem | None, estimate: EffortEstimate) -> float:
        if best_inc is None or not best_inc.effort_pool_hours:
            return 0.0
        consumed = self._consumed.get(best_inc.category, 0.0)
        return (consumed + estimate.high) / best_inc.effort_pool_hours


_TR_QUESTION_PARTICLE = re.compile(r"\b(mı|mi|mu|mü|mıdır|midir|mudur|müdür)\b", re.IGNORECASE)


def _merge_modules(a: list[CodeModule], b: list[CodeModule]) -> list[CodeModule]:
    """Union by module id, order preserved (hint-derived first, then package-derived)."""
    seen = {m.id for m in a}
    return a + [m for m in b if m.id not in seen]


def _is_interrogative(text: str) -> bool:
    """Question-form requests ('Can the system be faster?', '... kapsamda mı?')
    signal the asker's own uncertainty — they stay eligible for GRAY."""
    stripped = text.strip()
    return "?" in stripped or bool(_TR_QUESTION_PARTICLE.search(stripped))


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


_RANK = {"düşük": 0, "orta": 1, "yüksek": 2}


def _risk(impacted: list[CodeModule], *, budget_breach: bool = False, lang: str = "tr") -> Risk:
    max_churn = max((m.churn.commits_last_6mo for m in impacted), default=0)
    max_cx = max((m.complexity.cyclomatic for m in impacted), default=0)
    count = len(impacted)

    # Probability from the WORSE of two signals: change history (churn) AND code
    # complexity. On a new/shallow-clone project churn is ~0/1 → complexity kicks in
    # (so we never say "low risk" from commits alone). With history, churn can also
    # raise it.
    p_churn = "yüksek" if max_churn > 20 else "orta" if max_churn > 10 else "düşük"
    p_cx = "yüksek" if max_cx > 150 else "orta" if max_cx > 50 else "düşük"
    probability = p_churn if _RANK[p_churn] >= _RANK[p_cx] else p_cx
    impact = "yüksek" if count >= 4 else "orta" if count >= 2 else "düşük"
    level = _RISK_MATRIX[(probability, impact)]

    signals: list[str] = []
    if max_churn > 20:
        signals.append(t("engine.risk.sig_churn", lang, n=max_churn))
    if max_cx > 50:
        signals.append(t("engine.risk.sig_cx", lang, n=max_cx))
    if count >= 4:
        signals.append(t("engine.risk.sig_spread", lang))
    if budget_breach:
        signals.append(t("engine.risk.sig_pool", lang))
        if level is RiskLevel.LOW:
            level = RiskLevel.MEDIUM

    if max_churn > 1:
        basis = t("engine.risk.basis_churn", lang, churn=max_churn, cx=max_cx)
    else:
        basis = t("engine.risk.basis_cx", lang, cx=max_cx, n=count)

    escalation = level in (RiskLevel.HIGH, RiskLevel.CRITICAL) or budget_breach
    return Risk(
        probability=probability,
        impact=impact,
        level=level,
        escalation=escalation,
        signals=signals,
        basis=basis,
    )


__all__ = ["TriageEngine", "split_request"]
