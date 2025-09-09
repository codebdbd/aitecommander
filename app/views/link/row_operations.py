import logging
from typing import Dict

# Модуль для операций со строками таблицы ссылок
# Содержит методы добавления, обновления и удаления строк

logger = logging.getLogger(__name__)


class RowOperationsMixin:
    """Миксин для операций со строками таблицы ссылок."""

    def update_link_by_id(self, link: dict, mode: str = "normal"):
        """
        Обновляет строку таблицы по id ссылки, если она есть.
        """
        try:
            # Проверка входных параметров
            if not isinstance(link, dict):
                logger.warning(
                    "[LinksTableView] Некорректные данные ссылки для обновления: %s",
                    type(link),
                )
                return False

            link_id = link.get("id")

            if link_id is None:
                logger.warning(
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

            logger.debug("Ссылка с ID %s не найдена в таблице", link_id)
            return False
        except Exception as e:
            logger.error(
                "[LinksTableView] Ошибка обновления строки по ID: %s", e, exc_info=True
            )
            return False

    def _update_row(self, row: int, link: Dict, mode: str):
        """Обновляет существующую строку новыми данными через модель."""
        try:
            # Проверка входных параметров
            if not isinstance(link, dict):
                logger.warning(
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
                logger.warning(
                    "[LinksTableView] Некорректный индекс строки для обновления: %s",
                    row,
                )
                return False

            # Пытаемся обновить через модель
            updated = False
            if model is not None and hasattr(model, "update_link"):
                try:
                    updated = bool(model.update_link(row, link))
                except Exception as e:
                    logger.debug(
                        "[LinksTableView] model.update_link исключение: %s",
                        e,
                        exc_info=True,
                    )
                    updated = False

            if not updated:
                logger.warning(
                    "[LinksTableView] model.update_link недоступен — обновление пропущено"
                )
                return False

            # Обновляем кэш (для совместимости)
            try:
                self._current_links[row] = link
            except Exception:
                logger.debug(
                    "[LinksTableView] не удалось обновить кэш для строки %s",
                    row,
                    exc_info=True,
                )
            # Отказываемся от принудительной перерисовки viewport для снижения нагрузки —
            # перерисовка произойдет по сигналам модели (dataChanged)
            logger.debug("Строка %s обновлена", row)
            return True

        except Exception as e:
            logger.error(
                "[LinksTableView] Ошибка обновления строки %s: %s",
                row,
                e,
                exc_info=True,
            )
            return False

    def _add_row(self, row: int, link: Dict, mode: str):
        """Добавляет новую строку через модель."""
        try:
            # Проверка входных параметров
            if not isinstance(link, dict):
                logger.warning(
                    "[LinksTableView] Некорректные данные ссылки для добавления: %s",
                    type(link),
                )
                return False

            try:
                model = self.model()
                total = model.rowCount() if model is not None else 0
            except Exception:
                model = None
                total = 0

            if row < 0 or row > total:
                logger.warning(
                    "[LinksTableView] Некорректный индекс строки для добавления: %s",
                    row,
                )
                return False

            inserted = False
            if model is not None and hasattr(model, "insert_link"):
                try:
                    inserted = bool(model.insert_link(row, link))
                except Exception as e:
                    logger.debug(
                        "[LinksTableView] model.insert_link исключение: %s",
                        e,
                        exc_info=True,
                    )
                    inserted = False

            if not inserted:
                return False

            # Обновляем кэш по фактическим данным
            try:
                self.rebuild_cache_from_items()
            except Exception:
                logger.debug(
                    "[LinksTableView] rebuild_cache_from_items failed after insert",
                    exc_info=True,
                )

            return True

        except Exception as e:
            logger.error(
                "[LinksTableView] Ошибка добавления строки %s: %s",
                row,
                e,
                exc_info=True,
            )
            return False

    def _remove_row(self, row: int) -> bool:
        """Удаляет строку через модель. Возвращает True при успехе, иначе False."""
        try:
            # Проверка входных параметров
            try:
                model = self.model()
                total = model.rowCount() if model is not None else 0
            except Exception:
                model = None
                total = 0

            if row < 0 or row >= total:
                logger.warning(
                    "[LinksTableView] Некорректный индекс строки для удаления: %s",
                    row,
                )
                return False

            removed = False
            if model is not None and hasattr(model, "remove_row"):
                try:
                    removed = bool(model.remove_row(row))
                except Exception as e:
                    logger.debug(
                        "[LinksTableView] model.remove_row исключение: %s",
                        e,
                        exc_info=True,
                    )
                    removed = False

            if not removed:
                return False

            # Перестроить кэш по актуальным данным
            try:
                self.rebuild_cache_from_items()
            except Exception:
                pass

            return True

        except Exception as e:
            logger.error(
                "[LinksTableView] Ошибка удаления строки %s: %s", row, e, exc_info=True
            )
            return False
