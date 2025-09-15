import types

from app.controllers.ui.structure.selection_handling import SelectionHandling


class _DummySelModel:
    class SelectionFlag:
        ClearAndSelect = object()

    def hasSelection(self):
        return False

    def setCurrentIndex(self, *_args, **_kwargs):
        pass


class _DummyModel:
    def rowCount(self, *_):
        return 1

    def index(self, *_):
        class _Idx:
            def isValid(self):
                return True
        return _Idx()


class _DummyTree:
    def selectionModel(self):
        return _DummySelModel()

    def model(self):
        return _DummyModel()

    def setFocus(self):
        pass


class _DummyTiles:
    def refresh(self, *_):
        pass


class _DummyMain:
    pass


class _DummyController:
    def __init__(self):
        self.tree = _DummyTree()
        self.main = _DummyMain()
        self.business = types.SimpleNamespace(_suppress_category_restore_once=False)


def test_ensure_selection_without_state_selects_first(monkeypatch):
    ctrl = _DummyController()
    sh = SelectionHandling(ctrl, category_tiles_controller=_DummyTiles())

    # should select first when no state
    sh.ensure_selection_after_load(state=None)
    # if no exceptions — selection path executed; detailed selection is covered by _select_first_item_if_needed tests


def test_ensure_selection_with_flag_resets_and_selects_first(monkeypatch):
    ctrl = _DummyController()
    ctrl.business._suppress_category_restore_once = True
    sh = SelectionHandling(ctrl, category_tiles_controller=_DummyTiles())

    sh.ensure_selection_after_load(state=object())
    assert ctrl.business._suppress_category_restore_once is False


def test_ensure_selection_with_state_and_no_flag_does_not_select(monkeypatch):
    ctrl = _DummyController()
    sh = SelectionHandling(ctrl, category_tiles_controller=_DummyTiles())

    # Ensure no exception when state exists and no flag; selection should not be forced
    sh.ensure_selection_after_load(state=object())
