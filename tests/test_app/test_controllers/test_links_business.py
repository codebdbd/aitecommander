"""Tests for LinksBusinessLogic."""

import pytest
from unittest.mock import Mock, patch
from PyQt6.QtCore import QObject

from app.controllers.business.links_business import LinksBusinessLogic
from app.models.db import Database


@pytest.fixture
def mock_db():
    """Mock database."""
    return Mock(spec=Database)


@pytest.fixture
def mock_links_service():
    """Mock LinksService."""
    return Mock()


@pytest.fixture
def links_business(qt_app, mock_db, mock_links_service):
    """Create LinksBusinessLogic instance with mocks."""
    with patch('app.controllers.business.links_business.LinksService', return_value=mock_links_service), \
         patch('app.controllers.business.links_business.get_task_scheduler', return_value=Mock()), \
         patch('app.controllers.business.links_business.tasks_lock', Mock()):
        business = LinksBusinessLogic(mock_db)
        yield business


class TestLinksBusinessLogic:
    """Test LinksBusinessLogic."""

    def test_init(self, links_business, mock_db, mock_links_service):
        """Test initialization."""
        assert links_business.db == mock_db
        assert links_business.links == mock_links_service
        assert links_business.pending_tasks == {}
        assert links_business.task_counter == 0

    def test_load_links_async(self, qtbot, links_business, mock_links_service):
        """Test asynchronous link loading."""
        mock_links_service.get_links.return_value = [{"id": 1, "name": "Test"}]

        # Connect to signal
        with qtbot.wait_signal(links_business.links_loaded) as blocker:
            links_business.load_links(1)

        # Check signal emitted with correct data
        assert blocker.args == ([{"id": 1, "name": "Test"}], 1, 1)

    def test_search_links_async(self, qtbot, links_business, mock_links_service):
        """Test asynchronous link search."""
        mock_links_service.get_all_links.return_value = [{"id": 1, "name": "Test"}]

        with qtbot.wait_signal(links_business.search_results_ready) as blocker:
            links_business.search_links("")  # Empty query triggers all links

        assert blocker.args == ([{"id": 1, "name": "Test"}],)

    def test_toggle_favorite_async(self, qtbot, links_business, mock_links_service):
        """Test asynchronous favorite toggle."""
        mock_links_service.get_link_by_id.return_value = {"id": 1, "name": "Test", "is_favorite": False}
        mock_links_service.create_or_update_link.return_value = 1

        with qtbot.wait_signal(links_business.link_updated) as blocker:
            links_business.toggle_favorite({"id": 1, "name": "Test"})

        assert blocker.args == ({"id": 1, "name": "Test", "is_favorite": True},)

    def test_save_link_async_success(self, qtbot, links_business, mock_links_service):
        """Test successful asynchronous link save."""
        link_data = {"name": "New Link", "url": "http://example.com"}
        mock_links_service.create_or_update_link.return_value = 42

        with qtbot.wait_signal(links_business.link_updated) as blocker:
            links_business.save_link_async(link_data.copy())

        assert blocker.args == ({"id": 42, "name": "New Link", "url": "http://example.com"},)

    def test_delete_link_async(self, qtbot, links_business, mock_links_service):
        """Test asynchronous link deletion."""
        mock_links_service.delete_link.return_value = True

        with qtbot.wait_signal(links_business.link_deleted) as blocker:
            links_business.delete_link(1)

        assert blocker.args == (1,)

    def test_batch_update_links_async_success(self, qtbot, links_business, mock_links_service):
        """Test successful batch link update."""
        links_data = [{"id": 1, "name": "Link 1"}, {"id": 2, "name": "Link 2"}]
        mock_links_service.batch_update.return_value = True

        with qtbot.wait_signal(links_business.batch_updated) as blocker:
            links_business.batch_update_links_async(links_data)

        assert blocker.args == (True,)

    def test_batch_update_links_async_invalid_data(self, qtbot, links_business):
        """Test batch update with invalid data."""
        invalid_data = [None, {"name": "Valid"}]

        with qtbot.wait_signal(links_business.batch_updated) as blocker:
            links_business.batch_update_links_async(invalid_data)

        assert blocker.args == (False,)

    def test_error_handling_in_async_operation(self, qtbot, links_business, mock_links_service):
        """Test error handling in asynchronous operations."""
        mock_links_service.get_links.side_effect = Exception("DB Error")

        with qtbot.wait_signal(links_business.error_occurred) as blocker:
            links_business.load_links(1)

        assert "DB Error" in blocker.args[0]

    def test_cache_invalidation_after_save(self, links_business, mock_links_service):
        """Test cache invalidation after save."""
        link_data = {"name": "Test", "url": "http://test.com"}
        mock_links_service.create_or_update_link.return_value = 1

        links_business.save_link_async(link_data)

        # Cache should be invalidated
        assert len(links_business._cache) == 0

    def test_shutdown(self, links_business):
        """Test graceful shutdown."""
        # Mock scheduler and thread pool
        mock_scheduler = Mock()
        mock_thread_pool = Mock()
        mock_thread_pool.activeThreadCount.return_value = 1
        mock_scheduler.get_thread_pool.return_value = mock_thread_pool

        links_business.scheduler = mock_scheduler

        links_business.shutdown(1000)

        mock_thread_pool.waitForDone.assert_called_once_with(1000)
        mock_thread_pool.clear.assert_not_called()  # Not called in shutdown

    def test_validate_link_form_invalid_data(self, links_business):
        """Test link form validation with invalid data."""
        with pytest.raises(ValueError, match="Invalid link data provided"):
            links_business.save_link({})  # Missing required fields

    def test_validate_link_form_invalid_dict(self, links_business):
        """Test link form validation with non-dict data."""
        with pytest.raises(ValueError, match="Invalid link data provided: not a dict"):
            links_business.save_link("not a dict")
