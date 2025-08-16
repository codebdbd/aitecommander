"""
Централизованные Undo/Redo команды для drag-and-drop ссылок и категорий.
"""
import logging
from typing import List, Dict, Optional

from app.utils.system.undo.base import BaseCommand


def get_value(row, key, default=None):
    try:
        return row[key]
    except (KeyError, IndexError, TypeError):
        return default


class MoveLinksCommand(BaseCommand):
    """Перемещение одной или нескольких ссылок в другую категорию с корректным undo/redo."""
    def __init__(self, link_ids, new_category_id, main_window):
        super().__init__(f"Перемещение {len(link_ids)} ссылок", main_window)
        self.link_ids = link_ids
        self.new_category_id = new_category_id
        self._old_states = []  # состояние до перемещения
        self._new_states = []  # состояние после перемещения
        self.old_category_id = None
        self._prepared = False  # флаг подготовки данных
        
    def _prepare_data(self):
        """Подготавливает данные для операции (вызывается в redo)."""
        if self._prepared:
            return
            
        # Получаем исходные данные через бизнес-логику
        links_business = self.main.links_business
        for lid in self.link_ids:
            link_data = links_business.get_link_by_id(lid)
            if link_data is None:
                raise ValueError(f"Link with id {lid} not found")
            self._old_states.append(link_data)
            
        self.old_category_id = self._old_states[0]["category_id"] if self._old_states else None
        
        # Получаем следующую позицию через бизнес-логику
        start_pos = links_business.get_next_position(self.new_category_id)
        
        # Получаем существующие ссылки для проверки дубликатов
        existing_links = links_business.get_links_for_category(self.new_category_id)
        
        # Подготавливаем новые состояния
        temp_new_states = []
        for offset, st in enumerate(self._old_states):
            ns = st.copy()
            ns["category_id"] = self.new_category_id
            ns["position"] = start_pos + offset
            # Проверка на дубликат
            if not self._is_duplicate(ns, existing_links):
                temp_new_states.append(ns)
                existing_links.append(ns)  # Предотвращаем дубли при множественном копировании
                
        self._new_states = temp_new_states
        self._prepared = True
        
    def _is_duplicate(self, candidate, links):
        """Проверяет, является ли ссылка дубликатом."""
        for link in links:
            if (
                get_value(link, 'url', '') == get_value(candidate, 'url', '') and
                get_value(link, 'type', '') == get_value(candidate, 'type', '') and
                get_value(link, 'args', '') == get_value(candidate, 'args', '')
            ):
                return True
        return False

    def _execute_batch_operation(self, states):
        """Выполняет пакетную операцию с ссылками через бизнес-логику."""
        if not states:
            return
            
        links_business = self.main.links_business
        try:
            # Используем транзакционную пакетную операцию
            links_business.batch_update_links(states)
        except Exception as e:
            logging.error(f"Ошибка при пакетном обновлении ссылок: {e}")
            raise

    def _refresh_ui(self, old_category=None, new_category=None):
        """Обновляет UI после операции."""
        # Обновляем обе категории, если они разные
        categories_to_update = set()
        if old_category:
            categories_to_update.add(old_category)
        if new_category:
            categories_to_update.add(new_category)
            
        for category_id in categories_to_update:
            if hasattr(self.main, 'ui_state') and self.main.ui_state:
                self.main.ui_state.update_category_without_stack_switch(category_id)
            else:
                # ЦЕНТРАЛИЗОВАНО: Fallback убран - UIStateManager должен быть всегда доступен
                self.logger.error("UIStateManager not available in MoveLinkCommand")
        
        # Переключаем фокус на целевую категорию после перемещения
        if new_category and hasattr(self.main, 'structure_business') and self.main.structure_business:
            try:
                self.main.structure_business.select_category(new_category)
                logging.info(f"Переключен фокус на целевую категорию {new_category} после перемещения ссылок")
            except Exception as e:
                logging.warning(f"Не удалось переключить фокус на категорию {new_category}: {e}")

    def redo(self):
        """Выполнение перемещения ссылок."""
        self._prepare_data()  # Подготавливаем данные при первом выполнении
        self._execute_batch_operation(self._new_states)
        self._refresh_ui(old_category=self.old_category_id, new_category=self.new_category_id)

    def undo(self):
        """Отмена перемещения ссылок."""
        self._execute_batch_operation(self._old_states)
        # При undo меняем местами категории - фокус должен вернуться на исходную
        self._refresh_ui(old_category=self.new_category_id, new_category=self.old_category_id)


class MoveCategoryCommand(BaseCommand):
    """Перемещение категории между разделами."""
    def __init__(self, category_id, new_section_id, main_window):
        super().__init__("Перемещение категории", main_window)
        self.category_id = category_id
        self.new_section_id = new_section_id
        self.old_section_id = None
        self.cat_name = None
        self._prepared = False
        
    def _prepare_data(self):
        """Подготавливает данные для операции."""
        if self._prepared:
            return
            
        # Получаем данные категории через бизнес-логику
        structure_business = self.main.structure_business
        category_data = structure_business.get_category_data(self.category_id)
        if category_data is None:
            raise ValueError(f"Category {self.category_id} not found")
            
        self.old_section_id = category_data["section_id"]
        self.cat_name = category_data["name"]
        self._prepared = True

    def _set_section(self, section_id):
        """Устанавливает раздел для категории через бизнес-логику."""
        structure_business = self.main.structure_business
        # Получаем полные данные категории для обновления
        current_category = structure_business.get_category_data(self.category_id)
        if current_category is None:
            raise ValueError(f"Category {self.category_id} not found")
        
        # Обновляем только section_id, сохраняя остальные данные
        category_data = {
            "name": current_category["name"],
            "section_id": section_id,
            "icon_path": current_category.get("icon_path", ""),
            "position": current_category.get("position", 0)
        }
        structure_business.update_category(self.category_id, category_data)

    def redo(self):
        try:
            self._prepare_data()
            
            if self.old_section_id == self.new_section_id:
                return
                
            # Проверяем дубликаты через бизнес-логику
            structure_business = self.main.structure_business
            if structure_business.has_duplicate_category(self.new_section_id, self.cat_name, self.category_id):
                # Молча игнорируем дубликаты - не показываем ошибку пользователю
                logging.debug(f"Duplicate category '{self.cat_name}' found in target section {self.new_section_id}, ignoring move")
                self.setObsolete(True)
                return
                
            self._set_section(self.new_section_id)
            self._refresh_structure_ui()
        except Exception as e:
            logging.error(f"Ошибка при перемещении категории: {e}")
            raise

    def undo(self):
        try:
            self._set_section(self.old_section_id)
            self._refresh_structure_ui()
        except Exception as e:
            logging.error(f"Ошибка при отмене перемещения категории: {e}")
            raise
            
    def _refresh_structure_ui(self):
        """Обновляет UI структуры после операции."""
        if hasattr(self.main, 'structure') and self.main.structure:
            self.main.structure.load()  # Перезагружаем структуру
            
        # Переключаем фокус на перемещенную категорию
        if hasattr(self.main, 'structure_business') and self.main.structure_business:
            try:
                self.main.structure_business.select_category(self.category_id)
                logging.info(f"Переключен фокус на перемещенную категорию {self.category_id}")
            except Exception as e:
                logging.warning(f"Не удалось переключить фокус на категорию {self.category_id}: {e}")


class AddLinksCommand(BaseCommand):
    """Добавление набора ссылок в категорию с поддержкой undo/redo."""
    def __init__(self, links_payload: List[Dict], category_id: int, main_window):
        super().__init__(f"Добавление {len(links_payload)} ссылок", main_window)
        self.category_id = category_id
        self._payload = links_payload or []
        self._prepared = False
        self._new_items: List[Dict] = []    # то, что реально вставим (без дублей)
        self._created_ids: List[int] = []   # id, созданные при redo

    def _prepare_data(self):
        if self._prepared:
            return
        links_business = self.main.links_business
        # Существующие ссылки в категории для простой дедупликации по (url, type)
        existing = links_business.get_links_for_category(self.category_id) or []
        existing_keys = {(str(get_value(x, 'url', '')), str(get_value(x, 'type', '')))
                         for x in existing}

        # Фильтруем входные данные, оставляя только валидные и не дубли
        filtered: List[Dict] = []
        for item in self._payload:
            try:
                url = str(get_value(item, 'url', '')).strip()
                typ = str(get_value(item, 'type', '')).strip() or 'web'
                name = str(get_value(item, 'name', '')).strip() or url
                if not url:
                    continue
                key = (url, typ)
                if key in existing_keys:
                    continue
                filtered.append({
                    'name': name,
                    'url': url,
                    'type': typ,
                    'category_id': int(self.category_id),
                })
                existing_keys.add(key)
            except Exception:
                continue

        if not filtered:
            self._prepared = True
            self._new_items = []
            return

        # Присваиваем позиции последовательно
        start_pos = links_business.get_next_position(self.category_id)
        for i, it in enumerate(filtered):
            it['position'] = int(start_pos) + i

        self._new_items = filtered
        self._prepared = True

    def _refresh_ui(self):
        # По аналогии с MoveLinksCommand: обновляем UI и ставим фокус на категорию
        if hasattr(self.main, 'ui_state') and self.main.ui_state:
            try:
                self.main.ui_state.update_category_without_stack_switch(self.category_id)
            except Exception as e:
                logging.warning(f"UIStateManager update failed: {e}")
        else:
            logging.error("UIStateManager not available in AddLinksCommand")

        if hasattr(self.main, 'structure_business') and self.main.structure_business:
            try:
                self.main.structure_business.select_category(self.category_id)
            except Exception as e:
                logging.warning(f"Не удалось переключить фокус на категорию {self.category_id}: {e}")

    def redo(self):
        self._prepare_data()
        if not self._new_items:
            # Нечего вставлять (все дубли/пусто) — помечаем как устаревшую команду
            try:
                self.setObsolete(True)
            except Exception:
                pass
            return

        links_business = self.main.links_business
        self._created_ids = []
        # Вставляем по одной, чтобы гарантированно получить ID и триггерить link_updated
        for item in self._new_items:
            try:
                new_id = links_business.save_link(item)
                if new_id:
                    self._created_ids.append(int(new_id))
                elif 'id' in item and isinstance(item['id'], int):
                    self._created_ids.append(int(item['id']))
            except Exception as e:
                logging.error(
                    "Ошибка добавления ссылки '%s': %s",
                    item.get('url', ''),
                    str(e)
                )

        self._refresh_ui()

    def undo(self):
        if not self._created_ids:
            return
        links_business = self.main.links_business
        for lid in self._created_ids:
            try:
                links_business.delete_link(lid)
            except Exception as e:
                logging.error(f"Ошибка удаления ссылки {lid} при undo: {e}")
        self._refresh_ui()
