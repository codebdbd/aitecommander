import pytest

from app.controllers.ui.links.handlers import LinksUIHandlers


class ControllerStub:
    def __init__(self, table_controller):
        self.table = object()
        self.business = object()
        self.main = object()
        self.table_controller = table_controller


class LinkOperationsStub:
    def on_link_updated(self, *_):
        pass

    def on_favorite_toggled(self, *_):
        pass


class UIStateStub:
    def get_current_category_id(self):
        return 1


class LinksTableControllerRaises:
    def on_search_results(self, *_):
        raise TypeError("bad results format")


def make_handlers(table_controller):
    ctrl = ControllerStub(table_controller)
    ops = LinkOperationsStub()
    ui_state = UIStateStub()
    return LinksUIHandlers(ctrl, link_operations=ops, links_table_controller=table_controller, ui_state=ui_state)


def test_update_search_results_raises_on_table_controller_contract_error():
    h = make_handlers(LinksTableControllerRaises())
    with pytest.raises(TypeError):
        h._update_search_results([{"id": 1}])
