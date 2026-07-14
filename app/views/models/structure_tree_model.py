from __future__ import annotations

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable

from PyQt6.QtCore import (
    QAbstractItemModel,
    QCoreApplication,
    QModelIndex,
    QObject,
    QRunnable,
    Qt,
    QThread,
    QThreadPool,
    QTimer,
    pyqtSignal,
    pyqtSlot,
)
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtWidgets import QApplication

from app.config_data.runtime_config import (
    get_tree_icon_size,
    get_tree_section_icon_prewarm_limit,
)
from app.utils.ui.icon.loading_service import icon_loading_service
from app.utils.ui.icon.icon_resolver import resolve_icon_path, resolve_section_icon_path
from app.utils.ui.icon.validation import _validate_icon_name

NodeType = str  # "section" | "category" | "root"

logger = logging.getLogger(__name__)

if TYPE_CHECKING:  # pragma: no cover - imported for typing only
    from PyQt6.QtCore import QMimeData

_DISPATCHER = None


class _GuiCallbackDispatcher(QObject):
    invoke = pyqtSignal(object, object, object)

    def __init__(self) -> None:
        parent = QCoreApplication.instance()
        super().__init__(parent)
        self.invoke.connect(
            self._execute, Qt.ConnectionType.QueuedConnection  # type: ignore[arg-type]
        )

    @pyqtSlot(object, object, object)
    def _execute(
        self, callback: Callable[..., object], args: tuple, kwargs: dict
    ) -> None:
        try:
            callback(*args, **kwargs)
        except Exception as exc:
            logger.debug("GUI callback failed: %s", exc)


def _get_dispatcher() -> _GuiCallbackDispatcher | None:
    global _DISPATCHER
    if _DISPATCHER is not None:
        return _DISPATCHER
    app = QCoreApplication.instance()
    if app is None:
        return None
    if QThread.currentThread() != app.thread():
        return None
    _DISPATCHER = _GuiCallbackDispatcher()
    return _DISPATCHER


def _invoke_in_gui(callback: Callable[..., object] | None, *args) -> None:
    if callback is None:
        return
    dispatcher = _get_dispatcher()
    if dispatcher is None:
        callback(*args)
        return
    dispatcher.invoke.emit(callback, args, {})


def _coerce_optional_int(value: Any) -> int | None:
    """Return ``int(value)`` when the input can be safely coerced, else ``None``."""

    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, str)):
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
    return None

@dataclass(eq=False)
class TreeNode:
    type: NodeType
    id: int | None
    name: str = ""
    parent: TreeNode | None = None
    children: list[TreeNode] = field(default_factory=list)
    payload: dict[str, Any] = field(default_factory=dict)
    icon: QIcon | None = None
    children_populated: bool = True

    def row(self) -> int:
        if not self.parent:
            return 0
        try:
            return self.parent.children.index(self)
        except ValueError:
            return -1

    def __hash__(self) -> int:

        return id(self)

class IconLoader(QRunnable):
    """Фоновый загрузчик иконок для узлов дерева.
    
    Использует callback для потокобезопасной передачи результата в GUI-поток.
    """

    def __init__(
        self,
        icon_path: str,
        on_loaded: Callable[[str, QIcon], None] | None = None,
        on_error: Callable[[str, str], None] | None = None,
    ) -> None:
        super().__init__()
        self.icon_path = icon_path.strip()
        self._on_loaded = on_loaded
        self._on_error = on_error
        self.setAutoDelete(True)

    def run(self) -> None:  # pragma: no cover - executed in worker thread
        try:
            app = QApplication.instance()
            if app and app.closingDown():
                return
            if not self.icon_path:
                raise ValueError("Icon path is empty")

            try:
                resolved_path = icon_loading_service.resolve_path(self.icon_path)
            except Exception:
                logger.debug(
                    "IconLoader: failed to resolve path for %s",
                    self.icon_path,
                    exc_info=True,
                )
                resolved_path = ""

            def _run_in_gui() -> None:
                app_local = QApplication.instance()
                if app_local and app_local.closingDown():
                    return
                try:
                    icon = (
                        icon_loading_service.get_path_icon(resolved_path)
                        if resolved_path
                        else QIcon()
                    )
                except Exception:
                    icon = QIcon()

                if self._on_loaded:
                    self._on_loaded(self.icon_path, icon)

            _invoke_in_gui(_run_in_gui)
        except Exception as exc:
            logger.debug("Icon loading failed for %s: %s", self.icon_path, exc)
            if self._on_error:
                _invoke_in_gui(
                    lambda err=exc: self._on_error(self.icon_path, str(err))
                )

class _IconPreloadRunnable(QRunnable):
    """Best-effort batched icon warmup with a single GUI handoff."""

    def __init__(self, icon_paths: set[str]) -> None:
        super().__init__()
        self._icon_paths = icon_paths
        self.setAutoDelete(True)

    def run(self) -> None:  # pragma: no cover - executed in worker thread
        resolved_paths: list[str] = []
        for icon_path in self._icon_paths:
            if not icon_path:
                continue
            try:
                resolved = icon_loading_service.resolve_path(icon_path)
            except Exception:
                logger.debug("Icon preload resolve failed for %s", icon_path, exc_info=True)
                continue
            if resolved:
                resolved_paths.append(resolved)

        if not resolved_paths:
            return

        def _warmup_batch() -> None:
            for resolved in resolved_paths:
                try:
                    icon_loading_service.get_path_icon(resolved)
                except Exception as exc:  # noqa: BLE001
                    logger.debug("Icon preload failed for %s: %s", resolved, exc)

        _invoke_in_gui(_warmup_batch)

class StructureTreeModel(QAbstractItemModel):
    """Hierarchical model for sections/categories structure."""

    icon_loaded = pyqtSignal(object, QIcon, name="iconLoaded")
    icon_failed = pyqtSignal(object, str, name="iconFailed")

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        _get_dispatcher()
        self._root = TreeNode(type="root", id=None, name="root")
        self._section_by_id: dict[int, TreeNode] = {}
        self._category_by_id: dict[int, TreeNode] = {}
        self._placeholder_icon = self._create_placeholder_icon()

        self._thread_pool = QThreadPool(self)
        try:
            self._thread_pool.setMaxThreadCount(4)
        except Exception as exc:
            logger.warning("Failed to set thread pool max count: %s", exc)

        self._active_icon_tasks: set[str] = set()
        self._active_icon_lock = threading.Lock()
        self._icon_waiters_by_path: dict[str, list[TreeNode]] = {}
        self._shutdown = False
        self._snapshot_icon_load_token = 0
        self._tree_snapshot_icons_ready = False
        self._tree_snapshot_icons_expected = 0
        self._tree_snapshot_icons_warmed = 0
        self._deferred_categories_by_section: dict[int, list[dict[str, Any]]] = {}
        self._deferred_category_parent_by_id: dict[int, int] = {}

    def _create_placeholder_icon(self) -> QIcon:
        """Create a transparent QIcon placeholder to reserve space in the tree."""
        try:
            w, h = get_tree_icon_size()
        except Exception:
            w = h = 24
        pixmap = QPixmap(w, h)
        pixmap.fill(Qt.GlobalColor.transparent)
        return QIcon(pixmap)

    def _get_cached_icon(self, icon_ref: str | None) -> QIcon | None:
        """Return icon from cache if available without hitting disk."""
        if not isinstance(icon_ref, str):
            return None

        candidate = icon_ref.strip()
        if not candidate:
            return None

        try:
            from app.utils.ui.icon.cache_manager import get_icon as cache_get_icon
        except Exception:  # noqa: BLE001 - cache access must be optional
            return None

        is_absolute = (
            candidate.startswith(":/")
            or candidate.startswith("qrc:/")
            or "\\" in candidate
            or "/" in candidate
            or (len(candidate) > 2 and candidate[1] == ":" and candidate[2] in ("\\", "/"))
        )

        if is_absolute:
            shared_icon = icon_loading_service.peek_path_icon(candidate)
            if shared_icon is not None and not shared_icon.isNull():
                return shared_icon
            cache_key = f"abspath::{candidate}"
            icon = cache_get_icon(cache_key, "__abs__")
            return icon if icon is not None and not icon.isNull() else None

        normalized = candidate if "." in candidate else f"{candidate}.svg"
        try:
            from app.utils.ui.icon.path_service import get_current_theme
        except Exception:
            theme = "light"
        else:
            try:
                theme = get_current_theme()
            except Exception:
                theme = "light"

        icon = cache_get_icon(normalized, theme)
        return icon if icon is not None and not icon.isNull() else None

    @staticmethod
    def _is_theme_icon_path(candidate: str) -> bool:
        """Return True if icon path refers to a theme-relative or resource icon."""
        trimmed = candidate.strip()
        if not trimmed:
            return False

        if trimmed.startswith((":/", "qrc:/", "qresource:", "appres:")):
            return True

        lowered = trimmed.lower()
        if lowered.startswith(("file://", "http://", "https://")):
            return False

        if trimmed.startswith(("/", "\\")):
            return False

        if len(trimmed) > 1 and trimmed[1] == ":":
            return False
        return _validate_icon_name(trimmed)

    def _load_icon_immediately_if_safe(self, candidate: str) -> QIcon | None:
        """Try to resolve icon synchronously for lightweight theme-relative paths."""
        trimmed = candidate.strip()
        if not trimmed:
            return None

        is_absolute = (
            trimmed.startswith(":/")
            or trimmed.startswith("qrc:/")
            or trimmed.startswith("qresource:")
            or trimmed.startswith("/")
            or trimmed.startswith("\\")
            or (len(trimmed) > 2 and trimmed[1] == ":" and trimmed[2] in ("\\", "/"))
        )
        if is_absolute:
            icon = icon_loading_service.get_path_icon(trimmed)
            return icon if not icon.isNull() else None

        if not self._is_theme_icon_path(trimmed):
            try:
                icon = icon_loading_service.get_path_icon(trimmed)
            except Exception:
                logger.debug(
                    "StructureTreeModel._load_icon_immediately_if_safe: resolve/load failed for %s",
                    trimmed,
                    exc_info=True,
                )
                return None
            return icon if not icon.isNull() else None

        try:
            from app.utils.ui.icon.icon_operations.cache_proxy import icon_cache
        except Exception:
            logger.debug(
                "StructureTreeModel._load_icon_immediately_if_safe: icon cache unavailable",
                exc_info=True,
            )
            return None

        try:
            icon = icon_cache.get_icon(trimmed, source="tree_model_sync")
        except RuntimeError:

            return None
        except Exception:
            logger.debug(
                "StructureTreeModel._load_icon_immediately_if_safe: failed to load %s synchronously",
                trimmed,
                exc_info=True,
            )
            return None

        return icon if icon is not None and not icon.isNull() else None

    def _prepare_icon_fields(
        self,
        icon_value,
        icon_path_value,
    ) -> tuple[QIcon, str | None, str | None]:
        """Normalize QIcon/icon_path tuple and use cached icons when available."""
        icon_obj = (
            icon_value
            if isinstance(icon_value, QIcon) and not icon_value.isNull()
            else None
        )

        stored_path = None
        if isinstance(icon_path_value, str):
            stored_path = icon_path_value.strip() or None
        if stored_path is None and isinstance(icon_value, str):
            stored_path = icon_value.strip() or None

        pending_path: str | None = None
        if stored_path:
            if icon_obj is None:
                cached_icon = self._get_cached_icon(stored_path)
                if cached_icon is not None:
                    icon_obj = cached_icon
                else:
                    immediate_icon = self._load_icon_immediately_if_safe(stored_path)
                    if immediate_icon is not None:
                        icon_obj = immediate_icon
                    else:
                        pending_path = stored_path
            else:
                pending_path = None

        display_icon = icon_obj if icon_obj is not None else self._placeholder_icon
        return display_icon, pending_path, stored_path

    def _load_icon_sync_fallback(self, icon_path: str | None) -> QIcon | None:
        """Try a synchronous icon load for first-frame rendering.

        Used for section icons during snapshot application to avoid visual pop-in
        (text appears first, icon later). Falls back silently on any error.
        """
        if not isinstance(icon_path, str):
            return None
        candidate = icon_path.strip()
        if not candidate:
            return None
        try:
            from app.utils.ui.icon.icon_service import get_icon

            icon = get_icon(candidate, source="tree_model_sync_fallback")
            if isinstance(icon, QIcon) and not icon.isNull():
                return icon
        except Exception:
            logger.debug(
                "StructureTreeModel._load_icon_sync_fallback: failed for %s",
                candidate,
                exc_info=True,
            )
        return None

    def columnCount(self, parent: QModelIndex | None = None) -> int:  # noqa: N802 (Qt API)
        return 1

    def rowCount(self, parent: QModelIndex | None = None) -> int:  # noqa: N802
        if parent is None:
            parent = QModelIndex()
        node = self._node_from_index(parent)
        return len(node.children)

    def hasChildren(self, parent: QModelIndex | None = None) -> bool:  # noqa: N802
        if parent is None:
            parent = QModelIndex()
        node = self._node_from_index(parent)
        if node is self._root:
            return bool(self._root.children)
        if node.type == "section" and isinstance(node.id, int):
            if node.children:
                return True
            return bool(self._deferred_categories_by_section.get(node.id))
        return bool(node.children)

    def canFetchMore(self, parent: QModelIndex) -> bool:  # noqa: N802
        if not parent.isValid():
            return False
        node = self._node_from_index(parent)
        if node.type != "section" or not isinstance(node.id, int):
            return False
        return (not node.children_populated) and bool(
            self._deferred_categories_by_section.get(node.id)
        )

    def fetchMore(self, parent: QModelIndex) -> None:  # noqa: N802
        if not parent.isValid():
            return
        node = self._node_from_index(parent)
        if node.type != "section" or not isinstance(node.id, int):
            return
        self._populate_section_categories(node, parent)

    def index(
        self, row: int, column: int, parent: QModelIndex | None = None
    ) -> QModelIndex:  # noqa: N802
        if parent is None:
            parent = QModelIndex()
        if column != 0 or row < 0:
            return QModelIndex()
        parent_node = self._node_from_index(parent)
        if 0 <= row < len(parent_node.children):
            child = parent_node.children[row]
            return self.createIndex(row, 0, child)
        return QModelIndex()

    def parent(self, index: QModelIndex) -> QModelIndex:  # type: ignore[override]  # noqa: N802
        if not index.isValid():
            return QModelIndex()
        node: TreeNode = index.internalPointer()
        if not node.parent or node.parent is self._root:
            return QModelIndex()
        grand = node.parent.parent
        row = node.parent.row()
        if grand is None:
            row = node.parent.row()
        return self.createIndex(row, 0, node.parent)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:  # noqa: N802
        if not index.isValid():
            return None

        node: TreeNode = index.internalPointer()
        if node is None:
            return None

        if role == Qt.ItemDataRole.DisplayRole:
            return node.name
        if role == Qt.ItemDataRole.DecorationRole:
            return node.icon
        if role == Qt.ItemDataRole.UserRole:
            return (node.type, node.id)
        return None

    def setData(
        self, index: QModelIndex, value: Any, role: int = Qt.ItemDataRole.EditRole
    ) -> bool:  # noqa: N802
        if not index.isValid():
            return False

        node: TreeNode = index.internalPointer()
        if node is None:
            return False

        if role == Qt.ItemDataRole.EditRole:
            node.name = str(value)
            self.dataChanged.emit(index, index, [Qt.ItemDataRole.DisplayRole])
            return True

        if role == Qt.ItemDataRole.DecorationRole:
            if isinstance(value, QIcon):
                node.icon = value
                self.dataChanged.emit(index, index, [Qt.ItemDataRole.DecorationRole])
                return True
            if isinstance(value, str):
                self._start_icon_loading(node, value)
                return True

        return False

    def _preload_category_icons(self, categories: list[dict[str, Any]]) -> None:
        """Асинхронная предзагрузка иконок для новых категорий."""
        icon_paths: set[str] = set()
        for category in categories:
            icon_path = category.get("icon_path")
            if not icon_path and isinstance(category.get("icon"), str):
                icon_path = category["icon"]
            if isinstance(icon_path, str):
                trimmed = icon_path.strip()
                if trimmed and not any(sep in trimmed for sep in (":", "/", "\\")):
                    icon_paths.add(trimmed)

        if not icon_paths:
            return

        runnable = _IconPreloadRunnable(icon_paths)
        self._thread_pool.start(runnable)

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:  # noqa: N802
        if not index.isValid():
            return Qt.ItemFlag.ItemIsDropEnabled | Qt.ItemFlag.ItemIsEnabled
        node: TreeNode = index.internalPointer()
        flags = (
            Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsSelectable
            | Qt.ItemFlag.ItemIsDragEnabled
        )
        if node.type in ("root", "section"):
            flags |= Qt.ItemFlag.ItemIsDropEnabled
        return flags

    def supportedDropActions(self) -> Qt.DropAction:  # noqa: N802
        return Qt.DropAction.MoveAction | Qt.DropAction.CopyAction

    def mimeTypes(self) -> list[str]:  # noqa: N802
        return ["application/x-structure-tree-index"]

    def mimeData(self, indexes: list[QModelIndex]) -> QMimeData:  # type: ignore[override]  # noqa: N802
        import json

        from PyQt6.QtCore import QByteArray, QMimeData

        mime = QMimeData()
        payload = []
        for idx in indexes or []:
            if not idx or not idx.isValid() or idx.column() != 0:
                continue
            t = self.data(idx, Qt.ItemDataRole.UserRole)
            if isinstance(t, (tuple, list)) and len(t) == 2:
                payload.append([t[0], t[1]])
        try:
            ba = QByteArray(bytes(json.dumps(payload), encoding="utf-8"))
            mime.setData("application/x-structure-tree-index", ba)
        except Exception:
            pass
        return mime

    def dropMimeData(  # noqa: N802
        self,
        data,
        action: Qt.DropAction,
        row: int,
        column: int,
        parent: QModelIndex,
    ) -> bool:

        return False

    def insert_sections(self, row: int, sections: list[dict[str, Any]]) -> None:
        """Вставляет секции в указанную позицию.
        
        Args:
            row: Позиция для вставки (-1 для добавления в конец)
            sections: Список словарей с данными секций (id, name, icon, etc.)
        """
        if row < 0:
            row = len(self._root.children)
        count = len(sections or [])
        if count == 0:
            return

        prepared_sections = []
        for s in sections:
            icon_value = s.get("icon")
            if isinstance(icon_value, QIcon) and not icon_value.isNull():
                prepared_sections.append((s, icon_value))
                continue

            icon_path_raw = s.get("icon_path") or s.get("icon")
            if isinstance(icon_path_raw, str):
                icon_path = icon_path_raw.strip()
                if icon_path:
                    try:
                        icon = icon_loading_service.get_path_icon(icon_path)
                        if not icon.isNull():
                            prepared_sections.append((s, icon))
                            continue
                    except Exception:
                        pass

            prepared_sections.append((s, self._placeholder_icon))
        
        self.beginInsertRows(QModelIndex(), row, row + count - 1)
        for i, (s, icon) in enumerate(prepared_sections):
            sec_node = TreeNode(
                type="section",
                id=_coerce_optional_int(s.get("id")),
                name=str(s.get("name", "")),
                parent=self._root,
                icon=icon,
                payload=s,
            )
            self._root.children.insert(row + i, sec_node)
            if isinstance(sec_node.id, int):
                self._section_by_id[sec_node.id] = sec_node
        self.endInsertRows()

    def insert_categories(
        self, section_id: int, row: int, categories: list[dict[str, Any]]
    ) -> None:
        """Вставляет категории в указанную секцию.
        
        Args:
            section_id: ID секции, в которую вставляются категории
            row: Позиция для вставки (-1 для добавления в конец)
            categories: Список словарей с данными категорий (id, name, icon, etc.)
        """
        sec_node = self._section_by_id.get(int(section_id))
        if not sec_node:
            return
        if not sec_node.children_populated and isinstance(sec_node.id, int):
            deferred = self._deferred_categories_by_section.setdefault(sec_node.id, [])
            insert_at = len(deferred) if row < 0 else max(0, min(int(row), len(deferred)))
            for i, c in enumerate(categories or []):
                if not isinstance(c, dict):
                    continue
                deferred.insert(insert_at + i, c)
                cat_id = _coerce_optional_int(c.get("id"))
                if isinstance(cat_id, int):
                    self._deferred_category_parent_by_id[cat_id] = sec_node.id
            return
        parent_index = self.createIndex(sec_node.row(), 0, sec_node)
        if row < 0:
            row = len(sec_node.children)
        count = len(categories or [])
        if count == 0:
            return

        self.beginInsertRows(parent_index, row, row + count - 1)
        for i, c in enumerate(categories):
            icon_value = c.get("icon")
            if isinstance(icon_value, QIcon) and not icon_value.isNull():
                icon = icon_value
            else:
                icon_path_raw = c.get("icon_path") or c.get("icon")
                if isinstance(icon_path_raw, str):
                    icon_path = icon_path_raw.strip()
                    if icon_path:
                        try:
                            icon = icon_loading_service.get_path_icon(icon_path)
                            if icon.isNull():
                                icon = self._placeholder_icon
                        except Exception:
                            icon = self._placeholder_icon
                    else:
                        icon = self._placeholder_icon
                else:
                    icon = self._placeholder_icon

            cat_node = TreeNode(
                type="category",
                id=_coerce_optional_int(c.get("id")),
                name=str(c.get("name", "")),
                parent=sec_node,
                icon=icon,
                payload=c,
            )
            sec_node.children.insert(row + i, cat_node)
            if isinstance(cat_node.id, int):
                self._category_by_id[cat_node.id] = cat_node
        self.endInsertRows()

    def update_item(
        self, item_type: NodeType, item_id: int, data: dict[str, Any]
    ) -> None:
        """Обновляет данные элемента дерева.
        
        Args:
            item_type: Тип элемента ('section' или 'category')
            item_id: ID элемента
            data: Словарь с обновляемыми полями (name, icon, etc.)
        """
        if item_type == "category" and int(item_id) not in self._category_by_id:
            parent_sid = self._deferred_category_parent_by_id.get(int(item_id))
            if isinstance(parent_sid, int):
                deferred = self._deferred_categories_by_section.get(parent_sid) or []
                for c in deferred:
                    if isinstance(c, dict) and _coerce_optional_int(c.get("id")) == int(item_id):
                        c.update(data or {})
                        break

        idx = self.index_for(item_type, int(item_id))
        if not idx.isValid():
            return
        node: TreeNode = idx.internalPointer()
        if "name" in data:
            node.name = str(data.get("name", node.name))
        icon_value = data.get("icon") if "icon" in data else None
        if "icon" in data or "icon_path" in data:
            if isinstance(icon_value, QIcon):
                node.icon = icon_value
                if isinstance(node.payload, dict) and "icon_path" in data:
                    node.payload["icon_path"] = data.get("icon_path")
            else:
                icon_source = (
                    icon_value if isinstance(icon_value, str) else data.get("icon_path")
                )
                resolved_icon, pending_path, stored_path = self._prepare_icon_fields(
                    icon_source,
                    data.get("icon_path"),
                )
                node.icon = resolved_icon
                if isinstance(node.payload, dict):
                    if stored_path is not None:
                        node.payload["icon_path"] = stored_path
                    elif "icon_path" in node.payload:
                        node.payload["icon_path"] = stored_path
                if pending_path:
                    self._start_icon_loading(node, pending_path)
                elif icon_source is None and "icon" in data:
                    node.icon = self._placeholder_icon
        if data:
            node.payload.update(data)
        self.dataChanged.emit(
            idx,
            idx,
            [
                Qt.ItemDataRole.DisplayRole,
                Qt.ItemDataRole.DecorationRole,
                Qt.ItemDataRole.UserRole,
            ],
        )

    def remove_sections(self, section_ids: list[int]) -> None:
        for sec_id in list(section_ids or []):
            sec_node = self._section_by_id.get(int(sec_id))
            if not sec_node:
                continue
            row = sec_node.row()
            self.beginRemoveRows(QModelIndex(), row, row)
            for cat in sec_node.children:
                if isinstance(cat.id, int) and cat.id in self._category_by_id:
                    del self._category_by_id[cat.id]
            self._root.children.pop(row)
            if isinstance(sec_id, int) and sec_id in self._section_by_id:
                del self._section_by_id[sec_id]
            self.endRemoveRows()

    def remove_categories(self, category_ids: list[int]) -> None:
        by_parent: dict[TreeNode, list[TreeNode]] = {}
        affected_section_ids: set[int] = set()
        for cid in list(category_ids or []):
            cat_id = int(cid)
            cat_node = self._category_by_id.get(cat_id)
            if not cat_node or not cat_node.parent:
                parent_sid = self._deferred_category_parent_by_id.pop(cat_id, None)
                if isinstance(parent_sid, int):
                    affected_section_ids.add(parent_sid)
                    sec_node = self._section_by_id.get(parent_sid)
                    if (
                        sec_node is not None
                        and isinstance(sec_node.payload, dict)
                        and isinstance(sec_node.payload.get("categories"), list)
                    ):
                        sec_node.payload["categories"] = [
                            c
                            for c in sec_node.payload.get("categories") or []
                            if not (
                                isinstance(c, dict)
                                and _coerce_optional_int(c.get("id")) == cat_id
                            )
                        ]
                    deferred = self._deferred_categories_by_section.get(parent_sid)
                    if deferred is not None:
                        self._deferred_categories_by_section[parent_sid] = [
                            c
                            for c in deferred
                            if not (
                                isinstance(c, dict)
                                and _coerce_optional_int(c.get("id")) == cat_id
                            )
                        ]
                continue
            if isinstance(cat_node.parent.id, int):
                affected_section_ids.add(int(cat_node.parent.id))
                if (
                    isinstance(cat_node.parent.payload, dict)
                    and isinstance(cat_node.parent.payload.get("categories"), list)
                ):
                    cat_node.parent.payload["categories"] = [
                        c
                        for c in cat_node.parent.payload.get("categories") or []
                        if not (
                            isinstance(c, dict)
                            and _coerce_optional_int(c.get("id")) == cat_id
                        )
                    ]
            by_parent.setdefault(cat_node.parent, []).append(cat_node)
        for parent_node, cats in by_parent.items():
            cats_sorted = sorted(cats, key=lambda n: n.row())
            for node in reversed(cats_sorted):
                parent_index = (
                    QModelIndex()
                    if parent_node is self._root
                    else self.createIndex(parent_node.row(), 0, parent_node)
                )
                row = node.row()
                self.beginRemoveRows(parent_index, row, row)
                parent_node.children.pop(row)
                if isinstance(node.id, int) and node.id in self._category_by_id:
                    del self._category_by_id[node.id]
                self.endRemoveRows()
        for section_id in sorted(affected_section_ids):
            sec_node = self._section_by_id.get(section_id)
            if sec_node is None:
                continue
            sec_index = self.createIndex(sec_node.row(), 0, sec_node)
            if sec_index.isValid():
                self.dataChanged.emit(
                    sec_index,
                    sec_index,
                    [
                        Qt.ItemDataRole.DisplayRole,
                        Qt.ItemDataRole.DecorationRole,
                        Qt.ItemDataRole.UserRole,
                    ],
                )

    def section_ids_for_categories(self, category_ids: list[int]) -> list[int]:
        section_ids: set[int] = set()
        for raw_id in list(category_ids or []):
            try:
                cat_id = int(raw_id)
            except Exception:
                continue
            cat_node = self._category_by_id.get(cat_id)
            if cat_node is not None and isinstance(getattr(cat_node.parent, "id", None), int):
                section_ids.add(int(cat_node.parent.id))
                continue
            parent_sid = self._deferred_category_parent_by_id.get(cat_id)
            if isinstance(parent_sid, int):
                section_ids.add(parent_sid)
        return sorted(section_ids)

    def replace_section_categories(
        self, section_id: int, categories: list[dict[str, Any]]
    ) -> None:
        """Replace section children with optional deferred materialization for large sets."""
        sec_node = self._section_by_id.get(int(section_id))
        if sec_node is None or not isinstance(sec_node.id, int):
            return

        incoming = [c for c in (categories or []) if isinstance(c, dict)]
        # Large restores should avoid materializing all child nodes in one GUI slice.
        defer_threshold = 64
        was_populated = bool(getattr(sec_node, "children_populated", True))

        parent_index = self.createIndex(sec_node.row(), 0, sec_node)
        if sec_node.children:
            self.beginRemoveRows(parent_index, 0, len(sec_node.children) - 1)
            try:
                for node in sec_node.children:
                    if isinstance(node.id, int):
                        self._category_by_id.pop(node.id, None)
                sec_node.children.clear()
            finally:
                self.endRemoveRows()

        # Clear stale deferred ids for this parent before replacing payload.
        stale_deferred = self._deferred_categories_by_section.pop(sec_node.id, None) or []
        for payload in stale_deferred:
            if isinstance(payload, dict):
                cat_id = _coerce_optional_int(payload.get("id"))
                if isinstance(cat_id, int):
                    self._deferred_category_parent_by_id.pop(cat_id, None)

        if len(incoming) >= defer_threshold and not was_populated:
            sec_node.children_populated = False
            self._deferred_categories_by_section[sec_node.id] = incoming
            for payload in incoming:
                cat_id = _coerce_optional_int(payload.get("id"))
                if isinstance(cat_id, int):
                    self._deferred_category_parent_by_id[cat_id] = sec_node.id
            return

        sec_node.children_populated = True
        if incoming:
            self.insert_categories(int(section_id), 0, incoming)

    def move_category(
        self, category_id: int, new_section_id: int, new_row: int
    ) -> bool:
        cat_node = self._category_by_id.get(int(category_id))
        dst_parent = self._section_by_id.get(int(new_section_id))
        if cat_node is None:
            src_sid = self._deferred_category_parent_by_id.get(int(category_id))
            if isinstance(src_sid, int):
                src_node = self._section_by_id.get(src_sid)
                if src_node is not None and not src_node.children_populated:
                    src_idx = self.createIndex(src_node.row(), 0, src_node)
                    self._populate_section_categories(src_node, src_idx)
                    cat_node = self._category_by_id.get(int(category_id))
        if not cat_node or not dst_parent:
            return False
        src_parent = cat_node.parent
        if not src_parent:
            return False
        if new_row < 0:
            new_row = len(dst_parent.children)
        src_parent_index = (
            QModelIndex()
            if src_parent is self._root
            else self.createIndex(src_parent.row(), 0, src_parent)
        )
        dst_parent_index = (
            QModelIndex()
            if dst_parent is self._root
            else self.createIndex(dst_parent.row(), 0, dst_parent)
        )
        src_row = cat_node.row()
        if src_parent is dst_parent and new_row > src_row:
            new_row -= 1
        if not self.beginMoveRows(
            src_parent_index, src_row, src_row, dst_parent_index, new_row
        ):
            return False
        src_parent.children.pop(src_row)
        cat_node.parent = dst_parent
        dst_parent.children.insert(new_row, cat_node)
        self.endMoveRows()
        return True

    def set_snapshot(
        self,
        sections: list[dict[str, Any]],
        *,
        sections_first: bool = False,
        defer_category_icon_loads: bool = True,
        allow_sync_section_fallback: bool = True,
    ) -> None:
        """
        Full tree reload. The format for sections is a list[dict]:
        {
            "id": int,
            "name": str,
            "icon": Optional[QIcon],
            "categories": [ {"id": int, "name": str, "icon": Optional[QIcon]} ]
        }
        """
        perf_t0 = time.perf_counter()
        sections_count = len(sections or [])
        categories_count = 0
        try:
            categories_count = sum(
                len(s.get("categories") or [])
                for s in (sections or [])
                if isinstance(s, dict)
            )
        except Exception:
            categories_count = -1

        sync_fallback_count = 0
        sync_fallback_hits = 0
        sync_fallback_ms = 0.0
        async_section_icon_loads = 0
        async_category_icon_loads = 0
        deferred_category_icon_loads: list[tuple[TreeNode, str]] = []

        self._tree_snapshot_icons_ready = False
        self._tree_snapshot_icons_expected = 0
        self._tree_snapshot_icons_warmed = 0
        self._deferred_categories_by_section.clear()
        self._deferred_category_parent_by_id.clear()
        self.beginResetModel()
        self._root.children.clear()
        self._section_by_id.clear()
        self._category_by_id.clear()

        try:
            section_sync_icon_limit = get_tree_section_icon_prewarm_limit(6)
        except Exception:
            section_sync_icon_limit = 6
        for section_row, s in enumerate(sections or []):
            # Resolve section icon with type-specific fallback (section.png)
            raw_icon_path = s.get("icon_path") or ""
            resolved_section_path = resolve_section_icon_path(raw_icon_path) if raw_icon_path else ""
            section_icon, pending_section_path, stored_section_path = (
                self._prepare_icon_fields(
                    s.get("icon"),
                    resolved_section_path or raw_icon_path,
                )
            )
            if stored_section_path is not None:
                s["icon_path"] = stored_section_path
            if (
                allow_sync_section_fallback
                and pending_section_path
                and section_row < section_sync_icon_limit
            ):
                # Sections are few; sync fallback keeps first paint visually stable.
                sync_fallback_count += 1
                _fb_t0 = time.perf_counter()
                sync_icon = self._load_icon_sync_fallback(pending_section_path)
                sync_fallback_ms += (time.perf_counter() - _fb_t0) * 1000.0
                if sync_icon is not None:
                    sync_fallback_hits += 1
                    section_icon = sync_icon
                    pending_section_path = None

            sec_node = TreeNode(
                type="section",
                id=_coerce_optional_int(s.get("id")),
                name=str(s.get("name", "")),
                parent=self._root,
                icon=section_icon,
                payload=s,
            )
            sec_node.children_populated = not bool(sections_first and (s.get("categories") or []))
            self._root.children.append(sec_node)
            if isinstance(sec_node.id, int):
                self._section_by_id[sec_node.id] = sec_node
            if pending_section_path:
                async_section_icon_loads += 1
                self._start_icon_loading(sec_node, pending_section_path)

            section_categories = list(s.get("categories") or [])
            if sections_first and isinstance(sec_node.id, int) and section_categories:
                self._deferred_categories_by_section[sec_node.id] = section_categories
                for c in section_categories:
                    cat_id = _coerce_optional_int(c.get("id")) if isinstance(c, dict) else None
                    if isinstance(cat_id, int):
                        self._deferred_category_parent_by_id[cat_id] = sec_node.id
                continue

            for c in section_categories:
                category_icon, pending_cat_path, stored_cat_path = self._prepare_icon_fields(
                    c.get("icon"),
                    c.get("icon_path"),
                )
                if stored_cat_path is not None:
                    c["icon_path"] = stored_cat_path

                cat_node = TreeNode(
                    type="category",
                    id=_coerce_optional_int(c.get("id")),
                    name=str(c.get("name", "")),
                    parent=sec_node,
                    icon=category_icon,
                    payload=c,
                )
                sec_node.children.append(cat_node)
                if isinstance(cat_node.id, int):
                    self._category_by_id[cat_node.id] = cat_node
                    if pending_cat_path:
                        async_category_icon_loads += 1
                        if defer_category_icon_loads:
                            deferred_category_icon_loads.append((cat_node, pending_cat_path))
                        else:
                            self._start_icon_loading(cat_node, pending_cat_path)

        self.endResetModel()
        if deferred_category_icon_loads:
            self._schedule_snapshot_icon_loads(deferred_category_icon_loads)
        perf_t1 = time.perf_counter()
        logger.info(
            "[Perf] StructureTreeModel.set_snapshot sections=%s categories=%s total=%.2fms sync_section_fallback=%d hits=%d sync_fallback_ms=%.2fms async_section_icon_loads=%d async_category_icon_loads=%d",
            sections_count,
            categories_count,
            (perf_t1 - perf_t0) * 1000.0,
            sync_fallback_count,
            sync_fallback_hits,
            sync_fallback_ms,
            async_section_icon_loads,
            async_category_icon_loads,
        )

    def _populate_section_categories(
        self,
        sec_node: TreeNode,
        parent_index: QModelIndex | None = None,
    ) -> None:
        if sec_node.type != "section" or not isinstance(sec_node.id, int):
            return
        if sec_node.children_populated:
            return
        raw_categories = self._deferred_categories_by_section.pop(sec_node.id, None) or []
        sec_node.children_populated = True
        if not raw_categories:
            return

        if parent_index is None or not parent_index.isValid():
            parent_index = self.createIndex(sec_node.row(), 0, sec_node)

        deferred_category_icon_loads: list[tuple[TreeNode, str]] = []
        start_row = len(sec_node.children)
        end_row = start_row + len(raw_categories) - 1
        self.beginInsertRows(parent_index, start_row, end_row)
        try:
            for c in raw_categories:
                if not isinstance(c, dict):
                    continue
                category_icon, pending_cat_path, stored_cat_path = self._prepare_icon_fields(
                    c.get("icon"),
                    c.get("icon_path"),
                )
                if stored_cat_path is not None:
                    c["icon_path"] = stored_cat_path

                cat_node = TreeNode(
                    type="category",
                    id=_coerce_optional_int(c.get("id")),
                    name=str(c.get("name", "")),
                    parent=sec_node,
                    icon=category_icon,
                    payload=c,
                )
                sec_node.children.append(cat_node)
                if isinstance(cat_node.id, int):
                    self._category_by_id[cat_node.id] = cat_node
                    self._deferred_category_parent_by_id.pop(cat_node.id, None)
                    if pending_cat_path:
                        deferred_category_icon_loads.append((cat_node, pending_cat_path))
        finally:
            self.endInsertRows()

        if deferred_category_icon_loads:
            self._schedule_snapshot_icon_loads(deferred_category_icon_loads)

    def populate_section_categories_by_id(self, section_id: int) -> bool:
        """Materialize deferred categories for a section if they were loaded lazily."""
        sec_node = self._section_by_id.get(int(section_id))
        if sec_node is None:
            return False
        if sec_node.children_populated:
            return False
        sec_idx = self.createIndex(sec_node.row(), 0, sec_node)
        self._populate_section_categories(sec_node, sec_idx)
        return True

    def populate_for_selection(self, item_type: str, item_id: int) -> bool:
        """Materialize section children needed to restore/select an item."""
        if item_type == "section":
            return self.populate_section_categories_by_id(int(item_id))
        if item_type == "category":
            parent_sid = self._deferred_category_parent_by_id.get(int(item_id))
            if isinstance(parent_sid, int):
                return self.populate_section_categories_by_id(parent_sid)
        return False

    def populate_first_section_if_deferred(self) -> bool:
        """Materialize first section children for first-item auto-select path."""
        if not self._root.children:
            return False
        first = self._root.children[0]
        if first.type != "section" or not isinstance(first.id, int):
            return False
        return self.populate_section_categories_by_id(first.id)

    def _schedule_snapshot_icon_loads(
        self,
        pending_loads: list[tuple["TreeNode", str]],
        *,
        chunk_size: int = 16,
        initial_delay_ms: int = 25,
    ) -> None:
        """Start category icon loaders after model reset in small GUI slices."""
        if not pending_loads or self._shutdown:
            return
        try:
            self._snapshot_icon_load_token += 1
            token = int(self._snapshot_icon_load_token)
        except Exception:
            token = 0

        queue = deque(pending_loads)

        def _run_chunk() -> None:
            if self._shutdown:
                return
            try:
                if token and token != getattr(self, "_snapshot_icon_load_token", 0):
                    return
            except Exception:
                pass

            processed = 0
            while queue and processed < max(1, int(chunk_size)):
                node, icon_path = queue.popleft()
                try:
                    self._start_icon_loading(node, icon_path)
                except Exception:
                    logger.debug("Failed to start deferred snapshot icon load", exc_info=True)
                processed += 1

            if queue:
                try:
                    QTimer.singleShot(0, _run_chunk)
                except Exception:
                    _run_chunk()

        try:
            # Let deferred first-selection/tiles work run first; icon loads are visual polish.
            QTimer.singleShot(max(0, int(initial_delay_ms)), _run_chunk)
        except Exception:
            _run_chunk()

    @pyqtSlot(object, QIcon)
    def _on_icon_loaded(self, icon_path: str, icon: QIcon) -> None:
        """Обработчик успешной загрузки иконки (вызывается в GUI-потоке)."""
        if self._shutdown:
            return

        with self._active_icon_lock:
            waiters = self._icon_waiters_by_path.pop(icon_path, [])
            self._active_icon_tasks.discard(icon_path)

        for node in waiters:
            if node.parent is None:
                continue

            node.icon = icon

            try:
                row = node.parent.children.index(node)
                idx = self.createIndex(row, 0, node)
                if idx.isValid():
                    self.dataChanged.emit(idx, idx, [Qt.ItemDataRole.DecorationRole])
            except (ValueError, AttributeError):
                pass

            self.icon_loaded.emit(node, icon)

    @pyqtSlot(object, str)
    def _on_icon_failed(self, icon_path: str, _message: str) -> None:
        """Обработчик ошибки загрузки иконки (вызывается в GUI-потоке)."""
        if self._shutdown:
            return

        with self._active_icon_lock:
            waiters = self._icon_waiters_by_path.pop(icon_path, [])
            self._active_icon_tasks.discard(icon_path)

        for node in waiters:
            self.icon_failed.emit(node, _message)

    def _start_icon_loading(self, node: TreeNode, icon_path: str | None) -> None:
        """Запускает асинхронную загрузку иконки для узла.
        
        Args:
            node: Узел дерева для которого загружается иконка
            icon_path: Путь к файлу иконки
        """
        if not isinstance(icon_path, str) or not icon_path.strip():
            return

        def on_loaded(path: str, ic: QIcon) -> None:
            self._on_icon_loaded(path, ic)

        def on_error(path: str, msg: str) -> None:
            self._on_icon_failed(path, msg)

        normalized_path = icon_path.strip()

        with self._active_icon_lock:

            if self._shutdown:
                return

            waiters = self._icon_waiters_by_path.setdefault(normalized_path, [])
            if node not in waiters:
                waiters.append(node)

            if normalized_path in self._active_icon_tasks:
                return
            self._active_icon_tasks.add(normalized_path)

            loader = IconLoader(normalized_path, on_loaded=on_loaded, on_error=on_error)
            try:
                self._thread_pool.start(loader)
            except Exception as exc:
                self._active_icon_tasks.discard(normalized_path)
                self._icon_waiters_by_path.pop(normalized_path, None)
                logger.debug("Failed to start icon loader: %s", exc)

    def cleanup(self) -> None:
        """Останавливает все активные задачи загрузки иконок.
        
        Используется при закрытии окна или удалении модели.
        Ожидает завершения всех активных задач (максимум 5 секунд).
        """
        self._shutdown = True
        with self._active_icon_lock:
            self._active_icon_tasks.clear()
            self._icon_waiters_by_path.clear()

        if self._thread_pool:
            self._thread_pool.waitForDone(5000)

    def index_for(self, item_type: str, item_id: int) -> QModelIndex:
        """Возвращает QModelIndex для элемента по его типу и ID.
        
        Args:
            item_type: Тип элемента ('section' или 'category')
            item_id: ID элемента
            
        Returns:
            QModelIndex элемента или невалидный индекс если не найден
        """
        if item_type == "section":
            node = self._section_by_id.get(int(item_id))
            if node:
                return self.createIndex(node.row(), 0, node)
            return QModelIndex()
        if item_type == "category":
            node = self._category_by_id.get(int(item_id))
            if node is None:
                parent_section_id = self._deferred_category_parent_by_id.get(int(item_id))
                if isinstance(parent_section_id, int):
                    sec_node = self._section_by_id.get(parent_section_id)
                    if sec_node is not None:
                        sec_idx = self.createIndex(sec_node.row(), 0, sec_node)
                        self._populate_section_categories(sec_node, sec_idx)
                        node = self._category_by_id.get(int(item_id))
            if node:
                return self.createIndex(node.row(), 0, node)
            return QModelIndex()
        return QModelIndex()

    def _node_from_index(self, index: QModelIndex) -> TreeNode:
        if index.isValid():
            node = index.internalPointer()
            if isinstance(node, TreeNode):
                return node
        return self._root

