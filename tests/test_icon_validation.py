# test_icon_validation.py
"""Тесты для модуля validation.py.

Проверяет:
- Валидацию имён иконок
- Валидацию тем
- Проверку файлов (SVG, SVGZ, raster)
- Защиту от path traversal
"""

from __future__ import annotations

import gzip
from pathlib import Path

import pytest

from app.utils.ui.icon.validation import (
    InvalidIconError,
    Theme,
    _validate_icon_name,
    is_cached_icon_valid,
    is_valid_icon_file,
    validate_theme,
)


class TestIconNameValidation:
    """Тесты валидации имён иконок."""

    def test_valid_icon_names(self):
        """Валидные имена должны проходить проверку."""
        valid_names = [
            "add.svg",
            "edit.png",
            "delete-icon.svg",
            "icon_123.png",
            "my.icon.svg",
            "a.svg",
        ]
        for name in valid_names:
            assert _validate_icon_name(name) is True, f"Failed for: {name}"

    def test_invalid_icon_names(self):
        """Невалидные имена должны отклоняться."""
        invalid_names = [
            "",  # пустая строка
            "   ",  # только пробелы
            "../icon.svg",  # traversal
            "..\\icon.svg",  # traversal Windows
            "path/to/icon.svg",  # слэш
            "path\\to\\icon.svg",  # бэкслэш
            "icon with spaces.svg",  # пробелы
            "иконка.svg",  # не-ASCII
            "icon@#$.svg",  # спецсимволы
        ]
        for name in invalid_names:
            assert _validate_icon_name(name) is False, f"Should fail for: {name}"

    def test_path_traversal_protection(self):
        """Защита от path traversal атак."""
        traversal_attempts = [
            "../../../etc/passwd",
            "..\\..\\..\\windows\\system32",
            "icon/../../../secret.txt",
        ]
        for attempt in traversal_attempts:
            assert _validate_icon_name(attempt) is False


class TestThemeValidation:
    """Тесты валидации тем."""

    def test_valid_themes(self):
        """Валидные темы должны нормализоваться."""
        assert validate_theme("light") == "light"
        assert validate_theme("dark") == "dark"
        assert validate_theme("LIGHT") == "light"
        assert validate_theme("Dark") == "dark"
        assert validate_theme("  light  ") == "light"

    def test_invalid_themes_fallback_to_light(self):
        """Невалидные темы должны возвращать 'light'."""
        assert validate_theme("") == "light"
        assert validate_theme("unknown") == "light"
        assert validate_theme("blue") == "light"
        assert validate_theme(None) == "light"
        assert validate_theme(123) == "light"

    def test_theme_enum(self):
        """Проверка Theme enum."""
        assert Theme.LIGHT.value == "light"
        assert Theme.DARK.value == "dark"
        assert Theme.from_string("dark") == Theme.DARK
        assert Theme.from_string("light") == Theme.LIGHT
        assert Theme.from_string("unknown") == Theme.LIGHT


class TestSVGValidation:
    """Тесты валидации SVG файлов."""

    def test_valid_svg(self, tmp_path):
        """Валидный SVG должен проходить проверку."""
        svg_file = tmp_path / "valid.svg"
        svg_file.write_text(
            '<?xml version="1.0"?>\n'
            '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24">\n'
            '  <circle cx="12" cy="12" r="10" fill="red"/>\n'
            '</svg>',
            encoding='utf-8'
        )
        
        assert is_valid_icon_file(svg_file) is True

    def test_invalid_svg_no_tags(self, tmp_path):
        """SVG без тегов должен отклоняться."""
        svg_file = tmp_path / "invalid.svg"
        svg_file.write_text("This is not SVG", encoding='utf-8')
        
        assert is_valid_icon_file(svg_file) is False

    def test_invalid_svg_incomplete(self, tmp_path):
        """Неполный SVG должен отклоняться."""
        svg_file = tmp_path / "incomplete.svg"
        svg_file.write_text('<svg xmlns="http://www.w3.org/2000/svg">', encoding='utf-8')
        
        assert is_valid_icon_file(svg_file) is False

    def test_svg_size_limit(self, tmp_path):
        """Слишком большой SVG должен отклоняться."""
        svg_file = tmp_path / "huge.svg"
        # Создаём файл больше лимита
        huge_content = '<?xml version="1.0"?>\n<svg>' + 'x' * (10 * 1024 * 1024) + '</svg>'
        svg_file.write_text(huge_content, encoding='utf-8')
        
        assert is_valid_icon_file(svg_file) is False


class TestSVGZValidation:
    """Тесты валидации SVGZ (gzip compressed SVG) файлов."""

    def test_valid_svgz(self, tmp_path):
        """Валидный SVGZ должен проходить проверку."""
        svgz_file = tmp_path / "valid.svgz"
        svg_content = (
            '<?xml version="1.0"?>\n'
            '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24">\n'
            '  <circle cx="12" cy="12" r="10" fill="blue"/>\n'
            '</svg>'
        )
        
        with gzip.open(svgz_file, 'wb') as f:
            f.write(svg_content.encode('utf-8'))
        
        assert is_valid_icon_file(svgz_file) is True

    def test_invalid_svgz_not_gzip(self, tmp_path):
        """Не-gzip файл с расширением .svgz должен отклоняться."""
        svgz_file = tmp_path / "fake.svgz"
        svgz_file.write_bytes(b"Not a gzip file")
        
        assert is_valid_icon_file(svgz_file) is False

    def test_invalid_svgz_corrupted(self, tmp_path):
        """Повреждённый SVGZ должен отклоняться."""
        svgz_file = tmp_path / "corrupted.svgz"
        # Gzip header но повреждённые данные
        svgz_file.write_bytes(b'\x1f\x8b\x08\x00corrupted data')
        
        assert is_valid_icon_file(svgz_file) is False


class TestRasterValidation:
    """Тесты валидации растровых форматов."""

    def test_valid_png(self, tmp_path):
        """Валидный PNG должен проходить проверку."""
        png_file = tmp_path / "valid.png"
        # Минимальный валидный PNG (1x1 прозрачный)
        png_file.write_bytes(
            b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
            b'\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01'
            b'\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82'
        )
        
        assert is_valid_icon_file(png_file) is True

    def test_invalid_png_corrupted(self, tmp_path):
        """Повреждённый PNG должен отклоняться."""
        png_file = tmp_path / "corrupted.png"
        png_file.write_bytes(b'\x89PNG\r\n\x1a\ncorrupted')
        
        assert is_valid_icon_file(png_file) is False

    def test_unsupported_format(self, tmp_path):
        """Неподдерживаемый формат должен отклоняться."""
        webp_file = tmp_path / "image.webp"
        webp_file.write_bytes(b'RIFF\x00\x00\x00\x00WEBP')
        
        assert is_valid_icon_file(webp_file) is False

    def test_nonexistent_file(self, tmp_path):
        """Несуществующий файл должен отклоняться."""
        nonexistent = tmp_path / "nonexistent.png"
        
        assert is_valid_icon_file(nonexistent) is False

    def test_empty_file(self, tmp_path):
        """Пустой файл должен отклоняться."""
        empty_file = tmp_path / "empty.png"
        empty_file.write_bytes(b'')
        
        assert is_valid_icon_file(empty_file) is False


class TestCachedIconValidation:
    """Тесты проверки актуальности кэшированных иконок."""

    def test_cached_icon_valid_newer(self, tmp_path):
        """Кэш новее источника — валиден."""
        source = tmp_path / "source.svg"
        cached = tmp_path / "cached.png"
        
        source.write_text('<svg></svg>')
        import time
        time.sleep(0.01)
        cached.write_bytes(
            b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
            b'\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01'
            b'\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82'
        )
        
        assert is_cached_icon_valid(cached, source) is True

    def test_cached_icon_invalid_older(self, tmp_path):
        """Кэш старее источника — невалиден."""
        source = tmp_path / "source.svg"
        cached = tmp_path / "cached.png"
        
        cached.write_bytes(
            b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
            b'\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01'
            b'\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82'
        )
        import time
        time.sleep(0.01)
        source.write_text('<svg></svg>')
        
        assert is_cached_icon_valid(cached, source) is False

    def test_cached_icon_not_exists(self, tmp_path):
        """Несуществующий кэш — невалиден."""
        source = tmp_path / "source.svg"
        cached = tmp_path / "nonexistent.png"
        
        source.write_text('<svg></svg>')
        
        assert is_cached_icon_valid(cached, source) is False

    def test_cached_icon_invalid_file(self, tmp_path):
        """Невалидный файл кэша — невалиден."""
        source = tmp_path / "source.svg"
        cached = tmp_path / "invalid.png"
        
        source.write_text('<svg></svg>')
        cached.write_bytes(b'invalid png')
        
        assert is_cached_icon_valid(cached, source) is False


class TestEdgeCases:
    """Тесты граничных случаев."""

    def test_none_path(self):
        """None вместо пути должен отклоняться."""
        assert is_valid_icon_file(None) is False

    def test_empty_string_path(self):
        """Пустая строка должна отклоняться."""
        assert is_valid_icon_file("") is False

    def test_directory_instead_of_file(self, tmp_path):
        """Директория вместо файла должна отклоняться."""
        directory = tmp_path / "icons"
        directory.mkdir()
        
        assert is_valid_icon_file(directory) is False

    def test_symlink_to_valid_file(self, tmp_path):
        """Симлинк на валидный файл должен работать."""
        real_file = tmp_path / "real.png"
        real_file.write_bytes(
            b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
            b'\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01'
            b'\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82'
        )
        
        symlink = tmp_path / "link.png"
        try:
            symlink.symlink_to(real_file)
            assert is_valid_icon_file(symlink) is True
        except OSError:
            # Симлинки могут не поддерживаться на Windows без прав
            pytest.skip("Symlinks not supported")
