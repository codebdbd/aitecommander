"""
Подключение сигналов и обработчики событий.
"""

import logging
from functools import partial
from typing import Any, Dict

from PyQt6.QtCore import QTimer, pyqtSlot

from .types import SetupError, DatabaseProtocol, WindowProtocol
from app.controllers.business import StructureBusinessLogic
from app.controllers.ui.structure.structure_ui_controller import StructureUIController
from app.controllers.ui.structure.spheres_bar_controller import SpheresBarController
from app.controllers.ui.top_panels_controller import TopPanelsController
from app.controllers.ui.links.table_controller import LinksTableController
from app.services import LinksService

logger = logging.getLogger(__name__)


def _on_structure_changed_schedule_refresh(
    top_ctrl: TopPanelsController, *_args: Any
) -> None:
    """Поставить отложенное обновление топ-панелей при структурном событии."""
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
    """Подключить сигналы верхних панелей с явной передачей зависимостей."""
    _connect_quick_add_widget(quick_add_widget, links_actions)
    _connect_favorites_widget(fav_widget, top_panels_controller, links_actions)
    _connect_recent_widget(recent_links_widget, top_panels_controller, links_actions)
    _setup_ui_adjustments(auto_hide_tree_filter, topbar_manager)


def _connect_quick_add_widget(quick_add_widget: Any | None, links_actions: Any) -> None:
    """Подключить QuickAddWidget."""
    if quick_add_widget is not None:
        try:
            quick_add_widget.actionRequested.connect(links_actions.on_action_requested)
        except (AttributeError, TypeError) as e:
            raise SetupError(f"Failed to wire quick add: {e}") from e


def _connect_favorites_widget(
    fav_widget: Any, top_panels_controller: TopPanelsController, links_actions: Any
) -> None:
    """Подключить виджет избранного."""
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
        refresh_sig = getattr(fav_widget, "refreshRequested")
        if not hasattr(refresh_sig, "connect"):
            raise SetupError("Favorites refreshRequested must provide connect()")
        refresh_sig.connect(top_panels_controller.request_favorites_refresh)

        if hasattr(fav_widget, "clearRequested"):
            clear_sig = getattr(fav_widget, "clearRequested")
            if hasattr(clear_sig, "connect"):
                clear_sig.connect(top_panels_controller.clear_favorites)
    except (AttributeError, TypeError) as e:
        raise SetupError(
            f"Failed to wire Favorites (refresh/clear) to TopPanelsController: {e}"
        ) from e


def _connect_recent_widget(
    recent_links_widget: Any, top_panels_controller: TopPanelsController, links_actions: Any
) -> None:
    """Подключить виджет недавних ссылок."""
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
        refresh_sig = getattr(recent_links_widget, "refreshRequested")
        if not hasattr(refresh_sig, "connect"):
            raise SetupError("Recent refreshRequested must provide connect()")
        refresh_sig.connect(top_panels_controller.request_recents_refresh)
    except (AttributeError, TypeError) as e:
        raise SetupError(
            f"Failed to wire Recents (refresh) to TopPanelsController: {e}"
        ) from e


def _connect_widget_action_signal(widget: Any, links_actions: Any, widget_name: str) -> None:
    """Подключить actionRequested сигнал виджета к links_actions."""
    try:
        if hasattr(widget, "actionRequested"):
            action_signal = getattr(widget, "actionRequested")
            if hasattr(action_signal, "connect") and hasattr(
                links_actions, "on_action_requested"
            ) and callable(getattr(links_actions, "on_action_requested")):
                action_signal.connect(links_actions.on_action_requested)
            else:
                logger.debug(
                    f"{widget_name} action wiring skipped: missing connect() or handler"
                )
        else:
            logger.debug(f"{widget_name} widget has no actionRequested; skipping action wiring")
    except (AttributeError, TypeError) as e:
        logger.debug(f"{widget_name} actionRequested wiring failed (non-critical): %s", e)


def _setup_ui_adjustments(auto_hide_tree_filter: Any | None, topbar_manager: Any | None) -> None:
    """Настроить дополнительные UI корректировки."""
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
    controllers: Dict[str, Any],
    *,
    top_panels_controller: TopPanelsController,
) -> None:
    """Подключить сигналы контроллеров и UI."""
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
    QTimer.singleShot(0, partial(_connect_ui_signals, window))
    
    # Refresh вызывается в window_ui_setup._finalize_topbar_startup(), убран дубль


def _connect_structure_signals(
    window: Any,
    *,
    top_panels_controller: TopPanelsController,
    structure_business: StructureBusinessLogic,
    structure: StructureUIController,
    spheres_controller: SpheresBarController,
) -> None:
    """Подключить сигналы структуры."""
    if (
        hasattr(window, "_structure_signals_connected")
        and window._structure_signals_connected
    ):
        return
    try:
        structure_business.active_sphere_changed.connect(
            spheres_controller.update_active_sphere_button
        )
    except (AttributeError, TypeError) as e:
        logger.error("Failed to connect sphere button update: %s", e)
    structure_business.active_sphere_changed.connect(window._update_left_panel_style)
    
    top_ctrl = top_panels_controller

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

    if not top_ctrl:
        raise SetupError(
            "TopPanelsController is required to schedule structure-driven refreshes"
        )
    try:
        structure_business.active_sphere_changed.connect(
            partial(_on_structure_changed_schedule_refresh, top_ctrl)
        )
        structure_business.structure_loaded.connect(
            partial(_on_structure_changed_schedule_refresh, top_ctrl)
        )
    except (AttributeError, TypeError) as e:
        raise SetupError(
            f"Failed to connect structure signals to TopPanelsController: {e}"
        ) from e
    except Exception as e:
        raise SetupError(
            "Unexpected error while wiring structure signals to TopPanelsController"
        ) from e
    structure.item_changed.connect(window.on_structure_item_changed)
    structure.item_added.connect(window.on_structure_item_added)

    window._structure_signals_connected = True

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


def _connect_database_signals(window: Any) -> None:
    """Подключить сигналы базы данных."""
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


def _connect_ui_signals(window: Any) -> None:
    """Подключить сигналы UI."""
    if hasattr(window, "_ui_signals_connected") and window._ui_signals_connected:
        return
    if hasattr(window, "tree") and window.tree:
        tree = window.tree
        try:
            sel_model = tree.selectionModel()
        except (AttributeError, TypeError):
            sel_model = None
        if sel_model:

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

    if hasattr(window, "table") and window.table:
        table = window.table
        try:
            selection_model = table.selectionModel()
        except (AttributeError, TypeError):
            selection_model = None
        if selection_model:

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

        try:
            if hasattr(table, "table_populated") and hasattr(
                table.table_populated, "connect"
            ):
                table.table_populated.connect(window.update_statusbar)
        except (AttributeError, TypeError) as e:
            logger.debug("Failed to connect table_populated to update_statusbar: %s", e)
    window._ui_signals_connected = True


class DatabaseEventHandler:
    """Обработчик событий базы данных."""

    @staticmethod
    @pyqtSlot(object)
    def handle_database_restored(window: Any, new_db: Any):
        """Обработать восстановление базы данных."""
        window.db = new_db
        links_actions = getattr(window, "links_actions", None)
        DatabaseEventHandler._update_controllers_with_new_db(
            window, new_db, links_actions=links_actions
        )
        DatabaseEventHandler._restore_ui_state(window)
        window.update_statusbar()

    @staticmethod
    @pyqtSlot(object)
    def handle_database_connected(window: Any, new_db: Any):
        """Обработать подключение новой базы данных."""
        window.db = new_db
        links_actions = getattr(window, "links_actions", None)
        DatabaseEventHandler._update_controllers_with_new_db(
            window, new_db, links_actions=links_actions
        )
        DatabaseEventHandler._restore_ui_state(window)
        window.update_statusbar()

    @staticmethod
    def handle_favorites_cleared(
        window: Any,
        *,
        top_panels_controller: TopPanelsController,
        links_table_controller: LinksTableController,
    ):
        """Обработать очистку избранного."""
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
        """Обновить все контроллеры новой БД."""
        DatabaseEventHandler._update_structure_controllers(window, new_db)
        DatabaseEventHandler._update_links_controllers(window, new_db, links_actions)
        DatabaseEventHandler._update_business_logic(window, new_db)
        DatabaseEventHandler._trigger_reload_if_needed(window)

    @staticmethod
    def _update_structure_controllers(window: WindowProtocol, new_db: DatabaseProtocol):
        """Обновить контроллеры структуры новой БД."""
        if hasattr(window, "structure"):
            window.structure.db = new_db
            window.structure.spheres = new_db.spheres
            window.structure.sections = new_db.sections
            window.structure.categories = new_db.categories

    @staticmethod
    def _update_links_controllers(window: WindowProtocol, new_db: DatabaseProtocol, links_actions: Any):
        """Обновить контроллеры ссылок новой БД."""
        if links_actions is None:
            raise SetupError("links_actions is required when switching database")

        if not hasattr(links_actions, "links") or links_actions.links is None:
            raise SetupError("links_actions.links is required when switching database")

        links_ref = links_actions.links

        try:
            if hasattr(links_ref, "db") and hasattr(links_ref, "links"):
                links_ref.db = new_db
                links_ref.links = new_db.links
            elif hasattr(links_ref, "business") and hasattr(links_ref, "link_ops"):
                business = getattr(links_ref, "business")
                link_ops = getattr(links_ref, "link_ops")

                try:
                    if hasattr(link_ops, "db"):
                        link_ops.db = new_db
                except Exception:
                    logger.exception(
                        "Failed to update LinkOperationsController.db during DB switch"
                    )
                    raise

                try:
                    if hasattr(business, "db"):
                        business.db = new_db
                    if hasattr(business, "links_model"):
                        business.links_model = new_db.links
                    if hasattr(business, "links"):
                        business.links = LinksService(new_db)
                except Exception:
                    logger.exception(
                        "Failed to update LinksBusinessLogic with new DB during DB switch"
                    )
                    raise
            else:
                raise SetupError(
                    "links_actions.links must provide either ('db' and 'links') or ('business' and 'link_ops') attributes"
                )
        except SetupError:
            raise
        except Exception:
            logger.exception("Failed to update links controllers with new DB")
            raise

    @staticmethod
    def _update_business_logic(window: WindowProtocol, new_db: DatabaseProtocol):
        """Обновить бизнес-логику новой БД."""
        if hasattr(window, "structure_business"):
            sb = window.structure_business
            sb.db = new_db
            if not hasattr(sb, "spheres_loaded"):
                logger.error("structure_business.spheres_loaded signal is required")
                raise SetupError(
                    "structure_business must expose 'spheres_loaded' signal"
                )
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
            try:

                def _set_first_sphere_once(spheres_list):
                    try:
                        has_get = hasattr(sb, "get_current_sphere_id") and callable(
                            sb.get_current_sphere_id
                        )
                        if (
                            spheres_list
                            and has_get
                            and sb.get_current_sphere_id() is None
                        ):
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
                try:
                    curr_id = (
                        sb.get_current_sphere_id()
                        if hasattr(sb, "get_current_sphere_id") and callable(sb.get_current_sphere_id)
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
                    if hasattr(sb, "load_spheres_async") and callable(
                        sb.load_spheres_async
                    ):
                        sb.load_spheres_async()
            except Exception:
                logger.exception("Failed to update structure_business with new DB")
                raise

    @staticmethod
    def _trigger_reload_if_needed(window: WindowProtocol):
        """Запустить перезагрузку данных если необходимо."""
        if hasattr(window, "structure_business"):
            sb = window.structure_business
            try:
                curr_id = (
                    sb.get_current_sphere_id()
                    if hasattr(sb, "get_current_sphere_id") and callable(sb.get_current_sphere_id)
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
        """Восстановить состояние UI после смены БД."""
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
                if hasattr(window, "links_business") and window.links_business:
                    try:
                        window.links_business.load_links(category_id)
                    except (AttributeError, TypeError) as e:
                        logger.error(
                            "_restore_ui_state: links_business.load_links failed due to interface error: %s",
                            e,
                        )
                    except Exception:
                        logger.exception(
                            "_restore_ui_state: unexpected error during business load_links"
                        )
                        raise


class MessageHandler:
    """Обработчик сообщений пользователю."""

    @staticmethod
    def show_success_message(window: Any, title: str, message: str):
        """Показать сообщение об успехе."""
        from app.controllers.ui.dialogs import DialogManager

        DialogManager.show_info(
            window,
            title,
            message,
            informative_text="Операция выполнена успешно.",
        )

    @staticmethod
    def show_error_message(window: Any, title: str, message: str):
        """Показать сообщение об ошибке."""
        from app.controllers.ui.dialogs import DialogManager

        DialogManager.show_error(
            window,
            title,
            message,
            informative_text="Попробуйте повторить действие или обратитесь в поддержку.",
        )
