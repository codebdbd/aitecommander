# app/controllers/structure_modules/category_operations.py

"""Модуль для операций с категориями."""

import logging
from typing import Any, Callable, Dict, List, Optional
from dataclasses import dataclass

from .types import (
    CategoryData, CategoryCreateData, CategoryUpdateData,
    StructureItemType, SignalType, CategoryNestedCount
)

from app.models.structure_model import StructureModel
from app.services.structure_service import StructureService

from .base import BaseOperations, StructureItemType


class SignalTypes:
    """Константы для типов сигналов."""

    ITEM_ADDED = "item_added"
    ITEM_DELETED = "item_deleted"
    ITEM_UPDATED = "item_updated"


@dataclass
class CategoryDeletionInfo:
    """Информация об удалении категории."""
    
    success: bool
    category_data: CategoryData
    links_count: int
    
    @classmethod
    def create_empty(cls) -> "CategoryDeletionInfo":
        """Создает пустую информацию об удалении."""
        empty_category: CategoryData = {  # type: ignore
            "id": 0,
            "name": "",
            "section_id": 0,
            "description": None,
            "position": 0,
            "is_active": False,
            "color": None,
            "icon": None,
            "created_at": None,
            "updated_at": None
        }
        return cls(False, empty_category, 0)


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

    def create_category(self, data: CategoryCreateData) -> bool:
        """Создает новую категорию."""
        # Делегируем в универсальный метод базового класса
        result = self.create_item(StructureItemType.CATEGORY, data)
        if result:
            self._cache_manager.invalidate_first_category_cache()
        return result

    def update_category(self, category_id: int, data: CategoryUpdateData) -> bool:
        """Обновляет существующую категорию."""
        # Делегируем в универсальный метод базового класса
        result = self.update_item(StructureItemType.CATEGORY, category_id, data)
        if result:
            self._cache_manager.invalidate_first_category_cache()
        return result

    def delete_category(self, category_id: int) -> CategoryDeletionInfo:
        """Удаляет категорию. Возвращает информацию об удалении."""

        def _delete_category_operation():
            # Получаем данные категории
            category_data = self._get_category_data_internal(category_id)
            if not category_data:
                error_msg = f"Категория с ID {category_id} не найдена"
                self.logger.error(error_msg)
                return CategoryDeletionInfo.create_empty()
            
            # ✅ Преобразуем в строго типизированные данные
            typed_category_data: CategoryData = category_data  # type: ignore

            # Подсчитываем количество связанных ссылок
            links_count = self._count_category_links(category_id)

            self.logger.info(
                "Подготовка к удалению категории %s: %s ссылок",
                category_id,
                links_count,
            )

            return CategoryDeletionInfo(True, typed_category_data, links_count)

        return self._execute_with_error_handling(
            _delete_category_operation,
            f"получить данные категории {category_id}",
            default_return=CategoryDeletionInfo.create_empty(),
        )

    def confirm_delete_category(self, category_id: int) -> bool:
        """Подтверждает и выполняет удаление категории."""
        if not self._structure_service:
            def _raise_service_error():
                raise RuntimeError("StructureService недоступен для удаления категории")
            
            return self._execute_with_error_handling(
                _raise_service_error,
                f"удалить категорию {category_id}",
                default_return=False,
            )

        def _delete():
            self._structure_service.delete_category(category_id)

        result = self.delete_item(
            StructureItemType.CATEGORY,
            category_id,
            delete_func=_delete,
            emit_data=None,
        )
        if result:
            self._cache_manager.invalidate_first_category_cache()
        return result

    def get_category_data(self, category_id: int) -> Optional[Dict[str, Any]]:
        """Получает данные категории с гарантированной нормализацией."""

        def _get_category_operation():
            category_data = self._get_category_data_internal(category_id)
            if category_data:
                self.logger.debug("Найдена категория %s", category_id)
            else:
                self.logger.warning("Категория %s не найдена", category_id)
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
                "Загружено %s категорий для раздела %s",
                len(result),
                section_id,
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
        *,
        require_parent: bool = True,
    ) -> bool:
        """Переопределяем обработку для категорий: используем StructureService для мутаций.

        Для иных типов элементов используем базовую реализацию.
        """
        # Если это не категория — передаём вниз в базу
        if item_type is not StructureItemType.CATEGORY:
            return super()._process_item(
                data, item_type, item_id, is_update, require_parent=require_parent
            )

        # Нет сервисного слоя — безопасный фоллбек на базовую реализацию
        if not getattr(self, "_structure_service", None):
            return super()._process_item(
                data, item_type, item_id, is_update, require_parent=require_parent
            )

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
            require_parent=require_parent,
        )
        return result if result is not None else False

    def get_first_category_id(self) -> Optional[int]:
        """Получает ID первой категории с кэшированием для оптимизации."""
        # Проверяем кэш
        cached_id = self._cache_manager.get_first_category_id()
        if cached_id is not None:
            self.logger.debug(
                "Используется кэшированная первая категория: %s", cached_id
            )
            return cached_id

        def _get_first_category_operation():
            # Сервиса для этого метода пока нет — используем модель
            category_id = self.structure_model.get_first_category_id()
            if category_id:
                self.logger.debug("Найдена первая категория с ID: %s", category_id)
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

    def get_first_category_id_for_sphere(self, sphere_id: int) -> Optional[int]:
        """Получить ID первой категории в рамках конкретной сферы (per-sphere cache).

        - Не ломает совместимость: это дополнительный метод.
        - Сначала пытается взять из per-sphere кэша в `CacheManager`.
        - При промахе вычисляет через StructureModel/Service и записывает кэш.
        """
        # 1) Кэш per-sphere
        try:
            cached = self._cache_manager.get_first_category_id_for_sphere(sphere_id)
        except Exception:
            cached = None
        if cached is not None:
            self.logger.debug(
                "Используется per-sphere кэш первой категории для сферы %s: %s",
                sphere_id,
                cached,
            )
            return cached

        # 2) Вычисление: берём первую категорию в первой секции сферы, где есть категории
        def _compute_first_for_sphere() -> Optional[int]:
            try:
                get_sections = (
                    self._structure_service.get_sections
                    if self._structure_service
                    else self.structure_model.get_sections
                )
                get_categories = (
                    self._structure_service.get_categories
                    if self._structure_service
                    else self.structure_model.get_categories
                )
                sections = get_sections(int(sphere_id)) or []
                for section in sections:
                    sid = section.get("id") if isinstance(section, dict) else None
                    if sid is None:
                        continue
                    cats = get_categories(int(sid)) or []
                    if cats:
                        first_id = cats[0].get("id") if isinstance(cats[0], dict) else None
                        return int(first_id) if first_id is not None else None
                return None
            except Exception as e:
                self.logger.error(
                    "Ошибка вычисления первой категории для сферы %s: %s", sphere_id, e
                )
                return None

        result = _compute_first_for_sphere()
        try:
            self._cache_manager.set_first_category_id_for_sphere(sphere_id, result)
        except Exception:
            pass
        return result

    def get_category_hierarchy(self, category_id: int) -> Optional[Dict[str, Any]]:
        """Получает иерархию (sphere_id, section_id) для категории с гарантированной нормализацией."""

        def _get_hierarchy_operation():
            hierarchy_data = (
                self._structure_service.get_category_hierarchy(category_id)
                if self._structure_service
                else self.structure_model.get_category_hierarchy(category_id)
            )
            if hierarchy_data:
                self.logger.debug("Найдена иерархия для категории %s", category_id)
            else:
                self.logger.warning("Иерархия для категории %s не найдена", category_id)
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
                "Ошибка подсчета ссылок для категории %s: %s",
                category_id,
                e,
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
                "Ошибка отправки сигнала %s для %s %s: %s",
                signal_type,
                item_type.value,
                item_id,
                e,
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
                self.logger.warning("Не удалось создать %s для импорта", item_type)
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
                "Создан %s для импорта: %s",
                item_type,
                signal_data.get("name", "без имени"),
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
