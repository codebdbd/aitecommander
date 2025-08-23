from __future__ import annotations

from typing import Optional

from app.models.db import Database


class UnitOfWork:
    """
    Тонкая обёртка над транзакциями БД для атомарных операций.
    Использует Database.transaction() и предоставляет быстрый доступ к репозиториям.
    """

    def __init__(self, db: Database):
        self.db = db
        self._tx_ctx = None  # type: Optional[object]
        # Короткие алиасы на репозитории (без дублирования кода)
        self.spheres = db.spheres
        self.sections = db.sections
        self.categories = db.categories
        self.links = db.links

    def __enter__(self) -> "UnitOfWork":
        # Прокси к Database.transaction()
        self._tx_ctx = self.db.transaction()
        self._tx_ctx.__enter__()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        # Прокси к Database.transaction().__exit__
        assert self._tx_ctx is not None
        self._tx_ctx.__exit__(exc_type, exc, tb)
        self._tx_ctx = None
