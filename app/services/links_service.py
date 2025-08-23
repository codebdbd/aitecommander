from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.models.db import Database
from .uow import UnitOfWork


class LinksService:
    """
    Сервис работы со ссылками.
    Этап 1: тонкая обёртка над LinkModel через Database, без дублирования SQL.
    Этап 2+: инкапсуляция бизнес‑правил (лимиты избранного, проверка дубликатов и пр.).
    """

    def __init__(self, db: Database):
        self.db = db
        self.repo = db.links  # короткий алиас

    # --- Чтение ---
    def get_links(self, category_id: int) -> List[Dict[str, Any]]:
        return self.repo.get_links(category_id)

    def get_links_for_category(self, category_id: int) -> List[Dict[str, Any]]:
        return self.repo.get_links_for_category(category_id)

    def get_all_links(self) -> List[Dict[str, Any]]:
        return self.repo.get_all_links()

    def get_link_by_id(self, link_id: int) -> Optional[Dict[str, Any]]:
        return self.repo.get_link_by_id(link_id)

    def get_recent_links(self, limit: int = 10) -> List[Dict[str, Any]]:
        return self.repo.get_recent_links(limit)

    def get_favorite_links(self) -> List[Dict[str, Any]]:
        return self.repo.get_favorite_links()

    def search(self, query: str) -> List[Dict[str, Any]]:
        return self.repo.search_links(query)

    def count_links_by_category(self, category_id: int) -> int:
        return self.repo.count_links_by_category(category_id)

    def get_next_position(self, category_id: int) -> int:
        """Получить следующую позицию для новой ссылки в категории."""
        return self.repo.get_next_position(category_id)

    # --- Проверки/утилиты ---
    def find_duplicate(self, category_id: int, name: str, url: str, args: str = "") -> Optional[Dict[str, Any]]:
        return self.repo.get_link_by_name_url_args(category_id, name, url, args)

    # --- Мутации ---
    def create_or_update_link(self, link_data: Dict[str, Any]) -> int:
        """Создаёт или обновляет ссылку. Возвращает id.
        Бизнес‑правила (например, тихое игнорирование дубликатов) уже реализованы в репозитории.
        """
        with UnitOfWork(self.db):
            return self.repo.upsert_link(link_data)

    def delete_link(self, link_id: int) -> None:
        with UnitOfWork(self.db):
            self.repo.delete_link(link_id)

    def update_last_used(self, link_id: int) -> None:
        with UnitOfWork(self.db):
            self.repo.update_link_last_used(link_id)

    def clear_favorites(self) -> None:
        with UnitOfWork(self.db):
            self.repo.clear_favorites()

    def reorder(self, link_ids: List[int]) -> bool:
        with UnitOfWork(self.db):
            return self.repo.update_link_order(link_ids)

    def batch_update(self, links_data: List[Dict[str, Any]]) -> bool:
        # ВАЖНО: batch_update_links внутри репозитория уже управляет транзакцией
        # через self.transaction(). Оборачивать в UnitOfWork нельзя — это приведёт
        # к вложенной транзакции (SQLite: "cannot start a transaction within a transaction").
        return self.repo.batch_update_links(links_data)
