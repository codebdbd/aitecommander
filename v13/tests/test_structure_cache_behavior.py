from __future__ import annotations

import logging
import pytest

from app.controllers.business.structure_cache import StructureCache


class _RaisingCache:
    def __init__(self, err: Exception):
        self._err = err
        self.calls = []

    def invalidate(self, key: str | None = None) -> None:  # simulate both key/no-key
        self.calls.append(key)
        raise self._err

    # stubs to satisfy StructureCache.get/set passthroughs if ever used
    def get(self, key: str):  # pragma: no cover - not used in these tests
        return None

    def set(self, key: str, value):  # pragma: no cover - not used in these tests
        return None


@pytest.mark.parametrize("exc_type", [AttributeError, RuntimeError])
def test_invalidate_structure_expected_errors_are_logged_and_suppressed(caplog, exc_type):
    cache = _RaisingCache(exc_type("boom"))
    sc = StructureCache(
        cache_manager=cache,
        get_current_sphere_id=lambda: 123,
        logger=logging.getLogger("structure_cache_test"),
    )

    with caplog.at_level(logging.DEBUG):
        sc.invalidate_structure()

    # No exception propagated
    # Check that invalidate was attempted three times with sphere-specific keys
    assert cache.calls == [
        "structure_123",
        "sections_123",
        "first_category_id:123",
    ]

    # Ensure a debug log mentioning expected failure is present
    assert any(
        "failed (expected)" in rec.getMessage()
        for rec in caplog.records
    )


def test_invalidate_structure_unexpected_errors_are_propagated(caplog):
    cache = _RaisingCache(ValueError("unexpected"))
    sc = StructureCache(
        cache_manager=cache,
        get_current_sphere_id=lambda: 123,
        logger=logging.getLogger("structure_cache_test"),
    )

    with caplog.at_level(logging.DEBUG):
        with pytest.raises(ValueError):
            sc.invalidate_structure()

    # Should log with exception severity for unexpected errors
    assert any(
        "unexpected error" in rec.getMessage() and rec.levelno >= logging.ERROR
        for rec in caplog.records
    )


@pytest.mark.parametrize("exc_type", [AttributeError, RuntimeError])
def test_clear_all_expected_errors_are_logged_and_suppressed(caplog, exc_type):
    cache = _RaisingCache(exc_type("boom"))
    sc = StructureCache(
        cache_manager=cache,
        get_current_sphere_id=lambda: 123,
        logger=logging.getLogger("structure_cache_test"),
    )

    with caplog.at_level(logging.DEBUG):
        sc.clear_all()

    # Only one attempt without key
    assert cache.calls == [None]

    assert any(
        "failed (expected)" in rec.getMessage()
        for rec in caplog.records
    )


def test_clear_all_unexpected_errors_are_propagated(caplog):
    cache = _RaisingCache(ValueError("unexpected"))
    sc = StructureCache(
        cache_manager=cache,
        get_current_sphere_id=lambda: 123,
        logger=logging.getLogger("structure_cache_test"),
    )

    with caplog.at_level(logging.DEBUG):
        with pytest.raises(ValueError):
            sc.clear_all()

    assert any(
        "unexpected error" in rec.getMessage() and rec.levelno >= logging.ERROR
        for rec in caplog.records
    )
