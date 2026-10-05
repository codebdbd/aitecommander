import sys
import os

from PyQt6.QtWidgets import QApplication

app = QApplication.instance() or QApplication(sys.argv)

from app.core.settings_manager import SettingsManager
from app.controllers.ui.theme_controller import ThemeController
from app.views.windows.main_window import MainWindow

settings = SettingsManager()
theme_ctrl = ThemeController(settings)
window = MainWindow(settings=settings, theme_ctrl=theme_ctrl)

undo_stack = getattr(window, "undo_stack", None)
print("Initial undo_stack count:", undo_stack.stack.count() if undo_stack else None)

# Inspect what happens when user cuts a category
ac = getattr(window, "action_controller", None)
print("ActionController:", ac)

# Let's check cut action
cut_action = getattr(window, "cut_action", None)
print("Cut action:", cut_action)
print("Undo action:", getattr(window, "undo_action", None))

window.close()
