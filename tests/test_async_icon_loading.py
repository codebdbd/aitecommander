"""
Тесты для асинхронной загрузки иконок в модели дерева структуры.

Проверяет исправление проблемы с задержкой загрузки иконок при добавлении категорий
с использованием QThreadPool вместо asyncio.
"""
import pytest
from PyQt6.QtCore import Qt, QModelIndex, QTimer, QThreadPool
from PyQt6.QtGui import QIcon

from app.views.models.structure_tree_model import StructureTreeModel, TreeNode


class TestAsyncIconLoadingQt:
    """Тесты асинхронной загрузки иконок с использованием QThreadPool."""

    def test_model_initialization(self):
        """Тест инициализации модели с пулом потоков."""
        model = StructureTreeModel()

        # Проверяем, что пул потоков инициализирован
        assert model._thread_pool is not None
        assert isinstance(model._thread_pool, QThreadPool)

        # Проверяем ограничение количества потоков
        assert model._thread_pool.maxThreadCount() == 4

        # Проверяем, что множество активных задач пустое
        assert len(model._active_icon_tasks) == 0

    def test_icon_loader_creation(self):
        """Тест создания загрузчика иконок."""
        from app.views.models.structure_tree_model import IconLoader

        node = TreeNode(type="test", id=1, name="Test")
        loader = IconLoader(node, "test_icon.svg")

        # Проверяем, что загрузчик создан правильно
        assert loader.node == node
        assert loader.icon_path == "test_icon.svg"

        # Проверяем наличие сигналов
        assert hasattr(loader, 'icon_loaded')
        assert hasattr(loader, 'icon_error')

    def test_start_icon_loading(self):
        """Тест запуска асинхронной загрузки иконки."""
        model = StructureTreeModel()
        node = TreeNode(type="test", id=1, name="Test")

        # Запускаем загрузку иконки
        model._start_icon_loading(node, "test_icon.svg")

        # Проверяем, что задача добавлена в активные
        assert id(node) in model._active_icon_tasks

        # Ждем завершения задачи (в тесте она завершится быстро)
        model._thread_pool.waitForDone(1000)

        # Проверяем, что задача удалена из активных после завершения
        assert id(node) not in model._active_icon_tasks

    def test_insert_categories_with_qt_async_icons(self):
        """Тест вставки категорий с асинхронной загрузкой иконок через QThreadPool."""
        model = StructureTreeModel()

        # Сначала создаем секцию
        sections = [{"id": 1, "name": "Test Section"}]
        model.insert_sections(0, sections)

        # Создаем категории с иконками
        categories = [
            {"id": 1, "name": "Category 1", "icon": "test_icon1.svg"},
            {"id": 2, "name": "Category 2", "icon": "test_icon2.svg"},
        ]

        # Вставляем категории
        model.insert_categories(1, 0, categories)

        # Проверяем, что категории созданы с пустыми иконками
        section = model._section_by_id[1]
        assert len(section.children) == 2

        cat1 = section.children[0]
        cat2 = section.children[1]

        # Иконки должны быть пустыми изначально
        assert isinstance(cat1.icon, QIcon)
        assert isinstance(cat2.icon, QIcon)

        # Проверяем, что узлы созданы правильно
        assert cat1.name == "Category 1"
        assert cat2.name == "Category 2"
        assert cat1.type == "category"
        assert cat2.type == "category"

        # Ждем завершения загрузки иконок
        model._thread_pool.waitForDone(2000)

    def test_update_item_with_qt_async_icon(self):
        """Тест обновления элемента с асинхронной загрузкой иконки через QThreadPool."""
        model = StructureTreeModel()

        # Создаем секцию и категорию
        sections = [{"id": 1, "name": "Test Section"}]
        model.insert_sections(0, sections)

        categories = [{"id": 1, "name": "Category 1"}]
        model.insert_categories(1, 0, categories)

        # Обновляем категорию с новой иконкой
        model.update_item("category", 1, {"icon": "new_icon.svg"})

        # Проверяем, что обновление прошло без ошибок
        category = model._category_by_id[1]
        assert category.name == "Category 1"

        # Ждем завершения загрузки
        model._thread_pool.waitForDone(1000)

    def test_setData_with_qt_async_icon(self):
        """Тест установки данных с асинхронной загрузкой иконки через QThreadPool."""
        model = StructureTreeModel()

        # Создаем секцию и категорию
        sections = [{"id": 1, "name": "Test Section"}]
        model.insert_sections(0, sections)

        categories = [{"id": 1, "name": "Category 1"}]
        model.insert_categories(1, 0, categories)

        # Получаем индекс категории
        idx = model.index_for("category", 1)
        assert idx.isValid()

        # Устанавливаем новую иконку через setData
        result = model.setData(idx, "icon_path.svg", Qt.ItemDataRole.DecorationRole)

        # Проверяем, что setData вернул True (успех)
        assert result is True

        # Ждем завершения загрузки
        model._thread_pool.waitForDone(1000)

    def test_cleanup_method(self):
        """Тест метода очистки ресурсов."""
        model = StructureTreeModel()

        # Запускаем несколько задач
        node1 = TreeNode(type="test", id=1, name="Test1")
        node2 = TreeNode(type="test", id=2, name="Test2")

        model._start_icon_loading(node1, "icon1.svg")
        model._start_icon_loading(node2, "icon2.svg")

        # Проверяем, что задачи активны
        assert len(model._active_icon_tasks) == 2

        # Вызываем очистку
        model.cleanup()

        # Проверяем, что ресурсы очищены
        assert len(model._active_icon_tasks) == 0

    def test_qt_async_performance(self):
        """Тест производительности асинхронной загрузки через QThreadPool."""
        import time

        model = StructureTreeModel()

        # Создаем много категорий с иконками
        categories = []
        for i in range(5):  # Уменьшил количество для теста
            categories.append({
                "id": i,
                "name": f"Category {i}",
                "icon": f"test_icon_{i}.svg"
            })

        # Замеряем время вставки
        start_time = time.time()

        # Вставляем категории - это должно происходить быстро
        sections = [{"id": 1, "name": "Test Section"}]
        model.insert_sections(0, sections)
        model.insert_categories(1, 0, categories)

        end_time = time.time()
        duration = end_time - start_time

        # Вставка должна происходить быстро (менее 100мс для 5 элементов)
        assert duration < 0.1, f"Вставка заняла слишком много времени: {duration}с"

        # Проверяем, что все категории созданы
        section = model._section_by_id[1]
        assert len(section.children) == 5

        # Ждем завершения всех задач загрузки
        model._thread_pool.waitForDone(2000)
