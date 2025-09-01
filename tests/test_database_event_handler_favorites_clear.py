import pytest

from app.controllers.system.window_controllers_setup import (
    DatabaseEventHandler,
    SetupError,
)


class TopPanelsControllerStub:
    def __init__(self):
        self.cleared = False
        self.refreshed = False

    def clear_favorites(self):
        self.cleared = True

    def request_favorites_refresh(self):
        self.refreshed = True


class LinksTableControllerStub:
    def __init__(self):
        self.reloaded_with = None

    def reload(self, category_id):
        self.reloaded_with = category_id


class WindowStub:
    def __init__(self, current_category_id=42):
        self._category_id = current_category_id

    def get_current_category_id(self):
        return self._category_id


def test_handle_favorites_cleared_raises_without_links_table_controller():
    window = WindowStub(current_category_id=7)
    top_ctrl = TopPanelsControllerStub()

    with pytest.raises(SetupError, match=r"LinksTableController is required to reload table after favorites clear"):
        DatabaseEventHandler.handle_favorites_cleared(
            window,
            top_panels_controller=top_ctrl,
            links_table_controller=None,
        )
