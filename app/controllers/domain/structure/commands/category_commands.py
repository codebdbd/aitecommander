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
                        # Молча переключаем фокус на уже существующую категорию и выходим
                        try:
                            existing_id = None
                            try:
                                rows = self.db.categories.get_categories(section_id) or []
                                # rows могут быть sqlite Row, приводим к dict при необходимости
                                for r in rows:
                                    d = dict(r) if hasattr(r, 'keys') else r
                                    if str(d.get('name', '')).strip().lower() == str(name).strip().lower():
                                        existing_id = d.get('id') if isinstance(d, dict) else getattr(d, 'id', None)
                                        break
                            except Exception:
                                existing_id = None
                            if existing_id:
                                self.update_structure_tree(item_to_select=('category', existing_id))
                            else:
                                self.update_structure_tree(item_to_select=('section', section_id))
                        except Exception as _e:
                            self.logger.debug(f"SaveCategoryCommand: silent focus on duplicate failed: {_e}")
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
                        business.item_added.emit("category", self.new_id, self.new_data)
                    else:
                        business.item_updated.emit("category", self.new_id, (self._merged_update or self.new_data))
                    business.load_structure()
            except Exception as e:
                self.logger.warning(f"SaveCategoryCommand: не удалось инициировать бизнес-обновление структуры: {e}")
        except ValueError as e:
            # Считаем это, вероятно, дубликатом при добавлении. Молча фокусируемся на существующей категории/разделе.
            try:
                section_id = None
                name = None
                try:
                    # Пытаемся извлечь из new_data
                    if isinstance(self.new_data, dict):
                        section_id = self.new_data.get('section_id')
                        name = self.new_data.get('name')
                except Exception:
                    pass
                existing_id = None
                if section_id and name:
                    try:
                        rows = self.db.categories.get_categories(section_id) or []
                        for r in rows:
                            d = dict(r) if hasattr(r, 'keys') else r
                            if str(d.get('name', '')).strip().lower() == str(name).strip().lower():
                                existing_id = d.get('id') if isinstance(d, dict) else getattr(d, 'id', None)
                                break
                    except Exception:
                        existing_id = None
                if existing_id:
                    self.update_structure_tree(item_to_select=('category', existing_id))
                elif section_id:
                    self.update_structure_tree(item_to_select=('section', section_id))
            except Exception as _e:
                self.logger.debug(f"SaveCategoryCommand: silent focus after ValueError failed: {_e}")
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
        
        # Выбираем следующий элемент фокуса: категорию выше, иначе родительский раздел
        try:
            section_id = self.category_data.get('section_id')
            categories = self.db.categories.get_categories(section_id) if section_id is not None else []
            # Приводим к удобному виду и сортируем по position (если есть)
            def _to_dict(row):
                return dict(row) if hasattr(row, 'keys') else row
            cats = [_to_dict(r) for r in (categories or [])]

            next_selection = ('section', section_id)
            if cats:
                # Пытаемся найти предыдущую относительно удаленной позицию
                del_pos = None
                try:
                    del_pos = self.category_data.get('position')
                except Exception:
                    del_pos = None

                if any('position' in c for c in cats):
                    cats_sorted = sorted(cats, key=lambda c: c.get('position', 0))
                    prev_candidates = [c for c in cats_sorted if del_pos is not None and c.get('position') is not None and c.get('position') < del_pos]
                    if prev_candidates:
                        next_selection = ('category', prev_candidates[-1].get('id'))
                    else:
                        # Если не нашли предыдущую по позиции — берем последнюю в списке (визуально "выше")
                        next_selection = ('category', cats_sorted[-1].get('id'))
                else:
                    # Нет позиции — выбираем последнюю категорию как ближайшую "выше"
                    last_cat = cats[-1]
                    next_selection = ('category', (last_cat.get('id') if isinstance(last_cat, dict) else last_cat.id))

            # Меняем выделение в дереве до эмиссии сигналов
            self.update_structure_tree(item_to_select=next_selection)
        except Exception as e:
            # На всякий случай: если что-то пошло не так — пусть UI выберет раздел по умолчанию
            self.logger.warning(f"DeleteCategoryCommand: не удалось навести фокус после удаления: {e}")
            try:
                section_id = self.category_data.get('section_id')
                if section_id is not None:
                    self.update_structure_tree(item_to_select=('section', section_id))
            except Exception:
                pass

        # Отправляем сигнал об удалении и инициируем перезагрузку структуры
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
                business.item_added.emit("category", self.category_data['id'], self._backup_tree['category'])
                business.load_structure()
        except Exception as e:
            self.logger.warning(f"DeleteCategoryCommand.undo: не удалось инициировать бизнес-обновление структуры: {e}")