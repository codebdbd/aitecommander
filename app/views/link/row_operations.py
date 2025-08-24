# Модуль для операций со строками таблицы ссылок
# Содержит методы добавления, обновления и удаления строк

import logging
from typing import Dict


class RowOperationsMixin:
    """Миксин для операций со строками таблицы ссылок."""

    def update_link_by_id(self, link: dict, mode: str = "normal"):
        """
        Обновляет строку таблицы по id ссылки, если она есть.
        """
        try:
            # Проверка входных параметров
            if not isinstance(link, dict):
                logging.warning(
                    f"[LinksTableView] Некорректные данные ссылки для обновления: {type(link)}"
                )
                return False

            link_id = link.get("id")

            if link_id is None:
                logging.warning(
                    "[LinksTableView] Отсутствует ID в данных ссылки для обновления"
                )
                return False

            # Используем модель для поиска строки по ID
            try:
                model = self.model()
            except Exception:
                model = None
            row = -1
            if model is not None and hasattr(model, "find_row_by_id"):
                try:
                    row = model.find_row_by_id(link_id)
                except Exception:
                    row = -1
            else:
                # Фолбэк: линейный поиск через get_link_at
                try:
                    m = model if model is not None else None
                    total = m.rowCount() if m is not None else 0
                except Exception:
                    total = 0
                for r in range(total):
                    row_data = self.get_link_at(r)
                    if isinstance(row_data, dict) and row_data.get("id") == link_id:
                        row = r
                        break

            if row >= 0:
                success = self._update_row(row, link, mode)
                return success

            logging.debug(f"Ссылка с ID {link_id} не найдена в таблице")
            return False
        except Exception as e:
            logging.error(f"[LinksTableView] Ошибка обновления строки по ID: {e}")
            return False

    def _update_row(self, row: int, link: Dict, mode: str):
        """Обновляет существующую строку новыми данными через модель."""
        try:
            # Проверка входных параметров
            if not isinstance(link, dict):
                logging.warning(
                    f"[LinksTableView] Некорректные данные ссылки для обновления: {type(link)}"
                )
                return False

            # Проверяем границы по модели
            try:
                model = self.model()
                total = model.rowCount() if model is not None else 0
            except Exception:
                model = None
                total = 0

            if row < 0 or row >= total:
                logging.warning(
                    f"[LinksTableView] Некорректный индекс строки для обновления: {row}"
                )
                return False

            # Пытаемся обновить через модель
            updated = False
            if model is not None and hasattr(model, "update_link"):
                try:
                    updated = bool(model.update_link(row, link))
                except Exception as e:
                    logging.debug(f"[LinksTableView] model.update_link исключение: {e}")
                    updated = False

            if not updated:
                logging.warning("[LinksTableView] model.update_link недоступен — обновление пропущено")
                return False

            # Обновляем кэш (для совместимости)
            try:
                self._current_links[row] = link
            except Exception:
                pass
            # Принудительно перерисовываем видимую область таблицы,
            # чтобы гарантировать визуальное обновление иконок/текста
            try:
                viewport = getattr(self, "viewport", None)
                if callable(viewport):
                    vp = viewport()
                    if hasattr(vp, "update"):
                        vp.update()
                # Как дополнительный вариант, если потребуется более жёсткая перерисовка:
                # if hasattr(self, 'repaint'):
                #     self.repaint()
            except Exception as e:
                logging.debug(
                    f"[LinksTableView] Не удалось принудительно обновить viewport: {e}"
                )
            logging.info(f"Строка {row} успешно обновлена")
            return True

        except Exception as e:
            logging.error(f"[LinksTableView] Ошибка обновления строки {row}: {e}")
            return False

    def _add_row(self, row: int, link: Dict, mode: str):
        """Добавляет новую строку через модель."""
        try:
            # Проверка входных параметров
            if not isinstance(link, dict):
                logging.warning(
                    f"[LinksTableView] Некорректные данные ссылки для добавления: {type(link)}"
                )
                return False

            try:
                model = self.model()
                total = model.rowCount() if model is not None else 0
            except Exception:
                model = None
                total = 0

            if row < 0 or row > total:
                logging.warning(
                    f"[LinksTableView] Некорректный индекс строки для добавления: {row}"
                )
                return False

            inserted = False
            if model is not None and hasattr(model, "insert_link"):
                try:
                    inserted = bool(model.insert_link(row, link))
                except Exception as e:
                    logging.debug(f"[LinksTableView] model.insert_link исключение: {e}")
                    inserted = False

            if not inserted:
                return False

            # Обновляем кэш по фактическим данным
            try:
                self.rebuild_cache_from_items()
            except Exception:
                pass

            return True

        except Exception as e:
            logging.error(f"[LinksTableView] Ошибка добавления строки {row}: {e}")
            return False

    def _remove_row(self, row: int):
        """Удаляет строку через модель."""
        try:
            # Проверка входных параметров
            try:
                model = self.model()
                total = model.rowCount() if model is not None else 0
            except Exception:
                model = None
                total = 0

            if row < 0 or row >= total:
                logging.warning(
                    f"[LinksTableView] Некорректный индекс строки для удаления: {row}"
                )
                return

            removed = False
            if model is not None and hasattr(model, "remove_row"):
                try:
                    removed = bool(model.remove_row(row))
                except Exception as e:
                    logging.debug(f"[LinksTableView] model.remove_row исключение: {e}")
                    removed = False

            if not removed:
                return

            # Перестроить кэш по актуальным данным
            try:
                self.rebuild_cache_from_items()
            except Exception:
                pass

        except Exception as e:
            logging.error(f"[LinksTableView] Ошибка удаления строки {row}: {e}")
