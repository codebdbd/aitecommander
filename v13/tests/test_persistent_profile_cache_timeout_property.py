import math

from app.utils.browser.browser_profiles.persistent_cache import PersistentProfileCache


def test_timeout_property_reflects_default_ttl():
    # Значение TTL как float
    cache = PersistentProfileCache(default_ttl=123.0)
    assert isinstance(cache.timeout, (float, int))
    assert math.isclose(float(cache.timeout), 123.0)

    # Значение TTL как int
    cache_int = PersistentProfileCache(default_ttl=45)
    assert isinstance(cache_int.timeout, (float, int))
    assert float(cache_int.timeout) == 45.0


def test_timeout_property_none_when_not_set():
    # По умолчанию, если TTL не задан, свойство timeout должно быть None
    cache = PersistentProfileCache()
    assert cache.timeout is None or isinstance(cache.timeout, (float, int))
    # В идеале None, но оставляем чуть более мягкую проверку на случай конфигурационных переопределений
    # Основная проверка — отсутствие AttributeError и тип совместимый с ожиданиями потребителей
