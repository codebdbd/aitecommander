"""
Base class for all Chromium-based browsers (Chrome, Edge, Brave, Vivaldi, etc.).
"""

import json
import logging
import os
import platform
from pathlib import Path
from typing import Optional

from .base_profile_finder import BaseBrowserProfileFinder

logger = logging.getLogger(__name__)


def detect_chrome_profiles_dir():
    """Returns path to Chrome profiles for current OS or None if not found."""
    candidates = []
    if os.name == "nt":
        candidates.append(os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\User Data"))
    elif os.name == "posix":
        system = platform.system()
        if system == "Darwin":
            candidates.append(
                os.path.expanduser("~/Library/Application Support/Google/Chrome")
            )
        elif system == "Linux":
            candidates.append(os.path.expanduser("~/.config/google-chrome"))
            candidates.append(os.path.expanduser("~/.config/chromium"))
    for path in candidates:
        if Path(path).exists():
            return path
    return None


class ChromiumBaseBrowserFinder(BaseBrowserProfileFinder):
    """Base class for all Chromium-based browsers."""

    def __init__(self, profiles_dir: str, browser_name: str):
        """
        Initialization of finder for Chromium-based browser.

        Args:
            profiles_dir: Path to browser profiles folder
            browser_name: Readable browser name
        """
        self.profiles_dir = profiles_dir
        self.browser_name = browser_name

    def find_profiles(self) -> list[dict[str, str]]:
        """Universal profile search logic for Chromium-based browsers."""
        profiles: list[dict[str, str]] = []

        if not Path(self.profiles_dir).exists():
            logger.debug(
                "Profiles folder %s not found: %s",
                self.browser_name,
                self.profiles_dir,
            )
            return profiles

        logger.debug("find_profiles: profiles_dir=%s", self.profiles_dir)

        try:
            local_state_names = self._read_local_state_profile_names()
            for entry in os.listdir(self.profiles_dir):
                profile_path = str(Path(self.profiles_dir) / entry)
                if Path(profile_path).is_dir() and (
                    entry.startswith("Profile") or entry == "Default"
                ):
                    email, display_name = self._extract_profile_info_from_preferences(
                        profile_path, entry
                    )
                    if entry in local_state_names:
                        display_name = local_state_names.get(entry) or display_name
                    if email or display_name:
                        profiles.append(
                            {
                                "email": email,
                                "name": display_name or entry,
                                "directory": entry,
                                "path": profile_path,
                                "args": f'--profile-directory="{entry}"',
                            }
                        )
                        logger.debug(
                            "Found profile %s: %s (%s)",
                            self.browser_name,
                            display_name or email,
                            entry,
                        )
        except Exception as e:
            logger.error("Error searching profiles %s: %s", self.browser_name, e)

        logger.info("Found %s profiles %s", len(profiles), self.browser_name)
        return profiles

    def _read_local_state_profile_names(self) -> dict[str, str]:
        """Reads profile display names from Local State info_cache."""
        local_state_path = str(Path(self.profiles_dir) / "Local State")
        if not Path(local_state_path).exists():
            return {}
        try:
            with open(local_state_path, encoding="utf-8") as f:
                data = json.load(f)
            info_cache = data.get("profile", {}).get("info_cache", {})
            if isinstance(info_cache, dict):
                names: dict[str, str] = {}
                for key, val in info_cache.items():
                    if not isinstance(val, dict):
                        continue
                    name = (
                        val.get("name")
                        or val.get("gaia_name")
                        or val.get("gaia_given_name")
                        or val.get("shortcut_name")
                    )
                    user_name = val.get("user_name")
                    if isinstance(name, str) and name:
                        if name.startswith("Profile ") or name == "Default":
                            name = user_name or name
                    elif isinstance(user_name, str) and user_name:
                        name = user_name
                    if isinstance(name, str) and name:
                        names[key] = name
                return names
        except Exception:
            logger.debug(
                "Failed to read Local State profile names from %s",
                local_state_path,
                exc_info=True,
            )
        return {}

    def _extract_profile_info_from_preferences(
        self, profile_path: str, profile_dir: str
    ) -> tuple[Optional[str], Optional[str]]:
        """Extract profile display name and email from Preferences file.

        The method orchestrates small helpers to keep complexity low.
        """
        pref_path = str(Path(profile_path) / "Preferences")
        if not Path(pref_path).exists():
            return None, None

        try:
            prefs = self._read_prefs_json(pref_path)
            if prefs is None:
                return None, None

            email, display_name = self._extract_from_account_info(prefs)
            if not email:
                email2, name2 = self._extract_from_gaia_info(prefs)
                email = email or email2
                display_name = display_name or name2

            name3, email3 = self._extract_from_profile_info_cache(prefs, profile_dir)
            display_name = display_name or name3
            email = email or email3

            if not email:
                email = self._fallback_email_from_profile_info_cache(prefs)

            return email, display_name
        except Exception as e:
            logger.debug("Failed to extract email from %s: %s", pref_path, e)
            return None, None

    # --- Helpers to reduce complexity of _extract_profile_info_from_preferences() ---
    def _read_prefs_json(self, pref_path: str) -> dict | None:
        """Read Preferences JSON file safely."""
        try:
            with open(pref_path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def _extract_from_account_info(self, prefs: dict) -> tuple[Optional[str], Optional[str]]:
        """Try extracting email and display name from account_info section."""
        try:
            account_info = prefs.get("account_info", [])
            if account_info and isinstance(account_info, list) and len(account_info) > 0:
                email = account_info[0].get("email")
                display_name = (
                    account_info[0].get("full_name")
                    or account_info[0].get("given_name")
                )
                return email, display_name
        except Exception:
            pass
        return None, None

    def _extract_from_gaia_info(self, prefs: dict) -> tuple[Optional[str], Optional[str]]:
        """Try extracting email and display name from gaia_info section."""
        try:
            gaia_info = prefs.get("gaia_info", {})
            if isinstance(gaia_info, dict):
                email = gaia_info.get("email")
                display_name = gaia_info.get("full_name") or gaia_info.get("given_name")
                return email, display_name
        except Exception:
            pass
        return None, None

    def _extract_from_profile_info_cache(
        self, prefs: dict, profile_dir: str
    ) -> tuple[Optional[str], Optional[str]]:
        """Extract display name and email from profile.info_cache for specific directory."""
        try:
            profile_info = prefs.get("profile", {}).get("info_cache", {})
            if not profile_info:
                return None, None
            profile_data = profile_info.get(profile_dir)
            if not isinstance(profile_data, dict):
                for _profile_id, candidate in profile_info.items():
                    if isinstance(candidate, dict) and candidate.get("directory") == profile_dir:
                        profile_data = candidate
                        break
            if isinstance(profile_data, dict):
                display_name = (
                    profile_data.get("name")
                    or profile_data.get("gaia_name")
                    or profile_data.get("gaia_given_name")
                    or profile_data.get("short_name")
                    or profile_data.get("shortcut_name")
                )
                email = profile_data.get("user_name") if profile_data.get("user_name") else None
                return display_name, email
        except Exception:
            pass
        return None, None

    def _fallback_email_from_profile_info_cache(self, prefs: dict) -> Optional[str]:
        """Fallback: scan info_cache for any user_name if direct match failed."""
        try:
            profile_info = prefs.get("profile", {}).get("info_cache", {})
            if profile_info:
                for _profile_id, pdata in profile_info.items():
                    if isinstance(pdata, dict) and pdata.get("user_name"):
                        return pdata["user_name"]
        except Exception:
            pass
        return None

    def get_browser_name(self) -> str:
        """Returns readable browser name.
        NOTE: Intentional duplication with other profile finders for API consistency
        and local readability. Moving to common helper is not worthwhile.
        """
        return self.browser_name

    def get_profile_argument(self, profile_data: dict) -> str:
        """Generates command line argument for profile."""
        directory = profile_data.get("directory", profile_data.get("name", "Default"))
        return f'--profile-directory="{directory}"'

    def parse_profile_from_args(self, args: str) -> Optional[dict]:
        """Parses profile from command line arguments."""
        logger.debug("parse_profile_from_args: args=%s", args)

        if not args or "--profile-directory" not in args:
            logger.debug("parse_profile_from_args: no --profile-directory in args")
            return None

        try:
            import re

            match = re.search(r'--profile-directory="([^"]+)"', args)
            if match:
                directory = match.group(1)
                logger.debug("parse_profile_from_args: found directory=%s", directory)
                result = {
                    "directory": directory,
                    "name": directory,
                    "email": None,
                    "args": args,
                    "path": str(Path(self.profiles_dir) / directory)
                    if self.profiles_dir
                    else None,
                }
                logger.debug("parse_profile_from_args: returning result=%s", result)
                return result
        except Exception as e:
            logger.debug("Error parsing arguments %s: %s", self.browser_name, e)

        logger.debug("parse_profile_from_args: could not parse profile")
        return None


# Concrete implementations for each browser
class EdgeProfileFinder(ChromiumBaseBrowserFinder):
    """Finder for Microsoft Edge profiles."""

    def __init__(self):
        from app.config_data import app_config

        dir_path = app_config.paths.get_browser_profiles_dir("edge")
        super().__init__(str(dir_path) if dir_path else "", "Microsoft Edge")


class BraveProfileFinder(ChromiumBaseBrowserFinder):
    """Finder for Brave Browser profiles."""

    def __init__(self):
        from app.config_data import app_config

        dir_path = app_config.paths.get_browser_profiles_dir("brave")
        super().__init__(str(dir_path) if dir_path else "", "Brave")


class VivaldiProfileFinder(ChromiumBaseBrowserFinder):
    """Finder for Vivaldi Browser profiles."""

    def __init__(self):
        from app.config_data import app_config

        dir_path = app_config.paths.get_browser_profiles_dir("vivaldi")
        super().__init__(str(dir_path) if dir_path else "", "Vivaldi")


class OperaProfileFinder(ChromiumBaseBrowserFinder):
    """Finder for Opera Browser profiles."""

    def __init__(self):
        from app.config_data import app_config

        dir_path = app_config.paths.get_browser_profiles_dir("opera")
        super().__init__(str(dir_path) if dir_path else "", "Opera")


class YandexProfileFinder(ChromiumBaseBrowserFinder):
    """Finder for Yandex Browser profiles."""

    def __init__(self):
        from app.config_data import app_config

        dir_path = app_config.paths.get_browser_profiles_dir("yandex")
        super().__init__(str(dir_path) if dir_path else "", "Yandex Browser")


class ChromeProfileFinder(ChromiumBaseBrowserFinder):
    """Finder for Google Chrome profiles."""

    def __init__(self):
        from app.config_data import app_config

        dir_path = app_config.paths.get_browser_profiles_dir("chrome")
        super().__init__(str(dir_path) if dir_path else "", "Google Chrome")
