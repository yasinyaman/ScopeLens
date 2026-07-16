# Etki — Operations Runbook (Phase 4)

## Deployment (Docker)

```bash
docker compose up -d --build          # app (8000) + Postgres (5433)
curl -s localhost:8000/health         # {"status":"ok"}
open http://localhost:8000/           # live assistant UI
docker compose down                   # stop (data persists in the pgdata volume)
```

- The container ships no JVM → the code graph uses the **`ast`** adapter (`config/connectors.docker.yaml`). The index is built automatically on first request.
- **Fill in `.env` first** (`cp .env.example .env`): `POSTGRES_PASSWORD`, `ETKI_SESSION_SECRET` (long random), `ETKI_ADMIN_USER`/`ETKI_ADMIN_PASSWORD` (first PMO user). compose won't start without these.
- Env vars (all `ETKI_`-prefixed): `DB_URL`, `CONNECTORS_PATH`, `SESSION_SECRET`, `ADMIN_USER`/`ADMIN_PASSWORD`, `MAX_UPLOAD_MB`, `DEMO_MODE`, `IN_SCOPE_THRESHOLD`, `GRAY_THRESHOLD`, `DEFAULT_LANGUAGE` (default UI language tr|en|de), `FORCE_CODE_ENGINE` (`ast` | `joern` | `graphify`), `LLM_PROVIDER` (`anthropic`), `ANTHROPIC_API_KEY`/`ANTHROPIC_MODEL`, `COOKIE_SECURE` (set `true` on any TLS deployment — Secure session cookie + HSTS).
- **Health probes:** `/health` (liveness) and `/ready` (is the DB + engine ready; the compose healthcheck polls this). The Postgres port is not published to the host.
- **`workers=1` is MANDATORY.** The per-project triage engines (and their living baselines) are process-local; running uvicorn/gunicorn with more than one worker forks divergent baseline copies (a CR approved in worker A is invisible in worker B). The app **fails hard at startup** if `WEB_CONCURRENCY`/`UVICORN_WORKERS` > 1. Scale by giving the single worker more CPU, not by adding workers. (Since baselines are now rehydrated from the DB at startup, making the engine stateless and lifting this limit is a known future work item.)

## Database schema & migrations (Alembic)

The schema is now managed by **Alembic** (for production schema evolution; `create_all` is only a test/sqlite convenience):

```bash
ETKI_DB_URL=postgresql+psycopg://... uv run alembic upgrade head   # create/update the schema
uv run alembic revision --autogenerate -m "description"                 # new migration when models change
```
The first PMO user is created at startup from `ETKI_ADMIN_*` env (when there are no users) **or**
with `uv run python -m etki.persistence create-user <name> pmo`. After that, day-to-day user
administration lives in the UI: **Settings → Users** (pmo-only) — create/delete users, change
roles, edit per-user project grants, reset passwords. Guard rails: you cannot delete your own
account, and the last `pmo` user can be neither deleted nor demoted. A password reset rotates
the session-binding token, so the target's live sessions drop immediately.

## Code index (Joern) refresh — scheduled

The live Joern index (CPG) for production-grade impact analysis is produced on the host machine / CI; it can be mounted into the container as `.etki/index.json`.

```bash
uv run python -m etki.indexing          # all projects (or: ... indexing <project_id>)
```

The CLI runs the exact same path as the UI's reindex (`context.index_project`):
doc_root composite documents, multi-repo merged graph, and a DB-baseline reconcile —
approved CRs survive a re-index. A document that fails to parse is skipped with a
warning; it never takes the whole project's indexing down.

Recommended cron (nightly full re-index, more often for high-churn modules):
```cron
0 2 * * *  cd /opt/etki && uv run python -m etki.indexing >> /var/log/etki-index.log 2>&1
```
> If the index is stale it shows in the decision's freshness stamp (`index_freshness`) and
> as a yellow/red badge on the project screen; incremental re-indexing is future work.

**In-app alternative (single-container/pilot deployments, both OFF by default):**

```bash
ETKI_REINDEX_INTERVAL_HOURS=24   # background full re-index of every project + context rebuild
ETKI_POOL_REFRESH_MINUTES=15     # lightweight effort-pool recompute from the work-item
                                   # provider (no code/document re-index; engines see the
                                   # new consumed-by-category totals in place)
```

Cron remains the recommended production path (observable, survives restarts mid-cycle);
the in-app loops exist so a plain `docker compose up` deployment can stay fresh without
host-level scheduling. Note: work-item **similar-job evidence** is always fetched live at
triage time regardless — these intervals only affect the code/document index and the
effort-pool totals.

### graphify engine (optional, multi-language, no JVM)

For non-Python repos (JS/TS, Go, Java, …) the **`graphify`** engine (tree-sitter based, PyPI package `graphifyy`) produces the same normalized code index without a JVM — so it also works inside the container:

```bash
uv sync --extra graphify                       # installs the graphify CLI (graphifyy)
ETKI_FORCE_CODE_ENGINE=graphify uv run python -m etki.indexing
```

Config: `code_repo: { adapter: graphify, options: { src_root: ..., export_dir: ..., refresh: true } }`. The graph is written to `export_dir` (default `<src_root>/../graphify-out`) so cloned customer repos stay pristine; the build is deterministic (`graphify update --no-cluster`, no LLM key needed). Known limits: per-file LOC is derived from line counts and control-structure counts are unavailable (cyclomatic complexity falls back to the function count). Symbol-level API capture (`package_apis`, the dependency-effort surface) needs **graphify-mcp** installed (`pip install "graphify-mcp[treesitter] @ git+https://github.com/yasinyaman/graphify-mcp"` until it reaches PyPI); without it the surface stays empty and dependency-effort estimates carry the wider unknown-surface band.

### Cross-encoder reranker (optional assist, opt-in)

A TEI-compatible `/rerank` endpoint (`ETKI_RERANK_BASE_URL`, raw logits) feeds the
v4b matching lane — measured +12 pts on EtkiBench with no LLM. Where the official
TEI image is unavailable (arm64/GB10 boxes), `scripts/rerank_server.py` serves the
same contract:

```bash
pip install fastapi uvicorn sentence-transformers
python scripts/rerank_server.py --model BAAI/bge-reranker-v2-m3 --port 8021
# app side: ETKI_RERANK_BASE_URL=http://<host>:8021
```

Keep it **opt-in**: on the frozen golden set the lane currently costs adversarial
cases (see the EtkiBench scoreboard); leave `ETKI_RERANK_BASE_URL` unset unless
you accept that trade-off. CI never sets it (the gate stays deterministic).

## Decision wiki (file-based decision memory)

Every triage decision is automatically projected into a per-project markdown wiki
(`.etki/wiki-{project}/`, path template via `ETKI_WIKI_DIR`; empty string disables).
The **database stays the single source of truth** — the wiki is a regenerable
projection, so it never needs its own backup:

```bash
uv run python -m etki.wiki search "SSO entegrasyonu" --project demo   # find precedents
uv run python -m etki.wiki show DEC-20260709-req-demo-1a2b3c4d --project demo
uv run python -m etki.wiki rebuild            # regenerate ALL projects from the DB
```

Do not hand-edit wiki files (`rebuild` overwrites them). Deleting a project keeps its
wiki (readable projection of the preserved audit history). If the decision files contain
personal data, the directory falls under the same residency/access rules as the DB —
see `KVKK.md`. Search prefers `rg` (ripgrep) when installed and falls back to a pure-Python
scan.

The wiki also carries the **derived HITL memory** (regenerated on every PMO decision and
by `rebuild`): a PMO override promotes the case to `precedents/PRE-*.md` (boundary-case
memory), and conflicting resolved decisions on the same contract clause are collected in
`disputed.md` — read it before ruling on that clause again. Counters for both appear on
the project's Raporlar screen. Concepts and retrieval details: see
[Decision memory](memory.md).

## Backup & restore (Postgres)

```bash
docker compose exec db pg_dump -U postgres etki > backup_$(date +%F).sql   # date computed on the host
cat backup.sql | docker compose exec -T db psql -U postgres etki           # restore
```
The audit trail (`audit_events`) and versioned baseline (`baseline_versions`) are backed up — so every decision stays reconstructable for a contractual dispute.

## Capability negotiation & graceful degradation

Each adapter declares its capabilities (`supports_webhooks/realtime/effort_tracking/incremental_diff`). The system degrades accordingly:
- no webhooks → periodic polling; no incremental diff → full re-index.
- For a composite document source, a capability is supported only if **all children** support it (most conservative).

### Adapter health (degraded-adapter visibility)

A work-items or documents adapter that fails to **build** (bad options, a plugin
that failed to load, unreachable config) never takes the project down: the context
falls back to an empty fake and records an `AdapterHealth` entry. Degraded adapters
surface as **red badges** on the project's Özet screen and the Dosyalar work-items
card (tooltip = the recorded error), and the Raporlar effort-pool figures carry a
"pool may be stale" note when the provider failed at refresh time. There is **no
auto-heal**: fix the config/plugin, then re-save the work-items settings or trigger
a reindex — the context rebuild clears the badge. A project deliberately
*configured* with the `fake` adapter is not "degraded"; the badge only appears when
a real adapter fell back.

## Pluggability (vendor swap)

Moving to a new organization = a **config change** (`connectors.*.yaml`); core code does not change:
```yaml
work_items: { adapter: glpi|jira|file, ... }
code_repo:  { adapter: joern|ast|graphify, ... }
documents:  { adapter: filesystem|composite, ... }
```
Proof: `tests/integration/test_composite.py` — the documents `filesystem → composite` swap yields the same decision.

## Plugins (install, lockfile, policy)

Third-party adapters ship as **plugin packages** against `etki-api` (entry-point
group `etki.adapters`). Operational rules:

- **Policy is an env-only admin lock:** `ETKI_PLUGIN_POLICY=verified_only`
  (default — installs blocked, non-editable unverified distributions don't even
  load) | `allow_git` | `allow_local`. Deliberately NOT a UI/Settings value;
  `.etki/llm.json` cannot touch it.
- **Install** (operator CLI, capability confirmation from the static manifest —
  plugin code is never executed for the prompt):
  ```bash
  ETKI_PLUGIN_POLICY=allow_git uv run python -m etki.plugin install git+https://…@v1.2.0
  ETKI_PLUGIN_POLICY=allow_local uv run python -m etki.plugin install ./acme.whl --sha256 <hash>
  ```
  Branches are rejected; tags resolve to the full commit SHA and the SHA is what
  installs and locks. Wheel installs verify SHA-256 BEFORE anything runs.
- **`etki-plugins.lock`** (TOML, repo-committable) records source/commit/hash/
  capabilities per plugin. `python -m etki.plugin sync` reproduces the exact
  state on a new machine (local wheels re-hash-verified); `remove <dist>`
  uninstalls + drops the entry; `list [--json]` is the KVKK inventory feed.
- **Verified marketplace** (signed index): under the default `verified_only`
  policy the ONLY install path is an index-verified one:
  ```bash
  uv run python -m etki.plugin search acme --index https://…/index.json
  uv run python -m etki.plugin install etki-plugin-acme --index https://…/index.json
  ```
  A REMOTE index requires a valid **sigstore** signature (keyless, GitHub OIDC;
  the verification tooling ships behind the optional extra `etki[plugins]` — the
  base/air-gapped install never pulls it). The signer identity is pinned to the
  index repo's release workflow, overridable for forks/self-hosted marketplaces
  via `ETKI_PLUGIN_INDEX_IDENTITY`/`ETKI_PLUGIN_INDEX_ISSUER` (env-only, like the
  policy). The artifact's SHA-256 must match the index BEFORE any install
  subprocess; success writes `verified = true` to the lockfile — which is also
  what lets the plugin load at runtime under `verified_only`.
- **Air-gapped flow:** mirror on the ONLINE side —
  `python -m etki.plugin mirror <index-url> <dir>` (the signature is verified at
  mirror time, every artifact hash-checked, recorded in `mirror-manifest.json`) —
  carry the directory inside, then `install <name> --index <dir>` offline.
  Inside the mirror SHA-256 stays mandatory and the signature is optional
  (a missing sigstore toolchain degrades to a warning; a FAILED verification is
  always fatal).
- **UI — Settings → Plugins** (`/ayarlar/eklentiler`, pmo-only): every installed
  plugin with status (`active/failed/incompatible/blocked/disabled` + error
  text), install source (from the lockfile), `api_compat` and a verified badge;
  the policy is displayed **read-only**. The single UI mutation is
  enable/disable (persisted to `.etki/plugins.json`; the toggle rebuilds the
  registry/context) — install/remove/policy have **no HTTP endpoint by design**.
- **Containers install plugins at IMAGE BUILD TIME** from the lockfile — see
  `Dockerfile.plugins`. Runtime `sync` inside a container does not survive a
  restart (immutable images); it is for bare-metal/venv deployments.
- Private git hosts: authenticate via a git **credential helper** — never embed
  tokens in the URL (it would be recorded in the lockfile).
- The public `etki-plugins` index repo is not bootstrapped yet — until it lands,
  the marketplace path runs against mirrors/fixture indexes; git-tag and wheel
  installs are the current distribution channels.

## Pilot (shadow mode) & calibration

```bash
uv run python -m etki.pilot      # the system recommends, compared against the PMO reference
```
Report: decision agreement, effort-in-range hit rate, per-decision-type P/R, **confidence calibration**, threshold suggestion. Thresholds are config-driven (`ETKI_IN_SCOPE_THRESHOLD`); the calibration suggestion is applied with human approval.

## Multilingual & per-project LLM profile
- **Global LLM provider (UI-managed):** **Settings → AI Assistant** (pmo-only) selects *off / Anthropic Claude API / OpenAI-compatible (Ollama, vLLM)*, with model, endpoint, timeout and a **connection-test** button. Values are persisted to `.etki/llm.json` (chmod 600, git-ignored, only whitelisted LLM keys) and **take precedence over env vars** — "off" in the UI wins even when `ETKI_LLM_BASE_URL` is set. Changes apply on the next request (engine contexts rebuild; no restart). Keys are never echoed back to the form; an empty field keeps the stored secret, and a checkbox wipes stored keys. In production, prefer env vars for secrets and leave the UI fields empty.
- **UI language (TR/EN/DE):** changed from the top-right via `POST /dil` (written to the session); on first visit `Accept-Language` → `ETKI_DEFAULT_LANGUAGE`. UI text only; does not change data flow.
- **Per-project LLM profile:** each project gets an **output language** + a selectable **domain/skill profile** (`config/domains/*.md`) + free-text instructions (Files & Settings screen → `POST /projeler/{id}/ayarlar/llm-profili`). The index does not change; only the context cache is cleared. An optional **pivot translation** is enabled per project (translate input → working language → reason → translate back; extra LLM call). A new domain profile = add a `config/domains/<id>.md` file.

## Security
Authentication is a **real login** (pbkdf2 + signed session cookie); the old self-asserted `X-Role` header was removed. Roles (RBAC v3): `pmo` approves and administers, `engineer` runs triage/analysis, **`viewer` is read-only** (all mutating endpoints reject it with 403). **Project access is isolated** (RBAC v2): a user only sees projects granted in the `user_projects` table (managed in **Settings → Users**, or `create-user <name> <role> --projects p1,p2`); case/evidence endpoints derive the project from the case itself (no IDOR); the top-bar portfolio count is shown to `pmo` only. The `pmo` role bypasses grants while `ETKI_PMO_GLOBAL=true` (single-customer default) — set it to `false` for multi-customer pilots.

**Session hardening:** login is rate-limited in-process (5 failures per IP+username within 15 min → 15 min lock; single-worker enforcement makes the in-memory counter authoritative; a restart resets it). The post-login redirect only accepts site-relative paths (open-redirect guard). CSRF is covered twice: `same_site=lax` cookies plus a middleware that rejects mutating requests browsers stamp `Sec-Fetch-Site: cross-site`. Sessions are **token-bound to the password hash**: a password reset or user deletion invalidates live sessions on their next request, and role changes apply immediately (the role is re-read from the DB per request). "Remember me" is enforced server-side — 30 days checked, 8 hours unchecked. For production hardening (reverse proxy + OAuth/SSO + internal network) and KVKK/VERBİS/DPIA, see `docs/KVKK.md`.

**Hardening pass (2026-07 security audit):**
- Markdown from LLM output / user text (pre-analysis, chat) renders with **raw HTML
  disabled** — `<script>`/`<img onerror=…>` in a saved analysis is escaped, not
  executed (stored-XSS fix).
- Responses carry `X-Content-Type-Options: nosniff` and `X-Frame-Options: DENY`;
  with `ETKI_COOKIE_SECURE=true` (any TLS deployment) the session cookie gains
  `Secure` and HSTS is sent. Keep it `false` only for local HTTP dev.
- Uploads are size-capped (`ETKI_MAX_UPLOAD_MB`, default 20) and docx/xlsx archives
  declaring an unsafe expansion are rejected **before parsing** (zip-bomb guard:
  512 MB expanded / 200× ratio ceilings; PDFs get page and extracted-text caps).
- User/config-supplied LLM, embedding and rerank endpoints are refused when they
  point at the cloud instance-metadata range (`169.254.0.0/16` — SSRF guard,
  `etki/net_guard.py`). Localhost/RFC1918 stay allowed on purpose: local
  Ollama/vLLM is the primary use case.
- `.etki/llm.json` is created 0600 atomically (no window where an API key sits
  world-readable).

## Productization (notes)
- **Multi-project:** each contract gets its own baseline + index; separated by `contract_id`/`project_id`.
- **Multi-customer:** data separation (schema/DB per customer) + per-customer connector config.
- **Licensing:** core + adapter packages; vendor adapters can ship as plugins.
