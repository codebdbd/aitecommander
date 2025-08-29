# Модуль для заполнения и обновления таблицы ссылок
# Содержит методы массового обновления данных таблицы

import logging
from typing import Dict, List

from PyQt6.QtCore import Qt
from app.utils.ui.updates import suspend_updates


class PopulationManagerMixin:
    """Миксин для заполнения и обновления таблицы ссылок."""

    def populate(self, links: List[Dict], mode: str = "normal"):
        """Заполняет таблицу данными ссылок с инкрементальным обновлением."""
        if not isinstance(links, list):
            logging.warning(
                f"[LinksTableView] Ожидался список ссылок, получен {type(links)}"
            )
            return

        # Оптимизация: отключаем обновление UI при массовых изменениях
        with suspend_updates(self):
            # Сохраняем состояние UI
            try:
                sel = self.selectionModel()
                current_selection = [i.row() for i in sel.selectedRows()] if sel else []
            except Exception:
                current_selection = []
            current_scroll_pos = self.verticalScrollBar().value()

            # Сохраняем текущую сортировку
            try:
                header = self.horizontalHeader()
                sort_col, sort_order = (
                    header.sortIndicatorSection(),
                    header.sortIndicatorOrder(),
                )
            except Exception:
                sort_col, sort_order = -1, Qt.SortOrder.AscendingOrder

            # Если режим изменился, делаем полное обновление
            if mode != self._current_mode:
                self._current_mode = mode
                self._full_populate(links, mode)
                self._restore_ui_state(
                    current_selection, current_scroll_pos, sort_col, sort_order
                )
                return

            # Инкрементальное обновление
            try:
                self.blockSignals(True)
                self.horizontalHeader().blockSignals(True)
                # Гарантируем корректность кэша перед диффом
                cache_ok = self.validate_cache_integrity()
                if not cache_ok:
                    self.rebuild_cache_from_items()

                # Если нет активной сортировки и изменился порядок ID, проще и безопаснее сделать полное обновление
                def _ids_from_table() -> List:
                    ids = []
                    model = self.model()
                    total = model.rowCount() if model is not None else 0
                    for row in range(total):
                        data = self.get_link_at(row)
                        if data and "id" in data:
                            ids.append(data["id"])
                    return ids

                current_order = _ids_from_table()
                new_order = [link.get("id") for link in links if link and "id" in link]
                if (sort_col == -1) and current_order and (current_order != new_order):
                    logging.info(
                        "[LinksTableView] Обнаружено изменение порядка ID без активной сортировки — выполняем полное обновление"
                    )
                    self._full_populate(links, mode)
                    return

                current_ids = self._get_current_link_ids()
                new_ids = self._get_new_link_ids(links)
                new_link_map = self._create_link_id_to_data_map(links)

                # Находим изменения
                ids_to_remove = current_ids - new_ids
                ids_to_add = new_ids - current_ids
                ids_to_check = current_ids & new_ids

                # Если изменений очень много — дешевле сделать полное обновление
                bulk_changes = len(ids_to_add) + len(ids_to_remove)
                if bulk_changes >= 30 or len(links) >= 200:
                    logging.info(
                        "[LinksTableView] Большой объём изменений (%s) — выполняем полное обновление",
                        bulk_changes,
                    )
                    self._full_populate(links, mode)
                    return

                # Удаляем исчезнувшие ссылки (в обратном порядке)
                rows_to_remove = []
                # Создаем копию кэша для итерации, чтобы избежать проблем при изменении кэша во время итерации
                current_links_copy = self._current_links.copy()
                for row, link in current_links_copy.items():
                    if link and link.get("id") in ids_to_remove:
                        rows_to_remove.append(row)

                # Сортируем индексы в обратном порядке для корректного удаления
                for row in sorted(rows_to_remove, reverse=True):
                    self._remove_row(row)

                # Обновляем изменившиеся ссылки
                for row, current_link in list(self._current_links.items()):
                    if not current_link or current_link.get("id") not in ids_to_check:
                        continue

                    link_id = current_link.get("id")
                    new_link = new_link_map.get(link_id)

                    if new_link and not self._links_equal(current_link, new_link, mode):
                        self._update_row(row, new_link, mode)

                # Добавляем новые ссылки
                if ids_to_add:
                    # Находим позицию для вставки каждой новой ссылки
                    for i, link in enumerate(links):
                        link_id = link.get("id")
                        if link_id in ids_to_add:
                            # Ищем правильную позицию для вставки
                            # Если есть активная сортировка, добавляем в конец и затем сортировка восстановится
                            model = self.model()
                            total = model.rowCount() if model is not None else 0
                            target_row = (total if sort_col != -1 else min(i, total))
                            # Оптимизация: не перестраиваем кэш на каждый insert — сделаем один раз ниже
                            self._add_row(target_row, link, mode)

                # После пакетных операций — разовая перестройка кэша
                try:
                    if hasattr(self, "rebuild_cache_from_items"):
                        self.rebuild_cache_from_items()
                except Exception:
                    pass

            except Exception as e:
                logging.error(
                    f"[LinksTableView] Ошибка при инкрементальном обновлении: {e}"
                )
                # В случае ошибки делаем полное обновление
                self._full_populate(links, mode)
            finally:
                self.horizontalHeader().blockSignals(False)
                self.blockSignals(False)
                self._restore_ui_state(
                    current_selection, current_scroll_pos, sort_col, sort_order
                )
                # Сообщаем подписчикам, что таблица обновлена
                try:
                    if hasattr(self, "table_populated"):
                        self.table_populated.emit()
                except Exception as e:
                    logging.debug(
                        f"[LinksTableView] Не удалось эмитить table_populated после populate: {e}"
                    )

    def _full_populate(self, links: List[Dict], mode: str):
        """Выполняет полное обновление таблицы через модель."""
        try:
            # Обновляем режим
            self._current_mode = mode
            # Передаём данные в модель одним вызовом
            model = self.model()
            if model is not None and hasattr(model, "set_links"):
                model.set_links(links)
            # Обновляем кэш из модели
            if hasattr(self, "rebuild_cache_from_items"):
                self.rebuild_cache_from_items()

        except Exception as e:
            logging.error(f"[LinksTableView] Ошибка при полном обновлении таблицы: {e}")
        finally:
            # Сообщаем подписчикам, что таблица полностью обновлена
            try:
                if hasattr(self, "table_populated"):
                    self.table_populated.emit()
            except Exception as e:
                logging.debug(
                    f"[LinksTableView] Не удалось эмитить table_populated после _full_populate: {e}"
                )

    def _restore_ui_state(
        self,
        selection: List[int],
        scroll_pos: int,
        sort_col: int,
        sort_order: Qt.SortOrder,
    ):
        # Обновляем состояние сортировки
        self._sort_col = sort_col
        self._sort_order = sort_order
        """Восстанавливает состояние UI после обновления."""
        try:
            # Восстанавливаем сортировку
            model = self.model()
            total_cols = model.columnCount() if model is not None else 0
            if sort_col != -1 and sort_col < total_cols:
                # Для QTableView используем sortByColumn
                try:
                    self.sortByColumn(sort_col, sort_order)
                except Exception:
                    pass
                # ВАЖНО: после сортировки строки меняют индексы —
                # нужно синхронизировать кэш _current_links с фактическими элементами,
                # иначе возможны визуальные дубликаты и неверные обновления строк
                try:
                    if hasattr(self, "rebuild_cache_from_items"):
                        self.rebuild_cache_from_items()
                except Exception as e:
                    logging.warning(
                        f"[LinksTableView] Не удалось перестроить кэш после сортировки: {e}"
                    )

            # Убрано автоматическое восстановление выделения строк
            # для стандартного поведения Qt без принудительного выбора

            # Восстанавливаем позицию скролла
            self.verticalScrollBar().setValue(scroll_pos)

            self.viewport().update()

        except Exception as e:
            logging.error(f"[LinksTableView] Ошибка восстановления UI состояния: {e}")
