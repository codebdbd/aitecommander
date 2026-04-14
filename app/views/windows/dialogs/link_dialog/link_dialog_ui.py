"""
Module for constructing the add/edit link dialog UI.

`LinkDialogUI` encapsulates widget building and keeps references to key
elements via the `widgets` dictionary.
"""

import logging
from typing import Any

from PyQt6.QtCore import QT_TRANSLATE_NOOP, QCoreApplication, QSize, Qt
from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.config_data.runtime_config import runtime_app_config as app_config
from app.utils.i18n.common import tr as tr_common
from app.utils.ui.icon.icon_operations.creators import create_icon_from_path
from app.utils.ui.icon.icon_resolver import resolve_icon_for_link

logger = logging.getLogger(__name__)

_LINK_TYPE_FALLBACK_LABELS: dict[str, str] = {
    "web": QT_TRANSLATE_NOOP("LinkDialogUI", "Web link"),
    "file": QT_TRANSLATE_NOOP("LinkDialogUI", "File"),
    "program": QT_TRANSLATE_NOOP("LinkDialogUI", "Application"),
    "script": QT_TRANSLATE_NOOP("LinkDialogUI", "Script"),
    "folder": QT_TRANSLATE_NOOP("LinkDialogUI", "Folder"),
}

# lupdate hint for dynamic link type labels
if False:  # pragma: no cover
    QCoreApplication.translate("LinkDialogUI", "Web link")
    QCoreApplication.translate("LinkDialogUI", "File")
    QCoreApplication.translate("LinkDialogUI", "Application")
    QCoreApplication.translate("LinkDialogUI", "Script")
    QCoreApplication.translate("LinkDialogUI", "Folder")


class LinkDialogUI:
    """UI components for `LinkDialog`."""

    def __init__(self, parent: QWidget) -> None:
        """Initialise UI components.

        :param parent: Parent widget (typically the `LinkDialog` instance).
        """
        self.parent: QWidget = parent
        self.widgets: dict[str, QWidget] = {}
        self._link_type_titles: dict[str, str] = {}
        self._type_buttons: dict[str, QToolButton] = {}
        self._type_button_codes: list[str] = []

    def build_ui(self, link_types: list[tuple[str, str]]) -> None:
        """Build the UI.

        :param link_types: List of `(code, title)` pairs for link types.
        """
        vbox = QVBoxLayout(self.parent)
        margins = app_config.ui.get_link_dialog_margins()
        vbox.setContentsMargins(margins, margins, margins, margins)
        vbox.setSpacing(app_config.ui.get_link_dialog_spacing())

        # UI sections
        self._build_type_section(vbox, link_types)
        self._build_form_section(vbox)
        self._build_buttons(vbox)

        # "Save" button enabled only when both URL/Path and Name are filled
        self._update_save_button_state()
        try:
            self.url_le.textChanged.connect(lambda _t: self._update_save_button_state())
            self.name_le.textChanged.connect(
                lambda _t: self._update_save_button_state()
            )
        except (AttributeError, RuntimeError) as e:
            logger.warning("Failed to connect textChanged for name_le: %s", e)

        # Focus is handled by LinkDialog itself depending on link type

    def _build_type_section(
        self, container: QVBoxLayout, link_types: list[tuple[str, str]]
    ) -> None:
        """Create link type section and add it to container."""
        self._link_type_titles.clear()
        self._type_buttons.clear()
        self._type_button_codes.clear()
        self.lbl_link_type = QLabel(
            QCoreApplication.translate("LinkDialogUI", "Link type:")
        )
        container.addWidget(self.lbl_link_type)
        self.type_group = QButtonGroup(self.parent)
        hl_type = QHBoxLayout()

        for code, txt in link_types:
            btn = QToolButton()
            btn.setCheckable(True)
            self._link_type_titles[code] = txt
            # Enable hover events similar to sphere/category buttons
            try:
                btn.setMouseTracking(True)
                btn.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
            except Exception:
                pass
            try:
                self._type_button_codes.append(code)
                type_icon_size = app_config.ui.get_link_dialog_type_icon_size()
                btn.setIconSize(QSize(type_icon_size, type_icon_size))
            except (AttributeError, RuntimeError) as e:
                logger.warning("Failed to configure link type icon size: %s", e)
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            # Height by content. Width expands to share space equally.
            btn.setObjectName("linkTypeBtn")
            btn.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
            )
            self.type_group.addButton(btn)
            btn.setProperty("link_type", code)
            self._type_buttons[code] = btn
            hl_type.addWidget(btn, 1)

        container.addLayout(hl_type)
        self.widgets["type_group"] = self.type_group
        self._apply_link_type_translations()

    def apply_deferred_type_icons(self) -> None:
        """Apply link type icons after the dialog is shown."""
        for code in self._type_button_codes:
            btn = self._type_buttons.get(code)
            if btn is None:
                continue
            try:
                icon_path = resolve_icon_for_link({"type": code, "icon_path": ""})
                if icon_path:
                    btn.setIcon(create_icon_from_path(str(icon_path)))
            except Exception:
                logger.debug("Failed to apply deferred type icon for %s", code, exc_info=True)

    def _build_form_section(self, container: QVBoxLayout) -> None:
        """Create form section (URL/Name/Arguments/Hierarchy/Notes/Favorite)."""
        self.form = QFormLayout()
        self.form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # Build form rows
        self._form_add_path_row()
        self._form_add_name_row()
        self._form_add_args_row()
        self._form_add_hierarchy_section()
        self._form_add_notes_and_fav()

        container.addLayout(self.form)

    def _form_add_path_row(self) -> None:
        """Add URL/Path row with Browse/Profile buttons."""
        self.url_le = QLineEdit()
        hl_path = QHBoxLayout()
        hl_path.addWidget(self.url_le, 1)

        self.browse_btn = QPushButton(
            QCoreApplication.translate("LinkDialogUI", "Browse...")
        )
        self.browse_btn.setFixedWidth(app_config.ui.get_fixed_button_width())
        hl_path.addWidget(self.browse_btn)

        self.profile_btn = QPushButton(
            QCoreApplication.translate("LinkDialogUI", "Profile")
        )
        self.profile_btn.setFixedWidth(app_config.ui.get_fixed_button_width())
        hl_path.addWidget(self.profile_btn)

        self.form.addRow(
            QCoreApplication.translate("LinkDialogUI", "URL/Path:"), hl_path
        )
        self.widgets.update(
            {
                "url_le": self.url_le,
                "browse_btn": self.browse_btn,
                "profile_btn": self.profile_btn,
            }
        )

    def _form_add_name_row(self) -> None:
        """Add Name row with icon selection button."""
        self.name_le = QLineEdit()
        hl_name = QHBoxLayout()
        hl_name.addWidget(self.name_le, 1)

        self.icon_btn = QPushButton(tr_common("Icon"))
        self.icon_btn.setFixedWidth(app_config.ui.get_fixed_button_width())
        try:
            default_icon = int(app_config.ui.get_default_icon_size())
            self.icon_btn.setIconSize(QSize(default_icon, default_icon))
        except (AttributeError, RuntimeError, ValueError) as e:
            logger.warning("Failed to configure icon button size: %s", e)
        hl_name.addWidget(self.icon_btn)

        self.form.addRow(tr_common("Name:"), hl_name)
        self.widgets.update({"name_le": self.name_le, "icon_btn": self.icon_btn})

    def _form_add_args_row(self) -> None:
        """Add row for launch arguments."""
        self.args_le = QLineEdit()
        self.args_label = QLabel(
            QCoreApplication.translate("LinkDialogUI", "Arguments:")
        )
        self.form.addRow(self.args_label, self.args_le)
        self.widgets.update({"args_le": self.args_le, "args_label": self.args_label})

    def _form_add_hierarchy_section(self) -> None:
        """Add hierarchy combo boxes: Sphere, Section, Category."""
        self.sphere_cb = QComboBox()
        self.section_cb = QComboBox()
        self.category_cb = QComboBox()

        # Avoid focus stealing on hover — allow focus by click/Tab only
        try:
            for cb in (self.sphere_cb, self.section_cb, self.category_cb):
                cb.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        except Exception:
            pass

        self.form.addRow(
            QCoreApplication.translate("LinkDialogUI", "Sphere:"), self.sphere_cb
        )
        self.form.addRow(
            QCoreApplication.translate("LinkDialogUI", "Section:"), self.section_cb
        )
        self.form.addRow(
            QCoreApplication.translate("LinkDialogUI", "Category:"), self.category_cb
        )

        self.widgets.update(
            {
                "sphere_cb": self.sphere_cb,
                "section_cb": self.section_cb,
                "category_cb": self.category_cb,
            }
        )

    def _form_add_notes_and_fav(self) -> None:
        """Add notes field and favorites checkbox."""
        self.notes_te = QTextEdit()
        try:
            self.notes_te.setTabChangesFocus(True)
        except (AttributeError, RuntimeError) as e:
            logger.warning("Failed to set tabChangesFocus for notes_te: %s", e)
        self.form.addRow(
            QCoreApplication.translate("LinkDialogUI", "Notes:"), self.notes_te
        )
        self.widgets["notes_te"] = self.notes_te

        self.fav_chk = QCheckBox(
            QCoreApplication.translate("LinkDialogUI", "Add to favorites")
        )
        fav_row = QHBoxLayout()
        fav_row.setContentsMargins(0, 0, 0, 0)
        fav_row.setSpacing(0)
        fav_row.addWidget(self.fav_chk)
        fav_row.addStretch(1)
        self.form.addRow("", fav_row)
        self.widgets["fav_chk"] = self.fav_chk

    def _build_buttons(self, container: QVBoxLayout) -> None:
        """Create OK/Cancel buttons panel and add it to container."""
        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        ok_btn = self.button_box.button(QDialogButtonBox.StandardButton.Ok)
        ok_btn.setText(tr_common("Save"))
        # Remove default dotted focus: disable default/autoDefault and auto focus
        try:
            ok_btn.setAutoDefault(False)
            ok_btn.setDefault(False)
            ok_btn.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        except (AttributeError, RuntimeError) as e:
            logger.warning("Failed to configure focus for OK button: %s", e)
        ok_btn.setFixedWidth(app_config.ui.get_fixed_button_width())

        cancel_btn = self.button_box.button(QDialogButtonBox.StandardButton.Cancel)
        cancel_btn.setText(tr_common("Cancel"))
        try:
            cancel_btn.setAutoDefault(False)
            cancel_btn.setDefault(False)
            cancel_btn.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        except (AttributeError, RuntimeError) as e:
            logger.warning("Failed to configure focus for Cancel button: %s", e)
        cancel_btn.setFixedWidth(app_config.ui.get_fixed_button_width())

        container.addWidget(self.button_box)
        self.widgets["button_box"] = self.button_box
        self.widgets["ok_btn"] = ok_btn

    def get_widget(self, name: str) -> QWidget | None:
        """Return widget by name."""
        return self.widgets.get(name)

    def _update_save_button_state(self) -> None:
        """Enable "Save" button only when both URL/Path and Name are filled."""
        try:
            url_ok = bool(self.url_le.text().strip())
            name_ok = bool(self.name_le.text().strip())
            ok_btn = self.widgets.get("ok_btn") or self.button_box.button(
                QDialogButtonBox.StandardButton.Ok
            )
            ok_btn.setEnabled(url_ok and name_ok)
        except (AttributeError, RuntimeError) as e:
            logger.warning("Failed to update save button state: %s", e)

    def set_form_data(self, data: dict[str, Any]) -> None:
        """Set form data from dictionary."""
        for key, value in data.items():
            self.set_widget_value(key, value)

    def set_widget_value(self, name: str, value: Any) -> None:
        """Set widget value."""
        widget = self.get_widget(name)
        if widget:
            if hasattr(widget, "setChecked"):
                widget.setChecked(bool(value))
            elif hasattr(widget, "setText"):
                widget.setText(str(value))
            elif hasattr(widget, "setPlainText"):
                widget.setPlainText(str(value))

    def get_widget_value(self, name: str) -> Any:
        """Get widget value."""
        widget = self.get_widget(name)
        if widget:
            if hasattr(widget, "text"):
                return widget.text()
            elif hasattr(widget, "toPlainText"):
                return widget.toPlainText()
            elif hasattr(widget, "isChecked"):
                return widget.isChecked()
        return None

    # --- Runtime i18n -------------------------------------------------------
    def _retranslate_type_section(self):
        """Retranslate type section label."""
        try:
            if hasattr(self, "lbl_link_type") and self.lbl_link_type is not None:
                self.lbl_link_type.setText(
                    QCoreApplication.translate("LinkDialogUI", "Link type:")
                )
            self._apply_link_type_translations()
        except Exception:
            pass

    def _retranslate_path_row(self):
        """Retranslate path row buttons."""
        try:
            if hasattr(self, "browse_btn") and self.browse_btn is not None:
                self.browse_btn.setText(
                    QCoreApplication.translate("LinkDialogUI", "Browse...")
                )
            if hasattr(self, "profile_btn") and self.profile_btn is not None:
                if not self.profile_btn.text() or self.profile_btn.text() == (
                    QCoreApplication.translate("LinkDialogUI", "Profile")
                ):
                    self.profile_btn.setText(
                        QCoreApplication.translate("LinkDialogUI", "Profile")
                    )
        except Exception:
            pass

    def _retranslate_name_row(self):
        """Retranslate name row label."""
        try:
            if (
                hasattr(self, "form")
                and self.form is not None
                and hasattr(self, "name_le")
            ):
                name_label = self.form.labelForField(self.name_le)
                if name_label is not None:
                    name_label.setText(tr_common("Name:"))
            if hasattr(self, "icon_btn") and self.icon_btn is not None:
                self.icon_btn.setText(tr_common("Icon"))
        except Exception:
            pass

    def _retranslate_args_row(self):
        """Retranslate arguments row label."""
        try:
            if hasattr(self, "args_label") and self.args_label is not None:
                self.args_label.setText(
                    QCoreApplication.translate("LinkDialogUI", "Arguments:")
                )
        except Exception:
            pass

    def _retranslate_hierarchy(self):
        """Retranslate hierarchy labels (sphere, section, category)."""
        try:
            if hasattr(self, "form") and self.form is not None:
                if hasattr(self, "sphere_cb"):
                    lbl = self.form.labelForField(self.sphere_cb)
                    if lbl is not None:
                        lbl.setText(
                            QCoreApplication.translate("LinkDialogUI", "Sphere:")
                        )
                if hasattr(self, "section_cb"):
                    lbl = self.form.labelForField(self.section_cb)
                    if lbl is not None:
                        lbl.setText(
                            QCoreApplication.translate("LinkDialogUI", "Section:")
                        )
                if hasattr(self, "category_cb"):
                    lbl = self.form.labelForField(self.category_cb)
                    if lbl is not None:
                        lbl.setText(
                            QCoreApplication.translate("LinkDialogUI", "Category:")
                        )
        except Exception:
            pass

    def _retranslate_notes_and_favorites(self):
        """Retranslate notes label and favorites checkbox."""
        try:
            if (
                hasattr(self, "form")
                and self.form is not None
                and hasattr(self, "notes_te")
            ):
                notes_label = self.form.labelForField(self.notes_te)
                if notes_label is not None:
                    notes_label.setText(
                        QCoreApplication.translate("LinkDialogUI", "Notes:")
                    )
            if hasattr(self, "fav_chk") and self.fav_chk is not None:
                self.fav_chk.setText(
                    QCoreApplication.translate("LinkDialogUI", "Add to favorites")
                )
        except Exception:
            pass

    def _retranslate_buttons(self):
        """Retranslate dialog buttons."""
        try:
            if hasattr(self, "button_box") and self.button_box is not None:
                ok_btn = self.button_box.button(QDialogButtonBox.StandardButton.Ok)
                cancel_btn = self.button_box.button(
                    QDialogButtonBox.StandardButton.Cancel
                )
                if ok_btn is not None:
                    ok_btn.setText(tr_common("Save"))
                if cancel_btn is not None:
                    cancel_btn.setText(tr_common("Cancel"))
        except Exception:
            pass

    def retranslate(self) -> None:
        """Update all static texts when the application language changes."""
        self._retranslate_type_section()
        self._retranslate_path_row()
        self._retranslate_name_row()
        self._retranslate_args_row()
        self._retranslate_hierarchy()
        self._retranslate_notes_and_favorites()
        self._retranslate_buttons()

    def _apply_link_type_translations(self) -> None:
        """Apply translations to link type buttons."""
        try:
            for code, btn in self._type_buttons.items():
                if btn is None:
                    continue
                original = self._link_type_titles.get(code, btn.text())
                btn.setText(self._translate_link_type_title(code, original))
        except Exception:
            pass

    def _translate_link_type_title(self, code: str, original: str) -> str:
        """Return translated title for link type with graceful fallback."""
        label_key = _LINK_TYPE_FALLBACK_LABELS.get(code)
        if label_key:
            translated = QCoreApplication.translate("LinkDialogUI", label_key)
            if translated != label_key or not original or original == label_key:
                return translated
        # Fallback: try translating original value; if unavailable, return original
        translated_original = (
            QCoreApplication.translate("LinkDialogUI", original) if original else ""
        )
        return translated_original if translated_original else original
