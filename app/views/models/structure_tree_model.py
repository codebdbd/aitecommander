from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable

from PyQt6.QtCore import (
    QAbstractItemModel,
    QMetaObject,
    QModelIndex,
    QRunnable,
    Qt,
    QThreadPool,
    pyqtSignal,
    pyqtSlot,
)
from PyQt6.QtGui import QIcon, QPixmap

from app.utils.ui.icon.icon_resolver import resolve_icon_path
from app.utils.ui.icon.validation import _validate_icon_name

NodeType = str  # "section" | "category" | "root"

logger = logging.getLogger(__name__)

if TYPE_CHECKING:  # pragma: no cover - imported for typing only
    from PyQt6.QtCore import QMimeData

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
        node: TreeNode,
        icon_path: str,
        on_loaded: Callable[[TreeNode, QIcon], None] | None = None,
        on_error: Callable[[TreeNode, str], None] | None = None,
    ) -> None:
        super().__init__()
        self.node = node
        self.icon_path = icon_path.strip()
        self._on_loaded = on_loaded
        self._on_error = on_error
        self.setAutoDelete(True)

        self.icon_loaded = None
        self.icon_error = None

    def run(self) -> None:  # pragma: no cover - executed in worker thread
        from app.utils.ui.qt.gui_exec import run_in_gui_thread_sync

        try:
            if not self.icon_path:
                raise ValueError("Icon path is empty")

            def _fetch_icon() -> QIcon:
                try:
                    from app.utils.ui.icon.icon_operations.cache_proxy import icon_cache

                    return icon_cache.get_icon(self.icon_path, source="tree_model_async")
                except Exception:
                    return QIcon()

            icon = run_in_gui_thread_sync(_fetch_icon)

            if self._on_loaded:
                run_in_gui_thread_sync(lambda: self._on_loaded(self.node, icon))
        except Exception as exc:
            logger.debug("Icon loading failed for %s: %s", self.icon_path, exc)
            if self._on_error:
                run_in_gui_thread_sync(lambda: self._on_error(self.node, str(exc)))

class _IconPreloadRunnable(QRunnable):
    """Фоновая предзагрузка набора иконок для заполнения кэша."""

    def __init__(self, icon_paths: set[str]) -> None:
        super().__init__()
        self._icon_paths = icon_paths
        self.setAutoDelete(True)

    def run(self) -> None:  # pragma: no cover - executed in worker thread
        try:
            from app.utils.ui.icon.icon_operations.cache_proxy import icon_cache
            from app.utils.ui.qt.gui_exec import run_in_gui_thread_sync
        except Exception:
            return

        for path in self._icon_paths:
            if not path:
                continue

            def _warmup() -> None:
                try:
                    icon_cache.get_icon(path, source="tree_preload")
                except Exception as exc:  # noqa: BLE001
                    logger.debug("Icon preload failed for %s: %s", path, exc)

            run_in_gui_thread_sync(_warmup)

class StructureTreeModel(QAbstractItemModel):
    """Hierarchical model for sections/categories structure."""

    icon_loaded = pyqtSignal(object, QIcon, name="iconLoaded")
    icon_failed = pyqtSignal(object, str, name="iconFailed")

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._root = TreeNode(type="root", id=None, name="root")
        self._section_by_id: dict[int, TreeNode] = {}
        self._category_by_id: dict[int, TreeNode] = {}
        self._placeholder_icon = self._create_placeholder_icon()

        self._thread_pool = QThreadPool(self)
        self._thread_pool.setMaxThreadCount(6)  # increase concurrency for icon loading
        try:
            self._thread_pool.setMaxThreadCount(4)
        except Exception as exc:
            logger.warning("Failed to set thread pool max count: %s", exc)

        self._active_icon_tasks: set[int] = set()
        self._active_icon_lock = threading.Lock()
        self._shutdown = False
        self._tree_snapshot_icons_ready = False
        self._tree_snapshot_icons_expected = 0
        self._tree_snapshot_icons_warmed = 0

    def _create_placeholder_icon(self) -> QIcon:
        """Create a transparent QIcon placeholder to reserve space in the tree."""
        try:
            from app.config_data import app_config

            size_cfg = app_config.ui.get_tree_icon_size()
            w = int(size_cfg[0]) if isinstance(size_cfg, (list, tuple)) and len(size_cfg) else 24
            h = int(size_cfg[1]) if isinstance(size_cfg, (list, tuple)) and len(size_cfg) > 1 else w
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

        if not self._is_theme_icon_path(trimmed):
            try:
                resolved_path = resolve_icon_path(trimmed)
            except Exception:
                logger.debug(
                    "StructureTreeModel._load_icon_immediately_if_safe: resolve_icon_path failed for %s",
                    trimmed,
                    exc_info=True,
                )
                resolved_path = ""
            if resolved_path:
                icon = QIcon(resolved_path)
                return icon if not icon.isNull() else None
            return None

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

    def columnCount(self, parent: QModelIndex | None = None) -> int:  # noqa: N802 (Qt API)
        return 1

    def rowCount(self, parent: QModelIndex | None = None) -> int:  # noqa: N802
        if parent is None:
            parent = QModelIndex()
        node = self._node_from_index(parent)
        return len(node.children)

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
                        resolved = resolve_icon_path(icon_path)
                        if resolved:
                            icon = QIcon(resolved)
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
        parent_index = self.createIndex(sec_node.row(), 0, sec_node)
        if row < 0:
            row = len(sec_node.children)
        count = len(categories or [])
        if count == 0:
            return

        self._preload_category_icons(categories)

        self.beginInsertRows(parent_index, row, row + count - 1)
        for i, c in enumerate(categories):
            icon, pending_path, stored_path = self._prepare_icon_fields(
                c.get("icon"),
                c.get("icon_path"),
            )
            if stored_path is not None:
                c["icon_path"] = stored_path

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
                if pending_path:
                    self._start_icon_loading(cat_node, pending_path)
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
        idx = self.index_for(item_type, int(item_id))
        if not idx.isValid():
            return
        node: TreeNode = idx.internalPointer()
        if "name" in data:
            node.name = str(data.get("name", node.name))
        if "icon" in data:
            icon = data.get("icon")
            if isinstance(icon, QIcon):
                node.icon = icon
                if isinstance(node.payload, dict) and "icon_path" in data:
                    node.payload["icon_path"] = data.get("icon_path")
            elif isinstance(icon, str):
                resolved_icon, pending_path, stored_path = self._prepare_icon_fields(
                    icon,
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
            else:
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
        for cid in list(category_ids or []):
            cat_node = self._category_by_id.get(int(cid))
            if not cat_node or not cat_node.parent:
                continue
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

    def move_category(
        self, category_id: int, new_section_id: int, new_row: int
    ) -> bool:
        cat_node = self._category_by_id.get(int(category_id))
        dst_parent = self._section_by_id.get(int(new_section_id))
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

    def set_snapshot(self, sections: list[dict[str, Any]]) -> None:
        """
        Full tree reload. The format for sections is a list[dict]:
        {
            "id": int,
            "name": str,
            "icon": Optional[QIcon],
            "categories": [ {"id": int, "name": str, "icon": Optional[QIcon]} ]
        }
        """
        self._tree_snapshot_icons_ready = False
        self._tree_snapshot_icons_expected = 0
        self._tree_snapshot_icons_warmed = 0
        self.beginResetModel()
        self._root.children.clear()
        self._section_by_id.clear()
        self._category_by_id.clear()

        for s in sections or []:

            icon_value = s.get("icon")
            if isinstance(icon_value, QIcon) and not icon_value.isNull():
                section_icon = icon_value
            else:
                icon_path = s.get("icon_path") or s.get("icon")
                if isinstance(icon_path, str) and icon_path.strip():
                    section_icon = self._load_icon_immediately_if_safe(icon_path.strip())
                    if section_icon is None:
                        section_icon = self._placeholder_icon
                else:
                    section_icon = self._placeholder_icon

            sec_node = TreeNode(
                type="section",
                id=_coerce_optional_int(s.get("id")),
                name=str(s.get("name", "")),
                parent=self._root,
                icon=section_icon,
                payload=s,
            )
            self._root.children.append(sec_node)
            if isinstance(sec_node.id, int):
                self._section_by_id[sec_node.id] = sec_node

            for c in s.get("categories") or []:
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
                        self._start_icon_loading(cat_node, pending_cat_path)

        self.endResetModel()

    @pyqtSlot(object, QIcon)
    def _on_icon_loaded(self, node: TreeNode, icon: QIcon) -> None:
        """Обработчик успешной загрузки иконки (вызывается в GUI-потоке)."""
        if self._shutdown:
            return
            
        with self._active_icon_lock:
            self._active_icon_tasks.discard(id(node))

        if node.parent is None:
            return
            
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
    def _on_icon_failed(self, node: TreeNode, _message: str) -> None:
        """Обработчик ошибки загрузки иконки (вызывается в GUI-потоке)."""
        if self._shutdown:
            return
            
        with self._active_icon_lock:
            self._active_icon_tasks.discard(id(node))

        self.icon_failed.emit(node, _message)

    def _start_icon_loading(self, node: TreeNode, icon_path: str | None) -> None:
        """Запускает асинхронную загрузку иконки для узла.
        
        Args:
            node: Узел дерева для которого загружается иконка
            icon_path: Путь к файлу иконки
        """
        if not isinstance(icon_path, str) or not icon_path.strip():
            return

        def on_loaded(n: TreeNode, ic: QIcon) -> None:
            self._on_icon_loaded(n, ic)

        def on_error(n: TreeNode, msg: str) -> None:
            self._on_icon_failed(n, msg)

        with self._active_icon_lock:

            if self._shutdown:
                return
                
            if id(node) in self._active_icon_tasks:
                return
            self._active_icon_tasks.add(id(node))

            loader = IconLoader(node, icon_path, on_loaded=on_loaded, on_error=on_error)
            try:
                self._thread_pool.start(loader)
            except Exception as exc:
                self._active_icon_tasks.discard(id(node))
                logger.debug("Failed to start icon loader: %s", exc)

    def cleanup(self) -> None:
        """Останавливает все активные задачи загрузки иконок.
        
        Используется при закрытии окна или удалении модели.
        Ожидает завершения всех активных задач (максимум 5 секунд).
        """
        self._shutdown = True
        with self._active_icon_lock:
            self._active_icon_tasks.clear()

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
