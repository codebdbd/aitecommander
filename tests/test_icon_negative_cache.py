# test_icon_negative_cache.py
"""Тесты для negative cache модуля icon.

Проверяет:
- Корректность работы экспоненциального TTL
- Отсутствие утечек памяти в _strikes
- Правильную очистку при invalidate
"""

from __future__ import annotations

import time

import pytest

from app.utils.ui.icon.negative_cache import NegativeCache


class TestNegativeCache:
    """Проверка negative cache с экспоненциальным TTL."""

    def test_basic_negative_marking(self):
        """Базовая проверка маркировки negative."""
        cache = NegativeCache()

        # Маркируем ключ как negative
        cache.mark_negative("test_key")

        # Проверяем, что ключ помечен
        assert cache.is_negative("test_key") is True

    def test_negative_expires_after_ttl(self, monkeypatch):
        """Negative запись должна истекать после TTL."""
        from app.utils.ui.icon import negative_cache as nc_module
        
        # Мокаем глобальную функцию _base_ttl
        monkeypatch.setattr(nc_module, '_base_ttl', lambda: 0.01)
        
        cache = NegativeCache()

        # Маркируем ключ
        cache.mark_negative("test_key")
        assert cache.is_negative("test_key") is True

        # Ждём истечения TTL (очень короткое)
        time.sleep(0.02)

        # Ключ должен истечь
        assert cache.is_negative("test_key") is False

    def test_strikes_accumulate(self):
        """Strikes должны накапливаться при повторных промахах."""
        cache = NegativeCache()

        # Первый промах
        cache.mark_negative("test_key")
        assert cache._strikes.get("test_key", 0) == 1

        # Второй промах
        cache.mark_negative("test_key")
        assert cache._strikes.get("test_key", 0) == 2

        # Третий промах
        cache.mark_negative("test_key")
        assert cache._strikes.get("test_key", 0) == 3

    def test_strikes_bounded_by_max(self):
        """Strikes не должны расти бесконечно."""
        cache = NegativeCache()
        max_strikes = cache.max_strikes()

        # Пытаемся накопить больше max_strikes
        for _ in range(max_strikes + 10):
            cache.mark_negative("test_key")

        # Strikes ограничены max_strikes
        assert cache._strikes["test_key"] <= max_strikes

    def test_strikes_cleanup_on_invalidate(self):
        """Strikes должны удаляться при invalidate."""
        cache = NegativeCache()

        # Накапливаем strikes
        for _ in range(3):
            cache.mark_negative("test_key")

        # Проверяем, что strikes накопились
        assert cache._strikes.get("test_key", 0) == 3

        # Invalidate
        cache.invalidate("test_key")

        # Strikes должны быть удалены
        assert "test_key" not in cache._strikes
        assert cache.is_negative("test_key") is False

    def test_strikes_cleanup_on_expiration(self, monkeypatch):
        """Strikes должны уменьшаться при истечении TTL."""
        from app.utils.ui.icon import negative_cache as nc_module
        
        monkeypatch.setattr(nc_module, '_base_ttl', lambda: 0.01)
        
        cache = NegativeCache()

        # Накапливаем strikes
        cache.mark_negative("test_key")
        cache.mark_negative("test_key")
        initial_strikes = cache._strikes.get("test_key", 0)
        assert initial_strikes == 2

        # Ждём истечения TTL
        time.sleep(0.02)

        # Проверяем истечение (это должно уменьшить strikes)
        cache.is_negative("test_key")

        # Strikes должны уменьшиться или удалиться
        new_strikes = cache._strikes.get("test_key", 0)
        assert new_strikes < initial_strikes

    def test_strikes_removed_when_reach_zero(self, monkeypatch):
        """Ключ должен полностью удаляться из _strikes когда strikes достигают 0."""
        from app.utils.ui.icon import negative_cache as nc_module
        
        monkeypatch.setattr(nc_module, '_base_ttl', lambda: 0.01)
        
        cache = NegativeCache()

        # Один strike
        cache.mark_negative("test_key")
        assert cache._strikes.get("test_key", 0) == 1

        # Ждём истечения
        time.sleep(0.02)

        # Проверяем истечение
        cache.is_negative("test_key")

        # Ключ должен быть полностью удалён из _strikes
        assert "test_key" not in cache._strikes

    def test_exponential_ttl_growth(self):
        """TTL должен расти экспоненциально с количеством strikes."""
        cache = NegativeCache()

        # Первый strike - базовый TTL
        ttl_1 = cache.calc_ttl(1)
        # Второй strike - удвоенный TTL
        ttl_2 = cache.calc_ttl(2)
        # Третий strike - учетверённый TTL
        ttl_3 = cache.calc_ttl(3)

        assert ttl_2 == ttl_1 * 2
        assert ttl_3 == ttl_1 * 4

    def test_ttl_capped_at_max(self):
        """TTL не должен превышать max_ttl."""
        cache = NegativeCache()
        max_ttl = cache.max_ttl()

        # Очень большое количество strikes
        ttl = cache.calc_ttl(100)

        assert ttl <= max_ttl

    def test_clear_removes_all_data(self):
        """clear() должен удалять все данные."""
        cache = NegativeCache()

        # Добавляем несколько ключей
        cache.mark_negative("key1")
        cache.mark_negative("key2")
        cache.mark_negative("key3")

        # Проверяем, что данные есть
        assert len(cache._ts) > 0
        assert len(cache._strikes) > 0

        # Очищаем
        cache.clear()

        # Всё должно быть пусто
        assert len(cache._ts) == 0
        assert len(cache._strikes) == 0
        assert len(cache._gen) == 0
        assert len(cache._expire_heap) == 0
        assert len(cache._ts_heap) == 0

    def test_size_limit_evicts_oldest(self):
        """При превышении max_size должны вытесняться старые записи."""
        cache = NegativeCache()
        max_size = cache.max_size()

        # Заполняем кэш до предела + 1
        for i in range(max_size + 5):
            cache.mark_negative(f"key_{i}")

        # Размер не должен превышать max_size
        assert len(cache._ts) <= max_size

    def test_evicted_keys_have_strikes_removed(self):
        """При вытеснении ключа его strikes должны удаляться."""
        cache = NegativeCache()
        max_size = cache.max_size()

        # Заполняем кэш
        for i in range(max_size + 5):
            cache.mark_negative(f"key_{i}")

        # Проверяем, что количество strikes не превышает размер кэша
        # (могут быть меньше из-за истечения, но не больше)
        assert len(cache._strikes) <= max_size + 1  # +1 для погрешности

    def test_invalidate_all_clears_strikes(self):
        """invalidate(None) должен очищать все strikes."""
        cache = NegativeCache()

        # Добавляем данные
        for i in range(10):
            cache.mark_negative(f"key_{i}")

        assert len(cache._strikes) > 0

        # Полная очистка
        cache.invalidate(None)

        assert len(cache._strikes) == 0


class TestNegativeCacheMemoryLeak:
    """Проверка отсутствия утечек памяти."""

    def test_no_strike_leak_on_expiration(self, monkeypatch):
        """Strikes не должны накапливаться при истечении записей."""
        from app.utils.ui.icon import negative_cache as nc_module
        
        monkeypatch.setattr(nc_module, '_base_ttl', lambda: 0.01)
        
        cache = NegativeCache()

        # Создаём много записей
        for i in range(100):
            cache.mark_negative(f"key_{i}")

        initial_strikes = len(cache._strikes)

        # Ждём истечения
        time.sleep(0.02)

        # Проверяем истечение всех ключей
        for i in range(100):
            cache.is_negative(f"key_{i}")

        # Strikes должны уменьшиться или удалиться
        final_strikes = len(cache._strikes)
        assert final_strikes < initial_strikes

    def test_no_strike_leak_on_size_limit(self):
        """Strikes не должны накапливаться при вытеснении по размеру."""
        cache = NegativeCache()
        max_size = cache.max_size()

        # Создаём в 3 раза больше записей чем max_size
        for i in range(max_size * 3):
            cache.mark_negative(f"key_{i}")

        # Strikes не должны превышать разумный предел
        assert len(cache._strikes) <= max_size + 10  # +10 для погрешности
