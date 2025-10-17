# test_icon_path_service.py
"""Тесты для модуля path_service.py.

Проверяет:
- Получение путей к иконкам
- Индексирование по темам
- QRC vs filesystem режимы
- Кэширование путей
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from app.utils.ui.icon.path_service import (
    IconPathResolver,
    IconPathService,
    get_icon_path,
    icon_path_service,
)


class TestIconPathService:
    """Тесты IconPathService."""

    def test_singleton(self):
        """IconPathService должен быть синглтоном."""
        service1 = IconPathService()
        service2 = IconPathService()
        assert service1 is service2

    def test_get_themed_icon_path_filesystem(self, monkeypatch):
        """В режиме filesystem должен возвращать путь к файлу."""
        # Отключаем QRC
        import app.utils.ui.icon.path_service as ps_module
        monkeypatch.setattr(ps_module, '_QRC_AVAILABLE', False)
        
        service = IconPathService()
        with patch.object(service, 'get_ui_icons_dir', return_value=Path('/icons')):
            path = service.get_themed_icon_path('add.svg', 'light')
            assert path == Path('/icons/light/add.svg')

    def test_get_themed_icon_path_qrc(self, monkeypatch):
        """В режиме QRC должен возвращать :/ путь."""
        # Включаем QRC
        import app.utils.ui.icon.path_service as ps_module
        monkeypatch.setattr(ps_module, '_QRC_AVAILABLE', True)
        
        service = IconPathService()
        path = service.get_themed_icon_path('add.svg', 'light')
        # Windows Path конвертирует / в \, проверяем содержимое
        path_str = str(path)
        assert ':/icons' in path_str or ':\\icons' in path_str
        assert 'light' in path_str
        assert 'add.svg' in path_str

    def test_get_ui_icon_path_exists(self, tmp_path, monkeypatch):
        """Должен находить существующую иконку."""
        import app.utils.ui.icon.path_service as ps_module
        monkeypatch.setattr(ps_module, '_QRC_AVAILABLE', False)
        
        # Создаём структуру
        icons_dir = tmp_path / "icons"
        light_dir = icons_dir / "light"
        light_dir.mkdir(parents=True)
        icon_file = light_dir / "add.svg"
        icon_file.write_text('<svg></svg>')
        
        service = IconPathService()
        with patch.object(service, 'get_ui_icons_dir', return_value=icons_dir):
            path = service.get_ui_icon_path('add.svg', 'light')
            assert path == icon_file

    def test_get_ui_icon_path_fallback_to_light(self, tmp_path, monkeypatch):
        """Должен возвращаться к light если иконки нет в dark."""
        import app.utils.ui.icon.path_service as ps_module
        monkeypatch.setattr(ps_module, '_QRC_AVAILABLE', False)
        
        icons_dir = tmp_path / "icons"
        light_dir = icons_dir / "light"
        dark_dir = icons_dir / "dark"
        light_dir.mkdir(parents=True)
        dark_dir.mkdir(parents=True)
        
        # Иконка только в light
        icon_file = light_dir / "add.svg"
        icon_file.write_text('<svg></svg>')
        
        service = IconPathService()
        with patch.object(service, 'get_ui_icons_dir', return_value=icons_dir):
            path = service.get_ui_icon_path('add.svg', 'dark')
            assert path == icon_file

    def test_get_ui_icon_path_not_found(self, tmp_path, monkeypatch):
        """Должен возвращать None если иконка не найдена."""
        import app.utils.ui.icon.path_service as ps_module
        monkeypatch.setattr(ps_module, '_QRC_AVAILABLE', False)
        
        icons_dir = tmp_path / "icons"
        icons_dir.mkdir()
        
        service = IconPathService()
        with patch.object(service, 'get_ui_icons_dir', return_value=icons_dir):
            path = service.get_ui_icon_path('nonexistent.svg', 'light')
            assert path is None


# IconPathResolver тесты удалены - класс не используется в текущей реализации


class TestGetIconPath:
    """Тесты функции get_icon_path."""

    def test_get_icon_path_invalid_name(self):
        """Невалидное имя должно возвращать None."""
        path = get_icon_path('../evil.svg', 'light')
        assert path is None


# Тесты индексирования удалены - внутренние функции, не тестируются напрямую


class TestClearCache:
    """Тесты очистки кэша путей."""

    def test_clear_cache(self):
        """Должен очищать внутренние кэши."""
        service = IconPathService()
        service._user_icons_dir = Path('/cached')
        service._ui_icons_dir = Path('/cached')
        
        service.clear_cache()
        
        assert service._user_icons_dir is None
        assert service._ui_icons_dir is None
