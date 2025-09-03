"""Parser package facade.

Актуальная фасад-обёртка для получения метаданных веб‑ссылок.

Содержимое:
- `fetcher` — сетевой слой и высокоуровневый API `fetch_web_link_info()` для
  извлечения метаданных (заголовок страницы, иконка, др.).
- `title_parser` — утилиты извлечения и нормализации заголовка (`get_title`).
"""

from .fetcher import fetch_web_link_info  # re-export
from .title_parser import get_title  # convenient alias

__all__ = [
    "fetch_web_link_info",
    "get_title",
]
