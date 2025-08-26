import datetime
import logging
import sqlite3
import threading
from pathlib import Path
from typing import Dict, List, Optional

from app.config_data import app_config
from app.utils.db.synchronization import db_lock

from .category_model import CategoryModel
from .db_base import VALID_POSITION_TABLES, DatabaseBase, DatabaseError, ValidationError
from .link_model import LinkModel
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
                self.connection.commit()
            logger.info("Схема базы данных инициализирована")
        except Exception as e:
            logger.error(f"Ошибка инициализации схемы: {e}")
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
                    self.connection.commit()
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
                            self.connection.commit()
                            logger.info("Миграция link завершена успешно")
                        except Exception as inner:
                            self.connection.execute("ROLLBACK")
                            logger.error(f"Ошибка миграции таблицы link: {inner}")
                            # не пробрасываем исключение, чтобы не падало приложение
            except Exception as mig_err:
                logger.error(
                    f"Ошибка при подготовке миграции уникальности link: {mig_err}"
                )
        except Exception as e:
            logger.error(f"Ошибка выполнения миграций: {e}")
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

        try:
            with self.connection:
                for i, item_id in enumerate(ids_in_order):
                    self.connection.execute(
                        f"UPDATE {table_name} SET position = ? WHERE id = ?",
                        (i, item_id),
                    )
            logger.debug(f"Обновлены позиции в таблице {table_name}")
        except Exception as e:
            logger.error(f"Ошибка обновления позиций в таблице {table_name}: {e}")
            raise DatabaseError(f"Не удалось обновить позиции: {e}")

    # Методы импорта/экспорта
    def export_full_structure(self) -> Dict[str, List]:
        """Экспортирует всю структуру данных из БД в виде словаря."""
        try:
            spheres_data = []
            spheres = self.connection.execute(
                "SELECT * FROM sphere ORDER BY position"
            ).fetchall()

            for sphere_row in spheres:
                sphere = dict(sphere_row)
                sections_data = []
                sections = self.connection.execute(
                    "SELECT * FROM section WHERE sphere_id=? ORDER BY position",
                    (sphere["id"],),
                ).fetchall()

                for section_row in sections:
                    section = dict(section_row)
                    categories_data = []
                    categories = self.connection.execute(
                        "SELECT * FROM category WHERE section_id=? ORDER BY position",
                        (section["id"],),
                    ).fetchall()

                    for category_row in categories:
                        category = dict(category_row)
                        links = self.connection.execute(
                            "SELECT * FROM link WHERE category_id=? ORDER BY position",
                            (category["id"],),
                        ).fetchall()
                        category["links"] = [dict(link) for link in links]
                        categories_data.append(category)

                    section["categories"] = categories_data
                    sections_data.append(section)

                sphere["sections"] = sections_data
                spheres_data.append(sphere)

            logger.info("Экспорт структуры выполнен успешно")
            return {"spheres": spheres_data}
        except Exception as e:
            logger.error(f"Ошибка экспорта структуры: {e}")
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
            logger.error(f"Ошибка получения полной структуры: {e}")
            raise DatabaseError(f"Не удалось получить полную структуру: {e}")

    def import_full_structure(self, data: List[Dict]):
        """Очищает базу и импортирует данные из структуры."""
        try:
            with self.connection:
                # Очищаем таблицы в правильном порядке
                self.connection.execute("DELETE FROM link")
                self.connection.execute("DELETE FROM category")
                self.connection.execute("DELETE FROM section")
                self.connection.execute("DELETE FROM sphere")

                # Вставляем данные
                for sphere_data in data:
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
                    f"Не удалось создать резервную копию после импорта: {backup_err}"
                )
        except Exception as e:
            logger.error(f"Ошибка импорта структуры: {e}")
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
                        f"Не удалось удалить старую резервную копию {old_file}: {del_err}"
                    )
                    break  # Не зависаем, если файл занят — выходим из цикла
            logger.info(f"Создана резервная копия: {dst}")
        except Exception as e:
            logger.error(f"Ошибка создания резервной копии: {e}")
            raise DatabaseError(f"Не удалось создать резервную копию: {e}")

    def _get_max_backups(self) -> int:
        """Возвращает максимальное количество резервных копий из пользовательских настроек."""
        from app.config_data import app_config
        return app_config.get_max_backups()

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
        # Вставляем/обновляем сам раздел
        self.sections.upsert_section(tree["section"])
        # Восстанавливаем категории и их ссылки
        for item in tree.get("categories", []):
            cat = item.get("category", {})
            links = item.get("links", [])
            if cat:
                self.categories.upsert_category(cat)
            for link in links:
                self.links.upsert_link(link)

    def export_category_tree(self, category_id: int) -> dict:
        """Экспортирует категорию вместе со всеми ссылками."""
        cat = self.categories.get_category_by_id(category_id) or {}
        links = self.links.get_links(category_id)
        return {"category": cat, "links": links}

    def import_category_tree(self, tree: dict):
        """Восстанавливает категорию и все ссылки из backup-структуры."""
        self.categories.upsert_category(tree["category"])
        for link in tree["links"]:
            self.links.upsert_link(link)

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
                    cat = (tree or {}).get("category") or {}
                    if not cat:
                        continue
                    # --- Upsert категории с сохранением ID ---
                    # Поля категории
                    cat_id = cat.get("id")
                    name = cat.get("name")
                    section_id = cat.get("section_id")
                    icon_path = cat.get("icon_path", "")
                    position = cat.get("position", 0)

                    if cat_id:
                        cur = self.connection.execute(
                            "UPDATE category SET name=?, section_id=?, icon_path=?, position=? WHERE id=?",
                            (name, section_id, icon_path, position, cat_id),
                        )
                        if cur.rowcount == 0:
                            # Вставка с заданным ID (восстановление)
                            self.connection.execute(
                                "INSERT INTO category (id, name, section_id, icon_path, position) VALUES (?, ?, ?, ?, ?)",
                                (cat_id, name, section_id, icon_path, position),
                            )
                    else:
                        # Без ID — обычная вставка, позицию оставляем как в бэкапе
                        cur = self.connection.execute(
                            "INSERT INTO category (name, section_id, icon_path, position) VALUES (?, ?, ?, ?)",
                            (name, section_id, icon_path, position),
                        )
                        cat_id = cur.lastrowid

                    # --- Upsert ссылок для категории через LinkModel без собственной транзакции ---
                    raw_links = []
                    for link in (tree or {}).get("links", []) or []:
                        if not isinstance(link, dict):
                            continue
                        l = dict(link)
                        l["category_id"] = cat_id
                        raw_links.append(l)

                    # Переиспользуем единую логику апсерта без вложенных транзакций
                    if raw_links:
                        self.links._upsert_links_no_tx(raw_links)

            # Резервная копия после успешного bulk-импорта
            try:
                self.backup()
            except Exception as backup_err:
                logger.warning(
                    f"Не удалось создать резервную копию после bulk-импорта: {backup_err}"
                )
        except Exception as e:
            logger.error(f"Ошибка bulk-импорта деревьев категорий: {e}")
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
                        f"Ошибка WAL checkpoint при закрытии: {checkpoint_err}"
                    )

                self.thread_local.conn.close()
                del self.thread_local.conn
                logger.debug("Соединение с базой данных закрыто")
        except Exception as e:
            logger.error(f"Ошибка закрытия соединения: {e}")
