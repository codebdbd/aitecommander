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
from app.utils.db.synchronization import db_lock

from .category_model import CategoryModel
from .db_base import VALID_POSITION_TABLES, DatabaseBase, DatabaseError, ValidationError
from .link_model import LinkModel
from .link_type import LinkType
from .section_model import SectionModel
from .sphere_model import SphereModel

# Настройка логирования
logger = logging.getLogger(__name__)

# Пути к файлам
SCHEMA_PATH = Path(__file__).parent / "schema.sql"

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
            # Инициализация схемы и начальных данных, если БД новая
            if not DB_PATH.exists():
                self._init_schema()
                self.spheres.initialize_default_spheres()
            else:
                # Выполняем миграции для существующих БД
                self._run_migrations()
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
        conn = getattr(self.thread_local, "conn", None)
        if conn is not None:
            try:
                # Простая проверка, что соединение еще живо
                conn.execute("SELECT 1").fetchone()
                return conn
            except sqlite3.ProgrammingError:
                # Соединение было закрыто, нужно пересоздать
                self.close()

        # Создаем новое соединение
        self.thread_local.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.thread_local.conn.row_factory = sqlite3.Row
        self.thread_local.conn.execute("PRAGMA foreign_keys = ON")
        self.thread_local.conn.execute("PRAGMA journal_mode=WAL")
        return self.thread_local.conn

    def _init_schema(self):
        """Инициализирует схему базы данных из файла schema.sql."""
        try:
            sql = SCHEMA_PATH.read_text(encoding="utf-8")
            with db_lock:
                self.connection.executescript(sql)
                self.commit()
            logger.info("Схема базы данных инициализирована")
        except Exception as e:
            logger.error("Ошибка инициализации схемы: %s", e, exc_info=True)
            raise DatabaseError(f"Не удалось инициализировать схему базы данных: {e}")

    def _run_migrations(self):
        """Выполняет миграции для существующих баз данных."""
        try:
            # Миграция: добавление поля browser_key в таблицу link
            try:
                with db_lock:
                    self.connection.execute(
                        "ALTER TABLE link ADD COLUMN browser_key TEXT DEFAULT NULL"
                    )
                    self.commit()
                logger.info("Миграция: добавлено поле browser_key в таблицу link")
            except sqlite3.OperationalError as e:
                if "duplicate column name" in str(e).lower():
                    logger.debug("Поле browser_key уже существует в таблице link")
                else:
                    raise

            # Миграция: изменить уникальность с (category_id,url,args,type) на (category_id,name,url,args)
            try:
                with db_lock:
                    # Проверяем текущие уникальные индексы таблицы link
                    idx_list = self.connection.execute(
                        "PRAGMA index_list('link')"
                    ).fetchall()
                    need_migrate = False
                    for idx in idx_list:
                        # row: seq, name, unique, origin, partial
                        if idx[2] == 1:  # unique
                            cols = self.connection.execute(
                                f"PRAGMA index_info('{idx[1]}')"
                            ).fetchall()
                            col_names = [c[2] for c in cols]
                            if col_names == ["category_id", "url", "args", "type"]:
                                need_migrate = True
                                break

                    if need_migrate:
                        logger.info(
                            "Миграция: пересоздание link с UNIQUE(category_id,name,url,args)"
                        )
                        self.connection.execute("BEGIN TRANSACTION")
                        try:
                            # Создаем новую таблицу c нужным UNIQUE
                            self.connection.execute(
                                """
                                CREATE TABLE IF NOT EXISTS link_new (
                                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                                    category_id  INTEGER NOT NULL REFERENCES category(id) ON DELETE CASCADE,
                                    name         TEXT    NOT NULL,
                                    url          TEXT    NOT NULL,
                                    type         TEXT    NOT NULL CHECK(type IN ('web','file','program','script','chromeapp','folder')),
                                    notes        TEXT    DEFAULT '',
                                    is_favorite  INTEGER NOT NULL CHECK(is_favorite IN (0,1)) DEFAULT 0,
                                    last_used    TEXT    DEFAULT NULL,
                                    icon_path    TEXT    NOT NULL DEFAULT 'default.ico',
                                    args         TEXT    DEFAULT '',
                                    browser_key  TEXT    DEFAULT NULL,
                                    position     INTEGER NOT NULL DEFAULT 0,
                                    UNIQUE(category_id, name, url, args)
                                )
                                """
                            )

                            # Перенос данных
                            self.connection.execute(
                                """
                                INSERT OR IGNORE INTO link_new 
                                    (id, category_id, name, url, type, notes, is_favorite, last_used, icon_path, args, browser_key, position)
                                SELECT id, category_id, name, url, type, notes, is_favorite, last_used, icon_path, args, browser_key, position
                                FROM link
                                """
                            )

                            # Заменяем таблицы
                            self.connection.execute("DROP TABLE link")
                            self.connection.execute(
                                "ALTER TABLE link_new RENAME TO link"
                            )
                            self.commit()
                            logger.info("Миграция link завершена успешно")
                        except Exception as inner:
                            self.rollback()
                            logger.error(
                                "Ошибка миграции таблицы link: %s", inner, exc_info=True
                            )
                            # не пробрасываем исключение, чтобы не падало приложение
            except Exception as mig_err:
                logger.error(
                    "Ошибка при подготовке миграции уникальности link: %s",
                    mig_err,
                    exc_info=True,
                )
            # Миграция: добавить уникальные индексы с COLLATE NOCASE для case-insensitive уникальности
            try:
                with db_lock:
                    # Для сфер: уникальность имени без учёта регистра
                    self.connection.execute(
                        """
                        CREATE UNIQUE INDEX IF NOT EXISTS idx_sphere_name_nocase
                        ON sphere(name COLLATE NOCASE)
                        """
                    )
                    # Для разделов: уникальность (sphere_id, name) без учёта регистра
                    self.connection.execute(
                        """
                        CREATE UNIQUE INDEX IF NOT EXISTS idx_section_sphere_name_nocase
                        ON section(sphere_id, name COLLATE NOCASE)
                        """
                    )
                    # Для категорий: уникальность (section_id, name) без учёта регистра
                    self.connection.execute(
                        """
                        CREATE UNIQUE INDEX IF NOT EXISTS idx_category_section_name_nocase
                        ON category(section_id, name COLLATE NOCASE)
                        """
                    )
                    self.commit()
                logger.info(
                    "Миграция: добавлены case-insensitive уникальные индексы для sphere/section/category"
                )
            except sqlite3.OperationalError as e:
                # Если в данных уже есть дубликаты, создание индекса упадёт — логируем и продолжаем
                logger.warning(
                    "Не удалось создать NOCASE-индексы (возможны дубликаты по регистру): %s",
                    e,
                    exc_info=True,
                )
        except Exception as e:
            logger.error("Ошибка выполнения миграций: %s", e, exc_info=True)
            # Не прерываем работу приложения из-за ошибок миграции

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
        if table_name not in VALID_POSITION_TABLES:
            raise ValidationError(
                f"Недопустимое имя таблицы для обновления позиций: {table_name}"
            )

        # Валидация входных ID: типы, уникальность, существование
        try:
            ids = list(ids_in_order or [])
            if not ids:
                # Нечего обновлять — выходим без ошибок
                logger.debug(
                    "update_item_positions: пустой список ID для таблицы %s",
                    table_name,
                )
                return

            # Проверка типов и значений
            for v in ids:
                if isinstance(v, bool) or not isinstance(v, int) or v < 0:
                    raise ValidationError(f"Некорректный ID в списке позиций: {v}")

            # Проверка уникальности
            if len(set(ids)) != len(ids):
                raise ValidationError("Список ID содержит дубликаты")

            # Проверка существования и обновление выполняются под ЕДИНЫМ db_lock
            with db_lock:
                _t0 = time.perf_counter()
                # --- Проверка существования записей (чанками, чтобы не превысить лимит параметров SQLite ~999)
                existing_ids = set()
                SELECT_CHUNK = 900
                for s in range(0, len(ids), SELECT_CHUNK):
                    part = ids[s : s + SELECT_CHUNK]
                    placeholders = ",".join(["?"] * len(part))
                    rows = self.connection.execute(
                        f"SELECT id FROM {table_name} WHERE id IN ({placeholders})",
                        tuple(part),
                    ).fetchall()
                    existing_ids.update(row[0] for row in rows)
                missing = [i for i in ids if i not in existing_ids]
                if missing:
                    raise ValidationError(
                        f"Не найдены записи с ID: {missing} в таблице {table_name}"
                    )

                # --- Пакетное обновление позиций ---
                # Формируем пары (id, position) согласно порядку в ids
                id_pos_pairs = [(item_id, i) for i, item_id in enumerate(ids)]
                # Ограничение SQLite по количеству параметров по умолчанию ~999 — по 2 параметра на запись
                CHUNK_SIZE = 400
                with self.connection:
                    batches = 0
                    for start in range(0, len(id_pos_pairs), CHUNK_SIZE):
                        chunk = id_pos_pairs[start : start + CHUNK_SIZE]
                        # Подготавливаем VALUES плейсхолдеры и параметры (id, position)
                        values_sql = ",".join(["(?,?)"] * len(chunk))
                        params = []
                        for _id, pos in chunk:
                            params.extend([_id, pos])

                        sql = f"""
                            WITH newpos(id, position) AS (
                                VALUES {values_sql}
                            )
                            UPDATE {table_name}
                            SET position = (
                                SELECT newpos.position FROM newpos WHERE newpos.id = {table_name}.id
                            )
                            WHERE id IN (SELECT id FROM newpos)
                            """
                        self.connection.execute(sql, tuple(params))
                        batches += 1
                _t1 = time.perf_counter()
                logger.debug(
                    "update_item_positions: table=%s, count=%d, batches=%d, chunk=%d, duration_ms=%.2f",
                    table_name,
                    len(ids),
                    batches,
                    CHUNK_SIZE,
                    ("%.2f" % ((_t1 - _t0) * 1000.0)),
                )
            logger.debug(
                "Обновлены позиции (%s шт.) в таблице %s",
                len(ids),
                table_name,
            )
        except ValidationError:
            # Ошибки валидации входных данных пробрасываем как есть
            raise
        except Exception as e:
            logger.error(
                "Ошибка обновления позиций в таблице %s: %s",
                table_name,
                e,
                exc_info=True,
            )
            raise DatabaseError(f"Не удалось обновить позиции: {e}")

    # Методы импорта/экспорта
    def export_full_structure(self) -> Dict[str, List]:
        """Экспортирует всю структуру данных из БД в виде словаря."""
        try:
            # Загружаем все таблицы одной выборкой каждую под единой блокировкой
            t0 = time.perf_counter()
            with db_lock:
                spheres = self.connection.execute(
                    "SELECT * FROM sphere ORDER BY position"
                ).fetchall()
                sections = self.connection.execute(
                    "SELECT * FROM section ORDER BY position"
                ).fetchall()
                categories = self.connection.execute(
                    "SELECT * FROM category ORDER BY position"
                ).fetchall()
                links = self.connection.execute(
                    "SELECT * FROM link ORDER BY position"
                ).fetchall()
            t1 = time.perf_counter()

            # Подготовка индексов для сборки структуры
            spheres_by_id = {}
            sections_by_id = {}
            categories_by_id = {}

            sections_by_sphere = {}
            categories_by_section = {}

            # Преобразуем строки в dict и инициализируем контейнеры
            for s in spheres:
                sd = dict(s)
                sd["sections"] = []
                spheres_by_id[sd["id"]] = sd

            for sec in sections:
                sc = dict(sec)
                sc["categories"] = []
                sections_by_id[sc["id"]] = sc
                sections_by_sphere.setdefault(sc["sphere_id"], []).append(sc)

            for cat in categories:
                cd = dict(cat)
                cd["links"] = []
                categories_by_id[cd["id"]] = cd
                categories_by_section.setdefault(cd["section_id"], []).append(cd)

            # Линки просто добавляем к категориям
            for ln in links:
                ld = dict(ln)
                cat_id = ld.get("category_id")
                cat_obj = categories_by_id.get(cat_id)
                if cat_obj is not None:
                    cat_obj["links"].append(ld)

            # Собираем иерархию, сохраняя порядок по position (он уже в ORDER BY)
            spheres_data: List[Dict] = []
            for s in spheres:
                s_obj = spheres_by_id[s["id"]]
                # Добавляем секции в порядке их выборки (position)
                for sc in sections_by_sphere.get(s_obj["id"], []):
                    # Добавляем категории в порядке их выборки (position)
                    sc["categories"] = categories_by_section.get(sc["id"], [])
                    s_obj["sections"].append(sc)
                spheres_data.append(s_obj)

            t2 = time.perf_counter()
            total_ms = (t2 - t0) * 1000.0
            db_ms = (t1 - t0) * 1000.0
            build_ms = (t2 - t1) * 1000.0
            logger.debug(
                "export_full_structure: spheres=%d, sections=%d, categories=%d, links=%d, db_ms=%.2f, build_ms=%.2f, total_ms=%.2f",
                len(spheres),
                len(sections),
                len(categories),
                len(links),
                db_ms,
                build_ms,
                total_ms,
            )
            if total_ms > 50.0:
                logger.info(
                    "export_full_structure: завершено, total_ms=%.2f (>50ms), db_ms=%.2f, build_ms=%.2f",
                    total_ms,
                    db_ms,
                    build_ms,
                )
            else:
                logger.info("Экспорт структуры выполнен успешно (bulk-загрузка)")
            return {"spheres": spheres_data}
        except Exception as e:
            logger.error("Ошибка экспорта структуры: %s", e, exc_info=True)
            raise DatabaseError(f"Не удалось экспортировать структуру: {e}")

    def get_full_structure(self) -> List[Dict]:
        """Возвращает полную структуру данных в виде вложенных словарей."""
        try:
            spheres_data = []
            spheres = self.spheres.get_spheres()
            for sphere_row in spheres:
                # Модели возвращают dict — берём копию для безопасности
                sphere = sphere_row.copy()
                sphere["sections"] = []

                sections = self.sections.get_sections(sphere["id"])
                for section_row in sections:
                    section = section_row.copy()
                    section["categories"] = []

                    categories = self.categories.get_categories(section["id"])
                    for category_row in categories:
                        category = category_row.copy()
                        # Ссылки уже приходят списком dict — присваиваем напрямую
                        category["links"] = self.links.get_links(category["id"])

                        section["categories"].append(category)

                    sphere["sections"].append(section)

                spheres_data.append(sphere)

            return spheres_data
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
            # Создаем глубокую копию данных, чтобы не мутировать исходный объект
            data_copy = copy.deepcopy(data)

            with db_lock:  # Потокобезопасный доступ к базе данных
                with self.connection:
                    # Очищаем таблицы в правильном порядке
                    self.connection.execute("DELETE FROM link")
                    self.connection.execute("DELETE FROM category")
                    self.connection.execute("DELETE FROM section")
                    self.connection.execute("DELETE FROM sphere")

                    # Вставляем данные из копии
                    for sphere_data in data_copy:
                        sections = sphere_data.pop("sections", [])
                        self.spheres.upsert_sphere(sphere_data)

                        for section_data in sections:
                            categories = section_data.pop("categories", [])
                            self.sections.upsert_section(section_data)

                            for category_data in categories:
                                links = category_data.pop("links", [])
                                self.categories.upsert_category(category_data)

                                for link_data in links:
                                    self.links.upsert_link(link_data)

                logger.info("Импорт структуры выполнен успешно")
                # Создаем резервную копию после большой операции импорта
                try:
                    self.backup()
                except Exception as backup_err:
                    logger.warning(
                        "Не удалось создать резервную копию после импорта: %s",
                        backup_err,
                        exc_info=True,
                    )
        except Exception as e:
            logger.error("Ошибка импорта структуры: %s", e, exc_info=True)
            raise DatabaseError(f"Не удалось импортировать структуру: {e}")

    def backup(self):
        """Создаёт резервную копию базы данных и удаляет старые копии при превышении лимита.
        Использует sqlite3.Connection.backup для консистентности копии."""
        try:
            now = datetime.datetime.now()
            timestamp = now.strftime("%Y%m%d_%H%M%S_%f")
            dst = BACKUP_DIR / f"links_{timestamp}.db"
            with sqlite3.connect(self.db_path) as src, sqlite3.connect(dst) as dest:
                src.backup(dest)
            max_bak = self._get_max_backups()
            files = sorted(BACKUP_DIR.glob("links_*.db"))
            while len(files) > max_bak:
                old_file = files.pop(0)
                try:
                    old_file.unlink()
                except Exception as del_err:
                    logger.warning(
                        "Не удалось удалить старую резервную копию %s: %s",
                        old_file,
                        del_err,
                        exc_info=True,
                    )
                    break  # Не зависаем, если файл занят — выходим из цикла
            logger.info("Создана резервная копия: %s", dst)
        except Exception as e:
            logger.error("Ошибка создания резервной копии: %s", e, exc_info=True)
            raise DatabaseError(f"Не удалось создать резервную копию: {e}")

    def _get_max_backups(self) -> int:
        """Возвращает максимальное количество резервных копий из пользовательских настроек."""
        from app.config_data import app_config

        return app_config.settings.get_max_backups()

    def export_section_tree(self, section_id: int) -> dict:
        """Экспортирует раздел вместе со всеми категориями и ссылками."""
        section = self.sections.get_section_by_id(section_id) or {}
        categories = []
        for cat_row in self.categories.get_categories(section_id):
            cat = cat_row.copy()
            links = self.links.get_links(cat["id"])  # уже список dict
            categories.append({"category": cat, "links": links})
        return {"section": section, "categories": categories}

    def import_section_tree(self, tree: dict):
        """Восстанавливает раздел, его категории и все ссылки из backup-структуры."""
        section = (tree or {}).get("section") or {}
        categories = (tree or {}).get("categories") or []
        if not section:
            return

        # Одна транзакция на весь импорт раздела
        with self.connection:
            # --- Upsert раздела с сохранением ID ---
            sec_id = section.get("id")
            name = section.get("name")
            sphere_id = section.get("sphere_id")
            icon_path = section.get("icon_path", "")
            position = section.get("position", 0)

            if sec_id:
                cur = self.connection.execute(
                    "UPDATE section SET name=?, sphere_id=?, icon_path=?, position=? WHERE id=?",
                    (name, sphere_id, icon_path, position, sec_id),
                )
                if cur.rowcount == 0:
                    self.connection.execute(
                        "INSERT INTO section (id, name, sphere_id, icon_path, position) VALUES (?, ?, ?, ?, ?)",
                        (sec_id, name, sphere_id, icon_path, position),
                    )
            else:
                cur = self.connection.execute(
                    "INSERT INTO section (name, sphere_id, icon_path, position) VALUES (?, ?, ?, ?)",
                    (name, sphere_id, icon_path, position),
                )
                sec_id = cur.lastrowid

            # --- Восстановление категорий и их ссылок ---
            for item in categories:
                cat = (item or {}).get("category") or {}
                if not cat:
                    continue
                links = (item or {}).get("links") or []

                cat_id = cat.get("id")
                c_name = cat.get("name")
                c_section_id = cat.get("section_id", sec_id)
                c_icon_path = cat.get("icon_path", "")
                c_position = cat.get("position", 0)

                if cat_id:
                    ccur = self.connection.execute(
                        "UPDATE category SET name=?, section_id=?, icon_path=?, position=? WHERE id=?",
                        (c_name, c_section_id, c_icon_path, c_position, cat_id),
                    )
                    if ccur.rowcount == 0:
                        self.connection.execute(
                            "INSERT INTO category (id, name, section_id, icon_path, position) VALUES (?, ?, ?, ?, ?)",
                            (cat_id, c_name, c_section_id, c_icon_path, c_position),
                        )
                else:
                    ccur = self.connection.execute(
                        "INSERT INTO category (name, section_id, icon_path, position) VALUES (?, ?, ?, ?)",
                        (c_name, c_section_id, c_icon_path, c_position),
                    )
                    cat_id = ccur.lastrowid

                # Upsert ссылок для категории без вложенных транзакций
                raw_links = []
                for link in links:
                    if not isinstance(link, dict):
                        continue
                    link_copy = dict(link)
                    link_copy["category_id"] = cat_id
                    raw_links.append(link_copy)
                if raw_links:
                    self.links._upsert_links_no_tx(raw_links)

    def export_category_tree(self, category_id: int) -> dict:
        """Экспортирует категорию вместе со всеми ссылками."""
        cat = self.categories.get_category_by_id(category_id) or {}
        links = self.links.get_links(category_id)
        return {"category": cat, "links": links}

    def import_category_tree(self, tree: dict):
        """Восстанавливает категорию и все ссылки из backup-структуры."""
        with self.connection:
            _upsert_category_tree(tree, self.connection)

    def import_category_trees_bulk(self, trees: List[dict]) -> None:
        """Импортирует несколько поддеревьев категорий в ОДНОЙ транзакции.

        Требования:
        - Атомарность: одна транзакция на весь импорт.
        - Сохранение ID категорий и ссылок, если они заданы в данных.
        - Без вложенных транзакций: не использовать методы моделей, которые
          выполняют commit() или открывают свою транзакцию.
        - Толерантность к дубликатам ссылок по UNIQUE(category_id,name,url,args):
          при конфликте обновляем остальные поля существующей записи.
        """
        if not trees:
            return

        try:
            with self.connection:  # Единая транзакция на весь импорт
                for tree in trees:
                    if not tree:
                        continue
                    _upsert_category_tree(tree, self.connection)

            # Резервная копия после успешного bulk-импорта
            try:
                self.backup()
            except Exception as backup_err:
                logger.warning(
                    "Не удалось создать резервную копию после bulk-импорта: %s",
                    backup_err,
                )
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

    def close(self):
        """Закрывает соединение с базой данных."""
        try:
            if hasattr(self.thread_local, "conn"):
                # Выполняем WAL checkpoint перед закрытием для корректного восстановления
                try:
                    with db_lock:
                        self.thread_local.conn.execute("PRAGMA wal_checkpoint(FULL)")
                        self.thread_local.conn.commit()
                    logger.debug("WAL checkpoint выполнен перед закрытием")
                except Exception as checkpoint_err:
                    logger.warning(
                        "Ошибка WAL checkpoint при закрытии: %s",
                        checkpoint_err,
                        exc_info=True,
                    )

                self.thread_local.conn.close()
                del self.thread_local.conn
                logger.debug("Соединение с базой данных закрыто")
        except Exception as e:
            logger.error("Ошибка закрытия соединения: %s", e, exc_info=True)

    def detect_case_insensitive_duplicates(self) -> dict:
        """Ищет case-insensitive дубликаты имён.

        Возвращает dict с ключами 'sphere', 'section', 'category'. Значения — список групп,
        где каждая группа описана как dict с полями:
          - scope: None | sphere_id | section_id
          - lname: нижний регистр имени
          - ids: список int ID записей в конфликте (в произвольном порядке)
        """
        result = {"sphere": [], "section": [], "category": []}
        with db_lock:
            # Сферы: глобальная область
            rows = self.connection.execute(
                """
                SELECT LOWER(name) AS lname, GROUP_CONCAT(id) AS ids, COUNT(*) AS cnt
                FROM sphere
                GROUP BY LOWER(name)
                HAVING cnt > 1
                """
            ).fetchall()
            for r in rows or []:
                ids = [int(x) for x in (r["ids"] or "").split(",") if x]
                result["sphere"].append(
                    {"scope": None, "lname": r["lname"], "ids": ids}
                )

            # Разделы: внутри одной сферы
            rows = self.connection.execute(
                """
                SELECT sphere_id AS scope, LOWER(name) AS lname, GROUP_CONCAT(id) AS ids, COUNT(*) AS cnt
                FROM section
                GROUP BY sphere_id, LOWER(name)
                HAVING cnt > 1
                """
            ).fetchall()
            for r in rows or []:
                ids = [int(x) for x in (r["ids"] or "").split(",") if x]
                result["section"].append(
                    {"scope": int(r["scope"]), "lname": r["lname"], "ids": ids}
                )

            # Категории: внутри одного раздела
            rows = self.connection.execute(
                """
                SELECT section_id AS scope, LOWER(name) AS lname, GROUP_CONCAT(id) AS ids, COUNT(*) AS cnt
                FROM category
                GROUP BY section_id, LOWER(name)
                HAVING cnt > 1
                """
            ).fetchall()
            for r in rows or []:
                ids = [int(x) for x in (r["ids"] or "").split(",") if x]
                result["category"].append(
                    {"scope": int(r["scope"]), "lname": r["lname"], "ids": ids}
                )

        return result

    def resolve_case_insensitive_duplicates(self, strategy: str = "rename") -> dict:
        """Разрешает case-insensitive дубликаты.

        strategy:
          - 'rename': оставить запись с минимальным id, остальные переименовать, добавив ' (#{id})'.
          - 'remove': удалить все кроме записи с минимальным id.

        Возвращает отчёт: dict с количеством обработанных записей по таблицам.
        """
        if strategy not in {"rename", "remove"}:
            raise ValueError("Недопустимая стратегия: 'rename' или 'remove'")

        report = {"sphere": 0, "section": 0, "category": 0}
        dups = self.detect_case_insensitive_duplicates()

        with db_lock:
            with self.connection:
                # Вспомогательная функция получить текущее имя по id/таблице
                def get_name(table: str, rec_id: int) -> str:
                    row = self.connection.execute(
                        f"SELECT name FROM {table} WHERE id=?", (rec_id,)
                    ).fetchone()
                    return row[0] if row else ""

                # Обработчик группы
                def process_group(table: str, ids: list[int]):
                    ids_sorted = sorted(int(i) for i in ids)
                    _keep = ids_sorted[0]
                    to_change = ids_sorted[1:]
                    affected = 0
                    if strategy == "rename":
                        for rid in to_change:
                            base_name = get_name(table, rid)
                            new_name = f"{base_name} (#{rid})"
                            self.connection.execute(
                                f"UPDATE {table} SET name=? WHERE id=?", (new_name, rid)
                            )
                            affected += 1
                    else:  # remove
                        for rid in to_change:
                            self.connection.execute(
                                f"DELETE FROM {table} WHERE id=?", (rid,)
                            )
                            affected += 1
                    return affected

                for grp in dups.get("sphere", []):
                    report["sphere"] += process_group("sphere", grp["ids"])
                for grp in dups.get("section", []):
                    report["section"] += process_group("section", grp["ids"])
                for grp in dups.get("category", []):
                    report["category"] += process_group("category", grp["ids"])

        return report

    def create_nocase_unique_indexes(self) -> None:
        """Пере-создаёт case-insensitive уникальные индексы для sphere/section/category.

        Полезно вызвать после устранения дубликатов, если индексы ранее не удалось создать.
        """
        with db_lock:
            self.connection.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_sphere_name_nocase
                ON sphere(name COLLATE NOCASE)
                """
            )
            self.connection.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_section_sphere_name_nocase
                ON section(sphere_id, name COLLATE NOCASE)
                """
            )
            self.connection.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_category_section_name_nocase
                ON category(section_id, name COLLATE NOCASE)
                """
            )
            self.commit()


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
                "SELECT COALESCE(MAX(position), -1) + 1 FROM link WHERE category_id=?",
                (cat_id,),
            ).fetchone()
            try:
                next_pos = int(row[0]) if row is not None else 0
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
                    rec["id"] = int(row[0] if isinstance(row, tuple) else row["id"])  # type: ignore[index]
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


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.models.db",
        description="CLI для диагностики и устранения регистронезависимых дубликатов и обслуживания БД",
    )

    mx = parser.add_mutually_exclusive_group(required=True)
    mx.add_argument(
        "--detect-duplicates",
        action="store_true",
        help="Найти case-insensitive дубликаты (sphere/section/category)",
    )
    mx.add_argument(
        "--resolve-duplicates",
        choices=["rename", "remove"],
        help="Разрешить дубликаты стратегией: rename (переименовать) или remove (удалить)",
    )
    mx.add_argument(
        "--create-indexes",
        action="store_true",
        help="Создать уникальные индексы с COLLATE NOCASE (если их нет)",
    )
    mx.add_argument(
        "--backup",
        action="store_true",
        help="Создать резервную копию БД",
    )

    parser.add_argument(
        "--json",
        action="store_true",
        help="Вывод в JSON (для detect/resolve)",
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default=None,
        help="Путь к файлу БД (по умолчанию — из настроек приложения)",
    )
    parser.add_argument(
        "--create-indexes-after",
        action="store_true",
        help="После resolve запустить создание NOCASE-индексов",
    )

    args = parser.parse_args(argv)

    try:
        with Database() as db:
            if args.db_path:
                db.db_path = args.db_path

            if args.detect_duplicates:
                dups = db.detect_case_insensitive_duplicates()
                if args.json:
                    logger.info(json.dumps(dups, ensure_ascii=False, indent=2))
                else:
                    _log_duplicates_human(dups)
                return 0

            if args.resolve_duplicates:
                report = db.resolve_case_insensitive_duplicates(args.resolve_duplicates)
                if args.create_indexes_after:
                    db.create_nocase_unique_indexes()
                if args.json:
                    logger.info(json.dumps(report, ensure_ascii=False, indent=2))
                else:
                    logger.info("== Итог resolve ==")
                    for k, v in (report or {}).items():
                        logger.info("%s: %s", k, v)
                return 0

            if args.create_indexes:
                db.create_nocase_unique_indexes()
                logger.info("NOCASE-индексы созданы (если отсутствовали)")
                return 0

            if args.backup:
                db.backup()
                logger.info("Резервная копия создана")
                return 0

            parser.print_help()
            return 0
    except Exception as e:
        logger.error("CLI ошибка: %s", e)
        logger.error("Ошибка: %s", e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
