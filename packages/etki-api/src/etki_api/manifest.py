"""``etki-plugin.toml`` — the static twin of a ``PluginSpec``.

Readable WITHOUT importing or executing plugin code: the install confirmation
prompt and the marketplace index build read this file from a shallow clone or
an unpacked wheel. ``options_model`` is a dotted reference (a Pydantic class
cannot live in TOML); the loader resolves it only after the operator consented.

Example:

    [plugin]
    name = "etki-plugin-linear"
    type = "adapter"
    api_compat = ">=0.1,<0.2"

    [plugin.capabilities]
    network = true
    filesystem = "none"
    endpoints = ["api.linear.app"]

    [[plugin.adapters]]
    port = "work_items"
    name = "linear"
    options_model = "etki_plugin_linear:LinearOptions"
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from pydantic import BaseModel, Field

from etki_api.plugin import PortName, SecurityCapabilities

MANIFEST_FILENAME = "etki-plugin.toml"

PluginType = str  # "adapter" | "domain" | "report" | "mcp-tool" (reserved names)


class ManifestAdapter(BaseModel):
    """Static declaration of one provided adapter."""

    port: PortName
    name: str
    options_model: str = ""  # dotted ref "pkg.module:ClassName" — resolved post-consent


class PluginManifest(BaseModel):
    """Parsed ``etki-plugin.toml``. Field names/semantics mirror ``PluginSpec``."""

    name: str
    type: PluginType = "adapter"
    api_compat: str
    capabilities: SecurityCapabilities = Field(default_factory=SecurityCapabilities)
    adapters: list[ManifestAdapter] = Field(default_factory=list)


def load_manifest(path: str | Path) -> PluginManifest:
    """Parses an ``etki-plugin.toml`` (or a directory containing one).

    Raises ``FileNotFoundError`` when absent and ``pydantic.ValidationError`` /
    ``tomllib.TOMLDecodeError`` when malformed — callers decide how loudly to
    fail (the installer aborts; the loader marks the plugin ``failed``)."""
    p = Path(path)
    if p.is_dir():
        p = p / MANIFEST_FILENAME
    with p.open("rb") as fh:
        data = tomllib.load(fh)
    return PluginManifest.model_validate(data.get("plugin", {}))
