# app/controllers/link_dialog_controller.py

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from app.models.db import Database

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from app.controllers.business.structure_business import StructureBusinessLogic


class LinkDialogController:
    """Controller for managing link dialog business logic."""

    def __init__(
        self,
        database: Database,
        *,
        structure_business: Optional["StructureBusinessLogic"] = None,
    ):
        self.database = database
        self.structure_business = structure_business
        from app.controllers.business.links_business import LinksBusinessLogic

        self.links_business = LinksBusinessLogic(database)
        self.result_data: list[dict[str, Any]] = []
        self.profile_manager = None

    def _get_profile_manager(self):
        """Initialize browser profile manager only when needed."""
        if self.profile_manager is None:
            from app.utils.browser.browser_profiles import get_profile_manager

            self.profile_manager = get_profile_manager()
        return self.profile_manager

    def _get_spheres_cached(self) -> list[dict[str, Any]]:
        if self.structure_business is not None:
            try:
                spheres = self.structure_business.get_cached_spheres()
                if spheres:
                    return spheres
            except Exception as exc:
                logger.debug("Failed to read cached spheres: %s", exc, exc_info=True)
        return self.database.spheres.get_spheres() or []

    def _get_sections_cached(self, sphere_id: int) -> list[dict[str, Any]]:
        if self.structure_business is not None:
            try:
                sections = self.structure_business.get_cached_sections(sphere_id)
                if sections:
                    return sections
            except Exception as exc:
                logger.debug(
                    "Failed to read cached sections for %s: %s",
                    sphere_id,
                    exc,
                    exc_info=True,
                )
        return self.database.sections.get_sections(sphere_id) or []

    def _get_categories_cached(self, section_id: int) -> list[dict[str, Any]]:
        if self.structure_business is not None:
            try:
                categories = self.structure_business.get_cached_categories(section_id)
                if categories:
                    return categories
            except Exception as exc:
                logger.debug(
                    "Failed to read cached categories for %s: %s",
                    section_id,
                    exc,
                    exc_info=True,
                )
        return self.database.categories.get_categories(section_id) or []

    def get_initialization_data(
        self, category_id: Optional[int] = None, link: Optional[dict] = None
    ) -> dict[str, Any]:
        """Gets data for dialog initialization."""
        # Get spheres
        spheres = self._get_spheres_cached()

        # Determine category hierarchy
        category_hierarchy = None
        if category_id:
            category_hierarchy = self._get_category_hierarchy(category_id)
        elif link and link.get("category_id"):
            category_hierarchy = self._get_category_hierarchy(link["category_id"])

        return {
            "spheres": spheres,
            "category_hierarchy": category_hierarchy,
            # Browser profiles are loaded only on explicit profile selection.
            "chrome_profiles": [],
            "selected_category_id": category_id,
            "form_data": link,
        }

    def _get_category_hierarchy(self, category_id: int) -> Optional[dict[str, int]]:
        """Gets hierarchy for category (sphere -> section -> category)."""
        return self.database.categories.get_category_hierarchy(category_id)

    def _get_chrome_profiles(self) -> list[dict[str, Any]]:
        """Gets list of Chrome profiles."""
        try:
            return self._get_profile_manager().get_browser_profiles("chrome")
        except Exception:
            return []

    def get_sections_for_sphere(self, sphere_id: int) -> list[dict[str, Any]]:
        """Gets sections for sphere."""
        return self._get_sections_cached(sphere_id)

    def get_categories_for_section(self, section_id: int) -> list[dict[str, Any]]:
        """Gets categories for section."""
        return self._get_categories_cached(section_id)

    def validate_and_save(self, form_data: dict[str, Any]) -> dict[str, Any]:
        """Validates form data and prepares for saving."""
        # Basic validation
        validation_result = self._validate_form_data(form_data)
        if not validation_result["is_valid"]:
            return validation_result

        # Prepare data for saving
        self.result_data = self._prepare_links_data(form_data)

        return {"is_valid": True, "errors": []}

    def _validate_form_data(self, form_data: dict[str, Any]) -> dict[str, Any]:
        """Validates form data."""
        errors = []

        # Check required fields
        if not form_data.get("name", "").strip():
            errors.append("Имя ссылки не может быть пустым.")

        if not form_data.get("url", "").strip():
            errors.append("URL/Путь не может быть пустым.")

        if not form_data.get("link_type"):
            errors.append("Выберите тип ссылки.")

        if not form_data.get("category_id"):
            errors.append("Выберите категорию.")

        # Check file paths
        link_type = form_data.get("link_type")
        url = form_data.get("url", "").strip()
        if link_type in ("file", "folder") and url:
            if not Path(url).exists():
                errors.append("Указанный путь не существует.")

        return {"is_valid": len(errors) == 0, "errors": errors}

    def _prepare_links_data(self, form_data: dict[str, Any]) -> list[dict[str, Any]]:
        """Prepares link data for saving."""
        links_data = []

        # Edit mode: if web and profiles are set —
        # uses profile processing (will update current and add missing);
        # otherwise — one record
        is_edit = form_data.get("link_id") is not None
        if is_edit:
            if (
                form_data.get("link_type") == "web"
                and form_data.get("selected_profiles")
                and form_data.get("profiles_explicitly_changed")
            ):
                links_data.extend(self._prepare_profile_links(form_data))
            else:
                links_data.append(self._prepare_regular_link(form_data))
        else:
            # Режим создания: сохраняем текущее поведение —
            #   web + выбранные профили -> несколько записей;
            #   иначе -> одна запись
            if form_data.get("link_type") == "web" and form_data.get(
                "selected_profiles"
            ):
                links_data.extend(self._prepare_profile_links(form_data))
            else:
                links_data.append(self._prepare_regular_link(form_data))

        return links_data

    def _get_existing_link_data(self, form_data):
        """Get existing link data if editing."""
        is_edit = form_data.get("link_id") is not None
        if not is_edit:
            return None
        return {
            "id": form_data["link_id"],
            "args": form_data.get("args", ""),
            "last_used": form_data.get("last_used"),
            "position": form_data.get("position", 0),
        }

    def _detect_browser_key(self, profile, manager):
        """Detect browser key for profile."""
        browser_key = profile.get("browser_key")
        if browser_key:
            return browser_key

        browser_key = manager.detect_browser_from_args(profile.get("args", ""))
        if browser_key:
            return browser_key

        for key, finder in manager.finders.items():
            try:
                if hasattr(
                    finder, "validate_profile_data"
                ) and finder.validate_profile_data(profile):
                    return key
            except Exception:
                continue
        return None

    def _group_profiles_by_browser(self, selected_profiles, manager):
        """Group profiles by browser key."""
        profiles_by_browser = {}
        for profile in selected_profiles:
            browser_key = self._detect_browser_key(profile, manager)
            if not browser_key:
                logger.debug(
                    f"_prepare_profile_links: пропущен профиль без определённого браузера: {profile}"
                )
                continue
            if browser_key not in profiles_by_browser:
                profiles_by_browser[browser_key] = []
            profiles_by_browser[browser_key].append(profile)
        return profiles_by_browser

    def _log_profile_groups(self, profiles_by_browser):
        """Log profile grouping information."""
        try:
            summary = {bk: len(ps) for bk, ps in profiles_by_browser.items()}
            logger.info(
                "_prepare_profile_links: сгруппировано профилей по браузерам: %s",
                summary,
            )
        except Exception:
            logger.debug("Profiles by browser: %s", profiles_by_browser)
        for browser_key, profiles in profiles_by_browser.items():
            logger.debug("Browser %s: %s profiles", browser_key, len(profiles))
            for i, profile in enumerate(profiles):
                logger.debug(
                    "  Profile %s: %s - args: %s - directory: %s",
                    i,
                    profile.get("name", "Unknown"),
                    profile.get("args", "None"),
                    profile.get("directory", "None"),
                )

    def _prepare_profile_links(self, form_data: dict[str, Any]) -> list[dict[str, Any]]:
        """Prepares links with profiles of any browsers."""
        from app.utils.browser.browser_profiles import UniversalProfileProcessor

        processor = UniversalProfileProcessor(self.database)
        existing_link = self._get_existing_link_data(form_data)
        selected_profiles = form_data["selected_profiles"]
        if not selected_profiles:
            return []

        manager = self.profile_manager
        profiles_by_browser = self._group_profiles_by_browser(
            selected_profiles, manager
        )
        self._log_profile_groups(profiles_by_browser)

        if not profiles_by_browser:
            return []

        result_links = []
        current_browser_key = None
        if existing_link and existing_link.get("args"):
            current_browser_key = manager.detect_browser_from_args(
                existing_link.get("args", "")
            )

        first_browser_key = next(iter(profiles_by_browser))
        first_profiles = profiles_by_browser[first_browser_key]
        user_args = self._get_user_args_if_modified(
            form_data, existing_link, first_profiles, first_browser_key
        )

        # Get all existing links in category for duplicate checking
        existing_links_in_category = []
        if form_data.get("category_id"):
            existing_links_in_category = list(
                self.database.links.get_links(form_data["category_id"])
            )

        # Обрабатываем профили для каждого браузера
        for browser_key, profiles in profiles_by_browser.items():
            # Create separate links for each browser
            browser_links = processor.process_profile_links(
                name=form_data["name"],
                url=form_data["url"],
                link_type=form_data["link_type"],
                icon_name=form_data.get("icon_name", ""),
                notes=form_data.get("notes", ""),
                category_id=form_data["category_id"],
                browser_key=browser_key,
                selected_profiles=profiles,
                existing_link=existing_link
                if browser_key == current_browser_key
                else None,
                user_args=user_args if browser_key == first_browser_key else None,
                existing_links_in_category=existing_links_in_category,
            )
            result_links.extend(browser_links)
            logger.info(
                "_prepare_profile_links: для браузера %s создано ссылок: %s",
                browser_key,
                len(browser_links),
            )

        logger.info(
            "_prepare_profile_links: всего создано ссылок: %s",
            len(result_links),
        )
        return result_links

    def _get_user_args_if_modified(
        self,
        form_data: dict[str, Any],
        existing_link: dict,
        selected_profiles: list[dict],
        browser_key: str,
    ) -> Optional[str]:
        """
        Determines if user manually changed arguments.

        Args:
            form_data: Form data
            existing_link: Existing link (for editing)
            selected_profiles: Selected profiles
            browser_key: Browser key

        Returns:
            str: User arguments if they differ from auto-generated ones
            None: If arguments unchanged or this is a new link
        """
        current_args = form_data.get("args", "").strip()

        # For new links: if user entered arguments, use them
        if not existing_link:
            return current_args if current_args else None

        # For editing: compare with auto-generated arguments
        try:
            manager = self.profile_manager
            finder = manager.finders.get(browser_key)

            if not finder or not selected_profiles:
                return current_args if current_args else None

            # Generate expected arguments for first selected profile
            first_profile = selected_profiles[0]
            expected_args = finder.get_profile_argument(first_profile)

            # Compare current arguments with expected ones
            if current_args != expected_args:
                # IMPORTANT: consider that user overrode arguments
                # only if they are NOT empty. Empty ones should not suppress auto-generation.
                return current_args if current_args else None

            return None

        except Exception:
            # In case of error return user arguments if they exist
            return current_args if current_args else None

    def _prepare_regular_link(self, form_data: dict[str, Any]) -> dict[str, Any]:
        """Prepares regular link."""
        from app.utils.links.link_factory import make_link_record

        record = make_link_record(
            name=form_data["name"],
            url=form_data["url"],
            link_type=form_data["link_type"],
            icon_name=form_data.get("icon_name", ""),
            notes=form_data.get("notes", ""),
            last_used=form_data.get("last_used"),
            position=form_data.get("position", 0),
            category_id=form_data["category_id"],
            args=form_data.get("args", ""),
            is_favorite=int(form_data.get("is_favorite", False)),
            link_id=form_data.get("link_id"),
        )
        if form_data.get("_reparse_icon"):
            record["_reparse_icon"] = True
        return record

    def get_result_data(self) -> list[dict[str, Any]]:
        """Returns resulting data after saving."""
        logger.debug(
            "get_result_data: returning %s links",
            len(self.result_data) if self.result_data else 0,
        )
        if self.result_data:
            for i, link in enumerate(self.result_data):
                logger.debug(
                    "get_result_data: link %s: name=%s, browser_key=%s",
                    i,
                    link.get("name"),
                    link.get("browser_key"),
                )
        return self.result_data
