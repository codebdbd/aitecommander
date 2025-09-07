# app/views/main_components/init_scheduler.py
from __future__ import annotations

from typing import Callable, Dict, List, Optional, Tuple

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication


class AsyncStepRunner:
    """Универсальный исполнитель последовательности асинхронных шагов.

    Выполняет шаги последовательно, между шагами отдаёт цикл событий UI,
    измеряет длительность шагов и поддерживает post-hooks.
    """

    def __init__(
        self,
        metrics,
        set_status_message: Callable[[str], None],
    ) -> None:
        self._metrics = metrics
        self._set_status_message = set_status_message

    def run(
        self,
        steps: List[Tuple[str, Callable[[], None]]],
        index_getter: Callable[[], int],
        index_setter: Callable[[int], None],
        on_completed: Callable[[], None],
        on_error: Optional[Callable[[Exception], None]] = None,
        special_hooks: Optional[Dict[Callable[[], None], Callable[[], None]]] = None,
    ) -> None:
        """Запускает последовательное выполнение переданных шагов.

        Args:
            steps: Список пар (название шага, функция шага без аргументов)
            index_getter: Функция, возвращающая текущий индекс шага
            index_setter: Функция, сохраняющая новый индекс шага
            on_completed: Коллбек по завершении всех шагов
            special_hooks: Необязательные хуки (после конкретных функций шагов)
        """
        QTimer.singleShot(0, lambda: self._execute_next(steps, index_getter, index_setter, on_completed, on_error, special_hooks))

    # Внутренняя рекурсивная функция
    def _execute_next(
        self,
        steps: List[Tuple[str, Callable[[], None]]],
        index_getter: Callable[[], int],
        index_setter: Callable[[int], None],
        on_completed: Callable[[], None],
        on_error: Optional[Callable[[Exception], None]],
        special_hooks: Optional[Dict[Callable[[], None], Callable[[], None]]],
    ) -> None:
        idx = int(index_getter())
        if idx >= len(steps):
            on_completed()
            return

        step_name, step_func = steps[idx]
        # Обновляем статус-бар (если уже доступен)
        try:
            self._set_status_message(step_name)
        except Exception:
            # Не мешаем выполнению шагов, но фиксируем сбой обновления статуса
            import logging as _logging
            _logging.getLogger(__name__).debug("AsyncStepRunner: failed to set status message: %s", step_name, exc_info=True)

        # Выполняем шаг под метриками
        try:
            with self._metrics.time_span(f"heavy:{step_func.__name__}"):
                step_func()
        except Exception as e:
            if on_error:
                try:
                    on_error(e)
                finally:
                    return
            else:
                raise

        # Спец-хуки после шага
        if special_hooks and step_func in special_hooks:
            try:
                special_hooks[step_func]()
            except Exception as e:
                if on_error:
                    try:
                        on_error(e)
                    finally:
                        return
                # иначе подавляем, чтобы не ломать пайплайн, но логируем
                import logging as _logging
                _logging.getLogger(__name__).debug("AsyncStepRunner: special hook failed for %s", getattr(step_func, "__name__", str(step_func)), exc_info=True)

        # Инкремент индекса и продолжение
        index_setter(idx + 1)

        # Даём UI-потоку обработать события
        QApplication.processEvents()

        # Планируем следующий шаг
        QTimer.singleShot(0, lambda: self._execute_next(steps, index_getter, index_setter, on_completed, on_error, special_hooks))
