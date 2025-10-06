import logging
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QCoreApplication, QRunnable, QSize, Qt, QThreadPool, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.config_data import app_config
from app.controllers.business import StructureBusinessLogic
from app.controllers.ui.theme_controller import ThemeController
from app.utils.ui.icon.icon_operations.creators import create_icon_from_path
from app.utils.ui.icon.path_service import icon_path_service
from app.views.windows.dialogs.link_dialog.icon_utils import make_icon


from .base_dialog import BaseDialog

logger = logging.getLogger(__name__)


def _populate_spheres_common(
    structure_business: StructureBusinessLogic, sphere_cb: QComboBox
) -> None:
    """Populate the sphere combobox with available options.
    The list is not cleared to preserve caller expectations.
    """
    spheres = structure_business.get_spheres()
    for sphere in spheres:
        sphere_cb.addItem(sphere["name"], sphere["id"])


def _tr(context: str, text: str) -> str:
    return QCoreApplication.translate(context, text)


class BaseEntityDialog(BaseDialog):
    """Base dialog for entities that have a name and an icon (section, category)."""

    def __init__(
        self,
        structure_business: StructureBusinessLogic,
        entity_name: str,
        entity_id: Optional[int] = None,
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
        name_layout.setSpacing(6)
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
        title_verb = self.tr("Edit") if self.entity_id else self.tr("Add")
        title_noun_map = {
            "section": self.tr("section"),
            "category": self.tr("category"),
        }
        title_noun = title_noun_map.get(self.entity_name, self.tr("entity"))
        self.setWindowTitle(f"{title_verb} {title_noun}")

        if self._name_label is not None:
            self._name_label.setText(self.tr("Name:"))
        if self.icon_btn is not None:
            self.icon_btn.setText(self.tr("Icon"))

        if self._button_box is not None:
            ok_btn = self._button_box.button(QDialogButtonBox.StandardButton.Ok)
            cancel_btn = self._button_box.button(QDialogButtonBox.StandardButton.Cancel)
            if ok_btn is not None:
                ok_btn.setText(self.tr("Save"))
            if cancel_btn is not None:
                cancel_btn.setText(self.tr("Cancel"))

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
        """Return explicit icon path, preferring user icons over bundled ones."""
        link_icon_path = icon_path_service.get_user_icons_dir() / icon_filename
        if link_icon_path.exists():
            return link_icon_path
        return icon_path_service.get_ui_icons_dir() / icon_filename

    def _choose_icon(self):
        """Pick an icon with smart copy semantics that avoid duplicates."""
        try:
            from app.utils.ui.icon.selection import choose_icon_and_copy

            user_icons_dir = icon_path_service.get_user_icons_dir()
            fname, icon = choose_icon_and_copy(self, user_icons_dir)
            if not fname or not icon:
                return

            self.icon_btn.setIcon(icon)
            self._icon_filename = fname

        except Exception as e:
            self.show_error(
                self.tr("Unable to set selected icon."),
                self.tr("Icon selection error"),
                informative_text=self.tr(
                    "Choose another image file (.png, .ico, .jpg, .svg) and try again."
                ),
                details=str(e),
            )

    def _on_accept_base(self) -> Optional[dict]:
        """Perform base validation and collect name/icon data, returning ``None`` on error."""
        name = self.name_le.text().strip()
        if not name:
            self.show_warning(
                self.tr("Name cannot be empty."),
                self.tr("Invalid input"),
                informative_text=self.tr("Please provide a name for the entity."),
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
        section_id: Optional[int] = None,
        default_sphere_id: Optional[int] = None,
        parent=None,
    ):
        super().__init__(structure_business, "section", section_id, parent)
        self.default_sphere_id = default_sphere_id
        # Fix width only; height is determined by content
        self.setFixedWidth(400)
        self._init_ui()
        self._finalize_translations()
        # Focus the name field on open
        try:
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
        self.sphere_cb = QComboBox()
        self._populate_spheres()
        form.addRow(self.tr("Sphere:"), self.sphere_cb)

        if self.default_sphere_id is not None and self.entity_id is None:
            self._set_sphere_selection(self.default_sphere_id)

        vbox.addLayout(form)
        vbox.addWidget(self._create_button_box())

    def _set_sphere_selection(self, sphere_id: int):
        """Select a sphere by its ID."""
        idx = self.sphere_cb.findData(sphere_id)
        if idx >= 0:
            self.sphere_cb.setCurrentIndex(idx)

    def _load_section(self):
        """Load section data for editing."""
        section_data = self.structure_business.get_section_for_editing(self.entity_id)

        if not section_data:
            self.show_warning(
                self.tr("Section not found."),
                self.tr("Section unavailable"),
                informative_text=self.tr("The section might have been deleted. ID: %1") % self.entity_id,
            )
            return

        self.name_le.setText(section_data["name"])
        self._set_sphere_selection(section_data["sphere_id"])

        icon = section_data["icon_path"] or f"{self.entity_name}.ico"
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
                informative_text=self.tr("Choose a sphere from the list and press \"Save\"."),
            )
            return

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
        category_id: Optional[int] = None,
        parent=None,
    ):
        super().__init__(structure_business, "category", category_id, parent)
        # Fix width only; height is determined by content
        self.setFixedWidth(400)
        self._init_ui()
        self._finalize_translations()
        # Focus the name field on open
        try:
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
        self.sphere_cb = QComboBox()
        self._populate_spheres()
        self.sphere_cb.currentIndexChanged.connect(self._update_sections)
        form.addRow(self.tr("Sphere:"), self.sphere_cb)

        self.section_cb = QComboBox()
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
                icon_path = section.get("icon_path", "") if isinstance(section, dict) else ""
                icon = make_icon(icon_path)
                if icon:
                    self.section_cb.addItem(icon, section["name"], section["id"])
                else:
                    self.section_cb.addItem(section["name"], section["id"])
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
                informative_text=self.tr("The category might have been deleted. ID: %1") % self.entity_id,
            )
            return

        self.name_le.setText(category_data["name"])
        section_id = category_data["section_id"]

        # Retrieve hierarchy via business logic
        hierarchy = self.structure_business.get_category_hierarchy(self.entity_id)

        if hierarchy:
            sphere_id = hierarchy["sphere_id"]
            # Select the stored sphere
            sphere_idx = self.sphere_cb.findData(sphere_id)
            if sphere_idx >= 0:
                self.sphere_cb.setCurrentIndex(sphere_idx)
                self._update_sections()
                # Select the stored section
                section_idx = self.section_cb.findData(section_id)
                if section_idx >= 0:
                    self.section_cb.setCurrentIndex(section_idx)

        # Set icon from stored data
        icon = category_data["icon_path"] or f"{self.entity_name}.ico"
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
                informative_text=self.tr("Choose a section from the list and press \"Save\"."),
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
            sphere_idx = self.sphere_cb.findData(sphere_id)
            if sphere_idx >= 0:
                self.sphere_cb.setCurrentIndex(sphere_idx)
                self._update_sections()
                section_idx = self.section_cb.findData(section_id)
                if section_idx >= 0:
                    self.section_cb.setCurrentIndex(section_idx)


class NoteDialog(BaseDialog):
    def __init__(self, link: dict, parent=None):
        super().__init__(parent)
        self.link = link
        self._button_box: QDialogButtonBox | None = None
        self.resize(400, 300)
        self._init_ui()

        # Initial translate pass
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
        self.setWindowTitle(self.tr("Notes"))
        if self.notes_te is not None:
            self.notes_te.setPlaceholderText(self.tr("Enter notes here"))
        if self._button_box is not None:
            ok_btn = self._button_box.button(QDialogButtonBox.StandardButton.Ok)
            cancel_btn = self._button_box.button(QDialogButtonBox.StandardButton.Cancel)
            if ok_btn is not None:
                ok_btn.setText(self.tr("Save"))
            if cancel_btn is not None:
                cancel_btn.setText(self.tr("Cancel"))

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
        super().__init__(parent)
        self.settings = settings
        self.theme_ctrl = theme_ctrl  # Keep reference to reapply theme
        self.resize(400, 200)
        self._form_layout: QFormLayout | None = None
        self._button_box: QDialogButtonBox | None = None
        self._init_ui()

        # Initial translate pass
        self.retranslateUi()

    def _init_ui(self):
        """Initialize the settings dialog UI."""
        vbox = QVBoxLayout(self)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self._form_layout = form

        # Configure maximum number of backups via combo box
        self.max_backups_combo = QComboBox()
        self.max_backups_combo.addItems([str(i) for i in range(1, 11)])
        try:
            current = int(self.settings.get_max_backups())
            if 1 <= current <= 10:
                self.max_backups_combo.setCurrentIndex(current - 1)
            else:
                self.max_backups_combo.setCurrentIndex(0)
        except Exception:
            self.max_backups_combo.setCurrentIndex(0)
        form.addRow(self.tr("Max backups:"), self.max_backups_combo)

        # Configure font size options
        self.font_size_combo = QComboBox()
        self.font_size_combo.addItems([str(i) for i in range(9, 15)])
        try:
            current_font_size = int(self.settings.get_font_size())
            if 9 <= current_font_size <= 14:
                self.font_size_combo.setCurrentIndex(current_font_size - 9)
            else:
                self.font_size_combo.setCurrentIndex(3)  # Default to 12
        except Exception:
            self.font_size_combo.setCurrentIndex(3)
        form.addRow(self.tr("Font size:"), self.font_size_combo)

        vbox.addLayout(form)

        bb = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        bb.accepted.connect(self._on_accept)
        bb.rejected.connect(self.reject)
        vbox.addWidget(bb)
        self._button_box = bb

    def retranslateUi(self) -> None:
        self.setWindowTitle(self.tr("Settings"))
        if self._form_layout is not None:
            max_label = self._form_layout.labelForField(self.max_backups_combo)
            if max_label is not None:
                max_label.setText(self.tr("Max backups:"))
            font_label = self._form_layout.labelForField(self.font_size_combo)
            if font_label is not None:
                font_label.setText(self.tr("Font size:"))
        if self._button_box is not None:
            ok_btn = self._button_box.button(QDialogButtonBox.StandardButton.Ok)
            cancel_btn = self._button_box.button(QDialogButtonBox.StandardButton.Cancel)
            if ok_btn is not None:
                ok_btn.setText(self.tr("Save"))
            if cancel_btn is not None:
                cancel_btn.setText(self.tr("Cancel"))

    def _on_accept(self):
        """Persist settings changes."""
        try:
            # Save user-selected values from the combo boxes
            max_backups = int(self.max_backups_combo.currentText())
            self.settings.set_max_backups(max_backups)

            font_size = int(self.font_size_combo.currentText())
            self.settings.set_font_size(font_size)

            # Reapply current theme to propagate the updated font size
            # ThemeStylesheetService now reads user font size from settings and generates QSS
            if self.theme_ctrl:
                current_theme = self.settings.get_theme()
                if current_theme:
                    # Clear cache and apply theme again
                    self.theme_ctrl.clear_cache()
                    self.theme_ctrl.apply(current_theme)

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
        super().__init__(parent)
        self.setModal(True)
        self.result = []
        self.profile_checkboxes = []
        self._title_label: QLabel | None = None
        self._button_box: QDialogButtonBox | None = None
        self._setup_size()
        self._setup_ui()
        
        self.retranslateUi()
        self.threadpool = QThreadPool.globalInstance()
        self.profiles_loaded.connect(self._populate_profiles)
        self._start_profiles_loading()
    
    # Language changes are handled via BaseDialog(ReTranslatable)

    def _setup_size(self):
        """Set the dialog size based on scale factor."""
        base_width, base_height = 600, 500
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
        self.setWindowTitle(self.tr("Select Chrome profile"))
        if self._title_label is not None:
            self._title_label.setText(self.tr("Choose a Chrome profile:"))
        self.select_all_btn.setText(self.tr("Select all"))
        self.deselect_all_btn.setText(self.tr("Deselect all"))
        self.refresh_btn.setText(self.tr("Refresh profiles"))
        if self._button_box is not None:
            save_btn = self._button_box.button(QDialogButtonBox.StandardButton.Save)
            cancel_btn = self._button_box.button(QDialogButtonBox.StandardButton.Cancel)
            if save_btn is not None:
                save_btn.setText(self.tr("Save"))
            if cancel_btn is not None:
                cancel_btn.setText(self.tr("Cancel"))

    def _set_loading_state(self, loading: bool) -> None:
        self.refresh_btn.setEnabled(not loading)
        if loading:
            self.refresh_btn.setText(self.tr("Loading…"))
        else:
            self.refresh_btn.setText(self.tr("Refresh profiles"))

    def _start_profiles_loading(self):
        """Kick off asynchronous profile loading."""
        self._set_loading_state(True)

        worker = ChromeProfilesWorker(self._on_profiles_loaded)
        self.threadpool.start(worker)

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
        self.result = [cb.profile for cb in self.profile_checkboxes if cb.isChecked()]
        super().accept()

    def get_selected_profiles(self):
        """Return the list of selected profiles."""
        return self.result
