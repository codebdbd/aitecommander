import time

import pytest

from app.config_data import app_config
from app.utils.ui.icon.cache_manager import (
    clear_icon_cache,
    get_icon,
    get_icon_cache_stats,
    set_icon,
)


@pytest.fixture(autouse=True)
def _clear_cache_before_each():
    clear_icon_cache()
    yield
    clear_icon_cache()


def test_negative_qicon_ttl_eviction(monkeypatch):
    # Установим короткий TTL для негативных записей
    monkeypatch.setattr(app_config, "get_negative_cache_ttl", lambda: 0.2, raising=True)

    icon_name = "neg-icon"
    theme = "light"

    # Кэшируем отрицательный результат
    set_icon(icon_name, theme, None, negative=True)

    # Запись присутствует в кэше сразу после установки
    stats = get_icon_cache_stats()
    assert stats["qicon_cache_size"] >= 1

    # Через время > TTL запись должна стать невалидной и быть удаленной при обращении
    time.sleep(0.25)
    assert get_icon(icon_name, theme) is None

    stats_after = get_icon_cache_stats()
    # Доступ должен был очистить устаревшую запись
    assert stats_after["qicon_cache_size"] == 0
