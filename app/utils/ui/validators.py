"""Utilities for validating user input in dialogs.

Provides functions to verify data correctness before processing.
"""

import re
from pathlib import Path
from typing import Optional, Tuple
from PyQt6.QtCore import QCoreApplication
from urllib.parse import urlparse


_TR_CONTEXT = "Validators"

def _tr(text: str) -> str:
    return QCoreApplication.translate(_TR_CONTEXT, text)


def validate_url(url: str) -> Tuple[bool, Optional[str]]:
    """Validate a URL string.

    Args:
        url: URL to validate

    Returns:
        Tuple[bool, Optional[str]]: (is_valid, error_message)

    Example:
        >>> valid, error = validate_url("https://example.com")
        >>> if not valid:
        ...     print(error)
    """
    if not url or not url.strip():
        return False, _tr("URL cannot be empty")
    
    url = url.strip()
    
    try:
        result = urlparse(url)
        
        # Ensure scheme and netloc are present
        if not all([result.scheme, result.netloc]):
            return False, _tr("URL must contain a protocol (http://, https://) and a domain")
        
        # Check supported schemes
        if result.scheme not in ("http", "https", "ftp", "file"):
            return False, _tr("Unsupported protocol: %1").replace("%1", str(result.scheme))
        
        return True, None
        
    except ValueError as e:
        return False, _tr("Invalid URL: %1").replace("%1", str(e))


def validate_file_path(path: str, must_exist: bool = False) -> Tuple[bool, Optional[str]]:
    """Validate a file path.

    Args:
        path: File path
        must_exist: If True, the file must exist

    Returns:
        Tuple[bool, Optional[str]]: (is_valid, error_message)
    """
    if not path or not path.strip():
        return False, _tr("Path cannot be empty")
    
    path = path.strip()
    
    try:
        path_obj = Path(path)
        
        # Check existence if required
        if must_exist and not path_obj.exists():
            return False, _tr("File not found: %1").replace("%1", path)
        
        # Ensure it's a file, not a directory
        if must_exist and path_obj.is_dir():
            return False, _tr("A folder path is provided instead of a file path")
        
        return True, None
        
    except (ValueError, OSError) as e:
        return False, _tr("Invalid path: %1").replace("%1", str(e))


def validate_folder_path(path: str, must_exist: bool = False) -> Tuple[bool, Optional[str]]:
    """Validate a folder path.

    Args:
        path: Folder path
        must_exist: If True, the folder must exist

    Returns:
        Tuple[bool, Optional[str]]: (is_valid, error_message)
    """
    if not path or not path.strip():
        return False, _tr("Path cannot be empty")
    
    path = path.strip()
    
    try:
        path_obj = Path(path)
        
        # Check existence if required
        if must_exist and not path_obj.exists():
            return False, _tr("Folder not found: %1").replace("%1", path)
        
        # Ensure it's a directory
        if must_exist and not path_obj.is_dir():
            return False, _tr("A file path is provided instead of a folder path")
        
        return True, None
        
    except (ValueError, OSError) as e:
        return False, _tr("Invalid path: %1").replace("%1", str(e))


def validate_name(name: str, min_length: int = 1, max_length: int = 255) -> Tuple[bool, Optional[str]]:
    """Validate a name (category, section, link).

    Args:
        name: Name to validate
        min_length: Minimum length
        max_length: Maximum length

    Returns:
        Tuple[bool, Optional[str]]: (is_valid, error_message)
    """
    if not name or not name.strip():
        return False, _tr("Name cannot be empty")
    
    name = name.strip()
    
    if len(name) < min_length:
        return False, _tr("Name is too short (minimum %1 characters)").replace("%1", str(min_length))
    
    if len(name) > max_length:
        return False, _tr("Name is too long (maximum %1 characters)").replace("%1", str(max_length))
    
    # Check for invalid filename characters (optional)
    invalid_chars = r'[<>:"|?*]'
    if re.search(invalid_chars, name):
        return False, _tr("Name contains invalid characters: < > : \" | ? *")
    
    return True, None


def validate_icon_path(path: str, supported_formats: Optional[list] = None) -> Tuple[bool, Optional[str]]:
    """Validate an icon path.

    Args:
        path: Icon path
        supported_formats: Supported extensions (e.g., ['.ico', '.png'])

    Returns:
        Tuple[bool, Optional[str]]: (is_valid, error_message)
    """
    if not path or not path.strip():
        # Empty path is allowed (default icon will be used)
        return True, None
    
    path = path.strip()
    
    # Check file existence
    valid, error = validate_file_path(path, must_exist=True)
    if not valid:
        return False, error
    
    # Check extension
    if supported_formats:
        path_obj = Path(path)
        if path_obj.suffix.lower() not in supported_formats:
            formats_str = ", ".join(supported_formats)
            return False, _tr("Unsupported icon format. Supported: %1").replace("%1", formats_str)
    
    return True, None


def validate_email(email: str) -> Tuple[bool, Optional[str]]:
    """Validate an email address.

    Args:
        email: Email to validate

    Returns:
        Tuple[bool, Optional[str]]: (is_valid, error_message)
    """
    if not email or not email.strip():
        return False, _tr("Email cannot be empty")
    
    email = email.strip()
    
    # Simple regex email check
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    
    if not re.match(email_pattern, email):
        return False, _tr("Invalid email format")
    
    return True, None


def validate_port(port: str) -> Tuple[bool, Optional[str]]:
    """Validate a TCP/UDP port number.

    Args:
        port: Port to validate (string)

    Returns:
        Tuple[bool, Optional[str]]: (is_valid, error_message)
    """
    if not port or not port.strip():
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
