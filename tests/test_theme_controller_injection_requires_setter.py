import types
import pytest
from types import SimpleNamespace

from app.controllers.system import window_controllers_setup as wcs
from app.controllers.system.window_controllers_setup import setup_controllers, SetupError


# Lightweight stubs to bypass heavy UI/Qt dependencies while exercising the DI path
class _Signal:
    def connect(self, *_args, **_kwargs):
        pass


class CategoryTilesControllerStub:
    def __init__(self, ui_state, structure_business):  # noqa: ARG002
        pass

    def attach_tiles_widget(self, tiles_widget):  # noqa: ARG002
        return None


class StructureUIControllerStub:
    def __init__(self, tree, structure_business, window):  # noqa: ARG002
        # minimal signals used later in wiring (but we will fail earlier before wiring)
        self.item_changed = _Signal()
        self.item_added = _Signal()


class LinkOperationsControllerStub:
    def __init__(self, db, undo_stack, window):  # noqa: ARG002
        self.recents_changed = types.SimpleNamespace(connect=lambda *a, **k: None)


class LinksTableControllerStub:
    def __init__(self, window, table, links_business, category_provider):  # noqa: ARG002
        pass


class LinksUIControllerStub:
    def __init__(self, table, links_business, window, link_operations, links_table_controller):  # noqa: ARG002
        pass


class DatabaseControllerStub:
    def __init__(self, db, window):  # noqa: ARG002
        # minimal signals referenced later (but we will fail earlier)
        self.database_restored = _Signal()
        self.database_connected = _Signal()
        self.favorites_cleared = _Signal()
        self.operation_success = _Signal()
        self.operation_error = _Signal()


class SystemDialogControllerStub:
    def __init__(self, window, *, database_controller=None, links_table_controller=None, links_business=None):  # noqa: ARG002
        pass


class AppShutdownControllerStub:
    def __init__(self, window):  # noqa: ARG002
        pass


class SpheresBarControllerStub:
    def __init__(self, window):  # noqa: ARG002
        pass


class LinksBusinessLogicStub:
    def __init__(self, db):  # noqa: ARG002
        # minimal signals referenced later (but we will fail earlier)
        self.links_loaded = _Signal()
        self.search_results_ready = _Signal()


@pytest.fixture(autouse=True)
def patch_controllers(monkeypatch):
    # Patch heavy controllers with lightweight stubs directly in the setup module namespace
    monkeypatch.setattr(wcs, "CategoryTilesController", CategoryTilesControllerStub, raising=True)
    monkeypatch.setattr(wcs, "StructureUIController", StructureUIControllerStub, raising=True)
    monkeypatch.setattr(wcs, "LinkOperationsController", LinkOperationsControllerStub, raising=True)
    monkeypatch.setattr(wcs, "LinksTableController", LinksTableControllerStub, raising=True)
    monkeypatch.setattr(wcs, "LinksUIController", LinksUIControllerStub, raising=True)
    monkeypatch.setattr(wcs, "DatabaseController", DatabaseControllerStub, raising=True)
    monkeypatch.setattr(wcs, "SystemDialogController", SystemDialogControllerStub, raising=True)
    monkeypatch.setattr(wcs, "AppShutdownController", AppShutdownControllerStub, raising=True)
    monkeypatch.setattr(wcs, "SpheresBarController", SpheresBarControllerStub, raising=True)
    monkeypatch.setattr(wcs, "LinksBusinessLogic", LinksBusinessLogicStub, raising=True)


def test_theme_controller_without_setter_raises_setup_error():
    class Fav:
        def set_favorites(self, items):
            pass

        def clear_favorites(self):
            pass

    class Rec:
        def set_recent_links(self, items):
            pass

    # theme_ctrl lacks set_top_panels_controller
    theme_ctrl = SimpleNamespace()

    window = SimpleNamespace(
        tiles=object(),
        tree=object(),
        table=object(),
        undo_stack=object(),
        fav_widget=Fav(),
        recent_links_widget=Rec(),
        theme_ctrl=theme_ctrl,
    )

    class DummyDB:
        pass

    with pytest.raises(SetupError):
        setup_controllers(window, {}, DummyDB())
