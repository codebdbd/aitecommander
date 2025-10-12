"""Utilities for validating user input in dialogs.

Provides functions to verify data correctness before
 processing.                                        """

import re
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from PyQt6.QtCore import QCoreApplication

_TR_CONTEXT = "Validators"

def _tr(text: str) -> str:
    return QCoreApplication.translate(_TR_CONTEXT, text)

def validate_url(url: str) -> tuple[bool, Optional[str]]:
    """Validate a URL string.

    Args:
        url: URL string to validate

    Returns:
        tuple[bool, Optional[str]]: (is_valid, error_message)
    """
    if not url:
        return False, _tr("URL cannot be empty")

    try:
        result = urlparse(url.strip())
        if not result.netloc:
            return False, _tr("Invalid URL format")
        return True, None
    except Exception:
        return False, _tr("Invalid URL format")


def validate_file_path(path: str, must_exist: bool = False) -> tuple[bool, Optional[str]]:
    """Validate a file path.

    Args:
        path: File path to validate
        must_exist: Whether the file must exist

    Returns:
        tuple[bool, Optional[str]]: (is_valid, error_message)
    """
    if not path:
        return False, _tr("Path cannot be empty")

    try:
        path_obj = Path(path.strip())
        if must_exist and not path_obj.exists():
            return False, _tr("File does not exist")
        if must_exist and not path_obj.is_file():
            return False, _tr("Path is not a file")
        return True, None
    except Exception:
        return False, _tr("Invalid file path")


def validate_folder_path(path: str, must_exist: bool = False) -> tuple[bool, Optional[str]]:
    """Validate a folder path.

    Args:
        path: Folder path to validate
        must_exist: Whether the folder must exist

    Returns:
        tuple[bool, Optional[str]]: (is_valid, error_message)
    """
    if not path:
        return False, _tr("Path cannot be empty")

    try:
        path_obj = Path(path.strip())
        if must_exist and not path_obj.exists():
            return False, _tr("Folder does not exist")
        if must_exist and not path_obj.is_dir():
            return False, _tr("Path is not a folder")
        return True, None
    except Exception:
        return False, _tr("Invalid folder path")


def validate_name(name: str, min_length: int = 1, max_length: int = 255) -> tuple[bool, Optional[str]]:
    """Validate a name (category, section, link).

    Args:
        name: Name to validate
        min_length: Minimum length
        max_length: Maximum length

    Returns:
        tuple[bool, Optional[str]]: (is_valid, error_message)
    """
    if not name:
        return False, _tr("Name cannot be empty")

    name = name.strip()
    if len(name) < min_length:
        return False, _tr(f"Name must be at least {min_length} characters long")
    if len(name) > max_length:
        return False, _tr(f"Name cannot be longer than {max_length} characters")

    return True, None


def validate_icon_path(path: str, supported_formats: Optional[list] = None) -> tuple[bool, Optional[str]]:
    """Validate an icon path.

    Args:
        path: Icon path to validate
        supported_formats: List of supported formats

    Returns:
        tuple[bool, Optional[str]]: (is_valid, error_message)
    """
    if not path:
        return False, _tr("Icon path cannot be empty")

    try:
        path_obj = Path(path.strip())
        if not path_obj.exists():
            return False, _tr("Icon file does not exist")
        if not path_obj.is_file():
            return False, _tr("Icon path is not a file")

        if supported_formats:
            suffix = path_obj.suffix.lower()
            if suffix not in supported_formats:
                return False, _tr(f"Unsupported icon format. Supported: {', '.join(supported_formats)}")

        return True, None
    except Exception:
        return False, _tr("Invalid icon path")


def validate_email(email: str) -> tuple[bool, Optional[str]]:
    """Validate an email address.

    Args:
        email: Email address to validate

    Returns:
        tuple[bool, Optional[str]]: (is_valid, error_message)
    """
    if not email:
        return False, _tr("Email cannot be empty")

    email = email.strip()
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'

    if not re.match(email_pattern, email):
        return False, _tr("Invalid email format")

    return True, None


def validate_port(port: str) -> tuple[bool, Optional[str]]:
    """Validate a TCP/UDP port number.

    Args:
        port: Port number as string

    Returns:
        tuple[bool, Optional[str]]: (is_valid, error_message)
    """
    if not port:
        return False, _tr("Port cannot be empty")

    try:
        port_num = int(port.strip())

        if port_num < 1 or port_num > 65535:
            return False, _tr("Port must be in range 1-65535")
        return True, None

    except ValueError:
        return False, _tr("Port must be a number")


def sanitize_filename(filename: str) -> str:
    """Sanitize a filename by removing invalid characters.

    Args:
        filename: Original filename

    Returns:
        str: Sanitized filename

    Example:
        >>> sanitize_filename("file:name?.txt")
        'file_name_.txt'
    """
    # Replace invalid characters with underscore
    invalid_chars = r'[<>:"|?*/\\]'
    cleaned = re.sub(invalid_chars, '_', filename)

    # Collapse multiple underscores
    cleaned = re.sub(r'_+', '_', cleaned)

    # Trim underscores at both ends
    cleaned = cleaned.strip('_')

    return cleaned if cleaned else "unnamed"
