from __future__ import annotations

import logging
from typing import List, Optional, Callable

from PyQt6.QtWidgets import QLayout, QLineEdit, QToolButton, QWidget

logger = logging.getLogger(__name__)


def log_layout_snapshot(
    *,
    container_w: int,
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
    total_width_for_func: Callable[..., int],
) -> None:
    """Логирование состояния лэйаута (как в исходном менеджере), когда включён инфо-лог.

    total_width_for_func: Callable[..., int]
        Функция, вычисляющая суммарную ширину по текущему состоянию верхней панели.
        Совместима с вызовом: (top_bar, search, recent, fav, quick, recent_btns, fav_btns, quick_btns, c_r, c_f, c_q) -> int
    """
    try:
        total = total_width_for_func(
            top_bar,
            search,
            recent,
            fav,
            quick,
            recent_btns,
            fav_btns,
            quick_btns,
            c_r,
            c_f,
            c_q,
        )
        tb_spacing = top_bar.spacing() or 0
        tb_m = top_bar.contentsMargins()

        def _panel_line(name: str, panel: Optional[QWidget], btns: List[QToolButton], cnt: int) -> str:
            if not panel:
                return f"{name}: none"
            try:
                pw = int(panel.width())
                pmw = int(panel.maximumWidth())
            except Exception:
                pw = pmw = -1
            try:
                bg = getattr(panel, "bg_frame", None)
                lay = bg.layout() if bg else None
                sp = lay.spacing() if lay else 0
                lm = lay.contentsMargins() if lay else None
                lm_str = f"{lm.left()},{lm.right()}" if lm else "-"
            except Exception:
                sp = 0
                lm_str = "-"
            try:
                pm = panel.contentsMargins()
                pm_str = f"{pm.left()},{pm.right()}"
            except Exception:
                pm_str = "-"
            cur = 0
            for i, b in enumerate(btns):
                if b.isVisible():
                    cur = i + 1
            return (
                f"{name}: tgt={cnt} cur={cur} w={pw} maxW={pmw} "
                f"lay[sp={sp} mL,R={lm_str}] panel[mL,R={pm_str}]"
            )

        lines = [
            f"TopBarSnapshot: container_w={container_w} total={total} tb[sp={tb_spacing} mL,R={tb_m.left()},{tb_m.right()}]",
            _panel_line("recent", recent, recent_btns, c_r),
            _panel_line("fav", fav, fav_btns, c_f),
            _panel_line("quick", quick, quick_btns, c_q),
            f"search present={'yes' if search is not None else 'no'}",
        ]
        for ln in lines:
            logger.info(ln)
    except Exception:
        logger.debug("TopBarLM: log_layout_snapshot failed", exc_info=True)
