# Getting started

## Try it in 5 minutes — no API key

One command starts a fully seeded **English demo** (sample contract + code repo + past
work items). No LLM key, no JVM, no Postgres — the decision path is fully deterministic:

```bash
git clone https://github.com/yasinyaman/etki.git && cd etki
docker compose -f docker-compose.demo.yml up --build
```

Open <http://localhost:8000>, log in as `demo` / `demo` (hard-coded for local evaluation
only), open the **Meridian CRM (demo)** project → **Triage**, and try:

- *"We need SAML single sign-on with our corporate identity provider"* → **out of scope**,
  citing the explicit exclusion (Clause 7.1), with the effort such a CR would take —
  estimated from similar past tickets.
- *"Add a date filter to the monthly standard report"* → **in scope** (Clause 4.2.1),
  impacted modules, and an effort range by analogy.

## Local development setup

Requirements: Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync --dev                                   # venv + dependencies (editable install)
cp .env.example .env                            # settings (LLM optional)
uv run python -m etki.persistence create-user   # first PMO user (or ETKI_ADMIN_*)
uv run uvicorn etki.api.app:app --reload   # http://localhost:8000  (API docs: /docs)
```

Only the *first* PMO user needs the CLI/env bootstrap — after that, manage users (roles,
per-user project grants, password resets) from **Settings → Users** in the UI. Roles:
`pmo` approves and administers, `engineer` runs triage/analysis, `viewer` is read-only.

Common commands:

```bash
uv run pytest                                   # all tests (no Joern/JVM; fakes/AST)
uv run ruff check . && uv run mypy etki    # lint + type check
uv run python -m eval.runner                    # CI gate: retrieval + decision back-test
uv run python -m eval.runner --dataset my.json  # benchmark YOUR labeled cases (--llm to score a model)
uv run python -m etki.indexing             # rebuild the index (live Joern; AST alternative)
uv run python -m etki.wiki search "SSO"    # decision wiki: search|show|rebuild (see Decision memory)
uv run python -m etki.mcp_server           # MCP server (see the MCP page)
docker compose up -d --build                    # app + Postgres (JVM-free container)
```

## Enabling the LLM (optional)

With no API key the system runs deterministically/heuristically. The easiest way to
enable the LLM seam (semantic fallback matching, pre-analysis prose, the agent) is from
the UI: **Settings → AI Assistant** (pmo-only) — pick *off / Anthropic / OpenAI-compatible*,
paste the key or endpoint, and hit **Test connection**. Values saved there are stored in
`.etki/llm.json` (owner-readable only, git-ignored) and take precedence over env vars;
changes apply on the next request, no restart. For production prefer env/`.env`:

```bash
ETKI_LLM_PROVIDER=anthropic
ETKI_ANTHROPIC_API_KEY=sk-ant-...
```

## Fully air-gapped mode

The data Etki handles — client contracts, code, effort history — is exactly the
kind that can't leave your network. Every layer has a local option, including the LLM
(one OpenAI-compatible adapter covers Ollama, vLLM, LM Studio, llama.cpp server):

```bash
ETKI_LLM_BASE_URL=http://localhost:11434/v1   # Ollama endpoint (enables the local provider)
ETKI_LLM_MODEL=qwen2.5:3b                     # any model your server hosts
```

Local LLM + `ast` code engine + SQLite = **zero external dependencies** (the UI vendors
its own assets — no CDN). With no LLM configured at all, triage is fully deterministic
and reproducible.
