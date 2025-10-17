# test_icon_di.py
"""Тесты для Dependency Injection в модуле иконок."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import pytest

from app.utils.ui.icon.cache_manager import IconManager, ThreadSafeIconCache
from app.utils.ui.icon.path_service import IconPathService


class TestIconPathServiceDI:
    """Тесты DI для IconPathService."""

    def test_singleton_mode_without_args(self):
        """Без аргументов должен возвращать синглтон."""
        service1 = IconPathService()
        service2 = IconPathService()
        
        assert service1 is service2

    def test_di_mode_with_args(self, tmp_path):
        """С аргументами должен создавать новый экземпляр."""
        user_dir = tmp_path / "user"
        ui_dir = tmp_path / "ui"
        
        service = IconPathService(user_icons_dir=user_dir, ui_icons_dir=ui_dir)
        
        # Должен вернуть переданные директории
        assert service.get_user_icons_dir() == user_dir
        assert service.get_ui_icons_dir() == ui_dir

    def test_di_mode_with_custom_config(self, tmp_path):
        """Должен использовать переданный config."""
        mock_config = Mock()
        mock_config.paths.get_link_icons_dir.return_value = tmp_path / "custom_user"
        mock_config.paths.get_ui_icons_dir.return_value = tmp_path / "custom_ui"
        
        service = IconPathService(config=mock_config)
        
        # Должен использовать mock config
        user_dir = service.get_user_icons_dir()
        assert user_dir == tmp_path / "custom_user"
        mock_config.paths.get_link_icons_dir.assert_called_once()

    def test_di_instances_are_independent(self, tmp_path):
        """DI экземпляры должны быть независимыми."""
        dir1 = tmp_path / "dir1"
        dir2 = tmp_path / "dir2"
        
        service1 = IconPathService(user_icons_dir=dir1)
        service2 = IconPathService(user_icons_dir=dir2)
        
        assert service1 is not service2
        assert service1.get_user_icons_dir() != service2.get_user_icons_dir()


class TestIconManagerDI:
    """Тесты DI для IconManager."""

    def test_singleton_mode_without_args(self):
        """Без аргументов должен возвращать синглтон."""
        manager1 = IconManager()
        manager2 = IconManager()
        
        assert manager1 is manager2

    def test_di_mode_with_custom_cache(self):
        """С кастомным кэшем должен создавать новый экземпляр."""
        custom_cache = ThreadSafeIconCache(maxsize=50)
        manager = IconManager(cache=custom_cache)
        
        # Должен использовать переданный кэш
        assert manager._cache is custom_cache

    def test_di_mode_with_capacity(self):
        """С параметром capacity должен создавать кастомный кэш."""
        manager = IconManager(capacity=100)
        
        # Должен создать кэш с заданной ёмкостью
        assert manager._cache._capacity == 100

    def test_di_instances_are_independent(self):
        """DI экземпляры должны быть независимыми."""
        manager1 = IconManager(capacity=50)
        manager2 = IconManager(capacity=100)
        
        assert manager1 is not manager2
        assert manager1._cache is not manager2._cache
        assert manager1._cache._capacity != manager2._cache._capacity


class TestBackwardCompatibility:
    """Проверка обратной совместимости."""

    def test_existing_code_still_works(self):
        """Существующий код без DI должен продолжать работать."""
        # Старый способ - синглтон
        service = IconPathService()
        manager = IconManager()
        
        # Должны работать как раньше
        assert isinstance(service, IconPathService)
        assert isinstance(manager, IconManager)
        
        # Повторные вызовы возвращают тот же экземпляр
        assert IconPathService() is service
        assert IconManager() is manager
