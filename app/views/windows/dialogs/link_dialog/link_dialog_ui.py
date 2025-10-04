"""
Module for constructing the add/edit link dialog UI.

`LinkDialogUI` encapsulates widget building and keeps references to key
elements via the `widgets` dictionary.
"""

import logging
from typing import Any, Dict, List, Tuple

from PyQt6.QtCore import QCoreApplication, QSize, Qt
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

from app.config_data import app_config
from app.utils.ui.icon.icon_operations.creators import create_icon_from_path
from app.utils.ui.icon.icon_resolver import resolve_icon_for_link

logger = logging.getLogger(__name__)

_TR_CONTEXT = "LinkDialogUI"


def _tr(text: str, disambiguation: str | None = None) -> str:
    return QCoreApplication.translate(_TR_CONTEXT, text, disambiguation)


class LinkDialogUI:
    """UI components for `LinkDialog`."""

    def __init__(self, parent: QWidget) -> None:
        """Initialise UI components.

        :param parent: Parent widget (typically the `LinkDialog` instance).
        """
        self.parent: QWidget = parent
        self.widgets: Dict[str, QWidget] = {}

    def build_ui(self, link_types: List[Tuple[str, str]]) -> None:
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
        self, container: QVBoxLayout, link_types: List[Tuple[str, str]]
    ) -> None:
        """Create link type section and add it to container."""
        container.addWidget(QLabel(_tr("Link type:")))
        self.type_group = QButtonGroup(self.parent)
        hl_type = QHBoxLayout()

        for code, txt in link_types:
            btn = QToolButton()
            btn.setCheckable(True)
            btn.setText(txt)
            # Enable hover events similar to sphere/category buttons
            try:
                btn.setMouseTracking(True)
                btn.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
            except Exception:
                pass
            try:
                icon_path = resolve_icon_for_link({"type": code, "icon_path": ""})
                if icon_path:
                    btn.setIcon(create_icon_from_path(str(icon_path)))
                    # Icon size comes from UI config
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
            hl_type.addWidget(btn, 1)

        container.addLayout(hl_type)
        self.widgets["type_group"] = self.type_group

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

        self.browse_btn = QPushButton(_tr("Browse…"))
        self.browse_btn.setFixedWidth(app_config.ui.get_fixed_button_width())
        hl_path.addWidget(self.browse_btn)

        self.profile_btn = QPushButton(_tr("Profile"))
        self.profile_btn.setFixedWidth(app_config.ui.get_fixed_button_width())
        hl_path.addWidget(self.profile_btn)

        self.form.addRow(_tr("URL/Path:"), hl_path)
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

        self.icon_btn = QPushButton(_tr("Icon"))
        self.icon_btn.setFixedWidth(app_config.ui.get_fixed_button_width())
        try:
            default_icon = int(app_config.ui.get_default_icon_size())
            self.icon_btn.setIconSize(QSize(default_icon, default_icon))
        except (AttributeError, RuntimeError, ValueError) as e:
            logger.warning("Failed to configure icon button size: %s", e)
        hl_name.addWidget(self.icon_btn)

        self.form.addRow(_tr("Name:"), hl_name)
        self.widgets.update({"name_le": self.name_le, "icon_btn": self.icon_btn})

    def _form_add_args_row(self) -> None:
        """Add row for launch arguments."""
        self.args_le = QLineEdit()
        self.args_label = QLabel(_tr("Arguments:"))
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

        self.form.addRow(_tr("Sphere:"), self.sphere_cb)
        self.form.addRow(_tr("Section:"), self.section_cb)
        self.form.addRow(_tr("Category:"), self.category_cb)

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
        self.form.addRow(_tr("Notes:"), self.notes_te)
        self.widgets["notes_te"] = self.notes_te

        self.fav_chk = QCheckBox(_tr("Add to favorites"))
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
        ok_btn.setText(_tr("Save"))
        # Remove default dotted focus: disable default/autoDefault and auto focus
        try:
            ok_btn.setAutoDefault(False)
            ok_btn.setDefault(False)
            ok_btn.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        except (AttributeError, RuntimeError) as e:
            logger.warning("Failed to configure focus for OK button: %s", e)
        ok_btn.setFixedWidth(app_config.ui.get_fixed_button_width())

        cancel_btn = self.button_box.button(QDialogButtonBox.StandardButton.Cancel)
        cancel_btn.setText(_tr("Cancel"))
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

    def set_form_data(self, data: Dict[str, Any]) -> None:
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
