"""View-level sorting state controller for the links table."""

from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import Qt

from app.views.widgets.link.columns import LinkTableColumn, descriptor_for_column


@dataclass(frozen=True)
class LinkSortAction:
    """A table sort action requested by the sort controller."""

    column: int
    order: Qt.SortOrder
    show_indicator: bool = True
    persist_after_apply: bool = False


class LinkTableSortController:
    """Own the links table view-level sort state.

    The table currently has one intentional default: every normal category load
    starts from the saved user order (`Order ASC`). User header clicks can then
    sort another column without changing the default for the next category load.
    """

    def __init__(self) -> None:
        self._initialized = False
        self._allow_persist = False

    @staticmethod
    def default_sort() -> tuple[int, Qt.SortOrder]:
        """Return the default sort used for category loads."""
        return int(LinkTableColumn.ORDER), Qt.SortOrder.AscendingOrder

    def initial_sort(self, *, persist_after_apply: bool = False) -> LinkSortAction:
        """Return the startup sort action."""
        column, order = self.default_sort()
        return LinkSortAction(
            column,
            order,
            persist_after_apply=persist_after_apply,
        )

    def reset_for_category_load(self) -> None:
        """Force the next normal category populate to start from default order."""
        self._initialized = False
        self._allow_persist = False

    @staticmethod
    def should_apply_initial_sort_for_mode(mode: str) -> bool:
        """Return whether populate mode should apply the default initial sort."""
        return str(mode or "normal").lower() != "search"

    def ensure_initial_sort(self) -> LinkSortAction | None:
        """Return the initial sort action once per category load."""
        if self._initialized:
            return None
        self._initialized = True
        return self.initial_sort(persist_after_apply=True)

    def mark_action_applied(self, action: LinkSortAction) -> None:
        """Update controller state after the view applies a sort action."""
        if action.persist_after_apply:
            self._allow_persist = True

    def should_persist(self) -> bool:
        """Return whether current sort changes may be persisted."""
        return self._allow_persist

    def header_click_action(
        self,
        column: int,
        *,
        sorting_enabled: bool,
    ) -> LinkSortAction | None:
        """Return a manual header-click action when Qt sorting is disabled."""
        descriptor = descriptor_for_column(column)
        if descriptor is None or not descriptor.sortable:
            return None
        if sorting_enabled:
            return None
        return LinkSortAction(
            int(column),
            Qt.SortOrder.AscendingOrder,
            show_indicator=False,
            persist_after_apply=True,
        )

    def restore_after_populate_action(
        self,
        column: int,
        order: Qt.SortOrder,
        *,
        total_columns: int,
    ) -> LinkSortAction | None:
        """Return a restore action for a previously captured table sort."""
        if column < 0 or column >= total_columns:
            return None
        descriptor = descriptor_for_column(column)
        if descriptor is None or not descriptor.sortable:
            return None
        return LinkSortAction(
            int(column),
            Qt.SortOrder(order),
            persist_after_apply=False,
        )
