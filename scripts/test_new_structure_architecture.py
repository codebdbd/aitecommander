# scripts/test_new_structure_architecture.py
"""
Тестовый скрипт для проверки новой архитектуры StructureBusinessLogic.

Проверяет:
1. Инициализацию всех менеджеров
2. Работу упрощённой сигнальной системы
3. Автоматическую маршрутизацию в legacy сигналы
4. Стандартизированную обработку ошибок через OperationResult
5. Новые возможности (статистика, валидация, экспорт)
6. Управление жизненным циклом (teardown)

Запуск:
    python scripts/test_new_structure_architecture.py
"""

import sys
import logging
from typing import Dict, Any

# Настройка логирования для тестов
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

try:
    from app.controllers.domain.structure.structure_business_new import (
        StructureBusinessLogic, 
        OperationResult, 
        OperationStatus,
        check_compatibility_with_legacy,
        migrate_from_legacy
    )
    from app.models.db import Database
except ImportError as e:
    print(f"Ошибка импорта: {e}")
    print("Убедитесь, что все зависимости доступны")
    sys.exit(1)


class MockDatabase:
    """Заглушка базы данных для тестирования."""
    def __init__(self):
        self.connected = True
    
    def execute(self, query, params=None):
        return []
    
    def fetchall(self):
        return []
    
    def fetchone(self):
        return None


def test_initialization():
    """Тест инициализации контроллера."""
    print("\n=== Тест инициализации ===")
    
    try:
        db = MockDatabase()
        logger = logging.getLogger("test")
        
        controller = StructureBusinessLogic(db, logger)
        
        # Проверяем наличие менеджеров
        assert hasattr(controller, '_sphere_manager'), "SphereManager не инициализирован"
        assert hasattr(controller, '_section_manager'), "SectionManager не инициализирован"
        assert hasattr(controller, '_category_manager'), "CategoryManager не инициализирован"
        assert hasattr(controller, '_signal_manager'), "StructureSignalManager не инициализирован"
        assert hasattr(controller, '_async_manager'), "AsyncOperationsManager не инициализирован"
        
        print("✓ Все менеджеры успешно инициализированы")
        
        # Проверяем сигналы
        signal_names = [
            'data_changed', 'selection_changed', 'error_occurred', 'async_operation_finished',
            'structure_loaded', 'active_sphere_changed', 'item_added', 'item_updated', 
            'item_deleted', 'sections_loaded', 'section_selected', 'category_selected',
            'spheres_loaded', 'item_created', 'error', 'simple_error'
        ]
        
        for signal_name in signal_names:
            assert hasattr(controller, signal_name), f"Сигнал {signal_name} не найден"
        
        print("✓ Все сигналы присутствуют")
        
        return controller
        
    except Exception as e:
        print(f"✗ Ошибка инициализации: {e}")
        return None


def test_operation_result():
    """Тест системы OperationResult."""
    print("\n=== Тест OperationResult ===")
    
    # Успешный результат
    success_result = OperationResult(OperationStatus.SUCCESS, {"id": 1}, "Успех")
    assert success_result.is_success, "is_success должен быть True"
    assert not success_result.is_error, "is_error должен быть False"
    print("✓ Успешный OperationResult работает корректно")
    
    # Результат с ошибкой
    error_result = OperationResult(OperationStatus.ERROR, error_details="Тестовая ошибка")
    assert not error_result.is_success, "is_success должен быть False"
    assert error_result.is_error, "is_error должен быть True"
    print("✓ OperationResult с ошибкой работает корректно")


def test_signal_routing(controller):
    """Тест маршрутизации сигналов."""
    print("\n=== Тест маршрутизации сигналов ===")
    
    if not controller:
        print("✗ Контроллер не инициализирован")
        return
    
    # Счётчики для проверки получения сигналов
    signals_received = {
        'data_changed': 0,
        'item_added': 0,
        'item_created': 0,
        'selection_changed': 0,
        'active_sphere_changed': 0,
        'error_occurred': 0,
        'error': 0,
        'simple_error': 0
    }
    
    # Подписываемся на сигналы
    controller.data_changed.connect(lambda op, data: signals_received.update({'data_changed': signals_received['data_changed'] + 1}))
    controller.item_added.connect(lambda t, p, d: signals_received.update({'item_added': signals_received['item_added'] + 1}))
    controller.item_created.connect(lambda t, p, d: signals_received.update({'item_created': signals_received['item_created'] + 1}))
    controller.selection_changed.connect(lambda t, i, d: signals_received.update({'selection_changed': signals_received['selection_changed'] + 1}))
    controller.active_sphere_changed.connect(lambda i: signals_received.update({'active_sphere_changed': signals_received['active_sphere_changed'] + 1}))
    controller.error_occurred.connect(lambda t, m: signals_received.update({'error_occurred': signals_received['error_occurred'] + 1}))
    controller.error.connect(lambda t, m: signals_received.update({'error': signals_received['error'] + 1}))
    controller.simple_error.connect(lambda m: signals_received.update({'simple_error': signals_received['simple_error'] + 1}))
    
    # Эмитируем основные сигналы
    controller._signal_manager.emit_data_changed("item_added", item_type="section", parent_id=1, item_data={"id": 2})
    controller._signal_manager.emit_selection_changed("sphere", 1)
    controller._signal_manager.emit_error("Тестовая ошибка", "Сообщение об ошибке")
    
    # Проверяем маршрутизацию
    expected_counts = {
        'data_changed': 1,
        'item_added': 1,
        'item_created': 1,  # Должен быть эмитирован автоматически
        'selection_changed': 1,
        'active_sphere_changed': 1,  # Должен быть эмитирован автоматически
        'error_occurred': 1,
        'error': 1,  # Должен быть эмитирован автоматически
        'simple_error': 1  # Должен быть эмитирован автоматически
    }
    
    for signal_name, expected_count in expected_counts.items():
        actual_count = signals_received[signal_name]
        if actual_count == expected_count:
            print(f"✓ {signal_name}: получено {actual_count} сигналов")
        else:
            print(f"✗ {signal_name}: ожидалось {expected_count}, получено {actual_count}")


def test_new_features(controller):
    """Тест новых возможностей."""
    print("\n=== Тест новых возможностей ===")
    
    if not controller:
        print("✗ Контроллер не инициализирован")
        return
    
    # Тест статистики
    try:
        stats = controller.get_structure_stats()
        assert isinstance(stats, dict), "get_structure_stats должен возвращать dict"
        print("✓ get_structure_stats работает")
    except Exception as e:
        print(f"✗ Ошибка get_structure_stats: {e}")
    
    # Тест валидации
    try:
        validation = controller.validate_structure_integrity()
        assert isinstance(validation, dict), "validate_structure_integrity должен возвращать dict"
        assert 'valid' in validation, "Результат валидации должен содержать поле 'valid'"
        print("✓ validate_structure_integrity работает")
    except Exception as e:
        print(f"✗ Ошибка validate_structure_integrity: {e}")
    
    # Тест экспорта
    try:
        config = controller.export_structure_config()
        assert isinstance(config, dict), "export_structure_config должен возвращать dict"
        print("✓ export_structure_config работает")
    except Exception as e:
        print(f"✗ Ошибка export_structure_config: {e}")


def test_compatibility():
    """Тест совместимости с legacy версией."""
    print("\n=== Тест совместимости ===")
    
    try:
        compatibility = check_compatibility_with_legacy()
        assert isinstance(compatibility, dict), "check_compatibility_with_legacy должен возвращать dict"
        assert compatibility.get('compatible', False), "Должна быть обеспечена совместимость"
        print("✓ Совместимость с legacy версией подтверждена")
    except Exception as e:
        print(f"✗ Ошибка проверки совместимости: {e}")


def test_lifecycle(controller):
    """Тест управления жизненным циклом."""
    print("\n=== Тест управления жизненным циклом ===")
    
    if not controller:
        print("✗ Контроллер не инициализирован")
        return
    
    try:
        # Тест teardown
        controller.teardown()
        print("✓ teardown выполнен без ошибок")
    except Exception as e:
        print(f"✗ Ошибка teardown: {e}")


def main():
    """Основная функция тестирования."""
    print("Запуск тестов новой архитектуры StructureBusinessLogic")
    print("=" * 60)
    
    # Тест OperationResult
    test_operation_result()
    
    # Тест инициализации
    controller = test_initialization()
    
    # Тест маршрутизации сигналов
    test_signal_routing(controller)
    
    # Тест новых возможностей
    test_new_features(controller)
    
    # Тест совместимости
    test_compatibility()
    
    # Тест жизненного цикла
    test_lifecycle(controller)
    
    print("\n" + "=" * 60)
    print("Тестирование завершено")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
