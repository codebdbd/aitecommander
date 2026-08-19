"""
Universal processor for handling profiles of any browsers.
"""

import logging
from typing import Any, Optional

from app.utils.links.link_factory import make_profile_link_record
from app.utils.validators import (
    extract_base_name_from_profile_name,
    validate_chrome_profile_name,
)

from .profile_manager import get_profile_manager
from .utils import get_browser_display_name

logger = logging.getLogger(__name__)


class UniversalProfileProcessor:
    """Universal processor for handling profiles of any browsers."""

    def __init__(self, database):
        """
        Initialization of processor.

        Args:
            database: Database object for working with links
        """
        self.database = database
        self.profile_manager = get_profile_manager()
        logger.info("Initialized universal profile processor")

    def process_profile_links(

        self,

        name: str,

        url: str,

        link_type: str,

        icon_name: str,

        notes: str,

        category_id: int,

        browser_key: str,

        selected_profiles: list[dict],

        existing_link: Optional[dict[Any, Any]] = None,

        user_args: Optional[str] = None,

        existing_links_in_category: Optional[list[dict[Any, Any]]] = None,

    ) -> list[dict]:

        """

        Processes browser profiles and creates corresponding links.

    

        Args:

            name: Base link name

            url: Link URL

            link_type: Link type

            icon_name: Icon name

            notes: Notes

            category_id: Category ID

            browser_key: Browser key

            selected_profiles: List of selected profiles

            existing_link: Existing link (when editing)

            user_args: User arguments (if manually specified)

            existing_links_in_category: Existing links in category (for duplicate checking)

    

        Returns:

            List[Dict]: List of created link records

        """

        # Log immediately upon entering method

        logger.debug(

            "ENTER process_profile_links: browser_key=%s, selected_profiles_count=%s",

            browser_key,

            len(selected_profiles),

        )

        # Log input parameters for debugging

        logger.debug(

            "process_profile_links called with: name='%s', url='%s', link_type='%s', browser_key='%s', selected_profiles_count=%s, existing_link=%s, user_args=%s",

            name,

            url,

            link_type,

            browser_key,

            len(selected_profiles),

            "present" if existing_link else "None",

            "present" if user_args else "None",

        )

    

        logger.debug(

            "process_profile_links: name=%s, browser_key=%s, selected_profiles count=%s",

            name,

            browser_key,

            len(selected_profiles),

        )

    

        if not selected_profiles:

            logger.warning("No profiles selected")

            return []

    

        finder = self.profile_manager.finders.get(browser_key)

        if not finder:

            logger.error("Unknown browser: %s", browser_key)

            return []

    

        logger.info(

            "Processing %s profiles of %s",

            len(selected_profiles),

            get_browser_display_name(finder, browser_key),

        )

        logger.debug("Selected profiles: %s", selected_profiles)

    

        # Extract base name

        base_name = extract_base_name_from_profile_name(name)

    

        # Existing links and duplicate keys

        existing_links = self._load_existing_links(category_id, existing_links_in_category)

        existing_keys = self._build_existing_keys(existing_links)

    

        result_links: list[dict] = []

        is_edit = existing_link is not None

        existing_link_data = existing_link if existing_link is not None else None

        existing_last_used = (

            existing_link_data.get("last_used") if existing_link_data is not None else None

        )

        existing_position = 0

        if existing_link_data is not None:

            position_value = existing_link_data.get("position", 0)

            try:

                existing_position = int(position_value)  # type: ignore[arg-type]

            except (TypeError, ValueError):

                existing_position = 0

    

        for profile in selected_profiles:

            try:

                maybe_link = self._process_single_profile(

                    finder=finder,

                    profile=profile,

                    user_args=user_args,

                    browser_key=browser_key,

                    base_name=base_name,

                    name=name,

                    url=url,

                    link_type=link_type,

                    icon_name=icon_name,

                    notes=notes,

                    category_id=category_id,

                    is_edit=is_edit,

                    existing_link_data=existing_link_data,

                    existing_last_used=existing_last_used,

                    existing_position=existing_position,

                    existing_keys=existing_keys,

                    selected_count=len(selected_profiles),

                    current_results=result_links,

                )

                if maybe_link:

                    result_links.append(maybe_link)

            except Exception as e:

                logger.error(

                    "Error processing profile %s: %s", profile, e, exc_info=True

                )

                continue

    

        logger.info(

            "Created %s links for %s",

            len(result_links),

            get_browser_display_name(finder, browser_key),

        )

        return result_links


    def _load_existing_links(

        self, category_id: int, existing_links_in_category: Optional[list[dict]]

    ) -> list[dict]:

        if existing_links_in_category is not None:

            return [dict(link) for link in existing_links_in_category]

        try:

            return [dict(link) for link in self.database.links.get_links(category_id)]

        except Exception:

            return []


    def _build_existing_keys(self, existing_links: list[dict]) -> set[tuple[Any, Any, Any]]:

        """Build duplicate-check keys as (url, type, args)."""

        try:

            return {

                (

                    link_item.get("url"),

                    link_item.get("type"),

                    (

                        link_item.get("args")

                        if (

                            hasattr(link_item, "get") and link_item.get("args") is not None

                        )

                        else link_item.get("args") if isinstance(link_item, dict) else ""

                    ),

                )

                for link_item in existing_links

            }

        except Exception:

            return set()


    def _process_single_profile(

        self,

        *,

        finder,

        profile: dict,

        user_args: Optional[str],

        browser_key: str,

        base_name: str,

        name: str,

        url: str,

        link_type: str,

        icon_name: str,

        notes: str,

        category_id: int,

        is_edit: bool,

        existing_link_data: Optional[dict[Any, Any]],

        existing_last_used,

        existing_position: int,

        existing_keys: set[tuple[Any, Any, Any]],

        selected_count: int,

        current_results: list[dict],

    ) -> Optional[dict]:

        logger.debug("Processing profile: %s", profile)

        prof_name = self._format_profile_name(finder, profile)

        logger.debug("Formatted profile name: %s", prof_name)

        profile_arg = finder.get_profile_argument(profile)
        if user_args:
            # Prepend/combine profile argument with user-specified arguments
            if profile_arg not in user_args:
                prof_args = f"{profile_arg} {user_args}".strip()
            else:
                prof_args = user_args
            logger.debug("Combined profile and user args: '%s'", prof_args)
        else:
            prof_args = profile_arg
            logger.debug("Using profile arg only: '%s'", prof_args)

    

        if not prof_args:

            logger.info(

                "Skipping profile '%s' — empty arguments (browser=%s)",

                prof_name,

                browser_key,

            )

            return None
        existing_args = existing_link_data.get("args", "") if existing_link_data is not None else ""

        existing_id = existing_link_data.get("id") if existing_link_data is not None else None

        is_current = is_edit and prof_args == existing_args

        if is_edit and not is_current and existing_id:

            is_current = any(link.get("id") == existing_id for link in current_results)

    

        logger.debug(

            "Profile check: prof_args='%s', existing_args='%s', is_edit=%s, is_current=%s",

            prof_args,

            existing_args,

            is_edit,

            is_current,

        )

    

        link_name = self._generate_link_name(

            base_name, prof_name, selected_count == 1, is_current, name

        )

        logger.debug("Generated link_name='%s' for profile '%s'", link_name, prof_name)

    

        skip_duplicate_check = False

        if is_edit and not is_current and existing_link_data:

            skip_duplicate_check = True

            logger.debug(

                "Skipping duplicate check for profile of another browser: %s",

                prof_name,

            )

    

        logger.debug(

            "Duplicate check for %s: skip=%s, url=%s, type=%s, args=%s",

            link_name,

            skip_duplicate_check,

            url,

            link_type,

            prof_args,

        )

    

        duplicate_check_result = False

        if not skip_duplicate_check and not is_current:

            duplicate_check_result = (url, link_type, prof_args) in existing_keys

    

        logger.debug("Duplicate check result: %s", duplicate_check_result)

        if not skip_duplicate_check and duplicate_check_result:

            logger.info(

                "Skipping duplicate: name='%s', args='%s' (browser=%s)",

                link_name,

                prof_args,

                browser_key,

            )

            return None

    

        link_record = make_profile_link_record(

            link_name=link_name,

            url=url,

            link_type=link_type,

            icon_name=icon_name,

            prof_args=prof_args,

            notes=notes,

            category_id=category_id,

            last_used=existing_last_used,

            position=existing_position if existing_link_data is not None else 0,

            link_id=existing_id if is_current else None,

            browser_key=browser_key,

        )

        logger.debug("Created link: %s with arguments %s", link_name, prof_args)

        return link_record
    def _format_profile_name(self, finder, profile: dict) -> str:
        """Formats profile name for display."""
        if hasattr(finder, "format_profile_display_name"):
            display_name = finder.format_profile_display_name(profile)
        else:
            display_name = ""

        # Prefer profile name over email for link naming
        profile_name = (
            profile.get("name")
            or profile.get("email")
            or display_name
            or getattr(finder, "get_browser_name", lambda: "Browser")()
        )
        return validate_chrome_profile_name(profile_name)

    def _generate_link_name(
        self,
        base_name: str,
        profile_name: str,
        is_single_profile: bool,
        is_current_profile: bool,
        original_name: str,
    ) -> str:
        """Generates link name for profile."""
        logger.debug(
            "_generate_link_name: base_name='%s', profile_name='%s', is_single_profile=%s, is_current_profile=%s, original_name='%s'",
            base_name,
            profile_name,
            is_single_profile,
            is_current_profile,
            original_name,
        )

        # When editing current profile, always preserve user name
        if is_current_profile:
            logger.debug(
                "_generate_link_name: returning original_name='%s' (current profile)",
                original_name,
            )
            return original_name

        # For new links use standard name generation logic
        if profile_name == "Chrome" or profile_name == "Firefox":
            logger.debug(
                "_generate_link_name: returning base_name='%s' (default browser)",
                base_name,
            )
            return base_name

        generated_name = f"{base_name} | {profile_name}"
        logger.debug(
            "_generate_link_name: returning generated_name='%s' (new profile)",
            generated_name,
        )
        return generated_name

    def parse_existing_profile(self, link: dict) -> tuple[Optional[str], list[dict]]:
        """
        Parses existing profile from link and determines browser.

        Args:
            link: Link data

        Returns:
            tuple: (browser_key, [profile_data]) or (None, [])
        """
        logger.debug("parse_existing_profile: link=%s", link)

        if not (link.get("id") and link.get("type") == "web" and link.get("args")):
            logger.debug("parse_existing_profile: missing required fields")
            return None, []

        args = link.get("args", "")
        logger.debug("parse_existing_profile: args=%s", args)

        # Determine browser by arguments
        browser_key = self.profile_manager.detect_browser_from_args(args)
        logger.debug("parse_existing_profile: detected browser_key=%s", browser_key)

        if not browser_key:
            logger.debug("Failed to determine browser by arguments: %s", args)
            return None, []

        finder = self.profile_manager.finders[browser_key]
        logger.debug("parse_existing_profile: finder=%s", finder)

        parsed_profile = finder.parse_profile_from_args(args)
        logger.debug("parse_existing_profile: parsed_profile=%s", parsed_profile)

        if parsed_profile:
            logger.debug("Determined profile %s: %s", browser_key, parsed_profile)
            return browser_key, [parsed_profile]

        logger.debug("parse_existing_profile: could not parse profile")
        return None, []

    def validate_profiles(
        self, browser_key: str, selected_profiles: list[dict]
    ) -> bool:
        """Validates selected profiles."""
        if not selected_profiles:
            return False

        finder = self.profile_manager.finders.get(browser_key)
        if not finder:
            return False

        # Check that all profiles have required fields
        for profile in selected_profiles:
            if not isinstance(profile, dict):
                return False
            if not finder.validate_profile_data(profile):
                return False

        return True


