# app/controllers/structure_modules/crud.py

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple


class StructureCrud:
    """Инкапсулирует CRUD-операции разделов и категорий.

    Зависимости передаются через конструктор для простоты тестирования и переиспользования.
    Контракты сигналов и кэша соблюдаются, но сам класс не знает о Qt и только вызывает
    переданные коллбеки (emit_*), не импортируя pyqt.
    """

    def __init__(
        self,
        *,
        service,  # StructureService
        cache,  # StructureCache или совместимый фасад (invalidate_*())
        async_ops,  # AsyncOperations для частичных дозагрузок
        emit_item_added,
        emit_item_updated,
        emit_item_deleted,
        schedule_structure_reload,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self._service = service
        self._cache = cache
        self._async = async_ops
        self._emit_item_added = emit_item_added
        self._emit_item_updated = emit_item_updated
        self._emit_item_deleted = emit_item_deleted
        self._schedule_reload = schedule_structure_reload
        self._log = logger or logging.getLogger(__name__)

    # ------- Разделы -------
    def create_section(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        section_id = self._service.create_section(data)
        if not section_id:
            return None
        section_data = self._service.get_section_by_id(section_id) or {}
        sphere_id = section_data.get("sphere_id") if isinstance(section_data, dict) else None
        try:
            self._emit_item_added("section", int(sphere_id) if sphere_id else 0, section_data)
        finally:
            if sphere_id:
                self._cache.invalidate_categories(sphere_id)  # секции кэшируются по sphere
            self._cache.invalidate_structure()
        return section_data or None

    def update_section(self, section_id: int, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        ok = self._service.update_section(section_id, data)
        if not ok:
            return None
        section_data = self._service.get_section_by_id(section_id) or {}
        sphere_id = section_data.get("sphere_id") if isinstance(section_data, dict) else None
        try:
            self._emit_item_updated("section", section_id, section_data)
        finally:
            if sphere_id:
                self._cache.invalidate_categories(sphere_id)
            self._cache.invalidate_structure()
        return section_data or None

    def delete_section(self, section_id: int) -> Tuple[bool, Dict[str, Any], int, int]:
        section_before = self._service.get_section_by_id(section_id) or {}
        if not section_before:
            return False, {}, 0, 0
        sphere_id = section_before.get("sphere_id") if isinstance(section_before, dict) else None
        categories_before = (
            self._service.get_categories(section_before.get("id", section_id)) if section_before else []
        )
        categories_count = len(categories_before or [])
        success = self._service.delete_section(section_id)
        if success:
            try:
                self._emit_item_deleted("section", section_id)
            finally:
                if sphere_id:
                    self._cache.invalidate_categories(sphere_id)
                self._cache.invalidate_structure()
        return success, section_before, categories_count, 0

    # ------- Категории -------
    def create_category(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        category_id = self._service.create_category(data)
        if not category_id:
            return None
        category_data = self._service.get_category_by_id(category_id) or {}
        section_id = category_data.get("section_id") if isinstance(category_data, dict) else None
        try:
            self._emit_item_added("category", int(section_id) if section_id else 0, category_data)
        finally:
            self._cache.invalidate_categories(section_id)
        return category_data or None

    def update_category(self, category_id: int, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        ok = self._service.update_category(category_id, data)
        if not ok:
            return None
        category_data = self._service.get_category_by_id(category_id) or {}
        section_id = category_data.get("section_id") if isinstance(category_data, dict) else None
        try:
            self._emit_item_updated("category", category_id, category_data)
        finally:
            self._cache.invalidate_categories(section_id)
        return category_data or None

    def delete_category(self, category_id: int) -> Tuple[bool, Dict[str, Any], int]:
        category_before = self._service.get_category_by_id(category_id) or {}
        if not category_before:
            return False, {}, 0
        section_id = category_before.get("section_id") if isinstance(category_before, dict) else None
        success = self._service.delete_category(category_id)
        if success:
            try:
                self._emit_item_deleted("category", category_id)
            finally:
                self._cache.invalidate_categories(section_id)
        return success, category_before, 0

    # ------- Пакетные операции -------
    def move_categories_batch(
        self, category_ids: List[int], target_section_id: int, base_row: int = 0
    ) -> List[int]:
        if not category_ids or not isinstance(target_section_id, int) or target_section_id <= 0:
            return []
        # Соберём источники для инвалидирования
        source_sections: set[int] = set()
        try:
            for cid in category_ids:
                try:
                    cdata = self._service.get_category_by_id(int(cid))
                except Exception:
                    cdata = None
                if isinstance(cdata, dict):
                    sid = cdata.get("section_id")
                    if isinstance(sid, int) and sid > 0 and sid != target_section_id:
                        source_sections.add(int(sid))
        except Exception:
            source_sections = set()

        moved_ids = self._service.move_categories_to_section_bulk(category_ids, target_section_id, base_row) or []
        # Инвалидируем кэши источников и целевой раздел; одну перезагрузку структуры спланирует вызывающий код
        try:
            for sid in source_sections:
                self._cache.invalidate_categories(sid)
        except Exception:
            pass
        self._cache.invalidate_categories(target_section_id)
        return moved_ids

    def create_categories_bulk(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not items:
            return []
        created_or_existing = self._service.create_categories_bulk(items)
        try:
            touched_sections = {
                c.get("section_id") for c in (created_or_existing or []) if isinstance(c, dict)
            }
            for sid in touched_sections:
                if sid:
                    self._cache.invalidate_categories(sid)
            self._schedule_reload(0)
        except Exception:
            pass
        return created_or_existing or []
