"""Per-module churn from git history (commit count in the last 6 months).

An indicator of dependency uncertainty. If there is no git repo or the command
fails, silently returns empty (churn 0 — graceful degradation).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

_SHA_CHARS = set("0123456789abcdef")


def _git(root: Path, *args: str) -> str | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout if out.returncode == 0 else None


def _is_sha(line: str) -> bool:
    return len(line) == 40 and all(c in _SHA_CHARS for c in line)


def compute_churn(src_root: str | Path, since: str = "6 months ago") -> dict[str, int]:
    root = Path(src_root).resolve()
    prefix = _git(root, "rev-parse", "--show-prefix")
    if prefix is None:
        return {}  # not a git repository
    prefix = prefix.strip()
    log = _git(root, "log", f"--since={since}", "--name-only", "--pretty=format:%H", "--", ".")
    if log is None:
        return {}

    per_module: dict[str, set[str]] = {}
    commit = ""
    for raw in log.splitlines():
        line = raw.strip()
        if not line:
            continue
        if _is_sha(line):
            commit = line
            continue
        # line: repo-root-relative file path → drop the src_root prefix; first segment = module
        if prefix:
            if not line.startswith(prefix):
                continue
            line = line[len(prefix):]
        module = line.split("/", 1)[0]
        if module:
            per_module.setdefault(module, set()).add(commit)
    return {module: len(commits) for module, commits in per_module.items()}
