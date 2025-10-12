"""Query and selection helpers for structure business logic."""

from __future__ import annotations

from logging import Logger
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - typing only
    from app.controllers.business.structure_business import StructureBusinessLogic

    from .cache_service import StructureCacheService
    from .validation_service import StructureValidationService


class StructureQueryService:
    """Provides read/query helpers and selection workflows for the structure UI."""

    def __init__(
        self,
        owner: StructureBusinessLogic,
        cache_service: StructureCacheService,
        validation_facade: StructureValidationService,
        logger: Logger,
    ) -> None:
        self._owner = owner
        self._cache_service = cache_service
        self._validation_facade = validation_facade
        self._logger = logger

    # ------------------------------------------------------------------
    # Selection helpers
    # ------------------------------------------------------------------
    def select_section(self, section_id: int) -> None:
        categories = self._cache_service.get_categories(section_id)
        self._owner.section_selected.emit(section_id)
        try:
            count = len(categories) if isinstance(categories, list) else 0
        except Exception:
            count = 0
        self._logger.debug("Section %s selected with %s categories", section_id, count)

    def select_category(self, category_id: int) -> None:
        self._owner.category_selected.emit(category_id)
        self._logger.debug("Category %s selected", category_id)

    def on_active_sphere_changed(self) -> None:
        loader_async = getattr(self._owner, "load_structure_async", None)
        if callable(loader_async):
            loader_async()
            return
        loader_sync = getattr(self._owner, "load_structure", None)
        if callable(loader_sync):
            loader_sync()
            return
        self._logger.error(
            "StructureBusinessLogic has no load_structure_async() or load_structure(); skipping reload"
        )

    # ------------------------------------------------------------------
    # Cached data accessors
    # ------------------------------------------------------------------
    def get_spheres(self) -> list[dict[str, Any]]:
        return self._cache_service.get_spheres()

    def get_sections(self, sphere_id: int) -> list[dict[str, Any]]:
        return self._cache_service.get_sections(sphere_id)

    def get_categories(self, section_id: int) -> list[dict[str, Any]]:
        return self._cache_service.get_categories(section_id)

    def get_target_section_id(self) -> int | None:
        return self._cache_service.get_target_section_id()

    # ------------------------------------------------------------------
    # Validation facade accessors
    # ------------------------------------------------------------------
    def get_links(self, category_id: int) -> list[dict[str, Any]]:
        return self._validation_facade.get_links(category_id)

    def get_section_data(self, section_id: int) -> dict[str, Any] | None:
        return self._validation_facade.get_section_data(section_id)

    def get_category_data(self, category_id: int) -> dict[str, Any] | None:
        return self._validation_facade.get_category_data(category_id)

    def get_item_for_editing(
        self, item_id: int, item_type: str | Any
    ) -> dict[str, Any] | None:
        return self._validation_facade.get_item_for_editing(item_id, item_type)

    def get_sphere_by_id(self, sphere_id: int) -> dict[str, Any] | None:
        return self._validation_facade.get_sphere_by_id(sphere_id)

    def get_next_sphere_id(self) -> int | None:
        return self._validation_facade.get_next_sphere_id()

    def has_duplicate_category(
        self, section_id: int, category_name: str, exclude_id: int | None = None
    ) -> bool:
        return self._validation_facade.has_duplicate_category(
            section_id, category_name, exclude_id
        )

    def get_section_for_editing(self, section_id: int) -> dict[str, Any] | None:
        return self._validation_facade.get_section_for_editing(section_id)

    def get_category_for_editing(self, category_id: int) -> dict[str, Any] | None:
        return self._validation_facade.get_category_for_editing(category_id)
