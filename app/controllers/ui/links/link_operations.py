# app/controllers/links_ui/link_operations.py

import logging
from datetime import datetime
from typing import Dict, Optional

from PyQt6.QtWidgets import QDialog, QMessageBox

from app.controllers.domain.structure.commands import SaveLinkCommand
from app.utils.links.link_utils import LinkInfo, LinkOpener
from app.views.dialogs.entity_dialogs import NoteDialog

from .base_component import BaseLinksUIComponent
from .exceptions import CategoryNotFoundError, DatabaseError, LinkValidationError


class LinksUILinkOperations(BaseLinksUIComponent):
    """Операции с ссылками для LinksUIController."""
    
    def quick_add_link(self, link_type: str, category_id: int = None):
        """Быстрое добавление ссылки."""
        try:
            cat_id = self._validate_category_exists(category_id)
        except CategoryNotFoundError as e:
            self._show_warning(str(e))
            return
        
        # Создаем контроллер для диалога
        from PyQt6.QtWidgets import QDialog

        from app.controllers.ui.dialogs import LinkDialogController
        from app.views.dialogs.link_dialog.link_dialog import LinkDialog
        
        link_controller = LinkDialogController(self.business.db)
        init_data = link_controller.get_initialization_data(cat_id, None)
        
        dlg = LinkDialog(
            initialization_data=init_data,
            dialog_controller=link_controller,
            link=None,
            category_id=cat_id,
            parent=self.main,
            link_controller=link_controller
        )
        
        # Устанавливаем тип ссылки
        dlg.set_link_type(link_type)
        
        if dlg.exec() == QDialog.DialogCode.Accepted:
            links_to_save = link_controller.get_result_data()
            if links_to_save:
                for data in links_to_save:
                    cmd = SaveLinkCommand(new_data=data, old_data=None, main_window=self.main)
                    self.main.undo_stack.push(cmd)

    
    def show_note_dialog(self, link: Dict):
        """Показать диалог заметки для ссылки."""
        if not link:
            return
        
        # Создаем копию ссылки для безопасности
        link_copy = link.copy()
        
        dlg = NoteDialog(link_copy, parent=self.main)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            # Обновляем ссылку через бизнес-логику
            try:
                # Бизнес-слой сам эмитит link_updated внутри save_link()
                self.business.save_link(link_copy)
                self.logger.debug(f"Note saved for link: {link_copy.get('name')}")
            except DatabaseError as e:
                self.logger.error(f"Database error saving note: {e}")
                self._show_error(f"{self.get_message('database_error')}: {str(e)}")
            except Exception as e:
                self.logger.error(f"Unexpected error saving note: {e}")
                self._show_error(f"{self.get_message('error_saving')}: {str(e)}")
    
    def _open_link(self, link: Dict):
        """Открыть ссылку используя LinkOpener."""
        self.logger.debug(f"Opening link: type={link.get('type')}, url={link.get('url')}")
        
        success = False
        try:
            # Создаем LinkInfo из словаря
            self.logger.debug(f"_open_link: link dict={link}")
            link_info = LinkInfo.from_dict(link)
            self.logger.info(f"_open_link: link_info={link_info}")
            self.logger.debug(f"_open_link: link_info created with browser_key={link_info.browser_key}")
            
            # Используем LinkOpener для открытия
            opener = LinkOpener()
            opener.open_link(link_info)
            
            success = True
        except LinkValidationError as e:
            self.logger.error(f"Link validation error: {e}")
            self._show_error(f"{self.get_message('validation_error')}: {str(e)}")
        except ValueError as e:
            # Дружелюбная обработка небезопасных URL без всплывающих ошибок
            msg = str(e)
            if msg.startswith("Unsafe URL:"):
                from app.utils.ui.dialog_manager import DialogManager
                safe_msg = self.get_message('unsafe_url_info', 'Эта ссылка не может быть открыта по соображениям безопасности.')
                details = msg  # чтобы был доступен текст причины при включённых деталях
                self.logger.warning(f"Blocked unsafe URL: {msg}")
                DialogManager.show_info(
                    parent=self.main,
                    title=self.get_message('warning_title', 'Предупреждение'),
                    message=safe_msg,
                    informative_text=self.get_message('unsafe_url_hint', 'Проверьте адрес ссылки или отредактируйте её.'),
                    details=details,
                    silent=True,
                )
            else:
                # Прочие ValueError — как ошибка
                self.logger.error(f"Error opening link {link.get('url', link)}: {e}", exc_info=True)
                self._show_error(f"Не удалось открыть ссылку: {str(e)}")
        except Exception as e:
            self.logger.error(f"Error opening link {link.get('url', link)}: {e}", exc_info=True)
            self._show_error(f"Не удалось открыть ссылку: {str(e)}")
        
        # Обновляем счетчик последних ссылок только при успешном открытии
        if success:
            link_data = link.copy()
            link_data['last_used'] = datetime.now().isoformat()

            # Немедленно обновить строку в таблице (UI feedback)
            if hasattr(self.controller, 'table') and self.controller.table is not None:
                self.controller.table.update_link_by_id(link_data)

            # Асинхронно сохранить в БД (старое поведение)
            self.business.save_link(link_data)

            if hasattr(self.main, 'recent_links_widget'):
                self.main.recent_links_widget.update_recent_links()
    
    def _toggle_fav(self, link: Dict = None):
        """Переключить статус избранного."""
        if not link:
            selected_links = self.controller.get_selected_links()
            if not selected_links:
                return
            link = selected_links[0]
        
        self.business.toggle_favorite(link)