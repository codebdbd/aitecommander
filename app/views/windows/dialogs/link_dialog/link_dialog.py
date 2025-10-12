"""
LinkDialog - dialog for adding/editing a link.

Controller interfaces (for type checking):
- DialogControllerProtocol: provides hierarchical data and validation/save methods.
- LinkDataControllerProtocol: responsible only for validating/saving form data.
"""

import logging
from pathlib import Path
from typing import Any, Optional, Protocol, runtime_checkable

from PyQt6.QtCore import QCoreApplication, Qt, QTimer
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QWidget,
)

from app.config_data import app_config
from app.models.types.link_type import LinkType
from app.utils.ui.icon.icon_resolver import resolve_icon_for_link
from app.utils.ui.icon.path_service import icon_path_service
from app.utils.ui.icon.ui_helpers import set_icon_to_button
from app.utils.ui.icon.validation import validate_config_for_icons
from app.views.common.effects.neon_effect import NeonEventFilter

from ..base_dialog import BaseDialog
from .link_dialog_handlers import LinkDialogHandlers
from .link_dialog_ui import LinkDialogUI

logger = logging.getLogger(__name__)

_TR_CONTEXT = "LinkDialog"


def _tr(text: str, disambiguation: str | None = None, n: int | None = None) -> str:
    return QCoreApplication.translate(
        _TR_CONTEXT, text, disambiguation, n if n is not None else -1
    )


@runtime_checkable
class LinkDataControllerProtocol(Protocol):
    """Protocol describing the minimal link data controller contract.

    Implementations must provide `validate_and_save` returning a dict with
    the key `is_valid` and an optional list `errors`.
    """

    def validate_and_save(self, form_data: dict[str, Any]) -> dict[str, Any]: ...


@runtime_checkable
class DialogControllerProtocol(LinkDataControllerProtocol, Protocol):
    """Protocol for dialog controllers that supply hierarchical data.

    Implementations must return lists of sections and categories by IDs.
    Items must be dictionaries with at least `id` and `name`, optionally `icon_path`.
    """

    def get_sections_for_sphere(self, sphere_id: int) -> list[dict[str, Any]]: ...

    def get_categories_for_section(self, section_id: int) -> list[dict[str, Any]]: ...


class LinkDialog(BaseDialog):
    """Dialog for adding/editing links with a modular structure."""

    # Configurable debounce delay for URL/path processing in milliseconds.
    # Used by a timer to delay background parsing while the user types so that
    # background tasks are not triggered for every character.
    PATH_DEBOUNCE_MS: int = 300

    # --- Private UI widget getters to avoid duplication ---
    def _get_sphere_cb(self) -> QComboBox:
        """Return the sphere combo box (`QComboBox`)."""
        return self.ui.get_widget("sphere_cb")

    def _get_section_cb(self) -> QComboBox:
        """Return the section combo box (`QComboBox`)."""
        return self.ui.get_widget("section_cb")

    def _get_category_cb(self) -> QComboBox:
        """Return the category combo box (`QComboBox`)."""
        return self.ui.get_widget("category_cb")

    def _get_icon_btn(self) -> QPushButton:
        """Return the icon selection button (`QPushButton`)."""
        return self.ui.get_widget("icon_btn")

    def _get_type_group(self) -> QButtonGroup:
        """Return the group of link type buttons (`QButtonGroup`)."""
        return self.ui.get_widget("type_group")

    def _get_profile_btn(self) -> QPushButton:
        """Return the profile selection button (`QPushButton`)."""
        return self.ui.get_widget("profile_btn")

    # Additional getters for unified UI access
    def _get_url_le(self) -> QLineEdit:
        """Return the URL/path line edit (`QLineEdit`)."""
        return self.ui.get_widget("url_le")

    def _get_name_le(self) -> QLineEdit:
        """Return the name line edit (`QLineEdit`)."""
        return self.ui.get_widget("name_le")

    def _get_args_le(self) -> QLineEdit:
        """Return the arguments line edit (`QLineEdit`)."""
        return self.ui.get_widget("args_le")

    def _get_args_label(self) -> QLabel:
        """Return the arguments label (`QLabel`)."""
        return self.ui.get_widget("args_label")

    def _get_browse_btn(self) -> QPushButton:
        """Return the "Browse" button (`QPushButton`)."""
        return self.ui.get_widget("browse_btn")

    def _get_button_box(self) -> QDialogButtonBox:
        """Return the dialog button box (`QDialogButtonBox`)."""
        return self.ui.get_widget("button_box")

    def _get_fav_chk(self) -> QCheckBox:
        """Return the favorites checkbox (`QCheckBox`)."""
        return self.ui.get_widget("fav_chk")

    def _get_notes_te(self) -> QTextEdit:
        """Return the notes text edit (`QTextEdit`)."""
        return self.ui.get_widget("notes_te")

    def __init__(
        self,
        initialization_data: dict,
        dialog_controller: DialogControllerProtocol,
        link: Optional[dict] = None,
        category_id: Optional[int] = None,
        parent: Optional[QWidget] = None,
        link_controller: Optional[LinkDataControllerProtocol] = None,
    ):
        # Prepare core properties before BaseDialog/ReTranslatable hooks
        self._init_core_properties(
            initialization_data, dialog_controller, link, category_id
        )

        super().__init__(parent)

        # Ensure user icons directory exists (moved from module scope to avoid import side-effects)
        icon_path_service.ensure_user_icons_dir()

        # Obtain link types from configuration
        self.link_types = app_config.settings.get_link_types()

        # Optional MVC controller
        self.link_controller = link_controller

        # Init components
        self._init_components()

        # Validate configuration
        if not self._validate_configuration():
            return

        # Configure UI and load data
        self._setup_ui_properties()
        self._load_initial()
        # Initial translation pass
        self.retranslateUi()

    def _init_core_properties(
        self,
        initialization_data: dict,
        dialog_controller,
        link: Optional[dict],
        category_id: Optional[int],
    ) -> None:
        """Initialise the dialog core properties."""
        self.initialization_data = initialization_data
        self.dialog_controller = dialog_controller
        self.link = link.copy() if link else {}
        self.initial_category = category_id
        self.link_type = self.link.get("type", "web")
        self.icon_name = self.link.get("icon_path", "")
        self.selected_profiles: list[dict] = []

    def _init_components(self) -> None:
        """Initialise UI and handlers."""
        # UI components
        self.ui = LinkDialogUI(self)
        self.ui.build_ui(self.link_types)

        # Neon glow for type buttons — same behaviour as sphere buttons
        try:
            # Apply hover and active neon effect similar to sphere buttons
            self._neon_link_filter = NeonEventFilter(
                color=QColor("#0194F0"), blur_radius=18
            )
            for btn in self._get_type_group().buttons():
                btn.installEventFilter(self._neon_link_filter)
                # Track toggled state to sync the glow
                try:
                    self._neon_link_filter._maybe_connect_toggled(btn)
                    if getattr(btn, "isChecked", lambda: False)():
                        self._neon_link_filter._apply_effect(btn)
                    else:
                        self._neon_link_filter._clear_effect(btn)
                except Exception:
                    pass
        except (AttributeError, RuntimeError) as e:
            # Do not block the dialog if neon effect fails
            logger.warning(
                "Failed to install neon effect on link type buttons: %s",
                e,
                exc_info=True,
            )

        # Event handlers
        self.handlers = LinkDialogHandlers(self)
        self.handlers.connect_signals()

        # Install focus guard to prevent unwanted focus jumps in the hierarchy block
        try:
            self._install_focus_guard()
        except Exception:
            pass

        # Workers and timers
        self._init_workers_and_timers()

    # --- Focus guard -------------------------------------------------------
    def _install_focus_guard(self) -> None:
        """Install an event filter on hierarchy combo boxes.

        Prevents them from stealing focus immediately after type changes by
        using `_preferred_focus_widget`, set in `TypeChangeMixin._update_ui_state()`
        for 300 ms and then cleared.
        """
        try:
            for cb in (
                self._get_sphere_cb(),
                self._get_section_cb(),
                self._get_category_cb(),
            ):
                if cb and not getattr(cb, "_focus_guard_installed", False):
                    cb.installEventFilter(self)
                    cb._focus_guard_installed = True
        except Exception:
            pass

    def eventFilter(self, obj, event):
        try:
            # If a preferred focus widget is set and current object tries to grab focus, restore it
            if event and event.type() == event.Type.FocusIn:
                target = getattr(self, "_preferred_focus_widget", None)
                if target is not None and obj is not target:
                    try:
                        target.setFocus(Qt.FocusReason.OtherFocusReason)
                        return True  # Consume focus event
                    except Exception:
                        pass
        except Exception:
            pass
        return super().eventFilter(obj, event)

    def _init_workers_and_timers(self) -> None:
        """Initialise workers and timers used for link processing."""
        self._processing_timer = QTimer(self)
        self._processing_timer.setSingleShot(True)
        self._processing_timer.timeout.connect(self.handlers._trigger_link_processing)

    def _validate_configuration(self) -> bool:
        """Validate dialog configuration."""
        if not validate_config_for_icons(app_config):
            self.show_error(
                self.tr("Icon configuration is invalid."),
                self.tr("Configuration error"),
                informative_text=self.tr(
                    "Icons directory is not set. Specify the path in the application settings or config."
                ),
                details=self.tr(
                    "Configuration parameter for icons is missing or empty."
                ),
            )
            self.close()
            return False
        return True

    def _setup_ui_properties(self) -> None:
        """Configure dialog UI properties."""
        # Window title is updated in retranslateUi()
        self.setFixedSize(
            app_config.ui.get_link_dialog_width(),
            app_config.ui.get_link_dialog_height(),
        )

    def _load_initial(self) -> None:
        """Load initial data into the form."""
        logger.debug(
            "Form initialization: link_type=%s, category_id=%s, link_keys=%s",
            self.link_type,
            self.initial_category,
            list(self.link.keys()),
        )

        # Set link type button
        type_group = self._get_type_group()
        _lt = LinkType.from_value(self.link_type)
        for btn in type_group.buttons():
            if btn.property("link_type") == _lt.value:
                btn.setChecked(True)
                break

        # Prepare form data
        form_data = {
            "url_le": self.link.get("url", ""),
            "name_le": self.link.get("name", ""),
            "args_le": self.link.get("args", ""),
            "notes_te": self.link.get("notes", ""),
            "fav_chk": bool(self.link.get("is_favorite", False)),
        }

        logger.debug("Initial form data: %s", form_data)

        self.ui.set_form_data(form_data)

        logger.debug("Initial values applied to UI; continuing with icon setup")

        # Set icon
        self._set_initial_icon()

        # Populate hierarchy
        self._populate_hierarchy()

        # Load migrated profiles if present
        if self.link and self.link.get("migrated_profiles"):
            self.selected_profiles = self.link["migrated_profiles"]
            profile_btn = self._get_profile_btn()
            profile_btn.setText(self._format_profile_text(self.selected_profiles))

        # Update UI state
        self.handlers._update_ui_state()

        # Set focus depending on link type:
        #  - WEB: focus URL/path field
        #  - others: focus "Browse" button
        try:
            lt = LinkType.from_value(self.link_type)

            def _apply_initial_focus():
                try:
                    if lt == LinkType.WEB:
                        self._get_url_le().setFocus(
                            Qt.FocusReason.ActiveWindowFocusReason
                        )
                    else:
                        self._get_browse_btn().setFocus(
                            Qt.FocusReason.ActiveWindowFocusReason
                        )
                except Exception:
                    pass

            QTimer.singleShot(0, _apply_initial_focus)
        except Exception:
            pass

    def _set_initial_icon(self) -> None:
        """Set initial icon."""
        resolved, exists = self._resolve_and_apply_icon(
            LinkType.from_value(self.link_type).value, self.icon_name
        )
        if not exists:
            # Notify once when icon is missing
            self.show_warning(
                self.tr("Default icon not found."),
                self.tr("Icon issue"),
                informative_text=self.tr(
                    "The button will be shown without an icon. Provide a valid icons path in settings."
                ),
                details=self.tr("Expected file: {path}").format(path=resolved),
            )

    def _resolve_and_apply_icon(
        self, link_type: str, icon_name: str
    ) -> tuple[Optional[str], bool]:
        """Resolve and apply an icon to the button if the file exists.

        Returns `(resolved_path, exists)` where `resolved_path` is a string path or
        `None`, and `exists` indicates presence of the file.
        """
        link_dict = {"type": link_type, "icon_path": icon_name}
        resolved = resolve_icon_for_link(link_dict)
        exists = bool(resolved and Path(resolved).exists())
        if exists:
            set_icon_to_button(self._get_icon_btn(), resolved)
        return resolved, exists

    def set_link_type(self, link_type: str) -> None:
        """Programmatically select link type and update UI.

        Central implementation resides in `TypeChangeMixin` via `LinkDialogHandlers`.
        Kept as a stable entry point for external callers (e.g., `MainWindow.quick_add_link`).
        """
        self.handlers.set_link_type(link_type)

    def _populate_hierarchy(self) -> None:
        """Populate hierarchy combo boxes (spheres/sections/categories).

        Steps:
        1) load spheres from `initialization_data`,
        2) apply initial selection (from `category_hierarchy`, if present),
        3) delegate updating sections/categories to `HierarchyMixin`.
        """
        # 1) Load spheres from initialization_data
        self._populate_spheres()

        sphere_cb = self._get_sphere_cb()
        section_cb = self._get_section_cb()
        category_cb = self._get_category_cb()

        # 2) Apply initial selection (based on link/constructor params)
        cid = self.link.get("category_id") or self.initial_category
        if cid:
            hierarchy = self.initialization_data.get("category_hierarchy") or {}

            # Set sphere first (if provided)
            self._set_index_by_data(sphere_cb, hierarchy.get("sphere_id"))

            # Update sections under the current sphere
            self.handlers._update_sections()

            # Apply section if provided, otherwise keep current (or first)
            section_id = hierarchy.get("section_id")
            if not self._set_index_by_data(section_cb, section_id):
                self._select_first_if_unset(section_cb)

            # Update categories under the current section
            self.handlers._update_categories()

            # Apply category if provided, otherwise keep current (or first)
            category_id = hierarchy.get("category_id")
            if not self._set_index_by_data(category_cb, category_id):
                self._select_first_if_unset(category_cb)
        else:
            # Defaults: first sphere/section/category
            self._apply_default_hierarchy_selection()
            self.handlers._update_sections()
            if section_cb.count() > 0:
                self._select_first_if_unset(section_cb)
                self.handlers._update_categories()
                if category_cb.count() > 0:
                    self._select_first_if_unset(category_cb)

    def _populate_spheres(self) -> None:
        """Populate the sphere list from `initialization_data` (no icons)."""
        sphere_cb = self._get_sphere_cb()
        sphere_cb.clear()
        for sp in self.initialization_data.get("spheres", []):
            sphere_cb.addItem(sp["name"], sp["id"])

    def _apply_default_hierarchy_selection(self) -> None:
        """Select the first sphere, section, and category by default."""
        sphere_cb = self._get_sphere_cb()
        if sphere_cb.count() > 0:
            sphere_cb.setCurrentIndex(0)

    def _set_index_by_data(self, combo: Any, data_id: Any) -> bool:
        """Safely set combo box index by item data.

        Returns True when index changed, False if `data_id` is None, not found, or an exception occurs.
        """
        try:
            if data_id is None:
                return False
            idx = combo.findData(data_id)
            if idx >= 0:
                combo.setCurrentIndex(idx)
                return True
        except (AttributeError, RuntimeError, TypeError):
            # Do not change state on errors
            return False
        return False

    def _select_first_if_unset(self, combo: Any) -> bool:
        """Select the first combo box item if nothing is currently selected.

        Returns True on success, False if items are missing, an index already set, or an exception occurs.
        """
        try:
            if combo.count() > 0 and combo.currentIndex() < 0:
                combo.setCurrentIndex(0)
                return True
        except (AttributeError, RuntimeError):
            return False
        return False

    def get_ui_icons_dir(self) -> Path:
        """Return the UI icons directory."""
        return icon_path_service.get_ui_icons_dir()

    def get_user_icons_dir(self) -> Path:
        """Return the user icons directory."""
        return icon_path_service.get_user_icons_dir()

    def _format_profile_text(self, profiles: list[dict]) -> str:
        """Format display text for selected profiles."""
        emails = [p.get("email") or p.get("name") for p in profiles]
        if not emails:
            return self.tr("Profile")
        elif len(emails) == 1:
            return self.tr("Profile: {email}").format(email=emails[0])
        elif len(emails) == 2:
            return self.tr("Profiles: {first}, {second}").format(
                first=emails[0], second=emails[1]
            )
        return self.tr("Profiles: {first}, {second} and {rest} more").format(
            first=emails[0], second=emails[1], rest=len(emails) - 2
        )

    def closeEvent(self, event) -> None:
        """Handle dialog close event.

        If background processing is running, ask for confirmation, stop timers and
        clean up event filters to avoid leaks.
        """
        if self.handlers._is_processing or self.handlers._active_worker:
            if not self._show_confirm_close_while_processing():
                event.ignore()
                return

        # Clean event filters to prevent leaks
        try:
            if hasattr(self, "_neon_link_filter") and self._neon_link_filter:
                self._neon_link_filter.cleanup()
                self._neon_link_filter = None
        except Exception:
            pass

        self.handlers.cancel_processing()
        try:
            if getattr(self, "_processing_timer", None):
                self._processing_timer.stop()
                self._processing_timer.deleteLater()
        except (AttributeError, RuntimeError) as e:
            logger.debug(
                "LinkDialog: failed to stop processing timer during close: %s", e
            )
        super().closeEvent(event)

    def retranslateUi(self) -> None:  # type: ignore[override]
        """Update UI texts on language change."""
        # Window title
        self.setWindowTitle(self.tr("Edit link") if self.link else self.tr("Add link"))
        # Delegate to UI component
        if hasattr(self, "ui") and self.ui is not None:
            self.ui.retranslate()
        # Profile button text (reset to default if not customized)
        try:
            profile_btn = self._get_profile_btn()
            if profile_btn is not None:
                current_text = profile_btn.text()
                # Only reset if it's the default "Profile" text to avoid overriding custom summaries
                if not current_text or current_text == self.tr("Profile"):
                    profile_btn.setText(self.tr("Profile"))
        except Exception:
            pass
