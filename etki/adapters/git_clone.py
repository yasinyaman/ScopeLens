"""Git repo clone helper — used when adding a repo from the UI.

Security: the user-supplied URL is validated (scheme allow-list; `file://`/local
path/internal network rejected → SSRF/local-file exfiltration prevented) and a `--`
separator is added to the command (argument-injection guard). To add a local path,
use the separate `src_root` field in the UI.
"""

from __future__ import annotations

import ipaddress
import re
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

_ALLOWED_SCHEMES = {"http", "https", "ssh", "git"}
# scp-like ssh shortcut: user@host:path (no scheme)
_SCP_LIKE = re.compile(r"^[^/@]+@[^/:]+:.+$")


class GitCloneError(RuntimeError):
    pass


def _is_internal_host(host: str) -> bool:
    host = host.lower().strip("[]")  # drop IPv6 square brackets
    if host in {"localhost", "ip6-localhost", ""}:
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False  # hostname → we don't resolve DNS (pilot); scheme+local-IP guard suffices
    return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved


def _validate_git_url(git_url: str) -> None:
    url = git_url.strip()
    if not url or url.startswith("-"):
        raise GitCloneError("geçersiz git URL (boş ya da '-' ile başlıyor)")
    if url.lower().startswith(("file:", "ext::")):
        raise GitCloneError("yerel/file:// veya ext:: URL'lerine izin verilmez")
    if _SCP_LIKE.match(url):  # git@host:path → ssh shortcut
        host = url.split("@", 1)[1].split(":", 1)[0]
        if _is_internal_host(host):
            raise GitCloneError("iç ağ/yerel host'a clone'a izin verilmez")
        return
    parts = urlsplit(url)
    if parts.scheme not in _ALLOWED_SCHEMES:
        raise GitCloneError(
            f"izin verilmeyen şema: {parts.scheme or '(yok)'} "
            f"(yalnızca {', '.join(sorted(_ALLOWED_SCHEMES))})"
        )
    if _is_internal_host(parts.hostname or ""):
        raise GitCloneError("iç ağ/yerel host'a clone'a izin verilmez")


def clone(git_url: str, target: str | Path) -> str:
    """Shallow clone via `git clone --depth 1`; if the target exists, uses it as-is.
    Returns the path."""
    _validate_git_url(git_url)
    path = Path(target)
    if path.exists() and any(path.iterdir()):
        return str(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            # '--' separator: git_url cannot be interpreted as a flag (argument-injection guard)
            ["git", "clone", "--depth", "1", "--", git_url, str(path)],
            capture_output=True,
            text=True,
            timeout=300,
            check=True,
        )
    except FileNotFoundError as exc:
        raise GitCloneError("git bulunamadı (PATH?)") from exc
    except subprocess.SubprocessError as exc:
        detail = getattr(exc, "stderr", "") or str(exc)
        raise GitCloneError(f"clone başarısız: {detail[-300:]}") from exc
    return str(path)
