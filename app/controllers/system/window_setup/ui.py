"""
UI elements and dependency injection.
"""

import logging
from functools import partial
from typing import Any

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QAction, QFont
from PyQt6.QtWidgets import QPushButton, QWidget

from app.utils.ui.icon.icon_operations.creators import themed_icon
from app.utils.ui.icon.path_service import get_current_theme
from app.utils.ui.menu_builders.category_menu_builder import CategoryMenuBuilder

from .types import SetupError

logger = logging.getLogger(__name__)


def setup_ui_elements(window: Any, controllers: dict[str, Any]) -> None:
    """Create UI elements: sphere switch action and button, insert into panel."""
    window.switch_sphere_action = QAction(
        themed_icon("switch.svg", theme=get_current_theme(), source="main_window"),
        "Switch Sphere (F6)",
        window,
    )
    window.switch_sphere_action.setToolTip("Switch to next available sphere")
    window.switch_sphere_action.triggered.connect(
        window.structure.switch_to_next_sphere
    )

    window.switch_sphere_button = QPushButton(
        window.switch_sphere_action.icon(), "Sphere (F6)"
    )
    window.switch_sphere_button.setToolTip(window.switch_sphere_action.toolTip())

    font = QFont()
    try:
        font.setPointSize(window.font().pointSize())
    except Exception:
        font.setPointSize(10)
    window.switch_sphere_button.setFont(font)
    window.switch_sphere_button.clicked.connect(window.switch_sphere_action.trigger)

    bottom_container = window.findChild(QWidget, "bottomBarContainer")
    if bottom_container and bottom_container.layout():
        bottom_container.layout().insertWidget(0, window.switch_sphere_button)


def setup_dependency_injection(window: Any, controllers: dict[str, Any]) -> None:
    """Schedule deferred dependency injection into widgets."""
    QTimer.singleShot(0, partial(_deferred_setup, window, controllers))


def _deferred_setup(window: Any, controllers: dict[str, Any]) -> None:
    try:
        _inject_to_category_tiles(window, controllers)
        from .wiring import _connect_top_panels_signals_explicit

        _connect_top_panels_signals_explicit(
            top_panels_controller=window.top_panels_controller,
            links_actions=window.links_actions,
            fav_widget=window.fav_widget,
            recent_links_widget=window.recent_links_widget,
            quick_add_widget=(
                window.quick_add_widget if hasattr(window, "quick_add_widget") else None
            ),
            auto_hide_tree_filter=(
                window._auto_hide_tree_filter
                if hasattr(window, "_auto_hide_tree_filter")
                else None
            ),
            topbar_manager=(
                window._topbar_manager if hasattr(window, "_topbar_manager") else None
            ),
        )
    except (AttributeError, TypeError, SetupError) as e:
        logger.error("Failed during deferred dependency injection: %s", e)
        raise


def _inject_to_category_tiles(window: Any, controllers: dict[str, Any]) -> None:
    """Perform dependency injection for CategoryTiles."""
    if not (hasattr(window, "tiles") and window.tiles):
        return

    from app.controllers.ui.dialogs import DialogMixin

    class DialogProvider(DialogMixin):
        def __init__(self, parent_widget):
            self.parent = parent_widget

        def show_link_dialog_for_category(
            self, category_id: int | None = None, link=None
        ) -> bool:
            """Proxy link dialog show call to main window."""
            try:
                if hasattr(self.parent, "show_link_dialog_for_category"):
                    return bool(
                        self.parent.show_link_dialog_for_category(
                            category_id=category_id, link=link
                        )
                    )
                self.show_error("Cannot open link dialog: window not ready.")
                return False
            except Exception as e:
                self.show_error(f"Error opening link dialog: {e}")
                return False

    dialog_provider = DialogProvider(window)

    window.tiles.inject_dependencies(
        structure_controller=controllers["structure"],
        ui_state_manager=controllers["ui_state"],
        dialog_provider=dialog_provider,
    )

    tiles = window.tiles
    structure_ctrl = controllers["structure"]

    def on_tiles_context_menu(category_id: int, global_pos):
        # Context menu errors are not related to wiring and should not be hidden.
        # Log unexpected errors, but don't use general catch in wiring blocks.
        try:
            builder = CategoryMenuBuilder(tiles.view, window)
            menu, edit_action, add_link_action, delete_action = builder.build(
                category_id,
                edit_cb=structure_ctrl.handle_edit_category,
                delete_cb=structure_ctrl.handle_delete_category,
                add_link_cb=dialog_provider.show_link_dialog_for_category,
            )
            menu.popup(global_pos)
        except Exception:
            logger.exception("Failed to show category tiles context menu")

    try:
        tiles.contextMenuRequested.connect(on_tiles_context_menu)
        tiles.editRequested.connect(structure_ctrl.handle_edit_category)
        tiles.deleteRequested.connect(structure_ctrl.handle_delete_category)
        tiles.addLinkRequested.connect(dialog_provider.show_link_dialog_for_category)
    except (AttributeError, TypeError) as e:
        logger.error("Failed to connect CategoryTiles signals: %s", e, exc_info=True)
        raise SetupError("Failed to connect CategoryTiles signals") from e
