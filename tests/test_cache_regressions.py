from __future__ import annotations

import importlib
import logging
import threading
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from filelock import Timeout
from PyQt6.QtCore import QObject

from app.controllers.business.links_business import LinksBusinessLogic
from app.controllers.business.structure_business import StructureBusinessLogic
from app.controllers.ui.links.table_controller import LinksTableController
from app.utils.links.parser.favicon_cache import FaviconCache
from app.utils.ui.icon.negative_cache import NegativeCache
from tests.test_structure_business_cache_preserve import _CacheManagerStub


@pytest.fixture
def structure(monkeypatch):
    business = StructureBusinessLogic.__new__(StructureBusinessLogic)
    QObject.__init__(business)
    business.logger = logging.getLogger("cache_regressions")
    business.db = SimpleNamespace()
    business.cache_manager = _CacheManagerStub()
    business._structure_mutation_generation = 0
    business._structure_preload_generation = 0
    business._structure_cache_ready = False
    business._structure_dirty_since_preload = False
    business._cached_spheres = []
    business._cached_sections = {}
    business._cached_categories = {}
    business._structure_preload_in_progress = False
    business._structure_preload_pending = False
    business._structure_preload_active_token = None
    business._first_structure_loaded_completed = True
    business._last_switch_started_ms = None
    business._structure_preload_suspended_until_monotonic = 0.0
    business._structure_preload_cooldown_until_monotonic = 0.0
    business._structure_preload_interactive_until_monotonic = 0.0
    business._structure_preload_last_finished_monotonic = 0.0
    business._schedule_preload_structure_async = Mock()
    jobs = []
    monkeypatch.setattr(
        "app.controllers.business.structure_business.run_db",
        lambda task, **kwargs: jobs.append(kwargs),
    )
    return business, jobs


def test_structure_accepts_fresh_snapshot_after_mutation(structure):
    business, jobs = structure
    business._handle_structure_mutation("category", 1)
    business.preload_structure_async()
    payload = ([{"id": 1, "name": "fresh"}], {}, {})
    jobs[-1]["on_finished"](payload)
    assert business.get_cached_spheres() == payload[0]
    assert not business._structure_dirty_since_preload
    assert not business._structure_preload_in_progress
    assert business.cache_manager.get("all_spheres") == payload[0]
    assert business._schedule_preload_structure_async.call_count == 1


def test_structure_retries_snapshot_invalidated_during_load(structure):
    business, jobs = structure
    business.preload_structure_async()
    business._handle_structure_mutation("category", 1)
    jobs[0]["on_finished"](([{"id": 1, "name": "old"}], {}, {}))
    assert not business._structure_cache_ready
    assert not business._structure_preload_in_progress
    assert business._structure_dirty_since_preload
    business._schedule_preload_structure_async.assert_called_with(
        reason="dirty-after-stale-preload", delay_ms=300
    )
    business.preload_structure_async()
    jobs[-1]["on_finished"](([{"id": 1, "name": "new"}], {}, {}))
    assert business.get_cached_spheres() == [{"id": 1, "name": "new"}]
    assert not business._structure_dirty_since_preload


def test_old_structure_callback_does_not_cancel_active_load(structure):
    business, jobs = structure
    business.preload_structure_async()
    token = business._structure_preload_active_token
    business._on_structure_snapshot_ready(([], {}, {}), token - 1)
    business._on_structure_snapshot_error(RuntimeError("old"), token - 1)
    assert business._structure_preload_active_token == token
    assert business._structure_preload_in_progress
    jobs[0]["on_finished"](([{"id": 1}], {}, {}))
    assert business._structure_cache_ready


def test_structure_error_after_mutation_releases_load(structure):
    business, jobs = structure
    business.preload_structure_async()
    business._handle_structure_mutation("category", 1)
    business._structure_preload_pending = True
    jobs[0]["on_error"](RuntimeError("query failed"))
    assert not business._structure_preload_in_progress
    business._schedule_preload_structure_async.assert_called_with(
        reason="pending-after-error", delay_ms=250
    )


@pytest.fixture
def links():
    business = LinksBusinessLogic(
        SimpleNamespace(),
        scheduler=SimpleNamespace(),
        links_service=SimpleNamespace(),
        tasks_lock_instance=threading.RLock(),
    )
    jobs = []
    business._run_db_task = lambda task, **kwargs: jobs.append(kwargs)
    return business, jobs


def test_cache_invalidation_does_not_block_table_queue(links):
    business, jobs = links
    table = SimpleNamespace(update_link_by_id=Mock(), populate=Mock())
    category = SimpleNamespace(current_category_id=1)
    controller = LinksTableController(
        SimpleNamespace(), table=table, links_business=business,
        category_provider=category,
    )
    controller._trigger_background_icon_enrichment = Mock()
    business.links_loaded.connect(controller.on_links_loaded)
    controller.reload(1)
    business._on_last_used_updated(99)
    category.current_category_id = 2
    controller.reload(2)
    jobs[0]["on_finished"]([{"id": 1}])
    assert len(jobs) == 2
    jobs[1]["on_finished"]([{"id": 2}])
    assert not controller._reloading
    table.populate.assert_called_once_with([{"id": 2}])


@pytest.mark.parametrize(
    "method,args,signal,key,payload",
    [
        ("load_recent_links", (), "recent_links_loaded", "recent_links_10", [{"id": 1}]),
        ("load_favorite_links", (), "favorite_links_loaded", "favorite_links", [{"id": 1}]),
        ("load_link_by_id", (1,), "link_by_id_loaded", "link_1", {"id": 1}),
        ("load_next_position", (1,), "next_position_loaded", "next_pos_1", 3),
    ],
)
def test_stale_cache_results_are_rejected(links, method, args, signal, key, payload):
    business, jobs = links
    received = []
    getattr(business, signal).connect(lambda *data: received.append(data))
    getattr(business, method)(*args)
    business.invalidate_cache()
    jobs[0]["on_finished"](payload)
    assert not received
    assert key not in business._cache
    getattr(business, method)(*args)
    jobs[1]["on_finished"](payload)
    assert len(received) == 1
    assert business._cache[key] == payload


def test_database_switch_rejects_old_table_and_cache_results(links):
    business, jobs = links
    table_results, recent_results = [], []
    business.links_loaded.connect(lambda *data: table_results.append(data))
    business.recent_links_loaded.connect(recent_results.append)
    business.load_links(1)
    business.load_recent_links()
    business.reset_state_for_database_switch()
    jobs[0]["on_finished"]([{"id": 1}])
    jobs[1]["on_finished"]([{"id": 1}])
    assert not table_results
    assert not recent_results
    assert not business._cache


@pytest.mark.parametrize("backend", ["auto", "filelock"])
@pytest.mark.parametrize("persistent", [False, True])
def test_favicon_timeout_skips_all_disk_access(monkeypatch, backend, persistent):
    module = importlib.import_module("app.utils.links.parser.favicon_cache")
    monkeypatch.setattr(module, "_get_lock_backend", lambda: backend)
    monkeypatch.setattr(module, "_should_try_backend", lambda selected, name: name == "filelock")
    monkeypatch.setattr("filelock.FileLock.acquire", Mock(side_effect=Timeout("test.lock")))
    open_db = Mock(side_effect=AssertionError("disk access after timeout"))
    monkeypatch.setattr(module, "_open_shelve_with_recovery", open_db)
    cache = FaviconCache()
    cache._persistent_enabled = persistent
    cache._get_db_path = lambda: "unused-cache"
    clear_db = Mock(side_effect=AssertionError("clear after timeout"))
    cache._clear_all_cache = clear_db
    assert cache.get("key") is None
    cache.set("key", {"title": "new"})
    cache.invalidate("key")
    cache.invalidate()
    open_db.assert_not_called()
    clear_db.assert_not_called()


@pytest.fixture
def negative_clock(monkeypatch):
    module = importlib.import_module("app.utils.ui.icon.negative_cache")
    clock = SimpleNamespace(now=100.0)
    monkeypatch.setattr(
        module,
        "time",
        SimpleNamespace(monotonic=lambda: clock.now, time=lambda: clock.now),
    )
    monkeypatch.setattr(module, "_base_ttl", lambda: 10.0)
    monkeypatch.setattr(module, "_max_size", lambda: 8)
    return clock


@pytest.mark.parametrize("removal", ["invalidate", "evict"])
def test_negative_old_event_does_not_expire_new_mark(negative_clock, removal):
    cache = NegativeCache()
    cache.set("A", True)
    negative_clock.now = 105.0
    if removal == "invalidate":
        cache.invalidate("A")
    else:
        for index in range(8):
            cache.set(str(index), True)
        assert cache.get("A") is None
    cache.set("A", True)
    negative_clock.now = 111.0
    cache.set("B", True)
    assert cache.get("A") is True
    negative_clock.now = 116.0
    assert cache.get("A") is None


@pytest.mark.parametrize("expire_on_read", [False, True])
def test_negative_expired_metadata_is_bounded(negative_clock, expire_on_read):
    cache = NegativeCache()
    for index in range(100):
        cache.set(str(index), True)
        cache.set(str(index), True)  # Retain soft-decayed strike history, too.
        negative_clock.now += 21.0
        if expire_on_read:
            assert cache.get(str(index)) is None
    assert len(cache._ts) <= 1
    assert len(cache._gen) <= 1
    assert len(cache._strikes) <= 8
    assert len(cache._expire_heap) <= 16
    assert len(cache._ts_heap) <= 16


def test_negative_repeated_updates_keep_heaps_bounded(negative_clock):
    cache = NegativeCache()
    for _ in range(100):
        cache.set("same", True)
    assert cache.get("same") is True
    assert len(cache._expire_heap) <= 16
    assert len(cache._ts_heap) <= 16


def test_negative_expiry_preserves_soft_strike_decay(negative_clock):
    cache = NegativeCache()
    cache.set("A", True)
    cache.set("A", True)
    negative_clock.now = 121.0
    assert cache.get("A") is None
    cache.set("A", True)
    negative_clock.now = 136.0
    assert cache.get("A") is True
    negative_clock.now = 142.0
    assert cache.get("A") is None


def test_large_links_fresh_emits_and_stale_dropped(links):
    business, jobs = links
    received = []
    business.recent_links_loaded.connect(received.append)

    large_payload = [{"id": i, "name": f"link_{i}"} for i in range(2049)]

    # 1. Fresh large payload emits without caching
    business.load_recent_links(2049)
    jobs[0]["on_finished"](large_payload)
    assert len(received) == 1
    assert len(received[0]) == 2049
    assert "recent_links_2049" not in business._cache

    # 2. Stale large payload is dropped
    received.clear()
    business.load_recent_links(2049)
    business.invalidate_cache()
    jobs[1]["on_finished"](large_payload)
    assert len(received) == 0
    assert "recent_links_2049" not in business._cache


def test_icon_cache_universal_set_expires_by_ttl():
    import time
    from app.utils.ui.icon.cache_manager import ThreadSafeIconCache

    cache = ThreadSafeIconCache(maxsize=10)
    cache.set("path:expiring::light", "/path/to/icon.png", ttl=0.05)
    assert cache.get("path:expiring::light") == "/path/to/icon.png"

    time.sleep(0.08)
    assert cache.get("path:expiring::light") is None


def test_background_invalidation_dispatches_to_main_thread():
    import threading
    from PyQt6.QtWidgets import QApplication
    from app.utils.ui.icon.cache_manager import invalidate_icon, _icon_manager

    _ = QApplication.instance() or QApplication([])

    _icon_manager._cache.set("path:bg_test::light", "/path/to/bg_test.png")

    worker_thread_err = []

    def run_invalidate():
        try:
            invalidate_icon("/path/to/bg_test.png")
        except Exception as e:
            worker_thread_err.append(e)

    t = threading.Thread(target=run_invalidate)
    t.start()
    t.join()

    assert not worker_thread_err
    assert _icon_manager._cache.get("path:bg_test::light") is None


def test_previously_missing_icon_available_immediately_after_save():
    from app.utils.ui.icon.cache_manager import invalidate_icon
    from app.utils.ui.icon.negative_cache import negative_cache

    negative_cache.set("light:fresh_saved.svg", True)
    assert negative_cache.is_negative("light:fresh_saved.svg") is True

    invalidate_icon("fresh_saved.svg")
    assert negative_cache.is_negative("light:fresh_saved.svg") is not True


def test_update_single_icon_preserves_other_icons_and_metrics():
    from app.utils.ui.icon.cache_manager import invalidate_icon, _icon_manager

    cache = _icon_manager._cache
    cache.metrics.reset()
    cache.set("path:icon_a::light", "/path/to/icon_a.png")
    cache.set("path:icon_b::light", "/path/to/icon_b.png")

    cache.metrics.record_hit()
    hits_before = cache.metrics.hits

    invalidate_icon("/path/to/icon_a.png")

    assert cache.get("path:icon_a::light") is None
    assert cache.get("path:icon_b::light") == "/path/to/icon_b.png"
    assert cache.metrics.hits >= hits_before


def test_profile_cache_exit_error_triggers_automatic_retry(tmp_path):
    import time
    from unittest.mock import Mock
    from app.utils.browser.browser_profiles.persistent_cache import PersistentProfileCache

    cache = PersistentProfileCache()
    cache._path = tmp_path / "profiles.json"
    cache._flush_delay_sec = 0.1

    fail_mock = Mock(side_effect=OSError("Disk full"))
    cache._dump_to_disk = fail_mock

    with cache:
        cache.set("prof1", {"name": "Default"})

    assert cache._dirty is True
    assert cache._flush_timer is not None

    if cache._flush_timer:
        cache._flush_timer.cancel()
        cache._flush_timer = None
