"""
Firefox Profile Finder - search for Mozilla Firefox profiles.
"""

import configparser
import logging
import re
from pathlib import Path
from typing import Optional

from .base_profile_finder import BaseBrowserProfileFinder

logger = logging.getLogger(__name__)


class FirefoxProfileFinder(BaseBrowserProfileFinder):
    """Finder for Mozilla Firefox profiles."""

    def __init__(self):
        from app.config_data import app_config

        dir_path = app_config.paths.get_browser_profiles_dir("firefox")
        self.profiles_dir = str(dir_path) if dir_path else ""
        self.browser_name = "Mozilla Firefox"

    def find_profiles(self) -> list[dict[str, str]]:
        """Finds Firefox profiles from profiles.ini."""
        profiles = []
        profiles_ini = Path(self.profiles_dir) / "profiles.ini"

        if not profiles_ini.exists():
            logger.debug("profiles.ini file not found: %s", profiles_ini)
            return profiles

        try:
            config = configparser.ConfigParser()
            config.read(profiles_ini, encoding="utf-8")

            for section_name in config.sections():
                if section_name.startswith("Profile"):
                    section = config[section_name]
                    name = section.get("Name", "Default")
                    path = section.get("Path", "")
                    is_relative = section.getboolean("IsRelative", True)

                    if is_relative:
                        full_path = Path(self.profiles_dir) / path
                    else:
                        full_path = Path(path)

                    if full_path.exists():
                        # Attempt to get additional information from prefs.js
                        email = self._extract_email_from_prefs(str(full_path))

                        profiles.append(
                            {
                                "name": name,
                                "email": email or name,
                                "path": full_path,
                                "directory": path,
                                "args": f'-P "{name}"',
                            }
                        )
                        logger.debug(
                            "Found Firefox profile: %s (%s)",
                            name,
                            (email or "no email"),
                        )
        except Exception as e:
            logger.error("Error reading Firefox profiles: %s", e)

        logger.info("Found %s Firefox profiles", len(profiles))
        return profiles

    def _extract_email_from_prefs(self, profile_path: str) -> Optional[str]:
        """Extracts email from Firefox profile prefs.js."""
        prefs_file = Path(profile_path) / "prefs.js"
        if not prefs_file.exists():
            return None

        try:
            with open(prefs_file, encoding="utf-8") as f:
                content = f.read()

                # Search for mail or sync settings
                email_patterns = [
                    r'user_pref\("services\.sync\.username",\s*"([^"]+)"\)',
                    r'user_pref\("mail\.identity\.default\.useremail",\s*"([^"]+)"\)',
                    r'user_pref\("identity\.fxaccounts\.account\.device\.name",\s*"([^"]+)"\)',
                ]

                for pattern in email_patterns:
                    match = re.search(pattern, content)
                    if match:
                        email = match.group(1)
                        # Check that it looks like an email
                        if "@" in email and "." in email:
                            return email
        except Exception as e:
            logger.debug("Failed to extract email from %s: %s", prefs_file, e)

        return None

    def get_browser_name(self) -> str:
        """Returns readable browser name.
        NOTE: Intentional duplication with other profile finders for API consistency
        and local readability. Moving to common helper is not worthwhile.
        """
        return self.browser_name

    def get_profile_argument(self, profile_data: dict) -> str:
        """Generates command line argument for profile."""
        profile_name = profile_data.get("name", "default")
        return f'-P "{profile_name}"'

    def parse_profile_from_args(self, args: str) -> Optional[dict]:
        """Parses Firefox profile from command line arguments."""
        logger.debug("parse_profile_from_args: args=%s", args)

        if not args or "-P " not in args:
            logger.debug("parse_profile_from_args: no -P in args")
            return None

        try:
            # Extract profile name from -P "ProfileName"
            match = re.search(r'-P\s+"([^"]+)"', args)
            if match:
                profile_name = match.group(1)
                logger.debug(
                    "parse_profile_from_args: found profile_name=%s", profile_name
                )
                result = {
                    "name": profile_name,
                    "email": f"{profile_name} (Firefox)",
                    "args": args,
                    "directory": profile_name,
                    "path": None,  # Path is determined dynamically from profiles.ini
                }
                logger.debug("parse_profile_from_args: returning result=%s", result)
                return result
        except Exception as e:
            logger.debug("Error parsing Firefox arguments: %s", e)

        logger.debug("parse_profile_from_args: could not parse profile")
        return None
