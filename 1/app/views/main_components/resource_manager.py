"""Compatibility layer for legacy import `app.views.main_components.resource_manager`."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Callable

from app.views.main_components.common.resource_manager import logger


class ResourceManager:
    """Simplified resource manager implementation from the legacy API."""

    def __init__(self, name: str = "ResourceManager") -> None:
        self._name = name
        self._resources: list[
            tuple[str, Any, str | None, Callable[[], None] | None]
        ] = []
        self._cleaned_up = False
        self._cleanup_errors: list[tuple[str, Exception]] = []

    def register_resource(
        self,
        resource: Any,
        cleanup_func: Callable[[], None] | None = None,
        name: str = "",
        use_finalize: bool = False,
    ) -> None:
        if self._cleaned_up:
            logger.warning(
                "%s: attempted to register resource '%s' after cleanup",
                self._name,
                name or "unnamed",
            )
            return

        resource_name = name or f"{type(resource).__name__}@{id(resource)}"

        if cleanup_func is not None:
            # Explicit cleanup function
            self._resources.append((resource_name, None, None, cleanup_func))
        else:
            # Auto-detect: store resource and method name
            method_name = self._detect_cleanup_method_name(resource)
            if method_name is None:
                logger.warning(
                    "%s: cannot auto-detect cleanup for %s, skipping",
                    self._name,
                    type(resource).__name__,
                )
                return
            self._resources.append((resource_name, resource, method_name, None))

    def _detect_cleanup_method_name(self, resource: Any) -> str | None:
        """Determine the cleanup method name for the given resource."""
        for method_name in ("stop", "deleteLater", "close"):
            try:
                # Check attribute existence WITHOUT creating via hasattr
                method = object.__getattribute__(resource, method_name)
                if callable(method):
                    return method_name
            except AttributeError:
                # Attribute does not exist — try the next one
                continue
        return None

    def cleanup_all(self) -> None:
        if self._cleaned_up:
            logger.debug("%s: cleanup_all called multiple times, ignoring", self._name)
            return

        logger.debug(
            "%s: starting cleanup of %d resources", self._name, len(self._resources)
        )
        self._cleaned_up = True
        self._cleanup_errors.clear()

        for resource_name, resource_obj, method_name, cleanup_func in reversed(
            self._resources
        ):
            try:
                if cleanup_func is not None:
                    # Explicit cleanup function
                    cleanup_func()
                elif resource_obj is not None and method_name is not None:
                    # Auto-detected method — call via getattr
                    method = getattr(resource_obj, method_name, None)
                    if callable(method):
                        method()
                logger.debug("%s: cleaned up resource '%s'", self._name, resource_name)
            except Exception as exc:
                logger.warning(
                    "%s: error cleaning up resource '%s': %s",
                    self._name,
                    resource_name,
                    exc,
                    exc_info=True,
                )
                self._cleanup_errors.append((resource_name, exc))

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
        return self._cleaned_up

    def get_cleanup_errors(self) -> list[tuple[str, Exception]]:
        return self._cleanup_errors.copy()

    def __enter__(self) -> ResourceManager:
        return self

    def __exit__(self, exc_type, _exc_val, _exc_tb) -> None:
        self.cleanup_all()

    def __del__(self) -> None:  # pragma: no cover - best-effort cleanup
        if not self._cleaned_up:
            try:
                self.cleanup_all()
            except Exception:
                pass


@contextmanager
def managed_resource(
    resource: Any,
    cleanup_func: Callable[[], None],
    name: str = "",
):
    manager = ResourceManager(name or "managed_resource")
    manager.register_resource(resource, cleanup_func, name, use_finalize=False)
    try:
        yield resource
    finally:
        manager.cleanup_all()


__all__ = ["ResourceManager", "managed_resource"]
