import logging
from typing import Any, Dict, Optional

from .db_base import DatabaseBase

# Настройка логирования
logger = logging.getLogger(__name__)


class SectionModel(DatabaseBase):
    """Модель для работы с разделами"""

    def get_sections(self, sphere_id: int):
        """Возвращает список разделов для указанной сферы в формате dict."""
        rows = self._execute_with_error_handling(
            "SELECT id, name, sphere_id, position, icon_path FROM section "
            "WHERE sphere_id=? ORDER BY position",
            (sphere_id,),
            fetch_method="all",
        )
        return [dict(row) for row in rows] if rows else []

    def get_section_by_id(self, section_id: int):
        """Возвращает раздел по его ID в формате dict."""
        row = self._execute_with_error_handling(
            "SELECT * FROM section WHERE id=?", (section_id,), fetch_method="one"
        )
        return dict(row) if row else None

    def insert_section(self, data: Dict[str, Any]) -> int:
        """Вставляет новый раздел и возвращает его ID."""
        self._validate_required_fields(data, ["name", "sphere_id"], "раздела")

        position = self._get_next_position("section", "sphere_id", data["sphere_id"])
        cursor = self._execute_with_error_handling(
            "INSERT INTO section (name, sphere_id, icon_path, position) VALUES (?, ?, ?, ?)",
            (data["name"], data["sphere_id"], data.get("icon_path", ""), position),
        )
        self.connection.commit()
        logger.info(f"Добавлен новый раздел: {data['name']}")
        return cursor.lastrowid

    def update_section(self, section_id: int, data: Dict[str, Any]):
        """Обновляет существующий раздел."""
        valid_keys = ["name", "sphere_id", "icon_path", "position"]
        self._update_entity("section", section_id, data, valid_keys)

    def delete_section(self, section_id: int):
        """Удаляет раздел по его ID."""
        self._execute_with_error_handling(
            "DELETE FROM section WHERE id=?", (section_id,)
        )
        self.connection.commit()
        logger.info(f"Удален раздел с ID {section_id}")

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
            self.connection.commit()
            if cursor.rowcount == 0:
                # Записи не было, делаем вставку с нужным id
                self.connection.execute(
                    "INSERT INTO section (id, name, sphere_id, icon_path, position) VALUES (?, ?, ?, ?, ?)",
                    (
                        section_data["id"],
                        section_data["name"],
                        section_data["sphere_id"],
                        section_data.get("icon_path", ""),
                        section_data.get("position", 0),
                    ),
                )
                self.connection.commit()
            return section_data["id"]
        else:
            return self.insert_section(section_data)

    def get_sphere_id_by_section(self, section_id: int) -> Optional[int]:
        """Возвращает sphere_id для заданного раздела."""
        row = self.get_section_by_id(section_id)
        return row["sphere_id"] if row else None
