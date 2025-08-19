# app/controllers/window_controllers_setup.py

import logging
from typing import Dict, Any, Callable

from PyQt6.QtGui import QAction, QFont
from PyQt6.QtWidgets import QPushButton, QWidget
from PyQt6.QtCore import QTimer

from app.controllers.bootstrap import build_controllers
from app.controllers.keyboard import KeyboardManager
from app.controllers.ui.menu_controller import ActionController
from app.utils.ui.icon.icon_operations.creators import themed_icon
from app.utils.ui.icon.path_service import get_current_theme
from app.utils.ui_state.ui_state_manager import UIStateManager
from app.config_data import app_config

logger = logging.getLogger(__name__)


class SetupError(Exception):
    """Ошибки настройки компонентов окна."""
    pass


def setup_controllers(window, controllers: Dict[str, Any]) -> None:
    """Создание и настройка основных контроллеров."""
    # Централизованное создание контроллеров/бизнес-логики
    app_controllers = build_controllers(window)

    # Сохраняем контроллеры для других компонентов
    controllers.update({
        'structure_business': app_controllers.structure_business,
        'structure': app_controllers.structure,
        'links_business': app_controllers.links_business,
        'links': app_controllers.links,
        'link_operations': app_controllers.link_operations,
        'database_controller': app_controllers.database_controller,
        'system_dialogs': app_controllers.system_dialogs,
        'app_shutdown': app_controllers.app_shutdown,
    })

    # Пробрасываем на окно для существующего кода
    window.structure_business = controllers['structure_business']
    window.structure = controllers['structure']
    window.links_business = controllers['links_business']
    window.links = controllers['links']
    window.link_operations = controllers['link_operations']
    window.database_controller = controllers['database_controller']
    window.system_dialogs = controllers['system_dialogs']
    window.app_shutdown = controllers['app_shutdown']

    # Централизованный менеджер состояния UI
    window.ui_state = UIStateManager(window)
    controllers['ui_state'] = window.ui_state

    # Контроллер действий
    window.action_controller = ActionController(window)
    controllers['action_controller'] = window.action_controller


def setup_ui_elements(window, controllers: Dict[str, Any]) -> None:
    """Создание UI элементов: действие и кнопка переключения сфер, вставка в панель."""
    # Действие переключения сфер
    window.switch_sphere_action = QAction(
        themed_icon("switch.svg", theme=get_current_theme(), source='main_window'),
        "Переключить сферу (F6)",
        window
    )
    window.switch_sphere_action.setToolTip("Переключиться на следующую доступную сферу")
    window.switch_sphere_action.triggered.connect(window.structure.switch_to_next_sphere)

    # Кнопка переключения сфер
    window.switch_sphere_button = QPushButton(
        window.switch_sphere_action.icon(),
        "Сфера (F6)"
    )
    window.switch_sphere_button.setToolTip(window.switch_sphere_action.toolTip())

    font = QFont()
    try:
        font.setPointSize(window.font().pointSize())
    except Exception:
        font.setPointSize(11)
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
        _setup_quick_add_widget(window, controllers)
    except Exception as e:
        logger.error(f"Failed during deferred dependency injection: {e}")


def _inject_to_category_tiles(window, controllers: Dict[str, Any]) -> None:
    """Инъекция зависимостей для CategoryTiles."""
    if not (hasattr(window, 'tiles') and window.tiles):
        return

    from app.utils.ui.dialog_manager import DialogMixin

    class DialogProvider(DialogMixin):
        def __init__(self, parent_widget):
            self.parent = parent_widget

        def show_link_dialog_for_category(self, category_id: int | None = None, link=None) -> bool:
            """Проксирует вызов показа диалога ссылки к главному окну."""
            try:
                if hasattr(self.parent, 'show_link_dialog_for_category'):
                    return bool(self.parent.show_link_dialog_for_category(category_id=category_id, link=link))
                self.show_error("Невозможно открыть диалог ссылки: окно не готово.")
                return False
            except Exception as e:
                self.show_error(f"Ошибка открытия диалога ссылки: {e}")
                return False

    dialog_provider = DialogProvider(window)

    window.tiles.inject_dependencies(
        structure_controller=controllers['structure'],
        ui_state_manager=controllers['ui_state'],
        dialog_provider=dialog_provider
    )


def _setup_quick_add_widget(window, controllers: Dict[str, Any]) -> None:
    """Создание и настройка QuickAddWidget."""
    if hasattr(window, 'quick_add_widget') and window.quick_add_widget:
        return

    from app.views.quick_add_widget import QuickAddWidget

    window.quick_add_widget = QuickAddWidget(
        window,
        controllers['links'],
        window  # category_provider
    )

    _connect_quick_add_signal(window, controllers)
    _add_quick_add_to_top_bar(window)


def _connect_quick_add_signal(window, controllers: Dict[str, Any]) -> None:
    """Подключение сигнала QuickAddWidget."""
    try:
        window.quick_add_widget.quickAddRequested.connect(
            lambda payload: controllers['links'].quick_add_link(
                payload.get("link_type"),
                payload.get("category_id")
            )
        )
    except Exception as e:
        logger.warning(f"Failed to connect quick add signal: {e}")


def _add_quick_add_to_top_bar(window) -> None:
    """Добавление QuickAddWidget в топ-бар."""
    if not hasattr(window, 'content_container'):
        return

    top_bar = window.content_container.layout()
    if not top_bar:
        return

    # Вставляем QuickAdd непосредственно перед поиском (mainSearch)
    insert_index = top_bar.count()
    try:
        for i in range(top_bar.count()):
            w = top_bar.itemAt(i).widget()
            if w and getattr(w, 'objectName', lambda: '')() == 'mainSearch':
                insert_index = i
                break
    except Exception:
        pass

    top_bar.insertWidget(insert_index, window.quick_add_widget)
    try:
        filt = getattr(window, '_auto_hide_tree_filter', None)
        if filt:
            QTimer.singleShot(0, filt._apply)
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
    window.structure_business.active_sphere_changed.connect(
        window._update_active_sphere_button
    )
    window.structure_business.active_sphere_changed.connect(
        window._update_left_panel_style
    )
    # При смене сферы гарантируем перезагрузку структуры (обновление дерева)
    try:
        window.structure_business.active_sphere_changed.connect(
            lambda *_: (
                getattr(window.structure_business, 'load_structure_async', None)()
                if callable(getattr(window.structure_business, 'load_structure_async', None))
                else window.structure_business.load_structure()
            )
        )
    except Exception:
        pass
    # При смене сферы обновляем верхние панели (Избранное/Недавние)
    try:
        window.structure_business.active_sphere_changed.connect(
            lambda *_: getattr(window, '_refresh_top_panels', lambda: None)()
        )
    except Exception:
        pass

    # После загрузки структуры также обновляем верхние панели
    try:
        window.structure_business.structure_loaded.connect(
            lambda *_: getattr(window, '_refresh_top_panels', lambda: None)()
        )
    except Exception:
        pass
    window.structure.item_changed.connect(window.on_structure_item_changed)
    window.structure.item_added.connect(window.on_structure_item_added)

    # Подключение к UIStateManager (загрузка категории)
    window.structure_business.category_selected.connect(
        lambda cat_id: window.ui_state.load_category(
            cat_id, source="StructureBusiness"
        )
    )

    # Дополнительно обновляем верхние панели при выборе раздела/категории
    try:
        window.structure_business.section_selected.connect(
            lambda *_: getattr(window, '_refresh_top_panels', lambda: None)()
        )
    except Exception:
        pass
    try:
        window.structure_business.category_selected.connect(
            lambda *_: getattr(window, '_refresh_top_panels', lambda: None)()
        )
    except Exception:
        pass


def _connect_database_signals(window) -> None:
    """Подключение сигналов базы данных."""
    db_controller = window.database_controller

    db_controller.database_restored.connect(lambda new_db: DatabaseEventHandler.handle_database_restored(window, new_db))
    db_controller.database_connected.connect(lambda new_db: DatabaseEventHandler.handle_database_connected(window, new_db))
    db_controller.favorites_cleared.connect(lambda: DatabaseEventHandler.handle_favorites_cleared(window))
    db_controller.operation_success.connect(lambda title, message: MessageHandler.show_success_message(window, title, message))
    db_controller.operation_error.connect(lambda title, message: MessageHandler.show_error_message(window, title, message))


def _connect_ui_signals(window) -> None:
    """Подключение сигналов UI."""
    try:
        if hasattr(window, 'tree') and window.tree:
            window.tree.currentItemChanged.connect(
                lambda *_: window.update_statusbar()
            )
    except Exception as e:
        logger.warning(f"Failed to connect tree signals: {e}")

    try:
        if hasattr(window, 'table') and window.table:
            selection_model = window.table.selectionModel()
            if selection_model:
                selection_model.selectionChanged.connect(
                    lambda *_: window.update_statusbar()
                )
    except Exception as e:
        logger.warning(f"Failed to connect table selection signals: {e}")


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
        if hasattr(window, 'fav_widget') and window.fav_widget:
            window.fav_widget.clear_favorites()
        
        # Обновляем таблицу ссылок, если выбрана категория
        category_id = window.get_current_category_id()
        if category_id and hasattr(window, 'ui_state') and window.ui_state:
            window.ui_state.update_category_without_stack_switch(category_id)
    
    @staticmethod
    def _update_controllers_with_new_db(window, new_db):
        """Обновить все контроллеры с новой БД."""
        # Обновляем структуру
        if hasattr(window, 'structure'):
            window.structure.db = new_db
            window.structure.spheres = new_db.spheres
            window.structure.sections = new_db.sections
            window.structure.categories = new_db.categories
            window.structure.load()
        
        # Обновляем ссылки
        if hasattr(window, 'links'):
            window.links.db = new_db
            window.links.links = new_db.links
        
        # Обновляем бизнес-логику структуры
        if hasattr(window, 'structure_business'):
            window.structure_business.db = new_db
            # Устанавливаем первую сферу как активную
            spheres = window.structure_business.get_spheres()
            if spheres:
                first_sphere_id = spheres[0].get('id', 1)
                window.structure_business.set_current_sphere(first_sphere_id)
    
    @staticmethod
    def _restore_ui_state(window):
        """Восстановить состояние UI после смены БД."""
        category_id = window.get_current_category_id()
        if category_id and hasattr(window, 'ui_state') and window.ui_state:
            window.ui_state.update_category_without_stack_switch(category_id)


class MessageHandler:
    """Обработчик сообщений пользователю."""
    
    @staticmethod
    def show_success_message(window, title: str, message: str):
        """Показать сообщение об успехе."""
        from app.utils.ui.dialog_manager import DialogManager
        DialogManager.show_info(
            window,
            title,
            message,
            informative_text="Операция выполнена успешно.",
        )
    
    @staticmethod
    def show_error_message(window, title: str, message: str):
        """Показать сообщение об ошибке."""
        from app.utils.ui.dialog_manager import DialogManager
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
            setup_controllers(self.window, controllers)
            logger.info("Controllers setup completed")
        except Exception as e:
            logger.error(f"Failed to setup controllers: {e}")
            raise SetupError("Critical component ControllersSetup failed to initialize") from e

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
            self.window._init_spheres_ui()
        except Exception as e:
            logger.error(f"Failed to initialize spheres: {e}")
            # Не останавливаем выполнение, так как это не критично для базовой работы

    # Метод _log_setup_results больше не требуется после упрощения


# Экспорт для обратной совместимости
__all__ = ['WindowControllersSetup']