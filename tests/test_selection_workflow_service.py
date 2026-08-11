from __future__ import annotations

import unittest
from unittest.mock import Mock

from app.controllers.ui.structure.selection_workflow_service import (
    SelectionWorkflowService,
)


class TestSelectionWorkflowService(unittest.TestCase):
    def test_restore_category_selection_expands_target_section_before_select(self) -> None:
        tree = Mock()
        actions = Mock()
        service = SelectionWorkflowService(handler=None, tree=tree, actions=actions)

        selection_model = Mock()
        model = Mock()
        tree.model.return_value = model
        tree.selectionModel.return_value = selection_model

        root_index = Mock()
        root_index.isValid.return_value = False

        parent_index = Mock()
        parent_index.isValid.return_value = True
        parent_index.parent.return_value = root_index

        category_index = Mock()
        category_index.isValid.return_value = True
        category_index.parent.return_value = parent_index
        model.index_for.side_effect = [parent_index, category_index]

        result = service.restore_category_selection(42, target_section_id=10)

        self.assertIs(result, category_index)
        self.assertEqual(
            tree.expand.call_args_list,
            [
                ((parent_index,),),
                ((parent_index,),),
            ],
        )
        self.assertEqual(
            model.index_for.call_args_list,
            [
                (("section", 10),),
                (("category", 42),),
            ],
        )
        selection_model.setCurrentIndex.assert_called_once()
        tree.scrollTo.assert_called_once_with(category_index)
        actions.focus_tree.assert_called_once_with(use_scheduler=False)


if __name__ == "__main__":
    unittest.main()
