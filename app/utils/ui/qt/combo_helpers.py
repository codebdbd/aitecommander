from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Callable

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QComboBox


def select_combo_data(
    combo: QComboBox,
    *,
    current_data: object = None,
    preferred_data: object = None,
    fallback_to_first: bool = True,
) -> int:
    """Select combo item by current/preferred data with explicit fallback order.

    Returns the applied index, or ``-1`` if no suitable selection exists.
    """
    target_index = -1
    if current_data is not None:
        target_index = combo.findData(current_data)
    if target_index < 0 and preferred_data is not None:
        target_index = combo.findData(preferred_data)
    if target_index < 0 and fallback_to_first and combo.count() > 0:
        target_index = 0
    if target_index >= 0:
        combo.setCurrentIndex(target_index)
    return target_index


def select_first_combo_item(
    combo: QComboBox, *, only_if_unset: bool = False
) -> bool:
    """Select the first combo item.

    When ``only_if_unset`` is true, preserve the existing selection if the combo
    already has a valid current index.
    """
    if combo.count() <= 0:
        return False
    if only_if_unset and combo.currentIndex() >= 0:
        return False
    combo.setCurrentIndex(0)
    return True


def try_select_combo_data(combo: Any, data_id: Any) -> bool:
    """Best-effort ``findData`` selection for dialogs that tolerate missing combos."""
    try:
        if data_id is None:
            return False
        return select_combo_data(
            combo,
            current_data=data_id,
            fallback_to_first=False,
        ) >= 0
    except (AttributeError, RuntimeError, TypeError):
        return False


def try_select_first_combo_item(combo: Any, *, only_if_unset: bool = False) -> bool:
    """Best-effort first-item selection for dialogs that tolerate missing combos."""
    try:
        return select_first_combo_item(combo, only_if_unset=only_if_unset)
    except (AttributeError, RuntimeError, TypeError):
        return False


def add_combo_item(
    combo: QComboBox,
    text: object,
    data: object = None,
    *,
    icon: QIcon | None = None,
) -> None:
    """Add one combo item with optional icon and arbitrary user data."""
    display_text = str(text)
    if icon is not None and not icon.isNull():
        combo.addItem(icon, display_text, data)
        return
    combo.addItem(display_text, data)


def add_combo_mapping_item(
    combo: QComboBox,
    item: Mapping[str, Any],
    *,
    text_key: str = "name",
    data_key: str = "id",
    icon_key: str | None = None,
    icon_loader: Callable[[str], QIcon | None] | None = None,
) -> bool:
    """Add a combo item from a mapping-like record.

    Returns ``True`` when an item was added, ``False`` when required keys are absent.
    """
    text = item.get(text_key)
    data = item.get(data_key)
    if text is None or data is None:
        return False

    icon = None
    if icon_key and icon_loader is not None:
        icon = icon_loader(str(item.get(icon_key, "")))

    add_combo_item(combo, text, data, icon=icon)
    return True
