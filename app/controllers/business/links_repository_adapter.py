import logging
from typing import Any, Dict, List, Optional

from app.models.db import Database
from app.services.uow import UnitOfWork


class LinksRepositoryAdapter:
    """Адаптер доступа к данным ссылок.

    Инкапсулирует обращения к LinksService и, при необходимости, к Database.links,
    скрывая детали от бизнес-логики.
    """

    def __init__(self, db: Database, logger=None) -> None:
        self.db = db
        self.logger = logger or logging.getLogger(self.__class__.__name__)

    # Чтение/поиск
    def fetch_links(self, category_id: int) -> List[Dict]:
        return self.db.links.get_links(category_id) or []

    def search_links(self, query: str) -> List[Dict]:
        return self.db.links.search_links(query) or []

    def count_favorites(self) -> int:
        return int(self.db.links.count_favorites())

    def get_links_for_category(self, category_id: int) -> List[Dict]:
        return self.db.links.get_links_for_category(category_id) or []

    # Мутации/операции
    def reorder(self, link_ids: List[int]) -> None:
        # ВАЖНО: repo.update_link_order сам управляет транзакцией
        self.db.links.update_link_order(link_ids)

    def create_or_update_link(self, link_data: Dict[str, Any]) -> Optional[int]:
        with UnitOfWork(self.db):
            return self.db.links.upsert_link(link_data)

    def delete_link(self, link_id: int) -> None:
        with UnitOfWork(self.db):
            self.db.links.delete_link(link_id)

    def update_last_used(self, link_id: int) -> None:
        with UnitOfWork(self.db):
            self.db.links.update_link_last_used(link_id)

    def get_recent_links(self, limit: int = 10) -> List[Dict]:
        return self.db.links.get_recent_links(limit) or []

    def get_favorite_links(self) -> List[Dict]:
        return self.db.links.get_favorite_links() or []

    def clear_favorites(self) -> int:
        with UnitOfWork(self.db):
            try:
                affected = int(self.db.links.clear_favorites() or 0)
            except Exception:
                # clear_favorites в модели может не возвращать счётчик в старых версиях
                # Считаем как 0 в таком случае — вызывающая сторона обработает/заллогирует
                affected = 0
        self.logger.debug("clear_favorites affected=%s", affected)
        return affected

    def get_link_by_id(self, link_id: int) -> Optional[Dict]:
        return self.db.links.get_link_by_id(link_id)

    def get_next_position(self, category_id: int) -> int:
        return int(self.db.links.get_next_position(category_id) or 0)

    def batch_update(self, links_data: List[Dict]) -> bool:
        # ВАЖНО: repo.batch_update_links сам управляет транзакцией
        return bool(self.db.links.batch_update_links(links_data))

    def batch_create_or_update_links(self, links_data: List[Dict]) -> List[int]:
        """Пакетный upsert ссылок. Возвращает список созданных ID.

        ВАЖНО: repo.batch_upsert_links сам управляет транзакцией.
        """
        return self.db.links.batch_upsert_links(links_data) or []

    def batch_delete_links(self, link_ids: List[int]) -> int:
        """Пакетное удаление ссылок. Возвращает число удалённых записей.

        ВАЖНО: repo.batch_delete_links сам управляет транзакцией.
        """
        return int(self.db.links.batch_delete_links(link_ids) or 0)
