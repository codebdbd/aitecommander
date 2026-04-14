from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol, TypedDict, runtime_checkable

from PyQt6.QtCore import QModelIndex, pyqtBoundSignal


class TopPanelActionData(TypedDict, total=False):
    """Payload for unified actions from top panels."""

    type: str
    link: dict[str, Any]
    link_type: str
    category_id: int


@runtime_checkable
class SupportsSetData(Protocol):
    def set_data(self, items: Sequence[dict[str, Any]]) -> None: ...


@runtime_checkable
class SupportsUpdateData(Protocol):
    def update_data(
        self,
        items: Sequence[dict[str, Any]],
        options: dict[str, Any] | None = None,
    ) -> bool: ...


@runtime_checkable
class SupportsSetFavorites(Protocol):
    def set_favorites(self, items: Sequence[dict[str, Any]]) -> None: ...


@runtime_checkable
class SupportsSetRecentLinks(Protocol):
    def set_recent_links(self, items: Sequence[dict[str, Any]]) -> None: ...


@runtime_checkable
class SupportsGetLimit(Protocol):
    def get_limit(self) -> int: ...


@runtime_checkable
class SupportsCancelUpdate(Protocol):
    def cancel_update(self) -> bool: ...


@runtime_checkable
class CategoryTilesControllerProtocol(Protocol):
    def refresh(self, section_id: int, *, switch_view: bool = True) -> None: ...

    def clear(self) -> None: ...


@runtime_checkable
class LinksTableControllerProtocol(Protocol):
    def reload(self, category_id: int) -> None: ...


@runtime_checkable
class UIStateManagerProtocol(Protocol):
    def load_category(self, category_id: int, *args, **kwargs) -> None: ...


@runtime_checkable
class StructureTreeModelProtocol(Protocol):
    def set_snapshot(
        self,
        snapshot: Sequence[dict[str, Any]],
        *,
        sections_first: bool = False,
        defer_category_icon_loads: bool = True,
        allow_sync_section_fallback: bool = True,
    ) -> None: ...

    def insert_sections(self, row: int, sections: Sequence[dict[str, Any]]) -> None: ...

    def insert_categories(
        self, parent_id: int, row: int, categories: Sequence[dict[str, Any]]
    ) -> None: ...

    def update_item(
        self, item_type: str, item_id: int, data: dict[str, Any]
    ) -> None: ...

    def remove_sections(self, section_ids: Sequence[int]) -> None: ...

    def remove_categories(self, category_ids: Sequence[int]) -> None: ...

    def index_for(self, item_type: str, item_id: int) -> QModelIndex | None: ...

    def rowCount(self, parent: QModelIndex | None = None) -> int: ...

    def index(
        self, row: int, column: int, parent: QModelIndex | None = None
    ) -> QModelIndex: ...

    def data(self, index: QModelIndex, role: int = 0) -> Any: ...

    def setData(self, index: QModelIndex, value: Any, role: int = 0) -> bool: ...


@runtime_checkable
class LinksBusinessProtocol(Protocol):
    favorite_links_loaded: pyqtBoundSignal
    recent_links_loaded: pyqtBoundSignal
    favorites_cleared: pyqtBoundSignal

    def load_favorite_links(self) -> None: ...

    def load_recent_links(self, limit: int) -> None: ...

    def get_favorite_links(self) -> list[dict[str, Any]]: ...

    def get_recent_links(self, limit: int) -> list[dict[str, Any]]: ...

    def clear_favorites(self) -> None: ...

    def clear_favorites_async(self) -> None: ...


@runtime_checkable
class MainWindowProtocol(Protocol):
    top_panels_controller: Any
    menu_controller: Any

    def update_theme(self) -> None: ...
