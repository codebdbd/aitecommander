"""Validation and utility helpers for structure business logic."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.controllers.structure_modules import ValidationResult

if TYPE_CHECKING:  # pragma: no cover - typing only
    from logging import Logger

    from app.controllers.business.structure.cache_service import StructureCacheService
    from app.controllers.business.structure_business import StructureBusinessLogic
    from app.controllers.structure_services.utilities import UtilityService
    from app.controllers.structure_services.validation import ValidationService
    from app.models import StructureModel
    from app.services.structure_service import StructureService


class StructureValidationService:
    """Encapsulates validation logic and legacy utility helpers."""

    def __init__(
        self,
        owner: StructureBusinessLogic,
        validation_service: ValidationService,
        utility_service: UtilityService,
        cache_service: StructureCacheService,
        structure_service: StructureService,
        structure_model: StructureModel,
        logger: Logger,
    ) -> None:
        self._owner = owner
        self._validation_service = validation_service
        self._utility_service = utility_service
        self._cache_service = cache_service
        self._structure_service = structure_service
        self._structure_model = structure_model
        self._logger = logger

    def get_links(self, category_id: int) -> list[dict[str, Any]]:
        """Return links for a category via ``UtilityService``."""
        return self._utility_service.get_links(
            self._structure_model,
            category_id,
            self._logger,
        )

    def get_section_data(self, section_id: int) -> dict[str, Any] | None:
        """Return raw section payload."""
        return self._structure_service.get_section_by_id(section_id)

    def get_category_data(self, category_id: int) -> dict[str, Any] | None:
        """Return raw category payload."""
        return self._structure_service.get_category_by_id(category_id)

    def get_item_for_editing(
        self, item_id: int, item_type: Any
    ) -> dict[str, Any] | None:
        """Return payload for editing dialogs."""
        return self._utility_service.get_item_for_editing(
            item_id=item_id,
            item_type=item_type,
            get_section_data=self._structure_model.get_section_data,
            get_category_data=self._structure_model.get_category_data,
            logger=self._logger,
        )

    def get_section_for_editing(self, section_id: int) -> dict[str, Any] | None:
        """Return section payload for editing dialogs."""
        return self._structure_model.get_section_data(section_id)

    def get_category_for_editing(self, category_id: int) -> dict[str, Any] | None:
        """Return category payload for editing dialogs."""
        return self._structure_model.get_category_data(category_id)

    def validate_section_data(
        self, data: dict[str, Any], section_id: int | None = None
    ) -> ValidationResult:
        """Validate section payload using ``ValidationService``."""
        return self._validation_service.validate_section_data(
            data=data,
            section_id=section_id,
            get_sections=self._owner.get_sections,
        )

    def validate_category_data(
        self, data: dict[str, Any], category_id: int | None = None
    ) -> ValidationResult:
        """Validate category payload using ``ValidationService``."""
        return self._validation_service.validate_category_data(
            data=data,
            category_id=category_id,
            has_duplicate_category=self.has_duplicate_category,
        )

    def has_duplicate_category(
        self, section_id: int, category_name: str, exclude_id: int | None = None
    ) -> bool:
        """Check whether a duplicate category exists within the section."""
        if not category_name:
            return False
        categories = self._owner.get_categories(section_id)
        candidate = category_name.lower().strip()
        for category in categories:
            name = category.get("name")
            if not isinstance(name, str):
                continue
            if name.lower().strip() == candidate and category.get("id") != exclude_id:
                return True
        return False

    def get_sphere_by_id(self, sphere_id: int) -> dict[str, Any] | None:
        """Return sphere data by identifier."""
        spheres = self._owner.get_spheres()
        return next(
            (sphere for sphere in spheres if sphere.get("id") == sphere_id), None
        )

    def get_next_sphere_id(self) -> int | None:
        """Return the next sphere identifier cycling through the cache."""
        spheres = self._owner.get_spheres()
        if not spheres:
            return None
        if self._owner.current_sphere_id is None:
            return spheres[0].get("id")
        current_index = next(
            (
                idx
                for idx, sphere in enumerate(spheres)
                if sphere.get("id") == self._owner.current_sphere_id
            ),
            -1,
        )
        if current_index == -1:
            return spheres[0].get("id")
        next_index = (current_index + 1) % len(spheres)
        return spheres[next_index].get("id")
