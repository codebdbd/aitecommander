import logging
from typing import Any, Dict
from functools import partial

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QAction, QFont
from PyQt6.QtWidgets import QPushButton, QWidget

from app.controllers.business import StructureBusinessLogic
from app.controllers.business.links_business import LinksBusinessLogic
from app.controllers.system.app_shutdown_controller import AppShutdownController
from app.controllers.system.keyboard_manager import KeyboardManager
from app.controllers.ui.action_controller import ActionController
from app.controllers.ui.dialogs.database_controller import DatabaseController
from app.controllers.ui.dialogs.link_operations_controller import (
    LinkOperationsController,
)
from app.controllers.ui.dialogs.system_dialog_controller import SystemDialogController
from app.controllers.ui.links.controller import LinksUIController
from app.controllers.ui.links.table_controller import LinksTableController
from app.controllers.ui.links.links_actions import LinksActions
from app.controllers.ui.state.ui_state_manager import UIStateManager
from app.controllers.ui.category_tiles_controller import CategoryTilesController
from app.controllers.ui.structure.spheres_bar_controller import SpheresBarController
from app.controllers.ui.structure.structure_ui_controller import StructureUIController
from app.controllers.ui.top_panels_controller import TopPanelsController
from app.utils.ui.icon.icon_operations.creators import themed_icon
from app.utils.ui.icon.path_service import get_current_theme
from app.utils.ui.menu_builders.category_menu_builder import CategoryMenuBuilder

logger = logging.getLogger(__name__)


class SetupError(Exception):
    """Ошибки настройки компонентов окна."""

def _on_structure_changed_schedule_refresh(top_ctrl, *_args):
    """Внешний обработчик структурных событий: ставит отложенное обновление топ-панелей.

    При любых ошибках планировщика поднимаем SetupError, чтобы не маскировать проблемы.
    """
    try:
        top_ctrl.schedule_structure_refresh()
    except (AttributeError, TypeError) as e:
        raise SetupError("Scheduling structure-driven top panels refresh failed") from e
    except Exception as e:
        logger.error(f"Unexpected error when scheduling top panels refresh: {e}")
        raise SetupError("Scheduling structure-driven top panels refresh failed") from e

def setup_controllers(window, controllers: Dict[str, Any], db) -> None:
    """Создание и настройка основных контроллеров."""
    structure_business = StructureBusinessLogic(db)

    # Важно: сначала UIState и CategoryTilesController, затем StructureUIController (требует tiles-контроллер)
    window.ui_state = UIStateManager(window)
    controllers["ui_state"] = window.ui_state

    try:
        window.category_tiles_controller = CategoryTilesController(
            ui_state=controllers["ui_state"],
            structure_business=structure_business,
        )
        # Требуем наличие корректного tiles-виджета и жёстко валидируем ошибки подключения
        if not hasattr(window, "tiles") or not window.tiles:
            raise SetupError("Tiles widget is required for CategoryTilesController setup")
        try:
            window.category_tiles_controller.attach_tiles_widget(window.tiles)
        except (AttributeError, TypeError) as e:
            logger.error(f"Failed to attach tiles widget to CategoryTilesController: {e}")
            raise SetupError("CategoryTilesController attach_tiles_widget failed: incompatible or missing tiles widget") from e
        except Exception as e:
            logger.error(f"Unexpected error during tiles widget attachment: {e}")
            raise SetupError("Unexpected error while attaching tiles widget") from e
        controllers["category_tiles_controller"] = window.category_tiles_controller
    except Exception as e:
        logger.error(f"Failed to create CategoryTilesController: {e}")
        raise SetupError("CategoryTilesController creation failed") from e

    structure_ctrl = StructureUIController(window.tree, structure_business, window)

    # Создаём link_operations и links_table_controller до LinksUIController, чтобы явно передать зависимости
    link_ops = LinkOperationsController(db, window.undo_stack, window)
    # Ранняя проверка наличия критичных сигналов LinkOperationsController
    try:
        rec_sig = link_ops.recents_changed  # должен существовать и иметь connect
        _ = getattr(rec_sig, "connect")
    except Exception as e:
        raise SetupError("LinkOperationsController must expose recents_changed signal") from e
    # Инициализируем LinksBusiness только после успешной настройки tiles,
    # чтобы ошибки tiles не маскировались требованием DummyDB.links в тестах
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
    db_ctrl = DatabaseController(db, window)
    sys_dialogs = SystemDialogController(window)
    app_shutdown = AppShutdownController(window)

    controllers.update(
        {
            "structure_business": structure_business,
            "structure": structure_ctrl,
            "links_business": links_business,
            "links": links_ctrl,
            "link_operations": link_ops,
            "links_table_controller": links_table_ctrl,
            "database_controller": db_ctrl,
            "system_dialogs": sys_dialogs,
            "app_shutdown": app_shutdown,
        }
    )

    window.structure_business = controllers["structure_business"]
    window.structure = controllers["structure"]
    window.links_business = controllers["links_business"]
    window.database_controller = controllers["database_controller"]
    window.system_dialogs = controllers["system_dialogs"]
    window.app_shutdown = controllers["app_shutdown"]

    try:
        # Явно передаем созданные выше зависимости, без controllers.get
        window.links = links_ctrl
        window.link_operations = link_ops
        window.links_actions = LinksActions(
            window,
            links=links_ctrl,
            link_ops=link_ops,
        )
        controllers["links_actions"] = window.links_actions
    except (AttributeError, TypeError, ValueError) as e:
        logger.error(f"Failed to create LinksActions: {e}")
        raise SetupError("LinksActions creation failed") from e

    # ui_state и category_tiles_controller уже созданы выше

    # Прямая привязка контроллера таблицы
    window.links_table_controller = links_table_ctrl
    controllers["links_table_controller"] = window.links_table_controller

    window.action_controller = ActionController(window)
    controllers["action_controller"] = window.action_controller

    # Обязательная зависимость: SpheresBarController должен успешно создаться
    try:
        window.spheres_controller = SpheresBarController(window)
        controllers["spheres_controller"] = window.spheres_controller
    except (AttributeError, TypeError, ValueError) as e:
        logger.error(f"Failed to create SpheresBarController: {e}")
        raise SetupError("SpheresBarController creation failed") from e

    try:
        # Явно требуем наличие обоих виджетов (обязательные зависимости)
        fav_w = window.fav_widget  # may raise AttributeError
        rec_w = window.recent_links_widget  # may raise AttributeError
        window.top_panels_controller = TopPanelsController(
            window,
            fav_widget=fav_w,
            recent_links_widget=rec_w,
            links_business=links_business,
        )
        controllers["top_panels_controller"] = window.top_panels_controller
        # Прокидывание в бизнес-логику структуры — опционально; ошибки не фатальны
        try:
            setattr(structure_business, "top_panels_controller", window.top_panels_controller)
        except (AttributeError, TypeError) as e:
            logger.warning(f"Failed to assign top_panels_controller to structure_business: {e}")
    except (AttributeError, TypeError) as e:
        logger.error(f"Failed to create TopPanelsController: {e}")
        raise SetupError("Failed to create TopPanelsController") from e

    # Подключение сигналов — явные зависимости и конкретные исключения
    link_ops_ref = link_ops
    table_ref = window.links_table_controller
    top_panels_ref = window.top_panels_controller
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
        raise SetupError(f"Failed to connect LinkOperations -> LinksTableController: {e}") from e

    try:
        link_ops_ref.favorites_changed.connect(top_panels_ref.request_favorites_refresh)
        # Прямое подключение без getattr
        link_ops_ref.recents_changed.connect(top_panels_ref.request_recents_refresh)
    except (AttributeError, TypeError) as e:
        raise SetupError(f"Failed to connect LinkOperations -> TopPanelsController: {e}") from e

    # Подключаем бизнес-сигналы загрузки к контроллеру таблицы
    try:
        links_business.links_loaded.connect(table_ref.on_links_loaded)
        links_business.search_results_ready.connect(table_ref.on_search_results)
    except (AttributeError, TypeError) as e:
        raise SetupError(f"Failed to connect LinksBusiness -> LinksTableController: {e}") from e


def setup_ui_elements(window, controllers: Dict[str, Any]) -> None:
    """Создание UI элементов: действие и кнопка переключения сфер, вставка в панель."""
    window.switch_sphere_action = QAction(
        themed_icon("switch.svg", theme=get_current_theme(), source="main_window"),
        "Переключить сферу (F6)",
        window,
    )
    window.switch_sphere_action.setToolTip("Переключиться на следующую доступную сферу")
    window.switch_sphere_action.triggered.connect(
        window.structure.switch_to_next_sphere
    )

    window.switch_sphere_button = QPushButton(
        window.switch_sphere_action.icon(), "Сфера (F6)"
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


def setup_dependency_injection(window, controllers: Dict[str, Any]) -> None:
    """Планирование отложенной инъекции зависимостей в виджеты."""
    QTimer.singleShot(0, partial(_deferred_setup, window, controllers))


def _deferred_setup(window, controllers: Dict[str, Any]) -> None:
    try:
        _inject_to_category_tiles(window, controllers)
        _connect_top_panels_signals(window, controllers)
    except (AttributeError, TypeError, SetupError) as e:
        logger.error(f"Failed during deferred dependency injection: {e}")
        raise


def _inject_to_category_tiles(window, controllers: Dict[str, Any]) -> None:
    """Инъекция зависимостей для CategoryTiles."""
    if not (hasattr(window, "tiles") and window.tiles):
        return

    from app.controllers.ui.dialogs import DialogMixin

    class DialogProvider(DialogMixin):
        def __init__(self, parent_widget):
            self.parent = parent_widget

        def show_link_dialog_for_category(
            self, category_id: int | None = None, link=None
        ) -> bool:
            """Проксирует вызов показа диалога ссылки к главному окну."""
            try:
                if hasattr(self.parent, "show_link_dialog_for_category"):
                    return bool(
                        self.parent.show_link_dialog_for_category(
                            category_id=category_id, link=link
                        )
                    )
                self.show_error("Невозможно открыть диалог ссылки: окно не готово.")
                return False
            except Exception as e:
                self.show_error(f"Ошибка открытия диалога ссылки: {e}")
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
        try:
            builder = CategoryMenuBuilder(tiles.view, window)
            menu, edit_action, delete_action, add_link_action = builder.build(
                category_id,
                edit_cb=structure_ctrl.handle_edit_category,
                delete_cb=structure_ctrl.handle_delete_category,
                add_link_cb=dialog_provider.show_link_dialog_for_category,
            )
            menu.popup(global_pos)
        except Exception as e:
            logger.warning(f"Failed to show category tiles context menu: {e}")

    try:
        tiles.contextMenuRequested.connect(on_tiles_context_menu)
        tiles.editRequested.connect(structure_ctrl.handle_edit_category)
        tiles.deleteRequested.connect(structure_ctrl.handle_delete_category)
        tiles.addLinkRequested.connect(dialog_provider.show_link_dialog_for_category)
    except (AttributeError, TypeError) as e:
        raise SetupError(f"Failed to connect CategoryTiles signals: {e}") from e


def _setup_quick_add_widget(window, controllers: Dict[str, Any]) -> None:
    """Создание и настройка QuickAddWidget."""
    if hasattr(window, "quick_add_widget") and window.quick_add_widget:
        return

    from app.views.top_panel_widgets import TopPanelWidget

    window.quick_add_widget = TopPanelWidget(
        window, mode="quick", category_provider=window
    )

    _connect_quick_add_signal(window, controllers)
    _add_quick_add_to_top_bar(window)


def _connect_quick_add_signal(window, controllers: Dict[str, Any]) -> None:
    """Подключение сигнала QuickAddWidget."""
    try:
        window.quick_add_widget.quickAddRequested.connect(
            window.links.on_quick_add_requested
        )
    except (AttributeError, TypeError) as e:
        raise SetupError(f"Failed to connect quick add signal: {e}") from e


def _add_quick_add_to_top_bar(window) -> None:
    """Добавление QuickAddWidget в топ-бар."""
    return


## Внутренний внешний дебаунс удалён: используем TopPanelsController.request_refresh()


def _connect_top_panels_signals(window, controllers: Dict[str, Any]) -> None:
    """Подключение сигналов верхних панелей и первичная загрузка данных."""
    try:
        if window.quick_add_widget:
            _connect_quick_add_signal(window, controllers)
    except (AttributeError, TypeError) as e:
        logger.warning(f"Failed to wire quick add: {e}")

    # Favorites panel wiring — критично требует TopPanelsController
    if not hasattr(window, "fav_widget") or not window.fav_widget:
        raise SetupError("Favorites widget is required for wiring")
    else:
        try:
            window.fav_widget.linkClicked.connect(window.links_actions.open_link)
        except (AttributeError, TypeError) as e:
            raise SetupError(f"Failed to connect favorites link click: {e}") from e

        top_ctrl = window.top_panels_controller
        if not top_ctrl:
            raise SetupError("TopPanelsController is required for favorites panel wiring")
        try:
            window.fav_widget.refresh_requested.connect(top_ctrl.request_favorites_refresh)
            window.fav_widget.clear_requested.connect(top_ctrl.clear_favorites)
        except (AttributeError, TypeError) as e:
            raise SetupError(f"Failed to wire Favorites to TopPanelsController: {e}") from e

    # Recent panel wiring — критично требует TopPanelsController
    if not hasattr(window, "recent_links_widget") or not window.recent_links_widget:
        raise SetupError("Recent links widget is required for wiring")
    else:
        try:
            window.recent_links_widget.linkClicked.connect(window.links_actions.open_link)
        except (AttributeError, TypeError) as e:
            raise SetupError(f"Failed to connect recent link click: {e}") from e

        top_ctrl = window.top_panels_controller
        if not top_ctrl:
            raise SetupError("TopPanelsController is required for recent panel wiring")
        try:
            # Подключаем напрямую метод контроллера; сигнатуры совместимы
            window.recent_links_widget.refresh_requested[int].connect(top_ctrl.request_recents_refresh)
        except (AttributeError, TypeError) as e:
            raise SetupError(f"Failed to wire Recents to TopPanelsController: {e}") from e

    # Единичный дебаунс-запрос обновления обеих панелей после первичного подключения
    top_ctrl = window.top_panels_controller
    if not top_ctrl:
        raise SetupError("TopPanelsController not available for initial refresh")
    try:
        top_ctrl.request_refresh()
    except (AttributeError, TypeError) as e:
        raise SetupError(f"Failed to request initial top panels refresh: {e}") from e

    try:
        filt = getattr(window, "_auto_hide_tree_filter", None)
        if filt:
            QTimer.singleShot(0, filt._apply)
    except (AttributeError, TypeError):
        pass
    try:
        mgr = getattr(window, "_topbar_manager", None)
        if mgr:
            QTimer.singleShot(0, mgr.adjust)
    except (AttributeError, TypeError):
        pass


def setup_signal_connections(window, controllers: Dict[str, Any]) -> None:
    """Подключение сигналов контроллеров и UI."""
    _connect_structure_signals(
        window,
        top_panels_controller=window.top_panels_controller,
        structure_business=window.structure_business,
        structure=window.structure,
        spheres_controller=window.spheres_controller,
    )
    _connect_database_signals(window)
    QTimer.singleShot(0, partial(_connect_ui_signals, window))


def _connect_structure_signals(
    window,
    *,
    top_panels_controller,
    structure_business,
    structure,
    spheres_controller,
) -> None:
    """Подключение сигналов структуры."""
    if getattr(window, "_structure_signals_connected", False):
        return
    try:
        structure_business.active_sphere_changed.connect(
            spheres_controller.update_active_sphere_button
        )
    except (AttributeError, TypeError) as e:
        logger.error(f"Failed to connect sphere button update: {e}")
    structure_business.active_sphere_changed.connect(
        window._update_left_panel_style
    )
    # Обертки для исключения лямбд
    def _on_active_sphere_changed(*_args):
        # Требуем, чтобы хотя бы один из методов существовал в StructureBusinessLogic
        # Если отсутствуют оба — логируем и пропускаем перезагрузку (по требованиям тестов)
        try:
            try:
                # Предпочитаем асинхронную загрузку, если доступна
                structure_business.load_structure_async()
                return
            except AttributeError:
                # Переходим на синхронную, если async отсутствует
                try:
                    structure_business.load_structure()
                    return
                except AttributeError:
                    logger.error("StructureBusiness has no load_structure_async() or load_structure(); skipping reload")
                    return
        except TypeError as e:
            # Некорректный контракт методов загрузки
            raise SetupError("Invalid structure business loader signature") from e
        except Exception as e:
            logger.error(f"Unexpected error triggering structure reload: {e}")
            raise SetupError("Failed to trigger structure reload") from e

    # Явный контроллер верхних панелей
    top_ctrl = top_panels_controller

    # Подключаем обработчик смены активной сферы к перезагрузке структуры
    try:
        structure_business.active_sphere_changed.connect(_on_active_sphere_changed)
    except (AttributeError, TypeError) as e:
        raise SetupError(f"Failed to connect active_sphere_changed to structure reload: {e}") from e

    # Планировщик единого обновления верхних панелей при каскадных структурных событиях
    if not top_ctrl:
        raise SetupError("TopPanelsController is required to schedule structure-driven refreshes")
    try:
        # Подключаем только действительно влияющие на панели события
        structure_business.active_sphere_changed.connect(
            partial(_on_structure_changed_schedule_refresh, top_ctrl)
        )
        structure_business.structure_loaded.connect(
            partial(_on_structure_changed_schedule_refresh, top_ctrl)
        )
    except (AttributeError, TypeError) as e:
        raise SetupError(f"Failed to connect structure signals to TopPanelsController: {e}") from e
    except Exception as e:
        # Любые прочие ошибки подключения считаем ошибкой настройки
        raise SetupError("Unexpected error while wiring structure signals to TopPanelsController") from e
    structure.item_changed.connect(window.on_structure_item_changed)
    structure.item_added.connect(window.on_structure_item_added)

    # Обработка выбора категории централизована через
    # StructureUIController.SelectionHandling._on_category_selected,
    # поэтому прямое подключение к UIStateManager здесь не требуется.

    # Удалены прямые подключения к section_selected/category_selected, т.к. не влияют на данные верхних панелей
    window._structure_signals_connected = True

    # После подключения сигналов сразу выставим визуальное состояние активной кнопки,
    # если текущая сфера уже известна (исправляет отсутствие фокуса/чека на старте)
    try:
        curr_id = getattr(structure_business, "current_sphere_id", None)
        if isinstance(curr_id, int) and curr_id > 0:
            updater = getattr(spheres_controller, "update_active_sphere_button", None)
            if callable(updater):
                updater(int(curr_id))
    except Exception:
        pass


def _connect_database_signals(window) -> None:
    """Подключение сигналов базы данных."""
    if getattr(window, "_database_signals_connected", False):
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
        logger.warning(f"Failed to connect database signals: {e}")
    window._database_signals_connected = True


def _connect_ui_signals(window) -> None:
    """Подключение сигналов UI."""
    if getattr(window, "_ui_signals_connected", False):
        return
    try:
        if hasattr(window, "tree") and window.tree:
            tree = window.tree
            try:
                sel_model = getattr(tree, "selectionModel", lambda: None)()
                if sel_model:
                    def _update_statusbar_tree(*_):
                        window.update_statusbar()
                    sel_model.currentChanged.connect(_update_statusbar_tree)
            except (AttributeError, TypeError):
                pass
    except Exception as e:
        logger.warning(f"Failed to connect tree signals: {e}")

    try:
        if hasattr(window, "table") and window.table:
            selection_model = window.table.selectionModel()
            if selection_model:
                def _update_statusbar_table(*_):
                    window.update_statusbar()
                selection_model.selectionChanged.connect(_update_statusbar_table)
    except (AttributeError, TypeError) as e:
        logger.warning(f"Failed to connect table selection signals: {e}")
    window._ui_signals_connected = True


def setup_keyboard(window, controllers: Dict[str, Any]) -> None:
    """Настройка централизованного управления горячими клавишами."""
    window.keyboard_manager = KeyboardManager(window)


class DatabaseEventHandler:
    """Обработчик событий базы данных."""

    @staticmethod
    def handle_database_restored(window, new_db):
        """Обработка восстановления базы данных."""
        window.db = new_db
        DatabaseEventHandler._update_controllers_with_new_db(window, new_db)
        DatabaseEventHandler._restore_ui_state(window)
        window.update_statusbar()

    @staticmethod
    def handle_database_connected(window, new_db):
        """Обработка подключения новой базы данных."""
        window.db = new_db
        DatabaseEventHandler._update_controllers_with_new_db(window, new_db)
        DatabaseEventHandler._restore_ui_state(window)
        window.update_statusbar()

    @staticmethod
    def handle_favorites_cleared(window, *, top_panels_controller, links_table_controller):
        """Обработка очистки избранного.
        Требует явных зависимостей: TopPanelsController и LinksTableController.
        """
        # Валидация зависимостей
        if not top_panels_controller:
            raise SetupError("TopPanelsController is required to clear favorites")
        if not links_table_controller:
            raise SetupError("LinksTableController is required to reload table after favorites clear")

        # Действия через контроллеры
        top_panels_controller.clear_favorites()
        top_panels_controller.request_favorites_refresh()

        category_id = window.get_current_category_id()
        if category_id:
            links_table_controller.reload(category_id)

    @staticmethod
    def _update_controllers_with_new_db(window, new_db):
        """Обновить все контроллеры с новой БД."""
        if hasattr(window, "structure"):
            window.structure.db = new_db
            window.structure.spheres = new_db.spheres
            window.structure.sections = new_db.sections
            window.structure.categories = new_db.categories
            window.structure.load()

        try:
            la = getattr(window, "links_actions", None)
            if la and getattr(la, "links", None):
                la.links.db = new_db
                la.links.links = new_db.links
        except Exception:
            pass

        if hasattr(window, "structure_business"):
            window.structure_business.db = new_db
            try:
                sb = window.structure_business

                def _set_first_sphere_once(spheres_list):
                    try:
                        if spheres_list and getattr(sb, "get_current_sphere_id", None) and sb.get_current_sphere_id() is None:
                            first_sphere_id = spheres_list[0].get("id", 1)
                            sb.set_current_sphere(first_sphere_id)
                    finally:
                        try:
                            sb.spheres_loaded.disconnect(_set_first_sphere_once)
                        except Exception:
                            pass

                sb.spheres_loaded.connect(_set_first_sphere_once)
                if getattr(sb, "load_spheres_async", None):
                    sb.load_spheres_async()
            except Exception:
                pass

    @staticmethod
    def _restore_ui_state(window):
        """Восстановить состояние UI после смены БД."""
        category_id = window.get_current_category_id()
        if category_id:
            try:
                ctrl = getattr(window, "links_table_controller", None)
                if ctrl:
                    ctrl.reload(category_id)
                else:
                    links_business = getattr(window, "links_business", None)
                    if links_business:
                        try:
                            links_business.load_links(category_id)
                        except Exception:
                            pass
            except Exception:
                pass


class MessageHandler:
    """Обработчик сообщений пользователю."""

    @staticmethod
    def show_success_message(window, title: str, message: str):
        """Показать сообщение об успехе."""
        from app.controllers.ui.dialogs import DialogManager

        DialogManager.show_info(
            window,
            title,
            message,
            informative_text="Операция выполнена успешно.",
        )

    @staticmethod
    def show_error_message(window, title: str, message: str):
        """Показать сообщение об ошибке."""
        from app.controllers.ui.dialogs import DialogManager

        DialogManager.show_error(
            window,
            title,
            message,
            informative_text="Попробуйте повторить действие или обратитесь в поддержку.",
        )


class WindowControllersSetup:
    """Координатор настройки контроллеров и компонентов главного окна."""

    def __init__(self, window_initializer):
        self.window_initializer = window_initializer
        self.window = window_initializer.window
        self.db = window_initializer.db

    def setup_controllers(self):
        """Настройка контроллеров и компонентов."""
        controllers: Dict[str, Any] = {}

        try:
            setup_controllers(self.window, controllers, self.db)
            logger.info("Controllers setup completed")
        except Exception as e:
            logger.error(f"Failed to setup controllers: {e}")
            raise SetupError(
                "Critical component ControllersSetup failed to initialize"
            ) from e

        for name, step in (
            ("UIElementsSetup", setup_ui_elements),
            ("DependencyInjectionSetup", setup_dependency_injection),
            ("SignalConnectionSetup", setup_signal_connections),
            ("KeyboardSetup", setup_keyboard),
        ):
            try:
                step(self.window, controllers)
                logger.info(f"{name} completed")
            except (AttributeError, TypeError, ValueError, SetupError) as e:
                logger.error(f"{name} failed: {e}")
                # Не скрываем проблемы конфигурации шагов — завершаем настройку ошибкой
                raise SetupError(f"{name} failed during window setup") from e

    def initialize_spheres(self):
        """Инициализация сфер."""
        try:
            sc = getattr(self.window, "spheres_controller", None)
            if sc is None:
                # Обязательная зависимость: SpheresBarController должен быть доступен
                sc = SpheresBarController(self.window)
                self.window.spheres_controller = sc
            sc.init()
        except (AttributeError, TypeError, ValueError) as e:
            logger.error(f"Failed to initialize spheres: {e}")
            raise SetupError("Spheres initialization failed") from e

__all__ = ["WindowControllersSetup"]
