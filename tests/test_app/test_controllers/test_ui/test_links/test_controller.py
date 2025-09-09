import logging
from unittest.mock import MagicMock, patch

import pytest

from app.controllers.ui.links.controller import LinksUIController


@pytest.fixture
def mock_table_widget():
    """Fixture for a mock LinksTableView."""
    return MagicMock()


@pytest.fixture
def mock_business_logic():
    """Fixture for a mock LinksBusinessLogic."""
    return MagicMock()


@pytest.fixture
def mock_main_window():
    """Fixture for a mock main window."""
    # Mock the dependencies that the controller's __init__ expects
    main_window = MagicMock()
    main_window.ui_state = MagicMock()
    main_window.structure.tree = MagicMock()
    return main_window


@pytest.fixture
def links_controller(mock_table_widget, mock_business_logic, mock_main_window):
    """Fixture for LinksUIController with mocked dependencies."""
    with (
        patch("app.controllers.ui.links.controller.LinksUIHandlers"),
        patch("app.controllers.ui.links.controller.LinksUIClipboard"),
        patch("app.controllers.ui.links.controller.LinksUILinkOperations"),
    ):
        controller = LinksUIController(
            table_widget=mock_table_widget,
            business_logic=mock_business_logic,
            main_window=mock_main_window,
            link_operations=MagicMock(),
            links_table_controller=MagicMock(),
        )
        return controller


@pytest.mark.parametrize("error_to_raise", [AttributeError, RuntimeError])
class TestExceptionHandling:
    """Tests for graceful error handling in LinksUIController."""

    def test_get_row_count_handles_exception(
        self, links_controller, mock_table_widget, caplog, error_to_raise
    ):
        """Test get_row_count returns 0 and logs error on exception."""
        mock_table_widget.model.side_effect = error_to_raise("Test Error")
        with caplog.at_level(logging.ERROR):
            result = links_controller.get_row_count()
        assert result == 0
        assert "Ошибка при получении количества строк" in caplog.text

    def test_has_selection_handles_exception(
        self, links_controller, mock_table_widget, caplog, error_to_raise
    ):
        """Test has_selection returns False and logs error on exception."""
        mock_table_widget.selectionModel.side_effect = error_to_raise("Test Error")
        with caplog.at_level(logging.ERROR):
            result = links_controller.has_selection()
        assert result is False
        assert "Ошибка при проверке выделения" in caplog.text

    def test_current_row_handles_exception(
        self, links_controller, mock_table_widget, caplog, error_to_raise
    ):
        """Test current_row returns -1 and logs error on exception."""
        mock_table_widget.currentIndex.side_effect = error_to_raise("Test Error")
        with caplog.at_level(logging.ERROR):
            result = links_controller.current_row()
        assert result == -1
        assert "Ошибка при получении текущей строки" in caplog.text

    def test_set_current_cell_handles_exception(
        self, links_controller, mock_table_widget, caplog, error_to_raise
    ):
        """Test set_current_cell logs error on exception and does not crash."""
        mock_table_widget.model.side_effect = error_to_raise("Test Error")
        with caplog.at_level(logging.ERROR):
            links_controller.set_current_cell(0, 0)
        assert "Ошибка при установке текущей ячейки" in caplog.text

    def test_scroll_to_row_handles_exception(
        self, links_controller, mock_table_widget, caplog, error_to_raise
    ):
        """Test scroll_to_row logs error on exception and does not crash."""
        mock_table_widget.model.side_effect = error_to_raise("Test Error")
        with caplog.at_level(logging.ERROR):
            links_controller.scroll_to_row(0)
        assert "Ошибка при прокрутке к строке" in caplog.text
