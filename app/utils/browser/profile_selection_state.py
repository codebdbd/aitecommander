"""Persistence helpers for the browser profile selection UI."""

from __future__ import annotations

from typing import Any

from app.core.settings_manager import SettingsManager


LAST_WEB_LINK_PROFILE_KEYS_SETTING = "link_dialog.last_web_link_profile_keys"


def profile_selection_key(profile: dict[str, Any]) -> str:
    """Return a stable key for matching a browser profile across dialog opens."""
    browser_key = _clean(profile.get("browser_key"))
    identity = (
        _clean(profile.get("path"))
        or _clean(profile.get("directory"))
        or _clean(profile.get("args"))
        or _clean(profile.get("email"))
        or _clean(profile.get("name"))
    )
    if not browser_key or not identity:
        return ""
    return f"{browser_key}:{identity}".lower()


def load_last_web_link_profile_keys() -> set[str]:
    value = SettingsManager.get(LAST_WEB_LINK_PROFILE_KEYS_SETTING, [])
    if not isinstance(value, list):
        return set()
    return {str(item).strip().lower() for item in value if str(item).strip()}


def save_last_web_link_profile_keys(profiles: list[dict[str, Any]]) -> None:
    keys = [profile_selection_key(profile) for profile in profiles]
    SettingsManager.set(
        LAST_WEB_LINK_PROFILE_KEYS_SETTING,
        [key for key in keys if key],
    )
    SettingsManager.save()


def _clean(value: Any) -> str:
    return str(value or "").strip()
