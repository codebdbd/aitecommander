import json
import logging
from typing import Any, Dict, List, Optional, Union

from PyQt6.QtWidgets import QApplication

LinkData = Union[Dict[str, Any], List[Dict[str, Any]]]


def copy_link_to_clipboard(link_or_links: LinkData) -> None:
    """Копирует ссылку или список ссылок в системный буфер обмена.

    Безопасно обрабатывает отсутствие QApplication и ошибки сериализации.
    """
    app = QApplication.instance()
    if app is None:
        logging.error(
            "QApplication is not initialized; clipboard operations are unavailable"
        )
        return

    clipboard = app.clipboard()
    try:
        clipboard.setText(json.dumps(link_or_links, ensure_ascii=False))
    except Exception as e:
        logging.error(f"Failed to copy link(s) to clipboard: {e}", exc_info=True)
        try:
            clipboard.clear()
        except Exception:
            # Игнорируем вторичную ошибку очистки
            pass


def get_link_from_clipboard() -> Optional[LinkData]:
    """Читает ссылку/список ссылок из системного буфера обмена.

    Возвращает:
      - dict или list[dict] при успешном чтении
      - None при ошибке, пустом буфере, отсутствии QApplication или неверном формате
    """
    app = QApplication.instance()
    if app is None:
        logging.error(
            "QApplication is not initialized; clipboard operations are unavailable"
        )
        return None

    clipboard = app.clipboard()
    try:
        text = clipboard.text()
        if not text:
            return None

        data = json.loads(text)
        if isinstance(data, dict):
            # Базовая валидация структуры словаря (минимальная)
            return data
        if isinstance(data, list):
            return data
        # Неподдерживаемый формат
        return None
    except json.JSONDecodeError:
        return None
    except Exception as e:
        logging.error(f"Failed to read link from clipboard: {e}", exc_info=True)
        return None
