"""In-memory CodeRepositoryProvider — serves the seed code knowledge graph."""

from __future__ import annotations

from etki.adapters.fakes.seed import SEED_MODULES
from etki.core.models import CodeModule
from etki.core.ports import Capabilities


class FakeCodeRepositoryProvider:
    def __init__(self, modules: list[CodeModule] | None = None) -> None:
        self._modules = list(modules) if modules is not None else list(SEED_MODULES)

    async def list_modules(self) -> list[CodeModule]:
        return list(self._modules)

    async def get_impacted(self, module_hint: str | None) -> list[CodeModule]:
        """Module(s) matching the hint + their 1st-degree dependency neighbors (shallow spread)."""
        if not module_hint:
            return []
        hint = module_hint.lower()
        by_id = {m.id: m for m in self._modules}
        seeds = [
            m
            for m in self._modules
            if hint in m.id.lower() or any(hint in r.lower() for r in m.responsibilities)
        ]
        impacted: dict[str, CodeModule] = {}
        for m in seeds:
            impacted[m.id] = m
            for dep in (*m.depends_on, *m.depended_by):
                if dep in by_id:
                    impacted[dep] = by_id[dep]
        return list(impacted.values())

    def capabilities(self) -> Capabilities:
        return Capabilities(
            supports_webhooks=True,
            supports_realtime=False,
            supports_effort_tracking=False,
            supports_incremental_diff=True,
        )
