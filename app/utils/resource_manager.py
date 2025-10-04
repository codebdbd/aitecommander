"""Совместимый слой для легаси-импорта `app.utils.resource_manager`."""

from __future__ import annotations

from typing import Any, Callable, Optional

from app.views.main_components.common.resource_manager import (
    ResourceManager as _ModernResourceManager,
)


class ResourceManager(_ModernResourceManager):
    """Адаптер, предоставляющий легаси-методы (`register`, `cleanup`)."""

    def register(  # type: ignore[override]
        self,
        resource: Any,
        cleanup_func: Optional[Callable[[], None]] = None,
        name: str = "",
        use_finalize: bool = True,
    ) -> None:
        """Совместимость со старым API, делегирует в `register_resource`."""

        self.register_resource(
            resource=resource,
            cleanup_func=cleanup_func,
            name=name,
            use_finalize=use_finalize,
        )

    def cleanup(self) -> None:
        """Старое имя метода очистки."""

        self.cleanup_all()


__all__ = ["ResourceManager"]
