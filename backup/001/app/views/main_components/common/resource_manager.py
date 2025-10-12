"""Централизованный менеджер ресурсов для безопасной очистки.

УЛУЧШЕНИЕ: Добавлен ResourceManager для управления жизненным циклом ресурсов
и гарантированной очистки. Заменяет ненадежные __del__ методы и предотвращает
утечки памяти.
"""

from __future__ import annotations

import logging
import weakref
from contextlib import contextmanager
from typing import Any, Callable, List, Optional, Tuple

logger = logging.getLogger(__name__)


class ResourceManager:
    """Менеджер для централизованной очистки ресурсов.
    
    УЛУЧШЕНИЕ: Использует weakref.finalize() вместо __del__ для надежной очистки.
    Поддерживает context manager для автоматической очистки при выходе из scope.
    
    Example:
        >>> manager = ResourceManager()
        >>> timer = QTimer()
        >>> manager.register_resource(timer, timer.stop, "main_timer")
        >>> # ... использование ресурсов
        >>> manager.cleanup_all()  # Очистка всех ресурсов
        
        >>> # Или с context manager
        >>> with ResourceManager() as manager:
        ...     timer = QTimer()
        ...     manager.register_resource(timer, timer.stop)
        ...     # Автоматическая очистка при выходе
    """

    def __init__(self, name: str = "ResourceManager") -> None:
        """Инициализирует менеджер ресурсов.
        
        Args:
            name: Имя менеджера для логирования
        """
        self._name = name
        self._resources: List[Tuple[str, Callable[[], None], Optional[weakref.finalize]]] = []
        self._cleaned_up = False
        self._cleanup_errors: List[Tuple[str, Exception]] = []

    def register_resource(
        self,
        resource: Any,
        cleanup_func: Optional[Callable[[], None]] = None,
        name: str = "",
        use_finalize: bool = True,
    ) -> None:
        """Регистрирует ресурс для автоматической очистки.
        
        УЛУЧШЕНИЕ: Автоматически определяет cleanup метод для Qt объектов.
        
        Args:
            resource: Объект ресурса (для weakref)
            cleanup_func: Функция очистки (если None, определяется автоматически)
            name: Имя ресурса для логирования
            use_finalize: Использовать weakref.finalize для автоочистки
            
        Example:
            >>> # Автоматическое определение cleanup
            >>> manager.register_resource(QTimer())  # Вызовет stop()
            >>> manager.register_resource(QWidget())  # Вызовет deleteLater()
        """
        if self._cleaned_up:
            logger.warning(
                "%s: attempted to register resource '%s' after cleanup",
                self._name,
                name or "unnamed",
            )
            return

        # УЛУЧШЕНИЕ: Автоопределение cleanup функции для Qt объектов
        if cleanup_func is None:
            cleanup_func = self._auto_detect_cleanup(resource)
            if cleanup_func is None:
                logger.warning(
                    "%s: cannot auto-detect cleanup for %s, skipping",
                    self._name,
                    type(resource).__name__
                )
                return

        resource_name = name or f"{type(resource).__name__}@{id(resource)}"
        
        finalizer = None
        if use_finalize:
            try:
                # weakref.finalize вызовет cleanup_func когда resource будет удален
                finalizer = weakref.finalize(resource, self._safe_cleanup, cleanup_func, resource_name)
                logger.debug("%s: registered resource '%s' with finalize", self._name, resource_name)
            except TypeError as e:
                logger.debug(
                    "%s: cannot create finalize for '%s': %s (will use manual cleanup)",
                    self._name,
                    resource_name,
                    e,
                )

        self._resources.append((resource_name, cleanup_func, finalizer))
    
    def _auto_detect_cleanup(self, resource: Any) -> Optional[Callable[[], None]]:
        """Автоматически определяет cleanup метод для ресурса.
        
        УЛУЧШЕНИЕ: Упрощает API - не нужно указывать cleanup_func для Qt объектов.
        """
        # QTimer -> stop()
        if hasattr(resource, 'stop') and callable(getattr(resource, 'stop')):
            return resource.stop
        
        # QWidget, QObject -> deleteLater()
        if hasattr(resource, 'deleteLater') and callable(getattr(resource, 'deleteLater')):
            return resource.deleteLater
        
        # File-like -> close()
        if hasattr(resource, 'close') and callable(getattr(resource, 'close')):
            return resource.close
        
        return None

    def _safe_cleanup(self, cleanup_func: Callable[[], None], resource_name: str) -> None:
        """Безопасно вызывает функцию очистки с обработкой ошибок.
        
        Args:
            cleanup_func: Функция очистки
            resource_name: Имя ресурса для логирования
        """
        try:
            cleanup_func()
            logger.debug("%s: cleaned up resource '%s'", self._name, resource_name)
        except Exception as e:
            logger.warning(
                "%s: error cleaning up resource '%s': %s",
                self._name,
                resource_name,
                e,
                exc_info=True,
            )
            self._cleanup_errors.append((resource_name, e))

    def cleanup_all(self) -> None:
        """Очищает все зарегистрированные ресурсы.
        
        УЛУЧШЕНИЕ: Гарантирует вызов всех cleanup функций даже при ошибках.
        Логирует все ошибки очистки для диагностики.
        """
        if self._cleaned_up:
            logger.debug("%s: cleanup_all called multiple times, ignoring", self._name)
            return

        logger.debug("%s: starting cleanup of %d resources", self._name, len(self._resources))
        self._cleaned_up = True
        self._cleanup_errors.clear()

        # Очищаем в обратном порядке регистрации (LIFO)
        for resource_name, cleanup_func, finalizer in reversed(self._resources):
            # Отключаем finalize, так как мы вызываем cleanup вручную
            if finalizer is not None:
                try:
                    finalizer.detach()
                except Exception:
                    pass  # Игнорируем ошибки detach

            self._safe_cleanup(cleanup_func, resource_name)

        self._resources.clear()

        if self._cleanup_errors:
            logger.warning(
                "%s: cleanup completed with %d errors",
                self._name,
                len(self._cleanup_errors),
            )
        else:
            logger.info("%s: cleanup completed successfully", self._name)

    def is_cleaned_up(self) -> bool:
        """Проверяет, были ли очищены ресурсы.
        
        Returns:
            True если cleanup_all() был вызван
        """
        return self._cleaned_up

    def get_cleanup_errors(self) -> List[Tuple[str, Exception]]:
        """Возвращает список ошибок, произошедших при очистке.
        
        Returns:
            Список кортежей (resource_name, exception)
        """
        return self._cleanup_errors.copy()

    def __enter__(self) -> ResourceManager:
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit - автоматически очищает ресурсы."""
        self.cleanup_all()

    def __del__(self) -> None:
        """Деструктор - вызывает cleanup если не был вызван явно."""
        if not self._cleaned_up:
            logger.debug("%s: cleanup_all not called explicitly, cleaning up in __del__", self._name)
            try:
                self.cleanup_all()
            except Exception:
                # Игнорируем ошибки в деструкторе
                pass


@contextmanager
def managed_resource(
    resource: Any,
    cleanup_func: Callable[[], None],
    name: str = "",
):
    """Context manager для одиночного ресурса.
    
    УЛУЧШЕНИЕ: Упрощенный API для управления одним ресурсом.
    
    Example:
        >>> timer = QTimer()
        >>> with managed_resource(timer, timer.stop, "my_timer"):
        ...     timer.start(1000)
        ...     # ... использование
        ... # Автоматический вызов timer.stop()
    """
    manager = ResourceManager(name=name or "managed_resource")
    manager.register_resource(resource, cleanup_func, name, use_finalize=False)
    try:
        yield resource
    finally:
        manager.cleanup_all()
