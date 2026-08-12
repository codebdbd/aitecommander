from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from app.utils.browser.profile_selection_state import (
    LAST_WEB_LINK_PROFILE_KEYS_SETTING,
    load_last_web_link_profile_keys,
    profile_selection_key,
    save_last_web_link_profile_keys,
)
from app.views.windows.dialogs.link_dialog.handlers_mixins.profiles_mixin import (
    ProfilesMixin,
)


def test_profile_selection_key_prefers_browser_and_stable_path() -> None:
    profile = {
        "browser_key": "Chrome",
        "path": r"C:\Users\me\AppData\Chrome\User Data\Profile 7",
        "directory": "Profile 7",
        "name": "Work",
    }

    assert profile_selection_key(profile) == (
        r"chrome:c:\users\me\appdata\chrome\user data\profile 7"
    )


def test_profile_selection_key_falls_back_to_directory() -> None:
    profile = {
        "browser_key": "edge",
        "directory": "Default",
        "name": "Personal",
    }

    assert profile_selection_key(profile) == "edge:default"


def test_last_web_link_profile_keys_are_saved_and_loaded() -> None:
    store = {}

    with (
        patch(
            "app.utils.browser.profile_selection_state.SettingsManager.get",
            side_effect=lambda key, default=None: store.get(key, default),
        ),
        patch(
            "app.utils.browser.profile_selection_state.SettingsManager.set",
            side_effect=lambda key, value: store.__setitem__(key, value),
        ) as set_setting,
        patch("app.utils.browser.profile_selection_state.SettingsManager.save") as save,
    ):
        save_last_web_link_profile_keys(
            [
                {"browser_key": "chrome", "directory": "Default"},
                {"browser_key": "edge", "directory": "Profile 2"},
            ]
        )

        set_setting.assert_called_once_with(
            LAST_WEB_LINK_PROFILE_KEYS_SETTING,
            ["chrome:default", "edge:profile 2"],
        )
        save.assert_called_once()
        assert load_last_web_link_profile_keys() == {
            "chrome:default",
            "edge:profile 2",
        }


def test_profiles_mixin_prefers_current_dialog_profiles_over_saved_selection() -> None:
    mixin = ProfilesMixin()
    mixin.dialog = SimpleNamespace(
        link_type="web",
        selected_profiles=[{"browser_key": "chrome", "directory": "Profile 3"}],
    )

    with patch(
        "app.views.windows.dialogs.link_dialog.handlers_mixins.profiles_mixin."
        "load_last_web_link_profile_keys",
        return_value={"chrome:default"},
    ):
        assert mixin._initial_profile_selection_keys() == {"chrome:profile 3"}


def test_profiles_mixin_loads_saved_selection_for_new_web_link() -> None:
    mixin = ProfilesMixin()
    mixin.dialog = SimpleNamespace(link_type="web", selected_profiles=[])

    with patch(
        "app.views.windows.dialogs.link_dialog.handlers_mixins.profiles_mixin."
        "load_last_web_link_profile_keys",
        return_value={"chrome:default"},
    ):
        assert mixin._initial_profile_selection_keys() == {"chrome:default"}
