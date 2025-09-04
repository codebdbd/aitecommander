import sqlite3
import pytest

from app.models.db_base import DatabaseBase, DatabaseError


class FailingExecModel(DatabaseBase):
    """Тестовая модель, которая имитирует сбой запроса в _execute_with_error_handling."""

    def __init__(self):
        # Передаём фиктивный connection_manager, он не нужен, так как мы
        # переопределяем _execute_with_error_handling и не обращаемся к connection
        class _DummyMgr:
            connection = None
        super().__init__(_DummyMgr())

    def _execute_with_error_handling(self, query: str, params: tuple = (), fetch_method: str = None):  # type: ignore[override]
        # Эмулируем ошибку драйвера SQLite
        raise sqlite3.Error("simulated failure")


def test_get_next_position_raises_database_error_on_query_failure():
    model = FailingExecModel()
    with pytest.raises(DatabaseError):
        model._get_next_position("link")
