from __future__ import annotations

import functools
from typing import Optional

from app.models.db import Database


class UnitOfWork:
    """
    Thin wrapper over DB transactions for atomic operations.
    Uses Database.transaction() and provides quick access to repositories.
    """

    def __init__(self, db: Database):
        self.db = db
        self._tx_ctx = None  # type: Optional[object]
        # Short aliases to repositories (without code duplication); safe for test DBs
        self.spheres = getattr(db, "spheres", None)
        self.sections = getattr(db, "sections", None)
        self.categories = getattr(db, "categories", None)
        self.links = getattr(db, "links", None)

    def __enter__(self) -> UnitOfWork:
        # Proxy to Database.transaction()
        self._tx_ctx = self.db.transaction()
        self._tx_ctx.__enter__()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        # Proxy to Database.transaction().__exit__
        assert self._tx_ctx is not None
        self._tx_ctx.__exit__(exc_type, exc, tb)
        self._tx_ctx = None


def unit_of_work(func):
    """Decorator for wrapping service method in UnitOfWork(self.db) transaction.

    Used only where there is no internal transaction management in repository/model,
    to avoid nested transactions (especially in SQLite).
    """

    @functools.wraps(func)
    def _wrapped(self, *args, **kwargs):
        with UnitOfWork(self.db):
            return func(self, *args, **kwargs)

    return _wrapped
