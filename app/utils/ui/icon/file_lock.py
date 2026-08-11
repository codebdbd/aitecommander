from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager

_ICON_FILES_LOCK = threading.RLock()


@contextmanager
def icon_files_lock() -> Iterator[None]:
    """Serialize icon archive operations and on-disk icon rewrites."""
    with _ICON_FILES_LOCK:
        yield
