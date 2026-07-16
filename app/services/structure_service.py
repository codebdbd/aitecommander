from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import TypeAlias, TypeVar

from app.core.results import ErrorNotification, InvalidateRegion, Result
from app.models import Database, StructureCoordinator
from app.utils.db.sql_helpers import build_in_clause_placeholders
from app.services.bulk_operation_service import BulkOperationService

from .uow import unit_of_work

StructureRow: TypeAlias = dict[str, object]
StructureList: TypeAlias = list[StructureRow]
StructureTree: TypeAlias = dict[str, object]
StructureExport: TypeAlias = dict[str, list[StructureRow]]
ImportStats: TypeAlias = dict[str, int]
ExportFinishedCallback: TypeAlias = Callable[[StructureExport], None]
ImportFinishedCallback: TypeAlias = Callable[[ImportStats], None]
ErrorCallback: TypeAlias = Callable[[Exception, str], None]
ProgressCallback: TypeAlias = Callable[[int, int, str], None]


class StructureService:
    """
    Structure service (spheres -> sections -> categories).
    Stage 1: thin wrapper over current StructureCoordinator/Database without logic duplication.
    Stage 2+: gradual transfer of business logic from StructureCoordinator into service.
    """

    def __init__(self, db: Database):
        self.db = db
        # Temporarily use existing model as adapter
        self._model = StructureCoordinator(db)
        self._bulk = BulkOperationService(db)

    # --- Reading ---
    def get_spheres(self) -> StructureList:
        return self.db.spheres.get_spheres() or []

    def get_sphere_by_id(self, sphere_id: int) -> StructureRow | None:
        return self.db.spheres.get_sphere_by_id(sphere_id)

    def get_sections(self, sphere_id: int) -> StructureList:
        return self.db.sections.get_sections(sphere_id) or []

    def get_section_by_id(self, section_id: int) -> StructureRow | None:
        return self.db.sections.get_section_by_id(section_id)

    def get_categories(self, section_id: int) -> StructureList:
        return self.db.categories.get_categories(section_id) or []

    def get_category_by_id(self, category_id: int) -> StructureRow | None:
        return self.db.categories.get_category_by_id(category_id)

    def get_categories_by_ids(self, category_ids: list[int]) -> StructureList:
        return self.db.categories.get_categories_by_ids(category_ids) or []

    def get_category_hierarchy(self, category_id: int) -> StructureTree | None:
        return self._model.get_category_hierarchy(category_id)

    def get_full_structure(self) -> StructureList:
        # Use existing aggregating implementation
        return self.db.get_full_structure()

    # --- Statistics/calculations ---
    def count_nested_objects_for_section(self, section_id: int) -> tuple[int, int]:
        return self._model.count_nested_objects_for_section(section_id)

    def count_links_by_categories(self, category_ids: list[int]) -> dict[int, int]:
        """Batch link counting by categories (proxying to model)."""
        return self._model.count_links_by_categories(category_ids or [])

    # --- Mutations (with transactions) ---
    @unit_of_work
    def update_item_positions(self, table_name: str, ids_in_order: list[int]) -> None:
        # Guarantee atomicity of rearrangement
        self._model.update_item_positions(table_name, ids_in_order)

    @unit_of_work
    def create_section(self, data: StructureRow) -> Result[StructureRow | None]:
        try:
            section_id = self._model.create_section(data)
        except Exception as exc:
            return self._failure(exc)
        if not section_id:
            return self._failure(RuntimeError("Section creation failed"))
        section_data = self.db.sections.get_section_by_id(section_id) or {}
        sphere_id = (
            section_data.get("sphere_id") if isinstance(section_data, dict) else None
        )
        invalidate = self._invalidate_for_section(sphere_id, include_structure=True)
        return Result.success(section_data or None, invalidate=invalidate)

    @unit_of_work
    def update_section(
        self, section_id: int, data: StructureRow
    ) -> Result[StructureRow | None]:
        try:
            updated = self._model.update_section(section_id, data)
        except Exception as exc:
            return self._failure(exc)
        if not updated:
            return self._failure(RuntimeError("Section update failed"))
        section_data = self.db.sections.get_section_by_id(section_id) or {}
        sphere_id = (
            section_data.get("sphere_id") if isinstance(section_data, dict) else None
        )
        invalidate = self._invalidate_for_section(sphere_id, include_structure=True)
        return Result.success(section_data or None, invalidate=invalidate)

    @unit_of_work
    def delete_section(self, section_id: int) -> Result[StructureRow | None]:
        section_before = self.db.sections.get_section_by_id(section_id) or {}
        if not section_before:
            return self._failure(KeyError(f"Section {section_id} not found"))
        sphere_id = (
            section_before.get("sphere_id")
            if isinstance(section_before, dict)
            else None
        )
        invalidate = self._invalidate_for_section(sphere_id, include_structure=True)
        try:
            success = self._model.delete_section(section_id)
        except Exception as exc:
            return self._failure(exc, value=section_before, invalidate=invalidate)
        if not success:
            return self._failure(
                RuntimeError("Section deletion failed"),
                value=section_before,
                invalidate=invalidate,
            )
        return Result.success(section_before, invalidate=invalidate)

    def delete_sections_bulk(
        self, section_ids: list[int]
    ) -> Result[int]:
        """Batch deletion of sections in one transaction."""

        sphere_ids = self._sphere_ids_for_section_ids(section_ids or [])
        invalidate = self._invalidate_for_sections(
            sphere_ids, include_structure=True
        )
        try:
            deleted = self._bulk.delete_sections_bulk(section_ids or [])
        except Exception as exc:
            return self._failure(exc, value=0, invalidate=invalidate)
        return Result.success(deleted, invalidate=invalidate)

    def create_category(self, data: StructureRow) -> Result[StructureRow | None]:
        try:
            category_id = self._model.create_category(data)
        except Exception as exc:
            return self._failure(exc)
        if not category_id:
            return self._failure(RuntimeError("Category creation failed"))
        category_data = self.db.categories.get_category_by_id(category_id) or {}
        section_id = (
            category_data.get("section_id") if isinstance(category_data, dict) else None
        )
        invalidate = self._invalidate_for_category(section_id)
        return Result.success(category_data or None, invalidate=invalidate)

    def update_category(
        self, category_id: int, data: StructureRow
    ) -> Result[StructureRow | None]:
        try:
            updated = self._model.update_category(category_id, data)
        except Exception as exc:
            return self._failure(exc)
        if not updated:
            return self._failure(RuntimeError("Category update failed"))
        category_data = self.db.categories.get_category_by_id(category_id) or {}
        section_id = (
            category_data.get("section_id") if isinstance(category_data, dict) else None
        )
        invalidate = self._invalidate_for_category(section_id)
        return Result.success(category_data or None, invalidate=invalidate)

    def delete_category(self, category_id: int) -> Result[StructureRow | None]:
        category_before = self.db.categories.get_category_by_id(category_id) or {}
        if not category_before:
            return self._failure(KeyError(f"Category {category_id} not found"))
        section_id = (
            category_before.get("section_id")
            if isinstance(category_before, dict)
            else None
        )
        invalidate = self._invalidate_for_category(section_id)
        try:
            success = self._model.delete_category(category_id)
        except Exception as exc:
            return self._failure(exc, value=category_before, invalidate=invalidate)
        if not success:
            return self._failure(
                RuntimeError("Category deletion failed"),
                value=category_before,
                invalidate=invalidate,
            )
        return Result.success(category_before, invalidate=invalidate)

    def delete_categories_bulk(
        self, category_ids: list[int]
    ) -> Result[int]:
        """Batch deletion of categories in one transaction."""

        section_ids = self._section_ids_for_category_ids(category_ids or [])
        invalidate = self._invalidate_for_category_sections(section_ids)
        try:
            deleted = self._bulk.delete_categories_bulk(category_ids or [])
        except Exception as exc:
            return self._failure(exc, value=0, invalidate=invalidate)
        return Result.success(deleted, invalidate=invalidate)

    def create_categories_bulk(
        self, items: StructureList
    ) -> Result[StructureList | None]:
        """Batch creation of categories (single transaction)."""

        try:
            created = self._bulk.create_categories_bulk(items or [])
        except Exception as exc:
            return self._failure(exc, value=None)
        section_ids = self._section_ids_from_rows(created or [])
        invalidate = self._invalidate_for_category_sections(section_ids)
        return Result.success(created or None, invalidate=invalidate)

    def update_categories_bulk(self, updates: StructureList) -> Result[int]:
        """Batch update of categories (single transaction)."""

        section_ids = self._section_ids_from_rows(updates or [])
        if not section_ids:
            update_ids = [
                row.get("id")
                for row in (updates or [])
                if isinstance(row, dict) and isinstance(row.get("id"), int)
            ]
            section_ids = self._section_ids_for_category_ids(update_ids)
        invalidate = self._invalidate_for_category_sections(section_ids)
        try:
            updated = self._bulk.update_categories_bulk(updates or [])
        except Exception as exc:
            return self._failure(exc, value=0, invalidate=invalidate)
        return Result.success(updated, invalidate=invalidate)

    def move_categories_to_section_bulk(
        self, category_ids: list[int], target_section_id: int, base_row: int = 0
    ) -> Result[list[int]]:
        """Atomically moves categories to target section in one transaction."""

        source_sections = self._section_ids_for_category_ids(category_ids or [])
        touched_sections = set(source_sections)
        if isinstance(target_section_id, int):
            touched_sections.add(target_section_id)
        invalidate = self._invalidate_for_category_sections(touched_sections)
        try:
            moved = self._bulk.move_categories_bulk(
                category_ids or [],
                int(target_section_id),
                int(base_row) if isinstance(base_row, int) else 0,
            )
        except Exception as exc:
            return self._failure(exc, value=[], invalidate=invalidate)
        return Result.success(moved or [], invalidate=invalidate)

    # --- Import/export ---
    def export_full_structure(self) -> StructureExport:
        return self.db.export_full_structure()

    def export_full_structure_async(
        self,
        on_finished: ExportFinishedCallback | None = None,
        on_error: ErrorCallback | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> None:
        """Asynchronous structure export with callbacks."""

        return self.db.export_full_structure_async(on_finished, on_error, on_progress)

    @unit_of_work
    def import_full_structure(self, data: StructureList) -> None:
        self.db.import_full_structure(data)

    def import_full_structure_async(
        self,
        data: StructureList,
        on_finished: ImportFinishedCallback | None = None,
        on_error: ErrorCallback | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> None:
        """Asynchronous structure import with callbacks."""
        return self.db.import_full_structure_async(
            data, on_finished, on_error, on_progress
        )

    def export_section_tree(self, section_id: int) -> StructureTree:
        return self.db.export_section_tree(section_id)

    @unit_of_work
    def import_section_tree(self, tree: StructureTree) -> None:
        self.db.import_section_tree(tree)

    def import_section_trees_bulk(self, trees: list[StructureTree]) -> None:
        """Imports multiple section subtrees in one transaction."""
        self.db.import_section_trees_bulk(trees or [])

    def export_category_tree(self, category_id: int) -> StructureTree:
        return self.db.export_category_tree(category_id)

    @unit_of_work
    def import_category_tree(self, tree: StructureTree) -> None:
        self.db.import_category_tree(tree)

    # --- Bulk operations ---
    def import_category_trees_bulk(self, trees: list[StructureTree]) -> None:
        """Imports multiple category subtrees in one operation (one transaction).

        Delegates to Database.import_category_trees_bulk to avoid nested transactions.
        Used, for example, for quick undo of batch category deletion.
        """
        self.db.import_category_trees_bulk(trees or [])

    # --- Internal helpers -------------------------------------------------
    def _invalidate_for_section(
        self,
        sphere_id: object,
        *,
        include_structure: bool = False,
    ) -> tuple[InvalidateRegion, ...]:
        regions: list[InvalidateRegion] = []
        if isinstance(sphere_id, int):
            regions.append(InvalidateRegion(scope="sections", identifier=sphere_id))
        if include_structure:
            regions.append(InvalidateRegion(scope="structure", identifier=None))
        return tuple(regions)

    def _invalidate_for_category(
        self,
        section_id: object,
    ) -> tuple[InvalidateRegion, ...]:
        if not isinstance(section_id, int):
            return tuple()
        return (InvalidateRegion(scope="categories", identifier=section_id),)

    def _invalidate_for_sections(
        self,
        sphere_ids: Iterable[int],
        *,
        include_structure: bool = False,
    ) -> tuple[InvalidateRegion, ...]:
        regions: list[InvalidateRegion] = []
        seen: set[int] = set()
        for sphere_id in sphere_ids:
            if isinstance(sphere_id, int) and sphere_id not in seen:
                seen.add(sphere_id)
                regions.append(InvalidateRegion(scope="sections", identifier=sphere_id))
        if include_structure:
            regions.append(InvalidateRegion(scope="structure", identifier=None))
        return tuple(regions)

    T = TypeVar("T")

    def _section_ids_from_rows(
        self,
        rows: StructureList,
    ) -> list[int]:
        section_ids: list[int] = []
        for row in rows:
            if isinstance(row, dict):
                section_id = row.get("section_id")
                if isinstance(section_id, int):
                    section_ids.append(section_id)
        return section_ids

    def _section_ids_for_category_ids(
        self,
        category_ids: Iterable[object],
    ) -> list[int]:
        ids = self._normalize_positive_int_ids(category_ids)
        if not ids:
            return []

        connection = getattr(self.db, "connection", None)
        if connection is None or not hasattr(connection, "execute"):
            return self._section_ids_for_category_ids_fallback(ids)

        category_to_section: dict[int, int] = {}
        chunk_size = 900
        for start in range(0, len(ids), chunk_size):
            chunk = ids[start : start + chunk_size]
            placeholders = build_in_clause_placeholders(len(chunk))
            rows = connection.execute(
                f"SELECT id, section_id FROM category WHERE id IN ({placeholders})",
                tuple(chunk),
            ).fetchall()
            for row in rows or []:
                try:
                    category_id = int(row["id"])
                    section_id = int(row["section_id"])
                except Exception:
                    continue
                category_to_section[category_id] = section_id

        section_ids: list[int] = []
        seen: set[int] = set()
        for category_id in ids:
            section_id = category_to_section.get(category_id)
            if section_id is None or section_id in seen:
                continue
            seen.add(section_id)
            section_ids.append(section_id)
        return section_ids

    def _sphere_ids_for_section_ids(
        self,
        section_ids: Iterable[object],
    ) -> list[int]:
        ids = self._normalize_positive_int_ids(section_ids)
        if not ids:
            return []

        connection = getattr(self.db, "connection", None)
        if connection is None or not hasattr(connection, "execute"):
            return self._sphere_ids_for_section_ids_fallback(ids)

        section_to_sphere: dict[int, int] = {}
        chunk_size = 900
        for start in range(0, len(ids), chunk_size):
            chunk = ids[start : start + chunk_size]
            placeholders = build_in_clause_placeholders(len(chunk))
            rows = connection.execute(
                f"SELECT id, sphere_id FROM section WHERE id IN ({placeholders})",
                tuple(chunk),
            ).fetchall()
            for row in rows or []:
                try:
                    section_id = int(row["id"])
                    sphere_id = int(row["sphere_id"])
                except Exception:
                    continue
                section_to_sphere[section_id] = sphere_id

        sphere_ids: list[int] = []
        seen: set[int] = set()
        for section_id in ids:
            sphere_id = section_to_sphere.get(section_id)
            if sphere_id is None or sphere_id in seen:
                continue
            seen.add(sphere_id)
            sphere_ids.append(sphere_id)
        return sphere_ids

    def _normalize_positive_int_ids(self, ids: Iterable[object]) -> list[int]:
        result: list[int] = []
        seen: set[int] = set()
        for value in ids:
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                continue
            if value in seen:
                continue
            seen.add(value)
            result.append(value)
        return result

    def _section_ids_for_category_ids_fallback(
        self,
        category_ids: Iterable[int],
    ) -> list[int]:
        section_ids: list[int] = []
        seen: set[int] = set()
        for category_id in category_ids:
            category_data = self.db.categories.get_category_by_id(category_id) or {}
            if not isinstance(category_data, dict):
                continue
            section_id = category_data.get("section_id")
            if isinstance(section_id, int) and section_id not in seen:
                seen.add(section_id)
                section_ids.append(section_id)
        return section_ids

    def _sphere_ids_for_section_ids_fallback(
        self,
        section_ids: Iterable[int],
    ) -> list[int]:
        sphere_ids: list[int] = []
        seen: set[int] = set()
        for section_id in section_ids:
            section_data = self.db.sections.get_section_by_id(section_id) or {}
            if not isinstance(section_data, dict):
                continue
            sphere_id = section_data.get("sphere_id")
            if isinstance(sphere_id, int) and sphere_id not in seen:
                seen.add(sphere_id)
                sphere_ids.append(sphere_id)
        return sphere_ids

    def _invalidate_for_category_sections(
        self,
        section_ids: Iterable[int],
    ) -> tuple[InvalidateRegion, ...]:
        regions: list[InvalidateRegion] = []
        seen: set[int] = set()
        for section_id in section_ids:
            if isinstance(section_id, int) and section_id not in seen:
                seen.add(section_id)
                regions.append(InvalidateRegion(scope="categories", identifier=section_id))
        return tuple(regions)

    def _failure(
        self,
        error: Exception,
        *,
        value: T | None = None,
        invalidate: tuple[InvalidateRegion, ...] | None = None,
        notifications: tuple[ErrorNotification, ...] | None = None,
    ) -> Result[T | None]:
        return Result.failure(
            error=error,
            value=value,
            invalidate=invalidate,
            notifications=notifications,
        )
