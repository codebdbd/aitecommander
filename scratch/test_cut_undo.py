import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QUndoStack
from unittest.mock import Mock, MagicMock

# Create QApplication if not running
app = QApplication.instance() or QApplication(sys.argv)

from app.controllers.ui.action_controller import ActionController
from app.controllers.ui.undo.commands_structure import DeleteCategoryCmd, BatchDeleteCategoriesCmd, PasteCategoriesCmd
from app.controllers.ui.undo.stack import UndoManager

# Let's inspect UndoManager
main_mock = Mock()
undo_mgr = UndoManager()
main_mock.undo_stack = undo_mgr

print("Initial undo stack count:", undo_mgr.stack.count())

# Let's test DeleteCategoryCmd
cat_data = {"id": 10, "section_id": 1, "name": "TestCat"}
biz_mock = Mock()
biz_mock.structure_service.export_category_tree.return_value = {"category": cat_data, "links": []}
biz_mock.structure_service.delete_category.return_value = Mock(is_success=lambda: True, value={"id": 10}, error=None, invalidate_regions=(), notifications=())
biz_mock.get_category_data.return_value = cat_data

cmd = DeleteCategoryCmd(cat_data, main_mock, business=biz_mock, undo_manager=undo_mgr)
undo_mgr.push(cmd)

print("After DeleteCategoryCmd push count:", undo_mgr.stack.count())
print("Can undo:", undo_mgr.can_undo())

undo_mgr.undo()
print("After undo count:", undo_mgr.stack.count(), "index:", undo_mgr.stack.index())
