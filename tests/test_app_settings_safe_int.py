import pytest

from app.settings import AppSettings
from app.config_data import app_config


@pytest.fixture()
def settings_tmp(monkeypatch):
    # Используем отдельный QSettings через monkeypatch на org/app имена, чтобы не трогать реальные настройки
    monkeypatch.setattr(app_config, "get_org_name", lambda: "Codebdbd-TestOrg")
    monkeypatch.setattr(app_config, "get_app_name", lambda: "AiteCommander-TestApp")
    s = AppSettings()
    # Очистим потенциальные остатки
    s._qs.clear()
    try:
        yield s
    finally:
        s._qs.clear()


def test_get_max_backups_safe_cast(settings_tmp: AppSettings, caplog):
    s = settings_tmp
    default_value = app_config.get_max_backups()

    # Некорректное строковое значение
    s._qs.setValue("Backup/MaxCopies", "not-an-int")
    with caplog.at_level("WARNING"):
        val = s.get_max_backups()
    assert val == default_value
    assert any("некорректное числовое значение" in rec.message for rec in caplog.records)

    # Пустая строка -> дефолт
    s._qs.setValue("Backup/MaxCopies", " ")
    val2 = s.get_max_backups()
    assert val2 == default_value

    # Корректное значение
    s._qs.setValue("Backup/MaxCopies", 7)
    assert s.get_max_backups() == 7


def test_get_font_size_safe_cast(settings_tmp: AppSettings, caplog):
    s = settings_tmp
    default_value = app_config.get_default_font_size()

    s._qs.setValue("UI/FontSize", None)
    assert s.get_font_size() == default_value

    s._qs.setValue("UI/FontSize", "bad")
    with caplog.at_level("WARNING"):
        val = s.get_font_size()
    assert val == default_value

    s._qs.setValue("UI/FontSize", 15)
    assert s.get_font_size() == 15


def test_get_dpi_scale_safe_cast(settings_tmp: AppSettings, caplog):
    s = settings_tmp
    default_value = 100

    s._qs.setValue("UI/DPIScale", "oops")
    with caplog.at_level("WARNING"):
        val = s.get_dpi_scale()
    assert val == default_value

    s._qs.setValue("UI/DPIScale", " ")
    assert s.get_dpi_scale() == default_value

    s._qs.setValue("UI/DPIScale", 125)
    assert s.get_dpi_scale() == 125
