"""Plugin discovery over the ``etki.adapters`` entry-point group (registry v2).

Deliberately lives under ``adapters/`` — never in ``engine/`` — so plugin PRs
can't collide with the answer-key freeze guard. Loading NEVER raises: a broken
plugin is marked ``failed``/``incompatible`` and logged loudly (no silent
drop), the app keeps serving. Built-in adapters are not listed here; the
builders in ``registry.py`` match them first, so a plugin can never shadow a
built-in name.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from functools import lru_cache
from importlib import metadata
from typing import Literal

from packaging.specifiers import SpecifierSet
from packaging.version import Version

from etki_api import AdapterFactory, PluginSpec
from etki_api import __version__ as _api_version

logger = logging.getLogger(__name__)

GROUP = "etki.adapters"

PluginState = Literal["active", "failed", "incompatible", "blocked", "disabled"]


@dataclass
class PluginStatus:
    """One discovered plugin distribution, as shown by `etki plugin list` and
    recorded in the KVKK inventory. `commit` is filled for git installs
    (PEP 610 direct_url.json) — it feeds the audit stamp."""

    name: str
    version: str = "?"
    source: str = "plugin"
    ports: list[str] = field(default_factory=list)
    api_compat: str = ""
    state: PluginState = "active"
    error: str | None = None
    commit: str | None = None

    @property
    def stamp(self) -> str:
        suffix = f"+g{self.commit[:7]}" if self.commit else ""
        return f"{self.name}@{self.version}{suffix}"


def _git_commit(dist: metadata.Distribution | None) -> str | None:
    """PEP 610: pip/uv record the resolved VCS commit for git installs."""
    if dist is None:
        return None
    try:
        raw = dist.read_text("direct_url.json")
        if not raw:
            return None
        return json.loads(raw).get("vcs_info", {}).get("commit_id")
    except Exception:  # noqa: BLE001 — stamp enrichment, never load-bearing
        return None


def _is_editable(dist: metadata.Distribution | None) -> bool:
    """PEP 610 dir_info.editable — a developer's own working tree, not an
    acquired distribution; exempt from the verified_only runtime block."""
    if dist is None:
        return False
    try:
        raw = dist.read_text("direct_url.json")
        if not raw:
            return False
        return bool(json.loads(raw).get("dir_info", {}).get("editable"))
    except Exception:  # noqa: BLE001
        return False


def _disabled_names() -> set[str]:
    from etki.plugin.state import load_disabled

    return load_disabled()


def _should_block(name: str, dist: metadata.Distribution | None) -> str | None:
    """verified_only runtime enforcement (defense-in-depth BEHIND the install
    CLI's gate): a non-editable distribution with no verified lockfile entry
    does not load. Returns the reason, or None to allow. Fabricated/test entry
    points (dist None) can't be attributed to a distribution — exempt, like
    editable working trees."""
    from etki.plugin.lockfile import load_lockfile
    from etki.plugin.policy import current_policy

    if dist is None or _is_editable(dist):
        return None
    if current_policy() != "verified_only":
        return None
    try:
        entry = load_lockfile().get(name)
    except Exception:  # noqa: BLE001 — a corrupt lockfile must fail CLOSED
        entry = None
    if entry is not None and entry.verified:
        return None
    return (
        "ETKI_PLUGIN_POLICY=verified_only: bu dağıtımın lockfile'da doğrulanmış "
        "(verified) kaydı yok — yüklenmedi. Kurulumlar `python -m etki.plugin install` "
        "üzerinden yapılmalı ya da policy gevşetilmeli."
    )


class PluginRegistry:
    """Loads every ``etki.adapters`` entry point once per process. Failures are
    isolated per entry point; duplicates (same port+adapter name) keep the
    first and warn."""

    def __init__(self) -> None:
        self._factories: dict[tuple[str, str], AdapterFactory] = {}
        self._statuses: list[PluginStatus] = []
        # Loaded specs by plugin name — feeds the detail page (capabilities +
        # adapter list). Kept for EVERY parsed spec incl. disabled/blocked ones:
        # ep.load() already imported the module, holding the object adds nothing.
        self._specs: dict[str, PluginSpec] = {}

    def load(self) -> None:
        for ep in metadata.entry_points(group=GROUP):
            status = PluginStatus(name=ep.name)
            self._statuses.append(status)
            try:
                spec = ep.load()
            except Exception as exc:  # noqa: BLE001 — a broken plugin must not kill the app
                status.state = "failed"
                status.error = f"{type(exc).__name__}: {exc}"
                logger.exception("plugin %r yüklenemedi (entry point import hatası)", ep.name)
                continue
            if not isinstance(spec, PluginSpec):
                status.state = "failed"
                status.error = f"entry point PluginSpec değil: {type(spec).__name__}"
                logger.error("plugin %r reddedildi: %s", ep.name, status.error)
                continue
            status.name = spec.name
            status.api_compat = spec.api_compat
            status.ports = [f.port for f in spec.adapters]
            self._specs[spec.name] = spec
            dist = ep.dist
            status.version = dist.version if dist is not None else "?"
            status.commit = _git_commit(dist)
            if spec.name in _disabled_names():
                status.state = "disabled"
                status.error = "kullanıcı tarafından devre dışı bırakıldı (Ayarlar → Eklentiler)"
                logger.info("plugin %r devre dışı (kullanıcı)", spec.name)
                continue
            block_reason = _should_block(spec.name, dist)
            if block_reason is not None:
                status.state = "blocked"
                status.error = block_reason
                logger.error("plugin %r engellendi: %s", spec.name, block_reason)
                continue
            try:
                compatible = SpecifierSet(spec.api_compat).contains(
                    Version(_api_version), prereleases=True
                )
            except Exception as exc:  # noqa: BLE001 — malformed specifier = plugin bug
                status.state = "failed"
                status.error = f"api_compat çözümlenemedi: {exc}"
                logger.error("plugin %r reddedildi: %s", spec.name, status.error)
                continue
            if not compatible:
                status.state = "incompatible"
                status.error = (
                    f"etki-api {_api_version} kurulu, plugin {spec.api_compat!r} istiyor"
                )
                logger.error("plugin %r uyumsuz: %s", spec.name, status.error)
                continue
            for factory in spec.adapters:
                key = (factory.port, factory.name)
                if key in self._factories:
                    logger.warning(
                        "plugin %r: %s/%s adaptörü zaten kayıtlı — ilk kazanır, bu atlandı",
                        spec.name,
                        factory.port,
                        factory.name,
                    )
                    continue
                self._factories[key] = factory
            logger.info(
                "plugin yüklendi: %s %s (%s)",
                status.name,
                status.version,
                ", ".join(status.ports),
            )

    def find(self, port: str, name: str) -> AdapterFactory | None:
        return self._factories.get((port, name))

    def spec(self, name: str) -> PluginSpec | None:
        """The parsed PluginSpec for a plugin name (any state), or None."""
        return self._specs.get(name)

    def status(self, name: str) -> PluginStatus | None:
        return next((s for s in self._statuses if s.name == name), None)

    def names(self, port: str) -> list[str]:
        """Adapter names a given port can resolve via plugins (error messages, docs)."""
        return sorted(n for (p, n) in self._factories if p == port)

    def statuses(self) -> list[PluginStatus]:
        return list(self._statuses)

    def stamp(self) -> list[str]:
        """Sorted ``name@version[+gsha7]`` of ACTIVE plugins — the audit-chain
        stamp next to model_version (empty list when no plugins installed)."""
        return sorted(s.stamp for s in self._statuses if s.state == "active")


@lru_cache
def get_plugin_registry() -> PluginRegistry:
    registry = PluginRegistry()
    registry.load()
    return registry
