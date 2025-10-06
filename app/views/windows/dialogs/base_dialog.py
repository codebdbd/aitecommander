import logging

from PyQt6.QtCore import QCoreApplication, QSize, Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QToolButton,
)

from app.utils.ui.icon.icon_operations.cache_proxy import icon_cache
from app.utils.ui.icon.path_service import get_current_theme
from app.utils.ui.qt.delegates.combo_row_height_delegate import ComboRowHeightDelegate

from app.ui.retranslatable import ReTranslatable

logger = logging.getLogger(__name__)


def apply_uniform_height(dialog: QDialog):
    """
    Finds specific widget types within a dialog and sets their height to a uniform 32px.
    Excludes special-cased QToolButtons used for link type selection.
    """
    widgets_to_resize = dialog.findChildren(
        (QLineEdit, QComboBox, QPushButton, QToolButton, QSpinBox)
    )
    for widget in widgets_to_resize:
        # Exclude the large link type selector buttons in LinkDialog
        if isinstance(widget, QToolButton) and widget.property("link_type"):
            continue
        widget.setFixedHeight(32)
        if isinstance(widget, QPushButton):
            try:
                base_size = dialog.font().pointSize()
                f = widget.font()
                f.setPointSize(base_size)
                widget.setFont(f)
            except (RuntimeError, AttributeError, TypeError):
                # Fall back to leaving the current font as-is if something goes wrong
                logger.exception("Failed to set uniform font size for QPushButton")


def _tr(text: str) -> str:
    return QCoreApplication.translate("BaseDialog", text)


def create_context_menu(widget):
    menu = QMenu(widget)

    theme = get_current_theme()

    undo_action = menu.addAction(
        icon_cache.get_icon("undo", theme, "context_menu"), _tr("Undo")
    )
    undo_action.triggered.connect(widget.undo)
    undo_action.setShortcut("Ctrl+Z")

    redo_action = menu.addAction(
        icon_cache.get_icon("redo", theme, "context_menu"), _tr("Redo")
    )
    redo_action.triggered.connect(widget.redo)
    redo_action.setShortcut("Ctrl+Y")

    menu.addSeparator()

    cut_action = menu.addAction(
        icon_cache.get_icon("cut", theme, "context_menu"), _tr("Cut")
    )
    cut_action.triggered.connect(widget.cut)
    cut_action.setShortcut("Ctrl+X")

    copy_action = menu.addAction(
        icon_cache.get_icon("copy", theme, "context_menu"), _tr("Copy")
    )
    copy_action.triggered.connect(widget.copy)
    copy_action.setShortcut("Ctrl+C")

    try:
        from PyQt6.QtWidgets import QApplication

        app = QApplication.instance()
        clip_has_text = False
        if app is not None:
            md = app.clipboard().mimeData()
            clip_has_text = bool(md and md.hasText() and md.text())
        if clip_has_text:
            paste_action = menu.addAction(
                icon_cache.get_icon("paste", theme, "context_menu"), _tr("Paste")
            )
            paste_action.triggered.connect(widget.paste)
            paste_action.setShortcut("Ctrl+V")
    except (RuntimeError, AttributeError):
        logger.exception("Failed to evaluate clipboard state for context menu")

    delete_action = menu.addAction(
        icon_cache.get_icon("delete", theme, "context_menu"), _tr("Delete")
    )
    delete_action.triggered.connect(widget.clear)
    delete_action.setShortcut("Del")

    menu.addSeparator()

    select_all_action = menu.addAction(
        icon_cache.get_icon("select_all", theme, "context_menu"), _tr("Select All")
    )
    select_all_action.triggered.connect(widget.selectAll)
    select_all_action.setShortcut("Ctrl+A")

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
        self._context_menus: list = []  # ✅ ИСПРАВЛЕНИЕ: Трекинг context menu для cleanup
        # Подключаемся к службе языков, но не вызываем retranslateUi здесь (делают наследники)
        try:
            ReTranslatable.__init__(self, call_retranslate=False)
        except Exception:
            # Безопасно игнорируем, если наследник не QObject или нет слота destroyed
            logger.debug("BaseDialog: ReTranslatable init skipped", exc_info=True)
 
    def retranslateUi(self) -> None:
        """Базовая реализация. Наследники должны переопределить и установить тексты.
        Оставляем пустой метод, чтобы избежать NotImplementedError в миксине.
        """
        pass

    def showEvent(self, event):
        """
        Overrides the show event to apply styles just before the dialog is displayed.
        """
        if not self._styles_applied:
            apply_uniform_height(self)
            self._apply_combo_popup_styles()
            self._styles_applied = True
            self._setup_russian_context_menus()
        super().showEvent(event)

    def closeEvent(self, event):
        """✅ ИСПРАВЛЕНИЕ: Cleanup context menus для предотвращения утечек памяти."""
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
                # ✅ ИСПРАВЛЕНИЕ: Трекинг созданных menu для cleanup
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
                    # Apply row height delegate to the combo (popup uses it), DPI-aware 32px logical
                    combo.setItemDelegate(ComboRowHeightDelegate(combo))
                    # Ensure the combo field icon matches popup icon size
                    combo.setIconSize(QSize(target_icon, target_icon))
                    # Ensure popup view exists and set icon size
                    view = combo.view()
                    if view is not None:
                        view.setIconSize(QSize(target_icon, target_icon))
                except (RuntimeError, AttributeError, TypeError):
                    logger.exception(
                        "Failed to apply combo popup styles to a QComboBox"
                    )
                    continue
        except (RuntimeError, AttributeError):
            logger.exception("Failed to apply combo popup styles (outer)")

    def _show_context_menu(self, widget, pos):
        """✅ ИСПРАВЛЕНИЕ: Show context menu с трекингом для cleanup."""
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
            if not silent:
                mb.exec()
        except (RuntimeError, AttributeError):
            logger.exception("Failed to show error message box")

    def ask_confirmation(
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
            return mb.exec() == QMessageBox.StandardButton.Yes
        except (RuntimeError, AttributeError):
            logger.exception("Failed to show confirmation dialog")
            return False
