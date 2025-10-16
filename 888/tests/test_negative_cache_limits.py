import time

from app.utils.ui.icon import negative_cache as nc


def test_negative_cache_max_size_eviction(monkeypatch):
    # Ограничим размер кэша до 3
    # Используем простое поле конфигурации, чтобы не требовать наличия метода
    monkeypatch.setattr(nc.app_config, "negative_cache_max_size", 3, raising=False)

    nc.clear()

    # Проставим 5 ключей с небольшими задержками, чтобы был различимый порядок
    for i in range(5):
        nc.mark_negative(f"k{i}")
        time.sleep(0.01)

    # Должны остаться последние три ключа (LRU по времени метки)
    assert not nc.is_negative("k0")
    assert not nc.is_negative("k1")
    assert nc.is_negative("k2")
    assert nc.is_negative("k3")
    assert nc.is_negative("k4")


def test_negative_cache_periodic_cleanup(monkeypatch):
    # Сделаем базовый TTL очень коротким, чтобы быстро протухали
    monkeypatch.setattr(nc.app_config, "icon_negative_cache_ttl", 0.05, raising=False)
    monkeypatch.setattr(
        nc.app_config, "icon_negative_cache_ttl_max", 0.1, raising=False
    )

    nc.clear()

    nc.mark_negative("x")
    time.sleep(0.2)

    # Новая отметка должна не влиять на протухший "x"; он не должен считаться негативным
    nc.mark_negative("y")

    assert not nc.is_negative("x")
    assert nc.is_negative("y")
