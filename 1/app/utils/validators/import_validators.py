from __future__ import annotations

from pathlib import Path
from typing import Optional


def is_valid_bookmarks_html(path: str, max_size_mb: int = 50) -> bool:
    """Быстрая проверка файла HTML с закладками по пути.
    - файл существует и является файлом
    - расширение .html/.htm
    - разумный размер (по умолчанию < 50 МБ)
    - минимальная проверка содержимого: начало файла содержит HTML doctype/тег
    """
    try:
        p = Path(path)
        if not p.exists() or not p.is_file():
            return False
        if p.suffix.lower() not in {".html", ".htm"}:
            return False
        if p.stat().st_size > max_size_mb * 1024 * 1024:
            return False
        # минимальная проверка содержимого
        with p.open("r", encoding="utf-8", errors="ignore") as f:
            head = f.read(2048).lower()
            if ("<!doctype html" not in head) and ("<html" not in head):
                return False
        return True
    except OSError:
        return False


def can_parse_bookmarks_html(content: str) -> bool:
    """Лёгкая эвристика для ранней оценки пригодности содержимого к парсингу.
    Не заменяет полноценный парсер.
    Проверяем наличие базовых HTML-структур и типичных для bookmarks узлов.
    """
    if not content or not isinstance(content, str):
        return False
    low = content[:4096].lower()
    # базовые HTML
    if ("<html" not in low) and ("<!doctype" not in low):
        return False
    # типичные элементы экспортов закладок (браузер-зависимо, эвристика)
    keywords = ("<dl", "<dt", "<h3", "bookmark")
    return any(k in low for k in keywords)
