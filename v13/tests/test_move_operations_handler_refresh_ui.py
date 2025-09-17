import importlib
import types

import pytest


MODULE_PATH = "app.views.tree_components.move_operations_handler"


class DummyTreeWidget:
    def __init__(self, index=None):
        self._index = index

    def currentIndex(self):  # noqa: N802 - Qt-style API imitation
        return self._index

    def window(self):
        # Will be overridden per-test
        return getattr(self, "_window", types.SimpleNamespace())


class DummyIndex:
    def __init__(self, tuple_value=None, parent=None, valid=True):
        self._tuple_value = tuple_value
        self._parent = parent
        self._valid = valid

    def isValid(self):  # noqa: N802 - Qt-style API imitation
        return bool(self._valid)

    def parent(self):
        return self._parent


class DummySignal:
    def __init__(self):
        self.emitted = []

    def emit(self, *args, **kwargs):
        self.emitted.append((args, kwargs))


class DummySelectionHandler:
    def __init__(self):
        self.calls = []

    def begin_suppress_selection(self):
        self.calls.append("begin")

    def end_suppress_selection(self):
        self.calls.append("end")


class DummyTree:
    def __init__(self):
        self.calls = []
        self._enabled = True

    def blockSignals(self, enabled):  # noqa: N802 - Qt-style API imitation
        self._enabled = not enabled
        self.calls.append(enabled)


@pytest.fixture(autouse=True)
def reload_module(monkeypatch):
    # Ensure a clean module and logger each test
    mod = importlib.import_module(MODULE_PATH)
    importlib.reload(mod)
    yield


def _mk_handler_with_index(monkeypatch, tuple_for_index, tuple_for_parent=None):
    mod = importlib.import_module(MODULE_PATH)
    tree = DummyTreeWidget()
    parent_idx = DummyIndex(tuple_for_parent, parent=None, valid=True) if tuple_for_parent is not None else None
    idx = DummyIndex(tuple_for_index, parent=parent_idx, valid=True)
    tree._index = idx

    # Monkeypatch get_tree_tuple to simply return the embedded tuple from DummyIndex
    def fake_get_tree_tuple(obj, role):  # noqa: ARG001 - role unused
        if isinstance(obj, DummyIndex):
            return obj._tuple_value
        return None

    monkeypatch.setattr(mod, "get_tree_tuple", fake_get_tree_tuple)

    handler = mod.MoveOperationsHandler(tree)
    return handler, mod


def test_determine_current_section_id_for_section(monkeypatch):
    handler, _ = _mk_handler_with_index(monkeypatch, ("section", 5))
    assert handler._determine_current_section_id() == 5


def test_determine_current_section_id_for_category_parent_section(monkeypatch):
    handler, _ = _mk_handler_with_index(monkeypatch, ("category", 10), ("section", 7))
    assert handler._determine_current_section_id() == 7


def test_determine_current_section_id_logs_on_attribute_error(caplog, monkeypatch):
    mod = importlib.import_module(MODULE_PATH)
    tree = DummyTreeWidget(DummyIndex(("section", 1)))
    handler = mod.MoveOperationsHandler(tree)

    def boom(*args, **kwargs):  # noqa: ARG001
        raise AttributeError("broken")

    monkeypatch.setattr(mod, "get_tree_tuple", boom)

    caplog.set_level("ERROR")
    assert handler._determine_current_section_id() is None
    assert any(
        "Не удалось определить текущий раздел после перемещения" in rec.message for rec in caplog.records
    )


def test_maybe_switch_sphere_invokes_controller(monkeypatch):
    mod = importlib.import_module(MODULE_PATH)
    tree = DummyTreeWidget()
    handler = mod.MoveOperationsHandler(tree)

    called = {}

    class SpheresController:
        def switch_sphere(self, sid):
            called["sid"] = sid

    main_win = types.SimpleNamespace(
        structure_business=types.SimpleNamespace(current_sphere_id=3),
        spheres_controller=SpheresController(),
    )

    handler._maybe_switch_sphere(main_win)
    assert called.get("sid") == 3


def test_maybe_switch_sphere_logs_on_exception(caplog):
    mod = importlib.import_module(MODULE_PATH)
    tree = DummyTreeWidget()
    handler = mod.MoveOperationsHandler(tree)

    class BadController:
        def switch_sphere(self, sid):  # noqa: ARG002
            raise RuntimeError("boom")

    main_win = types.SimpleNamespace(
        structure_business=types.SimpleNamespace(current_sphere_id=1),
        spheres_controller=BadController(),
    )

    caplog.set_level("ERROR")
    handler._maybe_switch_sphere(main_win)
    assert any(
        "Не удалось переключить сферу после перемещения" in rec.message for rec in caplog.records
    )


def test_refresh_category_tiles_emits_and_suppresses():
    mod = importlib.import_module(MODULE_PATH)
    tree = DummyTreeWidget()
    handler = mod.MoveOperationsHandler(tree)

    selection = DummySelectionHandler()
    qt_tree = DummyTree()
    signal = DummySignal()

    main_win = types.SimpleNamespace(
        structure=types.SimpleNamespace(selection_handler=selection, tree=qt_tree),
        structure_business=types.SimpleNamespace(section_selected=signal),
    )

    handler._refresh_category_tiles(main_win, section_id=42)

    # Expect emissions and suppression calls
    assert signal.emitted and signal.emitted[-1][0] == (42,)
    assert selection.calls == ["begin", "end"]
    assert qt_tree.calls == [True, False]


def test_refresh_category_tiles_logs_on_failures(caplog):
    mod = importlib.import_module(MODULE_PATH)
    tree = DummyTreeWidget()
    handler = mod.MoveOperationsHandler(tree)

    class BadSelection:
        def begin_suppress_selection(self):
            raise AttributeError("bad begin")

        def end_suppress_selection(self):
            raise AttributeError("bad end")

    class BadTree:
        def blockSignals(self, enabled):  # noqa: N802
            raise AttributeError(f"bad block {enabled}")

    signal = DummySignal()

    main_win = types.SimpleNamespace(
        structure=types.SimpleNamespace(selection_handler=BadSelection(), tree=BadTree()),
        structure_business=types.SimpleNamespace(section_selected=signal),
    )

    caplog.set_level("ERROR")
    handler._refresh_category_tiles(main_win, section_id=7)

    msgs = [rec.message for rec in caplog.records]
    assert any("Ошибка начала подавления selection-событий" in m for m in msgs)
    assert any("Ошибка блокировки сигналов дерева" in m for m in msgs)
    assert any("Ошибка разблокировки сигналов дерева" in m for m in msgs)
    assert any("Ошибка завершения подавления selection-событий" in m for m in msgs)
