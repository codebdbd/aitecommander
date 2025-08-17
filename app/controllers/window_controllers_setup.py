# app/controllers/window_controllers_setup.py

import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Callable
from dataclasses import dataclass

from PyQt6.QtGui import QAction, QFont
from PyQt6.QtWidgets import QPushButton, QWidget, QHBoxLayout, QSizePolicy
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


@dataclass
class SetupResult:
    """Результат настройки компонента."""
    success: bool
    component_name: str
    error_message: Optional[str] = None


class IComponentSetup(ABC):
    """Интерфейс для настройки компонентов окна."""
    
    @abstractmethod
    def setup(self, window, controllers: Dict[str, Any]) -> SetupResult:
        """Настроить компонент."""
        pass


class ControllersSetup(IComponentSetup):
    """Настройка основных контроллеров."""
    
    def setup(self, window, controllers: Dict[str, Any]) -> SetupResult:
        """Создание и настройка контроллеров."""
        try:
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
            
            # Пробрасываем на окно для обратной совместимости существующего кода
            window.structure_business = controllers['structure_business']
            window.structure = controllers['structure']
            window.links_business = controllers['links_business']
            window.links = controllers['links']
            window.link_operations = controllers['link_operations']
            window.database_controller = controllers['database_controller']
            window.system_dialogs = controllers['system_dialogs']
            window.app_shutdown = controllers['app_shutdown']
            
            # Создание централизованного менеджера состояния UI
            window.ui_state = UIStateManager(window)
            controllers['ui_state'] = window.ui_state
            
            # Создание контроллера действий
            window.action_controller = ActionController(window)
            controllers['action_controller'] = window.action_controller
            
            return SetupResult(True, "ControllersSetup")
            
        except Exception as e:
            logger.error(f"Failed to setup controllers: {e}")
            return SetupResult(False, "ControllersSetup", str(e))


class UIElementsSetup(IComponentSetup):
    """Настройка UI элементов."""
    
    def setup(self, window, controllers: Dict[str, Any]) -> SetupResult:
        """Создание UI элементов."""
        try:
            self._setup_sphere_switch_action(window)
            self._setup_sphere_switch_button(window)
            self._add_button_to_bottom_panel(window)
            
            return SetupResult(True, "UIElementsSetup")
            
        except Exception as e:
            logger.error(f"Failed to setup UI elements: {e}")
            return SetupResult(False, "UIElementsSetup", str(e))
    
    def _setup_sphere_switch_action(self, window):
        """Создание действия переключения сфер."""
        window.switch_sphere_action = QAction(
            themed_icon("switch.svg", theme=get_current_theme(), source='main_window'),
            "Переключить сферу (F6)",
            window
        )
        window.switch_sphere_action.setToolTip("Переключиться на следующую доступную сферу")
        window.switch_sphere_action.triggered.connect(window.structure.switch_to_next_sphere)
    
    def _setup_sphere_switch_button(self, window):
        """Создание кнопки переключения сфер."""
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
    
    def _add_button_to_bottom_panel(self, window):
        """Добавление кнопки в нижнюю панель."""
        bottom_container = window.findChild(QWidget, "bottomBarContainer")
        if bottom_container and bottom_container.layout():
            bottom_container.layout().insertWidget(0, window.switch_sphere_button)


class DependencyInjectionSetup(IComponentSetup):
    """Настройка инъекции зависимостей для виджетов."""
    
    def setup(self, window, controllers: Dict[str, Any]) -> SetupResult:
        """Инъекция зависимостей в виджеты."""
        try:
            # Откладываем инъекцию и создание UI-виджетов до старта цикла событий,
            # чтобы виджеты были полностью готовы и не вызывали ранний рендеринг
            QTimer.singleShot(0, lambda: self._deferred_setup(window, controllers))
            return SetupResult(True, "DependencyInjectionSetup")
        except Exception as e:
            logger.error(f"Failed to schedule dependency injection: {e}")
            return SetupResult(False, "DependencyInjectionSetup", str(e))

    def _deferred_setup(self, window, controllers: Dict[str, Any]):
        try:
            self._inject_to_category_tiles(window, controllers)
            self._setup_quick_add_widget(window, controllers)
        except Exception as e:
            logger.error(f"Failed during deferred dependency injection: {e}")
    
    def _inject_to_category_tiles(self, window, controllers: Dict[str, Any]):
        """Инъекция зависимостей для CategoryTiles."""
        if not (hasattr(window, 'tiles') and window.tiles):
            return
            
        from app.utils.ui.dialog_manager import DialogMixin
        
        class DialogProvider(DialogMixin):
            def __init__(self, parent_widget):
                self.parent = parent_widget
        
        dialog_provider = DialogProvider(window)
        
        window.tiles.inject_dependencies(
            structure_controller=controllers['structure'],
            ui_state_manager=controllers['ui_state'],
            dialog_provider=dialog_provider
        )
    
    def _setup_quick_add_widget(self, window, controllers: Dict[str, Any]):
        """Создание и настройка QuickAddWidget."""
        if hasattr(window, 'quick_add_widget') and window.quick_add_widget:
            return
            
        from app.views.quick_add_widget import QuickAddWidget
        
        window.quick_add_widget = QuickAddWidget(
            window,
            controllers['links'],
            window  # category_provider
        )
        
        # Безопасное подключение сигнала
        self._connect_quick_add_signal(window, controllers)
        self._add_quick_add_to_top_bar(window)
    
    def _connect_quick_add_signal(self, window, controllers: Dict[str, Any]):
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
    
    def _add_quick_add_to_top_bar(self, window):
        """Добавление QuickAddWidget в топ-бар."""
        if not hasattr(window, 'content_container'):
            return
        
        top_bar = window.content_container.layout()
        if not top_bar:
            return
        
        # Вставляем QuickAdd непосредственно перед поиском (mainSearch),
        # чтобы порядок был: QuickAdd → Favorites → Recent → Search
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
        # Если установлен фильтр авто-скрытия топ-бара, применить его сразу
        try:
            filt = getattr(window, '_auto_hide_tree_filter', None)
            if filt:
                QTimer.singleShot(0, filt._apply)
        except Exception:
            pass


class SignalConnectionSetup(IComponentSetup):
    """Настройка подключения сигналов."""
    
    def setup(self, window, controllers: Dict[str, Any]) -> SetupResult:
        """Подключение сигналов контроллеров."""
        try:
            self._connect_structure_signals(window)
            self._connect_database_signals(window)
            # Откладываем подключение UI-сигналов, чтобы избежать ранних вызовов рендера
            QTimer.singleShot(0, lambda: self._connect_ui_signals(window))
            
            return SetupResult(True, "SignalConnectionSetup")
            
        except Exception as e:
            logger.error(f"Failed to connect signals: {e}")
            return SetupResult(False, "SignalConnectionSetup", str(e))
    
    def _connect_structure_signals(self, window):
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
                    getattr(window.structure_business, 'load_structure_async', None)() \
                    if callable(getattr(window.structure_business, 'load_structure_async', None)) \
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
        
        # ЦЕНТРАЛИЗОВАНО: Подключение к UIStateManager (загрузка категории)
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
    
    def _connect_database_signals(self, window):
        """Подключение сигналов базы данных."""
        db_controller = window.database_controller
        
        db_controller.database_restored.connect(self._create_db_restored_handler(window))
        db_controller.database_connected.connect(self._create_db_connected_handler(window))
        db_controller.favorites_cleared.connect(self._create_favorites_cleared_handler(window))
        db_controller.operation_success.connect(self._create_success_handler(window))
        db_controller.operation_error.connect(self._create_error_handler(window))
    
    def _connect_ui_signals(self, window):
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
    
    def _create_db_restored_handler(self, window) -> Callable:
        """Создание обработчика восстановления БД."""
        def handler(new_db):
            DatabaseEventHandler.handle_database_restored(window, new_db)
        return handler
    
    def _create_db_connected_handler(self, window) -> Callable:
        """Создание обработчика подключения БД."""
        def handler(new_db):
            DatabaseEventHandler.handle_database_connected(window, new_db)
        return handler
    
    def _create_favorites_cleared_handler(self, window) -> Callable:
        """Создание обработчика очистки избранного."""
        def handler():
            DatabaseEventHandler.handle_favorites_cleared(window)
        return handler
    
    def _create_success_handler(self, window) -> Callable:
        """Создание обработчика успешных операций."""
        def handler(title: str, message: str):
            MessageHandler.show_success_message(window, title, message)
        return handler
    
    def _create_error_handler(self, window) -> Callable:
        """Создание обработчика ошибок."""
        def handler(title: str, message: str):
            MessageHandler.show_error_message(window, title, message)
        return handler


class KeyboardSetup(IComponentSetup):
    """Настройка управления клавиатурой."""
    
    def setup(self, window, controllers: Dict[str, Any]) -> SetupResult:
        """Настройка централизованного управления горячими клавишами."""
        try:
            window.keyboard_manager = KeyboardManager(window)
            return SetupResult(True, "KeyboardSetup")
        except Exception as e:
            logger.error(f"Failed to setup keyboard manager: {e}")
            return SetupResult(False, "KeyboardSetup", str(e))


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
        
        # Реестр компонентов настройки
        self._setup_components = [
            ControllersSetup(),
            UIElementsSetup(),
            DependencyInjectionSetup(),
            SignalConnectionSetup(),
            KeyboardSetup(),
        ]
    
    def setup_controllers(self):
        """Настройка контроллеров и компонентов."""
        controllers = {}
        setup_results = []
        
        for component in self._setup_components:
            try:
                result = component.setup(self.window, controllers)
                setup_results.append(result)
                
                if not result.success:
                    logger.error(f"Component {result.component_name} failed: {result.error_message}")
                    # Продолжаем настройку других компонентов
                    
            except Exception as e:
                logger.error(f"Unexpected error in {component.__class__.__name__}: {e}")
                setup_results.append(
                    SetupResult(False, component.__class__.__name__, str(e))
                )
        
        # Логирование результатов
        self._log_setup_results(setup_results)
        
        # Проверяем критические компоненты
        critical_components = ['ControllersSetup']
        for result in setup_results:
            if result.component_name in critical_components and not result.success:
                raise SetupError(f"Critical component {result.component_name} failed to initialize")
    
    def initialize_spheres(self):
        """Инициализация сфер."""
        try:
            self.window._init_spheres_ui()
        except Exception as e:
            logger.error(f"Failed to initialize spheres: {e}")
            # Не останавливаем выполнение, так как это не критично для базовой работы
    
    def _log_setup_results(self, results):
        """Логирование результатов настройки."""
        successful = [r for r in results if r.success]
        failed = [r for r in results if not r.success]
        
        logger.info(f"Setup completed: {len(successful)} successful, {len(failed)} failed")
        
        if failed:
            logger.warning("Failed components:")
            for result in failed:
                logger.warning(f"  - {result.component_name}: {result.error_message}")


# Экспорт для обратной совместимости
__all__ = ['WindowControllersSetup']