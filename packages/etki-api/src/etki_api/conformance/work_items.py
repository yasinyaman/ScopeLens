"""WorkItemProvider contract.

Documented semantics under test:
- ``find_similar`` returns a LIST of ``WorkItem`` (possibly empty), never
  raises on a no-match or nonsense query, and returns at most ``limit`` items.
- Unicode/Turkish text must be accepted as-is.
- Every returned item is NORMALIZED: non-empty ``id``, ``effort_seconds`` is an
  ``int >= 0`` (the single source of truth for effort).
- ``capabilities()`` is sync, returns a ``Capabilities`` instance and is stable.
- ``get_work_item`` round-trips a known id (exercised when the subclass
  declares ``known_item_id``).
- A provider declaring ``supports_enumeration=True`` (0.1.3) must expose the
  optional ``all_items()`` returning a list of normalized ``WorkItem``;
  providers without the declaration are SKIPPED, not failed.
"""

from __future__ import annotations

from typing import Any

import pytest

from etki_api.conformance.base import NONSENSE_PROBE, TURKISH_PROBE, PortContract
from etki_api.models import WorkItem
from etki_api.ports import Capabilities


class WorkItemProviderContract(PortContract):
    similar_query = "raporlama ekranına CSV dışa aktarım eklensin"
    known_item_id: str | None = None

    @pytest.mark.asyncio
    async def test_find_similar_returns_normalized_items(self, provider: Any) -> None:
        items = await provider.find_similar(self.similar_query, limit=5)
        assert isinstance(items, list)
        assert len(items) <= 5
        for item in items:
            assert isinstance(item, WorkItem)
            assert item.id, "WorkItem.id boş olamaz"
            assert isinstance(item.effort_seconds, int)
            assert item.effort_seconds >= 0

    @pytest.mark.asyncio
    async def test_find_similar_respects_limit_one(self, provider: Any) -> None:
        items = await provider.find_similar(self.similar_query, limit=1)
        assert len(items) <= 1

    @pytest.mark.asyncio
    async def test_nonsense_query_returns_list_not_error(self, provider: Any) -> None:
        # No-match must degrade to a list (possibly empty or a recent-items
        # fallback) — never an exception.
        items = await provider.find_similar(NONSENSE_PROBE, limit=3)
        assert isinstance(items, list)
        assert len(items) <= 3

    @pytest.mark.asyncio
    async def test_turkish_unicode_accepted(self, provider: Any) -> None:
        items = await provider.find_similar(TURKISH_PROBE, limit=3)
        assert isinstance(items, list)

    def test_capabilities_declaration_is_stable(self, provider: Any) -> None:
        caps = provider.capabilities()
        assert isinstance(caps, Capabilities)
        assert provider.capabilities() == caps

    @pytest.mark.asyncio
    async def test_get_work_item_roundtrip(self, provider: Any) -> None:
        if self.known_item_id is None:
            pytest.skip("subclass declares no known_item_id")
        item = await provider.get_work_item(self.known_item_id)
        assert isinstance(item, WorkItem)
        assert item.id

    def test_declared_enumeration_exposes_all_items(self, provider: Any) -> None:
        # CONDITIONAL (0.1.3): the flag promises the optional method. Providers
        # without the declaration are skipped, never failed — pre-0.1.3
        # adapters (including ones that HAVE all_items but don't declare it)
        # stay green.
        if not provider.capabilities().supports_enumeration:
            pytest.skip("provider does not declare supports_enumeration")
        assert hasattr(provider, "all_items"), (
            "supports_enumeration=True promises an all_items() method"
        )
        items = provider.all_items()
        assert isinstance(items, list)
        for item in items:
            assert isinstance(item, WorkItem)
            assert item.id
            assert isinstance(item.effort_seconds, int) and item.effort_seconds >= 0
