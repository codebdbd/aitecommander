"""Base interface for browser profile finding."""

import logging
from abc import ABC, abstractmethod
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class BaseBrowserProfileFinder(ABC):
    """Base class for browser profile finding."""

    @abstractmethod
    def find_profiles(self) -> List[Dict[str, str]]:
        """Finds browser profiles."""
        pass

    @abstractmethod
    def get_browser_name(self) -> str:
        """Returns readable browser name."""
        pass

    @abstractmethod
    def get_profile_argument(self, profile_data: Dict) -> str:
        """Generates command line argument for profile."""
        pass

    @abstractmethod
    def parse_profile_from_args(self, args: str) -> Optional[Dict]:
        """Parses profile from command line arguments."""
        pass

    def validate_profile_data(self, profile_data: Dict) -> bool:
        """Validates profile data."""
        required_keys = ["args"]
        return all(key in profile_data for key in required_keys)

    def format_profile_display_name(self, profile_data: Dict) -> str:
        """Formats profile name for display in UI."""
        return profile_data.get("email") or profile_data.get("name") or "Profile"

    def get_browser_key(self) -> str:
        """Returns browser key for internal use."""
        return self.get_browser_name().lower().replace(" ", "_")
