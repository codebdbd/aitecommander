"""
Enhanced module for opening various types of links

Supports:
- Web links (including opening in different Chrome profiles)
- Files and folders
- Scripts (.ps1, .py, .bat, .cmd)
- Programs

Chrome profile usage examples:
- args: "--profile-directory=Profile 1"
- args: "--profile-directory=Default"
- args: "--incognito"
- args: "--new-window --profile-directory=Work"
"""

import logging
import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
import webbrowser
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlsplit, urlunsplit

logger = logging.getLogger(__name__)


def sanitize_url_for_logging(url: str) -> str:
    """Strip query parameters, fragments, and credentials from URLs for safe logging."""
    if not isinstance(url, str) or not url:
        return ""
    try:
        is_windows_path = len(url) > 2 and url[1] == ":" and url[2] in ("/", "\\")
        is_posix_path = url.startswith("/") and not url.startswith("//")
        is_unc_path = url.startswith("\\\\")
        if (is_windows_path or is_posix_path or is_unc_path) and ("?" not in url and "#" not in url):
            return url

        has_scheme = "://" in url
        has_query_or_frag = "?" in url or "#" in url
        has_userinfo = "@" in url and not (is_windows_path or is_posix_path or is_unc_path)

        dummy_prefix = False
        target = url
        if not has_scheme and (has_query_or_frag or has_userinfo or url.startswith("//")):
            target = "//" + url
            dummy_prefix = True

        parsed = urlsplit(target)
        if not parsed.scheme and not parsed.netloc and not dummy_prefix:
            return url

        netloc = parsed.hostname or ""
        if parsed.port:
            netloc = f"{netloc}:{parsed.port}"
        elif not netloc and parsed.netloc and "@" in parsed.netloc:
            netloc = parsed.netloc.split("@")[-1]
        elif not netloc and not dummy_prefix:
            netloc = parsed.netloc

        scheme = "" if dummy_prefix else parsed.scheme
        base = urlunsplit((scheme, netloc, parsed.path, "", ""))
        if dummy_prefix and base.startswith("//"):
            base = base[2:]
        if parsed.query:
            return f"{base}?"
        return base
    except Exception:
        return "<redacted-url>"


sanitize_url_for_log = sanitize_url_for_logging


def sanitize_link_dict_for_log(link_dict: dict[str, Any]) -> dict[str, Any]:
    """Return a shallow copy of a link dictionary with credentials, query params, args and notes redacted."""
    if not isinstance(link_dict, dict):
        return {}
    res = dict(link_dict)
    if "url" in res and isinstance(res["url"], str):
        res["url"] = sanitize_url_for_logging(res["url"])
    if "path" in res and isinstance(res["path"], str):
        link_type = str(res.get("type", "")).lower()
        if link_type in ("web", "") or "://" in res["path"]:
            res["path"] = sanitize_url_for_logging(res["path"])
    if "args" in res and res["args"]:
        res["args"] = "<redacted>"
    if "notes" in res and res["notes"]:
        res["notes"] = "<redacted>"
    return res


class LinkType(Enum):
    """Link types for handling"""

    WEB = "web"
    FILE = "file"
    FOLDER = "folder"
    SCRIPT = "script"
    PROGRAM = "program"


@dataclass
class LinkInfo:
    """Structure for storing link information"""

    id: Optional[int]
    link_type: LinkType
    path: str
    args: str = ""
    category_id: Optional[int] = None
    browser_key: Optional[str] = None
    chrome_rotation: bool = False
    rotation_index: int = 0
    rotation_profiles: Optional[str] = None

    def __repr__(self) -> str:
        safe_path = (
            sanitize_url_for_logging(self.path)
            if self.link_type == LinkType.WEB
            else self.path
        )
        safe_args = "<redacted>" if self.args else ""
        return (
            f"LinkInfo(id={self.id}, link_type={self.link_type}, path={safe_path!r}, "
            f"args={safe_args!r}, category_id={self.category_id}, browser_key={self.browser_key!r}, "
            f"chrome_rotation={self.chrome_rotation!r}, rotation_index={self.rotation_index!r})"
        )

    @classmethod
    def from_dict(cls, link_dict: dict[str, Any]) -> "LinkInfo":
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
            chrome_rotation=bool(link_dict.get("chrome_rotation", False)),
            rotation_index=int(link_dict.get("rotation_index", 0) or 0),
            rotation_profiles=link_dict.get("rotation_profiles"),
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
    CHROME_ARG_PATTERN = re.compile(r'^--[\w-]+(=[\w\s\-_./:\\"{}?&=]+)?$')
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
        "--guest",
    }

    # Blacklist of dangerous characters for shell commands and system paths
    DANGEROUS_CHARS = {"|", ";", ">", "<", "`", "$", "{", "}"}

    # Characters considered dangerous specifically in URLs (control characters, unencoded injection tokens).
    # RFC 3986 sub-delimiters such as '(', ')', '$', ';', '&' are explicitly allowed (e.g. Wikipedia links).
    DANGEROUS_URL_CHARS = {"\r", "\n", "\0", "<", ">", '"', "`", "|", "{", "}"}

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
        """Checks URL safety (RFC 3986 compliant, allows parentheses, e.g. Wikipedia)."""
        if not url:
            return False

        # Check for dangerous characters in URLs
        if any(char in url for char in cls.DANGEROUS_URL_CHARS):
            return False

        # Check URL pattern match
        return bool(cls.URL_PATTERN.match(url))

    @classmethod
    def is_safe_path(cls, path: str) -> bool:
        """Checks file path safety"""
        if not path:
            return False

        if platform.system() == "Windows" and path.lower().startswith("shell:appsfolder\\"):
            forbidden = {"|", ";", ">", "<", "`", "$", "\r", "\n", "\0", "&"}
            return not any(char in path for char in forbidden)

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
    def sanitize_cmd_arg(cls, arg: str) -> str:
        """Sanitizes argument for safe execution in Windows cmd.exe /c start.

        Prevents shell command injection, argument breakout, and newline injection
        by stripping newlines, escaping quotes, and escaping shell metacharacters (&, |, <, >, ^, %).
        """
        if not arg:
            return ""
        clean = arg.replace("\r", "").replace("\n", "")
        clean = clean.replace('"', '\\"')
        return re.sub(r'([&|<>\^%])', r'^\1', clean)

    @classmethod
    def split_cmdline(cls, cmdline: str) -> list[str]:
        """Parse command-line arguments using native Windows conventions or POSIX.

        On Windows, preserves backslashes (e.g. C:\\path\\to\\file) and follows
        MSDN Command-Line Parsing rules via CommandLineToArgvW.
        Raises ValueError if quotation marks are unclosed.
        """
        if not cmdline or not cmdline.strip():
            return []

        if platform.system() == "Windows":
            if cmdline.count('"') % 2 != 0:
                raise ValueError(f"Unclosed quotation mark in arguments: {cmdline}")

            try:
                import ctypes
                from ctypes import wintypes

                shell32 = ctypes.windll.shell32
                kernel32 = ctypes.windll.kernel32
                CommandLineToArgvW = shell32.CommandLineToArgvW
                CommandLineToArgvW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_int)]
                CommandLineToArgvW.restype = ctypes.POINTER(wintypes.LPWSTR)

                num_args = ctypes.c_int()
                ptr = CommandLineToArgvW("dummy.exe " + cmdline, ctypes.byref(num_args))
                if not ptr:
                    raise ValueError(f"Failed to parse arguments: {cmdline}")
                try:
                    return [ptr[i] for i in range(1, num_args.value)]
                finally:
                    kernel32.LocalFree(ptr)
            except Exception as e:
                if isinstance(e, ValueError):
                    raise
                # Fallback to posix=False shlex if win32 API fails
                return [t.strip('"') for t in shlex.split(cmdline, posix=False)]
        else:
            return shlex.split(cmdline)

    @classmethod
    def validate_chrome_args(cls, args: str) -> list[str]:
        """Validates Chrome arguments"""
        if not args:
            return []

        try:
            parsed = cls.split_cmdline(args)
        except ValueError:
            logger.warning("Failed to parse arguments: %s", args)
            return []

        validated = []
        needs_new_window = False
        has_new_window = False
        new_window_triggers = {"--incognito", "--guest"}

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
                if arg_name in new_window_triggers:
                    needs_new_window = True
                if arg_name == "--new-window":
                    has_new_window = True
            else:
                logger.warning("Argument not in whitelist: %s", arg_name)

        # If --incognito, --guest, or --start-fullscreen but no --new-window, add --new-window for forced new window creation
        if needs_new_window and not has_new_window:
            validated.insert(0, "--new-window")  # Add to beginning for correct order

        return validated

    @classmethod
    def validate_firefox_args(cls, args: str) -> list[str]:
        """Validates and translates arguments for Firefox."""
        if not args:
            return []

        try:
            parsed = cls.split_cmdline(args)
        except ValueError:
            logger.warning("Failed to parse arguments: %s", args)
            return []

        validated = []
        i = 0
        while i < len(parsed):
            arg = parsed[i]
            # Chrome to Firefox translation
            if arg.startswith("--"):
                arg_name = arg.split("=")[0]
                if arg_name == "--incognito":
                    validated.append("-private-window")
                elif arg_name == "--new-window":
                    validated.append("-new-window")
                elif arg_name == "--app":
                    validated.append("-kiosk")
            # Firefox native profile flag handling
            elif arg == "-P" and i + 1 < len(parsed):
                validated.extend(["-P", parsed[i+1]])
                i += 1
            # Firefox native flags
            elif arg in ["-private-window", "-new-window"]:
                validated.append(arg)
            else:
                logger.warning("Argument not in Firefox whitelist or not translatable: %s", arg)
            i += 1

        return validated

    @classmethod
    def validate_args(cls, args: str) -> list[str]:
        """Universal argument validation (preserves Windows paths/backslashes)."""
        if not args:
            return []

        return cls.split_cmdline(args)


class BrowserConfig:
    """Browser configuration"""

    def __init__(self):
        from app.config_data import app_config

        self._config = app_config.get_browser_config()
        self._cache = {}

    def get_browser_command(
        self, browser_key: str, url: str, args: list[str]
    ) -> list[str]:
        """Gets browser launch command"""
        if browser_key not in self._config:
            browser_key = "chrome"  # Fallback

        config = self._config[browser_key]
        executable = config["executable"]
        resolved_executable = self._resolve_executable(browser_key, executable)
        template = config["command_template"]

        # Process {url} placeholder in arguments
        processed_args = [arg.replace("{url}", url) for arg in args]
        has_app_arg = any(arg.startswith("--app=") for arg in processed_args)

        # On Windows avoid `cmd /c start ...` wrapper because it can silently
        # fail when browser executable is not on PATH (prints to console only).
        # Direct browser launch also gives deterministic argument ordering.
        if platform.system() == "Windows":
            # If the URL was already passed via --app=URL, don't pass it again at the end
            if has_app_arg:
                return [resolved_executable, *processed_args]
            return [resolved_executable, *processed_args, url]

        # Replace placeholders for other platforms
        command = []
        for part in template:
            if part == "{executable}":
                command.append(resolved_executable)
            elif part == "{url}":
                # Only add URL here if it wasn't already consumed by --app
                if not has_app_arg:
                    command.append(url)
            else:
                command.append(part)

        # Add arguments
        command.extend(processed_args)

        return command

    def _resolve_executable(self, browser_key: str, executable: str) -> str:
        """Resolve browser executable path for current platform."""
        if platform.system() != "Windows":
            return executable

        # Fast path: full path from config.
        expanded = os.path.expandvars(executable)
        if os.path.isabs(expanded) and Path(expanded).exists():
            return expanded

        # PATH lookup first.
        resolved = shutil.which(executable)
        if resolved:
            return resolved

        # Common installation locations by browser key.
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        program_files = os.environ.get("PROGRAMFILES", r"C:\Program Files")
        program_files_x86 = os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")
        candidates = {
            "chrome": [
                os.path.join(program_files, "Google", "Chrome", "Application", "chrome.exe"),
                os.path.join(
                    program_files_x86, "Google", "Chrome", "Application", "chrome.exe"
                ),
                os.path.join(
                    local_app_data, "Google", "Chrome", "Application", "chrome.exe"
                ),
            ],
            "edge": [
                os.path.join(program_files, "Microsoft", "Edge", "Application", "msedge.exe"),
                os.path.join(
                    program_files_x86, "Microsoft", "Edge", "Application", "msedge.exe"
                ),
                os.path.join(
                    local_app_data, "Microsoft", "Edge", "Application", "msedge.exe"
                ),
            ],
            "brave": [
                os.path.join(
                    program_files, "BraveSoftware", "Brave-Browser", "Application", "brave.exe"
                ),
                os.path.join(
                    program_files_x86,
                    "BraveSoftware",
                    "Brave-Browser",
                    "Application",
                    "brave.exe",
                ),
                os.path.join(
                    local_app_data,
                    "BraveSoftware",
                    "Brave-Browser",
                    "Application",
                    "brave.exe",
                ),
            ],
            "vivaldi": [
                os.path.join(program_files, "Vivaldi", "Application", "vivaldi.exe"),
                os.path.join(program_files_x86, "Vivaldi", "Application", "vivaldi.exe"),
                os.path.join(local_app_data, "Vivaldi", "Application", "vivaldi.exe"),
            ],
            "opera": [
                os.path.join(local_app_data, "Programs", "Opera", "opera.exe"),
                os.path.join(program_files, "Opera", "launcher.exe"),
                os.path.join(program_files_x86, "Opera", "launcher.exe"),
            ],
            "yandex": [
                os.path.join(
                    local_app_data, "Yandex", "YandexBrowser", "Application", "browser.exe"
                ),
                os.path.join(
                    program_files, "Yandex", "YandexBrowser", "Application", "browser.exe"
                ),
                os.path.join(
                    program_files_x86, "Yandex", "YandexBrowser", "Application", "browser.exe"
                ),
            ],
            "firefox": [
                os.path.join(program_files, "Mozilla Firefox", "firefox.exe"),
                os.path.join(program_files_x86, "Mozilla Firefox", "firefox.exe"),
            ],
        }.get(browser_key, [])

        for candidate in candidates:
            if candidate and Path(candidate).exists():
                return candidate

        return executable


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
        if browser_key == "firefox":
            validated_args = SecurityValidator.validate_firefox_args(link_info.args)
        else:
            validated_args = SecurityValidator.validate_chrome_args(link_info.args)

        # Create command
        command = self.browser_config.get_browser_command(
            browser_key, link_info.path, validated_args
        )

        self.logger.debug("================================================")
        self.logger.debug("BROWSER LAUNCH DIAGNOSTICS:")
        self.logger.debug("Raw input args: '%s'", link_info.args)
        self.logger.debug("Validated args: %s", validated_args)
        self.logger.debug("Final exact command: %s", command)
        self.logger.debug("================================================")

        safe_url = sanitize_url_for_logging(link_info.path)

        try:
            # Use shell=False for security
            subprocess.Popen(command, shell=False)
            self.logger.info(
                "Successfully opened URL %s with %s", safe_url, browser_key
            )
        except FileNotFoundError as e:
            self.logger.warning(
                "Browser executable not found for '%s' (cmd='%s'). Falling back to system browser. Error: %s",
                browser_key,
                command[0] if command else "",
                e,
            )
            webbrowser.open(link_info.path)
        except Exception as e:
            self.logger.error("Failed to open URL %s with %s: %s", safe_url, browser_key, e)
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

    def __init__(
        self,
        logger: logging.Logger,
        powershell_path: Optional[str] = None,
        python_path: Optional[str] = None,
    ):
        super().__init__(logger)
        self.powershell_path = powershell_path or self._get_powershell_path()
        self.python_path = python_path or self._get_python_path()

    def _get_powershell_path(self) -> str:
        """Gets PowerShell path"""
        try:
            from app.config_data import app_config

            return app_config.get_powershell_path()
        except Exception:
            return "powershell.exe"

    def _get_python_path(self) -> Optional[str]:
        """Gets configured Python path, if any"""
        try:
            from app.config_data import app_config

            if hasattr(app_config, "get_python_path"):
                return app_config.get_python_path()
            val = app_config.get("ui.python_path")
            return str(val) if val else None
        except Exception:
            return None

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
        try:
            arg_list = SecurityValidator.validate_args(link_info.args)
        except ValueError as e:
            self.logger.error(
                "Failed to parse script arguments for '%s': %s", link_info.path, e
            )
            raise ValueError(f"Invalid script arguments: {e}") from e

        script_handlers = {
            ".ps1": self._create_powershell_command,
            ".py": self._create_python_command,
            ".pyw": self._create_python_command,
            ".bat": self._create_batch_command,
            ".cmd": self._create_batch_command,
        }

        handler = script_handlers.get(ext)
        if handler:
            cmd = handler(link_info.path, arg_list)
            if not cmd:
                # Command handled directly (e.g. via os.startfile fallback)
                return
            flags = 0 if ext in (".bat", ".cmd", ".pyw") else subprocess.CREATE_NEW_CONSOLE
            subprocess.Popen(cmd, creationflags=flags, cwd=str(path.parent.resolve()))
        else:
            # For unknown extensions use system handler
            if platform.system() == "Windows":
                os.startfile(link_info.path)
            else:
                subprocess.Popen(["xdg-open", link_info.path])

    def _create_powershell_command(self, path: str, args: list[str]) -> list[str]:
        """Creates PowerShell script command"""
        cmd_args = ["-ExecutionPolicy", "Bypass", "-File", path]
        if args:
            cmd_args.extend(args)
        return [self.powershell_path] + cmd_args

    def _resolve_python_executable(self, script_path: str) -> Optional[str]:
        """Resolves the best Python executable for the script automatically.

        Zero-config cascade resolution order:
        1. Explicitly configured path in settings (self.python_path).
        2. Local virtualenv near the script (.venv, venv, env, .env).
        3. Windows Python Launcher (py.exe).
        4. Current running Python interpreter (if running from source / virtualenv).
        5. System PATH python (python / python3), ignoring 0-byte WindowsApps stubs.
        """
        # 1. Configured path
        if self.python_path:
            p = Path(self.python_path)
            if p.is_file():
                self.logger.info("Using configured Python path: %s", self.python_path)
                return str(p)

        # 2. Local virtual environment near script
        try:
            script_file = Path(script_path).resolve()
            search_dirs = [script_file.parent, script_file.parent.parent]
            for parent_dir in search_dirs:
                if not parent_dir.is_dir():
                    continue
                for venv_name in (".venv", "venv", "env", ".env"):
                    venv_dir = parent_dir / venv_name
                    if not venv_dir.is_dir():
                        continue
                    if platform.system() == "Windows":
                        candidate = venv_dir / "Scripts" / "python.exe"
                    else:
                        candidate = venv_dir / "bin" / "python"
                    if candidate.is_file():
                        self.logger.info(
                            "Found local virtualenv Python for %s: %s", script_path, candidate
                        )
                        return str(candidate)
        except Exception as e:
            self.logger.debug("Error checking local virtualenv for %s: %s", script_path, e)

        # 3. Windows Python Launcher (py.exe)
        if platform.system() == "Windows":
            py_launcher = shutil.which("py")
            if not py_launcher:
                win_py = Path(os.environ.get("SystemRoot", "C:\\Windows")) / "py.exe"
                if win_py.is_file():
                    py_launcher = str(win_py)
            if py_launcher:
                self.logger.info("Using Windows Python Launcher (py.exe) for %s", script_path)
                return py_launcher

        # 4. Running Python interpreter (if running from source / virtualenv, not PyInstaller frozen)
        if not getattr(sys, "frozen", False) and sys.executable:
            exec_path = Path(sys.executable)
            if exec_path.is_file():
                return str(exec_path)

        # 5. System PATH python / python3
        for cmd_name in ("python", "python3"):
            found = shutil.which(cmd_name)
            if found:
                if platform.system() == "Windows" and "WindowsApps" in found:
                    try:
                        if Path(found).stat().st_size == 0:
                            continue
                    except OSError:
                        continue
                return found

        return None

    def _create_python_command(self, path: str, args: list[str]) -> list[str]:
        """Creates Python script command with zero-config cascade resolution."""
        python_exe = self._resolve_python_executable(path)
        if python_exe:
            return [python_exe, path] + args

        # Fallback: on Windows without extra arguments, let the shell open via file association
        if platform.system() == "Windows" and not args:
            try:
                self.logger.info("No Python executable found; launching via Windows shell: %s", path)
                os.startfile(path)
                return []
            except OSError as e:
                self.logger.warning("os.startfile failed for %s: %s", path, e)

        raise FileNotFoundError(
            f"Python interpreter not found to run '{path}'. "
            "Please install Python (https://www.python.org/) or configure python_path in settings."
        )

    def _create_batch_command(self, path: str, args: list[str]) -> list[str]:
        """Creates batch file command with sanitized arguments to prevent shell injection"""
        sanitized_args = [SecurityValidator.sanitize_cmd_arg(arg) for arg in args]
        return ["cmd.exe", "/c", "start", '""', path] + sanitized_args


class ProgramLinkHandler(LinkHandler):
    """Program handler"""

    def can_handle(self, link_info: LinkInfo) -> bool:
        val = getattr(link_info.link_type, "value", link_info.link_type)
        return val == "program" or link_info.link_type == LinkType.PROGRAM

    def open(self, link_info: LinkInfo) -> None:
        """Opens program"""
        if not SecurityValidator.is_safe_path(link_info.path):
            raise ValueError(f"Unsafe program path: {link_info.path}")

        # Windows AppsFolder virtual applications
        if platform.system() == "Windows" and link_info.path.lower().startswith("shell:appsfolder\\"):
            try:
                os.startfile(link_info.path)
                self.logger.info("Successfully launched shell app: %s", link_info.path)
                return
            except OSError as e:
                self.logger.error("Failed to launch shell app %s: %s", link_info.path, e)
                raise

        if not Path(link_info.path).exists():
            raise FileNotFoundError(f"Program not found: {link_info.path}")

        try:
            # Windows shortcuts must be launched via shell, not as executables.
            if platform.system() == "Windows" and link_info.path.lower().endswith(".lnk"):
                os.startfile(link_info.path)
                self.logger.info("Successfully launched shortcut: %s", link_info.path)
                return

            # For programs use Windows argument splitting without strict Chrome validation
            arg_list = []
            if link_info.args:
                try:
                    arg_list = SecurityValidator.split_cmdline(link_info.args)
                except ValueError as e:
                    self.logger.error(
                        "Failed to parse program arguments for '%s': %s", link_info.path, e
                    )
                    raise ValueError(f"Invalid program arguments: {e}") from e

            subprocess.Popen([link_info.path] + arg_list)
            self.logger.info(
                "Successfully launched program: %s",
                link_info.path,
            )
            self.logger.debug(
                "Program arguments for %s: %s",
                link_info.path,
                arg_list,
            )
        except (OSError, subprocess.SubprocessError) as e:
            self.logger.error("Failed to launch program %s: %s", link_info.path, e)
            raise


class LinkOpener:
    """Main class for opening various types of links"""

    def __init__(
        self,
        powershell_path: Optional[str] = None,
        logger_obj: Optional[logging.Logger] = None,
        python_path: Optional[str] = None,
    ):
        # Use module logger by default with DI support
        self.logger = (
            logger_obj or globals().get("logger") or logging.getLogger(__name__)
        )
        self.browser_config = BrowserConfig()

        # Initialize handlers
        self.handlers: list[LinkHandler] = [
            WebLinkHandler(self.logger, self.browser_config),
            FileLinkHandler(self.logger),
            ScriptLinkHandler(self.logger, powershell_path, python_path),
            ProgramLinkHandler(self.logger),
        ]

    def _build_chrome_command(self, url: str, args: list[str]) -> list[str]:
        """Creates Chrome launch command (for backward compatibility)"""
        return self.browser_config.get_browser_command("chrome", url, args)

    def _build_browser_command(
        self, browser_key: str, url: str, args: list[str]
    ) -> list[str]:
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
def create_link_opener(
    powershell_path: Optional[str] = None,
    python_path: Optional[str] = None,
) -> LinkOpener:
    """Creates LinkOpener instance with default settings."""
    return LinkOpener(powershell_path=powershell_path, python_path=python_path)


def open_link_from_dict(
    link_dict: dict[str, Any],
    powershell_path: Optional[str] = None,
    python_path: Optional[str] = None,
) -> None:
    """
    Opens link from dictionary data.

    Args:
        link_dict: Dictionary with link data
        powershell_path: PowerShell path (optional)
        python_path: Python path (optional)
    """
    link_info = LinkInfo.from_dict(link_dict)
    opener = LinkOpener(powershell_path=powershell_path, python_path=python_path)
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
