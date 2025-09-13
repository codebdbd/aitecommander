from __future__ import annotations

from typing import Optional

from PyQt6.QtWidgets import QLayout, QLineEdit, QWidget

try:  # pragma: no cover - optional in tests without sip
    from sip import isdeleted as _sip_isdeleted
except Exception:  # pragma: no cover

    def _sip_isdeleted(_obj) -> bool:
        return False


def safe_get(obj: Optional[object], name: str) -> Optional[object]:
    """Безопасный getattr с защитой от удалённых Qt-объектов и RuntimeError."""
    if obj is None:
        return None
    try:
        if isinstance(obj, QWidget) and _sip_isdeleted(obj):
            return None
    except Exception:
        # В редких случаях проверка удалённости может кидать ошибки — игнорируем
        pass
    try:
        return getattr(obj, name, None)
    except Exception:
        return None


def install_topbar_event_filters(
    *, window: object, watched_set, event_filter_obj, safe_get
) -> None:
    """Устанавливает фильтры событий на релевантные виджеты верхней панели и на окно.

    Поведение соответствует TopBarLayoutManager._install_event_filters.
    """
    try:
        for attr_name in (
            "top_bar_host",
            "content_container",
            "quick_add_widget",
            "fav_widget",
            "recent_links_widget",
        ):
            widget = safe_get(window, attr_name)
            if isinstance(widget, QWidget) and widget not in watched_set:
                try:
                    widget.installEventFilter(event_filter_obj)
                except Exception:
                    pass
                try:
                    watched_set.add(widget)
                except Exception:
                    pass
        if isinstance(window, QWidget) and not _sip_isdeleted(window):
            try:
                window.installEventFilter(event_filter_obj)
            except Exception:
                pass
    except Exception:
        # Не мешаем падать из-за диагностики
        pass


def apply_counts(
    *,
    window: object,
    set_visible_count,
    safe_get,
    c_r: int,
    c_f: int,
    c_q: int,
) -> None:
    """Применить видимые количества для панелей recent/fav/quick через предоставленный callback.

    Менеджер устанавливает _last_applied самостоятельно.
    """
    recent = safe_get(window, "recent_links_widget")
    fav = safe_get(window, "fav_widget")
    quick = safe_get(window, "quick_add_widget")
    set_visible_count(recent, "recentButton", c_r)
    set_visible_count(fav, "favoriteButton", c_f)
    set_visible_count(quick, "quickButton", c_q)


def clamp_search_width_to_remaining_space(
    *,
    top_bar: QLayout,
    search: QLineEdit,
    get_container_widget,
    min_search_width: int,
) -> None:
    """Ограничивает ширину поля поиска оставшимся пространством, но не меньше минимума.

    Поведение эквивалентно блоку в TopBarLayoutManager.adjust().
    """
    # Считаем суммарную ширину уже применённых панелей + разделителей/отступов
    occupied = 0
    try:
        count = top_bar.count()
    except Exception:
        count = 0
    for i in range(count):
        it = top_bar.itemAt(i)
        w = it.widget()
        if w is None:
            sp = it.spacerItem()
            if sp:
                try:
                    occupied += max(0, sp.sizeHint().width())
                except Exception:
                    pass
            continue
        if w is search:
            continue
        if w.isVisible():
            try:
                occupied += int(w.width())
            except Exception:
                try:
                    occupied += int(w.sizeHint().width())
                except Exception:
                    pass
    try:
        spacing = top_bar.spacing() or 0
    except Exception:
        spacing = 0
    # число видимых элементов (без поиска) для корректировки spacing
    visible_widgets = []
    for i in range(count):
        it = top_bar.itemAt(i)
        w = it.widget()
        if w is not None and w is not search and w.isVisible():
            visible_widgets.append(w)
    occupied += spacing * max(0, len(visible_widgets) - 1)
    try:
        m = top_bar.contentsMargins()
        occupied += m.left() + m.right()
    except Exception:
        pass
    host = get_container_widget()
    try:
        container_w = host.width() if isinstance(host, QWidget) else 0
    except Exception:
        container_w = 0
    remaining = max(0, container_w - occupied)
    # Не даём меньше минимальной ширины поиска
    max_search_w = max(int(min_search_width), int(remaining))
    try:
        if search.maximumWidth() != max_search_w:
            search.setMaximumWidth(max_search_w)
    except Exception:
        pass
    try:
        if search.minimumWidth() != min_search_width:
            search.setMinimumWidth(min_search_width)
    except Exception:
        pass


def get_top_bar(window: object) -> Optional[QLayout]:
    """Найти лэйаут верхней панели в window: сначала top_bar_host, затем content_container."""
    for attr in ("top_bar_host", "content_container"):
        host = safe_get(window, attr)
        if isinstance(host, QWidget):
            try:
                lay = host.layout()
            except Exception:
                lay = None
            if lay:
                return lay
    return None


def set_top_bar_margins(top_bar: QLayout, left: int, top: int, right: int, bottom: int) -> None:
    """Безопасно выставляет отступы для top_bar (QLayout)."""
    try:
        m = top_bar.contentsMargins()
        if (
            m.left() == left
            and m.top() == top
            and m.right() == right
            and m.bottom() == bottom
        ):
            return
    except Exception:
        pass
    try:
        top_bar.setContentsMargins(left, top, right, bottom)
    except Exception:
        pass


def enforce_stretches(top_bar: QLayout, search: Optional[QLineEdit]) -> None:
    """Сбрасывает stretch=0 для всех элементов top_bar и ставит stretch=1 только для поиска."""
    try:
        count = top_bar.count()
    except Exception:
        return
    search_index = -1
    for i in range(count):
        try:
            it = top_bar.itemAt(i)
            w = it.widget()
        except Exception:
            w = None
        if isinstance(search, QLineEdit) and w is search:
            search_index = i
        try:
            top_bar.setStretch(i, 0)
        except Exception:
            pass
    if search_index >= 0:
        try:
            top_bar.setStretch(search_index, 1)
        except Exception:
            pass


def apply_panel_width_bounds(
    panel: Optional[QWidget],
    btns: list,
    visible: int,
    *,
    panel_width_func,
) -> None:
    """Устанавливает максимум ширины панели по расчету panel_width_func.

    Поведение соответствует _apply_panel_width_bounds из менеджера.
    """
    if not isinstance(panel, QWidget):
        return
    try:
        panel.setMinimumWidth(0)
    except Exception:
        pass
    try:
        max_w = panel_width_func(panel, btns, visible) if visible > 0 else 0
    except Exception:
        max_w = 0
    try:
        panel.setMaximumWidth(max_w)
    except Exception:
        pass


def zero_all_spacers(top_bar: QLayout) -> None:
    """Устанавливает ширину всех spacerItem в 0 для полного освобождения места (узкий режим)."""
    try:
        count = top_bar.count()
        for i in range(count):
            it = top_bar.itemAt(i)
            sp = it.spacerItem()
            if sp is not None:
                sp.changeSize(0, 0)
    except Exception:
        pass
