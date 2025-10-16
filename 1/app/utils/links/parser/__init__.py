"""Parser package facade.

Current facade-wrapper for fetching web link metadata.

Contents:
- `fetcher` — networking layer and high-level API `fetch_web_link_info()` to
  extract metadata (page title, icon, etc.).
- `title_parser` — helpers for extracting and normalising titles (`get_title`).
"""

from .fetcher import fetch_web_link_info  # re-export
from .title_parser import get_title  # convenient alias

__all__ = [
    "fetch_web_link_info",
    "get_title",
]
