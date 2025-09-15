import pytest
from PyQt6.QtWidgets import QWidget

from app.views.main_components.window_ui_setup import _AutoHideTreeFilter


class SplitterStub:
    def __init__(self, initial_sizes=(300, 700), initial_collapsible0=False):
        self._sizes = list(initial_sizes)
        self._collapsible0 = bool(initial_collapsible0)

    # API used by _AutoHideTreeFilter
    def sizes(self):
        return list(self._sizes)

    def setSizes(self, sizes):
        self._sizes = list(sizes)

    def isCollapsible(self, idx: int) -> bool:
        if idx != 0:
            # Only index 0 is relevant in our UI
            return False
        return self._collapsible0

    def setCollapsible(self, idx: int, val: bool):
        if idx == 0:
            self._collapsible0 = bool(val)


@pytest.mark.usefixtures("qapp")
@pytest.mark.parametrize("initial_collapsible0", [False, True])
def test_auto_hide_tree_filter_restores_splitter_collapsible(initial_collapsible0):
    # Arrange: a QWidget window with custom splitter
    window = QWidget()
    splitter = SplitterStub(initial_sizes=(250, 750), initial_collapsible0=initial_collapsible0)
    window.splitter = splitter

    # Narrow window to trigger collapse branch
    window.resize(200, 200)

    filt = _AutoHideTreeFilter(window, threshold_width=280, default_sizes=[250, 750])

    # Act: collapse on narrow width
    filt._apply()

    # Assert: left panel collapsible is forced to True and sizes collapsed
    assert splitter.isCollapsible(0) is True
    assert splitter.sizes()[0] == 0

    # Expand window beyond threshold and apply again
    window.resize(1000, 800)
    filt._apply()

    # Assert: 
    # 1) restored original collapsible state
    assert splitter.isCollapsible(0) is initial_collapsible0
    # 2) sizes restored back to saved pre-collapse sizes (250, 750)
    assert splitter.sizes() == [250, 750]
