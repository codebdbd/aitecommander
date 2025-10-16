"""
Enhanced module for opening various types of links

Supports:
- Web links (including opening in different Chrome profiles)
- Files and folders
- Scripts (.ps1, .py, .bat, .cmd)
- Programs
- Chrome apps

Chrome profile usage examples:
- args: "--profile-directory=Profile 1"
- args: "--profile-directory=Default"
- args: "--incognito"
- args: "--new-window --profile-directory=Work"
"""

import logging
import os
import platform
from pathlib import Path
import re
import shlex
import subprocess
import webbrowser
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class LinkType(Enum):
    """Link types for handling"""

    WEB = "web"
    FILE = "file"
    FOLDER = "folder"
    SCRIPT = "script"
    PROGRAM = "program"
    CHROMEAPP = "chromeapp"


@dataclass
class LinkInfo:
    """Structure for storing link information"""

    id: Optional[int]
    link_type: LinkType
    path: str
    args: str = ""
    category_id: Optional[int] = None
    browser_key: Optional[str] = None

    @classmethod
    def from_dict(cls, link_dict: Dict[str, Any]) -> "LinkInfo":
        """Creates LinkInfo object from dictionary"""
        logger.debug("Creating LinkInfo from dict")

        # Safe link type conversion
        link_type_str = link_dict.get("type", "web")

        try:
            link_type = LinkType(link_type_str)
        except ValueError:
            # Backward compatibility
            type_mapping = {
                "url": LinkType.WEB,
                "app": LinkType.PROGRAM,
            }
            link_type = type_mapping.get(link_type_str, LinkType.WEB)

        # Extract browser_key: first from field, then from args
        browser_key_from_field = link_dict.get("browser_key")
        browser_key_from_args = cls._extract_browser_key_from_args(
            link_dict.get("args", "")
        )
        browser_key = browser_key_from_field or browser_key_from_args

        return cls(
            id=link_dict.get("id"),
            link_type=link_type,
            path=link_dict.get("url") or link_dict.get("path", ""),
            args=link_dict.get("args", ""),
            category_id=link_dict.get("category_id"),
            browser_key=browser_key,
        )

    @staticmethod
    def _extract_browser_key_from_args(args: str) -> Optional[str]:
        """Extracts browser_key from arguments for backward compatibility"""
        if not args:
            return None

        # Simple detection by Chrome arguments
        if "--profile-directory" in args or "--incognito" in args:
            return "chrome"

        return None


class SecurityValidator:
    """Enhanced security validation"""

    # More strict patterns for different argument types
    CHROME_ARG_PATTERN = re.compile(r'^--[\w-]+(=[\w\s\-_./:\\"]+)?$')
    PATH_PATTERN = re.compile(r"^[a-zA-Z]:[\\\/][\w\s\-_./\\:()]+$|^[\w\s\-_./()]+$")
    URL_PATTERN = re.compile(r'^https?://[^\s<>"{}|\\^`\[\]]+$')

    # Whitelist of allowed Chrome arguments
    ALLOWED_CHROME_ARGS = {
        "--profile-directory",
        "--incognito",
        "--new-window",
        "--app",
        "--disable-web-security",
        "--user-data-dir",
        "--window-size",
        "--window-position",
        "--start-maximized",
        "--start-fullscreen",
    }

    # Blacklist of dangerous characters (removed '&' to support valid URLs)
    DANGEROUS_CHARS = {"|", ";", "\u003e", "\u003c", "`", "$", "(", ")", "{", "}"}

    @classmethod
    def sanitize_url(cls, url: str) -> str:
        """Returns cleaned URL.

        - Removes "view-source:" prefix if valid scheme follows (http/https/chrome/chrome-extension).
        """
        if not url:
            return url
        try:
            s = url.strip()
            low = s.lower()
            prefix = "view-source:"
            if low.startswith(prefix):
                candidate = s[len(prefix) :].lstrip()
                low_cand = candidate.lower()
                if low_cand.startswith(
                    ("http://", "https://", "chrome://", "chrome-extension://")
                ):
                    return candidate
            return s
        except Exception:
            return url

    @classmethod
    def is_safe_url(cls, url: str) -> bool:
        """Checks URL safety"""
        if not url:
            return False

        # Check for dangerous characters
        if any(char in url for char in cls.DANGEROUS_CHARS):
            return False

        # Check URL pattern match
        return bool(cls.URL_PATTERN.match(url))

    @classmethod
    def is_safe_path(cls, path: str) -> bool:
        """Checks file path safety"""
        if not path:
            return False

        # Check for dangerous characters (except allowed for paths)
        dangerous_for_paths = cls.DANGEROUS_CHARS - {"(", ")"}
        if any(char in path for char in dangerous_for_paths):
            return False

        # For Windows paths check basic security requirements
        # Allow regular program paths
        if platform.system() == "Windows":
            # Check if this looks like Windows path
            if len(path) >= 3 and path[1:3] == ":\\":
                return True
            if len(path) >= 3 and path[1:3] == ":/":
                return True

        # Check path pattern match
        return bool(cls.PATH_PATTERN.match(path))

    @classmethod
    def validate_chrome_args(cls, args: str) -> List[str]:
        """Validates Chrome arguments"""
        if not args:
            return []

        try:
            parsed = shlex.split(args)
        except ValueError:
            logger.warning("Failed to parse arguments: %s", args)
            return []

        validated = []
        has_incognito = False
        has_new_window = False

        for arg in parsed:
            # Check argument format
            if not cls.CHROME_ARG_PATTERN.match(arg):
                logger.warning("Invalid argument format: %s", arg)
                continue

            # Extract argument name
            arg_name = arg.split("=")[0]

            # Check whitelist
            if arg_name in cls.ALLOWED_CHROME_ARGS:
                validated.append(arg)
                if arg_name == "--incognito":
                    has_incognito = True
                elif arg_name == "--new-window":
                    has_new_window = True
            else:
                logger.warning("Argument not in whitelist: %s", arg_name)

        # If --incognito but no --new-window, add --new-window for forced new window creation
        if has_incognito and not has_new_window:
            validated.insert(
                0, "--new-window"
            )  # Add to beginning for correct order

        return validated

    @classmethod
    def validate_args(cls, args: str) -> List[str]:
        """Universal argument validation (for backward compatibility)"""
        if not args:
            return []

        try:
            return shlex.split(args)
        except ValueError:
            logger.warning("Failed to parse arguments: %s", args)
            return []


class BrowserConfig:
    """Browser configuration"""

    def __init__(self):
        from app.config_data import app_config

        self._config = app_config.get_browser_config()
        self._cache = {}

    def get_browser_command(
        self, browser_key: str, url: str, args: List[str]
    ) -> List[str]:
        """Gets browser launch command"""
        if browser_key not in self._config:
            browser_key = "chrome"  # Fallback

        config = self._config[browser_key]
        executable = config["executable"]
        template = config["command_template"]

        # Replace placeholders
        command = []
        for part in template:
            if part == "{executable}":
                command.append(executable)
            elif part == "{url}":
                command.append(url)
            else:
                command.append(part)

        # Add arguments
        command.extend(args)

        return command


class LinkHandler(ABC):
    """Base class for link handlers"""

    def __init__(self, logger: logging.Logger):
        self.logger = logger

    @abstractmethod
    def can_handle(self, link_info: LinkInfo) -> bool:
        """Checks if handler can work with this link type"""
        pass

    @abstractmethod
    def open(self, link_info: LinkInfo) -> None:
        """Opens link"""
        pass


class WebLinkHandler(LinkHandler):
    """Web link handler"""

    def __init__(self, logger: logging.Logger, browser_config: BrowserConfig):
        super().__init__(logger)
        self.browser_config = browser_config

    def can_handle(self, link_info: LinkInfo) -> bool:
        return link_info.link_type == LinkType.WEB

    def open(self, link_info: LinkInfo) -> None:
        """Opens web link"""
        # Clean and validate URL
        sanitized = SecurityValidator.sanitize_url(link_info.path)
        link_info.path = sanitized
        if not SecurityValidator.is_safe_url(link_info.path):
            raise ValueError(f"Unsafe URL: {link_info.path}")

        # Determine browser
        browser_key = (
            link_info.browser_key
            or self._extract_browser_key(link_info.args)
            or "chrome"
        )

        # Validate arguments
        validated_args = SecurityValidator.validate_chrome_args(link_info.args)

        # Create command
        command = self.browser_config.get_browser_command(
            browser_key, link_info.path, validated_args
        )

        try:
            # Use shell=False for security
            subprocess.Popen(command, shell=False)
            self.logger.info(
                "Successfully opened URL %s with %s", link_info.path, browser_key
            )
        except Exception as e:
            self.logger.error("Failed to open URL with %s: %s", browser_key, e)
            # Fallback to system browser
            webbrowser.open(link_info.path)

    def _extract_browser_key(self, args: str) -> Optional[str]:
        """Extracts browser_key from arguments"""
        if not args:
            return None

        if "--profile-directory" in args or "--incognito" in args:
            return "chrome"

        return None


class FileLinkHandler(LinkHandler):
    """File and folder handler"""

    def can_handle(self, link_info: LinkInfo) -> bool:
        return link_info.link_type in (LinkType.FILE, LinkType.FOLDER)

    def open(self, link_info: LinkInfo) -> None:
        """Opens file or folder"""
        # Path validation
        if not SecurityValidator.is_safe_path(link_info.path):
            raise ValueError(f"Unsafe path: {link_info.path}")

        if not Path(link_info.path).exists():
            raise FileNotFoundError(f"File or folder not found: {link_info.path}")

        try:
            if platform.system() == "Windows":
                os.startfile(link_info.path)
            else:
                subprocess.Popen(["xdg-open", link_info.path])

            self.logger.info("Successfully opened: %s", link_info.path)
        except OSError as e:
            self.logger.error("Failed to open %s: %s", link_info.path, e)
            raise


class ScriptLinkHandler(LinkHandler):
    """Script handler"""

    def __init__(self, logger: logging.Logger, powershell_path: str = None):
        super().__init__(logger)
        self.powershell_path = powershell_path or self._get_powershell_path()

    def _get_powershell_path(self) -> str:
        """Gets PowerShell path"""
        try:
            from app.config_data import app_config

            return app_config.get_powershell_path()
        except ImportError:
            return "powershell.exe"

    def can_handle(self, link_info: LinkInfo) -> bool:
        return link_info.link_type == LinkType.SCRIPT

    def open(self, link_info: LinkInfo) -> None:
        """Opens script"""
        if not SecurityValidator.is_safe_path(link_info.path):
            raise ValueError(f"Unsafe script path: {link_info.path}")

        if not Path(link_info.path).exists():
            raise FileNotFoundError(f"Script not found: {link_info.path}")

        path = Path(link_info.path)
        ext = path.suffix.lower()
        arg_list = SecurityValidator.validate_args(link_info.args)

        script_handlers = {
            ".ps1": self._create_powershell_command,
            ".py": self._create_python_command,
            ".bat": self._create_batch_command,
            ".cmd": self._create_batch_command,
        }

        handler = script_handlers.get(ext)
        if handler:
            cmd = handler(link_info.path, arg_list)
            flags = 0 if ext in (".bat", ".cmd") else subprocess.CREATE_NEW_CONSOLE
            subprocess.Popen(cmd, creationflags=flags)
        else:
            # For unknown extensions use system handler
            if platform.system() == "Windows":
                os.startfile(link_info.path)
            else:
                subprocess.Popen(["xdg-open", link_info.path])

    def _create_powershell_command(self, path: str, args: List[str]) -> List[str]:
        """Creates PowerShell script command"""
        cmd_args = ["-ExecutionPolicy", "Bypass", "-Command", f'& "{path}"']
        if args:
            cmd_args.extend(args)
        return [self.powershell_path] + cmd_args

    def _create_python_command(self, path: str, args: List[str]) -> List[str]:
        """Creates Python script command"""
        return ["python", path] + args

    def _create_batch_command(self, path: str, args: List[str]) -> List[str]:
        """Creates batch file command"""
        return ["cmd.exe", "/c", "start", '""', path] + args


class ProgramLinkHandler(LinkHandler):
    """Program handler"""

    def can_handle(self, link_info: LinkInfo) -> bool:
        return link_info.link_type == LinkType.PROGRAM

    def open(self, link_info: LinkInfo) -> None:
        """Opens program"""
        if not SecurityValidator.is_safe_path(link_info.path):
            raise ValueError(f"Unsafe program path: {link_info.path}")

        if not Path(link_info.path).exists():
            raise FileNotFoundError(f"Program not found: {link_info.path}")

        try:
            # For programs use simple argument splitting without strict Chrome validation
            arg_list = []
            if link_info.args:
                try:
                    arg_list = shlex.split(link_info.args)
                except ValueError:
                    self.logger.warning(
                        "Failed to parse program arguments: %s", link_info.args
                    )
                    arg_list = []

            subprocess.Popen([link_info.path] + arg_list)
            self.logger.info(
                "Successfully launched program: %s with args: %s",
                link_info.path,
                arg_list,
            )
        except (OSError, subprocess.SubprocessError) as e:
            self.logger.error("Failed to launch program %s: %s", link_info.path, e)
            raise


class ChromeAppLinkHandler(LinkHandler):
    """Chrome app handler"""

    def can_handle(self, link_info: LinkInfo) -> bool:
        return link_info.link_type == LinkType.CHROMEAPP

    def open(self, link_info: LinkInfo) -> None:
        """Opens Chrome app"""
        try:
            webbrowser.open(link_info.path)
            self.logger.info("Successfully opened Chrome app: %s", link_info.path)
        except Exception as e:
            self.logger.error("Failed to open Chrome app %s: %s", link_info.path, e)
            raise


class LinkOpener:
    """Main class for opening various types of links"""

    def __init__(
        self, powershell_path: str = None, logger_obj: Optional[logging.Logger] = None
    ):
        # Use module logger by default with DI support
        self.logger = (
            logger_obj or globals().get("logger") or logging.getLogger(__name__)
        )
        self.browser_config = BrowserConfig()

        # Initialize handlers
        self.handlers: List[LinkHandler] = [
            WebLinkHandler(self.logger, self.browser_config),
            FileLinkHandler(self.logger),
            ScriptLinkHandler(self.logger, powershell_path),
            ProgramLinkHandler(self.logger),
            ChromeAppLinkHandler(self.logger),
        ]

    def _build_chrome_command(self, url: str, args: List[str]) -> List[str]:
        """Creates Chrome launch command (for backward compatibility)"""
        return self.browser_config.get_browser_command("chrome", url, args)

    def _build_browser_command(
        self, browser_key: str, url: str, args: List[str]
    ) -> List[str]:
        """Creates browser launch command (for backward compatibility)"""
        return self.browser_config.get_browser_command(browser_key, url, args)

    def _open_web_link(self, link_info: LinkInfo) -> None:
        """Opens web link (for backward compatibility)"""
        handler = WebLinkHandler(self.logger, self.browser_config)
        handler.open(link_info)

    def _open_file_or_folder(self, link_info: LinkInfo) -> None:
        """Opens file or folder (for backward compatibility)"""
        handler = FileLinkHandler(self.logger)
        handler.open(link_info)

    def _open_script(self, link_info: LinkInfo) -> None:
        """Opens script (for backward compatibility)"""
        handler = ScriptLinkHandler(self.logger)
        handler.open(link_info)

    def _open_program(self, link_info: LinkInfo) -> None:
        """Opens program (for backward compatibility)"""
        handler = ProgramLinkHandler(self.logger)
        handler.open(link_info)

    def _open_chrome_app(self, link_info: LinkInfo) -> None:
        """Opens Chrome app (for backward compatibility)"""
        handler = ChromeAppLinkHandler(self.logger)
        handler.open(link_info)

    def open_link(self, link_info) -> None:
        """Opens link based on its type"""
        # Input validation
        if not link_info:
            raise ValueError("LinkInfo cannot be None")

        # Convert dictionary to LinkInfo if needed
        if isinstance(link_info, dict):
            link_info = LinkInfo.from_dict(link_info)
        elif not isinstance(link_info, LinkInfo):
            raise ValueError(f"Unsupported link_info type: {type(link_info)}")

        if not link_info.path or not link_info.path.strip():
            raise ValueError("Link path cannot be empty")

        if not isinstance(link_info.link_type, LinkType):
            raise ValueError(f"Incorrect link type: {link_info.link_type}")

        self.logger.debug(
            "Opening link: %s - %s", link_info.link_type.value, link_info.path
        )

        # Find suitable handler
        for handler in self.handlers:
            if handler.can_handle(link_info):
                try:
                    handler.open(link_info)
                    return
                except Exception as e:
                    self.logger.error(
                        "Handler %s failed: %s", handler.__class__.__name__, e
                    )
                    raise

        # If handler not found
        raise ValueError(f"Unsupported link type: {link_info.link_type}")


# Утилитарные функции для удобства использования (обратная совместимость)
def create_link_opener(powershell_path: str = None) -> LinkOpener:
    """Creates LinkOpener instance with default settings."""
    return LinkOpener(powershell_path)


def open_link_from_dict(link_dict: Dict[str, Any], powershell_path: str = None) -> None:
    """
    Opens link from dictionary data.

    Args:
        link_dict: Dictionary with link data
        powershell_path: PowerShell path (optional)
    """
    link_info = LinkInfo.from_dict(link_dict)
    opener = LinkOpener(powershell_path)
    opener.open_link(link_info)


# get_value импортируется из app.utils.common


def validate_link_path(path: str, link_type: LinkType) -> bool:
    """
    Validates link path based on its type.

    Args:
        path: Link path
        link_type: Link type

    Returns:
        True if path is valid, False otherwise
    """
    if not path or not path.strip():
        return False

    if link_type == LinkType.WEB:
        # Remove view-source: prefix then validate
        path = SecurityValidator.sanitize_url(path)
        return SecurityValidator.is_safe_url(path) or "." in path
    elif link_type in (
        LinkType.FILE,
        LinkType.FOLDER,
        LinkType.SCRIPT,
        LinkType.PROGRAM,
    ):
        return SecurityValidator.is_safe_path(path) and Path(path).exists()
    elif link_type == LinkType.CHROMEAPP:
        return path.startswith(
            ("chrome://", "chrome-extension://", "http://", "https://")
        )

    return True


def get_link_type_from_path(path: str) -> LinkType:
    """
    Determines link type by its path.

    Args:
        path: Link path

    Returns:
        Assumed link type
    """
    if not path:
        return LinkType.WEB

    # Clean special prefixes like view-source:
    path = SecurityValidator.sanitize_url(path)
    path_lower = path.lower()

    # Web links
    if path_lower.startswith(("http://", "https://", "ftp://")):
        return LinkType.WEB

    # Chrome apps
    if path_lower.startswith(("chrome://", "chrome-extension://")):
        return LinkType.CHROMEAPP

    # File paths
    if Path(path).exists():
        if Path(path).is_dir():
            return LinkType.FOLDER
        elif Path(path).is_file():
            ext = Path(path).suffix.lower()
            if ext in (".ps1", ".py", ".bat", ".cmd", ".sh"):
                return LinkType.SCRIPT
            elif ext in (".exe", ".msi", ".app"):
                return LinkType.PROGRAM
            else:
                return LinkType.FILE

    # Default to web link
    return LinkType.WEB
