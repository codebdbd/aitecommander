import logging

logger = logging.getLogger(__name__)


def validate_required_fields(
    data: dict, required_fields: list, entity_name: str = ""
) -> bool:
    """Checks for required fields in data dictionary.
    Logs error if fields are missing.
    """
    missing_fields = [field for field in required_fields if field not in data]
    if missing_fields:
        logger.error(f"Missing required fields for {entity_name}: {missing_fields}")
        return False
    return True


def validate_link_type(link_type) -> bool:
    """Checks that link type is a non-empty string."""
    return isinstance(link_type, str) and link_type.strip() != ""


def validate_path(path) -> bool:
    """Checks that path is a non-empty string."""
    return isinstance(path, str) and path.strip() != ""


def validate_category_id(category_id) -> bool:
    """Checks that category ID is valid."""
    return category_id is not None and isinstance(category_id, int) and category_id > 0
