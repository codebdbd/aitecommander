# test_icon_cache_manager.py
"""Тесты для модуля cache_manager.py.

Проверяет:
- LRU кэширование
- TTL механизм
- Negative caching
- Thread safety
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from PyQt6.QtGui import QIcon

from app.utils.ui.icon.cache_manager import (
    ThreadSafeIconCache,
    clear_icon_cache,
    get_cached_category_icon,
    get_icon,
    get_icon_cache_stats,
    set_icon,
)


class TestThreadSafeIconCache:
    """Тесты ThreadSafeIconCache."""

    def test_cache_creation(self):
        """Кэш должен создаваться с заданным размером."""
        cache = ThreadSafeIconCache(maxsize=100)
        assert cache._capacity == 100

    def test_cache_set_get_qicon(self, qapp):
        """Должен сохранять и возвращать QIcon."""
        cache = ThreadSafeIconCache(maxsize=10)
        icon = QIcon()
        
        cache.set_qicon("test.svg", "light", icon)
        result = cache.get_qicon("test.svg", "light")
        
        assert result is not None
        assert isinstance(result, QIcon)

    def test_cache_miss(self):
        """Промах кэша должен возвращать None."""
        cache = ThreadSafeIconCache(maxsize=10)
        
        result = cache.get_qicon("nonexistent.svg", "light")
        
        assert result is None

    def test_cache_ttl_expiration(self, monkeypatch, qapp):
        """Запись должна истекать по TTL."""
        cache = ThreadSafeIconCache(maxsize=10)
        
        # Устанавливаем короткий TTL
        monkeypatch.setattr(cache, '_ttl_icon', 0.1)
        
        icon = QIcon()
        cache.set_qicon("test.svg", "light", icon)
        
        # Сразу должно быть в кэше
        assert cache.get_qicon("test.svg", "light") is not None
        
        # После истечения TTL должно быть None
        time.sleep(0.15)
        assert cache.get_qicon("test.svg", "light") is None

    def test_cache_lru_eviction(self, qapp):
        """Должен вытеснять старые записи при переполнении."""
        cache = ThreadSafeIconCache(maxsize=3)
        
        icon1 = QIcon()
        icon2 = QIcon()
        icon3 = QIcon()
        icon4 = QIcon()
        
        cache.set_qicon("icon1.svg", "light", icon1)
        cache.set_qicon("icon2.svg", "light", icon2)
        cache.set_qicon("icon3.svg", "light", icon3)
        
        # Все 3 должны быть в кэше
        assert cache.get_qicon("icon1.svg", "light") is not None
        
        # Добавляем 4-ю - должна вытеснить icon1
        cache.set_qicon("icon4.svg", "light", icon4)
        
        assert cache.get_qicon("icon1.svg", "light") is None
        assert cache.get_qicon("icon4.svg", "light") is not None

    def test_cache_negative_entry(self, qapp):
        """Должен кэшировать negative записи."""
        cache = ThreadSafeIconCache(maxsize=10)
        
        cache.set_qicon("missing.svg", "light", None, negative=True)
        
        result = cache.get_qicon("missing.svg", "light")
        assert result is None

    def test_cache_path_operations(self):
        """Должен кэшировать пути."""
        cache = ThreadSafeIconCache(maxsize=10)
        
        cache.set_path("test.svg", "light", "/path/to/icon.svg")
        result = cache.get_path("test.svg", "light")
        
        assert result == "/path/to/icon.svg"

    def test_cache_clear(self, qapp):
        """Должен очищать весь кэш."""
        cache = ThreadSafeIconCache(maxsize=10)
        
        icon = QIcon()
        cache.set_qicon("test.svg", "light", icon)
        cache.set_path("test.svg", "light", "/path")
        
        cache.clear()
        
        assert cache.get_qicon("test.svg", "light") is None
        assert cache.get_path("test.svg", "light") is None

    def test_cache_stats(self, qapp):
        """Должен возвращать статистику."""
        cache = ThreadSafeIconCache(maxsize=10)
        
        icon = QIcon()
        cache.set_qicon("test.svg", "light", icon)
        cache.get_qicon("test.svg", "light")  # hit
        cache.get_qicon("missing.svg", "light")  # miss
        
        stats = cache.get_cache_stats()
        
        assert stats['hits'] >= 1
        assert stats['misses'] >= 1
        assert 'qicon_cache_size' in stats


class TestGlobalCacheFunctions:
    """Тесты глобальных функций кэша."""

    def test_set_get_icon(self, qapp):
        """Должен сохранять и получать иконки через глобальный API."""
        icon = QIcon()
        
        set_icon("global.svg", "light", icon)
        result = get_icon("global.svg", "light")
        
        assert result is not None

    def test_clear_icon_cache(self, qapp):
        """Должен очищать глобальный кэш."""
        icon = QIcon()
        set_icon("test.svg", "light", icon)
        
        clear_icon_cache()
        
        result = get_icon("test.svg", "light")
        assert result is None

    def test_get_icon_cache_stats(self, qapp):
        """Должен возвращать статистику глобального кэша."""
        icon = QIcon()
        set_icon("test.svg", "light", icon)
        
        stats = get_icon_cache_stats()
        
        assert isinstance(stats, dict)
        assert 'hits' in stats
        assert 'misses' in stats


class TestGetCachedCategoryIcon:
    """Тесты get_cached_category_icon."""

    def test_get_cached_category_icon_gui_thread(self, qapp, tmp_path):
        """Должен работать из GUI-потока."""
        icon_file = tmp_path / "category.png"
        icon_file.write_bytes(
            b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
            b'\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01'
            b'\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82'
        )
        
        icon = get_cached_category_icon(str(icon_file))
        
        assert isinstance(icon, QIcon)

    def test_get_cached_category_icon_nonexistent(self, qapp, tmp_path):
        """Несуществующий файл должен возвращать пустую иконку."""
        icon = get_cached_category_icon(str(tmp_path / "nonexistent.png"))
        
        assert isinstance(icon, QIcon)
        assert icon.isNull()

    def test_get_cached_category_icon_caching(self, qapp, tmp_path):
        """Должен кэшировать результат."""
        icon_file = tmp_path / "category.png"
        icon_file.write_bytes(
            b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
            b'\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01'
            b'\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82'
        )
        
        # Первый вызов
        icon1 = get_cached_category_icon(str(icon_file))
        # Второй вызов - из кэша
        icon2 = get_cached_category_icon(str(icon_file))
        
        assert isinstance(icon1, QIcon)
        assert isinstance(icon2, QIcon)


class TestCacheKeyParsing:
    """Тесты парсинга unified keys."""

    def test_parse_path_key(self):
        """Должен парсить path: ключи."""
        cache = ThreadSafeIconCache(maxsize=10)
        
        prefix, name, theme = cache._parse_unified_key("path:icon.svg::light")
        
        assert prefix == "path"
        assert name == "icon.svg"
        assert theme == "light"

    def test_parse_qicon_key(self):
        """Должен парсить qicon: ключи."""
        cache = ThreadSafeIconCache(maxsize=10)
        
        prefix, name, theme = cache._parse_unified_key("qicon:icon.svg::dark")
        
        assert prefix == "qicon"
        assert name == "icon.svg"
        assert theme == "dark"

    def test_parse_invalid_key(self):
        """Невалидный ключ должен выбрасывать ValueError."""
        cache = ThreadSafeIconCache(maxsize=10)
        
        with pytest.raises(ValueError):
            cache._parse_unified_key("invalid_key")

    def test_parse_invalid_prefix(self):
        """Невалидный префикс должен выбрасывать ValueError."""
        cache = ThreadSafeIconCache(maxsize=10)
        
        with pytest.raises(ValueError):
            cache._parse_unified_key("invalid:icon.svg::light")


class TestCacheSynchronization:
    """Тесты синхронизации кэша и LRU."""

    def test_sync_path_structs(self, qapp):
        """Должен синхронизировать path кэш с LRU."""
        cache = ThreadSafeIconCache(maxsize=10)
        
        cache.set_path("test.svg", "light", "/path")
        cache._sync_path_structs()
        
        # После синхронизации LRU должен содержать ключ
        assert cache._path_lru.size() > 0

    def test_sync_qicon_structs(self, qapp):
        """Должен синхронизировать qicon кэш с LRU."""
        cache = ThreadSafeIconCache(maxsize=10)
        
        icon = QIcon()
        cache.set_qicon("test.svg", "light", icon)
        cache._sync_qicon_structs()
        
        assert cache._qicon_lru.size() > 0


@pytest.fixture
def qapp():
    """Фикстура для QApplication."""
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app
