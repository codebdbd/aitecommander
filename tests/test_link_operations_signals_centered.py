import pytest
from PyQt6.QtCore import QObject

from app.controllers.ui.dialogs.link_operations_controller import LinkOperationsController


class DummyDb:
    pass


class DummyUndo:
    def macro(self, *_args, **_kwargs):
        class _Ctx:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False
        return _Ctx()

    def push(self, _cmd):
        return None


class DummyMain(QObject):
    def get_current_category_id(self):
        return 1


@pytest.fixture()
def ctrl(qtbot):
    return LinkOperationsController(db=DummyDb(), undo_stack=DummyUndo(), main_window=DummyMain())


def test_on_link_opened_emits_recents_and_links_changed_once(ctrl, qtbot):
    recents_count = {"n": 0}
    links_changed = {"args": []}

    ctrl.recents_changed.connect(lambda: recents_count.__setitem__("n", recents_count["n"] + 1))
    ctrl.links_changed.connect(lambda cat_id: links_changed["args"].append(cat_id))

    ctrl.on_link_opened({"category_id": 5})

    assert recents_count["n"] == 1
    assert links_changed["args"] == [5]


def test_on_favorite_toggled_emits_favorites_and_links_changed_once(ctrl, qtbot):
    fav_count = {"n": 0}
    links_changed = {"args": []}

    ctrl.favorites_changed.connect(lambda: fav_count.__setitem__("n", fav_count["n"] + 1))
    ctrl.links_changed.connect(lambda cat_id: links_changed["args"].append(cat_id))

    ctrl.on_favorite_toggled(7)
    assert fav_count["n"] == 1
    assert links_changed["args"] == [7]

    # Без валидной категории links_changed не эмитится
    links_changed["args"].clear()
    ctrl.on_favorite_toggled(None)
    assert fav_count["n"] == 2  # только favorites_changed
    assert links_changed["args"] == []


def test_on_link_updated_emits_recents_and_links_changed_once(ctrl, qtbot):
    recents_count = {"n": 0}
    links_changed = {"args": []}

    ctrl.recents_changed.connect(lambda: recents_count.__setitem__("n", recents_count["n"] + 1))
    ctrl.links_changed.connect(lambda cat_id: links_changed["args"].append(cat_id))

    ctrl.on_link_updated({"category_id": 3})

    assert recents_count["n"] == 1
    assert links_changed["args"] == [3]


def test_on_links_deleted_emits_all(ctrl, qtbot):
    recents_count = {"n": 0}
    links_changed = {"args": []}
    deleted_payloads = []

    ctrl.recents_changed.connect(lambda: recents_count.__setitem__("n", recents_count["n"] + 1))
    ctrl.links_changed.connect(lambda cat_id: links_changed["args"].append(cat_id))
    ctrl.link_deleted.connect(lambda payload: deleted_payloads.append(payload))

    links = [
        {"id": 1, "category_id": 9},
        {"id": 2, "category_id": 9},
        {"id": 3, "category_id": 9},
    ]

    ctrl.on_links_deleted(links)

    assert recents_count["n"] == 1
    assert links_changed["args"] == [9]
    assert [p.get("id") for p in deleted_payloads] == [1, 2, 3]
