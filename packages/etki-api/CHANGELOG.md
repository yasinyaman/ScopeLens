# etki-api Changelog

All notable changes to the plugin API. Semver: major = breaking, minor = new
optional method/field, patch = fixes. `0.x` until the first external plugin
ships — breaking changes are allowed but MUST be announced here.

## [0.1.3] - 2026-07-21

### Added
- `Capabilities.supports_enumeration: bool = False` — declares the optional
  `all_items() -> list[WorkItem]` cheap-enumeration method on a
  `WorkItemProvider` (feeds effort-pool consumption and KPI screens). Purely
  additive: the host keeps probing with `hasattr`, the flag documents intent;
  the method is deliberately NOT part of the runtime-checkable protocol.
- Conformance: `WorkItemProviderContract` gains a CONDITIONAL check — a
  provider declaring `supports_enumeration=True` must expose `all_items()`
  returning a list of `WorkItem`; providers without the declaration are
  SKIPPED, not failed (pre-0.1.3 adapters stay green).

## [0.1.2] - 2026-07-16

### Added
- **Request intake / response ports** — the first WRITING integration surface:
  - `RequestIntakeProvider.fetch_new(cursor, limit) -> IntakeBatch` — pulls new
    client requests from a tracker (poll transport; `supports_webhooks` reserves
    the push upgrade). The cursor is opaque to the host.
  - `ResponseChannel.post_response(OutboundResponse)` — writes a triage/decision
    outcome back (e.g. a tracker comment).
  - Normalized models `IncomingRequest`, `IntakeBatch`, `OutboundResponse`.
  - `SecurityCapabilities.external_write: bool = False` — declares that the
    plugin writes OUT of the boundary; shown at install time.
  - Conformance contracts `RequestIntakeProviderContract`,
    `ResponseChannelContract`.
  Additive within the 0.1 range (`>=0.1,<0.2` pins keep working; existing
  plugins never use the new `PortName` values).
- **`py.typed` marker** — the package now ships PEP 561 typing so downstream
  mypy resolves the real port/model types instead of treating them as `Any`.

### Design decisions (recorded)
- `ResponseChannel.post_response` RAISES on failure (a bool would drop the
  vendor error message that must go into the audit chain). The HOST is the only
  best-effort layer — it catches, records ok/error, and never blocks a PMO
  approval on a failed post.
- Host composes the response TEXT (already localized to the project language),
  the adapter only transports it — same rule as engine free text, so a comment
  is reproducible from the frozen audit detail. `OutboundResponse.extras`
  carries structured fields for richer renderers without a contract change.
- Posting is NOT idempotent (two calls = two comments). Dedup is the host's
  responsibility (deterministic case ids + an audit guard).

## [0.1.1] - 2026-07-16

### Added
- **Conformance suite** (`etki_api.conformance`, extra `etki-api[conformance]`):
  contract-test classes for all 7 ports (documented semantics — no-match → list,
  normalization, alignment, determinism, degrade-to-None) + a runner
  (`python -m etki_api.conformance <dist> --report out.json`) that binds a
  plugin's `PluginSpec.conformance()` offline providers and emits a JSON report
  with version-compat matrix fields. Port contracts themselves are UNCHANGED —
  additive within the 0.1 range (`>=0.1,<0.2` pins keep working).

### Changed
- Docstring vendor examples no longer reference GLPI (the builtin GLPI adapter
  was removed from the etki app). No API or contract change.

## [0.1.0] - 2026-07-15

First cut of the frozen plugin API, extracted from `etki.core` (the symbols are
identical objects — `etki.core.ports`/`etki.core.models` re-export them).

### Added
- External-integration ports: `WorkItemProvider`, `CodeRepositoryProvider`,
  `DocumentSourceProvider`, `LLMClient`, `EmbeddingProvider`, `RerankProvider`,
  `RegistryMetadataProvider` + the functional `Capabilities` declaration.
- Normalized models: `WorkItem`, `CodeModule` (+`Complexity`, `Churn`),
  `DocumentRef`, `PackageMetadata`.
- Plugin contract: `PluginSpec`, `AdapterFactory`, `SecurityCapabilities`,
  `PortName` (entry-point group `etki.adapters`).
- Manifest: `PluginManifest` + `load_manifest()` for `etki-plugin.toml` — the
  static twin of `PluginSpec`, readable without executing plugin code.

### Design decisions (recorded)
- `LLMClient` is deliberately single-method (`complete_json`) in 0.x. A
  tool-loop/streaming surface, if ever needed by plugins, will be an additive
  minor bump.
- Internal ports (`CaseFileRepository`, `WikiStore`, `IngestPort`,
  `GraphQueryPort`) are NOT part of this API — freezing them would lock the
  Etki domain model's evolution.
