import logging
from typing import cast

from PyQt6.QtCore import QCoreApplication, QSize, Qt
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QDateEdit,
    QDialog,
    QDoubleSpinBox,
    QLineEdit,
    QListWidget,
    QMenu,
    QMessageBox,
    QPushButton,
    QListView,
    QSpinBox,
    QTextEdit,
    QTimeEdit,
    QToolButton,
)

from app.config_data.runtime_config import runtime_app_config as app_config
from app.core.hotkey_manager import HotkeyManager
from app.utils.ui.icon.path_service import get_current_theme
from app.utils.ui.menu_builders.base import get_menu_icon
from app.utils.ui.qt.combo_helpers import identify_combo_popup_view
from app.utils.ui.qt.delegates.combo_row_height_delegate import ComboRowHeightDelegate
from app.utils.ui.qt.delegates.list_item_height_delegate import (
    ListItemHeightDelegate,
)
from app.views.common.retranslatable import ReTranslatable

logger = logging.getLogger(__name__)


def apply_uniform_height(dialog: QDialog):
    """
    Finds specific widget types within a dialog and sets their height to a uniform 32px.
    Excludes special-cased QToolButtons used for link type selection.
    """
    widgets_to_resize = dialog.findChildren(
        (
            QLineEdit,
            QComboBox,
            QPushButton,
            QToolButton,
            QSpinBox,
            QDoubleSpinBox,
            QDateEdit,
            QTimeEdit,
        )
    )
    for widget in widgets_to_resize:
        # Exclude the large link type selector buttons in LinkDialog
        if isinstance(widget, QToolButton) and widget.property("link_type"):
            continue
        widget.setFixedHeight(app_config.ui.get_dialog_control_height())


def apply_uniform_height_to_message_box(msg_box: QMessageBox):
    """
    Apply uniform 32px height to all buttons in a QMessageBox.
    Call this after adding all buttons to the message box.
    """
    buttons = msg_box.findChildren(QPushButton)
    for button in buttons:
        button.setFixedHeight(app_config.ui.get_dialog_control_height())


def _tr(text: str) -> str:
    return QCoreApplication.translate("MenuActions", text)


def create_context_menu(widget):
    menu = QMenu(widget)

    theme = getattr(getattr(widget, "window", lambda: None)(), "settings", None)
    theme_name = (
        theme.get_theme()
        if theme and hasattr(theme, "get_theme")
        else get_current_theme()
    )

    undo_action = cast(
        QAction,
        menu.addAction(get_menu_icon("undo", theme_name), _tr("&Undo")),
    )
    undo_action.triggered.connect(widget.undo)
    undo_action.setShortcut(HotkeyManager.get_sequence("edit.undo"))

    redo_action = cast(
        QAction,
        menu.addAction(get_menu_icon("redo", theme_name), _tr("&Redo")),
    )
    redo_action.triggered.connect(widget.redo)
    redo_action.setShortcut(HotkeyManager.get_sequence("edit.redo"))

    menu.addSeparator()

    cut_action = cast(
        QAction,
        menu.addAction(get_menu_icon("cut", theme_name), _tr("Cut")),
    )
    cut_action.triggered.connect(widget.cut)
    cut_action.setShortcut(HotkeyManager.get_sequence("edit.cut"))

    copy_action = cast(
        QAction,
        menu.addAction(get_menu_icon("copy", theme_name), _tr("Copy")),
    )
    copy_action.triggered.connect(widget.copy)
    copy_action.setShortcut(HotkeyManager.get_sequence("edit.copy"))

    try:
        clip_has_text = False
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            md = clipboard.mimeData()
            clip_has_text = bool(md and md.hasText() and md.text())
        if clip_has_text:
            paste_action = cast(
                QAction,
                menu.addAction(
                    get_menu_icon("paste", theme_name),
                    _tr("Paste"),
                ),
            )
            paste_action.triggered.connect(widget.paste)
            paste_action.setShortcut(HotkeyManager.get_sequence("edit.paste"))
    except (RuntimeError, AttributeError):
        logger.exception("Failed to evaluate clipboard state for context menu")

    delete_action = cast(
        QAction,
        menu.addAction(get_menu_icon("delete", theme_name), _tr("Delete")),
    )
    delete_action.triggered.connect(widget.clear)
    delete_action.setShortcut(HotkeyManager.get_sequence("edit.delete"))

    menu.addSeparator()

    select_all_action = cast(
        QAction,
        menu.addAction(
            get_menu_icon("select_all", theme_name), _tr("Select all")
        ),
    )
    select_all_action.triggered.connect(widget.selectAll)
    select_all_action.setShortcut(HotkeyManager.get_sequence("edit.select_all"))

    return menu


class BaseDialog(QDialog, ReTranslatable):
    """
    A base dialog class that applies uniform widget heights when shown.

    Note: When inheriting from both BaseDialog and ReTranslatable, call
    ReTranslatable.__init__() explicitly after UI setup to avoid AttributeError.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._styles_applied = False
        self._context_menus: list = []  # Track created context menus for cleanup
        # Connect to language service, but do not call retranslateUi here (done by subclasses)
        try:
            ReTranslatable.__init__(self, call_retranslate=False)
        except Exception:
            # Safely ignore if subclass is not a QObject or lacks destroyed slot
            logger.debug("BaseDialog: ReTranslatable init skipped", exc_info=True)

    def retranslateUi(self) -> None:
        """Base implementation. Subclasses should override and set texts.
        Keep empty to avoid NotImplementedError in the mixin.
        """
        pass

    def showEvent(self, event):
        """
        Overrides the show event to apply styles just before the dialog is displayed.
        """
        if not self._styles_applied:
            apply_uniform_height(self)
            self._apply_combo_popup_styles()
            self._apply_list_widget_styles()
            self._styles_applied = True
            self._setup_russian_context_menus()
        super().showEvent(event)

    def closeEvent(self, event):
        """Cleanup context menus to prevent memory leaks."""
        self._cleanup_context_menus()
        super().closeEvent(event)

    def _cleanup_context_menus(self) -> None:
        """Cleanup all created context menus."""
        for menu in self._context_menus:
            try:
                if menu and not menu.isHidden():
                    menu.close()
                menu.deleteLater()
            except (AttributeError, RuntimeError):
                pass
        self._context_menus.clear()

    def _setup_russian_context_menus(self):
        """Setup context menus with proper cleanup tracking."""
        for widget in self.findChildren((QLineEdit, QTextEdit)):
            widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            widget.customContextMenuRequested.connect(
                # Track created menus for cleanup
                lambda pos, w=widget: self._show_context_menu(w, pos)
            )

    def _apply_combo_popup_styles(self):
        """Apply DPI-aware row height delegate and icon size to all QComboBox in this dialog."""
        try:
            combos = self.findChildren(QComboBox)
            if not combos:
                return
            # Determine DPI scale from this dialog window
            scale = 1.0
            try:
                wh = self.windowHandle()
                screen = wh.screen() if wh else None
                if screen is not None:
                    scale = max(1.0, screen.logicalDotsPerInch() / 96.0)
            except (RuntimeError, AttributeError):
                logger.exception("Failed to determine DPI scale for combo boxes")
            # DPI-aware popup icon size based on 24px logical (was 20)
            target_icon = int(round(24 * scale))
            for combo in combos:
                try:
                    view = combo.view()
                    if view is None or not isinstance(view, QListView):
                        view = QListView(combo)
                        combo.setView(view)
                    identify_combo_popup_view(combo)
                    # Apply row height delegate to the combo (popup uses it), DPI-aware 32px logical
                    combo.setItemDelegate(ComboRowHeightDelegate(combo))
                    # Ensure the combo field icon matches popup icon size
                    combo.setIconSize(QSize(target_icon, target_icon))
                    # Force the Qt popup path and enable hover tracking uniformly.
                    if view is not None:
                        view.setIconSize(QSize(target_icon, target_icon))
                        view.setMouseTracking(True)
                        view.setUniformItemSizes(False)
                        viewport = view.viewport()
                        if viewport is not None:
                            viewport.setMouseTracking(True)
                            viewport.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
                except (RuntimeError, AttributeError, TypeError):
                    logger.exception(
                        "Failed to apply combo popup styles to a QComboBox"
                    )
                    continue
        except (RuntimeError, AttributeError):
            logger.exception("Failed to apply combo popup styles (outer)")

    def _apply_list_widget_styles(self) -> None:
        """Apply DPI-aware row height delegate to all QListWidget in this dialog."""
        try:
            list_widgets = self.findChildren(QListWidget)
            if not list_widgets:
                return
            for list_widget in list_widgets:
                try:
                    # Skip if delegate is already set (e.g., manually in subclass)
                    if list_widget.itemDelegate() is not None and isinstance(
                        list_widget.itemDelegate(), ListItemHeightDelegate
                    ):
                        continue
                    # Apply row height delegate for 32px logical height
                    list_widget.setItemDelegate(ListItemHeightDelegate(list_widget))
                except (RuntimeError, AttributeError, TypeError):
                    logger.exception(
                        "Failed to apply list widget styles to a QListWidget"
                    )
                    continue
        except (RuntimeError, AttributeError):
            logger.exception("Failed to apply list widget styles (outer)")

    def _show_context_menu(self, widget, pos):
        """Show context menu with tracking for cleanup."""
        try:
            menu = create_context_menu(widget)
            self._context_menus.append(menu)
            menu.popup(widget.mapToGlobal(pos))
        except Exception as e:
            logger.warning("Failed to show context menu: %s", e)

    # --- Local message box helpers to avoid importing controllers in views ---
    def show_info(
        self,
        text: str,
        title: str | None = None,
        informative_text: str | None = None,
        details: str | None = None,
        silent: bool = False,
    ) -> None:
        try:
            mb = QMessageBox(self)
            mb.setIcon(QMessageBox.Icon.Information)
            mb.setWindowTitle(title or self.tr("Information"))
            mb.setText(text)
            if informative_text:
                mb.setInformativeText(informative_text)
            if details:
                mb.setDetailedText(details)
            mb.setStandardButtons(QMessageBox.StandardButton.Ok)
            apply_uniform_height_to_message_box(mb)
            if not silent:
                mb.exec()
        except (RuntimeError, AttributeError):
            logger.exception("Failed to show info message box")

    def show_warning(
        self,
        text: str,
        title: str | None = None,
        informative_text: str | None = None,
        details: str | None = None,
        silent: bool = False,
    ) -> None:
        try:
            mb = QMessageBox(self)
            mb.setIcon(QMessageBox.Icon.Warning)
            mb.setWindowTitle(title or self.tr("Warning"))
            mb.setText(text)
            if informative_text:
                mb.setInformativeText(informative_text)
            if details:
                mb.setDetailedText(details)
            mb.setStandardButtons(QMessageBox.StandardButton.Ok)
            apply_uniform_height_to_message_box(mb)
            if not silent:
                mb.exec()
        except (RuntimeError, AttributeError):
            logger.exception("Failed to show warning message box")

    def show_error(
        self,
        text: str,
        title: str | None = None,
        informative_text: str | None = None,
        details: str | None = None,
        silent: bool = False,
    ) -> None:
        try:
            mb = QMessageBox(self)
            mb.setIcon(QMessageBox.Icon.Critical)
            mb.setWindowTitle(title or self.tr("Error"))
            mb.setText(text)
            if informative_text:
                mb.setInformativeText(informative_text)
            if details:
                mb.setDetailedText(details)
            mb.setStandardButtons(QMessageBox.StandardButton.Ok)
            apply_uniform_height_to_message_box(mb)
            if not silent:
                mb.exec()
        except (RuntimeError, AttributeError):
            logger.exception("Failed to show error message box")

    def show_confirmation(
        self,
        text: str,
        title: str | None = None,
        informative_text: str | None = None,
        details: str | None = None,
    ) -> bool:
        try:
            mb = QMessageBox(self)
            mb.setIcon(QMessageBox.Icon.Question)
            mb.setWindowTitle(title or self.tr("Confirmation"))
            mb.setText(text)
            if informative_text:
                mb.setInformativeText(informative_text)
            if details:
                mb.setDetailedText(details)
            mb.setStandardButtons(
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            mb.setDefaultButton(QMessageBox.StandardButton.No)
            apply_uniform_height_to_message_box(mb)
            return mb.exec() == QMessageBox.StandardButton.Yes
        except (RuntimeError, AttributeError):
            logger.exception("Failed to show confirmation dialog")
            return False
