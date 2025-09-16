# Ensure project root is on sys.path for `import app`
import os
import sys

import pytest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


class SignalStub:
    def __init__(self):
        self._subs = []

    def connect(self, cb):
        self._subs.append(cb)

    def emit(self, *args, **kwargs):
        for cb in list(self._subs):
            cb(*args, **kwargs)

    def __getitem__(self, _):
        return self


@pytest.fixture
def signal_stub_cls():
    return SignalStub


@pytest.fixture
def fav_widget_stub_min():
    class Fav:
        def set_favorites(self, items):
            pass

        def set_data(self, items):
            self.set_favorites(items)

        def clear_favorites(self):
            pass

    return Fav()


@pytest.fixture
def rec_widget_stub_min():
    class Rec:
        def set_recent_links(self, items):
            pass

        def set_data(self, items):
            self.set_recent_links(items)

    return Rec()


@pytest.fixture
def fav_widget_stub_with_clear_signals(signal_stub_cls):
    class Fav:
        def __init__(self):
            self.refreshRequested = signal_stub_cls()
            self.clearRequested = signal_stub_cls()
            self.linkClicked = signal_stub_cls()

        def set_favorites(self, items):
            pass

        def set_data(self, items):
            self.set_favorites(items)

        def clear_favorites(self):
            pass

    return Fav()


@pytest.fixture
def rec_widget_stub_with_signals(signal_stub_cls):
    class Rec:
        def __init__(self):
            self.refreshRequested = signal_stub_cls()
            self.linkClicked = signal_stub_cls()

        def set_recent_links(self, items):
            pass

        def set_data(self, items):
            self.set_recent_links(items)

    return Rec()


@pytest.fixture
def links_business_stub():
    class LinksBusiness:
        def get_favorite_links(self):
            return []

        def get_recent_links(self, limit: int):
            return []

    return LinksBusiness()
