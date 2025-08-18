"""Parser package facade.

Provides stable imports for link metadata fetching components.
Initially proxies to legacy implementations in `app.utils.links.web_favicon`.
"""
from .fetcher import fetch_web_link_info  # re-export
from .title_parser import get_title  # convenient alias

__all__ = [
    "fetch_web_link_info",
    "get_title",
]
