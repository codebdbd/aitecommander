"""Dialog for importing links from a browser."""

import logging
from typing import Dict, Optional

from PyQt6.QtCore import QCoreApplication
from PyQt6.QtWidgets import QComboBox, QDialogButtonBox, QFormLayout, QLabel, QVBoxLayout

from .base_dialog import BaseDialog

_TR_CONTEXT = "ImportBrowserDialog"


def _tr(text: str, disambiguation: str | None = None) -> str:
    return QCoreApplication.translate(_TR_CONTEXT, text, disambiguation)


logger = logging.getLogger(__name__)


class ImportBrowserDialog(BaseDialog):
    """Dialog for selecting a section when importing browser links."""

    def __init__(self, structure_business_logic, parent=None):
        # Pre-initialize UI attributes so early retranslate calls are safe
        self._header_label: QLabel | None = None
        self._button_box: QDialogButtonBox | None = None
        self.sphere_cb: QComboBox | None = None
        self.section_cb: QComboBox | None = None

        super().__init__(parent)

        self.structure_business_logic = structure_business_logic
        self.selected_section_id = None

        self.setWindowTitle(self.tr("Import from browser"))
        self.resize(400, 180)
        self.setModal(True)

        self._init_ui()
        self._populate_spheres()
        self._update_sections()
        self.retranslateUi()

    def _init_ui(self) -> None:
        """Initialize dialog widgets."""
        vbox = QVBoxLayout(self)

        # Header
        self._header_label = QLabel(self.tr("Select where to import links:"))
        vbox.addWidget(self._header_label)

        # Form with two rows: sphere and section
        form = QFormLayout()

        self.sphere_cb = QComboBox()
        self.sphere_cb.setMinimumHeight(32)
        form.addRow(self.tr("Sphere:"), self.sphere_cb)

        self.section_cb = QComboBox()
        self.section_cb.setMinimumHeight(32)
        form.addRow(self.tr("Section:"), self.section_cb)

        vbox.addLayout(form)

        # Buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )

        # Configure button texts
        ok_btn = button_box.button(QDialogButtonBox.StandardButton.Ok)
        ok_btn.setText(self.tr("Import"))

        cancel_btn = button_box.button(QDialogButtonBox.StandardButton.Cancel)
        cancel_btn.setText(self.tr("Cancel"))

        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        vbox.addWidget(button_box)
        self._button_box = button_box

        # Connect signals
        self.sphere_cb.currentIndexChanged.connect(self._update_sections)
        self.section_cb.currentIndexChanged.connect(self._on_section_changed)

    def retranslateUi(self) -> None:  # type: ignore[override]
        """Update all user-facing texts on language change."""
        self.setWindowTitle(self.tr("Import from browser"))
        if self._header_label is not None:
            self._header_label.setText(self.tr("Select where to import links:"))
        # Update form labels via labelForField
        # (FormLayout auto-creates QLabel instances for string labels)
        try:
            # Find the form layout by scanning the top-level layout
            for i in range(self.layout().count()):
                item = self.layout().itemAt(i)
                form = isinstance(item.layout(), QFormLayout) and item.layout() or None
                if form:
                    sphere_label = form.labelForField(self.sphere_cb)
                    if sphere_label is not None:
                        sphere_label.setText(self.tr("Sphere:"))
                    section_label = form.labelForField(self.section_cb)
                    if section_label is not None:
                        section_label.setText(self.tr("Section:"))
                    break
        except Exception:
            pass
        if self._button_box is not None:
            ok_btn = self._button_box.button(QDialogButtonBox.StandardButton.Ok)
            cancel_btn = self._button_box.button(QDialogButtonBox.StandardButton.Cancel)
            if ok_btn is not None:
                ok_btn.setText(self.tr("Import"))
            if cancel_btn is not None:
                cancel_btn.setText(self.tr("Cancel"))

    def _populate_spheres(self) -> None:
        """Populate the sphere combobox."""
        try:
            self.sphere_cb.clear()
            spheres = self.structure_business_logic.get_spheres()
            logger.debug("Found spheres: %s", len(spheres))
            if not spheres:
                # No spheres available — disable both comboboxes
                self._show_no_data_message(self.tr("No spheres found"))
                return
            for sphere in spheres:
                self.sphere_cb.addItem(sphere["name"], sphere["id"])
            if self.sphere_cb.count() > 0:
                self.sphere_cb.setCurrentIndex(0)
        except Exception as e:
            logger.error("Failed to load spheres: %s", e, exc_info=True)
            self._show_error_message(str(e))

    def _update_sections(self) -> None:
        """Update section list for the selected sphere."""
        try:
            self.section_cb.clear()
            sphere_id = self.sphere_cb.currentData()
            if not sphere_id:
                self._show_no_sections_message(self.tr("Select a sphere first"))
                return
            sections = self.structure_business_logic.get_sections(sphere_id)
            if not sections:
                self._show_no_sections_message(
                    self.tr("The selected sphere has no sections")
                )
                return
            for section in sections:
                self.section_cb.addItem(section["name"], section["id"])
            if self.section_cb.count() > 0:
                self.section_cb.setCurrentIndex(0)
        except Exception as e:
            logger.error("Failed to load sections: %s", e, exc_info=True)
            self._show_error_message(str(e))

    def _show_no_data_message(self, message: str) -> None:
        """Display a message when no spheres are available."""
        self.sphere_cb.addItem(message)
        self.sphere_cb.setEnabled(False)
        self.section_cb.addItem(self.tr("No data"))
        self.section_cb.setEnabled(False)
        logger.warning("%s", message)

    def _show_no_sections_message(self, message: str) -> None:
        """Display a message when no sections are available for the sphere."""
        self.section_cb.addItem(message)
        self.section_cb.setEnabled(False)
        logger.warning(message)

    def _show_error_message(self, message: str) -> None:
        """Display an error message to the user."""
        self.section_cb.addItem(
            self.tr("Error: {error}").format(error=message)
        )
        self.section_cb.setEnabled(False)
        self.show_error(
            self.tr("Failed to load sections."),
            self.tr("Sections load error"),
            informative_text=self.tr(
                "Check the database connection and try again."
            ),
            details=message,
        )

    def _on_section_changed(self) -> None:
        """Handle changes in the selected section."""
        section_id = self.section_cb.currentData()
        if section_id:
            sphere_name = self.sphere_cb.currentText()
            section_name = self.section_cb.currentText()
            logger.debug("Selected section: %s / %s", sphere_name, section_name)

    def get_selected_section_id(self) -> Optional[int]:
        """Return the selected section ID."""
        if not self.section_cb.isEnabled():
            return None
        return self.section_cb.currentData()

    def get_selected_section_info(self) -> Optional[Dict]:
        """Return information about the selected section and sphere."""
        section_id = self.get_selected_section_id()
        if not section_id:
            return None
        return {
            "section_id": section_id,
            "sphere_id": self.sphere_cb.currentData(),
            "sphere_name": self.sphere_cb.currentText(),
            "section_name": self.section_cb.currentText(),
        }

    def accept(self) -> None:
        """Confirm the selected section."""
        section_id = self.get_selected_section_id()

        if not section_id:
            self.show_warning(
                self.tr("No section selected for import."),
                self.tr("Section selection required"),
                informative_text=self.tr(
                    "Choose a section from the dropdown, then click 'Import'."
                ),
            )
            return

        # Ensure the selected section still exists
        try:
            section_info = self.get_selected_section_info()
            if not section_info:
                self.show_warning(
                    self.tr("The selected section is unavailable."),
                    self.tr("Section not found"),
                    informative_text=self.tr(
                        "The section may have been removed. Refresh sections and select another."
                    ),
                )
                return

            self.selected_section_id = section_id
            logger.info(
                "Confirmed import to section: %s / %s",
                section_info["sphere_name"],
                section_info["section_name"],
            )
            super().accept()

        except Exception as e:
            logger.error(
                "Error while confirming section selection: %s", e, exc_info=True
            )
            self.show_error(
                self.tr("Failed to confirm section selection."),
                self.tr("Confirmation error"),
                informative_text=self.tr(
                    "Try selecting the section again or refresh the sections list."
                ),
                details=str(e),
            )

    def get_result(self) -> Optional[Dict]:
        """Return the selection result after closing the dialog."""
        if self.selected_section_id:
            return self.get_selected_section_info()
        return None
