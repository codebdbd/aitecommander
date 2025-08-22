import logging
import sqlite3
from typing import Any, Dict

from app.utils.db.synchronization import db_lock
from app.utils.ui.icon.icon_resolver import resolve_icon_for_link

from .db_base import DatabaseBase, DatabaseError

# Настройка логирования
logger = logging.getLogger(__name__)

# Централизованный резолв иконок


class SphereModel(DatabaseBase):
    """Модель для работы со сферами"""
    
    def get_spheres(self):
        """Возвращает список всех сфер."""
        return self._execute_with_error_handling(
            "SELECT id, name, position, icon_path FROM sphere ORDER BY position",
            fetch_method='all'
        )

    def get_sphere_by_id(self, sphere_id: int):
        """Возвращает сферу по её ID."""
        return self._execute_with_error_handling(
            "SELECT id, name, position, icon_path FROM sphere WHERE id = ?",
            (sphere_id,),
            fetch_method='one'
        )

    def insert_sphere(self, data: Dict[str, Any]) -> int:
        """Вставляет новую сферу и возвращает её ID."""
        self._validate_required_fields(data, ['name'], 'сферы')
        
        position = self._get_next_position('sphere')
        with db_lock:
            cursor = self._execute_with_error_handling(
                "INSERT INTO sphere (name, icon_path, position) VALUES (?, ?, ?)",
                (data["name"], data.get("icon_path", ""), position)
            )
            self.connection.commit()
        logger.info(f"Добавлена новая сфера: {data['name']}")
        return cursor.lastrowid

    def update_sphere(self, sphere_id: int, data: Dict[str, Any]):
        """Обновляет существующую сферу."""
        valid_keys = ["name", "icon_path", "position"]
        self._update_entity('sphere', sphere_id, data, valid_keys)

    def upsert_sphere(self, sphere_data: Dict[str, Any]) -> int:
        """Вставляет или обновляет сферу."""
        if 'id' in sphere_data and sphere_data['id']:
            self.update_sphere(sphere_data['id'], sphere_data)
            return sphere_data['id']
        else:
            return self.insert_sphere(sphere_data)

    def get_sphere_name(self, sphere_id: int) -> str:
        """Возвращает имя сферы по её ID."""
        row = self._execute_with_error_handling(
            "SELECT name FROM sphere WHERE id=?",
            (sphere_id,),
            fetch_method='one'
        )
        return row[0] if row else ""

    def seed_spheres(self):
        """Заполняет таблицу sphere начальными данными, если она пуста."""
        try:
            cur = self.connection.execute("SELECT COUNT(*) FROM sphere")
            count = cur.fetchone()[0]
            if count == 0:
                try:
                    self.connection.execute("ALTER TABLE sphere ADD COLUMN icon_path TEXT DEFAULT ''")
                except sqlite3.OperationalError:
                    pass  # Игнорируем, если колонка уже существует

                default = [
                    ("AI", 0, resolve_icon_for_link({"type": "ai", "icon_path": ""})),
                    ("Работа", 1, resolve_icon_for_link({"type": "work", "icon_path": ""})),
                    ("Учеба", 2, resolve_icon_for_link({"type": "study", "icon_path": ""})),
                    ("Личное", 3, resolve_icon_for_link({"type": "personal", "icon_path": ""})),
                ]
                with db_lock:
                    self.connection.executemany(
                        "INSERT INTO sphere(name, position, icon_path) VALUES(?,?,?)",
                        default
                    )
                    self.connection.commit()
                logger.info("Начальные данные для сфер добавлены")
        except Exception as e:
            logger.error(f"Ошибка заполнения начальных данных: {e}")
            raise DatabaseError(f"Не удалось заполнить начальные данные: {e}")

    def init_default_data(self):
        """Инициализирует начальные данные для сфер."""
        try:
            # Проверяем, есть ли уже данные
            cursor = self.connection.execute("SELECT COUNT(*) FROM sphere")
            count = cursor.fetchone()[0]
            
            if count == 0:
                # Добавляем колонку icon_path если её нет (для совместимости)
                try:
                    self.connection.execute("ALTER TABLE sphere ADD COLUMN icon_path TEXT DEFAULT ''")
                except sqlite3.OperationalError:
                    pass  # Игнорируем, если колонка уже существует

                default = [
                    ("AI", 0, resolve_icon_for_link({"type": "ai", "icon_path": ""})),
                    ("Работа", 1, resolve_icon_for_link({"type": "work", "icon_path": ""})),
                    ("Учеба", 2, resolve_icon_for_link({"type": "study", "icon_path": ""})),
                    ("Личное", 3, resolve_icon_for_link({"type": "personal", "icon_path": ""})),
                ]
                with db_lock:
                    self.connection.executemany(
                        "INSERT INTO sphere(name, position, icon_path) VALUES(?,?,?)",
                        default
                    )
                    self.connection.commit()
                logger.info("Начальные данные для сфер добавлены")
            else:
                logger.info("Начальные данные уже существуют")
        except Exception as e:
            logger.error(f"Ошибка заполнения начальных данных: {e}")
            raise DatabaseError(f"Не удалось заполнить начальные данные: {e}")
