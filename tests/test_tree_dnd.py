# Tests for tree drag-drop

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.utils.ui.dnd import tree as tree_dnd


@pytest.fixture(autouse=True)
def restore_get_tree_tuple(monkeypatch):
    original = tree_dnd.get_tree_tuple
    yield
    monkeypatch.setattr(tree_dnd, "get_tree_tuple", original)


def test_handle_category_drop_index_uses_batch(monkeypatch):
    tree_widget = SimpleNamespace()
    model = SimpleNamespace(rowCount=lambda index: 7)
    tree_widget.model = lambda: model
    handler = tree_dnd.DragDropHandler(tree_widget)

    monkeypatch.setattr(
        tree_dnd.MimeDataParser,
        "extract_item_ids",
        staticmethod(lambda mime, fmt: [101, 202]),
    )

    fake_index = Mock()
    monkeypatch.setattr(
        tree_dnd, "get_tree_tuple", lambda index, depth=0: ("section", 55)
    )

    captured = {}

    def fake_move_categories(ids, section, base_row):
        captured["ids"] = ids
        captured["section"] = section
        captured["base_row"] = base_row
        return len(ids)

    monkeypatch.setattr(handler, "move_categories", fake_move_categories)

    handler._handle_category_drop_index(mime=object(), target_index=fake_index)

    assert captured == {"ids": [101, 202], "section": 55, "base_row": 7}
