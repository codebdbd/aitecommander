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
    QStackedWidget,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.config_data.runtime_config import runtime_app_config as app_config
from app.utils.links.type_labels import link_type_label_source
from app.utils.i18n.common import tr as tr_common
from app.utils.ui.icon.icon_operations.cache_proxy import icon_cache
from app.utils.ui.icon.icon_operations.creators import create_icon_from_path
from app.utils.ui.icon.icon_resolver import resolve_icon_for_link
from app.utils.ui.icon.path_service import get_current_theme
from app.utils.ui.qt.combo_helpers import PopupComboBox
from app.views.widgets.input_frame import InputFrame

logger = logging.getLogger(__name__)

# lupdate hint for dynamic link type labels
if False:  # pragma: no cover
    QCoreApplication.translate("LinkDialogUI", "Web link")
    QCoreApplication.translate("LinkDialogUI", "File")
    QCoreApplication.translate("LinkDialogUI", "Application")
    QCoreApplication.translate("LinkDialogUI", "Script")
    QCoreApplication.translate("LinkDialogUI", "Folder")
    QCoreApplication.translate("LinkDialogUI", "Note")

# lupdate hint for Web argument preset labels
if False:  # pragma: no cover
    QCoreApplication.translate("LinkDialogUI", "Default")
    QCoreApplication.translate("LinkDialogUI", "As application")
    QCoreApplication.translate("LinkDialogUI", "Incognito")
    QCoreApplication.translate("LinkDialogUI", "New window")
    QCoreApplication.translate("LinkDialogUI", "Guest mode")
    QCoreApplication.translate("LinkDialogUI", "Run as administrator")
    QCoreApplication.translate("LinkDialogUI", "Keep console open")
    QCoreApplication.translate("LinkDialogUI", "Administrator + Keep open")

# lupdate hint for browser profile labels
if False:  # pragma: no cover
    QCoreApplication.translate("LinkDialogUI", "No profile")
    QCoreApplication.translate("LinkDialogUI", "Single profile")
    QCoreApplication.translate("LinkDialogUI", "Create for each profile")
    QCoreApplication.translate("LinkDialogUI", "Rotation")
    QCoreApplication.translate("LinkDialogUI", "Select")
    QCoreApplication.translate("LinkDialogUI", "Profile:")
    QCoreApplication.translate("LinkDialogUI", "Favorites")


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
        self._form_add_profile_row()
        self._form_add_args_row()
        self._form_add_hierarchy_section()
        self._form_add_notes_and_fav()

        container.addLayout(self.form)

    @staticmethod
    def adjust_button_width(
        btn: QPushButton | None,
        min_width: int = 115,
        padding: int = 28,
    ) -> int:
        """Adjust button width dynamically based on its text and font metrics.

        Ensures text is never clipped regardless of language, font, or DPI scaling,
        while maintaining a clean minimum width for visual consistency.
        """
        if btn is None:
            return 0
        try:
            text = btn.text()
            fm = btn.fontMetrics()
            text_width = fm.horizontalAdvance(text) if text else 0
            icon_width = 0
            if hasattr(btn, "icon") and not btn.icon().isNull():
                icon_size = btn.iconSize()
                icon_width = (icon_size.width() if icon_size.isValid() else 16) + 8
            required_width = int(text_width) + int(icon_width) + padding
            target_width = max(min_width, required_width)
            btn.setFixedWidth(target_width)
            return target_width
        except Exception as e:
            logger.debug("Failed to adjust button width: %s", e)
            try:
                btn.setFixedWidth(min_width)
            except Exception:
                pass
            return min_width

    def _form_add_path_row(self) -> None:
        """Add URL/Path row with Browse/Profile buttons."""
        self.url_le = QLineEdit()
        hl_path = QHBoxLayout()
        hl_path.addWidget(self.url_le, 1)

        self.browse_btn = QPushButton(
            QCoreApplication.translate("LinkDialogUI", "Browse")
        )
        self.adjust_button_width(self.browse_btn)
        hl_path.addWidget(self.browse_btn)

        self.apps_btn = QPushButton(
            QCoreApplication.translate("LinkDialogUI", "Apps")
        )
        self.adjust_button_width(self.apps_btn)
        self.apps_btn.setVisible(False)
        hl_path.addWidget(self.apps_btn)

        self.form.addRow(
            QCoreApplication.translate("LinkDialogUI", "URL/Path:"), hl_path
        )
        self.widgets.update(
            {
                "url_le": self.url_le,
                "browse_btn": self.browse_btn,
                "apps_btn": self.apps_btn,
            }
        )

    def _form_add_name_row(self) -> None:
        """Add Name row with icon selection button."""
        self.name_le = QLineEdit()
        hl_name = QHBoxLayout()
        hl_name.addWidget(self.name_le, 1)

        self.icon_btn = QPushButton(f"  {tr_common('Icon')}")
        try:
            default_icon = int(app_config.ui.get_default_icon_size())
            self.icon_btn.setIconSize(QSize(default_icon, default_icon))
        except (AttributeError, RuntimeError, ValueError) as e:
            logger.warning("Failed to configure icon button size: %s", e)
        self.adjust_button_width(self.icon_btn)
        hl_name.addWidget(self.icon_btn)

        self.form.addRow(tr_common("Name:"), hl_name)
        self.widgets.update({"name_le": self.name_le, "icon_btn": self.icon_btn})

    def _form_add_profile_row(self) -> None:
        """Add dedicated row for browser profile selection and display."""
        self.profile_label = QLabel(
            QCoreApplication.translate("LinkDialogUI", "Profile:")
        )
        hl_profile = QHBoxLayout()
        hl_profile.setContentsMargins(0, 0, 0, 0)
        hl_profile.setSpacing(8)

        self.profile_le = QLineEdit()
        self.profile_le.setReadOnly(True)
        self.profile_le.setClearButtonEnabled(True)
        self.profile_le.setCursor(Qt.CursorShape.PointingHandCursor)
        self.profile_le.setPlaceholderText(
            QCoreApplication.translate("LinkDialogUI", "No profile")
        )

        self.profile_select_btn = QPushButton(
            QCoreApplication.translate("LinkDialogUI", "Select")
        )
        self.adjust_button_width(self.profile_select_btn)
        self.profile_select_btn.setEnabled(True)

        hl_profile.addWidget(self.profile_le, 1)
        hl_profile.addWidget(self.profile_select_btn, 0)

        self.profile_container = QWidget()
        self.profile_container.setLayout(hl_profile)

        self.form.addRow(self.profile_label, self.profile_container)
        self.widgets.update(
            {
                "profile_label": self.profile_label,
                "profile_container": self.profile_container,
                "profile_le": self.profile_le,
                "profile_select_btn": self.profile_select_btn,
            }
        )

    # Predefined browser launch flags for Web links.
    # Stored as (translation_key, flag_value). Empty flag = open normally.
    _WEB_ARG_PRESETS = [
        (QT_TRANSLATE_NOOP("LinkDialogUI", "Default"),            ""),
        (QT_TRANSLATE_NOOP("LinkDialogUI", "As application"),     "--app={url}"),
        (QT_TRANSLATE_NOOP("LinkDialogUI", "Incognito"),          "--incognito"),
        (QT_TRANSLATE_NOOP("LinkDialogUI", "New window"),         "--new-window"),
        (QT_TRANSLATE_NOOP("LinkDialogUI", "Guest mode"),         "--guest"),
    ]

    def _form_add_args_row(self) -> None:
        """Add row for launch arguments.

        Uses a QStackedWidget with two pages:
        - index 0: editable QComboBox with browser flag presets (Web links)
        - index 1: plain QLineEdit (Program / Script links)
        """
        self.args_label = QLabel(
            QCoreApplication.translate("LinkDialogUI", "Arguments:")
        )

        # Web: non-editable PopupComboBox dropdown with preset flags
        self.args_cb = PopupComboBox()
        self.args_cb.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        for label, value in self._WEB_ARG_PRESETS:
            translated = QCoreApplication.translate("LinkDialogUI", label)
            self.args_cb.addItem(translated, userData=value)

        # Program / Script: clean reliable QLineEdit
        self.args_le = QLineEdit()

        self.args_stack = QStackedWidget()
        self.args_stack.addWidget(self.args_cb)   # index 0 → Web
        self.args_stack.addWidget(self.args_le)   # index 1 → Program/Script

        self.form.addRow(self.args_label, self.args_stack)
        self.widgets.update({
            "args_le":    self.args_le,
            "args_cb":    self.args_cb,
            "args_stack": self.args_stack,
            "args_label": self.args_label,
        })


    def _form_add_hierarchy_section(self) -> None:
        """Add hierarchy combo boxes: Sphere, Section, Category."""
        self.sphere_cb = PopupComboBox()
        self.section_cb = PopupComboBox()
        self.category_cb = PopupComboBox()

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
        """Add notes field to form section."""
        self.notes_te = QTextEdit()
        try:
            self.notes_te.setTabChangesFocus(True)
        except (AttributeError, RuntimeError) as e:
            logger.warning("Failed to set tabChangesFocus for notes_te: %s", e)
        self.notes_frame = InputFrame(self.notes_te)
        self.form.addRow(
            QCoreApplication.translate("LinkDialogUI", "Notes:"), self.notes_frame
        )
        self.widgets["notes_te"] = self.notes_te
        self.widgets["notes_frame"] = self.notes_frame

    def _build_buttons(self, container: QVBoxLayout) -> None:
        """Create bottom row with options (favorite, rotation) and OK/Cancel buttons."""
        bottom_row = QHBoxLayout()
        bottom_row.setContentsMargins(0, 0, 0, 0)
        bottom_row.setSpacing(12)

        # Favorite checkbox
        self.fav_chk = QCheckBox(
            QCoreApplication.translate("LinkDialogUI", "Favorites")
        )
        bottom_row.addWidget(self.fav_chk)

        # Run as administrator checkbox (for Program / Script)
        self.run_as_admin_chk = QCheckBox(
            QCoreApplication.translate("LinkDialogUI", "Run as administrator")
        )
        self.run_as_admin_chk.setVisible(False)
        bottom_row.addWidget(self.run_as_admin_chk)

        bottom_row.addStretch(1)

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

        bottom_row.addWidget(self.button_box)
        container.addLayout(bottom_row)

        self.widgets["fav_chk"] = self.fav_chk
        self.widgets["run_as_admin_chk"] = self.run_as_admin_chk
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
            self._apply_link_type_translations()
        except Exception:
            pass

    def _retranslate_path_row(self):
        """Retranslate path row buttons."""
        try:
            if hasattr(self, "browse_btn") and self.browse_btn is not None:
                self.browse_btn.setText(
                    QCoreApplication.translate("LinkDialogUI", "Browse")
                )
                self.adjust_button_width(self.browse_btn)
            if hasattr(self, "apps_btn") and self.apps_btn is not None:
                self.apps_btn.setText(
                    QCoreApplication.translate("LinkDialogUI", "Apps")
                )
                self.adjust_button_width(self.apps_btn)
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
                self.icon_btn.setText(f"  {tr_common('Icon')}")
                self.adjust_button_width(self.icon_btn)
        except Exception:
            pass

    def _retranslate_args_row(self):
        """Retranslate arguments row label and preset options."""
        try:
            if hasattr(self, "args_label") and self.args_label is not None:
                self.args_label.setText(
                    QCoreApplication.translate("LinkDialogUI", "Arguments:")
                )
            if hasattr(self, "args_cb") and self.args_cb is not None:
                for idx, (label, _) in enumerate(self._WEB_ARG_PRESETS):
                    if idx < self.args_cb.count():
                        self.args_cb.setItemText(
                            idx, QCoreApplication.translate("LinkDialogUI", label)
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

    def _retranslate_profile_row(self):
        """Retranslate profile row label, placeholder, and button."""
        try:
            if hasattr(self, "profile_label") and self.profile_label is not None:
                self.profile_label.setText(
                    QCoreApplication.translate("LinkDialogUI", "Profile:")
                )
            if hasattr(self, "profile_le") and self.profile_le is not None:
                self.profile_le.setPlaceholderText(
                    QCoreApplication.translate("LinkDialogUI", "No profile")
                )
            if hasattr(self, "profile_select_btn") and self.profile_select_btn is not None:
                self.profile_select_btn.setText(
                    QCoreApplication.translate("LinkDialogUI", "Select")
                )
                self.adjust_button_width(self.profile_select_btn)
        except Exception:
            pass

    def _retranslate_notes_and_favorites(self):
        """Retranslate notes label and options checkboxes."""
        try:
            if hasattr(self, "form") and self.form is not None:
                field = getattr(self, "notes_frame", getattr(self, "notes_te", None))
                if field is not None:
                    notes_label = self.form.labelForField(field)
                    if notes_label is not None:
                        notes_label.setText(
                            QCoreApplication.translate("LinkDialogUI", "Notes:")
                        )
            if hasattr(self, "fav_chk") and self.fav_chk is not None:
                self.fav_chk.setText(
                    QCoreApplication.translate("LinkDialogUI", "Favorites")
                )
            if hasattr(self, "run_as_admin_chk") and self.run_as_admin_chk is not None:
                self.run_as_admin_chk.setText(
                    QCoreApplication.translate("LinkDialogUI", "Run as administrator")
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
        self._retranslate_profile_row()
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
        label_key = link_type_label_source(code)
        translated = QCoreApplication.translate("LinkDialogUI", label_key)
        if translated != label_key or not original or original == label_key:
            return translated
        # Fallback: try translating original value; if unavailable, return original
        translated_original = (
            QCoreApplication.translate("LinkDialogUI", original) if original else ""
        )
        return translated_original if translated_original else original
