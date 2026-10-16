"""Architectural guard: verify ApplicationInitializer cleanup is called through aboutToQuit only."""

from unittest.mock import MagicMock

from app.startup.initializer import ApplicationInitializer


def test_no_initializer_cleanup_handler_in_shutdown_controller() -> None:
    """Verify ApplicationInitializer does NOT register a shutdown handler in AppShutdownController."""
    mock_app = MagicMock()
    initializer = ApplicationInitializer(mock_app)

    # The registration call was deleted in Stage 3; ensure it remains absent
    assert not hasattr(initializer, "_cleanup_via_shutdown_controller")
    assert not hasattr(initializer, "_shutdown_cleanup_started")


def test_initializer_cleanup_is_idempotent() -> None:
    """Verify ApplicationInitializer.cleanup() runs cleanly and is idempotent."""
    mock_app = MagicMock()
    mock_pool = MagicMock()
    mock_pool.activeThreadCount.return_value = 0
    mock_pool.waitForDone.return_value = True
    initializer = ApplicationInitializer(mock_app, thread_pool=mock_pool)

    # Initial state
    assert initializer.has_pending_cleanup() is True
    assert initializer._cleanup_done is False

    # First cleanup execution
    res1 = initializer.cleanup(async_cleanup=False)
    assert res1 is True
    assert initializer._cleanup_done is True
    assert initializer.has_pending_cleanup() is False

    # Second cleanup execution must be an immediate no-op returning True
    res2 = initializer.cleanup(async_cleanup=False)
    assert res2 is True
    assert initializer._cleanup_done is True
