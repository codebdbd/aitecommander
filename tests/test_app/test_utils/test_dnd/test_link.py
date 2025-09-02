# tests/test_app/test_utils/test_dnd/test_link.py

import logging
from unittest.mock import MagicMock

import pytest

from app.utils.ui.dnd.link import DragDropHandlerMixin


# Dummy class that uses the mixin for testing purposes
class MockView(DragDropHandlerMixin):
    def __init__(self, model):
        self._model = model
        self._current_links = {}
        # Mock the method that is part of another mixin (DataManagementMixin)
        self.get_link_at = MagicMock()

    def model(self):
        return self._model


@pytest.fixture
def mock_model():
    """Fixture for a mock QAbstractItemModel."""
    model = MagicMock()
    model.rowCount.return_value = 3
    return model


@pytest.fixture
def mock_view(mock_model):
    """Fixture for a mock view that uses the mixin."""
    return MockView(mock_model)


class TestDragDropHandlerMixin:
    """Tests for the Drag & Drop handler mixin logic."""

    def test_rebuild_current_links_success(self, mock_view, mock_model):
        """Test that the cache is rebuilt correctly on success."""
        # Arrange: Simulate stale cache and define model data
        mock_view._current_links = {0: {"id": 99, "name": "Stale"}}
        mock_view.get_link_at.side_effect = [
            {"id": 1, "name": "Link 1"},
            {"id": 2, "name": "Link 2"},
            {"id": 3, "name": "Link 3"},
        ]

        # Act
        mock_view._rebuild_current_links()

        # Assert
        assert mock_view._current_links == {
            0: {"id": 1, "name": "Link 1"},
            1: {"id": 2, "name": "Link 2"},
            2: {"id": 3, "name": "Link 3"},
        }
        assert mock_view.get_link_at.call_count == mock_model.rowCount()

    def test_move_row_visually_success(self, mock_view, mock_model):
        """Test successful row move and that cache is rebuilt once."""
        # Arrange: After the move, the data order changes.
        # Let's say row 0 moves to the end (position 3, but becomes row 2).
        # The new order of links will be 2, 3, 1.
        mock_view.get_link_at.side_effect = [
            {"id": 2, "name": "Link 2"},
            {"id": 3, "name": "Link 3"},
            {"id": 1, "name": "Link 1"},
        ]

        # Act
        mock_view._move_row_visually(source_row=0, target_row=3)

        # Assert
        mock_model.move_rows.assert_called_once_with([0], 3)
        assert mock_view._current_links == {
            0: {"id": 2, "name": "Link 2"},
            1: {"id": 3, "name": "Link 3"},
            2: {"id": 1, "name": "Link 1"},
        }

    def test_move_row_visually_failure(self, mock_view, mock_model, caplog):
        """Test that cache is still rebuilt even if the move operation fails."""
        # Arrange
        mock_model.move_rows.side_effect = ValueError("Move failed unexpectedly")
        # The model's internal state is assumed to be unchanged on failure.
        mock_view.get_link_at.side_effect = [
            {"id": 1, "name": "Link 1"},
            {"id": 2, "name": "Link 2"},
            {"id": 3, "name": "Link 3"},
        ]

        # Act
        with caplog.at_level(logging.ERROR):
            mock_view._move_row_visually(source_row=0, target_row=3)

        # Assert
        mock_model.move_rows.assert_called_once_with([0], 3)
        assert "Ошибка визуального перемещения строки" in caplog.text
        assert "Move failed unexpectedly" in caplog.text

        # Check that the cache reflects the model's state (which didn't change)
        assert mock_view._current_links == {
            0: {"id": 1, "name": "Link 1"},
            1: {"id": 2, "name": "Link 2"},
            2: {"id": 3, "name": "Link 3"},
        }
