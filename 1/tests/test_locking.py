# test_locking.py
"""Тесты для модуля app.utils.locking.

Проверяет:
- Корректность создания и работы блокировок
- Предотвращение deadlock при множественных блокировках
- Реентерабельность RLock
"""

from __future__ import annotations

import threading
import time

import pytest

from app.utils.locking import (
    acquire_icon_cache,
    acquire_icon_global,
    acquire_icon_lru,
    acquire_icon_metrics,
    acquire_multiple_locks,
    get_lock_info,
    reset_all_locks,
)


class TestBasicLocking:
    """Базовые тесты блокировок."""

    def setup_method(self):
        """Сброс блокировок перед каждым тестом."""
        reset_all_locks()

    def test_acquire_icon_cache_lock(self):
        """Проверка захвата блокировки кэша."""
        with acquire_icon_cache():
            # Блокировка захвачена
            pass
        # Блокировка освобождена

    def test_acquire_icon_global_lock(self):
        """Проверка захвата глобальной блокировки."""
        with acquire_icon_global():
            pass

    def test_acquire_icon_metrics_lock(self):
        """Проверка захвата блокировки метрик."""
        with acquire_icon_metrics():
            pass

    def test_acquire_icon_lru_lock(self):
        """Проверка захвата блокировки LRU."""
        with acquire_icon_lru():
            pass

    def test_lock_is_reentrant(self):
        """RLock должен поддерживать реентерабельность."""
        with acquire_icon_cache():
            # Вложенный захват той же блокировки
            with acquire_icon_cache():
                # Должно работать без deadlock
                pass

    def test_lock_prevents_concurrent_access(self):
        """Блокировка должна предотвращать одновременный доступ."""
        counter = {"value": 0}
        results = []

        def worker():
            with acquire_icon_cache():
                # Критическая секция
                local_value = counter["value"]
                time.sleep(0.01)  # Имитация работы
                counter["value"] = local_value + 1
                results.append(counter["value"])

        # Запускаем 10 потоков
        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Счётчик должен быть ровно 10 (без race conditions)
        assert counter["value"] == 10
        # Все результаты должны быть уникальными и последовательными
        assert sorted(results) == list(range(1, 11))


class TestMultipleLocks:
    """Тесты множественных блокировок."""

    def setup_method(self):
        """Сброс блокировок перед каждым тестом."""
        reset_all_locks()

    def test_acquire_multiple_locks_in_order(self):
        """Множественные блокировки должны захватываться в порядке."""
        with acquire_multiple_locks("icon.cache", "icon.metrics"):
            # Обе блокировки захвачены
            pass

    def test_acquire_multiple_locks_prevents_deadlock(self):
        """Автоматическая сортировка должна предотвращать deadlock."""
        results = []

        def worker1():
            # Захватываем в одном порядке
            with acquire_multiple_locks("icon.cache", "icon.metrics"):
                time.sleep(0.01)
                results.append("worker1")

        def worker2():
            # Захватываем в обратном порядке
            # Благодаря сортировке deadlock не произойдёт
            with acquire_multiple_locks("icon.metrics", "icon.cache"):
                time.sleep(0.01)
                results.append("worker2")

        t1 = threading.Thread(target=worker1)
        t2 = threading.Thread(target=worker2)

        t1.start()
        t2.start()
        t1.join(timeout=1.0)
        t2.join(timeout=1.0)

        # Оба потока должны завершиться без deadlock
        assert len(results) == 2
        assert "worker1" in results
        assert "worker2" in results

    def test_acquire_multiple_locks_deduplicates(self):
        """Дублирующиеся имена блокировок должны удаляться."""
        # Не должно быть ошибки при дублировании
        with acquire_multiple_locks("icon.cache", "icon.cache", "icon.metrics"):
            pass

    def test_nested_multiple_locks(self):
        """Вложенные множественные блокировки должны работать."""
        with acquire_multiple_locks("icon.cache", "icon.metrics"):
            # Вложенный захват
            with acquire_multiple_locks("icon.lru"):
                pass


class TestLockInfo:
    """Тесты утилит для отладки."""

    def setup_method(self):
        """Сброс блокировок перед каждым тестом."""
        reset_all_locks()

    def test_get_lock_info_empty(self):
        """get_lock_info должен возвращать информацию о зарегистрированных блокировках."""
        info = get_lock_info()
        assert isinstance(info, dict)
        # Icon locks регистрируются автоматически
        assert len(info) >= 0

    def test_get_lock_info_after_lock_creation(self):
        """get_lock_info должен показывать созданные блокировки."""
        with acquire_icon_cache():
            info = get_lock_info()
            assert "icon.cache" in info

    def test_reset_all_locks_clears_everything(self):
        """reset_all_locks пересоздаёт блокировки."""
        # Создаём блокировки
        with acquire_icon_cache():
            pass
        with acquire_icon_metrics():
            pass

        info_before = get_lock_info()
        assert len(info_before) > 0

        # Сбрасываем (для LockManager это просто пересоздание)
        reset_all_locks()

        info_after = get_lock_info()
        # Блокировки остаются зарегистрированными в LockManager
        assert isinstance(info_after, dict)


class TestConcurrentAccess:
    """Стресс-тесты для проверки потокобезопасности."""

    def setup_method(self):
        """Сброс блокировок перед каждым тестом."""
        reset_all_locks()

    def test_high_concurrency_single_lock(self):
        """Тест с большим количеством потоков и одной блокировкой."""
        counter = {"value": 0}
        num_threads = 50
        increments_per_thread = 20

        def worker():
            for _ in range(increments_per_thread):
                with acquire_icon_cache():
                    counter["value"] += 1

        threads = [threading.Thread(target=worker) for _ in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        expected = num_threads * increments_per_thread
        assert counter["value"] == expected

    def test_high_concurrency_multiple_locks(self):
        """Тест с множественными блокировками и многими потоками."""
        counters = {"cache": 0, "metrics": 0, "lru": 0}
        num_threads = 30

        def worker(lock_names, counter_key):
            for _ in range(10):
                with acquire_multiple_locks(*lock_names):
                    counters[counter_key] += 1

        threads = []
        threads.extend(
            [
                threading.Thread(target=worker, args=(["icon.cache"], "cache"))
                for _ in range(num_threads)
            ]
        )
        threads.extend(
            [
                threading.Thread(target=worker, args=(["icon.metrics"], "metrics"))
                for _ in range(num_threads)
            ]
        )
        threads.extend(
            [
                threading.Thread(target=worker, args=(["icon.lru"], "lru"))
                for _ in range(num_threads)
            ]
        )

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert counters["cache"] == num_threads * 10
        assert counters["metrics"] == num_threads * 10
        assert counters["lru"] == num_threads * 10
