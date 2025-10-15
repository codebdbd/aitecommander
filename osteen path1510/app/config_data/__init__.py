from __future__ import annotations

"""Configuration entry point with lazy initialization semantics.

Avoids performing filesystem I/O while importing `app.config_data`; the actual
configuration object is created only when code first accesses attributes on
`app_config`.
"""

# Публичные символы модуля
from typing import Any, TYPE_CHECKING

__all__ = ["app_config", "get_app_config", "AppConfig"]

if TYPE_CHECKING:  # pragma: no cover - только для подсказок типов
    from .config_loader import AppConfig as AppConfig


def get_app_config() -> "AppConfig":
    """Получить лениво инициализированный экземпляр `AppConfig`."""
    instance = app_config._get_instance()
    if instance is None:
        raise RuntimeError("AppConfig instance was not initialized")
    return instance


class _LazyAppConfig:
    """Lazy proxy around :class:`AppConfig` that instantiates on demand."""

    __slots__ = ("_instance",)

    _instance: "AppConfig | None"

    def __init__(self) -> None:
        # use ``object.__setattr__`` to avoid triggering the overridden ``__setattr__``
        object.__setattr__(self, "_instance", None)

    def _get_instance(self) -> "AppConfig":
        if self._instance is None:
            # Local import; the loader itself performs no I/O at import time
            from .config_loader import AppConfig as _AppConfig

            self._instance = _AppConfig()
        return self._instance

    def __getattr__(self, name: str) -> Any:
        return getattr(self._get_instance(), name)

    def __setattr__(self, name: str, value: Any) -> None:
        # Forward assignments to the real AppConfig so monkeypatching keeps working
        if name == "_instance":
            object.__setattr__(self, name, value)
            return
        inst = object.__getattribute__(self, "_instance")
        if inst is None:
            # Lazy initialization triggered by the first assignment
            from .config_loader import AppConfig as _AppConfig  # локальный импорт

            inst = _AppConfig()
            object.__setattr__(self, "_instance", inst)
        setattr(inst, name, value)

    def __delattr__(self, name: str) -> None:
        # Delegate attribute deletion to the real AppConfig (needed for monkeypatch teardown)
        if name == "_instance":
            raise AttributeError("Нельзя удалять служебный атрибут _instance")
        inst = object.__getattribute__(self, "_instance")
        if inst is None:
            # Nothing to delete when the instance is not initialized yet
            return
        try:
            delattr(inst, name)
        except AttributeError:
            # Support ``raising=False`` scenarios from pytest monkeypatch by ignoring missing attrs
            return

    def __repr__(self) -> str:  # helpful during debugging
        if self._instance is None:
            return "<Lazy(AppConfig): not initialized>"
        return f"<Lazy(AppConfig): initialized at {id(self._instance):#x}>"


# Global lazy proxy to the application configuration
app_config = _LazyAppConfig()


def __getattr__(name: str) -> Any:
    if name == "AppConfig":
        from .config_loader import AppConfig as _AppConfig

        globals()["AppConfig"] = _AppConfig
        return _AppConfig
    raise AttributeError(f"module 'app.config_data' has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
