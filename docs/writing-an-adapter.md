# Writing an adapter

Adapters are Etki's main extension point — and the most wanted contribution.
The core is hexagonal: the decision engine, indexer and API talk only to abstract
**ports** and never mention a vendor. Adding Jira, Confluence, SharePoint or your
in-house tracker means writing **one new file** plus **one registry branch**. Core
code never changes; which adapter is active is **configuration, never code**.

> Looking for what the *existing* adapters pull (endpoints, field mappings, known
> limitations)? See the [Adapter reference](adapters.md).

## The ports

Defined in [`etki/core/ports.py`](https://github.com/yasinyaman/etki/blob/master/etki/core/ports.py) as
`typing.Protocol`s — adapters satisfy them *structurally*, no base class to inherit:

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

from etki.core.models import WorkItem
from etki.core.ports import Capabilities


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
