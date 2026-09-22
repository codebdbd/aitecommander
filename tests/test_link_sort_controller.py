from __future__ import annotations

from PyQt6.QtCore import Qt

from app.views.widgets.link.columns import LinkTableColumn
from app.views.widgets.link.sort_controller import LinkTableSortController


def test_default_sort_is_order_ascending() -> None:
    column, order = LinkTableSortController.default_sort()

    assert column == int(LinkTableColumn.ORDER)
    assert order == Qt.SortOrder.AscendingOrder


def test_initial_sort_runs_once_until_category_reset() -> None:
    controller = LinkTableSortController()

    first = controller.ensure_initial_sort()
    second = controller.ensure_initial_sort()
    controller.reset_for_category_load()
    third = controller.ensure_initial_sort()

    assert first is not None
    assert first.column == int(LinkTableColumn.ORDER)
    assert first.persist_after_apply
    assert second is None
    assert third is not None


def test_persist_is_allowed_only_after_marking_initial_action_applied() -> None:
    controller = LinkTableSortController()
    action = controller.ensure_initial_sort()

    assert action is not None
    assert not controller.should_persist()

    controller.mark_action_applied(action)

    assert controller.should_persist()


def test_reset_for_category_load_disables_persist_until_sort_reapplied() -> None:
    controller = LinkTableSortController()
    action = controller.ensure_initial_sort()
    assert action is not None
    controller.mark_action_applied(action)
    assert controller.should_persist()

    controller.reset_for_category_load()

    assert not controller.should_persist()


def test_header_click_action_only_runs_when_qt_sorting_is_disabled() -> None:
    controller = LinkTableSortController()

    assert (
        controller.header_click_action(
            int(LinkTableColumn.NAME),
            sorting_enabled=True,
        )
        is None
    )

    action = controller.header_click_action(
        int(LinkTableColumn.NAME),
        sorting_enabled=False,
    )

    assert action is not None
    assert action.column == int(LinkTableColumn.NAME)
    assert action.order == Qt.SortOrder.AscendingOrder
    assert not action.show_indicator


def test_header_click_ignores_unsortable_group_launch_column() -> None:
    controller = LinkTableSortController()

    assert (
        controller.header_click_action(
            int(LinkTableColumn.GROUP_LAUNCH),
            sorting_enabled=False,
        )
        is None
    )


def test_search_mode_does_not_request_initial_default_sort() -> None:
    assert LinkTableSortController.should_apply_initial_sort_for_mode("normal")
    assert LinkTableSortController.should_apply_initial_sort_for_mode("default")
    assert not LinkTableSortController.should_apply_initial_sort_for_mode("search")


def test_restore_after_populate_validates_sortable_column_bounds() -> None:
    controller = LinkTableSortController()

    action = controller.restore_after_populate_action(
        int(LinkTableColumn.NAME),
        Qt.SortOrder.DescendingOrder,
        total_columns=6,
    )

    assert action is not None
    assert action.column == int(LinkTableColumn.NAME)
    assert action.order == Qt.SortOrder.DescendingOrder
    assert not action.persist_after_apply
    assert (
        controller.restore_after_populate_action(-1, Qt.SortOrder.AscendingOrder, total_columns=6)
        is None
    )
    assert (
        controller.restore_after_populate_action(
            int(LinkTableColumn.GROUP_LAUNCH),
            Qt.SortOrder.AscendingOrder,
            total_columns=6,
        )
        is None
    )
    assert (
        controller.restore_after_populate_action(99, Qt.SortOrder.AscendingOrder, total_columns=6)
        is None
    )
