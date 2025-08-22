# app/controllers/structure_modules/legacy_support.py

"""Модуль для поддержки устаревших методов и обратной совместимости."""

import inspect
import logging
import threading
import warnings
from typing import Any, Dict, List, Tuple

from .base import StructureItemType, ValidationError
from .validation import validate_item_data


class LegacySupport:
    """
    Класс для поддержки устаревших методов и обратной совместимости.
    
    Этот класс предназначен для плавного перехода от старых методов API
    к новым. Все методы помечены как устаревшие и будут удалены в версии 2.0.
    
    Примеры использования:
        # Старый способ (устаревший):
        legacy = LegacySupport(sphere_ops, section_ops, category_ops)
        is_valid, error = legacy.validate_section_data(data)
        
        # Новый способ (рекомендуемый):
        try:
            validate_item_data(data, StructureItemType.SECTION)
        except ValidationError as e:
            # обработка ошибки
    
    План миграции:
        - v1.1: Добавлены предупреждения об устаревании
        - v1.5: Методы помечены как deprecated в документации
        - v2.0: Полное удаление legacy методов
    """
    
    # Версия модуля для отслеживания изменений
    __version__ = "1.1.0"
    
    def __init__(
        self,
        sphere_operations,
        section_operations,
        category_operations
    ) -> None:
        """
        Инициализация поддержки устаревших методов.
        
        Args:
            sphere_operations: Операции со сферами
            section_operations: Операции с разделами  
            category_operations: Операции с категориями
        """
        self.sphere_operations = sphere_operations
        self.section_operations = section_operations
        self.category_operations = category_operations
        self._logger = logging.getLogger(__name__)
        
        # Счетчик использования для аналитики
        self._usage_stats = {
            'validate_section_data': 0,
            'validate_category_data': 0,
            'get_sphere_data': 0
        }
        # Блокировка для потокобезопасного инкремента счётчиков
        self._stats_lock = threading.Lock()
        # Детальная статистика по вызывающему модулю/функции
        # Формат: { method_name: { "module:function": count } }
        self._usage_stats_by_caller: Dict[str, Dict[str, int]] = {
            'validate_section_data': {},
            'validate_category_data': {},
            'get_sphere_data': {},
        }
    
    def _get_caller_label(self) -> str:
        """Определяет метку вызывающего (module:function), пропуская внутренние кадры."""
        try:
            # Пропускаем текущую функцию и _log_deprecation_warning
            for frame_info in inspect.stack()[2:]:
                mod = frame_info.frame.f_globals.get('__name__', '')
                if mod and not mod.endswith('legacy_support'):
                    func = frame_info.function or 'unknown'
                    return f"{mod}:{func}"
        except Exception:
            pass
        return "unknown:unknown"
    
    def _log_deprecation_warning(self, method_name: str, replacement: str) -> None:
        """
        Логирует предупреждение об использовании устаревшего метода.
        
        Args:
            method_name: Имя устаревшего метода
            replacement: Рекомендуемая замена
        """
        # Определяем метку вызывающего для логов и статистики
        caller_label = self._get_caller_label()
        # Потокобезопасно инкрементируем счётчик использования
        try:
            with self._stats_lock:
                self._usage_stats[method_name] += 1
                # Записываем статистику по вызывающему
                bucket = self._usage_stats_by_caller.get(method_name)
                if bucket is not None:
                    bucket[caller_label] = bucket.get(caller_label, 0) + 1
        except Exception:
            # Не допускаем срыва из-за аналитики
            pass
        
        warnings.warn(
            f"Метод {method_name} устарел и будет удален в версии 2.0. "
            f"Используйте {replacement}",
            DeprecationWarning,
            stacklevel=3
        )
        # Дублируем предупреждение в лог, чтобы не зависеть от фильтров warnings
        try:
            self._logger.warning(
                "[DEPRECATED] %s: используйте %s. Метод будет удалён в v2.0. caller=%s",
                method_name,
                replacement,
                caller_label,
            )
        except Exception:
            pass
    
    def _validate_data_generic(
        self, 
        data: Dict[str, Any], 
        item_type: StructureItemType,
        method_name: str
    ) -> Tuple[bool, str]:
        """
        Универсальный метод валидации данных.
        
        Args:
            data: Данные для валидации
            item_type: Тип структурного элемента
            method_name: Имя вызывающего метода для логирования
            
        Returns:
            Tuple[bool, str]: (результат_валидации, сообщение_об_ошибке)
        """
        try:
            validate_item_data(data, item_type)
            return True, ""
        except ValidationError as e:
            return False, str(e)
        except Exception as e:
            # Дополнительная обработка неожиданных ошибок
            return False, f"Неожиданная ошибка валидации: {str(e)}"
    
    def validate_section_data(self, data: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Устаревший метод валидации данных раздела.
        
        Args:
            data: Словарь с данными раздела для валидации
            
        Returns:
            Tuple[bool, str]: (True если валидация прошла, сообщение об ошибке)
            
        Deprecated:
            Используйте validate_item_data(data, StructureItemType.SECTION) вместо этого метода.
            
        Examples:
            >>> legacy = LegacySupport(sphere_ops, section_ops, category_ops)
            >>> is_valid, error = legacy.validate_section_data({'name': 'Test'})
            >>> if not is_valid:
            ...     print(f"Ошибка: {error}")
        """
        self._log_deprecation_warning(
            'validate_section_data',
            'validate_item_data(data, StructureItemType.SECTION)'
        )
        
        return self._validate_data_generic(
            data, 
            StructureItemType.SECTION, 
            'validate_section_data'
        )
    
    def validate_category_data(self, data: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Устаревший метод валидации данных категории.
        
        Args:
            data: Словарь с данными категории для валидации
            
        Returns:
            Tuple[bool, str]: (True если валидация прошла, сообщение об ошибке)
            
        Deprecated:
            Используйте validate_item_data(data, StructureItemType.CATEGORY) вместо этого метода.
            
        Examples:
            >>> legacy = LegacySupport(sphere_ops, section_ops, category_ops)
            >>> is_valid, error = legacy.validate_category_data({'name': 'Test'})
            >>> if not is_valid:
            ...     print(f"Ошибка: {error}")
        """
        self._log_deprecation_warning(
            'validate_category_data',
            'validate_item_data(data, StructureItemType.CATEGORY)'
        )
        
        return self._validate_data_generic(
            data, 
            StructureItemType.CATEGORY, 
            'validate_category_data'
        )
    
    def get_sphere_data(self) -> List[Dict[str, Any]]:
        """
        Устаревший метод получения данных сфер.
        
        Returns:
            List[Dict[str, Any]]: Список словарей с данными сфер
            
        Deprecated:
            Используйте sphere_operations.get_spheres() напрямую.
            
        Examples:
            >>> legacy = LegacySupport(sphere_ops, section_ops, category_ops)
            >>> spheres = legacy.get_sphere_data()
            >>> print(f"Найдено сфер: {len(spheres)}")
        """
        self._log_deprecation_warning(
            'get_sphere_data',
            'sphere_operations.get_spheres()'
        )
        
        try:
            return self.sphere_operations.get_spheres()
        except Exception as e:
            # Возвращаем пустой список в случае ошибки для обратной совместимости
            warnings.warn(
                f"Ошибка получения данных сфер: {str(e)}. Возвращен пустой список.",
                RuntimeWarning
            )
            return []
    
    def get_usage_statistics(self) -> Dict[str, int]:
        """
        Получить статистику использования устаревших методов.
        
        Returns:
            Dict[str, int]: Словарь с количеством вызовов каждого метода
        """
        return self._usage_stats.copy()

    def get_usage_statistics_detailed(self) -> Dict[str, Dict[str, int]]:
        """Детальная статистика: по методам и вызывающим (module:function)."""
        with self._stats_lock:
            # Глубокая копия структуры словарями
            return {k: v.copy() for k, v in self._usage_stats_by_caller.items()}


class StructureBusinessLogicLegacy:
    """
    Класс для полной обратной совместимости со старыми методами.
    
    Этот класс обеспечивает полную совместимость с предыдущими версиями API
    и делегирует все операции основному контроллеру или legacy-модулю.
    
    Deprecated:
        Этот класс устарел начиная с версии 1.1.0 и будет удален в версии 2.0.
        Используйте основной контроллер напрямую.
    
    Examples:
        # Старый способ (работает, но устарел):
        legacy_controller = StructureBusinessLogicLegacy(main_controller)
        
        # Новый способ (рекомендуемый):
        controller = main_controller  # используйте напрямую
    """
    
    def __init__(self, main_controller) -> None:
        """
        Инициализация legacy-контроллера.
        
        Args:
            main_controller: Основной контроллер структуры
        """
        warnings.warn(
            "StructureBusinessLogicLegacy устарел и будет удален в версии 2.0. "
            "Используйте основной контроллер напрямую.",
            DeprecationWarning,
            stacklevel=2
        )
        
        self.main_controller = main_controller
        self.legacy_support = LegacySupport(
            main_controller.sphere_operations,
            main_controller.section_operations, 
            main_controller.category_operations
        )
    
    def __getattr__(self, name: str) -> Any:
        """
        Делегирует все неопределенные методы к основному контроллеру.
        
        Args:
            name: Имя атрибута или метода
            
        Returns:
            Any: Атрибут или метод основного контроллера
            
        Raises:
            AttributeError: Если атрибут не найден
        """
        try:
            return getattr(self.main_controller, name)
        except AttributeError:
            raise AttributeError(
                f"'{self.__class__.__name__}' object has no attribute '{name}'"
            )
    
    def validate_section_data(self, data: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Устаревший метод валидации данных раздела.
        
        Args:
            data: Данные раздела для валидации
            
        Returns:
            Tuple[bool, str]: Результат валидации и сообщение об ошибке
        """
        return self.legacy_support.validate_section_data(data)
    
    def validate_category_data(self, data: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Устаревший метод валидации данных категории.
        
        Args:
            data: Данные категории для валидации
            
        Returns:
            Tuple[bool, str]: Результат валидации и сообщение об ошибке
        """
        return self.legacy_support.validate_category_data(data)
    
    def get_sphere_data(self) -> List[Dict[str, Any]]:
        """
        Устаревший метод получения данных сфер.
        
        Returns:
            List[Dict[str, Any]]: Список данных сфер
        """
        return self.legacy_support.get_sphere_data()
    
    def get_legacy_usage_statistics(self) -> Dict[str, int]:
        """
        Получить статистику использования legacy-методов.
        
        Returns:
            Dict[str, int]: Статистика использования
        """
        return self.legacy_support.get_usage_statistics()

    def get_legacy_usage_statistics_detailed(self) -> Dict[str, Dict[str, int]]:
        """Детальная статистика использования (по вызывающим)."""
        return self.legacy_support.get_usage_statistics_detailed()


# Вспомогательные функции для миграции
def create_migration_guide() -> str:
    """
    Создает руководство по миграции с legacy API на новый.
    
    Returns:
        str: Текстовое руководство по миграции
    """
    return """
    Руководство по миграции с Legacy API:
    
    1. validate_section_data(data) -> validate_item_data(data, StructureItemType.SECTION)
    2. validate_category_data(data) -> validate_item_data(data, StructureItemType.CATEGORY)  
    3. get_sphere_data() -> sphere_operations.get_spheres()
    4. StructureBusinessLogicLegacy -> используйте основной контроллер напрямую
    
    Временные рамки:
    - v1.1: Предупреждения об устаревании (текущая версия)
    - v1.5: Методы помечены как deprecated в документации
    - v2.0: Полное удаление legacy-кода
    """


def check_legacy_usage(legacy_support: LegacySupport) -> bool:
    """
    Проверяет, используются ли legacy-методы в текущем сеансе.
    
    Args:
        legacy_support: Экземпляр LegacySupport для проверки
        
    Returns:
        bool: True если legacy-методы использовались
    """
    stats = legacy_support.get_usage_statistics()
    return any(count > 0 for count in stats.values())