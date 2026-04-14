"""Link bulk upsert service.

Separates complex bulk upsert logic from LinkModel into dedicated service class.
Reduces cognitive complexity and improves testability.
"""

from __future__ import annotations

import logging
import sqlite3
from typing import Any

from ...utils.db.sql_helpers import build_in_clause_placeholders
from ..base.db_base import DatabaseError

logger = logging.getLogger(__name__)


class LinkBulkUpsertService:
    """Service for bulk upserting links with proper position assignment."""
    
    def __init__(self, connection: sqlite3.Connection):
        """Initialize service with database connection.
        
        Args:
            connection: SQLite connection (must be within transaction context)
        """
        self.connection = connection
    
    def upsert_links_for_category(
        self, 
        category_id: int, 
        items: list[dict[str, Any]],
        all_fields: list[str]
    ) -> list[int]:
        """Upsert links for single category.
        
        Args:
            category_id: Category ID
            items: List of normalized link dictionaries
            all_fields: List of all link field names
            
        Returns:
            List of created link IDs
        """
        # 1. Load existing links for this category
        existing_by_key, existing_by_id, max_pos = self._fetch_existing_maps(category_id)
        
        # 2. Assign positions to items without position
        self._assign_positions_for_items(items, max_pos + 1)
        
        # 3. Build UPDATE and INSERT parameters
        updates, inserts_no_id = self._build_update_params(items, existing_by_key)
        
        # 4. Execute UPDATEs and collect missing records
        inserts_with_id = self._execute_updates_collect_missing(updates)
        
        # 5. Execute INSERTs (both with and without ID)
        created_ids = self._execute_inserts(
            inserts_no_id, inserts_with_id, all_fields
        )
        
        return created_ids
    
    def _fetch_existing_maps(
        self, category_id: int
    ) -> tuple[
        dict[tuple[str, str, str], dict[str, Any]],
        dict[int, dict[str, Any]],
        int,
    ]:
        """Gets existing links and max(position) for category.

        Returns tuple (existing_by_key, existing_by_id, max_pos).
        key = (name, url, args)
        """
        cursor = self.connection.execute(
            "SELECT id, name, url, args, position FROM link WHERE category_id=?",
            (category_id,),
        )
        rows = cursor.fetchall()
        
        existing_by_key: dict[tuple[str, str, str], dict[str, Any]] = {}
        existing_by_id: dict[int, dict[str, Any]] = {}
        max_pos = -1
        
        for row in rows:
            rid = row["id"]
            rname = row["name"]
            rurl = row["url"]
            rargs = row["args"]
            rpos = row["position"]
            
            existing_by_id[int(rid)] = {
                "id": int(rid),
                "name": rname or "",
                "url": rurl or "",
                "args": rargs or "",
                "position": rpos if rpos is not None else -1,
            }
            existing_by_key[(rname or "", rurl or "", rargs or "")] = existing_by_id[
                int(rid)
            ]
            
            if rpos is not None:
                try:
                    if int(rpos) > max_pos:
                        max_pos = int(rpos)
                except Exception:
                    pass
        
        return existing_by_key, existing_by_id, max_pos
    
    def _assign_positions_for_items(
        self, items: list[dict[str, Any]], start_pos: int
    ) -> None:
        """Assigns position to items that don't have it set."""
        next_pos = start_pos
        for item in items:
            if item.get("position") is None:
                item["position"] = next_pos
                next_pos += 1
    
    def _build_update_params(
        self,
        items: list[dict[str, Any]],
        existing_by_key: dict[tuple[str, str, str], dict[str, Any]],
    ) -> tuple[list[tuple[Any, ...]], list[dict[str, Any]]]:
        """Forms parameters for UPDATE and list of inserts without id."""
        updates: list[tuple[Any, ...]] = []
        inserts_no_id: list[dict[str, Any]] = []
        
        for item in items:
            key = (item.get("name", ""), item.get("url", ""), item.get("args", ""))
            iid = item.get("id")
            
            if iid:
                # Has ID - prepare for UPDATE
                updates.append(self._build_update_tuple(item, int(iid)))
            else:
                # No ID - check if exists by key
                ex = existing_by_key.get(key)
                if ex:
                    # Found existing - update it
                    item["id"] = ex["id"]
                    updates.append(self._build_update_tuple(item, ex["id"]))
                else:
                    # Not found - insert new
                    inserts_no_id.append(item)
        
        return updates, inserts_no_id
    
    def _build_update_tuple(self, item: dict[str, Any], record_id: int) -> tuple:
        """Build tuple for UPDATE statement."""
        return (
            item.get("category_id"),
            item.get("name"),
            item.get("url"),
            item.get("type"),
            item.get("notes"),
            int(item.get("is_favorite", 0) or 0),
            item.get("last_used"),
            item.get("icon_path"),
            item.get("args"),
            item.get("browser_key"),
            item.get("position", 0) if item.get("position") is not None else 0,
            record_id,
        )
    
    def _execute_updates_collect_missing(
        self, updates: list[tuple[Any, ...]]
    ) -> list[dict[str, Any]]:
        """Execute batch UPDATE and collect records for insert with fixed id."""
        inserts_with_id: list[dict[str, Any]] = []
        
        if not updates:
            return inserts_with_id
        
        update_sql = (
            "UPDATE link SET category_id=?, name=?, url=?, type=?, notes=?, "
            "is_favorite=?, last_used=?, icon_path=?, args=?, browser_key=?, position=? WHERE id=?"
        )
        
        try:
            self.connection.executemany(update_sql, updates)
        except sqlite3.IntegrityError as e:
            raise DatabaseError(
                f"UNIQUE constraint failed during batch update: {e}"
            ) from e
        
        # Check which IDs actually existed
        update_ids = [int(p[-1]) for p in updates]
        if update_ids:
            placeholders = build_in_clause_placeholders(len(update_ids))
            cursor = self.connection.execute(
                f"SELECT id FROM link WHERE id IN ({placeholders})",
                tuple(update_ids),
            )
            existed_ids = {int(r["id"]) for r in cursor.fetchall()}
            
            # Collect non-existent IDs for INSERT
            for update_tuple in updates:
                record_id = int(update_tuple[-1])
                if record_id not in existed_ids:
                    inserts_with_id.append({
                        "id": record_id,
                        "category_id": update_tuple[0],
                        "name": update_tuple[1],
                        "url": update_tuple[2],
                        "type": update_tuple[3],
                        "notes": update_tuple[4],
                        "is_favorite": update_tuple[5],
                        "last_used": update_tuple[6],
                        "icon_path": update_tuple[7],
                        "args": update_tuple[8],
                        "browser_key": update_tuple[9],
                        "position": update_tuple[10],
                    })
        
        return inserts_with_id
    
    def _execute_inserts(
        self,
        inserts_no_id: list[dict[str, Any]],
        inserts_with_id: list[dict[str, Any]],
        all_fields: list[str],
    ) -> list[int]:
        """Execute INSERT operations and return created IDs."""
        created_ids: list[int] = []
        
        # Insert without ID (auto-generated)
        if inserts_no_id:
            columns_no_id = [f for f in all_fields if f != "id"]
            placeholders = ", ".join(["?"] * len(columns_no_id))
            insert_values = [
                tuple(item.get(c) for c in columns_no_id) for item in inserts_no_id
            ]
            
            try:
                self.connection.executemany(
                    f"INSERT INTO link ({', '.join(columns_no_id)}) VALUES ({placeholders})",
                    insert_values,
                )
            except sqlite3.IntegrityError as e:
                raise DatabaseError(
                    f"UNIQUE constraint failed during batch insert: {e}"
                ) from e
            
            # Fetch created IDs
            if inserts_no_id:
                first_id = self.connection.execute(
                    "SELECT last_insert_rowid()"
                ).fetchone()[0]
                created_ids.extend(range(first_id - len(inserts_no_id) + 1, first_id + 1))
        
        # Insert with fixed ID
        if inserts_with_id:
            insert_values_with_id = [
                tuple(item.get(f) for f in all_fields) for item in inserts_with_id
            ]
            placeholders_with_id = ", ".join(["?"] * len(all_fields))
            
            try:
                self.connection.executemany(
                    f"INSERT INTO link ({', '.join(all_fields)}) VALUES ({placeholders_with_id})",
                    insert_values_with_id,
                )
            except sqlite3.IntegrityError as e:
                raise DatabaseError(
                    f"UNIQUE constraint failed during batch insert with ID: {e}"
                ) from e
            
            created_ids.extend(int(item["id"]) for item in inserts_with_id)
        
        return created_ids


__all__ = ["LinkBulkUpsertService"]
