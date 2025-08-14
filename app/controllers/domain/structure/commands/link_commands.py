# app/controllers/commands/link_commands.py

from .base import BaseCommand


class SaveLinkCommand(BaseCommand):
    """Команда для добавления или обновления ссылки."""
    def __init__(self, new_data, old_data, main_window, defer_ui_update=False):
        self.is_update = old_data is not None
        name = new_data.get('name', '(без имени)')
        desc = f"Редактирование '{name}'" if self.is_update else f"Добавление '{name}'"
        super().__init__(desc, main_window)

        self.new_data = new_data
        self.old_data = old_data
        self.defer_ui_update = defer_ui_update
        self.created_id = old_data.get('id') if self.is_update and isinstance(old_data, dict) else None

    def redo(self):
        """Выполняет или повторяет действие: сохраняет данные ссылки в БД."""
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            returned_id = self.db.links.upsert_link(self.new_data)
            logger.info(f"SaveLinkCommand.redo: upsert_link returned id={returned_id}")

            if not self.is_update and self.created_id is None:
                self.created_id = returned_id
                self.new_data['id'] = returned_id

            if not self.defer_ui_update:
                self._update_ui()
            # Бизнес-сигналы для унифицированного обновления UI
            try:
                if hasattr(self.main, 'structure_business') and self.main.structure_business:
                    business = self.main.structure_business
                    logger.info(f"[CMD:Link] Emitting to business id={id(business)} is_update={self.is_update}")
                    link_id = self.created_id or returned_id
                    if self.is_update:
                        business.item_updated.emit("link", link_id, self.new_data)
                    else:
                        business.item_added.emit("link", link_id, self.new_data)
                    # Обновление структуры может быть необходимо для плиток счетчиков/бейджей
                    # (вес незначительный, но повышает консистентность отображения)
                    business.load_structure()
            except Exception as e:
                logger.warning(f"SaveLinkCommand: не удалось инициировать бизнес-обновление: {e}")
                
            # Простое решение: фокус на ссылку после сохранения
            focus_id = self.created_id or returned_id
            logger.info(f"Focus check: focus_id={focus_id}")
            if focus_id:
                self._focus_on_new_link(focus_id)
                
        except Exception as e:
            logger.error(f"SaveLinkCommand.redo: exception during upsert: {e}")
            # Используем централизованный обработчик ошибок
            # Для дубликатов и других ожидаемых ошибок не выбрасываем исключение
            self.handle_db_error(e)
            # Просто возвращаемся без re-raise

    def undo(self):
        """Отменяет действие."""
        try:
            if self.is_update:
                self.db.links.upsert_link(self.old_data)
                self.category_id = self.old_data['category_id']
            else:
                self.db.links.delete_link(self.created_id)

            self.refresh_all_views(self.new_data['category_id'] if not self.is_update else self.old_data['category_id'])
            # Сигнализируем бизнес-слою для консистентного обновления UI
            try:
                if hasattr(self.main, 'structure_business') and self.main.structure_business:
                    business = self.main.structure_business
                    self.logger.info(f"[CMD:Link.undo] Emitting to business id={id(business)} is_update={self.is_update}")
                    if self.is_update:
                        business.item_updated.emit("link", self.old_data['id'], self.old_data)
                    else:
                        business.item_deleted.emit("link", self.created_id)
                    business.load_structure()
            except Exception as e:
                self.logger.warning(f"SaveLinkCommand.undo: не удалось инициировать бизнес-обновление: {e}")
        except Exception as e:
            logger.error(f"SaveLinkCommand.undo: exception during undo: {e}")
            # Используем централизованный обработчик ошибок для undo операций
            self.handle_db_error(e)
            # Не выбрасываем исключение, чтобы не прерывать работу приложения

    def force_ui_update(self):
        """Принудительно обновляет UI (используется в конце макроса)."""
        self.refresh_all_views(self.new_data['category_id'] if not self.is_update else self.old_data['category_id'])

    def _update_ui(self):
        """Обновляет UI после сохранения ссылки."""
        # Обновляем таблицу ссылок и избранное
        category_id = self.new_data.get('category_id') or (self.old_data.get('category_id') if self.old_data else None)
        if category_id:
            self.update_links_table(category_id)
            # Для новой ссылки также устанавливаем фокус на категорию в дереве
            if not self.is_update:
                self.restore_tree_selection('category', category_id)
        self.update_favorites()

    def _focus_on_new_link(self, link_id):
        """Устанавливает фокус на новую ссылку."""
        try:
            import logging

            from PyQt6.QtCore import QTimer
            logger = logging.getLogger(__name__)

            logger.info(f"Focusing on new link ID {link_id}")

            # Надёжная фокусировка с повторными попытками, чтобы дождаться,
            # когда таблица завершит перезаполнение после load_category()
            def try_focus(remaining: int, interval_ms: int = 120):
                links_table = getattr(self.main, 'table', None)
                if not links_table or not hasattr(links_table, 'focus_on_link_id'):
                    logger.warning("Links table or focus method not available")
                    return

                try:
                    success = links_table.focus_on_link_id(link_id)
                except Exception as e:
                    logger.warning(f"focus_on_link_id raised: {e}")
                    success = False

                if success:
                    logger.info(f"Focus set on link ID {link_id}")
                elif remaining > 0:
                    logger.debug(f"Link ID {link_id} not yet in table, retry in {interval_ms}ms (left={remaining})")
                    QTimer.singleShot(interval_ms, lambda: try_focus(remaining - 1, interval_ms))
                else:
                    logger.warning(f"Failed to focus link ID {link_id} after retries")

            # Первая попытка — чуть позже, чтобы дать UI обновиться
            QTimer.singleShot(120, lambda: try_focus(remaining=10))

        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Error focusing on new link: {e}")


class BatchSaveLinksCommand(BaseCommand):
    """Команда для пакетного сохранения множества ссылок."""
    def __init__(self, links_data, old_link_data, main_window):
        count = len(links_data)
        is_update = old_link_data is not None
        action_text = f"Редактирование ссылки" if is_update else f"Добавление {count} ссылок"
        super().__init__(action_text, main_window)
        
        self.links_data = links_data.copy()
        self.old_link_data = old_link_data
        self.created_ids = []
        self.category_id = links_data[0]['category_id'] if links_data else None
        self.is_update = is_update

    def redo(self):
        """Выполняет пакетное сохранение ссылок."""
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            logger.debug(f"BatchSaveLinksCommand.redo: processing {len(self.links_data)} links")
            self.created_ids.clear()
            
            for i, link_data in enumerate(self.links_data):
                logger.debug(f"BatchSaveLinksCommand.redo: processing link {i}: name={link_data.get('name')}, browser_key={link_data.get('browser_key')}")
                
                if link_data.get("_action") == "delete":
                    self.db.links.delete_link(link_data["id"])
                    # Бизнес-сигнал удаления
                    try:
                        if hasattr(self.main, 'structure_business') and self.main.structure_business:
                            self.main.structure_business.item_deleted.emit("link", link_data["id"])
                    except Exception as e:
                        logger.warning(f"BatchSaveLinksCommand: failed to emit item_deleted for link {link_data['id']}: {e}")
                    continue
                    
                returned_id = self.db.links.upsert_link(link_data)
                logger.debug(f"BatchSaveLinksCommand.redo: upsert_link returned ID {returned_id}")
                
                if not self.is_update:
                    self.created_ids.append(returned_id)
                    link_data['id'] = returned_id
                # Бизнес-сигналы добавления/обновления
                try:
                    if hasattr(self.main, 'structure_business') and self.main.structure_business:
                        if self.is_update:
                            self.main.structure_business.item_updated.emit("link", link_data['id'], link_data)
                        else:
                            self.main.structure_business.item_added.emit("link", returned_id, link_data)
                except Exception as e:
                    logger.warning(f"BatchSaveLinksCommand: failed to emit business signal for link: {e}")
            
            if self.category_id:
                self.refresh_all_views(self.category_id)
            try:
                if hasattr(self.main, 'structure_business') and self.main.structure_business:
                    self.logger.info(f"[CMD:BatchLinks] Emitting load_structure to business id={id(self.main.structure_business)}")
                    self.main.structure_business.load_structure()
            except Exception as e:
                logger.warning(f"BatchSaveLinksCommand: не удалось инициировать бизнес-обновление структуры: {e}")
        except Exception as e:
            # Используем централизованный обработчик ошибок
            # Для дубликатов и других ожидаемых ошибок не выбрасываем исключение
            self.handle_db_error(e)
            # Просто возвращаемся без re-raise

    def undo(self):
        """Отменяет пакетное сохранение."""
        if self.is_update:
            if self.old_link_data:
                self.db.links.upsert_link(self.old_link_data)
        else:
            for created_id in self.created_ids:
                if created_id:
                    self.db.links.delete_link(created_id)
        
        if self.category_id:
            self.refresh_all_views(self.category_id)
            # Для новых ссылок также устанавливаем фокус на категорию в дереве
            if not self.is_update:
                self.restore_tree_selection('category', self.category_id)


class DeleteLinkCommand(BaseCommand):
    """Команда для удаления ссылки."""
    def __init__(self, link_to_delete, main_window):
        super().__init__(f"Удаление '{link_to_delete['name']}'", main_window)
        self.deleted_link_data = link_to_delete
        self.link_id = link_to_delete['id']

    def redo(self):
        """Выполняет действие: удаляет ссылку."""
        try:
            self.db.links.delete_link(self.link_id)
            self.refresh_all_views(self.deleted_link_data['category_id'])
            try:
                if hasattr(self.main, 'structure_business') and self.main.structure_business:
                    business = self.main.structure_business
                    self.logger.info(f"[CMD:DeleteLink] Emitting to business id={id(business)}")
                    business.item_deleted.emit("link", self.link_id)
                    business.load_structure()
            except Exception as e:
                self.logger.warning(f"DeleteLinkCommand.redo: не удалось инициировать бизнес-обновление структуры: {e}")
        except Exception as e:
            # Используем централизованный обработчик ошибок
            if not self.handle_db_error(e):
                raise

    def undo(self):
        """Отменяет действие: восстанавливает ссылку."""
        try:
            self.db.links.upsert_link(self.deleted_link_data)
            self.refresh_all_views(self.deleted_link_data['category_id'])
            try:
                if hasattr(self.main, 'structure_business') and self.main.structure_business:
                    business = self.main.structure_business
                    self.logger.info(f"[CMD:DeleteLink.undo] Emitting to business id={id(business)}")
                    business.item_added.emit("link", self.deleted_link_data['id'], self.deleted_link_data)
                    business.load_structure()
            except Exception as e:
                self.logger.warning(f"DeleteLinkCommand.undo: не удалось инициировать бизнес-обновление структуры: {e}")
        except Exception as e:
            # Используем централизованный обработчик ошибок
            if not self.handle_db_error(e):
                raise