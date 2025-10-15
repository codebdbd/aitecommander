# app/controllers/structure_modules/category_operations.py

"""Module providing category operations."""

import logging
from importlib import import_module
from types import ModuleType
from typing import Any, Callable, Optional, Protocol, cast

from app.models import StructureModel
from app.services.structure_service import StructureService

from ..models.category_types import CategoryDeletionInfo, SignalTypes
from ..models.types import (
    CategoryCreateData,
    CategoryData,
    CategoryUpdateData,
    StructureItemType,
)
from .base import BaseOperations, StructureSignalEmitter

class _NormalizationValidator(Protocol):
    def __call__(
        self,
        items: list[dict[str, Any]],
        *,
        required_keys: list[str] | None = None,
    ) -> bool: ...


_normalization_module: ModuleType | None = None
try:  # pragma: no cover - optional import for runtime
    _normalization_module = import_module(
        "app.controllers.structure_modules.operations.normalization"
    )
except ModuleNotFoundError:
    _normalization_module = None

_normalize_fn: _NormalizationValidator | None = None
if _normalization_module is not None:
    _candidate = getattr(_normalization_module, "validate_normalized_data", None)
    if callable(_candidate):
        _normalize_fn = cast(_NormalizationValidator, _candidate)


def validate_normalized_data(
    items: list[dict[str, Any]], *, required_keys: list[str] | None = None
) -> bool:
    if _normalize_fn is not None:
        return _normalize_fn(items, required_keys=required_keys)

    required_keys = required_keys or []
    for item in items:
        if not isinstance(item, dict):
            return False
        if any(key not in item for key in required_keys):
            return False
    return True


class CategoryOperations(BaseOperations):
    """Operations handler for categories."""

    def __init__(
        self,
        structure_model: StructureModel,
        logger: logging.Logger,
        execute_with_error_handling: Callable,
        execute_with_validation: Callable,
        emit_signal_callback: Callable,
        cache_manager,
    ):
        super().__init__(
            structure_model, logger, execute_with_error_handling, emit_signal_callback
        )
        self._execute_with_validation_fn: Callable[
            [Callable[[], Optional[int]], Any, StructureItemType, str], Optional[int]
        ] = execute_with_validation
        self._cache_manager = cache_manager
        # Service layer: transactions and reads without duplicating SQL
        try:
            self._structure_service: Optional[StructureService] = StructureService(
                structure_model.db
            )
        except Exception:
            self._structure_service = None

    def create_category(self, data: CategoryCreateData) -> bool:
        """Create a new category."""
        # Delegate to the universal base-class helper
        result = self.create_item(StructureItemType.CATEGORY, data)
        if result:
            self._cache_manager.invalidate_first_category_cache()
        return result

    def update_category(self, category_id: int, data: CategoryUpdateData) -> bool:
        """Update an existing category."""
        # Delegate to the universal base-class helper
        result = self.update_item(StructureItemType.CATEGORY, category_id, data)
        if result:
            self._cache_manager.invalidate_first_category_cache()
        return result

    def delete_category(self, category_id: int) -> CategoryDeletionInfo:
        """Delete a category and return deletion info."""

        def _delete_category_operation():
            # Retrieve category data
            category_data = self._get_category_data_internal(category_id)
            if not category_data:
                error_msg = f"Category with ID {category_id} was not found"
                self.logger.error(error_msg)
                return CategoryDeletionInfo.create_empty()

            # ✅ Convert to strongly typed data
            typed_category_data: CategoryData = category_data  # type: ignore

            # Count linked links
            links_count = self._count_category_links(category_id)

            self.logger.info(
                "Preparing to delete category %s: %s linked items",
                category_id,
                links_count,
            )

            return CategoryDeletionInfo(True, typed_category_data, links_count)

        return self._execute_with_error_handling(
            _delete_category_operation,
            f"fetch category data {category_id}",
            default_return=CategoryDeletionInfo.create_empty(),
        )

    def confirm_delete_category(self, category_id: int) -> bool:
        """Confirm and perform category deletion."""
        structure_service = self._structure_service
        if structure_service is None:

            def _raise_service_error():
                raise RuntimeError(
                    "StructureService is unavailable for category deletion"
                )

            return self._execute_with_error_handling(
                _raise_service_error,
                f"delete category {category_id}",
                default_return=False,
            )

        def _delete():
            structure_service.delete_category(category_id)

        result = self.delete_item(
            StructureItemType.CATEGORY,
            category_id,
            delete_func=_delete,
            emit_data=None,
        )
        if result:
            self._cache_manager.invalidate_first_category_cache()
        return result

    def get_category_data(self, category_id: int) -> Optional[dict[str, Any]]:
        """Fetch category data with guaranteed normalization."""

        def _get_category_operation():
            category_data = self._get_category_data_internal(category_id)
            if category_data:
                self.logger.debug("Category %s found", category_id)
            else:
                self.logger.warning("Category %s not found", category_id)
            return category_data

        return self._exec_with_norm(
            _get_category_operation,
            f"load category data {category_id}",
            default_return=None,
        )

    def get_categories(self, section_id: int) -> list[dict[str, Any]]:
        """Retrieve categories for the specified section."""

        def _get_categories_operation():
            categories_data = (
                self._structure_service.get_categories(section_id)
                if self._structure_service
                else self.structure_model.get_categories(section_id)
            )
            result = categories_data if categories_data else []
            self.logger.debug(
                "Loaded %s categories for section %s",
                len(result),
                section_id,
            )
            return result

        return self._exec_with_norm(
            _get_categories_operation,
            f"load categories for section {section_id}",
            default_return=[],
        )

    def get_categories_batch(self, section_ids: list[int]) -> list[dict[str, Any]]:
        """Fetch categories for multiple sections with guaranteed normalization."""
        if not section_ids:
            return []

        def _get_categories_batch_operation():
            # Use the optimized model method
            rows = self.structure_model.get_categories_batch(section_ids)
            return rows if rows else []

        # Apply normalization and validation
        normalized = self._exec_with_norm(
            _get_categories_batch_operation,
            f"load categories for sections {section_ids}",
            default_return=[],
        )

        # Additional validation for batch operations
        return self._validate_batch_categories(normalized)

    def _process_item(
        self,
        item_type: StructureItemType,
        data: Any,
        emit_signal: "StructureSignalEmitter",
        is_update: bool = False,
        item_id: Optional[int] = None,
    ) -> Optional[int]:
        """Handle category mutations via `StructureService`, preserving base signature."""

        if item_type is not StructureItemType.CATEGORY or not getattr(
            self, "_structure_service", None
        ):
            return super()._process_item(
                item_type,
                data,
                emit_signal,
                is_update=is_update,
                item_id=item_id,
            )

        def _operation() -> Optional[int]:
            assert self._structure_service is not None
            if is_update:
                assert item_id is not None
                self._structure_service.update_category(int(item_id), data)
                current = self._structure_service.get_category_by_id(int(item_id)) or {}
                emit_signal.emit(
                    SignalTypes.ITEM_UPDATED,
                    item_type.value,
                    int(item_id),
                    current,
                )
                try:
                    self._cache_manager.invalidate_first_category_cache()
                except Exception:
                    pass
                return int(item_id)

            new_id = self._structure_service.create_category(data)
            if not new_id:
                return None
            current = self._structure_service.get_category_by_id(int(new_id)) or {
                **data,
                "id": int(new_id),
            }
            parent_id = (
                (current.get("section_id") if isinstance(current, dict) else None)
                or data.get("section_id")
                or 0
            )
            emit_signal.emit(
                SignalTypes.ITEM_ADDED,
                item_type.value,
                int(parent_id),
                current,
            )
            try:
                self._cache_manager.invalidate_first_category_cache()
            except Exception:
                pass
            return int(new_id)

        return self._execute_with_validation_fn(
            _operation,
            data,
            item_type,
            "update" if is_update else "create",
        )

    def get_first_category_id(self) -> Optional[int]:
        """Return the first category ID with caching for optimization."""
        # Check cache
        cached_id = self._cache_manager.get_first_category_id()
        if cached_id is not None:
            self.logger.debug("Using cached first category: %s", cached_id)
            return cached_id

        def _get_first_category_operation():
            # The service layer lacks this method, rely on the model
            category_id = self.structure_model.get_first_category_id()
            if category_id:
                self.logger.debug("First category found with ID: %s", category_id)
                self._cache_manager.set_first_category_id(category_id)
                return category_id
            else:
                self.logger.debug("No categories found")
                return None

        return self._execute_with_error_handling(
            _get_first_category_operation,
            "get first category",
            default_return=None,
        )

    def get_first_category_id_for_sphere(self, sphere_id: int) -> Optional[int]:
        """Return the first category ID within a sphere using per-sphere cache.

        - Maintains backward compatibility as an additional helper.
        - First consults the per-sphere cache in `CacheManager`.
        - On cache miss it calculates via StructureModel/Service and stores the result.
        """
        # 1) Per-sphere cache lookup
        try:
            cached = self._cache_manager.get_first_category_id_for_sphere(sphere_id)
        except Exception:
            cached = None
        if cached is not None:
            self.logger.debug(
                "Using per-sphere cache for sphere %s: %s",
                sphere_id,
                cached,
            )
            return cached

        # 2) Compute: find the first category in the first section that has categories
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
                        first_id = (
                            cats[0].get("id") if isinstance(cats[0], dict) else None
                        )
                        return int(first_id) if first_id is not None else None
                return None
            except Exception as e:
                self.logger.error(
                    "Failed to compute first category for sphere %s: %s", sphere_id, e
                )
                return None

        result = _compute_first_for_sphere()
        try:
            self._cache_manager.set_first_category_id_for_sphere(sphere_id, result)
        except Exception:
            pass
        return result

    def get_category_hierarchy(self, category_id: int) -> Optional[dict[str, Any]]:
        """Fetch hierarchy (sphere_id, section_id) for a category with normalization."""

        def _get_hierarchy_operation():
            hierarchy_data = (
                self._structure_service.get_category_hierarchy(category_id)
                if self._structure_service
                else self.structure_model.get_category_hierarchy(category_id)
            )
            if hierarchy_data:
                self.logger.debug("Hierarchy found for category %s", category_id)
            else:
                self.logger.warning("Hierarchy for category %s not found", category_id)
            return hierarchy_data

        return self._exec_with_norm(
            _get_hierarchy_operation,
            f"fetch category hierarchy {category_id}",
            default_return=None,
        )

    def has_duplicate_category(
        self, section_id: int, category_name: str, exclude_id: Optional[int] = None
    ) -> bool:
        """Check whether a duplicate category exists in the section."""

        def _check_duplicate_operation():
            return self.structure_model.has_duplicate_category(
                section_id, category_name, exclude_id
            )

        result = self._execute_with_error_handling(
            _check_duplicate_operation,
            f"check duplicate category '{category_name}' in section {section_id}",
            default_return=False,
        )
        return bool(result) if result is not None else False

    def create_category_for_import(
        self, category_data: dict[str, Any]
    ) -> Optional[int]:
        """Create a new category for import."""
        if self._structure_service:
            return self._structure_service.create_category(category_data)
        else:
            raise RuntimeError("StructureService is unavailable for category creation")

    # Private helper methods

    def _get_category_data_internal(self, category_id: int) -> Optional[dict[str, Any]]:
        """Internal helper to load category data."""
        if self._structure_service:
            return self._structure_service.get_category_by_id(category_id)
        return self.structure_model.get_category_by_id(category_id)

    def _count_category_links(self, category_id: int) -> int:
        """Count the number of links in a category."""
        try:
            return self.structure_model.count_links_by_category(category_id)
        except Exception as e:
            self.logger.error(
                "Failed to count links for category %s: %s",
                category_id,
                e,
            )
            return 0

    def _emit_item_signal(
        self,
        signal_type: str,
        item_type: StructureItemType,
        item_id: int,
        data: Optional[dict[str, Any]] = None,
    ):
        """Emit structure signals centrally for items."""
        try:
            if data:
                self._emit_signal(signal_type, item_type.value, item_id, data)
            else:
                self._emit_signal(signal_type, item_type.value, item_id)
        except Exception as e:
            self.logger.error(
                "Failed to emit signal %s for %s %s: %s",
                signal_type,
                item_type.value,
                item_id,
                e,
            )

    def _validate_batch_categories(
        self, categories: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Validate category data after batch loading."""
        if not categories:
            return []

        # Require `section_id` key for grouping in coordination.py
        if not validate_normalized_data(categories, required_keys=["section_id"]):
            self.logger.warning(
                "Some category records do not contain the required 'section_id' key. "
                "Invalid entries will be filtered out."
            )
            # Keep only valid entries
            categories = [
                item
                for item in categories
                if isinstance(item, dict) and "section_id" in item
            ]

        return categories

    def _create_item_for_import(
        self, item_type: str, item_data: dict[str, Any], create_func: Callable
    ) -> Optional[int]:
        """Generic helper for creating items during import."""

        def _create_import_operation():
            result_id = create_func(item_data)
            if not result_id:
                self.logger.warning("Failed to create %s for import", item_type)
                return None

            # Prepare payload for the signal
            signal_data = item_data.copy()
            signal_data["id"] = result_id

            # Determine parent_id depending on the item type
            parent_id = self._get_parent_id_for_item_type(item_type, signal_data)

            if parent_id is None:
                self.logger.warning(
                    "Cannot emit %s signal for %s: missing parent id",
                    SignalTypes.ITEM_ADDED,
                    item_type,
                )
                return result_id

            # Map string item type to enum and emit the signal centrally
            enum_type = self._to_item_enum(item_type)
            self._emit_item_signal(
                SignalTypes.ITEM_ADDED,
                enum_type,
                parent_id,
                signal_data,
            )

            self.logger.info(
                "Created %s for import: %s",
                item_type,
                signal_data.get("name", "unnamed"),
            )
            return result_id

        return self._execute_with_error_handling(
            _create_import_operation,
            f"create {item_type} for import",
            default_return=None,
        )

    def _to_item_enum(self, item_type: str) -> StructureItemType:
        """Convert string item type into `StructureItemType`."""
        mapping = {
            "section": StructureItemType.SECTION,
            "category": StructureItemType.CATEGORY,
            "link": StructureItemType.LINK,
        }
        try:
            return mapping[item_type]
        except KeyError as e:
            raise ValueError(f"Unsupported item type: {item_type}") from e

    def _get_parent_id_for_item_type(
        self, item_type: str, item_data: dict[str, Any]
    ) -> Optional[int]:
        """Determine parent_id for an item depending on its type."""
        # Use section_id as parent_id for categories
        if item_type == "category":
            return item_data.get("section_id")
        # Other types can be handled later
        elif item_type == "section":
            return item_data.get("sphere_id")
        elif item_type == "link":
            return item_data.get("category_id")
        else:
            raise ValueError(f"Unsupported item type: {item_type}")
