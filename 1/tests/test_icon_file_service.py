# test_icon_file_service.py
"""Тесты для IconFileService - сервиса файловых операций с иконками."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.utils.ui.icon.file_service import IconFileService


class TestIconFileService:
    """Тесты IconFileService."""

    def test_copy_icon_to_user_dir(self, tmp_path):
        """Должен копировать валидную иконку в пользовательскую директорию."""
        # Создаём исходную иконку
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        source_file = source_dir / "test.png"
        source_file.write_bytes(
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
            b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
        )

        # Копируем
        target_dir = tmp_path / "target"
        service = IconFileService(target_dir)
        result = service.copy_icon_to_user_dir(source_file)

        # Проверяем
        assert result.exists()
        assert result.parent == target_dir
        assert result.name == "test.png"

    def test_copy_icon_with_name_collision(self, tmp_path):
        """Должен автоматически переименовывать при коллизии имён."""
        # Создаём исходную иконку
        source_file = tmp_path / "test.png"
        source_file.write_bytes(
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
            b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
        )

        target_dir = tmp_path / "target"
        target_dir.mkdir()

        # Создаём существующий файл
        existing = target_dir / "test.png"
        existing.write_text("existing")

        # Копируем
        service = IconFileService(target_dir)
        result = service.copy_icon_to_user_dir(source_file)

        # Должен переименовать
        assert result.exists()
        assert result.name == "test_1.png"

    def test_copy_nonexistent_file_raises(self, tmp_path):
        """Должен выбрасывать FileNotFoundError для несуществующего файла."""
        service = IconFileService(tmp_path)

        with pytest.raises(FileNotFoundError):
            service.copy_icon_to_user_dir(tmp_path / "nonexistent.png")

    def test_copy_invalid_icon_raises(self, tmp_path):
        """Должен выбрасывать ValueError для невалидной иконки."""
        # Создаём невалидный файл
        invalid_file = tmp_path / "invalid.png"
        invalid_file.write_text("not an image")

        target_dir = tmp_path / "target"
        service = IconFileService(target_dir)

        with pytest.raises(ValueError, match="not a valid icon"):
            service.copy_icon_to_user_dir(invalid_file)

    def test_get_supported_formats_filter(self, tmp_path):
        """Должен возвращать строку фильтра для диалога."""
        service = IconFileService(tmp_path)
        filter_str = service.get_supported_formats_filter()

        assert isinstance(filter_str, str)
        assert "Images" in filter_str
        assert "*.png" in filter_str or "*.svg" in filter_str

    def test_validate_icon_file(self, tmp_path):
        """Должен валидировать файл иконки."""
        # Валидный PNG
        valid_file = tmp_path / "valid.png"
        valid_file.write_bytes(
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
            b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
        )

        service = IconFileService(tmp_path)
        assert service.validate_icon_file(valid_file) is True

        # Невалидный файл
        invalid_file = tmp_path / "invalid.txt"
        invalid_file.write_text("not an image")
        assert service.validate_icon_file(invalid_file) is False
