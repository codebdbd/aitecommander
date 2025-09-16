from __future__ import annotations

from typing import Callable, Optional

from PyQt6.QtWidgets import QLayout, QLineEdit, QSizePolicy, QWidget


def _is_vertical_separator(w: Optional[QWidget]) -> bool:
    if not w:
        return False
    try:
        if w.objectName() == "vSeparator":
            return True
    except Exception:
        pass
    try:
        cls = str(w.property("class") or "")
        return cls == "vertical_separator"
    except Exception:
        return False


def update_separators_visibility(
    *,
    top_bar: QLayout,
    window: object,
    recent_visible: bool,
    fav_visible: bool,
    quick_visible: bool,
    search_exists: bool,
    safe_get: Callable[[Optional[object], str], Optional[object]],
    spacer_size: int,
) -> None:
    """Обновляет видимость вертикальных разделителей и размеры соседних spacer'ов.

    Логика полностью совпадает с исходной реализацией менеджера.
    """
    # Кэшируем виджеты панелей, чтобы не вызывать safe_get в каждой проверке
    try:
        _recent_widget = safe_get(window, "recent_links_widget")
    except Exception:
        _recent_widget = None
    try:
        _fav_widget = safe_get(window, "fav_widget")
    except Exception:
        _fav_widget = None
    try:
        _quick_widget = safe_get(window, "quick_add_widget")
    except Exception:
        _quick_widget = None

    def logical_visible_panel(w: Optional[QWidget]) -> bool:
        if not w:
            return False
        try:
            if w is _recent_widget:
                return recent_visible and w.isVisible()
            if w is _fav_widget:
                return fav_visible and w.isVisible()
            if w is _quick_widget:
                return quick_visible and w.isVisible()
        except Exception:
            return False
        return False

    try:
        count = top_bar.count()
    except Exception:
        return

    i = 0
    while i < count:
        it = top_bar.itemAt(i)
        w = it.widget()
        if _is_vertical_separator(w):
            left_widget: Optional[QWidget] = None
            j = i - 1
            while j >= 0 and not left_widget:
                prev_it = top_bar.itemAt(j)
                if prev_it.widget():
                    left_widget = prev_it.widget()
                j -= 1
            right_widget: Optional[QWidget] = None
            j = i + 1
            while j < count and not right_widget:
                next_it = top_bar.itemAt(j)
                if next_it.widget():
                    right_widget = next_it.widget()
                j += 1
            show_sep = logical_visible_panel(left_widget) and (
                logical_visible_panel(right_widget)
                or (search_exists and isinstance(right_widget, QLineEdit))
            )
            try:
                w.setVisible(show_sep)
            except Exception:
                pass
            # Размеры спейсеров по бокам разделителя (безопасный доступ)
            left_sp = None
            if i - 1 >= 0:
                try:
                    left_item = top_bar.itemAt(i - 1)
                    if left_item is not None:
                        left_sp = left_item.spacerItem()
                except Exception:
                    left_sp = None
            right_sp = None
            if i + 1 < count:
                try:
                    right_item = top_bar.itemAt(i + 1)
                    if right_item is not None:
                        right_sp = right_item.spacerItem()
                except Exception:
                    right_sp = None

            if show_sep:
                if left_sp:
                    left_sp.changeSize(
                        spacer_size,
                        0,
                        QSizePolicy.Policy.Fixed,
                        QSizePolicy.Policy.Fixed,
                    )
                if right_sp:
                    right_sp.changeSize(
                        spacer_size,
                        0,
                        QSizePolicy.Policy.Fixed,
                        QSizePolicy.Policy.Fixed,
                    )
            else:
                is_search_right = isinstance(right_widget, QLineEdit)
                if left_sp:
                    left_sp.changeSize(
                        0 if is_search_right else spacer_size,
                        0,
                        QSizePolicy.Policy.Fixed,
                        QSizePolicy.Policy.Fixed,
                    )
                if right_sp:
                    right_sp.changeSize(
                        spacer_size if is_search_right else 0,
                        0,
                        QSizePolicy.Policy.Fixed,
                        QSizePolicy.Policy.Fixed,
                    )
        i += 1
    try:
        top_bar.invalidate()
    except Exception:
        pass
