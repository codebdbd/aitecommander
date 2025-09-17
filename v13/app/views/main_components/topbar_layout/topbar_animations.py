from __future__ import annotations

from typing import Callable, Optional

from PyQt6.QtCore import QParallelAnimationGroup, QPropertyAnimation, QEasingCurve, QTimer
from PyQt6.QtWidgets import QGraphicsOpacityEffect, QToolButton, QWidget


def apply_with_animation(
    *,
    panel: Optional[QWidget],
    btns: list[QToolButton],
    target_visible: int,
    anim_duration_ms: int,
    anim_curve: QEasingCurve.Type,
    get_container_widget: Callable[[], Optional[QWidget]],
    throttle_timer: QTimer,
    panel_width_func: Callable[[Optional[QWidget], list[QToolButton], int], int],
) -> int:
    """Анимированно применяет видимое количество кнопок панели.

    Поведение соответствует исходному _apply_with_animation из менеджера.
    Возвращает итоговое количество видимых кнопок (target clamped).
    """
    if not panel:
        return 0
    target_visible = max(0, min(target_visible, len(btns)))

    # Build animation group
    group = QParallelAnimationGroup(panel)
    any_anim = False

    # 1) Width animation (maximumWidth)
    panel.setMinimumWidth(0)
    new_w = panel_width_func(panel, btns, target_visible) if target_visible > 0 else 0
    try:
        old_w = int(panel.maximumWidth())
    except Exception:
        old_w = new_w
    if old_w != new_w:
        wa = QPropertyAnimation(panel, b"maximumWidth")
        wa.setDuration(anim_duration_ms)
        wa.setEasingCurve(anim_curve)
        wa.setStartValue(old_w)
        wa.setEndValue(new_w)
        group.addAnimation(wa)
        any_anim = True
    else:
        panel.setMaximumWidth(new_w)

    # 2) Buttons opacity animations
    for i, btn in enumerate(btns):
        need_visible = i < target_visible
        cur_visible = btn.isVisible()
        eff = btn.graphicsEffect()
        if not isinstance(eff, QGraphicsOpacityEffect):
            eff = QGraphicsOpacityEffect(btn)
            btn.setGraphicsEffect(eff)
        if need_visible and not cur_visible:
            btn.setVisible(True)
            eff.setOpacity(0.0)
            oa = QPropertyAnimation(eff, b"opacity")
            oa.setDuration(anim_duration_ms)
            oa.setEasingCurve(anim_curve)
            oa.setStartValue(0.0)
            oa.setEndValue(1.0)
            group.addAnimation(oa)
            any_anim = True
        elif (not need_visible) and cur_visible:
            eff.setOpacity(1.0)
            oa = QPropertyAnimation(eff, b"opacity")
            oa.setDuration(anim_duration_ms)
            oa.setEasingCurve(anim_curve)
            oa.setStartValue(1.0)
            oa.setEndValue(0.0)

            def _hide_button(b=btn):
                try:
                    b.setVisible(False)
                except Exception:
                    pass

            oa.finished.connect(_hide_button)
            group.addAnimation(oa)
            any_anim = True

    # Run or apply instantly
    if any_anim:
        def _on_done():
            try:
                host = get_container_widget()
                if isinstance(host, QWidget):
                    host.updateGeometry()
                    host.update()
            except Exception:
                pass
            # Trigger a final adjust to settle last state
            try:
                throttle_timer.start(0)
            except Exception:
                pass

        group.finished.connect(_on_done)
        group.start()
    else:
        # Ensure panel width is applied when no animation
        panel.setMaximumWidth(new_w)
        # Trigger a deferred adjust when applied instantly (no animations)
        try:
            throttle_timer.start(0)
        except Exception:
            pass

    return target_visible
