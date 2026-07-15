"""etki-plugin.toml parsing: valid manifest, directory form, malformed input."""

import pytest
from pydantic import ValidationError

from etki_api import PluginManifest, SecurityCapabilities, load_manifest

_VALID = """\
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


def test_valid_manifest_parses(tmp_path):
    path = tmp_path / "etki-plugin.toml"
    path.write_text(_VALID, encoding="utf-8")
    manifest = load_manifest(path)
    assert manifest.name == "etki-plugin-linear"
    assert manifest.api_compat == ">=0.1,<0.2"
    assert manifest.capabilities.network is True
    assert manifest.capabilities.endpoints == ["api.linear.app"]
    assert manifest.adapters[0].port == "work_items"
    assert manifest.adapters[0].options_model == "etki_plugin_linear:LinearOptions"


def test_directory_form_finds_the_manifest(tmp_path):
    (tmp_path / "etki-plugin.toml").write_text(_VALID, encoding="utf-8")
    assert load_manifest(tmp_path).name == "etki-plugin-linear"


def test_capability_defaults_are_least_privilege():
    caps = SecurityCapabilities()
    assert caps.network is False
    assert caps.filesystem == "none"
    assert caps.endpoints == []


def test_missing_required_fields_fail():
    with pytest.raises(ValidationError):
        PluginManifest.model_validate({"name": "x"})  # api_compat missing


def test_unknown_port_rejected(tmp_path):
    bad = _VALID.replace('port = "work_items"', 'port = "root_shell"')
    path = tmp_path / "etki-plugin.toml"
    path.write_text(bad, encoding="utf-8")
    with pytest.raises(ValidationError):
        load_manifest(path)


def test_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_manifest(tmp_path / "yok.toml")
