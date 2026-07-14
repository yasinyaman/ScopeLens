"""Login hardening: rate limiter (brute force) + open-redirect guard + viewer role."""

from etki.api.web import _safe_next
from etki.auth import LoginRateLimiter


class FakeClock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


def test_limiter_locks_after_max_failures() -> None:
    clock = FakeClock()
    lim = LoginRateLimiter(max_failures=5, window_s=900, lock_s=900, now=clock)
    key = "1.2.3.4|pmo"
    for _ in range(4):
        lim.register_failure(key)
    assert lim.retry_after(key) == 0  # still allowed at 4 failures
    lim.register_failure(key)  # 5th failure → lock
    assert lim.retry_after(key) > 0


def test_limiter_lock_expires_and_resets_window() -> None:
    clock = FakeClock()
    lim = LoginRateLimiter(max_failures=3, window_s=900, lock_s=900, now=clock)
    key = "k"
    for _ in range(3):
        lim.register_failure(key)
    assert lim.retry_after(key) > 0
    clock.t += 901  # lock expired
    assert lim.retry_after(key) == 0
    lim.register_failure(key)  # a single new failure must NOT re-lock
    assert lim.retry_after(key) == 0


def test_limiter_old_failures_fall_out_of_window() -> None:
    clock = FakeClock()
    lim = LoginRateLimiter(max_failures=3, window_s=100, lock_s=900, now=clock)
    key = "k"
    lim.register_failure(key)
    lim.register_failure(key)
    clock.t += 101  # both failures aged out
    lim.register_failure(key)
    assert lim.retry_after(key) == 0


def test_limiter_success_resets() -> None:
    clock = FakeClock()
    lim = LoginRateLimiter(max_failures=2, window_s=900, lock_s=900, now=clock)
    key = "k"
    lim.register_failure(key)
    lim.reset(key)
    lim.register_failure(key)
    assert lim.retry_after(key) == 0


def test_safe_next_allows_only_site_relative_paths() -> None:
    assert _safe_next("/projeler/demo") == "/projeler/demo"
    assert _safe_next("/") == "/"
    assert _safe_next("") == "/"
    assert _safe_next("https://evil.com") == "/"
    assert _safe_next("//evil.com") == "/"
    assert _safe_next("/\\evil.com") == "/"
    assert _safe_next("javascript://x") == "/"
    assert _safe_next("  /a  ") == "/a"


def test_engine_keeps_consumed_dict_by_reference() -> None:
    """The background pool refresh mutates the dict in place — the engine must see it."""
    from etki.adapters.fakes.code_repo import FakeCodeRepositoryProvider
    from etki.adapters.fakes.document import FakeDocumentSourceProvider
    from etki.adapters.fakes.seed import SEED_BASELINE
    from etki.adapters.fakes.work_item import FakeWorkItemProvider
    from etki.engine.triage import TriageEngine

    shared: dict[str, float] = {}
    engine = TriageEngine(
        FakeWorkItemProvider(),
        FakeCodeRepositoryProvider(),
        FakeDocumentSourceProvider(),
        SEED_BASELINE.model_copy(deep=True),
        consumed_by_category=shared,
    )
    shared["raporlama"] = 39.0
    assert engine._consumed["raporlama"] == 39.0  # same object, no copy


def test_refresh_pools_updates_in_place() -> None:
    from types import SimpleNamespace

    from etki.api.context import AppContext
    from etki.core.models import WorkItem

    provider = SimpleNamespace(
        all_items=lambda: [
            WorkItem(id="1", title="a", category="raporlama", effort_seconds=7200),
            WorkItem(id="2", title="b", category="raporlama", effort_seconds=3600),
        ]
    )
    consumed = {"raporlama": 1.0}
    ctx = AppContext(
        engines={},
        consumed={"demo": consumed},
        projects=[],
        repo=None,  # type: ignore[arg-type]
        approval=None,  # type: ignore[arg-type]
        default_project="demo",
        user_store=None,  # type: ignore[arg-type]
        work_item_providers={"demo": provider},
    )
    assert ctx.refresh_pools() == 1
    assert consumed == {"raporlama": 3.0}  # 3 hours, updated IN the same dict object
