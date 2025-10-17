"""Тест для проверки отсутствия гонки при shutdown StructureTreeModel."""

import pytest
from PyQt6.QtCore import QCoreApplication
from app.views.models.structure_tree_model import StructureTreeModel, TreeNode


def test_icon_loading_shutdown_race(qtbot):
    """Проверка что shutdown корректно останавливает загрузку иконок."""
    model = StructureTreeModel()
    
    # Создать 100 узлов с иконками
    sections = [
        {"id": i, "name": f"Section {i}", "icon": f"icon_{i}.png", "categories": []}
        for i in range(100)
    ]
    model.set_snapshot(sections)
    
    # Немедленно вызвать cleanup (имитация быстрого закрытия окна)
    model.cleanup()
    
    # Подождать завершения всех задач
    model._thread_pool.waitForDone(6000)
    
    # Проверить что все задачи завершены
    assert len(model._active_icon_tasks) == 0
    assert model._shutdown is True


def test_no_icon_loading_after_shutdown(qtbot):
    """Проверка что после shutdown новые задачи не запускаются."""
    model = StructureTreeModel()
    model.cleanup()
    
    node = TreeNode(type="section", id=1, name="Test")
    model._start_icon_loading(node, "test.png")
    
    # Проверить что задача не была добавлена
    assert id(node) not in model._active_icon_tasks


def test_concurrent_icon_loading_and_cleanup(qtbot):
    """Проверка что cleanup безопасен при активной загрузке иконок."""
    model = StructureTreeModel()
    
    # Создать много узлов для параллельной загрузки
    sections = [
        {
            "id": i,
            "name": f"Section {i}",
            "icon": f"icon_{i}.png",
            "categories": [
                {"id": i * 100 + j, "name": f"Cat {j}", "icon": f"cat_{j}.png"}
                for j in range(10)
            ],
        }
        for i in range(20)
    ]
    model.set_snapshot(sections)
    
    # Дать задачам начать выполнение
    QCoreApplication.processEvents()
    
    # Немедленно вызвать cleanup
    model.cleanup()
    
    # Проверить что cleanup завершился корректно
    assert model._shutdown is True
    assert len(model._active_icon_tasks) == 0
    
    # Проверить что новые задачи не запускаются
    node = TreeNode(type="section", id=999, name="New")
    model._start_icon_loading(node, "new.png")
    assert id(node) not in model._active_icon_tasks
