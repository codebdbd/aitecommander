from typing import Dict, List, Any

from app.utils.validators.validate_link_payload import ValidationError


def validate_toggle_favorite_input(link: Dict[str, Any]) -> None:
    """Validate input for toggle_favorite operation.

    Raises ValidationError on invalid input.
    """
    if not isinstance(link, dict):
        raise ValidationError("toggle_favorite expects a dict")
    link_id = link.get("id")
    if not isinstance(link_id, int) or link_id <= 0:
        raise ValidationError("toggle_favorite requires positive int id")


def validate_batch_update_links_input(links_data: List[Dict[str, Any]]) -> bool:
    """Validate input for batch_update_links operation.

    Returns True if valid; raises ValidationError or returns False if invalid.
    Empty list is treated as a no-op and valid.
    """
    if links_data is None:
        raise ValidationError("links_data must not be None")
    if not isinstance(links_data, list):
        raise ValidationError("links_data must be a list")
    if not links_data:
        return True

    for idx, item in enumerate(links_data):
        if not isinstance(item, dict) or not item:
            raise ValidationError(f"Invalid link payload at index {idx}")
    return True
