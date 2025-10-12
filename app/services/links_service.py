from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from app.models.db import Database

from .uow import unit_of_work


class LinksService:
    """
    Link service.
    Stage 1: thin wrapper over LinkModel via Database, without SQL duplication.
    Stage 2+: encapsulation of business rules (favorite limits, duplicate checking, etc.).
    """

    def __init__(self, db: Database):
        self.db = db
        self.repo = db.links  # short alias
        self._chunk_size = 900

    # --- Reading ---
    def get_links(self, category_id: int) -> List[Dict[str, Any]]:
        return self.repo.get_links(category_id)

    def get_links_for_categories(
        self, category_ids: List[int]
    ) -> Dict[int, List[Dict[str, Any]]]:
        return self.repo.get_links_for_categories(category_ids)

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

    def search_links(self, query: str) -> List[Dict[str, Any]]:
        """Alias for search method to maintain backward compatibility."""
        return self.search(query)

    def count_links_by_category(self, category_id: int) -> int:
        return self.repo.count_links_by_category(category_id)

    def get_next_position(self, category_id: int) -> int:
        """Get next position for new link in category."""
        return self.repo.get_next_position(category_id)

    # --- Checks/utilities ---
    def find_duplicate(
        self, category_id: int, name: str, url: str, args: str = ""
    ) -> Optional[Dict[str, Any]]:
        return self.repo.get_link_by_name_url_args(category_id, name, url, args)

    def find_by_unique_fields(
        self,
        category_id: int,
        url: str,
        args: str = "",
        link_type: str = "web",
        name: str = "",
    ) -> Optional[Dict[str, Any]]:
        """Search link by unique fields (compatible with repository).

        Used as fallback path if search by (name,url,args) yielded no results.
        """
        return self.repo.get_link_by_unique_fields(
            category_id, url, args, link_type, name
        )

    # --- Mutations ---
    @unit_of_work
    def create_or_update_link(self, link_data: Dict[str, Any]) -> int:
        """Creates or updates link. Returns id.
        Business rules (e.g., silent duplicate ignoring) are already implemented in repository.
        """
        return self.repo.upsert_link(link_data)

    @unit_of_work
    def delete_link(self, link_id: int) -> None:
        self.repo.delete_link(link_id)

    @unit_of_work
    def update_last_used(self, link_id: int) -> None:
        self.repo.update_link_last_used(link_id)

    @unit_of_work
    def clear_favorites(self) -> None:
        self.repo.clear_favorites()

    def reorder(self, link_ids: List[int]) -> bool:
        # IMPORTANT: update_link_order in repository manages transaction itself via self.transaction()
        # Wrapping in UnitOfWork will lead to nested transaction (SQLite: cannot start a transaction within a transaction)
        return self.repo.update_link_order(link_ids)

    def batch_update(self, links_data: List[Dict[str, Any]]) -> bool:
        # IMPORTANT: batch_update_links inside repository already manages transaction
        # via self.transaction(). Cannot wrap in UnitOfWork — this will lead
        # to nested transaction (SQLite: "cannot start a transaction within a transaction").
        if not links_data:
            return False
        success = True
        for chunk in self._iter_chunks(links_data):
            if not chunk:
                continue
            result = self.repo.batch_update_links(chunk)
            success = success and bool(result)
        return success

    def batch_create_or_update_links(
        self, links_data: List[Dict[str, Any]]
    ) -> List[int]:
        """Batch creation/update of links with return of created IDs.

        Wraps repo.batch_upsert_links in UnitOfWork for operation atomicity.
        Updates input elements links_data with set IDs for new links.
        """
        # IMPORTANT: batch_upsert_links manages transaction itself via self.transaction()
        # Wrapping in UnitOfWork will lead to nested transaction in SQLite.
        if not links_data:
            return []
        created_ids: List[int] = []
        for chunk in self._iter_chunks(links_data):
            if not chunk:
                continue
            created_ids.extend(self.repo.batch_upsert_links(chunk))
        return created_ids

    def count_favorites(self) -> int:
        """Returns number of favorite links."""
        return self.repo.count_favorites()

    def batch_delete_links(self, link_ids: List[int]) -> int:
        """Delete multiple links by IDs in a single transaction."""
        if not link_ids:
            return 0
        valid_ids = [
            int(x)
            for x in link_ids
            if isinstance(x, int) and not isinstance(x, bool) and x > 0
        ]
        if not valid_ids:
            return 0
        unique_ids = list(dict.fromkeys(valid_ids))
        deleted = 0
        for chunk in self._iter_id_chunks(unique_ids):
            if not chunk:
                continue
            deleted += self.repo.batch_delete_links(chunk)
        return deleted

    def _iter_chunks(
        self, items: Iterable[Dict[str, Any]]
    ) -> Iterable[List[Dict[str, Any]]]:
        buffer: List[Dict[str, Any]] = []
        for item in items or []:
            buffer.append(item)
            if len(buffer) >= self._chunk_size:
                yield buffer
                buffer = []
        if buffer:
            yield buffer

    def _iter_id_chunks(self, ids: Iterable[int]) -> Iterable[List[int]]:
        buffer: List[int] = []
        for item in ids or []:
            buffer.append(int(item))
            if len(buffer) >= self._chunk_size:
                yield buffer
                buffer = []
        if buffer:
            yield buffer
