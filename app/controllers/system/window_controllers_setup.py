# app/controllers/window_controllers_setup.py AITE

import logging
from typing import Any, Dict

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QAction, QFont
from PyQt6.QtWidgets import QPushButton, QWidget

# Direct controller imports (remove facade usage)
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

    pass


# Дребезг-обновление верхних панелей, чтобы не вызывать refresh_all лавинообразно
_TOP_PANELS_REFRESH_DEBOUNCE_MS = 150


def _do_panels_refresh(window) -> None:
    """Внутренняя функция выполнения обновления верхних панелей."""
    try:
        setattr(window, "_pending_top_panels_refresh", False)
    except (AttributeError, TypeError):
        logger.warning("_do_panels_refresh: cannot clear _pending_top_panels_refresh (attr/type)")
    except Exception:
        logger.exception("_do_panels_refresh: unexpected error while clearing pending flag")
    try:
        ctrl = getattr(window, "top_panels_controller", None)
        if ctrl:
            ctrl.refresh_all()
    except (AttributeError, TypeError) as e:
        logger.warning(f"Failed to refresh top panels (attr/type): {e}")
    except Exception:
        logger.exception("Failed to refresh top panels (unexpected)")


def _request_panels_refresh(window, delay_ms: int | None = None) -> None:
    """Запросить обновление верхних панелей с дебаунсом.

    Если обновление уже запланировано, повторный запрос игнорируется до срабатывания таймера.
    """
    try:
        if getattr(window, "_pending_top_panels_refresh", False):
            return
        setattr(window, "_pending_top_panels_refresh", True)
        QTimer.singleShot(int(delay_ms or _TOP_PANELS_REFRESH_DEBOUNCE_MS), lambda: _do_panels_refresh(window))
        return
    except (AttributeError, TypeError) as e:
        logger.warning(f"_request_panels_refresh: state/type error while scheduling: {e}")
    except Exception:
        logger.exception("_request_panels_refresh: unexpected error while scheduling refresh")

    # Fallback на прямой вызов, если что-то пошло не так. Обязательно сбрасываем pending-флаг
    try:
        setattr(window, "_pending_top_panels_refresh", False)
    except (AttributeError, TypeError):
        # если нет атрибута/тип некорректный — продолжаем, это не должно ронять UI
        pass
    except Exception:
        logger.exception("_request_panels_refresh: unexpected error while clearing pending flag in fallback")

    try:
        ctrl = getattr(window, "top_panels_controller", None)
        if ctrl:
            ctrl.refresh_all()
    except (AttributeError, TypeError) as e:
        logger.warning(f"_request_panels_refresh: fallback refresh failed (attr/type): {e}")
    except Exception:
        logger.exception("_request_panels_refresh: fallback refresh failed (unexpected)")


def setup_controllers(window, controllers: Dict[str, Any], db) -> None:
    """Создание и настройка основных контроллеров."""
    # Прямое создание контроллеров/бизнес-логики (без фасада)
    structure_business = StructureBusinessLogic(db)
    links_business = LinksBusinessLogic(db)

    structure_ctrl = StructureUIController(window.tree, structure_business, window)
    links_ctrl = LinksUIController(window.table, links_business, window)

    link_ops = LinkOperationsController(db, window.undo_stack, window)
    db_ctrl = DatabaseController(db, window)
    sys_dialogs = SystemDialogController(window)
    app_shutdown = AppShutdownController(window)

    # Сохраняем контроллеры для других компонентов
    controllers.update(
        {
            "structure_business": structure_business,
            "structure": structure_ctrl,
            "links_business": links_business,
            "links": links_ctrl,
            "link_operations": link_ops,
            "database_controller": db_ctrl,
            "system_dialogs": sys_dialogs,
            "app_shutdown": app_shutdown,
        }
    )

    # Пробрасываем на окно для существующего кода
    window.structure_business = controllers["structure_business"]
    window.structure = controllers["structure"]
    window.links_business = controllers["links_business"]
    window.database_controller = controllers["database_controller"]
    window.system_dialogs = controllers["system_dialogs"]
    window.app_shutdown = controllers["app_shutdown"]

    # Фасад ссылочных действий (UI): единая точка делегирования
    try:
        window.links_actions = LinksActions(
            window,
            links=controllers.get("links"),
            link_ops=controllers.get("link_operations"),
        )
        controllers["links_actions"] = window.links_actions
    except Exception as e:
        logger.error(f"Failed to create LinksActions: {e}")

    # Централизованный менеджер состояния UI
    window.ui_state = UIStateManager(window)
    controllers["ui_state"] = window.ui_state

    # Контроллер плиток категорий
    try:
        window.category_tiles_controller = CategoryTilesController(
            window, structure_business
        )
        controllers["category_tiles_controller"] = window.category_tiles_controller
    except Exception as e:
        logger.error(f"Failed to create CategoryTilesController: {e}")

    # Контроллер таблицы ссылок (централизация обновлений)
    try:
        window.links_table_controller = LinksTableController(
            window,
            table=window.table,
            links_business=links_business,
        )
        controllers["links_table_controller"] = window.links_table_controller
    except Exception as e:
        logger.error(f"Failed to create LinksTableController: {e}")

    # Контроллер действий
    window.action_controller = ActionController(window)
    controllers["action_controller"] = window.action_controller

    # Создаём контроллер панели сфер заранее (до подключения сигналов)
    try:
        window.spheres_controller = SpheresBarController(window)
        controllers["spheres_controller"] = window.spheres_controller
    except Exception as e:
        logger.error(f"Failed to create SpheresBarController: {e}")

    # Контроллер верхних панелей (Избранное/Недавние)
    try:
        window.top_panels_controller = TopPanelsController(
            window,
            fav_widget=getattr(window, "fav_widget", None),
            recent_links_widget=getattr(window, "recent_links_widget", None),
        )
        controllers["top_panels_controller"] = window.top_panels_controller
    except Exception as e:
        logger.error(f"Failed to create TopPanelsController: {e}")

    # Подключение сигналов LinkOperationsController к централизованным обновлениям UI
    try:
        link_ops = controllers.get("link_operations")
        links_table_ctrl = controllers.get("links_table_controller")
        if link_ops:
            if links_table_ctrl:
                # При изменении ссылок в категории перезагружаем таблицу через контроллер
                link_ops.links_changed.connect(lambda cat_id: links_table_ctrl.reload(cat_id))
            # Изменение избранного отражаем через обновление верхних панелей с дебаунсом
            link_ops.favorites_changed.connect(lambda: _request_panels_refresh(window))
    except Exception as e:
        logger.warning(f"Failed to connect LinkOperationsController signals: {e}")


def setup_ui_elements(window, controllers: Dict[str, Any]) -> None:
    """Создание UI элементов: действие и кнопка переключения сфер, вставка в панель."""
    # Действие переключения сфер
    window.switch_sphere_action = QAction(
        themed_icon("switch.svg", theme=get_current_theme(), source="main_window"),
        "Переключить сферу (F6)",
        window,
    )
    window.switch_sphere_action.setToolTip("Переключиться на следующую доступную сферу")
    window.switch_sphere_action.triggered.connect(
        window.structure.switch_to_next_sphere
    )

    # Кнопка переключения сфер
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

    # Вставка в нижнюю панель
    bottom_container = window.findChild(QWidget, "bottomBarContainer")
    if bottom_container and bottom_container.layout():
        bottom_container.layout().insertWidget(0, window.switch_sphere_button)


def setup_dependency_injection(window, controllers: Dict[str, Any]) -> None:
    """Планирование отложенной инъекции зависимостей в виджеты."""
    # Откладываем инъекцию и создание UI-виджетов до старта цикла событий
    QTimer.singleShot(0, lambda: _deferred_setup(window, controllers))


def _deferred_setup(window, controllers: Dict[str, Any]) -> None:
    try:
        _inject_to_category_tiles(window, controllers)
        # Подключаем сигналы уже созданных виджетов верхней панели
        _connect_top_panels_signals(window, controllers)
    except Exception as e:
        logger.error(f"Failed during deferred dependency injection: {e}")


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

    # Подключение сигналов плиток к контроллерам и показу контекстного меню
    try:
        tiles = window.tiles
        structure_ctrl = controllers["structure"]

        # Контекстное меню через CategoryMenuBuilder
        def on_tiles_context_menu(category_id: int, global_pos):
            try:
                # CategoryTiles использует QListView в поле `view`; list_widget отсутствует
                builder = CategoryMenuBuilder(tiles.view, window)
                menu, edit_action, delete_action, add_link_action = builder.build(
                    category_id,
                    edit_cb=lambda cid: structure_ctrl.handle_edit_category(cid),
                    delete_cb=lambda cid: structure_ctrl.handle_delete_category(cid),
                    add_link_cb=lambda cid: dialog_provider.show_link_dialog_for_category(
                        category_id=cid
                    ),
                )
                menu.popup(global_pos)
            except Exception as e:
                logger.warning(f"Failed to show category tiles context menu: {e}")

        tiles.contextMenuRequested.connect(on_tiles_context_menu)

        # Операции через сигналы
        tiles.editRequested.connect(structure_ctrl.handle_edit_category)
        tiles.deleteRequested.connect(structure_ctrl.handle_delete_category)
        tiles.addLinkRequested.connect(
            lambda cid: dialog_provider.show_link_dialog_for_category(category_id=cid)
        )
    except Exception as e:
        logger.warning(f"Failed to connect CategoryTiles signals: {e}")


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
            lambda payload: controllers["links"].quick_add_link(
                payload.get("link_type"), payload.get("category_id")
            )
        )
    except Exception as e:
        logger.warning(f"Failed to connect quick add signal: {e}")


def _add_quick_add_to_top_bar(window) -> None:
    """Добавление QuickAddWidget в топ-бар."""
    # Больше не вставляем здесь: QuickAdd создаётся и добавляется в WindowUISetup
    return


def _connect_top_panels_signals(window, controllers: Dict[str, Any]) -> None:
    """Подключение сигналов верхних панелей и первичная загрузка данных."""
    try:
        # QuickAdd
        if hasattr(window, "quick_add_widget") and window.quick_add_widget:
            _connect_quick_add_signal(window, controllers)
    except Exception as e:
        logger.warning(f"Failed to wire quick add: {e}")

    # Favorites
    try:
        if hasattr(window, "fav_widget") and window.fav_widget:
            window.fav_widget.linkClicked.connect(window.links_actions.open_link)
            window.fav_widget.refresh_requested.connect(
                controllers["links_actions"].on_favorites_refresh_requested
            )
            window.fav_widget.clear_requested.connect(
                controllers["links_actions"].on_favorites_clear_requested
            )
            # Первичная загрузка: централизованно через контроллер верхних панелей
            try:
                ctrl = getattr(window, "top_panels_controller", None)
                if ctrl:
                    ctrl.refresh_all()
                else:
                    logger.warning(
                        "TopPanelsController not available; skipping initial top panels refresh (favorites)"
                    )
            except Exception as e:
                logger.warning(f"Failed to request top panels refresh (favorites): {e}")
    except Exception as e:
        logger.warning(f"Failed to wire favorites panel: {e}")

    # Recent
    try:
        if hasattr(window, "recent_links_widget") and window.recent_links_widget:
            window.recent_links_widget.linkClicked.connect(
                window.links_actions.open_link
            )
            window.recent_links_widget.refresh_requested[int].connect(
                controllers["links_actions"].on_recent_refresh_requested
            )
            # Первичная загрузка: централизованно через контроллер верхних панелей
            try:
                ctrl = getattr(window, "top_panels_controller", None)
                if ctrl:
                    ctrl.refresh_all()
                else:
                    logger.warning(
                        "TopPanelsController not available; skipping initial top panels refresh (recent)"
                    )
            except Exception as e:
                logger.warning(f"Failed to request top panels refresh (recent): {e}")
    except Exception as e:
        logger.warning(f"Failed to wire recent panel: {e}")

    # Применить авто-скрытие и пересчёт топ-бара после подключения
    try:
        filt = getattr(window, "_auto_hide_tree_filter", None)
        if filt:
            QTimer.singleShot(0, filt._apply)
    except Exception:
        pass
    try:
        mgr = getattr(window, "_topbar_manager", None)
        if mgr:
            QTimer.singleShot(0, mgr.adjust)
    except Exception:
        pass


def setup_signal_connections(window, controllers: Dict[str, Any]) -> None:
    """Подключение сигналов контроллеров и UI."""
    _connect_structure_signals(window)
    _connect_database_signals(window)
    # Откладываем подключение UI-сигналов, чтобы избежать ранних вызовов рендера
    QTimer.singleShot(0, lambda: _connect_ui_signals(window))


def _connect_structure_signals(window) -> None:
    """Подключение сигналов структуры."""
    if getattr(window, "_structure_signals_connected", False):
        return
    # Обновляем состояние кнопок сфер через контроллер панелей сфер
    try:
        window.structure_business.active_sphere_changed.connect(
            window.spheres_controller.update_active_sphere_button
        )
    except Exception as e:
        logger.error(f"Failed to connect sphere button update: {e}")
    window.structure_business.active_sphere_changed.connect(
        window._update_left_panel_style
    )
    # При смене сферы гарантируем перезагрузку структуры (обновление дерева)
    try:
        window.structure_business.active_sphere_changed.connect(
            lambda *_: (
                getattr(window.structure_business, "load_structure_async", None)()
                if callable(
                    getattr(window.structure_business, "load_structure_async", None)
                )
                else window.structure_business.load_structure()
            )
        )
    except Exception:
        pass
    # При смене сферы запрашиваем обновление верхних панелей с дебаунсом
    try:
        window.structure_business.active_sphere_changed.connect(
            lambda *_: _request_panels_refresh(window)
        )
    except Exception:
        pass

    # После загрузки структуры также дебаунсим обновление верхних панелей
    try:
        window.structure_business.structure_loaded.connect(
            lambda *_: _request_panels_refresh(window)
        )
    except Exception:
        pass
    window.structure.item_changed.connect(window.on_structure_item_changed)
    window.structure.item_added.connect(window.on_structure_item_added)

    # Подключение к UIStateManager (загрузка категории)
    window.structure_business.category_selected.connect(
        lambda cat_id: window.ui_state.load_category(cat_id, source="StructureBusiness")
    )

    # Дополнительно дебаунсим обновление верхних панелей при выборе раздела/категории
    try:
        window.structure_business.section_selected.connect(
            lambda *_: _request_panels_refresh(window)
        )
    except Exception:
        pass
    try:
        window.structure_business.category_selected.connect(
            lambda *_: _request_panels_refresh(window)
        )
    except Exception:
        pass
    window._structure_signals_connected = True


def _connect_database_signals(window) -> None:
    """Подключение сигналов базы данных."""
    if getattr(window, "_database_signals_connected", False):
        return
    db_controller = window.database_controller

    db_controller.database_restored.connect(
        lambda new_db: DatabaseEventHandler.handle_database_restored(window, new_db)
    )
    db_controller.database_connected.connect(
        lambda new_db: DatabaseEventHandler.handle_database_connected(window, new_db)
    )
    db_controller.favorites_cleared.connect(
        lambda: DatabaseEventHandler.handle_favorites_cleared(window)
    )
    db_controller.operation_success.connect(
        lambda title, message: MessageHandler.show_success_message(
            window, title, message
        )
    )
    db_controller.operation_error.connect(
        lambda title, message: MessageHandler.show_error_message(window, title, message)
    )
    window._database_signals_connected = True


def _connect_ui_signals(window) -> None:
    """Подключение сигналов UI."""
    if getattr(window, "_ui_signals_connected", False):
        return
    try:
        if hasattr(window, "tree") and window.tree:
            tree = window.tree
            # QTreeView-only: используем selectionModel().currentChanged
            try:
                sel_model = getattr(tree, "selectionModel", lambda: None)()
                if sel_model:
                    sel_model.currentChanged.connect(lambda *_: window.update_statusbar())
            except Exception:
                pass
    except Exception as e:
        logger.warning(f"Failed to connect tree signals: {e}")

    try:
        if hasattr(window, "table") and window.table:
            selection_model = window.table.selectionModel()
            if selection_model:
                selection_model.selectionChanged.connect(
                    lambda *_: window.update_statusbar()
                )
    except Exception as e:
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
    def handle_favorites_cleared(window):
        """Обработка очистки избранного."""
        if hasattr(window, "fav_widget") and window.fav_widget:
            window.fav_widget.clear_favorites()

        # Обновляем таблицу ссылок, если выбрана категория
        category_id = window.get_current_category_id()
        if category_id:
            try:
                ctrl = getattr(window, "links_table_controller", None)
                if ctrl:
                    ctrl.reload(category_id)
                else:
                    # Фолбэк без прямого UI: загрузка через бизнес-логику
                    links_business = getattr(window, "links_business", None)
                    if links_business:
                        try:
                            links_business.load_links(category_id)
                        except Exception:
                            pass
            except Exception:
                # Последний фолбэк — тихо игнорируем, чтобы не сломать обработчик
                pass

    @staticmethod
    def _update_controllers_with_new_db(window, new_db):
        """Обновить все контроллеры с новой БД."""
        # Обновляем структуру
        if hasattr(window, "structure"):
            window.structure.db = new_db
            window.structure.spheres = new_db.spheres
            window.structure.sections = new_db.sections
            window.structure.categories = new_db.categories
            window.structure.load()

        # Обновляем ссылки через фасад LinksActions (без хранения на окне)
        try:
            la = getattr(window, "links_actions", None)
            if la and getattr(la, "links", None):
                la.links.db = new_db
                la.links.links = new_db.links
        except Exception:
            pass

        # Обновляем бизнес-логику структуры
        if hasattr(window, "structure_business"):
            window.structure_business.db = new_db
            # Переводим выбор первой сферы на асинхронный путь, чтобы не блокировать UI
            try:
                sb = window.structure_business

                def _set_first_sphere_once(spheres_list):
                    try:
                        # Устанавливаем первую доступную сферу, если ещё не выбрана
                        if spheres_list and getattr(sb, "get_current_sphere_id", None) and sb.get_current_sphere_id() is None:
                            first_sphere_id = spheres_list[0].get("id", 1)
                            sb.set_current_sphere(first_sphere_id)
                    finally:
                        # Одноразовое подключение
                        try:
                            sb.spheres_loaded.disconnect(_set_first_sphere_once)
                        except Exception:
                            pass

                # Подключаем одноразовый обработчик и запускаем асинхронную загрузку сфер
                sb.spheres_loaded.connect(_set_first_sphere_once)
                if getattr(sb, "load_spheres_async", None):
                    sb.load_spheres_async()
            except Exception:
                # В случае любой ошибки не ломаем процесс обновления контроллеров
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

        # Шаг 1. Критичный: контроллеры
        try:
            setup_controllers(self.window, controllers, self.db)
            logger.info("Controllers setup completed")
        except Exception as e:
            logger.error(f"Failed to setup controllers: {e}")
            raise SetupError(
                "Critical component ControllersSetup failed to initialize"
            ) from e

        # Прочие шаги — ошибки не критичны, логируем и продолжаем
        for name, step in (
            ("UIElementsSetup", setup_ui_elements),
            ("DependencyInjectionSetup", setup_dependency_injection),
            ("SignalConnectionSetup", setup_signal_connections),
            ("KeyboardSetup", setup_keyboard),
        ):
            try:
                step(self.window, controllers)
                logger.info(f"{name} completed")
            except Exception as e:
                logger.error(f"{name} failed: {e}")

    def initialize_spheres(self):
        """Инициализация сфер."""
        try:
            # Используем новый контроллер панели сфер
            self.window.spheres_controller = SpheresBarController(self.window)
            self.window.spheres_controller.init()
        except Exception as e:
            logger.error(f"Failed to initialize spheres: {e}")
            # Не останавливаем выполнение, так как это не критично для базовой работы

    # Метод _log_setup_results больше не требуется после упрощения


# Экспорт для обратной совместимости
__all__ = ["WindowControllersSetup"]
