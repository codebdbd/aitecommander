"""
Адаптеры для преобразования конфигурационных данных в Qt-объекты.
Изолирует PyQt6 зависимости от основного конфигурационного модуля.
"""

from typing import Any, List, Tuple, Union


def to_qsize(size_data: Union[int, List[int], Tuple[int, int]]) -> Any:
    """Преобразует размер из конфигурации в QSize объект."""
    from PyQt6.QtCore import QSize

    if isinstance(size_data, (list, tuple)) and len(size_data) >= 2:
        return QSize(int(size_data[0]), int(size_data[1]))
    elif isinstance(size_data, int):
        return QSize(size_data, size_data)
    else:
        return QSize(24, 24)  # fallback


def to_size_list(size_data: Union[int, List[int], Tuple[int, int]]) -> List[int]:
    """Преобразует размер из конфигурации в список [width, height]."""
    if isinstance(size_data, (list, tuple)) and len(size_data) >= 2:
        return [int(size_data[0]), int(size_data[1])]
    elif isinstance(size_data, int):
        return [size_data, size_data]
    else:
        return [24, 24]  # fallback
