# Module for managing data and cache of the links table
# Provides cache utilities, validation, and comparison helpers

import logging
from typing import TYPE_CHECKING, Any, Optional

from PyQt6.QtCore import QAbstractItemModel, QModelIndex, Qt

if TYPE_CHECKING:
    pass


class DataManagementMixin:
    """Mixin responsible for managing data and cache of the links table."""

    logger = logging.getLogger(__name__)
    _current_links: dict[
        int, dict[str, Any]
    ]  # expected to be populated by the table view

    # Methods expected from QTableView (for type checking)
    if TYPE_CHECKING:

        def selectRow(self, row: int) -> None: ...
        def model(self) -> Optional["QAbstractItemModel"]: ...
        def setCurrentIndex(self, index: QModelIndex) -> None: ...
        def scrollTo(self, index: QModelIndex) -> None: ...

    # --- Helper properties ---
    @property
    def _link_cache(self) -> dict[int, dict[str, Any]]:
        """Return the internal links cache, creating it if missing."""
        cache = getattr(self, "_current_links", None)
        if cache is None:
            cache = {}
            self._current_links = cache
        return cache

    def validate_cache_integrity(self) -> bool:
        """Validate the integrity of the links cache."""
        try:
            model = getattr(self, "model", lambda: None)()
            row_count = model.rowCount() if model is not None else 0
            cache_size = len(self._link_cache)

            # Ensure cache size matches the number of rows
            if cache_size != row_count:
                self.logger.warning(
                    "[LinksTableView] Cache size mismatch: %s != %s",
                    cache_size,
                    row_count,
                )
                return False

            # Verify every cached index is within the valid range
            for row in self._link_cache.keys():
                if not (0 <= row < row_count):
                    self.logger.warning(
                        "[LinksTableView] Invalid cache index: %s",
                        row,
                    )
                    return False

            return True
        except Exception as e:
            self.logger.error(
                "[LinksTableView] Cache integrity validation error: %s", e
            )
            return False

    def _links_equal(self, link1: dict, link2: dict, mode: str) -> bool:
        """Compare two links for equality under the active mode."""
        # Optimization: early identity check
        if link1 is link2:
            return True

        if not link1 or not link2:
            return False

        # Quick ID check
        if link1.get("id") != link2.get("id"):
            return False

        # Base fields always considered
        basic_fields = ["name", "is_favorite", "notes", "icon_path", "args"]

        # Additional fields per mode
        if mode == "normal":
            basic_fields.append("last_used")
        else:  # search mode
            basic_fields.extend(
                ["url", "path", "sphere_name", "section_name", "category_name"]
            )

        # Optimization: lean on ``all()`` for fast comparison
        return all(link1.get(field) == link2.get(field) for field in basic_fields)

    def _get_current_link_ids(self) -> set[int]:
        """Return the set of current link IDs based on table items (not cache)."""
        ids: set[int] = set()
        model = getattr(self, "model", lambda: None)()
        total = model.rowCount() if model is not None else 0
        for row in range(total):
            link_data = self.get_link_at(row)
            if link_data is not None:
                link_id = link_data.get("id")
                if isinstance(link_id, int):
                    ids.add(link_id)
        return ids

    def _get_new_link_ids(self, new_links: list[dict[str, Any]]) -> set[int]:
        """Return the set of new link IDs."""
        ids: set[int] = set()
        for link in new_links:
            if not link:
                continue
            link_id = link.get("id")
            if isinstance(link_id, int):
                ids.add(link_id)
        return ids

    def rebuild_cache_from_items(self) -> None:
        """Rebuild ``_current_links`` cache from the current table state."""
        try:
            self._link_cache.clear()
            model = getattr(self, "model", lambda: None)()
            total = model.rowCount() if model is not None else 0
            for row in range(total):
                link_data = self.get_link_at(row)
                if link_data:
                    self._link_cache[row] = link_data
        except Exception as e:
            self.logger.error(
                "[LinksTableView] Failed to rebuild cache from items: %s",
                e,
            )

    def _create_link_id_to_data_map(
        self, links: list[dict[str, Any]]
    ) -> dict[int, dict[str, Any]]:
        """Create a mapping ``ID -> link data``."""
        mapping: dict[int, dict[str, Any]] = {}
        for link in links:
            if not link:
                continue
            link_id = link.get("id")
            if isinstance(link_id, int):
                mapping[link_id] = link
        return mapping

    def get_link_at(self, row: int) -> Optional[dict[str, Any]]:
        """Return link data for the row via model ``UserRole``."""
        try:
            model = getattr(self, "model", lambda: None)()
            if model is None:
                return None
            if not (0 <= row < model.rowCount()):
                return None
            idx = model.index(row, 0)
            data = model.data(idx, Qt.ItemDataRole.UserRole)
            return data if isinstance(data, dict) else None
        except Exception as e:
            self.logger.error(
                "[LinksTableView] Failed to fetch link data at row %s: %s",
                row,
                e,
            )
            return None

    def find_row_by_link_id(self, link_id: int) -> Optional[int]:
        """Find a table row by the link ID."""
        try:
            model = getattr(self, "model", lambda: None)()
            if model is None:
                return None
            for row in range(model.rowCount()):
                link_data = self.get_link_at(row)
                if link_data and link_data.get("id") == link_id:
                    return row
            return None
        except Exception as e:
            self.logger.error(
                "[LinksTableView] Failed to find row by ID %s: %s", link_id, e
            )
            return None

    def focus_on_link_id(self, link_id: int) -> bool:
        """Focus the view on the link with the given ID."""
        try:
            row = self.find_row_by_link_id(link_id)
            if row is not None:
                # QTableView API
                self.selectRow(row)
                model = self.model()
                if model is None:
                    return False
                idx = model.index(row, 0)
                self.setCurrentIndex(idx)
                self.scrollTo(idx)
                self.logger.info(
                    "[LinksTableView] Focused on link ID %s at row %s",
                    link_id,
                    row,
                )
                return True
            else:
                self.logger.warning(
                    "[LinksTableView] Link with ID %s not found in the table",
                    link_id,
                )
                return False
        except Exception as e:
            self.logger.error(
                "[LinksTableView] Failed to focus link ID %s: %s",
                link_id,
                e,
            )
            return False
