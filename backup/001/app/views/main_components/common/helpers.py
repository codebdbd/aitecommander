"""Простые helper функции для упрощения частых операций.

УЛУЧШЕНИЕ: Практичные утилиты без излишнего усложнения.
"""

from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QTimer

from .constants import Timeout


def defer(callback: callable, delay_ms: int = Timeout.DEFER_OPERATION) -> None:
    """Отложить выполнение callback на следующий тик event loop.
    
    УЛУЧШЕНИЕ: Упрощает частый паттерн QTimer.singleShot(0, callback).
    
    Args:
        callback: Функция для вызова
        delay_ms: Задержка в миллисекундах (по умолчанию 0)
        
    Example:
        >>> defer(lambda: print("Deferred"))
        >>> defer(self.update_ui, 100)
    """
    QTimer.singleShot(delay_ms, callback)


def safe_getattr(obj: Any, name: str, default: Any = None) -> Any:
    """Безопасное получение атрибута с проверкой на deleted Qt объекты.
    
    УЛУЧШЕНИЕ: Упрощает частый паттерн проверки deleted objects.
    
    Args:
        obj: Объект для получения атрибута
        name: Имя атрибута
        default: Значение по умолчанию
        
    Returns:
        Значение атрибута или default
        
    Example:
        >>> widget = safe_getattr(window, "search")
        >>> if widget:
        ...     widget.setText("test")
    """
    if obj is None:
        return default
    
    try:
        from sip import isdeleted
        if isdeleted(obj):
            return default
    except ImportError:
        pass
    
    try:
        return getattr(obj, name, default)
    except (RuntimeError, AttributeError):
        return default


def safe_disconnect(signal, slot) -> bool:
    """Безопасное отключение сигнала от слота.
    
    УЛУЧШЕНИЕ: Упрощает частый паттерн отключения сигналов.
    
    Args:
        signal: Qt сигнал
        slot: Слот для отключения
        
    Returns:
        True если отключено успешно, False иначе
        
    Example:
        >>> safe_disconnect(button.clicked, self.on_click)
    """
    try:
        signal.disconnect(slot)
        return True
    except (TypeError, RuntimeError, AttributeError):
        return False


def clamp(value: float, min_val: float, max_val: float) -> float:
    """Ограничить значение в диапазоне [min_val, max_val].
    
    Args:
        value: Значение для ограничения
        min_val: Минимум
        max_val: Максимум
        
    Returns:
        Ограниченное значение
        
    Example:
        >>> clamp(150, 100, 200)  # 150
        >>> clamp(50, 100, 200)   # 100
        >>> clamp(250, 100, 200)  # 200
    """
    return max(min_val, min(value, max_val))
