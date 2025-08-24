# app/controllers/structure_modules/category_operations.py

"""Модуль для операций с категориями."""

import logging
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.models.structure_model import StructureModel
from app.services.structure_service import StructureService

from .base import BaseOperations, StructureItemType


class SignalTypes:
    """Константы для типов сигналов."""

    ITEM_ADDED = "item_added"
    ITEM_DELETED = "item_deleted"
    ITEM_UPDATED = "item_updated"


class CategoryOperations(BaseOperations):
    """Класс для операций с категориями."""

    def __init__(
        self,
        structure_model: StructureModel,
        logger: logging.Logger,
        execute_with_error_handling: Callable,
        execute_with_validation: Callable,
        emit_signal_callback: Callable,
        cache_manager,
    ):
        super().__init__(structure_model, logger, execute_with_error_handling)
        self._execute_with_validation = execute_with_validation
        self._emit_signal = emit_signal_callback
        self._cache_manager = cache_manager
        # Сервисный слой: транзакции и чтения без дублирования SQL
        try:
            self._structure_service = StructureService(structure_model.db)
        except Exception:
            self._structure_service = None

    def create_category(self, data: Dict[str, Any]) -> bool:
        """Создает новую категорию."""
        result = self._process_item(data, StructureItemType.CATEGORY)
        if result:
            self._cache_manager.invalidate_first_category_cache()
        return result

    def update_category(self, category_id: int, data: Dict[str, Any]) -> bool:
        """Обновляет существующую категорию."""
        result = self._process_item(
            data, StructureItemType.CATEGORY, category_id, is_update=True
        )
        if result:
            self._cache_manager.invalidate_first_category_cache()
        return result

    def delete_category(self, category_id: int) -> Tuple[bool, Dict[str, Any], int]:
        """Удаляет категорию. Возвращает (успех, данные_категории, количество_ссылок)."""

        def _delete_category_operation():
            # Получаем данные категории
            category_data = self._get_category_data_internal(category_id)
            if not category_data:
                error_msg = f"Категория с ID {category_id} не найдена"
                self.logger.error(error_msg)
                return False, {}, 0

            # Подсчитываем количество связанных ссылок
            links_count = self._count_category_links(category_id)

            self.logger.info(
                f"Подготовка к удалению категории {category_id}: {links_count} ссылок"
            )

            return True, category_data, links_count

        return self._execute_with_error_handling(
            _delete_category_operation,
            f"получить данные категории {category_id}",
            default_return=(False, {}, 0),
        )

    def confirm_delete_category(self, category_id: int) -> bool:
        """Подтверждает и выполняет удаление категории."""

        def _confirm_delete_operation():
            # Удаление через сервисный слой (UnitOfWork)
            if not self._structure_service:
                raise RuntimeError("StructureService недоступен для удаления категории")
            self._structure_service.delete_category(category_id)
            self._emit_item_signal(
                SignalTypes.ITEM_DELETED, StructureItemType.CATEGORY, category_id
            )
            self.logger.info(f"Удалена категория {category_id}")
            self._cache_manager.invalidate_first_category_cache()
            return True

        return self._execute_with_error_handling(
            _confirm_delete_operation,
            f"удалить категорию {category_id}",
            default_return=False,
        )

    def get_category_data(self, category_id: int) -> Optional[Dict[str, Any]]:
        """Получает данные категории с гарантированной нормализацией."""

        def _get_category_operation():
            category_data = self._get_category_data_internal(category_id)
            if category_data:
                self.logger.debug(f"Найдена категория {category_id}")
            else:
                self.logger.warning(f"Категория {category_id} не найдена")
            return category_data

        return self._exec_with_norm(
            _get_category_operation,
            f"загрузить данные категории {category_id}",
            default_return=None,
        )

    def get_categories(self, section_id: int) -> List[Dict[str, Any]]:
        """Получает список категорий для указанного раздела."""

        def _get_categories_operation():
            categories_data = (
                self._structure_service.get_categories(section_id)
                if self._structure_service
                else self.structure_model.get_categories(section_id)
            )
            result = categories_data if categories_data else []
            self.logger.debug(
                f"Загружено {len(result)} категорий для раздела {section_id}"
            )
            return result

        return self._exec_with_norm(
            _get_categories_operation,
            f"загрузить категории для раздела {section_id}",
            default_return=[],
        )

    def get_categories_batch(self, section_ids: List[int]) -> List[Dict[str, Any]]:
        """Получает категории для нескольких разделов с гарантированной нормализацией."""
        if not section_ids:
            return []

        def _get_categories_batch_operation():
            # Используем оптимизированный метод модели
            rows = self.structure_model.get_categories_batch(section_ids)
            return rows if rows else []

        # Применяем нормализацию и валидацию
        normalized = self._exec_with_norm(
            _get_categories_batch_operation,
            f"загрузить категории для разделов {section_ids}",
            default_return=[],
        )

        # Дополнительная валидация для batch операций
        return self._validate_batch_categories(normalized)

    def _process_item(
        self,
        data: Dict[str, Any],
        item_type: StructureItemType,
        item_id: Optional[int] = None,
        is_update: bool = False,
    ) -> bool:
        """Переопределяем обработку для категорий: используем StructureService для мутаций.

        Для иных типов элементов используем базовую реализацию.
        """
        # Если это не категория — передаём вниз в базу
        if item_type is not StructureItemType.CATEGORY:
            return super()._process_item(data, item_type, item_id, is_update)

        # Нет сервисного слоя — безопасный фоллбек на базовую реализацию
        if not getattr(self, "_structure_service", None):
            return super()._process_item(data, item_type, item_id, is_update)

        def _operation():
            if is_update:
                # Обновление через сервис
                self._structure_service.update_category(int(item_id), data)  # type: ignore[arg-type]
                current = self._structure_service.get_category_by_id(int(item_id)) or {}
                # parent_or_id = id элемента для updated
                self._emit_item_signal(
                    SignalTypes.ITEM_UPDATED, item_type, int(item_id), current
                )  # type: ignore[arg-type]
                # Инвалидация лёгкого кэша первой категории
                try:
                    self._cache_manager.invalidate_first_category_cache()
                except Exception:
                    pass
                return True
            else:
                # Создание через сервис
                new_id = self._structure_service.create_category(data)
                if not new_id:
                    return False
                current = self._structure_service.get_category_by_id(int(new_id)) or {
                    **data,
                    "id": int(new_id),
                }
                parent_id = (
                    (current.get("section_id") if isinstance(current, dict) else None)
                    or data.get("section_id")
                    or 0
                )
                # parent_or_id = section_id для added
                self._emit_item_signal(
                    SignalTypes.ITEM_ADDED, item_type, int(parent_id), current
                )
                try:
                    self._cache_manager.invalidate_first_category_cache()
                except Exception:
                    pass
                return True

        operation_name = "обновления" if is_update else "создания"
        result = self._execute_with_validation(
            _operation,
            data,
            item_type,
            operation_name,
            require_parent=not is_update,
        )
        return result if result is not None else False

    def get_first_category_id(self) -> Optional[int]:
        """Получает ID первой категории с кэшированием для оптимизации."""
        # Проверяем кэш
        cached_id = self._cache_manager.get_first_category_id()
        if cached_id is not None:
            self.logger.debug(
                f"Используется кэшированная первая категория: {cached_id}"
            )
            return cached_id

        def _get_first_category_operation():
            # Сервиса для этого метода пока нет — используем модель
            category_id = self.structure_model.get_first_category_id()
            if category_id:
                self.logger.debug(f"Найдена первая категория с ID: {category_id}")
                self._cache_manager.set_first_category_id(category_id)
                return category_id
            else:
                self.logger.debug("Категории не найдены")
                return None

        return self._execute_with_error_handling(
            _get_first_category_operation,
            "получить первую категорию",
            default_return=None,
        )

    def get_category_hierarchy(self, category_id: int) -> Optional[Dict[str, Any]]:
        """Получает иерархию (sphere_id, section_id) для категории с гарантированной нормализацией."""

        def _get_hierarchy_operation():
            hierarchy_data = (
                self._structure_service.get_category_hierarchy(category_id)
                if self._structure_service
                else self.structure_model.get_category_hierarchy(category_id)
            )
            if hierarchy_data:
                self.logger.debug(f"Найдена иерархия для категории {category_id}")
            else:
                self.logger.warning(f"Иерархия для категории {category_id} не найдена")
            return hierarchy_data

        return self._exec_with_norm(
            _get_hierarchy_operation,
            f"получить иерархию категории {category_id}",
            default_return=None,
        )

    def has_duplicate_category(
        self, section_id: int, category_name: str, exclude_id: Optional[int] = None
    ) -> bool:
        """Проверяет наличие дубликата категории в разделе."""

        def _check_duplicate_operation():
            return self.structure_model.has_duplicate_category(
                section_id, category_name, exclude_id
            )

        result = self._execute_with_error_handling(
            _check_duplicate_operation,
            f"проверить дубликат категории '{category_name}' в разделе {section_id}",
            default_return=False,
        )
        return bool(result) if result is not None else False

    def create_category_for_import(
        self, category_data: Dict[str, Any]
    ) -> Optional[int]:
        """Создает новую категорию для импорта."""
        if self._structure_service:
            return self._structure_service.create_category(category_data)
        else:
            raise RuntimeError("StructureService недоступен для создания категории")

    # Приватные вспомогательные методы

    def _get_category_data_internal(self, category_id: int) -> Optional[Dict[str, Any]]:
        """Внутренний метод для получения данных категории."""
        if self._structure_service:
            return self._structure_service.get_category_by_id(category_id)
        return self.structure_model.get_category_by_id(category_id)

    def _count_category_links(self, category_id: int) -> int:
        """Подсчитывает количество ссылок в категории."""
        try:
            return self.structure_model.count_links_by_category(category_id)
        except Exception as e:
            self.logger.error(
                f"Ошибка подсчета ссылок для категории {category_id}: {e}"
            )
            return 0

    def _emit_item_signal(
        self,
        signal_type: str,
        item_type: StructureItemType,
        item_id: int,
        data: Optional[Dict[str, Any]] = None,
    ):
        """Централизованная отправка сигналов для элементов структуры."""
        try:
            if data:
                self._emit_signal(signal_type, item_type.value, item_id, data)
            else:
                self._emit_signal(signal_type, item_type.value, item_id)
        except Exception as e:
            self.logger.error(
                f"Ошибка отправки сигнала {signal_type} для {item_type.value} {item_id}: {e}"
            )

    def _validate_batch_categories(
        self, categories: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Валидирует данные категорий после batch загрузки."""
        if not categories:
            return []

        from .normalization import validate_normalized_data

        # Требуем ключ section_id для группировки в coordination.py
        if not validate_normalized_data(categories, required_keys=["section_id"]):
            self.logger.warning(
                "Некоторые записи категорий не содержат обязательного ключа 'section_id'. "
                "Будут отфильтрованы некорректные элементы."
            )
            # Фильтруем только валидные элементы
            categories = [
                item
                for item in categories
                if isinstance(item, dict) and "section_id" in item
            ]

        return categories

    def _create_item_for_import(
        self, item_type: str, item_data: Dict[str, Any], create_func: Callable
    ) -> Optional[int]:
        """Универсальный метод создания элементов для импорта."""

        def _create_import_operation():
            result_id = create_func(item_data)
            if not result_id:
                self.logger.warning(f"Не удалось создать {item_type} для импорта")
                return None

            # Подготавливаем данные для сигнала
            signal_data = item_data.copy()
            signal_data["id"] = result_id

            # Определяем parent_id в зависимости от типа элемента
            parent_id = self._get_parent_id_for_item_type(item_type, signal_data)

            # Маппим строковый тип к enum и эмитируем сигнал централизованно
            enum_type = self._to_item_enum(item_type)
            self._emit_item_signal(
                SignalTypes.ITEM_ADDED, enum_type, parent_id, signal_data
            )

            self.logger.info(
                f"Создан {item_type} для импорта: {signal_data.get('name', 'без имени')}"
            )
            return result_id

        return self._execute_with_error_handling(
            _create_import_operation,
            f"создать {item_type} для импорта",
            default_return=None,
        )

    def _to_item_enum(self, item_type: str) -> StructureItemType:
        """Преобразует строковый тип элемента в enum StructureItemType."""
        mapping = {
            "section": StructureItemType.SECTION,
            "category": StructureItemType.CATEGORY,
            "link": StructureItemType.LINK,
        }
        try:
            return mapping[item_type]
        except KeyError:
            raise ValueError(f"Неподдерживаемый тип элемента: {item_type}")

    def _get_parent_id_for_item_type(
        self, item_type: str, item_data: Dict[str, Any]
    ) -> Optional[int]:
        """Определяет parent_id для элемента в зависимости от его типа."""
        # Для категорий используем section_id как parent_id
        if item_type == "category":
            return item_data.get("section_id")
        # Для других типов можно добавить логику позже
        elif item_type == "section":
            return item_data.get("sphere_id")
        elif item_type == "link":
            return item_data.get("category_id")
        else:
            raise ValueError(f"Неподдерживаемый тип элемента: {item_type}")
