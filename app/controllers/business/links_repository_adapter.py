import logging
from typing import Any, Dict, List, Optional

from app.models.db import Database
from app.services import LinksService


class LinksRepositoryAdapter:
    """Адаптер доступа к данным ссылок.

    Инкапсулирует обращения к LinksService и, при необходимости, к Database.links,
    скрывая детали от бизнес-логики.
    """

    def __init__(self, db: Database, service: Optional[LinksService] = None, logger=None) -> None:
        self.db = db
        self.service = service or LinksService(db)
        self.logger = logger or logging.getLogger(self.__class__.__name__)

    # Чтение/поиск
    def fetch_links(self, category_id: int) -> List[Dict]:
        return self.db.links.get_links(category_id) or []

    def search_links(self, query: str) -> List[Dict]:
        return self.db.links.search_links(query) or []

    def count_favorites(self) -> int:
        return int(self.db.links.count_favorites())

    def get_links_for_category(self, category_id: int) -> List[Dict]:
        return self.service.get_links_for_category(category_id) or []

    def get_all_links(self) -> List[Dict]:
        try:
            return self.service.get_all_links() or []
        except Exception:
            # совместимость с текущей бизнес-логикой
            return []

    # Мутации/операции
    def reorder(self, link_ids: List[int]) -> None:
        self.service.reorder(link_ids)

    def create_or_update_link(self, link_data: Dict[str, Any]) -> Optional[int]:
        return self.service.create_or_update_link(link_data)

    def delete_link(self, link_id: int) -> None:
        self.service.delete_link(link_id)

    def update_last_used(self, link_id: int) -> None:
        self.service.update_last_used(link_id)

    def get_recent_links(self, limit: int = 10) -> List[Dict]:
        return self.service.get_recent_links(limit) or []

    def get_favorite_links(self) -> List[Dict]:
        return self.service.get_favorite_links() or []

    def clear_favorites(self) -> bool:
        return bool(self.service.clear_favorites() or True)

    def get_link_by_id(self, link_id: int) -> Optional[Dict]:
        return self.service.get_link_by_id(link_id)

    def get_next_position(self, category_id: int) -> int:
        return int(self.service.get_next_position(category_id) or 0)

    def batch_update(self, links_data: List[Dict]) -> bool:
        return bool(self.service.batch_update(links_data))
