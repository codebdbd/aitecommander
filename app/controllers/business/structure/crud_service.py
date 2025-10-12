"""CRUD helpers for structure business logic."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, TYPE_CHECKING, Set

try:
    from app.utils.metrics import measure_time
except ImportError:
    # Fallback если метрики недоступны
    def measure_time(name: str, **kwargs):
        def decorator(func):
            return func
        return decorator

if TYPE_CHECKING:  # pragma: no cover - typing only
    from logging import Logger

    from app.controllers.business.structure_business import StructureBusinessLogic
    from app.controllers.structure_services.importer import ImportService
    from app.models import StructureModel
    from app.services.structure_service import StructureService

    from .async_service import StructureAsyncService
    from .cache_service import StructureCacheService


@dataclass(slots=True)
class MoveCategoriesBatchResult:
    moved_ids: list[int]
    touched_sections: Set[int]


class StructureCrudService:
    """Encapsulates CRUD operations and related cache updates."""

    def __init__(
        self,
        owner: StructureBusinessLogic,
        structure_service: StructureService,
        cache_service: StructureCacheService,
        async_service: StructureAsyncService,
        import_service: ImportService,
        structure_model: StructureModel,
        logger: Logger,
    ) -> None:
        self._owner = owner
        self._structure_service = structure_service
        self._cache_service = cache_service
        self._async_service = async_service
        self._import_service = import_service
        self._structure_model = structure_model
        self._logger = logger

    # ------------------------------------------------------------------
    # Section operations
    # ------------------------------------------------------------------
    @measure_time("create_section", log_threshold_ms=200)
    def create_section(self, data: dict[str, Any]) -> Optional[dict[str, Any]]:
        """Создаёт раздел и эмитит сигнал.
        
        ✅ ИСПРАВЛЕНИЕ: Добавлена проверка на None перед использованием sphere_id.
        ✅ Метрика производительности: измеряется время выполнения.
        """
        section_id = self._structure_service.create_section(data)
        if not section_id:
            return None

        section_data = self._structure_service.get_section_by_id(section_id) or {}
        sphere_id = (
            section_data.get("sphere_id") if isinstance(section_data, dict) else None
        )
        try:
            # ✅ Проверяем sphere_id на None перед использованием
            if sphere_id is not None and isinstance(sphere_id, int):
                self._owner.item_added.emit("section", int(sphere_id), section_data)
            else:
                self._logger.warning("create_section: sphere_id is None or invalid")
        finally:
            if sphere_id:
                self._cache_service.invalidate_sections_cache(sphere_id)
            self._cache_service.invalidate_structure_cache()
        return section_data or None

    @measure_time("update_section", log_threshold_ms=200)
    def update_section(
        self, section_id: int, data: dict[str, Any]
    ) -> Optional[dict[str, Any]]:
        """Обновляет раздел и эмитит сигнал.
        
        ✅ Метрика производительности: измеряется время выполнения.
        """
        ok = self._structure_service.update_section(section_id, data)
        if not ok:
            return None

        section_data = self._structure_service.get_section_by_id(section_id) or {}
        sphere_id = (
            section_data.get("sphere_id") if isinstance(section_data, dict) else None
        )
        try:
            self._owner.item_updated.emit("section", section_id, section_data)
        finally:
            if sphere_id:
                self._cache_service.invalidate_sections_cache(sphere_id)
            self._cache_service.invalidate_structure_cache()
        return section_data or None

    @measure_time("delete_section", log_threshold_ms=300)
    def delete_section(
        self, section_id: int
    ) -> tuple[bool, dict[str, Any], int, int]:
        """Удаляет раздел и эмитит сигнал.
        
        ✅ Метрика производительности: измеряется время выполнения.
        """
        section_before = self._structure_service.get_section_by_id(section_id) or {}
        if not section_before:
            return False, {}, 0, 0

        sphere_id = (
            section_before.get("sphere_id")
            if isinstance(section_before, dict)
            else None
        )
        categories_before = (
            self._structure_service.get_categories(section_before.get("id", section_id))
            if section_before
            else []
        )
        categories_count = len(categories_before or [])
        success = self._structure_service.delete_section(section_id)
        if success:
            try:
                self._owner.item_deleted.emit("section", section_id)
            finally:
                if sphere_id:
                    self._cache_service.invalidate_sections_cache(sphere_id)
                self._cache_service.invalidate_structure_cache()
        return success, section_before, categories_count, 0

    # ------------------------------------------------------------------
    # Category operations
    # ------------------------------------------------------------------
    @measure_time("create_category", log_threshold_ms=200)
    def create_category(self, data: dict[str, Any]) -> Optional[dict[str, Any]]:
        """Создаёт категорию и эмитит сигнал.
        
        ✅ ИСПРАВЛЕНИЕ: Добавлена проверка на None перед использованием section_id.
        ✅ Метрика производительности: измеряется время выполнения.
        """
        category_id = self._structure_service.create_category(data)
        if not category_id:
            return None

        category_data = self._structure_service.get_category_by_id(category_id) or {}
        section_id = (
            category_data.get("section_id") if isinstance(category_data, dict) else None
        )
        try:
            # ✅ Проверяем section_id на None перед использованием
            if section_id is not None and isinstance(section_id, int):
                self._owner.item_added.emit("category", int(section_id), category_data)
            else:
                self._logger.warning("create_category: section_id is None or invalid")
        finally:
            self._cache_service.invalidate_categories_cache(section_id)
        return category_data or None

    @measure_time("update_category", log_threshold_ms=200)
    def update_category(
        self, category_id: int, data: dict[str, Any]
    ) -> Optional[dict[str, Any]]:
        """Обновляет категорию и эмитит сигнал.
        
        ✅ Метрика производительности: измеряется время выполнения.
        """
        ok = self._structure_service.update_category(category_id, data)
        if not ok:
            return None

        category_data = self._structure_service.get_category_by_id(category_id) or {}
        section_id = (
            category_data.get("section_id") if isinstance(category_data, dict) else None
        )
        try:
            self._owner.item_updated.emit("category", category_id, category_data)
        finally:
            self._cache_service.invalidate_categories_cache(section_id)
        return category_data or None

    @measure_time("delete_category", log_threshold_ms=300)
    def delete_category(self, category_id: int) -> tuple[bool, dict[str, Any], int]:
        """Удаляет категорию и эмитит сигнал.
        
        ✅ Метрика производительности: измеряется время выполнения.
        """
        category_before = self._structure_service.get_category_by_id(category_id) or {}
        if not category_before:
            return False, {}, 0

        section_id = (
            category_before.get("section_id")
            if isinstance(category_before, dict)
            else None
        )
        success = self._structure_service.delete_category(category_id)
        if success:
            try:
                self._owner.item_deleted.emit("category", category_id)
            finally:
                self._cache_service.invalidate_categories_cache(section_id)
        return success, category_before, 0

    @measure_time("move_categories_batch", log_threshold_ms=500)
    def move_categories_batch(
        self, category_ids: list[int], target_section_id: int, base_row: int = 0
    ) -> list[int]:
        """Перемещает категории batch операцией.
        
        ✅ Метрика производительности: измеряется время выполнения.
        """
        if (
            not category_ids
            or not isinstance(target_section_id, int)
            or target_section_id <= 0
        ):
            return MoveCategoriesBatchResult(moved_ids=[], touched_sections=set())

        source_sections: Set[int] = set()
        try:
            for cid in category_ids:
                try:
                    cdata = self._structure_service.get_category_by_id(int(cid))
                except (ValueError, TypeError) as e:
                    # ✅ Ожидаемые ошибки валидации
                    self._logger.debug("Invalid category_id %s: %s", cid, e)
                    cdata = None
                except Exception as e:
                    # ✅ Неожиданные ошибки
                    self._logger.exception("Unexpected error getting category %s: %s", cid, e)
                    cdata = None
                if isinstance(cdata, dict):
                    sid = cdata.get("section_id")
                    if isinstance(sid, int) and sid > 0 and sid != target_section_id:
                        source_sections.add(int(sid))
        except (ValueError, TypeError) as e:
            # ✅ Ожидаемые ошибки
            self._logger.warning("Error collecting source sections: %s", e)
            source_sections = set()
        except Exception as e:
            # ✅ Неожиданные ошибки
            self._logger.exception("Critical error in move_categories_batch: %s", e)
            raise

        moved_ids = self._structure_service.move_categories_to_section_bulk(
            category_ids, target_section_id, base_row
        ) or []

        touched_sections: Set[int] = set(source_sections)
        if isinstance(target_section_id, int) and target_section_id > 0:
            touched_sections.add(int(target_section_id))

        for sid in touched_sections:
            try:
                self._cache_service.invalidate_categories_cache(sid)
            except Exception:  # pragma: no cover - defensive
                pass

        try:
            self._cache_service.invalidate_structure_cache()
        except Exception:  # pragma: no cover - defensive
            pass

        try:
            from app.config_data import app_config

            delay = int(app_config.ui.get_structure_reload_immediate_delay_ms())
            self._async_service.schedule_structure_reload(delay)
        except Exception:  # pragma: no cover - defensive
            pass

        return MoveCategoriesBatchResult(
            moved_ids=moved_ids, touched_sections=touched_sections
        )

    def create_categories_bulk(
        self, items: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        if not items:
            return []

        created_or_existing = self._structure_service.create_categories_bulk(items)
        try:
            touched_sections = {
                c.get("section_id")
                for c in (created_or_existing or [])
                if isinstance(c, dict)
            }
            for sid in touched_sections:
                if sid:
                    self._cache_service.invalidate_categories_cache(sid)
            from app.config_data import app_config

            delay = int(app_config.ui.get_structure_reload_immediate_delay_ms())
            self._async_service.schedule_structure_reload(delay)
        except Exception:  # pragma: no cover - defensive
            pass
        return created_or_existing or []

    def create_category_for_import(
        self, category_data: dict[str, Any]
    ) -> Optional[int]:
        """Create a category during import workflow and refresh caches."""

        category_id = self._import_service.create_category_for_import(
            self._structure_model, category_data, self._logger
        )
        if category_id:
            section_id = category_data.get("section_id")
            if section_id:
                self._cache_service.invalidate_categories_cache(section_id)
        return category_id
