from __future__ import annotations

from typing import List, Optional

from PyQt6.QtWidgets import QLayout, QLineEdit, QToolButton, QWidget


def _safe_get(obj: Optional[object], name: str) -> Optional[object]:
    """Безопасный getattr без зависимости от sip.isdeleted.

    Если объект удалён, обращение может бросить исключение — мы его перехватываем и
    возвращаем None. Это поведение согласовано с topbar_layout_utils.safe_get.
    """
    if obj is None:
        return None
    try:
        return getattr(obj, name, None)
    except Exception:
        return None


def iter_buttons(panel_widget: Optional[QWidget], name: str) -> List[QToolButton]:
    """Возвращает упорядоченный список кнопок в панели по objectName.

    Сначала идём по layout(bg_frame), затем дополняем findChildren — поведение идентично менеджеру.
    """
    panel = panel_widget  # alias
    if not isinstance(panel, QWidget):
        return []
    bg = _safe_get(panel, "bg_frame")
    lay = bg.layout() if isinstance(bg, QWidget) and hasattr(bg, "layout") else None
    ordered: List[QToolButton] = []
    if lay:
        for i in range(lay.count()):
            w = lay.itemAt(i).widget()
            if isinstance(w, QToolButton) and w.objectName() == name:
                ordered.append(w)
    # Дополнить findChildren
    for b in panel.findChildren(QToolButton, name):
        if b not in ordered:
            ordered.append(b)
    return ordered


def current_visible_count(btns: List[QToolButton]) -> int:
    cnt = 0
    for i, b in enumerate(btns):
        if b.isVisible():
            cnt = i + 1
    return cnt


def panel_width(panel: Optional[QWidget], btns: List[QToolButton], count: int, *, button_size: int) -> int:
    """Рассчитать ширину панели для указанного количества видимых кнопок.

    Учитывает spacing, margins layout'а панели и margins самой панели.
    """
    if not isinstance(panel, QWidget) or not btns or count <= 0:
        return 0
    bg = _safe_get(panel, "bg_frame")
    lay = bg.layout() if isinstance(bg, QWidget) and hasattr(bg, "layout") else None
    spacing = lay.spacing() if lay else 0
    total = 0
    for i in range(count):
        try:
            btn_w = max(button_size, int(btns[i].sizeHint().width()))
        except Exception:
            btn_w = button_size
        if i > 0:
            total += spacing
        total += btn_w
    if lay:
        try:
            m = lay.contentsMargins()
            total += m.left() + m.right()
        except Exception:
            pass
    try:
        pm = panel.contentsMargins()
        total += pm.left() + pm.right()
    except Exception:
        pass
    return total


def compute_visible_counts(
    *,
    width: int,
    top_bar: QLayout,
    search: Optional[QLineEdit],
    recent: Optional[QWidget],
    fav: Optional[QWidget],
    quick: Optional[QWidget],
    recent_btns: List[QToolButton],
    fav_btns: List[QToolButton],
    quick_btns: List[QToolButton],
    max_recent_cap: int,
    max_fav_cap: int,
    max_quick_cap: int,
    total_width_for_func,
) -> tuple[int, int, int]:
    """Рассчитать видимые количества кнопок для панелей при заданной ширине.

    Поведение повторяет метод менеджера: сначала берём максимумы (с учётом длины списков),
    затем уменьшаем по одной кнопке, пока total_width_for > width, без минимальных квот.
    """
    max_recent = min(max_recent_cap, len(recent_btns))
    max_fav = min(max_fav_cap, len(fav_btns))
    max_quick = min(max_quick_cap, len(quick_btns))

    min_recent = 0
    min_fav = 0
    min_quick = 0

    cnt_recent, cnt_fav, cnt_quick = max_recent, max_fav, max_quick
    cnt_recent = max(min_recent, cnt_recent)
    cnt_fav = max(min_fav, cnt_fav)
    cnt_quick = max(min_quick, cnt_quick)

    max_steps = (cnt_recent - min_recent) + (cnt_fav - min_fav) + (cnt_quick - min_quick)
    steps = 0
    while (
        total_width_for_func(
            top_bar,
            search,
            recent,
            fav,
            quick,
            recent_btns,
            fav_btns,
            quick_btns,
            cnt_recent,
            cnt_fav,
            cnt_quick,
        )
        > width
        and steps < max_steps
    ):
        steps += 1
        if cnt_recent > min_recent:
            cnt_recent -= 1
        elif cnt_fav > min_fav:
            cnt_fav -= 1
        elif cnt_quick > min_quick:
            cnt_quick -= 1
        else:
            break

    if (
        total_width_for_func(
            top_bar,
            search,
            recent,
            fav,
            quick,
            recent_btns,
            fav_btns,
            quick_btns,
            cnt_recent,
            cnt_fav,
            cnt_quick,
        )
        > width
    ):
        cnt_recent, cnt_fav, cnt_quick = 0, 0, 0

    return cnt_recent, cnt_fav, cnt_quick


def total_width_for(
    top_bar: QLayout,
    search: Optional[QLineEdit],
    recent: Optional[QWidget],
    fav: Optional[QWidget],
    quick: Optional[QWidget],
    recent_btns: List[QToolButton],
    fav_btns: List[QToolButton],
    quick_btns: List[QToolButton],
    c_r: int,
    c_f: int,
    c_q: int,
    *,
    button_size: int,
    min_search_width: int,
) -> int:
    """Суммарная требуемая ширина топ-бара с учётом текущих целевых количеств.
    Поведение идентично оригиналу в менеджере.
    """
    items: List[int] = []
    for i in range(top_bar.count()):
        it = top_bar.itemAt(i)
        w = it.widget()
        if w:
            if w is search:
                # Используем явный min_search_width, чтобы поведение совпадало с менеджером
                items.append(int(min_search_width))
            elif w is recent and c_r > 0:
                items.append(panel_width(recent, recent_btns, c_r, button_size=button_size))
            elif w is fav and c_f > 0:
                items.append(panel_width(fav, fav_btns, c_f, button_size=button_size))
            elif w is quick and c_q > 0:
                items.append(panel_width(quick, quick_btns, c_q, button_size=button_size))
            elif w.isVisible():
                try:
                    items.append(int(w.sizeHint().width()))
                except Exception:
                    pass
        else:
            sp = it.spacerItem()
            if sp:
                try:
                    items.append(max(0, sp.sizeHint().width()))
                except Exception:
                    pass
    total = sum(items)
    try:
        spacing = top_bar.spacing() or 0
        total += spacing * max(0, len(items) - 1)
        m = top_bar.contentsMargins()
        total += m.left() + m.right()
    except Exception:
        pass
    return total
