from __future__ import annotations

import logging
from typing import Iterable, List, Optional

from PyQt6.QtCore import QParallelAnimationGroup, QPropertyAnimation
from PyQt6.QtWidgets import (
    QGraphicsOpacityEffect,
    QLayout,
    QLineEdit,
    QToolButton,
    QWidget,
)

from .constants import TopBarConstants
from .panel_state import PanelState
from .width_calculator import WidthCalculator

logger = logging.getLogger(__name__)


class PanelVisibilityManager:
    """Управляет видимостью кнопок панелей и их анимацией."""

    def __init__(self, width_calculator: WidthCalculator):
        self._width_calculator = width_calculator

    def iter_buttons(
        self, panel_widget: Optional[QWidget], object_name: str
    ) -> List[QToolButton]:
        """Находит все кнопки с заданным именем в панели."""
        if not panel_widget:
            return []
        
        buttons: List[QToolButton] = []
        
        # Сначала ищем в bg_frame layout
        try:
            bg = getattr(panel_widget, "bg_frame", None)
            if isinstance(bg, QWidget):
                layout = bg.layout()
                if layout:
                    for index in range(layout.count()):
                        item = layout.itemAt(index)
                        if item:
                            widget = item.widget()
                            if (isinstance(widget, QToolButton) and 
                                widget.objectName() == object_name):
                                buttons.append(widget)
        except (RuntimeError, AttributeError) as e:
            logger.debug(f"Failed to iterate layout buttons: {e}")
        
        # Затем ищем через findChildren для подстраховки
        try:
            for button in panel_widget.findChildren(QToolButton, object_name):
                if button not in buttons:
                    buttons.append(button)
        except (RuntimeError, AttributeError) as e:
            logger.debug(f"Failed to find child buttons: {e}")
        
        return buttons

    def set_visible_count(
        self, panel_widget: Optional[QWidget], buttons: List[QToolButton], count: int
    ) -> int:
        """Устанавливает количество видимых кнопок в панели."""
        if not buttons:
            self._ensure_panel_visible(panel_widget)
            return 0
        
        visible = max(0, min(count, len(buttons)))
        
        # Безопасно устанавливаем видимость кнопок
        for index, button in enumerate(buttons):
            should_be_visible = index < visible
            try:
                if button.isVisible() != should_be_visible:
                    button.setVisible(should_be_visible)
            except (RuntimeError, AttributeError) as e:
                logger.debug(f"Failed to set button visibility: {e}")
        
        self._ensure_panel_visible(panel_widget)
        return visible

    def apply_counts(
        self,
        panel_states: Iterable[PanelState],
        counts: dict[str, int],
    ) -> dict[str, int]:
        """Применяет количество видимых кнопок ко всем панелям.
        
        Примечание: Управление размерами панелей теперь делегировано PanelSizeManager.
        Этот метод отвечает только за видимость кнопок.
        """
        applied: dict[str, int] = {}
        for state in panel_states:
            visible = self.set_visible_count(
                state.widget,
                state.buttons,
                counts.get(state.definition.label, 0),
            )
            applied[state.definition.label] = visible
        return applied

    # Метод _apply_panel_width_bounds удален - теперь используется PanelSizeManager

    def apply_with_animation(
        self,
        panel: Optional[QWidget],
        buttons: List[QToolButton],
        target_visible: int,
        duration_ms: int,
        easing,
    ) -> int:
        """Применяет изменения видимости с анимацией.
        
        Примечание: Анимация размеров панели теперь должна управляться через PanelSizeManager.
        Этот метод отвечает только за анимацию видимости кнопок.
        """
        if not panel:
            return 0
        
        target_visible = max(0, min(target_visible, len(buttons)))
        group = QParallelAnimationGroup(panel)
        any_animation = False

        # Анимируем видимость кнопок
        for index, button in enumerate(buttons):
            need_visible = index < target_visible
            current_visible = button.isVisible()
            
            if need_visible == current_visible:
                continue  # Нет изменений
            
            try:
                effect = button.graphicsEffect()
                if not isinstance(effect, QGraphicsOpacityEffect):
                    effect = QGraphicsOpacityEffect(button)
                    button.setGraphicsEffect(effect)
                
                if need_visible and not current_visible:
                    # Показываем кнопку с fade-in
                    button.setVisible(True)
                    effect.setOpacity(0.0)
                    animation = QPropertyAnimation(effect, b"opacity")
                    animation.setDuration(duration_ms)
                    animation.setEasingCurve(easing)
                    animation.setStartValue(0.0)
                    animation.setEndValue(1.0)
                    group.addAnimation(animation)
                    any_animation = True
                    
                elif not need_visible and current_visible:
                    # Скрываем кнопку с fade-out
                    effect.setOpacity(1.0)
                    animation = QPropertyAnimation(effect, b"opacity")
                    animation.setDuration(duration_ms)
                    animation.setEasingCurve(easing)
                    animation.setStartValue(1.0)
                    animation.setEndValue(0.0)

                    def _hide_button(btn: QToolButton = button) -> None:
                        try:
                            btn.setVisible(False)
                        except (RuntimeError, AttributeError):
                            pass

                    animation.finished.connect(_hide_button)
                    group.addAnimation(animation)
                    any_animation = True
                    
            except (RuntimeError, AttributeError) as e:
                logger.debug(f"Failed to animate button visibility: {e}")

        if any_animation:
            group.start()
        return target_visible

    def _ensure_panel_visible(self, panel_widget: Optional[QWidget]) -> None:
        """Обеспечивает видимость панели и обновляет её геометрию."""
        if panel_widget is None:
            return
        
        try:
            if not panel_widget.isVisible():
                panel_widget.setVisible(True)
        except (RuntimeError, AttributeError) as e:
            logger.debug(f"Failed to set panel visible: {e}")
        
        try:
            panel_widget.updateGeometry()
        except (RuntimeError, AttributeError) as e:
            logger.debug(f"Failed to update panel geometry: {e}")
    
    def get_stats(self) -> dict[str, int]:
        """Возвращает статистику менеджера видимости для мониторинга."""
        return {
            "version": 2,  # Версия улучшенного менеджера
            "features": {
                "safe_operations": 1,
                "improved_logging": 1,
                "separated_size_management": 1,
            }
        }
