import logging
import sqlite3
import threading
import time
import warnings
from pathlib import Path
from typing import Dict, List, Optional, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from PyQt6.QtCore import QObject

from PyQt6.QtCore import QObject, QThreadPool, pyqtSignal

from app.config_data import app_config
from app.utils.db.migrations import MigrationRunner
from .managers.backup_manager import BackupManager
from .managers.import_export_manager import ImportExportManager
from .managers.duplicate_resolver import DuplicateResolver
from .managers.structure_manager import StructureManager
from .types.constants import (
    SQLITE_SAFE_BATCH_SIZE,
    SQLITE_SAFE_SELECT_CHUNK,
)
from .base.db_base import DatabaseBase, DatabaseError, ValidationError, db_lock
from .entities.sphere_model import SphereModel
from .entities.section_model import SectionModel
from .entities.category_model import CategoryModel
from .entities.link_model import LinkModel

logger = logging.getLogger(__name__)

# Пути к файлам
SCHEMA_PATH = Path(__file__).parent / "schema.sql"
MIGRATIONS_DIR = Path(__file__).parent / "migrations"

# Пути к базе данных из централизованной конфигурации
PATHS = app_config.paths
DB_PATH = PATHS.get_db_path()
BACKUP_DIR = PATHS.get_backups_dir()


class Database(QObject):
    """Главный класс для работы с базой данных.
    
    Наследуется от QObject для поддержки Qt сигналов и реактивного обновления UI.
    Использует композицию для доступа к базовым операциям БД.
    """
    
    # Qt сигналы для уведомления UI об изменениях данных
    data_changed = pyqtSignal(str, str, list)  # table_name, operation, affected_ids
    structure_loaded = pyqtSignal()  # Структура загружена/импортирована
    backup_created = pyqtSignal(str)  # backup_path
    error_occurred = pyqtSignal(str, str)  # title, message
    
    # Сигналы прогресса длительных операций
    operation_started = pyqtSignal(str, int)  # operation_name, total_items
    operation_progress = pyqtSignal(str, int, int, str)  # operation_name, current, total, message
    operation_finished = pyqtSignal(str, bool)  # operation_name, success
    warning_occurred = pyqtSignal(str, str)  # title, message
    
    def __init__(self, parent: Optional[QObject] = None):
        """Инициализирует Database.
        
        ✅ ИСПРАВЛЕНИЕ: Добавлен parent параметр для правильного управления памятью.
        
        Args:
            parent: Родительский QObject (опционально)
        """
        # Инициализируем QObject с parent
        super().__init__(parent)
        
        self.db_path = str(DB_PATH)
        self.thread_local = threading.local()
        
        # Композиция вместо наследования от DatabaseBase
        self._base = DatabaseBase(self)
        
        # Thread pool для асинхронных операций
        self._thread_pool = QThreadPool.globalInstance()
        max_threads = app_config.get("threading.max_db_threads", 4)
        self._thread_pool.setMaxThreadCount(max_threads)

        # Инициализируем модели после полной инициализации Database
        # ✅ ИСПРАВЛЕНИЕ: Модели не являются QObject, parent не нужен
        self.spheres = SphereModel(self)
        self.sections = SectionModel(self)
        self.categories = CategoryModel(self)
        self.links = LinkModel(self)
        
        # Инициализируем менеджеры
        self.backup_manager = BackupManager(self)
        self.import_export_manager = ImportExportManager(self)
        self.duplicate_resolver = DuplicateResolver(self)
        self.structure_manager = StructureManager(self)
        
        # ✅ Флаг для отслеживания cleanup
        self._cleaned_up = False
    
    # Делегируем методы DatabaseBase через композицию
    def commit(self) -> None:
        """Фиксирует текущую транзакцию."""
        return self._base.commit()
    
    def rollback(self) -> None:
        """Откатывает текущую транзакцию."""
        return self._base.rollback()
    
    def transaction(self):
        """Контекстный менеджер транзакции с автоматическим commit/rollback."""
        return self._base.transaction()

    def prepare_dirs(self) -> None:
        """Создаёт необходимые пользовательские каталоги для данных.

        Вызывать в фоне до первой работы с БД, чтобы не блокировать UI.
        """
        PATHS.ensure_user_data_dirs()

    def initialize_or_migrate(self) -> None:
        """Инициализирует новую БД или выполняет миграции для существующей.

        .. deprecated::
            Используйте :meth:`initialize_or_migrate_async` для предотвращения блокировки UI.
        
        Тяжёлая операция: запускать в фоне (QRunnable) с использованием глобальной
        блокировки `db_lock` внутри методов, где это необходимо.
        """
        warnings.warn(
            "Метод initialize_or_migrate() устарел. Используйте initialize_or_migrate_async().",
            DeprecationWarning,
            stacklevel=2
        )
        operation = "initialize_or_migrate"
        try:
            self.operation_started.emit(operation, 1)
            is_new = not DB_PATH.exists()
            # Запускаем миграции через MigrationRunner (создаст схему через 0001_init)
            with db_lock:
                self.operation_progress.emit(operation, 0, 1, "Применение миграций...")
                runner = MigrationRunner(self.connection, MIGRATIONS_DIR)
                applied = runner.run_all_pending()
                logger.info("Миграции применены: %d", applied)

            # Инициализация дефолтных данных для новой базы (после миграций)
            if is_new:
                try:
                    self.operation_progress.emit(operation, 1, 1, "Инициализация дефолтных данных...")
                    self.spheres.initialize_default_spheres()
                except Exception as init_err:
                    logger.warning(
                        "Не удалось инициализировать дефолтные сферы: %s",
                        init_err,
                        exc_info=True,
                    )
            self.operation_finished.emit(operation, True)
        except Exception as e:
            self.operation_finished.emit(operation, False)
            raise
        finally:
            # Закрываем соединение текущего потока (например, воркера),
            # чтобы не держать открытым соединение из фонового потока.
            try:
                self.close()
            except Exception:
                pass
    
    def initialize_or_migrate_async(
        self,
        on_finished: Optional[Callable] = None,
        on_error: Optional[Callable] = None,
        on_progress: Optional[Callable] = None
    ):
        """Инициализирует БД в фоновом потоке (РЕКОМЕНДУЕТСЯ).
        
        ✅ ИСПРАВЛЕНИЕ: Добавлен async метод для предотвращения блокировки UI.
        
        Args:
            on_finished: Callback при завершении (stats: {is_new: bool, migrations_applied: int})
            on_error: Callback при ошибке (exception, traceback)
            on_progress: Callback для прогресса (current, total, message)
            
        Example:
            >>> def on_done(stats):
            ...     print(f"Migrations applied: {stats['migrations_applied']}")
            >>> db.initialize_or_migrate_async(on_finished=on_done)
        """
        from .workers import InitializationWorker
        
        worker = InitializationWorker(self.db_path, MIGRATIONS_DIR)
        
        # Подключаем внутренние сигналы Database
        worker.signals.finished.connect(
            lambda stats: self._safe_emit(self.operation_finished, "initialize_or_migrate", True)
        )
        worker.signals.error.connect(
            lambda e, tb: self._safe_emit(self.error_occurred, "Ошибка инициализации", str(e))
        )
        
        # Подключаем пользовательские callbacks
        if on_finished:
            worker.signals.finished.connect(on_finished)
        if on_error:
            worker.signals.error.connect(on_error)
        if on_progress:
            worker.signals.progress.connect(on_progress)
        
        self._thread_pool.start(worker)
        logger.info("Запущена асинхронная инициализация БД")
    
    def _safe_emit(self, signal: pyqtSignal, *args) -> None:
        """Безопасный эмит сигнала с проверкой QApplication.
        
        ✅ ИСПРАВЛЕНИЕ: Добавлена проверка QApplication.instance() перед эмитом.
        
        Предотвращает падение при использовании вне Qt-приложения (тесты, CLI).
        
        Args:
            signal: Сигнал для эмита
            *args: Аргументы сигнала
        """
        try:
            from PyQt6.QtWidgets import QApplication
            
            # Проверяем наличие QApplication instance
            if QApplication.instance() is None:
                logger.debug(
                    "Skipping signal emit (no QApplication): %s",
                    signal.__class__.__name__
                )
                return
            
            # Эмитим сигнал
            signal.emit(*args)
            
        except Exception as e:
            # Не прерываем основную операцию при ошибке сигнала
            logger.debug(
                "Error emitting signal %s: %s",
                signal.__class__.__name__,
                e,
                exc_info=True
            )

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
            # Лёгкая самодиагностика соединения: если закрыто/некорректно — переоткроем.
            try:
                conn.execute("SELECT 1").fetchone()
                return conn
            except Exception:
                try:
                    conn.close()
                except Exception:
                    pass
                # Отвязываем битый дескриптор и создаём новый ниже
                try:
                    del self.thread_local.conn
                except Exception:
                    pass

        # Создаем новое соединение (лениво), без тестового запроса
        self.thread_local.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.thread_local.conn.row_factory = sqlite3.Row
        self.thread_local.conn.execute("PRAGMA foreign_keys = ON")
        self.thread_local.conn.execute("PRAGMA journal_mode=WAL")
        return self.thread_local.conn

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
        from .types.constants import VALID_POSITION_TABLES
        
        if table_name not in VALID_POSITION_TABLES:
            raise ValidationError(
                f"Недопустимое имя таблицы для обновления позиций: {table_name}"
            )

        # Валидация и проверка существования
        try:
            ids = self._validate_ids(ids_in_order)
            if not ids:
                logger.debug(
                    "update_item_positions: пустой список ID для таблицы %s",
                    table_name,
                )
                return

            self._ensure_ids_exist(table_name, ids)

            # Проверка существования и обновление выполняются под ЕДИНЫМ db_lock
            with db_lock:
                _t0 = time.perf_counter()
                # --- Пакетное обновление позиций ---
                # Формируем пары (id, position) согласно порядку в ids
                id_pos_pairs = [(item_id, i) for i, item_id in enumerate(ids)]
                # Ограничение SQLite по количеству параметров по умолчанию ~999 — по 2 параметра на запись
                with self.connection:
                    batches = 0
                    for start in range(0, len(id_pos_pairs), SQLITE_SAFE_BATCH_SIZE):
                        chunk = id_pos_pairs[start : start + SQLITE_SAFE_BATCH_SIZE]
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
                    SQLITE_SAFE_BATCH_SIZE,
                    ((_t1 - _t0) * 1000.0),
                )
            logger.debug(
                "Обновлены позиции (%s шт.) в таблице %s",
                len(ids),
                table_name,
            )
            
            # Уведомляем UI об изменении данных через Qt сигнал
            # ✅ ИСПРАВЛЕНИЕ: Используем _safe_emit
            self._safe_emit(self.data_changed, table_name, "update_positions", ids)
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
            for s in range(0, len(ids), SQLITE_SAFE_SELECT_CHUNK):
                part = ids[s : s + SQLITE_SAFE_SELECT_CHUNK]
                placeholders = ",".join(["?"] * len(part))
                rows = self.connection.execute(
                    f"SELECT id FROM {table_name} WHERE id IN ({placeholders})",
                    tuple(part),
                ).fetchall()
                for row in rows:
                    try:
                        existing_ids.add(int(dict(row)["id"]))
                    except (KeyError, TypeError, ValueError) as e:
                        logger.warning("Ошибка преобразования ID: %s", e)
                        continue
        missing = [i for i in ids if i not in existing_ids]
        if missing:
            raise ValidationError(
                f"Не найдены записи с ID: {missing} в таблице {table_name}"
            )

    # Методы импорта/экспорта
    def export_full_structure(self) -> Dict[str, List]:
        """Экспортирует всю структуру данных из БД в виде словаря (синхронно).
        
        .. deprecated::
            Используйте :meth:`export_full_structure_async` для предотвращения блокировки UI.
        """
        warnings.warn(
            "Метод export_full_structure() устарел. Используйте export_full_structure_async().",
            DeprecationWarning,
            stacklevel=2
        )
        return self.import_export_manager.export_full_structure()
    
    def export_full_structure_async(
        self,
        on_finished: Optional[Callable] = None,
        on_error: Optional[Callable] = None,
        on_progress: Optional[Callable] = None
    ):
        """Экспортирует структуру в фоновом потоке.
        
        Args:
            on_finished: Callback при завершении (result: Dict[str, List])
            on_error: Callback при ошибке (exception, traceback)
            on_progress: Callback для прогресса (current, total, message)
        """
        from .workers import ExportStructureWorker
        
        worker = ExportStructureWorker(self.db_path)
        
        if on_finished:
            worker.signals.finished.connect(on_finished)
        if on_error:
            worker.signals.error.connect(on_error)
        if on_progress:
            worker.signals.progress.connect(on_progress)
        
        self._thread_pool.start(worker)
        logger.info("Запущен асинхронный экспорт структуры")

    def get_full_structure(self) -> List[Dict]:
        """Возвращает полную структуру данных в виде вложенных словарей."""
        return self.structure_manager.get_full_structure()

    def import_full_structure(self, data: List[Dict]):
        """Очищает базу и импортирует данные из структуры (синхронно).
        
        .. deprecated::
            Используйте :meth:`import_full_structure_async` для предотвращения блокировки UI.
        """
        warnings.warn(
            "Метод import_full_structure() устарел. Используйте import_full_structure_async().",
            DeprecationWarning,
            stacklevel=2
        )
        return self.structure_manager.import_full_structure(data)
    
    def import_full_structure_async(
        self,
        data: List[Dict],
        on_finished: Optional[Callable] = None,
        on_error: Optional[Callable] = None,
        on_progress: Optional[Callable] = None
    ):
        """Импортирует данные в фоновом потоке (РЕКОМЕНДУЕТСЯ).
        
        Args:
            data: Данные для импорта
            on_finished: Callback при завершении (stats: {spheres, sections, categories, links})
            on_error: Callback при ошибке (exception, traceback)
            on_progress: Callback для прогресса (current, total, message)
            
        Example:
            >>> def on_done(stats):
            ...     print(f"Imported {stats['spheres']} spheres")
            >>> db.import_full_structure_async(data, on_finished=on_done)
        """
        from .workers import ImportStructureWorker
        
        worker = ImportStructureWorker(self.db_path, data)
        
        # Подключаем внутренние сигналы Database
        worker.signals.finished.connect(lambda stats: self.structure_loaded.emit())
        worker.signals.error.connect(lambda e, tb: self.error_occurred.emit("Ошибка импорта", str(e)))
        
        # Подключаем пользовательские callbacks
        if on_finished:
            worker.signals.finished.connect(on_finished)
        if on_error:
            worker.signals.error.connect(on_error)
        if on_progress:
            worker.signals.progress.connect(on_progress)
        
        self._thread_pool.start(worker)
        logger.info("Запущен асинхронный импорт структуры")

    def backup(self):
        """Создаёт резервную копию базы данных (синхронно)."""
        return self.backup_manager.backup(BACKUP_DIR)
    
    def backup_async(
        self,
        on_finished: Optional[Callable] = None,
        on_error: Optional[Callable] = None,
        on_progress: Optional[Callable] = None
    ):
        """Создаёт резервную копию в фоновом потоке.
        
        Args:
            on_finished: Callback при успешном завершении (result)
            on_error: Callback при ошибке (exception, traceback)
            on_progress: Callback для прогресса (current, total, message)
        """
        from .workers import BackupWorker
        
        worker = BackupWorker(self.db_path, BACKUP_DIR)
        
        if on_finished:
            worker.signals.finished.connect(on_finished)
        if on_error:
            worker.signals.error.connect(on_error)
        if on_progress:
            worker.signals.progress.connect(on_progress)
        
        # Запускаем в thread pool
        self._thread_pool.start(worker)
        logger.info("Запущено асинхронное резервное копирование")

    def export_section_tree(self, section_id: int) -> dict:
        """Экспортирует раздел вместе со всеми категориями и ссылками."""
        return self.import_export_manager.export_section_tree(section_id)

    def import_section_tree(self, tree: dict):
        """Восстанавливает раздел, его категории и все ссылки из backup-структуры."""
        return self.import_export_manager.import_section_tree(tree)

    def export_category_tree(self, category_id: int) -> dict:
        """Экспортирует категорию вместе со всеми ссылками."""
        return self.import_export_manager.export_category_tree(category_id)

    def import_category_tree(self, tree: dict):
        """Восстанавливает категорию и все ссылки из backup-структуры."""
        return self.import_export_manager.import_category_tree(tree)

    def import_category_trees_bulk(self, trees: List[dict]) -> None:
        """Импортирует несколько поддеревьев категорий в ОДНОЙ транзакции."""
        return self.import_export_manager.import_category_trees_bulk(trees)

    def is_connected(self) -> bool:
        """Проверяет, установлено ли соединение с базой данных."""
        try:
            conn = getattr(self.thread_local, "conn", None)
            if conn is not None:
                conn.execute("SELECT 1").fetchone()
                return True
            return False
        except Exception:
            return False

    def close(self):
        """Закрывает соединение с базой данных."""
        try:
            if hasattr(self.thread_local, "conn"):
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
        """Ищет case-insensitive дубликаты имён."""
        return self.duplicate_resolver.detect_case_insensitive_duplicates()

    def resolve_case_insensitive_duplicates(self, strategy: str = "rename") -> dict:
        """Разрешает case-insensitive дубликаты."""
        return self.duplicate_resolver.resolve_case_insensitive_duplicates(strategy)

    def create_nocase_unique_indexes(self) -> None:
        """Пере-создаёт case-insensitive уникальные индексы для sphere/section/category."""
        return self.duplicate_resolver.create_nocase_unique_indexes()
    
    def cleanup(self) -> None:
        """Освобождает ресурсы Database.
        
        ✅ ИСПРАВЛЕНИЕ: Добавлен метод cleanup для предотвращения утечек памяти.
        
        Вызывается при закрытии приложения для корректного завершения:
        - Ожидает завершения всех workers в thread pool
        - Закрывает соединения с БД
        - Освобождает ресурсы моделей и менеджеров
        
        Идемпотентен - можно вызывать многократно.
        """
        if self._cleaned_up:
            return
        
        try:
            logger.debug("Database cleanup started")
            
            # 1. Ждём завершения всех workers (макс 5 секунд)
            if hasattr(self, '_thread_pool') and self._thread_pool:
                try:
                    logger.debug("Waiting for thread pool to finish...")
                    # waitForDone возвращает True если все завершились, False если таймаут
                    if not self._thread_pool.waitForDone(5000):
                        logger.warning(
                            "Thread pool did not finish within timeout, "
                            "some workers may still be running"
                        )
                except Exception as e:
                    logger.warning("Error waiting for thread pool: %s", e)
            
            # 2. Закрываем соединение с БД
            try:
                self.close()
            except Exception as e:
                logger.warning("Error closing database connection: %s", e)
            
            # 3. Очищаем ссылки на модели и менеджеры
            # (Python GC сам освободит память, но явно обнуляем для ясности)
            for attr in ['spheres', 'sections', 'categories', 'links',
                        'backup_manager', 'import_export_manager', 
                        'duplicate_resolver', 'structure_manager']:
                if hasattr(self, attr):
                    try:
                        delattr(self, attr)
                    except Exception:
                        pass
            
            self._cleaned_up = True
            logger.debug("Database cleanup completed")
            
        except Exception as exc:
            logger.error("Error during Database cleanup: %s", exc, exc_info=True)
