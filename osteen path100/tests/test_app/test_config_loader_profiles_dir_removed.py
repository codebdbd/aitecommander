import pytest

from app.config_data.config_loader import AppConfig

BROWSER_METHODS = [
    "get_chrome_profiles_dir",
    "get_firefox_profiles_dir",
    "get_edge_profiles_dir",
    "get_brave_profiles_dir",
    "get_vivaldi_profiles_dir",
    "get_opera_profiles_dir",
    "get_yandex_profiles_dir",
]


def test_appconfig_profile_methods_not_defined_directly():
    # Проверяем, что методы отсутствуют в __dict__ класса (удалены из AppConfig)
    cls_dict = AppConfig.__dict__
    for name in BROWSER_METHODS:
        assert name not in cls_dict, f"Метод {name} должен быть удалён из AppConfig"


@pytest.mark.parametrize("name", BROWSER_METHODS)
def test_access_via_paths_still_available(name):
    # Дополнительно убеждаемся, что доступ остаётся через подконфиг paths
    from app.config_data import app_config

    assert hasattr(app_config.paths, name), f"Ожидается {name} в app_config.paths"
    # Вызов должен быть возможен и возвращать Optional[Path]
    func = getattr(app_config.paths, name)
    _ = func()  # не проверяем значение, только факт вызова
