import logging
import os
import time
from typing import Optional, Protocol, runtime_checkable

from PyQt6.QtCore import QObject

logger = logging.getLogger(__name__)
_DIAG_TABLE_POPULATE = str(os.getenv("APP_LINKS_TABLE_DIAG", "")).lower() in {
    "1",
    "true",
    "yes",
    "on",
}


@runtime_checkable
class LinksTableLike(Protocol):
    """Structural protocol for links table for early dependency validation."""

    def update_link_by_id(self, link: dict) -> None: ...

    def populate(self, links: list[dict], mode: str = "default") -> None: ...


class LinksTableController(QObject):
    """Centralized controller for links table updates.

    Tasks:
    - Safe data reload by category: reload(category_id)
    - Point update of table row by link_dict: update_row(link_dict)
    - Centralized logging and protection from parallel updates
    """

    def __init__(self, main_window, *, table, links_business, category_provider):
        """Initialize controller with explicit dependencies.

        :param main_window: main window (QObject parent)
        :param table: links table widget, must have update_link_by_id(dict) method
        :param links_business: links business logic with load_links(category_id) method
        """
        # In tests main_window can be SimpleNamespace — don't pass it as QObject parent
        try:
            from PyQt6.QtCore import (
                QObject as _QtQObject,  # local import for safety
            )

            parent = main_window if isinstance(main_window, _QtQObject) else None
        except Exception:
            parent = None
        super().__init__(parent=parent)
        self.main = main_window
        self.table = table
        self.business = links_business
        self.category_provider = category_provider
        if self.table is None or self.business is None:
            raise ValueError(
                "LinksTableController: table and links_business must be passed explicitly"
            )
        # Explicit category provider validation
        if not hasattr(self.category_provider, "current_category_id"):
            raise ValueError(
                "LinksTableController: category_provider must expose 'current_category_id' attribute"
            )
        # Check table interface at startup to not ignore runtime errors
        if not isinstance(self.table, LinksTableLike):
            raise TypeError(
                "LinksTableController: 'table' must implement LinksTableLike (update_link_by_id, populate)"
            )
        self._reloading: bool = False
        self._queued_category_id: Optional[int] = None
        self._current_category_id: Optional[int] = None
        self._current_request_id: Optional[int] = None

    # --- Public API ---
    def reload(self, category_id: Optional[int], request_id: Optional[int] = None) -> None:
        """Reload links table for specified category.

        - Delegate loading to business logic (links_ui.business or main.links_business)
        - Protection from parallel reloads: single-value queue
        """
        try:
            if not isinstance(category_id, int) or category_id <= 0:
                logger.debug(
                    "LinksTableController.reload: invalid category_id=%s", category_id
                )
                return

            if self._reloading:
                if (
                    category_id == self._current_category_id
                    and request_id == self._current_request_id
                ):
                    logger.debug(
                        "LinksTableController.reload: duplicate in-flight reload (category_id=%s request_id=%s)",
                        category_id,
                        request_id,
                    )
                    return
                # If reload already running, queue it, but avoid duplicates
                if (
                    category_id == self._current_category_id
                    or category_id == self._queued_category_id
                ):
                    logger.debug(
                        "LinksTableController.reload: already processing or queued category_id=%s",
                        category_id,
                    )
                    return
                self._queued_category_id = category_id
                logger.debug(
                    "LinksTableController.reload: busy, queued category_id=%s",
                    category_id,
                )
                return

            self._reloading = True
            logger.debug(
                "LinksTableController.reload: start (category_id=%s)", category_id
            )
            self._current_category_id = category_id
            self._current_request_id = request_id

            # Centralized: load data via business logic; UI subscribed to changes
            # Catch exceptions here for uniform logging and to not crash UI
            self.business.load_links(category_id)
        except Exception as e:
            logger.error(
                "LinksTableController.reload: unexpected error: %s", e, exc_info=True
            )
            # Release lock on error to avoid deadlock
            self._reloading = False

    def update_row(self, link_dict: Optional[dict]) -> None:
        """Point update of table row by link_dict.

        Safely calls table.update_link_by_id if available.
        """
        if not link_dict:
            return
        table = self.table
        if table is None:
            logger.debug("LinksTableController.update_row: no table available")
            return
        try:
            table.update_link_by_id(link_dict)
        except (TypeError, ValueError) as e:
            # Invalid link_dict — don't crash, but explicitly log
            logger.warning("LinksTableController.update_row: invalid link_dict: %s", e)
        except AttributeError as e:
            # Table doesn't implement required method — programming error, re-raise
            logger.error(
                "LinksTableController.update_row: table missing update_link_by_id: %s",
                e,
            )
            raise

    # --- Slots for business signals ---
    def on_links_loaded(
        self, links: list[dict], category_id: int, task_id: int
    ) -> None:
        """Centralized reaction to links loaded from business logic.

        Performs populate only if it's current category to avoid UI desync.
        """
        try:
            # Explicitly use passed category provider
            current_category_id = self.category_provider.current_category_id
            if current_category_id is not None and category_id != current_category_id:
                logger.info(
                    "Skipping table update: loaded links for category %s (task_id=%s), but current category = %s",
                    category_id,
                    task_id,
                    current_category_id,
                )
                return
            if _DIAG_TABLE_POPULATE:
                t0 = time.perf_counter()
                self.table.populate(links)
                elapsed_ms = (time.perf_counter() - t0) * 1000
                if elapsed_ms >= 50:
                    logger.info(
                        "[Perf] LinksTable.populate: %d links in %.1f ms (category_id=%s)",
                        len(links or []),
                        elapsed_ms,
                        category_id,
                    )
            else:
                self.table.populate(links)
        except Exception as e:
            logger.error(
                "LinksTableController.on_links_loaded: failed: %s", e, exc_info=True
            )
        finally:
            # Release reload lock and process queued category if any
            self._reloading = False
            if (
                isinstance(self._queued_category_id, int)
                and self._queued_category_id > 0
                and self._queued_category_id != self._current_category_id
            ):
                queued = self._queued_category_id
                self._queued_category_id = None
                logger.debug(
                    "LinksTableController.on_links_loaded: processing queued category_id=%s",
                    queued,
                )
                try:
                    self.reload(queued)
                except Exception:
                    logger.exception("LinksTableController.on_links_loaded: queued call failed")

    def on_search_results(self, search_results: list[dict]) -> None:
        """Update table with search results centrally."""
        try:
            self.table.populate(search_results, mode="search")
            # Switch right area to table so results are visible
            try:
                stack = getattr(self.main, "stack", None)
                table_container = getattr(self.main, "table_container", None)
                if stack is not None and table_container is not None:
                    # Find table container index and set current view
                    for i in range(stack.count()):
                        if stack.widget(i) is table_container:
                            stack.setCurrentIndex(i)
                            break
            except Exception:
                logger.debug(
                    "LinksTableController.on_search_results: failed to switch stack to table",
                    exc_info=True,
                )
        except Exception as e:
            logger.error(
                "LinksTableController.on_search_results: failed: %s", e, exc_info=True
            )

    # --- Slots for link_operations signals ---
    def on_links_changed(self, category_id: Optional[int]) -> None:
        """Slot for link_operations.links_changed(int) signal."""
        self.reload(category_id)

    def on_link_saved(self, payload: Optional[dict] = None) -> None:
        """Slot for link_operations.link_saved(dict) signal."""
        try:
            from app.config_data.runtime_config import is_debug_links_inline_update

            _debug = is_debug_links_inline_update()
            # If sufficiently complete link data arrived and category matches current,
            # perform ONLY point row update without full reload.
            if isinstance(payload, dict):
                link_id = payload.get("id")
                cat_id = payload.get("category_id")
                current_category_id = getattr(
                    self.category_provider, "current_category_id", None
                )
                if (
                    isinstance(link_id, int)
                    and link_id > 0
                    and isinstance(cat_id, int)
                    and cat_id > 0
                    and current_category_id == cat_id
                ):
                    try:
                        if _debug:
                            logger.debug(
                                "on_link_saved: inline update id=%s category=%s (current=%s)",
                                link_id,
                                cat_id,
                                current_category_id,
                            )
                        self.update_row(payload)
                        return
                    except Exception:
                        logger.debug(
                            "LinksTableController.on_link_saved: lightweight update failed; fallback to reload",
                            exc_info=True,
                        )
                # Fallback: if data insufficient or category mismatch — do regular reload
                if _debug:
                    logger.debug(
                        "on_link_saved: reload due to payload insufficiency or category mismatch payload_cat=%s current_cat=%s",
                        cat_id,
                        current_category_id,
                    )
                self.reload(cat_id)
                return
            # No useful payload — do safe reload without category
            if _debug:
                logger.debug("on_link_saved: reload without payload")
            self.reload(None)
        except Exception:
            logger.exception("LinksTableController.on_link_saved: failed")

    def on_link_deleted(self, payload: Optional[dict] = None) -> None:
        """Slot for link_operations.link_deleted(dict) signal."""
        try:
            cat_id = None
            if isinstance(payload, dict):
                cat_id = payload.get("category_id")
            self.reload(cat_id)
        except Exception:
            logger.exception("LinksTableController.on_link_deleted: failed")

    # --- Internals ---
