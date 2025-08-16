from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QLineEdit,
    QMenu,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QToolButton,
)

from app.utils.ui.icon.icon_operations.cache_proxy import icon_cache
from app.utils.ui.icon.path_service import get_current_theme


def apply_uniform_height(dialog: QDialog):
    """
    Finds specific widget types within a dialog and sets their height to a uniform 32px.
    Excludes special-cased QToolButtons used for link type selection.
    """
    widgets_to_resize = dialog.findChildren((QLineEdit, QComboBox, QPushButton, QToolButton, QSpinBox))
    for widget in widgets_to_resize:
        # Exclude the large link type selector buttons in LinkDialog
        if isinstance(widget, QToolButton) and widget.property("link_type"):
            continue
        widget.setFixedHeight(32)
        if isinstance(widget, QPushButton):
            try:
                base_size = dialog.font().pointSize()
                f = widget.font()
                f.setPointSize(base_size)
                widget.setFont(f)
            except Exception:
                # Fall back to leaving the current font as-is if something goes wrong
                pass


def create_russian_context_menu(widget):
    menu = QMenu(widget)
    
    # Получаем текущую тему для иконок (единый источник)
    theme = get_current_theme()
    
    # Создаем действия с иконками
    undo_action = menu.addAction(icon_cache.get_icon('undo', theme, 'context_menu'), "Отменить")
    undo_action.triggered.connect(widget.undo)
    undo_action.setShortcut("Ctrl+Z")
    
    redo_action = menu.addAction(icon_cache.get_icon('redo', theme, 'context_menu'), "Повторить")
    redo_action.triggered.connect(widget.redo)
    redo_action.setShortcut("Ctrl+Y")
    
    menu.addSeparator()
    
    cut_action = menu.addAction(icon_cache.get_icon('cut', theme, 'context_menu'), "Вырезать")
    cut_action.triggered.connect(widget.cut)
    cut_action.setShortcut("Ctrl+X")
    
    copy_action = menu.addAction(icon_cache.get_icon('copy', theme, 'context_menu'), "Копировать")
    copy_action.triggered.connect(widget.copy)
    copy_action.setShortcut("Ctrl+C")
    
    paste_action = menu.addAction(icon_cache.get_icon('paste', theme, 'context_menu'), "Вставить")
    paste_action.triggered.connect(widget.paste)
    paste_action.setShortcut("Ctrl+V")
    
    delete_action = menu.addAction(icon_cache.get_icon('delete', theme, 'context_menu'), "Удалить")
    delete_action.triggered.connect(widget.clear)
    delete_action.setShortcut("Del")
    
    menu.addSeparator()
    
    select_all_action = menu.addAction(icon_cache.get_icon('select_all', theme, 'context_menu'), "Выделить всё")
    select_all_action.triggered.connect(widget.selectAll)
    select_all_action.setShortcut("Ctrl+A")
    
    return menu

class BaseDialog(QDialog):
    """
    A base dialog class that applies uniform widget heights when shown.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._styles_applied = False

    def showEvent(self, event):
        """
        Overrides the show event to apply styles just before the dialog is displayed.
        """
        if not self._styles_applied:
            apply_uniform_height(self)
            self._apply_button_focus_style()
            self._apply_tab_behavior()
            self._styles_applied = True
            self._setup_russian_context_menus()
        super().showEvent(event)

    def _setup_russian_context_menus(self):
        for widget in self.findChildren((QLineEdit, QTextEdit)):
            widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            widget.customContextMenuRequested.connect(
                lambda pos, w=widget: create_russian_context_menu(w).popup(w.mapToGlobal(pos))
            )

    def _apply_button_focus_style(self):
        """Applies a unified focus style for push/tool buttons to avoid dotted outline on Windows.
        Replaces it with a clear solid border for focused state, matching input focus visuals.
        """
        # Keep any existing stylesheet and append our rules
        current = self.styleSheet() or ""
        focus_qss = (
            "QPushButton:focus {\n"
            "    outline: 0;\n"
            "    border: 1px solid rgba(93, 169, 255, 0.9);\n"
            "}\n"
            "QToolButton:focus {\n"
            "    outline: 0;\n"
            "    border: 1px solid rgba(93, 169, 255, 0.9);\n"
            "}\n"
        )
        # Avoid duplicating rules if showEvent happens multiple times
        if focus_qss not in current:
            self.setStyleSheet(current + ("\n" if current else "") + focus_qss)

    def _apply_tab_behavior(self):
        """Make multi-line text edits pass Tab to focus navigation instead of inserting a tab symbol."""
        try:
            for te in self.findChildren(QTextEdit):
                te.setTabChangesFocus(True)
        except Exception:
            pass
