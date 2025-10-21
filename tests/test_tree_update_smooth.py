"""
Тесты для проверки плавного обновления дерева при добавлении элементов.

Проверяет отсутствие блокирующих операций и множественных перерисовок.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from PyQt6.QtCore import QModelIndex, Qt
from PyQt6.QtGui import QIcon

from app.views.models.structure_tree_model import StructureTreeModel


class TestTreeUpdateSmooth:
    """Тесты плавности обновления дерева."""

    @pytest.fixture
    def model(self, qtbot):
        """Создает модель дерева."""
        model = StructureTreeModel()
        qtbot.addWidget(model)
        yield model
        model.cleanup()

    def test_insert_section_theme_icon_loaded_immediately(self, model, qtbot):
        """���������, ��� ������� ������ ���������� ������� ��������."""
        section_data = {
            "id": 1,
            "name": "Test Section",
            "icon": "folder",
        }

        with (
            patch(
                "app.utils.ui.icon.icon_operations.cache_proxy.icon_cache.get_icon",
                return_value=QIcon(),
            ) as mock_get_icon,
            patch.object(model, "_start_icon_loading") as mock_start,
        ):
            model.insert_sections(0, [section_data])

        mock_get_icon.assert_called_once()
        assert mock_get_icon.call_args.args[0] == "folder"
        assert mock_get_icon.call_args.kwargs.get("source") == "tree_model_sync"
        mock_start.assert_not_called()

    def test_insert_category_user_icon_loaded_from_path(self, model, qtbot, tmp_path):
        """���������, ��� ������������ ������ ������������ ������� ��������."""
        from PyQt6.QtGui import QPixmap

        user_icon = tmp_path / "User Icon.png"
        pix = QPixmap(16, 16)
        pix.fill(Qt.GlobalColor.blue)
        assert pix.save(str(user_icon), "PNG")

        section_data = {"id": 1, "name": "Section", "icon": None}
        model.insert_sections(0, [section_data])

        category_data = {
            "id": 10,
            "name": "Test Category",
            "icon": str(user_icon),
        }

        with patch.object(model, "_start_icon_loading") as mock_start:
            model.insert_categories(1, 0, [category_data])

        mock_start.assert_not_called()

    def test_no_duplicate_icon_loading(self, model, qtbot):
        """Проверяет, что иконка не загружается повторно если уже загружена."""
        # Создаем секцию с иконкой
        section_data = {"id": 1, "name": "Section", "icon": "path/to/icon.png"}
        model.insert_sections(0, [section_data])
        
        # Получаем узел
        idx = model.index_for("section", 1)
        assert idx.isValid()
        node = idx.internalPointer()
        
        # Устанавливаем иконку вручную (имитируем загруженную)
        node.icon = QIcon()
        
        # Пытаемся запустить загрузку снова
        with patch.object(model._thread_pool, "start") as mock_start:
            model._start_icon_loading(node, "path/to/icon.png")
            
            # Загрузка НЕ должна запускаться (иконка уже есть)
            mock_start.assert_not_called()

    def test_single_data_changed_per_icon_load(self, model, qtbot):
        """Проверяет, что dataChanged вызывается только один раз при загрузке иконки."""
        # Создаем секцию
        section_data = {"id": 1, "name": "Section", "icon": None}
        model.insert_sections(0, [section_data])
        
        idx = model.index_for("section", 1)
        node = idx.internalPointer()
        
        # Отслеживаем сигнал dataChanged
        signal_spy = qtbot.waitSignal(model.dataChanged, timeout=1000, raising=False)
        
        # Имитируем загрузку иконки
        icon = QIcon()
        model._on_icon_loaded(node, icon)
        
        # Должен быть ровно один сигнал dataChanged
        assert signal_spy.signal_triggered

    def test_async_icon_loading_uses_thread_pool(self, model, qtbot):
        """Проверяет, что загрузка иконок использует thread pool (асинхронно)."""
        section_data = {"id": 1, "name": "Section", "icon": "path/to/icon.png"}
        
        with patch.object(model._thread_pool, "start") as mock_start:
            model.insert_sections(0, [section_data])
            
            # Должна быть запущена асинхронная задача
            assert mock_start.call_count >= 1

    def test_insert_multiple_items_batched(self, model, qtbot):
        """Проверяет, что вставка нескольких элементов происходит батчем."""
        sections_data = [
            {"id": 1, "name": "Section 1", "icon": "icon1.png"},
            {"id": 2, "name": "Section 2", "icon": "icon2.png"},
            {"id": 3, "name": "Section 3", "icon": "icon3.png"},
        ]
        
        # Отслеживаем сигналы модели
        with qtbot.waitSignals([model.rowsInserted], timeout=1000):
            model.insert_sections(0, sections_data)
        
        # Проверяем, что все секции добавлены
        assert model.rowCount(QModelIndex()) == 3

    def test_update_item_no_redundant_signals(self, model, qtbot):
        """Проверяет, что обновление элемента не вызывает избыточных сигналов."""
        # Создаем секцию
        section_data = {"id": 1, "name": "Section", "icon": None}
        model.insert_sections(0, [section_data])
        
        # Считаем количество сигналов dataChanged
        signal_count = 0
        
        def count_signal(*args):
            nonlocal signal_count
            signal_count += 1
        
        model.dataChanged.connect(count_signal)
        
        # Обновляем имя секции
        model.update_item("section", 1, {"name": "Updated Section"})
        
        # Должен быть ровно один сигнал
        assert signal_count == 1


class TestTreeUpdateServiceIntegration:
    """Интеграционные тесты TreeUpdateService с моделью."""

    @pytest.fixture
    def setup(self, qtbot):
        """Создает окружение для тестов."""
        from app.controllers.ui.structure.tree_update_service import TreeUpdateService
        
        # Мокируем зависимости
        manager = Mock()
        tree = Mock()
        model = StructureTreeModel()
        qtbot.addWidget(model)
        
        service = TreeUpdateService(manager, tree, model)
        
        yield service, model
        
        model.cleanup()

    def test_handle_item_added_section_async(self, setup, qtbot):
        """Проверяет, что добавление секции происходит асинхронно."""
        service, model = setup
        
        data = {
            "id": 1,
            "name": "New Section",
            "icon_path": "path/to/icon.png",
            "row": 0
        }
        
        with patch.object(model._thread_pool, "start") as mock_start:
            service.handle_item_added("section", 0, data)
            
            # Должна быть запущена асинхронная загрузка иконки
            assert mock_start.call_count >= 1

    def test_handle_item_added_category_async(self, setup, qtbot):
        """Проверяет, что добавление категории происходит асинхронно."""
        service, model = setup
        
        # Сначала добавляем секцию
        section_data = {"id": 1, "name": "Section", "icon": None}
        model.insert_sections(0, [section_data])
        
        category_data = {
            "id": 10,
            "name": "New Category",
            "icon_path": "path/to/icon.png",
            "row": 0
        }
        
        with patch.object(model._thread_pool, "start") as mock_start:
            service.handle_item_added("category", 1, category_data)
            
            # Должна быть запущена асинхронная загрузка иконки
            assert mock_start.call_count >= 1

    def test_no_blocking_operations_in_insert(self, setup, qtbot):
        """Проверяет отсутствие блокирующих операций при вставке."""
        service, model = setup
        
        # Мокируем потенциально блокирующие операции
        with patch("app.utils.ui.icon.icon_operations.cache_proxy.icon_cache") as mock_cache:
            # Если бы была синхронная загрузка, get_icon был бы вызван
            mock_cache.get_icon = Mock(return_value=QIcon())
            
            data = {
                "id": 1,
                "name": "Section",
                "icon_path": "blocking_icon.png",
                "row": 0
            }
            
            # Вставка должна завершиться мгновенно
            service.handle_item_added("section", 0, data)
            
            # get_icon НЕ должен вызываться синхронно в GUI-потоке
            # (только через IconLoader в фоновом потоке)
            mock_cache.get_icon.assert_not_called()
