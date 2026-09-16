"""Parser package facade.

Current facade-wrapper for fetching web link metadata.

Contents:
- `fetcher` — networking layer and high-level API `fetch_web_link_info()` to
  extract metadata (page title, icon, etc.).
- `title_parser` — helpers for extracting and normalising titles (`get_title`).
"""

from .fetcher import fetch_web_link_info  # re-export
from .title_parser import get_title  # convenient alias


def shutdown_parser_background_tasks(wait: bool = False, cancel_futures: bool = True) -> None:
    """Stop shared parser executors/network helpers to allow fast shutdown.

    ЕДИНСТВЕННЫЙ централизованный путь shutdown для parser-модулей.
    Ранее эти действия дублировались через `atexit.register(...)` в каждом модуле отдельно,
    но в GUI-режиме эти хендлеры были мёртвым кодом: runtime выходил через sys.exit/ExitProcess
    до запуска стандартного интерпретаторного atexit run-loop.
    """
    try:
        from .icon_downloader import _shutdown_icon_executor
        _shutdown_icon_executor(wait=wait)
    except Exception:
        pass
    try:
        from .icon_candidates import shutdown_manifest_executor
        shutdown_manifest_executor(wait=wait, cancel_futures=cancel_futures)
    except Exception:
        pass
    try:
        from .http_client import shutdown_cloudscraper
        shutdown_cloudscraper(wait=wait)
    except Exception:
        pass
    try:
        from .favicon_cache import FaviconCache
        FaviconCache.shutdown_all_instances()
    except Exception:
        pass
    try:
        from .http_client import _cleanup_thread_local_session
        _cleanup_thread_local_session()
    except Exception:
        pass

__all__ = [
    "fetch_web_link_info",
    "get_title",
    "shutdown_parser_background_tasks",
]
