# test_icon_converters.py
"""Тесты для модуля converters.py.

Проверяет:
- Конвертацию SVG → PNG
- Конвертацию raster → PNG
- Копирование иконок
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PyQt6.QtGui import QImage

from app.utils.ui.icon.icon_operations.converters import (
    convert_icon_to_png_128,
    convert_icon_to_png_32,
    convert_raster_icon_to_png,
    copy_icon,
    copy_icon_smart,
    copy_icon_to_path,
)


class TestSVGConversion:
    """Тесты конвертации SVG в PNG."""

    def test_convert_svg_to_png_128(self, tmp_path):
        """Должен конвертировать SVG в PNG 128x128."""
        svg_file = tmp_path / "icon.svg"
        svg_file.write_text(
            '<?xml version="1.0"?>\n'
            '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24">\n'
            '  <circle cx="12" cy="12" r="10" fill="red"/>\n'
            '</svg>',
            encoding='utf-8'
        )
        
        png_file = tmp_path / "icon.png"
        
        result = convert_icon_to_png_128(str(svg_file), str(png_file), size=128)
        
        assert result is True
        assert png_file.exists()
        
        # Проверяем размер
        img = QImage(str(png_file))
        assert img.width() == 128
        assert img.height() == 128

    def test_convert_svg_to_png_32(self, tmp_path):
        """Должен конвертировать SVG в PNG 32x32."""
        svg_file = tmp_path / "icon.svg"
        svg_file.write_text(
            '<?xml version="1.0"?>\n'
            '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24">\n'
            '  <rect x="2" y="2" width="20" height="20" fill="blue"/>\n'
            '</svg>',
            encoding='utf-8'
        )
        
        png_file = tmp_path / "icon.png"
        
        result = convert_icon_to_png_32(str(svg_file), str(png_file), size=32)
        
        assert result is True
        assert png_file.exists()
        
        img = QImage(str(png_file))
        assert img.width() == 32
        assert img.height() == 32

    def test_convert_invalid_svg(self, tmp_path):
        """Невалидный SVG должен возвращать False."""
        svg_file = tmp_path / "invalid.svg"
        svg_file.write_text("Not an SVG", encoding='utf-8')
        
        png_file = tmp_path / "output.png"
        
        result = convert_icon_to_png_128(str(svg_file), str(png_file))
        
        assert result is False

    def test_convert_nonexistent_svg(self, tmp_path):
        """Несуществующий SVG должен возвращать False."""
        svg_file = tmp_path / "nonexistent.svg"
        png_file = tmp_path / "output.png"
        
        result = convert_icon_to_png_128(str(svg_file), str(png_file))
        
        assert result is False


class TestRasterConversion:
    """Тесты конвертации растровых форматов."""

    def test_convert_png_to_png_resize(self, tmp_path):
        """Должен изменять размер PNG."""
        # Создаём PNG 1x1
        src_png = tmp_path / "source.png"
        src_png.write_bytes(
            b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
            b'\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01'
            b'\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82'
        )
        
        dst_png = tmp_path / "resized.png"
        
        result = convert_raster_icon_to_png(str(src_png), str(dst_png), size=32)
        
        assert result is True
        assert dst_png.exists()
        
        img = QImage(str(dst_png))
        assert img.width() == 32
        assert img.height() == 32

    def test_convert_invalid_raster(self, tmp_path):
        """Невалидный файл должен возвращать False."""
        src_file = tmp_path / "invalid.png"
        src_file.write_bytes(b"invalid data")
        
        dst_file = tmp_path / "output.png"
        
        result = convert_raster_icon_to_png(str(src_file), str(dst_file))
        
        assert result is False


class TestCopyIcon:
    """Тесты копирования иконок."""

    def test_copy_icon_smart(self, tmp_path):
        """Должен копировать иконку в директорию."""
        src_file = tmp_path / "source" / "icon.svg"
        src_file.parent.mkdir()
        src_file.write_text('<svg></svg>')
        
        dest_dir = tmp_path / "dest"
        
        result = copy_icon_smart(str(src_file), dest_dir)
        
        assert result == "icon.svg"
        assert (dest_dir / "icon.svg").exists()

    def test_copy_icon_smart_avoid_duplicates(self, tmp_path):
        """Должен избегать дубликатов при копировании."""
        src_file = tmp_path / "source" / "icon.svg"
        src_file.parent.mkdir()
        src_file.write_text('<svg></svg>')
        
        dest_dir = tmp_path / "dest"
        dest_dir.mkdir()
        
        # Первая копия
        result1 = copy_icon_smart(str(src_file), dest_dir)
        assert result1 == "icon.svg"
        
        # Вторая копия - должна получить другое имя
        result2 = copy_icon_smart(str(src_file), dest_dir)
        assert result2 == "icon_1.svg"
        assert (dest_dir / "icon_1.svg").exists()

    def test_copy_icon_to_path(self, tmp_path):
        """Должен копировать иконку по указанному пути."""
        src_file = tmp_path / "source.svg"
        src_file.write_text('<svg></svg>')
        
        dst_file = tmp_path / "subdir" / "dest.svg"
        
        result = copy_icon_to_path(str(src_file), str(dst_file))
        
        assert result is True
        assert dst_file.exists()
        assert dst_file.read_text() == '<svg></svg>'

    def test_copy_icon_to_path_creates_parent(self, tmp_path):
        """Должен создавать родительские директории."""
        src_file = tmp_path / "source.svg"
        src_file.write_text('<svg></svg>')
        
        dst_file = tmp_path / "a" / "b" / "c" / "dest.svg"
        
        result = copy_icon_to_path(str(src_file), str(dst_file))
        
        assert result is True
        assert dst_file.exists()
        assert dst_file.parent.exists()

    def test_copy_icon_invalid_source(self, tmp_path):
        """Невалидный источник должен выбрасывать исключение."""
        src_file = tmp_path / "nonexistent.svg"
        dest_dir = tmp_path / "dest"
        
        with pytest.raises(Exception):  # InvalidIconError
            copy_icon_smart(str(src_file), dest_dir)

    def test_copy_icon_backward_compat(self, tmp_path):
        """copy_icon должен работать как copy_icon_smart."""
        src_file = tmp_path / "icon.svg"
        src_file.write_text('<svg></svg>')
        
        dest_dir = tmp_path / "dest"
        
        result = copy_icon(str(src_file), dest_dir)
        
        assert result == "icon.svg"
        assert (dest_dir / "icon.svg").exists()


class TestEdgeCases:
    """Тесты граничных случаев."""

    def test_convert_creates_parent_dirs(self, tmp_path):
        """Конвертация должна создавать родительские директории."""
        svg_file = tmp_path / "icon.svg"
        svg_file.write_text(
            '<?xml version="1.0"?>\n'
            '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24">\n'
            '  <circle cx="12" cy="12" r="10"/>\n'
            '</svg>',
            encoding='utf-8'
        )
        
        png_file = tmp_path / "a" / "b" / "c" / "icon.png"
        
        result = convert_icon_to_png_128(str(svg_file), str(png_file))
        
        assert result is True
        assert png_file.exists()
        assert png_file.parent.exists()

    def test_convert_overwrites_existing(self, tmp_path):
        """Конвертация должна перезаписывать существующий файл."""
        svg_file = tmp_path / "icon.svg"
        svg_file.write_text(
            '<?xml version="1.0"?>\n'
            '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24">\n'
            '  <circle cx="12" cy="12" r="10"/>\n'
            '</svg>',
            encoding='utf-8'
        )
        
        png_file = tmp_path / "icon.png"
        png_file.write_bytes(b"old content")
        
        result = convert_icon_to_png_128(str(svg_file), str(png_file))
        
        assert result is True
        # Проверяем что файл перезаписан
        assert png_file.read_bytes() != b"old content"
