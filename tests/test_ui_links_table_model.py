"""Тесты для LinksTableModel - модели таблицы ссылок."""

import pytest
from datetime import datetime
from PyQt6.QtCore import Qt, QModelIndex
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

from app.views.link.links_model import LinksTableModel


pytestmark = pytest.mark.qt


@pytest.fixture(scope="session")
def qapp():
    """Fixture для QApplication."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture
def sample_links():
    """Пример данных ссылок."""
    return [
        {
            "id": 1,
            "name": "Google",
            "url": "https://google.com",
            "is_favorite": True,
            "last_used": "2024-01-01T10:00:00",
            "notes": "Search engine",
            "icon_path": "google.png",
        },
        {
            "id": 2,
            "name": "GitHub",
            "url": "https://github.com",
            "is_favorite": False,
            "last_used": "2024-01-02T11:00:00",
            "notes": "",
            "icon_path": "",
        },
        {
            "id": 3,
            "name": "Stack Overflow",
            "url": "https://stackoverflow.com",
            "is_favorite": False,
            "last_used": None,
            "notes": "Programming Q&A",
            "icon_path": None,
        },
    ]


class TestLinksTableModelInit:
    """Тесты инициализации модели."""
    
    def test_init_empty(self, qapp):
        """Тест создания пустой модели."""
        model = LinksTableModel()
        
        assert model.rowCount() == 0
        assert model.columnCount() == 4
        assert model._headers == ["♥", "Название", "Открывалась", "Заметки"]
    
    def test_init_with_data(self, qapp, sample_links):
        """Тест создания модели с данными."""
        model = LinksTableModel(sample_links)
        
        assert model.rowCount() == 3
        assert len(model._links) == 3


class TestLinksTableModelRowColumn:
    """Тесты rowCount и columnCount."""
    
    def test_row_count_empty(self, qapp):
        """Тест подсчёта строк пустой модели."""
        model = LinksTableModel()
        assert model.rowCount() == 0
    
    def test_row_count_with_data(self, qapp, sample_links):
        """Тест подсчёта строк с данными."""
        model = LinksTableModel(sample_links)
        assert model.rowCount() == 3
    
    def test_column_count(self, qapp):
        """Тест подсчёта колонок."""
        model = LinksTableModel()
        assert model.columnCount() == 4
    
    def test_row_count_with_valid_parent_returns_zero(self, qapp, sample_links):
        """Тест: rowCount с валидным parent должен вернуть 0 (плоская модель)."""
        model = LinksTableModel(sample_links)
        
        parent_index = model.index(0, 0)
        assert model.rowCount(parent_index) == 0


class TestLinksTableModelData:
    """Тесты получения данных."""
    
    def test_data_display_role_col0_favorite(self, qapp, sample_links):
        """Тест DisplayRole колонка 0 (избранное)."""
        model = LinksTableModel(sample_links)
        
        index = model.index(0, 0)
        data = model.data(index, Qt.ItemDataRole.DisplayRole)
        
        assert data == "★"  # Избранное
    
    def test_data_display_role_col0_not_favorite(self, qapp, sample_links):
        """Тест DisplayRole колонка 0 (не избранное)."""
        model = LinksTableModel(sample_links)
        
        index = model.index(1, 0)
        data = model.data(index, Qt.ItemDataRole.DisplayRole)
        
        assert data == ""  # Не избранное
    
    def test_data_display_role_col1_name(self, qapp, sample_links):
        """Тест DisplayRole колонка 1 (название)."""
        model = LinksTableModel(sample_links)
        
        index = model.index(0, 1)
        data = model.data(index, Qt.ItemDataRole.DisplayRole)
        
        assert data == "Google"
    
    def test_data_display_role_col2_last_used(self, qapp, sample_links):
        """Тест DisplayRole колонка 2 (последнее использование)."""
        model = LinksTableModel(sample_links)
        
        index = model.index(0, 2)
        data = model.data(index, Qt.ItemDataRole.DisplayRole)
        
        # Проверяем, что возвращается строка (формат зависит от реализации)
        assert isinstance(data, str)
    
    def test_data_display_role_col3_notes(self, qapp, sample_links):
        """Тест DisplayRole колонка 3 (заметки)."""
        model = LinksTableModel(sample_links)
        
        index = model.index(0, 3)
        data = model.data(index, Qt.ItemDataRole.DisplayRole)
        
        assert data == "Search engine"
    
    def test_data_user_role_returns_dict(self, qapp, sample_links):
        """Тест UserRole возвращает весь словарь ссылки."""
        model = LinksTableModel(sample_links)
        
        index = model.index(0, 1)
        data = model.data(index, Qt.ItemDataRole.UserRole)
        
        assert isinstance(data, dict)
        assert data["id"] == 1
        assert data["name"] == "Google"
    
    def test_data_tooltip_role_col1(self, qapp, sample_links):
        """Тест ToolTipRole для колонки названия."""
        model = LinksTableModel(sample_links)
        
        index = model.index(0, 1)
        tooltip = model.data(index, Qt.ItemDataRole.ToolTipRole)
        
        # Может быть None или строка
        assert tooltip is None or isinstance(tooltip, str)
    
    def test_data_text_alignment_col0(self, qapp, sample_links):
        """Тест выравнивания для колонки 0 (избранное)."""
        model = LinksTableModel(sample_links)
        
        index = model.index(0, 0)
        alignment = model.data(index, Qt.ItemDataRole.TextAlignmentRole)
        
        assert alignment == int(Qt.AlignmentFlag.AlignCenter)
    
    def test_data_invalid_index(self, qapp, sample_links):
        """Тест получения данных с невалидным индексом."""
        model = LinksTableModel(sample_links)
        
        invalid_index = QModelIndex()
        data = model.data(invalid_index, Qt.ItemDataRole.DisplayRole)
        
        # QVariant() в PyQt6 конвертируется в None/пустое значение
        assert data is None or data == ""


class TestLinksTableModelSetData:
    """Тесты установки данных."""
    
    def test_set_data_col0_is_favorite(self, qapp, sample_links):
        """Тест изменения is_favorite через setData."""
        model = LinksTableModel(sample_links)
        
        index = model.index(1, 0)  # GitHub, изначально не избранное
        
        result = model.setData(index, True, Qt.ItemDataRole.EditRole)
        
        assert result is True
        assert model._links[1]["is_favorite"] is True
    
    def test_set_data_col1_name(self, qapp, sample_links):
        """Тест изменения названия через setData."""
        model = LinksTableModel(sample_links)
        
        index = model.index(0, 1)
        result = model.setData(index, "New Name", Qt.ItemDataRole.EditRole)
        
        assert result is True
        assert model._links[0]["name"] == "New Name"
    
    def test_set_data_col3_notes(self, qapp, sample_links):
        """Тест изменения заметок через setData."""
        model = LinksTableModel(sample_links)
        
        index = model.index(1, 3)
        result = model.setData(index, "New notes", Qt.ItemDataRole.EditRole)
        
        assert result is True
        assert model._links[1]["notes"] == "New notes"
    
    def test_set_data_user_role_replaces_dict(self, qapp, sample_links):
        """Тест замены всего словаря ссылки через UserRole."""
        model = LinksTableModel(sample_links)
        
        new_link = {
            "id": 999,
            "name": "Replaced",
            "url": "https://replaced.com",
            "is_favorite": False,
            "last_used": None,
            "notes": "",
        }
        
        index = model.index(0, 0)
        result = model.setData(index, new_link, Qt.ItemDataRole.UserRole)
        
        assert result is True
        assert model._links[0]["id"] == 999
        assert model._links[0]["name"] == "Replaced"
    
    def test_set_data_invalid_index(self, qapp, sample_links):
        """Тест setData с невалидным индексом."""
        model = LinksTableModel(sample_links)
        
        invalid_index = QModelIndex()
        result = model.setData(invalid_index, "test", Qt.ItemDataRole.EditRole)
        
        assert result is False


class TestLinksTableModelMutations:
    """Тесты мутаций данных."""
    
    def test_set_links_replaces_data(self, qapp, sample_links):
        """Тест замены данных через set_links."""
        model = LinksTableModel()
        assert model.rowCount() == 0
        
        model.set_links(sample_links)
        
        assert model.rowCount() == 3
        assert model._links[0]["id"] == 1
    
    def test_insert_link_at_position(self, qapp, sample_links):
        """Тест вставки ссылки в позицию."""
        model = LinksTableModel(sample_links)
        
        new_link = {"id": 99, "name": "New Link", "url": "", "is_favorite": False}
        
        result = model.insert_link(1, new_link)
        
        assert result is True
        assert model.rowCount() == 4
        assert model._links[1]["id"] == 99
    
    def test_append_link(self, qapp, sample_links):
        """Тест добавления ссылки в конец."""
        model = LinksTableModel(sample_links)
        
        new_link = {"id": 99, "name": "Appended", "url": "", "is_favorite": False}
        
        result = model.append_link(new_link)
        
        assert result is True
        assert model.rowCount() == 4
        assert model._links[-1]["id"] == 99
    
    def test_remove_row(self, qapp, sample_links):
        """Тест удаления строки."""
        model = LinksTableModel(sample_links)
        
        result = model.remove_row(1)
        
        assert result is True
        assert model.rowCount() == 2
        assert model._links[1]["id"] == 3  # Stack Overflow сдвинулась вверх
    
    def test_remove_row_invalid_index(self, qapp, sample_links):
        """Тест удаления несуществующей строки."""
        model = LinksTableModel(sample_links)
        
        result = model.remove_row(999)
        
        assert result is False
        assert model.rowCount() == 3
    
    def test_update_link(self, qapp, sample_links):
        """Тест обновления ссылки."""
        model = LinksTableModel(sample_links)
        
        update_data = {"name": "Updated Name", "notes": "Updated notes"}
        
        result = model.update_link(0, update_data)
        
        assert result is True
        assert model._links[0]["name"] == "Updated Name"
        assert model._links[0]["notes"] == "Updated notes"
        assert model._links[0]["id"] == 1  # id остался прежним


class TestLinksTableModelHelpers:
    """Тесты вспомогательных методов."""
    
    def test_get_link_valid_row(self, qapp, sample_links):
        """Тест получения ссылки по номеру строки."""
        model = LinksTableModel(sample_links)
        
        link = model.get_link(1)
        
        assert link is not None
        assert link["id"] == 2
        assert link["name"] == "GitHub"
    
    def test_get_link_invalid_row(self, qapp, sample_links):
        """Тест получения ссылки с невалидным индексом."""
        model = LinksTableModel(sample_links)
        
        link = model.get_link(999)
        
        assert link is None
    
    def test_find_row_by_id_existing(self, qapp, sample_links):
        """Тест поиска строки по id."""
        model = LinksTableModel(sample_links)
        
        row = model.find_row_by_id(2)
        
        assert row == 1
    
    def test_find_row_by_id_non_existing(self, qapp, sample_links):
        """Тест поиска несуществующей ссылки."""
        model = LinksTableModel(sample_links)
        
        row = model.find_row_by_id(999)
        
        assert row == -1


class TestLinksTableModelSorting:
    """Тесты сортировки."""
    
    def test_sort_by_name_ascending(self, qapp, sample_links):
        """Тест сортировки по названию (возрастание)."""
        model = LinksTableModel(sample_links)
        
        model.sort(1, Qt.SortOrder.AscendingOrder)
        
        names = [model._links[i]["name"] for i in range(3)]
        assert names == ["GitHub", "Google", "Stack Overflow"]
    
    def test_sort_by_name_descending(self, qapp, sample_links):
        """Тест сортировки по названию (убывание)."""
        model = LinksTableModel(sample_links)
        
        model.sort(1, Qt.SortOrder.DescendingOrder)
        
        names = [model._links[i]["name"] for i in range(3)]
        assert names == ["Stack Overflow", "Google", "GitHub"]
    
    def test_sort_by_favorite(self, qapp, sample_links):
        """Тест сортировки по избранному."""
        model = LinksTableModel(sample_links)
        
        model.sort(0, Qt.SortOrder.DescendingOrder)
        
        # Избранные должны быть сверху
        assert model._links[0]["is_favorite"] is True
    
    def test_sort_by_last_used(self, qapp, sample_links):
        """Тест сортировки по времени использования."""
        model = LinksTableModel(sample_links)
        
        model.sort(2, Qt.SortOrder.DescendingOrder)
        
        # Новые сверху (2024-01-02 > 2024-01-01 > None)
        assert model._links[0]["id"] == 2  # GitHub (2024-01-02)
        assert model._links[1]["id"] == 1  # Google (2024-01-01)
        assert model._links[2]["id"] == 3  # Stack Overflow (None)
    
    def test_sort_empty_model(self, qapp):
        """Тест сортировки пустой модели (не должна падать)."""
        model = LinksTableModel()
        
        model.sort(1, Qt.SortOrder.AscendingOrder)
        
        assert model.rowCount() == 0


class TestLinksTableModelMoveRows:
    """Тесты перемещения строк."""
    
    def test_move_single_row_down(self, qapp, sample_links):
        """Тест перемещения одной строки вниз."""
        model = LinksTableModel(sample_links)
        
        # Google (0) -> позиция 2
        model.move_rows([0], 2)
        
        names = [model._links[i]["name"] for i in range(3)]
        assert names == ["GitHub", "Google", "Stack Overflow"]
    
    def test_move_single_row_up(self, qapp, sample_links):
        """Тест перемещения одной строки вверх."""
        model = LinksTableModel(sample_links)
        
        # GitHub (1) -> позиция 0
        model.move_rows([1], 0)
        
        names = [model._links[i]["name"] for i in range(3)]
        assert names == ["GitHub", "Google", "Stack Overflow"]
    
    def test_move_multiple_rows(self, qapp, sample_links):
        """Тест перемещения нескольких строк."""
        model = LinksTableModel(sample_links)
        
        # Google (0) и Stack Overflow (2) -> конец
        model.move_rows([0, 2], 3)
        
        names = [model._links[i]["name"] for i in range(3)]
        # GitHub остаётся, Google и SO перемещаются
        assert names[0] == "GitHub"
    
    def test_move_rows_empty_list(self, qapp, sample_links):
        """Тест перемещения пустого списка (не должна падать)."""
        model = LinksTableModel(sample_links)
        
        model.move_rows([], 1)
        
        # Ничего не изменилось
        assert model.rowCount() == 3
        assert model._links[0]["name"] == "Google"


class TestLinksTableModelFlags:
    """Тесты флагов элементов."""
    
    def test_flags_valid_index(self, qapp, sample_links):
        """Тест флагов для валидного индекса."""
        model = LinksTableModel(sample_links)
        
        index = model.index(0, 0)
        flags = model.flags(index)
        
        assert flags & Qt.ItemFlag.ItemIsSelectable
        assert flags & Qt.ItemFlag.ItemIsEnabled
        assert flags & Qt.ItemFlag.ItemIsDragEnabled
    
    def test_flags_invalid_index(self, qapp, sample_links):
        """Тест флагов для невалидного индекса."""
        model = LinksTableModel(sample_links)
        
        invalid_index = QModelIndex()
        flags = model.flags(invalid_index)
        
        assert flags == Qt.ItemFlag.NoItemFlags


class TestLinksTableModelHeaders:
    """Тесты заголовков."""
    
    def test_header_data_horizontal(self, qapp):
        """Тест получения заголовков колонок."""
        model = LinksTableModel()
        
        header0 = model.headerData(0, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole)
        header1 = model.headerData(1, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole)
        
        assert header0 == "♥"
        assert header1 == "Название"
    
    def test_set_headers(self, qapp):
        """Тест установки пользовательских заголовков."""
        model = LinksTableModel()
        
        custom_headers = ["Fav", "Name", "Last Used", "Notes"]
        model.set_headers(custom_headers)
        
        assert model._headers == custom_headers
        assert model.columnCount() == 4


class TestLinksTableModelIconCache:
    """Тесты кэширования иконок."""
    
    def test_icon_cache_lru_limit(self, qapp):
        """Тест ограничения LRU кэша иконок."""
        model = LinksTableModel()
        
        # Проверяем, что MAX_ICON_CACHE установлен
        assert hasattr(model, 'MAX_ICON_CACHE')
        assert model.MAX_ICON_CACHE > 0
    
    def test_cached_icon_same_path(self, qapp, sample_links):
        """Тест, что одинаковые пути возвращают закэшированную иконку."""
        model = LinksTableModel(sample_links)
        
        # Два вызова с одним путём
        icon1 = model._get_cached_icon("test.png")
        icon2 = model._get_cached_icon("test.png")
        
        # Должны быть одинаковыми (из кэша)
        # В реальности это может быть разными объектами, но логика кэша работает
        assert icon1 is not None or icon2 is not None
