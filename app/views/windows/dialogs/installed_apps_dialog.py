"""Dialog for selecting an installed application from Windows."""

import logging
from pathlib import Path
from typing import Any, Optional

from PyQt6 import sip
from PyQt6.QtCore import QCoreApplication, QFileInfo, QSize, Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QDialogButtonBox,
    QFileIconProvider,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

from app.utils.i18n.common import tr as tr_common
from app.utils.system.installed_apps_service import (
    InstalledAppInfo,
    extract_shell_icon_image,
    get_installed_apps,
)
from app.utils.ui.qt.delegates.list_item_height_delegate import ListItemHeightDelegate
from app.views.windows.dialogs.base_dialog import BaseDialog

logger = logging.getLogger(__name__)

# lupdate hints for InstalledAppsDialog
if False:  # pragma: no cover
    QCoreApplication.translate("InstalledAppsDialog", "Select Installed Application")
    QCoreApplication.translate("InstalledAppsDialog", "Search applications...")
    QCoreApplication.translate("InstalledAppsDialog", "Loading installed applications...")
    QCoreApplication.translate("InstalledAppsDialog", "Total applications: %d")
    QCoreApplication.translate("InstalledAppsDialog", "Shown: %d of %d")
    QCoreApplication.translate("InstalledAppsDialog", "Select")
    QCoreApplication.translate("InstalledAppsDialog", "Cancel")


class _AppsLoaderThread(QThread):
    """Background thread to fetch installed applications and their authentic icons."""

    apps_ready = pyqtSignal(list)
    icon_ready = pyqtSignal(int, object)
    all_done = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._is_cancelled = False

    def cancel(self) -> None:
        self._is_cancelled = True
        self.requestInterruption()

    def run(self) -> None:
        try:
            apps = get_installed_apps()
            if self._is_cancelled or self.isInterruptionRequested():
                return
            self.apps_ready.emit(apps)

            # Progressive icon extraction in background (works for UWP and clean .exe)
            for idx, app in enumerate(apps):
                if self._is_cancelled or self.isInterruptionRequested():
                    return
                if getattr(app, "cached_image", None) is not None:
                    self.icon_ready.emit(idx, app.cached_image)
                    continue
                try:
                    target_src = (
                        app.icon_path
                        if (app.icon_path and Path(app.icon_path).exists())
                        else app.path
                    )
                    img = extract_shell_icon_image(target_src)
                    if img is not None and not img.isNull():
                        if self._is_cancelled or self.isInterruptionRequested():
                            return
                        app.cached_image = img
                        self.icon_ready.emit(idx, img)
                except Exception:
                    pass
        except Exception as e:
            logger.error("Failed to load installed apps: %s", e)
            if not (self._is_cancelled or self.isInterruptionRequested()):
                self.apps_ready.emit([])
        finally:
            if not (self._is_cancelled or self.isInterruptionRequested()):
                self.all_done.emit()


class InstalledAppsDialog(BaseDialog):
    """Dialog allowing the user to select from installed Windows applications."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("InstalledAppsDialog")
        self.setWindowTitle(self.tr("Select Installed Application"))
        self.setMinimumSize(480, 560)
        self.resize(520, 620)

        self._all_apps: list[InstalledAppInfo] = []
        self._selected_app: Optional[InstalledAppInfo] = None
        self._icon_provider = QFileIconProvider()

        self._setup_ui()
        self._start_loading()
        self.retranslateUi()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # 1. Search bar
        search_layout = QHBoxLayout()
        self.search_le = QLineEdit()
        self.search_le.setObjectName("appsSearchLineEdit")
        self.search_le.setPlaceholderText(self.tr("Search applications..."))
        self.search_le.setClearButtonEnabled(True)
        self.search_le.textChanged.connect(self._on_search_changed)
        search_layout.addWidget(self.search_le)
        layout.addLayout(search_layout)

        # 2. Loading indicator
        self.loading_label = QLabel(self.tr("Loading installed applications..."))
        self.loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.loading_bar = QProgressBar()
        self.loading_bar.setRange(0, 0)  # Indeterminate
        self.loading_bar.setFixedHeight(4)
        self.loading_bar.setTextVisible(False)
        layout.addWidget(self.loading_label)
        layout.addWidget(self.loading_bar)

        # 3. List of apps
        self.apps_list = QListWidget()
        self.apps_list.setObjectName("installedAppsListWidget")
        self.apps_list.setIconSize(QSize(32, 32))
        self.apps_list.setItemDelegate(
            ListItemHeightDelegate(self.apps_list, target_height=42)
        )
        self.apps_list.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.apps_list.itemSelectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self.apps_list, 1)

        # 4. Bottom row: count label on the left, buttons on the right
        bottom_layout = QHBoxLayout()
        bottom_layout.setContentsMargins(0, 4, 0, 0)
        bottom_layout.setSpacing(12)

        self.count_label = QLabel("")
        self.count_label.setStyleSheet("color: #888888; font-size: 11px;")
        bottom_layout.addWidget(self.count_label, 0, Qt.AlignmentFlag.AlignVCenter)

        bottom_layout.addStretch(1)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.ok_button = self.button_box.button(QDialogButtonBox.StandardButton.Ok)
        self.cancel_button = self.button_box.button(
            QDialogButtonBox.StandardButton.Cancel
        )
        if self.ok_button:
            self.ok_button.setText(self.tr("Select"))
            self.ok_button.setEnabled(False)
        if self.cancel_button:
            self.cancel_button.setText(tr_common("Cancel"))

        self.button_box.accepted.connect(self._on_accepted)
        self.button_box.rejected.connect(self.reject)
        bottom_layout.addWidget(self.button_box, 0, Qt.AlignmentFlag.AlignVCenter)

        layout.addLayout(bottom_layout)

    def _start_loading(self) -> None:
        # Pass parent=None to prevent QThread destroyed while running crash on dialog destruction
        self.loader_thread = _AppsLoaderThread(parent=None)
        self.loader_thread.finished.connect(self.loader_thread.deleteLater)
        self.loader_thread.apps_ready.connect(self._on_apps_loaded)
        self.loader_thread.icon_ready.connect(self._on_icon_loaded)
        self.loader_thread.all_done.connect(self._on_loading_done)
        self.loader_thread.start()

    def _on_apps_loaded(self, apps: list[InstalledAppInfo]) -> None:
        self._all_apps = apps

        self.apps_list.clear()
        for app in apps:
            item = QListWidgetItem()
            item.setText(app.name)
            item.setSizeHint(QSize(0, 42))
            # Use app description as secondary tooltip
            item.setToolTip(f"{app.name}\n{app.path}")
            item.setData(Qt.ItemDataRole.UserRole, app)
            self.apps_list.addItem(item)

        self._update_count_label()
        self.search_le.setFocus()

    def _on_icon_loaded(self, row: int, img: Any) -> None:
        if 0 <= row < self.apps_list.count():
            item = self.apps_list.item(row)
            if item is not None and img is not None:
                from PyQt6.QtGui import QIcon, QPixmap

                item.setIcon(QIcon(QPixmap.fromImage(img)))

    def _on_loading_done(self) -> None:
        self.loading_label.setVisible(False)
        self.loading_bar.setVisible(False)

    def _on_search_changed(self, text: str) -> None:
        query = text.strip().lower()
        visible_count = 0
        for i in range(self.apps_list.count()):
            item = self.apps_list.item(i)
            matches = not query or query in item.text().lower()
            item.setHidden(not matches)
            if matches:
                visible_count += 1

        self._update_count_label(visible_count)

    def _update_count_label(self, count: Optional[int] = None) -> None:
        total = len(self._all_apps)
        current = count if count is not None else total
        if total == 0:
            self.count_label.setText("")
        elif current == total:
            self.count_label.setText(
                self.tr("Total applications: %d") % total
            )
        else:
            self.count_label.setText(
                self.tr("Shown: %d of %d") % (current, total)
            )

    def _on_selection_changed(self) -> None:
        selected_items = self.apps_list.selectedItems()
        has_selection = len(selected_items) > 0
        if self.ok_button:
            self.ok_button.setEnabled(has_selection)
        if has_selection:
            self._selected_app = selected_items[0].data(Qt.ItemDataRole.UserRole)
        else:
            self._selected_app = None

    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        self._selected_app = item.data(Qt.ItemDataRole.UserRole)
        self.accept()

    def _on_accepted(self) -> None:
        if self._selected_app is not None:
            self.accept()

    def _stop_loader_thread(self, timeout_ms: int = 1500) -> None:
        """Cooperatively cancel and disconnect the background loader thread."""
        thread = getattr(self, "loader_thread", None)
        if thread is None:
            return

        # PyQt6: guard against already-destroyed C++ QThread object.
        # Use sip.isdeleted with a RuntimeError fallback to be robust across bindings.
        def _alive(qobj) -> bool:
            try:
                return not sip.isdeleted(qobj)
            except Exception:
                try:
                    qobj.objectName()
                    return True
                except RuntimeError:
                    return False

        if not _alive(thread):
            self.loader_thread = None
            return

        # Disconnect signals so finishing thread does not touch destroyed UI
        try:
            if _alive(thread):
                thread.apps_ready.disconnect(self._on_apps_loaded)
        except Exception:
            pass
        try:
            if _alive(thread):
                thread.icon_ready.disconnect(self._on_icon_loaded)
        except Exception:
            pass
        try:
            if _alive(thread):
                thread.all_done.disconnect(self._on_loading_done)
        except Exception:
            pass

        try:
            if _alive(thread) and thread.isRunning():
                thread.cancel()
                thread.quit()
                if not thread.wait(timeout_ms):
                    logger.warning(
                        "Installed apps loader thread did not terminate within %d ms; running asynchronously until completion",
                        timeout_ms,
                    )
        except RuntimeError as e:
            logger.debug("Loader thread already destroyed while stopping: %s", e)

        # Drop the Python reference so repeated calls (reject/closeEvent/accept)
        # never touch a possibly-deleted C++ object.
        self.loader_thread = None

    def accept(self) -> None:
        self._stop_loader_thread()
        super().accept()

    def closeEvent(self, event) -> None:
        self._stop_loader_thread()
        super().closeEvent(event)

    def reject(self) -> None:
        self._stop_loader_thread()
        super().reject()

    def get_selected_app(self) -> Optional[InstalledAppInfo]:
        """Return the user-selected application info, or None if cancelled."""
        return self._selected_app

    def retranslateUi(self) -> None:
        """Update strings when language changes."""
        self.setWindowTitle(self.tr("Select Installed Application"))
        if hasattr(self, "search_le") and self.search_le is not None:
            self.search_le.setPlaceholderText(self.tr("Search applications..."))
        if hasattr(self, "loading_label") and self.loading_label is not None:
            if self.loading_label.isVisible():
                self.loading_label.setText(self.tr("Loading installed applications..."))
        if hasattr(self, "ok_button") and self.ok_button is not None:
            self.ok_button.setText(self.tr("Select"))
        if hasattr(self, "cancel_button") and self.cancel_button is not None:
            self.cancel_button.setText(tr_common("Cancel"))
        if hasattr(self, "count_label"):
            self._update_count_label()
