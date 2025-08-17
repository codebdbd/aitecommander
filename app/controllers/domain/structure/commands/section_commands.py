# app/controllers/commands/section_commands.py

from .base import BaseCommand


class SaveSectionCommand(BaseCommand):
    """Команда для сохранения (добавления/редактирования) раздела."""
    def __init__(self, data, main_window, old_data=None):
        self.is_new = 'id' not in data or data['id'] is None
        title = "Добавление раздела" if self.is_new else f"Редактирование раздела '{data['name']}'"
        super().__init__(title, main_window)
        self.new_data = data
        self.old_data = old_data
        self.new_id = None if self.is_new else data['id']

    def redo(self):
        try:
            # Предчек дубликатов имен в пределах сферы для улучшения UX
            name = (self.new_data.get('name') or '').strip()
            sphere_id = self.new_data.get('sphere_id')
            if name and sphere_id:
                try:
                    existing = self.db.sections.get_sections(sphere_id) or []
                    def is_dup(row):
                        same_name = str(row['name']).strip().lower() == name.lower()
                        same_scope = int(row['sphere_id']) == int(sphere_id)
                        if self.is_new:
                            return same_name and same_scope
                        # при редактировании исключаем сам элемент
                        return same_name and same_scope and int(row['id']) != int(self.new_id)
                    if any(is_dup(row) for row in existing):
                        self.show_error(
                            f"Раздел с именем '{name}' уже существует в выбранной сфере.",
                            "Ошибка добавления раздела"
                        )
                        # Не бросаем исключение, помечаем команду устаревшей
                        self.setObsolete(True)
                        return
                except Exception as e:
                    # Предчек не должен ломать выполнение — просто логируем и продолжаем
                    self.logger.warning(f"Не удалось выполнить предчек дубликатов раздела: {e}")

            if self.is_new:
                if self.new_id is None:
                    self.new_id = self.db.sections.upsert_section(self.new_data)
                    self.new_data['id'] = self.new_id
                else:
                    self.db.sections.upsert_section(self.new_data)
            else:
                self.db.sections.upsert_section(self.new_data)
            self.update_structure_tree(item_to_select=('section', self.new_id))
            # Эмитим бизнес-сигналы и инициируем асинхронную перезагрузку структуры,
            # чтобы UI гарантированно обновился через единый канал сигналов
            try:
                if hasattr(self.main, 'structure_business') and self.main.structure_business:
                    business = self.main.structure_business
                    self.logger.info(f"[CMD:Section] Emitting to business id={id(business)} is_new={self.is_new}")
                    if self.is_new:
                        business.item_added.emit("section", self.new_id, self.new_data)
                    else:
                        business.item_updated.emit("section", self.new_id, self.new_data)
                    # Если при редактировании изменилась сфера — инвалидируем кэш старой сферы
                    # и переключаемся на новую, чтобы раздел появился сразу
                    try:
                        if not self.is_new and self.old_data:
                            old_sphere_id = self.old_data.get('sphere_id')
                            new_sphere_id = self.new_data.get('sphere_id')
                            if old_sphere_id and new_sphere_id and int(old_sphere_id) != int(new_sphere_id):
                                # Инвалидируем кэш старой сферы (структура/разделы/first_category)
                                cm = getattr(business, 'cache_manager', None)
                                if cm:
                                    cm.invalidate(f"structure_{old_sphere_id}")
                                    cm.invalidate(f"sections_{old_sphere_id}")
                                    cm.invalidate(f"first_category_{old_sphere_id}")
                                # Переключаем текущую сферу на новую и загружаем её структуру
                                business.set_current_sphere(int(new_sphere_id))
                                business.load_structure()
                            else:
                                # Обычное обновление в рамках той же сферы
                                business.load_structure()
                        else:
                            # Новое добавление — обновляем текущую сферу
                            business.load_structure()
                    except Exception as e:
                        self.logger.warning(f"SaveSectionCommand: post-update sphere handling failed: {e}")
            except Exception as e:
                # Логируем, но не прерываем UX
                self.logger.warning(f"SaveSectionCommand: не удалось инициировать бизнес-обновление структуры: {e}")
        except Exception as e:
            # Используем централизованный обработчик ошибок
            # Для дубликатов и других ожидаемых ошибок не выбрасываем исключение
            self.handle_db_error(e)
            # Не выбрасываем исключение обратно, просто помечаем команду устаревшей
            self.setObsolete(True)

    def undo(self):
        if self.is_new:
            self.db.sections.delete_section(self.new_id)
            self.update_structure_tree()
            try:
                if hasattr(self.main, 'structure_business') and self.main.structure_business:
                    business = self.main.structure_business
                    self.logger.info(f"[CMD:Section.undo-del] Emitting to business id={id(business)}")
                    business.item_deleted.emit("section", self.new_id)
                    business.load_structure()
            except Exception as e:
                self.logger.warning(f"SaveSectionCommand.undo: не удалось инициировать бизнес-обновление после удаления: {e}")
        else:
            self.db.sections.upsert_section(self.old_data)
            self.update_structure_tree(item_to_select=('section', self.old_data['id']))
            try:
                if hasattr(self.main, 'structure_business') and self.main.structure_business:
                    business = self.main.structure_business
                    self.logger.info(f"[CMD:Section.undo-restore] Emitting to business id={id(business)}")
                    business.item_updated.emit("section", self.old_data['id'], self.old_data)
                    business.load_structure()
            except Exception as e:
                self.logger.warning(f"SaveSectionCommand.undo: не удалось инициировать бизнес-обновление после восстановления: {e}")


class DeleteSectionCommand(BaseCommand):
    """Команда для удаления раздела."""
    def __init__(self, section_data, main_window):
        super().__init__(f"Удаление раздела '{section_data['name']}'", main_window)
        self.section_data = section_data
        # Сохраняем полное дерево раздела для восстановления (раздел + категории + ссылки)
        self._backup_tree = self.db.export_section_tree(section_data['id'])

    def redo(self):
        self.db.sections.delete_section(self.section_data['id'])
        self.update_structure_tree()
        self.main.structure.switch_sphere(self.main.structure_business.current_sphere_id)
        try:
            if hasattr(self.main, 'structure_business') and self.main.structure_business:
                business = self.main.structure_business
                business.item_deleted.emit("section", self.section_data['id'])
                business.load_structure()
        except Exception as e:
            self.logger.warning(f"DeleteSectionCommand.redo: не удалось инициировать бизнес-обновление после удаления: {e}")

    def undo(self):
        # Восстанавливаем полное дерево раздела (раздел + категории + ссылки)
        try:
            self.db.import_section_tree(self._backup_tree)
            section_name = self._backup_tree['section']['name']
            section_id = self._backup_tree['section']['id']
            self.logger.info(f"Восстановлено полное дерево раздела с ID {section_id}: {section_name}")
            self.update_structure_tree(item_to_select=('section', section_id))
            try:
                if hasattr(self.main, 'structure_business') and self.main.structure_business:
                    business = self.main.structure_business
                    business.item_added.emit("section", section_id, self._backup_tree['section'])
                    business.load_structure()
            except Exception as e:
                self.logger.warning(f"DeleteSectionCommand.undo: не удалось инициировать бизнес-обновление после восстановления: {e}")
        except Exception as e:
            section_name = self._backup_tree.get('section', {}).get('name', 'неизвестный')
            self.logger.error(f"Ошибка восстановления дерева раздела: {e}")
            self.show_error(
                f"Не удалось восстановить раздел '{section_name}' с категориями и ссылками.\n"
                f"Ошибка: {str(e)}",
                "Ошибка восстановления"
            )