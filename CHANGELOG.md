# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
(pre-1.0: minor versions may break APIs).

## [Unreleased]

## [0.1.0a4] - 2026-07-17

### Added

- **Request intake + write-back** — Etki can now poll a tracker (e.g. Jira) for
  new client requests, triage each through the existing pipeline into a PENDING
  case, and write the decision back to the source. Write-back timing is
  per-project (`on_decision` — after the PMO decides, the default and the
  copilot invariant — / `on_triage` / `both`); it is best-effort and never
  blocks an approval. Configure via *Dosyalar → Talep Kanalı*, or the in-app
  `ETKI_INTAKE_POLL_MINUTES` loop / `python -m etki.intake` cron. This is the
  first WRITING integration; the Jira connection ships as the `etki-plugin-jira`
  plugin.
- **etki-api 0.1.2** — two new ports `RequestIntakeProvider` +
  `ResponseChannel` (the first writing port), models `IncomingRequest` /
  `IntakeBatch` / `OutboundResponse`, `SecurityCapabilities.external_write`, two
  conformance contracts, and a `py.typed` marker.
- **Plugin submission tooling** — `scripts/build_plugin_submission.py` and a
  `workflow_dispatch` GitHub Action build a plugin's verified-marketplace bundle
  (wheel + green conformance report + schema-validated `index.json` entry) in one
  step. Plugins are distributed on GitHub only (signed index / git), never PyPI.
- **Marketplace browse UI** — the Settings → Plugins screen gained a lazy-loaded
  card projecting the SIGNED index: search, per-plugin summary/ports/capability
  declaration, highest compatible version vs the installed etki-api,
  installed/update badges and a copyable operator-CLI install command. Index
  source is env-only (`ETKI_PLUGIN_INDEX_URL`, default = the official index; a
  mirror directory works air-gapped); responses cached in-process for 15 min.
- **UI install (opt-in)** — with env-only `ETKI_PLUGIN_UI_INSTALL=true`
  (default OFF) the market card offers Install/Update to pmo users, using ONLY
  the verified path: env-pinned source, capability confirmation, the same
  signature + SHA-256 + lockfile chain as the CLI; git/wheel targets still have
  no UI route. Installs are audited as `plugin_install` process-log events.
- **Plugin detail & adapter defaults page** (`/ayarlar/eklentiler/<plugin>`) —
  status/manifest info plus a default-options form per adapter rendered from
  its `options_model` (e.g. the Linear `api_key`). Stored 0600/atomic in
  `.etki/plugin-options.json`; secret-named fields are masked, never echoed
  back, kept on empty submit, and clearable via Reset. Defaults merge UNDER
  project options at build time — the project value always wins.

### Changed

- `python -m etki.plugin search|install` no longer require `--index`: both
  resolve the same trust root as the UI (`ETKI_PLUGIN_INDEX_URL` env, else the
  official index) and print the resolved source.

## [0.1.0a3] - 2026-07-16

### Added

- **Plugin runtime (Faz 2)** — entry-point discovery over the `etki.adapters`
  group (`PluginRegistry`: broken/incompatible plugins are isolated with loud
  logs, never crash startup; builtin adapter names always win). `adapter: linear`
  now resolves through the installed `etki-plugin-linear` plugin — the builtin
  file was removed, config is unchanged. `TriageDecision.plugin_set` stamps the
  active plugin set into every decision's audit trail. `python -m etki.plugin
  list [--json]` feeds the KVKK inventory; plugins can register MCP tools via
  the `etki.mcp_tools` group.
- **Plugin distribution (Faz 3)** — `python -m etki.plugin install|sync|remove`
  with a byte-stable `etki-plugins.lock` (TOML). `ETKI_PLUGIN_POLICY` ordered
  levels `verified_only` (default, fail-closed) < `allow_git` < `allow_local`;
  git tags resolve to full commit SHAs (the SHA installs and locks), wheel
  SHA-256 is verified before any subprocess, and under `verified_only` a
  non-editable distribution without a verified lockfile entry is `blocked` at
  registry load. Containers install plugins at image build time
  (`Dockerfile.plugins`).
- **Conformance suite "AdapterBench" (Faz 4)** — `etki_api.conformance`
  (extra `etki-api[conformance]`, etki-api 0.1.1): contract tests pinning the
  documented semantics of all seven ports + a JSON-report runner
  (`python -m etki_api.conformance <dist> --report out.json`). Reusable GitHub
  workflow `plugin-conformance.yml`; the linear plugin runs through it on every
  push.
- **Verified marketplace (Faz 5)** — signed plugin index (sigstore keyless
  verification behind the `etki[plugins]` extra; air-gapped mirrors are
  hash-mandatory), `search`/`install <name> --index <url|dir>`/`mirror` CLI,
  and the **Ayarlar → Eklentiler** screen (statuses, verified badge, read-only
  policy; the only UI-writable action is enable/disable).
- **Plugin UI round (U1–U4)** — the work-items adapter dropdown is registry-fed
  (installed plugins appear with zero template edits); `AdapterHealth`
  degradation badges on Özet/Dosyalar/Raporlar; `plugin_set` provenance on case
  screens; typed option models for the builtin work-item adapters with a
  schema-rendered options form (`env:` references are never resolved for
  display).

### Security

- Fixes from the 2026-07 security audit: markdown rendering hardened against
  stored XSS, zip-bomb cap on document uploads, `Secure` session cookie +
  security headers, case-chat cross-project access closed, plugin-installer git
  URL validation, SSRF guard for LLM endpoints (`net_guard`), atomic 0600
  writes for `.etki/llm.json`, upload size caps.

### Removed

- **GLPI adapter** (adapter, options model, registry branch, tests, docs) —
  work-item trackers are now file/Jira/GitLab/Redmine/Azure DevOps/Linear
  (plugin).

### Fixed

- `plugin-conformance` CI job: `uv venv --clear` — setup-uv pre-creates the
  venv and recent uv errors instead of silently replacing it.

## [0.1.0a2] - 2026-07-15

### Added

- **Plugin API (Faz 1)** — the repo is now a **uv workspace**. New PyPI package
  **`etki-api`** (import `etki_api`, depends only on pydantic) carries the frozen
  plugin surface: the seven external-integration ports (`WorkItemProvider`,
  `CodeRepositoryProvider`, `DocumentSourceProvider`, `LLMClient`,
  `EmbeddingProvider`, `RerankProvider`, `RegistryMetadataProvider`) +
  `Capabilities`, the normalized models (`WorkItem`, `CodeModule`, `DocumentRef`,
  `PackageMetadata`, …), the plugin contract (`PluginSpec`, `AdapterFactory`,
  `SecurityCapabilities`; entry-point group `etki.adapters`) and the
  `etki-plugin.toml` manifest loader. `etki.core.ports`/`etki.core.models`
  re-export the moved symbols (same class objects — no behavior change).
- **`etki-plugin-linear`** — the Linear adapter extracted as the first-party
  reference plugin (depends only on `etki-api` + httpx); the built-in adapter
  remains until runtime plugin discovery lands (Faz 2).
- The API surface is contract-tested (`tests/unit/test_api_surface.py`);
  `docs/writing-an-adapter.md` gained plugin packaging + semver policy sections;
  `etki-api` keeps its own CHANGELOG under `packages/etki-api/`.

### Changed

- Release workflow publishes `etki` and `etki-api` from separate jobs/environments
  (`pypi` / `pypi-etki-api`) via PyPI trusted publishing.

## [0.1.0a1] - 2026-07-14

First public release.

### Changed (2026-07-14)

- **Rebrand: Kapsam → Etki** — package `etki/`, env prefix `ETKI_*`, data dir
  `.etki/`, default DB `etki.db`, benchmark **EtkiBench**, repo
  `yasinyaman/etki`. Full-depth rename (alpha, no backward compatibility).
  Turkish UI terms that used "etki" in its natural sense ("impact") were
  neutralized so they can't be read as the brand: the Sankey screen is now
  **Akış Haritası / Flow Map / Flusskarte**, and "etki analizi" became
  "yayılım analizi" in Turkish UI strings and the `.docx` report (EN/DE keep
  "impact analysis" — no collision there).

### Added (2026-07-13/14)

- **Ask (Sor) screen** — a single-input question box per project: an instant
  deterministic answer over the knowledge graph (source-labeled), and, with an
  LLM configured, an AI answer grounded in that deterministic result. Questions
  and answers append to the process log (`.etki/process-log.jsonl`), documented
  in the KVKK/compliance data inventories.
- **Explorable index screens** — clause detail (`/madde/{id}`: rulings, memory
  and pool status per scope item), per-module code-graph table (repo-scoped),
  index-run history, baseline version timeline (which CR added which clause,
  when), and effort-pool bars that expand into a per-item consumption breakdown.
- **Report ergonomics** — KPI tiles link to the lists that answer "which
  ones?"; decision-distribution badges filter the history screen; Özet document
  rows preview inline.
- **Petrol palette** — teal brand, reserved status colors, copper audit accent;
  role-neutral landing copy; stylesheet cache-busting by content mtime.

### Added (2026-07-11/12)

- **Surface-based dependency effort** — for dependency-change requests the effort
  driver is the usage surface (importing modules + used-API call sites;
  `estimation.DependencySurface`, `ETKI_EST_DEP_*` constants), not module LOC: a
  14k-LOC FastAPI version bump moved from 98.4–173.0h to an evidence-backed
  13.4–23.5h. `dependency_impact` now returns an `estimate` from the same estimator,
  so tool and engine numbers can no longer contradict each other.
- **Multi-language symbol capture under graphify** — the graphify adapter fills
  `package_apis`/`package_api_paths` via graphify-mcp's `api_uses_for_source`
  (optional seam; Python via stdlib ast, JS/TS/Go/Java via its `[treesitter]`
  extra). Engine absent → empty surface → the estimator's unknown-surface widening
  (honest degradation). Also stops graphify's per-file imported-symbol nodes from
  leaking into imports as phantom packages.
- **Disputed-clause risk escalation** — a request citing a clause with conflicting
  final PMO rulings escalates the risk layer (24h look + signal); decision,
  confidence and effort stay byte-identical (pinned by test). Kill switch:
  `ETKI_DISPUTED_ESCALATION=false`.
- `scripts/rerank_server.py` — minimal TEI-compatible `/rerank` server
  (sentence-transformers, raw logits) for hosts without an official TEI image
  (arm64/GB10).

### Changed (2026-07-11/12)

- **Single indexing path** — `python -m etki.indexing` now delegates to
  `context.index_project` (doc_root composite, multi-repo merged graph, DB-baseline
  reconcile); its old raw-connectors copy could feed a project the fake corpus and
  overwrite approved CRs. `IndexingEngine.build` skips unparseable documents with a
  warning instead of failing the whole project.
- **UI consolidation** — Onaylar is now a PENDING-only approval queue; the separate
  Analizler page folded into Geçmiş as tab filters (old URL redirects); the Hafıza
  screen keeps only its distinct content (disputes/precedents/wiki search) with
  explicit empty states.
- **English source pass** — all code comments, docstrings and LLM prompts are
  English; runtime Turkish (i18n values, logs, eval output, fixtures, stopword
  tables) deliberately unchanged. Re-measured: the guarded assist held (see the
  EtkiBench scoreboard).

### Measured (2026-07-12, EtkiBench v0, English prompts)

- gpt-oss:20b + live bge-reranker-v2-m3: **62/66 (94%)**; gpt-oss:20b / gemma3:27b
  88%; deterministic+reranker 80% (no LLM); deterministic floor 68%. The reranker
  lane stays opt-in: it costs 4 adversarial cases on the frozen golden set
  (61 → 57/66) — `rerank_strong` recalibration on a dev set is the follow-up.
  *Follow-up CLOSED 2026-07-22:* a 7-threshold sweep over 174 dev cases on the
  current engine found no better operating point (-8 gains one dev case but
  drops golden 57 → 56); **-6.8 stays the default, assist stays opt-in** — see
  the sweep table in `eval/datasets/etkibench/README.md`.
- Live packing A/B (GraphRAG): rerank packing loses to BFS (recall 0.99 → 0.97) —
  published as a negative; packing stays BFS.

### Fixed

- **Effort-pool accounting was dead on English corpora (v8)** — the payments
  clause tied 1–1 between category keyword lists and lost on dict order,
  keying its effort pool away from the payment work items (`consumed` stayed
  0 forever). English card keywords break the tie; regression-tested. Net 0
  on the benchmark (a documented label tension, see the EtkiBench README),
  but the pool feature now actually fires for real deployments.

### Added

- **Dependency-impact analysis (library add / version upgrade)** — measures
  the project impact of dependency changes across ecosystems. Offline core:
  manifest parsers (requirements.txt, pyproject.toml, package.json, pom.xml,
  go.mod, Cargo.toml — verbatim version specs, no cross-ecosystem
  resolution), external-import capture in the code graph (the previously
  discarded complement of internal imports), `dependency_impact` tool
  (IndexTools + MCP + agent + nl_query whitelist), "package" graph nodes
  with `uses_package` edges, a Bağımlılıklar card on project detail.
  Triage recognizes dependency-change requests (`RequestType.
  DEPENDENCY_CHANGE`; version numbers never leak into quantity/limit
  checks). Online registry metadata (PyPI/npm/Maven Central) is opt-in
  (`ETKI_DEPS_ONLINE`, off by default; query-time display only). The
  decision branch was built dataset-first: the labeled set measured the old
  tree at 29%, the branch (declared+maintenance-clause → MAINTENANCE,
  undeclared upgrade → GRAY, new library → CR floor, exclusions always win)
  re-measured at 93%; golden set unchanged.
- **Clause memory read at decision time** (follow-up package to the GraphRAG
  layer): the approval screen shows a per-decision precedent/disputed strip;
  the engine adds a NON-SIGNAL informational note to the evidence chain when
  the cited clause has past PMO corrections or conflicting rulings (decision
  and confidence byte-identical by test; golden set unchanged); a per-project
  **Hafıza** screen (wiki search + DB-backed precedent/disputed cards); the
  developer pre-analysis receives graph-packed related context; MCP gains
  `graph_query` and `wiki_search`; wiki search becomes prefix/synonym-tolerant
  (engine tokenizer) and wiki headings render in the project's language; the
  graph-retrieval CI gate extends to a second TR corpus (shop 0.70→1.00 at
  precision 0.34, first honest run) with `strategy_routing.json` pinning the
  strategy selector.
- **GraphRAG memory layer — all four phases** (plan:
  `Etki_GraphRAG_Hafiza_Plani.md`):
  - **Decision wiki (Faz 1)** — every triage decision is auto-projected to a
    per-project markdown wiki (`.etki/wiki-{id}/`: `decisions/DEC-*.md`,
    generated `index.md`, entity backlink pages). The wiki is ALWAYS a
    projection of the DB: single writer (`ApprovalService.sync_wiki`),
    regenerable bit-identical via `python -m etki.wiki rebuild`, and a wiki
    failure never breaks triage. `WikiStore` port +
    `adapters/filesystem_wiki.py` (PyYAML frontmatter, rg-with-Python-fallback
    token-AND search); `ETKI_WIKI_DIR` (empty = off); CLI
    `python -m etki.wiki search|show|rebuild`. `delete_project` preserves
    the wiki (readable projection of the preserved audit history).
  - **GraphQueryPort (Faz 2)** — three retrieval strategies behind one port
    (`etki/graphquery.py`): `find_k_nodes` (embedding cosine when
    `ETKI_EMBED_*` is set, else the engine's lexical score; retrieval-only,
    never a decision signal), `expand` (token-budgeted BFS over the index's
    real edges), `nl_query` (LLM picks ONE whitelisted read-only IndexTools
    call, injection-guarded, falls back to `find_k`). Rule-based strategy
    selector; the chosen path is recorded in `QueryResult.strategy`. Eval:
    `eval/graph_retrieval.py` over a pre-committed 24-query set — TR recall
    find_k 0.82 → find_k+expand 1.00 at precision 0.36; CI gate wired into
    `eval/runner`. The triage decision path is unchanged.
  - **HITL ingest loop (Faz 3)** — PMO feedback flows back into the derived
    memory: an override promotes the case to `precedents/PRE-*.md`,
    conflicting resolved decisions on the same cited clause project to
    `disputed.md` (`hitl/ingest.py`; idempotent by projection — duplicate
    ingest is byte-identical; no queue/Celery). KPI gains
    `precedent_count`/`disputed_count` + Raporlar tiles (tr/en/de).
  - **Rerank-packed expand (Faz 4 harness)** — `expand(…, query=)` packs
    non-seed neighbours by cross-encoder relevance (existing
    `TeiRerankClient`; `Subgraph.packing: bfs|rerank`); without a reranker the
    behavior is byte-identical BFS. A/B harness
    (`eval/graph_retrieval.ab_pack`); a keyword-fake smoke showed a weak
    reranker can HURT recall (0.99→0.97) — the live bge-reranker-v2-m3
    measurement awaits a TEI endpoint.
- **Cross-encoder reranker evidence layer (v4b)** — `RerankProvider` port +
  TEI-compatible `/rerank` adapter (`ETKI_RERANK_BASE_URL`, off by default,
  CI unchanged). A cross-encoder reads the (request, clause) pair jointly and
  is the first measured non-LLM mechanism that separates "paraphrase of a
  clause" from "new capability near it" (AUC 0.975 on EtkiBench). Include-
  side floor only, raw-logit threshold `ETKI_RERANK_STRONG` calibrated for
  bge-reranker-v2-m3; measured on the dev set: deterministic 41/66 → 45/66
  with zero regressions.
- **Pick-then-verify assist (v4a, opt-in)** — `ETKI_LLM_ASSIST_MODE=verify`;
  measured negative (see the EtkiBench README), default remains "pick".
- **Assist gate widening + exclusion veto (v7)** — exclusion-grazing requests
  now reach the guarded LLM (strong EXCLUDED picks only; the include floor
  stays strict), and a margin-based single-hit exclusion gets one focused
  confirmation question before routing OUT (fail-open). Full stack:
  gpt-oss:120b **136/150 (91%)**, dev-66 62/66 (94%); zero regressions.
- **Word-number quantities (v5a)** — EN+TR cardinals and ordinals reach the
  limit/quota check ("six reports", "a fourth provider", "altı rapor");
  ambiguous tokens ("on", "one", "bir") deliberately excluded.
- **Reranker as negative evidence (v5b)** — when the cross-encoder shows no
  clause covers a declarative gray-band request, it is reclassified CR
  (tokenizer-artifact population); short/vague and **interrogative** requests
  stay GRAY. Deterministic dev-66: 47 → **51/66 (77%)**, zero regressions,
  golden set unchanged — the LLM-free row has gone 50% → 77% since v1.
- **Defect-symptom routing (v5c)** — symptom phrases without defect vocabulary
  ("cuts off", "empty page") route to maintenance, and defect-type requests may
  prove delivered-functionality via code evidence (impacted scoped modules)
  instead of text overlap. Deterministic dev-66 with local layers:
  **53/66 (80%)** — maintenance 6/6, zero regressions, golden unchanged.
- **Vendor lexicon (v4c)** — conservative brand→concept tokenizer bridge
  (Okta/Auth0/Entra→idp, Android/iPhone→mobile, Ethereum→cryptocurrency):
  requests name products, contracts name concepts. Deterministic 41→43 on
  the dev benchmark; combined with the reranker: **47/66 (71%)**, zero
  regressions, frozen golden set unchanged.

Initial public state of **Etki** (previously developed as Kapsam, earlier
ScopeLens; history was squashed at each rename):

- **Triage engine** — deterministic decision tree (maintenance → EXCLUDED match
  → two-evidence code+text → limit/quota → effort-pool) over a versioned living
  baseline; three-point/PERT effort **ranges** (single points forbidden); every
  decision carries a frozen, localized evidence chain.
- **Hexagonal adapters** — work items: file/Jira/GitLab/Redmine/Azure DevOps/
  Linear/GLPI; documents: filesystem/composite/Confluence/SharePoint; code
  graph: Joern CPG or dependency-free Python AST; optional LLM
  (Anthropic/OpenAI-compatible) and embedding providers. Selection is
  configuration, never code; secrets via `env:` references.
- **HITL & audit** — approval workflow (approve/reject/convert-to-CR, baseline
  version+1), full audit trail, RBAC with per-project grants, KPI dashboard.
- **PMO Guard UI** — project-centric HTMX screens (triage + auto pre-analysis
  + case chat, approvals, analyses, reports, Request→Clause→Module Sankey),
  TR/EN/DE i18n, per-project LLM language/domain profile.
- **EtkiBench** — public 66-case benchmark with clause-citing rationales,
  one-command reproduction, pre-registered one-shot held-out sets, and a CI
  **freeze guard** that keeps engine changes and answer-key edits apart.
- **Ops** — Docker/compose stacks (JVM-free demo profile: `docker compose -f
  docker-compose.demo.yml up --build`, login demo/demo), Alembic migrations,
  MCP server with a read-only `triage_request` tool, MkDocs documentation.
