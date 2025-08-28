# app/controllers/structure_modules/helpers.py
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional, Protocol, runtime_checkable

from .base import StructureItemType

logger = logging.getLogger(__name__)

__all__ = [
    "StructureController",
    "process_item",
    "process_item_old_signature",
]


@runtime_checkable
class StructureController(Protocol):
    """Протокол для контроллера структурных элементов."""

    def _upsert_and_emit(
        self,
        *,
        item_type: StructureItemType,
        data: Dict[str, Any],
        is_update: bool,
        item_id: Optional[int],
        emit_signal: Callable[..., None],
    ) -> Any:
        """Создание/обновление элемента с отправкой сигнала."""
        ...

    def _emit_signal(self, *args, **kwargs) -> None:
        """Отправка сигнала о событии."""
        ...

    def _execute_with_validation(
        self,
        operation: Callable[[], Any],
        data: Dict[str, Any],
        item_type: StructureItemType,
        operation_name: str,
        *,
        require_parent: bool = True,
    ) -> Any:
        """Выполнение операции с валидацией."""
        ...


def process_item(
    controller: StructureController,
    data: Dict[str, Any],
    item_type: StructureItemType,
    item_id: Optional[int] = None,
    is_update: bool = False,
    *,
    require_parent: bool = True,
) -> bool:
    """
    Общий помощник для создания/обновления элементов структуры с валидацией.

    Args:
        controller: Контроллер, реализующий протокол StructureController
        data: Данные для создания/обновления элемента
        item_type: Тип структурного элемента
        item_id: ID элемента для обновления (опционально)
        is_update: True для обновления, False для создания
        require_parent: Требовать наличие родителя (sphere_id/section_id/...).
            По умолчанию True. Отключайте явно только если операция допускает отсутствие родителя.

    Returns:
        bool: True в случае успеха, False в случае неудачи

    Raises:
        TypeError: Если controller не реализует необходимый протокол
        ValueError: Если переданы некорректные данные
    """
    # Проверяем, что контроллер реализует необходимый протокол
    if not isinstance(controller, StructureController):
        error_msg = f"Контроллер должен реализовывать протокол StructureController, получен {type(controller)}"
        logger.error(error_msg)
        raise TypeError(error_msg)

    # Валидируем входные данные
    if not isinstance(data, dict):
        error_msg = f"Аргумент data должен быть dict, получен {type(data)}"
        logger.error(error_msg)
        raise ValueError(error_msg)

    if is_update and item_id is None:
        error_msg = "Для операций обновления требуется item_id"
        logger.error(error_msg)
        raise ValueError(error_msg)

    def _process_operation():
        """Внутренняя функция для выполнения операции создания/обновления."""
        try:
            return controller._upsert_and_emit(
                item_type=item_type,
                data=data,
                is_update=is_update,
                item_id=item_id,
                emit_signal=controller._emit_signal,
            )
        except Exception as e:
            logger.error(f"Error in _upsert_and_emit: {e}")
            raise

    operation_name = "обновление" if is_update else "создание"

    try:
        result = controller._execute_with_validation(
            _process_operation,
            data,
            item_type,
            operation_name,
            require_parent=require_parent,
        )

        # Явно обрабатываем различные типы результатов
        if result is None:
            logger.warning(
                "Операция %s вернула None (item_type=%s, item_id=%s)",
                operation_name,
                getattr(item_type, "name", item_type),
                item_id,
            )
            return False

        # Преобразуем результат в boolean, учитывая различные типы
        success = bool(result)

        log_level = logging.INFO if success else logging.WARNING
        logger.log(
            log_level,
            "Элемент: %s (%s)",
            "успешно обновлён"
            if is_update and success
            else (
                "не обновлён"
                if is_update and not success
                else ("успешно создан" if success else "не создан")
            ),
            getattr(item_type, "name", item_type),
        )

        return success

    except Exception as e:
        logger.exception("Ошибка во время операции %s: %s", operation_name, e)
        return False


# Обратная совместимость: алиас для старой сигнатуры
# Это позволяет вызывать как process_item(self, data, ...) без изменения существующего кода
def process_item_old_signature(
    self: Any,
    data: Dict[str, Any],
    item_type: StructureItemType,
    item_id: Optional[int] = None,
    is_update: bool = False,
    *,
    require_parent: bool = True,
) -> bool:
    """
    Версия с старой сигнатурой для полной обратной совместимости.
    Автоматически перенаправляет вызов на новую версию.
    """
    return process_item(self, data, item_type, item_id, is_update, require_parent=require_parent)
