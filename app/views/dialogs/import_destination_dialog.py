"""Dialog for choosing destination sphere and section when importing an archive."""
from __future__ import annotations

from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from app.config_data.runtime_config import runtime_app_config as app_config
from app.utils.ui.qt.combo_helpers import (
    PopupComboBox,
    add_combo_mapping_item,
)
from app.views.windows.dialogs.base_dialog import BaseDialog
from app.views.windows.dialogs.link_dialog.icon_utils import (
    get_cached_icon_with_fallback,
)


def _combo_icon_loader(entity_type: str):
    def _load(icon_path: str, entity_data: Any = None):
        return get_cached_icon_with_fallback(icon_path, entity_type)

    return _load


class ImportDestinationDialog(BaseDialog):
    """Dialog prompting user where to place an imported section or category."""

    def __init__(
        self,
        parent: QWidget | None,
        package_type: str,
        item_name: str,
        spheres: list[dict[str, Any]],
        sections_by_sphere: dict[int, list[dict[str, Any]]],
        default_sphere_id: int | None = None,
        default_section_id: int | None = None,
    ) -> None:
        super().__init__(parent)
        self.package_type = package_type
        self.spheres = spheres
        self.sections_by_sphere = sections_by_sphere
        self.section_combo: PopupComboBox | None = None

        self.setWindowFlags(
            self.windowFlags() | Qt.WindowType.MSWindowsFixedSizeDialogHint
        )
        try:
            self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        except AttributeError:
            pass

        self.setWindowTitle(
            self.tr("Import Section")
            if package_type == "section"
            else self.tr("Import Category")
        )
        self.setFixedWidth(380)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(*app_config.ui.get_settings_dialog_margins())
        layout.setSpacing(app_config.ui.get_settings_dialog_spacing())

        info_label = QLabel(
            self.tr("Importing: <b>{name}</b>").format(name=item_name), self
        )
        info_label.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(info_label)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setHorizontalSpacing(
            app_config.ui.get_settings_dialog_form_horizontal_spacing()
        )
        form.setVerticalSpacing(
            app_config.ui.get_settings_dialog_form_vertical_spacing()
        )

        self.sphere_combo = PopupComboBox(self)
        for sp in self.spheres:
            add_combo_mapping_item(
                self.sphere_combo,
                sp,
                icon_key="icon_path",
                icon_loader=_combo_icon_loader("sphere"),
            )

        if default_sphere_id is not None:
            idx = self.sphere_combo.findData(default_sphere_id)
            if idx >= 0:
                self.sphere_combo.setCurrentIndex(idx)

        form.addRow(self.tr("Destination Sphere:"), self.sphere_combo)

        if package_type == "category":
            self.section_combo = PopupComboBox(self)
            form.addRow(self.tr("Destination Section:"), self.section_combo)
            self.sphere_combo.currentIndexChanged.connect(self._on_sphere_changed)
            self._update_sections(default_section_id)

        layout.addLayout(form)

        self.btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        self.btn_box.button(QDialogButtonBox.StandardButton.Ok).setText(
            self.tr("Import")
        )
        self.btn_box.button(QDialogButtonBox.StandardButton.Cancel).setText(
            self.tr("Cancel")
        )
        self.btn_box.accepted.connect(self.accept)
        self.btn_box.rejected.connect(self.reject)
        self.equalize_button_box(self.btn_box)
        layout.addWidget(self.btn_box)

        if package_type == "category":
            self._update_ok_button_state()

        self.adjustSize()

    def _on_sphere_changed(self) -> None:
        self._update_sections()

    def _update_sections(self, prefer_section_id: int | None = None) -> None:
        if self.section_combo is None:
            return
        self.section_combo.clear()
        sp_id = self.sphere_combo.currentData()
        if sp_id is None:
            self._update_ok_button_state()
            return
        sections = self.sections_by_sphere.get(int(sp_id), [])
        for sec in sections:
            add_combo_mapping_item(
                self.section_combo,
                sec,
                icon_key="icon_path",
                icon_loader=_combo_icon_loader("section"),
            )
        if prefer_section_id is not None:
            idx = self.section_combo.findData(prefer_section_id)
            if idx >= 0:
                self.section_combo.setCurrentIndex(idx)
        self._update_ok_button_state()

    def _update_ok_button_state(self) -> None:
        if (
            self.package_type == "category"
            and hasattr(self, "btn_box")
            and self.section_combo is not None
        ):
            ok_btn = self.btn_box.button(QDialogButtonBox.StandardButton.Ok)
            if ok_btn is not None:
                ok_btn.setEnabled(self.section_combo.count() > 0)

    def get_selected_sphere_id(self) -> int | None:
        data = self.sphere_combo.currentData()
        return int(data) if data is not None else None

    def get_selected_section_id(self) -> int | None:
        if self.section_combo is None:
            return None
        data = self.section_combo.currentData()
        return int(data) if data is not None else None
