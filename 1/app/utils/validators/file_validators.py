import logging
import os
from pathlib import Path
from typing import Optional, Union

from PIL import Image, UnidentifiedImageError

from app.config_data import app_config

# Получаем константы через app_config
MAX_ICON_SIZE = app_config.get_max_icon_size()
SUPPORTED_ICON_FORMATS = app_config.get_supported_icon_formats()

logger = logging.getLogger(__name__)


def validate_exe_path(exe_path: str) -> bool:
    """Валидация пути к exe файлу"""
    if not exe_path or not isinstance(exe_path, str):
        return False
    if not os.path.exists(exe_path):
        return False
    if not exe_path.lower().endswith('.exe'):
        return False
    # Проверяем размер файла (не более 100 МБ)
    try:
        if os.path.getsize(exe_path) > 100 * 1024 * 1024:
            logging.warning(f"EXE file too large: {exe_path}")
            return False
    except OSError:
        return False
    return True


def _validate_svg_content(path: Path) -> bool:
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            c = f.read(2048).lower()
            return '<svg' in c and '>' in c and ('</svg>' in c or '/>' in c)
    except Exception:
        return False


def is_valid_icon_file(path: Optional[Union[str, Path]]) -> bool:
    """Проверить валидность файла иконки."""
    if not path:
        return False
    
    path_obj = Path(path)
    
    if not path_obj.exists():
        return False
    
    try:
        from app.config_data import app_config
        if path_obj.stat().st_size > app_config.get_max_icon_size():
            logger.warning(f"Файл иконки слишком большой: {path}")
            return False
        
        # Проверяем расширение
        if path_obj.suffix.lower() not in SUPPORTED_ICON_FORMATS:
            return False
        
        # Для SVG проверяем содержимое
        if path_obj.suffix.lower() == '.svg':
            return _validate_svg_content(path_obj)
        
        # Для растровых форматов проверяем через PIL
        with Image.open(path_obj) as img:
            img.verify()
        return True
        
    except (UnidentifiedImageError, IOError, OSError) as e:
        logger.warning(f"Неверный или поврежденный файл изображения: {path}: {e}")
        return False


def is_cached_icon_valid(save_path: str, source_path: str) -> bool:
    """Проверяет, актуальна ли кэшированная иконка"""
    if not os.path.exists(save_path) or not is_valid_icon_file(save_path):
        return False
    try:
        ico_mtime = os.path.getmtime(save_path)
        source_mtime = os.path.getmtime(source_path)
        return ico_mtime >= source_mtime
    except OSError:
        return False
