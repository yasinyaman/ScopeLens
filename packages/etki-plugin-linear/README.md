# etki-plugin-linear

Linear `WorkItemProvider` plugin for [Etki](https://github.com/yasinyaman/etki) — the
first-party reference plugin, extracted from the built-in adapter to dogfood the
`etki-api` contract. Depends **only** on `etki-api` + `httpx`.

Linear has no native time tracking: issues carry an `estimate` in POINTS. Effort is 0
unless the team opts into a conversion via `hours_per_point` (declared, not measured);
`find_similar` drops zero-effort issues so the engine degrades gracefully to code metrics.

```yaml
connectors:
  work_items:
    adapter: linear
    options:
      api_key: env:LINEAR_API_KEY
      hours_per_point: 4        # optional; omit to keep effort at 0
```
