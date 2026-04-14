"""
Data validation module for Osteen Path application.
Divided into specialized modules by validation types.
"""

from .basic_validators import (
    validate_category_id,
    validate_link_type,
    validate_path,
    validate_required_fields,
)
from .import_validators import can_parse_bookmarks_html, is_valid_bookmarks_html
from .link_validators import (
    extract_base_name_from_profile_name,
    validate_chrome_profile_name,
    validate_link_duplicate,
    validate_link_form_data,
    validate_name_and_url,
    validate_web_url,
)
from .structure_validators import (
    has_no_forbidden_chars,
    is_name_length_ok,
    is_non_empty_name,
    validate_category_data,
    validate_section_data,
)

__all__ = [
    # Basic validators
    "validate_required_fields",
    "validate_link_type",
    "validate_path",
    "validate_category_id",
    # Link validators
    "validate_name_and_url",
    "validate_web_url",
    "validate_link_duplicate",
    "validate_link_form_data",
    "validate_chrome_profile_name",
    "extract_base_name_from_profile_name",
    # File validators (without UI icons) — empty after inlining
    # Structure validators
    "validate_section_data",
    "is_non_empty_name",
    "is_name_length_ok",
    "has_no_forbidden_chars",
    "validate_category_data",
    # Import validators
    "is_valid_bookmarks_html",
    "can_parse_bookmarks_html",
]
