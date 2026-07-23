"""Gate / back-test runner.

Two gates:
1. Decision agreement (Faz 0) — do decisions match the expected type.
2. Retrieval (Faz 1) — are the right scope clause + code regions retrieved (precision/recall).

The engine is built over an AST-based index for Joern-free reproducibility
(the live Joern index is the production path; the logic is validated on the
same normalized graph). Runs on every PR; non-zero exit below threshold (CI gate).

Usage:
    python -m eval.runner                       # full CI gate (unchanged, deterministic)
    python -m eval.runner --dataset cases.json  # report-only run over YOUR labeled cases
    python -m eval.runner --llm [...]           # enable the configured LLM assist (env)

`--dataset` case format (actual_effort_hours optional):
    [{"id": "...", "request_text": "...", "expected_decision": "IN_SCOPE",
      "actual_effort_hours": 6}, ...]
`--llm` requires a configured provider (ETKI_LLM_BASE_URL for Ollama/vLLM, or
ETKI_LLM_PROVIDER=anthropic + API key) — this is how different models can be
scored against the same dataset. Scope extraction stays heuristic either way, so
the baseline is identical across runs and only the matching assist is compared.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from etki.adapters.ast_code_index import AstCodeRepositoryProvider
from etki.adapters.code_index import StaticCodeRepository
from etki.adapters.registry import (
    build_documents,
    build_embedder,
    build_llm_client,
    build_reranker,
    build_work_items,
)
from etki.config import Settings, load_connectors
from etki.core.ports import LLMClient
from etki.engine.estimation import consumed_by_category
from etki.engine.triage import TriageEngine
from etki.extraction.scope_extractor import build_scope_extractor
from etki.indexing.engine import IndexingEngine

from eval import backtest, graph_retrieval, retrieval
from eval.stats import gate_verdict, wilson_interval

_DATASETS = Path(__file__).parent / "datasets"
AGREEMENT_THRESHOLD = 0.8
SCOPE_F1_THRESHOLD = 0.8
MODULE_RECALL_THRESHOLD = 0.8
BACKTEST_AGREEMENT = 0.75
BACKTEST_RANGE = 0.70
# Golden set (eval/datasets/frozen/) — frozen, stratified ≥60 cases. Changing the golden
# set in the SAME PR as an engine/synonym change is forbidden (see CLAUDE.md).
GOLDEN_AGREEMENT = 0.8
# Graph retrieval (Faz 2.6): TR-only gate (EN rows are embedding-run report points;
# the shop_en corpus is held-out → report-only forever). First honest runs:
# demo find_k 0.82 → combined 1.00 (precision 0.36 — the measured Faz 4 rerank
# motivation). Floor below the first measurement; combined must also never fall
# behind plain find_k. Applies to every gated corpus in graph_retrieval.CORPORA.
GRAPH_COMBINED_RECALL = 0.9


async def build_engine(
    llm_client: LLMClient | None = None,
    connectors_path: str | None = None,
    code_engine: str = "ast",
) -> TriageEngine:
    settings = Settings()
    connectors = load_connectors(connectors_path or settings.connectors_path)
    documents = build_documents(connectors.documents)
    src_root = connectors.code_repo.options.get("src_root", "samples/demo_project/src")
    if code_engine == "graphify":
        # Opt-in engine comparison run (--engine graphify); the CI gate stays on ast.
        import tempfile

        from etki.adapters.graphify_code_repo import GraphifyCodeRepositoryProvider

        export = Path(tempfile.mkdtemp(prefix="etki-eval-graphify-")) / "graphify-out"
        code_repo: AstCodeRepositoryProvider | GraphifyCodeRepositoryProvider = (
            GraphifyCodeRepositoryProvider(src_root, export_dir=export)
        )
    else:
        code_repo = AstCodeRepositoryProvider(src_root)  # reproducible, no Joern required
    extractor = build_scope_extractor()  # heuristic even with --llm (identical baseline)
    index = await IndexingEngine(documents, code_repo, extractor).build()
    work_items = build_work_items(connectors.work_items)
    consumed = (
        consumed_by_category(work_items.all_items())
        if hasattr(work_items, "all_items")
        else {}
    )
    return TriageEngine(
        work_items,
        StaticCodeRepository(index.modules),
        documents,
        index.baseline,
        index_freshness=index.freshness,
        consumed_by_category=consumed,
        in_scope_threshold=settings.in_scope_threshold,
        gray_threshold=settings.gray_threshold,
        llm_client=llm_client,  # None in CI → fully deterministic gate
        llm_assist_mode=settings.llm_assist_mode,  # pick (v2) | judge (v3) — env-driven A/B
        # Embeddings are env-driven (ETKI_EMBED_BASE_URL): absent in CI → pure
        # lexical; when present they are deterministic per model (reproducible runs).
        embedder=build_embedder(settings),
        embed_strong=settings.embed_strong,
        embed_weak=settings.embed_weak,
        # Reranker is env-driven too (ETKI_RERANK_BASE_URL): absent in CI → off.
        reranker=build_reranker(settings),
        rerank_strong=settings.rerank_strong,
        # When constants change via config, the gate re-measures (no code change needed).
        estimation_params=settings.estimation_params(),
        # Manifest declarations (dependency-change recognition + branch evidence).
        dependencies=index.dependencies,
    )


async def _decision_agreement(engine: TriageEngine) -> tuple[bool, str]:
    cases = json.loads((_DATASETS / "sample_crs.json").read_text(encoding="utf-8"))
    total = matched = 0
    failures: list[str] = []
    for case in cases:
        result = await engine.triage(case["request_text"], request_id=case["id"])
        expected = case["expected"]
        got = [d.decision.value for d in result.decisions]
        if len(got) != len(expected):
            failures.append(f"{case['id']}: {len(got)} alt-ister, beklenen {len(expected)}")
        for exp, actual in zip(expected, got, strict=False):
            total += 1
            matched += exp == actual
            if exp != actual:
                failures.append(f"{case['id']}: beklenen {exp}, gelen {actual}")
    agreement = matched / total if total else 0.0
    ok = not failures and agreement >= AGREEMENT_THRESHOLD
    report = f"karar-örtüşme: {matched}/{total} ({agreement:.0%})"
    for f in failures:
        report += f"\n  ✗ {f}"
    return ok, report


async def _golden_agreement(engine: TriageEngine) -> tuple[bool, str]:
    """Decision agreement over the frozen golden set — reported with a Wilson interval.

    A marginal threshold breach (interval still covers the threshold) prints a WARNING
    but does not fail the gate; a clear breach (upper bound < threshold) fails it."""
    cases = json.loads((_DATASETS / "frozen" / "golden_crs.json").read_text(encoding="utf-8"))
    matched = 0
    misses: list[str] = []
    for cr in cases:
        case = await engine.triage(cr["request_text"], request_id=cr["id"])
        got = case.decisions[0].decision.value
        if got == cr["expected_decision"]:
            matched += 1
        else:
            misses.append(f"{cr['id']}: beklenen {cr['expected_decision']}, gelen {got}")
    n = len(cases)
    verdict, (low, high) = gate_verdict(matched, n, GOLDEN_AGREEMENT)
    point = matched / n if n else 0.0
    label = {"gecti": "✓", "uyari": "UYARI (marjinal — gürültü payı içinde)", "kaldi": "✗"}
    report = (
        f"golden-set örtüşme: {matched}/{n} ({point:.0%}, %95 GA {low:.0%}–{high:.0%}, "
        f"eşik {GOLDEN_AGREEMENT:.0%}) {label[verdict]}"
    )
    for m in misses:
        report += f"\n  ✗ {m}"
    if verdict == "uyari":
        # Surfaced as a first-class CI annotation: the warn band is statistically
        # defensible (Wilson) but must never pass silently — the real hard floor
        # sits at the interval's edge (47/66 ≈ 71%), not the advertised 80%.
        print(f"::warning title=Golden warn-bandı::{report.splitlines()[0]}")
    return verdict != "kaldi", report


async def run_dataset(
    path: Path,
    llm_client: LLMClient | None,
    connectors_path: str | None = None,
    code_engine: str = "ast",
) -> int:
    """Report-only run over a user-supplied case file: decision agreement (Wilson
    interval) + effort-in-range over the rows that carry actual_effort_hours.
    No thresholds are applied — this is a benchmark report, not the CI gate."""
    engine = await build_engine(llm_client, connectors_path, code_engine)
    bt = await backtest.evaluate(engine, path)
    n = len(bt["rows"])
    matched = round(bt["agreement"] * n)
    low, high = wilson_interval(matched, n)
    mode = "deterministic" if llm_client is None else "deterministic+LLM assist"
    print(f"dataset: {path} ({n} vaka, mod: {mode}, kod motoru: {code_engine})")
    print(f"karar-örtüşme: {matched}/{n} ({bt['agreement']:.0%}, %95 GA {low:.0%}–{high:.0%})")
    if bt["range_accuracy"] is not None:
        print(
            f"efor-isabet: {bt['range_accuracy']:.0%} "
            f"({bt['effort_scored']}/{n} vakada gerçek efor etiketi var)"
        )
    else:
        print("efor-isabet: — (hiçbir vakada actual_effort_hours yok)")
    print(f"kapsam-dışı P/R: {bt['oos_precision']:.2f}/{bt['oos_recall']:.2f}")
    print(
        f"gri-alan P/R: {bt['gray_precision']:.2f}/{bt['gray_recall']:.2f} "
        f"({bt['gray_produced']} GRAY üretildi)"
    )
    for row in bt["rows"]:
        mark = "✓" if row["match"] else "✗"
        effort = ""
        if row["actual"] is not None:
            rng = "✓" if row["in_range"] else "✗"
            effort = f" efor {row['actual']}sa∈{row['range']}={rng}"
        print(f"  {mark} {row['id']}: {row['got']} (beklenen {row['expected']}){effort}")
    return 0


async def run(llm_client: LLMClient | None = None, code_engine: str = "ast") -> int:
    engine = await build_engine(llm_client, code_engine=code_engine)

    agreement_ok, agreement_report = await _decision_agreement(engine)
    print(agreement_report)

    golden_ok, golden_report = await _golden_agreement(engine)
    print(golden_report)

    metrics = await retrieval.evaluate(engine, _DATASETS / "retrieval_crs.json")
    print(
        f"retrieval: scope_f1={metrics['mean_scope_f1']:.2f} "
        f"module_recall={metrics['mean_module_recall']:.2f}"
    )
    for row in metrics["rows"]:
        mark = "✓" if row["scope_f1"] >= SCOPE_F1_THRESHOLD else "✗"
        print(f"  {mark} {row['id']}: scope_f1={row['scope_f1']} "
              f"module_recall={row['module_recall']} "
              f"(getirilen {row['retrieved_scopes']} / beklenen {row['expected_scopes']})")

    retrieval_ok = (
        metrics["mean_scope_f1"] >= SCOPE_F1_THRESHOLD
        and metrics["mean_module_recall"] >= MODULE_RECALL_THRESHOLD
    )

    bt = await backtest.evaluate(engine, _DATASETS / "backtest_crs.json")
    bt_n = len(bt["rows"])
    bt_low, bt_high = wilson_interval(round(bt["agreement"] * bt_n), bt_n)
    print(
        f"geriye-test: örtüşme={bt['agreement']:.0%} (%95 GA {bt_low:.0%}–{bt_high:.0%}) "
        f"efor-isabet={bt['range_accuracy']:.0%} "
        f"kapsam-dışı P/R={bt['oos_precision']:.2f}/{bt['oos_recall']:.2f} "
        f"gri P/R={bt['gray_precision']:.2f}/{bt['gray_recall']:.2f}"
    )
    for row in bt["rows"]:
        mark = "✓" if row["match"] else "✗"
        rng = "✓" if row["in_range"] else "✗"
        print(f"  {mark} {row['id']}: {row['got']} (beklenen {row['expected']}) "
              f"efor {row['actual']}sa∈{row['range']}={rng}")
    backtest_ok = (
        bt["agreement"] >= BACKTEST_AGREEMENT and bt["range_accuracy"] >= BACKTEST_RANGE
    )

    graph_results = await graph_retrieval.evaluate_corpora()
    print(graph_retrieval.corpora_report(graph_results))
    graph_ok = all(
        m["tr_combined"] >= GRAPH_COMBINED_RECALL
        and m["tr_combined"] >= m["tr_find_k"]  # expand must never hurt recall
        for m in graph_results.values()
        if m["gated"]
    )

    ok = agreement_ok and golden_ok and retrieval_ok and backtest_ok and graph_ok
    print("eval SONUÇ:", "GEÇTİ ✅" if ok else "KALDI ❌")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Etki eval: CI gate or custom benchmark")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=None,
        help="report-only run over this case file instead of the CI gate "
        "(format: see the module docstring)",
    )
    parser.add_argument(
        "--llm",
        action="store_true",
        help="enable the configured LLM assist (ETKI_LLM_* / ANTHROPIC_API_KEY env)",
    )
    parser.add_argument(
        "--connectors",
        default=None,
        help="connectors yaml to build the engine from (pins the benchmark corpus; "
        "only valid with --dataset)",
    )
    parser.add_argument(
        "--engine",
        choices=["ast", "graphify"],
        default="ast",
        help="code-graph engine for the comparison run (default ast — the CI gate "
        "always uses ast; graphify needs `uv sync --extra graphify`)",
    )
    args = parser.parse_args(argv)
    if args.connectors and args.dataset is None:
        parser.error("--connectors requires --dataset (the CI gate uses the default corpus)")

    llm_client: LLMClient | None = None
    if args.llm:
        llm_client = build_llm_client(Settings())
        if llm_client is None:
            print(
                "--llm istendi ama yapılandırılmış LLM yok: ETKI_LLM_BASE_URL "
                "(Ollama/vLLM) ya da ETKI_LLM_PROVIDER=anthropic + API anahtarı verin.",
                file=sys.stderr,
            )
            return 2

    if args.dataset is not None:
        if "heldout_v2" in str(args.dataset) and os.environ.get("ETKI_UNSEAL") != "1":
            print(
                "REDDEDİLDİ: heldout_v2 MÜHÜRLÜ bir tek-koşu setidir — koşmak onu yakar. "
                "Bilinçli tek-koşu için ETKI_UNSEAL=1 ile çağırın ve sonucu README'ye "
                "işleyip seti emekliye ayırın.",
                file=sys.stderr,
            )
            return 3
        return asyncio.run(run_dataset(args.dataset, llm_client, args.connectors, args.engine))
    if llm_client is not None:
        # The full suite with LLM assist — for scoring a model against the standard sets.
        # (CI never passes --llm; the gate stays deterministic.)
        print("mod: deterministic+LLM assist (zayıf eşleşmede LLM devrede)")
    if args.engine != "ast":
        print(f"mod: kod motoru = {args.engine} (karşılaştırma koşusu; CI gate ast kullanır)")
    return asyncio.run(run(llm_client, args.engine))


if __name__ == "__main__":
    sys.exit(main())
