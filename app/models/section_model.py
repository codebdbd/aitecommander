import logging
import sqlite3
from typing import Any, Dict, Optional, cast

from .db_base import DatabaseBase

# Настройка логирования
logger = logging.getLogger(__name__)


class SectionModel(DatabaseBase):
    """Модель для работы с разделами"""

    def get_sections(self, sphere_id: int) -> list[dict[str, Any]]:
        """Возвращает список разделов для указанной сферы в формате dict."""
        rows = self.fetch_all(
            "SELECT id, name, sphere_id, position, icon_path FROM section WHERE sphere_id=? ORDER BY position",
            (sphere_id,),
        )
        if not rows:
            return []
        result: list[dict[str, Any]] = []
        for r in rows:
            try:
                result.append(dict(r))
            except Exception:
                continue
        return result

    def get_section_by_id(self, section_id: int) -> dict[str, Any] | None:
        """Возвращает раздел по его ID в формате dict."""
        row = self.fetch_one("SELECT * FROM section WHERE id=?", (section_id,))
        if row is None:
            return None
        try:
            return dict(row)
        except Exception:
            return None

    def insert_section(self, data: Dict[str, Any]) -> int:
        """Вставляет новый раздел и возвращает его ID."""
        self._validate_required_fields(data, ["name", "sphere_id"], "раздела")

        position = self._get_next_position("section", "sphere_id", data["sphere_id"])
        cursor = self.exec_query(
            "INSERT INTO section (name, sphere_id, icon_path, position) VALUES (?, ?, ?, ?)",
            (data["name"], data["sphere_id"], data.get("icon_path", ""), position),
        )
        logger.info("Добавлен новый раздел: %s", data["name"])
        return int(cursor.lastrowid or 0)

    def update_section(self, section_id: int, data: Dict[str, Any]) -> None:
        """Обновляет существующий раздел."""
        valid_keys = ["name", "sphere_id", "icon_path", "position"]
        self._update_entity("section", section_id, data, valid_keys)

    def delete_section(self, section_id: int) -> None:
        """Удаляет раздел по его ID и реиндексирует позиции оставшихся в той же сфере."""
        # Определим сферу раздела до удаления
        row = self.fetch_one("SELECT sphere_id FROM section WHERE id=?", (section_id,))
        if row is not None:
            d = dict(row)
            val = d.get("sphere_id")
            sphere_id: Optional[int] = int(val) if isinstance(val, int) else None
        else:
            sphere_id = None

        self._execute_with_error_handling(
            "DELETE FROM section WHERE id=?", (section_id,)
        )
        logger.info("Удален раздел с ID %s", section_id)

        # Реиндексация позиций оставшихся разделов в той же сфере
        if isinstance(sphere_id, int):
            try:
                self._reindex_positions(sphere_id)
            except Exception:
                # Не прерываем удаление, но логируем предупреждение
                logger.warning(
                    "Не удалось переиндексировать позиции разделов после удаления", exc_info=False
                )

    def _reindex_positions(self, sphere_id: int) -> None:
        """Переиндексировать поле position для всех разделов сферы последовательно от 0.

        Выполняется без собственного begin/commit, предполагая внешний контекст транзакции.
        """
        # Получаем id разделов в нужном порядке
        rows = self.fetch_all(
            "SELECT id FROM section WHERE sphere_id = ? ORDER BY position, id",
            (sphere_id,),
        )
        ids_in_order = [int(dict(r).get("id", 0)) for r in rows]
        if not ids_in_order:
            return
        # Готовим батч обновлений позиций 0..n-1
        updates = [(pos, cid) for pos, cid in enumerate(ids_in_order)]
        self._execute_many_with_error_handling(
            "UPDATE section SET position = ? WHERE id = ?",
            updates,
        )

    def upsert_section(self, section_data: Dict[str, Any]) -> int:
        """Вставляет или обновляет раздел. Если раздела с таким id нет, вставляет новый с этим id."""
        if "id" in section_data and section_data["id"]:
            cursor = self._execute_with_error_handling(
                "UPDATE section SET name=?, sphere_id=?, icon_path=?, position=? WHERE id=?",
                (
                    section_data["name"],
                    section_data["sphere_id"],
                    section_data.get("icon_path", ""),
                    section_data.get("position", 0),
                    section_data["id"],
                ),
            )
            cur = cast(sqlite3.Cursor, cursor)
            if int(getattr(cur, "rowcount", 0) or 0) == 0:
                # Записи не было, делаем вставку с нужным id
                self._execute_with_error_handling(
                    "INSERT INTO section (id, name, sphere_id, icon_path, position) VALUES (?, ?, ?, ?, ?)",
                    (
                        section_data["id"],
                        section_data["name"],
                        section_data["sphere_id"],
                        section_data.get("icon_path", ""),
                        section_data.get("position", 0),
                    ),
                )
            return section_data["id"]
        else:
            return self.insert_section(section_data)

    def get_sphere_id_by_section(self, section_id: int) -> Optional[int]:
        """Возвращает sphere_id для заданного раздела."""
        row = self.get_section_by_id(section_id)
        return row["sphere_id"] if row else None
