import logging
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


def validate_name_and_url(name: str, url: str) -> bool:
    """Check: name and path/URL are not empty."""
    return bool(name) and bool(url)


def validate_web_url(url: str) -> bool:
    parsed_url = urlparse(url)
    return bool(parsed_url.netloc) and ("." in parsed_url.netloc)


def validate_favorite_limit(db, want_fav: bool, is_edit: bool, was_fav: bool) -> bool:
    if want_fav and (not is_edit or not was_fav):
        fav_count = db.links.count_favorites()
        if fav_count >= 20:
            return False
    return True


def validate_link_duplicate(
    url: str,
    link_type: str,
    args: str,
    existing_links: list,
    current_link_id: int = None,
) -> bool:
    """Checks if there is no duplicate link in the category."""
    for link in existing_links:
        # Skip current edited link
        if current_link_id and link["id"] == current_link_id:
            continue

        # Check URL, type and arguments match
        link_args = (
            link.get("args")
            if hasattr(link, "get")
            else link["args"]
            if "args" in link
            else ""
        )
        if link["url"] == url and link["type"] == link_type and (link_args == args):
            try:
                logger.info(
                    f"validate_link_duplicate: duplicate found id={link.get('id')} name='{link.get('name', '')}' "
                    f"url='{url}' type='{link_type}' args='{args}' (current_link_id={current_link_id})"
                )
            except Exception:
                pass
            return True  # Duplicate found

    return False  # Duplicate not found


def validate_chrome_profile_name(profile_name: str) -> str:
    """Cleans and validates Chrome profile name."""
    if not profile_name:
        return "Chrome"

    # Remove email domain if present
    if "@" in profile_name:
        profile_name = profile_name.split("@")[0]

    return profile_name if profile_name != "Chrome" else "Chrome"


def extract_base_name_from_profile_name(name: str) -> str:
    """Extracts base name from name with profile."""
    import re

    match = re.match(r"^(.*?)\s*\(.*\)$", name)
    if match:
        return match.group(1).strip()
    return name


def validate_link_form_data(name: str, url: str, link_type: str) -> bool:
    """Comprehensive validation of link form data."""
    # 1. Check required fields
    if not validate_name_and_url(name, url):
        return False

    # 2. Check link type
    from .basic_validators import validate_link_type, validate_path

    if not validate_link_type(link_type):
        return False

    # 3. Check path for file links
    if link_type in ("file", "folder"):
        if not validate_path(url):
            return False

    # 4. Check web URL
    if link_type == "web" and not validate_web_url(url):
        return False

    return True
