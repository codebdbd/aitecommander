import time

import pytest

from app.config_data import app_config
from app.utils.ui.icon import cache_manager as ic


def _sleep(s: float) -> None:
    time.sleep(s)


@pytest.fixture(autouse=True)
def _clear_cache_before():
    ic.clear()
    yield
    ic.clear()


def test_ttl_override_via_unified_set_read_by_get_path(monkeypatch: pytest.MonkeyPatch):
    # Глобальные TTL делаем большими, чтобы не мешали per-entry override
    monkeypatch.setattr(app_config, "get_icon_cache_ttl", lambda: 10.0, raising=True)
    monkeypatch.setattr(
        app_config, "get_abs_icon_cache_ttl", lambda: 10.0, raising=True
    )
    monkeypatch.setattr(
        app_config, "get_negative_cache_ttl", lambda: 10.0, raising=True
    )

    key = "path:special-path-ttl::dark"

    # Устанавливаем через унифицированный API с индивидуальным TTL
    ic.set(key, "/tmp/icon.svg", ttl=0.1)

    # Специализированный accessor должен видеть запись сразу
    assert ic.get_path("special-path-ttl", "dark") == "/tmp/icon.svg"

    # После истечения override запись должна протухнуть и для специализированного accessor'а
    _sleep(0.2)
    assert ic.get_path("special-path-ttl", "dark") is None


def test_ttl_override_via_unified_set_read_by_get_icon(monkeypatch: pytest.MonkeyPatch):
    # Глобальные TTL делаем большими, чтобы не мешали per-entry override
    monkeypatch.setattr(app_config, "get_icon_cache_ttl", lambda: 10.0, raising=True)
    monkeypatch.setattr(
        app_config, "get_abs_icon_cache_ttl", lambda: 10.0, raising=True
    )
    monkeypatch.setattr(
        app_config, "get_negative_cache_ttl", lambda: 10.0, raising=True
    )

    key = "qicon:special-qicon-ttl::light"

    # Устанавливаем через унифицированный API с индивидуальным TTL
    from PyQt6.QtGui import QIcon

    ic.set(key, QIcon(), ttl=0.1)

    # Специализированный accessor должен видеть запись сразу
    assert ic.get_icon("special-qicon-ttl", "light") is not None

    # После истечения override запись должна протухнуть и для специализированного accessor'а
    _sleep(0.2)
    assert ic.get_icon("special-qicon-ttl", "light") is None
