"""Command for moving a section to another sphere with undo/redo support."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, cast

from app.utils.ui.dnd.base_bulk_command import BaseBulkCommand
from app.utils.ui.dnd.error_handler import BulkOperationErrorHandler

if TYPE_CHECKING:
    from app.controllers.business.structure_business import StructureBusinessLogic
    from app.views.windows.main_window_protocol import MainWindowProtocol

logger = logging.getLogger(__name__)
error_handler = BulkOperationErrorHandler()


def _require_main(main: object | None) -> MainWindowProtocol:
    if main is None:
        raise RuntimeError("Command requires an attached main window")
    return cast("MainWindowProtocol", main)


def _require_structure_business(main: object | None) -> StructureBusinessLogic:
    main_window = _require_main(main)
    structure_business = getattr(main_window, "structure_business", None)
    if structure_business is None:
        raise RuntimeError("Main window is missing structure_business")
    return cast("StructureBusinessLogic", structure_business)


class MoveSectionToSphereCommand(BaseBulkCommand):
    """Command to move a section into another sphere with Undo/Redo."""

    def __init__(
        self, section_id: int, target_sphere_id: int, main_window: object
    ) -> None:
        super().__init__("Move section to sphere", main_window, "section")
        self.section_id = int(section_id)
        self.target_sphere_id = int(target_sphere_id)
        self.old_sphere_id: int | None = None
        self.original_name: str = ""
        self.new_name: str = ""
        self.icon_path: str = ""
        self.old_position: int = 0
        self.new_position: int = 0
        self._prepared = False

    def _prepare_data(self) -> None:
        if self._prepared:
            return

        sb = _require_structure_business(self.main)
        section_data = sb.get_section_data(self.section_id)
        if section_data is None:
            raise ValueError(f"Section {self.section_id} not found")

        self.old_sphere_id = int(section_data["sphere_id"])
        self.original_name = str(section_data.get("name", ""))
        self.icon_path = str(section_data.get("icon_path", "") or "")
        self.old_position = int(section_data.get("position", 0) or 0)

        # Handle name duplicates in target sphere
        name = self.original_name
        if sb.has_duplicate_section(self.target_sphere_id, name, exclude_id=self.section_id):
            counter = 1
            while sb.has_duplicate_section(
                self.target_sphere_id, f"{self.original_name} ({counter})", exclude_id=self.section_id
            ):
                counter += 1
            name = f"{self.original_name} ({counter})"
        self.new_name = name

        # Compute next position in target sphere
        existing = sb.get_sections(self.target_sphere_id) or []
        if existing:
            self.new_position = max((int(s.get("position", 0) or 0) for s in existing), default=0) + 1
        else:
            self.new_position = 0

        self._prepared = True

    def _execute_operation(self) -> bool:
        try:
            self._prepare_data()

            if self.old_sphere_id == self.target_sphere_id:
                return True

            sb = _require_structure_business(self.main)

            # Update section
            update_data: dict[str, Any] = {
                "name": self.new_name,
                "sphere_id": self.target_sphere_id,
                "position": self.new_position,
                "icon_path": self.icon_path,
            }
            updated = sb.update_section(self.section_id, update_data)
            if updated is None:
                raise ValueError(f"Failed to update section {self.section_id}")

            # Reindex positions in old sphere
            self._reindex_sphere_sections(sb, self.old_sphere_id)

            # Invalidate structure caches
            self._invalidate_caches(sb, [self.old_sphere_id, self.target_sphere_id])

            return True
        except Exception as e:
            context = {
                "operation": "move_section_to_sphere",
                "section_id": self.section_id,
                "target_sphere_id": self.target_sphere_id,
            }
            error_handler.handle_error(e, context)
            return False

    def _restore_original_state(self) -> bool:
        try:
            if self.old_sphere_id is None or self.old_sphere_id == self.target_sphere_id:
                return True

            sb = _require_structure_business(self.main)

            # Restore original section
            update_data: dict[str, Any] = {
                "name": self.original_name,
                "sphere_id": self.old_sphere_id,
                "position": self.old_position,
                "icon_path": self.icon_path,
            }
            updated = sb.update_section(self.section_id, update_data)
            if updated is None:
                raise ValueError(f"Failed to restore section {self.section_id}")

            # Reindex positions in target sphere (which lost the section)
            self._reindex_sphere_sections(sb, self.target_sphere_id)

            # Invalidate structure caches
            self._invalidate_caches(sb, [self.old_sphere_id, self.target_sphere_id])

            return True
        except Exception as e:
            context = {
                "operation": "undo_move_section_to_sphere",
                "section_id": self.section_id,
                "original_sphere_id": self.old_sphere_id,
            }
            error_handler.handle_error(e, context)
            return False

    def _reindex_sphere_sections(
        self, sb: StructureBusinessLogic, sphere_id: int | None
    ) -> None:
        if sphere_id is None:
            return
        try:
            db = getattr(getattr(sb, "structure_service", None), "db", None)
            if db and hasattr(db, "sections") and hasattr(db.sections, "_reindex_positions"):
                db.sections._reindex_positions("section", "sphere_id", sphere_id)
        except Exception as exc:
            logger.warning(
                "Failed to reindex sections in sphere %s: %s", sphere_id, exc
            )

    def _invalidate_caches(
        self, sb: StructureBusinessLogic, sphere_ids: list[int | None]
    ) -> None:
        cache_service = getattr(sb, "cache_service", None)
        if cache_service and hasattr(cache_service, "invalidate_structure_cache"):
            for sid in sphere_ids:
                if isinstance(sid, int):
                    try:
                        cache_service.invalidate_structure_cache(sid)
                    except Exception:
                        pass

    def _refresh_ui(self, affected_items: list | None = None) -> None:
        target_sphere = (
            self.target_sphere_id
            if self._last_operation == "redo"
            else self.old_sphere_id
        )
        if target_sphere is None:
            return

        main_window = _require_main(self.main)
        structure_ctrl = getattr(main_window, "structure", None)
        if structure_ctrl and hasattr(structure_ctrl, "switch_sphere"):
            try:
                structure_ctrl.switch_sphere(
                    target_sphere, item_to_select=("section", self.section_id)
                )
                logger.info(
                    "Switched sphere to %s and requested focus on moved section %s",
                    target_sphere,
                    self.section_id,
                )
            except Exception as e:
                logger.warning(
                    "Failed to switch sphere and focus moved section: %s", e
                )
