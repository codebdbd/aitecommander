from __future__ import annotations

from typing import Any, Dict

from app.controllers.domain.structure.infrastructure.exceptions import handle_exceptions


class ExportIntegrityMixin:
    """Миксин для операций экспорта и проверки целостности структуры."""

    @handle_exceptions()
    def validate_structure_integrity(self) -> Dict[str, Any]:
        """Проверяет целостность структуры данных (делегировано в IntegrityService)."""
        return self.integrity_service.validate_structure_integrity(
            get_spheres=self.get_spheres,
            get_sections=self.get_sections,
            get_categories=self.get_categories,
            get_statistics=lambda: self.integrity_service.get_statistics(
                get_spheres=self.get_spheres,
                get_sections=self.get_sections,
                get_categories=self.get_categories,
                current_sphere_id=self.current_sphere_id,
                logger=self.logger,
            ),
            logger=self.logger,
        )

    @handle_exceptions()
    def export_structure_data(self) -> Dict[str, Any]:
        """Экспортирует данные структуры для резервного копирования (делегировано в ExportService)."""
        return self.export_service.export_structure_data(
            current_sphere_id=self.current_sphere_id,
            get_spheres=self.get_spheres,
            get_sections=self.get_sections,
            get_categories=self.get_categories,
            logger=self.logger,
        )
