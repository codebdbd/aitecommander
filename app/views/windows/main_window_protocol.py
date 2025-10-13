from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class MainWindowProtocol(Protocol):
    """Subset of interactions required by controllers and menu builders."""

    tree: Any
    table: Any
    links_actions: Any
    links: Any
    structure: Any
    tiles: Any
    stack: Any
    settings: Any
    undo_action: Any
    redo_action: Any
    switch_sphere_action: Any
    structure_business: Any
    database_controller: Any

    def focusWidget(self) -> Any: ...
    def select_all_links(self) -> None: ...
    def edit_structure_item(self, item: Any) -> None: ...
    def add_new_category(self, *args: Any, **kwargs: Any) -> None: ...
    def add_new_section(self, *args: Any, **kwargs: Any) -> None: ...
    def update_statusbar(self) -> None: ...
    def get_link_at_row(self, row: int) -> dict[str, Any] | None: ...
    def get_current_category_id(self) -> int | None: ...
    def show_link_dialog_for_category(self, category_id: int | None) -> None: ...
