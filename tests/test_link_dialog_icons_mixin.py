from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock, patch

from PyQt6.QtGui import QIcon

from app.views.windows.dialogs.link_dialog.handlers_mixins.icons_mixin import (
    IconsMixin,
)


def _build_handler(*, icon_name: str, link_type: str = "web"):
    button = Mock()
    dialog = SimpleNamespace(
        link_type=link_type,
        icon_name=icon_name,
        get_user_icons_dir=Mock(return_value="C:/icons"),
        _get_icon_btn=Mock(return_value=button),
    )
    handler = IconsMixin()
    handler.dialog = dialog
    return handler, dialog, button


def test_clicking_assigned_web_icon_opens_picker_first_and_resets_on_cancel(
    tmp_path,
) -> None:
    default_icon = tmp_path / "web.png"
    default_icon.write_bytes(b"icon")
    handler, dialog, button = _build_handler(icon_name="custom.png")

    with (
        patch(
            "app.views.windows.dialogs.link_dialog.handlers_mixins.icons_mixin.resolve_icon_for_link",
            return_value=str(default_icon),
        ),
        patch(
            "app.views.windows.dialogs.link_dialog.handlers_mixins.icons_mixin.set_icon_to_button"
        ) as set_icon_mock,
        patch(
            "app.views.windows.dialogs.link_dialog.handlers_mixins.icons_mixin.choose_icon_and_copy"
        , return_value=(None, None)) as choose_mock,
    ):
        handler._on_choose_icon()

    assert dialog.icon_name == ""
    set_icon_mock.assert_called_once_with(button, str(default_icon))
    choose_mock.assert_called_once_with(dialog, "C:/icons")


def test_clicking_empty_web_icon_allows_custom_selection() -> None:
    handler, dialog, button = _build_handler(icon_name="")
    selected_icon = QIcon()

    with patch(
        "app.views.windows.dialogs.link_dialog.handlers_mixins.icons_mixin.choose_icon_and_copy",
        return_value=("selected.png", selected_icon),
    ) as choose_mock:
        handler._on_choose_icon()

    assert dialog.icon_name == "selected.png"
    choose_mock.assert_called_once_with(dialog, "C:/icons")
    button.setIcon.assert_called_once_with(selected_icon)


def test_non_web_icon_click_keeps_file_selection_behavior() -> None:
    handler, dialog, _button = _build_handler(
        icon_name="program-custom.png",
        link_type="program",
    )

    with patch(
        "app.views.windows.dialogs.link_dialog.handlers_mixins.icons_mixin.choose_icon_and_copy",
        return_value=("replacement.png", QIcon()),
    ) as choose_mock:
        handler._on_choose_icon()

    assert dialog.icon_name == "replacement.png"
    choose_mock.assert_called_once()


def test_non_web_cancel_resets_to_type_default(tmp_path) -> None:
    default_icon = tmp_path / "program.png"
    default_icon.write_bytes(b"icon")
    handler, dialog, button = _build_handler(
        icon_name="program-custom.png",
        link_type="program",
    )

    with (
        patch(
            "app.views.windows.dialogs.link_dialog.handlers_mixins.icons_mixin.resolve_icon_for_link",
            return_value=str(default_icon),
        ),
        patch(
            "app.views.windows.dialogs.link_dialog.handlers_mixins.icons_mixin.set_icon_to_button"
        ) as set_icon_mock,
        patch(
            "app.views.windows.dialogs.link_dialog.handlers_mixins.icons_mixin.choose_icon_and_copy",
            return_value=(None, None),
        ),
    ):
        handler._on_choose_icon()

    assert dialog.icon_name == ""
    set_icon_mock.assert_called_once_with(button, str(default_icon))
