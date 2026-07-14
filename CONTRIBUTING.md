# Contributing to Etki

Thanks for your interest! Etki is an alpha-stage project and contributions of
all kinds are welcome: bug reports, docs, translations, new adapters, and core fixes.

## Development setup

Requirements: Python 3.12+ and [uv](https://docs.astral.sh/uv/). No JVM, no Postgres
and no LLM key are needed for development — tests use fakes, the AST code engine and
SQLite.

```bash
git clone https://github.com/yasinyaman/etki.git
cd etki
uv sync --dev                                   # venv + dependencies (editable install)
uv run pytest                                   # all tests
uv run ruff check . && uv run mypy etki    # lint + type check
uv run python -m eval.runner                    # the CI quality gate (see below)
uv run uvicorn etki.api.app:app --reload   # dev server → http://localhost:8000
```

A quick way to see the product: `docker compose -f docker-compose.demo.yml up --build`
(login `demo`/`demo`).

## What a PR needs to pass

CI runs exactly these four steps on every push/PR:

1. `uv run ruff check .`
2. `uv run mypy etki`
3. `uv run pytest --cov=etki --cov-fail-under=70`
4. `uv run python -m eval.runner` — the **eval gate**: retrieval F1, a
   decision-agreement back-test, and a frozen 66-case golden set. A change that
   lowers these metrics is not "done", even if all unit tests pass.

**Golden-set freeze rule:** never change `eval/datasets/frozen/golden_crs.json` in
the same PR that changes engine/matching/synonym logic. Grow the golden set in its
own PR, with labels justified against the sample contracts — the gate must not be
gamed by editing the answer key.

## Writing an adapter (the most wanted contribution)

**Full step-by-step guide with a worked example: [docs/writing-an-adapter.md](docs/writing-an-adapter.md).** The short version:

The core is hexagonal and vendor-agnostic: it only talks to three ports defined in
`etki/core/ports.py` (`WorkItemProvider`, `CodeRepositoryProvider`,
`DocumentSourceProvider`) plus the optional `LLMClient`. Adding a vendor never
touches core code:

1. Create `etki/adapters/<vendor>.py` implementing one port. Ports are
   `typing.Protocol`s — no inheritance needed; match the method signatures.
   Normalize vendor quirks *inside* the adapter (e.g. map whatever the tracker
   calls time-spent to `WorkItem.effort_seconds`).
2. Register it: add one branch to the relevant `build_*` function in
   `etki/adapters/registry.py`. Which adapter is active is **configuration,
   never code** (`config/connectors.example.yaml`).
3. Test it against the fake/reference implementations in
   `etki/adapters/fakes/` — see `tests/unit/test_jira.py` or
   `tests/integration/test_composite.py` for the pattern. Adapters that need a live
   server must degrade gracefully and skip in CI.

Good vendor candidates: Azure DevOps, GitLab, Linear, Redmine, Confluence,
SharePoint. Open an issue with the `adapter` template first so we can agree on scope.

## Other conventions

- **Two cadences:** heavy work belongs in indexing (offline); triage must stay a
  fast index lookup. Don't add per-request I/O to the engine.
- **Estimates are ranges** — never introduce a single-point estimate anywhere.
- **EXCLUDED scope is first-class** — never collapse `ScopeItem.polarity` into a
  boolean.
- **UI strings** go through the i18n catalog (`etki/i18n/catalog.py`,
  keys with tr/en/de). Adding a language = adding a column to the catalog — a great
  first contribution.
- The codebase carries Turkish domain terminology (the product domain is Turkish
  PMO/contract work), but **code comments, docstrings and LLM prompts are English**
  (full pass 2026-07-12). Runtime Turkish stays Turkish by design: i18n catalog
  values, log/exception messages, eval console output, fixture corpora and the
  stopword/keyword tables are product data, not commentary. New public-facing docs
  should be English.

## Releases (maintainers)

Bump `version` in `pyproject.toml`, add a CHANGELOG section, then tag: `git tag
v<version> && git push --tags`. The release workflow re-runs all checks, publishes
the Docker image to GHCR and the package to PyPI, and creates the GitHub Release
from the CHANGELOG section.

## Questions

Use GitHub Discussions for questions and design conversations, issues for bugs and
concrete proposals. Security reports: see [SECURITY.md](SECURITY.md).
