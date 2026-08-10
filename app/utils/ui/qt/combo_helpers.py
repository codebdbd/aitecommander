from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Callable

from PyQt6.QtCore import QPoint, QRect, QSize, Qt
from PyQt6.QtGui import QGuiApplication, QIcon, QKeyEvent
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QListView,
    QWidget,
)


COMBO_POPUP_VIEW_OBJECT_NAME = "comboPopupView"
COMBO_POPUP_CONTAINER_OBJECT_NAME = "comboPopupContainer"


class ComboPopupListView(QListView):
    """List view used by the custom combo popup."""

    def __init__(
        self,
        owner: "PopupComboBox",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._owner = owner
        self.setObjectName(COMBO_POPUP_VIEW_OBJECT_NAME)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setMouseTracking(True)
        viewport = self.viewport()
        if viewport is not None:
            viewport.setMouseTracking(True)
            viewport.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._owner._activate_popup_index(self.currentIndex())
            event.accept()
            return
        if event.key() == Qt.Key.Key_Escape:
            self._owner.hidePopup()
            event.accept()
            return
        super().keyPressEvent(event)


class _ComboPopupFrame(QFrame):
    """Popup container for a custom combo box dropdown."""

    def __init__(self, owner: "PopupComboBox") -> None:
        super().__init__(
            None,
            Qt.WindowType.Popup
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint,
        )
        self._owner = owner
        self.setObjectName(COMBO_POPUP_CONTAINER_OBJECT_NAME)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(owner._popup_view)

    def hideEvent(self, event) -> None:
        self._owner._popup_visible = False
        super().hideEvent(event)


class PopupComboBox(QComboBox):
    """QComboBox with a custom popup to avoid native dropdown chrome."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._popup_visible = False
        self._popup_view = ComboPopupListView(self)
        self._popup = _ComboPopupFrame(self)
        self._popup_view.clicked.connect(self._activate_popup_index)
        self._popup_view.activated.connect(self._activate_popup_index)
        self.currentIndexChanged.connect(self._sync_popup_current_index)
        self._install_popup_model()

    def view(self) -> QListView:  # type: ignore[override]
        return self._popup_view

    def setView(self, item_view: QAbstractItemView) -> None:  # type: ignore[override]
        if not isinstance(item_view, QListView):
            raise TypeError("PopupComboBox requires QListView-based popup views")
        if item_view is self._popup_view:
            return

        old_view = self._popup_view
        self._popup.layout().removeWidget(old_view)
        old_view.setParent(None)
        try:
            old_view.clicked.disconnect(self._activate_popup_index)
        except (RuntimeError, TypeError):
            pass
        try:
            old_view.activated.disconnect(self._activate_popup_index)
        except (RuntimeError, TypeError):
            pass

        self._popup_view = item_view
        self._popup_view.setParent(self._popup)
        self._popup_view.setObjectName(COMBO_POPUP_VIEW_OBJECT_NAME)
        self._popup_view.setMouseTracking(True)
        viewport = self._popup_view.viewport()
        if viewport is not None:
            viewport.setMouseTracking(True)
            viewport.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self._popup.layout().addWidget(self._popup_view)
        self._popup_view.clicked.connect(self._activate_popup_index)
        self._popup_view.activated.connect(self._activate_popup_index)
        self._install_popup_model()

    def setModel(self, model) -> None:  # type: ignore[override]
        super().setModel(model)
        self._install_popup_model()

    def setRootModelIndex(self, index) -> None:  # type: ignore[override]
        super().setRootModelIndex(index)
        self._popup_view.setRootIndex(index)

    def setItemDelegate(self, delegate) -> None:  # type: ignore[override]
        super().setItemDelegate(delegate)
        self._popup_view.setItemDelegate(delegate)

    def setIconSize(self, size: QSize) -> None:  # type: ignore[override]
        super().setIconSize(size)
        self._popup_view.setIconSize(size)

    def showPopup(self) -> None:  # type: ignore[override]
        if self.count() <= 0:
            return
        self._install_popup_model()
        self._sync_popup_current_index(self.currentIndex())
        self._resize_popup()
        self._popup.move(self._popup_origin())
        self._popup_visible = True
        self._popup.show()
        self._popup.raise_()
        self._popup_view.setFocus(Qt.FocusReason.PopupFocusReason)

    def hidePopup(self) -> None:  # type: ignore[override]
        if self._popup.isVisible():
            self._popup.hide()
        self._popup_visible = False

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Down, Qt.Key.Key_Up, Qt.Key.Key_F4):
            if not self._popup_visible:
                self.showPopup()
                event.accept()
                return
        super().keyPressEvent(event)

    def _install_popup_model(self) -> None:
        self._popup_view.setModel(self.model())
        self._popup_view.setRootIndex(self.rootModelIndex())
        self._popup_view.setIconSize(self.iconSize())
        delegate = self.itemDelegate()
        if delegate is not None:
            self._popup_view.setItemDelegate(delegate)

    def _sync_popup_current_index(self, current_index: int) -> None:
        if current_index < 0 or self.model() is None:
            self._popup_view.clearSelection()
            return
        model_index = self.model().index(
            current_index, self.modelColumn(), self.rootModelIndex()
        )
        if model_index.isValid():
            self._popup_view.setCurrentIndex(model_index)
            self._popup_view.scrollTo(
                model_index,
                QAbstractItemView.ScrollHint.PositionAtCenter,
            )

    def _activate_popup_index(self, model_index) -> None:
        if not model_index.isValid():
            return
        self.setCurrentIndex(model_index.row())
        self.hidePopup()
        self.setFocus(Qt.FocusReason.MouseFocusReason)

    def _resize_popup(self) -> None:
        content_width = self.width()
        visible_rows = min(max(1, self.maxVisibleItems()), self.count())
        row_height = self._popup_row_height()
        height = (visible_rows * row_height) + 2
        self._popup.resize(content_width, height)

    def _popup_row_height(self) -> int:
        if self.count() <= 0:
            return max(self.height(), 32)
        first = self.model().index(0, self.modelColumn(), self.rootModelIndex())
        row_height = self._popup_view.sizeHintForIndex(first).height()
        if row_height <= 0:
            row_height = max(self.height(), 32)
        return row_height

    def _popup_origin(self) -> QPoint:
        origin = self.mapToGlobal(self.rect().bottomLeft())
        origin.setY(origin.y() - 1)
        screen = QGuiApplication.screenAt(origin) or self.screen()
        if screen is None:
            return origin
        available = screen.availableGeometry()
        popup_rect = QRect(origin, self._popup.size())
        if popup_rect.right() > available.right():
            popup_rect.moveRight(available.right())
        if popup_rect.left() < available.left():
            popup_rect.moveLeft(available.left())
        if popup_rect.bottom() > available.bottom():
            above = self.mapToGlobal(self.rect().topLeft())
            popup_rect.moveTop(max(available.top(), above.y() - self._popup.height()))
        return popup_rect.topLeft()


def identify_combo_popup_view(combo: QComboBox) -> QAbstractItemView | None:
    """Give the popup view a stable QSS target after Qt reparents it."""
    view = combo.view()
    if view is not None and view.objectName() != COMBO_POPUP_VIEW_OBJECT_NAME:
        view.setObjectName(COMBO_POPUP_VIEW_OBJECT_NAME)
        style = view.style()
        style.unpolish(view)
        style.polish(view)
        view.update()
    return view


def select_combo_data(
    combo: QComboBox,
    *,
    current_data: object = None,
    preferred_data: object = None,
    fallback_to_first: bool = True,
) -> int:
    """Select combo item by current/preferred data with explicit fallback order.

    Returns the applied index, or ``-1`` if no suitable selection exists.
    """
    target_index = -1
    if current_data is not None:
        target_index = combo.findData(current_data)
    if target_index < 0 and preferred_data is not None:
        target_index = combo.findData(preferred_data)
    if target_index < 0 and fallback_to_first and combo.count() > 0:
        target_index = 0
    if target_index >= 0:
        combo.setCurrentIndex(target_index)
    return target_index


def select_first_combo_item(
    combo: QComboBox, *, only_if_unset: bool = False
) -> bool:
    """Select the first combo item.

    When ``only_if_unset`` is true, preserve the existing selection if the combo
    already has a valid current index.
    """
    if combo.count() <= 0:
        return False
    if only_if_unset and combo.currentIndex() >= 0:
        return False
    combo.setCurrentIndex(0)
    return True


def try_select_combo_data(combo: Any, data_id: Any) -> bool:
    """Best-effort ``findData`` selection for dialogs that tolerate missing combos."""
    try:
        if data_id is None:
            return False
        return select_combo_data(
            combo,
            current_data=data_id,
            fallback_to_first=False,
        ) >= 0
    except (AttributeError, RuntimeError, TypeError):
        return False


def try_select_first_combo_item(combo: Any, *, only_if_unset: bool = False) -> bool:
    """Best-effort first-item selection for dialogs that tolerate missing combos."""
    try:
        return select_first_combo_item(combo, only_if_unset=only_if_unset)
    except (AttributeError, RuntimeError, TypeError):
        return False


def add_combo_item(
    combo: QComboBox,
    text: object,
    data: object = None,
    *,
    icon: QIcon | None = None,
) -> None:
    """Add one combo item with optional icon and arbitrary user data."""
    display_text = str(text)
    if icon is not None and not icon.isNull():
        combo.addItem(icon, display_text, data)
        return
    combo.addItem(display_text, data)


def add_combo_mapping_item(
    combo: QComboBox,
    item: Mapping[str, Any],
    *,
    text_key: str = "name",
    data_key: str = "id",
    icon_key: str | None = None,
    icon_loader: Callable[[str], QIcon | None] | None = None,
) -> bool:
    """Add a combo item from a mapping-like record.

    Returns ``True`` when an item was added, ``False`` when required keys are absent.
    """
    text = item.get(text_key)
    data = item.get(data_key)
    if text is None or data is None:
        return False

    icon = None
    if icon_key and icon_loader is not None:
        icon = icon_loader(str(item.get(icon_key, "")))

    add_combo_item(combo, text, data, icon=icon)
    return True
