# app/controllers/window_controllers_setup.py

from PyQt6.QtGui import QAction, QFont
from PyQt6.QtWidgets import QPushButton

from app.config_data import app_config
from app.controllers.app_shutdown_controller import AppShutdownController
from app.controllers.bootstrap import build_controllers
from app.controllers.keyboard import KeyboardManager
from app.controllers.ui.menu_controller import ActionController, MenuController
from app.utils.ui.icon.icon_operations.creators import themed_icon
from app.utils.ui.icon.path_service import get_current_theme
from app.utils.ui_state.ui_state_manager import UIStateManager


class WindowControllersSetup:
    """Компонент для настройки контроллеров и бизнес-логики главного окна."""
    
    def __init__(self, window_initializer):
        self.window_initializer = window_initializer
        self.window = window_initializer.window
        self.db = window_initializer.db
    
    def setup_controllers(self):
        """Настройка контроллеров."""
        # Централизованное создание контроллеров/бизнес-логики
        controllers = build_controllers(self.window)
        # Пробрасываем на окно для обратной совместимости существующего кода
        self.window.structure_business = controllers.structure_business
        self.window.structure = controllers.structure
        self.window.links_business = controllers.links_business
        self.window.links = controllers.links
        self.window.link_operations = controllers.link_operations
        self.window.database_controller = controllers.database_controller
        self.window.system_dialogs = controllers.system_dialogs
        self.window.app_shutdown = controllers.app_shutdown
        
        # Создание централизованного менеджера состояния UI
        self.window.ui_state = UIStateManager(self.window)
        
        # Создание контроллера действий
        self.window.action_controller = ActionController(self.window)
        
        # Создание действия переключения сфер
        self.window.switch_sphere_action = QAction(
            themed_icon("switch.svg", theme=get_current_theme(), source='main_window'), 
            "Переключить сферу (F6)", 
            self.window
        )
        
        # Инжектируем зависимости в виджеты после создания контроллеров
        self._inject_dependencies_to_widgets()
        self.window.switch_sphere_action.setToolTip("Переключиться на следующую доступную сферу")
        self.window.switch_sphere_action.triggered.connect(self.window.structure.switch_to_next_sphere)
        
        # Создание кнопки переключения сфер
        self.window.switch_sphere_button = QPushButton(
            self.window.switch_sphere_action.icon(), 
            "Сфера (F6)"
        )
        self.window.switch_sphere_button.setToolTip(self.window.switch_sphere_action.toolTip())
        font10 = QFont()
        font10.setPointSize(11)
        self.window.switch_sphere_button.setFont(font10)
        self.window.switch_sphere_button.clicked.connect(self.window.switch_sphere_action.trigger)
        
        # Добавление кнопки в нижнюю панель
        from PyQt6.QtWidgets import QWidget
        bottom_container = self.window.findChild(QWidget, "bottomBarContainer")
        if bottom_container and bottom_container.layout():
            bottom_container.layout().insertWidget(0, self.window.switch_sphere_button)
        
        # Подключение сигналов
        self.connect_signals()
        
        # Настройка централизованного управления горячими клавишами
        self.setup_keyboard_manager()
    
    def _inject_dependencies_to_widgets(self):
        """Инжектирует зависимости в виджеты после создания контроллеров."""
        # Инъекция для CategoryTiles
        if hasattr(self.window, 'tiles') and self.window.tiles:
            # Создаем правильный DialogMixin вместо передачи главного окна
            from app.utils.ui.dialog_manager import DialogMixin
            
            class DialogProvider(DialogMixin):
                def __init__(self, parent_widget):
                    self.parent = parent_widget
            
            dialog_provider = DialogProvider(self.window)
            
            self.window.tiles.inject_dependencies(
                structure_controller=self.window.structure,
                ui_state_manager=self.window.ui_state,
                dialog_provider=dialog_provider
            )
        
        # Инъекция для QuickAddWidget (создаем с зависимостями если не создан)
        if not hasattr(self.window, 'quick_add_widget') or not self.window.quick_add_widget:
            from app.views.quick_add_widget import QuickAddWidget
            self.window.quick_add_widget = QuickAddWidget(
                self.window,
                self.window.links,
                self.window  # category_provider
            )
            # Подключаем сигнал слабой связанности к контроллеру ссылок
            try:
                self.window.quick_add_widget.quickAddRequested.connect(
                    lambda payload: self.window.links.quick_add_link(
                        payload.get("link_type"), payload.get("category_id")
                    )
                )
            except Exception:
                pass
            # Добавляем в топ-бар после сепаратора
            if hasattr(self.window, 'content_container'):
                top_bar = self.window.content_container.layout()
                if top_bar:
                    # Находим позицию для вставки (после сепаратора favQuickSeparatorAfter)
                    separator_found = False
                    for i in range(top_bar.count()):
                        item = top_bar.itemAt(i)
                        if (item.widget() and 
                            item.widget().objectName() == "favQuickSeparatorAfter"):
                            # Вставляем QuickAddWidget сразу после сепаратора
                            top_bar.insertWidget(i + 1, self.window.quick_add_widget)
                            separator_found = True
                            break
                    
                    if not separator_found:
                        # Если сепаратор не найден, добавляем в конец
                        top_bar.addWidget(self.window.quick_add_widget)
    
    def connect_signals(self):
        """Подключение сигналов контроллеров."""
        self.window.structure_business.active_sphere_changed.connect(self.window._update_active_sphere_button)
        self.window.structure_business.active_sphere_changed.connect(self.window._update_left_panel_style)
        self.window.structure.item_changed.connect(self.window.on_structure_item_changed)
        self.window.structure.item_added.connect(self.window.on_structure_item_added)
        # ЦЕНТРАЛИЗОВАНО: Подключение к UIStateManager
        self.window.structure_business.category_selected.connect(
            lambda cat_id: self.window.ui_state.load_category(cat_id, source="StructureBusiness")
        )
        
        # Подключение сигналов DatabaseController
        self.window.database_controller.database_restored.connect(self._on_database_restored)
        self.window.database_controller.database_connected.connect(self._on_database_connected)
        self.window.database_controller.favorites_cleared.connect(self._on_favorites_cleared)
        self.window.database_controller.operation_success.connect(self._show_success_message)
        self.window.database_controller.operation_error.connect(self._show_error_message)
        
        # Подключение сигналов для обновления статусбара
        self.window.tree.currentItemChanged.connect(lambda *_: self.window.update_statusbar())
        sel = self.window.table.selectionModel()
        if sel:
            sel.selectionChanged.connect(lambda *_: self.window.update_statusbar())
    
    def setup_keyboard_manager(self):
        """Настройка централизованного управления горячими клавишами."""
        self.window.keyboard_manager = KeyboardManager(self.window)
    
    def initialize_spheres(self):
        """Инициализация сфер."""
        self.window._init_spheres_ui()
    
    # Обработчики сигналов DatabaseController
    def _on_database_restored(self, new_db):
        """Обработка восстановления базы данных."""
        self.window.db = new_db
        self._update_controllers_with_new_db(new_db)
        self._restore_ui_state()
        self.window.update_statusbar()
    
    def _on_database_connected(self, new_db):
        """Обработка подключения новой базы данных."""
        self.window.db = new_db
        self._update_controllers_with_new_db(new_db)
        self._restore_ui_state()
        self.window.update_statusbar()
    
    def _on_favorites_cleared(self):
        """Обработка очистки избранного."""
        if hasattr(self.window, 'fav_widget') and self.window.fav_widget:
            self.window.fav_widget.clear_favorites()
        
        # Обновляем таблицу ссылок, если выбрана категория
        category_id = self.window.get_current_category_id()
        if category_id and hasattr(self.window, 'ui_state') and self.window.ui_state:
            self.window.ui_state.update_category_without_stack_switch(category_id)
    
    def _show_success_message(self, title: str, message: str):
        """Показать сообщение об успехе."""
        from app.utils.ui.dialog_manager import DialogManager
        DialogManager.show_info(
            self.window,
            title,
            message,
            informative_text="Операция выполнена успешно.",
        )
    
    def _show_error_message(self, title: str, message: str):
        """Показать сообщение об ошибке."""
        from app.utils.ui.dialog_manager import DialogManager
        DialogManager.show_error(
            self.window,
            title,
            message,
            informative_text="Попробуйте повторить действие или обратитесь в поддержку.",
        )
    
    def _update_controllers_with_new_db(self, new_db):
        """Обновить все контроллеры с новой БД."""
        # Обновляем структуру
        if hasattr(self.window, 'structure'):
            self.window.structure.db = new_db
            self.window.structure.spheres = new_db.spheres
            self.window.structure.sections = new_db.sections
            self.window.structure.categories = new_db.categories
            self.window.structure.load()
        
        # Обновляем ссылки
        if hasattr(self.window, 'links'):
            self.window.links.db = new_db
            self.window.links.links = new_db.links
        
        # Обновляем бизнес-логику структуры
        if hasattr(self.window, 'structure_business'):
            self.window.structure_business.db = new_db
            # Устанавливаем первую сферу как активную
            spheres = self.window.structure_business.get_spheres()
            if spheres:
                first_sphere_id = spheres[0].get('id', 1)
                self.window.structure_business.set_current_sphere(first_sphere_id)
    
    def _restore_ui_state(self):
        """Восстановить состояние UI после смены БД."""
        category_id = self.window.get_current_category_id()
        if category_id and hasattr(self.window, 'ui_state') and self.window.ui_state:
            self.window.ui_state.update_category_without_stack_switch(category_id)
