import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QUndoStack, QUndoCommand
from unittest.mock import Mock, MagicMock

app = QApplication.instance() or QApplication(sys.argv)

from app.controllers.ui.undo.commands_structure import DeleteCategoryCmd, PasteCategoriesCmd
from app.controllers.ui.undo.stack import UndoManager

print("Test merge ready.")
