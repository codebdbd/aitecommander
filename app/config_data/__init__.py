"""Точка входа конфигурации.

Переведено на ленивую инициализацию, чтобы избежать дискового I/O при импорте
`app.config_data`. Объект конфигурации создаётся только при первом фактическом
обращении к атрибутам `app_config`.
"""

# Экспортируем класс для прямого использования при необходимости (без побочных эффектов)
from .config_loader import AppConfig  # noqa: F401


class _LazyAppConfig:
    """Ленивый прокси для AppConfig.

    Создаёт реальный экземпляр только при первом обращении к атрибутам.
    """

    __slots__ = ("_instance",)

    def __init__(self):
        self._instance = None

    def _get_instance(self):
        if self._instance is None:
            # Локальный импорт инициализатора, сам по себе не делает I/O
            from .config_loader import AppConfig as _AppConfig

            self._instance = _AppConfig()
        return self._instance

    def __getattr__(self, name):
        return getattr(self._get_instance(), name)

    def __repr__(self) -> str:  # для удобства отладки
        if self._instance is None:
            return "<Lazy(AppConfig): not initialized>"
        return f"<Lazy(AppConfig): initialized at {id(self._instance):#x}>"


# Глобальный ленивый прокси конфигурации приложения
app_config = _LazyAppConfig()
