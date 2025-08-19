# app/views/main_window.py

from __future__ import annotations
from typing import TYPE_CHECKING, Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QIcon, QKeySequence
from PyQt6.QtWidgets import QMainWindow, QToolButton

if TYPE_CHECKING:  # Только для аннотаций типов, без зависимости во время выполнения
    from app.controllers.ui.theme_controller import ThemeController

from app.config_data import app_config
from app.models.db import Database
from app.settings import AppSettings
from app.utils.ui.icon.cache_manager import clear_icon_cache
from app.utils.ui.icon.icon_operations.creators import create_icon_from_path
from app.views.status_bar import update_status_bar as _update_status_bar
from app.utils.ui.icon.path_service import icon_path_service
from app.utils.db.synchronization import signal_guard
from app.views.effects.neon_effect import NeonEventFilter


class MainWindow(QMainWindow):
    shown: pyqtSignal = pyqtSignal()  # Сигнал отображения окна

    @property
    def has_structure(self) -> bool:
        """Проверка наличия и валидности структуры."""
        return hasattr(self, 'structure') and self.structure is not None
    
    @property
    def has_links(self) -> bool:
        """Проверка наличия и валидности контроллера ссылок."""
        return hasattr(self, 'links') and self.links is not None
    
    @property
    def has_tiles(self) -> bool:
        """Проверка наличия и валидности плиток."""
        return hasattr(self, 'tiles') and self.tiles is not None
    
    @property
    def has_table(self) -> bool:
        """Проверка наличия и валидности таблицы."""
        return hasattr(self, 'table') and self.table is not None
    
    @property
    def has_stack(self) -> bool:
        """Проверка наличия и валидности стека."""
        return hasattr(self, 'stack') and self.stack is not None
    
    @property
    def has_structure_business(self) -> bool:
        """Проверка наличия и валидности бизнес-логики структуры."""
        return hasattr(self, 'structure_business') and self.structure_business is not None
    
    @property
    def has_theme_ctrl(self) -> bool:
        """Проверка наличия и валидности контроллера тем."""
        return hasattr(self, 'theme_ctrl') and self.theme_ctrl is not None
    
    @property
    def has_undo_stack(self) -> bool:
        """Проверка наличия и валидности undo stack."""
        return hasattr(self, 'undo_stack') and self.undo_stack is not None
    
    @property
    def has_left_panel(self) -> bool:
        """Проверка наличия и валидности левой панели."""
        return hasattr(self, 'left_panel') and self.left_panel is not None
    
    @property
    def has_fav_widget(self) -> bool:
        """Проверка наличия и валидности виджета избранного."""
        return hasattr(self, 'fav_widget') and self.fav_widget is not None
    
    @property
    def has_db(self) -> bool:
        """Проверка наличия и валидности базы данных."""
        return hasattr(self, 'db') and self.db is not None
    
    def handle_import_browser_bookmarks(self):
        self.system_dialogs.handle_import_browser_bookmarks()

    
    def get_current_category_id(self) -> Optional[int]:
        """Возвращает ID текущей категории."""
        tiles_stack_index = app_config.get('ui.stack_indices.tiles', 0)
        if (self.has_tiles and self.has_stack and 
            self.stack.currentIndex() == tiles_stack_index and 
            hasattr(self.tiles, '_current_item_id') and self.tiles._current_item_id is not None):
            return self.tiles._current_item_id
        
        if hasattr(self, 'current_category_id') and self.current_category_id:
            return self.current_category_id
        
        if self.has_structure and hasattr(self.structure, 'tree'):
            current_item = self.structure.tree.currentItem()
            if current_item:
                from app.utils.ui.qt.roles import get_tree_tuple
                t = get_tree_tuple(current_item, 0)
                if t:
                    item_type, item_id = t
                    if item_type == 'category' and isinstance(item_id, int):
                        return item_id
        
        if self.has_structure_business:
            return self.structure_business.get_first_category_id()
        
        return None
    
    
    
    def edit_structure_item(self, item):
        """Редактировать элемент структуры."""
        if self.has_structure:
            self.structure.edit_item(item)
    
    def add_new_category(self):
        """Добавить новую категорию."""
        if self.has_structure:
            self.structure.add_new_category()
    
    def show_link_dialog_for_category(self, category_id: int = None, link=None) -> bool:
        """Показать диалог ссылки для категории."""
        return self.link_operations.show_link_dialog(link=link, category_id=category_id)
    
    def reload_structure(self) -> None:
        """Перезагрузить структуру."""
        if self.has_structure:
            self.structure.load()
    
    def reload_current_category(self) -> None:
        """Перезагрузить текущую категорию через UIStateManager."""
        category_id = self.get_current_category_id()
        if category_id:
            if hasattr(self, 'ui_state') and self.ui_state:
                self.ui_state.load_category(category_id, source="reload_current_category")
    
    
    
    def get_link_at_row(self, row: int):
        """Получить ссылку по номеру строки."""
        if self.has_links:
            return self.links.get_link_at(row)
        return None
    
    def open_link(self, link):
        """Открыть ссылку."""
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"MainWindow.open_link called with link: {link}")
        if self.has_links:
            self.links.open_link(link)
    
    def toggle_link_favorite(self, link):
        """Переключить статус избранного."""
        if self.has_links:
            self.links.toggle_favorite(link)
    
    def copy_selected_links(self):
        """Копировать выбранные ссылки."""
        if self.has_links:
            self.links.copy_selected_links()
    
    def paste_links(self):
        """Вставить ссылки."""
        if self.has_links:
            self.links.paste_links()
    
    def cut_selected_links(self):
        """Вырезать выбранные ссылки."""
        if self.has_links:
            self.links.cut_selected_links()
    
    def show_note_dialog_for_link(self, link):
        """Показать диалог заметки для ссылки."""
        if self.has_links:
            self.links.show_note_dialog(link)
    
    def delete_selected_links(self):
        """Удалить выбранные ссылки."""
        if self.has_links:
            self.links.delete_selected_links()
    
    def select_all_links(self):
        """Выделить все ссылки."""
        if self.has_table:
            self.table.selectAll()
    
    def get_selected_rows(self):
        """Получить номера выбранных строк."""
        if self.has_table and hasattr(self.table, 'selectionModel'):
            selected_indexes = self.table.selectionModel().selectedRows()
            return [index.row() for index in selected_indexes if index.isValid()]
        return []
    
    
    
    def get_available_themes(self):
        """Получить доступные темы."""
        if self.has_theme_ctrl:
            return self.theme_ctrl.available()
        return []
    
    def apply_theme(self, theme_name: str):
        """Применить тему."""
        if self.has_theme_ctrl:
            self.theme_ctrl.apply(theme_name)
    
    def get_undo_stack(self):
        """Вернуть undo stack."""
        return getattr(self, 'undo_stack', None)
    
    def create_undo_redo_actions(self):
        """Создать действия Undo/Redo."""
        if not self.has_undo_stack:
            return None, None
            
        undo_action = self.undo_stack.createUndoAction(self)
        undo_action.setText("&Отменить")
        undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        
        redo_action = self.undo_stack.createRedoAction(self)
        redo_action.setText("&Повторить")
        redo_action.setShortcut(QKeySequence.StandardKey.Redo)
        
        self.undo_stack.undoTextChanged.connect(
            lambda *_: undo_action.setText("&Отменить")
        )
        self.undo_stack.redoTextChanged.connect(
            lambda *_: redo_action.setText("&Повторить")
        )
        
        self.undo_action = undo_action
        self.redo_action = redo_action
        
        return undo_action, redo_action

    def __init__(self, db: Database, settings: AppSettings, theme_ctrl: ThemeController):
        super().__init__()
        
        from app.views.main_components import WindowInitializer
        initializer = WindowInitializer(self, db, settings, theme_ctrl)
        initializer.initialize_window()

    def _init_spheres_ui(self):
        """Инициализировать UI для сфер (асинхронно)."""
        self.structure_business.spheres_loaded.connect(self._on_spheres_loaded_ui)
        
        self.structure_business.load_spheres_async()
    
    def _on_spheres_loaded_ui(self, spheres: list):
        """Обработчик завершения асинхронной загрузки сфер."""
        self.spheres_bar.setUpdatesEnabled(False)
        
        try:
            for button in self.sphere_group.buttons():
                self.sphere_group.removeButton(button)
            
            s_layout = self.spheres_bar.layout()
            
            for i in reversed(range(s_layout.count())): 
                widget = s_layout.itemAt(i).widget()
                if widget:
                    widget.setParent(None)
                    widget.deleteLater()
            self.sphere_buttons.clear()
            
            self.sphere_group.setExclusive(True)
            
            # Единый фильтр для неонового эффекта кнопок сфер
            if not hasattr(self, '_neon_sphere_filter') or self._neon_sphere_filter is None:
                self._neon_sphere_filter = NeonEventFilter(self)

            for sp in spheres:
                btn = QToolButton()
                sphere_id = sp["id"]
                btn.setCheckable(True)
                icon_name = sp["icon_path"] if "icon_path" in sp.keys() else None
                if icon_name:
                    icon_path = icon_path_service.get_ui_icons_dir() / icon_name
                    if icon_path.exists():
                        btn.setIcon(create_icon_from_path(str(icon_path)))
                    else:
                        btn.setIcon(QIcon())
                else:
                    btn.setIcon(QIcon())
                btn.setIconSize(app_config.get_sphere_button_icon_size())
                btn.setToolTip(sp["name"])
                self.sphere_group.addButton(btn, sphere_id)
                btn.clicked.connect(lambda _, sid=sphere_id: self._switch_sphere(sid))
                # Неоновый эффект при hover/focus
                btn.installEventFilter(self._neon_sphere_filter)
                self.sphere_buttons[sphere_id] = btn
                s_layout.addWidget(btn)

        finally:
            self.spheres_bar.setUpdatesEnabled(True)
            self.spheres_bar.update()
        
        if spheres:
            self._switch_sphere(spheres[0]["id"])

    @signal_guard("_update_active_sphere_button")
    def _update_active_sphere_button(self, sphere_id: int):
        """Обновляет состояние кнопок сфер и фокус."""
        for button in self.sphere_buttons.values():
            button.setChecked(False)

        button = self.sphere_buttons.get(sphere_id)
        if button:
            button.setChecked(True)
            button.setFocus()


    def show_link_dialog(self, link=None, category_id=None):
        """Показать диалог создания/редактирования ссылки."""
        selected_link_id = link.get('id') if link else None
        
        result = self.link_operations.show_link_dialog(link, category_id)
        self.update_statusbar()
        
        if result and selected_link_id:
            from app.utils.system.task_scheduler import schedule_selection_restore
            schedule_selection_restore(
                lambda: self._restore_table_selection(selected_link_id),
                f"table_selection_{selected_link_id}"
            )

    def _get_selected_links(self):
        """Вернуть список выбранных ссылок."""
        selected_rows = self.links.get_selected_rows()
        if not selected_rows:
            return []
        
        links = [self.links.get_link_at(r) for r in selected_rows]
        return [ln for ln in links if ln]
    
    def _edit_selected_link(self):
        """Редактировать выбранную ссылку."""
        link = self.links.get_link_by_row(self.links.current_row())
        if link:
            self.show_link_dialog(link=link)
            self.update_statusbar()
            return True
        return False

    def edit_current(self):
        """Редактировать текущий элемент."""
        if hasattr(self, 'action_controller') and self.action_controller:
            self.action_controller.edit_current()

    def delete_current(self):
        """Удалить текущий элемент (ссылку или структурный элемент)."""
        if hasattr(self, 'action_controller') and self.action_controller:
            self.action_controller.delete_current()

    def show_section_dialog(self):
        self.structure.add_new_section()

    def show_category_dialog(self):
        self.structure.add_new_category()


    def update_statusbar(self):
        _update_status_bar(self)

    def on_structure_item_added(self, item_type: str, parent_id: int, data: dict):
        self.structure.on_structure_item_added(item_type, parent_id, data)

    @signal_guard("on_structure_item_changed")
    def on_structure_item_changed(self, item_type: str, item_id: int, data: dict):
        self.structure.on_structure_item_changed(item_type, item_id, data)

    def show_about_dialog(self):
        self.system_dialogs.show_about_dialog()

    def show_settings_dialog(self):
        self.system_dialogs.show_settings_dialog()

    def show_file_search_dialog(self):
        self.system_dialogs.show_file_search_dialog()

    def update_theme(self):
        clear_icon_cache()
        old_menu = self.menuBar()
        if old_menu is not None:
            old_menu.deleteLater()
        self.menu_controller.clear_cache()
        self.setMenuBar(self.menu_controller.create_main_menu())
        self.structure.reload_icons()
        if self.has_fav_widget:
            self.fav_widget.update_favorites()
        else:
            def _try_update_fav():
                if self.has_fav_widget:
                    self.fav_widget.update_favorites()
            QTimer.singleShot(150, _try_update_fav)

    def _switch_sphere(self, sphere_id: int) -> None:
        self.structure.switch_sphere(sphere_id)

    def _show_note_for_current(self):
        """Показать диалог заметки для текущей ссылки."""
        row = self.links.current_row()
        if row >= 0:
            link = self.links.get_link_by_row(row)
            if link:
                self.links.show_note_dialog(link)

    @signal_guard("_update_left_panel_style")
    def _update_left_panel_style(self, sphere_id: int):
        """Обновляет стиль левой панели при смене сферы."""
        if self.has_left_panel:
            current_sphere = self.left_panel.property("sphere")
            if current_sphere == str(sphere_id):
                return

            self.left_panel.setUpdatesEnabled(False)
            try:
                self.left_panel.setProperty("sphere", str(sphere_id))
                self.left_panel.style().unpolish(self.left_panel)
                self.left_panel.style().polish(self.left_panel)
            finally:
                self.left_panel.setUpdatesEnabled(True)
                self.left_panel.update()

    def _refresh_top_panels(self) -> None:
        """Обновляет верхние панели (Избранное/Недавние)."""
        try:
            if hasattr(self, 'fav_widget') and self.fav_widget:
                self.fav_widget.update_favorites()
        except Exception:
            pass
        try:
            if hasattr(self, 'recent_links_widget') and self.recent_links_widget:
                self.recent_links_widget.update_recent_links()
        except Exception:
            pass

    def on_search(self, text: str):
        self.links.on_search(text)

    def _restore_table_selection(self, link_id: int):
        """Восстановить выбор ссылки в таблице по ID."""
        if not self.has_table:
            return
            
        for row in range(self.links.get_row_count()):
            link = self.links.get_link_by_row(row)
            if link and link.get('id') == link_id:
                self.links.select_row(row)
                self.links.set_current_cell(row, 0)
                self.links.scroll_to_row(row)
                if self.has_table:
                    self.table.setFocus()
                break
    
    def showEvent(self, event):
        """Эмитит сигнал shown при первом показе окна."""
        super().showEvent(event)
        if not hasattr(self, '_shown_emitted'):
            self._shown_emitted = True
            QTimer.singleShot(200, self.shown.emit)

    
    def closeEvent(self, event):
        """Корректное завершение и закрытие ресурсов."""
        if hasattr(self, 'app_shutdown') and self.app_shutdown:
            self.app_shutdown.perform_shutdown(event)
            return
        super().closeEvent(event)

