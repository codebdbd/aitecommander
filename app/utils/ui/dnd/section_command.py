"""Command for moving a section to another sphere with undo/redo support."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, cast

from app.controllers.ui.undo.base import BaseCommand
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
        self,
        section_id: int,
        target_sphere_id: int,
        main_window: object,
        new_name: str | None = None,
    ) -> None:
        super().__init__("Move section to sphere", main_window, "section")
        self.section_id = int(section_id)
        self.target_sphere_id = int(target_sphere_id)
        self.old_sphere_id: int | None = None
        self._custom_new_name: str | None = new_name
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
        if self._custom_new_name:
            name = self._custom_new_name
        else:
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
        if structure_ctrl:
            sb = getattr(main_window, "structure_business", None)
            current_sphere = getattr(sb, "current_sphere_id", None) if sb else None
            item_to_select = ("section", self.section_id)
            if isinstance(current_sphere, int) and current_sphere == target_sphere:
                if hasattr(structure_ctrl, "load"):
                    try:
                        structure_ctrl.load(item_to_select=item_to_select)
                        logger.info(
                            "Reloaded current sphere %s and requested focus on moved section %s",
                            target_sphere,
                            self.section_id,
                        )
                    except Exception as e:
                        logger.warning(
                            "Failed to reload structure and focus moved section: %s", e
                        )
            elif hasattr(structure_ctrl, "switch_sphere"):
                try:
                    structure_ctrl.switch_sphere(
                        target_sphere, item_to_select=item_to_select
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


class MoveSectionsToSphereCommand(BaseCommand):
    """Move multiple sections as one undoable operation and refresh the UI once."""

    def __init__(
        self,
        section_ids: list[int],
        target_sphere_id: int,
        main_window: object,
        *,
        name_overrides: dict[int, str] | None = None,
    ) -> None:
        super().__init__("Move sections to sphere", main_window)
        self.target_sphere_id = int(target_sphere_id)
        overrides = name_overrides or {}
        self.commands = [
            MoveSectionToSphereCommand(
                section_id,
                target_sphere_id,
                main_window,
                new_name=overrides.get(section_id),
            )
            for section_id in section_ids
        ]
        self._target_positions_prepared = False

    def _run_batched(self, operation: str) -> bool:
        sb = _require_structure_business(self.main)
        begin_batch = getattr(sb, "begin_batch", None)
        end_batch = getattr(sb, "end_batch", None)
        if callable(begin_batch):
            begin_batch()
        completed: list[MoveSectionToSphereCommand] = []
        try:
            sequence = (
                self.commands
                if operation == "redo"
                else list(reversed(self.commands))
            )
            next_target_position: int | None = None
            if operation == "redo" and not self._target_positions_prepared:
                existing = sb.get_sections(self.target_sphere_id) or []
                next_target_position = (
                    max(
                        (int(item.get("position", 0) or 0) for item in existing),
                        default=-1,
                    )
                    + 1
                )
            for command in sequence:
                command.prepare_if_needed()
                if next_target_position is not None:
                    command.new_position = next_target_position
                    next_target_position += 1
                ok = (
                    command._execute_operation()
                    if operation == "redo"
                    else command._restore_original_state()
                )
                if not ok:
                    if operation == "redo":
                        for applied in reversed(completed):
                            applied._restore_original_state()
                    return False
                completed.append(command)
            if operation == "redo":
                self._target_positions_prepared = True
            return True
        finally:
            if callable(end_batch):
                end_batch()

    def _refresh_once(self, operation: str) -> None:
        if not self.commands:
            return
        command = self.commands[-1] if operation == "redo" else self.commands[0]
        command._last_operation = operation
        command._refresh_ui()

    def redo(self) -> None:
        if self._run_batched("redo"):
            self._refresh_once("redo")
        else:
            self.set_obsolete(True)

    def undo(self) -> None:
        if self._run_batched("undo"):
            self._refresh_once("undo")


class MergeSectionToSphereCommand(BaseCommand):
    """Merge a source section into an existing target section in another sphere with Undo/Redo."""

    def __init__(
        self, source_section_id: int, target_section_id: int, main_window: object
    ) -> None:
        super().__init__("Merge section into target", main_window)
        self.source_id = int(source_section_id)
        self.target_id = int(target_section_id)
        self._source_section_data: dict[str, Any] = {}
        self._moved_category_ids: list[int] = []
        self._renamed_categories: dict[int, tuple[str, str]] = {}
        self._target_sphere_id: int | None = None
        self._source_sphere_id: int | None = None
        self._prepared = False

    def _prepare_data(self) -> None:
        if self._prepared:
            return
        sb = _require_structure_business(self.main)
        s_data = sb.get_section_data(self.source_id)
        if not s_data:
            raise ValueError(f"Source section {self.source_id} not found")
        t_data = sb.get_section_data(self.target_id)
        if not t_data:
            raise ValueError(f"Target section {self.target_id} not found")

        self._source_section_data = dict(s_data)
        self._source_sphere_id = int(s_data["sphere_id"])
        self._target_sphere_id = int(t_data["sphere_id"])

        cats = sb.get_categories(self.source_id) or []
        self._moved_category_ids = [int(c["id"]) for c in cats if c.get("id")]

        target_cats = sb.get_categories(self.target_id) or []
        target_cat_names = {str(c.get("name", "")).strip().lower() for c in target_cats}
        existing_names_set = {str(c.get("name", "")).strip() for c in target_cats}

        from app.utils.naming import generate_unique_name
        self._renamed_categories = {}
        for c in cats:
            cid = int(c["id"])
            cname = str(c.get("name", "")).strip()
            if cname.lower() in target_cat_names:
                unique_name = generate_unique_name(existing_names_set, cname)
                self._renamed_categories[cid] = (cname, unique_name)
                existing_names_set.add(unique_name)
                target_cat_names.add(unique_name.lower())

        self._prepared = True

    def redo(self) -> None:
        self._prepare_data()
        sb = _require_structure_business(self.main)
        db = getattr(getattr(sb, "structure_service", None), "db", None)

        def _do_redo():
            for cid, (_, new_name) in self._renamed_categories.items():
                sb.update_category(cid, {"name": new_name})
            for cid in self._moved_category_ids:
                res = sb.update_category(cid, {"section_id": self.target_id})
                if not res:
                    raise RuntimeError(f"Failed to transfer category {cid} to section {self.target_id}")
            sb.delete_section(self.source_id)

        if db and hasattr(db, "transaction"):
            with db.transaction():
                _do_redo()
        else:
            _do_redo()

        self._invalidate_caches(sb)
        self._refresh_ui(self._target_sphere_id, self.target_id)

    def undo(self) -> None:
        if not self._source_section_data:
            return
        sb = _require_structure_business(self.main)
        db = getattr(getattr(sb, "structure_service", None), "db", None)

        def _do_undo():
            if db and hasattr(db, "connection"):
                db.connection.execute(
                    """
                    INSERT OR REPLACE INTO section (id, sphere_id, name, position, icon_path)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        self.source_id,
                        self._source_section_data.get("sphere_id"),
                        self._source_section_data.get("name"),
                        self._source_section_data.get("position", 0),
                        self._source_section_data.get("icon_path", ""),
                    ),
                )
            for cid in self._moved_category_ids:
                sb.update_category(cid, {"section_id": self.source_id})
            for cid, (old_name, _) in self._renamed_categories.items():
                sb.update_category(cid, {"name": old_name})

        if db and hasattr(db, "transaction"):
            with db.transaction():
                _do_undo()
        else:
            _do_undo()

        self._invalidate_caches(sb)
        self._refresh_ui(self._source_sphere_id, self.source_id)

    def _invalidate_caches(self, sb: StructureBusinessLogic) -> None:
        cache_service = getattr(sb, "cache_service", None)
        if cache_service and hasattr(cache_service, "invalidate_structure_cache"):
            for sid in (self._source_sphere_id, self._target_sphere_id):
                if sid is not None:
                    try:
                        cache_service.invalidate_structure_cache(sid)
                    except Exception:
                        pass

    def _refresh_ui(self, target_sphere: int | None, select_section_id: int | None) -> None:
        if target_sphere is None:
            return
        main_win = _require_main(self.main)
        structure_ctrl = getattr(main_win, "structure", None)
        if structure_ctrl:
            sb = getattr(main_win, "structure_business", None)
            current_sphere = getattr(sb, "current_sphere_id", None) if sb else None
            item_to_select = ("section", select_section_id) if select_section_id else None
            if isinstance(current_sphere, int) and current_sphere == target_sphere:
                if hasattr(structure_ctrl, "load"):
                    try:
                        structure_ctrl.load(item_to_select=item_to_select)
                    except Exception as e:
                        logger.warning("Failed to reload structure after merge: %s", e)
            elif hasattr(structure_ctrl, "switch_sphere"):
                try:
                    structure_ctrl.switch_sphere(target_sphere, item_to_select=item_to_select)
                except Exception as e:
                    logger.warning("Failed to refresh UI after merge: %s", e)


class ReorderSectionsCommand(BaseBulkCommand):
    """Command for reordering sections within their sphere with Undo/Redo."""

    def __init__(
        self, section_ids: list[int], target_row: int, main_window: object
    ) -> None:
        super().__init__("Reorder sections", main_window, "section")
        self.section_ids = [int(sid) for sid in section_ids]
        self.target_row = int(target_row)
        self.sphere_id: int | None = None
        self._old_positions: dict[int, int] = {}
        self._new_positions: dict[int, int] = {}
        self._sections_meta: dict[int, dict[str, Any]] = {}
        self._prepared = False

    def _prepare_data(self) -> None:
        if self._prepared or not self.section_ids:
            return

        sb = _require_structure_business(self.main)
        first_sec = sb.get_section_data(self.section_ids[0])
        if first_sec is None:
            raise ValueError(f"Section {self.section_ids[0]} not found")

        self.sphere_id = int(first_sec["sphere_id"])
        all_sections = sb.get_sections(self.sphere_id) or []
        all_sections.sort(
            key=lambda s: (int(s.get("position", 0) or 0), int(s.get("id", 0) or 0))
        )

        all_ids = [int(s["id"]) for s in all_sections]
        moving_set = set(self.section_ids)
        moving_ids = [sid for sid in all_ids if sid in moving_set]
        remaining_ids = [sid for sid in all_ids if sid not in moving_set]

        items_before_target = sum(
            1 for idx, sid in enumerate(all_ids) if sid in moving_set and idx < self.target_row
        )
        insert_idx = max(0, min(self.target_row - items_before_target, len(remaining_ids)))
        reordered_ids = remaining_ids[:insert_idx] + moving_ids + remaining_ids[insert_idx:]

        for s in all_sections:
            sid = int(s["id"])
            self._sections_meta[sid] = dict(s)
            self._old_positions[sid] = int(s.get("position", 0) or 0)

        for pos, sid in enumerate(reordered_ids):
            self._new_positions[sid] = pos

        self._prepared = True

    def _execute_operation(self) -> bool:
        try:
            self._prepare_data()
            if self.sphere_id is None or self._old_positions == self._new_positions:
                return True

            sb = _require_structure_business(self.main)
            begin_batch = getattr(sb, "begin_batch", None)
            end_batch = getattr(sb, "end_batch", None)
            if callable(begin_batch):
                begin_batch()
            try:
                for sid, pos in self._new_positions.items():
                    if self._old_positions.get(sid) != pos:
                        meta = self._sections_meta.get(sid, {})
                        payload = {
                            "name": meta.get("name", ""),
                            "sphere_id": self.sphere_id,
                            "icon_path": meta.get("icon_path", ""),
                            "position": pos,
                        }
                        sb.update_section(sid, payload)
            finally:
                if callable(end_batch):
                    end_batch()

            self._invalidate_caches(sb, [self.sphere_id])
            return True
        except Exception as e:
            context = {
                "operation": "reorder_sections",
                "section_ids": self.section_ids,
                "target_row": self.target_row,
            }
            error_handler.handle_error(e, context)
            return False

    def _restore_original_state(self) -> bool:
        try:
            if self.sphere_id is None or self._old_positions == self._new_positions:
                return True

            sb = _require_structure_business(self.main)
            begin_batch = getattr(sb, "begin_batch", None)
            end_batch = getattr(sb, "end_batch", None)
            if callable(begin_batch):
                begin_batch()
            try:
                for sid, pos in self._old_positions.items():
                    if self._new_positions.get(sid) != pos:
                        meta = self._sections_meta.get(sid, {})
                        payload = {
                            "name": meta.get("name", ""),
                            "sphere_id": self.sphere_id,
                            "icon_path": meta.get("icon_path", ""),
                            "position": pos,
                        }
                        sb.update_section(sid, payload)
            finally:
                if callable(end_batch):
                    end_batch()

            self._invalidate_caches(sb, [self.sphere_id])
            return True
        except Exception as e:
            context = {
                "operation": "undo_reorder_sections",
                "section_ids": self.section_ids,
            }
            error_handler.handle_error(e, context)
            return False

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
        if self.sphere_id is None:
            return
        main_window = _require_main(self.main)
        structure_ctrl = getattr(main_window, "structure", None)
        tree = getattr(structure_ctrl, "tree", None) if structure_ctrl else None
        model = tree.model() if tree and hasattr(tree, "model") else None

        target_positions = (
            self._new_positions
            if getattr(self, "_last_operation", "redo") != "undo"
            else self._old_positions
        )
        ordered_ids = [
            sid for sid, _ in sorted(target_positions.items(), key=lambda item: item[1])
        ]

        if model and hasattr(model, "reorder_sections") and model.reorder_sections(ordered_ids):
            focus_id = self.section_ids[0] if self.section_ids else None
            if focus_id and hasattr(model, "index_for") and tree:
                idx = model.index_for("section", focus_id)
                if idx and idx.isValid():
                    tree.setCurrentIndex(idx)
        elif structure_ctrl and hasattr(structure_ctrl, "load"):
            focus_id = self.section_ids[0] if self.section_ids else None
            item_to_select = ("section", focus_id) if focus_id else None
            try:
                structure_ctrl.load(item_to_select=item_to_select)
            except Exception as e:
                logger.warning("Failed to refresh structure after reordering sections: %s", e)

