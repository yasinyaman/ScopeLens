# Decision memory (wiki & graph query)

Etki keeps a long-form, file-based **decision memory** next to the database:
every triage decision becomes a readable markdown page, PMO corrections become
precedents, and a retrieval port serves that knowledge back to tools and future
phases. The design goal is *"decision memory as code"* — the memory is plain
markdown you can grep, diff and version.

## The one rule that everything hangs on

> **The wiki is ALWAYS a projection of the database.**

The DB (`CaseFileRepository`) is the single source of truth. The wiki is written
from one place only (`ApprovalService.sync_wiki` + the HITL ingest hook), can be
deleted and regenerated **bit-identically** at any time, and is never hand-edited
(a rebuild overwrites manual changes). A wiki failure never breaks triage or
approval — every write is best-effort. This is what keeps the memory from ever
becoming a second, conflicting truth.

```bash
python -m etki.wiki rebuild            # regenerate every project's wiki from the DB
python -m etki.wiki search "SSO"       # token-AND search (rg if installed, else Python)
python -m etki.wiki show DEC-20260709-req-demo-1a2b3c4d --project demo
```

## Layout

```
.etki/wiki-{project_id}/
├── index.md                    # generated: counts, verdict distribution, last 10
├── disputed.md                 # generated: clauses with CONFLICTING resolved rulings
├── decisions/
│   └── DEC-{yyyymmdd}-{slug}.md   # one case = one file (frontmatter + evidence)
├── precedents/
│   └── PRE-{slug}.md              # cases where the PMO overrode the system
└── entities/
    ├── contracts/{id}.md          # backlinks: which decisions cited this contract
    └── modules/{id}.md            # backlinks: which decisions touched this module
```

Decision files carry YAML frontmatter (case id, verdicts, confidence, cited
clause refs, impacted modules, model version, index freshness) and a body
projected from the **frozen evidence chain** — reasoning, cited clauses in full,
effort *range*, risk, assumptions, the PMO's decision and the saved
pre-analysis. Enable/disable and relocate via `ETKI_WIKI_DIR`
(default `.etki/wiki-{id}`; empty string turns the wiki off).

## The feedback loop (HITL ingest)

Human decisions flow back into the memory automatically, on every approval
action:

- **Override → precedent.** When the PMO's ruling differs from the system's
  recommendation, the case is promoted to `precedents/PRE-*.md`: what the
  system said, what the human decided, who and when — the boundary-case file
  future triage should consult.
- **Conflict → disputed.** When *resolved* decisions on the same cited clause
  disagree (one approved as in-scope, another converted to CR…), the clause is
  listed in `disputed.md` with its full ruling history. Read it before ruling
  on that clause again.
- **Counters.** The project's Raporlar screen shows precedent and
  disputed-clause counts (computed from the DB, not read back from files).

And the memory is READ back at decision time — closing the loop end to end:

- **Review panel.** The approval screen shows a per-decision "clause memory"
  strip (precedent count, last human correction, a red disputed warning) right
  where the PMO clicks Approve/CR/Reject.
- **Engine note (non-signal).** When the cited clause has memory, the triage
  decision carries an informational note in its evidence chain ("clause memory:
  N past PMO corrections — informational, no decision effect"). Structurally it
  cannot change the decision or confidence: it is added after classification,
  and a byte-identical-decision test plus the frozen golden set pin that down.
- **Dispute → risk escalation.** A request citing a clause with *conflicting*
  final rulings additionally escalates the RISK layer (24h PMO look + a risk
  signal), the same pattern as the security-wording rule — decision, confidence
  and effort stay byte-identical (pinned by test). Kill switch:
  `ETKI_DISPUTED_ESCALATION=false` reverts to note-only.
- **Memory screen.** Each project has a **Hafıza** page: wiki search,
  disputed-clause and precedent cards (DB-backed — they work even with the wiki
  off), and the decision-file list.
- **Pre-analysis context.** The developer pre-analysis (LLM path) receives a
  related-context block packed by `expand(query=…)` — with a reranker
  configured, relevance-ordered.
- **MCP.** `graph_query(question)` (strategy-routed retrieval) and
  `wiki_search(query)` expose the memory to Claude/MCP clients.

There is no queue and no Celery: writes are file-fast and **idempotency comes
from projection** — re-processing the same feedback event regenerates the same
bytes. `python -m etki.wiki rebuild` re-derives precedents and disputed pages
too, so the derived memory is covered by the same projection guarantee.

## Graph retrieval (`GraphQueryPort`)

One port, three strategies, over the same knowledge the engine runs on (scope
clauses + code modules + historical work items — the normalized JSON index; no
graph database, no Cypher):

| Strategy | What it does | When it's picked (rule-based v1) |
|---|---|---|
| `find_k_nodes` | top-k nodes by text relevance | default |
| `expand` | token-budgeted BFS over the index's real edges (scope↔module mapping, `depends_on`/`depended_by`, work-item↔module) | dependency/impact wording |
| `nl_query` | an LLM picks **one** whitelisted read-only `IndexTools` call (injection-guarded, 3 attempts, falls back to `find_k`) | interrogatives |

The chosen path is recorded in `QueryResult.strategy` — auditable like every
other decision artifact. Scoring is the engine's deterministic lexical score by
default; configure `ETKI_EMBED_*` for embedding cosine (deterministic per
model, with lexical fallback on endpoint errors). **Retrieval is never a
decision signal**: it returns candidates for context and precedent lookup; the
measured bi-encoder limitation (paraphrase vs new capability) is documented in
[Concepts](concepts.md).

### Rerank-packed expansion

With a configured reranker (`ETKI_RERANK_BASE_URL`, TEI-compatible,
bge-reranker-v2-m3), `expand(…, query=…)` packs non-seed neighbours into the
token budget by **cross-encoder relevance** instead of BFS order — under a tight
budget the relevant neighbours survive, not the accidentally-nearest ones.
`Subgraph.packing` records which packing ran. Without a reranker (or on any
endpoint error) the behavior is byte-identical plain BFS.

**Measured honestly:** the retrieval eval (24 pre-committed queries) scores TR
recall 0.82 (find_k) → 1.00 (find_k+expand) at precision 0.36 — expansion earns
its recall by over-fetching, which is exactly what reranked packing is meant to
fix. A plumbing smoke with a trivial keyword reranker *hurt* recall
(0.99→0.97): a weak reranker is worse than BFS. The live A/B ran 2026-07-12
with a real bge-reranker-v2-m3 (GPU, raw logits, p50 88 ms) and **confirmed the
smoke**: recall BFS 0.99 → rerank 0.97, precision 0.38 → 0.37. Packing therefore
stays BFS by default — on these corpora the graph structure already orders
neighbours well; the reranker's measured value is on the *scope-matching* lane
(see Concepts), not here. An honest negative, published as-is.

## Compliance note

Wiki files contain request texts and reasoning. If those carry personal data,
the wiki directory falls under the same residency/access rules as the database
— see [Compliance](compliance.md) and `KVKK.md`. Deleting a project keeps its
wiki (it is the readable projection of the preserved audit history); a KVKK
erasure request is honored by deleting the case from the DB and running
`rebuild`.
