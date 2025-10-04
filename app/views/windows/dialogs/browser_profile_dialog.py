import logging
from typing import Dict, List

from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.utils.browser.browser_profiles import async_profile_manager as _apm
from app.utils.browser.browser_profiles import get_profile_manager
from app.utils.browser.browser_profiles import persistent_cache as _pc
from app.utils.browser.browser_profiles import profile_manager as _pm
from app.utils.browser.browser_profiles.utils import get_browser_display_name

logger = logging.getLogger(__name__)


class BrowserProfileDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Select browser profile"))
        self.setMinimumSize(480, 400)
        self.manager = get_profile_manager()
        self.selected_profiles = []
        self.profile_checkboxes = []
        self._setup_ui()
        self._populate_browsers()
        # Do not load every profile immediately; populate on demand for the chosen browser.
        # self._populate_profiles()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        # 1. Row: browsers + refresh button
        top_layout = QHBoxLayout()
        top_layout.addWidget(QLabel(self.tr("Browsers:")))
        self.browser_combo = QComboBox()
        self.browser_combo.currentIndexChanged.connect(self._populate_profiles)
        top_layout.addWidget(self.browser_combo, 1)
        self.refresh_btn = QPushButton(self.tr("Refresh"))
        self.refresh_btn.clicked.connect(self.refresh_profiles)
        top_layout.addWidget(self.refresh_btn, 0)
        layout.addLayout(top_layout)

        # 2. Row: search input
        search_layout = QHBoxLayout()
        self.search_line = QLineEdit()
        self.search_line.setPlaceholderText(self.tr("Search by name/email…"))
        self.search_line.textChanged.connect(self._populate_profiles)
        search_layout.addWidget(self.search_line, 1)
        layout.addLayout(search_layout)

        # Profiles list
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.profile_widget = QWidget()
        self.profile_layout = QVBoxLayout(self.profile_widget)
        self.scroll.setWidget(self.profile_widget)
        layout.addWidget(self.scroll)

        # Buttons
        # 4. Bottom row: selection buttons and status on the left, Save/Cancel on the right
        bottom_layout = QHBoxLayout()
        left_bottom = QHBoxLayout()
        # Selection helper buttons on the left
        self.select_all_btn = QPushButton(self.tr("Add all"))
        self.select_all_btn.clicked.connect(self._select_all_profiles)
        left_bottom.addWidget(self.select_all_btn)
        self.deselect_all_btn = QPushButton(self.tr("Clear selection"))
        self.deselect_all_btn.clicked.connect(self._deselect_all_profiles)
        left_bottom.addWidget(self.deselect_all_btn)
        # Status/progress indicator
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: gray; margin-left: 8px;")
        left_bottom.addWidget(self.status_label, 0)
        bottom_layout.addLayout(left_bottom, 1)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        # Localize button labels
        ok_btn = self.button_box.button(QDialogButtonBox.StandardButton.Ok)
        cancel_btn = self.button_box.button(QDialogButtonBox.StandardButton.Cancel)
        if ok_btn is not None:
            ok_btn.setText(self.tr("Save"))
            ok_btn.setEnabled(False)  # disabled until a profile is selected
            self._ok_button = ok_btn
        if cancel_btn is not None:
            cancel_btn.setText(self.tr("Cancel"))
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        bottom_layout.addWidget(self.button_box, 0)
        layout.addLayout(bottom_layout)

    def _set_controls_enabled(self, enabled: bool):
        self.browser_combo.setEnabled(enabled)
        self.search_line.setEnabled(enabled)
        self.refresh_btn.setEnabled(enabled)
        self.select_all_btn.setEnabled(enabled)
        self.deselect_all_btn.setEnabled(enabled)
        # The save button depends on selection, but also disables when the dialog is locked
        if hasattr(self, "_ok_button") and self._ok_button is not None:
            if not enabled:
                self._ok_button.setEnabled(False)
            else:
                self._update_save_enabled()

    def _populate_browsers(self):
        self.browser_combo.clear()
        browsers = self.manager.get_supported_browsers()
        for b in browsers:
            self.browser_combo.addItem(b["name"], b["key"])
        # Select the first browser by default
        if self.browser_combo.count() > 0:
            self.browser_combo.setCurrentIndex(0)

    def _populate_profiles(self):
        # Remove previous widgets from the layout
        for cb in self.profile_checkboxes:
            cb.deleteLater()
        self.profile_checkboxes.clear()

        # Clear all widgets from the layout
        while self.profile_layout.count():
            child = self.profile_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        browser_key = self.browser_combo.currentData()
        profiles = []

        # Load profiles for the selected browser from manager cache (no disk scan)
        profiles = self.manager.get_profiles_by_browser(browser_key)
        # Filter by search query
        query = (self.search_line.text() or "").strip().lower()
        if query:

            def _match(p: Dict) -> bool:
                name = str(p.get("email") or p.get("name") or "").lower()
                path = str(p.get("path") or "").lower()
                return query in name or query in path

            profiles = [p for p in profiles if _match(p)]
        finder = self.manager.finders.get(browser_key)
        if finder:
            for profile in profiles:
                profile["browser_key"] = browser_key
                profile["browser_name"] = get_browser_display_name(finder, browser_key)

        logger.debug("_populate_profiles: browser_key=%s", browser_key)

        if not profiles:
            self.profile_layout.addWidget(QLabel(self.tr("No profiles found")))
            return

        # Create checkboxes for every profile
        for profile in profiles:
            # Add browser name for clarity
            browser_name = profile.get("browser_name", "")
            profile_name = (
                profile.get("email")
                or profile.get("name")
                or self.tr("Unnamed")
            )
            text = self.tr("{profile} ({browser})").format(
                profile=profile_name, browser=browser_name
            )
            cb = QCheckBox(text)
            cb.profile_data = profile
            # Track changes for Save button availability
            try:
                cb.stateChanged.connect(self._update_save_enabled)
            except Exception:
                logger.debug(
                    "BrowserProfileDialog: failed to connect stateChanged for checkbox",
                    exc_info=True,
                )
            self.profile_layout.addWidget(cb)
            self.profile_checkboxes.append(cb)
        # Add stretch to prevent vertical stretching
        self.profile_layout.addStretch()
        # Refresh Save button state after rebuilding the list
        self._update_save_enabled()

    def refresh_profiles(self):
        """Manually refresh profiles asynchronously while updating caches and UI."""
        self._set_controls_enabled(False)
        self.status_label.setText(self.tr("Loading profiles…"))
        try:
            async_mgr = _apm.get_async_profile_manager()

            def _on_ready(all_profiles: Dict[str, List[Dict]]):
                try:
                    # Persist profiles in cache
                    cache = _pc.PersistentProfileCache(default_ttl=3600)
                    for key, profiles in (all_profiles or {}).items():
                        try:
                            cache.set(key, profiles)
                        except Exception:
                            logger.debug(
                                "BrowserProfileDialog: persistent cache set failed for %s",
                                key,
                                exc_info=True,
                            )
                    # Update synchronous manager cache (shared cache)
                    mgr = _pm.get_profile_manager()
                    for key, profiles in (all_profiles or {}).items():
                        try:
                            mgr.cache.set(key, profiles)
                        except Exception:
                            logger.debug(
                                "BrowserProfileDialog: runtime cache set failed for %s",
                                key,
                                exc_info=True,
                            )
                    # Rebuild dialog lists
                    self._populate_browsers()
                    self._populate_profiles()
                finally:
                    # Disconnect signals and restore controls
                    try:
                        async_mgr.all_profiles_ready.disconnect(_on_ready)
                        async_mgr.loading_progress.disconnect(_on_progress)
                        async_mgr.loading_error.disconnect(_on_error)
                    except Exception:
                        logger.debug(
                            "BrowserProfileDialog: failed to disconnect async signals",
                            exc_info=True,
                        )
                    self._set_controls_enabled(True)
                    self.status_label.setText("")

            # Subscribe and start loading without using worker RAM cache
            async_mgr.all_profiles_ready.connect(_on_ready)

            def _on_progress(operation: str, current: int, total: int):
                # `operation` is a string like "Loading chrome" from the manager
                try:
                    self.status_label.setText(
                        self.tr("{operation} ({current}/{total})…").format(
                            operation=operation, current=current, total=total
                        )
                    )
                except Exception:
                    logger.debug(
                        "BrowserProfileDialog: failed to update status label on progress",
                        exc_info=True,
                    )

            def _on_error(operation: str, message: str):
                logger.warning("Error during %s: %s", operation, message)
                self.status_label.setText(self.tr("Failed to load profiles"))

            async_mgr.loading_progress.connect(_on_progress)
            async_mgr.loading_error.connect(_on_error)
            async_mgr.load_all_profiles_async(use_cache=False)
        except Exception as e:
            logger.warning("Failed to start profiles refresh: %s", e)
            self._set_controls_enabled(True)
            self.status_label.setText(self.tr("Failed to start loading"))

    def accept(self):
        """Override ``accept`` to persist the selected profiles."""
        self.selected_profiles = [
            cb.profile_data for cb in self.profile_checkboxes if cb.isChecked()
        ]
        super().accept()

    def get_selected_profiles(self) -> List[Dict]:
        """Return the list of chosen profiles."""
        selected = self.selected_profiles

        logger.debug("get_selected_profiles: returning %s profiles", len(selected))
        for i, profile in enumerate(selected):
            logger.debug(
                "get_selected_profiles: profile %s: name=%s, browser_key=%s",
                i,
                profile.get("name"),
                profile.get("browser_key"),
            )

        return selected

    def _select_all_profiles(self):
        """Select every profile in the list."""
        for cb in self.profile_checkboxes:
            cb.setChecked(True)
        self._update_save_enabled()

    def _deselect_all_profiles(self):
        """Clear selection on every profile."""
        for cb in self.profile_checkboxes:
            cb.setChecked(False)
        self._update_save_enabled()

    def _update_save_enabled(self):
        """Enable the Save button when at least one profile is selected."""
        try:
            any_checked = any(cb.isChecked() for cb in self.profile_checkboxes)
            if hasattr(self, "_ok_button") and self._ok_button is not None:
                self._ok_button.setEnabled(any_checked)
        except Exception:
            logger.debug(
                "BrowserProfileDialog: failed to update save enabled state",
                exc_info=True,
            )
