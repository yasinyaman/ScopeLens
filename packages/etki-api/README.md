# etki-api

The **stable plugin API** for [Etki](https://github.com/yasinyaman/etki): the external-integration
ports (`WorkItemProvider`, `CodeRepositoryProvider`, `DocumentSourceProvider`, `LLMClient`,
`EmbeddingProvider`, `RerankProvider`, `RegistryMetadataProvider`), the normalized models they
exchange (`WorkItem`, `CodeModule`, `DocumentRef`, …) and the plugin contract
(`PluginSpec`, `etki-plugin.toml` manifest).

Third-party plugins depend **only** on this package — never on `etki` itself.

```python
from etki_api import Capabilities, WorkItem, WorkItemProvider
```

- **Semver:** major = breaking, minor = new optional method/field. `0.x` until the first
  external plugin ships (breaking allowed, announced in `CHANGELOG.md`).
- **Internal ports** (persistence, wiki, graph query, HITL ingest) are deliberately NOT part
  of this API — they live in `etki.core` and may change freely.
- Plugin authoring guide: [`docs/writing-an-adapter.md`](https://github.com/yasinyaman/etki/blob/master/docs/writing-an-adapter.md)
