"""CRUD helpers for structure business logic."""

from __future__ import annotations

from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    from logging import Logger

    from app.controllers.business.structure_business import StructureBusinessLogic
    from app.controllers.structure_services.importer import ImportService
    from app.models import StructureModel
    from app.services.structure_service import StructureService

    from .async_service import StructureAsyncService
    from .cache_service import StructureCacheService


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
    def create_section(self, data: dict[str, Any]) -> Optional[dict[str, Any]]:
        section_id = self._structure_service.create_section(data)
        if not section_id:
            return None

        section_data = self._structure_service.get_section_by_id(section_id) or {}
        sphere_id = (
            section_data.get("sphere_id") if isinstance(section_data, dict) else None
        )
        try:
            self._owner.item_added.emit(
                "section", int(sphere_id) if sphere_id else 0, section_data
            )
        finally:
            if sphere_id:
                self._cache_service.invalidate_sections_cache(sphere_id)
            self._cache_service.invalidate_structure_cache()
        return section_data or None

    def update_section(
        self, section_id: int, data: dict[str, Any]
    ) -> Optional[dict[str, Any]]:
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

    def delete_section(
        self, section_id: int
    ) -> tuple[bool, dict[str, Any], int, int]:
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
    def create_category(self, data: dict[str, Any]) -> Optional[dict[str, Any]]:
        category_id = self._structure_service.create_category(data)
        if not category_id:
            return None

        category_data = self._structure_service.get_category_by_id(category_id) or {}
        section_id = (
            category_data.get("section_id") if isinstance(category_data, dict) else None
        )
        try:
            self._owner.item_added.emit(
                "category", int(section_id) if section_id else 0, category_data
            )
        finally:
            self._cache_service.invalidate_categories_cache(section_id)
        return category_data or None

    def update_category(
        self, category_id: int, data: dict[str, Any]
    ) -> Optional[dict[str, Any]]:
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

    def delete_category(self, category_id: int) -> tuple[bool, dict[str, Any], int]:
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

    def move_categories_batch(
        self, category_ids: list[int], target_section_id: int, base_row: int = 0
    ) -> list[int]:
        if (
            not category_ids
            or not isinstance(target_section_id, int)
            or target_section_id <= 0
        ):
            return []

        source_sections: set[int] = set()
        try:
            for cid in category_ids:
                try:
                    cdata = self._structure_service.get_category_by_id(int(cid))
                except Exception:  # pragma: no cover - defensive
                    cdata = None
                if isinstance(cdata, dict):
                    sid = cdata.get("section_id")
                    if isinstance(sid, int) and sid > 0 and sid != target_section_id:
                        source_sections.add(int(sid))
        except Exception:  # pragma: no cover - defensive
            source_sections = set()

        self._owner.begin_batch()
        try:
            moved_ids = self._structure_service.move_categories_to_section_bulk(
                category_ids, target_section_id, base_row
            )

            try:
                for sid in source_sections:
                    self._cache_service.invalidate_categories_cache(sid)
            except Exception:  # pragma: no cover - defensive
                pass
            self._cache_service.invalidate_categories_cache(target_section_id)

            return moved_ids or []
        finally:
            self._owner.end_batch()

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
