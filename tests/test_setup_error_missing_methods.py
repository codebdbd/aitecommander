from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.controllers.system.window_controllers_setup import (
    DatabaseEventHandler,
    SetupError,
    _connect_structure_signals,
    _resolve_structure_loader,
)
from app.controllers.ui.links.handlers import LinksUIHandlers


def test_structure_business_without_required_methods_raises_setup_error():
    """Тест проверяет, что StructureBusinessLogic без необходимых методов вызывает SetupError."""
    # Создаем мок StructureBusinessLogic без нужных методов
    structure_business = SimpleNamespace()
    # Добавляем только сигнал, но не методы обработки
    structure_business.active_sphere_changed = Mock()
    structure_business.active_sphere_changed.connect = Mock()
    
    window = SimpleNamespace()
    window._update_left_panel_style = Mock()
    
    top_panels_controller = Mock()
    spheres_controller = Mock()
    
    with pytest.raises(SetupError) as exc_info:
        _connect_structure_signals(
            window,
            top_panels_controller=top_panels_controller,
            structure_business=structure_business,
            structure=Mock(),
            spheres_controller=spheres_controller,
        )
    
    assert "must provide on_active_sphere_changed, load_structure_async, or load_structure" in str(exc_info.value)


def test_structure_business_with_non_callable_handler_raises_setup_error():
    """Тест проверяет, что StructureBusinessLogic с некорректным on_active_sphere_changed вызывает SetupError."""
    structure_business = SimpleNamespace()
    structure_business.on_active_sphere_changed = "not_callable"  # Не callable
    structure_business.active_sphere_changed = Mock()
    structure_business.active_sphere_changed.connect = Mock()
    
    window = SimpleNamespace()
    window._update_left_panel_style = Mock()
    
    top_panels_controller = Mock()
    spheres_controller = Mock()
    
    with pytest.raises(SetupError) as exc_info:
        _connect_structure_signals(
            window,
            top_panels_controller=top_panels_controller,
            structure_business=structure_business,
            structure=Mock(),
            spheres_controller=spheres_controller,
        )
    
    assert "on_active_sphere_changed must be callable" in str(exc_info.value)


def test_update_controllers_without_links_actions_raises_setup_error():
    """Тест проверяет, что _update_controllers_with_new_db без links_actions вызывает SetupError."""
    window = SimpleNamespace()
    new_db = Mock()
    
    with pytest.raises(SetupError) as exc_info:
        DatabaseEventHandler._update_controllers_with_new_db(window, new_db, links_actions=None)
    
    assert "links_actions is required when switching database" in str(exc_info.value)


def test_update_controllers_with_invalid_links_actions_raises_setup_error():
    """Тест проверяет, что _update_controllers_with_new_db с некорректным links_actions вызывает SetupError."""
    window = SimpleNamespace()
    new_db = Mock()
    
    # links_actions без атрибута links
    links_actions = SimpleNamespace()
    
    with pytest.raises(SetupError) as exc_info:
        DatabaseEventHandler._update_controllers_with_new_db(window, new_db, links_actions=links_actions)
    
    assert "links_actions.links is required when switching database" in str(exc_info.value)


def test_links_ui_handlers_update_table_contract_error_not_suppressed():
    """Тест проверяет, что ошибки контракта в _update_table не подавляются."""
    # Создаем мок-зависимости
    controller = Mock()
    link_operations = Mock()
    links_table_controller = Mock()
    category_provider = Mock()
    
    # Настраиваем category_provider
    category_provider.get_current_category_id = Mock(return_value=1)
    
    # Создаем LinksUIHandlers
    handlers = LinksUIHandlers(
        controller,
        link_operations=link_operations,
        links_table_controller=links_table_controller,
        category_provider=category_provider,
    )
    
    # Настраиваем links_table_controller для выброса ValueError
    links_table_controller.on_links_loaded.side_effect = ValueError("Contract violation")
    
    # Проверяем, что ValueError не подавляется
    with pytest.raises(ValueError) as exc_info:
        handlers._update_table([], 1, 123)
    
    assert "Contract violation" in str(exc_info.value)


def test_links_ui_handlers_update_table_runtime_error_not_suppressed():
    """Тест проверяет, что RuntimeError в _update_table не подавляется."""
    # Создаем мок-зависимости
    controller = Mock()
    link_operations = Mock()
    links_table_controller = Mock()
    category_provider = Mock()
    
    # Настраиваем category_provider
    category_provider.get_current_category_id = Mock(return_value=1)
    
    # Создаем LinksUIHandlers
    handlers = LinksUIHandlers(
        controller,
        link_operations=link_operations,
        links_table_controller=links_table_controller,
        category_provider=category_provider,
    )
    
    # Настраиваем links_table_controller для выброса RuntimeError
    links_table_controller.on_links_loaded.side_effect = RuntimeError("Runtime issue")
    
    # Проверяем, что RuntimeError не подавляется
    with pytest.raises(RuntimeError) as exc_info:
        handlers._update_table([], 1, 123)
    
    assert "Runtime issue" in str(exc_info.value)


def test_links_ui_handlers_update_table_unexpected_error_not_suppressed():
    """Тест проверяет, что неожиданные ошибки в _update_table не подавляются."""
    # Создаем мок-зависимости
    controller = Mock()
    link_operations = Mock()
    links_table_controller = Mock()
    category_provider = Mock()
    
    # Настраиваем category_provider
    category_provider.get_current_category_id = Mock(return_value=1)
    
    # Создаем LinksUIHandlers
    handlers = LinksUIHandlers(
        controller,
        link_operations=link_operations,
        links_table_controller=links_table_controller,
        category_provider=category_provider,
    )
    
    # Настраиваем links_table_controller для выброса неожиданной ошибки
    links_table_controller.on_links_loaded.side_effect = AttributeError("Unexpected error")
    
    # Проверяем, что AttributeError не подавляется
    with pytest.raises(AttributeError) as exc_info:
        handlers._update_table([], 1, 123)
    
    assert "Unexpected error" in str(exc_info.value)


def test_resolve_structure_loader_without_methods_raises_setup_error():
    """Тест проверяет, что _resolve_structure_loader без методов загрузки вызывает SetupError."""
    # Создаем объект без методов load_structure_async и load_structure
    structure_business = SimpleNamespace()
    
    with pytest.raises(SetupError) as exc_info:
        _resolve_structure_loader(structure_business)
    
    assert "must provide load_structure_async() or load_structure()" in str(exc_info.value)


def test_resolve_structure_loader_with_non_callable_async_raises_setup_error():
    """Тест проверяет, что _resolve_structure_loader с некорректным load_structure_async вызывает SetupError."""
    structure_business = SimpleNamespace()
    structure_business.load_structure_async = "not_callable"  # Не callable
    
    with pytest.raises(SetupError) as exc_info:
        _resolve_structure_loader(structure_business)
    
    assert "load_structure_async must be callable" in str(exc_info.value)


def test_resolve_structure_loader_with_non_callable_sync_raises_setup_error():
    """Тест проверяет, что _resolve_structure_loader с некорректным load_structure вызывает SetupError."""
    structure_business = SimpleNamespace()
    structure_business.load_structure = "not_callable"  # Не callable
    
    with pytest.raises(SetupError) as exc_info:
        _resolve_structure_loader(structure_business)
    
    assert "load_structure must be callable" in str(exc_info.value)


def test_resolve_structure_loader_prefers_async_method():
    """Тест проверяет, что _resolve_structure_loader предпочитает async метод."""
    structure_business = SimpleNamespace()
    
    async_mock = Mock()
    sync_mock = Mock()
    
    structure_business.load_structure_async = async_mock
    structure_business.load_structure = sync_mock
    
    result = _resolve_structure_loader(structure_business)
    
    assert result is async_mock


def test_resolve_structure_loader_fallback_to_sync():
    """Тест проверяет, что _resolve_structure_loader использует sync метод при отсутствии async."""
    structure_business = SimpleNamespace()
    
    sync_mock = Mock()
    structure_business.load_structure = sync_mock
    
    result = _resolve_structure_loader(structure_business)
    
    assert result is sync_mock
