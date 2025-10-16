"""Configuration entry point with lazy initialization semantics.

Avoids performing filesystem I/O while importing `app.config_data`; the actual
configuration object is created only when code first accesses attributes on
`app_config`.
"""

# Re-export the loader class for direct use when needed (without side effects)
from .config_loader import AppConfig  # noqa: F401


class _LazyAppConfig:
    """Lazy proxy around :class:`AppConfig` that instantiates on demand."""

    __slots__ = ("_instance",)

    def __init__(self):
        # use ``object.__setattr__`` to avoid triggering the overridden ``__setattr__``
        object.__setattr__(self, "_instance", None)

    def _get_instance(self):
        if self._instance is None:
            # Local import; the loader itself performs no I/O at import time
            from .config_loader import AppConfig as _AppConfig

            self._instance = _AppConfig()
        return self._instance

    def __getattr__(self, name):
        return getattr(self._get_instance(), name)

    def __setattr__(self, name, value):
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

    def __delattr__(self, name):
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
