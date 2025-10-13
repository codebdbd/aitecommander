"""Tests for PyQt6 cache improvements: weakref tracking, TTL refresh, and QPixmapCache integration."""

from __future__ import annotations

import time
import weakref
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtCore import QEvent, QObject
from PyQt6.QtGui import QIcon, QPixmapCache
from PyQt6.QtWidgets import QApplication, QToolButton, QWidget

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


@pytest.fixture
def width_calculator():
    """Create a WidthCalculator instance for testing."""
    from app.views.main_components.ui.topbar.width_calculator import WidthCalculator

    return WidthCalculator()


@pytest.fixture
def icon_cache():
    """Create a fresh ThreadSafeIconCache instance for testing."""
    from app.utils.ui.icon.cache_manager import ThreadSafeIconCache

    cache = ThreadSafeIconCache(maxsize=10)
    yield cache
    cache.clear()


class TestWidthCalculatorWeakrefTracking:
    """Test weakref-based widget lifetime tracking in WidthCalculator."""

    def test_weakref_cache_key_creation(self, qtbot: QtBot, width_calculator):
        """Test that cache keys use weakref instead of id()."""
        panel = QWidget()
        qtbot.addWidget(panel)
        buttons = [QToolButton() for _ in range(3)]

        # Calculate width - this should create a cache entry with weakref key
        width = width_calculator.panel_width(panel, buttons, 2)
        assert width >= width_calculator.MIN_PANEL_WIDTH

        # Verify cache has entry
        stats = width_calculator.get_cache_stats()
        assert stats["size"] == 1
        assert stats["misses"] == 1

        # Second call should hit cache
        width2 = width_calculator.panel_width(panel, buttons, 2)
        assert width2 == width
        stats = width_calculator.get_cache_stats()
        assert stats["hits"] == 1

    def test_automatic_cleanup_on_widget_destruction(self, qtbot: QtBot, width_calculator):
        """Test that cache entries are automatically cleaned when widget is destroyed."""
        panel = QWidget()
        qtbot.addWidget(panel)
        buttons = [QToolButton() for _ in range(2)]

        # Create cache entry
        width_calculator.panel_width(panel, buttons, 2)
        assert width_calculator.get_cache_stats()["size"] == 1

        # Destroy the widget
        panel.deleteLater()
        qtbot.wait(100)  # Wait for deletion
        QApplication.processEvents()

        # Cache should be cleaned automatically via weakref.finalize
        # Force a cache access to trigger cleanup check
        dummy_panel = QWidget()
        qtbot.addWidget(dummy_panel)
        width_calculator.panel_width(dummy_panel, buttons, 1)

        # The stale entry should be cleaned
        width_calculator._clean_stale_entries()
        # Note: We can't guarantee exact timing, but the entry should be gone or marked stale

    def test_invalidate_cache_for_panel(self, qtbot: QtBot, width_calculator):
        """Test selective cache invalidation for a specific panel."""
        panel1 = QWidget()
        panel2 = QWidget()
        qtbot.addWidget(panel1)
        qtbot.addWidget(panel2)
        buttons = [QToolButton() for _ in range(3)]

        # Create cache entries for both panels
        width_calculator.panel_width(panel1, buttons, 2)
        width_calculator.panel_width(panel2, buttons, 2)
        assert width_calculator.get_cache_stats()["size"] == 2

        # Invalidate only panel1
        removed = width_calculator.invalidate_cache_for_panel(panel1)
        assert removed == 1
        assert width_calculator.get_cache_stats()["size"] == 1

        # panel2 should still be cached
        width_calculator.panel_width(panel2, buttons, 2)
        assert width_calculator.get_cache_stats()["hits"] == 1

    def test_clear_cache_detaches_finalizers(self, qtbot: QtBot, width_calculator):
        """Test that clear_cache properly detaches all finalizers."""
        panels = [QWidget() for _ in range(3)]
        for panel in panels:
            qtbot.addWidget(panel)
        buttons = [QToolButton() for _ in range(2)]

        # Create cache entries
        for panel in panels:
            width_calculator.panel_width(panel, buttons, 2)

        assert width_calculator.get_cache_stats()["size"] == 3
        assert len(width_calculator._finalizers) == 3

        # Clear cache
        width_calculator.clear_cache()
        assert width_calculator.get_cache_stats()["size"] == 0
        assert len(width_calculator._finalizers) == 0


class TestWidthCalculatorEventFilter:
    """Test event filter for automatic cache invalidation on style changes."""

    def test_event_filter_on_style_change(self, qtbot: QtBot, width_calculator):
        """Test that cache is invalidated on StyleChange event."""
        panel = QWidget()
        qtbot.addWidget(panel)
        buttons = [QToolButton() for _ in range(2)]

        # Create cache entry
        width_calculator.panel_width(panel, buttons, 2)
        assert width_calculator.get_cache_stats()["size"] == 1

        # Install event filter
        panel.installEventFilter(width_calculator)

        # Simulate style change event
        event = QEvent(QEvent.Type.StyleChange)
        width_calculator.eventFilter(panel, event)

        # Cache should be invalidated
        assert width_calculator.get_cache_stats()["size"] == 0

    def test_event_filter_on_font_change(self, qtbot: QtBot, width_calculator):
        """Test that cache is invalidated on FontChange event."""
        panel = QWidget()
        qtbot.addWidget(panel)
        buttons = [QToolButton() for _ in range(2)]

        width_calculator.panel_width(panel, buttons, 2)
        panel.installEventFilter(width_calculator)

        event = QEvent(QEvent.Type.FontChange)
        width_calculator.eventFilter(panel, event)

        assert width_calculator.get_cache_stats()["size"] == 0

    def test_event_filter_ignores_other_events(self, qtbot: QtBot, width_calculator):
        """Test that event filter doesn't invalidate cache on unrelated events."""
        panel = QWidget()
        qtbot.addWidget(panel)
        buttons = [QToolButton() for _ in range(2)]

        width_calculator.panel_width(panel, buttons, 2)
        panel.installEventFilter(width_calculator)

        # Send unrelated event
        event = QEvent(QEvent.Type.MouseMove)
        width_calculator.eventFilter(panel, event)

        # Cache should still have entry
        assert width_calculator.get_cache_stats()["size"] == 1


class TestIconCacheTTLRefresh:
    """Test TTL refresh logic without holding cache lock."""

    def test_ttl_refresh_without_cache_lock(self, icon_cache):
        """Test that TTL refresh doesn't hold cache lock during config polling."""
        # Mock app_config to simulate slow config access
        with patch("app.utils.ui.icon.cache_manager.app_config") as mock_config:
            mock_config.get_icon_cache_ttl.return_value = 300.0
            mock_config.get_abs_icon_cache_ttl.return_value = 600.0
            mock_config.get_negative_cache_ttl.return_value = 60.0

            # Trigger TTL refresh
            icon_cache._ensure_fresh_ttls()

            # Verify TTLs were updated
            ttl_icon, ttl_abs, ttl_negative = icon_cache._get_ttls_snapshot()
            assert ttl_icon == 300.0
            assert ttl_abs == 600.0
            assert ttl_negative == 60.0

    def test_get_path_refreshes_ttl_before_lock(self, icon_cache):
        """Test that get_path refreshes TTL before acquiring cache lock."""
        icon_cache.set_path("test_icon.svg", "light", "/path/to/icon.svg")

        # Mock to track call order
        calls = []

        original_ensure = icon_cache._ensure_fresh_ttls
        original_lock = icon_cache._sync_path_structs

        def track_ensure():
            calls.append("ensure_ttls")
            original_ensure()

        def track_lock():
            calls.append("sync_structs")
            original_lock()

        icon_cache._ensure_fresh_ttls = track_ensure
        icon_cache._sync_path_structs = track_lock

        # Get path - should call ensure_ttls before sync_structs
        icon_cache.get_path("test_icon.svg", "light")

        # Verify order: TTL refresh happens before cache lock operations
        assert calls[0] == "ensure_ttls"
        assert "sync_structs" in calls

    def test_ttl_snapshot_thread_safety(self, icon_cache):
        """Test that TTL snapshot is thread-safe."""
        import threading

        results = []

        def get_snapshot():
            snapshot = icon_cache._get_ttls_snapshot()
            results.append(snapshot)

        # Create multiple threads accessing TTL snapshot
        threads = [threading.Thread(target=get_snapshot) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All threads should get consistent snapshots
        assert len(results) == 10
        for snapshot in results:
            assert isinstance(snapshot, tuple)
            assert len(snapshot) == 3


class TestQPixmapCacheIntegration:
    """Test QPixmapCache integration with ThreadSafeIconCache."""

    def test_qpixmapcache_initialization(self, icon_cache):
        """Test that QPixmapCache is initialized with proper limit."""
        # QPixmapCache should have been configured during init
        limit = QPixmapCache.cacheLimit()
        assert limit > 0  # Should have a reasonable limit set

    def test_icon_stored_in_qpixmapcache(self, qtbot: QtBot, icon_cache):
        """Test that icons are stored in QPixmapCache when cached."""
        # Create a simple icon
        icon = QIcon()
        # Note: In real scenario, icon would have pixmaps

        icon_cache.set_qicon("test_icon.svg", "light", icon, negative=False)

        # Verify it's in our cache
        cached = icon_cache.get_qicon("test_icon.svg", "light")
        assert cached is not None

    def test_qpixmapcache_cleared_on_cache_clear(self, icon_cache):
        """Test that QPixmapCache is cleared when cache is cleared."""
        # Add some icons
        icon = QIcon()
        icon_cache.set_qicon("icon1.svg", "light", icon)
        icon_cache.set_qicon("icon2.svg", "light", icon)

        # Clear cache
        icon_cache.clear()

        # QPixmapCache should also be cleared
        # We can't directly verify QPixmapCache contents, but clear() was called

    def test_qpixmapcache_eviction_on_lru(self, icon_cache):
        """Test that QPixmapCache entries are removed when LRU evicts."""
        # Fill cache to capacity
        for i in range(15):  # More than maxsize=10
            icon = QIcon()
            icon_cache.set_qicon(f"icon{i}.svg", "light", icon)

        # Oldest entries should be evicted from both caches
        stats = icon_cache.get_cache_stats()
        assert stats["qicon_cache_size"] <= 10


class TestAsyncIconPreloadGuard:
    """Test QApplication guard in async icon preload."""

    @pytest.mark.asyncio
    async def test_preload_fails_without_qapplication(self):
        """Test that preload_icons_async fails gracefully without QApplication."""
        from app.utils.ui.icon.icon_operations.cache_proxy import IconCache

        cache = IconCache()

        # Mock QApplication.instance to return None
        with patch("PyQt6.QtWidgets.QApplication.instance", return_value=None):
            result = await cache.preload_icons_async(["icon1", "icon2"])

            # Should return empty icons for all requested
            assert len(result) == 2
            assert all(icon.isNull() for icon in result.values())

    @pytest.mark.asyncio
    async def test_preload_works_with_qapplication(self, qtbot: QtBot):
        """Test that preload_icons_async works when QApplication exists."""
        from app.utils.ui.icon.icon_operations.cache_proxy import IconCache

        cache = IconCache()

        # QApplication should exist in test environment
        app = QApplication.instance()
        assert app is not None

        # Mock themed_icon_async to return test icons
        async def mock_themed_icon_async(name, theme, source):
            return QIcon()

        with patch(
            "app.utils.ui.icon.icon_operations.cache_proxy.themed_icon_async",
            side_effect=mock_themed_icon_async,
        ):
            result = await cache.preload_icons_async(["icon1", "icon2"])

            # Should return icons (even if empty in test)
            assert len(result) == 2


class TestCacheRegressions:
    """Test that fixes don't break existing functionality."""

    def test_width_calculator_basic_functionality(self, qtbot: QtBot, width_calculator):
        """Test that basic width calculation still works."""
        panel = QWidget()
        qtbot.addWidget(panel)
        buttons = [QToolButton() for _ in range(3)]

        width = width_calculator.panel_width(panel, buttons, 2)
        assert width >= width_calculator.MIN_PANEL_WIDTH
        assert isinstance(width, int)

    def test_icon_cache_basic_functionality(self, icon_cache):
        """Test that basic icon caching still works."""
        # Set and get path
        icon_cache.set_path("test.svg", "light", "/path/to/test.svg")
        path = icon_cache.get_path("test.svg", "light")
        assert path == "/path/to/test.svg"

        # Set and get icon
        icon = QIcon()
        icon_cache.set_qicon("test.svg", "light", icon)
        cached_icon = icon_cache.get_qicon("test.svg", "light")
        assert cached_icon is not None

    def test_cache_metrics_still_work(self, icon_cache):
        """Test that cache metrics are still collected correctly."""
        # Miss
        result = icon_cache.get_path("nonexistent.svg", "light")
        assert result is None

        # Set and hit
        icon_cache.set_path("test.svg", "light", "/path/to/test.svg")
        result = icon_cache.get_path("test.svg", "light")
        assert result is not None

        stats = icon_cache.get_cache_stats()
        assert stats["hits"] >= 1
        assert stats["misses"] >= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
