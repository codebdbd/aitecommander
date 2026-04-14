"""Configuration helpers for application limits and quotas."""

from __future__ import annotations

from .base_config import BaseConfig


class LimitsConfig(BaseConfig):
    """Provide strongly typed accessors for limit-related settings."""

    # === File size limits ===

    def get_max_icon_size(self) -> int:
        """Return the maximum allowed icon file size in bytes."""
        return self.get("limits.max_icon_size", 10 * 1024 * 1024)

    def get_max_web_icon_size(self) -> int:
        """Return the maximum allowed web icon size in bytes."""
        return self.get("limits.max_web_icon_size", 2 * 1024 * 1024)

    # === Caching ===

    def get_icon_cache_size(self) -> int:
        """Return the cache capacity for icons."""
        return self.get("limits.icon_cache_size", 100)

    def get_icon_cache_ttl(self) -> int:
        """Return the cache time-to-live for icons in seconds.

        Defaults to 300 seconds (5 minutes). Recommended range: 300-600 seconds to
        refresh icon file updates automatically.
        """
        return self.get("limits.icon_cache_ttl", 300)

    def get_negative_cache_ttl(self) -> int:
        """Return the negative cache TTL for missing icons in seconds.

        Defaults to 30 seconds and helps avoid repeated filesystem lookups for
        absent files.
        """
        return self.get("limits.negative_cache_ttl", 30)

    def get_abs_icon_cache_ttl(self) -> int:
        """Return the cache TTL for icons resolved by absolute path in seconds.

        Defaults to 30 seconds and prevents frequent filesystem checks when files
        appear dynamically.
        """
        return self.get("limits.abs_icon_cache_ttl", 30)

    # === Theme package limits ===

    def get_theme_max_package_size(self) -> int:
        """Return the maximum allowed theme package size in bytes."""
        return self.get("limits.theme_max_package_size", 50 * 1024 * 1024)

    def get_theme_max_uncompressed_size(self) -> int:
        """Return the maximum allowed uncompressed size for theme packages in bytes."""
        return self.get("limits.theme_max_uncompressed_size", 200 * 1024 * 1024)

    def get_theme_max_files(self) -> int:
        """Return the maximum allowed file count for a theme package."""
        return self.get("limits.theme_max_files", 5000)

    # === Bulk operation limits ===

    def get_bulk_operation_max_batch_size(self) -> int:
        """Return the maximum allowed bulk operation batch size."""
        return self.get("limits.bulk_operation_max_batch_size", 5000)
