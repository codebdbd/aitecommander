import logging
from typing import TYPE_CHECKING, Any, Collection, Mapping, cast

# Module containing row operations for the links table
# Provides methods for adding, updating, and removing rows

if TYPE_CHECKING:
    from app.views.widgets.protocols import LinkTableWidgetProtocol

logger = logging.getLogger(__name__)


class RowOperationsMixin:
    """Mixin with row-level operations for the links table.
    
    This mixin expects to be used with a class that implements LinkTableProtocol.
    Provides methods for updating, adding, and removing individual rows.
    """
    
    if TYPE_CHECKING:
        _current_links: dict[int, dict[str, Any]]
        def _links_equal(
            self,
            link1: dict[str, Any],
            link2: dict[str, Any],
            mode: str,
        ) -> bool: ...

    def _link_table(self) -> "LinkTableWidgetProtocol":
        """Return ``self`` typed as ``LinkTableWidgetProtocol`` for mypy."""

        return cast("LinkTableWidgetProtocol", self)

    def _link_cache(self) -> dict[int, dict[str, Any]]:
        """Helper access to current links cache."""
        cache = getattr(self, "_current_links", None)
        if cache is None:
            cache = {}
            self._current_links = cache
        return cache

    def update_link_by_id(self, link: dict[str, Any], mode: str = "normal") -> bool:
        """
        Update a table row by the link ID when present.
        """
        try:
            from app.config_data import app_config

            _debug = bool(app_config.ui.get_debug_links_inline_update())
            # Validate input
            if not isinstance(link, dict):
                logger.warning(
                    "[LinksTableView] Invalid link payload for update: %s",
                    type(link),
                )
                return False

            link_id = link.get("id")
            if not isinstance(link_id, int):
                logger.warning(
                    "[LinksTableView] Missing integer ID in link payload for update"
                )
                return False

            # Use the model to locate the row by ID
            table = self._link_table()
            try:
                model = table.model()
            except Exception:
                model = None
            row = -1
            if model is not None and hasattr(model, "find_row_by_id"):
                try:
                    row = model.find_row_by_id(link_id)
                except Exception:
                    row = -1
            else:
                # Fallback: linear search via ``get_link_at``
                try:
                    total = model.rowCount() if model is not None else 0
                except Exception:
                    total = 0
                for r in range(total):
                    row_data = table.get_link_at(r)
                    if (
                        isinstance(row_data, dict)
                        and isinstance(row_data.get("id"), int)
                        and row_data.get("id") == link_id
                    ):
                        row = r
                        break

            if row >= 0:
                if _debug:
                    logger.debug(
                        "update_link_by_id: found row=%s for id=%s; updating",
                        row,
                        link_id,
                    )
                success = self._update_row(row, link, mode)
                if _debug:
                    logger.debug(
                        "update_link_by_id: dataChanged emitted for row=%s success=%s",
                        row,
                        success,
                    )
                return success

            if _debug:
                logger.debug("update_link_by_id: id=%s not found in table", link_id)
            return False
        except Exception as e:
            logger.error(
                "[LinksTableView] Row update by ID failed: %s", e, exc_info=True
            )
            return False

    def _update_row(self, row: int, link: dict[str, Any], mode: str) -> bool:
        """Update an existing row with new data via the model."""
        try:
            # Validate input
            if not isinstance(link, dict):
                logger.warning(
                    f"[LinksTableView] Invalid link payload for row update: {type(link)}"
                )
                return False

            # Validate row index against the model
            table = self._link_table()
            try:
                model = table.model()
                total = model.rowCount() if model is not None else 0
            except Exception:
                model = None
                total = 0

            if row < 0 or row >= total:
                logger.warning(
                    "[LinksTableView] Invalid row index for update: %s",
                    row,
                )
                return False

            # Attempt to update via model
            updated = False
            if model is not None and hasattr(model, "update_link"):
                try:
                    updated = bool(model.update_link(row, link))
                except Exception as e:
                    logger.debug(
                        "[LinksTableView] model.update_link raised: %s",
                        e,
                        exc_info=True,
                    )
                    updated = False

            if not updated:
                logger.warning(
                    "[LinksTableView] model.update_link unavailable — skipping row update"
                )
                return False

            # Refresh cache (legacy compatibility)
            try:
                self._link_cache()[row] = link
            except Exception:
                logger.debug(
                    "[LinksTableView] Failed to refresh cache for row %s",
                    row,
                    exc_info=True,
                )
            # Skip forced viewport repaint to reduce load — dataChanged will trigger repaint
            logger.debug("Row %s updated", row)
            return True

        except Exception as e:
            logger.error(
                "[LinksTableView] Row update error %s: %s",
                row,
                e,
                exc_info=True,
            )
            return False

    def _add_row(self, row: int, link: dict[str, Any], mode: str) -> bool:
        """Insert a new row via the model for the given mode."""
        try:
            if not isinstance(link, dict):
                logger.warning(
                    "[LinksTableView] Invalid link payload for insert: %s",
                    type(link),
                )
                return False

            table = self._link_table()
            try:
                model = table.model()
                total = model.rowCount() if model is not None else 0
            except Exception:
                model = None
                total = 0

            if row < 0 or row > total:
                logger.warning(
                    "[LinksTableView] Invalid row index for insert: %s",
                    row,
                )
                return False

            inserted = False
            if model is not None and hasattr(model, "insert_link"):
                try:
                    inserted = bool(model.insert_link(row, link))
                except Exception as e:
                    logger.debug(
                        "[LinksTableView] model.insert_link raised: %s",
                        e,
                        exc_info=True,
                    )
                    inserted = False

            if not inserted:
                return False

            try:
                table.rebuild_cache_from_items()
            except Exception:
                logger.debug(
                    "[LinksTableView] rebuild_cache_from_items failed after insert",
                    exc_info=True,
                )

            return True

        except Exception as e:
            logger.error(
                "[LinksTableView] Row insert error %s: %s",
                row,
                e,
                exc_info=True,
            )
            return False

    def _remove_row(self, row: int) -> bool:
        """Remove a row via the model."""
        try:
            table = self._link_table()
            try:
                model = table.model()
                total = model.rowCount() if model is not None else 0
            except Exception:
                model = None
                total = 0

            if row < 0 or row >= total:
                logger.warning(
                    "[LinksTableView] Invalid row index for removal: %s",
                    row,
                )
                return False

            removed = False
            if model is not None and hasattr(model, "remove_row"):
                try:
                    removed = bool(model.remove_row(row))
                except Exception as e:
                    logger.debug(
                        "[LinksTableView] model.remove_row raised: %s",
                        e,
                        exc_info=True,
                    )
                    removed = False

            if not removed:
                return False

            try:
                table.rebuild_cache_from_items()
            except Exception:
                pass

            return True

        except Exception as e:
            logger.error(
                "[LinksTableView] Row removal error %s: %s",
                row,
                e,
                exc_info=True,
            )
            return False

    def _remove_links(self, ids_to_remove: Collection[int]) -> None:
        """Remove multiple links by their IDs."""

        if not ids_to_remove:
            return

        ids = {link_id for link_id in ids_to_remove if isinstance(link_id, int)}
        if not ids:
            return

        table = self._link_table()
        try:
            model = table.model()
            total = model.rowCount() if model is not None else 0
        except Exception:
            model = None
            total = 0

        if total <= 0:
            return

        removed: set[int] = set()
        for row in range(total - 1, -1, -1):
            link_data = table.get_link_at(row)
            link_id = link_data.get("id") if isinstance(link_data, dict) else None
            if not isinstance(link_id, int) or link_id not in ids:
                continue

            if self._remove_row(row):
                removed.add(link_id)

            if removed == ids:
                break

        missing = ids - removed
        if missing:
            logger.debug(
                "[LinksTableView] Failed to remove IDs via incremental update: %s",
                sorted(missing),
            )

    def _update_links(
        self,
        ids_to_check: Collection[int],
        new_link_map: Mapping[int, dict[str, Any]],
        mode: str,
    ) -> None:
        """Update existing rows for the given IDs."""

        if not ids_to_check or not new_link_map:
            return

        ids = {link_id for link_id in ids_to_check if isinstance(link_id, int)}
        if not ids:
            return

        compare_mode = mode or getattr(self, "_current_mode", "normal")

        table = self._link_table()
        try:
            model = table.model()
            total = model.rowCount() if model is not None else 0
        except Exception:
            model = None
            total = 0

        if total <= 0:
            return

        for row in range(total):
            link_data = table.get_link_at(row)
            if not isinstance(link_data, dict):
                continue

            link_id = link_data.get("id")
            if not isinstance(link_id, int) or link_id not in ids:
                continue

            new_data = new_link_map.get(link_id)
            if not isinstance(new_data, dict):
                continue

            try:
                unchanged = self._links_equal(link_data, new_data, compare_mode)
            except Exception:
                unchanged = link_data == new_data

            if unchanged:
                continue

            self._update_row(row, new_data, compare_mode)

    def _add_links(
        self,
        links: Collection[dict[str, Any]],
        ids_to_add: Collection[int],
        sort_col: int,
    ) -> None:
        """Add new links for the given IDs."""

        if not links or not ids_to_add:
            return

        ids = {link_id for link_id in ids_to_add if isinstance(link_id, int)}
        if not ids:
            return

        table = self._link_table()
        try:
            model = table.model()
            base_row = model.rowCount() if model is not None else 0
        except Exception:
            model = None
            base_row = 0

        mode = getattr(self, "_current_mode", "normal")
        inserted = 0
        processed: set[int] = set()

        for link in links:
            if not isinstance(link, dict):
                continue

            link_id = link.get("id")
            if not isinstance(link_id, int) or link_id not in ids:
                continue

            if link_id in processed:
                continue

            target_row = base_row + inserted
            if self._add_row(target_row, link, mode):
                inserted += 1
                processed.add(link_id)

        missing = ids - processed
        if missing:
            logger.debug(
                "[LinksTableView] Failed to add IDs via incremental update: %s",
                sorted(missing),
            )
