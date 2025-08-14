# app/controllers/commands/category_commands.py

from .base import BaseCommand


class SaveCategoryCommand(BaseCommand):
    """Команда для сохранения (добавления/редактирования) категории."""
    def __init__(self, data, main_window, old_data=None, skip_reload=False):
        self.is_new = 'id' not in data or data['id'] is None
        title = "Добавление категории" if self.is_new else f"Редактирование категории '{data['name']}'"
        super().__init__(title, main_window)
        self.new_data = data
        self.old_data = old_data
        self.new_id = None if self.is_new else data['id']
        self.skip_reload = skip_reload

    def redo(self):
        try:
            if self.is_new:
                if self.new_id is None:
                    self.new_id = self.db.categories.upsert_category(self.new_data)
                    self.new_data['id'] = self.new_id
                else:
                    self.db.categories.upsert_category(self.new_data)
            else:
                self.db.categories.upsert_category(self.new_data)
            
            if not self.skip_reload:
                self.update_structure_tree(item_to_select=('category', self.new_id))
                # Для новой категории переключаем на таблицу ссылок с задержкой (после установки фокуса)
                if self.is_new:
                    from app.utils.system.task_scheduler import TaskType as TimerType
                    from app.utils.system.task_scheduler import schedule_operation
                    schedule_operation(
                        lambda: self.update_links_table(self.new_id),
                        TimerType.TABLE_UPDATE,
                        operation_id=f"update_links_table_{self.new_id}"
                    )
        except ValueError as e:
            self.show_info("Информация", str(e))
            self.setObsolete(True)
        except Exception as e:
            # Используем централизованный обработчик ошибок
            # Для дубликатов и других ожидаемых ошибок не выбрасываем исключение
            self.handle_db_error(e)
            # Не выбрасываем исключение обратно, просто помечаем команду устаревшей
            self.setObsolete(True)

    def undo(self):
        if self.is_new:
            section_id = self.new_data['section_id']
            self.db.categories.delete_category(self.new_id)
            if not self.skip_reload:
                self.update_structure_tree(item_to_select=('section', section_id))
        else:
            self.db.categories.upsert_category(self.old_data)
            if not self.skip_reload:
                self.update_structure_tree(item_to_select=('category', self.old_data['id']))
            else:
                if hasattr(self.structure, '_update_category_display'):
                    self.structure._update_category_display(self.old_data['id'], self.old_data)


class DeleteCategoryCommand(BaseCommand):
    """Команда для удаления категории."""
    def __init__(self, category_data, main_window):
        super().__init__(f"Удаление категории '{category_data['name']}'", main_window)
        self.category_data = category_data
        # Сохраняем полное дерево категории для undo
        self._backup_tree = self.db.export_category_tree(category_data['id'])

    def redo(self):
        # Удаляем категорию из базы данных
        self.db.categories.delete_category(self.category_data['id'])
        
        # Отправляем сигнал об удалении для правильной обработки фокуса
        # (TreeManagement автоматически выберет родительский раздел)
        if hasattr(self.main, 'structure_business') and self.main.structure_business:
            self.main.structure_business.item_deleted.emit("category", self.category_data['id'])

    def undo(self):
        # Восстанавливаем полное дерево категории
        self.db.import_category_tree(self._backup_tree)
        # Обновляем таблицу ссылок для восстановленной категории
        self.update_links_table(self.category_data['id'])
        self.update_structure_tree(item_to_select=('category', self.category_data['id']))