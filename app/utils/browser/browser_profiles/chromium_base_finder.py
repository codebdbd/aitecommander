"""
Base class for all Chromium-based browsers (Chrome, Edge, Brave, Vivaldi, etc.).
"""

import json
import logging
import os
from pathlib import Path
from typing import Optional

from .base_profile_finder import BaseBrowserProfileFinder

logger = logging.getLogger(__name__)


def detect_chrome_profiles_dir():
    """Returns path to Chrome profiles for current OS or None if not found."""
    candidates = []
    if os.name == "nt":
        candidates.append(os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\User Data"))
    elif os.name == "posix" and os.uname().sysname == "Darwin":
        candidates.append(
            os.path.expanduser("~/Library/Application Support/Google/Chrome")
        )
    elif os.name == "posix" and os.uname().sysname == "Linux":
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
            for entry in os.listdir(self.profiles_dir):
                profile_path = str(Path(self.profiles_dir) / entry)
                if Path(profile_path).is_dir() and (
                    entry.startswith("Profile") or entry == "Default"
                ):
                    email = self._extract_email_from_preferences(profile_path)
                    if email:
                        profiles.append(
                            {
                                "email": email,
                                "name": entry,
                                "directory": entry,
                                "path": profile_path,
                                "args": f'--profile-directory="{entry}"',
                            }
                        )
                        logger.debug(
                            "Found profile %s: %s (%s)",
                            self.browser_name,
                            email,
                            entry,
                        )
        except Exception as e:
            logger.error("Error searching profiles %s: %s", self.browser_name, e)

        logger.info("Found %s profiles %s", len(profiles), self.browser_name)
        return profiles

    def _extract_email_from_preferences(self, profile_path: str) -> Optional[str]:
        """Extracts email from Preferences file."""
        pref_path = str(Path(profile_path) / "Preferences")
        if not Path(pref_path).exists():
            return None

        try:
            with open(pref_path, encoding="utf-8") as f:
                prefs = json.load(f)

            # Try different places where email might be
            email = None

            # Main places to search for email
            account_info = prefs.get("account_info", [])
            if (
                account_info
                and isinstance(account_info, list)
                and len(account_info) > 0
            ):
                email = account_info[0].get("email")

            if not email:
                gaia_info = prefs.get("gaia_info", {})
                email = gaia_info.get("email")

            if not email:
                profile_info = prefs.get("profile", {}).get("info_cache", {})
                if profile_info:
                    # info_cache may contain multiple profiles
                    for _profile_id, profile_data in profile_info.items():
                        if isinstance(profile_data, dict) and profile_data.get(
                            "user_name"
                        ):
                            email = profile_data["user_name"]
                            break

            return email
        except Exception as e:
            logger.debug("Failed to extract email from %s: %s", pref_path, e)
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
                    "email": f"{directory} ({self.browser_name})",
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
