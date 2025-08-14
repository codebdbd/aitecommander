"""
Унифицированный планировщик задач для управления параллелизмом и отложенными операциями.

Объединяет функциональность:
1. Пула потоков (threading)
2. Централизованного менеджера таймеров (timer_manager)

Решает проблемы:
1. Управление параллелизмом через пул потоков с ограничением
2. Оптимизация QTimer usage и предотвращение перегрузки event loop
3. Единый слой для управления всеми асинхронными операциями
"""

import logging
from enum import Enum
from typing import Any, Callable, Dict, Optional

from PyQt6.QtCore import QObject, QRunnable, QThreadPool, QTimer

logger = logging.getLogger(__name__)


class TaskType(Enum):
    """Типы задач для группировки."""
    FOCUS_MANAGEMENT = "focus"
    SELECTION_RESTORE = "selection"
    UI_LAYOUT = "layout"
    TABLE_UPDATE = "table"
    GENERAL = "general"
    BACKGROUND_TASK = "background"


class LimitedThreadPool(QThreadPool):
    """Пул потоков с ограничением на максимальное количество."""
    def __init__(self, max_threads=4):
        super().__init__()
        self.setMaxThreadCount(max_threads)
        self.max_threads = max_threads


class TaskScheduler(QObject):
    """Унифицированный планировщик задач для управления потоками и таймерами."""
    
    def __init__(self, max_threads=4):
        super().__init__()
        # Инициализация пула потоков
        self.thread_pool = LimitedThreadPool(max_threads)
        
        # Инициализация таймеров
        self._active_timers: Dict[str, QTimer] = {}
        self._pending_operations: Dict[TaskType, Dict[str, Callable]] = {
            task_type: {} for task_type in TaskType
        }
        self._default_delays = {
            TaskType.FOCUS_MANAGEMENT: 0,      # Немедленно после event loop
            TaskType.SELECTION_RESTORE: 100,   # Стандартная задержка для восстановления
            TaskType.UI_LAYOUT: 0,             # Немедленно для layout
            TaskType.TABLE_UPDATE: 100,        # Стандартная задержка для таблиц
            TaskType.GENERAL: 50,              # Общая задержка по умолчанию
            TaskType.BACKGROUND_TASK: 10       # Задержка для фоновых задач
        }
        
        # Таймеры для батчинга операций
        self._batch_timers: Dict[TaskType, QTimer] = {}
        self._setup_batch_timers()
    
    def _setup_batch_timers(self):
        """Настраивает таймеры для батчинга операций по типам."""
        for task_type in TaskType:
            timer = QTimer()
            timer.setSingleShot(True)
            # Используем лямбда-функцию с замыканием для правильной передачи task_type
            timer.timeout.connect(lambda t=task_type: self._execute_batched_operations(t))
            self._batch_timers[task_type] = timer
    
    def schedule_operation(self, 
                          operation: Callable,
                          task_type: TaskType = TaskType.GENERAL,
                          delay: Optional[int] = None,
                          operation_id: Optional[str] = None,
                          replace_existing: bool = True) -> str:
        """
        Планирует выполнение операции с оптимизацией.
        
        Args:
            operation: Функция для выполнения
            task_type: Тип операции для группировки
            delay: Задержка в мс (None = использовать по умолчанию)
            operation_id: Уникальный ID операции (None = автогенерация)
            replace_existing: Заменять ли существующую операцию с тем же ID
            
        Returns:
            ID операции для возможной отмены
        """
        if delay is None:
            delay = self._default_delays[task_type]
        
        if operation_id is None:
            operation_id = f"{task_type.value}_{id(operation)}"
        
        # Проверяем, есть ли уже операция с таким ID
        if operation_id in self._pending_operations[task_type]:
            if not replace_existing:
                logger.debug(f"Операция {operation_id} уже запланирована, пропускаем")
                return operation_id
            else:
                logger.debug(f"Заменяем существующую операцию {operation_id}")
        
        # Добавляем операцию в очередь
        self._pending_operations[task_type][operation_id] = operation
        
        # Запускаем или перезапускаем батч-таймер для этого типа
        batch_timer = self._batch_timers[task_type]
        if batch_timer.isActive():
            batch_timer.stop()
        
        batch_timer.start(delay)
        
        logger.debug(f"Запланирована операция {operation_id} типа {task_type.value} с задержкой {delay}ms")
        return operation_id
    
    def _execute_batched_operations(self, task_type: TaskType):
        """Выполняет все накопленные операции определенного типа."""
        operations = self._pending_operations[task_type]
        if not operations:
            return
        
        logger.debug(f"Выполняем {len(operations)} операций типа {task_type.value}")
        
        # Специальная обработка для focus operations - выполняем только последнюю
        if task_type == TaskType.FOCUS_MANAGEMENT:
            if operations:
                # Берем последнюю операцию (самую актуальную)
                last_operation_id = list(operations.keys())[-1]
                last_operation = operations[last_operation_id]
                try:
                    last_operation()
                    logger.debug(f"Выполнена focus операция: {last_operation_id}")
                except Exception as e:
                    logger.error(f"Ошибка выполнения focus операции {last_operation_id}: {e}")
        else:
            # Для остальных типов выполняем все операции
            for operation_id, operation in operations.items():
                try:
                    operation()
                    logger.debug(f"Выполнена операция: {operation_id}")
                except Exception as e:
                    logger.error(f"Ошибка выполнения операции {operation_id}: {e}")
        
        # Очищаем выполненные операции
        operations.clear()
    
    def cancel_operation(self, operation_id: str, task_type: TaskType = None) -> bool:
        """
        Отменяет запланированную операцию.
        
        Args:
            operation_id: ID операции для отмены
            task_type: Тип операции (None = поиск во всех типах)
            
        Returns:
            True если операция была найдена и отменена
        """
        if task_type:
            search_types = [task_type]
        else:
            search_types = list(TaskType)
        
        for tt in search_types:
            if operation_id in self._pending_operations[tt]:
                del self._pending_operations[tt][operation_id]
                logger.debug(f"Отменена операция {operation_id} типа {tt.value}")
                return True
        
        logger.debug(f"Операция {operation_id} не найдена для отмены")
        return False
    
    def submit_task(self, task: QRunnable) -> None:
        """
        Отправляет задачу в пул потоков для выполнения.
        
        Args:
            task: Задача для выполнения (QRunnable)
        """
        self.thread_pool.start(task)
        logger.debug(f"Задача отправлена в пул потоков")
    
    def get_thread_pool(self) -> LimitedThreadPool:
        """Возвращает пул потоков."""
        return self.thread_pool
    
    def schedule_focus_operation(self, widget_focus_func: Callable, widget_name: str = None) -> str:
        """Удобный метод для планирования операций установки фокуса."""
        operation_id = f"focus_{widget_name or id(widget_focus_func)}"
        return self.schedule_operation(
            widget_focus_func,
            TaskType.FOCUS_MANAGEMENT,
            operation_id=operation_id,
            replace_existing=True
        )
    
    def schedule_selection_restore(self, restore_func: Callable, item_id: Any = None) -> str:
        """Удобный метод для планирования восстановления выделения."""
        operation_id = f"selection_{item_id or id(restore_func)}"
        return self.schedule_operation(
            restore_func,
            TaskType.SELECTION_RESTORE,
            operation_id=operation_id,
            replace_existing=True
        )
    
    def schedule_layout_operation(self, layout_func: Callable, layout_name: str = None) -> str:
        """Удобный метод для планирования операций с layout."""
        operation_id = f"layout_{layout_name or id(layout_func)}"
        return self.schedule_operation(
            layout_func,
            TaskType.UI_LAYOUT,
            operation_id=operation_id,
            replace_existing=True
        )
    
    def get_pending_operations_count(self, task_type: TaskType = None) -> int:
        """Возвращает количество ожидающих операций."""
        if task_type:
            return len(self._pending_operations[task_type])
        else:
            return sum(len(ops) for ops in self._pending_operations.values())
    
    def clear_all_operations(self):
        """Очищает все запланированные операции и останавливает таймеры."""
        for timer in self._batch_timers.values():
            if timer.isActive():
                timer.stop()
        
        for operations in self._pending_operations.values():
            operations.clear()
        
        logger.info("Все запланированные операции очищены")


# Глобальный экземпляр планировщика задач
_task_scheduler_instance: Optional[TaskScheduler] = None


def get_task_scheduler() -> TaskScheduler:
    """Возвращает глобальный экземпляр TaskScheduler (singleton)."""
    global _task_scheduler_instance
    if _task_scheduler_instance is None:
        _task_scheduler_instance = TaskScheduler()
        logger.info("Создан глобальный TaskScheduler")
    return _task_scheduler_instance


def schedule_focus(widget_focus_func: Callable, widget_name: str = None) -> str:
    """Глобальная функция для планирования установки фокуса."""
    return get_task_scheduler().schedule_focus_operation(widget_focus_func, widget_name)


def schedule_selection_restore(restore_func: Callable, item_id: Any = None) -> str:
    """Глобальная функция для планирования восстановления выделения."""
    return get_task_scheduler().schedule_selection_restore(restore_func, item_id)


def schedule_layout(layout_func: Callable, layout_name: str = None) -> str:
    """Глобальная функция для планирования операций с layout."""
    return get_task_scheduler().schedule_layout_operation(layout_func, layout_name)


def schedule_operation(operation: Callable, 
                      task_type: TaskType = TaskType.GENERAL,
                      delay: Optional[int] = None,
                      operation_id: Optional[str] = None) -> str:
    """Глобальная функция для планирования произвольных операций."""
    return get_task_scheduler().schedule_operation(operation, task_type, delay, operation_id)


def submit_task(task: QRunnable) -> None:
    """Глобальная функция для отправки задач в пул потоков."""
    get_task_scheduler().submit_task(task)
