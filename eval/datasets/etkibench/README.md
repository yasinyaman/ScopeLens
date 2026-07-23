# EtkiBench v0

A public, reproducible benchmark for **contract-scope triage**: given a client request,
a contract, a codebase and past work items, decide *in scope / out of scope / change
request / gray area / maintenance*.

Nothing else measures this. Delivery-metrics platforms score throughput; estimation
tools score points. EtkiBench scores the **scope decision itself** — the thing that
actually gets disputed with a client.

## Anchor corpus (fully bundled, nothing to download)

Every case is labeled against the repository's English demo corpus, **Meridian CRM**:

- contract: [`samples/demo_project_en/contract.md`](../../../samples/demo_project_en/contract.md)
  (8 clauses incl. explicit exclusions, per-month limits and effort pools)
- codebase: `samples/demo_project_en/src` (5 modules, indexed with the AST engine)
- history: `samples/demo_project_en/work_items.json` (9 closed items with real efforts)

## Run it

```bash
# Deterministic baseline (no LLM, fully reproducible):
uv run python -m eval.runner \
    --dataset eval/datasets/etkibench/etkibench_v0.json \
    --connectors config/connectors.etkibench.yaml

# Score a model (any OpenAI-compatible endpoint — Ollama, vLLM, LM Studio):
ETKI_LLM_BASE_URL=http://localhost:11434/v1 ETKI_LLM_MODEL=qwen2.5:3b \
uv run python -m eval.runner --llm \
    --dataset eval/datasets/etkibench/etkibench_v0.json \
    --connectors config/connectors.etkibench.yaml

# Or Anthropic:
ETKI_LLM_PROVIDER=anthropic ANTHROPIC_API_KEY=sk-ant-... \
uv run python -m eval.runner --llm --dataset ... --connectors ...
```

The LLM runs as Etki uses it in production: **assist-on-weak-match only** — the
deterministic decision tree stays in charge, the model is consulted when lexical
matching is inconclusive, and its output is whitelist-validated. Scope extraction is
heuristic in both modes, so every run judges the *same* baseline.

## The suite (150 open cases + 24 sealed)

The headline scoreboard below is anchored to the original 66-case file so every
historical number stays comparable. The full suite has grown around it:

| File | n | Corpus | Status |
|---|---|---|---|
| `etkibench_v0.json` | 66 | Meridian CRM | open — headline scoreboard |
| `heldout_v0.json` | 36 | Northwind Shop | open (burned held-out, now dev) |
| `heldout_v1_meridian/northwind.json` | 24 | both | open (burned held-out, now dev) |
| `etkibench_v1_meridian.json` | 12 | Meridian CRM | open — fresh 2026-07 batch |
| `etkibench_v1_northwind.json` | 12 | Northwind Shop | open — fresh 2026-07 batch |
| `heldout_v2_*.json` | 24 | both | **SEALED** — one-shot, do not run |
| `heldout_v3_*.json` | 24 | both | open (burned held-out, now dev) — pre-registered 2026-07-21 for the matching/estimator round, scored once at its end |

Northwind files run with `--connectors config/connectors.heldout.yaml`;
Meridian files with `config/connectors.etkibench.yaml`. Deterministic
baselines on the fresh 2026-07 batch (engine with lexicon, no reranker):
**Meridian 5/12, Northwind 2/12** — deliberately harder paraphrases; two new
honest findings came straight from the misses: **word-numbers escape the
limit extractor** ("six reports", "a fourth provider" → the quantity check
never fires), and the v4c vendor lexicon has a measurable false-positive cost
(KM-08 keeps a contact's *mobile number* — the word alone flips it toward the
mobile-app exclusion; the case is designed to keep that trade-off measured).

**rerank_strong recalibration sweep (2026-07-22, closing the 2026-07-12
follow-up; live bge-reranker-v2-m3 on gx10, current engine, `--llm` off):**
7 thresholds × 8 open dev files (174 cases; the SEALED heldout_v2 was not
touched). Dev totals: -2 → 119, -3/-4 → 118, -5 → 121, -6 → 122, **-6.8 →
126**, -8 → 127; pooled out-of-scope P/R was 0.868/0.733 at EVERY threshold
(the include-side floor never touches exclusion evidence — by design). The
pre-committed rule picked θ*=-8 on dev, but the golden regression gate
rejected it: fresh golden with reranker is 57/66 at -6.8 vs **56/66 at -8**
(one more adversarial promotion, GS-49). **Conclusion: -6.8 stays the
default; the assist lane lifts the deterministic dev floor 103 → 126/174 yet
remains opt-in** (the golden trade-off is unchanged; a default-on decision
would need a fresh pre-registered held-out one-shot, which this sweep is
not). No generalization claim — the selection ran on open dev sets only.

**Gate honesty notes (2026-07-23, from the critical study):**

- **The golden warn band's real floor is ~71%, not 80%.** The gate uses a
  Wilson interval: a point estimate below 80% whose interval still covers the
  threshold prints a WARNING but passes — that tolerates down to 47/66 (71%);
  a clear fail starts at 46/66. This is statistically deliberate (single-case
  flips should not break CI) and now surfaced as a first-class `::warning::`
  annotation instead of a silent pass.
- **The effort-in-range gate is weak evidence for now:** 6 of the 12 backtest
  requests are close restatements of the very work items the analogy draws
  from, and the effort labels come from those analogs — the gate mostly
  verifies the plumbing, not calibration. Real pilot data replaces it.
- **Sealed sets are now enforced, not just convention:** the freeze guard
  fails any change set touching `heldout_v2_*.json`, and `eval.runner` refuses
  to run them without `ETKI_UNSEAL=1`.
- Deterministic baseline moved 45 → **46/66** in the 2026-07-23 W4 lexicon
  round (TR quota family; quantity_crs 11/12, period_quota 11/11, backtest
  12/12 — all without touching any answer key).

**Pilot-set refresh one-shot (2026-07-23):** the old `pilot_crs.json` was
10/12 a verbatim copy of the backtest answer key — its 75-83% "pilot agreement"
double-counted the same cases. The refreshed set (12 fresh TR phrasings, zero
copies, full strata mix) scores **7/12 (58%) — below the 0.75 gate — and
effort-in-range 6/12**, matching the open dev-set reality (50-68%) instead of
the circular number. Per the pre-committed rule the pilot gate therefore does
NOT enter CI; `python -m etki.pilot` now reports the honest number (RET) and
its calibration suggestions run on genuinely fresh data. The answer key stays
as labeled — the gap is the engine's (and the effort labels are judgment
calls, stated as such).

**heldout_v3 one-shot (2026-07-21, after the matching/estimator round —
azure-lexicon fix, TR boilerplate-verb stopwords, diacritic-folded stop lookup,
surface-count short-query cap, zero-spread analogy widening): Meridian 7/12,
Northwind 7/12.** No generalization improvement is claimed at n=24 (CIs overlap
v1's 12/24 heavily). What the round *did* demonstrably fix, case by case: both
multi-brand exclusions (M3-06 Okta/Auth0, N3-05 Bitcoin/Ethereum) now register
as OUT; ASCII-typed Turkish (M3-11) and "sağlanacaktır" boilerplate (N3-11,
M3-12) no longer distort routing; the single-analog effort case (M3-02, 4h)
lands inside the widened range where the old point estimate [3,3] would miss.
Honest remaining misses: paraphrase-weak matches still cap at GRAY (M3-02/03,
N3-03/08/10), "from 3 to 10" word-pair quantities escape the limit extractor
(M3-09, the known gap), and M3-04 (Azure DevOps) improved from a false
exclusion to CR_CANDIDATE but not to IN_SCOPE — the lexical bridge to the
integration clause stays weak.

## The 66 cases

| Stratum | n | What it tests |
|---|---|---|
| `in_scope_direct` | 10 | requests sharing vocabulary with an included clause |
| `in_scope_paraphrase` | 8 | same deliverables, **no keyword overlap** |
| `out_of_scope_direct` | 7 | explicitly excluded deliverables, named directly |
| `out_of_scope_paraphrase` | 3 | exclusions phrased without the excluded term |
| `out_of_scope_adversarial` | 4 | excluded deliverables wearing included-clause vocabulary |
| `cr_new_capability` | 10 | deliverables no clause covers |
| `cr_limit_quota` | 4 | included deliverables **beyond a contractual limit** |
| `cr_effort_pool` | 2 | included deliverables the remaining effort pool can't absorb |
| `gray_vague` | 6 | one-word / no-deliverable requests a PMO must clarify |
| `maintenance` | 6 | defects in delivered functionality |
| `cross_lingual_tr` | 6 | Turkish requests against the English contract |

Each case carries a `rationale` citing the contract clause that justifies its label.
Labels describe **what a competent PMO should decide from the contract and history** —
they are deliberately independent of what the current engine happens to answer.

## Scoreboard

All LLM rows run the production configuration: **assist-on-weak-match with whitelist
validation** — the LLM cannot freely overwrite the decision tree.

**v1 snapshot** (the engine as first benchmarked — kept for the before/after story;
current numbers are in the next section):

| Mode | Agreement | 95% CI |
|---|---|---|
| Deterministic (no LLM) | **33/66 (50%)** | 38%–62% |
| gpt-oss:20b (Ollama, DGX GB10) | **34/66 (52%)** | 40%–63% |
| qwen2.5:14b (Ollama, DGX GB10) | **34/66 (52%)** | 40%–63% |
| qwen2.5:32b (Ollama, DGX GB10) | 33/66 (50%) | 38%–62% |
| qwen2.5-coder:7b (Ollama, DGX GB10) | 33/66 (50%) | 38%–62% |
| qwen2.5:3b (Ollama, local) | 33/66 (50%) | 38%–62% |
| gemma3:27b (Ollama, DGX GB10) | 31/66 (47%) | 35%–59% |
| llama3.3:70b (Ollama, DGX GB10) | 31/66 (47%) | 35%–59% |
| gpt-oss:120b (Ollama, DGX GB10) | 30/66 (45%) | 34%–57% |
| llama3.2:3b (Ollama, local) | 29/66 (44%) | 33%–56% |
| qwen3:4b (Ollama, local) | *did not complete — reasoning latency (2 × 10 min attempts)* | |
| *your model here — PRs welcome* | | |

All DGX runs completed with `assist_failures=0` (no timeout contamination;
`ETKI_LLM_TIMEOUT=300`).

**What the first runs show (honest notes):**

- The assist is **conservative by design**. With qwen2.5-coder:7b it fired on 20/66
  cases (recorded as an "LLM destekli eşleştirme" assumption in the evidence chain)
  but changed only 2 final decisions — both CR→GRAY on paraphrase cases, i.e. moved
  *toward* the right answer without reaching it (0 fixed, 0 broken, net 0). Whitelist
  validation rejects most suggestions that would flip a decision.
- **A weak model can make things worse:** llama3.2:3b's whitelist-passing but wrong
  matches cost 4 cases net. Guardrails reduce, not eliminate, downside.
- **qwen2.5:14b and gpt-oss:20b are the only net positives** (+1 each).
- **Scale not only fails to help — past ~27B it hurts.** The full 3B→120B ladder is
  non-monotonic with a peak in the middle: 14b/20b +1, 32b/7b/3b net 0, then
  gemma3:27b −2, llama3.3:70b −2 and gpt-oss:120b −3. Larger models produce more
  assertive clause mappings; the ones that survive whitelist validation flip more
  decisions, and on this stratified set those flips are net wrong. The paraphrase
  strata (1/8 and 0/3 deterministic) remain essentially unclaimed at every size.
  Conclusion: the assist's ceiling is set by its **prompt + validation design**,
  not by model capability — that, or embeddings, is where the headroom lives.

Per-stratum, deterministic:

| Stratum | Score | Reading |
|---|---|---|
| cr_limit_quota | 4/4 | quantity extraction + limit check work |
| cross_lingual_tr | 5/6 | the TR↔EN term bridge mostly holds |
| in_scope_direct | 6/10 | borderline scores on short direct asks |
| cr_new_capability | 6/10 | |
| out_of_scope_direct | 4/7 | |
| out_of_scope_adversarial | 3/4 | the exclusion-margin guard earns its keep |
| gray_vague | 3/6 | unmatched vague asks fall through to CR |
| **in_scope_paraphrase** | **1/8** | lexical matching can't do semantics — this is the LLM's headroom |
| **out_of_scope_paraphrase** | **0/3** | same |
| **maintenance** | **1/6** | see finding #1 below |
| cr_effort_pool | 0/2 | paraphrased integrations stall before the pool check |

### After the engine improvements the v1 runs motivated (rounds 1–2)

Transparency note: the v1 results above exposed real engine defects, which were then
fixed — **the dataset was not touched**; labels predate the fixes, per the freeze rule.
Round 1 (assist v2): the LLM could previously only match INCLUDED clauses and an
accepted match was capped at the gray floor — the assist could break correct CRs but
never produce IN_SCOPE or OUT_OF_SCOPE; fixed with strength-gated matching + exclusion
routing + anti-hallucination rules (whitelist intact). Round 2: English maintenance
routing (defect vocabulary + a maintenance citation independent of text overlap with
the maintenance clause). A third experiment (unmatched short query → GRAY) was tried
and **reverted** after it broke two frozen golden-set cases — the answer key wins.
The frozen CI golden set improved 60 → 61/66 along the way.

| Mode | Agreement | 95% CI | v1 → now |
|---|---|---|---|
| gpt-oss:120b (Ollama, DGX GB10) | **55/66 (83%)** | 73%–90% | 30 → 55 (+25) |
| gpt-oss:20b (Ollama, DGX GB10) | **55/66 (83%)** | 73%–90% | 34 → 55 (+21) |
| claude-opus-4-8 (Anthropic API) | **52/66 (79%)** | 67%–87% | — |
| qwen2.5:14b (Ollama, DGX GB10) | **48/66 (73%)** | 61%–82% | 34 → 48 (+14) |
| Deterministic (no LLM) | **41/66 (62%)** | 50%–73% | 33 → 41 (+8) |

Honest note on the Claude row: opus is *more conservative* here — perfect
`in_scope_direct` 10/10, cross-lingual 6/6 and effort-pool 2/2, but it escalates more
paraphrases and new-capability asks to GRAY, landing below the local gpt-oss models on
this stratification. Local models beating a frontier API model on a guarded, structured
task is a result we're happy to publish as-is.

All rows on the round-3 engine; maintenance is 5/6 on every model row and every run
reported `assist_failures=0`.

**Round 3 (deterministic):** diagnosis showed the symmetric score was systematically
diluted for English — `_STOP` had Turkish function words and Turkish contract
boilerplate by design, but no English mirror (one in-scope case missed the threshold
by 0.002 on the mass of "their/able/should"; every exclusion clause leaked
"out"/"scope" tokens as false exclusion evidence). Completing the English stopword
list took the deterministic row 35 → 41/66 with the frozen golden set unchanged.
Also tried and **reverted**: a coverage floor for single-hit exclusions (killed
golden's legitimate single-head-term exclusions — answer key wins). Held-out check
(fresh pre-registered v1, 24 cases, two corpora): pre-round-3 engine 8/24, round-3
engine 10/24 — the +9pp dev gain shows up as +8pp on unseen data. v1's one-shot also
caught a real extraction defect (a "…is supported" payment clause categorized as
*maintenance*, silently disabling the effort-pool check) — fixed and gate-validated;
v1 is now burned per protocol.

The inverted scale curve is fixed: model capability now converts to accuracy (120b went
from worst to best). `out_of_scope_paraphrase` 0/3 → 3/3, `in_scope_paraphrase`
1/8 → 6/8 (120b), `maintenance` 1/6 → 4/6 on every model row (3/6 deterministic),
cross-lingual 6/6 — while `cr_new_capability` held at 6/10 for every size (no
hallucination regression) and `cr_limit_quota` held at 4/4. All runs
`assist_failures=0`. Remaining misses cluster in the finding-#2 tokenizer artifacts
(SB-016/039/042), IdP-brand paraphrases (SB-020/021) and vague-request gray areas.

## What v0 already surfaced (known findings)

1. **English maintenance routing gap** *(fixed in round 2)* — the maintenance branch
   keyed on Turkish defect vocabulary, and defect reports share vocabulary with the
   broken feature's clause rather than the maintenance clause itself, so English
   "crash / bug / broken / error" requests never reached it (1/6). Fixed by an English
   defect vocabulary + a relaxed maintenance path with an overlap-independent citation:
   deterministic 1/6 → 3/6, all model rows 1/6 → 4/6. The dataset was not edited.
2. **Tokenizer adversarial artifacts** — e.g. "third-party developers" pulls toward the
   "third-party identity provider" exclusion; "bulk import of customer **data**" grazes
   "real-time **data** streaming". Honest weaknesses; cases stay. (A coverage-floor fix
   was tried and reverted: it also killed legitimate single-head-term exclusions. The
   semantic distinction belongs to the LLM lane.)
3. **Bi-encoder embeddings cannot make the scope-vs-CR distinction** (round 4,
   measured on this set). nomic-embed-text and bge-m3 showed no usable separation at
   all — an "Azure AD login" paraphrase preferred the INCLUDED auth clause over the
   SSO exclusion. qwen3-embedding:0.6b got directions right, but no cosine threshold
   separates *"a paraphrase of a clause"* (IN) from *"a new capability near a clause"*
   (CR): an audit-log request scored 0.629 against the reporting clause while a real
   reporting paraphrase scored 0.630. An include-side floor bought +5 total at the
   cost of collapsing `cr_new_capability` 4/10 → 2/10 with confidently-wrong INs —
   rejected. The shipped design is therefore asymmetric: embeddings route only
   **clear exclusion matches** (strong cosine + dominance margin) and otherwise add
   an informational nearest-clause note. The paraphrase judgment stays with the
   guarded LLM assist — which is exactly what this scoreboard shows working.

## Held-out validation (overfit check)

Both the golden set and EtkiBench v0 were fully visible during the round-1/2 engine
tuning — so the improvements above could, in principle, be partly fit to those 66
cases. To measure generalization, `heldout_v0.json` (36 cases, same strata and
labeling methodology) is anchored to a **different corpus** the tuning never touched:
**Northwind Shop** (`samples/demo_shop_en`, `config/connectors.heldout.yaml` — cart /
payments with an exhausted effort pool / catalog; exclusions: crypto, marketplace).

**Protocol:** the set was authored *after* round 2 closed, committed *before* any
engine run against it (verifiable in git history), then scored **once** and reported
as-is below. It must not be used to tune the engine unless a fresh held-out set is
authored to replace it.

```bash
uv run python -m eval.runner --dataset eval/datasets/etkibench/heldout_v0.json \
    --connectors config/connectors.heldout.yaml
```

**One-shot results** (dev-set score alongside for the generalization comparison):

| Mode | Held-out (36) | 95% CI | Dev set (66) |
|---|---|---|---|
| gpt-oss:120b (Ollama, DGX GB10) | **26/36 (72%)** | 56%–84% | 77% |
| gpt-oss:20b (Ollama, DGX GB10) | **26/36 (72%)** | 56%–84% | 74% |
| claude-opus-4-8 (Anthropic API)* | **26/36 (72%)** | 56%–84% | — |
| qwen2.5:14b (Ollama, DGX GB10) | 22/36 (61%) | 45%–75% | 67% |
| Deterministic (no LLM) | 18/36 (50%) | 34%–66% | 53% |

\* *Disclosure: the Claude row ran first by accident — the runner picked up the
machine's configured Anthropic key — and is reported as the one-shot it was.*

**Reading:** the rounds 1–2 improvements **generalize**. The deterministic baseline
replicates almost exactly (50% vs 53%), and the assist lift carries to a corpus the
tuning never saw: 20b 74%→72%, 120b 77%→72%, 14b 67%→61% — mild regression toward
the mean, CIs overlapping, no collapse. Stratum detail confirms the *structural*
fixes travel: `out_of_scope_paraphrase` 3/3 on every model (exclusion routing),
`in_scope_paraphrase` 4/5 at 20b/120b (strength-gated matching), maintenance 2/3
(the miss is "shows the wrong state" — defect phrasing outside the vocabulary, a
known boundary). Weakest held-out strata: effort-pool CRs (0–1/1) and one
cross-lingual paraphrase. **This set is now burned for tuning** — any future
engine round must author a fresh held-out set to claim generalization.

### Judge-mode assist (v3) — measured, negative result

An alternative assist design was hypothesized to protect CR answers better:
instead of letting the model *pick* a clause from the full baseline ("pick",
the shipped v2), build a lexical candidate shortlist and ask for per-clause
verdicts (`covers / new_capability / excluded / unrelated`) with an explicit
new-capability guard ("judge", opt-in via `ETKI_LLM_ASSIST_MODE=judge`).

One A/B on the dev set (same round-3 engine, embeddings off, `assist_failures=0`):

| Model | pick (v2) | judge (v3) |
|---|---|---|
| gpt-oss:20b | **55/66 (83%)** | 46/66 (70%) |
| gpt-oss:120b | **55/66 (83%)** | 47/66 (71%) |

Judge loses on both models, and the stratum detail shows why:
`out_of_scope_paraphrase` collapses 3/3 → 0/3 and `cr_new_capability` drops
6/10 → 4/10 — the **lexical shortlist is the bottleneck**. Exactly on the
paraphrase cases where the assist matters, the right clause never makes the
shortlist, so the per-clause verdicts run on the wrong candidates and the
engine escalates to GRAY. Pick mode hands the model the full clause list and
avoids the trap. Lesson recorded: shortlist quality bounds any judge-style
design; a judge over *semantic* candidates would need an embedding shortlist —
which finding #3 already shows can't separate IN from CR. The default remains
**"pick"**; v3 stays available as an opt-in experiment flag.

(Per protocol, no default changed, so held-out v2 below remains unscored.)

### Pick-then-verify assist (v4a) — measured, negative result

v3's failure was candidate generation, so the next hypothesis kept pick's
full-list selection and added ONE focused follow-up on the accepted INCLUDED
clause: *"does this clause cover the request, or is it a new capability near
it?"* — only a confident `new_capability` cancels the in-scope floor
(opt-in via `ETKI_LLM_ASSIST_MODE=verify`, fail-open to pick on any error).

Because run-to-run noise turned out to be real (see below), this A/B was scored
against a **same-day pick control**, not the historical 55/66 row:

| Model | pick (same-day control) | verify (v4a) |
|---|---|---|
| gpt-oss:20b | 54/66 | 53/66 |
| gpt-oss:120b | **55/66** | 51/66 |

Two findings, both instructive:

1. **Verify cannot improve its target stratum.** `cr_new_capability` is 4/10
   under both modes *with identical misses* — those misses come from the
   deterministic side (two exclusion-artifact OUT flips, four two-evidence GRAY
   escalations where impacted-module evidence conflicts with a low text score),
   not from wrong assist floors. There is nothing for a verify layer to cancel.
2. **Verify adds new damage instead:** `in_scope_direct` 10/10 → 8/10 — on
   borderline automation phrasings ("log users out automatically…") the model
   answers `new_capability` for genuinely covered deliverables. Asked point-blank,
   the covers-vs-new-capability boundary is hard even for a capable LLM; pick's
   implicit rule ("don't force a new capability onto a clause") outperforms an
   explicit post-hoc verdict.

Methodology note adopted from this round: same-model reruns differ by ±1–2
cases day-over-day (20b pick 55 → 54; one cross-lingual case flipped both ways).
Scoreboard deltas of ≤2 are treated as noise, and every future A/B runs a
same-day control arm. Default remains **"pick"**; verify stays as an opt-in flag.

### Cross-encoder separability (v4b measurement) — POSITIVE, not yet integrated

Finding #3 showed bi-encoders cannot separate *"a paraphrase of a clause"* (IN)
from *"a new capability near a clause"* (CR) — 0.629 vs 0.630 cosine. The v4b
question: can a **cross-encoder**, which reads the (request, clause) pair
jointly, make that distinction? Measured in isolation (no engine integration)
with `BAAI/bge-reranker-v2-m3` over every (request, clause) pair of the dev set:

| Separation (on max score over INCLUDED clauses) | AUC |
|---|---|
| in_scope (direct+paraphrase) vs cr_new_capability | **0.978** |
| in_scope_paraphrase alone vs cr_new_capability | **0.975** |
| exclusion side: out_* vs rest (max over EXCLUDED) | 0.838 |

The margins are real, not rank noise: paraphrase pairs score −7.5..−2.8 raw
logits while new-capability pairs sit at −9.9..−7.05 — a ≈−7.2 threshold puts
7/8 paraphrases above and 10/10 new-capability cases below. **This is the first
mechanism measured on this benchmark that makes the IN-vs-CR distinction
without an LLM.** Known caveats going into integration: thresholds are
model-specific (like the embedding thresholds), single-word vague requests can
score high (the engine's short-query guard already caps those at GRAY), the
exclusion side is weaker, and 66 cases invite threshold overfit — so the
integration A/B follows the same-day-control standard and any default change
burns held-out v2.

### Reranker integration (v4b) — deterministic +4, not additive to the LLM

The separability finding above shipped as an opt-in evidence layer
(`ETKI_RERANK_BASE_URL`, TEI-compatible `/rerank`, include-side floor only,
raw-logit threshold calibrated for bge-reranker-v2-m3). Same-day-control A/B:

| Configuration | Score |
|---|---|
| Deterministic (control) | 41/66 |
| **Deterministic + reranker** | **45/66** (+4, misses a strict subset — zero regressions) |
| gpt-oss:20b pick (control) | 54/66 |
| gpt-oss:20b pick + reranker | 54/66 (±0) |
| gpt-oss:120b pick (control) | 55/66 |
| gpt-oss:120b pick + reranker | 54/66 (−1, within noise) |

Reading: the reranker and the LLM assist claim the **same paraphrase headroom**
— stacked, they don't compound. The value is in the **LLM-free row**: three
in-scope paraphrases and one effort-pool case (the clause match unlocked the
pool check) now resolve fully locally and deterministically — roughly 40% of
the LLM assist's lift at zero LLM cost, which matters for air-gapped
deployments. Honesty notes: the threshold was calibrated on this same dev set
(treat 45/66 as an upper bound; no held-out claim is made), the layer is off
by default, and no engine default changed — held-out v2 stays sealed.

### Vendor lexicon (v4c) — deterministic +2, targeted

Requests name PRODUCTS while contracts name CONCEPTS ("integrate Okta" vs
"third-party identity provider (IdP) … out of scope"). A deliberately
conservative brand→concept lexicon in the tokenizer (Okta/Auth0/Keycloak/
OneLogin/Entra/Azure→idp, Android/iPhone/iOS/phone→mobile,
Ethereum→cryptocurrency) fixes exactly the two targeted misses — SB-020 and
SB-023, `out_of_scope_direct` 5/7 → 7/7 — with zero regressions and the frozen
golden set unchanged at 61/66. Ambiguous words ("live", "native") and any term
the sealed held-out v2 tests were deliberately left out (no contamination).
Deterministic runs are bit-reproducible, so this +2 is real, not noise.

**Deterministic story so far:** 33/66 (v1 snapshot) → 41 (round 3, stopwords)
→ **43 (+lexicon) → 45 (+reranker) → 47/66 (71%) with both** — the local
layers compose with zero regressions:

| Deterministic configuration | Score |
|---|---|
| round-3 engine (control) | 41/66 |
| + vendor lexicon (v4c) | 43/66 |
| + reranker (v4b) | 45/66 |
| + both | **47/66 (71%)** |

### Round 5 — word-numbers + the reranker as negative evidence

**v5a (word-numbers):** "six reports" / "a fourth provider" / "altı rapor" now
reach the limit check (cardinals AND ordinals, EN+TR; "on"/"one"/"bir" excluded
as ambiguous). Fixed exactly the two targeted fresh-batch misses (KM-09,
KN-09); dev-66 and the golden set untouched.

**v5b (negative evidence):** the gray band holds two very different
populations — genuinely vague asks (correctly GRAY) and new-capability requests
whose lexical overlap with a clause is a tokenizer artifact. The cross-encoder
already tells them apart: when its best include score is *below* the floor
threshold ("no clause covers this"), a declarative full-sentence gray-band case
is reclassified CR. Guards, both measured in: short/vague requests exempt
(that's what the band is for) and **interrogative requests exempt** — a
question ("Can the system be faster…?") signals the asker's own uncertainty
(added after exactly one such regression, SB-053, showed up and was fixed).
The negative signal also fires at a margin-failed single exclusion graze
(exc_hits ≤ 1) — that is where the finding-#2 artifact cases were stuck —
while the include *floor* still requires zero exclusion evidence.

**v5c (defect-symptom routing):** two measured gaps in maintenance routing —
symptom phrasings without defect vocabulary ("cuts off the last page", "shows
an empty page"; added as *phrases*, not single words), and defect reports that
share no token with the broken feature's clause ("the login button does
nothing" vs an auth clause that never says "login") — the second-evidence rule
now accepts **code evidence** (impacted modules mapped to scoped clauses) in
place of text overlap for defect-type requests. Maintenance went 4/6 → 6/6 on
dev-66 and KN-11 resolved.

| Deterministic configuration (dev-66) | Score |
|---|---|
| round-3 engine | 41/66 |
| + lexicon (v4c) + reranker (v4b) | 47/66 |
| + word-numbers & negative evidence (v5a/b) | 51/66 |
| + defect-symptom routing (v5c) | **53/66 (80%)** |

Fresh batch: Meridian 5→7/12, Northwind 2→6/12. Golden set unchanged at
61/66; every miss list is a strict subset of its control. Honest note: four
in-scope paraphrase misses that used to escalate to GRAY now land as confident
CRs (SB-009/011/064 + one variant) — the same borderline cases sitting below
the reranker threshold; a slightly worse failure mode (no human escalation)
traded for the structural wins. The deterministic, LLM-free row has now gone
**33 → 53 (50% → 80%)** since the v1 snapshot — above the LLM-assisted
qwen2.5:14b row (73%) and two cases behind the gpt-oss rows (83%), with zero
LLM calls.

### Full-suite deterministic score (v5d, 150 open cases)

The strongest LLM-free configuration (lexicon + reranker + v5 rules) over
every open file:

| File | Score |
|---|---|
| etkibench_v0 (dev-66, tuning target) | 53/66 (80%) |
| heldout_v0 (36, burned) | 25/36 (69%) |
| heldout_v1 (24, burned) | 18/24 (75%) |
| etkibench_v1 fresh batch (24) | 13/24 (54%) |
| **Suite total** | **109/150 (73%)** |

Honest reading: rounds 3–5 tuned only against dev-66, so the 80%-there vs
67% on the other 84 cases (56/84) quantifies the tuning-set gap directly.
Still, the never-tuned files improved dramatically against their own history —
heldout_v0 was 18/36 (50%) at its one-shot, now 25/36; heldout_v1 was 10/24,
now 18/24 — the local layers generalize, they are just not magic.

**Full-suite LLM rows** (pick assist, production config, no reranker;
`assist_failures=0` on both):

| Configuration | dev-66 | heldout_v0 | heldout_v1 | fresh | **Suite (150)** |
|---|---|---|---|---|---|
| gpt-oss:20b pick | 54 | 27 | 19 | 15 | **115 (77%)** |
| gpt-oss:120b pick | 54 | 27 | 19 | 15 | **115 (77%)** |
| Deterministic + local layers | 53 | 25 | 18 | 13 | **109 (73%)** |

The two model sizes land on identical totals with near-identical miss lists —
on a guarded, whitelist-validated assist the model has little room to
differentiate. The headline result is the gap: the LLM's edge over the fully
local deterministic stack is now **6 cases in 150 (4pp)** — on dev-66 it is a
single case (54 vs 53). For air-gapped deployments the local stack is,
measurably, almost the whole product.

### Round 6 — the exclusion side of the cross-encoder (measured, negative)

The reranker's exclusion side (AUC 0.838 in the v4b measurement) was the last
unused signal, with two mirrored hypotheses: *positive* (an OUT-paraphrase
scores high against its EXCLUDED clause → second exclusion evidence) and
*veto* (an artifact single-hit exclusion scores low against the clause it
grazes → cancel the exclusion). Per-case measurement kills both:

- OUT-paraphrases score **low** against their own exclusion clause
  ("connect to our Azure AD…" vs the SSO exclusion: −9.7 raw; the phones and
  live-update paraphrases likewise ≤ −9). The cross-encoder reads an exclusion
  clause as a *statement about exclusion*, not as a topic — relevance only
  fires on literal topic identity (blockchain↔cryptocurrency, −3.7, the one
  case it would fix).
- The veto cannot be thresholded: legitimately excluded requests score as low
  as the artifacts (legit "Build an Android app" −9.1, "corporate directory"
  −8.6 vs artifact −9.7). A −8 veto would trade 2 fixes for 3 regressions.

So the v4b AUC of 0.838 was carried by direct cases and is useless at the
margin. This is the symmetric completion of finding #3: **the scope judgment
is not reducible to relevance scoring at either polarity** — the include side
works only because "does clause X cover request Y" happens to align with
relevance when X is a *deliverable* clause; exclusion clauses break that
alignment. Nothing was integrated; the exclusion lane stays lexical
(+ the guarded LLM assist).

### Round 6 — the full stack, measured (LLM + reranker + v5 rules)

The v4-era "reranker is not additive to the LLM" verdict is now obsolete: v5
gave the reranker decision roles the LLM assist does not have (the negative
gray-band evidence and defect-symptom code routing). Stacked, the layers
compound (`assist_failures=0` on both models):

| Configuration | dev-66 | heldout_v0 | heldout_v1 | fresh | **Suite (150)** |
|---|---|---|---|---|---|
| **gpt-oss:120b pick + reranker** | 59 | 30 | 22 | 16 | **127 (85%)** |
| **gpt-oss:20b pick + reranker** | 58 | 29 | 22 | 15 | **124 (83%)** |
| gpt-oss pick only (either size) | 54 | 27 | 19 | 15 | 115 (77%) |
| Deterministic + local layers | 53 | 25 | 18 | 13 | 109 (73%) |

heldout_v1 Meridian is a perfect 12/12 under the full stack. This is also the
first time model size differentiates positively (127 vs 124, +3 — at the edge
of the ±2 noise band, so read it as a lean, not a law). Remaining misses now
concentrate in three honest families: exclusion-side paraphrases (the finding
above says no local signal reaches them), the two finding-#2 tokenizer
artifacts, and gray-vague boundary disagreements.

### Round 7 — opening the last two doors for the guarded LLM

Round 6 proved no *local* signal reaches the exclusion-side paraphrases; the
guarded LLM was the only lane left — and it turned out the lane was gated shut.

**v7a (gate widening):** the assist gate required `exc_hits == 0`, so any
request grazing an exclusion by a single token ("connect to our **Azure AD**…")
was never shown to the LLM at all. The gate now admits a margin-failed single
graze (mirroring the v5b reranker gate); with any graze present an INCLUDED
pick cannot lift the score (it could tip the deterministic exclusion-margin
comparison) — only a strong EXCLUDED pick is acted on. **+6 on both models,
zero regressions**; every targeted exclusion-paraphrase resolved.

**v7b (exclusion veto):** a single-hit exclusion about to rout via the margin
rule gets one focused confirmation question — *does the work this clause
excludes match the work this request asks for?* ("a contact's mobile-number
field" ≠ "mobile application development"). Fail-open: errors and "excluded"
verdicts leave the deterministic route untouched; 2+-hit exclusions are never
questioned; a veto-confirmed case skips the assist call entirely. Unlike the
v4a covers/new-capability boundary (measured too hard for a direct question),
this clause-level yes/no is crisp. **+3 on both models, zero regressions**:
both remaining finding-#2 artifacts' worst case (SB-039, the designed KM-08
trap) resolved, and the veto also rescued a legitimate in-scope request that a
false exclusion had been routing OUT (H-009). SB-042 remains the one honest
artifact (the model confirms its exclusion).

| Configuration | dev-66 | heldout_v0 | heldout_v1 | fresh | **Suite (150)** |
|---|---|---|---|---|---|
| **gpt-oss:120b full stack (v7)** | **62 (94%)** | 32 | 22 | 20 | **136 (91%)** |
| gpt-oss:20b full stack (v7) | 61 | 31 | 22 | 19 | **133 (89%)** |
| full stack pre-v7 | 59 | 30 | 22 | 16 | 127 (85%) |
| Deterministic + local layers | 53 | 25 | 18 | 13 | 109 (73%) |

`assist_failures=0` throughout. The journey on the headline file: **v1
snapshot 45% (120b) → 94%** — and the remaining misses are two tokenizer-
artifact INs (SB-012/016), one confirmed-artifact exclusion (SB-042) and one
gray-boundary disagreement (SB-049).

### Round 8 — a real product bug the benchmark surfaced (net 0 on the scoreboard)

Chasing the persistent `N1-10`/`H-028` misses (effort-pool CRs answered IN)
uncovered a mechanism bug, not a judgment gap: the English payments clause
("…Integration with at most 3 payment providers…") tied 1–1 between the
`payment` and `integration` category keyword lists and lost the tie on dict
order — so the clause's 30-hour effort pool was keyed to `integration` while
every work item logged under `payment`. **`consumed` was 0 forever; the pool
feature was dead on this corpus.** Fixed by adding the missing English card
keywords (the tie breaks 3–1); regression-tested at the extractor level.

Scoreboard effect: exactly net 0 on both models — the two real pool-CRs now
resolve (H-028, N1-10) while two single-word gray cases that graze the pooled
clause now trigger a confident pool-breach CR (H-029 "payments", N1-12
"usability"). A short-query exemption for the pool check was tried and
**reverted**: the frozen golden set expects the opposite for the same
structure (GS-53 "entegrasyon", single word, labeled CR on an exhausted
pool). **Two frozen answer keys disagree on this boundary** — recorded here as
an open label tension rather than resolved by editing either key. The fix
ships anyway: a customer's exhausted pool now actually fires, which is worth
more than two benchmark cases.

### Held-out v2 — REGISTERED, UNSCORED

`heldout_v2_meridian.json` + `heldout_v2_northwind.json` (12 + 12 cases, same
strata mix and labeling methodology as v1, near-duplicate-checked against every
existing set) were authored on 2026-07-04, **after** the round-3/4 engine closed
and **before any engine run against them** — this commit is the pre-registration.
They exist to back the next default-changing engine claim (first candidate: the
judge-mode assist default flip, pending its deferred A/B). Per protocol they will
be scored **once**, reported as-is, and then burned. Do not run them casually;
do not tune against them.

```bash
# The one-shot, when its time comes (not before):
uv run python -m eval.runner --dataset eval/datasets/etkibench/heldout_v2_meridian.json \
    --connectors config/connectors.etkibench.yaml
uv run python -m eval.runner --dataset eval/datasets/etkibench/heldout_v2_northwind.json \
    --connectors config/connectors.heldout.yaml
```

## Rules

- **This is not the CI gate.** The gate is `eval/datasets/frozen/golden_crs.json`
  (66 separate cases, agreement ≥ 0.8, Wilson-interval verdicts). EtkiBench is a
  public benchmark: no threshold, report-only.
- **Never tune the engine against EtkiBench and edit EtkiBench in the same PR.**
  Same answer-key discipline as the golden set.
- **Contributing cases:** keep them anchored to the bundled corpus, one clause-citing
  `rationale` per case, labels argued from the contract — open a PR and expect the
  label to be debated. Growing the set (target: 150) and adding a second corpus are
  both welcome.

### 2026-07-12 — English prompts, dependency rounds, and the reranker lane

Engine state for these rows: the dependency-change decision branch + surface-based
dependency effort (2026-07-09/11), and **all LLM prompts translated to English**
(output language still follows the project via the language directive). Same
`etkibench_v0.json`, same production configuration; reranker rows use a live
bge-reranker-v2-m3 (TEI-compatible `scripts/rerank_server.py`, raw logits,
p50 88 ms / p90 106 ms over the network — comfortably inside a +200 ms budget).

| Mode | Agreement | 95% CI |
|---|---|---|
| gpt-oss:20b + reranker (Ollama, DGX GB10) | **62/66 (94%)** | 85%–98% |
| gpt-oss:20b (Ollama, DGX GB10) | **58/66 (88%)** | 78%–94% |
| gemma3:27b (Ollama, DGX GB10) | **58/66 (88%)** | 78%–94% |
| gpt-oss:120b (Ollama, DGX GB10) | 56/66 (85%) | 74%–92% |
| qwen2.5:32b (Ollama, DGX GB10) | 54/66 (82%) | 71%–89% |
| llama3.3:70b (Ollama, DGX GB10) | 53/66 (80%) | 69%–88% |
| Deterministic + reranker (no LLM) | **53/66 (80%)** | 69%–88% |
| qwen2.5-coder:7b (Ollama, DGX GB10) | 51/66 (77%) | 66%–86% |
| qwen2.5:14b (Ollama, DGX GB10) | 50/66 (76%) | 64%–84% |
| Deterministic (no assists) | 45/66 (68%) | 56%–78% |

Honest notes:

- **The English-prompt translation held**: 120b 55 → 56, i.e. inside noise — prompt
  language is not load-bearing for the guarded assist.
- **The small-beats-big finding got stronger**: gemma3:27b and gpt-oss:20b (88%) sit
  above 120b (85%), and 20b finishes the whole bench in ~3 minutes vs ~20. All CIs
  overlap at n=66, so 88-vs-85 is not a significant ranking — but "a 20B-class model
  is enough for the guarded assist" is.
- **The reranker lane is the cheapest win measured so far**: +12 pts with no LLM at
  all, deterministic and reproducible. BUT the frozen golden set moves 61 → 57/66
  with it (adversarial paraphrase-negatives get promoted past the strength floor),
  so it stays **opt-in**; recalibrating `rerank_strong` on a dev set (never on
  golden) is the registered follow-up.
- **Packing A/B (GraphRAG)**: the same live reranker was also A/B-tested for
  context-packing order under a tight token budget — recall 0.99 → 0.97 vs plain
  BFS, confirming the earlier keyword-fake smoke. Packing stays BFS; published as a
  negative result.
