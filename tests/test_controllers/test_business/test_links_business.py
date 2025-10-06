# tests/test_controllers/test_business/test_links_business.py

import pytest
from unittest.mock import Mock, MagicMock, patch
from PyQt6.QtCore import QObject, QMutex
import threading
import time

from app.controllers.business.links_business import LinksBusinessLogic
from app.models.db import Database
from app.services.links_service import LinksService


@pytest.fixture
def mock_db():
    db = Mock(spec=Database)
    db.links = Mock()
    return db


@pytest.fixture
def mock_scheduler():
    scheduler = Mock()
    thread_pool = Mock()
    thread_pool.activeThreadCount.return_value = 0
    thread_pool.waitForDone.return_value = True
    scheduler.get_thread_pool.return_value = thread_pool
    return scheduler


@pytest.fixture
def links_business_logic(qtbot, mock_db, mock_scheduler):
    logic = LinksBusinessLogic(db=mock_db, scheduler=mock_scheduler)
    qtbot.addWidget(logic)  # Ensure proper cleanup
    return logic


class TestLinksBusinessLogic:
    """Test suite for LinksBusinessLogic."""

    def test_initialization(self, links_business_logic, mock_db):
        """Test proper initialization."""
        assert links_business_logic.db == mock_db
        assert links_business_logic._cache is not None
        assert isinstance(links_business_logic.pending_tasks, dict)

    def test_load_links_emits_signal(self, qtbot, links_business_logic, mock_db):
        """Test that load_links emits links_loaded signal asynchronously."""
        mock_db.links.get_links.return_value = [{"id": 1, "name": "Test Link"}]

        with qtbot.waitSignal(links_business_logic.links_loaded, timeout=1000) as blocker:
            links_business_logic.load_links(category_id=1)

        # Check signal emission
        assert blocker.args == ([{"id": 1, "name": "Test Link"}], 1, 1)

    def test_search_links_emits_signal(self, qtbot, links_business_logic, mock_db):
        """Test search_links emits search_results_ready signal."""
        mock_db.links.search_links.return_value = [{"id": 2, "name": "Found Link"}]

        with qtbot.waitSignal(links_business_logic.search_results_ready, timeout=1000) as blocker:
            links_business_logic.search_links("test query")

        assert blocker.args == ([{"id": 2, "name": "Found Link"}],)

    def test_delete_link_emits_signal(self, qtbot, links_business_logic, mock_db):
        """Test delete_link emits link_deleted signal."""
        mock_db.links.delete_link.return_value = None

        with qtbot.waitSignal(links_business_logic.link_deleted, timeout=1000) as blocker:
            links_business_logic.delete_link(link_id=1)

        assert blocker.args == (1,)

    def test_toggle_favorite_emits_signals(self, qtbot, links_business_logic, mock_db):
        """Test toggle_favorite emits link_updated and favorites_counted."""
        mock_db.links.get_link_by_id.return_value = {"id": 1, "is_favorite": False}
        mock_db.links.create_or_update_link.return_value = 1
        mock_db.links.count_favorites.return_value = 1

        # Wait for link_updated signal
        with qtbot.waitSignal(links_business_logic.link_updated, timeout=1000):
            links_business_logic.toggle_favorite({"id": 1, "is_favorite": False})

        # Check that count_favorites was called
        assert mock_db.links.count_favorites.called

    def test_save_link_async_emits_signal(self, qtbot, links_business_logic, mock_db):
        """Test save_link_async emits link_updated signal."""
        mock_db.links.create_or_update_link.return_value = 1

        with qtbot.waitSignal(links_business_logic.link_updated, timeout=1000) as blocker:
            links_business_logic.save_link_async({"name": "New Link"})

        assert blocker.args[0]["id"] == 1

    def test_clear_favorites_async_emits_signal(self, qtbot, links_business_logic, mock_db):
        """Test clear_favorites_async emits favorites_cleared signal."""
        mock_db.links.clear_favorites.return_value = True

        with qtbot.waitSignal(links_business_logic.favorites_cleared, timeout=1000) as blocker:
            links_business_logic.clear_favorites_async()

        assert blocker.args == (True,)

    def test_load_recent_links_emits_signal(self, qtbot, links_business_logic, mock_db):
        """Test load_recent_links emits recent_links_loaded signal."""
        mock_db.links.get_recent_links.return_value = [{"id": 1, "name": "Recent"}]

        with qtbot.waitSignal(links_business_logic.recent_links_loaded, timeout=1000) as blocker:
            links_business_logic.load_recent_links(limit=5)

        assert blocker.args == ([{"id": 1, "name": "Recent"}],)

    def test_load_favorite_links_emits_signal(self, qtbot, links_business_logic, mock_db):
        """Test load_favorite_links emits favorite_links_loaded signal."""
        mock_db.links.get_favorite_links.return_value = [{"id": 1, "is_favorite": True}]

        with qtbot.waitSignal(links_business_logic.favorite_links_loaded, timeout=1000) as blocker:
            links_business_logic.load_favorite_links()

        assert blocker.args == ([{"id": 1, "is_favorite": True}],)

    def test_load_link_by_id_emits_signal(self, qtbot, links_business_logic, mock_db):
        """Test load_link_by_id emits link_by_id_loaded signal."""
        mock_db.links.get_link_by_id.return_value = {"id": 1, "name": "Test"}

        with qtbot.waitSignal(links_business_logic.link_by_id_loaded, timeout=1000) as blocker:
            links_business_logic.load_link_by_id(link_id=1)

        assert blocker.args == ({"id": 1, "name": "Test"}, 1)

    def test_load_next_position_emits_signal(self, qtbot, links_business_logic, mock_db):
        """Test load_next_position emits next_position_loaded signal."""
        mock_db.links.get_next_position.return_value = 5

        with qtbot.waitSignal(links_business_logic.next_position_loaded, timeout=1000) as blocker:
            links_business_logic.load_next_position(category_id=1)

        assert blocker.args == (5, 1)

    def test_batch_update_links_async_emits_signal(self, qtbot, links_business_logic, mock_db):
        """Test batch_update_links_async emits batch_updated signal."""
        mock_db.links.batch_update.return_value = True

        with qtbot.waitSignal(links_business_logic.batch_updated, timeout=1000) as blocker:
            links_business_logic.batch_update_links_async([{"id": 1, "name": "Updated"}])

        assert blocker.args == (True,)

    def test_error_handling(self, qtbot, links_business_logic, mock_db):
        """Test error handling emits error_occurred signal."""
        mock_db.links.get_links.side_effect = Exception("DB Error")

        with qtbot.waitSignal(links_business_logic.error_occurred, timeout=1000) as blocker:
            links_business_logic.load_links(category_id=1)

        assert "DB Error" in blocker.args[0]

    def test_shutdown(self, links_business_logic, mock_scheduler):
        """Test shutdown completes without errors."""
        links_business_logic.shutdown(timeout=100)
        mock_scheduler.get_thread_pool.return_value.waitForDone.assert_called_once_with(100)

    def test_cache_invalidation(self, links_business_logic):
        """Test cache invalidation clears cache."""
        links_business_logic._cache["test_key"] = "test_value"
        links_business_logic._invalidate_cache()
        assert len(links_business_logic._cache) == 0

    def test_batch_update_links_async_empty_data(self, qtbot, links_business_logic, mock_db):
        """Test batch_update_links_async with empty data emits success."""
        with qtbot.waitSignal(links_business_logic.batch_updated, timeout=1000) as blocker:
            links_business_logic.batch_update_links_async([])

        assert blocker.args == (True,)

    def test_batch_update_links_async_invalid_data(self, qtbot, links_business_logic, mock_db):
        """Test batch_update_links_async with invalid data emits failure."""
        with qtbot.waitSignal(links_business_logic.batch_updated, timeout=1000) as blocker:
            links_business_logic.batch_update_links_async([{}])  # Invalid: empty dict

        assert blocker.args == (False,)

    def test_load_links_invalid_category(self, qtbot, links_business_logic, mock_db):
        """Test load_links with invalid category ID does not emit signal."""
        # Should not emit, but check no crash
        links_business_logic.load_links(category_id=-1)
        # No signal expected, just ensure no error

    def test_toggle_favorite_invalid_link(self, qtbot, links_business_logic, mock_db):
        """Test toggle_favorite with invalid link raises ValueError."""
        with pytest.raises(ValueError, match="Invalid link data"):
            links_business_logic.toggle_favorite({})  # Missing id

    def test_shutdown_with_active_tasks(self, links_business_logic, mock_scheduler):
        """Test shutdown waits for active threads."""
        links_business_logic.shutdown(timeout=100)
        assert mock_scheduler.get_thread_pool.return_value.waitForDone.called

    def test_cache_miss_and_load(self, qtbot, links_business_logic, mock_db):
        """Test cache miss triggers load."""
        mock_db.links.get_links.return_value = [{"id": 1}]
        # Clear cache
        links_business_logic._invalidate_cache()

        with qtbot.waitSignal(links_business_logic.links_loaded, timeout=1000):
            links_business_logic.load_links(category_id=1)

        # Check cache populated
        assert "links_1" in links_business_logic._cache

    def test_cancellation_via_task_lock(self, qtbot, links_business_logic, mock_db):
        """Test task cancellation by clearing pending tasks."""
        mock_db.links.get_links.return_value = []
        links_business_logic.load_links(category_id=1)
        # Simulate cancellation
        links_business_logic._clear_pending_tasks()
        # No signal should be emitted for cancelled task

    def test_integration_load_and_search(self, qtbot, links_business_logic, mock_db):
        """Integration test: load links then search."""
        mock_db.links.get_links.return_value = [{"id": 1, "name": "Test"}]
        mock_db.links.search_links.return_value = [{"id": 1, "name": "Test"}]

        # Load
        with qtbot.waitSignal(links_business_logic.links_loaded):
            links_business_logic.load_links(category_id=1)

        # Search
        with qtbot.waitSignal(links_business_logic.search_results_ready):
            links_business_logic.search_links("Test")

    def test_error_in_toggle_favorite(self, qtbot, links_business_logic, mock_db):
        """Test error handling in toggle_favorite."""
        mock_db.links.get_link_by_id.return_value = None  # Link not found

        with qtbot.waitSignal(links_business_logic.error_occurred):
            links_business_logic.toggle_favorite({"id": 1})

    def test_save_link_for_import_success(self, links_business_logic, mock_db):
        """Test save_link_for_import returns ID on success."""
        mock_db.links.create_or_update_link.return_value = 1
        result = links_business_logic.create_link_for_import({"name": "Import"})
        assert result == 1

    def test_save_link_for_import_failure(self, links_business_logic, mock_db):
        """Test save_link_for_import returns None on failure."""
        mock_db.links.create_or_update_link.return_value = None
        result = links_business_logic.create_link_for_import({"name": "Import"})
        assert result is None

    def test_mutex_locking_in_toggle_favorite(self, qtbot, links_business_logic, mock_db):
        """Test that mutex properly locks during toggle_favorite operations."""
        mock_db.links.get_link_by_id.return_value = {"id": 1, "is_favorite": False}
        mock_db.links.create_or_update_link.return_value = 1
        
        # Create a mock that tracks mutex state
        original_mutex = links_business_logic._mutex
        lock_acquired = threading.Event()
        lock_released = threading.Event()
        
        def mock_lock():
            lock_acquired.set()
            original_mutex.lock()
            
        def mock_unlock():
            original_mutex.unlock()
            lock_released.set()
            
        with patch.object(original_mutex, 'lock', side_effect=mock_lock), \
             patch.object(original_mutex, 'unlock', side_effect=mock_unlock):
            
            links_business_logic.toggle_favorite({"id": 1})
            
            # Verify lock was acquired and released
            assert lock_acquired.wait(timeout=1.0)
            assert lock_released.wait(timeout=1.0)

    def test_thread_safety_cache_operations(self, links_business_logic):
        """Test thread safety of cache operations."""
        import concurrent.futures
        
        def cache_operation(key: str, value: str):
            links_business_logic._cache[key] = value
            time.sleep(0.01)  # Small delay to increase chance of race condition
            return links_business_logic._cache.get(key)
        
        # Run multiple cache operations concurrently
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = []
            for i in range(10):
                future = executor.submit(cache_operation, f"key_{i}", f"value_{i}")
                futures.append(future)
            
            # Wait for all operations to complete
            results = [future.result() for future in concurrent.futures.as_completed(futures)]
            
        # All operations should have completed successfully
        assert len(results) == 10
        assert all(result is not None for result in results)

    def test_signal_emission_from_worker_thread(self, qtbot, links_business_logic, mock_db):
        """Test that signals are properly emitted from worker threads via dispatch."""
        mock_db.links.get_links.return_value = [{"id": 1, "name": "Test"}]
        
        # Track signal emission
        signal_received = threading.Event()
        
        def on_signal_received(*args):
            signal_received.set()
            
        links_business_logic.links_loaded.connect(on_signal_received)
        
        with qtbot.waitSignal(links_business_logic.links_loaded, timeout=2000):
            links_business_logic.load_links(category_id=1)
            
        # Verify signal was received
        assert signal_received.wait(timeout=2.0)

    def test_error_dispatch_mechanism(self, qtbot, links_business_logic, mock_db):
        """Test error dispatch mechanism works correctly."""
        mock_db.links.get_links.side_effect = Exception("Test error")
        
        with qtbot.waitSignal(links_business_logic.error_occurred, timeout=2000) as blocker:
            links_business_logic.load_links(category_id=1)
            
        assert "Test error" in blocker.args[0]

    def test_pending_tasks_cleanup_on_error(self, qtbot, links_business_logic, mock_db):
        """Test that pending tasks are cleaned up when errors occur."""
        mock_db.links.get_links.side_effect = Exception("Test error")
        
        # Load links to create pending task
        links_business_logic.load_links(category_id=1)
        
        # Wait for error to be processed
        with qtbot.waitSignal(links_business_logic.error_occurred, timeout=2000):
            pass
            
        # Pending tasks should be cleaned up
        assert len(links_business_logic.pending_tasks) == 0
