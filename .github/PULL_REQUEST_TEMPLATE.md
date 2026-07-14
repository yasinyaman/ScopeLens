## What & why

<!-- What does this PR change, and what problem does it solve? Link the issue if any. -->

## Checklist

- [ ] `uv run pytest` passes
- [ ] `uv run ruff check .` and `uv run mypy etki` pass
- [ ] `uv run python -m eval.runner` passes — and this PR does **not** modify
      `eval/datasets/frozen/golden_crs.json` together with engine/matching logic
      (golden-set freeze rule, see CONTRIBUTING.md)
- [ ] New adapter? Registered in `adapters/registry.py`, no vendor references in core,
      tests use fakes / skip cleanly without a live server
- [ ] UI strings added through the i18n catalog (tr/en/de)
