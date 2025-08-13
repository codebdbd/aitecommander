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
            if self.is_new:
                if self.new_id is None:
                    self.new_id = self.db.sections.upsert_section(self.new_data)
                    self.new_data['id'] = self.new_id
                else:
                    self.db.sections.upsert_section(self.new_data)
            else:
                self.db.sections.upsert_section(self.new_data)
            self.update_structure_tree(item_to_select=('section', self.new_id))
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
        else:
            self.db.sections.upsert_section(self.old_data)
            self.update_structure_tree(item_to_select=('section', self.old_data['id']))


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

    def undo(self):
        # Восстанавливаем полное дерево раздела (раздел + категории + ссылки)
        try:
            self.db.import_section_tree(self._backup_tree)
            section_name = self._backup_tree['section']['name']
            section_id = self._backup_tree['section']['id']
            self.logger.info(f"Восстановлено полное дерево раздела с ID {section_id}: {section_name}")
            self.update_structure_tree(item_to_select=('section', section_id))
        except Exception as e:
            section_name = self._backup_tree.get('section', {}).get('name', 'неизвестный')
            self.logger.error(f"Ошибка восстановления дерева раздела: {e}")
            self.show_error(
                f"Не удалось восстановить раздел '{section_name}' с категориями и ссылками.\n"
                f"Ошибка: {str(e)}",
                "Ошибка восстановления"
            )