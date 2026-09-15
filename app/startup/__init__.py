"""Modules for application initialization and startup."""

from __future__ import annotations

__all__ = [
    "ApplicationInitializer",
    "THREAD_POOL_SHUTDOWN_TIMEOUT_MS",
    "StartupMode",
    "application_context",
    "initialization_method",
    "retry_on_failure",
    "ExitCode",
    "StartupOptions",
    "run",
]


def __getattr__(name: str):
    if name in {
        "ApplicationInitializer",
        "THREAD_POOL_SHUTDOWN_TIMEOUT_MS",
        "StartupMode",
        "application_context",
        "initialization_method",
        "retry_on_failure",
    }:
        from app.startup import initializer

        return getattr(initializer, name)
    if name in {"ExitCode", "StartupOptions", "run"}:
        from app.startup import runtime

        return getattr(runtime, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
