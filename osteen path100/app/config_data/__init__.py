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
        # используем object.__setattr__, чтобы не задействовать переопределённый __setattr__
        object.__setattr__(self, "_instance", None)

    def _get_instance(self):
        if self._instance is None:
            # Локальный импорт инициализатора, сам по себе не делает I/O
            from .config_loader import AppConfig as _AppConfig

            self._instance = _AppConfig()
        return self._instance

    def __getattr__(self, name):
        return getattr(self._get_instance(), name)

    def __setattr__(self, name, value):
        # Прокидываем присваивания в реальный AppConfig, чтобы monkeypatch мог работать
        if name == "_instance":
            object.__setattr__(self, name, value)
            return
        inst = object.__getattribute__(self, "_instance")
        if inst is None:
            # Ленивая инициализация при первом set
            from .config_loader import AppConfig as _AppConfig  # локальный импорт

            inst = _AppConfig()
            object.__setattr__(self, "_instance", inst)
        setattr(inst, name, value)

    def __delattr__(self, name):
        # Делегируем удаление атрибутов в реальный AppConfig (нужно для monkeypatch teardown)
        if name == "_instance":
            raise AttributeError("Нельзя удалять служебный атрибут _instance")
        inst = object.__getattribute__(self, "_instance")
        if inst is None:
            # Если ещё не инициализировано — нечего удалять
            return
        try:
            delattr(inst, name)
        except AttributeError:
            # Поддерживаем raising=False сценарии из monkeypatch — игнорируем отсутствие атрибута
            return

    def __repr__(self) -> str:  # для удобства отладки
        if self._instance is None:
            return "<Lazy(AppConfig): not initialized>"
        return f"<Lazy(AppConfig): initialized at {id(self._instance):#x}>"


# Глобальный ленивый прокси конфигурации приложения
app_config = _LazyAppConfig()
