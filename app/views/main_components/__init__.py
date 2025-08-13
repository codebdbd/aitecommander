# app/views/main_components/__init__.py

"""
Модульные компоненты главного окна.

Этот пакет содержит извлеченные из main_window.py компоненты для улучшения
модульности и читаемости кода.
"""

from .delayed_widgets_initializer import DelayedWidgetsInitializer
from .window_initializer import WindowInitializer

__all__ = [
    'WindowInitializer',
    'DelayedWidgetsInitializer'
]
