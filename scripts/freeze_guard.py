"""Answer-key freeze guard (CI).

Mechanizes the documented rule: a change set must NOT touch engine/matching logic
and the eval answer keys at the same time — otherwise the gate can be gamed by
editing the answer key alongside the engine change (see CONTRIBUTING.md and
eval/datasets/etkibench/README.md).

Usage:
    python scripts/freeze_guard.py <git-range>     # e.g. origin/master...HEAD (PR mode)
    python scripts/freeze_guard.py --per-commit <git-range>   # push mode: each commit
                                                              # in the range is checked
                                                              # individually

Exit 0 = clean, exit 1 = violation (message names the offending files/commit).
"""

from __future__ import annotations

import subprocess
import sys

# Engine/matching logic: the code whose changes the frozen answer keys are meant
# to measure impartially.
ENGINE_PREFIXES = (
    "etki/engine/",
    "etki/extraction/",
    "etki/core/text.py",
    # Decision-equivalent lane (W5): threshold/estimation DEFAULTS live in
    # Settings — changing them changes decisions exactly like engine code, so
    # config edits cannot ride in the same change set as an answer key either.
    # (adapters/ stays OUTSIDE deliberately: manifests.py was placed there so
    # manifest tweaks never collide with the guard — a documented decision.)
    "etki/config.py",
)

# The SEALED one-shot sets: any change to them is a violation on its own —
# they are pre-registered answer keys awaiting their single scoring run.
SEALED_PREFIXES = ("eval/datasets/etkibench/heldout_v2_",)
# Answer keys: every labeled dataset the gates or the public benchmark score against.
# Only the labeled data itself (.json) — READMEs/docs inside the datasets tree are
# documentation and may legitimately change alongside engine work (e.g. scoreboards).
DATASET_PREFIX = "eval/datasets/"


def _is_answer_key(path: str) -> bool:
    return path.startswith(DATASET_PREFIX) and path.endswith(".json")


def classify(files: list[str]) -> tuple[list[str], list[str]]:
    """Splits a changed-file list into (engine-side hits, answer-key hits)."""
    engine = [f for f in files if any(f.startswith(p) for p in ENGINE_PREFIXES)]
    datasets = [f for f in files if _is_answer_key(f)]
    return engine, datasets


def violation(files: list[str]) -> str | None:
    """Returns a human-readable violation message, or None if the change set is clean."""
    sealed = [f for f in files if any(f.startswith(p) for p in SEALED_PREFIXES)]
    if sealed:
        return (
            "FREEZE VIOLATION: sealed held-out set edited: "
            + ", ".join(sealed)
            + " — heldout_v2 is a pre-registered one-shot answer key; it can only "
            "change in a change set that ALSO retires it in the EtkiBench README."
        )
    engine, datasets = classify(files)
    if engine and datasets:
        return (
            "FREEZE VIOLATION: engine/matching logic and eval answer keys changed together.\n"
            f"  engine:   {', '.join(sorted(engine))}\n"
            f"  datasets: {', '.join(sorted(datasets))}\n"
            "Split into separate PRs — grow/adjust datasets in their own PR with labels\n"
            "justified against the contract (see CONTRIBUTING.md, 'golden-set freeze rule')."
        )
    return None


def _changed_files(range_spec: str) -> list[str]:
    out = subprocess.run(
        ["git", "diff", "--name-only", range_spec],
        capture_output=True, text=True, check=True,
    )
    return [line for line in out.stdout.splitlines() if line.strip()]


def _has_parent(sha: str) -> bool:
    return (
        subprocess.run(
            ["git", "rev-parse", "--verify", "--quiet", f"{sha}^"],
            capture_output=True, text=True,
        ).returncode
        == 0
    )


def _commits_in(range_spec: str) -> list[str]:
    out = subprocess.run(
        ["git", "rev-list", range_spec],
        capture_output=True, text=True, check=True,
    )
    return [line for line in out.stdout.splitlines() if line.strip()]


def main(argv: list[str]) -> int:
    per_commit = "--per-commit" in argv
    args = [a for a in argv if a != "--per-commit"]
    if len(args) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    range_spec = args[0]

    if per_commit:
        for sha in _commits_in(range_spec):
            if not _has_parent(sha):
                # A root commit is a repository bootstrap, not an engine change —
                # it necessarily contains both engine code and answer keys.
                continue
            msg = violation(_changed_files(f"{sha}^..{sha}"))
            if msg:
                print(f"[{sha[:10]}] {msg}", file=sys.stderr)
                return 1
        print("freeze guard: clean (per-commit)")
        return 0

    msg = violation(_changed_files(range_spec))
    if msg:
        print(msg, file=sys.stderr)
        return 1
    print("freeze guard: clean")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
