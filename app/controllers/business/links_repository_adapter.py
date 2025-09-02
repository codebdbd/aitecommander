import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from app.models.db import Database
from app.services.uow import UnitOfWork


class LinksRepositoryAdapter:
    """Адаптер доступа к данным ссылок.

    Единая точка доступа к Database.links с единообразной политикой транзакций (UnitOfWork
    там, где это требуется) и нормализацией результатов для бизнес-слоя.
    """

    def __init__(self, db: Database, logger=None) -> None:
        self.db = db
        self.logger = logger or logging.getLogger(self.__class__.__name__)
        # Простой TTL-кэш: key -> (expires_at, value)
        self._cache: Dict[str, Tuple[float, Any]] = {}
        self._ttl_seconds: int = 3

    # --- Кэш-помощники ---
    def _cache_key(self, name: str, *parts: Any) -> str:
        return f"{name}:{parts!r}"

    def _cache_get(self, key: str) -> Optional[Any]:
        item = self._cache.get(key)
        if not item:
            return None
        expires_at, value = item
        if expires_at < time.monotonic():
            # Просрочено — удаляем
            self._cache.pop(key, None)
            return None
        self.logger.debug("cache hit: %s", key)
        return value

    def _cache_set(self, key: str, value: Any) -> Any:
        self._cache[key] = (time.monotonic() + float(self._ttl_seconds), value)
        self.logger.debug("cache set: %s", key)
        return value

    def _cache_invalidate_all(self) -> None:
        if self._cache:
            self.logger.debug("cache invalidate: %d entries", len(self._cache))
        self._cache.clear()

    # Чтение/поиск
    def fetch_links(self, category_id: int) -> List[Dict]:
        if not isinstance(category_id, int) or category_id <= 0:
            self.logger.warning("fetch_links: invalid category_id=%r", category_id)
            return []
        try:
            key = self._cache_key("fetch_links", category_id)
            cached = self._cache_get(key)
            if cached is not None:
                return cached
            res = self.db.links.get_links(category_id) or []
            return self._cache_set(key, res)
        except Exception as e:
            self.logger.error("fetch_links failed: %s", e)
            raise

    def search_links(self, query: str) -> List[Dict]:
        q = (query or "").strip()
        if not q:
            # Пустой запрос — предсказуемый пустой результат
            return []
        try:
            key = self._cache_key("search_links", q)
            cached = self._cache_get(key)
            if cached is not None:
                return cached
            res = self.db.links.search_links(q) or []
            return self._cache_set(key, res)
        except Exception as e:
            self.logger.error("search_links failed: %s", e)
            raise

    def count_favorites(self) -> int:
        try:
            key = self._cache_key("count_favorites")
            cached = self._cache_get(key)
            if cached is not None:
                return int(cached)
            res = int(self.db.links.count_favorites() or 0)
            return int(self._cache_set(key, res))
        except Exception as e:
            self.logger.error("count_favorites failed: %s", e)
            raise

    def get_links_for_category(self, category_id: int) -> List[Dict]:
        if not isinstance(category_id, int) or category_id <= 0:
            self.logger.warning(
                "get_links_for_category: invalid category_id=%r", category_id
            )
            return []
        try:
            key = self._cache_key("get_links_for_category", category_id)
            cached = self._cache_get(key)
            if cached is not None:
                return cached
            res = self.db.links.get_links_for_category(category_id) or []
            return self._cache_set(key, res)
        except Exception as e:
            self.logger.error("get_links_for_category failed: %s", e)
            raise

    # Мутации/операции
    def reorder(self, link_ids: List[int]) -> None:
        # ВАЖНО: repo.update_link_order сам управляет транзакцией
        ids = [i for i in (link_ids or []) if isinstance(i, int) and i > 0]
        if not ids:
            self.logger.debug("reorder: empty/invalid ids, no-op")
            return
        try:
            self.db.links.update_link_order(ids)
            self._cache_invalidate_all()
        except Exception as e:
            self.logger.error("reorder failed: %s", e)
            raise

    def create_or_update_link(self, link_data: Dict[str, Any]) -> Optional[int]:
        if not isinstance(link_data, dict) or not link_data:
            self.logger.warning("create_or_update_link: empty or invalid payload")
            return None
        with UnitOfWork(self.db):
            try:
                res = self.db.links.upsert_link(link_data)
                self._cache_invalidate_all()
                return res
            except Exception as e:
                self.logger.error("create_or_update_link failed: %s", e)
                raise

    def delete_link(self, link_id: int) -> None:
        if not isinstance(link_id, int) or link_id <= 0:
            self.logger.warning("delete_link: invalid id=%r", link_id)
            return
        with UnitOfWork(self.db):
            try:
                self.db.links.delete_link(link_id)
                self._cache_invalidate_all()
            except Exception as e:
                self.logger.error("delete_link failed: %s", e)
                raise

    def update_last_used(self, link_id: int) -> None:
        if not isinstance(link_id, int) or link_id <= 0:
            self.logger.warning("update_last_used: invalid id=%r", link_id)
            return
        with UnitOfWork(self.db):
            try:
                self.db.links.update_link_last_used(link_id)
                self._cache_invalidate_all()
            except Exception as e:
                self.logger.error("update_last_used failed: %s", e)
                raise

    def get_recent_links(self, limit: int = 10) -> List[Dict]:
        lim = int(limit or 0)
        if lim <= 0:
            self.logger.warning("get_recent_links: invalid limit=%r", limit)
            return []
        try:
            key = self._cache_key("get_recent_links", lim)
            cached = self._cache_get(key)
            if cached is not None:
                return cached
            res = self.db.links.get_recent_links(lim) or []
            return self._cache_set(key, res)
        except Exception as e:
            self.logger.error("get_recent_links failed: %s", e)
            raise

    def get_favorite_links(self) -> List[Dict]:
        try:
            key = self._cache_key("get_favorite_links")
            cached = self._cache_get(key)
            if cached is not None:
                return cached
            res = self.db.links.get_favorite_links() or []
            return self._cache_set(key, res)
        except Exception as e:
            self.logger.error("get_favorite_links failed: %s", e)
            raise

    def clear_favorites(self) -> int:
        with UnitOfWork(self.db):
            try:
                affected = int(self.db.links.clear_favorites() or 0)
            except Exception:
                # clear_favorites в модели может не возвращать счётчик в старых версиях
                # Считаем как 0 в таком случае — вызывающая сторона обработает/заллогирует
                affected = 0
        self._cache_invalidate_all()
        self.logger.debug("clear_favorites affected=%s", affected)
        return affected

    def get_link_by_id(self, link_id: int) -> Optional[Dict]:
        if not isinstance(link_id, int) or link_id <= 0:
            self.logger.warning("get_link_by_id: invalid id=%r", link_id)
            return None
        try:
            key = self._cache_key("get_link_by_id", link_id)
            cached = self._cache_get(key)
            if cached is not None:
                return cached
            res = self.db.links.get_link_by_id(link_id)
            return self._cache_set(key, res)
        except Exception as e:
            self.logger.error("get_link_by_id failed: %s", e)
            raise

    def get_next_position(self, category_id: int) -> int:
        if not isinstance(category_id, int) or category_id <= 0:
            self.logger.warning(
                "get_next_position: invalid category_id=%r", category_id
            )
            return 0
        try:
            key = self._cache_key("get_next_position", category_id)
            cached = self._cache_get(key)
            if cached is not None:
                return int(cached)
            res = int(self.db.links.get_next_position(category_id) or 0)
            return int(self._cache_set(key, res))
        except Exception as e:
            self.logger.error("get_next_position failed: %s", e)
            raise

    def batch_update(self, links_data: List[Dict]) -> bool:
        # ВАЖНО: repo.batch_update_links сам управляет транзакцией
        items = [x for x in (links_data or []) if isinstance(x, dict) and x]
        if not items:
            self.logger.debug("batch_update: empty payload, no-op")
            return False
        try:
            res = bool(self.db.links.batch_update_links(items))
            if res:
                self._cache_invalidate_all()
            return res
        except Exception as e:
            self.logger.error("batch_update failed: %s", e)
            raise

    def batch_create_or_update_links(self, links_data: List[Dict]) -> List[int]:
        """Пакетный upsert ссылок. Возвращает список созданных ID.

        ВАЖНО: repo.batch_upsert_links сам управляет транзакцией.
        """
        items = [x for x in (links_data or []) if isinstance(x, dict) and x]
        if not items:
            self.logger.debug("batch_create_or_update_links: empty payload, no-op")
            return []
        try:
            res = self.db.links.batch_upsert_links(items) or []
            if res is not None:
                self._cache_invalidate_all()
            return res
        except Exception as e:
            self.logger.error("batch_create_or_update_links failed: %s", e)
            raise

    def batch_delete_links(self, link_ids: List[int]) -> int:
        """Пакетное удаление ссылок. Возвращает число удалённых записей.

        ВАЖНО: repo.batch_delete_links сам управляет транзакцией.
        """
        ids = [i for i in (link_ids or []) if isinstance(i, int) and i > 0]
        if not ids:
            self.logger.debug("batch_delete_links: empty/invalid ids, no-op")
            return 0
        try:
            res = int(self.db.links.batch_delete_links(ids) or 0)
            if res:
                self._cache_invalidate_all()
            return res
        except Exception as e:
            self.logger.error("batch_delete_links failed: %s", e)
            raise
