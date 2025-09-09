# app/controllers/structure_modules/coordination.py

"""Модуль для координации сложных операций между модулями."""

import logging
from collections import defaultdict
from typing import Any, Callable, Dict, List, Optional, Protocol

from app.controllers.structure_services.validation import ValidationService
from app.models.structure_model import StructureModel

from .base import StructureItemType, ValidationError
from .normalization import normalize_row, normalize_rows, validate_normalized_data

# Константы для валидации
SECTION_REQUIRED_KEYS = ["id"]
CATEGORY_REQUIRED_KEYS = ["section_id"]

logger = logging.getLogger(__name__)


class CategoryOperationsProtocol(Protocol):
    """Протокол для операций с категориями."""

    def get_categories_batch(self, section_ids: List[int]) -> List[Dict[str, Any]]:
        """Получает категории для списка разделов."""
        ...


class OperationCoordinator:
    """Координатор для сложных операций, требующих взаимодействия нескольких модулей."""

    def __init__(
        self, structure_model: StructureModel, logger: Optional[logging.Logger] = None
    ):
        self.structure_model = structure_model
        self.logger = logger or globals().get("logger") or logging.getLogger(__name__)
        # Централизованный сервис валидации
        self.validation_service = ValidationService()

    def load_structure_with_categories(
        self,
        sphere_id: int,
        category_operations: CategoryOperationsProtocol,
        error_callback: Optional[Callable] = None,
    ) -> List[Dict[str, Any]]:
        """
        Загружает структуру для сферы с оптимизированной загрузкой категорий.

        Args:
            sphere_id: ID сферы
            category_operations: Объект для операций с категориями
            error_callback: Колбэк для обработки ошибок (принимает title, message, is_critical)

        Returns:
            Список разделов с категориями
        """

        def _load_operation():
            # Загружаем разделы
            sections_data = self.structure_model.get_sections(sphere_id)
            if not sections_data:
                return []

            # Валидируем и фильтруем разделы
            sections_data = self._validate_and_filter_data(
                sections_data, SECTION_REQUIRED_KEYS, "разделов"
            )

            if not sections_data:
                return []

            # Получаем ID всех разделов для батчевой загрузки категорий
            section_ids = [section["id"] for section in sections_data]
            categories_raw = category_operations.get_categories_batch(section_ids)

            # Валидируем и фильтруем категории
            categories_raw = self._validate_and_filter_data(
                categories_raw, CATEGORY_REQUIRED_KEYS, "категорий"
            )

            # Группируем категории по разделам
            categories_by_section = self._group_categories_by_section(categories_raw)

            # Добавляем категории к разделам
            for section in sections_data:
                section_id = section.get("id")
                if section_id is not None:
                    section["categories"] = categories_by_section.get(section_id, [])
                else:
                    section["categories"] = []

            self.logger.debug(
                "Загружена структура для сферы %s: %s разделов",
                sphere_id,
                len(sections_data),
            )
            return sections_data

        return self.execute_with_error_handling(
            _load_operation,
            f"загрузить структуру для сферы {sphere_id}",
            default_return=[],
            error_callback=error_callback,
        )

    def _validate_and_filter_data(
        self, data: List[Dict[str, Any]], required_keys: List[str], data_type: str
    ) -> List[Dict[str, Any]]:
        """
        Валидирует и фильтрует данные по обязательным ключам.

        Args:
            data: Список словарей для валидации
            required_keys: Список обязательных ключей
            data_type: Тип данных для логирования

        Returns:
            Отфильтрованный список данных
        """
        # Защита от None/не-списка
        if not isinstance(data, list):
            self.logger.warning(
                "Ожидался список %s, получено %s. Данные будут проигнорированы.",
                data_type,
                type(data),
            )
            return []

        original_len = len(data)
        if not validate_normalized_data(data, required_keys=required_keys):
            # Фильтруем записи, содержащие все обязательные ключи
            filtered_data: List[Dict[str, Any]] = []
            for item in data:
                if isinstance(item, dict) and all(key in item for key in required_keys):
                    filtered_data.append(item)
            self.logger.warning(
                "Некоторые записи %s не содержат обязательных ключей %s. Отфильтровано: %d → %d.",
                data_type,
                required_keys,
                original_len,
                len(filtered_data),
            )
            return filtered_data
        return data

    def _group_categories_by_section(
        self, categories: List[Dict[str, Any]]
    ) -> Dict[Any, List[Dict[str, Any]]]:
        """
        Группирует категории по разделам.

        Args:
            categories: Список категорий

        Returns:
            Словарь категорий, сгруппированных по section_id
        """
        categories_by_section = defaultdict(list)
        for cat in categories:
            section_id = cat.get("section_id")
            if section_id is not None:
                categories_by_section[section_id].append(cat)
            else:
                self.logger.warning("Категория без section_id найдена: %s", cat)

        return dict(categories_by_section)

    def execute_with_error_handling(
        self,
        operation_func: Callable[[], Any],
        operation_name: str,
        default_return: Any = None,
        normalize_result: bool = False,
        error_callback: Optional[Callable] = None,
    ) -> Any:
        """
        Универсальный метод выполнения операций с централизованной обработкой ошибок.

        Args:
            operation_func: Функция операции для выполнения
            operation_name: Описание операции для логирования
            default_return: Значение по умолчанию при ошибке
            normalize_result: Нужно ли нормализовать результат
            error_callback: Колбэк для обработки ошибок

        Returns:
            Результат операции или default_return при ошибке
        """
        try:
            result = operation_func()

            if normalize_result and result is not None:
                if isinstance(result, list):
                    result = normalize_rows(result, self.logger)
                elif isinstance(result, dict):
                    result = normalize_row(result, self.logger)

            return result
        except Exception as e:
            error_msg = f"Не удалось {operation_name}: {e}"
            if error_callback:
                try:
                    error_callback("Ошибка", error_msg, True)
                except Exception as callback_error:
                    self.logger.error("Ошибка в callback: %s", callback_error)
                    self.logger.error("Исходная ошибка: %s", error_msg, exc_info=True)
            else:
                self.logger.error("Ошибка: %s", error_msg, exc_info=True)
            return default_return

    def execute_with_validation(
        self,
        operation_func: Callable[[], Any],
        data: Dict[str, Any],
        item_type: StructureItemType,
        operation_name: str,
        require_parent: bool = True,
        error_callback: Optional[Callable] = None,
    ) -> Any:
        """
        Универсальный метод выполнения операций с валидацией данных.

        Args:
            operation_func: Функция операции для выполнения
            data: Данные для валидации
            item_type: Тип структурного элемента
            operation_name: Описание операции для логирования
            require_parent: Требовать родительский элемент
            error_callback: Колбэк для обработки ошибок

        Returns:
            Результат операции или None при ошибке
        """
        try:
            # Делегируем валидацию в ValidationService с необходимыми коллбеками
            if item_type == StructureItemType.SECTION:

                def _get_sections(sphere_id: int):
                    try:
                        return self.structure_model.get_sections(sphere_id)
                    except Exception:
                        return []

                vr = self.validation_service.validate_section_data(
                    data=data,
                    section_id=data.get("id"),
                    get_sections=_get_sections,
                )
            elif item_type == StructureItemType.CATEGORY:

                def _has_duplicate(
                    section_id: int, name: str, exclude_id: Optional[int]
                ) -> bool:
                    try:
                        cats = self.structure_model.get_categories(section_id)
                        for c in cats or []:
                            if (
                                c.get("name", "").lower() == (name or "").lower()
                                and c.get("id") != exclude_id
                            ):
                                return True
                        return False
                    except Exception:
                        return False

                vr = self.validation_service.validate_category_data(
                    data=data,
                    category_id=data.get("id"),
                    has_duplicate_category=_has_duplicate,
                )
            else:
                raise ValidationError(f"Неизвестный тип элемента: {item_type}")

            if not vr.is_valid:
                raise ValidationError("; ".join(vr.errors))

            self.logger.debug("Валидация прошла успешно для %s", operation_name)
            return operation_func()
        except ValidationError as e:
            error_msg = f"Ошибка валидации при {operation_name}: {e}"
            if error_callback:
                try:
                    error_callback("Ошибка валидации", error_msg, False)
                except Exception as callback_error:
                    self.logger.error("Ошибка в callback: %s", callback_error)
                    self.logger.error("Исходная ошибка валидации: %s", error_msg)
            else:
                self.logger.error("%s", error_msg)
            return None
        except Exception as e:
            error_msg = f"Неожиданная ошибка при {operation_name}: {e}"
            if error_callback:
                try:
                    error_callback("Ошибка", error_msg, True)
                except Exception as callback_error:
                    self.logger.error("Ошибка в callback: %s", callback_error)
                    self.logger.error("Исходная ошибка: %s", error_msg, exc_info=True)
            else:
                self.logger.error("%s", error_msg, exc_info=True)
            return None
