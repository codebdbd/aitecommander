import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from PyQt6.QtGui import QIcon, QClipboard
from typing import cast
from PyQt6.QtWidgets import QApplication

LinkData = Union[Dict[str, Any], List[Dict[str, Any]]]

logger = logging.getLogger(__name__)


def _to_jsonable(value: Any) -> Any:
    """Преобразует значение к JSON-совместимому виду или возвращает None для пропуска.

    - Удаляет объекты UI (например, QIcon)
    - Конвертирует Path в str
    - Рекурсивно обрабатывает dict/list/tuple
    - Пропускает (возвращает None) неподдерживаемые типы
    """
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, QIcon):
        return None  # не сериализуем в буфер, иконка восстанавливается по icon_path
    if isinstance(value, dict):
        out: Dict[str, Any] = {}
        for k, v in value.items():
            # пропускаем служебные ключи вида _icon, _cache и т.п.
            if isinstance(k, str) and k.startswith("_"):
                continue
            jv = _to_jsonable(v)
            if jv is not None:
                out[k] = jv
        return out
    if isinstance(value, (list, tuple)):
        arr = []
        for item in value:
            jv = _to_jsonable(item)
            if jv is not None:
                arr.append(jv)
        return arr
    # Любые иные типы не сериализуем — пропускаем
    return None


def _sanitize_for_clipboard(data: LinkData) -> LinkData:
    if isinstance(data, list):
        return _to_jsonable(data) or []
    return _to_jsonable(data) or {}


def copy_link_to_clipboard(link_or_links: LinkData) -> bool:
    """Копирует ссылку или список ссылок в системный буфер обмена.

    Возвращает True при успехе, False при ошибке. Перед копированием удаляет несерилизуемые
    поля (QIcon, приватные ключи с подчеркиванием и т.п.).
    """
    app = cast(QApplication | None, QApplication.instance())
    if app is None:
        logger.error(
            "QApplication is not initialized; clipboard operations are unavailable"
        )
        return False

    clipboard = cast(QClipboard, app.clipboard())
    try:
        sanitized = _sanitize_for_clipboard(link_or_links)
        clipboard.setText(json.dumps(sanitized, ensure_ascii=False))
        return True
    except Exception as e:
        logger.error("Failed to copy link(s) to clipboard: %s", e, exc_info=True)
        try:
            clipboard.clear()
        except Exception:
            # Игнорируем вторичную ошибку очистки
            pass
        return False


def get_link_from_clipboard() -> Optional[LinkData]:
    """Читает ссылку/список ссылок из системного буфера обмена.

    Возвращает:
      - dict или list[dict] при успешном чтении
      - None при ошибке, пустом буфере, отсутствии QApplication или неверном формате
    """
    app = cast(QApplication | None, QApplication.instance())
    if app is None:
        logger.error(
            "QApplication is not initialized; clipboard operations are unavailable"
        )
        return None

    clipboard = cast(QClipboard, app.clipboard())
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
        logger.error("Failed to read link from clipboard: %s", e, exc_info=True)
        return None
