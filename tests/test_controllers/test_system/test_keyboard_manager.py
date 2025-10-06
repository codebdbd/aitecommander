"""
Тесты для KeyboardManager.

✅ НОВЫЙ ФАЙЛ: Покрытие keyboard handling логики.
"""

from unittest.mock import Mock, patch

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QApplication, QWidget

from app.controllers.system.keyboard_manager import (
    BaseKeyHandler,
    ClipboardKeyHandler,
    EditingKeyHandler,
)


@pytest.fixture
def main_window():
    """Создаёт mock главного окна."""
    window = Mock()
    window.structure = Mock()
    window.structure.tree = Mock()
    window.table = Mock()
    window.links_actions = Mock()
    window.links = Mock()
    return window


@pytest.fixture
def clipboard_handler(main_window):
    """Создаёт ClipboardKeyHandler."""
    return ClipboardKeyHandler(main_window)


@pytest.fixture
def editing_handler(main_window):
    """Создаёт EditingKeyHandler."""
    return EditingKeyHandler(main_window)


class TestBaseKeyHandler:
    """Тесты базового класса."""

    def test_safe_getattr_returns_attribute(self, main_window):
        """_safe_getattr() возвращает атрибут если он существует."""
        # Arrange
        handler = BaseKeyHandler(main_window)
        main_window.test_attr = "test_value"

        # Act
        result = handler._safe_getattr(main_window, "test_attr")

        # Assert
        assert result == "test_value"

    def test_safe_getattr_returns_default_on_missing(self, main_window):
        """_safe_getattr() возвращает default если атрибут отсутствует."""
        # Arrange
        handler = BaseKeyHandler(main_window)

        # Act
        result = handler._safe_getattr(main_window, "missing_attr", default="default")

        # Assert
        assert result == "default"

    def test_safe_call_calls_method(self, main_window):
        """_safe_call() вызывает метод если он существует."""
        # Arrange
        handler = BaseKeyHandler(main_window)
        obj = Mock()
        obj.test_method = Mock(return_value="result")

        # Act
        result = handler._safe_call(obj, "test_method", "arg1", kwarg="value")

        # Assert
        obj.test_method.assert_called_once_with("arg1", kwarg="value")
        assert result == "result"

    def test_safe_call_returns_default_on_missing(self, main_window):
        """_safe_call() возвращает default если метод отсутствует."""
        # Arrange
        handler = BaseKeyHandler(main_window)
        obj = Mock(spec=[])  # Нет методов

        # Act
        result = handler._safe_call(obj, "missing_method", default="default")

        # Assert
        assert result == "default"


class TestClipboardKeyHandler:
    """Тесты обработчика буфера обмена."""

    def test_handle_copy_calls_links_actions(self, clipboard_handler, main_window):
        """handle_copy() вызывает links_actions.copy_selected_links()."""
        # Act
        clipboard_handler.handle_copy()

        # Assert
        main_window.links_actions.copy_selected_links.assert_called_once()

    def test_handle_cut_calls_links_actions(self, clipboard_handler, main_window):
        """handle_cut() вызывает links_actions.cut_selected_links()."""
        # Act
        clipboard_handler.handle_cut()

        # Assert
        main_window.links_actions.cut_selected_links.assert_called_once()

    def test_handle_paste_calls_links_actions(self, clipboard_handler, main_window):
        """handle_paste() вызывает links_actions.paste_links()."""
        # Act
        clipboard_handler.handle_paste()

        # Assert
        main_window.links_actions.paste_links.assert_called_once()

    def test_handle_copy_fallback_to_links(self, clipboard_handler, main_window):
        """handle_copy() использует links если links_actions отсутствует."""
        # Arrange
        main_window.links_actions = None

        # Act
        clipboard_handler.handle_copy()

        # Assert
        main_window.links.copy_selected_links.assert_called_once()

    @patch("app.controllers.system.keyboard_manager.QApplication.focusWidget")
    def test_handle_select_all_in_table(
        self, mock_focus_widget, clipboard_handler, main_window
    ):
        """handle_select_all() вызывает table.selectAll() если фокус на таблице."""
        # Arrange
        mock_widget = Mock()
        mock_widget.__class__.__name__ = "LinksTableView"
        mock_focus_widget.return_value = mock_widget

        # Act
        clipboard_handler.handle_select_all()

        # Assert
        main_window.table.selectAll.assert_called_once()


class TestEditingKeyHandler:
    """Тесты обработчика редактирования."""

    def test_is_tree_focused_returns_true_for_tree(self, editing_handler):
        """_is_tree_focused() возвращает True для дерева."""
        # Arrange
        widget = Mock()
        widget.__class__.__name__ = "StructureTreeView"

        # Act
        result = editing_handler._is_tree_focused(widget)

        # Assert
        assert result is True

    def test_is_tree_focused_returns_false_for_table(self, editing_handler):
        """_is_tree_focused() возвращает False для таблицы."""
        # Arrange
        widget = Mock()
        widget.__class__.__name__ = "LinksTableView"

        # Act
        result = editing_handler._is_tree_focused(widget)

        # Assert
        assert result is False

    def test_is_table_focused_returns_true_for_table(self, editing_handler):
        """_is_table_focused() возвращает True для таблицы."""
        # Arrange
        widget = Mock()
        widget.__class__.__name__ = "LinksTableView"

        # Act
        result = editing_handler._is_table_focused(widget)

        # Assert
        assert result is True

    def test_is_table_focused_returns_false_for_tree(self, editing_handler):
        """_is_table_focused() возвращает False для дерева."""
        # Arrange
        widget = Mock()
        widget.__class__.__name__ = "StructureTreeView"

        # Act
        result = editing_handler._is_table_focused(widget)

        # Assert
        assert result is False


class TestContextualHandling:
    """Тесты контекстной обработки."""

    @patch("app.controllers.system.keyboard_manager.QApplication.focusWidget")
    def test_select_all_clears_tree_when_table_focused(
        self, mock_focus_widget, clipboard_handler, main_window
    ):
        """Выделение в таблице снимает выделение в дереве (эксклюзивность)."""
        # Arrange
        mock_widget = Mock()
        mock_widget.__class__.__name__ = "LinksTableView"
        mock_focus_widget.return_value = mock_widget

        tree = Mock()
        main_window.structure.tree = tree

        # Act
        clipboard_handler.handle_select_all()

        # Assert
        tree.clearSelection.assert_called_once()


class TestEdgeCases:
    """Тесты граничных случаев."""

    def test_handle_copy_with_no_links_actions(self, main_window):
        """handle_copy() не падает если links_actions отсутствует."""
        # Arrange
        main_window.links_actions = None
        main_window.links = None
        handler = ClipboardKeyHandler(main_window)

        # Act & Assert (не должно быть исключений)
        handler.handle_copy()

    def test_safe_call_with_exception(self, main_window):
        """_safe_call() возвращает default если метод выбрасывает исключение."""
        # Arrange
        handler = BaseKeyHandler(main_window)
        obj = Mock()
        obj.failing_method = Mock(side_effect=RuntimeError("Test error"))

        # Act
        result = handler._safe_call(obj, "failing_method", default="fallback")

        # Assert
        assert result == "fallback"

    @patch("app.controllers.system.keyboard_manager.QApplication.focusWidget")
    def test_handle_select_all_with_none_focus(
        self, mock_focus_widget, clipboard_handler, main_window
    ):
        """handle_select_all() не падает если focusWidget() возвращает None."""
        # Arrange
        mock_focus_widget.return_value = None

        # Act & Assert (не должно быть исключений)
        clipboard_handler.handle_select_all()
