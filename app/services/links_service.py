from __future__ import annotations

from app.models.base.db_base import ValidationError
from app.models.db import Database
from app.models.types.link_type import LinkType
from app.models.types.link_types import LinkDict, LinkInput
from app.models.utils.link_validators import validate_link_data

from .bulk_operation_service import BulkOperationService
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
        self._bulk = BulkOperationService(db)

    # --- Reading ---
    def get_links(self, category_id: int) -> list[LinkDict]:
        self._validate_positive_int(category_id, "category_id")
        return self.repo.get_links(category_id)

    def get_links_for_categories(
        self, category_ids: list[int]
    ) -> dict[int, list[LinkDict]]:
        self._validate_positive_int_list(category_ids, "category_ids")
        return self.repo.get_links_for_categories(category_ids)

    def get_link_by_id(self, link_id: int) -> LinkDict | None:
        self._validate_positive_int(link_id, "link_id")
        return self.repo.get_link_by_id(link_id)

    def get_recent_links(self, limit: int = 10) -> list[LinkDict]:
        self._validate_positive_int(limit, "limit")
        return self.repo.get_recent_links(limit)

    def get_favorite_links(self, limit: int | None = None) -> list[LinkDict]:
        if limit is not None:
            self._validate_positive_int(limit, "limit")
        return self.repo.get_favorite_links(limit=limit)

    def search(self, query: str) -> list[LinkDict]:
        self._validate_str(query, "query")
        query = query.strip()
        if not query:
            return []
        return self.repo.search_links(query)

    def search_links(self, query: str) -> list[LinkDict]:
        """Alias for search method to maintain backward compatibility."""
        return self.search(query)

    def count_links_by_category(self, category_id: int) -> int:
        self._validate_positive_int(category_id, "category_id")
        return self.repo.count_links_by_category(category_id)

    def get_next_position(self, category_id: int) -> int:
        """Get next position for new link in category."""
        self._validate_positive_int(category_id, "category_id")
        return self.repo.get_next_position(category_id)

    # --- Checks/utilities ---
    def find_duplicate(
        self, category_id: int, name: str, url: str, args: str = ""
    ) -> LinkDict | None:
        self._validate_positive_int(category_id, "category_id")
        self._validate_non_empty_str(name, "name")
        self._validate_non_empty_str(url, "url")
        return self.repo.get_link_by_name_url_args(category_id, name, url, args)

    def find_by_unique_fields(
        self,
        category_id: int,
        url: str,
        args: str = "",
        link_type: str = "web",
        name: str = "",
    ) -> LinkDict | None:
        """Search link by unique fields (compatible with repository).

        Used as fallback path if search by (name,url,args) yielded no results.
        """
        self._validate_positive_int(category_id, "category_id")
        self._validate_non_empty_str(url, "url")
        self._validate_non_empty_str(link_type, "link_type")
        return self.repo.get_link_by_unique_fields(
            category_id, url, args, link_type, name
        )

    # --- Mutations ---
    @unit_of_work
    def create_or_update_link(self, link_data: LinkInput) -> int:
        """Creates or updates link. Returns id.
        Business rules (e.g., silent duplicate ignoring) are already implemented in repository.
        """
        self._validate_link_payload(link_data, "link_data", require_id=None)
        previous_icon_path = None
        link_id = link_data.get("id")
        if isinstance(link_id, int) and link_id > 0:
            existing = self.repo.get_link_by_id(link_id)
            if existing:
                previous_icon_path = existing.get("icon_path")

        saved_id = self.repo.upsert_link(link_data)
        new_icon_path = link_data.get("icon_path")
        if previous_icon_path and previous_icon_path != new_icon_path:
            self._cleanup_orphaned_icon(str(previous_icon_path))
        return saved_id

    def resolve_link_id(self, link_data: LinkInput) -> int | None:
        """Resolve persisted link ID by unique fields after batch save."""
        self._validate_link_payload(link_data, "link_data", require_id=None)
        link_id = link_data.get("id")
        if isinstance(link_id, int) and link_id > 0:
            return link_id

        category_id = int(link_data.get("category_id") or 0)
        if category_id <= 0:
            return None

        name = str(link_data.get("name") or "")
        url = str(link_data.get("url") or "").strip()
        args = str(link_data.get("args") or "")
        link_type = str(link_data.get("type") or LinkType.WEB.value)
        if not url:
            return None

        existing = self.find_duplicate(category_id, name, url, args)
        if not existing:
            existing = self.find_by_unique_fields(
                category_id,
                url,
                args=args,
                link_type=link_type,
                name=name,
            )
        if not existing:
            return None
        resolved = existing.get("id")
        return int(resolved) if isinstance(resolved, int) and resolved > 0 else None

    @unit_of_work
    def delete_link(self, link_id: int) -> None:
        """Удалить ссылку с очисткой осиротевшей иконки."""
        self._validate_positive_int(link_id, "link_id")

        # Получаем данные ссылки перед удалением
        link = self.repo.get_link_by_id(link_id)
        icon_path = link.get("icon_path") if link else None

        # Удаляем ссылку
        self.repo.delete_link(link_id)

        # Очищаем осиротевшую иконку
        if icon_path:
            self._cleanup_orphaned_icon(icon_path)

    @unit_of_work
    def update_last_used(self, link_id: int) -> None:
        self._validate_positive_int(link_id, "link_id")
        self.repo.update_link_last_used(link_id)

    @unit_of_work
    def clear_favorites(self) -> None:
        self.repo.clear_favorites()

    def reorder(self, link_ids: list[int]) -> bool:
        """Reorder links in a category by IDs.

        Note: repository manages its own transaction to avoid nested ones.
        """
        # IMPORTANT: update_link_order in repository manages transaction itself via self.transaction()
        # Wrapping in UnitOfWork will lead to nested transaction (SQLite: cannot start a transaction within a transaction)
        self._validate_positive_int_list(link_ids, "link_ids")
        return self.repo.update_link_order(link_ids)

    def batch_update(self, links_data: list[LinkInput]) -> bool:
        """Bulk update links.

        Note: empty input is a no-op and returns True.
        """
        # IMPORTANT: batch_update_links inside repository already manages transaction
        # via self.transaction(). Cannot wrap in UnitOfWork - this will lead
        # to nested transaction (SQLite: "cannot start a transaction within a transaction").
        self._validate_list_payload(links_data, "links_data")
        self._validate_link_payload_list(
            links_data, "links_data", require_id=True
        )
        if not links_data:
            return True
        return self._bulk.update_links_bulk(links_data)

    def batch_create_or_update_links(
        self, links_data: list[LinkInput]
    ) -> list[int]:
        """Batch creation/update of links with return of created IDs.

        Delegates to BulkOperationService, which validates input and calls
        repo.batch_upsert_links. Transaction handling is done in repository to
        avoid nested transactions.
        """
        # IMPORTANT: batch_upsert_links manages transaction itself via self.transaction()
        # Wrapping in UnitOfWork will lead to nested transaction in SQLite.
        self._validate_list_payload(links_data, "links_data")
        self._validate_link_payload_list(
            links_data, "links_data", require_id=None
        )
        if not links_data:
            return []
        return self._bulk.create_links_bulk(links_data)

    def count_favorites(self) -> int:
        """Returns number of favorite links."""
        return self.repo.count_favorites()

    def move_links_bulk(self, link_ids: list[int], target_category_id: int) -> int:
        """Move multiple links to another category in a single transaction."""
        self._validate_positive_int_list(link_ids, "link_ids")
        self._validate_positive_int(target_category_id, "target_category_id")
        return self._bulk.move_links_bulk(link_ids, target_category_id)

    def batch_delete_links(self, link_ids: list[int]) -> int:
        """Удалить несколько ссылок по IDs с очисткой осиротевших иконок."""
        self._validate_positive_int_list(link_ids, "link_ids")

        # Получаем данные ссылок перед удалением
        links_to_delete = []
        for link_id in link_ids:
            link = self.repo.get_link_by_id(link_id)
            if link and link.get("icon_path"):
                links_to_delete.append(link["icon_path"])

        # Удаляем ссылки
        deleted_count = self._bulk.delete_links_bulk(link_ids)

        # Очищаем осиротевшие иконки
        for icon_path in links_to_delete:
            self._cleanup_orphaned_icon(icon_path)

        return deleted_count

    def _cleanup_orphaned_icon(self, icon_path: str) -> None:
        """Очистить осиротевшую иконку, если она больше не используется."""
        try:
            from .icon_reference_service import IconReferenceService

            icon_service = IconReferenceService(self.db)
            icon_service.cleanup_icon_if_orphaned(icon_path)
        except Exception as e:
            # Не позволяем ошибке очистки нарушить основную операцию
            import logging

            logging.getLogger(__name__).warning(
                "Failed to cleanup orphaned icon %s: %s", icon_path, e
            )

    @staticmethod
    def _validate_positive_int(value: object, field_name: str) -> None:
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise ValidationError(f"{field_name} must be a positive int")

    @staticmethod
    def _validate_non_negative_int(value: object, field_name: str) -> None:
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValidationError(f"{field_name} must be a non-negative int")

    @staticmethod
    def _validate_positive_int_list(values: object, field_name: str) -> None:
        if not isinstance(values, list):
            raise ValidationError(f"{field_name} must be a list of positive ints")
        for idx, value in enumerate(values):
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ValidationError(
                    f"{field_name}[{idx}] must be a positive int"
                )

    @staticmethod
    def _validate_non_empty_str(value: object, field_name: str) -> None:
        if not isinstance(value, str) or not value.strip():
            raise ValidationError(f"{field_name} must be a non-empty string")

    @staticmethod
    def _validate_str(value: object, field_name: str) -> None:
        if not isinstance(value, str):
            raise ValidationError(f"{field_name} must be a string")

    @staticmethod
    def _validate_list_payload(value: object, field_name: str) -> None:
        if not isinstance(value, list):
            raise ValidationError(f"{field_name} must be a list")

    @staticmethod
    def _validate_dict_payload(value: object, field_name: str) -> None:
        if not isinstance(value, dict):
            raise ValidationError(f"{field_name} must be a dict")

    @classmethod
    def _validate_link_payload(
        cls,
        value: object,
        field_name: str,
        *,
        require_id: bool | None,
    ) -> None:
        cls._validate_dict_payload(value, field_name)
        link_data = value  # type: ignore[assignment]
        validate_link_data(link_data)

        cls._validate_id_block(link_data, field_name, require_id)
        cls._validate_category_id_block(link_data, field_name)
        cls._validate_required_fields_for_new(link_data, field_name)
        cls._validate_optional_position(link_data, field_name)
        cls._validate_optional_is_favorite(link_data, field_name)
        cls._validate_optional_string_fields(link_data, field_name)
        cls._validate_optional_type(link_data, field_name)

    @classmethod
    def _validate_id_block(
        cls, link_data: dict, field_name: str, require_id: bool | None
    ) -> None:
        if require_id is True:
            if link_data.get("id") is None:
                raise ValidationError(f"{field_name}.id is required")
            cls._validate_positive_int(link_data["id"], f"{field_name}.id")
        elif "id" in link_data and link_data["id"] is not None:
            cls._validate_positive_int(link_data["id"], f"{field_name}.id")

    @classmethod
    def _validate_category_id_block(cls, link_data: dict, field_name: str) -> None:
        if link_data.get("category_id") is None:
            raise ValidationError(f"{field_name}.category_id is required")
        cls._validate_positive_int(link_data["category_id"], f"{field_name}.category_id")

    @classmethod
    def _validate_required_fields_for_new(cls, link_data: dict, field_name: str) -> None:
        if link_data.get("id") is None:
            cls._validate_non_empty_str(link_data.get("name"), f"{field_name}.name")
            cls._validate_non_empty_str(link_data.get("url"), f"{field_name}.url")

    @classmethod
    def _validate_optional_position(cls, link_data: dict, field_name: str) -> None:
        if "position" in link_data and link_data["position"] is not None:
            cls._validate_non_negative_int(link_data["position"], f"{field_name}.position")

    @classmethod
    def _validate_optional_is_favorite(cls, link_data: dict, field_name: str) -> None:
        if "is_favorite" not in link_data:
            return
        is_favorite = link_data["is_favorite"]
        if is_favorite is None:
            return
        if isinstance(is_favorite, bool):
            return
        if not isinstance(is_favorite, int) or is_favorite not in (0, 1):
            raise ValidationError(f"{field_name}.is_favorite must be 0 or 1")

    @classmethod
    def _validate_optional_string_fields(cls, link_data: dict, field_name: str) -> None:
        for key in ("name", "url", "notes", "last_used", "icon_path", "args", "browser_key"):
            if key in link_data and link_data[key] is not None and not isinstance(link_data[key], str):
                raise ValidationError(f"{field_name}.{key} must be a string")

    @classmethod
    def _validate_optional_type(cls, link_data: dict, field_name: str) -> None:
        if "type" in link_data and link_data["type"] is not None:
            if not isinstance(link_data["type"], (str, LinkType)):
                raise ValidationError(f"{field_name}.type must be a string or LinkType")

    @classmethod
    def _validate_link_payload_list(
        cls,
        values: list[LinkInput],
        field_name: str,
        *,
        require_id: bool | None,
    ) -> None:
        for idx, value in enumerate(values):
            cls._validate_link_payload(
                value, f"{field_name}[{idx}]", require_id=require_id
            )
