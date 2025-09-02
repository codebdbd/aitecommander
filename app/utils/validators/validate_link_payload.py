from typing import Any, Dict

from app.utils.validators.link_validators import validate_link_form_data


class ValidationError(ValueError):
    """Ошибка валидации данных ссылки."""


def validate_link_payload(data: Dict[str, Any]) -> Dict[str, Any]:
    """Проверить и нормализовать входные данные ссылки.

    Возвращает нормализованный словарь данных или выбрасывает ValidationError.
    """
    if not isinstance(data, dict):
        raise ValidationError("Invalid link data provided: not a dict")

    name = data.get("name")
    url = data.get("url")
    link_type = data.get("type")
    category_id = data.get("category_id")

    # Нормализация строк
    if isinstance(name, str):
        name = name.strip()
    if isinstance(url, str):
        url = url.strip()
    if isinstance(link_type, str):
        link_type = link_type.strip()

    if not (validate_link_form_data(name, url, link_type)):
        raise ValidationError("Invalid link fields: name/url/type")

    if not isinstance(category_id, int) or category_id <= 0:
        raise ValidationError("Invalid category_id: must be positive int")

    normalized = dict(data)
    normalized["name"] = name
    normalized["url"] = url
    normalized["type"] = link_type
    normalized["category_id"] = int(category_id)
    return normalized
