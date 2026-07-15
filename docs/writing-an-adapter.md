# Writing an adapter / plugin

Adapters are Etki's main extension point — and the most wanted contribution.
The core is hexagonal: the decision engine, indexer and API talk only to abstract
**ports** and never mention a vendor. Core code never changes; which adapter is
active is **configuration, never code**. Two ways to ship one:

1. **In-tree adapter** (a PR to this repo): one new file under `etki/adapters/`
   plus one registry branch — the classic path, described below.
2. **Plugin package** (your own repo/distribution): a package depending only on
   **[`etki-api`](https://pypi.org/project/etki-api/)** that declares an
   `etki.adapters` entry point — see
   [Shipping it as a plugin package](#shipping-it-as-a-plugin-package).
   The first-party reference is
   [`packages/etki-plugin-linear`](https://github.com/yasinyaman/etki/tree/master/packages/etki-plugin-linear).

> Looking for what the *existing* adapters pull (endpoints, field mappings, known
> limitations)? See the [Adapter reference](adapters.md).

## The ports

The **external-integration ports** (the first six rows below) live in the frozen
plugin API package [`etki-api`](https://github.com/yasinyaman/etki/tree/master/packages/etki-api)
(`from etki_api import WorkItemProvider, WorkItem, Capabilities`); `etki/core/ports.py`
re-exports them, so in-tree code may import from either — plugins import **only**
`etki_api`. The internal ports (`WikiStore`, `GraphQueryPort`, persistence) stay in
[`etki/core/ports.py`](https://github.com/yasinyaman/etki/blob/master/etki/core/ports.py)
and are not part of the plugin API. All are `typing.Protocol`s — adapters satisfy
them *structurally*, no base class to inherit:

| Port | Abstracts | Methods |
|---|---|---|
| `WorkItemProvider` | the work tracker (Jira, GLPI, ADO…) | `get_work_item(id)`, `find_similar(description, limit=5)`, `capabilities()` |
| `CodeRepositoryProvider` | repo + module graph (Joern, AST…) | `list_modules()`, `get_impacted(module_hint)`, `capabilities()` |
| `DocumentSourceProvider` | the document source (filesystem, Confluence, SharePoint…) | `list_documents()`, `fetch_content(id)`, `capabilities()` |
| `LLMClient` | the LLM serving layer (optional) | `complete_json(system=, user=)` |
| `EmbeddingProvider` | embeddings, OpenAI-compatible (optional) | `embed(texts, kind=)` |
| `RerankProvider` | a TEI-compatible cross-encoder (optional) | `rerank(query, documents)` |
| `WikiStore` | the decision-memory store (default: filesystem markdown) | `write_decision(case)`, `search(project, query)`, `rebuild(project, cases)`, `write_precedent(…)`, `write_disputed(…)` |
| `GraphQueryPort` | retrieval over the knowledge graph | `find_k_nodes(text, k)`, `expand(seeds, hops, budget, query=)`, `nl_query(question)` |

All data crossing a port is **normalized** in vendor-neutral models
(`etki/core/models.py`). The single most important normalization:
**`WorkItem.effort_seconds`** — whatever the tracker calls time spent (Jira
`timespent`, GLPI `actiontime`, GitLab `total_time_spent`, Redmine `spent_hours`,
Azure DevOps `CompletedWork`), the adapter converts it to seconds. That field
powers effort-by-analogy estimation.

## Worked example: a WorkItemProvider

The real reference is [`adapters/jira_work_item.py`](https://github.com/yasinyaman/etki/blob/master/etki/adapters/jira_work_item.py)
(~80 lines). The skeleton every work-item adapter follows:

```python
"""Acme Tracker WorkItemProvider.

Effort in Acme comes from <vendor field>; the core only ever sees the
normalized WorkItem.effort_seconds. Needs a live server → integration is
CI-skipped; pure parsing is unit-tested.
"""
from __future__ import annotations

import httpx

from etki_api import Capabilities, WorkItem


class AcmeWorkItemProvider:
    def __init__(self, base_url: str, api_token: str, timeout: float = 30.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = api_token
        self._timeout = timeout

    def _to_work_item(self, raw: dict) -> WorkItem:
        # ALL vendor quirks die here — nothing vendor-shaped leaves this method.
        return WorkItem(
            id=str(raw["id"]),
            title=raw.get("subject", ""),
            description=raw.get("body", ""),
            status=raw.get("state"),
            effort_seconds=int(raw.get("minutes_spent", 0)) * 60,  # normalize!
        )

    async def get_work_item(self, item_id: str) -> WorkItem:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            r = await client.get(f"{self._base_url}/api/items/{item_id}",
                                 headers={"Authorization": f"Bearer {self._token}"})
            r.raise_for_status()
            return self._to_work_item(r.json())

    async def find_similar(self, description: str, *, limit: int = 5) -> list[WorkItem]:
        ...  # vendor search API → [self._to_work_item(x) for x in hits[:limit]]

    def capabilities(self) -> Capabilities:
        # Declare honestly — the system degrades gracefully from this
        # (no webhooks → polling; no effort tracking → code-metric estimates).
        return Capabilities(supports_effort_tracking=True)
```

### Register it (the only other file you touch)

One branch in the relevant builder in
[`adapters/registry.py`](https://github.com/yasinyaman/etki/blob/master/etki/adapters/registry.py):

```python
if cfg.adapter == "acme":
    return AcmeWorkItemProvider(opt["base_url"], _secret(opt["api_token"]))
```

`_secret()` resolves `env:VARIABLE` references, so tokens never sit in YAML:

```yaml
connectors:
  work_items:
    adapter: acme
    options:
      base_url: https://acme.example.com
      api_token: env:ACME_TOKEN
```

### Test it

Follow [`tests/unit/test_jira.py`](https://github.com/yasinyaman/etki/blob/master/tests/unit/test_jira.py):

1. **Pure parsing, no network** — feed `_to_work_item` a captured payload dict and
   assert the normalization (especially `effort_seconds`).
2. **Capabilities** — assert the declaration matches reality.
3. **Graceful degradation** — anything needing a live server must be CI-skipped,
   and triage must survive your adapter being unreachable: the engine already
   catches `find_similar` errors and falls back to code-metric estimates
   (`TriageEngine._safe_find_similar`); don't wrap your errors in ways that hide them.
4. For engine-level tests, in-memory fakes live in `etki/adapters/fakes/` —
   your adapter is *not* needed to test core logic.

## Shipping it as a plugin package

The same provider class, packaged out-of-tree. Your distribution depends **only on
`etki-api`** (never on `etki`) and declares three things:

**1. A `PluginSpec`** — the runtime contract, a module-level instance:

```python
from pydantic import BaseModel
from etki_api import AdapterFactory, PluginSpec, SecurityCapabilities


class AcmeOptions(BaseModel):
    """Validated BEFORE build(); secrets (env:VAR) arrive already resolved."""
    base_url: str
    api_token: str
    timeout: float = 30.0


def _build(options: BaseModel) -> AcmeWorkItemProvider:
    opts = AcmeOptions.model_validate(options.model_dump())
    return AcmeWorkItemProvider(opts.base_url, opts.api_token, timeout=opts.timeout)


PLUGIN = PluginSpec(
    name="etki-plugin-acme",
    api_compat=">=0.1,<0.2",          # PEP 440 range against etki-api
    capabilities=SecurityCapabilities(  # SECURITY declaration (KVKK inventory),
        network=True,                   # separate from the functional Capabilities
        filesystem="none",
        endpoints=["acme.example.com"],
    ),
    adapters=(AdapterFactory(port="work_items", name="acme",
                             options_model=AcmeOptions, build=_build),),
)
```

**2. An entry point** in your `pyproject.toml` — this is how Etki discovers you:

```toml
[project.entry-points."etki.adapters"]
acme = "etki_plugin_acme:PLUGIN"
```

**3. An `etki-plugin.toml` manifest** at the repo/wheel root — the *static twin*
of the spec, readable **without executing your code** (the install confirmation
prompt and the marketplace index read it; `etki plugin verify` cross-checks it
against the spec and fails on drift):

```toml
[plugin]
name = "etki-plugin-acme"
type = "adapter"
api_compat = ">=0.1,<0.2"

[plugin.capabilities]
network = true
filesystem = "none"
endpoints = ["acme.example.com"]

[[plugin.adapters]]
port = "work_items"
name = "acme"
options_model = "etki_plugin_acme:AcmeOptions"
```

Once installed next to Etki, `adapter: acme` in `connectors.yaml` resolves to your
plugin — no registry branch needed. (Runtime discovery lands in plugin Faz 2;
until then the spec + manifest are validated by the package's own tests.)

### etki-api versioning policy

- `etki-api` follows **semver**: major = breaking, minor = new optional
  method/field, patch = fixes. Every change is recorded in
  [`packages/etki-api/CHANGELOG.md`](https://github.com/yasinyaman/etki/blob/master/packages/etki-api/CHANGELOG.md).
- While `0.x`, breaking changes are allowed but announced — pin
  `etki-api>=0.1,<0.2` and set the same range as your `api_compat`; the loader
  refuses (loudly, never silently) plugins whose range doesn't cover the
  installed version.
- The public surface is exactly `etki_api.__all__` — enforced by
  `tests/unit/test_api_surface.py`. If you need a symbol that isn't exported,
  open an issue; don't reach into `etki.*`.

## Rules that keep the architecture honest

- **No vendor names in core.** If `engine/`, `indexing/` or `api/` needs to know
  it's talking to Acme, the design is wrong — push it into the adapter.
- **Normalize inside the adapter.** Units, field names, pagination, auth: none of
  it leaks past the port.
- **Declare capabilities truthfully.** `supports_effort_tracking=False` with a
  fallback beats fabricated efforts (single-point estimates are forbidden anyway).
- **Fail soft.** An unreachable backend must degrade the answer, not kill triage.
- **Secrets via `env:` references** — never plain text in config.

## Checklist for the PR

- [ ] One file under `etki/adapters/`, one branch in `registry.py`, zero core changes
- [ ] `effort_seconds` (or the port's equivalent) normalized and unit-tested from a captured payload
- [ ] Live-server tests CI-skipped; parsing tested without network
- [ ] `uv run ruff check . && uv run mypy etki && uv run pytest` green
- [ ] `uv run python -m eval.runner` still green (adapters shouldn't move it — if it moves, something leaked)
- [ ] A config example in your adapter's module docstring or the PR description

Vendor candidates we'd love: **Azure DevOps, GitLab, Linear, Redmine, Confluence,
SharePoint.** Open an issue first so we can agree on scope — see
[CONTRIBUTING.md](https://github.com/yasinyaman/etki/blob/master/CONTRIBUTING.md).
