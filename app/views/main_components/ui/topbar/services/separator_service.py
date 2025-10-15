"""Service for managing separator visibility in the top bar layout."""

from __future__ import annotations

from typing import Mapping

from PyQt6.QtWidgets import QLayout, QLineEdit, QSizePolicy, QWidget

from ..models.topbar_constants import TOPBAR_CONSTANTS as C
from ..models.types import PanelLabel


class SeparatorVisibilityService:
    """Manage separator visibility and spacing in the top bar.
    
    Responsibilities:
    - Determine which separators should be visible based on panel states
    - Update spacer sizes around separators
    - Handle separator bridging logic (show separator if next visible widget exists)
    """

    def __init__(self) -> None:
        self._separator_spacing_visible = C.SEPARATOR_SPACING_VISIBLE
        self._separator_spacing_hidden = C.SEPARATOR_SPACING_HIDDEN

    def update_separators(
        self,
        top_bar: QLayout,
        applied_counts: Mapping[str, int],
        has_search: bool,
        panel_widgets_map: Mapping[int, tuple[str, QWidget]],
    ) -> None:
        """Update separator visibility and spacing based on panel states.
        
        Args:
            top_bar: Top bar layout containing separators
            applied_counts: Visible button counts per panel
            has_search: Whether search widget is present
            panel_widgets_map: Mapping of widget id to (label, widget) tuples
        """
        widgets_map = self._build_widgets_map(top_bar)
        count = top_bar.count()

        for index in range(count):
            item = top_bar.itemAt(index)
            widget = item.widget()
            if widget is None or widget.objectName() != "vSeparator":
                continue

            left_widget = self._find_neighbor_widget(widgets_map, index, -1, count)
            right_widget = self._find_neighbor_widget(widgets_map, index, +1, count)

            show_sep, target_right_widget = self._should_show_separator(
                left_widget,
                right_widget,
                panel_widgets_map,
                applied_counts,
                has_search,
                widgets_map,
                index,
                count,
            )

            widget.setVisible(show_sep)
            self._update_spacer_sizes(
                top_bar, index, count, show_sep, target_right_widget
            )

    def build_panel_widgets_map(
        self, window, panel_labels: tuple[str, ...]
    ) -> dict[int, tuple[str, QWidget]]:
        """Build mapping of panel widget IDs to (label, widget) tuples.
        
        Args:
            window: Window object containing panel widgets
            panel_labels: Tuple of panel label strings
            
        Returns:
            Dictionary mapping widget id() to (label, widget)
        """
        panel_widgets = {}
        label_to_attr = {
            PanelLabel.RECENT.value: "recent_links_widget",
            PanelLabel.FAVORITES.value: "fav_widget",
            PanelLabel.QUICK.value: "quick_add_widget",
        }
        
        for label in panel_labels:
            attr_name = label_to_attr.get(label)
            if not attr_name:
                continue
            widget = getattr(window, attr_name, None)
            if widget:
                panel_widgets[id(widget)] = (label, widget)
        return panel_widgets

    def _build_widgets_map(self, top_bar: QLayout) -> dict[int, QWidget]:
        """Build mapping of layout indices to widgets."""
        count = top_bar.count()
        widgets_map = {}
        for index in range(count):
            item = top_bar.itemAt(index)
            widget = item.widget()
            if widget is not None:
                widgets_map[index] = widget
        return widgets_map

    def _find_neighbor_widget(
        self, widgets_map: dict[int, QWidget], index: int, direction: int, count: int
    ) -> QWidget | None:
        """Find the nearest widget neighbor in the given direction."""
        if direction < 0:
            for idx in range(index - 1, -1, -1):
                if idx in widgets_map:
                    return widgets_map[idx]
        else:
            for idx in range(index + 1, count):
                if idx in widgets_map:
                    return widgets_map[idx]
        return None

    def _is_panel_visible(
        self,
        widget: QWidget | None,
        panel_widgets: Mapping[int, tuple[str, QWidget]],
        applied_counts: Mapping[str, int],
    ) -> bool:
        """Check if a panel widget is visible based on applied counts."""
        if not widget:
            return False
        panel_info = panel_widgets.get(id(widget))
        if panel_info:
            state_label, panel_widget = panel_info
            return applied_counts.get(state_label, 0) > 0 and panel_widget.isVisible()
        return False

    def _find_next_visible_widget(
        self,
        widgets_map: dict[int, QWidget],
        panel_widgets: Mapping[int, tuple[str, QWidget]],
        applied_counts: Mapping[str, int],
        start_index: int,
        step: int,
        count: int,
    ) -> QWidget | None:
        """Find the next visible widget, skipping separators and hidden panels."""
        idx = start_index + step
        while 0 <= idx < count:
            widget = widgets_map.get(idx)
            if widget is None:
                idx += step
                continue
            if widget.objectName() == "vSeparator":
                idx += step
                continue

            panel_info = panel_widgets.get(id(widget))
            if panel_info:
                state_label, panel_widget = panel_info
                if applied_counts.get(state_label, 0) > 0 and panel_widget.isVisible():
                    return panel_widget
                idx += step
                continue

            return widget
        return None

    def _should_show_separator(
        self,
        left_widget: QWidget | None,
        right_widget: QWidget | None,
        panel_widgets: Mapping[int, tuple[str, QWidget]],
        applied_counts: Mapping[str, int],
        has_search: bool,
        widgets_map: dict[int, QWidget],
        index: int,
        count: int,
    ) -> tuple[bool, QWidget | None]:
        """Determine if separator should be shown and identify target right widget."""
        left_visible = self._is_panel_visible(
            left_widget, panel_widgets, applied_counts
        )
        right_visible = self._is_panel_visible(
            right_widget, panel_widgets, applied_counts
        )

        show_sep = left_visible and (
            right_visible or (has_search and isinstance(right_widget, QLineEdit))
        )

        target_right_widget = right_widget

        # Bridging logic: show separator if next visible widget exists
        if (
            not show_sep
            and left_visible
            and not right_visible
            and right_widget is not None
            and panel_widgets.get(id(right_widget))
        ):
            bridged_right = self._find_next_visible_widget(
                widgets_map, panel_widgets, applied_counts, index, +1, count
            )
            if bridged_right is not None and (
                self._is_panel_visible(bridged_right, panel_widgets, applied_counts)
                or (has_search and isinstance(bridged_right, QLineEdit))
            ):
                target_right_widget = bridged_right
                show_sep = True

        return show_sep, target_right_widget

    def _update_spacer_sizes(
        self,
        top_bar: QLayout,
        index: int,
        count: int,
        show_sep: bool,
        target_right_widget: QWidget | None,
    ) -> None:
        """Update spacer sizes around a separator based on visibility."""
        left_sp = top_bar.itemAt(index - 1).spacerItem() if index - 1 >= 0 else None
        right_sp = top_bar.itemAt(index + 1).spacerItem() if index + 1 < count else None

        if show_sep:
            if left_sp:
                left_sp.changeSize(
                    self._separator_spacing_visible,
                    0,
                    QSizePolicy.Policy.Fixed,
                    QSizePolicy.Policy.Fixed,
                )
            if right_sp:
                right_sp.changeSize(
                    self._separator_spacing_visible,
                    0,
                    QSizePolicy.Policy.Fixed,
                    QSizePolicy.Policy.Fixed,
                )
        else:
            is_search_right = isinstance(target_right_widget, QLineEdit)
            spacing = (
                self._separator_spacing_visible
                if is_search_right
                else self._separator_spacing_hidden
            )
            if left_sp:
                left_sp.changeSize(
                    spacing,
                    0,
                    QSizePolicy.Policy.Fixed,
                    QSizePolicy.Policy.Fixed,
                )
            if right_sp:
                right_sp.changeSize(
                    spacing,
                    0,
                    QSizePolicy.Policy.Fixed,
                    QSizePolicy.Policy.Fixed,
                )
