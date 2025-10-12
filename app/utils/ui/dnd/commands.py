"""Centralized Undo/Redo commands for drag-and-drop links and categories."""

import logging
from typing import Any

from app.controllers.ui.undo.base import BaseCommand
from app.utils.common import get_value

logger = logging.getLogger(__name__)
# get_value imported from app.utils.common


class MoveLinksCommand(BaseCommand):
    """Move one or more links to another category with undo/redo support."""

    def __init__(self, link_ids, new_category_id, main_window):
        super().__init__(f"Moving {len(list(link_ids))} links", main_window)
        self.link_ids = [int(lid) for lid in link_ids]
        self.new_category_id = int(new_category_id)
        self._old_states: list[dict[str, Any]] = []
        self._new_states: list[dict[str, Any]] = []
        self.old_category_id: int | None = None
        self._prepared = False

    def _prepare_data(self) -> None:
        if self._prepared:
            return
        links_business = getattr(self.main, "links_business", None)
        if not links_business:
            raise RuntimeError("links_business is not available in main window")
        links_service = getattr(links_business, "links", None)
        if not links_service:
            raise RuntimeError("links_business.links service is unavailable")

        self._old_states.clear()
        for lid in self.link_ids:
            try:
                link_data = links_service.get_link_by_id(int(lid)) or {}
            except Exception as exc:
                raise ValueError(f"Failed to load link #{lid}: {exc}") from exc
            if not link_data:
                raise ValueError(f"Link with id {lid} not found")
            self._old_states.append(dict(link_data))

        if not self._old_states:
            raise ValueError("No valid links supplied for move operation")

        origin_category_raw = self._old_states[0].get("category_id")
        self.old_category_id = int(origin_category_raw) if origin_category_raw else None

        try:
            start_pos = links_business.get_next_position(self.new_category_id)
        except Exception:
            start_pos = 0

        try:
            existing = links_business.get_links(self.new_category_id) or []
            existing_links = [dict(row) for row in existing]
        except Exception:
            existing_links = []

        prepared: list[dict[str, Any]] = []
        for offset, original in enumerate(self._old_states):
            candidate = dict(original)
            candidate["category_id"] = self.new_category_id
            candidate["position"] = start_pos + offset
            if not self._is_duplicate(candidate, existing_links):
                prepared.append(candidate)
                existing_links.append(candidate)
        self._new_states = prepared
        self._prepared = True

    def _is_duplicate(self, candidate, links):
        for link in links:
            if (
                get_value(link, "name", "") == get_value(candidate, "name", "")
                and get_value(link, "url", "") == get_value(candidate, "url", "")
                and get_value(link, "args", "") == get_value(candidate, "args", "")
            ):
                return True
        return False

    def _execute_batch_operation(self, states):
        if not states:
            return
        links_business = getattr(self.main, "links_business", None)
        if not links_business or not hasattr(links_business, "links"):
            raise RuntimeError("links_business is not available in main window")
        try:
            links_business.links.batch_update(states)
        except Exception as exc:
            logger.error("Error during batch link update: %s", exc, exc_info=True)
            raise

    def _refresh_ui(self, old_category=None, new_category=None):
        categories_to_update = {cid for cid in (old_category, new_category) if cid}
        for category_id in categories_to_update:
            try:
                ctrl = getattr(self.main, "links_table_controller", None)
                if ctrl:
                    ctrl.reload(category_id)
                else:
                    links_business = getattr(self.main, "links_business", None)
                    if links_business:
                        links_business.load_links(category_id)
            except Exception as exc:
                logger.debug(
                    "Failed to refresh links for category %s: %s", category_id, exc
                )

    def redo(self):
        self._prepare_data()
        self._execute_batch_operation(self._new_states)
        self._refresh_ui(
            old_category=self.old_category_id, new_category=self.new_category_id
        )

    def undo(self):
        self._execute_batch_operation(self._old_states)
        self._refresh_ui(
            old_category=self.new_category_id, new_category=self.old_category_id
        )


class MoveCategoryCommand(BaseCommand):
    """Moving category between sections."""

    def __init__(self, category_id, new_section_id, main_window):
        super().__init__("Moving category", main_window)

        self.category_id = category_id

        self.new_section_id = new_section_id

        self.old_section_id = None

        self.cat_name = None

        self._prepared = False

    def _prepare_data(self):
        """Prepares data for operation."""

        if self._prepared:
            return

        # Get category data via business logic

        structure_business = self.main.structure_business

        category_data = structure_business.get_category_data(self.category_id)

        if category_data is None:
            raise ValueError(f"Category {self.category_id} not found")

        self.old_section_id = category_data["section_id"]

        self.cat_name = category_data["name"]

        self._prepared = True

    def _set_section(self, section_id):
        """Sets section for category via business logic."""

        structure_business = self.main.structure_business

        # Get full category data for update

        current_category = structure_business.get_category_data(self.category_id)

        if current_category is None:
            raise ValueError(f"Category {self.category_id} not found")

        # Update only section_id, keeping other data

        category_data = {
            "name": current_category["name"],
            "section_id": section_id,
            "icon_path": current_category.get("icon_path", ""),
            "position": current_category.get("position", 0),
        }

        # Now update is delegated to business layer which calls StructureService

        updated = structure_business.update_category(self.category_id, category_data)

        if updated is None:
            raise ValueError(f"Failed to update category {self.category_id}")

    def redo(self):
        try:
            self._prepare_data()

            if self.old_section_id == self.new_section_id:
                return

            # Check duplicates via business logic

            structure_business = self.main.structure_business

            if structure_business.has_duplicate_category(
                self.new_section_id, self.cat_name, self.category_id
            ):
                # Silently ignore duplicates - don't show error to user

                logger.debug(
                    "Duplicate category '%s' found in target section %s, ignoring move",
                    self.cat_name,
                    self.new_section_id,
                )

                self.setObsolete(True)

                return

            self._set_section(self.new_section_id)

            self._refresh_structure_ui()

        except Exception as e:
            logger.error("Error during category moving: %s", e)

            raise

    def undo(self):
        try:
            self._set_section(self.old_section_id)

            self._refresh_structure_ui()

        except Exception as e:
            logger.error("Error during category move undo: %s", e)

            raise

    def _refresh_structure_ui(self):
        """Updates structure UI after operation."""

        # Full tree reload no longer required — model updates incrementally

        # through business logic signals (item_updated etc.). Focus needed category.

        if hasattr(self.main, "structure_business") and self.main.structure_business:
            try:
                self.main.structure_business.select_category(self.category_id)

                logger.info("Switched focus to moved category %s", self.category_id)

            except Exception as e:
                logger.warning(
                    "Failed to switch focus to category %s: %s",
                    self.category_id,
                    e,
                )


class MoveCategoriesCommand(BaseCommand):
    """Batch moving multiple categories to one section with unified undo/redo.

    - Saves original states (section_id, position, name, icon_path)

    - Redo: moves to target section, setting positions base_row + i

    - Undo: restores original section_id and position

    - Duplicates in target section are silently skipped (DEBUG)

    """

    def __init__(self, category_ids, new_section_id, base_row, main_window):
        super().__init__(f"Moving {len(category_ids)} categories", main_window)

        self.category_ids = list(category_ids or [])

        self.new_section_id = (
            int(new_section_id) if isinstance(new_section_id, int) else new_section_id
        )

        self.base_row = int(base_row) if isinstance(base_row, int) else 0

        self._old_states = []  # [{id, name, section_id, position, icon_path}]

        self._new_states = []  # same format but with target section/position

        self._prepared = False

    def _prepare_data(self):
        if self._prepared:
            return

        sb = self.main.structure_business

        # Load original states

        old_states = []

        for cid in self.category_ids:
            data = sb.get_category_data(cid)

            if not data:
                logger.debug("Category %s not found, skipping", cid)

                continue

            old_states.append(
                {
                    "id": data["id"],
                    "name": data.get("name", ""),
                    "section_id": data.get("section_id"),
                    "position": data.get("position", 0),
                    "icon_path": data.get("icon_path", ""),
                }
            )

        # Stable order by original position, then by id

        old_states.sort(key=lambda x: (x.get("position", 0), x.get("id", 0)))

        # Form target states with name duplicate check in target section

        new_states = []

        offset = 0

        for st in old_states:
            cid = st["id"]

            name = st.get("name", "")

            # Name duplicates in target section — skip

            try:
                if sb.has_duplicate_category(self.new_section_id, name, cid):
                    logger.debug(
                        "Duplicate category '%s' in target section %s, skipping id=%s",
                        name,
                        self.new_section_id,
                        cid,
                    )

                    continue

            except Exception:
                # If check fails — don't block operation, try to move

                pass

            ns = {
                "id": cid,
                "name": name,
                "section_id": self.new_section_id,
                "position": self.base_row + offset,
                "icon_path": st.get("icon_path", ""),
            }

            new_states.append(ns)

            offset += 1

        self._old_states = old_states

        self._new_states = new_states

        self._prepared = True

    def _suppress_ui_signals(self, selection, tree):
        """Suppress selection and tree signals during batch operations."""
        if selection is not None:
            try:
                selection.begin_suppress_selection()
            except Exception:
                pass
        if tree is not None:
            try:
                tree.blockSignals(True)
            except Exception:
                pass

    def _restore_ui_signals(self, selection, tree):
        """Restore selection and tree signals after batch operations."""
        if tree is not None:
            try:
                tree.blockSignals(False)
            except Exception:
                pass
        if selection is not None:
            try:
                selection.end_suppress_selection()
            except Exception:
                pass

    def _extract_target_info(self, states):
        """Extract target IDs and section info from states."""
        try:
            target_ids = [
                int(st.get("id")) for st in states if isinstance(st.get("id"), int)
            ]
            targets = {
                st.get("section_id")
                for st in states
                if isinstance(st.get("section_id"), int)
            }
            single_target = len(targets) == 1
            target_section_id = next(iter(targets)) if single_target else None
            return target_ids, single_target, target_section_id
        except Exception:
            return [], False, None

    def _try_batch_move(self, sb, target_ids, target_section_id, states):
        """Attempt batch move operation, return (moved_ids, success)."""
        try:
            base_row = (
                min(int(st.get("position", 0) or 0) for st in states)
                if states
                else 0
            )
        except Exception:
            base_row = 0

        try:
            moved_ids = (
                sb.move_categories_batch(
                    target_ids, int(target_section_id), int(base_row)
                )
                or []
            )
            batch_done = bool(moved_ids)
            if batch_done and len(moved_ids) != len(target_ids):
                logger.debug(
                    "Some categories skipped by batch move (name duplicates in target section)"
                )
            return moved_ids, batch_done
        except Exception as exc:
            logger.debug(
                "Batch move failed, falling back to per-item updates: %s",
                exc,
                exc_info=True,
            )
            return [], False

    def _update_remaining_categories(self, sb, remaining_states, old_section_by_id):
        """Update categories that weren't moved in batch operation."""
        touched_override: set[int] = set()

        touched_override.update(
            {
                old_section_by_id.get(st.get("id"))
                for st in remaining_states
                if isinstance(old_section_by_id.get(st.get("id")), int)
            }
        )
        touched_override.update(
            {
                st.get("section_id")
                for st in remaining_states
                if isinstance(st.get("section_id"), int)
            }
        )

        for st in remaining_states:
            try:
                cid = st["id"]
                payload = {
                    "name": st.get("name", ""),
                    "section_id": st.get("section_id"),
                    "icon_path": st.get("icon_path", ""),
                    "position": st.get("position", 0),
                }
                sb.update_category(cid, payload)
            except Exception as exc:
                logger.error(
                    "Error updating category %s during fallback move: %s",
                    st.get("id"),
                    exc,
                )
        return touched_override

    def _apply_states(self, states):
        if not states:
            return

        sb = self.main.structure_business
        struct = getattr(self.main, "structure", None)
        tree = getattr(struct, "tree", None)
        selection = getattr(struct, "selection_handler", None)

        batch_started = False

        try:
            self._suppress_ui_signals(selection, tree)

            target_ids, single_target, target_section_id = self._extract_target_info(
                states
            )

            old_section_by_id = {
                st.get("id"): st.get("section_id")
                for st in getattr(self, "_old_states", [])
            }

            if hasattr(sb, "begin_batch") and callable(sb.begin_batch):
                try:
                    sb.begin_batch()
                    batch_started = True
                except Exception:
                    batch_started = False

            moved_ids, batch_done = [], False
            if single_target and isinstance(target_section_id, int):
                moved_ids, batch_done = self._try_batch_move(
                    sb, target_ids, target_section_id, states
                )

            moved_ids_set = set(moved_ids)
            remaining_states = (
                [st for st in states if st.get("id") not in moved_ids_set]
                if batch_done
                else list(states)
            )

            if remaining_states:
                touched_override = self._update_remaining_categories(
                    sb, remaining_states, old_section_by_id
                )

                if touched_override:
                    normalized = {
                        int(sid)
                        for sid in touched_override
                        if isinstance(sid, int) and sid > 0
                    }
                    if normalized:
                        try:
                            sb.event_service.replace_touched_sections(normalized)
                        except Exception as exc:
                            logger.debug(
                                "replace_touched_sections failed in _apply_states: %s",
                                exc,
                                exc_info=True,
                            )
        finally:
            if batch_started:
                try:
                    sb.end_batch()
                except Exception:
                    pass
            self._restore_ui_signals(selection, tree)

    def _refresh_ui(self, focus_section_id=None, focus_category_id=None):
        sb = getattr(self.main, "structure_business", None)
        if not sb:
            return

        struct = getattr(self.main, "structure", None)
        selection = getattr(struct, "selection_handler", None)
        tree = getattr(struct, "tree", None)

        try:
            self._suppress_ui_signals(selection, tree)

            try:
                if focus_section_id is not None:
                    sb.section_selected.emit(focus_section_id)
            except Exception:
                pass

            try:
                if focus_category_id is not None:
                    sb.select_category(focus_category_id)
            except Exception:
                pass

        finally:
            self._restore_ui_signals(selection, tree)

        try:
            logger.info(
                "Switched focus to section %s after batch category moving",
                focus_section_id,
            )
        except Exception:
            pass

    def redo(self):
        self._prepare_data()

        # Apply new states

        self._apply_states(self._new_states)

        # Focus on target section and first successfully moved category

        first_new_id = self._new_states[0]["id"] if self._new_states else None

        self._refresh_ui(self.new_section_id, first_new_id)

    def undo(self):
        # Restore original states

        self._apply_states(self._old_states)

        # Focus on original section of first category (if available)

        focus_section = None

        focus_category = None

        for st in self._old_states:
            if st.get("section_id") is not None:
                focus_section = st["section_id"]

                focus_category = st.get("id")

                break

        self._refresh_ui(focus_section, focus_category)
