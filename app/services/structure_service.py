from __future__ import annotations

from typing import Any

from app.models import Database, StructureModel

from .uow import unit_of_work


class StructureService:
    """
    Structure service (spheres -> sections -> categories).
    Stage 1: thin wrapper over current StructureModel/Database without logic duplication.
    Stage 2+: gradual transfer of business logic from StructureModel into service.
    """

    def __init__(self, db: Database):
        self.db = db
        # Temporarily use existing model as adapter
        self._model = StructureModel(db)

    # --- Reading ---
    def get_spheres(self) -> list[dict[str, Any]]:
        return self._model.get_spheres()

    def get_sphere_by_id(self, sphere_id: int) -> dict[str, Any] | None:
        return self._model.get_sphere_by_id(sphere_id)

    def get_sections(self, sphere_id: int) -> list[dict[str, Any]]:
        return self._model.get_sections(sphere_id)

    def get_section_by_id(self, section_id: int) -> dict[str, Any] | None:
        return self._model.get_section_by_id(section_id)

    def get_categories(self, section_id: int) -> list[dict[str, Any]]:
        return self._model.get_categories(section_id)

    def get_category_by_id(self, category_id: int) -> dict[str, Any] | None:
        return self._model.get_category_by_id(category_id)

    def get_category_hierarchy(self, category_id: int) -> dict[str, Any] | None:
        return self._model.get_category_hierarchy(category_id)

    def get_full_structure(self) -> list[dict[str, Any]]:
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
    def create_section(self, data: dict[str, Any]) -> int | None:
        return self._model.create_section(data)

    @unit_of_work
    def update_section(self, section_id: int, data: dict[str, Any]) -> bool:
        return self._model.update_section(section_id, data)

    @unit_of_work
    def delete_section(self, section_id: int) -> bool:
        return self._model.delete_section(section_id)

    @unit_of_work
    def create_category(self, data: dict[str, Any]) -> int | None:
        return self._model.create_category(data)

    def update_category(self, category_id: int, data: dict[str, Any]) -> bool:
        # IMPORTANT: StructureModel.update_category -> upsert_category category
        # uses internal transaction (see CategoryModel.upsert_category with self.transaction()).
        # Wrapping here in UnitOfWork will lead to nested transaction in SQLite
        # (error "cannot start a transaction within a transaction") and update won't be saved.
        # Therefore call directly without external UnitOfWork.
        return self._model.update_category(category_id, data)

    def delete_category(self, category_id: int) -> bool:
        # IMPORTANT: CategoryModel.delete_category() already uses self.transaction()
        # and manages transaction independently (BEGIN/COMMIT). Wrapping
        # in external UnitOfWork will lead to nested transactions in SQLite and
        # error of type "cannot start a transaction within a transaction".
        return self._model.delete_category(category_id)

    def delete_categories_bulk(self, category_ids: list[int]) -> int:
        """Batch deletion of categories in one transaction (delegating to model).

        IMPORTANT: model method manages transaction itself, so we DON'T use UnitOfWork here,
        to avoid nested transactions in SQLite.
        Returns number of deleted categories.
        """
        return self.db.categories.delete_categories_bulk(category_ids or [])

    def create_categories_bulk(
        self, items: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Batch creation of categories (single transaction).

        IMPORTANT: insert_categories_bulk in CategoryModel/Repository already manages
        transaction independently. Wrapping here in UnitOfWork will lead to
        nested transactions in SQLite and error of type
        "cannot start a transaction within a transaction".
        """
        return self._model.create_categories_bulk(items)

    def move_categories_to_section_bulk(
        self, category_ids: list[int], target_section_id: int, base_row: int = 0
    ) -> list[int]:
        """Atomically moves categories to target section in one transaction.

        IMPORTANT: model method manages transaction itself; don't wrap in UnitOfWork.
        Returns list of actually moved IDs (duplicates by name are skipped).
        """
        # Delegate to CategoryModel via Database
        return self.db.categories.move_categories_to_section_bulk(
            category_ids or [],
            int(target_section_id),
            int(base_row) if isinstance(base_row, int) else 0,
        )

    # --- Import/export ---
    def export_full_structure(self) -> dict[str, list]:
        return self.db.export_full_structure()
    
    def export_full_structure_async(self, on_finished=None, on_error=None, on_progress=None):
        """Asynchronous structure export with callbacks."""
        return self.db.export_full_structure_async(on_finished, on_error, on_progress)

    @unit_of_work
    def import_full_structure(self, data: list[dict[str, Any]]) -> None:
        self.db.import_full_structure(data)
    
    def import_full_structure_async(self, data: list[dict[str, Any]], on_finished=None, on_error=None, on_progress=None):
        """Asynchronous structure import with callbacks."""
        return self.db.import_full_structure_async(data, on_finished, on_error, on_progress)

    def export_section_tree(self, section_id: int) -> dict[str, Any]:
        return self.db.export_section_tree(section_id)

    @unit_of_work
    def import_section_tree(self, tree: dict[str, Any]) -> None:
        self.db.import_section_tree(tree)

    def export_category_tree(self, category_id: int) -> dict[str, Any]:
        return self.db.export_category_tree(category_id)

    @unit_of_work
    def import_category_tree(self, tree: dict[str, Any]) -> None:
        self.db.import_category_tree(tree)

    # --- Bulk operations ---
    def import_category_trees_bulk(self, trees: list[dict[str, Any]]) -> None:
        """Imports multiple category subtrees in one operation (one transaction).

        Delegates to Database.import_category_trees_bulk to avoid nested transactions.
        Used, for example, for quick undo of batch category deletion.
        """
        self.db.import_category_trees_bulk(trees or [])
