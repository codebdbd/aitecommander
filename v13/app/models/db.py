import argparse
import copy
import datetime
import json
import logging
import sqlite3
import sys
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

from app.config_data import app_config
from app.utils.db.migrations import MigrationRunner
from app.utils.db.synchronization import db_lock
from . import legacy_db

from .category_model import CategoryModel
from .db_base import VALID_POSITION_TABLES, DatabaseBase, DatabaseError, ValidationError
from .link_model import LinkModel
from .link_type import LinkType
from .section_model import SectionModel
from .sphere_model import SphereModel
from app.models.database import duplicates as db_duplicates
from app.models.database import backup as db_backup
from app.models.database import positioning as db_positioning
from app.models.database import structure_io as db_structure_io
from app.models.database import subtree_io as db_subtree_io
from app.models.database import connection as db_connection
from app.models.database import migrations as db_migrations

# Настройка логирования
logger = logging.getLogger(__name__)

# Пути к файлам
SCHEMA_PATH = Path(__file__).parent / "schema.sql"
MIGRATIONS_DIR = Path(__file__).parent / "migrations"

# Пути к базе данных из централизованной конфигурации
PATHS = app_config.paths
DB_PATH = PATHS.get_db_path()
BACKUP_DIR = PATHS.get_backups_dir()


class Database(DatabaseBase):
    def __init__(self):
        self.db_path = str(DB_PATH)
        self.thread_local = threading.local()

        # Инициализируем базовый класс (передаем self как connection_manager)
        super().__init__(self)

        # Инициализируем модели после полной инициализации Database
        self.spheres = SphereModel(self)
        self.sections = SectionModel(self)
        self.categories = CategoryModel(self)
        self.links = LinkModel(self)

    def prepare_dirs(self) -> None:
        """Создаёт необходимые пользовательские каталоги для данных.

        Вызывать в фоне до первой работы с БД, чтобы не блокировать UI.
        """
        PATHS.ensure_user_data_dirs()

    def initialize_or_migrate(self) -> None:
        """Инициализирует новую БД или выполняет миграции для существующей.

        Тяжёлая операция: запускать в фоне (QRunnable) с использованием глобальной
        блокировки `db_lock` внутри методов, где это необходимо.
        """
        try:
            db_migrations.initialize_or_migrate(
                db=self,
                migrations_dir=MIGRATIONS_DIR,
                db_path=DB_PATH,
                db_lock=db_lock,
                logger=logger,
                MigrationRunnerClass=MigrationRunner,
            )
        finally:
            # Закрываем соединение текущего потока (например, воркера),
            # чтобы не держать открытым соединение из фонового потока.
            try:
                self.close()
            except Exception:
                pass

    def __enter__(self):
        """Позволяет использовать Database как context manager."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    @property
    def connection(self):
        """Возвращает потокобезопасное соединение с БД. ВАЖНО: используйте объект только из одного потока!
        Для PyQt6 рекомендуется работать с базой только в главном потоке или через отдельный worker с передачей данных через сигналы/слоты."""
        return db_connection.get_connection(self.thread_local, self.db_path)

    def _init_schema(self):
        """[DEPRECATED] Инициализация схемы напрямую из schema.sql.

        Используйте систему миграций (MigrationRunner) вместо прямого вызова.
        Оставлено для обратной совместимости в утилитах.
        """
        logger.warning(
            "Database._init_schema is deprecated; delegating to app.models.legacy_db.init_schema"
        )
        legacy_db.init_schema(self)

    def _run_migrations(self):
        """[DEPRECATED] Ручные миграции. Не используется, оставлено для истории."""
        logger.warning(
            "Database._run_migrations is deprecated; delegating to app.models.legacy_db.run_migrations"
        )
        legacy_db.run_migrations(self)

    # Вспомогательные методы

    def get_section_id_by_category(self, category_id: int) -> Optional[int]:
        """Возвращает section_id для заданной категории."""
        row = self.categories.get_category_by_id(category_id)
        return row["section_id"] if row else None

    def get_sphere_id_by_section(self, section_id: int) -> Optional[int]:
        """Возвращает sphere_id для заданного раздела."""
        return self.sections.get_sphere_id_by_section(section_id)

    def update_item_positions(self, table_name: str, ids_in_order: List[int]):
        """Обновляет поле 'position' для списка элементов в указанной таблице."""
        return db_positioning.update_item_positions(self.connection, db_lock, table_name, ids_in_order)

    # === Helpers for update_item_positions ===
    def _validate_ids(self, ids_in_order: List[int]) -> List[int]:
        """Проверяет и нормализует входные ID: типы, значения, уникальность.

        Возвращает список int ID. Бросает ValidationError при несоответствиях.
        """
        ids = list(ids_in_order or [])
        if not ids:
            return []

        for v in ids:
            if isinstance(v, bool) or not isinstance(v, int) or v < 0:
                raise ValidationError(f"Некорректный ID в списке позиций: {v}")

        if len(set(ids)) != len(ids):
            raise ValidationError("Список ID содержит дубликаты")

        return ids

    def _ensure_ids_exist(self, table_name: str, ids: List[int]) -> None:
        """Проверяет существование всех указанных ID в таблице. Бросает ValidationError при отсутствии."""
        with db_lock:
            existing_ids = set()
            SELECT_CHUNK = 900
            for s in range(0, len(ids), SELECT_CHUNK):
                part = ids[s : s + SELECT_CHUNK]
                placeholders = ",".join(["?"] * len(part))
                rows = self.connection.execute(
                    f"SELECT id FROM {table_name} WHERE id IN ({placeholders})",
                    tuple(part),
                ).fetchall()
                existing_ids.update(int(dict(row)["id"]) for row in rows)
        missing = [i for i in ids if i not in existing_ids]
        if missing:
            raise ValidationError(
                f"Не найдены записи с ID: {missing} в таблице {table_name}"
            )

    # Методы импорта/экспорта
    def export_full_structure(self) -> Dict[str, List]:
        """Экспортирует всю структуру данных из БД в виде словаря."""
        try:
            return db_structure_io.export_full_structure(self)
        except Exception as e:
            logger.error("Ошибка экспорта структуры: %s", e, exc_info=True)
            raise DatabaseError(f"Не удалось экспортировать структуру: {e}")

    def get_full_structure(self) -> List[Dict]:
        """Возвращает полную структуру данных в виде вложенных словарей."""
        try:
            return db_structure_io.get_full_structure(self)
        except Exception as e:
            logger.error("Ошибка получения полной структуры: %s", e, exc_info=True)
            raise DatabaseError(f"Не удалось получить полную структуру: {e}")

    def import_full_structure(self, data: List[Dict]):
        """Очищает базу и импортирует данные из структуры.

        Потокобезопасная операция, которая не изменяет входные данные.

        Args:
            data: Список словарей со структурой данных для импорта.
                  Исходный объект остается неизменным.
        """
        try:
            # Гарантируем deepcopy на стороне модуля db (для совместимости тестов)
            data_copy = copy.deepcopy(data or [])
            # Используем db_lock из этого модуля (для совместимости тестов)
            with db_lock:
                # Вся тяжёлая логика импорта остаётся в перенесённой функции
                return db_structure_io.import_full_structure(self, data_copy)
        except Exception as e:
            logger.error("Ошибка импорта структуры: %s", e, exc_info=True)
            raise DatabaseError(f"Не удалось импортировать структуру: {e}")

    def export_section_tree(self, section_id: int) -> dict:
        """Экспортирует раздел вместе со всеми категориями и ссылками."""
        exporter = db_subtree_io.export_section_tree(self)
        return exporter(section_id)

    def import_section_tree(self, tree: dict):
        """Восстанавливает раздел, его категории и все ссылки из backup-структуры."""
        importer = db_subtree_io.import_section_tree(self)
        return importer(tree)

    def export_category_tree(self, category_id: int) -> dict:
        """Экспортирует категорию вместе со всеми ссылками."""
        exporter = db_subtree_io.export_category_tree(self)
        return exporter(category_id)

    def import_category_tree(self, tree: dict):
        """Восстанавливает категорию и все ссылки из backup-структуры."""
        importer = db_subtree_io.import_category_tree(self)
        return importer(tree)

    def import_category_trees_bulk(self, trees: List[dict]) -> None:
        """Импортирует несколько поддеревьев категорий в ОДНОЙ транзакции."""
        if not trees:
            return
        try:
            importer = db_subtree_io.import_category_trees_bulk(self)
            return importer(trees)
        except Exception as e:
            logger.error("Ошибка bulk-импорта деревьев категорий: %s", e)
            raise DatabaseError(f"Не удалось импортировать деревья категорий: {e}")

    def is_connected(self) -> bool:
        """Проверяет, установлено ли соединение с базой данных."""
        try:
            conn = getattr(self.thread_local, "conn", None)
            if conn is not None:
                # Простая проверка, что соединение еще живо
                conn.execute("SELECT 1").fetchone()
                return True
            return False
        except Exception:
            return False

    def backup(self):
        """Создаёт резервную копию базы данных и удаляет старые копии при превышении лимита.
        Использует sqlite3.Connection.backup для консистентности копии."""
        try:
            max_bak = self._get_max_backups()
            db_backup.perform_backup(self.db_path, BACKUP_DIR, max_bak)
        except Exception as e:
            logger.error("Ошибка создания резервной копии: %s", e, exc_info=True)
            raise DatabaseError(f"Не удалось создать резервную копию: {e}")

    def _get_max_backups(self) -> int:
        """Возвращает максимальное количество резервных копий из пользовательских настроек."""
        from app.config_data import app_config as _app_config

        return _app_config.settings.get_max_backups()

    def close(self):
        """Закрывает соединение с базой данных."""
        db_connection.close_connection(self.thread_local, logger, db_lock)

    def detect_case_insensitive_duplicates(self) -> dict:
        """Ищет case-insensitive дубликаты имён.

        Возвращает dict с ключами 'sphere', 'section', 'category'. Значения — список групп,
        где каждая группа описана как dict с полями:
          - scope: None | sphere_id | section_id
          - lname: нижний регистр имени
          - ids: список int ID записей в конфликте (в произвольном порядке)
        """
        return db_duplicates.detect_case_insensitive_duplicates(self.connection, db_lock)

    def resolve_case_insensitive_duplicates(self, strategy: str = "rename") -> dict:
        """Разрешает case-insensitive дубликаты.

        strategy:
          - 'rename': оставить запись с минимальным id, остальные переименовать, добавив ' (#{id})'.
          - 'remove': удалить все кроме записи с минимальным id.

        Возвращает отчёт: dict с количеством обработанных записей по таблицам.
        """
        if strategy not in {"rename", "remove"}:
            raise ValueError("Недопустимая стратегия: 'rename' или 'remove'")
        dups = self.detect_case_insensitive_duplicates()
        return db_duplicates.resolve_case_insensitive_duplicates(
            self.connection, db_lock, dups, strategy
        )

    def create_nocase_unique_indexes(self) -> None:
        """Пере-создаёт case-insensitive уникальные индексы для sphere/section/category.

        Полезно вызвать после устранения дубликатов, если индексы ранее не удалось создать.
        """
        db_duplicates.create_nocase_unique_indexes(self.connection, db_lock)


# === Вспомогательная функция апсерта категории и её ссылок (без транзакций) ===
def _upsert_category_tree(tree: dict, connection: sqlite3.Connection) -> None:
    """Выполняет апсерт категории и её ссылок, используя только переданное соединение.

    Требования:
    - Не открывает и не завершает транзакции (ожидается внешняя обёртка).
    - Не обращается к внешнему состоянию/моделям; работает с готовыми словарями.
    - Поведение для ссылок соответствует поштучным INSERT без временных таблиц:
      при конфликте по UNIQUE(category_id,name,url,args) извлекается существующий id
      без дополнительного обновления остальных полей.
    """
    if not tree:
        return

    cat = (tree or {}).get("category") or {}
    links = (tree or {}).get("links") or []
    if not isinstance(cat, dict) or not cat:
        return

    # --- Upsert категории с сохранением ID ---
    cat_id = cat.get("id")
    name = cat.get("name")
    section_id = cat.get("section_id")
    icon_path = cat.get("icon_path", "")
    position = cat.get("position", 0)

    if cat_id:
        cur = connection.execute(
            "UPDATE category SET name=?, section_id=?, icon_path=?, position=? WHERE id=?",
            (name, section_id, icon_path, position, cat_id),
        )
        if getattr(cur, "rowcount", 0) == 0:
            connection.execute(
                "INSERT INTO category (id, name, section_id, icon_path, position) VALUES (?, ?, ?, ?, ?)",
                (cat_id, name, section_id, icon_path, position),
            )
    else:
        cur = connection.execute(
            "INSERT INTO category (name, section_id, icon_path, position) VALUES (?, ?, ?, ?)",
            (name, section_id, icon_path, position),
        )
        try:
            cat_id = int(getattr(cur, "lastrowid", 0) or 0)
        except Exception:
            cat_id = None

    if not cat_id:
        return

    # --- Upsert ссылок для категории (поштучно, без вложенных транзакций) ---
    # Нормализация входных элементов и назначение category_id
    prepared_links: List[dict] = []
    for link in links or []:
        if not isinstance(link, dict):
            continue
        rec = dict(link)
        rec["category_id"] = cat_id
        # Нормализация значений по умолчанию
        rec["name"] = rec.get("name", "") or ""
        rec["url"] = rec.get("url", "") or ""
        rec["args"] = rec.get("args", "") or ""
        # Нормализация типа к строковому значению ('web', 'file', ...), на случай Enum
        try:
            rec["type"] = LinkType.from_value(rec.get("type", "web")).value
        except Exception:
            rec["type"] = LinkType.WEB.value
        rec["notes"] = rec.get("notes", "") or ""
        rec["is_favorite"] = int(rec.get("is_favorite", 0) or 0)
        rec["icon_path"] = rec.get("icon_path", "default.ico") or "default.ico"
        prepared_links.append(rec)

    if not prepared_links:
        return

    # Подготовка столбцов таблицы link
    all_fields = [
        "id",
        "category_id",
        "name",
        "url",
        "type",
        "notes",
        "is_favorite",
        "last_used",
        "icon_path",
        "args",
        "browser_key",
        "position",
    ]

    # Для вычисления позиции при необходимости будем кэшировать следующий position на категорию
    # (внутри одной категории cat_id один общий счётчик)
    # Стартовое значение: COALESCE(MAX(position), -1) + 1
    next_pos: Optional[int] = None

    def ensure_position(rec: dict) -> None:
        nonlocal next_pos
        if rec.get("position") is not None:
            return
        if next_pos is None:
            row = connection.execute(
                "SELECT COALESCE(MAX(position), 0) + 1 AS next_pos FROM link WHERE category_id=?",
                (cat_id,),
            ).fetchone()
            try:
                next_pos = int(dict(row)["next_pos"]) if row is not None else 0
            except Exception:
                next_pos = 0
        rec["position"] = next_pos
        next_pos += 1 if next_pos is not None else 1

    for rec in prepared_links:
        iid = rec.get("id")
        if iid:  # Обновление/восстановление по id
            # position по умолчанию 0 при обновлении, если None
            if rec.get("position") is None:
                rec["position"] = 0
            update_fields = [f for f in all_fields if f != "id"]
            update_placeholders = ", ".join([f"{f}=?" for f in update_fields])
            update_values = [rec.get(f) for f in update_fields]
            cur = connection.execute(
                f"UPDATE link SET {update_placeholders} WHERE id=?",
                tuple(update_values + [iid]),
            )
            if getattr(cur, "rowcount", 0) == 0:
                # Вставка с фиксированным id
                insert_fields = all_fields
                placeholders = ", ".join(["?"] * len(insert_fields))
                insert_values = [rec.get(f) for f in insert_fields]
                connection.execute(
                    f"INSERT INTO link ({', '.join(insert_fields)}) VALUES ({placeholders})",
                    tuple(insert_values),
                )
            continue

        # Новая запись: назначаем позицию при необходимости
        ensure_position(rec)
        columns = [f for f in all_fields if f != "id"]
        placeholders = ", ".join(["?"] * len(columns))
        values = [rec.get(c) for c in columns]
        try:
            cur = connection.execute(
                f"INSERT INTO link ({', '.join(columns)}) VALUES ({placeholders})",
                tuple(values),
            )
            # можно сохранить cur.lastrowid в rec["id"], если нужно далее
            try:
                new_id = int(getattr(cur, "lastrowid", 0) or 0)
                if new_id:
                    rec["id"] = new_id
            except Exception:
                pass
        except sqlite3.IntegrityError:
            # Дубликат по (category_id,name,url,args) — находим существующий id
            row = connection.execute(
                "SELECT id FROM link WHERE category_id=? AND name=? AND url=? AND args=?",
                (
                    rec.get("category_id"),
                    rec.get("name", ""),
                    rec.get("url", ""),
                    rec.get("args", ""),
                ),
            ).fetchone()
            if row:
                try:
                    rec["id"] = int(dict(row)["id"])  # stable key-based access
                except Exception:
                    pass


def _log_duplicates_human(dups: dict) -> None:
    logger.info("== Дубликаты (регистронезависимые) ==")
    for table in ("sphere", "section", "category"):
        groups = dups.get(table, []) or []
        logger.info("%s: %s групп(ы)", table, len(groups))
        for g in groups:
            scope = g.get("scope")
            lname = g.get("lname")
            ids = ",".join(str(i) for i in g.get("ids", []))
            logger.info("  - scope=%s, lname='%s', ids=[%s]", scope, lname, ids)

