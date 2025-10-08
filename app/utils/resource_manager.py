"""Compatible layer for legacy import `app.utils.resource_manager`."""

from __future__ import annotations

from typing import Any, Callable, Optional

from app.views.main_components.common.resource_manager import (
    ResourceManager as _ModernResourceManager,
)


class ResourceManager(_ModernResourceManager):
    """Adapter providing legacy methods (`register`, `cleanup`)."""

    def register(  # type: ignore[override]
        self,
        resource: Any,
        cleanup_func: Optional[Callable[[], None]] = None,
        name: str = "",
        use_finalize: bool = True,
    ) -> None:
        """Compatibility with old API, delegates to `register_resource`."""

        self.register_resource(
            resource=resource,
            cleanup_func=cleanup_func,
            name=name,
            use_finalize=use_finalize,
        )

    def cleanup(self) -> None:
        """Old method name for cleanup."""

        self.cleanup_all()


__all__ = ["ResourceManager"]
