"""Базовый класс для workers, выполняющих операции БД в фоновом потоке."""
import logging
import traceback
from typing import Any, Optional

from PyQt6.QtCore import QObject, QRunnable, pyqtSignal, pyqtSlot

logger = logging.getLogger(__name__)


class WorkerSignals(QObject):
    """Сигналы для коммуникации worker -> UI."""
    
    # Прогресс операции: current, total, message
    progress = pyqtSignal(int, int, str)
    
    # Успешное завершение: result
    finished = pyqtSignal(object)
    
    # Ошибка: exception, traceback_str
    error = pyqtSignal(Exception, str)
    
    # Отмена операции
    cancelled = pyqtSignal()


class DatabaseWorker(QRunnable):
    """Базовый класс для выполнения операций БД в фоновом потоке.
    
    Особенности:
    - Создает отдельное соединение с БД для потокобезопасности
    - Использует сигналы для передачи результатов в UI
    - Поддерживает отмену операции
    - Автоматическая обработка ошибок и логирование
    
    Подклассы должны реализовать метод `do_work()`.
    """
    
    def __init__(self, db_path: str):
        """
        Args:
            db_path: Путь к файлу базы данных
        """
        super().__init__()
        self.db_path = db_path
        self.signals = WorkerSignals()
        self._is_cancelled = False
        
        # Флаг автоматического удаления после завершения
        self.setAutoDelete(True)
    
    def cancel(self):
        """Отменяет выполнение операции."""
        self._is_cancelled = True
        logger.info("Worker %s отменен", self.__class__.__name__)
    
    @property
    def is_cancelled(self) -> bool:
        """Проверяет, отменена ли операция."""
        return self._is_cancelled
    
    def emit_progress(self, current: int, total: int, message: str = ""):
        """Отправляет сигнал прогресса.
        
        Args:
            current: Текущий прогресс
            total: Общее количество элементов
            message: Текстовое сообщение о статусе
        """
        if not self._is_cancelled:
            self.signals.progress.emit(current, total, message)
    
    def create_connection(self):
        """Создает отдельное соединение с БД для этого потока.
        
        Returns:
            sqlite3.Connection: Соединение с БД
        """
        import sqlite3
        from ..base.db_base import db_lock
        
        with db_lock:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            # Настройки для производительности
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA cache_size=-64000")  # 64MB
            conn.execute("PRAGMA temp_store=MEMORY")
            return conn
    
    def do_work(self, connection) -> Any:
        """Выполняет основную работу. Должен быть переопределен в подклассах.
        
        Args:
            connection: Соединение с БД
            
        Returns:
            Результат операции (будет передан через сигнал finished)
            
        Raises:
            Exception: Любые ошибки будут перехвачены и переданы через сигнал error
        """
        raise NotImplementedError("Подклассы должны реализовать метод do_work()")
    
    @pyqtSlot()
    def run(self):
        """Основной метод, вызываемый QThreadPool.
        
        Создает соединение, выполняет работу, обрабатывает ошибки.
        """
        connection = None
        try:
            # Создаем отдельное соединение для этого потока
            connection = self.create_connection()
            
            # Выполняем работу
            result = self.do_work(connection)
            
            # Проверяем отмену перед отправкой результата
            if self._is_cancelled:
                self.signals.cancelled.emit()
            else:
                self.signals.finished.emit(result)
                
        except Exception as e:
            # Перехватываем все ошибки и передаем через сигнал
            tb_str = traceback.format_exc()
            logger.error(
                "Ошибка в worker %s: %s\n%s",
                self.__class__.__name__,
                str(e),
                tb_str
            )
            self.signals.error.emit(e, tb_str)
            
        finally:
            # Закрываем соединение
            if connection:
                try:
                    connection.close()
                except Exception as close_err:
                    logger.warning("Ошибка закрытия соединения: %s", close_err)
