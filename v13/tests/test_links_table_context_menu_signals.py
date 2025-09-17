import pytest

from app.controllers.ui.links.handlers import LinksUIHandlers, SetupError


class ControllerStub:
    def __init__(self, table, business=None, main=None, table_controller=None):
        self.table = table
        self.business = business or object()
        self.main = main or object()
        self.table_controller = table_controller


class LinkOperationsStub:
    def on_link_updated(self, *_):
        pass

    def on_favorite_toggled(self, *_):
        pass


class UIStateStub:
    def get_current_category_id(self):
        return 1


class TableMissingSetPolicy:
    # Нет setContextMenuPolicy
    def __init__(self):
        self.customContextMenuRequested = type(
            "Sig", (), {"connect": lambda *args, **kwargs: None}
        )()


class TableMissingContextSignal:
    def setContextMenuPolicy(self, *_):
        pass

    # Нет customContextMenuRequested


class TableBadContextSignal:
    def setContextMenuPolicy(self, *_):
        pass

    # customContextMenuRequested есть, но без connect()
    class Dummy:
        pass

    customContextMenuRequested = Dummy()


def make_handlers(table):
    ctrl = ControllerStub(table)
    ops = LinkOperationsStub()
    ui_state = UIStateStub()
    return LinksUIHandlers(
        ctrl, link_operations=ops, links_table_controller=object(), ui_state=ui_state
    )


def test_missing_set_context_menu_policy_raises_setup_error():
    h = make_handlers(TableMissingSetPolicy())
    with pytest.raises(SetupError):
        h._connect_table_signals()


def test_missing_context_signal_raises_setup_error():
    h = make_handlers(TableMissingContextSignal())
    with pytest.raises(SetupError):
        h._connect_table_signals()


def test_bad_context_signal_connect_raises_setup_error():
    h = make_handlers(TableBadContextSignal())
    with pytest.raises(SetupError):
        h._connect_table_signals()
