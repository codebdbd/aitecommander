from __future__ import annotations

from app.models.db import Database
import functools
from typing import Any, Callable, Optional, TypeVar, ParamSpec, Protocol, ContextManager, Concatenate


class UnitOfWork:
    """
    Тонкая обёртка над транзакциями БД для атомарных операций.
    Использует Database.transaction() и предоставляет быстрый доступ к репозиториям.
    """

    def __init__(self, db: Database):
        self.db = db
        self._tx_ctx: Optional[ContextManager[Any]] = None
        # Короткие алиасы на репозитории (без дублирования кода); безопасны для тестовых DB
        self.spheres = getattr(db, "spheres", None)
        self.sections = getattr(db, "sections", None)
        self.categories = getattr(db, "categories", None)
        self.links = getattr(db, "links", None)

    def __enter__(self) -> "UnitOfWork":
        # Прокси к Database.transaction()
        self._tx_ctx = self.db.transaction()
        self._tx_ctx.__enter__()
        return self

    def __exit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: Any) -> None:
        # Прокси к Database.transaction().__exit__
        assert self._tx_ctx is not None
        self._tx_ctx.__exit__(exc_type, exc, tb)
        self._tx_ctx = None


P = ParamSpec("P")
T = TypeVar("T")


class HasDB(Protocol):
    db: Database


S = TypeVar("S", bound=HasDB)


def unit_of_work(func: Callable[Concatenate[S, P], T]) -> Callable[Concatenate[S, P], T]:
    """Декоратор для оборачивания метода сервиса в транзакцию UnitOfWork(self.db).

    Используется только там, где нет внутреннего управления транзакциями в репозитории/модели,
    чтобы избежать вложенных транзакций (особенно в SQLite).
    """

    @functools.wraps(func)
    def _wrapped(self: S, *args: P.args, **kwargs: P.kwargs) -> T:
        with UnitOfWork(self.db):
            return func(self, *args, **kwargs)

    return _wrapped
