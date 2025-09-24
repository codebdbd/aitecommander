"""Менеджер анимаций для топбара с поддержкой PyQt6."""
from __future__ import annotations

import logging
from typing import List, Optional

from PyQt6.QtCore import QEasingCurve, QParallelAnimationGroup, QPropertyAnimation, QObject
from PyQt6.QtWidgets import QGraphicsOpacityEffect, QToolButton, QWidget

from app.views.main_components.topbar.top_bar_config import TopBarConfig

logger = logging.getLogger(__name__)


class TopBarAnimationManager:
    """Управление анимациями топбара."""

    def __init__(self, config: TopBarConfig) -> None:
        """Инициализация менеджера анимаций."""
        self.config = config
        self._active_groups: List[QParallelAnimationGroup] = []

    def animate_panel_width_and_buttons(
        self,
        panel: Optional[QWidget],
        buttons: List[QToolButton],
        target_visible: int,
        on_finished: Optional[callable] = None
    ) -> int:
        """Анимировать изменение ширины панели и видимость кнопок."""
        if not panel:
            return 0

        target_visible = max(0, min(target_visible, len(buttons)))

        # Создать группу анимаций
        group = QParallelAnimationGroup(panel)
        any_animation = False

        # 1. Анимация ширины панели
        panel.setMinimumWidth(0)
        new_width = self._calculate_panel_width(panel, buttons, target_visible)
        old_width = panel.maximumWidth()

        if old_width != new_width:
            width_anim = QPropertyAnimation(panel, b"maximumWidth")
            width_anim.setDuration(self.config.anim_duration_ms)
            width_anim.setEasingCurve(self._get_easing_curve())
            width_anim.setStartValue(old_width)
            width_anim.setEndValue(new_width)
            group.addAnimation(width_anim)
            any_animation = True
        else:
            panel.setMaximumWidth(new_width)

        # 2. Анимация прозрачности кнопок
        for i, button in enumerate(buttons):
            need_visible = i < target_visible
            cur_visible = button.isVisible()

            # Создать или получить эффект прозрачности
            effect = button.graphicsEffect()
            if not isinstance(effect, QGraphicsOpacityEffect):
                effect = QGraphicsOpacityEffect(button)
                button.setGraphicsEffect(effect)

            if need_visible and not cur_visible:
                # Показать кнопку с анимацией появления
                button.setVisible(True)
                effect.setOpacity(0.0)
                opacity_anim = QPropertyAnimation(effect, b"opacity")
                opacity_anim.setDuration(self.config.anim_duration_ms)
                opacity_anim.setEasingCurve(self._get_easing_curve())
                opacity_anim.setStartValue(0.0)
                opacity_anim.setEndValue(1.0)
                group.addAnimation(opacity_anim)
                any_animation = True

            elif not need_visible and cur_visible:
                # Скрыть кнопку с анимацией исчезания
                effect.setOpacity(1.0)
                opacity_anim = QPropertyAnimation(effect, b"opacity")
                opacity_anim.setDuration(self.config.anim_duration_ms)
                opacity_anim.setEasingCurve(self._get_easing_curve())
                opacity_anim.setStartValue(1.0)
                opacity_anim.setEndValue(0.0)

                # Скрыть кнопку после завершения анимации
                def hide_button(btn: QToolButton) -> None:
                    try:
                        btn.setVisible(False)
                    except RuntimeError:
                        pass  # Виджет может быть уже удален

                opacity_anim.finished.connect(lambda: hide_button(button))
                group.addAnimation(opacity_anim)
                any_animation = True

        # Запустить анимацию или применить изменения мгновенно
        if any_animation:
            self._active_groups.append(group)

            def on_animation_finished() -> None:
                try:
                    # Обновить геометрию контейнера
                    parent = panel.parentWidget()
                    if parent:
                        parent.updateGeometry()
                        parent.update()
                except RuntimeError:
                    pass

                # Удалить группу из активных
                if group in self._active_groups:
                    self._active_groups.remove(group)

                # Вызвать пользовательский колбэк
                if on_finished:
                    on_finished()

            group.finished.connect(on_animation_finished)
            group.start()
        else:
            # Применить изменения без анимации
            panel.setMaximumWidth(new_width)
            if on_finished:
                on_finished()

        return target_visible

    def _calculate_panel_width(
        self,
        panel: QWidget,
        buttons: List[QToolButton],
        visible_count: int
    ) -> int:
        """Рассчитать ширину панели для заданного количества кнопок."""
        if not panel or not buttons or visible_count <= 0:
            return 0

        # Получить layout
        layout = panel.layout()
        spacing = layout.spacing() if layout else 0

        total_width = 0

        # Рассчитать ширину кнопок
        for i in range(min(visible_count, len(buttons))):
            try:
                button_width = max(self.config.button_size, buttons[i].sizeHint().width())
            except (AttributeError, RuntimeError):
                button_width = self.config.button_size
            if i > 0:
                total_width += spacing
            total_width += button_width

        # Добавить отступы layout'а
        if layout:
            margins = layout.contentsMargins()
            total_width += margins.left() + margins.right()

        # Добавить отступы панели
        try:
            panel_margins = panel.contentsMargins()
            total_width += panel_margins.left() + panel_margins.right()
        except (AttributeError, RuntimeError):
            pass

        return total_width

    def _get_easing_curve(self) -> QEasingCurve.Type:
        """Получить кривую easing для анимаций."""
        curve_mapping = {
            "OutCubic": QEasingCurve.Type.OutCubic,
            "InOutCubic": QEasingCurve.Type.InOutCubic,
            "OutQuad": QEasingCurve.Type.OutQuad,
            "Linear": QEasingCurve.Type.Linear,
        }
        return curve_mapping.get(self.config.anim_curve, QEasingCurve.Type.OutCubic)

    def is_animating(self) -> bool:
        """Проверить, выполняется ли анимация."""
        return len(self._active_groups) > 0

    def stop_all_animations(self) -> None:
        """Остановить все активные анимации."""
        for group in self._active_groups[:]:  # Копируем список, так как он может измениться
            try:
                group.stop()
                if group in self._active_groups:
                    self._active_groups.remove(group)
            except RuntimeError:
                pass

    def cleanup(self) -> None:
        """Очистка ресурсов."""
        self.stop_all_animations()
