# app/controllers/link_dialog_controller.py

import logging
from typing import Any, Dict, List, Optional

from app.controllers.business.links_business import LinksBusinessLogic
from app.models.db import Database
from app.utils.browser.browser_profiles import get_profile_manager

logger = logging.getLogger(__name__)


class LinkDialogController:
    """Controller for managing link dialog business logic."""

    def __init__(self, database: Database):
        self.database = database
        self.links_business = LinksBusinessLogic(database)
        self.result_data: List[Dict[str, Any]] = []
        # Unified profile manager via factory — exclude repeated profile scans
        self.profile_manager = get_profile_manager()

    def get_initialization_data(
        self, category_id: Optional[int] = None, link: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Gets data for dialog initialization."""
        # Get spheres
        spheres = self.database.spheres.get_spheres()

        # Determine category hierarchy
        category_hierarchy = None
        if category_id:
            category_hierarchy = self._get_category_hierarchy(category_id)
        elif link and link.get("category_id"):
            category_hierarchy = self._get_category_hierarchy(link["category_id"])

        # Get Chrome profiles
        chrome_profiles = self._get_chrome_profiles()

        # Migrate old Chrome profiles to universal format
        if link and link.get("args", "").startswith("--profile-directory"):
            from app.utils.browser.browser_profiles import UniversalProfileProcessor

            processor = UniversalProfileProcessor(self.database)
            browser_key, profiles = processor.parse_existing_profile(link)
            if browser_key and profiles:
                # Добавляем browser_key в каждый профиль для совместимости
                for profile in profiles:
                    profile["browser_key"] = browser_key
                    if "browser_name" not in profile:
                        from app.utils.browser.browser_profiles.utils import (
                            get_browser_display_name,
                        )

                        finder = self.profile_manager.finders.get(browser_key)
                        if finder:
                            profile["browser_name"] = get_browser_display_name(
                                finder, browser_key
                            )
                link["migrated_profiles"] = profiles

        return {
            "spheres": spheres,
            "category_hierarchy": category_hierarchy,
            "chrome_profiles": chrome_profiles,
            "selected_category_id": category_id,
            "form_data": link,
        }

    def _get_category_hierarchy(self, category_id: int) -> Optional[Dict[str, int]]:
        """Gets hierarchy for category (sphere -> section -> category)."""
        return self.database.categories.get_category_hierarchy(category_id)

    def _get_chrome_profiles(self) -> List[Dict[str, Any]]:
        """Gets list of Chrome profiles."""
        try:
            return self.profile_manager.get_browser_profiles("chrome")
        except Exception:
            return []

    def get_sections_for_sphere(self, sphere_id: int) -> List[Dict[str, Any]]:
        """Gets sections for sphere."""
        return self.database.sections.get_sections(sphere_id)

    def get_categories_for_section(self, section_id: int) -> List[Dict[str, Any]]:
        """Gets categories for section."""
        return self.database.categories.get_categories(section_id)

    def validate_and_save(self, form_data: Dict[str, Any]) -> Dict[str, Any]:
        """Validates form data and prepares for saving."""
        # Basic validation
        validation_result = self._validate_form_data(form_data)
        if not validation_result["is_valid"]:
            return validation_result

        # Prepare data for saving
        self.result_data = self._prepare_links_data(form_data)

        return {"is_valid": True, "errors": []}

    def _validate_form_data(self, form_data: Dict[str, Any]) -> Dict[str, Any]:
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
            import os

            if not os.path.exists(url):
                errors.append("Указанный путь не существует.")

        return {"is_valid": len(errors) == 0, "errors": errors}

    def _prepare_links_data(self, form_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Prepares link data for saving."""
        links_data = []

        # Edit mode: if web and profiles are set —
        # uses profile processing (will update current and add missing);
        # otherwise — one record
        is_edit = form_data.get("link_id") is not None
        if is_edit:
            if form_data.get("link_type") == "web" and form_data.get(
                "selected_profiles"
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

    def _prepare_profile_links(self, form_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Prepares links with profiles of any browsers."""
        from app.utils.browser.browser_profiles import (
            UniversalProfileProcessor,
        )

        processor = UniversalProfileProcessor(self.database)
        is_edit = form_data.get("link_id") is not None
        existing_link = None
        if is_edit:
            # Pass all necessary fields for proper profile comparison
            existing_link = {
                "id": form_data["link_id"],
                "args": form_data.get(
                    "args", ""
                ),  # Ключевое поле для сравнения профилей
                "last_used": form_data.get("last_used"),
                "position": form_data.get("position", 0),
            }

        # Process selected profiles
        selected_profiles = form_data["selected_profiles"]
        if not selected_profiles:
            return []

        # Separate profiles by browsers (use unified manager per controller)
        manager = self.profile_manager
        profiles_by_browser = {}

        for profile in selected_profiles:
            # Determine browser_key for each profile
            browser_key = profile.get("browser_key")
            if not browser_key:
                # Fallback 1: attempt by args
                browser_key = manager.detect_browser_from_args(profile.get("args", ""))
                if not browser_key:
                    # Fallback 2: iterate through finders and validate profile
                    for key, finder in manager.finders.items():
                        try:
                            if hasattr(
                                finder, "validate_profile_data"
                            ) and finder.validate_profile_data(profile):
                                browser_key = key
                                break
                        except Exception:
                            continue
                if not browser_key:
                    logger.debug(
                        f"_prepare_profile_links: пропущен профиль без определённого браузера: {profile}"
                    )
                    continue  # Пропускаем профиль, если не можем определить браузер

            # Group profiles by browser_key
            if browser_key not in profiles_by_browser:
                profiles_by_browser[browser_key] = []
            profiles_by_browser[browser_key].append(profile)

        # Log profile information for debugging
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

        if not profiles_by_browser:
            return []

        # Process profiles for each browser separately
        result_links = []

        # For editing determine current browser_key from existing link
        current_browser_key = None
        if existing_link and existing_link.get("args"):
            current_browser_key = manager.detect_browser_from_args(
                existing_link.get("args", "")
            )

        # Determine if user manually changed arguments (for first browser)
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
        form_data: Dict[str, Any],
        existing_link: Dict,
        selected_profiles: List[Dict],
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

    def _prepare_regular_link(self, form_data: Dict[str, Any]) -> Dict[str, Any]:
        """Prepares regular link."""
        from app.utils.links.link_factory import make_link_record

        return make_link_record(
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

    def get_result_data(self) -> List[Dict[str, Any]]:
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
