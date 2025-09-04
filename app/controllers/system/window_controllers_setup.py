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


def _resolve_structure_loader(structure_business: StructureBusinessLogic):
    """Вернуть callable для загрузки структуры: load_structure_async или load_structure.

    Строго типизированный поиск загрузчика: проверяем наличие методов через hasattr
    и сразу поднимаем SetupError, если оба метода отсутствуют.
    """
    # Проверяем наличие методов загрузки до попытки их использования
    has_async = hasattr(structure_business, "load_structure_async")
    has_sync = hasattr(structure_business, "load_structure")
    
    if not has_async and not has_sync:
        raise SetupError(
            "StructureBusinessLogic must provide load_structure_async() or load_structure()"
        )
    
    try:
        # Приоритет async методу, если доступен
        if has_async:
            loader = structure_business.load_structure_async  # type: ignore[attr-defined]
            if not callable(loader):
                raise SetupError("StructureBusinessLogic.load_structure_async must be callable")
            return loader
        
        if has_sync:
            loader = structure_business.load_structure  # type: ignore[attr-defined]
            if not callable(loader):
                raise SetupError("StructureBusinessLogic.load_structure must be callable")
            return loader
            
    except SetupError:
        # SetupError уже содержит информативное сообщение - пробрасываем как есть
        raise
    except Exception as e:
        logger.exception("Unexpected error while resolving structure loader")
        raise SetupError("Failed to resolve structure loader due to unexpected error") from e
    
    # Этот код никогда не должен выполниться из-за проверок выше
    raise SetupError("Internal error: structure loader resolution failed")

def _on_structure_changed_schedule_refresh(top_ctrl: TopPanelsController, *_args: Any) -> None:
    """Поставить отложенное обновление топ-панелей при структурном событии.

    Используем внутренний таймер структуры TopPanelsController.schedule_structure_refresh().
    При любых ошибках поднимаем SetupError, чтобы не маскировать проблемы.
    """
    try:
        # Без прямых вызовов refresh_all/request_refresh — только планирование через структурный таймер
        top_ctrl.schedule_structure_refresh()
    except (AttributeError, TypeError) as e:
        raise SetupError("Scheduling structure-driven top panels refresh failed") from e
    except Exception:
        logger.exception("Unexpected error when scheduling top panels refresh")
        # Не скрываем тип исключения: пробрасываем как есть
        raise

def setup_controllers(window: Any, controllers: Dict[str, Any], db: Any) -> None:
    """Создать и настроить основные контроллеры."""
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
        if not hasattr(rec_sig, "connect"):
            raise AttributeError("recents_changed must have connect")
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
    sys_dialogs = SystemDialogController(
        window,
        database_controller=db_ctrl,
        links_table_controller=links_table_ctrl,
        links_business=links_business,
    )
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
        # Внедряем контроллер верхних панелей в бизнес-логику явным сеттером (обязательно)
        if not hasattr(structure_business, "set_top_panels_controller"):
            raise SetupError("StructureBusinessLogic must implement set_top_panels_controller")
        structure_business.set_top_panels_controller(window.top_panels_controller)
        # Также внедряем TopPanelsController в ThemeController, если доступен
        try:
            theme_ctrl = getattr(window, "theme_ctrl", None)
            if theme_ctrl and hasattr(theme_ctrl, "set_top_panels_controller"):
                theme_ctrl.set_top_panels_controller(window.top_panels_controller)
        except Exception as e:
            # Не считаем критичным для продолжения работы UI, но логируем для диагностики
            logger.warning(f"Failed to inject TopPanelsController into ThemeController: {e}")
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


def setup_ui_elements(window: Any, controllers: Dict[str, Any]) -> None:
    """Создать UI элементы: действие и кнопку переключения сфер, вставить в панель."""
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


def setup_dependency_injection(window: Any, controllers: Dict[str, Any]) -> None:
    """Запланировать отложенную инъекцию зависимостей в виджеты."""
    QTimer.singleShot(0, partial(_deferred_setup, window, controllers))


def _deferred_setup(window: Any, controllers: Dict[str, Any]) -> None:
    try:
        _inject_to_category_tiles(window, controllers)
        _connect_top_panels_signals_explicit(
            top_panels_controller=window.top_panels_controller,
            links_actions=window.links_actions,
            fav_widget=window.fav_widget,
            recent_links_widget=window.recent_links_widget,
            links=controllers.get("links"),
            quick_add_widget=(window.quick_add_widget if hasattr(window, "quick_add_widget") else None),
            auto_hide_tree_filter=(window._auto_hide_tree_filter if hasattr(window, "_auto_hide_tree_filter") else None),
            topbar_manager=(window._topbar_manager if hasattr(window, "_topbar_manager") else None),
        )
    except (AttributeError, TypeError, SetupError) as e:
        logger.error(f"Failed during deferred dependency injection: {e}")
        raise


def _inject_to_category_tiles(window: Any, controllers: Dict[str, Any]) -> None:
    """Выполнить инъекцию зависимостей для CategoryTiles."""
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
        # Ошибки контекстного меню не относятся к wiring и не должны скрываться.
        # Логируем неожиданные ошибки, но не используем общий перехват в wiring-блоках.
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


def _setup_quick_add_widget(window: Any, controllers: Dict[str, Any]) -> None:
    """Создать и настроить QuickAddWidget."""
    if hasattr(window, "quick_add_widget") and window.quick_add_widget:
        return

    from app.views.top_panel_widgets import TopPanelWidget

    window.quick_add_widget = TopPanelWidget(
        window, mode="quick", category_provider=window
    )

    _connect_quick_add_signal(
        quick_add_widget=window.quick_add_widget,
        links=controllers.get("links"),
    )
    _add_quick_add_to_top_bar(window)


def _connect_quick_add_signal(*, quick_add_widget: Any, links: Any) -> None:
    """Подключить сигнал QuickAddWidget c явными зависимостями."""
    if not quick_add_widget:
        return
    try:
        quick_add_widget.quickAddRequested.connect(links.on_quick_add_requested)
    except (AttributeError, TypeError) as e:
        raise SetupError(f"Failed to connect quick add signal: {e}") from e


def _add_quick_add_to_top_bar(window: Any) -> None:
    """Добавить QuickAddWidget в топ-бар."""
    return


def _connect_top_panels_signals_explicit(
    *,
    top_panels_controller: TopPanelsController,
    links_actions: Any,
    fav_widget: Any,
    recent_links_widget: Any,
    links: Any,
    quick_add_widget: Any | None = None,
    auto_hide_tree_filter: Any | None = None,
    topbar_manager: Any | None = None,
) -> None:
    """Подключить сигналы верхних панелей с явной передачей зависимостей."""
    # QuickAddWidget — необязательная часть
    if quick_add_widget is not None:
        try:
            _connect_quick_add_signal(quick_add_widget=quick_add_widget, links=links)
        except (AttributeError, TypeError) as e:
            raise SetupError(f"Failed to wire quick add: {e}") from e

    # Favorites panel wiring — критично требует TopPanelsController
    if not fav_widget:
        raise SetupError("Favorites widget is required for wiring")
    try:
        fav_widget.linkClicked.connect(links_actions.open_link)
    except (AttributeError, TypeError) as e:
        raise SetupError(f"Failed to connect favorites link click: {e}") from e

    if not top_panels_controller:
        raise SetupError("TopPanelsController is required for favorites panel wiring")
    try:
        fav_widget.refresh_requested.connect(top_panels_controller.request_favorites_refresh)
        fav_widget.clear_requested.connect(top_panels_controller.clear_favorites)
    except (AttributeError, TypeError) as e:
        raise SetupError(f"Failed to wire Favorites to TopPanelsController: {e}") from e

    # Recent panel wiring — критично требует TopPanelsController
    if not recent_links_widget:
        raise SetupError("Recent links widget is required for wiring")
    try:
        recent_links_widget.linkClicked.connect(links_actions.open_link)
    except (AttributeError, TypeError) as e:
        raise SetupError(f"Failed to connect recent link click: {e}") from e

    if not top_panels_controller:
        raise SetupError("TopPanelsController is required for recent panel wiring")
    try:
        # Подключаем напрямую метод контроллера; сигнатуры совместимы
        recent_links_widget.refresh_requested[int].connect(top_panels_controller.request_recents_refresh)
    except (AttributeError, TypeError) as e:
        raise SetupError(f"Failed to wire Recents to TopPanelsController: {e}") from e

    # Доп. настройки интерфейса — валидируем callables, без getattr от window
    if auto_hide_tree_filter is not None:
        if not hasattr(auto_hide_tree_filter, "_apply") or not callable(auto_hide_tree_filter._apply):
            raise SetupError("_auto_hide_tree_filter must provide callable _apply()")
        QTimer.singleShot(0, auto_hide_tree_filter._apply)
    if topbar_manager is not None:
        if not hasattr(topbar_manager, "adjust") or not callable(topbar_manager.adjust):
            raise SetupError("_topbar_manager must provide callable adjust()")
        QTimer.singleShot(0, topbar_manager.adjust)


 


def setup_signal_connections(window: Any, controllers: Dict[str, Any], *, top_panels_controller: TopPanelsController) -> None:
    """Подключить сигналы контроллеров и UI.

    Требует явной передачи top_panels_controller для ранней валидации DI.
    """
    # Ранняя валидация явной зависимости
    if not top_panels_controller:
        raise SetupError("TopPanelsController must be provided to setup_signal_connections")

    _connect_structure_signals(
        window,
        top_panels_controller=top_panels_controller,
        structure_business=window.structure_business,
        structure=window.structure,
        spheres_controller=window.spheres_controller,
    )
    _connect_database_signals(window)
    QTimer.singleShot(0, partial(_connect_ui_signals, window))
    # Выполнить первичное обновление верхних панелей отдельно от проводки — через явный контроллер
    try:
        top_panels_controller.request_refresh()
    except (AttributeError, TypeError) as e:
        raise SetupError(f"Failed to request initial top panels refresh: {e}") from e


def _connect_structure_signals(
    window: Any,
    *,
    top_panels_controller: TopPanelsController,
    structure_business: StructureBusinessLogic,
    structure: StructureUIController,
    spheres_controller: SpheresBarController,
) -> None:
    """Подключить сигналы структуры."""
    if hasattr(window, "_structure_signals_connected") and window._structure_signals_connected:
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
    # Явный контроллер верхних панелей
    top_ctrl = top_panels_controller

    # Подключаем обработчик смены активной сферы к перезагрузке структуры
    try:
        # Явная проверка наличия метода on_active_sphere_changed
        if hasattr(structure_business, "on_active_sphere_changed"):
            handler = structure_business.on_active_sphere_changed
            if not callable(handler):
                raise SetupError("StructureBusinessLogic.on_active_sphere_changed must be callable")
        else:
            # Проверяем наличие методов загрузки до создания обработчика
            if not (hasattr(structure_business, "load_structure_async") or hasattr(structure_business, "load_structure")):
                raise SetupError("StructureBusinessLogic must provide on_active_sphere_changed, load_structure_async, or load_structure")
            
            # Разрешаем целевой загрузчик один раз при подключении, чтобы ошибка конфигурации проявилась сразу
            loader = _resolve_structure_loader(structure_business)

            def _on_active_sphere_changed(*_args: Any) -> None:
                try:
                    loader()
                except TypeError as e:
                    raise SetupError("Invalid structure business loader signature") from e
                except Exception as e:
                    logger.error(f"Unexpected error triggering structure reload: {e}")
                    raise SetupError("Failed to trigger structure reload") from e

            handler = _on_active_sphere_changed
        structure_business.active_sphere_changed.connect(handler)
    except (AttributeError, TypeError) as e:
        # Ошибка сигнатуры/отсутствия сигналов — это ошибка настройки
        raise SetupError(
            f"Failed to connect active_sphere_changed to structure reload: {e}"
        ) from e

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

    
    window._structure_signals_connected = True

    # После подключения сигналов сразу выставим визуальное состояние активной кнопки,
    # если текущая сфера уже известна (исправляет отсутствие фокуса/чека на старте)
    curr_id = structure_business.current_sphere_id if hasattr(structure_business, "current_sphere_id") else None
    if isinstance(curr_id, int) and curr_id > 0:
        if hasattr(spheres_controller, "update_active_sphere_button") and callable(spheres_controller.update_active_sphere_button):
            try:
                spheres_controller.update_active_sphere_button(int(curr_id))
            except (TypeError, ValueError):
                logger.debug("Failed to update active sphere button with current_sphere_id", exc_info=False)


def _connect_database_signals(window: Any) -> None:
    """Подключить сигналы базы данных."""
    if hasattr(window, "_database_signals_connected") and window._database_signals_connected:
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


def _connect_ui_signals(window: Any) -> None:
    """Подключить сигналы UI."""
    if hasattr(window, "_ui_signals_connected") and window._ui_signals_connected:
        return
    # Дерево структуры: подключаем без широких исключений
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
                    logger.debug("update_statusbar failed during tree selection change", exc_info=False)
            try:
                sel_model.currentChanged.connect(_update_statusbar_tree)
            except (AttributeError, TypeError) as e:
                logger.warning(f"Failed to connect tree selection signals: {e}")

    if hasattr(window, "table") and window.table:
        try:
            selection_model = window.table.selectionModel()
        except (AttributeError, TypeError):
            selection_model = None
        if selection_model:
            def _update_statusbar_table(*_):
                try:
                    window.update_statusbar()
                except Exception:
                    logger.debug("update_statusbar failed during table selection change", exc_info=False)
            try:
                selection_model.selectionChanged.connect(_update_statusbar_table)
            except (AttributeError, TypeError) as e:
                logger.warning(f"Failed to connect table selection signals: {e}")
    window._ui_signals_connected = True


def setup_keyboard(window: Any, controllers: Dict[str, Any]) -> None:
    """Настроить централизованное управление горячими клавишами."""
    window.keyboard_manager = KeyboardManager(window)


class DatabaseEventHandler:
    """Обработчик событий базы данных."""

    @staticmethod
    def handle_database_restored(window: Any, new_db: Any):
        """Обработать восстановление базы данных."""
        window.db = new_db
        # Явно передаем links_actions как зависимость
        links_actions = getattr(window, "links_actions", None)
        DatabaseEventHandler._update_controllers_with_new_db(window, new_db, links_actions=links_actions)
        DatabaseEventHandler._restore_ui_state(window)
        window.update_statusbar()

    @staticmethod
    def handle_database_connected(window: Any, new_db: Any):
        """Обработать подключение новой базы данных."""
        window.db = new_db
        # Явно передаем links_actions как зависимость
        links_actions = getattr(window, "links_actions", None)
        DatabaseEventHandler._update_controllers_with_new_db(window, new_db, links_actions=links_actions)
        DatabaseEventHandler._restore_ui_state(window)
        window.update_statusbar()

    @staticmethod
    def handle_favorites_cleared(
        window: Any,
        *,
        top_panels_controller: TopPanelsController,
        links_table_controller: LinksTableController,
    ):
        """Обработать очистку избранного.
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
    def _update_controllers_with_new_db(window: Any, new_db: Any, *, links_actions: Any = None):
        """Обновить все контроллеры новой БД.
        
        Args:
            window: Главное окно приложения
            new_db: Новая база данных
            links_actions: LinksActions контроллер (обязательная зависимость)
        """
        if hasattr(window, "structure"):
            window.structure.db = new_db
            window.structure.spheres = new_db.spheres
            window.structure.sections = new_db.sections
            window.structure.categories = new_db.categories
            window.structure.load()

        # Явная проверка обязательной зависимости links_actions
        if links_actions is None:
            raise SetupError("links_actions is required when switching database")
        
        # Критичная зависимость: links_actions.links должен существовать
        if not hasattr(links_actions, "links") or links_actions.links is None:
            raise SetupError("links_actions.links is required when switching database")
        
        links = links_actions.links
        # И должен поддерживать необходимые атрибуты
        if not hasattr(links, "db") or not hasattr(links, "links"):
            raise SetupError("links_actions.links must have 'db' and 'links' attributes")
        
        try:
            links.db = new_db
            links.links = new_db.links
        except Exception:
            logger.exception("Failed to update links_actions.links with new DB")
            raise

        if hasattr(window, "structure_business"):
            sb = window.structure_business
            sb.db = new_db
            # Критичные проверки интерфейса
            if not hasattr(sb, "spheres_loaded"):
                logger.error("structure_business.spheres_loaded signal is required")
                raise SetupError("structure_business must expose 'spheres_loaded' signal")
            signal = sb.spheres_loaded
            if not hasattr(signal, "connect") or not hasattr(signal, "disconnect"):
                logger.error("structure_business.spheres_loaded must support connect/disconnect")
                raise SetupError("structure_business.spheres_loaded must support connect/disconnect")
            if not hasattr(sb, "get_current_sphere_id") or not hasattr(sb, "set_current_sphere"):
                logger.error("structure_business must implement get_current_sphere_id/set_current_sphere")
                raise SetupError("structure_business must implement get_current_sphere_id and set_current_sphere")
            try:
                def _set_first_sphere_once(spheres_list):
                    try:
                        has_get = hasattr(sb, "get_current_sphere_id") and callable(sb.get_current_sphere_id)
                        if spheres_list and has_get and sb.get_current_sphere_id() is None:
                            first_sphere_id = spheres_list[0].get("id", 1)
                            sb.set_current_sphere(first_sphere_id)
                    finally:
                        try:
                            sb.spheres_loaded.disconnect(_set_first_sphere_once)
                        except Exception:
                            logger.exception("Failed to disconnect _set_first_sphere_once from spheres_loaded")
                sb.spheres_loaded.connect(_set_first_sphere_once)
                if hasattr(sb, "load_spheres_async") and callable(sb.load_spheres_async):
                    sb.load_spheres_async()
            except Exception:
                logger.exception("Failed to update structure_business with new DB")
                raise

    @staticmethod
    def _restore_ui_state(window: Any):
        """Восстановить состояние UI после смены БД."""
        category_id = window.get_current_category_id()
        if category_id:
            if hasattr(window, "links_table_controller") and window.links_table_controller:
                try:
                    window.links_table_controller.reload(category_id)
                except (AttributeError, TypeError) as e:
                    logger.error(
                        "_restore_ui_state: links_table_controller.reload failed due to interface error: %s",
                        e,
                    )
                except Exception:
                    # Неожиданная ошибка — не скрываем
                    logger.exception("_restore_ui_state: unexpected error during table reload")
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
                        logger.exception("_restore_ui_state: unexpected error during business load_links")
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


class WindowControllersSetup:
    """Координатор настройки контроллеров и компонентов главного окна."""

    def __init__(self, window_initializer: Any):
        self.window_initializer = window_initializer
        self.window = window_initializer.window
        self.db = window_initializer.db

    def setup_controllers(self) -> None:
        """Настроить контроллеры и компоненты."""
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
                if step is setup_signal_connections:
                    # Явно передаем TopPanelsController для ранней валидации DI
                    step(self.window, controllers, top_panels_controller=self.window.top_panels_controller)
                else:
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
