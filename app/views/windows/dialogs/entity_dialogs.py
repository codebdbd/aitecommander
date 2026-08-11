from __future__ import annotations

import logging
from pathlib import Path

from PyQt6.QtCore import (
    QCoreApplication,
    QRunnable,
    QSize,
    Qt,
    QUrl,
    pyqtSignal,
    pyqtSlot,
)
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.config_data.runtime_config import runtime_app_config as app_config
from app.controllers.business import StructureBusinessLogic
from app.controllers.ui.theme_controller import ThemeController
from app.core.worker_manager import WorkerManager
from app.services.theme_import_service import (
    ThemeConflictError,
    ThemeImportError,
    ThemeImportService,
)
from app.services.theme_registry import theme_registry
from app.utils.i18n.common import tr as tr_common
from app.utils.ui.icon.icon_operations.creators import create_icon_from_path
from app.utils.ui.icon.path_service import icon_path_service
from app.utils.ui.icon.icon_resolver import (
    resolve_category_icon_path,
    resolve_section_icon_path,
)
from app.utils.ui.qt.combo_helpers import (
    PopupComboBox,
    add_combo_mapping_item,
    select_combo_data,
)
from app.views.widgets.language_selector import LanguageSelector
from app.views.windows.dialogs.link_dialog.icon_utils import get_cached_icon_with_fallback

from .base_dialog import BaseDialog

logger = logging.getLogger(__name__)


def _combo_icon_loader(entity_type: str):
    def _load(icon_path: str):
        return get_cached_icon_with_fallback(icon_path, entity_type)

    return _load


def _populate_spheres_common(
    structure_business: StructureBusinessLogic, sphere_cb: QComboBox
) -> None:
    """Populate the sphere combobox with available options.
    The list is not cleared to preserve caller expectations.
    """
    spheres = structure_business.get_spheres()
    for sphere in spheres:
        if not isinstance(sphere, dict):
            continue
        add_combo_mapping_item(
            sphere_cb,
            sphere,
            icon_key="icon_path",
            icon_loader=_combo_icon_loader("sphere"),
        )


def _tr(context: str, text: str) -> str:
    return QCoreApplication.translate(context, text)


class BaseEntityDialog(BaseDialog):
    """Base dialog for entities that have a name and an icon (section, category)."""

    _TR_CONTEXT = "BaseEntityDialog"

    @classmethod
    def _translate(cls, text: str) -> str:
        """Translate text using the shared base dialog context."""
        return _tr(cls._TR_CONTEXT, text)

    def __init__(
        self,
        structure_business: StructureBusinessLogic,
        entity_name: str,
        entity_id: int | None = None,
        parent=None,
    ):
        # Assign critical attributes before dialog initialization so that
        # `ReTranslatable.__init__` (triggered via the MRO chain) can safely
        # access them during the initial `retranslateUi()` call.
        self.structure_business = structure_business
        self.entity_id = entity_id
        self.entity_name = entity_name  # e.g., 'section', 'category'
        self._result = None
        self._icon_filename = f"{entity_name}.png"
        self._button_box: QDialogButtonBox | None = None
        self._name_label: QLabel | None = None
        self._name_field_widget: QWidget | None = None
        # Ensure attributes accessed during initial retranslateUi() exist
        self.icon_btn: QPushButton | None = None
        self.name_le: QLineEdit | None = None
        self._retranslation_initialized = False

        super().__init__(parent)

    def _init_common_ui(self, form_layout: QFormLayout):
        """Initialize common UI elements: name input and icon button."""
        self.name_le = QLineEdit()
        # Save on Enter only when the name field is not empty (without default button)
        try:
            self.name_le.returnPressed.connect(self._on_return_pressed)
        except Exception:
            logger.debug(
                "BaseEntityDialog: failed to connect returnPressed handler",
                exc_info=True,
            )
        self.icon_btn = QPushButton()
        self.icon_btn.setFixedWidth(app_config.ui.get_fixed_button_width())
        # Use centralized dialog icon size from UIConfig
        self.icon_btn.setIconSize(QSize(*app_config.ui.get_dialog_icon_size()))
        self.icon_btn.setIcon(
            create_icon_from_path(
                str(icon_path_service.get_ui_icons_dir() / self._icon_filename)
            )
        )
        self.icon_btn.clicked.connect(self._choose_icon)

        name_container = QWidget()
        name_layout = QHBoxLayout(name_container)
        name_layout.setContentsMargins(0, 0, 0, 0)
        name_layout.setSpacing(app_config.ui.get_entity_dialog_name_spacing())
        name_layout.addWidget(self.name_le, 1)
        name_layout.addWidget(self.icon_btn)

        if self._name_label is None:
            self._name_label = QLabel()
        form_layout.addRow(self._name_label, name_container)
        self._name_field_widget = name_container

    def _create_button_box(self):
        """Create and return a `QDialogButtonBox`."""
        bb = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._button_box = bb
        ok_btn = bb.button(QDialogButtonBox.StandardButton.Ok)
        ok_btn.setFixedWidth(app_config.ui.get_fixed_button_width())
        # Do not mark the button as default to avoid default highlighting without focus
        try:
            ok_btn.setDefault(False)
            ok_btn.setAutoDefault(False)
            # The button should receive focus only via Tab, not automatically when shown
            ok_btn.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        except Exception:
            logger.debug(
                "BaseEntityDialog: failed to adjust Ok button defaults/focus",
                exc_info=True,
            )

        cancel_btn = bb.button(QDialogButtonBox.StandardButton.Cancel)
        cancel_btn.setFixedWidth(app_config.ui.get_fixed_button_width())
        # Remove default/autoDefault from Cancel so buttons do not grab focus by default
        try:
            cancel_btn.setDefault(False)
            cancel_btn.setAutoDefault(False)
            cancel_btn.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        except Exception:
            logger.debug(
                "BaseEntityDialog: failed to adjust Cancel button defaults/focus",
                exc_info=True,
            )

        # Disable the Save button while the name is empty; update as text changes
        try:
            name_text = self.name_le.text().strip() if hasattr(self, "name_le") else ""
            ok_btn.setEnabled(bool(name_text))
            if hasattr(self, "name_le"):
                self.name_le.textChanged.connect(
                    lambda _t: ok_btn.setEnabled(bool(self.name_le.text().strip()))
                )
        except Exception:
            logger.debug(
                "BaseEntityDialog: failed to wire name_le textChanged to Ok button enable",
                exc_info=True,
            )

        bb.accepted.connect(self._on_accept)
        bb.rejected.connect(self.reject)
        return bb

    def _finalize_translations(self) -> None:
        if not self._retranslation_initialized:
            # Call retranslateUi() now that all attributes are initialized
            if hasattr(self, "retranslateUi"):
                self.retranslateUi()
            self._retranslation_initialized = True

    # Language changes are handled via BaseDialog(ReTranslatable)

    def retranslateUi(self) -> None:
        if self.entity_name == "section":
            title = (
                tr_common("Edit section")
                if self.entity_id
                else tr_common("Add section")
            )
        elif self.entity_name == "category":
            title = (
                tr_common("Edit category")
                if self.entity_id
                else tr_common("Add category")
            )
        else:
            title_verb = (
                self._translate("Edit") if self.entity_id else self._translate("Add")
            )
            title_noun_map = {
                "section": self._translate("section"),
                "category": self._translate("category"),
            }
            title_noun = title_noun_map.get(self.entity_name, self._translate("entity"))
            title = f"{title_verb} {title_noun}"
        self.setWindowTitle(title)

        if self._name_label is not None:
            self._name_label.setText(tr_common("Name:"))
        if self.icon_btn is not None:
            self.icon_btn.setText(tr_common("Icon"))

        if self._button_box is not None:
            ok_btn = self._button_box.button(QDialogButtonBox.StandardButton.Ok)
            cancel_btn = self._button_box.button(QDialogButtonBox.StandardButton.Cancel)
            if ok_btn is not None:
                ok_btn.setText(tr_common("Save"))
            if cancel_btn is not None:
                cancel_btn.setText(tr_common("Cancel"))

    def showEvent(self, event):
        """Force focus to the name field when the dialog appears to prevent button focus."""
        super().showEvent(event)
        try:
            self.name_le.setFocus(Qt.FocusReason.ActiveWindowFocusReason)
        except Exception:
            logger.debug("BaseEntityDialog.showEvent: setFocus failed", exc_info=True)
        # After applying uniform height in `BaseDialog`, adjust the size to content
        try:
            self.adjustSize()
        except Exception:
            logger.debug("BaseEntityDialog.showEvent: adjustSize failed", exc_info=True)

    def _on_return_pressed(self):
        """Handle Enter presses on the name field, saving only when valid."""
        try:
            if hasattr(self, "name_le") and self.name_le.text().strip():
                # Delegate detailed validation to `_on_accept`; subclasses verify additional fields
                self._on_accept()
        except Exception:
            logger.debug("BaseEntityDialog._on_return_pressed failed", exc_info=True)

    def _get_icon_path(self, icon_filename: str) -> Path:
        """Return explicit icon path with type-specific fallback."""
        # Try user icons first
        link_icon_path = icon_path_service.get_user_icons_dir() / icon_filename
        if link_icon_path.exists():
            return link_icon_path
        # Try UI icons
        ui_path = icon_path_service.get_ui_icons_dir() / icon_filename
        if ui_path.exists():
            return ui_path
        # Fallback to type-specific default icon
        if self.entity_name == "section":
            fallback = resolve_section_icon_path(icon_filename)
        elif self.entity_name == "category":
            fallback = resolve_category_icon_path(icon_filename)
        else:
            fallback = ""
        return Path(fallback) if fallback else ui_path

    def _choose_icon(self):
        """Open icon picker immediately; cancel resets to the default entity icon."""
        try:
            from app.utils.ui.icon.selection import choose_icon_and_copy

            user_icons_dir = icon_path_service.get_user_icons_dir()
            fname, icon = choose_icon_and_copy(self, user_icons_dir)
            if not fname or not icon:
                self._icon_filename = f"{self.entity_name}.png"
                if self.icon_btn is not None:
                    self.icon_btn.setIcon(
                        create_icon_from_path(str(self._get_icon_path(self._icon_filename)))
                    )
                return

            self.icon_btn.setIcon(icon)
            self._icon_filename = fname

        except Exception as e:
            self.show_error(
                self._translate("Unable to set selected icon."),
                self._translate("Icon selection error"),
                informative_text=self._translate(
                    "Choose another image file (.png, .ico, .jpg, .svg) and try again."
                ),
                details=str(e),
            )

    def _on_accept_base(self) -> dict | None:
        """Perform base validation and collect name/icon data, returning ``None`` on error."""
        if self.name_le is None:
            return None
        name = self.name_le.text().strip()
        if not name:
            self.show_warning(
                self._translate("Name cannot be empty."),
                self._translate("Invalid input"),
                informative_text=self._translate("Please provide a name for the entity."),
            )
            return None
        return {"name": name, "icon_path": self._icon_filename}

    def get_result(self):
        return self._result

    def _populate_spheres(self):
        """Populate the spheres combobox (used by subclasses)."""
        _populate_spheres_common(self.structure_business, self.sphere_cb)


class SectionDialog(BaseEntityDialog):
    def __init__(
        self,
        structure_business: StructureBusinessLogic,
        section_id: int | None = None,
        default_sphere_id: int | None = None,
        parent=None,
    ):
        super().__init__(structure_business, "section", section_id, parent)
        self.default_sphere_id = default_sphere_id
        # Fix width only; height is determined by content
        self.setFixedWidth(app_config.ui.get_entity_dialog_fixed_width())
        self._init_ui()
        self._finalize_translations()
        # Focus the name field on open
        try:
            if self.name_le is not None:
                self.name_le.setFocus()
        except Exception:
            logger.debug("SectionDialog.__init__: setFocus failed", exc_info=True)
        if section_id:
            self._load_section()
        # Adjust height to content after initialization and optional data load
        try:
            self.adjustSize()
        except Exception:
            logger.debug("SectionDialog: adjustSize failed", exc_info=True)

    def _init_ui(self):
        vbox = QVBoxLayout(self)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self._form_layout = form

        # Name field in the first row
        self._init_common_ui(form)

        # Sphere selection afterward
        self.sphere_cb = PopupComboBox()
        self._populate_spheres()
        form.addRow(self.tr("Sphere:"), self.sphere_cb)

        if self.default_sphere_id is not None and self.entity_id is None:
            self._set_sphere_selection(self.default_sphere_id)

        vbox.addLayout(form)
        vbox.addWidget(self._create_button_box())

    def _set_sphere_selection(self, sphere_id: int):
        """Select a sphere by its ID."""
        select_combo_data(
            self.sphere_cb,
            current_data=sphere_id,
            fallback_to_first=False,
        )

    def _load_section(self):
        """Load section data for editing."""
        section_data = self.structure_business.get_section_for_editing(self.entity_id)

        if not section_data:
            self.show_warning(
                self.tr("Section not found."),
                self.tr("Section unavailable"),
                informative_text=self.tr("The section might have been deleted. ID: %1")
                % self.entity_id,
            )
            return

        self.name_le.setText(section_data["name"])
        self._set_sphere_selection(section_data["sphere_id"])

        icon = section_data["icon_path"] or f"{self.entity_name}.png"
        self._icon_filename = icon
        icon_path = self._get_icon_path(icon)
        self.icon_btn.setIcon(create_icon_from_path(str(icon_path)))

    def _on_accept(self):
        base_result = self._on_accept_base()
        if base_result is None:
            return

        sphere_id = self.sphere_cb.currentData()
        if sphere_id is None:
            self.show_warning(
                self.tr("Sphere not selected."),
                self.tr("Sphere selection required"),
                informative_text=self.tr(
                    'Choose a sphere from the list and press "Save".'
                ),
            )
            return

        # Check for duplicate section name in sphere
        section_name = base_result["name"]
        try:
            if self.structure_business.has_duplicate_section(
                sphere_id, section_name, exclude_id=self.entity_id
            ):
                self.show_warning(
                    self.tr("Section with this name already exists in the selected sphere."),
                    self.tr("Duplicate section name"),
                    informative_text=self.tr(
                        "Please choose a different name or edit the existing section."
                    ),
                )
                return
        except Exception as e:
            logger.warning("Failed to check duplicate section: %s", e, exc_info=True)
            # Continue anyway - DB constraint will catch it

        self._result = base_result
        self._result["sphere_id"] = sphere_id
        self.accept()

    def retranslateUi(self) -> None:
        super().retranslateUi()
        if hasattr(self, "_form_layout") and self._form_layout is not None:
            label = self._form_layout.labelForField(self.sphere_cb)
            if label is not None:
                label.setText(self.tr("Sphere:"))


class CategoryDialog(BaseEntityDialog):
    def __init__(
        self,
        structure_business: StructureBusinessLogic,
        category_id: int | None = None,
        parent=None,
    ):
        super().__init__(structure_business, "category", category_id, parent)
        # Fix width only; height is determined by content
        self.setFixedWidth(app_config.ui.get_entity_dialog_fixed_width())
        self._init_ui()
        self._finalize_translations()
        # Focus the name field on open
        try:
            if self.name_le is not None:
                self.name_le.setFocus()
        except Exception:
            pass
        if category_id:
            self._load_category()
        # Adjust height to content after initialization and potential data load
        try:
            self.adjustSize()
        except Exception:
            logger.debug("CategoryDialog: adjustSize failed", exc_info=True)

    def _init_ui(self):
        vbox = QVBoxLayout(self)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self._form_layout = form

        # Name field in the first row
        self._init_common_ui(form)

        # Then sphere and section selectors
        self.sphere_cb = PopupComboBox()
        self._populate_spheres()
        self.sphere_cb.currentIndexChanged.connect(self._update_sections)
        form.addRow(self.tr("Sphere:"), self.sphere_cb)

        self.section_cb = PopupComboBox()
        form.addRow(self.tr("Section:"), self.section_cb)
        self._update_sections()

        vbox.addLayout(form)
        vbox.addWidget(self._create_button_box())

    def _update_sections(self):
        """Refresh section list when the sphere changes."""
        sphere_id = self.sphere_cb.currentData()
        if sphere_id is None:
            return

        self.section_cb.clear()
        try:
            sections = self.structure_business.get_sections(sphere_id)
            for section in sections:
                # Follow the same pattern as in `LinkDialog`: add icon when available
                if not isinstance(section, dict):
                    continue
                add_combo_mapping_item(
                    self.section_cb,
                    section,
                    icon_key="icon_path",
                    icon_loader=_combo_icon_loader("section"),
                )
        except Exception as e:
            self.show_error(
                self.tr("Failed to load sections."),
                self.tr("Error loading sections"),
                informative_text=self.tr("Check database connection and try again."),
                details=str(e),
            )

    def _load_category(self):
        """Load category data for editing."""
        category_data = self.structure_business.get_category_for_editing(self.entity_id)

        if not category_data:
            self.show_warning(
                self.tr("Category not found."),
                self.tr("Category unavailable"),
                informative_text=self.tr("The category might have been deleted. ID: %1")
                % self.entity_id,
            )
            return

        self.name_le.setText(category_data["name"])
        section_id = category_data["section_id"]

        # Retrieve hierarchy via business logic
        hierarchy = self.structure_business.get_category_hierarchy(self.entity_id)

        if hierarchy:
            sphere_id = hierarchy["sphere_id"]
            # Select the stored sphere
            if (
                select_combo_data(
                    self.sphere_cb,
                    current_data=sphere_id,
                    fallback_to_first=False,
                )
                >= 0
            ):
                self._update_sections()
                # Select the stored section
                select_combo_data(
                    self.section_cb,
                    current_data=section_id,
                    fallback_to_first=False,
                )

        # Set icon from stored data
        icon = category_data["icon_path"] or f"{self.entity_name}.png"
        self._icon_filename = icon
        icon_path = self._get_icon_path(icon)
        self.icon_btn.setIcon(create_icon_from_path(str(icon_path)))

    def _on_accept(self):
        base_result = self._on_accept_base()
        if base_result is None:
            return

        section_id = self.section_cb.currentData()
        if section_id is None:
            self.show_warning(
                self.tr("Section not selected."),
                self.tr("Section selection required"),
                informative_text=self.tr(
                    'Choose a section from the list and press "Save".'
                ),
            )
            return

        self._result = base_result
        self._result["section_id"] = section_id
        self.accept()

    def retranslateUi(self) -> None:
        super().retranslateUi()
        if hasattr(self, "_form_layout") and self._form_layout is not None:
            sphere_label = self._form_layout.labelForField(self.sphere_cb)
            if sphere_label is not None:
                sphere_label.setText(self.tr("Sphere:"))
            section_label = self._form_layout.labelForField(self.section_cb)
            if section_label is not None:
                section_label.setText(self.tr("Section:"))

    def set_result(self, data: dict):
        """Populate dialog state from provided data dictionary."""
        if "section_id" not in data:
            return

        section_id = data.get("section_id")
        if not section_id:
            return

        section_data = self.structure_business.get_section_for_editing(section_id)

        if section_data:
            sphere_id = section_data["sphere_id"]
            if (
                select_combo_data(
                    self.sphere_cb,
                    current_data=sphere_id,
                    fallback_to_first=False,
                )
                >= 0
            ):
                self._update_sections()
                select_combo_data(
                    self.section_cb,
                    current_data=section_id,
                    fallback_to_first=False,
                )


class NoteDialog(BaseDialog):
    def __init__(self, link: dict, parent=None):
        self.link = link
        self._button_box: QDialogButtonBox | None = None
        self.notes_te: QTextEdit | None = None

        super().__init__(parent)
        width, height = app_config.ui.get_notes_dialog_size()
        self.resize(width, height)
        self._init_ui()

        # Translate after widgets are created
        self.retranslateUi()

    def _init_ui(self):
        """Initialize the notes dialog UI."""
        vbox = QVBoxLayout(self)

        self.notes_te = QTextEdit(self.link.get("notes", ""))
        try:
            self.notes_te.setTabChangesFocus(True)
        except Exception:
            pass
        vbox.addWidget(self.notes_te)

        bb = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        bb.accepted.connect(self._on_accept)
        bb.rejected.connect(self.reject)
        vbox.addWidget(bb)
        self._button_box = bb

    def retranslateUi(self) -> None:
        self.setWindowTitle(tr_common("Notes"))
        if self.notes_te is not None:
            self.notes_te.setPlaceholderText(self.tr("Enter notes here"))
        if self._button_box is not None:
            ok_btn = self._button_box.button(QDialogButtonBox.StandardButton.Ok)
            cancel_btn = self._button_box.button(QDialogButtonBox.StandardButton.Cancel)
            if ok_btn is not None:
                ok_btn.setText(tr_common("Save"))
            if cancel_btn is not None:
                cancel_btn.setText(tr_common("Cancel"))

    def _on_accept(self):
        """Update notes in the link object."""
        try:
            notes = self.notes_te.toPlainText()
            self.link["notes"] = notes
            self.accept()
        except Exception as e:
            self.show_error(
                self.tr("Failed to update notes."),
                self.tr("Notes update error"),
                informative_text=self.tr(
                    "Close and reopen the dialog, then try again."
                ),
                details=str(e),
            )


class SettingsDialog(BaseDialog):
    def __init__(self, settings, theme_ctrl: ThemeController, parent=None):
        self.settings = settings
        self.theme_ctrl = theme_ctrl
        self._button_box: QDialogButtonBox | None = None
        self.language_selector: LanguageSelector | None = None
        self.theme_combo: QComboBox | None = None
        self.theme_import_btn: QPushButton | None = None
        self.remove_theme_btn: QPushButton | None = None
        self._form_layout: QFormLayout | None = None
        self._theme_actions_row: QWidget | None = None
        self.font_size_combo: QComboBox | None = None
        self.max_backups_combo: QComboBox | None = None
        self._theme_importer = ThemeImportService()

        super().__init__(parent)
        self.setObjectName("SettingsDialog")
        try:
            self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        except AttributeError:
            pass
        width, height = app_config.ui.get_settings_dialog_size()
        self.resize(width, height)
        self._init_ui()
        self.retranslateUi()

    def _init_ui(self):
        """Initialize the settings dialog UI as a single-page form."""
        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(*app_config.ui.get_settings_dialog_margins())
        vbox.setSpacing(app_config.ui.get_settings_dialog_spacing())

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setHorizontalSpacing(
            app_config.ui.get_settings_dialog_form_horizontal_spacing()
        )
        form.setVerticalSpacing(
            app_config.ui.get_settings_dialog_form_vertical_spacing()
        )
        self._form_layout = form

        # Language
        self.language_selector = LanguageSelector(self)
        form.addRow(self.tr("Language:"), self.language_selector)

        # Theme
        self.theme_combo = PopupComboBox()
        self._refresh_theme_list()
        self.theme_combo.currentIndexChanged.connect(self._on_theme_selection_changed)
        form.addRow(self.tr("Theme:"), self.theme_combo)

        actions_row = QWidget()
        self._theme_actions_row = actions_row
        actions_layout = QHBoxLayout(actions_row)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(app_config.ui.get_settings_dialog_actions_spacing())

        self.theme_import_btn = QPushButton(self)
        self.theme_import_btn.clicked.connect(self._on_import_theme)
        actions_layout.addWidget(self.theme_import_btn)

        self.remove_theme_btn = QPushButton(self)
        self.remove_theme_btn.clicked.connect(self._on_remove_theme)
        actions_layout.addWidget(self.remove_theme_btn)

        actions_layout.addStretch(1)
        form.addRow(self.tr("Theme actions:"), actions_row)

        # Font size
        self.font_size_combo = PopupComboBox()
        self.font_size_combo.addItems([str(i) for i in range(9, 15)])
        try:
            current_font_size = int(self.settings.get_font_size())
            if 9 <= current_font_size <= 14:
                self.font_size_combo.setCurrentIndex(current_font_size - 9)
            else:
                self.font_size_combo.setCurrentIndex(3)
        except Exception:
            self.font_size_combo.setCurrentIndex(3)
        form.addRow(self.tr("Font size:"), self.font_size_combo)

        # Max backups
        self.max_backups_combo = PopupComboBox()
        self.max_backups_combo.addItems([str(i) for i in range(1, 11)])
        try:
            current = int(self.settings.get_max_backups())
            if 1 <= current <= 10:
                self.max_backups_combo.setCurrentIndex(current - 1)
            else:
                self.max_backups_combo.setCurrentIndex(9)
        except Exception:
            self.max_backups_combo.setCurrentIndex(9)
        form.addRow(self.tr("Max backups:"), self.max_backups_combo)

        vbox.addLayout(form)

        # Buttons
        bb = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        bb.accepted.connect(self._on_accept)
        bb.rejected.connect(self.reject)
        vbox.addWidget(bb)
        self._button_box = bb
    
    
    def _get_available_themes(self):
        """Get available themes from parent window."""
        if hasattr(self.parent(), 'get_available_themes'):
            return self.parent().get_available_themes()
        return [("light", "Light"), ("dark", "Dark")]

    def _refresh_theme_list(self, *, keep_selection: bool = True) -> None:
        if self.theme_combo is None:
            return
        current = self.theme_combo.currentData() if keep_selection else None
        preferred = self.settings.get_theme() if hasattr(self, "settings") else None
        if self.theme_ctrl:
            self.theme_ctrl.refresh_themes()
        themes = self._get_available_themes()
        self.theme_combo.blockSignals(True)
        self.theme_combo.clear()
        for theme_id, theme_name in themes:
            self.theme_combo.addItem(theme_name, theme_id)
        select_combo_data(
            self.theme_combo,
            current_data=current if keep_selection else None,
            preferred_data=preferred,
            fallback_to_first=bool(themes),
        )
        self.theme_combo.blockSignals(False)
        self._update_remove_button_state()

    def _on_theme_selection_changed(self) -> None:
        self._update_remove_button_state()

    def _update_remove_button_state(self) -> None:
        if self.remove_theme_btn is None or self.theme_combo is None:
            return
        theme_id = self.theme_combo.currentData()
        can_remove = bool(theme_id and theme_registry.is_user_theme(str(theme_id)))
        self.remove_theme_btn.setEnabled(can_remove)

    def _on_import_theme(self) -> None:
        if self.theme_combo is None:
            return
        path, _ = QFileDialog.getOpenFileName(
            self,
            self.tr("Import theme"),
            "",
            self.tr("Theme packages (*.zip);;All files (*)"),
        )
        if not path:
            return
        try:
            theme = self._theme_importer.import_theme(Path(path), conflict_policy="prompt")
        except ThemeConflictError as conflict:
            msg = QMessageBox(self)
            msg.setWindowTitle(tr_common("Theme already exists"))
            msg.setText(
                self.tr("Theme '%1' already exists. What would you like to do?")
                .replace("%1", conflict.theme_id)
            )
            replace_btn = msg.addButton(self.tr("Replace"), QMessageBox.ButtonRole.AcceptRole)
            rename_btn = msg.addButton(self.tr("Rename"), QMessageBox.ButtonRole.ActionRole)
            msg.addButton(QMessageBox.StandardButton.Cancel)
            msg.exec()
            clicked = msg.clickedButton()
            if clicked == replace_btn:
                theme = self._theme_importer.import_theme(
                    Path(path), conflict_policy="overwrite"
                )
            elif clicked == rename_btn:
                theme = self._theme_importer.import_theme(
                    Path(path), conflict_policy="rename"
                )
            else:
                return
        except ThemeImportError as exc:
            self.show_error(
                self.tr("Failed to import theme."),
                self.tr("Theme import error"),
                details=str(exc),
            )
            return

        self._refresh_theme_list(keep_selection=False)
        if theme and self.theme_combo is not None:
            select_combo_data(
                self.theme_combo,
                current_data=theme.theme_id,
                fallback_to_first=False,
            )

    def _on_open_themes_dir(self) -> None:
        themes_dir = app_config.paths.get_user_themes_dir()
        themes_dir.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(themes_dir)))

    def _on_remove_theme(self) -> None:
        if self.theme_combo is None:
            return
        theme_id = self.theme_combo.currentData()
        if not theme_id:
            return
        theme_id = str(theme_id)
        if not theme_registry.is_user_theme(theme_id):
            return
        confirm = self.show_custom_dialog(
            QMessageBox.Icon.Question,
            self.tr("Remove theme"),
            self.tr("Remove theme '%1'?").replace("%1", theme_id),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        try:
            self._theme_importer.remove_theme(theme_id)
        except ThemeImportError as exc:
            self.show_error(
                self.tr("Failed to remove theme."),
                self.tr("Theme remove error"),
                details=str(exc),
            )
            return

        if self.settings.get_theme() == theme_id:
            fallback = theme_registry.get_default_theme_id()
            self.settings.set_theme(fallback)
            if self.theme_ctrl:
                self.theme_ctrl.clear_cache()
                self.theme_ctrl.apply(fallback)

        self._refresh_theme_list(keep_selection=False)

    def retranslateUi(self) -> None:
        self.setWindowTitle(tr_common("Settings"))

        if self._form_layout is not None:
            if self.language_selector is not None:
                label = self._form_layout.labelForField(self.language_selector)
                if label is not None:
                    label.setText(self.tr("Language:"))
            if self.theme_combo is not None:
                label = self._form_layout.labelForField(self.theme_combo)
                if label is not None:
                    label.setText(self.tr("Theme:"))
            if self.font_size_combo is not None:
                label = self._form_layout.labelForField(self.font_size_combo)
                if label is not None:
                    label.setText(self.tr("Font size:"))
            if self.max_backups_combo is not None:
                label = self._form_layout.labelForField(self.max_backups_combo)
                if label is not None:
                    label.setText(self.tr("Max backups:"))

        if self.theme_import_btn is not None:
            self.theme_import_btn.setText(self.tr("Import theme..."))
        if self.remove_theme_btn is not None:
            self.remove_theme_btn.setText(self.tr("Remove theme"))

        if self._form_layout is not None and self._theme_actions_row is not None:
            label = self._form_layout.labelForField(self._theme_actions_row)
            if label is not None:
                label.setText(self.tr("Theme actions:"))

        if self.theme_combo is not None:
            # Refresh theme names to match current language while preserving selection.
            self._refresh_theme_list(keep_selection=True)

        # Retranslate buttons
        if self._button_box is not None:
            ok_btn = self._button_box.button(QDialogButtonBox.StandardButton.Ok)
            cancel_btn = self._button_box.button(QDialogButtonBox.StandardButton.Cancel)
            if ok_btn is not None:
                ok_btn.setText(tr_common("Save"))
            if cancel_btn is not None:
                cancel_btn.setText(tr_common("Cancel"))

    def _on_accept(self):
        """Persist settings changes."""
        try:
            # General tab
            if self.theme_combo is not None:
                theme_id = self.theme_combo.currentData()
                if theme_id and theme_id != self.settings.get_theme():
                    self.settings.set_theme(theme_id)
                    if self.theme_ctrl:
                        self.theme_ctrl.clear_cache()
                        self.theme_ctrl.apply(theme_id)
            
            if self.font_size_combo is not None:
                font_size = int(self.font_size_combo.currentText())
                self.settings.set_font_size(font_size)
            
            # Backup tab
            if self.max_backups_combo is not None:
                max_backups = int(self.max_backups_combo.currentText())
                self.settings.set_max_backups(max_backups)
            
            # Apply font size to tree and table widgets
            if self.font_size_combo is not None:
                font_size = int(self.font_size_combo.currentText())
                if self.parent() and hasattr(self.parent(), 'apply_font_size_to_content'):
                    try:
                        self.parent().apply_font_size_to_content(font_size)
                    except Exception as e:
                        logger.debug("Failed to apply font size to content: %s", e)

            self.accept()

        except Exception as e:
            self.show_error(
                self.tr("Failed to save settings."),
                self.tr("Settings save error"),
                informative_text=self.tr("Check the values and try again."),
                details=str(e),
            )


class ChromeProfilesWorker(QRunnable):
    """Worker that loads Chrome profiles asynchronously."""

    def __init__(self, callback):
        super().__init__()
        self.callback = callback

    @pyqtSlot()
    def run(self):
        """Retrieve Chrome profiles in a background thread."""
        try:
            from app.utils.browser.browser_profiles import get_profile_manager

            manager = get_profile_manager()
            profiles = manager.get_browser_profiles("chrome")
            self.callback(profiles)
        except ImportError:
            self.callback([])  # Return empty list when module is unavailable
        except Exception:
            self.callback([])  # Return empty list on any error


class ChromeProfileDialog(BaseDialog):
    profiles_loaded = pyqtSignal(list)
    """Dialog to select Chrome profiles with bulk controls and save/cancel actions."""

    def __init__(self, parent=None):
        self.result = []
        self.profile_checkboxes = []
        self._title_label: QLabel | None = None
        self._button_box: QDialogButtonBox | None = None
        self.select_all_btn: QPushButton | None = None
        self.deselect_all_btn: QPushButton | None = None
        self.refresh_btn: QPushButton | None = None

        super().__init__(parent)
        self.setModal(True)
        self._setup_size()
        self._setup_ui()

        # Translate after widgets are created
        self.retranslateUi()
        self.profiles_loaded.connect(self._populate_profiles)
        self._start_profiles_loading()

    # Language changes are handled via BaseDialog(ReTranslatable)

    def _setup_size(self):
        """Set the dialog size based on scale factor."""
        base_width, base_height = app_config.ui.get_chrome_profile_dialog_base_size()
        scale = getattr(self, "scale_factor", 1.0)
        self.resize(int(base_width * scale), int(base_height * scale))

    def _setup_ui(self):
        """Set up dialog controls and layout."""
        main_layout = QVBoxLayout(self)

        self._title_label = QLabel()
        main_layout.addWidget(self._title_label)

        # List of profiles with checkboxes
        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        try:
            for bar in (self.scroll.verticalScrollBar(), self.scroll.horizontalScrollBar()):
                if bar is None:
                    continue
        except Exception:
            logger.debug("ChromeProfileDialog: failed to normalize scrollbars", exc_info=True)
        try:
            self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        except Exception:
            logger.debug("ChromeProfileDialog: failed to set scrollbar policies", exc_info=True)
        scroll_content = QWidget(self.scroll)
        self.profiles_layout = QVBoxLayout(scroll_content)
        self.profiles_layout.setContentsMargins(0, 0, 0, 0)
        self.profiles_layout.setSpacing(0)
        self.scroll.setWidget(scroll_content)
        main_layout.addWidget(self.scroll, 1)

        # "Select all" / "Clear all" buttons
        btns_layout = QHBoxLayout()

        self.select_all_btn = QPushButton()
        self.select_all_btn.clicked.connect(self._on_select_all)
        btns_layout.addWidget(self.select_all_btn)

        self.deselect_all_btn = QPushButton()
        self.deselect_all_btn.clicked.connect(self._on_deselect_all)
        btns_layout.addWidget(self.deselect_all_btn)

        main_layout.addLayout(btns_layout)

        # Refresh profiles button
        self.refresh_btn = QPushButton()
        self.refresh_btn.clicked.connect(self._start_profiles_loading)
        main_layout.addWidget(self.refresh_btn)

        # Bottom action buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        main_layout.addWidget(button_box)
        self._button_box = button_box

    def retranslateUi(self) -> None:
        self.setWindowTitle(tr_common("Select Chrome profile"))
        if self._title_label is not None:
            self._title_label.setText(self.tr("Choose a Chrome profile:"))
        if self.select_all_btn is not None:
            self.select_all_btn.setText(self.tr("Select all"))
        if self.deselect_all_btn is not None:
            self.deselect_all_btn.setText(self.tr("Deselect all"))
        if self.refresh_btn is not None:
            self.refresh_btn.setText(self.tr("Refresh profiles"))
        if self._button_box is not None:
            save_btn = self._button_box.button(QDialogButtonBox.StandardButton.Save)
            cancel_btn = self._button_box.button(QDialogButtonBox.StandardButton.Cancel)
            if save_btn is not None:
                save_btn.setText(tr_common("Save"))
            if cancel_btn is not None:
                cancel_btn.setText(tr_common("Cancel"))

    def _set_loading_state(self, loading: bool) -> None:
        if self.refresh_btn is None:
            return
        self.refresh_btn.setEnabled(not loading)
        if loading:
            self.refresh_btn.setText(self.tr("Loading..."))
        else:
            self.refresh_btn.setText(self.tr("Refresh profiles"))

    def _start_profiles_loading(self):
        """Kick off asynchronous profile loading."""
        self._set_loading_state(True)

        worker = ChromeProfilesWorker(self._on_profiles_loaded)
        WorkerManager.run(worker)

    def _on_profiles_loaded(self, profiles):
        """Handle worker completion and emit results."""
        self._set_loading_state(False)

        # Pass results to the main thread via signal
        self.profiles_loaded.emit(profiles)

    def _populate_profiles(self, profiles):
        """Populate the profile list with checkboxes."""
        # Remove existing checkboxes
        self._clear_profile_checkboxes()

        if not profiles:
            no_profiles_label = QLabel(self.tr("Chrome profiles not found"))
            no_profiles_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.profiles_layout.addWidget(no_profiles_label)
            return

        # Create a checkbox for each profile
        for profile in profiles:
            email = profile.get("email", self.tr("(no email)"))
            cb = QCheckBox(email)
            cb.profile = profile
            self.profiles_layout.addWidget(cb)
            self.profile_checkboxes.append(cb)

    def _clear_profile_checkboxes(self):
        """Clear profile checkbox list and remove widgets."""
        while self.profiles_layout.count():
            child = self.profiles_layout.takeAt(0)
            widget = child.widget()
            if widget:
                widget.setParent(None)
        self.profile_checkboxes.clear()

    def _on_select_all(self):
        """Select all available profiles."""
        for cb in self.profile_checkboxes:
            cb.setChecked(True)

    def _on_deselect_all(self):
        """Clear selection for all profiles."""
        for cb in self.profile_checkboxes:
            cb.setChecked(False)

    def accept(self) -> None:
        """Persist selected profiles and close the dialog."""
        self._selected_profiles = [cb.profile for cb in self.profile_checkboxes if cb.isChecked()]
        super().accept()

    def get_selected_profiles(self):
        """Return the list of selected profiles."""
        return getattr(self, '_selected_profiles', [])
