import logging
from unittest.mock import MagicMock, patch

import pytest

from app.services.structure_context_service import StructureContextService


@pytest.fixture
def mock_db():
    """Fixture for a mock database connection."""
    return MagicMock()


@pytest.fixture
def mock_qapplication():
    """Fixture for mocking QApplication and its clipboard."""
    with patch('PyQt6.QtWidgets.QApplication.instance') as mock_instance:
        mock_app = MagicMock()
        mock_clipboard = MagicMock()
        mock_app.clipboard.return_value = mock_clipboard
        mock_instance.return_value = mock_app
        # Mock mimeData as well for clipboard_has_text
        mock_mime_data = MagicMock()
        mock_clipboard.mimeData.return_value = mock_mime_data
        yield mock_instance, mock_clipboard, mock_mime_data


@pytest.fixture
def service(mock_db):
    """Fixture for StructureContextService with a mock DB."""
    return StructureContextService(mock_db)


def test_clipboard_get_json_invalid_json(service, mock_qapplication, caplog):
    """Test _clipboard_get_json returns None and logs a warning for invalid JSON."""
    _, mock_clipboard, mock_mime_data = mock_qapplication
    mock_mime_data.hasText.return_value = True
    mock_mime_data.text.return_value = 'невалидный json'
    mock_clipboard.text.return_value = 'невалидный json'

    with caplog.at_level(logging.WARNING):
        result = service._clipboard_get_json()

    assert result is None
    assert "Failed to get and parse JSON from clipboard" in caplog.text
    assert "JSONDecodeError" in caplog.text


def test_clipboard_get_json_no_qapplication(service, mock_qapplication, caplog):
    """Test _clipboard_get_json returns None when QApplication is not available."""
    mock_instance, _, _ = mock_qapplication
    mock_instance.return_value = None

    with caplog.at_level(logging.INFO):
        result = service._clipboard_get_json()

    assert result is None
    assert not caplog.text  # Ошибки не должно быть, код обрабатывает это штатно


@patch('app.services.structure_context_service.StructureService')
def test_copy_category_tree_value_error(MockStructureService, mock_db, mock_qapplication, caplog):
    """Test copy_category_tree_to_clipboard handles ValueError on cat_id."""
    mock_ss_instance = MockStructureService.return_value
    mock_ss_instance.export_category_tree.side_effect = ValueError("Invalid ID")
    service = StructureContextService(mock_db)

    with caplog.at_level(logging.ERROR):
        service.copy_category_tree_to_clipboard('invalid_id')

    assert "copy_category_tree_to_clipboard failed" in caplog.text
    assert "ValueError" in caplog.records[0].exc_text


def test_paste_from_clipboard_key_error(service, mock_qapplication, caplog):
    """Test paste_from_clipboard_to_section handles KeyError from invalid data."""
    _, mock_clipboard, mock_mime_data = mock_qapplication
    mock_mime_data.hasText.return_value = True
    mock_mime_data.text.return_value = '[{"invalid_key": 1}]'
    mock_clipboard.text.return_value = '[{"invalid_key": 1}]'
    service._normalize_to_tree_list = MagicMock(side_effect=KeyError("Missing key"))

    with caplog.at_level(logging.ERROR):
        result = service.paste_from_clipboard_to_section(1)

    assert result == []
    assert "paste_from_clipboard_to_section(section_id=1) failed" in caplog.text
    assert "KeyError" in caplog.records[0].exc_text
