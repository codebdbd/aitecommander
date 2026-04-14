"""
Business logic for controller setup.
"""

import logging
from typing import Any

from PyQt6.QtWidgets import QApplication

from app.controllers.business import StructureBusinessLogic
from app.controllers.business.links_business import LinksBusinessLogic
from app.controllers.system.app_shutdown_controller import AppShutdownController
from app.controllers.ui.action_controller import ActionController
from app.controllers.ui.category_tiles_controller import CategoryTilesController
from app.controllers.ui.dialogs.database_controller import DatabaseController
from app.controllers.ui.dialogs.link_operations_controller import (
    LinkOperationsController,
)
from app.controllers.ui.dialogs.system_dialog_controller import SystemDialogController
from app.controllers.ui.links.controller import LinksUIController
from app.controllers.ui.links.links_actions import LinksActions
from app.controllers.ui.links.table_controller import LinksTableController
from app.controllers.ui.state.ui_state_manager import UIStateManager
from app.controllers.ui.structure.spheres_bar_controller import SpheresBarController
from app.controllers.ui.structure.structure_ui_controller import StructureUIController
from app.controllers.ui.top_panels_controller import TopPanelsController
from app.utils.cache.topbar_snapshot import TopBarSnapshot

from .types import DatabaseProtocol, SetupError, WindowProtocol

logger = logging.getLogger(__name__)


def _validate_qt_context() -> None:
    """Validate Qt application instance presence."""
    app_instance = QApplication.instance()
    if app_instance is None:
        raise SetupError(
            "QApplication instance is required before setting up controllers. "
            "Make sure QApplication is created before calling setup_controllers()."
        )
    logger.debug("Qt application context validated successfully")


def _setup_business_logic(controllers: dict[str, Any], db: DatabaseProtocol) -> None:
    """Create business logic."""
    structure_business = StructureBusinessLogic(db)
    controllers["structure_business"] = structure_business


def _setup_ui_state_and_tiles(
    window: WindowProtocol, controllers: dict[str, Any]
) -> None:
    """Set up UI state and category tiles controller."""
    # Important: first UIState and CategoryTilesController
    window.ui_state = UIStateManager(window)
    controllers["ui_state"] = window.ui_state

    try:
        widgets = getattr(window, "widgets", None)
        tiles_widget = widgets.tiles if widgets else getattr(window, "tiles", None)
        window.category_tiles_controller = CategoryTilesController(
            ui_state=controllers["ui_state"],
            structure_business=controllers["structure_business"],
        )
        # Require correct tiles widget and strictly validate connection errors
        if tiles_widget is None:
            raise SetupError(
                "Tiles widget is required for CategoryTilesController setup"
            )
        try:
            window.category_tiles_controller.attach_tiles_widget(tiles_widget)
        except (AttributeError, TypeError) as e:
            logger.error(
                "Failed to attach tiles widget to CategoryTilesController: %s",
                e,
                exc_info=True,
            )
            raise SetupError(
                "CategoryTilesController attach_tiles_widget failed: incompatible or missing tiles widget"
            ) from e
        except Exception as e:
            logger.error(
                "Unexpected error during tiles widget attachment: %s", e, exc_info=True
            )
            raise SetupError("Unexpected error while attaching tiles widget") from e
        controllers["category_tiles_controller"] = window.category_tiles_controller
    except Exception as e:
        logger.error("Failed to create CategoryTilesController: %s", e, exc_info=True)
        raise SetupError("CategoryTilesController creation failed") from e


def _setup_structure_controllers(window: Any, controllers: dict[str, Any]) -> None:
    """Set up structure controllers."""
    structure_ctrl = StructureUIController(
        window.tree, controllers["structure_business"], window
    )
    controllers["structure"] = structure_ctrl


def _setup_links_controllers(window: Any, controllers: dict[str, Any], db: Any) -> None:
    """Set up link controllers."""
    # Create link_operations and links_table_controller before LinksUIController
    link_ops = LinkOperationsController(db, window.undo_stack, window)
    # Early check for critical LinkOperationsController signals
    try:
        rec_sig = link_ops.recents_changed  # должен существовать и иметь connect
        if not hasattr(rec_sig, "connect"):
            raise AttributeError("recents_changed must have connect")
    except Exception as e:
        raise SetupError(
            "LinkOperationsController must expose recents_changed signal"
        ) from e

    # Initialize LinksBusiness only after successful tiles setup
    links_business = LinksBusinessLogic(db)

    links_table_ctrl = LinksTableController(
        window,
        table=window.table,
        links_business=links_business,
        category_provider=window,
    )
    links_ctrl = LinksUIController(
        window.table,
        links_business,
        window,
        link_operations=link_ops,
        links_table_controller=links_table_ctrl,
    )

    controllers.update(
        {
            "links_business": links_business,
            "links": links_ctrl,
            "link_operations": link_ops,
            "links_table_controller": links_table_ctrl,
        }
    )


def _setup_dialog_controllers(
    window: Any, controllers: dict[str, Any], db: Any
) -> None:
    """Set up dialog controllers."""
    db_ctrl = DatabaseController(db, window)
    sys_dialogs = SystemDialogController(
        window,
        database_controller=db_ctrl,
        links_table_controller=controllers["links_table_controller"],
        links_business=controllers["links_business"],
    )

    controllers.update(
        {
            "database_controller": db_ctrl,
            "system_dialogs": sys_dialogs,
        }
    )


def _setup_shutdown_controller(window: Any, controllers: dict[str, Any]) -> None:
    """Set up application shutdown controller."""
    app_shutdown = AppShutdownController(window)
    controllers["app_shutdown"] = app_shutdown


def _setup_links_actions(window: Any, controllers: dict[str, Any]) -> None:
    """Set up LinksActions controller."""
    try:
        # Explicitly pass dependencies created above, without controllers.get
        window.links = controllers["links"]
        window.link_operations = controllers["link_operations"]
        window.links_actions = LinksActions(
            window,
            links=controllers["links"],
            link_ops=controllers["link_operations"],
        )
        controllers["links_actions"] = window.links_actions
    except (AttributeError, TypeError, ValueError) as e:
        logger.error("Failed to create LinksActions: %s", e, exc_info=True)
        raise SetupError("LinksActions creation failed") from e


def _setup_additional_controllers(window: Any, controllers: dict[str, Any]) -> None:
    """Set up additional controllers."""
    # Direct binding of table controller
    window.links_table_controller = controllers["links_table_controller"]

    window.action_controller = ActionController(window)
    controllers["action_controller"] = window.action_controller
    try:
        window.action_controller.setup_global_actions()
    except Exception as e:
        logger.warning("Failed to setup global actions: %s", e, exc_info=True)

    # Required dependency: SpheresBarController must be created successfully
    try:
        window.spheres_controller = SpheresBarController(window)
        controllers["spheres_controller"] = window.spheres_controller
    except (AttributeError, TypeError, ValueError) as e:
        logger.error("Failed to create SpheresBarController: %s", e, exc_info=True)
        raise SetupError("SpheresBarController creation failed") from e


def _setup_top_panels_controller(window: Any, controllers: dict[str, Any]) -> None:
    """Set up top panels controller."""
    try:
        # Explicitly require both widgets (required dependencies)
        fav_w = window.fav_widget  # may raise AttributeError
        rec_w = window.recent_links_widget  # may raise AttributeError
        window.top_panels_controller = TopPanelsController(
            window,
            fav_widget=fav_w,
            recent_links_widget=rec_w,
            links_business=controllers["links_business"],
        )
        controllers["top_panels_controller"] = window.top_panels_controller

        pending_snapshot = getattr(window, "_pending_topbar_snapshot", None)
        if isinstance(pending_snapshot, TopBarSnapshot):
            try:
                fav_current = []
                rec_current = []

                fav_getter = getattr(window.fav_widget, "get_items", None)
                if callable(fav_getter):
                    fav_current = fav_getter() or []

                rec_getter = getattr(window.recent_links_widget, "get_items", None)
                if callable(rec_getter):
                    rec_current = rec_getter() or []

                if fav_current != pending_snapshot.favorites or rec_current != pending_snapshot.recents:
                    window.top_panels_controller.apply_snapshot(
                        pending_snapshot.favorites,
                        pending_snapshot.recents,
                    )
                    logger.debug(
                        "TopPanelsController: applied pending snapshot "
                        "(favorites=%s, recents=%s)",
                        len(pending_snapshot.favorites),
                        len(pending_snapshot.recents),
                    )
                else:
                    logger.debug(
                        "TopPanelsController: skipped pending snapshot reapply "
                        "(already present in widgets)"
                    )
            except Exception as exc:
                logger.debug(
                    "TopPanelsController: failed to apply pending snapshot: %s",
                    exc,
                    exc_info=True,
                )
            finally:
                try:
                    delattr(window, "_pending_topbar_snapshot")
                except AttributeError:
                    pass

        # Inject top panels controller into business logic with explicit setter (required)
        structure_business = controllers["structure_business"]
        if not hasattr(structure_business, "set_top_panels_controller"):
            raise SetupError(
                "StructureBusinessLogic must implement set_top_panels_controller"
            )
        structure_business.set_top_panels_controller(window.top_panels_controller)

        # Also inject TopPanelsController into ThemeController if available
        try:
            theme_ctrl = getattr(window, "theme_ctrl", None)
            if theme_ctrl and hasattr(theme_ctrl, "set_top_panels_controller"):
                theme_ctrl.set_top_panels_controller(window.top_panels_controller)
        except Exception as e:
            # Not critical for UI operation continuation, but log for diagnostics
            logger.warning(
                "Failed to inject TopPanelsController into ThemeController: %s",
                e,
                exc_info=True,
            )
    except (AttributeError, TypeError) as e:
        logger.error("Failed to create TopPanelsController: %s", e, exc_info=True)
        raise SetupError("Failed to create TopPanelsController") from e


def _connect_controller_signals(controllers: dict[str, Any]) -> None:
    """Connect signals between controllers."""
    # Signal connection — explicit dependencies and specific exceptions
    link_ops_ref = controllers["link_operations"]
    table_ref = controllers["links_table_controller"]
    top_panels_ref = controllers["top_panels_controller"]
    links_business = controllers["links_business"]

    if not link_ops_ref:
        raise SetupError("LinkOperationsController is required for signals wiring")
    if not table_ref:
        raise SetupError("LinksTableController is required for signals wiring")
    if not top_panels_ref:
        raise SetupError("TopPanelsController is required for signals wiring")

    try:
        link_ops_ref.links_changed.connect(table_ref.on_links_changed)
        link_ops_ref.link_saved.connect(table_ref.on_link_saved)
        link_ops_ref.link_deleted.connect(table_ref.on_link_deleted)
    except (AttributeError, TypeError) as e:
        raise SetupError(
            f"Failed to connect LinkOperations -> LinksTableController: {e}"
        ) from e

    try:
        link_ops_ref.favorites_changed.connect(top_panels_ref.request_refresh)
        # Прямое подключение без getattr
        link_ops_ref.recents_changed.connect(top_panels_ref.request_refresh)
    except (AttributeError, TypeError) as e:
        raise SetupError(
            f"Failed to connect LinkOperations -> TopPanelsController: {e}"
        ) from e

    # Подключаем бизнес-сигналы загрузки к контроллеру таблицы
    try:
        links_business.links_loaded.connect(table_ref.on_links_loaded)
        links_business.search_results_ready.connect(table_ref.on_search_results)
    except (AttributeError, TypeError) as e:
        raise SetupError(
            f"Failed to connect LinksBusiness -> LinksTableController: {e}"
        ) from e


def _assign_controllers_to_window(window: Any, controllers: dict[str, Any]) -> None:
    """Assign controllers to window attributes."""
    window.structure_business = controllers["structure_business"]
    window.structure = controllers["structure"]
    window.links_business = controllers["links_business"]
    window.database_controller = controllers["database_controller"]
    window.system_dialogs = controllers["system_dialogs"]
    window.app_shutdown = controllers["app_shutdown"]

    _setup_links_actions(window, controllers)
    _setup_additional_controllers(window, controllers)
    _setup_top_panels_controller(window, controllers)
    _connect_controller_signals(controllers)
