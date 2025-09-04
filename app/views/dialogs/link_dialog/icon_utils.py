"""
Утилиты для работы с иконками в диалоге ссылок.
"""
import logging
from pathlib import Path
from typing import Optional

from PyQt6.QtGui import QIcon

from app.utils.ui.icon.path_service import icon_path_service

logger = logging.getLogger(__name__)


def make_icon(icon_path_str: str) -> Optional[QIcon]:
    """Создаёт QIcon из пути (абсолютного или относительного к папкам иконок).
    
    Args:
        icon_path_str: Путь к иконке (абсолютный или относительный)
        
    Returns:
        QIcon объект или None, если иконка не найдена
        
    Поддерживает:
    - Абсолютные пути
    - Относительные пути относительно пользовательской папки иконок
    - Относительные пути относительно UI папки иконок
    """
    try:
        if not icon_path_str:
            return None
            
        p = Path(icon_path_str)
        
        # Абсолютный путь
        if p.exists():
            return QIcon(str(p))
            
        # Пользовательская папка иконок
        user_p = icon_path_service.get_user_icons_dir() / icon_path_str
        if user_p.exists():
            return QIcon(str(user_p))
            
        # UI папка иконок
        ui_p = icon_path_service.get_ui_icons_dir() / icon_path_str
        if ui_p.exists():
            return QIcon(str(ui_p))
            
    except (OSError, FileNotFoundError, PermissionError) as e:
        logger.warning(f"Ошибка доступа к файлу иконки '{icon_path_str}': {e}")
    except Exception as e:
        logger.exception(f"Неожиданная ошибка при создании иконки '{icon_path_str}': {e}")
        
    return None
