from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock, patch

from PyQt6.QtGui import QIcon

from app.views.windows.dialogs.entity_dialogs import BaseEntityDialog


def test_entity_icon_cancel_resets_to_default(tmp_path: Path) -> None:
    default_icon = tmp_path / "category.png"
    default_icon.write_bytes(b"icon")
    dialog = BaseEntityDialog.__new__(BaseEntityDialog)
    dialog.entity_name = "category"
    dialog._icon_filename = "custom.png"
    dialog.icon_btn = Mock()
    dialog._translate = Mock(side_effect=lambda text: text)
    dialog.show_error = Mock()
    dialog._get_icon_path = Mock(return_value=default_icon)

    with (
        patch(
            "app.views.windows.dialogs.entity_dialogs.icon_path_service.get_user_icons_dir",
            return_value=tmp_path,
        ),
        patch(
            "app.views.windows.dialogs.entity_dialogs.choose_icon_and_copy",
            create=True,
        ),
    ):
        pass

    with (
        patch(
            "app.utils.ui.icon.selection.choose_icon_and_copy",
            return_value=(None, None),
        ),
        patch(
            "app.views.windows.dialogs.entity_dialogs.create_icon_from_path",
            return_value=QIcon(),
        ) as create_icon_mock,
    ):
        dialog._choose_icon()

    assert dialog._icon_filename == "category.png"
    create_icon_mock.assert_called_once_with(str(default_icon))
    dialog.icon_btn.setIcon.assert_called_once()
