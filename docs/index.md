# Etki

**The only open-source tool that answers *"is this in scope?"* with contract evidence,
code impact and historical effort.**

![Etki demo](demo.gif)

!!! warning "Alpha"
    APIs, schema and screens may change. Intended for pilot/evaluation, not production.

For every incoming client request, Etki answers one question:
**is this in-scope, out-of-scope, or a Change Request; what is the effort; which code
and which contract clause does it touch?** It fuses three sources no other tool combines:

1. **Contract scope** — clauses extracted into structured scope items, *including the
   explicitly excluded ones*.
2. **Code knowledge graph** — modules, dependencies, complexity, churn — for impact
   analysis and effort.
3. **Historical effort** — real time logged on similar past requests, used by analogy.

Every decision carries an **auditable evidence chain** that can be reconstructed for a
contractual dispute. **Copilot, not autopilot:** the system recommends, the PMO decides.

## Where to go

- **[Getting started](getting-started.md)** — the 5-minute no-API-key demo, quick start,
  fully air-gapped mode.
- **[Concepts](concepts.md)** — the load-bearing design decisions: evidence chain,
  two-evidence rule, first-class EXCLUDED scope, effort ranges.
- **[Decision memory](memory.md)** — the git-versionable decision wiki (a pure DB
  projection), precedents from PMO overrides, disputed clauses, and graph retrieval.
- **[MCP](MCP.md)** — ask Claude *"is this in scope?"* and get the real Etki answer.
- **[Writing an adapter](writing-an-adapter.md)** — connect your tracker, repo host or
  document source without touching core code.
- **[Operations](RUNBOOK.md)** — deployment, backup, index refresh.

Source, issues and discussions: [github.com/yasinyaman/etki](https://github.com/yasinyaman/etki) · License: Apache-2.0
