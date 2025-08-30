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


def test_negative_ttl_shorter_than_regular(monkeypatch):
    """Негативные записи должны протухать быстрее обычных при меньшем TTL."""
    from PyQt6.QtGui import QIcon

    # Обычный TTL длиннее, негативный короче
    monkeypatch.setattr(app_config, "get_icon_cache_ttl", lambda: 0.5, raising=True)
    monkeypatch.setattr(app_config, "get_negative_cache_ttl", lambda: 0.15, raising=True)

    icon_neg = "neg-faster"
    icon_pos = "pos-slower"
    theme = "light"

    # Кэшируем обе записи: негативную (None, negative=True) и обычную (QIcon())
    set_icon(icon_neg, theme, None, negative=True)
    set_icon(icon_pos, theme, QIcon())

    # Ждем больше негативного TTL, но меньше обычного
    time.sleep(0.2)

    # Негативная запись должна протухнуть и быть удалена при обращении
    assert get_icon(icon_neg, theme) is None

    # Обычная запись ещё валидна
    from PyQt6.QtGui import QIcon as _QIcon

    pos_val = get_icon(icon_pos, theme)
    assert isinstance(pos_val, _QIcon)

    # Дополнительно убедимся, что по истечении общего TTL обычная запись тоже протухает
    time.sleep(0.35)
    assert get_icon(icon_pos, theme) is None
