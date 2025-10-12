"""Dialog for importing links from a browser."""

import logging
from functools import partial
from typing import Any, Optional

from PyQt6.QtCore import QCoreApplication, QSignalBlocker
from PyQt6.QtWidgets import (
    QComboBox,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QVBoxLayout,
)

from app.utils.db.api import run_db

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
        self._db = getattr(structure_business_logic, "db", None)
        self.selected_section_id = None
        self._sections_request_token = 0
        self._latest_requested_sphere: Optional[int] = None

        self.setWindowTitle(self.tr("Import from browser"))
        self.resize(400, 180)
        self.setModal(True)

        self._init_ui()
        self.retranslateUi()
        self._load_spheres_async()

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
        self.sphere_cb.setEnabled(False)
        self.sphere_cb.addItem(self.tr("Loading…"))
        form.addRow(self.tr("Sphere:"), self.sphere_cb)

        self.section_cb = QComboBox()
        self.section_cb.setMinimumHeight(32)
        self.section_cb.setEnabled(False)
        self.section_cb.addItem(self.tr("Select a sphere first"))
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
        self.sphere_cb.currentIndexChanged.connect(self._on_sphere_changed)
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

    def _load_spheres_async(self) -> None:
        cached_spheres: list[dict[str, Any]] = []
        try:
            cached_spheres = self.structure_business_logic.get_cached_spheres()
        except Exception as exc:
            logger.debug("ImportBrowserDialog: cached spheres unavailable: %s", exc, exc_info=True)

        if cached_spheres:
            self._apply_spheres(cached_spheres)
            return

        if self._db is None:
            self._handle_spheres_error(RuntimeError("Database connection is not available"))
            return

        with QSignalBlocker(self.sphere_cb):
            self.sphere_cb.clear()
            self.sphere_cb.addItem(self.tr("Loading…"))
            self.sphere_cb.setEnabled(False)

        run_db(
            lambda: self._db.spheres.get_spheres() or [],
            description="import_browser_dialog_load_spheres",
            on_finished=self._apply_spheres,
            on_error=self._handle_spheres_error,
        )

    def _on_sphere_changed(self, index: int) -> None:
        if self.sphere_cb is None or index < 0:
            return
        data = self.sphere_cb.itemData(index)
        self._latest_requested_sphere = data if isinstance(data, int) else None
        self._load_sections_async(self._latest_requested_sphere)

    def _load_sections_async(self, sphere_id: Optional[int]) -> None:
        if not isinstance(sphere_id, int):
            self._show_no_sections_message(self.tr("Select a sphere first"))
            return

        cached_sections: list[dict[str, Any]] = []
        try:
            cached_sections = self.structure_business_logic.get_cached_sections(sphere_id)
        except Exception as exc:
            logger.debug(
                "ImportBrowserDialog: cached sections unavailable for %s: %s",
                sphere_id,
                exc,
                exc_info=True,
            )

        if cached_sections:
            self._apply_sections(cached_sections)
            return

        if self._db is None:
            self._handle_sections_error(self._sections_request_token, RuntimeError("Database connection is not available"))
            return

        self._sections_request_token += 1
        token = self._sections_request_token
        self._set_section_placeholder(self.tr("Loading…"), enabled=False)

        run_db(
            lambda: self._db.sections.get_sections(sphere_id) or [],
            description="import_browser_dialog_load_sections",
            on_finished=partial(self._on_sections_async_result, sphere_id, token),
            on_error=partial(self._handle_sections_error, token),
        )

    def _on_sections_async_result(
        self,
        sphere_id: int,
        token: int,
        sections: list[dict[str, Any]],
    ) -> None:
        if token != self._sections_request_token:
            return
        if self._latest_requested_sphere is not None and sphere_id != self._latest_requested_sphere:
            return
        self._apply_sections(sections)

    def _handle_spheres_error(self, error: Exception) -> None:
        logger.error("Failed to load spheres for import dialog: %s", error, exc_info=True)
        with QSignalBlocker(self.sphere_cb):
            self.sphere_cb.clear()
            self.sphere_cb.addItem(self.tr("Failed to load spheres"))
            self.sphere_cb.setEnabled(False)
        self._show_error_message(str(error))

    def _handle_sections_error(self, token: int, error: Exception) -> None:
        if token != self._sections_request_token:
            return
        logger.error("Failed to load sections for import dialog: %s", error, exc_info=True)
        self._show_error_message(str(error))

    def _apply_spheres(self, spheres: list[dict[str, Any]]) -> None:
        with QSignalBlocker(self.sphere_cb):
            self.sphere_cb.clear()
            if not spheres:
                self._show_no_data_message(self.tr("No spheres found"))
                return
            for sphere in spheres:
                name = sphere.get("name")
                sphere_id = sphere.get("id")
                if name is None or sphere_id is None:
                    continue
                self.sphere_cb.addItem(str(name), sphere_id)
            if self.sphere_cb.count() > 0:
                self.sphere_cb.setEnabled(True)
                self.sphere_cb.setCurrentIndex(0)
        current_data = self.sphere_cb.currentData()
        self._latest_requested_sphere = current_data if isinstance(current_data, int) else None
        if isinstance(current_data, int):
            self._load_sections_async(current_data)
        else:
            self._show_no_sections_message(self.tr("Select a sphere first"))

    def _apply_sections(self, sections: list[dict[str, Any]]) -> None:
        with QSignalBlocker(self.section_cb):
            self.section_cb.clear()
            if not sections:
                self._show_no_sections_message(
                    self.tr("The selected sphere has no sections")
                )
                return
            for section in sections:
                name = section.get("name")
                section_id = section.get("id")
                if name is None or section_id is None:
                    continue
                self.section_cb.addItem(str(name), section_id)
            self.section_cb.setEnabled(True)
            self.section_cb.setCurrentIndex(0)
        self.selected_section_id = self.get_selected_section_id()

    def _set_section_placeholder(self, text: str, *, enabled: bool) -> None:
        with QSignalBlocker(self.section_cb):
            self.section_cb.clear()
            self.section_cb.addItem(text)
            self.section_cb.setEnabled(enabled)

    def _show_no_data_message(self, message: str) -> None:
        """Display a message when no spheres are available."""
        with QSignalBlocker(self.sphere_cb):
            self.sphere_cb.clear()
            self.sphere_cb.addItem(message)
            self.sphere_cb.setEnabled(False)
        self._set_section_placeholder(self.tr("No data"), enabled=False)
        logger.warning("%s", message)

    def _show_no_sections_message(self, message: str) -> None:
        """Display a message when no sections are available for the sphere."""
        self._set_section_placeholder(message, enabled=False)
        logger.warning(message)

    def _show_error_message(self, message: str) -> None:
        """Display an error message to the user."""
        self._set_section_placeholder(
            self.tr("Error: {error}").format(error=message),
            enabled=False,
        )
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

    def get_selected_section_info(self) -> Optional[dict]:
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

    def get_result(self) -> Optional[dict]:
        """Return the selection result after closing the dialog."""
        if self.selected_section_id:
            return self.get_selected_section_info()
        return None


