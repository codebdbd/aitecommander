# app/controllers/commands/category_commands.py

from .base import BaseCommand


class SaveCategoryCommand(BaseCommand):
    """Команда для сохранения (добавления/редактирования) категории."""
    def __init__(self, data, main_window, old_data=None, skip_reload=False):
        self.is_new = 'id' not in data or data['id'] is None
        # Безопасно формируем заголовок (на случай частичных данных из диалога)
        safe_name = None
        if not self.is_new:
            safe_name = (data.get('name') if isinstance(data, dict) else None) or ((old_data or {}).get('name'))
        title = "Добавление категории" if self.is_new else f"Редактирование категории '{safe_name or ''}'"
        super().__init__(title, main_window)
        self.new_data = data
        self.old_data = old_data
        self.new_id = None if self.is_new else data.get('id')
        self.skip_reload = skip_reload
        # Для редактирования готовим слитые данные, чтобы не потерять обязательные поля
        self._merged_update = None
        if not self.is_new and isinstance(self.old_data, dict):
            merged = dict(self.old_data)
            if isinstance(self.new_data, dict):
                merged.update(self.new_data)
            self._merged_update = merged

    def redo(self):
        try:
            if self.is_new:
                if self.new_id is None:
                    self.new_id = self.db.categories.upsert_category(self.new_data)
                    self.new_data['id'] = self.new_id
                else:
                    self.db.categories.upsert_category(self.new_data)
            else:
                payload = self._merged_update or self.new_data
                # гарантируем id в полезной нагрузке
                if isinstance(payload, dict) and payload.get('id') is None:
                    payload['id'] = self.new_id
                # Валидация обязательных полей
                name = payload.get('name') if isinstance(payload, dict) else None
                section_id = payload.get('section_id') if isinstance(payload, dict) else None
                if not name or section_id is None:
                    self.show_info(
                        "Некорректные данные",
                        "Не указаны обязательные поля категории: имя или раздел.")
                    self.setObsolete(True)
                    return
                # Проверка дубликатов в рамках раздела (исключая текущую категорию)
                try:
                    if self.db.categories.has_duplicate_category(section_id, name, exclude_id=payload.get('id')):
                        self.show_info(
                            "Дубликат категории",
                            f"Категория с именем '{name}' уже существует в этом разделе.")
                        self.setObsolete(True)
                        return
                except Exception as e:
                    # На случай ошибки в проверке дубликатов — не падаем, а логируем и продолжаем с апдейтом
                    self.logger.warning(f"SaveCategoryCommand.duplicate-check failed: {e}")
                self.db.categories.upsert_category(payload)
            
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
            # Синхронизация через бизнес-сигналы + асинхронная перезагрузка структуры
            try:
                if hasattr(self.main, 'structure_business') and self.main.structure_business:
                    business = self.main.structure_business
                    self.logger.info(f"[CMD:Category] Emitting to business id={id(business)} is_new={self.is_new}")
                    if self.is_new:
                        # ВАЖНО: вторым параметром (parent_id) должен быть section_id,
                        # чтобы бизнес-логика корректно инвалидировала кэш категорий и перезагрузила их.
                        parent_section_id = None
                        try:
                            parent_section_id = self.new_data.get('section_id') if isinstance(self.new_data, dict) else None
                        except Exception:
                            parent_section_id = None
                        business.item_added.emit("category", parent_section_id, self.new_data)
                    else:
                        business.item_updated.emit("category", self.new_id, (self._merged_update or self.new_data))
                    business.load_structure()
            except Exception as e:
                self.logger.warning(f"SaveCategoryCommand: не удалось инициировать бизнес-обновление структуры: {e}")
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
            try:
                if hasattr(self.main, 'structure_business') and self.main.structure_business:
                    business = self.main.structure_business
                    self.logger.info(f"[CMD:Category.undo-del] Emitting to business id={id(business)}")
                    business.item_deleted.emit("category", self.new_id)
                    business.load_structure()
            except Exception as e:
                self.logger.warning(f"SaveCategoryCommand.undo: не удалось инициировать бизнес-обновление после удаления: {e}")
        else:
            self.db.categories.upsert_category(self.old_data)
            if not self.skip_reload:
                self.update_structure_tree(item_to_select=('category', self.old_data['id']))
            else:
                if hasattr(self.structure, '_update_category_display'):
                    self.structure._update_category_display(self.old_data['id'], self.old_data)
            try:
                if hasattr(self.main, 'structure_business') and self.main.structure_business:
                    business = self.main.structure_business
                    self.logger.info(f"[CMD:Category.undo-restore] Emitting to business id={id(business)}")
                    business.item_updated.emit("category", self.old_data['id'], self.old_data)
                    business.load_structure()
            except Exception as e:
                self.logger.warning(f"SaveCategoryCommand.undo: не удалось инициировать бизнес-обновление после восстановления: {e}")


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
        
        # ВАЖНО: Инвалидируем кэш категорий соответствующего раздела ДО переключений UI
        try:
            section_id = self.category_data.get('section_id')
            if hasattr(self.main, 'structure_business') and self.main.structure_business and isinstance(section_id, int):
                # Прямо инвалидируем кэш, чтобы последующий select_section загрузил свежие категории
                self.main.structure_business._invalidate_categories_cache(section_id)
        except Exception:
            # Не критично, продолжим стандартным путём
            pass

        # Отправляем сигнал об удалении для правильной обработки фокуса
        # (TreeManagement автоматически выберет родительский раздел)
        if hasattr(self.main, 'structure_business') and self.main.structure_business:
            self.main.structure_business.item_deleted.emit("category", self.category_data['id'])
            try:
                self.main.structure_business.load_structure()
            except Exception as e:
                self.logger.warning(f"DeleteCategoryCommand.redo: не удалось инициировать бизнес-обновление структуры: {e}")

    def undo(self):
        # Восстанавливаем полное дерево категории
        self.db.import_category_tree(self._backup_tree)
        # Обновляем таблицу ссылок для восстановленной категории
        self.update_links_table(self.category_data['id'])
        self.update_structure_tree(item_to_select=('category', self.category_data['id']))
        try:
            if hasattr(self.main, 'structure_business') and self.main.structure_business:
                business = self.main.structure_business
                # ВАЖНО: передаём parent_id = section_id восстановленной категории
                restored_category = self._backup_tree.get('category') if isinstance(self._backup_tree, dict) else None
                try:
                    parent_section_id = restored_category.get('section_id') if isinstance(restored_category, dict) else None
                except Exception:
                    parent_section_id = None
                business.item_added.emit("category", parent_section_id, restored_category)
                business.load_structure()
        except Exception as e:
            self.logger.warning(f"DeleteCategoryCommand.undo: не удалось инициировать бизнес-обновление структуры: {e}")