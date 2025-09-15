import logging
import sqlite3
from typing import Any, Dict

from app.utils.ui.icon.icon_resolver import resolve_icon_for_link

from .db_base import DatabaseBase, DatabaseError

# Настройка логирования
logger = logging.getLogger(__name__)

# Централизованный резолв иконок


class SphereModel(DatabaseBase):
    """Модель для работы со сферами"""

    def get_spheres(self) -> list[dict[str, Any]]:
        """Возвращает список всех сфер в формате dict."""
        rows = self.fetch_all(
            "SELECT id, name, position, icon_path FROM sphere ORDER BY position"
        )
        return [dict(r) for r in rows] if rows else []

    def get_sphere_by_id(self, sphere_id: int) -> dict[str, Any] | None:
        """Возвращает сферу по её ID в формате dict."""
        row = self.fetch_one(
            "SELECT id, name, position, icon_path FROM sphere WHERE id = ?",
            (sphere_id,),
        )
        return dict(row) if row else None

    def insert_sphere(self, data: Dict[str, Any]) -> int:
        """Вставляет новую сферу и возвращает её ID."""
        self._validate_required_fields(data, ["name"], "сферы")

        position = self._get_next_position("sphere")
        cursor = self.exec_query(
            "INSERT INTO sphere (name, icon_path, position) VALUES (?, ?, ?)",
            (data["name"], data.get("icon_path", ""), position),
        )
        logger.info("Добавлена новая сфера: %s", data["name"])
        return int(getattr(cursor, "lastrowid", 0) or 0)

    def update_sphere(self, sphere_id: int, data: Dict[str, Any]) -> None:
        """Обновляет существующую сферу."""
        valid_keys = ["name", "icon_path", "position"]
        self._update_entity("sphere", sphere_id, data, valid_keys)

    def upsert_sphere(self, sphere_data: Dict[str, Any]) -> int:
        """Вставляет или обновляет сферу."""
        if "id" in sphere_data and sphere_data["id"]:
            self.update_sphere(sphere_data["id"], sphere_data)
            return sphere_data["id"]
        else:
            return self.insert_sphere(sphere_data)

    def get_sphere_name(self, sphere_id: int) -> str:
        """Возвращает имя сферы по её ID."""
        row = self.fetch_one(
            "SELECT name FROM sphere WHERE id=?",
            (sphere_id,),
        )
        if not row:
            return ""
        try:
            return str(dict(row).get("name", ""))
        except Exception:
            return ""

    def initialize_default_spheres(self) -> None:
        """Инициализирует начальные данные для таблицы sphere, если она пуста.

        Включает добавление совместимой колонки icon_path (если её нет) и
        вставку стандартного набора значений. Коммит выполняется в конце
        операции. Повторный вызов безопасен: если данные уже есть, только логируем.
        """
        try:
            cursor = self.connection.execute("SELECT COUNT(*) FROM sphere")
            count = cursor.fetchone()[0]

            if count == 0:
                # Совместимость: добавить колонку icon_path, если отсутствует
                try:
                    self.connection.execute(
                        "ALTER TABLE sphere ADD COLUMN icon_path TEXT DEFAULT ''"
                    )
                except sqlite3.OperationalError:
                    # Колонка уже существует — это не ошибка
                    pass

                default = [
                    ("AI", 0, resolve_icon_for_link({"type": "ai", "icon_path": ""})),
                    (
                        "Работа",
                        1,
                        resolve_icon_for_link({"type": "work", "icon_path": ""}),
                    ),
                    (
                        "Учеба",
                        2,
                        resolve_icon_for_link({"type": "study", "icon_path": ""}),
                    ),
                    (
                        "Личное",
                        3,
                        resolve_icon_for_link({"type": "personal", "icon_path": ""}),
                    ),
                ]
                self._execute_many_with_error_handling(
                    "INSERT INTO sphere(name, position, icon_path) VALUES(?,?,?)",
                    default,
                )
                self.commit()
                logger.info("Начальные данные для сфер добавлены")
            else:
                logger.info("Начальные данные для сфер уже существуют")
        except Exception as e:
            logger.error("Ошибка инициализации начальных данных сфер: %s", e)
            raise DatabaseError(
                f"Не удалось инициализировать начальные данные сфер: {e}"
            )
