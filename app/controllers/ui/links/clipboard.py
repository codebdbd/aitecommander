# app/controllers/links_ui/clipboard.py

import logging
from typing import Dict, List

from app.controllers.ui.undo.commands_links import (
    BatchDeleteLinksCmd,
    BatchSaveLinksCmd,
    DeleteLinkCmd,
    SaveLinkCmd,
)
from app.utils.ui.clipboard import copy_link_to_clipboard, get_link_from_clipboard

from .base_component import BaseLinksUIComponent
from .exceptions import CategoryNotFoundError, DatabaseError

logger = logging.getLogger(__name__)


class LinksUIClipboard(BaseLinksUIComponent):
    """Логика работы с буфером обмена для LinksUIController."""

    def cut_link(self):
        """Вырезать выбранные ссылки."""
        self._process_clipboard_operation(is_cut=True)

    def copy_link(self):
        """Копировать выбранные ссылки."""
        self._process_clipboard_operation(is_cut=False)

    def _process_clipboard_operation(self, is_cut: bool = False):
        """Общая логика для копирования/вырезания ссылок."""
        links = self.get_selected_links()
        if not links:
            return

        success = copy_link_to_clipboard(links[0] if len(links) == 1 else links)
        if is_cut and success:
            self.delete_links(links)

    def paste_link(self):
        """Вставить ссылки из буфера обмена."""
        try:
            current_category_id = self._validate_category_exists(None)
        except CategoryNotFoundError as e:
            self._show_warning(str(e))
            return

        try:
            links = self._validate_clipboard_data()
            if not links:
                return

            # Получаем существующие ссылки для проверки дубликатов
            existing = self.links_business.get_links(current_category_id)

            # Оптимизированная фильтрация дубликатов с использованием set
            new_links = self._filter_duplicates_optimized(
                links, existing, current_category_id
            )

            if not new_links:
                return  # Все ссылки являются дубликатами

            # Вставка ссылок
            self._insert_links(new_links)

        except Exception as e:
            logger.error(f"Ошибка при вставке ссылок: {e}", exc_info=True)
            self._show_error(f"Не удалось вставить ссылки: {str(e)}")

    def delete_links(self, links: List[Dict]):
        """Удалить ссылки."""
        if not links:
            return

        category_id = links[0].get("category_id")

        if len(links) > 1:
            # Пакетная команда: одна транзакция и один внеш. reload
            with self.main.undo_stack.macro(f"Удаление {len(links)} ссылок"):
                command = BatchDeleteLinksCmd(links_to_delete=links, main_window=self.main)
                command._suppress_ui = True
                self.main.undo_stack.push(command)
        else:
            for link in links:
                command = DeleteLinkCmd(link_to_delete=link, main_window=self.main)
                command._suppress_ui = True
                self.main.undo_stack.push(command)

        # Обновляем отображение (команда подавляет внутренний UI, здесь — один reload)
        if category_id is not None:
            try:
                self._update_category_safe(category_id)
            except DatabaseError as e:
                logger.error(f"Failed to update category after deletion: {e}")
        # Централизованная эмиссия сигналов через LinkOperationsController
        try:
            self.link_operations.on_links_deleted(links)
        except Exception as e:
            logger.debug(f"Failed to emit signals after delete_links: {e}")

    def get_selected_links(self) -> List[Dict]:
        """Получить выбранные ссылки."""
        selected_rows = sorted(set(idx.row() for idx in self.table.selectedIndexes()))
        return [
            self.controller.get_link_at(row)
            for row in selected_rows
            if self.controller.get_link_at(row)
        ]

    def _validate_clipboard_data(self) -> List[Dict]:
        """Валидация данных из буфера обмена."""
        links = get_link_from_clipboard()
        if not links:
            return []

        # Нормализация к списку
        if isinstance(links, dict):
            links = [links]
        elif not isinstance(links, list):
            raise ValueError("Некорректный формат данных в буфере обмена")

        return links

    def _prepare_link_data(self, link: Dict, category_id: int) -> Dict:
        """Подготовка данных ссылки для вставки."""
        new_data = dict(link)
        new_data.pop("id", None)  # Удаляем старый ID
        new_data["category_id"] = category_id
        return new_data

    def _insert_links(self, links: List[Dict]):
        """Вставка списка ссылок с поддержкой undo."""
        if len(links) > 1:
            # Пакетная вставка: одна транзакция, один reload в команде
            with self.main.undo_stack.macro(f"Вставка {len(links)} ссылок"):
                cmd = BatchSaveLinksCmd(
                    links_data=links,
                    old_link_data=None,
                    main_window=self.main,
                )
                # Команда сама выполнит единичный reload; внешние обновления не нужны
                self.main.undo_stack.push(cmd)
        else:
            for link_data in links:
                self.main.undo_stack.push(
                    SaveLinkCmd(
                        new_data=link_data, old_data=None, main_window=self.main
                    )
                )

    def _filter_duplicates_optimized(
        self, links: List[Dict], existing_links: List[Dict], category_id: int
    ) -> List[Dict]:
        """Оптимизированная фильтрация дубликатов с использованием set для O(n) сложности."""
        # Создаем set существующих ключей для быстрого поиска
        existing_keys = set()
        for link in existing_links:
            link_dict = dict(link) if not isinstance(link, dict) else link
            key = (
                link_dict.get("url", ""),
                link_dict.get("type", ""),
                link_dict.get("args", ""),
                link_dict.get("name", ""),  # Учитываем name, как в UNIQUE(category_id,name,url,args)
            )
            existing_keys.add(key)

        new_links = []
        filtered_count = 0
        for link in links:
            new_data = self._prepare_link_data(link, category_id)
            candidate_key = (
                new_data.get("url", ""),
                new_data.get("type", ""),
                new_data.get("args", ""),
                new_data.get("name", ""),
            )

            if candidate_key not in existing_keys:
                new_links.append(new_data)
                existing_keys.add(candidate_key)  # Добавляем для следующих проверок
            else:
                filtered_count += 1

        if filtered_count:
            logger.info(
                f"[Paste] Отфильтровано дубликатов: {filtered_count} из {len(links)} по ключу (url,type,args,name)"
            )
        return new_links

    def _is_duplicate(self, candidate: Dict, links: List[Dict]) -> bool:
        """Проверить, является ли ссылка дубликатом (сохранено для обратной совместимости)."""
        candidate_key = (
            candidate.get("url", ""),
            candidate.get("type", ""),
            candidate.get("args", ""),
        )

        for link in links:
            link_dict = dict(link) if not isinstance(link, dict) else link
            link_key = (
                link_dict.get("url", ""),
                link_dict.get("type", ""),
                link_dict.get("args", ""),
            )
            if candidate_key == link_key:
                return True
        return False
