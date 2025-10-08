from typing import Any, Dict, Optional


class LinkRecordFactory:
    """Factory for creating link records in standardized format."""

    @staticmethod
    def create_link_record(
        name: str,
        url: str,
        link_type: str,
        icon_name: str,
        notes: str,
        last_used: Any,
        position: int,
        category_id: Optional[int],
        args: str = "",
        is_favorite: int = 0,
        link_id: Optional[int] = None,
        browser_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Creates link record with all required fields.

        Args:
            name: Link name
            url: URL or path to link
            link_type: Link type (web, file, folder, script, program, chromeapp)
            icon_name: Path to icon
            notes: Link notes
            last_used: Last used time
            position: Position in list
            category_id: Category ID
            args: Command line arguments
            is_favorite: Favorite flag (0 or 1)
            link_id: Link ID (for updating existing)
            browser_key: Browser key for web links

        Returns:
            Dictionary with link data
        """
        record = {
            "name": name,
            "url": url,
            "type": link_type,
            "icon_path": icon_name,
            "notes": notes,
            "last_used": last_used,
            "position": position,
            "category_id": category_id,
            "args": args,
            "is_favorite": is_favorite,
        }

        # Add browser_key if provided
        if browser_key is not None:
            record["browser_key"] = browser_key

        # Add ID if provided
        if link_id is not None:
            record["id"] = link_id

        return record


# Backward compatibility functions
def make_link_record(
    name: str,
    url: str,
    link_type: str,
    icon_name: str,
    notes: str,
    last_used: Any,
    position: int,
    category_id: Optional[int],
    args: str,
    is_favorite: int,
    link_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Creates regular link record (backward compatibility function)."""
    return LinkRecordFactory.create_link_record(
        name=name,
        url=url,
        link_type=link_type,
        icon_name=icon_name,
        notes=notes,
        last_used=last_used,
        position=position,
        category_id=category_id,
        args=args,
        is_favorite=is_favorite,
        link_id=link_id,
    )


def make_profile_link_record(
    link_name: str,
    url: str,
    link_type: str,
    icon_name: str,
    prof_args: str,
    notes: str,
    category_id: Optional[int],
    last_used: Any,
    position: int,
    link_id: Optional[int] = None,
    browser_key: Optional[str] = None,
) -> Dict[str, Any]:
    """Creates link record with browser profile (backward compatibility function)."""
    return LinkRecordFactory.create_link_record(
        name=link_name,
        url=url,
        link_type=link_type,
        icon_name=icon_name,
        notes=notes,
        last_used=last_used,
        position=position,
        category_id=category_id,
        args=prof_args,
        is_favorite=0,  # Profile links not in favorites by default
        link_id=link_id,
        browser_key=browser_key,
    )
