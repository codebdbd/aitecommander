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
    """Decorator that guards Qt widget operations.

    Fix: automatically verifies that the widget is not ``None`` or deleted to
    avoid ``RuntimeError`` on dangling Qt objects.
    """
    @wraps(func)
    def wrapper(self, widget: Optional[QWidget], *args, **kwargs):
        if widget is None or self._is_deleted(widget):
            logger.debug(f"{func.__name__}: widget is None or deleted")
            # Return a sensible default
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
    """Manage panel buttons and their animations.

    Responsibilities:
    - Find panel buttons
    - Toggle button visibility
    - Animate show/hide transitions
    - Constrain panel widths
    """

    def __init__(self, width_calculator: WidthCalculator, parent: Optional[QWidget] = None):
        """Initialize panel-visibility manager.

        Fix: include ``AccessibilityManager`` for complete accessibility support.

        Args:
            width_calculator: Panel width calculator.
            parent: Parent widget used by the accessibility manager.
        """
        self._width_calculator = width_calculator
        # Fix: keep references to active animations to prevent GC collection
        self._active_animations: List[QParallelAnimationGroup] = []
        # Fix: instantiate accessibility manager
        self._accessibility_manager = AccessibilityManager(parent)

    def iter_buttons(
        self, panel_widget: Optional[QWidget], object_name: str
    ) -> List[QToolButton]:
        """Find all buttons with the given ``objectName`` inside a panel.

        Fix: add checks for deleted objects.

        Args:
            panel_widget: Panel widget.
            object_name: Target button ``objectName`` to locate.

        Returns:
            List of matching buttons.
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
        
        # Fallback: search via ``findChildren``
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
        """Set the number of visible buttons within the panel.

        Fix: protect against deleted widgets via ``@safe_widget_operation`` and set
        baseline accessibility metadata for screen readers.
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
                    
                    # Fix: baseline accessibility attributes (full setup occurs in
                    # ``AccessibilityManager`` via ``apply_counts``)
                    if is_visible:
                        button.setAccessibleDescription(
                            f"Button {index + 1} of {visible} visible buttons"
                        )
                    else:
                        button.setAccessibleDescription("Hidden button")
                except (RuntimeError, AttributeError):
                    pass
        
        self._ensure_panel_visible(panel_widget)
        
        # Fix: refresh focus after visibility changes
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
        """Apply visible button counts across all panels.

        Fix: configure full accessibility metadata per panel.
        """
        applied: dict[str, int] = {}
        shortcut_counter = 1  # Counter for keyboard shortcuts
        
        for state in panel_states:
            visible = self.set_visible_count(
                state.widget,
                state.buttons,
                counts.get(state.definition.label, 0),
            )
            # Apply panel width bounds after adjusting button visibility
            self._apply_panel_width_bounds(state.widget, state.buttons, visible)
            applied[state.definition.label] = visible
            
            # Fix: configure full accessibility for the panel
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
                
                # Increment counter for the next panel
                shortcut_counter += visible
                
            except Exception as e:
                logger.debug("Failed to setup accessibility for %s: %s", state.definition.label, e)
        
        return applied

    @safe_widget_operation
    def _apply_panel_width_bounds(
        self, panel: Optional[QWidget], buttons: List[QToolButton], visible: int
    ) -> None:
        """Set panel width bounds based on visible buttons.

        Fix: guard execution with ``@safe_widget_operation`` to handle deleted widgets.
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
                    # Collect current visible buttons and their ``sizeHint`` values
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
        """Animate button visibility changes.

        Args:
            panel: Panel widget.
            buttons: Button list to animate.
            target_visible: Desired visible button count.
            duration_ms: Animation duration in milliseconds.
            easing: Easing curve for the animation.

        Returns:
            Actual number of visible buttons.
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

                # Fix: use weak references to avoid memory leaks when hiding buttons
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

        if any_animation:
            # Fix: retain reference to the animation group
            self._active_animations.append(group)
            try:
                # Fix: use weak references for cleanup to avoid circular references
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
                # Fix: perform cleanup on failure
                self._cleanup_animation(group)
        return target_visible
    
    def _create_hide_callback(self, button: QToolButton):
        """Create a hide callback that avoids memory leaks."""
        def hide_button():
            try:
                if button and not self._is_deleted(button):
                    button.setVisible(False)
            except (RuntimeError, AttributeError) as e:
                logger.debug("Failed to hide button: %s", e)
        return hide_button
    
    def _safe_hide_button(self, button: QToolButton) -> None:
        """Hide a button safely."""
        try:
            if button and not self._is_deleted(button):
                button.setVisible(False)
        except (RuntimeError, AttributeError):
            pass
    
    def _cleanup_animation(self, group: QParallelAnimationGroup) -> None:
        """Remove a completed animation group from the active list."""
        try:
            if group in self._active_animations:
                self._active_animations.remove(group)
        except (ValueError, RuntimeError):
            pass
    
    def _is_deleted(self, obj) -> bool:
        """Check whether a Qt object has been deleted."""
        try:
            from sip import isdeleted
            return isdeleted(obj)
        except ImportError:
            return False

    @safe_widget_operation
    def _ensure_panel_visible(self, panel_widget: Optional[QWidget]) -> None:
        """Ensure that the panel itself stays visible.

        Fix: guard the call with ``@safe_widget_operation`` to handle deleted widgets.
        """
        try:
            panel_widget.setVisible(True)
        except (RuntimeError, AttributeError):
            pass
        try:
            panel_widget.updateGeometry()
        except (RuntimeError, AttributeError):
            pass
