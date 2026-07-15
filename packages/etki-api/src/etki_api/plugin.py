"""The plugin contract: what an ``etki.adapters`` entry point resolves to.

A plugin distribution declares one entry point in the ``etki.adapters`` group
pointing at a module-level ``PluginSpec`` instance:

    [project.entry-points."etki.adapters"]
    linear = "etki_plugin_linear:PLUGIN"

The loader (etki side) validates ``api_compat`` against the installed etki-api
version BEFORE any adapter is built; options are validated through
``AdapterFactory.options_model`` and secrets (``env:VAR`` references) are
resolved by the host BEFORE ``build()`` is called — a plugin never sees raw
secret references.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel

PortName = Literal[
    "work_items",
    "code_repo",
    "documents",
    "llm",
    "embedding",
    "rerank",
    "registry_metadata",
]


class SecurityCapabilities(BaseModel):
    """SECURITY capability declaration (KVKK/compliance inventory) — what the
    plugin's code may do, shown to the operator at install time. Separate from
    the functional ``Capabilities`` model on the ports (webhooks/diff support).
    Declared here AND in ``etki-plugin.toml``; enforcement is a later phase,
    the declaration is collected from day one."""

    network: bool = False
    filesystem: Literal["none", "read", "write"] = "none"
    endpoints: list[str] = []  # declared outbound hosts (documentation; sandbox seam)
    notes: str = ""


@dataclass(frozen=True)
class AdapterFactory:
    """One adapter a plugin provides: the config ``adapter:`` name, the options
    schema, and the factory. ``build`` receives a VALIDATED options model with
    secrets already resolved."""

    port: PortName
    name: str  # the config `adapter:` string, e.g. "linear"
    options_model: type[BaseModel]
    build: Callable[[BaseModel], object]


@dataclass(frozen=True)
class PluginSpec:
    """The runtime source of truth for a plugin. ``etki-plugin.toml`` is its
    static twin (readable without importing plugin code); ``etki plugin verify``
    cross-checks the two and fails on drift."""

    name: str  # distribution name, e.g. "etki-plugin-linear"
    api_compat: str  # PEP 440 specifier against etki-api, e.g. ">=0.1,<0.2"
    capabilities: SecurityCapabilities = field(default_factory=SecurityCapabilities)
    adapters: tuple[AdapterFactory, ...] = ()
    # Conformance factory (Faz 4): returns OFFLINE provider instances (canned
    # data / mock transports) keyed by port, so `etki plugin verify` runs
    # credential-free in any CI.
    conformance: Callable[[], dict[PortName, object]] | None = None
