# etki-api Changelog

All notable changes to the plugin API. Semver: major = breaking, minor = new
optional method/field, patch = fixes. `0.x` until the first external plugin
ships — breaking changes are allowed but MUST be announced here.

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
