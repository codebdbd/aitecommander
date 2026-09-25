"""
Event handlers for `LinkDialog`.
Contains logic for processing user actions.
"""

import logging

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLineEdit, QToolButton

from .handlers_mixins.apps_picker_mixin import AppsPickerMixin
from .handlers_mixins.file_dialog_mixin import FileDialogMixin
from .handlers_mixins.form_data_mixin import FormDataMixin
from .handlers_mixins.hierarchy_mixin import HierarchyMixin
from .handlers_mixins.icons_mixin import IconsMixin
from .handlers_mixins.link_processing_mixin import LinkProcessingMixin
from .handlers_mixins.profiles_mixin import ProfilesMixin
from .handlers_mixins.rotation_mixin import RotationMixin
from .handlers_mixins.type_change_mixin import TypeChangeMixin
from .handlers_mixins.validation_mixin import ValidationMixin
from .link_dialog_signals import LinkDialogSignals

logger = logging.getLogger(__name__)


class LinkDialogHandlers(
    TypeChangeMixin,
    FileDialogMixin,
    AppsPickerMixin,
    IconsMixin,
    ProfilesMixin,
    RotationMixin,
    HierarchyMixin,
    FormDataMixin,
    ValidationMixin,
    LinkProcessingMixin,
):
    """Event handlers orchestrating `LinkDialog` behaviour."""

    def __init__(self, dialog):
        """Initialise handlers container."""
        self.dialog = dialog
        self._last_processed_path = ""
        self._is_processing = False
        self._worker_task_id = 0
        self._active_worker = None
        self._pending_processed_path = ""
        self._callbacks_enabled = True
        # Local signals (replacement for StructureWorkerSignals)
        self.signals = LinkDialogSignals()
        # Connect internal signals
        self.signals.link_info_finished.connect(self._handle_link_info_finished)
        self.signals.simple_error.connect(self._handle_link_info_error)

    def _handle_link_info_finished(self, info) -> None:
        if not self._callbacks_enabled:
            logger.info("LinkDialogHandlers: ignored late link_info_finished callback")
            return
        self._on_link_info_fetched(info)

    def _handle_link_info_error(self, error) -> None:
        if not self._callbacks_enabled:
            logger.info("LinkDialogHandlers: ignored late link_info_error callback")
            return
        self._on_link_info_error(error)

    def connect_signals(self) -> None:
        """Wire dialog widgets to handlers."""
        # Link type selection
        if getattr(self.dialog.ui, "type_group", None) is not None:
            self.dialog.ui.type_group.buttonClicked.connect(
                lambda b: self.on_type_changed(b.property("link_type"))
            )

        # URL change
        url_widget = self.dialog._get_url_le()
        url_widget.textChanged.connect(self._on_path_changed)
        # Immediate trigger when editing finishes (Enter/focus loss)
        try:
            url_widget.editingFinished.connect(self._trigger_link_processing)
        except (AttributeError, RuntimeError) as e:
            logger.warning(
                "Failed to connect editingFinished for url_widget: %s",
                e,
                exc_info=True,
            )

        # Buttons
        self.dialog._get_browse_btn().clicked.connect(self._on_browse)
        apps_btn = self.dialog._get_apps_btn()
        if apps_btn is not None:
            apps_btn.clicked.connect(self._on_apps_picker)
        profile_select_btn = self.dialog._get_profile_select_btn()
        if profile_select_btn is not None:
            profile_select_btn.clicked.connect(self._on_select_profile_clicked)
        profile_le = self.dialog._get_profile_le()
        if profile_le is not None:
            profile_le.setCursor(Qt.CursorShape.PointingHandCursor)
            profile_le.mousePressEvent = self._on_profile_le_clicked
        self.dialog._get_icon_btn().clicked.connect(self._on_choose_icon)

        # Hierarchy combo boxes
        self.dialog._get_sphere_cb().currentIndexChanged.connect(self._update_sections)
        self.dialog._get_section_cb().currentIndexChanged.connect(
            self._update_categories
        )

        # Real-time structure updates (e.g. sphere icon changed)
        dc = getattr(self.dialog, "dialog_controller", None)
        sb = getattr(dc, "structure_business", None) if dc else None
        if sb and hasattr(sb, "sphere_updated"):
            try:
                sb.sphere_updated.connect(self._on_sphere_updated)
            except Exception:
                pass

        # Dialog buttons
        self.dialog._get_button_box().accepted.connect(self._on_accept)
        self.dialog._get_button_box().rejected.connect(self.dialog.reject)

    def _on_sphere_updated(self, sphere_id: int, data: dict) -> None:
        if "icon_path" in data and hasattr(self.dialog, "update_sphere_icon_in_combo"):
            self.dialog.update_sphere_icon_in_combo(sphere_id, str(data["icon_path"]))

    def _on_accept(self) -> None:
        """Confirm handler orchestrating validation and save logic."""
        form_data = self._build_form_data()
        result = self._validate_and_save_data(form_data)

        if result["is_valid"]:
            self.dialog.accept()
        else:
            self._handle_validation_errors(form_data, result)

    def cancel_processing(self) -> None:
        """Safely cancel all background tasks and timers.

        - Stop the deferred path processing timer
        - Cancel the active worker and disconnect its signals
        - Disconnect local callback signals
        - Reset internal state flags
        - Increment task id to avoid stale results
        """
        logger.info(
            "LinkDialogHandlers.cancel_processing: task_id=%s processing=%s active_worker=%s callbacks_enabled=%s",
            self._worker_task_id,
            self._is_processing,
            bool(self._active_worker),
            self._callbacks_enabled,
        )
        self._callbacks_enabled = False

        try:
            active_cancel_event = getattr(self, "_active_cancel_event", None)
            if active_cancel_event is not None:
                active_cancel_event.set()
        except Exception:
            logger.debug("cancel_processing: failed to signal cancel event", exc_info=True)

        try:
            self.signals.link_info_finished.disconnect(self._handle_link_info_finished)
        except (TypeError, RuntimeError):
            pass
        try:
            self.signals.simple_error.disconnect(self._handle_link_info_error)
        except (TypeError, RuntimeError):
            pass

        # Stop timer (if still alive)
        try:
            if getattr(self.dialog, "_processing_timer", None):
                self.dialog._processing_timer.stop()
        except (AttributeError, RuntimeError):
            logger.debug(
                "cancel_processing: failed to stop processing timer", exc_info=True
            )

        # Cancel active worker
        if self._active_worker:
            try:
                # Safely disconnect worker signals when present
                try:
                    self._active_worker.signals.finished.disconnect()
                except (AttributeError, RuntimeError):
                    logger.debug(
                        "cancel_processing: failed to disconnect worker finished signal",
                        exc_info=True,
                    )
                try:
                    self._active_worker.signals.error.disconnect()
                except (AttributeError, RuntimeError):
                    logger.debug(
                        "cancel_processing: failed to disconnect worker error signal",
                        exc_info=True,
                    )
                self._active_worker.cancel()
            except (AttributeError, RuntimeError) as e:
                logger.debug(
                    "cancel_processing: failed to cancel worker: %s", e, exc_info=True
                )
            finally:
                self._active_worker = None

        # Reset state and prevent stale results
        self._is_processing = False
        # Reset last processed path to avoid stale warnings on close
        self._last_processed_path = ""
        self._worker_task_id += 1
        try:
            self._active_cancel_event = None
        except Exception:
            pass
        logger.info(
            "LinkDialogHandlers.cancel_processing: completed next_task_id=%s",
            self._worker_task_id,
        )

    def _on_profile_le_clicked(self, event) -> None:
        """Open profile selection dialog when clicking anywhere on the profile line edit."""
        profile_le = self.dialog._get_profile_le()
        if profile_le is not None:
            clear_btn = profile_le.findChild(QToolButton)
            if clear_btn and clear_btn.geometry().contains(event.pos()):
                QLineEdit.mousePressEvent(profile_le, event)
                return
            QLineEdit.mousePressEvent(profile_le, event)
        self._on_select_profile_clicked()
