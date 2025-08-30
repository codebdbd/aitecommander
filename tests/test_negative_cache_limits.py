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

    # Должно остаться не более 3 самых новых
    assert len(nc._NEGATIVE_CACHE) <= 3  # noqa: SLF001 (тест внутреннего состояния)

    # Самые ранние ключи должны быть вытеснены
    remaining = set(nc._NEGATIVE_CACHE.keys())
    assert "k0" not in remaining and "k1" not in remaining


def test_negative_cache_periodic_cleanup(monkeypatch):
    # Сделаем базовый TTL очень коротким, чтобы быстро протухали
    monkeypatch.setattr(nc.app_config, "icon_negative_cache_ttl", 0.05, raising=False)
    monkeypatch.setattr(nc.app_config, "icon_negative_cache_ttl_max", 0.1, raising=False)

    nc.clear()

    nc.mark_negative("x")
    time.sleep(0.2)

    # Новая отметка должна спровоцировать сборку мусора
    nc.mark_negative("y")

    assert "x" not in nc._NEGATIVE_CACHE  # noqa: SLF001
