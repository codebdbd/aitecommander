"""
Signal connections and event handlers.
"""

import logging
import os
from functools import partial
from typing import Any

from PyQt6.QtCore import QT_TRANSLATE_NOOP, QCoreApplication, QTimer, pyqtSlot

from app.controllers.business import StructureBusinessLogic
from app.controllers.ui.links.table_controller import LinksTableController
from app.controllers.ui.structure.spheres_bar_controller import SpheresBarController
from app.controllers.ui.structure.structure_ui_controller import StructureUIController
from app.controllers.ui.top_panels_controller import TopPanelsController
from app.services import LinksService

from .types import DatabaseProtocol, SetupError, WindowProtocol

logger = logging.getLogger(__name__)

_MESSAGE_CONTEXT = "MessageHandler"
_MSG_SUCCESS_INFO = QT_TRANSLATE_NOOP(
    _MESSAGE_CONTEXT, "Operation completed successfully."
)
_MSG_ERROR_INFO = QT_TRANSLATE_NOOP(
    _MESSAGE_CONTEXT, "Try repeating the action or contact support."
)
_TOP_PANELS_REFRESH_ON_STRUCTURE = str(
    os.getenv("APP_TOP_PANELS_REFRESH_ON_STRUCTURE", "")
).lower() in {"1", "true", "yes", "on"}


def _tr_message(text: str) -> str:
    return QCoreApplication.translate(_MESSAGE_CONTEXT, text)


def _on_structure_changed_schedule_refresh(
    top_ctrl: TopPanelsController, *_args: Any
) -> None:
    """Schedule deferred update of top panels on structural event."""
    try:
        top_ctrl.schedule_structure_refresh()
    except (AttributeError, TypeError) as e:
        raise SetupError("Scheduling structure-driven top panels refresh failed") from e
    except Exception:
        logger.exception("Unexpected error when scheduling top panels refresh")
        raise


def _connect_top_panels_signals_explicit(
    *,
    top_panels_controller: TopPanelsController,
    links_actions: Any,
    fav_widget: Any,
    recent_links_widget: Any,
    quick_add_widget: Any | None = None,
    auto_hide_tree_filter: Any | None = None,
    topbar_manager: Any | None = None,
) -> None:
    """Connect top panel signals with explicit dependency passing."""
    _connect_quick_add_widget(quick_add_widget, links_actions)
    _connect_favorites_widget(fav_widget, top_panels_controller, links_actions)
    _connect_recent_widget(recent_links_widget, top_panels_controller, links_actions)
    _setup_ui_adjustments(auto_hide_tree_filter, topbar_manager)


def _connect_quick_add_widget(quick_add_widget: Any | None, links_actions: Any) -> None:
    """Connect QuickAddWidget."""
    if quick_add_widget is not None:
        try:
            quick_add_widget.actionRequested.connect(links_actions.on_action_requested)
        except (AttributeError, TypeError) as e:
            raise SetupError(f"Failed to wire quick add: {e}") from e


def _connect_favorites_widget(
    fav_widget: Any, top_panels_controller: TopPanelsController, links_actions: Any
) -> None:
    """Connect favorites widget."""
    if not fav_widget:
        raise SetupError("Favorites widget is required for wiring")
    if not top_panels_controller:
        raise SetupError("TopPanelsController is required for favorites panel wiring")

    _connect_widget_action_signal(fav_widget, links_actions, "Favorites")

    try:
        if not hasattr(fav_widget, "refreshRequested"):
            raise SetupError(
                "Favorites widget must expose unified signal refreshRequested"
            )
        refresh_sig = fav_widget.refreshRequested
        if not hasattr(refresh_sig, "connect"):
            raise SetupError("Favorites refreshRequested must provide connect()")
        refresh_sig.connect(top_panels_controller.request_favorites_refresh)

        if hasattr(fav_widget, "clearRequested"):
            clear_sig = fav_widget.clearRequested
            if hasattr(clear_sig, "connect"):
                clear_sig.connect(top_panels_controller.clear_favorites)
    except (AttributeError, TypeError) as e:
        raise SetupError(
            f"Failed to wire Favorites (refresh/clear) to TopPanelsController: {e}"
        ) from e


def _connect_recent_widget(
    recent_links_widget: Any,
    top_panels_controller: TopPanelsController,
    links_actions: Any,
) -> None:
    """Connect recent links widget."""
    if not recent_links_widget:
        raise SetupError("Recent links widget is required for wiring")
    if not top_panels_controller:
        raise SetupError("TopPanelsController is required for recent panel wiring")

    _connect_widget_action_signal(recent_links_widget, links_actions, "Recent")

    try:
        if not hasattr(recent_links_widget, "refreshRequested"):
            raise SetupError(
                "Recent links widget must expose unified signal refreshRequested"
            )
        refresh_sig = recent_links_widget.refreshRequested
        if not hasattr(refresh_sig, "connect"):
            raise SetupError("Recent refreshRequested must provide connect()")
        refresh_sig.connect(top_panels_controller.request_recents_refresh)
    except (AttributeError, TypeError) as e:
        raise SetupError(
            f"Failed to wire Recents (refresh) to TopPanelsController: {e}"
        ) from e


def _connect_widget_action_signal(
    widget: Any, links_actions: Any, widget_name: str
) -> None:
    """Connect widget's actionRequested signal to links_actions."""
    try:
        if hasattr(widget, "actionRequested"):
            action_signal = widget.actionRequested
            if (
                hasattr(action_signal, "connect")
                and hasattr(links_actions, "on_action_requested")
                and callable(links_actions.on_action_requested)
            ):
                action_signal.connect(links_actions.on_action_requested)
            else:
                logger.debug(
                    f"{widget_name} action wiring skipped: missing connect() or handler"
                )
        else:
            logger.debug(
                f"{widget_name} widget has no actionRequested; skipping action wiring"
            )
    except (AttributeError, TypeError) as e:
        logger.debug(
            f"{widget_name} actionRequested wiring failed (non-critical): %s", e
        )


def _setup_ui_adjustments(
    auto_hide_tree_filter: Any | None, topbar_manager: Any | None
) -> None:
    """Set up additional UI adjustments."""
    if auto_hide_tree_filter is not None:
        if not hasattr(auto_hide_tree_filter, "_apply") or not callable(
            auto_hide_tree_filter._apply
        ):
            raise SetupError("_auto_hide_tree_filter must provide callable _apply()")

    if topbar_manager is not None:
        if not hasattr(topbar_manager, "adjust") or not callable(topbar_manager.adjust):
            raise SetupError("_topbar_manager must provide callable adjust()")
        QTimer.singleShot(0, topbar_manager.adjust)


def setup_signal_connections(
    window: Any,
    controllers: dict[str, Any],
    *,
    top_panels_controller: TopPanelsController,
) -> None:
    """Connect controller and UI signals."""
    if not top_panels_controller:
        raise SetupError(
            "TopPanelsController must be provided to setup_signal_connections"
        )

    _connect_structure_signals(
        window,
        top_panels_controller=top_panels_controller,
        structure_business=window.structure_business,
        structure=window.structure,
        spheres_controller=window.spheres_controller,
    )
    _connect_database_signals(window)
    _connect_ui_signals(window)

    # Refresh is called in window_ui_setup._finalize_topbar_startup(), duplicate removed


def _connect_sphere_change_signals(
    window: Any,
    structure_business: StructureBusinessLogic,
    spheres_controller: SpheresBarController,
) -> None:
    """Connect signals for sphere changes."""
    try:
        structure_business.active_sphere_changed.connect(
            spheres_controller.update_active_sphere_button
        )
    except (AttributeError, TypeError) as e:
        logger.error("Failed to connect sphere button update: %s", e)

    structure_business.active_sphere_changed.connect(window._update_left_panel_style)


def _connect_structure_reload_handler(
    structure_business: StructureBusinessLogic,
) -> None:
    """Connect handler for structure reload on sphere change."""
    try:
        if hasattr(structure_business, "on_active_sphere_changed"):
            handler = structure_business.on_active_sphere_changed
            if not callable(handler):
                raise SetupError(
                    "StructureBusinessLogic.on_active_sphere_changed must be callable"
                )
        else:
            if not (
                hasattr(structure_business, "load_structure_async")
                or hasattr(structure_business, "load_structure")
            ):
                raise SetupError(
                    "StructureBusinessLogic must provide on_active_sphere_changed, load_structure_async, or load_structure"
                )

            from . import _resolve_structure_loader

            loader = _resolve_structure_loader(structure_business)

            def _on_active_sphere_changed(*_args: Any) -> None:
                try:
                    loader()
                except TypeError as e:
                    raise SetupError(
                        "Invalid structure business loader signature"
                    ) from e
                except Exception as e:
                    logger.error("Unexpected error triggering structure reload: %s", e)
                    raise SetupError("Failed to trigger structure reload") from e

            handler = _on_active_sphere_changed

        structure_business.active_sphere_changed.connect(handler)
    except (AttributeError, TypeError) as e:
        raise SetupError(
            f"Failed to connect active_sphere_changed to structure reload: {e}"
        ) from e


def _connect_top_panels_refresh(
    structure_business: StructureBusinessLogic,
    top_panels_controller: TopPanelsController,
) -> None:
    """Connect structure signals to top panels refresh."""
    if not top_panels_controller:
        raise SetupError(
            "TopPanelsController is required to schedule structure-driven refreshes"
        )
    if not _TOP_PANELS_REFRESH_ON_STRUCTURE:
        logger.debug(
            "TopPanelsController: structure-driven refresh disabled "
            "(set APP_TOP_PANELS_REFRESH_ON_STRUCTURE=1 to enable)"
        )
        return
    try:
        structure_business.active_sphere_changed.connect(
            partial(_on_structure_changed_schedule_refresh, top_panels_controller)
        )
        structure_business.structure_loaded.connect(
            partial(_on_structure_changed_schedule_refresh, top_panels_controller)
        )
    except (AttributeError, TypeError) as e:
        raise SetupError(
            f"Failed to connect structure signals to TopPanelsController: {e}"
        ) from e
    except Exception as e:
        raise SetupError(
            "Unexpected error while wiring structure signals to TopPanelsController"
        ) from e


def _connect_structure_item_signals(
    window: Any,
    structure: StructureUIController,
) -> None:
    """Connect structure item change signals."""
    structure.item_changed.connect(window.on_structure_item_changed)
    structure.item_added.connect(window.on_structure_item_added)


def _initialize_current_sphere_button(
    structure_business: StructureBusinessLogic,
    spheres_controller: SpheresBarController,
) -> None:
    """Initialize active sphere button with current sphere ID."""
    curr_id = (
        structure_business.current_sphere_id
        if hasattr(structure_business, "current_sphere_id")
        else None
    )
    if isinstance(curr_id, int) and curr_id > 0:
        if hasattr(spheres_controller, "update_active_sphere_button") and callable(
            spheres_controller.update_active_sphere_button
        ):
            try:
                spheres_controller.update_active_sphere_button(int(curr_id))
            except (TypeError, ValueError):
                logger.debug(
                    "Failed to update active sphere button with current_sphere_id",
                    exc_info=False,
                )


def _connect_structure_signals(
    window: Any,
    *,
    top_panels_controller: TopPanelsController,
    structure_business: StructureBusinessLogic,
    structure: StructureUIController,
    spheres_controller: SpheresBarController,
) -> None:
    """Connect structure signals."""
    if (
        hasattr(window, "_structure_signals_connected")
        and window._structure_signals_connected
    ):
        return

    # Connect sphere change signals
    _connect_sphere_change_signals(window, structure_business, spheres_controller)

    # Connect structure reload handler
    _connect_structure_reload_handler(structure_business)

    # Top panels refresh is handled via StructureEventService to avoid duplication.

    # Connect structure item signals
    _connect_structure_item_signals(window, structure)

    window._structure_signals_connected = True

    # Initialize current sphere button
    _initialize_current_sphere_button(structure_business, spheres_controller)


def _connect_database_signals(window: Any) -> None:
    """Connect database signals."""
    if (
        hasattr(window, "_database_signals_connected")
        and window._database_signals_connected
    ):
        return
    db_controller = window.database_controller

    try:
        db_controller.database_restored.connect(
            partial(DatabaseEventHandler.handle_database_restored, window)
        )
        db_controller.database_connected.connect(
            partial(DatabaseEventHandler.handle_database_connected, window)
        )
        db_controller.favorites_cleared.connect(
            partial(
                DatabaseEventHandler.handle_favorites_cleared,
                window,
                top_panels_controller=window.top_panels_controller,
                links_table_controller=window.links_table_controller,
            )
        )
        db_controller.operation_success.connect(
            partial(MessageHandler.show_success_message, window)
        )
        db_controller.operation_error.connect(
            partial(MessageHandler.show_error_message, window)
        )
    except (AttributeError, TypeError) as e:
        logger.warning("Failed to connect database signals: %s", e)
    window._database_signals_connected = True


def _connect_tree_selection_signals(window: Any) -> None:
    """Connect tree selection signals to statusbar update."""
    if not hasattr(window, "tree") or not window.tree:
        return

    tree = window.tree
    try:
        sel_model = tree.selectionModel()
    except (AttributeError, TypeError):
        sel_model = None

    if not sel_model:
        return

    def _update_statusbar_tree(*_):
        try:
            window.update_statusbar()
        except Exception:
            logger.debug(
                "update_statusbar failed during tree selection change",
                exc_info=False,
            )

    try:
        sel_model.currentChanged.connect(_update_statusbar_tree)
        sel_model.selectionChanged.connect(_update_statusbar_tree)
    except (AttributeError, TypeError) as e:
        logger.warning("Failed to connect tree selection signals: %s", e)


def _connect_table_selection_signals(window: Any) -> None:
    """Connect table selection signals to statusbar update."""
    widgets = getattr(window, "widgets", None)
    table = widgets.table if widgets else getattr(window, "table", None)
    if table is None:
        return
    try:
        selection_model = table.selectionModel()
    except (AttributeError, TypeError):
        selection_model = None

    if not selection_model:
        return

    def _update_statusbar_table(*_):
        try:
            window.update_statusbar()
        except Exception:
            logger.debug(
                "update_statusbar failed during table selection change",
                exc_info=False,
            )

    try:
        selection_model.selectionChanged.connect(_update_statusbar_table)
    except (AttributeError, TypeError) as e:
        logger.warning("Failed to connect table selection signals: %s", e)


def _connect_table_populated_signal(window: Any) -> None:
    """Connect table populated signal to statusbar update."""
    widgets = getattr(window, "widgets", None)
    table = widgets.table if widgets else getattr(window, "table", None)
    if table is None:
        return
    try:
        if hasattr(table, "table_populated") and hasattr(
            table.table_populated, "connect"
        ):
            table.table_populated.connect(window.update_statusbar)
    except (AttributeError, TypeError) as e:
        logger.debug("Failed to connect table_populated to update_statusbar: %s", e)


def _connect_statusbar_controller_signals(window: Any) -> None:
    """Connect controller signals that affect status bar content."""
    if getattr(window, "_statusbar_controller_signals_connected", False):
        return

    update_statusbar = getattr(window, "update_statusbar", None)
    if not callable(update_statusbar):
        return

    signal_sources = [
        (
            getattr(window, "database_controller", None),
            (
                "database_connected",
                "database_restored",
                "favorites_cleared",
            ),
        ),
        (
            getattr(window, "structure_business", None),
            (
                "active_sphere_changed",
                "structure_loaded",
                "item_added",
                "item_updated",
                "item_deleted",
                "items_batch_deleted",
                "section_selected",
                "category_selected",
            ),
        ),
        (
            getattr(window, "link_operations", None),
            (
                "links_changed",
                "favorites_changed",
                "recents_changed",
                "link_saved",
                "link_deleted",
            ),
        ),
        (getattr(window, "top_panels_controller", None), ("data_loaded",)),
    ]

    for owner, signal_names in signal_sources:
        if owner is None:
            continue
        for signal_name in signal_names:
            signal = getattr(owner, signal_name, None)
            if not hasattr(signal, "connect"):
                continue
            try:
                signal.connect(update_statusbar)
            except (AttributeError, TypeError) as exc:
                logger.debug(
                    "Failed to connect %s.%s to update_statusbar: %s",
                    type(owner).__name__,
                    signal_name,
                    exc,
                )

    window._statusbar_controller_signals_connected = True


def _connect_ui_signals(window: Any) -> None:
    """Connect UI signals."""
    if hasattr(window, "_ui_signals_connected") and window._ui_signals_connected:
        return

    # Connect tree selection signals
    _connect_tree_selection_signals(window)

    # Connect table selection signals
    _connect_table_selection_signals(window)

    # Connect table populated signal
    _connect_table_populated_signal(window)

    # Connect controller-driven updates for status bar content.
    _connect_statusbar_controller_signals(window)

    window._ui_signals_connected = True


class DatabaseEventHandler:
    """Database event handler."""

    @staticmethod
    @pyqtSlot(object)
    def handle_database_restored(window: Any, new_db: Any):
        """Handle database restoration."""
        logger.info(f"handle_database_restored called with new_db: {new_db}")
        business = (
            getattr(window, "structure_business", None)
            or getattr(window, "business", None)
            or getattr(getattr(window, "structure", None), "business", None)
        )
        if business is not None and hasattr(business, "suspend_structure_preload"):
            try:
                business.suspend_structure_preload(
                    duration_ms=6000,
                    reason="database-restore",
                )
            except Exception:
                logger.debug(
                    "handle_database_restored: failed to suspend structure preload",
                    exc_info=True,
                )
        try:
            tree_manager = getattr(getattr(window, "structure", None), "tree_manager", None)
            if tree_manager is not None and hasattr(tree_manager, "request_next_snapshot_mode"):
                tree_manager.request_next_snapshot_mode("full_restore")
        except Exception:
            logger.debug(
                "handle_database_restored: failed to set next snapshot mode",
                exc_info=True,
            )
        logger.info("Updating window.db reference")
        window.db = new_db
        try:
            from app.core.database_manager import DatabaseManager

            DatabaseManager.close()
            DatabaseManager.get_connection()
        except Exception as exc:
            logger.warning("handle_database_restored: failed to refresh DB connection: %s", exc)
        
        logger.info("Updating controllers with new DB")
        links_actions = getattr(window, "links_actions", None)
        DatabaseEventHandler._update_controllers_with_new_db(
            window, new_db, links_actions=links_actions
        )
        
        logger.info("Restoring UI state")
        DatabaseEventHandler._restore_ui_state(window)
        DatabaseEventHandler._refresh_top_panels(window)
        
        logger.info("Updating statusbar")
        window.update_statusbar()
        if business is not None and hasattr(business, "resume_structure_preload"):
            try:
                business.resume_structure_preload(
                    delay_ms=3500,
                    reason="database-restore",
                )
            except Exception:
                logger.debug(
                    "handle_database_restored: failed to resume structure preload",
                    exc_info=True,
                )
        
        logger.info("Database restoration handler completed")

    @staticmethod
    @pyqtSlot(object)
    def handle_database_connected(window: Any, new_db: Any):
        """Handle new database connection."""
        window.db = new_db
        try:
            from app.core.database_manager import DatabaseManager

            DatabaseManager.close()
            DatabaseManager.get_connection()
        except Exception as exc:
            logger.warning("handle_database_connected: failed to refresh DB connection: %s", exc)
        links_actions = getattr(window, "links_actions", None)
        DatabaseEventHandler._update_controllers_with_new_db(
            window, new_db, links_actions=links_actions
        )
        DatabaseEventHandler._restore_ui_state(window)
        DatabaseEventHandler._refresh_top_panels(window)
        window.update_statusbar()

    @staticmethod
    def handle_favorites_cleared(
        window: Any,
        *,
        top_panels_controller: TopPanelsController,
        links_table_controller: LinksTableController,
    ):
        """Handle favorites clearing."""
        if not top_panels_controller:
            raise SetupError("TopPanelsController is required to clear favorites")
        if not links_table_controller:
            raise SetupError(
                "LinksTableController is required to reload table after favorites clear"
            )

        top_panels_controller.clear_favorites()
        top_panels_controller.request_favorites_refresh()

        category_id = window.get_current_category_id()
        if category_id:
            links_table_controller.reload(category_id)

    @staticmethod
    def _update_controllers_with_new_db(
        window: WindowProtocol, new_db: DatabaseProtocol, *, links_actions: Any = None
    ):
        """Update all controllers with new DB."""
        DatabaseEventHandler._update_structure_controllers(window, new_db)
        DatabaseEventHandler._update_links_controllers(window, new_db, links_actions)
        DatabaseEventHandler._update_business_logic(window, new_db)

    @staticmethod
    def _update_structure_controllers(window: WindowProtocol, new_db: DatabaseProtocol):
        """Update structure controllers with new DB."""
        if hasattr(window, "structure"):
            window.structure.db = new_db
            window.structure.spheres = new_db.spheres
            window.structure.sections = new_db.sections
            window.structure.categories = new_db.categories

    @staticmethod
    def _validate_links_actions(links_actions: Any) -> Any:
        """Validate links_actions and return links reference."""
        if links_actions is None:
            raise SetupError("links_actions is required when switching database")

        if not hasattr(links_actions, "links") or links_actions.links is None:
            raise SetupError("links_actions.links is required when switching database")

        return links_actions.links

    @staticmethod
    def _update_simple_links_ref(links_ref: Any, new_db: DatabaseProtocol) -> bool:
        """Update simple links reference (has db and links attributes)."""
        if hasattr(links_ref, "db") and hasattr(links_ref, "links"):
            links_ref.db = new_db
            links_ref.links = new_db.links
            return True
        return False

    @staticmethod
    def _update_link_operations(link_ops: Any, new_db: DatabaseProtocol) -> None:
        """Update LinkOperationsController with new DB."""
        try:
            if hasattr(link_ops, "db"):
                link_ops.db = new_db
        except Exception:
            logger.exception(
                "Failed to update LinkOperationsController.db during DB switch"
            )
            raise

    @staticmethod
    def _update_links_business(business: Any, new_db: DatabaseProtocol) -> None:
        """Update LinksBusinessLogic with new DB."""
        try:
            if hasattr(business, "reset_state_for_database_switch") and callable(
                business.reset_state_for_database_switch
            ):
                business.reset_state_for_database_switch()
            if hasattr(business, "db"):
                business.db = new_db
            if hasattr(business, "links_model"):
                business.links_model = new_db.links
            if hasattr(business, "links"):
                business.links = LinksService(new_db)
            if hasattr(business, "invalidate_cache") and callable(
                business.invalidate_cache
            ):
                business.invalidate_cache()
        except Exception:
            logger.exception(
                "Failed to update LinksBusinessLogic with new DB during DB switch"
            )
            raise

    @staticmethod
    def _update_links_controllers(
        window: WindowProtocol, new_db: DatabaseProtocol, links_actions: Any
    ):
        """Update link controllers with new DB."""
        links_ref = DatabaseEventHandler._validate_links_actions(links_actions)

        try:
            # Try simple update first
            if DatabaseEventHandler._update_simple_links_ref(links_ref, new_db):
                return

            # Try complex update (business + link_ops)
            if hasattr(links_ref, "business") and hasattr(links_ref, "link_ops"):
                DatabaseEventHandler._update_link_operations(links_ref.link_ops, new_db)
                DatabaseEventHandler._update_links_business(links_ref.business, new_db)
                return

            # Neither pattern matched
            raise SetupError(
                "links_actions.links must provide either ('db' and 'links') or ('business' and 'link_ops') attributes"
            )
        except SetupError:
            raise
        except Exception:
            logger.exception("Failed to update links controllers with new DB")
            raise

    @staticmethod
    def _validate_structure_business(sb: Any) -> None:
        """Validate structure_business has required attributes."""
        if not hasattr(sb, "spheres_loaded"):
            logger.error("structure_business.spheres_loaded signal is required")
            raise SetupError("structure_business must expose 'spheres_loaded' signal")

        signal = sb.spheres_loaded
        if not hasattr(signal, "connect") or not hasattr(signal, "disconnect"):
            logger.error(
                "structure_business.spheres_loaded must support connect/disconnect"
            )
            raise SetupError(
                "structure_business.spheres_loaded must support connect/disconnect"
            )

        if not hasattr(sb, "get_current_sphere_id") or not hasattr(
            sb, "set_current_sphere"
        ):
            logger.error(
                "structure_business must implement get_current_sphere_id/set_current_sphere"
            )
            raise SetupError(
                "structure_business must implement get_current_sphere_id and set_current_sphere"
            )

    @staticmethod
    def _setup_first_sphere_handler(sb: Any) -> None:
        """Setup handler to set first sphere on spheres_loaded."""

        def _set_first_sphere_once(spheres_list):
            try:
                has_get = hasattr(sb, "get_current_sphere_id") and callable(
                    sb.get_current_sphere_id
                )
                if spheres_list and has_get and sb.get_current_sphere_id() is None:
                    first_sphere_id = spheres_list[0].get("id", 1)
                    sb.set_current_sphere(first_sphere_id)
            finally:
                try:
                    sb.spheres_loaded.disconnect(_set_first_sphere_once)
                except Exception:
                    logger.exception(
                        "Failed to disconnect _set_first_sphere_once from spheres_loaded"
                    )

        sb.spheres_loaded.connect(_set_first_sphere_once)

    @staticmethod
    def _trigger_initial_structure_load(sb: Any) -> None:
        """Trigger initial structure load if sphere is set."""
        try:
            curr_id = (
                sb.get_current_sphere_id()
                if hasattr(sb, "get_current_sphere_id")
                and callable(sb.get_current_sphere_id)
                else None
            )
        except Exception:
            curr_id = None

        if isinstance(curr_id, int) and curr_id > 0:
            try:
                from . import _resolve_structure_loader

                loader_now = _resolve_structure_loader(sb)
                loader_now()
            except Exception as e:
                logger.error(
                    "Immediate structure reload after DB switch failed: %s",
                    e,
                    exc_info=True,
                )
        else:
            if hasattr(sb, "load_spheres_async") and callable(sb.load_spheres_async):
                sb.load_spheres_async()

    @staticmethod
    def _update_business_logic(window: WindowProtocol, new_db: DatabaseProtocol):
        """Update business logic with new DB."""
        logger.info("_update_business_logic: Starting")
        if not hasattr(window, "structure_business"):
            logger.warning("_update_business_logic: window has no structure_business")
            return

        sb = window.structure_business
        logger.info(f"_update_business_logic: Updating sb.db from {sb.db} to {new_db}")
        sb.db = new_db
        
        # CRITICAL: Update coordinator and service with new DB reference
        # After DB restore, old references become stale and cause data inconsistency
        if hasattr(sb, "structure_coordinator"):
            logger.info("_update_business_logic: Updating structure_coordinator.db")
            sb.structure_coordinator.db = new_db
        if hasattr(sb, "structure_service"):
            logger.info("_update_business_logic: Updating structure_service.db")
            sb.structure_service.db = new_db
            # StructureService also has internal _model (StructureCoordinator)
            if hasattr(sb.structure_service, "_model"):
                logger.info("_update_business_logic: Updating structure_service._model.db")
                sb.structure_service._model.db = new_db
        
        # Update async_service and its nested AsyncOperations
        if hasattr(sb, "async_service") and hasattr(sb.async_service, "async_operations"):
            logger.info("_update_business_logic: Updating async_service.async_operations.db")
            sb.async_service.async_operations.db = new_db

        try:
            logger.info("_update_business_logic: Validating structure_business")
            DatabaseEventHandler._validate_structure_business(sb)
            logger.info("_update_business_logic: Setting up first sphere handler")
            DatabaseEventHandler._setup_first_sphere_handler(sb)
            logger.info("_update_business_logic: Triggering initial structure load")
            DatabaseEventHandler._trigger_initial_structure_load(sb)
            logger.info("_update_business_logic: Completed successfully")
        except Exception:
            logger.exception("Failed to update structure_business with new DB")
            raise

    @staticmethod
    def _trigger_reload_if_needed(window: WindowProtocol):
        """Trigger data reload if necessary."""
        if hasattr(window, "structure_business"):
            sb = window.structure_business
            try:
                curr_id = (
                    sb.get_current_sphere_id()
                    if hasattr(sb, "get_current_sphere_id")
                    and callable(sb.get_current_sphere_id)
                    else None
                )
            except Exception:
                curr_id = None

            if isinstance(curr_id, int) and curr_id > 0:
                try:
                    from . import _resolve_structure_loader

                    loader_now = _resolve_structure_loader(sb)
                    loader_now()
                except Exception as e:
                    logger.error(
                        "Immediate structure reload after DB switch failed: %s",
                        e,
                        exc_info=True,
                    )

    @staticmethod
    def _restore_ui_state(window: Any):
        """Restore UI state after DB switch."""
        category_id = window.get_current_category_id()
        if category_id:
            if (
                hasattr(window, "links_table_controller")
                and window.links_table_controller
            ):
                try:
                    window.links_table_controller.reload(category_id)
                except (AttributeError, TypeError) as e:
                    logger.error(
                        "_restore_ui_state: links_table_controller.reload failed due to interface error: %s",
                        e,
                    )
                except Exception:
                    logger.exception(
                        "_restore_ui_state: unexpected error during table reload"
                    )
                    raise
            else:
                    links_ctrl = getattr(window, "links_table_controller", None)
                    if links_ctrl and hasattr(links_ctrl, "reload"):
                        try:
                            links_ctrl.reload(category_id)
                        except (AttributeError, TypeError) as e:
                            logger.error(
                                "_restore_ui_state: links_table_controller.reload failed due to interface error: %s",
                                e,
                            )
                        except Exception:
                            logger.exception(
                                "_restore_ui_state: unexpected error during table reload"
                            )
                            raise

    @staticmethod
    def _refresh_top_panels(window: Any) -> None:
        """Refresh top panels explicitly after DB switch/restore."""
        controller = getattr(window, "top_panels_controller", None)
        if controller is None:
            return
        try:
            if hasattr(controller, "refresh_all") and callable(controller.refresh_all):
                controller.refresh_all()
                return
            if hasattr(controller, "request_refresh") and callable(
                controller.request_refresh
            ):
                controller.request_refresh(0)
        except Exception:
            logger.exception("Failed to refresh top panels after database switch")


class MessageHandler:
    """User message handler."""

    @staticmethod
    def show_success_message(window: Any, title: str, message: str):
        """Show success message."""
        from app.controllers.ui.dialogs import DialogManager

        DialogManager.show_info(
            window,
            message,
            title,
            informative_text=_tr_message(_MSG_SUCCESS_INFO),
        )

    @staticmethod
    def show_error_message(window: Any, title: str, message: str):
        """Show error message."""
        from app.controllers.ui.dialogs import DialogManager

        DialogManager.show_error(
            window,
            message,
            title,
            informative_text=_tr_message(_MSG_ERROR_INFO),
        )
