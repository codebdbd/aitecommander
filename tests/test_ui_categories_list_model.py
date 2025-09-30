"""Тесты для CategoriesListModel - модели списка категорий."""

import pytest
from PyQt6.QtCore import Qt, QModelIndex
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

from app.views.models.categories_list_model import CategoriesListModel


pytestmark = pytest.mark.qt


@pytest.fixture(scope="session")
def qapp():
    """Fixture для QApplication."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture
def sample_categories():
    """Пример данных категорий."""
    return [
        {"id": 1, "name": "Category 1", "icon_path": ""},
        {"id": 2, "name": "Category 2", "icon_path": "test.png"},
        {"id": 3, "name": "Category 3", "icon_path": None},
    ]


class TestCategoriesListModelInit:
    """Тесты инициализации модели."""
    
    def test_init_empty(self, qapp):
        """Тест создания пустой модели."""
        model = CategoriesListModel()
        
        assert model.rowCount() == 0
        assert model._items == []
        assert model._row_by_id == {}
    
    def test_init_with_data(self, qapp, sample_categories):
        """Тест создания модели с данными."""
        model = CategoriesListModel(sample_categories)
        
        assert model.rowCount() == 3
        assert len(model._items) == 3
        assert model._row_by_id[1] == 0
        assert model._row_by_id[2] == 1
        assert model._row_by_id[3] == 2


class TestCategoriesListModelData:
    """Тесты получения данных из модели."""
    
    def test_data_display_role(self, qapp, sample_categories):
        """Тест получения DisplayRole."""
        model = CategoriesListModel(sample_categories)
        
        index = model.index(0, 0)
        data = model.data(index, Qt.ItemDataRole.DisplayRole)
        
        assert data == "Category 1"
    
    def test_data_user_role(self, qapp, sample_categories):
        """Тест получения UserRole (id)."""
        model = CategoriesListModel(sample_categories)
        
        index = model.index(1, 0)
        data = model.data(index, Qt.ItemDataRole.UserRole)
        
        assert data == 2
    
    def test_data_tooltip_role(self, qapp, sample_categories):
        """Тест получения ToolTipRole."""
        model = CategoriesListModel(sample_categories)
        
        index = model.index(0, 0)
        data = model.data(index, Qt.ItemDataRole.ToolTipRole)
        
        assert data == "Category 1"
    
    def test_data_decoration_role_default_icon(self, qapp, sample_categories):
        """Тест получения DecorationRole с дефолтной иконкой."""
        model = CategoriesListModel(sample_categories)
        
        index = model.index(0, 0)
        icon = model.data(index, Qt.ItemDataRole.DecorationRole)
        
        assert isinstance(icon, QIcon)
    
    def test_data_invalid_index(self, qapp, sample_categories):
        """Тест получения данных с невалидным индексом."""
        model = CategoriesListModel(sample_categories)
        
        invalid_index = QModelIndex()
        data = model.data(invalid_index, Qt.ItemDataRole.DisplayRole)
        
        assert data is None
    
    def test_data_out_of_range(self, qapp, sample_categories):
        """Тест получения данных с индексом вне диапазона."""
        model = CategoriesListModel(sample_categories)
        
        index = model.index(999, 0)
        data = model.data(index, Qt.ItemDataRole.DisplayRole)
        
        assert data is None


class TestCategoriesListModelRowCount:
    """Тесты подсчёта строк."""
    
    def test_row_count_empty(self, qapp):
        """Тест подсчёта строк пустой модели."""
        model = CategoriesListModel()
        
        assert model.rowCount() == 0
    
    def test_row_count_with_data(self, qapp, sample_categories):
        """Тест подсчёта строк с данными."""
        model = CategoriesListModel(sample_categories)
        
        assert model.rowCount() == 3
    
    def test_row_count_with_parent(self, qapp, sample_categories):
        """Тест подсчёта строк с родительским индексом (должен вернуть 0)."""
        model = CategoriesListModel(sample_categories)
        
        parent_index = model.index(0, 0)
        count = model.rowCount(parent_index)
        
        assert count == 0


class TestCategoriesListModelSetCategories:
    """Тесты установки категорий."""
    
    def test_set_categories_replaces_data(self, qapp, sample_categories):
        """Тест замены данных."""
        model = CategoriesListModel()
        
        assert model.rowCount() == 0
        
        model.set_categories(sample_categories)
        
        assert model.rowCount() == 3
    
    def test_set_categories_skips_invalid_id(self, qapp, caplog):
        """Тест пропуска элементов с некорректным id."""
        model = CategoriesListModel()
        
        invalid_data = [
            {"id": 1, "name": "Valid"},
            {"id": None, "name": "Invalid None"},  # Некорректный
            {"id": "abc", "name": "Invalid String"},  # Некорректный
            {"name": "No ID"},  # Нет id
        ]
        
        model.set_categories(invalid_data)
        
        # Должна остаться только одна валидная категория
        assert model.rowCount() == 1
        assert model.data(model.index(0, 0), Qt.ItemDataRole.DisplayRole) == "Valid"
    
    def test_set_categories_rebuilds_cache(self, qapp, sample_categories):
        """Тест перестроения кэша индексов."""
        model = CategoriesListModel(sample_categories)
        
        # Проверяем исходный кэш
        assert model._row_by_id[1] == 0
        assert model._row_by_id[2] == 1
        
        # Устанавливаем новые данные в обратном порядке
        new_data = [
            {"id": 3, "name": "Category 3", "icon_path": ""},
            {"id": 2, "name": "Category 2", "icon_path": ""},
            {"id": 1, "name": "Category 1", "icon_path": ""},
        ]
        
        model.set_categories(new_data)
        
        # Проверяем обновлённый кэш
        assert model._row_by_id[3] == 0
        assert model._row_by_id[2] == 1
        assert model._row_by_id[1] == 2
    
    def test_set_categories_handles_duplicates(self, qapp):
        """Тест обработки дубликатов id (сохраняется первое вхождение)."""
        model = CategoriesListModel()
        
        data = [
            {"id": 1, "name": "First", "icon_path": ""},
            {"id": 2, "name": "Second", "icon_path": ""},
            {"id": 1, "name": "Duplicate", "icon_path": ""},  # Дубликат
        ]
        
        model.set_categories(data)
        
        # Все 3 элемента добавлены
        assert model.rowCount() == 3
        
        # Кэш указывает на первое вхождение id=1
        assert model._row_by_id[1] == 0
        assert model.data(model.index(0, 0), Qt.ItemDataRole.DisplayRole) == "First"


class TestCategoriesListModelFindRowById:
    """Тесты поиска строки по id."""
    
    def test_find_row_by_id_existing(self, qapp, sample_categories):
        """Тест поиска существующей категории."""
        model = CategoriesListModel(sample_categories)
        
        row = model.find_row_by_id(2)
        
        assert row == 1
        assert model.data(model.index(row, 0), Qt.ItemDataRole.DisplayRole) == "Category 2"
    
    def test_find_row_by_id_non_existing(self, qapp, sample_categories):
        """Тест поиска несуществующей категории."""
        model = CategoriesListModel(sample_categories)
        
        row = model.find_row_by_id(999)
        
        assert row == -1
    
    def test_find_row_by_id_empty_model(self, qapp):
        """Тест поиска в пустой модели."""
        model = CategoriesListModel()
        
        row = model.find_row_by_id(1)
        
        assert row == -1
    
    def test_find_row_by_id_performance(self, qapp):
        """Тест производительности поиска (должен быть O(1))."""
        # Создаём большой датасет
        large_dataset = [
            {"id": i, "name": f"Category {i}", "icon_path": ""}
            for i in range(1000)
        ]
        
        model = CategoriesListModel(large_dataset)
        
        # Поиск должен быть быстрым благодаря кэшу
        import time
        start = time.perf_counter()
        
        for _ in range(100):
            model.find_row_by_id(500)
        
        elapsed = time.perf_counter() - start
        
        # 100 поисков должны занять менее 10ms (очень консервативно)
        assert elapsed < 0.01


class TestCategoriesListModelEdgeCases:
    """Тесты граничных случаев."""
    
    def test_empty_name(self, qapp):
        """Тест категории с пустым именем."""
        model = CategoriesListModel()
        
        data = [{"id": 1, "name": "", "icon_path": ""}]
        model.set_categories(data)
        
        assert model.rowCount() == 1
        assert model.data(model.index(0, 0), Qt.ItemDataRole.DisplayRole) == ""
    
    def test_very_long_name(self, qapp):
        """Тест категории с очень длинным именем."""
        model = CategoriesListModel()
        
        long_name = "A" * 1000
        data = [{"id": 1, "name": long_name, "icon_path": ""}]
        model.set_categories(data)
        
        assert model.data(model.index(0, 0), Qt.ItemDataRole.DisplayRole) == long_name
    
    def test_special_characters_in_name(self, qapp):
        """Тест категории со специальными символами."""
        model = CategoriesListModel()
        
        special_name = "Test <>&\"'🎉"
        data = [{"id": 1, "name": special_name, "icon_path": ""}]
        model.set_categories(data)
        
        assert model.data(model.index(0, 0), Qt.ItemDataRole.DisplayRole) == special_name
    
    def test_negative_id(self, qapp):
        """Тест категории с отрицательным id."""
        model = CategoriesListModel()
        
        data = [{"id": -1, "name": "Negative", "icon_path": ""}]
        model.set_categories(data)
        
        assert model.rowCount() == 1
        assert model.find_row_by_id(-1) == 0
    
    def test_zero_id(self, qapp):
        """Тест категории с id=0."""
        model = CategoriesListModel()
        
        data = [{"id": 0, "name": "Zero", "icon_path": ""}]
        model.set_categories(data)
        
        assert model.rowCount() == 1
        assert model.find_row_by_id(0) == 0


class TestCategoriesListModelSignals:
    """Тесты сигналов модели."""
    
    def test_begin_reset_model_emitted(self, qapp, qtbot, sample_categories):
        """Тест эмиссии сигналов при сбросе модели."""
        model = CategoriesListModel()
        
        # Подключаем spy к сигналам
        with qtbot.waitSignal(model.modelAboutToBeReset):
            with qtbot.waitSignal(model.modelReset):
                model.set_categories(sample_categories)


class TestCategoriesListModelMemory:
    """Тесты управления памятью."""
    
    def test_no_memory_leak_on_reset(self, qapp):
        """Тест отсутствия утечек памяти при повторной установке данных."""
        model = CategoriesListModel()
        
        large_dataset = [
            {"id": i, "name": f"Category {i}", "icon_path": "icon.png"}
            for i in range(1000)
        ]
        
        # Многократно устанавливаем данные
        for _ in range(10):
            model.set_categories(large_dataset)
        
        # Проверяем, что старые данные очищены
        assert len(model._items) == 1000
        assert len(model._row_by_id) == 1000
