# app/controllers/structure_modules/base.py
"""Base classes, enums and constants for structure operations."""

import logging
from typing import Any, Callable, Optional, TypeVar, cast

from ..models.types import (
    AnyCreateData,
    AnyItemData,
    AnyItemPayload,
    AnyUpdateData,
    ItemTypeConfig,
    SignalType,
    StructureItemType,
)
from ..validation.validators import ValidationError, validate_and_raise

logger = logging.getLogger(__name__)


TExecResult = TypeVar("TExecResult")


class StructureOperationError(Exception):
    """Exception for structure operation errors."""

    def __init__(self, message: str, operation: str, item_type: str):
        super().__init__(message)
        self.operation = operation
        self.item_type = item_type
        self.message = message


class StructureLogger:
    """Wrapper for logging structure operations."""

    def __init__(self, logger: logging.Logger):
        self.logger = logger

    def log_operation(
        self, operation: str, item_type: str, item_name: str, display_name: str
    ) -> None:
        """Log an operation with a structure item."""
        self.logger.info("%s %s: %s", display_name.capitalize(), operation, item_name)

    def log_error(self, operation: str, item_type: str, error: str) -> None:
        """Log an operation error."""
        self.logger.error("Error %s for %s: %s", operation, item_type, error)


class StructureSignalEmitter:
    """Wrapper for emitting structure signals."""

    def __init__(
        self,
        emit_signal_func: Optional[
            Callable[[str, str, int, AnyItemPayload | None], None]
        ] = None,
    ):
        self._emit_signal = emit_signal_func

    def emit(
        self,
        signal_type: str,
        item_type: str,
        parent_or_id: int,
        data: AnyItemPayload | None = None,
    ) -> None:
        """Emit a signal."""
        if not self._emit_signal:
            return  # Если функция не установлена, просто ничего не делаем

        try:
            if data is None:
                self._emit_signal(signal_type, item_type, parent_or_id, None)
            else:
                self._emit_signal(signal_type, item_type, parent_or_id, data)
        except (AttributeError, TypeError, ValueError) as e:
            # Expected errors — log as warning
            logger.warning("Signal emission error: %s", e)
        except Exception as e:
            # Unexpected errors — full traceback and re-raise
            logger.exception("Critical signal emission error: %s", e)
            raise


# ItemTypeConfig импортируется из types.py


class ItemTypeRegistry:
    """Registry of configurations for structure item types."""

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
        """Get configuration for an item type."""
        if item_type not in cls._configs:
            raise ValueError(f"Unsupported item_type: {item_type}")
        return cls._configs[item_type]

    @classmethod
    def is_supported(cls, item_type: StructureItemType) -> bool:
        """Check whether the item type is supported."""
        return item_type in cls._configs


class BaseOperations:
    """Base class for structure operation modules.

    Refactoring with improved architecture:
    - Separation of concerns
    - Improved error handling
    - Support of all item types via registry
    """

    def __init__(
        self,
        structure_model: Any,  # StructureModel из app.models.structure_model
        logger: logging.Logger,
        execute_with_error_handling: Callable,
        emit_signal_func: Optional[
            Callable[[str, str, int, AnyItemPayload | None], None]
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
        data: dict[str, Any],
        item_type: StructureItemType,
        require_parent: bool = True,
    ) -> None:
        """Basic data validation."""
        if not isinstance(data, dict):
            raise ValidationError(f"Data must be a dict for {item_type.value}")

        if not data.get("name", "").strip():
            raise ValidationError(f"Field 'name' is required for {item_type.value}")

        if require_parent:
            try:
                config = ItemTypeRegistry.get_config(item_type)
                parent_field = config.parent_field
                if parent_field not in data or data[parent_field] is None:
                    raise ValidationError(
                        f"Field '{parent_field}' is required for {item_type.value}"
                    )
            except ValueError as e:
                raise ValidationError(f"{item_type.value}: {e}") from e

    def _exec_with_norm(
        self, operation_func: Callable, operation_name: str, default_return: Any
    ):
        """Helper to call with normalize_result=True."""
        return self._execute_with_error_handling(
            operation_func,
            operation_name,
            default_return=default_return,
            normalize_result=True,
        )

    def _execute_with_validation(
        self,
        operation_func: Callable[[], TExecResult],
        data: Any,  # Accept both dict[str, Any] and TypedDict variants
        item_type: StructureItemType,
        operation_name: str,
        require_parent: bool = True,
    ) -> Optional[TExecResult]:
        """Perform validation and operation with error handling."""
        try:
            # Валидация
            self._validate_data(data, item_type, require_parent)

            # Выполнение операции
            return operation_func()

        except ValidationError as e:
            self.slogger.log_error(
                operation_name, item_type.value, f"Validation: {e.message}"
            )
            return None
        except StructureOperationError as e:
            self.slogger.log_error(operation_name, item_type.value, e.message)
            return None
        except Exception as e:
            self.slogger.log_error(
                operation_name, item_type.value, f"Unexpected error: {str(e)}"
            )
            return None

    def _emit_signal(
        self,
        signal_type: str,
        item_type: str,
        parent_or_id: int,
        data: AnyItemPayload | None = None,
    ) -> None:
        """Emit a signal via the configured emitter."""
        self.signal_emitter.emit(signal_type, item_type, parent_or_id, data)

    def _upsert_and_emit(
        self,
        item_type: StructureItemType,
        data: dict[str, Any],
        is_update: bool,
        item_id: Optional[int],
        emit_signal: Callable[[str, str, int, AnyItemPayload | None], None],
    ) -> Optional[int]:
        """Generic create/update method for structure items.

        Performs runtime data validation before processing.
        """
        # Runtime validation of input data
        try:
            validate_and_raise(data, item_type, is_update)
        except ValidationError as e:
            logger.error("Validation failed for %s: %s", item_type.value, e.message)
            raise StructureOperationError(
                f"Invalid data for {item_type.value}: {e.message}",
                "validation",
                item_type.value,
            ) from e

        # Check item type support
        if not ItemTypeRegistry.is_supported(item_type):
            raise StructureOperationError(
                f"Unsupported item type: {item_type}", "upsert", item_type.value
            )

        config = ItemTypeRegistry.get_config(item_type)

        # Copy only when necessary (optimization)
        if is_update and item_id is not None:
            data_copy = data.copy()
            data_copy["id"] = item_id
        else:
            data_copy = data

        # Optimization: id already set above when copying

        # Perform upsert operation
        upsert_method = getattr(self.structure_model, config.upsert_method_name, None)
        if not upsert_method:
            raise StructureOperationError(
                f"Method {config.upsert_method_name} not found in model",
                "upsert",
                config.item_type.value,
            )

        try:
            result_id = upsert_method(data_copy)
        except Exception as e:
            raise StructureOperationError(
                f"Error executing {config.upsert_method_name}: {str(e)}",
                "upsert",
                config.item_type.value,
            ) from e

        # Prepare signal data
        if not is_update:
            # Copy only if not already copied above
            if data_copy is data:
                data_copy = data.copy()
            data_copy["id"] = result_id
            signal_type = SignalType.ITEM_ADDED
            signal_parent_or_id = data_copy[config.parent_field]
        else:
            signal_type = SignalType.ITEM_UPDATED
            signal_parent_or_id = item_id  # type: ignore[arg-type]

        payload = cast(AnyItemPayload, data_copy)
        emit_signal(
            signal_type.value,
            item_type.value,
            signal_parent_or_id,
            payload,
        )

        # Log successful operation with validation confirmation
        operation_name = "updated" if is_update else "created"
        logger.info(
            "✅ %s %s '%s' (validation passed)",
            config.ru_name.capitalize(),
            operation_name,
            data_copy.get("name", "unnamed"),
        )

        return result_id

    def _process_item(
        self,
        item_type: StructureItemType,
        data: Any,  # Accept AnyItemData, AnyCreateData, AnyUpdateData
        emit_signal: "StructureSignalEmitter",
        is_update: bool = False,
        item_id: Optional[int] = None,
    ) -> Optional[int]:
        """Process a structure item create/update operation.

        Args:
            item_type: Structure item type
            data: Item data
            emit_signal: Signal emitter
            is_update: Update flag
            item_id: Item identifier for update
        """

        def _process_operation():
            return self._upsert_and_emit(
                item_type=item_type,
                data=data,
                is_update=is_update,
                item_id=item_id,
                emit_signal=emit_signal.emit,
            )

        operation_name = (
            "update" if is_update else "create"
        )  # For logging/error handling
        result = self._execute_with_validation(
            _process_operation,
            data,
            item_type,
            operation_name,
            require_parent=True,
        )
        return result if result is not None else None

    # === Public CRUD operation wrappers ===
    def create_item(self, item_type: StructureItemType, data: AnyCreateData) -> bool:
        """Create a structure item using generic processing logic.

        Delegates to `_process_item`, preserving validation, signals and logging policy.

        Args:
            item_type: Structure item type
            data: Data of the created item

        Returns:
            bool: Whether operation succeeded
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
        """Update a structure item using generic processing logic.

        Delegates to `_process_item`, preserving validation, signals and logging policy.

        Args:
            item_type: Structure item type
            item_id: Identifier of the item to update
            data: New item data

        Returns:
            bool: Whether operation succeeded
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
        emit_data: Optional[dict[str, Any]] = None,
    ) -> bool:
        """Delete a structure item via provided function, emit signal and log.

        Args:
            item_type: Item type
            item_id: Item identifier
            delete_func: Function performing actual deletion (must raise on error)
            emit_data: Optional data to pass in the signal

        Returns:
            bool: Whether operation succeeded
        """

        def _delete_operation():
            # Execute deletion and emit signal
            delete_func()
            self._emit_signal(
                SignalType.ITEM_DELETED.value,
                item_type.value,
                item_id,
                emit_data or {},
            )

            # Log deletion
            ru_name = ItemTypeRegistry.get_config(item_type).ru_name
            self.slogger.log_operation(
                "deleted", item_type.value, str(item_id), ru_name
            )
            return True

        return self._execute_with_error_handling(
            _delete_operation,
            f"delete {item_type.value} {item_id}",  # Error context message
            default_return=False,
        )
