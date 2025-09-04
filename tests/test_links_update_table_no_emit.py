from types import SimpleNamespace

from app.controllers.ui.links.handlers import LinksUIHandlers


class DummyProvider:
    def __init__(self, current_id: int):
        self._id = current_id

    def get_current_category_id(self):
        return self._id


class DummyLinkOps:
    def __init__(self):
        self.emitted = []

    # legacy API that used to be called from _update_table
    def emit_links_changed(self, category_id: int):
        self.emitted.append(category_id)


class DummyLinksTableController:
    def __init__(self):
        self.loaded_calls = []

    def on_links_loaded(self, links, category_id, task_id):
        self.loaded_calls.append((links, category_id, task_id))


class ControllerStub:
    def __init__(self):
        # minimal surface used by BaseLinksUIComponent
        self.table = SimpleNamespace()
        self.business = SimpleNamespace()
        self.main = SimpleNamespace()


def test_update_table_does_not_emit_links_changed_anymore():
    # Arrange
    category_id = 42
    provider = DummyProvider(current_id=category_id)
    link_ops = DummyLinkOps()
    table_ctrl = DummyLinksTableController()
    ctrl = ControllerStub()

    handlers = LinksUIHandlers(
        ctrl,
        link_operations=link_ops,
        links_table_controller=table_ctrl,
        ui_state=provider,
    )

    links_payload = [{"id": 1, "name": "A"}]
    task_id = 7

    # Act
    handlers._update_table(links_payload, category_id, task_id)

    # Assert: table was updated directly
    assert table_ctrl.loaded_calls == [(links_payload, category_id, task_id)]
    # And no links_changed emitted from _update_table (prevents redundant reload)
    assert link_ops.emitted == []


def test_update_table_ignores_results_for_non_current_category():
    # Arrange: provider current id differs from payload category
    provider = DummyProvider(current_id=10)
    link_ops = DummyLinkOps()
    table_ctrl = DummyLinksTableController()
    ctrl = ControllerStub()

    handlers = LinksUIHandlers(
        ctrl,
        link_operations=link_ops,
        links_table_controller=table_ctrl,
        ui_state=provider,
    )

    # Act: incoming results for another category
    handlers._update_table([{"id": 2}], category_id=11, task_id=1)

    # Assert: no table update and no emission
    assert table_ctrl.loaded_calls == []
    assert link_ops.emitted == []
