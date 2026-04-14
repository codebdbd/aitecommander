import logging
import time
from typing import Any, Optional

from PyQt6.QtCore import QAbstractListModel, QModelIndex, Qt, QTimer
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QWidget

from app.utils.ui.icon.loading_policy import get_tiles_icon_loading_policy
from app.utils.ui.icon.loading_service import icon_loading_service

logger = logging.getLogger(__name__)

# Single default QIcon to save allocations
DEFAULT_ICON = QIcon()


class CategoriesListModel(QAbstractListModel):
    """Simple model for a list of categories.

    Item: dict with keys: id (int), name (str), icon_path (str|None)
    Roles:
      - DisplayRole: name
      - DecorationRole: QIcon resolved from icon_path
      - UserRole: id
      - ToolTipRole: name (can be extended)
    """

    def __init__(
        self,
        categories: Optional[list[dict[str, Any]]] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._items: list[dict[str, Any]] = []
        # Row cache by id for O(1) lookup: id -> row
        self._row_by_id: dict[int, int] = {}
        self._pending_icon_rows: set[int] = set()
        self._icon_timer: Optional[QTimer] = None
        self._apply_icon_loading_policy()
        if categories:
            self.set_categories(categories)

    def _apply_icon_loading_policy(self) -> None:
        try:
            policy = get_tiles_icon_loading_policy()
            self._lazy_icons_enabled = bool(policy.lazy)
            self._icon_prefetch = int(policy.sync_prefetch_count)
            self._sync_prefetch_cap = int(policy.sync_prefetch_count)
            self._icon_batch_size = int(policy.batch_size)
        except Exception:
            self._lazy_icons_enabled = True
            self._icon_prefetch = 24
            self._sync_prefetch_cap = 24
            self._icon_batch_size = 32

    # --- data API ---
    def rowCount(self, parent: QModelIndex | None = None) -> int:  # type: ignore[override]
        if parent is None:
            parent = QModelIndex()
        if parent.isValid():
            return 0
        return len(self._items)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:  # type: ignore[override]
        if not index.isValid():
            return None
        row = index.row()
        if row < 0 or row >= len(self._items):
            return None
        item = self._items[row]
        if role == Qt.ItemDataRole.DisplayRole:
            return item.get("name", "")
        if role == Qt.ItemDataRole.DecorationRole:
            icon = item.get("_icon")
            if isinstance(icon, QIcon):
                return icon
            if self._lazy_icons_enabled:
                self._schedule_icon_row(row)
            return DEFAULT_ICON
        if role == Qt.ItemDataRole.UserRole:
            return item.get("id")
        if role == Qt.ItemDataRole.UserRole + 1:
            return bool(item.get("_icon_pending"))
        if role == Qt.ItemDataRole.ToolTipRole:
            return item.get("name", "")
        return None

    # --- mutators ---
    def set_categories(self, categories: list[dict[str, Any]]) -> None:
        t0 = time.perf_counter()
        t_sig_done = t0
        t_norm_done = t0
        t_reset_done = t0
        t_prefetch_done = t0
        # Normalize input data and prepare icons
        items: list[dict[str, Any]] = []
        # Fast path: if ids+names match current, skip full reset
        try:
            new_signature = [
                (int(cat.get("id")), str(cat.get("name", "")))
                for cat in categories
                if cat.get("id") is not None
            ]
            old_signature = [
                (int(it.get("id")), str(it.get("name", ""))) for it in self._items
            ]
            if new_signature == old_signature:
                logger.debug(
                    "[Perf] CategoriesListModel.set_categories skip_same_signature count=%s total=%.2f ms",
                    len(new_signature),
                    (time.perf_counter() - t0) * 1000.0,
                )
                return
        except Exception:
            pass
        t_sig_done = time.perf_counter()
        for cat in categories:
            name = cat.get("name", "")
            raw_id = cat.get("id")
            try:
                if raw_id is None:
                    raise ValueError("id is None")
                cat_id = int(raw_id)
            except Exception as e:
                # Log skipping of invalid element per common pattern
                logger.warning(
                    "Skipped category list item: invalid id (%r). Item=%r; reason: %s",
                    raw_id,
                    cat,
                    e,
                    exc_info=False,
                )
                continue
            icon_path = cat.get("icon_path", "") or ""
            item = {
                "id": cat_id,
                "name": name,
                "icon_path": icon_path,
                "_icon": None,
                "_icon_pending": self._lazy_icons_enabled,
            }
            if not self._lazy_icons_enabled:
                icon = icon_loading_service.get_path_icon(icon_path, category=True)
                item["_icon"] = icon if not icon.isNull() else DEFAULT_ICON
            items.append(item)
        t_norm_done = time.perf_counter()

        self.beginResetModel()
        self._items = items
        self._pending_icon_rows.clear()
        # Rebuild row cache by id
        # Important: keep the index of the FIRST occurrence for compatibility with previous linear lookup
        row_by_id: dict[int, int] = {}
        for idx, it in enumerate(self._items):
            cid = it["id"]
            if cid not in row_by_id:
                row_by_id[cid] = idx
        self._row_by_id = row_by_id
        self.endResetModel()
        t_reset_done = time.perf_counter()

        sync_prefetched_hits = 0
        if self._lazy_icons_enabled:
            # Prefetch a small number of icons synchronously for the first frame.
            prefetch_count = max(0, self._icon_prefetch)
            prefetch_cap = max(0, int(self._sync_prefetch_cap))
            prefetch_count = min(prefetch_count, prefetch_cap)
            if prefetch_count:
                for row in range(min(prefetch_count, len(self._items))):
                    item = self._items[row]
                    if isinstance(item.get("_icon"), QIcon):
                        continue
                    icon_path = item.get("icon_path", "") or ""
                    resolved_path = icon_loading_service.resolve_path(
                        icon_path, category=True
                    )
                    if not resolved_path:
                        item["_icon"] = DEFAULT_ICON
                        item["_icon_pending"] = False
                        continue
                    # First visible tiles should render with real icons on first paint.
                    # Keep the synchronous window bounded to avoid blocking large lists.
                    item["_icon"] = icon_loading_service.get_path_icon(
                        resolved_path, category=True
                    )
                    item["_icon_pending"] = False
                    sync_prefetched_hits += 1
            # Schedule remaining icon loads
            for row in range(prefetch_count, len(self._items)):
                self._pending_icon_rows.add(row)
            # Also schedule rows from the synchronous prefetch window that were cache misses.
            for row in range(min(prefetch_count, len(self._items))):
                item = self._items[row]
                if not bool(item.get("_icon_pending")):
                    continue
                self._pending_icon_rows.add(row)
            self._schedule_icon_loads_for_visible()
            t_prefetch_done = time.perf_counter()
        else:
            t_prefetch_done = time.perf_counter()

        logger.info(
            "[Perf] CategoriesListModel.set_categories count=%s sig=%.2f ms normalize=%.2f ms reset=%.2f ms prefetch/schedule=%.2f ms total=%.2f ms lazy=%s prefetch=%s prefetch_hits=%s pending=%s",
            len(self._items),
            (t_sig_done - t0) * 1000.0,
            (t_norm_done - t_sig_done) * 1000.0,
            (t_reset_done - t_norm_done) * 1000.0,
            (t_prefetch_done - t_reset_done) * 1000.0,
            (t_prefetch_done - t0) * 1000.0,
            self._lazy_icons_enabled,
            min(max(0, int(self._sync_prefetch_cap)), max(0, int(self._icon_prefetch))),
            sync_prefetched_hits,
            len(self._pending_icon_rows),
        )

    # --- helpers ---
    def find_row_by_id(self, category_id: int) -> int:
        # Use cache for O(1) lookup
        return self._row_by_id.get(category_id, -1)

    def _schedule_icon_loads_for_visible(self) -> None:
        if not self._lazy_icons_enabled:
            return
        if self._icon_timer is None:
            self._icon_timer = QTimer(self)
            self._icon_timer.setSingleShot(True)
            self._icon_timer.timeout.connect(self._process_icon_batch)
        # Schedule initial batch
        if not self._icon_timer.isActive():
            self._icon_timer.start(0)

    def _schedule_icon_row(self, row: int) -> None:
        if not self._lazy_icons_enabled:
            return
        if row in self._pending_icon_rows:
            return
        self._pending_icon_rows.add(row)
        if self._icon_timer is None:
            self._icon_timer = QTimer(self)
            self._icon_timer.setSingleShot(True)
            self._icon_timer.timeout.connect(self._process_icon_batch)
        if not self._icon_timer.isActive():
            self._icon_timer.start(0)

    def _process_icon_batch(self) -> None:
        if not self._pending_icon_rows:
            return
        batch = []
        for _ in range(min(self._icon_batch_size, len(self._pending_icon_rows))):
            batch.append(self._pending_icon_rows.pop())

        changed_rows: list[int] = []
        for row in batch:
            if row < 0 or row >= len(self._items):
                continue
            item = self._items[row]
            if isinstance(item.get("_icon"), QIcon):
                continue
            icon_path = item.get("icon_path", "") or ""
            icon = icon_loading_service.get_path_icon(icon_path, category=True)
            if icon.isNull():
                icon = DEFAULT_ICON
            item["_icon"] = icon
            item["_icon_pending"] = False
            changed_rows.append(row)

        if changed_rows:
            roles = [Qt.ItemDataRole.DecorationRole, Qt.ItemDataRole.UserRole + 1]
            for start, end in self._iter_contiguous_ranges(changed_rows):
                top = self.index(start, 0)
                bottom = self.index(end, 0)
                if top.isValid() and bottom.isValid():
                    self.dataChanged.emit(top, bottom, roles)

        if self._pending_icon_rows:
            self._icon_timer.start(0)

    @staticmethod
    def _iter_contiguous_ranges(rows: list[int]) -> list[tuple[int, int]]:
        if not rows:
            return []
        sorted_rows = sorted(set(rows))
        ranges: list[tuple[int, int]] = []
        start = sorted_rows[0]
        prev = start
        for row in sorted_rows[1:]:
            if row == prev + 1:
                prev = row
                continue
            ranges.append((start, prev))
            start = row
            prev = row
        ranges.append((start, prev))
        return ranges
