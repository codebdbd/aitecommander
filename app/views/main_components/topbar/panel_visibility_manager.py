from __future__ import annotations

import logging
from functools import wraps
from typing import Callable, Iterable, List, Optional

from PyQt6.QtCore import QParallelAnimationGroup, QPropertyAnimation
from PyQt6.QtWidgets import (
    QGraphicsOpacityEffect,
    QToolButton,
    QWidget,
)

from .panel_state import PanelState
from .width_calculator import WidthCalculator
from .accessibility_manager import AccessibilityManager

logger = logging.getLogger(__name__)


def safe_widget_operation(func: Callable) -> Callable:
    """Декоратор для безопасных операций с Qt-виджетами.
    
    ИСПРАВЛЕНИЕ: Автоматически проверяет виджет на None и deleted состояние.
    Предотвращает RuntimeError при работе с удаленными Qt-объектами.
    """
    @wraps(func)
    def wrapper(self, widget: Optional[QWidget], *args, **kwargs):
        if widget is None or self._is_deleted(widget):
            logger.debug(f"{func.__name__}: widget is None or deleted")
            # Возвращаем разумное значение по умолчанию
            if func.__name__.startswith('get'):
                return None
            elif func.__name__.startswith('set') or func.__name__.startswith('apply'):
                return 0
            return None
        try:
            return func(self, widget, *args, **kwargs)
        except (RuntimeError, AttributeError) as e:
            logger.debug(f"{func.__name__}: operation failed - {e}")
            if func.__name__.startswith('get'):
                return None
            return 0
    return wrapper


class PanelVisibilityManager:
    """Управляет кнопками панелей и их анимацией.
    
    Отвечает за:
    - Поиск кнопок в панелях
    - Установку видимости кнопок
    - Анимацию появления/скрытия кнопок
    - Управление шириной панелей
    """

    def __init__(self, width_calculator: WidthCalculator, parent: Optional[QWidget] = None):
        """Инициализирует менеджер видимости панелей.
        
        ИСПРАВЛЕНИЕ: Добавлен AccessibilityManager для полной поддержки доступности.
        
        Args:
            width_calculator: Калькулятор ширины панелей
            parent: Родительский виджет (для accessibility manager)
        """
        self._width_calculator = width_calculator
        # ИСПРАВЛЕНИЕ: Сохраняем ссылки на активные анимации для предотвращения GC
        self._active_animations: List[QParallelAnimationGroup] = []
        # ИСПРАВЛЕНИЕ: Добавлен менеджер accessibility
        self._accessibility_manager = AccessibilityManager(parent)

    def iter_buttons(
        self, panel_widget: Optional[QWidget], object_name: str
    ) -> List[QToolButton]:
        """Находит все кнопки с заданным objectName в панели.
        
        ИСПРАВЛЕНИЕ: Добавлены проверки на удаленные объекты.
        
        Args:
            panel_widget: Виджет панели
            object_name: Имя объекта кнопки для поиска
            
        Returns:
            Список найденных кнопок
        """
        if not panel_widget or self._is_deleted(panel_widget):
            return []
        
        buttons: List[QToolButton] = []
        bg = getattr(panel_widget, "bg_frame", None)
        
        if bg and isinstance(bg, QWidget) and not self._is_deleted(bg):
            try:
                layout = bg.layout()
                if layout:
                    for index in range(layout.count()):
                        item = layout.itemAt(index)
                        if item:
                            widget = item.widget()
                            if (isinstance(widget, QToolButton) and 
                                not self._is_deleted(widget) and
                                widget.objectName() == object_name):
                                buttons.append(widget)
            except (RuntimeError, AttributeError):
                pass
        
        # Fallback: поиск через findChildren
        try:
            for button in panel_widget.findChildren(QToolButton, object_name):
                if button not in buttons and not self._is_deleted(button):
                    buttons.append(button)
        except (RuntimeError, AttributeError):
            pass
        
        return buttons

    @safe_widget_operation
    def set_visible_count(
        self, panel_widget: Optional[QWidget], buttons: List[QToolButton], count: int
    ) -> int:
        """Устанавливает количество видимых кнопок в панели.
        
        ИСПРАВЛЕНИЕ: Добавлен декоратор @safe_widget_operation для защиты от deleted widgets.
        ИСПРАВЛЕНИЕ: Добавлены accessibility атрибуты для screen readers.
        """
        if not buttons:
            self._ensure_panel_visible(panel_widget)
            return 0
        visible = max(0, min(count, len(buttons)))
        for index, button in enumerate(buttons):
            if not self._is_deleted(button):
                try:
                    is_visible = index < visible
                    button.setVisible(is_visible)
                    
                    # ИСПРАВЛЕНИЕ: Базовые accessibility атрибуты
                    # (полная настройка через AccessibilityManager в apply_counts)
                    if is_visible:
                        button.setAccessibleDescription(
                            f"Button {index + 1} of {visible} visible buttons"
                        )
                    else:
                        button.setAccessibleDescription("Hidden button")
                except (RuntimeError, AttributeError):
                    pass
        
        self._ensure_panel_visible(panel_widget)
        
        # ИСПРАВЛЕНИЕ: Обновляем фокус после изменения видимости
        try:
            self._accessibility_manager.update_focus_after_visibility_change(buttons, visible)
        except Exception as e:
            logger.debug("Failed to update focus: %s", e)
        
        return visible

    def apply_counts(
        self,
        panel_states: Iterable[PanelState],
        counts: dict[str, int],
    ) -> dict[str, int]:
        """Применяет количество видимых кнопок для всех панелей.
        
        ИСПРАВЛЕНИЕ: Добавлена полная настройка accessibility для каждой панели.
        """
        applied: dict[str, int] = {}
        shortcut_counter = 1  # Счетчик для keyboard shortcuts
        
        for state in panel_states:
            visible = self.set_visible_count(
                state.widget,
                state.buttons,
                counts.get(state.definition.label, 0),
            )
            # Применяем ширину панели ПОСЛЕ установки видимости кнопок
            self._apply_panel_width_bounds(state.widget, state.buttons, visible)
            applied[state.definition.label] = visible
            
            # ИСПРАВЛЕНИЕ: Настраиваем полную accessibility для панели
            try:
                panel_name_map = {
                    "recent": "Recent Links",
                    "fav": "Favorites",
                    "quick": "Quick Add",
                }
                panel_name = panel_name_map.get(state.definition.label, state.definition.label)
                
                self._accessibility_manager.setup_panel_accessibility(
                    state.widget,
                    state.buttons,
                    panel_name,
                    visible,
                    start_shortcut_number=shortcut_counter
                )
                
                # Увеличиваем счетчик для следующей панели
                shortcut_counter += visible
                
            except Exception as e:
                logger.debug("Failed to setup accessibility for %s: %s", state.definition.label, e)
        
        return applied

    @safe_widget_operation
    def _apply_panel_width_bounds(
        self, panel: Optional[QWidget], buttons: List[QToolButton], visible: int
    ) -> None:
        """Устанавливает ширину панели на основе видимых кнопок.
        
        ИСПРАВЛЕНИЕ: Добавлен декоратор @safe_widget_operation для защиты от deleted widgets.
        """
        try:
            panel.setMinimumWidth(0)
            max_width = (
                self._width_calculator.panel_width(panel, buttons, visible)
                if visible > 0
                else 0
            )
            panel.setMaximumWidth(max_width)
            # One-time diagnostics for favorites/quick panels to catch sizing root cause
            try:
                name = getattr(panel, 'objectName', lambda: '')() or ''
            except Exception:
                name = ''
            low = name.lower()
            if ('fav' in low or 'quick' in low) and not bool(getattr(panel, '_dbg_logged_once', False)):
                try:
                    # Collect current visible buttons and their sizeHints
                    visible_btns = []
                    for i, b in enumerate(buttons):
                        try:
                            if b.isVisible():
                                visible_btns.append(int(b.sizeHint().width()))
                        except Exception:
                            pass
                    panel_hint = 0
                    try:
                        panel_hint = int(panel.sizeHint().width())
                    except Exception:
                        pass
                    logger.info(
                        "[TopbarDiag:%s] visible=%s widths=%s computed_max=%s panel_hint=%s margins(panel)=%s",
                        low,
                        visible,
                        visible_btns,
                        max_width,
                        panel_hint,
                        getattr(panel, 'contentsMargins', lambda: None)(),
                    )
                except Exception:
                    pass
                try:
                    setattr(panel, '_dbg_logged_once', True)
                except Exception:
                    pass
        except (RuntimeError, AttributeError):
            pass

    def apply_with_animation(
        self,
        panel: Optional[QWidget],
        buttons: List[QToolButton],
        target_visible: int,
        duration_ms: int,
        easing,
    ) -> int:
        """Применяет видимость кнопок с анимацией.
        
        Args:
            panel: Виджет панели
            buttons: Список кнопок для анимации
            target_visible: Целевое количество видимых кнопок
            duration_ms: Длительность анимации в миллисекундах
            easing: Кривая сглаживания анимации
            
        Returns:
            Фактическое количество видимых кнопок
        """
        if not panel:
            return 0
        target_visible = max(0, min(target_visible, len(buttons)))
        group = QParallelAnimationGroup(panel)
        any_animation = False

        panel.setMinimumWidth(0)
        new_width = self._width_calculator.panel_width(panel, buttons, target_visible)
        old_width = int(panel.maximumWidth())
        if old_width != new_width:
            animation = QPropertyAnimation(panel, b"maximumWidth")
            animation.setDuration(duration_ms)
            animation.setEasingCurve(easing)
            animation.setStartValue(old_width)
            animation.setEndValue(new_width)
            group.addAnimation(animation)
            any_animation = True
        else:
            panel.setMaximumWidth(new_width)

        for index, button in enumerate(buttons):
            need_visible = index < target_visible
            current_visible = button.isVisible()
            effect = button.graphicsEffect()
            if not isinstance(effect, QGraphicsOpacityEffect):
                effect = QGraphicsOpacityEffect(button)
                button.setGraphicsEffect(effect)
            if need_visible and not current_visible:
                button.setVisible(True)
                effect.setOpacity(0.0)
                animation = QPropertyAnimation(effect, b"opacity")
                animation.setDuration(duration_ms)
                animation.setEasingCurve(easing)
                animation.setStartValue(0.0)
                animation.setEndValue(1.0)
                group.addAnimation(animation)
                any_animation = True
            elif (not need_visible) and current_visible:
                effect.setOpacity(1.0)
                animation = QPropertyAnimation(effect, b"opacity")
                animation.setDuration(duration_ms)
                animation.setEasingCurve(easing)
                animation.setStartValue(1.0)
                animation.setEndValue(0.0)

                # ИСПРАВЛЕНИЕ: Используем WeakMethod для избежания утечек памяти
                # Создаем слабую ссылку на button, чтобы не препятствовать GC
                try:
                    from weakref import ref
                    button_ref = ref(button)
                    
                    def hide_callback():
                        btn = button_ref()
                        if btn is not None and not self._is_deleted(btn):
                            try:
                                btn.setVisible(False)
                            except (RuntimeError, AttributeError):
                                pass
                    
                    animation.finished.connect(hide_callback)
                except Exception as e:
                    logger.debug("Failed to create hide callback: %s", e)
                
                group.addAnimation(animation)
                any_animation = True

        if any_animation:
            # ИСПРАВЛЕНИЕ: Сохраняем ссылку на группу анимаций
            self._active_animations.append(group)
            try:
                # ИСПРАВЛЕНИЕ: Используем WeakMethod для cleanup, чтобы избежать circular reference
                from weakref import ref
                group_ref = ref(group)
                
                def cleanup_callback():
                    grp = group_ref()
                    if grp is not None:
                        self._cleanup_animation(grp)
                
                group.finished.connect(cleanup_callback)
                group.start()
            except Exception as e:
                logger.warning("Failed to start animation group: %s", e)
                # ИСПРАВЛЕНИЕ: Очищаем при ошибке
                self._cleanup_animation(group)
        return target_visible
    
    def _create_hide_callback(self, button: QToolButton):
        """Создает callback для скрытия кнопки без утечек памяти."""
        def hide_button():
            try:
                if button and not self._is_deleted(button):
                    button.setVisible(False)
            except (RuntimeError, AttributeError) as e:
                logger.debug("Failed to hide button: %s", e)
        return hide_button
    
    def _safe_hide_button(self, button: QToolButton) -> None:
        """Безопасно скрывает кнопку."""
        try:
            if button and not self._is_deleted(button):
                button.setVisible(False)
        except (RuntimeError, AttributeError):
            pass
    
    def _cleanup_animation(self, group: QParallelAnimationGroup) -> None:
        """Удаляет завершенную анимацию из списка активных."""
        try:
            if group in self._active_animations:
                self._active_animations.remove(group)
        except (ValueError, RuntimeError):
            pass
    
    def _is_deleted(self, obj) -> bool:
        """Проверяет, удален ли Qt-объект."""
        try:
            from sip import isdeleted
            return isdeleted(obj)
        except ImportError:
            return False

    @safe_widget_operation
    def _ensure_panel_visible(self, panel_widget: Optional[QWidget]) -> None:
        """Гарантирует видимость панели.
        
        ИСПРАВЛЕНИЕ: Добавлен декоратор @safe_widget_operation для защиты от deleted widgets.
        """
        try:
            panel_widget.setVisible(True)
        except (RuntimeError, AttributeError):
            pass
        try:
            panel_widget.updateGeometry()
        except (RuntimeError, AttributeError):
            pass
