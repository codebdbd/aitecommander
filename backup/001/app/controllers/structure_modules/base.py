# app/controllers/structure_modules/base.py

"""Базовые классы, енумы и константы для структуры."""

import logging
from .types import StructureItemType as ImportedStructureItemType
from typing import Any, Callable, Dict, Optional

from .types import (
    StructureItemType, SignalType, AnyItemData, AnyCreateData, AnyUpdateData,
    ItemTypeConfig
)
from .validators import validate_and_raise, ValidationError

logger = logging.getLogger(__name__)


# ✅ Используем импортированный StructureItemType из types.py
StructureItemType = ImportedStructureItemType

# ValidationError импортируется из validators.py


class StructureOperationError(Exception):
    """Исключение для ошибок операций структуры."""

    def __init__(self, message: str, operation: str, item_type: str):
        super().__init__(message)
        self.operation = operation
        self.item_type = item_type
        self.message = message


# ✅ Используем импортированный SignalType из types.py
# SignalType уже импортирован выше


class StructureLogger:
    """Обертка для логирования операций структуры."""

    def __init__(self, logger: logging.Logger):
        self.logger = logger

    def log_operation(
        self, operation: str, item_type: str, item_name: str, ru_name: str
    ) -> None:
        """Логирует операцию с элементом структуры."""
        self.logger.info("%s %s: %s", ru_name.capitalize(), operation, item_name)

    def log_error(self, operation: str, item_type: str, error: str) -> None:
        """Логирует ошибку операции."""
        self.logger.error("Ошибка %s для %s: %s", operation, item_type, error)


class StructureSignalEmitter:
    """Обертка для эмиссии сигналов структуры."""

    def __init__(
        self,
        emit_signal_func: Optional[
            Callable[[str, str, int, Dict[str, Any]], None]
        ] = None,
    ):
        self._emit_signal = emit_signal_func

    def emit(
        self, signal_type: str, item_type: str, parent_or_id: int, data: AnyItemData
    ) -> None:
        """Эмитирует сигнал."""
        if not self._emit_signal:
            return  # Если функция не установлена, просто ничего не делаем

        try:
            self._emit_signal(signal_type, item_type, parent_or_id, data)
        except (AttributeError, TypeError, ValueError) as e:
            # ✅ Ожидаемые ошибки - логируем warning
            logger.warning("Ошибка эмиссии сигнала: %s", e)
        except Exception as e:
            # ✅ Неожиданные ошибки - полный traceback и проброс
            logger.exception("Критическая ошибка эмиссии сигнала: %s", e)
            raise


# ItemTypeConfig импортируется из types.py


class ItemTypeRegistry:
    """Реестр конфигураций для типов элементов."""

    _configs = {
        StructureItemType.SPHERE: ItemTypeConfig(
            StructureItemType.SPHERE, "parent_id", "сфера", "upsert_sphere"
        ),
        StructureItemType.SECTION: ItemTypeConfig(
            StructureItemType.SECTION, "sphere_id", "раздел", "upsert_section"
        ),
        StructureItemType.CATEGORY: ItemTypeConfig(
            StructureItemType.CATEGORY, "section_id", "категория", "upsert_category"
        ),
    }

    @classmethod
    def get_config(cls, item_type: StructureItemType) -> ItemTypeConfig:
        """Получает конфигурацию для типа элемента."""
        if item_type not in cls._configs:
            raise ValueError(f"Unsupported item_type: {item_type}")
        return cls._configs[item_type]

    @classmethod
    def is_supported(cls, item_type: StructureItemType) -> bool:
        """Проверяет, поддерживается ли тип элемента."""
        return item_type in cls._configs


class BaseOperations:
    """Базовый класс для модулей операций структуры.

    Рефакторинг с улучшенной архитектурой:
    - Разделение ответственностей
    - Улучшенная обработка ошибок
    - Поддержка всех типов элементов через реестр
    """

    def __init__(
        self,
        structure_model: Any,  # StructureModel из app.models.structure_model
        logger: logging.Logger,
        execute_with_error_handling: Callable,
        emit_signal_func: Optional[
            Callable[[str, str, int, Dict[str, Any]], None]
        ] = None,
    ):
        self.structure_model = structure_model
        # Сохраняем обычный logger для совместимости со старыми модулями
        self.logger = logger
        # Дополнительно используем структурированный логгер для стандартных сообщений
        self.slogger = StructureLogger(logger)
        self._execute_with_error_handling = execute_with_error_handling

        # Инициализация компонентов
        self.signal_emitter = StructureSignalEmitter(emit_signal_func)

    def _validate_data(
        self,
        data: Dict[str, Any],
        item_type: StructureItemType,
        require_parent: bool = True,
    ) -> None:
        """Базовая валидация данных."""
        if not isinstance(data, dict):
            raise ValidationError(
                "Данные должны быть словарем", item_type=item_type.value
            )

        if not data.get("name", "").strip():
            raise ValidationError(
                "Поле 'name' обязательно", field="name", item_type=item_type.value
            )

        if require_parent:
            try:
                config = ItemTypeRegistry.get_config(item_type)
                parent_field = config.parent_field
                if parent_field not in data or data[parent_field] is None:
                    raise ValidationError(
                        f"Поле '{parent_field}' обязательно",
                        field=parent_field,
                        item_type=item_type.value,
                    )
            except ValueError as e:
                raise ValidationError(str(e), item_type=item_type.value) from e

    def _exec_with_norm(
        self, operation_func: Callable, operation_name: str, default_return: Any
    ):
        """Вспомогательный метод для вызова с normalize_result=True."""
        return self._execute_with_error_handling(
            operation_func,
            operation_name,
            default_return=default_return,
            normalize_result=True,
        )

    def _execute_with_validation(
        self,
        operation_func: Callable,
        data: Dict[str, Any],
        item_type: StructureItemType,
        operation_name: str,
        require_parent: bool = True,
    ) -> Optional[bool]:
        """Выполняет валидацию и операцию с обработкой ошибок."""
        try:
            # Валидация
            self._validate_data(data, item_type, require_parent)

            # Выполнение операции
            return operation_func()

        except ValidationError as e:
            self.slogger.log_error(
                operation_name, item_type.value, f"Валидация: {e.message}"
            )
            return None
        except StructureOperationError as e:
            self.slogger.log_error(operation_name, item_type.value, e.message)
            return None
        except Exception as e:
            self.slogger.log_error(
                operation_name, item_type.value, f"Неожиданная ошибка: {str(e)}"
            )
            return None

    def _emit_signal(
        self, signal_type: str, item_type: str, parent_or_id: int, data: Dict[str, Any]
    ) -> None:
        """Эмитирует сигнал через настроенный эмиттер."""
        self.signal_emitter.emit(signal_type, item_type, parent_or_id, data)

    def _upsert_and_emit(
        self,
        item_type: StructureItemType,
        data: Dict[str, Any],
        is_update: bool,
        item_id: Optional[int],
        emit_signal: Callable[[str, str, int, Dict[str, Any]], None],
    ) -> Optional[int]:
        """Универсальный метод для создания/обновления элементов структуры.

        ✅ Выполняет runtime валидацию данных перед обработкой.
        """
        # ✅ Runtime валидация входных данных
        try:
            validate_and_raise(data, item_type, is_update)
        except ValidationError as e:
            logger.error("Validation failed for %s: %s", item_type.value, e.message)
            raise StructureOperationError(
                f"Invalid data for {item_type.value}: {e.message}",
                "validation",
                item_type.value
            ) from e
        
        # Проверка поддержки типа элемента
        if not ItemTypeRegistry.is_supported(item_type):
            raise StructureOperationError(
                f"Неподдерживаемый тип элемента: {item_type}", "upsert", item_type.value
            )

        config = ItemTypeRegistry.get_config(item_type)

        # ✅ Копируем только при необходимости (оптимизация)
        if is_update and item_id is not None:
            data_copy = data.copy()
            data_copy["id"] = item_id
        else:
            data_copy = data

        # ✅ Оптимизация: id уже установлен выше при копировании

        # Выполнение upsert операции
        upsert_method = getattr(self.structure_model, config.upsert_method_name, None)
        if not upsert_method:
            raise StructureOperationError(
                f"Метод {config.upsert_method_name} не найден в модели",
                "upsert",
                config.item_type.value,
            )

        try:
            result_id = upsert_method(data_copy)
        except Exception as e:
            raise StructureOperationError(
                f"Ошибка при выполнении {config.upsert_method_name}: {str(e)}",
                "upsert",
                config.item_type.value,
            ) from e

        # Подготовка данных сигнала
        if not is_update:
            # ✅ Копируем только если не копировали раньше
            if data_copy is data:
                data_copy = data.copy()
            data_copy["id"] = result_id
            signal_type = SignalType.ITEM_ADDED
            signal_parent_or_id = data_copy[config.parent_field]
        else:
            signal_type = SignalType.ITEM_UPDATED
            signal_parent_or_id = item_id  # type: ignore[arg-type]

        emit_signal(signal_type.value, item_type.value, signal_parent_or_id, data_copy)

        # Логирование с указанием валидации
        operation_name = "обновлен" if is_update else "создан"
        logger.info(
            "✅ %s %s '%s' (валидация пройдена)",
            config.ru_name.capitalize(),
            operation_name,
            data_copy.get("name", "без имени")
        )

        return result_id

    def _process_item(
        self,
        item_type: StructureItemType,
        data: AnyItemData,
        emit_signal: "StructureSignalEmitter",
        is_update: bool = False,
        item_id: Optional[int] = None,
    ) -> Optional[int]:
        """Универсальный метод для создания/обновления элементов структуры.

        Args:
            item_type: тип элемента структуры
            data: данные элемента
            emit_signal: эмиттер сигналов
            is_update: флаг обновления
            item_id: идентификатор элемента для обновления
        """

        def _process_operation():
            return self._upsert_and_emit(
                item_type=item_type,
                data=data,
                is_update=is_update,
                item_id=item_id,
                emit_signal=emit_signal.emit,
            )

        operation_name = "обновления" if is_update else "создания"
        result = self._execute_with_validation(
            _process_operation,
            data,
            item_type,
            operation_name,
            require_parent=True,
        )
        return result if result is not None else None

    # === Публичные универсальные CRUD-обёртки ===
    def create_item(self, item_type: StructureItemType, data: AnyCreateData) -> bool:
        """Создает элемент указанного типа через универсальную логику.

        Делегирует в `_process_item`, сохраняя политику валидации, сигналов и логирования.

        Args:
            item_type: тип элемента структуры
            data: данные создаваемого элемента
            require_parent: требовать ли наличие родительского идентификатора

        Returns:
            bool: успех операции
        """
        result = self._process_item(
            item_type,
            data,
            self.signal_emitter,
            is_update=False,
            item_id=None,
        )
        return result is not None

    def update_item(
        self,
        item_type: StructureItemType,
        item_id: int,
        data: AnyUpdateData,
    ) -> bool:
        """Обновляет элемент указанного типа через универсальную логику.

        Делегирует в `_process_item`, сохраняя политику валидации, сигналов и логирования.

        Args:
            item_type: тип элемента структуры
            item_id: идентификатор обновляемого элемента
            data: новые данные элемента

        Returns:
            bool: успех операции
        """
        result = self._process_item(
            item_type,
            data,
            self.signal_emitter,
            is_update=True,
            item_id=item_id,
        )
        return result is not None

    def delete_item(
        self,
        item_type: StructureItemType,
        item_id: int,
        delete_func: Callable[[], None],
        *,
        emit_data: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Удаляет элемент указанного типа через переданную функцию, эмитит сигнал и логирует.

        Args:
            item_type: тип элемента
            item_id: идентификатор элемента
            delete_func: функция, выполняющая фактическое удаление (должна бросать исключение при ошибке)
            emit_data: опциональные данные для передачи в сигнал

        Returns:
            bool: успех операции
        """

        def _delete_operation():
            # Выполняем фактическое удаление
            delete_func()

            # Эмитим сигнал удаления (parent_or_id = id элемента)
            self._emit_signal(
                SignalType.ITEM_DELETED, item_type.value, item_id, emit_data or {}
            )

            # Логирование
            ru_name = ItemTypeRegistry.get_config(item_type).ru_name
            self.slogger.log_operation("удален", item_type.value, str(item_id), ru_name)
            return True

        return self._execute_with_error_handling(
            _delete_operation,
            f"удалить {item_type.value} {item_id}",
            default_return=False,
        )
