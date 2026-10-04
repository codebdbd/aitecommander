from __future__ import annotations

import threading
import time
from pathlib import Path
from unittest.mock import Mock

import pytest
from PyQt6.QtGui import QIcon, QPixmap, QPixmapCache
from PyQt6.QtWidgets import QApplication

from app.utils.ui.icon import cache_manager as cm
from app.utils.ui.icon import icon_resolver as resolver
from app.utils.ui.icon.loading_service import icon_loading_service
from app.utils.ui.icon.negative_cache import negative_cache
from app.utils.ui.icon.path_service import icon_path_service
from app.views.widgets.link import links_model


@pytest.fixture
def icons(monkeypatch):
    app = QApplication.instance() or QApplication([])
    cache = cm.ThreadSafeIconCache(maxsize=32)
    monkeypatch.setattr(cm._icon_manager, "_cache", cache)
    for name in ("_generic_resolved_cache", "_category_resolved_cache", "_existing_path_cache"):
        monkeypatch.setattr(icon_loading_service, name, {})
    monkeypatch.setattr(icon_path_service, "_theme_index", {})
    monkeypatch.setattr(icon_path_service, "_theme_index_ts", {})
    resolver._resolve_filesystem.cache_clear()
    links_model._get_icon_cached.cache_clear()
    negative_cache.clear()
    pixmap = QPixmap(8, 8)
    pixmap.fill()
    yield app, cache, pixmap, QIcon(pixmap)
    resolver._resolve_filesystem.cache_clear()
    links_model._get_icon_cached.cache_clear()
    negative_cache.clear()
    QPixmapCache.clear()


@pytest.mark.parametrize("namespace,theme", [("__abs__", "__abs__"), ("category", "__category__")])
def test_targeted_qicon_preserves_same_filename_elsewhere(icons, tmp_path, namespace, theme):
    _, cache, _, icon = icons
    target = tmp_path / "one" / "a.png"
    other = tmp_path / "two" / "a.png"
    target_key = f"{namespace}::{target}"
    other_key = f"{namespace}::{other}"
    cache.set_qicon(target_key, theme, icon)
    cache.set_qicon(other_key, theme, icon)
    cache.metrics.record_hit()
    hits = cache.metrics.hits
    cm.invalidate_icon(target.as_posix())
    assert cache.metrics.hits == hits
    assert cache.get_qicon(target_key, theme) is None
    assert cache.get_qicon(other_key, theme) is not None


def test_filename_is_not_compared_with_theme(icons, tmp_path):
    _, cache, _, icon = icons
    cache.set_qicon("unrelated", "light", icon)
    cm.invalidate_icon(tmp_path / "light.svg")
    assert cache.get_qicon("unrelated", "light") is not None


def test_loading_and_symbolic_caches_use_known_resolution(icons, tmp_path):
    _, cache, _, icon = icons
    target = str(tmp_path / "one" / "a.png")
    other = str(tmp_path / "two" / "a.png")
    for store in (icon_loading_service._generic_resolved_cache,
                  icon_loading_service._category_resolved_cache,
                  icon_loading_service._existing_path_cache):
        store[target] = target
        store[other] = other
        store["a.png"] = other
    cache.set_path("a", "light", other)
    cache.set_qicon("a", "light", icon)
    negative_cache.set("custom_theme:a.png", True)
    cm.invalidate_icon(target)
    for store in (icon_loading_service._generic_resolved_cache,
                  icon_loading_service._category_resolved_cache,
                  icon_loading_service._existing_path_cache):
        assert target not in store
        assert store[other] == other
        assert store["a.png"] == other
    assert cache.get_path("a", "light") == other
    assert cache.get_qicon("a", "light") is not None
    assert negative_cache.get("custom_theme:a.png") is None


@pytest.mark.parametrize("operation", ["clear", "remove"])
def test_first_background_call_reaches_qt_cache(icons, monkeypatch, tmp_path, operation):
    app, cache, pixmap, icon = icons
    monkeypatch.setattr(cm, "_pixmap_dispatcher", None)
    path = str(tmp_path / "worker.png")
    name = f"__abs__::{path}"
    cache.set_qicon(name, "__abs__", icon)
    key = f"icon:{cache._key(name, '__abs__')}"
    assert QPixmapCache.insert(key, pixmap)
    errors = []

    def work():
        try:
            cm.clear_icon_cache() if operation == "clear" else cm.invalidate_icon(path)
        except Exception as exc:
            errors.append(exc)

    worker = threading.Thread(target=work)
    worker.start()
    worker.join(timeout=2)
    assert not worker.is_alive()
    assert not errors
    deadline = time.monotonic() + 1
    while QPixmapCache.find(key) is not None and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.001)
    assert cm._pixmap_dispatcher.thread() == app.thread()
    assert QPixmapCache.find(key) is None


def test_resolver_and_table_keep_unrelated_lru_entries(icons, monkeypatch, tmp_path):
    _, _, pixmap, icon = icons
    target, other = tmp_path / "a.png", tmp_path / "b.png"
    assert pixmap.save(str(target))
    assert pixmap.save(str(other))
    creator = Mock(return_value=icon)
    monkeypatch.setattr(links_model, "create_icon_from_path", creator)
    for path in (str(target), str(other)):
        assert resolver._resolve_filesystem(path) == path
        links_model._get_icon_cached(path)
    fs_before = resolver._resolve_filesystem.cache_info()
    cm.invalidate_icon(target)
    assert resolver._resolve_filesystem(str(other)) == str(other)
    assert resolver._resolve_filesystem.cache_info().hits == fs_before.hits + 1
    links_model._get_icon_cached(str(other))
    assert creator.call_count == 2
    links_model._get_icon_cached(str(target))
    assert creator.call_count == 3
    resolver._resolve_filesystem(str(target))
    assert resolver._resolve_filesystem.cache_info().misses == fs_before.misses + 1


@pytest.mark.parametrize("previously_indexed", [True, False])
def test_theme_index_rebuilt_without_directory_mtime_change(icons, monkeypatch, tmp_path, previously_indexed):
    target = tmp_path / "a.svg"
    old = {"a.svg": target} if previously_indexed else {}
    icon_path_service._theme_index["light"] = old
    icon_path_service._theme_index_ts["light"] = time.time()
    monkeypatch.setattr(icon_path_service, "_get_theme_dir", lambda theme: tmp_path)
    monkeypatch.setattr(icon_path_service, "_theme_dir_mtime", {"light": tmp_path.stat().st_mtime})
    builder = Mock(return_value={"a.svg": target})
    monkeypatch.setattr(icon_path_service, "_build_theme_index", builder)
    cm.invalidate_icon(target)
    assert icon_path_service.get_indexed_icon("light", "a.svg") == target
    builder.assert_called_once_with("light")
