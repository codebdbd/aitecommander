import types
import pytest

from app.views.tree_components.move_operations_handler import MoveOperationsHandler


class _IndexStub:
    def __init__(self, t):
        # t is a tuple like (type, id)
        self._t = t
        self._parent = None

    def set_parent(self, parent):
        self._parent = parent
        return self

    def parent(self):
        return self._parent

    def isValid(self):
        return self._t is not None


def _get_tree_tuple_stub(idx, _):
    if idx is None:
        return None
    if hasattr(idx, "_t"):
        return idx._t
    return None


class _SelectionStub:
    def __init__(self):
        self.begin = 0
        self.end = 0

    def begin_suppress_selection(self):
        self.begin += 1

    def end_suppress_selection(self):
        self.end += 1


class _TreeStub:
    def __init__(self, index: _IndexStub):
        self._index = index
        self.blocked = []

    def currentIndex(self):
        return self._index

    def blockSignals(self, val: bool):
        self.blocked.append(bool(val))


class _SignalStub:
    def __init__(self):
        self.calls = []

    def emit(self, *args, **kwargs):
        self.calls.append((args, kwargs))


class _MainWindowStub:
    def __init__(self):
        self.structure_business = types.SimpleNamespace(
            current_sphere_id=42,
            section_selected=_SignalStub(),
        )
        self.spheres_controller = types.SimpleNamespace(
            switched_to=None,
            switch_sphere=lambda sid: setattr(self.spheres_controller, "switched_to", sid),
        )
        self.structure = types.SimpleNamespace(
            selection_handler=_SelectionStub(),
            tree=None,
        )


class _TreeWidgetStub:
    def __init__(self, main_win, index: _IndexStub):
        self._main = main_win
        self._index = index

    def window(self):
        return self._main

    def currentIndex(self):
        return self._index


@pytest.fixture(autouse=True)
def patch_get_tree_tuple(monkeypatch):
    from app.views.tree_components import move_operations_handler as mod

    monkeypatch.setattr(mod, "get_tree_tuple", _get_tree_tuple_stub, raising=True)


def test_switch_sphere_if_needed_switches_sphere():
    mw = _MainWindowStub()
    handler = MoveOperationsHandler(tree_widget=_TreeWidgetStub(mw, _IndexStub(("section", 1))))

    handler._switch_sphere_if_needed(mw)

    assert mw.spheres_controller.switched_to == 42


def test_current_section_id_from_tree_selection_from_section():
    mw = _MainWindowStub()
    tree_widget = _TreeWidgetStub(mw, _IndexStub(("section", 7)))
    handler = MoveOperationsHandler(tree_widget=tree_widget)

    assert handler._current_section_id_from_tree_selection() == 7


def test_current_section_id_from_tree_selection_from_category_parent_section():
    mw = _MainWindowStub()
    parent = _IndexStub(("section", 9))
    child = _IndexStub(("category", 123)).set_parent(parent)
    tree_widget = _TreeWidgetStub(mw, child)
    handler = MoveOperationsHandler(tree_widget=tree_widget)

    assert handler._current_section_id_from_tree_selection() == 9


def test_emit_section_selected_with_suppression_blocks_and_emits():
    mw = _MainWindowStub()
    idx = _IndexStub(("section", 3))
    tree_stub = _TreeStub(index=idx)
    mw.structure.tree = tree_stub

    handler = MoveOperationsHandler(tree_widget=_TreeWidgetStub(mw, idx))

    handler._emit_section_selected_with_suppression(mw, section_id=11)

    # Проверяем блокировку/разблокировку сигналов
    assert tree_stub.blocked == [True, False]
    # Проверяем suppress selection begin/end
    assert mw.structure.selection_handler.begin == 1
    assert mw.structure.selection_handler.end == 1
    # Проверяем эмит секции
    assert mw.structure_business.section_selected.calls
    assert mw.structure_business.section_selected.calls[-1][0][0] == 11


def test_refresh_ui_after_move_integration_calls_helpers(monkeypatch):
    mw = _MainWindowStub()
    idx = _IndexStub(("section", 5))
    handler = MoveOperationsHandler(tree_widget=_TreeWidgetStub(mw, idx))

    called = {"switch": 0, "emit": 0}

    def mock_switch(main_win):
        called["switch"] += 1

    def mock_emit(main_win, section_id):
        called["emit"] += 1
        assert section_id == 5

    monkeypatch.setattr(handler, "_switch_sphere_if_needed", mock_switch)
    monkeypatch.setattr(handler, "_emit_section_selected_with_suppression", mock_emit)

    handler._refresh_ui_after_move()

    assert called["switch"] == 1
    assert called["emit"] == 1
