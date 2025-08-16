# app/utils/links/url_detect.py

from typing import Optional
from PyQt6.QtCore import QUrl


def normalize_to_url(s: str) -> Optional[str]:
    """Нормализует входную строку к URL-строке.
    Поддержка локальных путей Windows/Unix и схем http/https/ftp/mailto/file.
    Возвращает None, если нормализовать не удалось.
    """
    if not s:
        return None
    s = s.strip()
    if not s:
        return None

    # Попробуем распарсить как URL напрямую
    url = QUrl(s)
    if url.isValid() and url.scheme():
        # Если это локальный файл, убеждаемся в корректном формате file://
        if url.isLocalFile():
            return QUrl.fromLocalFile(url.toLocalFile()).toString()
        # Допускаем известные схемы
        if url.scheme().lower() in ("http", "https", "ftp", "mailto", "file"):
            return url.toString(QUrl.UrlFormattingOption.FullyEncoded)

    # Если схемы нет — считаем это локальным путем
    file_url = QUrl.fromLocalFile(s)
    if file_url.isValid():
        return file_url.toString()

    return None


essential_schemes = {
    "http": "web",
    "https": "web",
    "ftp": "ftp",
    "mailto": "email",
    "file": "file",
}


def detect_link_type(url_str: str) -> str:
    """Определяет тип ссылки по схеме URL."""
    try:
        url = QUrl(url_str)
        scheme = (url.scheme() or "").lower()
        return essential_schemes.get(scheme, "web" if scheme else "web")
    except Exception:
        return "web"


def suggest_name(url_str: str, fallback_max: int = 64) -> str:
    """Предлагает человекочитаемое имя для ссылки.
    Для file:// — имя файла. Для web — хост + последний сегмент пути; иначе — укороченная строка URL.
    """
    try:
        url = QUrl(url_str)
        scheme = (url.scheme() or "").lower()
        if scheme == "file":
            name = url.fileName() or url.toLocalFile().split("/")[-1]
            return name or "Файл"
        if scheme in ("http", "https"):
            host = url.host() or ""
            path = url.path().rstrip("/")
            last = path.split("/")[-1] if path else ""
            base = last or host or url_str
            return base[:fallback_max]
        if scheme == "mailto":
            return (url.path() or url_str)[:fallback_max]
        return url_str[:fallback_max]
    except Exception:
        return (url_str or "Ссылка")[:fallback_max]
