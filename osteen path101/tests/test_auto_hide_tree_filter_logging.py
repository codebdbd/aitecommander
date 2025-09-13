import logging

import pytest
from PyQt6.QtWidgets import QWidget

from app.views.main_components.window_ui_setup import _AutoHideTreeFilter
from app.views.main_components.window_ui_setup import logger as module_logger


@pytest.mark.usefixtures("qapp")
def test_auto_hide_tree_filter_uses_module_logger(caplog):
    # Prepare a QWidget as window (QObject parent is required)
    window = QWidget()

    # Force width below threshold to enter collapse branch
    window.resize(200, 200)

    class BadSplitter:
        def sizes(self):
            raise RuntimeError("boom sizes")

        def setCollapsible(self, *_):
            raise RuntimeError("boom setCollapsible")

        def setSizes(self, *_):
            raise RuntimeError("boom setSizes")

    class BadStack:
        def currentIndex(self):
            raise RuntimeError("boom index")

        def count(self):
            return 0

    class BadPanel:
        def setVisible(self, *_):
            raise RuntimeError("boom setVisible")

    # Attach problematic attributes to trigger debug logging paths
    window.splitter = BadSplitter()
    window.stack = BadStack()
    window.table = object()  # non-None to enter switch branch and then fail
    window.quick_add_widget = BadPanel()
    window.fav_widget = BadPanel()
    window.recent_links_widget = BadPanel()

    filt = _AutoHideTreeFilter(
        window, threshold_width=280, default_sizes=[250, 750], logger_=module_logger
    )

    caplog.set_level(logging.DEBUG, logger=module_logger.name)
    filt._apply()

    # Ensure debug messages are emitted from the module logger
    msgs = [r for r in caplog.records if r.name == module_logger.name]
    assert any("AutoHideTree:" in r.getMessage() for r in msgs)
