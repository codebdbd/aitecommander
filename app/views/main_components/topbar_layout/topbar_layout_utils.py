from __future__ import annotations

from typing import Optional, MutableSet, Callable
import logging

from PyQt6.QtWidgets import QLayout, QLineEdit, QWidget
from PyQt6.QtCore import QObject
from app.config_data import app_config

logger = logging.getLogger(__name__)


def _topbar_debug_enabled() -> bool:
    """Флаг детального отладочного логирования для topbar utils из конфига.

    Ключ: ui.topbar.debug_utils (bool). По умолчанию False.
    """
    try:
        return bool(app_config.get("ui.topbar.debug_utils", False))
    except Exception:
        return False


def _dbg_log(msg: str, *args, exc: bool = False) -> None:
    """Условное debug-логирование, управляемое конфигом ui.topbar.debug_utils.

    Если exc=True, прикладывается traceback (exc_info=True).
    """
    if _topbar_debug_enabled():
        if exc:
            logger.debug(msg, *args, exc_info=True)
        else:
            logger.debug(msg, *args)

# Убрана опциональная зависимость от sip.isdeleted: избежим различий окружений PyQt5/PyQt6


def safe_get(obj: Optional[object], name: str) -> Optional[object]:
    """Безопасный getattr с защитой от исключений RuntimeError/AttributeError.

    Проверка «удалённости» Qt-объектов через sip.isdeleted удалена ради совместимости и
    предсказуемости поведения в PyQt6. Если объект удалён, getattr, как правило, вызовет
    исключение — мы его перехватим и вернём None.
    """
    if obj is None:
        return None
    try:
        return getattr(obj, name, None)
    except Exception:
        _dbg_log("TopBar utils: getattr failed: obj=%r, name=%s", obj, name, exc=True)
        return None


def install_topbar_event_filters(
    *,
    window: object,
    watched_set: MutableSet[QWidget],
    event_filter_obj: QObject,
    safe_get: Callable[[Optional[object], str], Optional[object]],
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
                except Exception as e:
                    _dbg_log(
                        "TopBar utils: failed to install event filter on %s (%r)",
                        attr_name,
                        widget,
                        exc=True,
                    )
                try:
                    watched_set.add(widget)
                except Exception:
                    _dbg_log(
                        "TopBar utils: failed to add widget to watched_set: %s (%r)",
                        attr_name,
                        widget,
                        exc=True,
                    )
        if isinstance(window, QWidget):
            try:
                window.installEventFilter(event_filter_obj)
            except Exception:
                _dbg_log(
                    "TopBar utils: failed to install event filter on window (%r)",
                    window,
                    exc=True,
                )
    except Exception:
        # Не мешаем падать из-за диагностики, но пишем в debug при включенном флаге
        _dbg_log(
            "TopBar utils: install_topbar_event_filters encountered an error",
            exc=True,
        )


def apply_counts(
    *,
    window: object,
    set_visible_count: Callable[[Optional[QWidget], str, int], int],
    safe_get: Callable[[Optional[object], str], Optional[object]],
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
    # За один проход также считаем число видимых виджетов (без поля поиска)
    occupied = 0
    try:
        count = top_bar.count()
    except Exception:
        _dbg_log("TopBar utils: failed to read top_bar.count()", exc=True)
        count = 0
    visible_count = 0  # количество видимых виджетов (без поиска)
    for i in range(count):
        it = top_bar.itemAt(i)
        w = it.widget()
        if w is None:
            sp = it.spacerItem()
            if sp:
                try:
                    occupied += max(0, sp.sizeHint().width())
                except Exception:
                    _dbg_log("TopBar utils: spacer sizeHint failed at index=%d", i, exc=True)
            continue
        if w is search:
            continue
        if w.isVisible():
            visible_count += 1
            try:
                occupied += int(w.width())
            except Exception:
                try:
                    occupied += int(w.sizeHint().width())
                except Exception:
                    _dbg_log("TopBar utils: widget sizeHint failed for %r", w, exc=True)
    try:
        spacing = top_bar.spacing() or 0
    except Exception:
        _dbg_log("TopBar utils: failed to read top_bar.spacing()", exc=True)
        spacing = 0
    # корректировка spacing по числу видимых элементов (без поиска)
    occupied += spacing * max(0, visible_count - 1)
    try:
        m = top_bar.contentsMargins()
        occupied += m.left() + m.right()
    except Exception:
        _dbg_log("TopBar utils: failed to read top_bar.contentsMargins()", exc=True)
    host = get_container_widget()
    try:
        container_w = host.width() if isinstance(host, QWidget) else 0
    except Exception:
        _dbg_log("TopBar utils: failed to read container width for %r", host, exc=True)
        container_w = 0
    remaining = max(0, container_w - occupied)
    # Не даём меньше минимальной ширины поиска
    max_search_w = max(int(min_search_width), int(remaining))
    try:
        if search.maximumWidth() != max_search_w:
            search.setMaximumWidth(max_search_w)
    except Exception:
        _dbg_log("TopBar utils: failed to set search width", exc=True)
    try:
        if search.minimumWidth() != min_search_width:
            search.setMinimumWidth(min_search_width)
    except Exception:
        _dbg_log("TopBar utils: failed to set search width", exc=True)


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
        _dbg_log("TopBar utils: enforce_stretches failed to read top_bar.count()", exc=True)
        return
    search_index = -1
    for i in range(count):
        try:
            it = top_bar.itemAt(i)
            w = it.widget()
        except Exception:
            _dbg_log("TopBar utils: failed to read itemAt(%d).widget()", i, exc=True)
            w = None
        if isinstance(search, QLineEdit) and w is search:
            search_index = i
        try:
            top_bar.setStretch(i, 0)
        except Exception:
            _dbg_log("TopBar utils: top_bar.setStretch(%d, 0) failed", i, exc=True)
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
        _dbg_log("TopBar utils: panel.setMinimumWidth(0) failed for %r", panel, exc=True)
    try:
        max_w = panel_width_func(panel, btns, visible) if visible > 0 else 0
    except Exception:
        _dbg_log("TopBar utils: panel_width_func failed for %r", panel, exc=True)
        max_w = 0
    try:
        panel.setMaximumWidth(max_w)
    except Exception:
        _dbg_log("TopBar utils: panel.setMaximumWidth(%s) failed for %r", max_w, panel, exc=True)


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
        _dbg_log("TopBar utils: zero_all_spacers failed", exc=True)
