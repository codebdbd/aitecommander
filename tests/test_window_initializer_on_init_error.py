import types

import pytest

from app.views.main_components.window_initializer import WindowInitializer, logger


class DummyMetrics:
    def __init__(self, raise_on_flush=False):
        self.raise_on_flush = raise_on_flush
        self.flushed = 0
        self.last_logger = None

    def flush_log(self, lg):
        self.flushed += 1
        self.last_logger = lg
        if self.raise_on_flush:
            raise RuntimeError("flush failed")


class Dummy:
    pass


@pytest.fixture
def wi_instance():
    # Создаём инстанс с минимальными зависимостями
    inst = WindowInitializer(Dummy(), Dummy(), Dummy(), Dummy())
    return inst


def test_on_init_error_flushes_and_delegates(wi_instance, monkeypatch):
    metrics = DummyMetrics()
    wi_instance._metrics = metrics

    delegated = {}

    def _delegate(exc):
        delegated["exc"] = exc

    wi_instance._handle_deferred_init_error = _delegate  # type: ignore[attr-defined]

    err = Exception("boom")
    wi_instance._on_init_error(err)

    assert metrics.flushed == 1
    assert metrics.last_logger is logger
    assert delegated.get("exc") is err


def test_on_init_error_delegates_even_if_flush_raises(wi_instance, monkeypatch):
    metrics = DummyMetrics(raise_on_flush=True)
    wi_instance._metrics = metrics

    delegated = {}

    def _delegate(exc):
        delegated["exc"] = exc

    wi_instance._handle_deferred_init_error = _delegate  # type: ignore[attr-defined]

    err = Exception("boom-2")
    wi_instance._on_init_error(err)

    # Несмотря на ошибку flush_log, делегирование должно произойти
    assert delegated.get("exc") is err
