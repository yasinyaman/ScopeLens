# Compliance & traceability

*(English sibling of [`KVKK.md`](KVKK.md), which covers the Turkish KVKK/GDPR
perspective. This note describes what Etki stores, how decisions stay
reconstructable, and where the human is in the loop — the properties frameworks like
the EU AI Act ask of decision-support systems.)*

## What the system is, in regulatory terms

Etki is a **decision-support** system: it produces *recommendations* about
contract scope (in scope / out of scope / change request), and a human (the PMO)
makes every decision of record. It is not an automated decision system — the
"copilot, not autopilot" rule is enforced by the workflow, not just stated: nothing
becomes binding without an explicit approve/reject/convert action by a user with the
`pmo` role, and the system's recommendation and the human's action are recorded
separately.

## Data inventory

| Data | Where | Notes |
|---|---|---|
| Contract/spec text and extracted scope clauses | project index (`.etki/index-*.json`) + uploaded files under the project workspace | stays on the deployment host |
| Code metadata (module names, size/complexity/churn metrics) | project index | no source code is stored in the index beyond identifiers and metrics |
| Historical work items (titles, descriptions, logged effort) | pulled from the configured tracker (file/Jira/GLPI/GitLab) at index/triage time | normalized; tracker credentials come from environment references (`env:VAR`), never from config files |
| Case files (request text, decisions, evidence chains, pre-analyses, chat turns) | the application database (SQLite or Postgres) | the audit record — see below |
| Users | `users` table: username, pbkdf2 password hash, role; per-user project grants in `user_projects` | no plaintext credentials; managed from the UI (Settings → Users, pmo-only) |
| Decision wiki (markdown projection of case files: request texts, reasoning, precedents, disputed clauses) | `.etki/wiki-{project}/` (`ETKI_WIKI_DIR`; empty = off) | pure DB projection — regenerable, never authoritative; same residency/access rules as the DB; erasure = delete the case in the DB, then `python -m etki.wiki rebuild` |
| LLM provider settings | `.etki/llm.json` when configured from the UI (owner-readable only, git-ignored); env vars otherwise | API keys are never echoed back to the browser |
| Process log (Ask-screen questions → strategy → matched nodes → assistant answers; indexing runs) | `.etki/process-log.jsonl` (git-ignored, append-only) | questions are free text and **may contain personal data** — same residency/access rules as the database; erasure requests require pruning the matching lines |

**Deployment model:** self-hosted; a fully air-gapped configuration is supported
(local LLM/embeddings via Ollama or vLLM, `ast` code engine, SQLite, no CDN assets).
With no LLM configured, no text ever leaves the host and the decision path is fully
deterministic.

## Reconstructability (the audit story)

Every triage decision is stored with a **frozen evidence chain**:

- the clauses checked and the best match with its similarity score;
- the **full text of cited clauses at decision time** — a later contract amendment or
  re-index cannot silently rewrite the basis of an old decision;
- impacted code modules with the metrics that fed the effort range;
- source coverage (which of spec/code/history were available) and explicit
  assumptions for whatever was missing;
- reasoning, confidence, a **model/prompt version stamp** and an **index-freshness
  stamp**;
- when the optional LLM or embedding assist contributed, that contribution is
  recorded as a labeled assumption (e.g. "LLM-assisted matching", "semantic match —
  cosine 0.63, deterministic") in the evidence chain.

On top of the decision record, an append-only **audit trail** captures every action
(TRIAGED, approvals, rejections, CR conversions, baseline bumps, pre-analysis edits)
with actor and timestamp. Approving a CR creates a **new baseline version** rather
than mutating scope in place, so "what did the contract scope look like when this
decision was made?" always has an answer.

## Human oversight & over-reliance monitoring

- Approval requires the `pmo` role; `engineer` runs triage/analysis; **`viewer` is
  read-only** (every mutating endpoint rejects it). Per-user **project access grants**
  isolate who can see and act on which project; an inaccessible project returns 404,
  and the portfolio count is shown to `pmo` only.
- Account security: login is rate-limited (5 failures per IP+username / 15 min →
  15 min lock), the post-login redirect only accepts site-relative paths, sessions
  are token-bound to the password hash (a reset or deletion drops live sessions,
  role changes apply immediately), and "remember me" lifetimes are enforced
  server-side (30 days checked / 8 hours unchecked).
- When the PMO decides against the system's recommendation, the **override** is
  recorded and surfaced as an over-reliance metric on the KPI dashboard — drift
  toward rubber-stamping is visible, not hidden.
- Calibration is a *suggestion loop*: pilot mismatches produce threshold-change
  proposals that a human applies in configuration; the system never retunes itself.

## LLM and embedding usage

- **Off by default.** The CI quality gates run fully deterministically.
- When enabled, the LLM is consulted only on weak deterministic matches; its output
  is **whitelist-validated** against real clause ids, strength-gated, and wrapped in
  **prompt-injection guards** (untrusted-content delimiters on contract/request text,
  output sanitation). A poisoned document cannot instruct the matcher.
- Embeddings are deterministic per model; their only decision-changing power is
  routing *clear* exclusion matches — measured limits and the rationale are published
  in the [EtkiBench documentation](https://github.com/yasinyaman/etki/blob/master/eval/datasets/etkibench/README.md).
- Every decision carries the model/prompt version that produced it.

## Evaluation integrity

Quality claims are backed by public, versioned datasets with two protections:
a CI **freeze guard** (engine changes and answer-key edits cannot land in the same
change set) and **pre-registered, one-shot held-out sets** for generalization claims
(the set is committed before any run — verifiable in git history — scored once, and
then never used for tuning).

## Known limitations (honest section)

- Alpha software; no real-customer pilot has run yet.
- Estimation constants are config-driven but not yet calibrated against real closed
  work items.
- Old case files keep evidence text in the language it was frozen in (by design —
  audit records are not retroactively translated).
