from app.utils.browser.browser_profiles import profile_manager as pm_module


def test_browser_profile_manager_cache_timeout_reflects_config(monkeypatch):
    # Подменяем конфигурацию, чтобы вернуть контролируемый cache_timeout
    from app.config_data import app_config

    def fake_get_browser_profile_settings():
        return {"cache_timeout": 777}

    monkeypatch.setattr(
        app_config, "get_browser_profile_settings", fake_get_browser_profile_settings, raising=True
    )

    # Сбрасываем синглтон, чтобы менеджер пересоздался с новой конфигурацией
    monkeypatch.setattr(pm_module, "_PROFILE_MANAGER", None, raising=True)

    mgr = pm_module.get_profile_manager()
    # Свойство timeout должно отражать значение из конфигурации
    assert getattr(mgr.cache, "timeout", None) == 777
