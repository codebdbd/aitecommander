"""Service for icon file operations (copying, validation, path management).

Separates file system logic from UI layer for better testability.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from app.config_data import app_config

from .validation import is_valid_icon_file

logger = logging.getLogger(__name__)


class IconFileService:
    """Service for managing icon file operations."""

    def __init__(self, user_icons_dir: Path | None = None):
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
        target_dir: Path | None = None,
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
        
        # For .ico files, normalize to safe PNG to avoid problematic native shell handlers.
        if src.suffix.lower() == ".ico":
            safe_dst = self._convert_ico_to_safe_png(src, target_dir)
            if safe_dst is not None:
                logger.info("Converted ICO to safe PNG: %s -> %s", src, safe_dst)
                return safe_dst

        # Find unique filename
        dst = self._unique_path(target_dir, src.stem, src.suffix)
        
        # Copy file
        try:
            shutil.copy2(src, dst)
            logger.info("Copied icon from %s to %s", src, dst)
            return dst
        except (OSError, PermissionError) as e:
            logger.error("Failed to copy icon from %s to %s: %s", src, dst, e)
            raise

    @staticmethod
    def _unique_path(target_dir: Path, stem: str, suffix: str) -> Path:
        dst = target_dir / f"{stem}{suffix}"
        counter = 1
        while dst.exists():
            dst = target_dir / f"{stem}_{counter}{suffix}"
            counter += 1
        return dst

    def _convert_ico_to_safe_png(self, src: Path, target_dir: Path) -> Path | None:
        """Decode ICO via Pillow and save as normalized PNG.

        Returns destination path on success, otherwise None (caller can fallback to copy).
        """
        try:
            with Image.open(src) as im:
                best = self._pick_best_ico_frame(im)
                if best.mode != "RGBA":
                    best = best.convert("RGBA")

                dst = self._unique_path(target_dir, f"{src.stem}_safe", ".png")
                best.save(dst, format="PNG")

            if not is_valid_icon_file(dst):
                try:
                    dst.unlink(missing_ok=True)
                except OSError:
                    pass
                raise ValueError(f"Generated safe PNG is invalid: {dst}")
            return dst
        except (UnidentifiedImageError, OSError, ValueError) as e:
            logger.warning("ICO safe conversion failed for %s: %s", src, e)
            return None

    @staticmethod
    def _pick_best_ico_frame(im: Image.Image) -> Image.Image:
        """Pick the largest frame from a multi-frame ICO image."""
        try:
            n_frames = int(getattr(im, "n_frames", 1) or 1)
        except Exception:
            n_frames = 1

        best = im.copy()
        best_area = best.size[0] * best.size[1]
        for idx in range(n_frames):
            try:
                im.seek(idx)
                frame = im.copy()
                area = frame.size[0] * frame.size[1]
                if area >= best_area:
                    best = frame
                    best_area = area
            except Exception:
                continue
        return best

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
