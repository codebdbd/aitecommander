"""Менеджер accessibility для TopBar компонентов.

ИСПРАВЛЕНИЕ: Добавлен полноценный менеджер accessibility с поддержкой:
- Keyboard navigation (Tab, Arrow keys, Alt+Number)
- Screen reader descriptions
- Focus management
- ARIA-like атрибуты
"""

from __future__ import annotations

import logging
from typing import List, Optional

from PyQt6.QtCore import Qt, QObject, QEvent
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import QToolButton, QWidget

logger = logging.getLogger(__name__)


class AccessibilityManager(QObject):
    """Управляет accessibility для TopBar панелей.
    
    ИСПРАВЛЕНИЕ: Централизованное управление доступностью:
    - Keyboard shortcuts (Alt+1-9 для быстрого доступа)
    - Tab navigation между панелями
    - Arrow keys для навигации внутри панели
    - Screen reader descriptions
    - Focus management при изменении видимости
    
    Example:
        >>> manager = AccessibilityManager(window)
        >>> manager.setup_panel_accessibility(
        ...     panel_widget, 
        ...     buttons, 
        ...     "Recent Links",
        ...     visible_count=5
        ... )
    """
    
    def __init__(self, parent: Optional[QWidget] = None):
        """Инициализирует менеджер accessibility.
        
        Args:
            parent: Родительский виджет (обычно главное окно)
        """
        super().__init__(parent)
        self._shortcuts: List[QShortcut] = []
        self._focused_panel: Optional[QWidget] = None
        self._focused_button_index: int = 0
    
    def setup_panel_accessibility(
        self,
        panel: QWidget,
        buttons: List[QToolButton],
        panel_name: str,
        visible_count: int,
        start_shortcut_number: int = 1,
    ) -> None:
        """Настраивает accessibility для панели.
        
        ИСПРАВЛЕНИЕ: Комплексная настройка доступности:
        - Устанавливает accessible names и descriptions
        - Создает keyboard shortcuts
        - Настраивает tab order
        - Устанавливает focus policy
        
        Args:
            panel: Виджет панели
            buttons: Список кнопок в панели
            panel_name: Человекочитаемое имя панели (для screen readers)
            visible_count: Количество видимых кнопок
            start_shortcut_number: Начальный номер для shortcuts (Alt+N)
        """
        if not panel or not buttons:
            return
        
        try:
            # Устанавливаем accessible name для панели
            panel.setAccessibleName(panel_name)
            panel.setAccessibleDescription(
                f"{panel_name} panel with {visible_count} visible items"
            )
            
            # Настраиваем каждую кнопку
            for index, button in enumerate(buttons):
                is_visible = index < visible_count
                
                # Accessible name и description
                button.setAccessibleName(f"{panel_name} item {index + 1}")
                
                if is_visible:
                    button.setAccessibleDescription(
                        f"Button {index + 1} of {visible_count} in {panel_name}. "
                        f"Press Enter to activate, Arrow keys to navigate."
                    )
                    
                    # Focus policy - только видимые кнопки могут получить фокус
                    button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
                    
                    # Keyboard shortcut для первых 9 кнопок
                    shortcut_num = start_shortcut_number + index
                    if shortcut_num <= 9:
                        self._create_button_shortcut(
                            button, 
                            shortcut_num, 
                            f"{panel_name} item {index + 1}"
                        )
                else:
                    button.setAccessibleDescription(
                        f"Hidden button {index + 1} in {panel_name}"
                    )
                    # Скрытые кнопки не должны получать фокус
                    button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            
            # Устанавливаем tab order для видимых кнопок
            self._setup_tab_order(buttons[:visible_count])
            
            logger.debug(
                "Accessibility setup for %s: %d visible buttons with shortcuts",
                panel_name,
                visible_count
            )
            
        except (RuntimeError, AttributeError) as e:
            logger.warning("Failed to setup accessibility for %s: %s", panel_name, e)
    
    def _create_button_shortcut(
        self, 
        button: QToolButton, 
        number: int, 
        description: str
    ) -> None:
        """Создает keyboard shortcut для кнопки.
        
        Args:
            button: Кнопка для привязки shortcut
            number: Номер shortcut (1-9)
            description: Описание для логирования
        """
        try:
            # Alt+Number для активации кнопки
            shortcut = QShortcut(QKeySequence(f"Alt+{number}"), button)
            shortcut.activated.connect(button.click)
            shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            
            self._shortcuts.append(shortcut)
            
            # Добавляем информацию о shortcut в tooltip
            current_tooltip = button.toolTip()
            shortcut_info = f" (Alt+{number})"
            if current_tooltip and shortcut_info not in current_tooltip:
                button.setToolTip(current_tooltip + shortcut_info)
            elif not current_tooltip:
                button.setToolTip(f"{description}{shortcut_info}")
                
        except (RuntimeError, AttributeError) as e:
            logger.debug("Failed to create shortcut for button: %s", e)
    
    def _setup_tab_order(self, buttons: List[QToolButton]) -> None:
        """Устанавливает порядок tab navigation для кнопок.
        
        Args:
            buttons: Список видимых кнопок в порядке tab navigation
        """
        if len(buttons) < 2:
            return
        
        try:
            for i in range(len(buttons) - 1):
                QWidget.setTabOrder(buttons[i], buttons[i + 1])
        except (RuntimeError, AttributeError) as e:
            logger.debug("Failed to setup tab order: %s", e)
    
    def handle_arrow_navigation(
        self, 
        event: QEvent, 
        buttons: List[QToolButton], 
        current_button: QToolButton
    ) -> bool:
        """Обрабатывает навигацию стрелками внутри панели.
        
        ИСПРАВЛЕНИЕ: Добавлена поддержка Arrow keys для навигации.
        
        Args:
            event: Событие клавиатуры
            buttons: Список всех кнопок в панели
            current_button: Текущая кнопка с фокусом
            
        Returns:
            True если событие обработано, False иначе
        """
        if event.type() != QEvent.Type.KeyPress:
            return False
        
        try:
            key = event.key()
            
            # Находим индекс текущей кнопки
            try:
                current_index = buttons.index(current_button)
            except ValueError:
                return False
            
            # Определяем новый индекс на основе нажатой клавиши
            new_index = current_index
            
            if key == Qt.Key.Key_Right or key == Qt.Key.Key_Down:
                # Следующая кнопка
                new_index = current_index + 1
                if new_index >= len(buttons):
                    new_index = 0  # Wrap around
            
            elif key == Qt.Key.Key_Left or key == Qt.Key.Key_Up:
                # Предыдущая кнопка
                new_index = current_index - 1
                if new_index < 0:
                    new_index = len(buttons) - 1  # Wrap around
            
            elif key == Qt.Key.Key_Home:
                # Первая кнопка
                new_index = 0
            
            elif key == Qt.Key.Key_End:
                # Последняя кнопка
                new_index = len(buttons) - 1
            
            else:
                return False
            
            # Переключаем фокус на новую кнопку
            if new_index != current_index and 0 <= new_index < len(buttons):
                new_button = buttons[new_index]
                if new_button.isVisible() and new_button.isEnabled():
                    new_button.setFocus(Qt.FocusReason.KeyboardFocusReason)
                    return True
            
        except (RuntimeError, AttributeError) as e:
            logger.debug("Failed to handle arrow navigation: %s", e)
        
        return False
    
    def update_focus_after_visibility_change(
        self, 
        buttons: List[QToolButton], 
        visible_count: int
    ) -> None:
        """Обновляет фокус после изменения видимости кнопок.
        
        ИСПРАВЛЕНИЕ: Управление фокусом при динамическом изменении видимости.
        Если текущая кнопка с фокусом стала невидимой, переключаем фокус
        на первую видимую кнопку.
        
        Args:
            buttons: Список всех кнопок
            visible_count: Новое количество видимых кнопок
        """
        if not buttons or visible_count <= 0:
            return
        
        try:
            # Проверяем, есть ли фокус на какой-либо кнопке
            focused_button = None
            for button in buttons:
                if button.hasFocus():
                    focused_button = button
                    break
            
            # Если фокус на невидимой кнопке, переключаем на первую видимую
            if focused_button and not focused_button.isVisible():
                first_visible = buttons[0] if visible_count > 0 else None
                if first_visible and first_visible.isVisible():
                    first_visible.setFocus(Qt.FocusReason.OtherFocusReason)
                    logger.debug("Focus moved to first visible button after visibility change")
        
        except (RuntimeError, AttributeError) as e:
            logger.debug("Failed to update focus: %s", e)
    
    def cleanup(self) -> None:
        """Очищает ресурсы accessibility manager.
        
        ИСПРАВЛЕНИЕ: Удаляет все созданные shortcuts и отключает обработчики.
        """
        try:
            # Удаляем все shortcuts
            for shortcut in self._shortcuts:
                try:
                    shortcut.setEnabled(False)
                    shortcut.deleteLater()
                except RuntimeError:
                    pass
            
            self._shortcuts.clear()
            self._focused_panel = None
            
            logger.debug("AccessibilityManager cleanup completed")
        
        except Exception as e:
            logger.warning("Error during AccessibilityManager cleanup: %s", e)
    
    def __del__(self):
        """Деструктор с безопасной очисткой."""
        try:
            self.cleanup()
        except Exception:
            pass  # Игнорируем ошибки в деструкторе
