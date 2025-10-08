"""
Centralized Undo/Redo commands for drag-and-drop links and categories.
"""

import logging

from app.controllers.ui.undo.base import BaseCommand
from app.utils.common import get_value

logger = logging.getLogger(__name__)

# get_value imported from app.utils.common


class MoveLinksCommand(BaseCommand):
    """Moving one or multiple links to another category with proper undo/redo."""

    def __init__(self, link_ids, new_category_id, main_window):
        super().__init__(f"Moving {len(link_ids)} links", main_window)
        self.link_ids = link_ids
        self.new_category_id = new_category_id
        self._old_states = []  # state before moving
        self._new_states = []  # state after moving
        self.old_category_id = None
        self._prepared = False  # data preparation flag

    def _prepare_data(self):
        """Prepares data for operation (called in redo)."""
        if self._prepared:
            return

        # Get original data via business logic
        links_business = self.main.links_business
        for lid in self.link_ids:
            link_data = links_business.get_link_by_id(lid)
            if link_data is None:
                raise ValueError(f"Link with id {lid} not found")
            self._old_states.append(link_data)

        self.old_category_id = (
            self._old_states[0]["category_id"] if self._old_states else None
        )

        # Get next position via business logic
        start_pos = links_business.get_next_position(self.new_category_id)

        # Get existing links for duplicate check
        existing_links = links_business.get_links(self.new_category_id)

        # Prepare new states
        temp_new_states = []
        for offset, st in enumerate(self._old_states):
            ns = st.copy()
            ns["category_id"] = self.new_category_id
            ns["position"] = start_pos + offset
            # Check for duplicate
            if not self._is_duplicate(ns, existing_links):
                temp_new_states.append(ns)
                existing_links.append(
                    ns
                )  # Prevent duplicates during multiple copying

        self._new_states = temp_new_states
        self._prepared = True

    def _is_duplicate(self, candidate, links):
        """Checks if link is a duplicate."""
        for link in links:
            # Duplicate per user requirement: name, url, args match within category
            # Type is not considered
            if (
                get_value(link, "name", "") == get_value(candidate, "name", "")
                and get_value(link, "url", "") == get_value(candidate, "url", "")
                and get_value(link, "args", "") == get_value(candidate, "args", "")
            ):
                return True
        return False

    def _execute_batch_operation(self, states):
        """Executes batch operation with links via business logic."""
        if not states:
            return

        links_business = self.main.links_business
        try:
            # Use transactional batch operation
            links_business.batch_update_links(states)
        except Exception as e:
            logger.error("Error during batch link update: %s", e)
            raise

    def _refresh_ui(self, old_category=None, new_category=None):
        """Updates UI after operation."""
        # Update both categories if they are different
        categories_to_update = set()
        if old_category:
            categories_to_update.add(old_category)
        if new_category:
            categories_to_update.add(new_category)

        for category_id in categories_to_update:
            try:
                ctrl = getattr(self.main, "links_table_controller", None)
                if ctrl:
                    ctrl.reload(category_id)
                else:
                    links_business = getattr(self.main, "links_business", None)
                    if links_business:
                        try:
                            links_business.load_links(category_id)
                        except Exception:
                            pass
            except Exception:
                # Don't fail command due to UI
                pass

        # Switch focus to target category after moving
        if (
            new_category
            and hasattr(self.main, "structure_business")
            and self.main.structure_business
        ):
            try:
                self.main.structure_business.select_category(new_category)
                logger.info(
                    "Switched focus to target category %s after moving links",
                    new_category,
                )
            except Exception as e:
                logger.warning(
                    "Failed to switch focus to category %s: %s",
                    new_category,
                    e,
                )

    def redo(self):
        """Execute link moving."""
        self._prepare_data()  # Prepare data on first execution
        self._execute_batch_operation(self._new_states)
        self._refresh_ui(
            old_category=self.old_category_id, new_category=self.new_category_id
        )

    def undo(self):
        """Undo link moving."""
        self._execute_batch_operation(self._old_states)
        # On undo swap categories - focus should return to original
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
                logger.info(
                    "Switched focus to moved category %s", self.category_id
                )
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

    def _apply_states(self, states):
        if not states:
            return
        sb = self.main.structure_business
        # Подавляем лишние сигналы выбора/перерисовки дерева на время пакетного применения
        struct = getattr(self.main, "structure", None)
        tree = getattr(struct, "tree", None)
        selection = getattr(struct, "selection_handler", None)
        try:
            # Включаем батч-режим бизнес-слоя (если поддерживается)
            try:
                if hasattr(sb, "begin_batch"):
                    sb.begin_batch()
            except Exception:
                pass
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

            # Attempt to use real batch operation if all elements move to one section
            try:
                target_ids = [
                    int(st.get("id")) for st in states if isinstance(st.get("id"), int)
                ]
                targets = {st.get("section_id") for st in states}
                single_target = len(targets) == 1
                target_section_id = next(iter(targets)) if single_target else None
            except Exception:
                target_ids = []
                single_target = False
                target_section_id = None

            batch_done = False
            if single_target and isinstance(target_section_id, int):
                try:
                    # Вычислим base_row как минимальную позицию среди целевых состояний
                    base_row = 0
                    try:
                        base_row = (
                            min(int(st.get("position", 0) or 0) for st in states)
                            if states
                            else 0
                        )
                    except Exception:
                        base_row = 0
                    moved = sb.move_categories_batch(
                        target_ids, int(target_section_id), int(base_row)
                    )
                    batch_done = True
                    if len(moved) != len(target_ids):
                        logger.debug(
                            "Some categories skipped by batch move (name duplicates in target section)"
                        )
                except Exception:
                    # Safe fallback to individual category updates
                    batch_done = False

            # Fallback: individual category updates (old behavior)
            for st in states:
                try:
                    cid = st["id"]
                    payload = {
                        "name": st.get("name", ""),
                        "section_id": st.get("section_id"),
                        "icon_path": st.get("icon_path", ""),
                        "position": st.get("position", 0),
                    }
                    sb.update_category(cid, payload)
                except Exception as e:
                    logger.error(
                        "Error updating category %s: %s", st.get("id"), e
                    )
        finally:
            # Restore normal signal processing
            try:
                if tree is not None:
                    tree.blockSignals(False)
            except Exception:
                pass
            try:
                if selection is not None:
                    selection.end_suppress_selection()
            except Exception:
                pass
            # End batch mode to perform single reload consolidation
            try:
                if hasattr(sb, "end_batch"):
                    sb.end_batch()
            except Exception:
                pass

    def _refresh_ui(self, focus_section_id=None, focus_category_id=None):
        sb = getattr(self.main, "structure_business", None)
        if not sb:
            return
        # Suppress selection event flood during final focus switch
        struct = getattr(self.main, "structure", None)
        selection = getattr(struct, "selection_handler", None)
        tree = getattr(struct, "tree", None)
        try:
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

        # Informative log
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
