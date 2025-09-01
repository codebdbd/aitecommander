import pytest
from types import SimpleNamespace

from app.controllers.ui.links.handlers import LinksUIHandlers, SetupError


class DummyLinkOps:
    def __init__(self):
        # minimal API used elsewhere; not needed here
        pass


class DummyLinksTableController:
    pass


class Provider:
    def get_current_category_id(self):
        return 1


class ControllerStub:
    def __init__(self, table):
        self.table = table
        self.business = SimpleNamespace()
        self.main = SimpleNamespace()


class Signal:
    def __init__(self):
        self._subs = []

    def connect(self, slot):
        if not callable(slot):
            raise TypeError("slot must be callable")
        self._subs.append(slot)


class SelModel:
    def __init__(self):
        self.selectionChanged = Signal()


@pytest.mark.parametrize(
    "table_factory",
    [
        # Missing doubleClicked
        lambda: SimpleNamespace(
            clicked=Signal(),
            links_reordered=Signal(),
            selectionModel=lambda: SelModel(),
        ),
        # Missing clicked
        lambda: SimpleNamespace(
            doubleClicked=Signal(),
            links_reordered=Signal(),
            selectionModel=lambda: SelModel(),
        ),
        # Missing links_reordered
        lambda: SimpleNamespace(
            doubleClicked=Signal(),
            clicked=Signal(),
            selectionModel=lambda: SelModel(),
        ),
        # selectionModel returns None
        lambda: SimpleNamespace(
            doubleClicked=Signal(),
            clicked=Signal(),
            links_reordered=Signal(),
            selectionModel=lambda: None,
        ),
        # selectionModel method missing
        lambda: SimpleNamespace(
            doubleClicked=Signal(),
            clicked=Signal(),
            links_reordered=Signal(),
        ),
    ],
)
def test_connect_table_signals_raises_setup_error_on_missing_critical_signals(table_factory):
    table = table_factory()
    controller = ControllerStub(table)
    handlers = LinksUIHandlers(
        controller,
        link_operations=DummyLinkOps(),
        links_table_controller=DummyLinksTableController(),
        ui_state=Provider(),
    )

    with pytest.raises(SetupError):
        handlers._connect_table_signals()
