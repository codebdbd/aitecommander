import pytest
from unittest.mock import Mock

from app.utils.ui.qt.roles import get_selected_rows


def test_get_selected_rows_with_no_selection_model():
    """Тест: get_selected_rows должна вернуть пустой список, если selectionModel is None."""
    # Arrange
    mock_view = Mock()
    mock_view.selectionModel.return_value = None

    # Act
    result = get_selected_rows(mock_view)

    # Assert
    assert result == []
    mock_view.selectionModel.assert_called_once()


def test_get_selected_rows_with_selection():
    """Тест: get_selected_rows возвращает правильный список выбранных строк."""
    # Arrange
    mock_view = Mock()
    mock_selection_model = Mock()

    # Имитируем QModelIndex-подобные объекты
    mock_index1 = Mock()
    mock_index1.row.return_value = 1
    mock_index2 = Mock()
    mock_index2.row.return_value = 3
    mock_index3 = Mock()
    mock_index3.row.return_value = 3 # дубликат

    mock_selection_model.selectedRows.return_value = [mock_index1, mock_index2, mock_index3]
    mock_view.selectionModel.return_value = mock_selection_model

    # Act
    result = get_selected_rows(mock_view)

    # Assert
    assert result == [1, 3]
    mock_view.selectionModel.assert_called_once()
    mock_selection_model.selectedRows.assert_called_once()
