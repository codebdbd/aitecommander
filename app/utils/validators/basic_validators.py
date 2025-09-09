import logging

logger = logging.getLogger(__name__)


def validate_required_fields(
    data: dict, required_fields: list, entity_name: str = ""
) -> bool:
    """Проверяет наличие обязательных полей в словаре данных.
    Логирует ошибку, если поля отсутствуют.
    """
    missing_fields = [field for field in required_fields if field not in data]
    if missing_fields:
        logger.error(
            f"Отсутствуют обязательные поля для {entity_name}: {missing_fields}"
        )
        return False
    return True


def validate_link_type(link_type) -> bool:
    """Проверяет, что тип ссылки — непустая строка."""
    return isinstance(link_type, str) and link_type.strip() != ""


def validate_path(path) -> bool:
    """Проверяет, что путь — непустая строка."""
    return isinstance(path, str) and path.strip() != ""


def validate_category_id(category_id) -> bool:
    """Проверяет, что ID категории корректно."""
    return category_id is not None and isinstance(category_id, int) and category_id > 0
