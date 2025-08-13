# app/controllers/link_operations_controller.py

from PyQt6.QtWidgets import QDialog

from app.config_data import app_config
from app.controllers.domain.structure.commands import (
    BatchSaveLinksCommand,
    DeleteLinkCommand,
    SaveLinkCommand,
)
from app.utils.system.undo.stack import UndoManager
from app.views.dialogs.link_dialog.link_dialog import LinkDialog

# Константы для макросов отмены/повтора
MACRO_DELETE_LINKS_TEXT = "Удаление {count} ссылок"


class LinkOperationsController:
    """Контроллер для операций со ссылками: создание, редактирование, удаление."""
    
    def __init__(self, db, undo_stack: UndoManager, main_window):
        self.db = db
        self.undo_stack = undo_stack
        self.main_window = main_window
    
    def get_dialog_initialization_data(self, category_id=None):
        """Получить данные для инициализации диалога ссылки."""
        data = {
            'spheres': self._prepare_spheres_data(),
            'category_hierarchy': None
        }
        
        if category_id:
            data['category_hierarchy'] = self._get_category_hierarchy(category_id)
        
        return data
    
    def _prepare_spheres_data(self):
        """Подготовить данные сфер для диалога."""
        return self.db.spheres.get_spheres()
    
    def _get_category_hierarchy(self, category_id):
        """Получить иерархию категории (сфера -> раздел -> категория)."""
        return self.db.categories.get_category_hierarchy(category_id)
    
    def get_sections_for_sphere(self, sphere_id):
        """Получить разделы для сферы."""
        return self.db.sections.get_sections(sphere_id)
    
    def get_categories_for_section(self, section_id):
        """Получить категории для раздела."""
        return self.db.categories.get_categories(section_id)
    
    def get_database(self):
        """Получить ссылку на базу данных для валидации."""
        return self.db
    
    def show_link_dialog(self, link=None, category_id=None):
        """Показать диалог создания/редактирования ссылки."""
        # Гарантировать, что всегда передаём валидный category_id
        cat_id = category_id or self.main_window.get_current_category_id()
        if not cat_id:
            # Попробовать взять первую доступную категорию из базы
            cats = self.db.connection.execute("SELECT id FROM category ORDER BY id LIMIT 1").fetchone()
            if cats:
                cat_id = cats["id"]
        
        # Создаем контроллер для диалога
        from .link_dialog_controller import LinkDialogController
        link_controller = LinkDialogController(self.db)
        
        # Получаем данные для инициализации через контроллер
        init_data = link_controller.get_initialization_data(cat_id, link)
        
        dlg = LinkDialog(
            initialization_data=init_data,
            dialog_controller=self,
            link=link,
            category_id=cat_id,
            parent=self.main_window,
            link_controller=link_controller
        )
        
        result = dlg.exec() == QDialog.DialogCode.Accepted
        if result:
            # Получаем данные через контроллер
            links_to_save = link_controller.get_result_data()
            import logging
            logger = logging.getLogger(__name__)
            logger.debug(f"show_link_dialog: got {len(links_to_save) if links_to_save else 0} links to save")
            if links_to_save:
                for i, link in enumerate(links_to_save):
                    logger.debug(f"show_link_dialog: link {i}: name={link.get('name')}, browser_key={link.get('browser_key')}")
            
            if not links_to_save:
                return False
            # ВАЖНО: определяем обновление/создание по самим результатам, а не по факту редактирования
            # Если результат содержит id, это обновление существующей записи; иначе — создание новой
            is_update = link is not None
            
            # Используем пакетную команду для множественных ссылок
            if len(links_to_save) > 1:
                # Для множественных ссылок (профили) всегда создаются новые записи
                logger.debug(f"show_link_dialog: using BatchSaveLinksCommand for {len(links_to_save)} links")
                cmd = BatchSaveLinksCommand(
                    links_data=links_to_save,
                    old_link_data=None,  # Всегда None для множественных ссылок
                    main_window=self.main_window
                )
                self.undo_stack.push(cmd)
                
                # Устанавливаем фокус на первую добавленную ссылку
                if hasattr(self.main_window, 'links') and hasattr(self.main_window.links, 'focus_on_link'):
                    # Используем QTimer для отложенной фокусировки после обновления UI
                    from PyQt6.QtCore import QTimer
                    first_link_id = cmd.created_ids[0] if hasattr(cmd, 'created_ids') and cmd.created_ids else None
                    if first_link_id:
                        QTimer.singleShot(200, lambda: self.main_window.links.focus_on_link(first_link_id))
            else:
                # Для одиночных ссылок используем обычную команду
                data = links_to_save[0]
                logger.debug(f"show_link_dialog: using SaveLinkCommand for single link: name={data.get('name')}, browser_key={data.get('browser_key')}")
                if data.get("_action") == "delete":
                    self.db.links.delete_link(data["id"])
                else:
                    # Переопределяем признак обновления для одиночного результата:
                    # если у данных нет id — это создание новой ссылки, не передаём old_data
                    is_update_single = bool(data.get('id'))
                    cmd = SaveLinkCommand(
                        new_data=data,
                        old_data=link if is_update_single else None,
                        main_window=self.main_window
                    )
                    self.undo_stack.push(cmd)
                    
                    # Устанавливаем фокус на добавленную ссылку (только для новых ссылок)
                    logger.debug(f"Focus check: is_update={is_update_single}, has_links={hasattr(self.main_window, 'links')}")
                    if hasattr(self.main_window, 'links'):
                        logger.debug(f"Links object exists, has_focus_method={hasattr(self.main_window.links, 'focus_on_link')}")
                    
                    if not is_update_single and hasattr(self.main_window, 'links') and hasattr(self.main_window.links, 'focus_on_link'):
                        # Используем QTimer для отложенной фокусировки после обновления UI
                        from PyQt6.QtCore import QTimer
                        link_id = cmd.created_id or data.get('id')
                        logger.info(f"Attempting to focus on link: cmd.created_id={cmd.created_id}, data.id={data.get('id')}, final_link_id={link_id}")
                        if link_id:
                            logger.info(f"Scheduling focus on link ID {link_id} in 200ms")
                            QTimer.singleShot(200, lambda: self.main_window.links.focus_on_link(link_id))
                        else:
                            logger.warning("No link ID available for focusing")
    
        return result
    
    def delete_links_with_confirmation(self, links):
        """Удалить ссылки с подтверждением пользователя."""
        if not links:
            return
        
        # Если выделена только одна ссылка — удаляем без подтверждения
        if len(links) == 1:
            cmd = DeleteLinkCommand(link_to_delete=links[0], main_window=self.main_window)
            self.undo_stack.push(cmd)
            return
        
        # Если выделено несколько — спрашиваем подтверждение
        from app.utils.ui.dialog_manager import DialogManager
        reply = DialogManager.ask_confirmation(
            self.main_window,
            app_config.get('ui.delete_confirm_text', 'Вы уверены, что хотите удалить {count} ссылк(и/у)?').format(count=len(links)),
            app_config.get('ui.delete_confirm_title', 'Подтверждение удаления'),
            informative_text="Действие необратимо. Выбранные ссылки будут удалены из базы данных.",
            details=f"count={len(links)}",
        )

        if reply:
            with self.undo_stack.macro(MACRO_DELETE_LINKS_TEXT.format(count=len(links))):
                for link_to_delete in links:
                    cmd = DeleteLinkCommand(link_to_delete=link_to_delete, main_window=self.main_window)
                    self.undo_stack.push(cmd)
