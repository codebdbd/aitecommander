"""
Централизованные Undo/Redo команды для drag-and-drop ссылок и категорий.
"""

import logging

from app.controllers.ui.undo.base import BaseCommand
from app.utils.common import get_value

logger = logging.getLogger(__name__)

# get_value импортируется из app.utils.common


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

        self.old_category_id = (
            self._old_states[0]["category_id"] if self._old_states else None
        )

        # Получаем следующую позицию через бизнес-логику
        start_pos = links_business.get_next_position(self.new_category_id)

        # Получаем существующие ссылки для проверки дубликатов
        existing_links = links_business.get_links(self.new_category_id)

        # Подготавливаем новые состояния
        temp_new_states = []
        for offset, st in enumerate(self._old_states):
            ns = st.copy()
            ns["category_id"] = self.new_category_id
            ns["position"] = start_pos + offset
            # Проверка на дубликат
            if not self._is_duplicate(ns, existing_links):
                temp_new_states.append(ns)
                existing_links.append(
                    ns
                )  # Предотвращаем дубли при множественном копировании

        self._new_states = temp_new_states
        self._prepared = True

    def _is_duplicate(self, candidate, links):
        """Проверяет, является ли ссылка дубликатом."""
        for link in links:
            # Дубликат по требованию пользователя: совпадают name, url, args в рамках категории
            # Тип (type) не учитывается
            if (
                get_value(link, "name", "") == get_value(candidate, "name", "")
                and get_value(link, "url", "") == get_value(candidate, "url", "")
                and get_value(link, "args", "") == get_value(candidate, "args", "")
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
            logger.error("Ошибка при пакетном обновлении ссылок: %s", e)
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
            try:
                ctrl = getattr(self.main, "links_table_controller", None)
                if ctrl:
                    ctrl.reload(category_id)
                else:
                    links_business = getattr(self.main, "links_business", None)
                    if links_business:
                        try:
                            links_business.load_links(category_id)
                        except Exception:
                            pass
            except Exception:
                # Не роняем команду из-за UI
                pass

        # Переключаем фокус на целевую категорию после перемещения
        if (
            new_category
            and hasattr(self.main, "structure_business")
            and self.main.structure_business
        ):
            try:
                self.main.structure_business.select_category(new_category)
                logger.info(
                    "Переключен фокус на целевую категорию %s после перемещения ссылок",
                    new_category,
                )
            except Exception as e:
                logger.warning(
                    "Не удалось переключить фокус на категорию %s: %s",
                    new_category,
                    e,
                )

    def redo(self):
        """Выполнение перемещения ссылок."""
        self._prepare_data()  # Подготавливаем данные при первом выполнении
        self._execute_batch_operation(self._new_states)
        self._refresh_ui(
            old_category=self.old_category_id, new_category=self.new_category_id
        )

    def undo(self):
        """Отмена перемещения ссылок."""
        self._execute_batch_operation(self._old_states)
        # При undo меняем местами категории - фокус должен вернуться на исходную
        self._refresh_ui(
            old_category=self.new_category_id, new_category=self.old_category_id
        )


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
            "position": current_category.get("position", 0),
        }
        # Теперь обновление делегируется в бизнес-слой, который вызывает StructureService
        updated = structure_business.update_category(self.category_id, category_data)
        if updated is None:
            raise ValueError(f"Не удалось обновить категорию {self.category_id}")

    def redo(self):
        try:
            self._prepare_data()

            if self.old_section_id == self.new_section_id:
                return

            # Проверяем дубликаты через бизнес-логику
            structure_business = self.main.structure_business
            if structure_business.has_duplicate_category(
                self.new_section_id, self.cat_name, self.category_id
            ):
                # Молча игнорируем дубликаты - не показываем ошибку пользователю
                logger.debug(
                    "Duplicate category '%s' found in target section %s, ignoring move",
                    self.cat_name,
                    self.new_section_id,
                )
                self.setObsolete(True)
                return

            self._set_section(self.new_section_id)
            self._refresh_structure_ui()
        except Exception as e:
            logger.error("Ошибка при перемещении категории: %s", e)
            raise

    def undo(self):
        try:
            self._set_section(self.old_section_id)
            self._refresh_structure_ui()
        except Exception as e:
            logger.error("Ошибка при отмене перемещения категории: %s", e)
            raise

    def _refresh_structure_ui(self):
        """Обновляет UI структуры после операции."""
        # Полная перезагрузка дерева больше не требуется — модель обновляется инкрементально
        # через сигналы бизнес-логики (item_updated и пр.). Сфокусируем нужную категорию.
        if hasattr(self.main, "structure_business") and self.main.structure_business:
            try:
                self.main.structure_business.select_category(self.category_id)
                logger.info(
                    "Переключен фокус на перемещенную категорию %s", self.category_id
                )
            except Exception as e:
                logger.warning(
                    "Не удалось переключить фокус на категорию %s: %s",
                    self.category_id,
                    e,
                )


class MoveCategoriesCommand(BaseCommand):
    """Пакетное перемещение нескольких категорий в один раздел с единым undo/redo.

    - Сохраняет исходные состояния (section_id, position, name, icon_path)
    - Redo: переносит в целевой раздел, проставляя позиции base_row + i
    - Undo: восстанавливает исходные section_id и position
    - Дубликаты в целевом разделе пропускаются молча (DEBUG)
    """

    def __init__(self, category_ids, new_section_id, base_row, main_window):
        super().__init__(f"Перемещение {len(category_ids)} категорий", main_window)
        self.category_ids = list(category_ids or [])
        self.new_section_id = (
            int(new_section_id) if isinstance(new_section_id, int) else new_section_id
        )
        self.base_row = int(base_row) if isinstance(base_row, int) else 0
        self._old_states = []  # [{id, name, section_id, position, icon_path}]
        self._new_states = []  # такой же формат, но с целевыми section/position
        self._prepared = False

    def _prepare_data(self):
        if self._prepared:
            return
        sb = self.main.structure_business
        # Загружаем исходные состояния
        old_states = []
        for cid in self.category_ids:
            data = sb.get_category_data(cid)
            if not data:
                logger.debug("Категория %s не найдена, пропуск", cid)
                continue
            old_states.append(
                {
                    "id": data["id"],
                    "name": data.get("name", ""),
                    "section_id": data.get("section_id"),
                    "position": data.get("position", 0),
                    "icon_path": data.get("icon_path", ""),
                }
            )
        # Стабильный порядок по исходной позиции, затем по id
        old_states.sort(key=lambda x: (x.get("position", 0), x.get("id", 0)))

        # Формируем целевые состояния с проверкой дубликатов имени в целевом разделе
        new_states = []
        offset = 0
        for st in old_states:
            cid = st["id"]
            name = st.get("name", "")
            # Дубликаты имени в целевом разделе — пропускаем
            try:
                if sb.has_duplicate_category(self.new_section_id, name, cid):
                    logger.debug(
                        "Duplicate category '%s' in target section %s, skipping id=%s",
                        name,
                        self.new_section_id,
                        cid,
                    )
                    continue
            except Exception:
                # В случае ошибки проверки — не блокируем операцию, пробуем переместить
                pass
            ns = {
                "id": cid,
                "name": name,
                "section_id": self.new_section_id,
                "position": self.base_row + offset,
                "icon_path": st.get("icon_path", ""),
            }
            new_states.append(ns)
            offset += 1

        self._old_states = old_states
        self._new_states = new_states
        self._prepared = True

    def _apply_states(self, states):
        if not states:
            return
        sb = self.main.structure_business
        # Подавляем лишние сигналы выбора/перерисовки дерева на время пакетного применения
        struct = getattr(self.main, "structure", None)
        tree = getattr(struct, "tree", None)
        selection = getattr(struct, "selection_handler", None)
        try:
            # Включаем батч-режим бизнес-слоя (если поддерживается)
            try:
                if hasattr(sb, "begin_batch"):
                    sb.begin_batch()
            except Exception:
                pass
            if selection is not None:
                try:
                    selection.begin_suppress_selection()
                except Exception:
                    pass
            if tree is not None:
                try:
                    tree.blockSignals(True)
                except Exception:
                    pass

            # Попытка использовать настоящую батч-операцию, если все элементы переносятся в один раздел
            try:
                target_ids = [
                    int(st.get("id")) for st in states if isinstance(st.get("id"), int)
                ]
                targets = {st.get("section_id") for st in states}
                single_target = len(targets) == 1
                target_section_id = next(iter(targets)) if single_target else None
            except Exception:
                target_ids = []
                single_target = False
                target_section_id = None

            batch_done = False
            if single_target and isinstance(target_section_id, int):
                try:
                    # Вычислим base_row как минимальную позицию среди целевых состояний
                    base_row = 0
                    try:
                        base_row = (
                            min(int(st.get("position", 0) or 0) for st in states)
                            if states
                            else 0
                        )
                    except Exception:
                        base_row = 0
                    moved = sb.move_categories_batch(
                        target_ids, int(target_section_id), int(base_row)
                    )
                    batch_done = True
                    if len(moved) != len(target_ids):
                        logger.debug(
                            "Часть категорий пропущена батч-переносом (дубликаты имён в целевом разделе)"
                        )
                except Exception:
                    # Безопасный фолбэк на поштучное обновление
                    batch_done = False

            if not batch_done:
                # Фолбэк: поштучное обновление категорий (старое поведение)
                for st in states:
                    try:
                        cid = st["id"]
                        payload = {
                            "name": st.get("name", ""),
                            "section_id": st.get("section_id"),
                            "icon_path": st.get("icon_path", ""),
                            "position": st.get("position", 0),
                        }
                        sb.update_category(cid, payload)
                    except Exception as e:
                        logger.error(
                            "Ошибка обновления категории %s: %s", st.get("id"), e
                        )
        finally:
            # Возвращаем обычную обработку сигналов
            try:
                if tree is not None:
                    tree.blockSignals(False)
            except Exception:
                pass
            try:
                if selection is not None:
                    selection.end_suppress_selection()
            except Exception:
                pass
            # Завершаем батч-режим, чтобы выполнить одну консолидацию перезагрузок
            try:
                if hasattr(sb, "end_batch"):
                    sb.end_batch()
            except Exception:
                pass

    def _refresh_ui(self, focus_section_id=None, focus_category_id=None):
        sb = getattr(self.main, "structure_business", None)
        if not sb:
            return
        # Подавляем лавину selection-событий на время финального переключения фокуса
        struct = getattr(self.main, "structure", None)
        selection = getattr(struct, "selection_handler", None)
        tree = getattr(struct, "tree", None)
        try:
            if selection is not None:
                try:
                    selection.begin_suppress_selection()
                except Exception:
                    pass
            if tree is not None:
                try:
                    tree.blockSignals(True)
                except Exception:
                    pass

            try:
                if focus_section_id is not None:
                    sb.section_selected.emit(focus_section_id)
            except Exception:
                pass
            try:
                if focus_category_id is not None:
                    sb.select_category(focus_category_id)
            except Exception:
                pass
        finally:
            if tree is not None:
                try:
                    tree.blockSignals(False)
                except Exception:
                    pass
            if selection is not None:
                try:
                    selection.end_suppress_selection()
                except Exception:
                    pass

        # Информативный лог
        try:
            logger.info(
                "Переключен фокус на раздел %s после пакетного перемещения категорий",
                focus_section_id,
            )
        except Exception:
            pass

    def redo(self):
        self._prepare_data()
        # Применяем новые состояния
        self._apply_states(self._new_states)
        # Фокус на целевом разделе и первой успешно перенесённой категории
        first_new_id = self._new_states[0]["id"] if self._new_states else None
        self._refresh_ui(self.new_section_id, first_new_id)

    def undo(self):
        # Восстановление исходных состояний
        self._apply_states(self._old_states)
        # Фокус на исходном разделе первой категории (если доступен)
        focus_section = None
        focus_category = None
        for st in self._old_states:
            if st.get("section_id") is not None:
                focus_section = st["section_id"]
                focus_category = st.get("id")
                break
        self._refresh_ui(focus_section, focus_category)
