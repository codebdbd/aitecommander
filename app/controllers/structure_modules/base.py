# app/controllers/structure_modules/base.py

"""Базовые классы, енумы и константы для структуры."""

import logging
from enum import Enum
from typing import Any, Dict, Callable, Optional


class StructureItemType(Enum):
    """Типы элементов структуры для валидации и CRUD операций.
    
    Примечание: Для сигналов также используется "link", но он не входит в этот enum,
    так как ссылки управляются отдельным контроллером.
    """
    SECTION = "section"
    CATEGORY = "category"


class ValidationError(Exception):
    """Исключение для ошибок валидации."""
    pass


# Типы элементов для сигналов (строковые литералы)
ItemTypeStr = str  # "section" | "category" | "link"


class ItemTypes:
    """Константы типов элементов для использования в сигналах и методах импорта."""
    SECTION = "section"
    CATEGORY = "category" 
    LINK = "link"
    
    # Множество всех допустимых типов для валидации
    ALL = {SECTION, CATEGORY, LINK}
    
    # Маппинг типов на parent_id поля
    PARENT_FIELDS: Dict[str, str] = {
        SECTION: "sphere_id",
        CATEGORY: "section_id", 
        LINK: "category_id"
    }


class BaseOperations:
    """Базовый класс для модулей операций структуры.
    Содержит общий конструктор и поля: `structure_model`, `logger`, `_execute_with_error_handling`.
    """
    def __init__(self, structure_model: Any, logger: logging.Logger, execute_with_error_handling: Callable):
        self.structure_model = structure_model
        self.logger = logger
        self._execute_with_error_handling = execute_with_error_handling

    def _exec_with_norm(self, operation_func: Callable, operation_name: str, default_return: Any):
        """Вспомогательный метод для вызова с normalize_result=True."""
        return self._execute_with_error_handling(
            operation_func,
            operation_name,
            default_return=default_return,
            normalize_result=True,
        )

    def _upsert_and_emit(
        self,
        item_type: StructureItemType,
        data: Dict[str, Any],
        is_update: bool,
        item_id: Optional[int],
        emit_signal: Callable[[str, str, int, Dict[str, Any]], None],
    ) -> bool:
        """Единый upsert с формированием данных для сигнала и логированием.

        Не выполняет валидацию — предполагается, что она уже была.
        """
        # Если обновление — проставляем id
        if is_update and item_id is not None:
            data['id'] = item_id

        # Выбор upsert-метода и родительского поля
        parent_field_by_type = {
            StructureItemType.SECTION: 'sphere_id',
            StructureItemType.CATEGORY: 'section_id',
        }
        ru_name_by_type = {
            StructureItemType.SECTION: 'раздел',
            StructureItemType.CATEGORY: 'категория',
        }

        if item_type == StructureItemType.SECTION:
            result_id = self.structure_model.upsert_section(data)
            parent_id = data[parent_field_by_type[item_type]]
        elif item_type == StructureItemType.CATEGORY:
            result_id = self.structure_model.upsert_category(data)
            parent_id = data[parent_field_by_type[item_type]]
        else:
            # На всякий случай — не должен использоваться для других типов
            raise ValueError(f"Unsupported item_type: {item_type}")

        # Подготовка данных сигнала
        if not is_update:
            data['id'] = result_id
            signal_type = 'item_added'
            signal_parent_or_id = parent_id
        else:
            signal_type = 'item_updated'
            signal_parent_or_id = item_id  # type: ignore[arg-type]

        emit_signal(signal_type, item_type.value, signal_parent_or_id, data)

        operation_name = 'обновлен' if is_update else 'создан'
        item_ru = ru_name_by_type[item_type]
        self.logger.info(f"{item_ru.capitalize()} {operation_name}: {data.get('name', 'без имени')}")
        return True

    def _process_item(
        self,
        data: Dict[str, Any],
        item_type: StructureItemType,
        item_id: Optional[int] = None,
        is_update: bool = False,
    ) -> bool:
        """Универсальный метод для создания/обновления элементов структуры (реализация по умолчанию)."""
        def _process_operation():
            return self._upsert_and_emit(
                item_type=item_type,
                data=data,
                is_update=is_update,
                item_id=item_id,
                emit_signal=self._emit_signal,
            )

        operation_name = "обновления" if is_update else "создания"
        result = self._execute_with_validation(
            _process_operation,
            data,
            item_type,
            operation_name,
            require_parent=not is_update,
        )
        return result if result is not None else False
