"""Service for icon file operations (copying, validation, path management).

Separates file system logic from UI layer for better testability.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Optional

from app.config_data import app_config
from .validation import is_valid_icon_file

logger = logging.getLogger(__name__)


class IconFileService:
    """Service for managing icon file operations."""

    def __init__(self, user_icons_dir: Optional[Path] = None):
        """Initialize service.
        
        Args:
            user_icons_dir: Directory for user icons. If None, uses app_config.
        """
        self._user_icons_dir = user_icons_dir

    def get_user_icons_dir(self) -> Path:
        """Get user icons directory."""
        if self._user_icons_dir is None:
            self._user_icons_dir = app_config.paths.get_link_icons_dir()
        return self._user_icons_dir

    def copy_icon_to_user_dir(
        self,
        source_path: Path | str,
        target_dir: Optional[Path] = None,
    ) -> Path:
        """Copy icon file to user icons directory with automatic renaming if needed.
        
        Args:
            source_path: Source icon file path.
            target_dir: Target directory. If None, uses user_icons_dir.
            
        Returns:
            Path to copied file.
            
        Raises:
            FileNotFoundError: If source file doesn't exist.
            ValueError: If source file is not a valid icon.
            OSError: If copy operation fails.
        """
        src = Path(source_path)
        
        # Validate source
        if not src.exists():
            raise FileNotFoundError(f"Source icon file not found: {src}")
        
        if not src.is_file():
            raise ValueError(f"Source path is not a file: {src}")
        
        if not is_valid_icon_file(src):
            raise ValueError(f"Source file is not a valid icon: {src}")
        
        # Prepare target directory
        if target_dir is None:
            target_dir = self.get_user_icons_dir()
        
        target_dir.mkdir(parents=True, exist_ok=True)
        
        # Find unique filename
        dst = target_dir / src.name
        counter = 1
        while dst.exists():
            dst = target_dir / f"{src.stem}_{counter}{src.suffix}"
            counter += 1
        
        # Copy file
        try:
            shutil.copy2(src, dst)
            logger.info("Copied icon from %s to %s", src, dst)
            return dst
        except (OSError, PermissionError) as e:
            logger.error("Failed to copy icon from %s to %s: %s", src, dst, e)
            raise

    def get_supported_formats_filter(self) -> str:
        """Get file filter string for supported icon formats.
        
        Returns:
            Filter string suitable for QFileDialog (e.g., "Images (*.png *.svg *.jpg)")
        """
        exts = list(app_config.get_supported_icon_formats())
        patterns = [f"*{ext if ext.startswith('.') else '.' + ext}" for ext in exts]
        return "Images (" + " ".join(patterns) + ")"

    def validate_icon_file(self, path: Path | str) -> bool:
        """Validate if file is a valid icon.
        
        Args:
            path: Path to icon file.
            
        Returns:
            True if valid icon file.
        """
        try:
            return is_valid_icon_file(Path(path))
        except Exception as e:
            logger.debug("Icon validation failed for %s: %s", path, e)
            return False
