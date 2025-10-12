from __future__ import annotations

import logging
from typing import Any

from app.models import StructureModel
from app.services.structure_service import StructureService


class ImportService:
    """Structure import operations service."""

    def create_category_for_import(
        self,
        model: StructureModel,
        category_data: dict[str, Any],
        logger: logging.Logger | None = None,
    ) -> int | None:
        """Create category in import mode and return its ID."""
        try:
            # Try to use service layer with UnitOfWork transaction
            service = None
            try:
                service = StructureService(model.db)
            except (ImportError, AttributeError, RuntimeError) as service_error:
                if logger:
                    logger.warning(
                        "Failed to create StructureService, using direct model: %s",
                        service_error,
                    )

            if service:
                category_id = service.create_category(category_data)
            else:
                # Fallback to direct model (undesirable but maintains compatibility)
                category_id = model.create_category(category_data)

            if logger and category_id:
                logger.info(
                    "Created import category %s: %s",
                    category_id,
                    category_data.get("name", "Untitled"),
                )
            return category_id
        except (ValueError, KeyError, TypeError) as e:
            if logger:
                logger.error("Category data validation error for import: %s", e)
            return None
        except Exception:
            if logger:
                logger.exception("Critical error creating category for import")
            raise  # Re-raise critical errors
