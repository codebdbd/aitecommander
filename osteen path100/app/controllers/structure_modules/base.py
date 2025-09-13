# app/controllers/structure_modules/base.py

"""Базовые классы, енумы и константы для структуры."""

import logging
from enum import Enum
from typing import Any, Callable, Dict, Optional, Protocol

logger = logging.getLogger(__name__)


class StructureItemType(Enum):
    """Типы элементов структуры для валидации и CRUD операций."""

    SECTION = "section"
    CATEGORY = "category"
    LINK = "link"  # Добавлен для полноты


class ValidationError(Exception):
    """Исключение для ошибок валидации."""

    def __init__(
        self, message: str, field: Optional[str] = None, item_type: Optional[str] = None
    ):
        super().__init__(message)
        self.field = field
        self.item_type = item_type
        self.message = message


class StructureOperationError(Exception):
    """Исключение для ошибок операций структуры."""

    def __init__(self, message: str, operation: str, item_type: str):
        super().__init__(message)
        self.operation = operation
        self.item_type = item_type
        self.message = message


# Типы элементов для сигналов (строковые литералы) - сохраняем для обратной совместимости
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
        LINK: "category_id",
    }


class StructureModelProtocol(Protocol):
    """Протокол для модели структуры."""

    def upsert_section(self, data: Dict[str, Any]) -> int:
        """Создает или обновляет раздел."""
        ...

    def upsert_category(self, data: Dict[str, Any]) -> int:
        """Создает или обновляет категорию."""
        ...

    def upsert_link(self, data: Dict[str, Any]) -> int:
        """Создает или обновляет ссылку."""
        ...


class SignalEmitterProtocol(Protocol):
    """Протокол для эмиттера сигналов."""

    def emit_signal(
        self, signal_type: str, item_type: str, parent_or_id: int, data: Dict[str, Any]
    ) -> None:
        """Эмитирует сигнал."""
        ...


class ItemTypeConfig:
    """Конфигурация для типа элемента структуры."""

    def __init__(
        self,
        item_type: StructureItemType,
        parent_field: str,
        ru_name: str,
        upsert_method_name: str,
    ):
        self.item_type = item_type
        self.parent_field = parent_field
        self.ru_name = ru_name
        self.upsert_method_name = upsert_method_name


class ItemTypeRegistry:
    """Реестр конфигураций для типов элементов."""

    _configs = {
        StructureItemType.SECTION: ItemTypeConfig(
            StructureItemType.SECTION, "sphere_id", "раздел", "upsert_section"
        ),
        StructureItemType.CATEGORY: ItemTypeConfig(
            StructureItemType.CATEGORY, "section_id", "категория", "upsert_category"
        ),
        StructureItemType.LINK: ItemTypeConfig(
            StructureItemType.LINK, "category_id", "ссылка", "upsert_link"
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


class SignalType:
    """Константы типов сигналов."""

    ITEM_ADDED = "item_added"
    ITEM_UPDATED = "item_updated"
    ITEM_DELETED = "item_deleted"


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
        self, signal_type: str, item_type: str, parent_or_id: int, data: Dict[str, Any]
    ) -> None:
        """Эмитирует сигнал."""
        if not self._emit_signal:
            return  # Если функция не установлена, просто ничего не делаем

        try:
            self._emit_signal(signal_type, item_type, parent_or_id, data)
        except Exception as e:
            # Логируем, но не прерываем выполнение основной операции
            logger.warning("Ошибка эмиссии сигнала: %s", e)


class BaseOperations:
    """Базовый класс для модулей операций структуры.

    Рефакторинг с улучшенной архитектурой:
    - Разделение ответственностей
    - Улучшенная обработка ошибок
    - Поддержка всех типов элементов через реестр
    """

    def __init__(
        self,
        structure_model: StructureModelProtocol,
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
    ) -> bool:
        """Единый upsert с формированием данных для сигнала и логированием.

        Не выполняет валидацию — предполагается, что она уже была.
        """
        # Проверка поддержки типа элемента
        if not ItemTypeRegistry.is_supported(item_type):
            raise StructureOperationError(
                f"Неподдерживаемый тип элемента: {item_type}", "upsert", item_type.value
            )

        config = ItemTypeRegistry.get_config(item_type)

        # Создаем копию данных для избежания мутации исходных данных
        data_copy = data.copy()

        # Если обновление — проставляем id
        if is_update and item_id is not None:
            data_copy["id"] = item_id

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
            data_copy["id"] = result_id
            signal_type = SignalType.ITEM_ADDED
            signal_parent_or_id = data_copy[config.parent_field]
        else:
            signal_type = SignalType.ITEM_UPDATED
            signal_parent_or_id = item_id  # type: ignore[arg-type]

        emit_signal(signal_type, item_type.value, signal_parent_or_id, data_copy)

        # Логирование
        operation_name = "обновлен" if is_update else "создан"
        self.slogger.log_operation(
            operation_name,
            item_type.value,
            data_copy.get("name", "без имени"),
            config.ru_name,
        )

        return True

    def _process_item(
        self,
        data: Dict[str, Any],
        item_type: StructureItemType,
        item_id: Optional[int] = None,
        is_update: bool = False,
        *,
        require_parent: bool = True,
    ) -> bool:
        """Универсальный метод для создания/обновления элементов структуры.

        Args:
            data: Данные элемента
            item_type: Тип элемента структуры
            item_id: ID элемента для обновления
            is_update: Флаг обновления
            require_parent: Требовать наличие родительского идентификатора. По умолчанию True.
                Отключайте только явно, если операция допускает отсутствие родителя.
        """

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
            require_parent=require_parent,
        )
        return result if result is not None else False

    # === Публичные универсальные CRUD-обёртки ===
    def create_item(
        self,
        item_type: StructureItemType,
        data: Dict[str, Any],
        *,
        require_parent: bool = True,
    ) -> bool:
        """Создает элемент указанного типа через универсальную логику.

        Делегирует в `_process_item`, сохраняя политику валидации, сигналов и логирования.

        Args:
            item_type: тип элемента структуры
            data: данные создаваемого элемента
            require_parent: требовать ли наличие родительского идентификатора

        Returns:
            bool: успех операции
        """
        return self._process_item(
            data,
            item_type,
            item_id=None,
            is_update=False,
            require_parent=require_parent,
        )

    def update_item(
        self,
        item_type: StructureItemType,
        item_id: int,
        data: Dict[str, Any],
        *,
        require_parent: bool = True,
    ) -> bool:
        """Обновляет элемент указанного типа через универсальную логику.

        Делегирует в `_process_item`, сохраняя политику валидации, сигналов и логирования.

        Args:
            item_type: тип элемента структуры
            item_id: идентификатор обновляемого элемента
            data: новые данные элемента
            require_parent: требовать ли наличие родительского идентификатора

        Returns:
            bool: успех операции
        """
        return self._process_item(
            data,
            item_type,
            item_id=item_id,
            is_update=True,
            require_parent=require_parent,
        )

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
