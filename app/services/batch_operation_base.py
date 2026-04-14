"""Shared helpers for batch/bulk operations."""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Callable, Iterable, TypeVar

logger = logging.getLogger(__name__)

ERROR_CODE_VALIDATION = "validation_error"
ERROR_CODE_BATCH_SIZE = "batch_size_exceeded"
ERROR_CODE_REPOSITORY = "repository_error"


class BulkOperationError(RuntimeError):
    """Base error for batch/bulk operation failures."""

    def __init__(self, message: str, *, code: str = "bulk_error") -> None:
        super().__init__(message)
        self.code = code


class BulkOperationValidationError(BulkOperationError):
    """Raised when batch operation input validation fails."""

    def __init__(self, message: str, *, code: str = ERROR_CODE_VALIDATION) -> None:
        super().__init__(message, code=code)


class BulkOperationRepositoryError(BulkOperationError):
    """Raised when repository call fails during batch operation."""

    def __init__(self, message: str, *, code: str = ERROR_CODE_REPOSITORY) -> None:
        super().__init__(message, code=code)


@dataclass(slots=True)
class BatchContext:
    operation: str
    total_items: int
    chunk_size: int
    chunks: int
    skipped: int = 0
    operation_id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])


T = TypeVar("T")
R = TypeVar("R")


class BaseBatchOperation:
    """Base class with shared batching, logging and error handling."""

    def __init__(self, *, logger: logging.Logger, max_batch_size: int | None) -> None:
        self._logger = logger
        self._max_batch_size = max_batch_size if max_batch_size and max_batch_size > 0 else None

    def _resolve_chunk_size(
        self,
        *,
        total_items: int,
        operation: str,
        allow_chunking: bool,
    ) -> int:
        if self._max_batch_size is None or total_items <= self._max_batch_size:
            return total_items
        if not allow_chunking:
            raise BulkOperationValidationError(
                f"{operation}: batch size {total_items} exceeds limit {self._max_batch_size}",
                code=ERROR_CODE_BATCH_SIZE,
            )
        self._logger.info(
            "[Batch] op=%s items=%s exceeds limit=%s -> chunking",
            operation,
            total_items,
            self._max_batch_size,
        )
        return self._max_batch_size

    @staticmethod
    def _iter_chunks(items: list[T], chunk_size: int) -> Iterable[list[T]]:
        if chunk_size <= 0:
            yield items
            return
        for start in range(0, len(items), chunk_size):
            yield items[start : start + chunk_size]

    @staticmethod
    def _duration_ms(start: float) -> float:
        return (time.perf_counter() - start) * 1000.0

    def _execute_batch(
        self,
        *,
        operation: str,
        items: list[T],
        process_chunk: Callable[[list[T]], R],
        combine_results: Callable[[list[R]], R],
        empty_result: R,
        skipped: int = 0,
        allow_chunking: bool = True,
        error_message: str | None = None,
    ) -> R:
        total_items = len(items)
        if total_items == 0:
            self._logger.debug(
                "[Batch] op=%s empty payload (skipped=%s)",
                operation,
                skipped,
            )
            return empty_result

        chunk_size = self._resolve_chunk_size(
            total_items=total_items,
            operation=operation,
            allow_chunking=allow_chunking,
        )
        chunks = list(self._iter_chunks(items, chunk_size))
        context = BatchContext(
            operation=operation,
            total_items=total_items,
            chunk_size=chunk_size,
            chunks=len(chunks),
            skipped=skipped,
        )

        start = time.perf_counter()
        results: list[R] = []
        for idx, chunk in enumerate(chunks, start=1):
            try:
                results.append(process_chunk(chunk))
            except BulkOperationValidationError:
                raise
            except Exception as exc:
                self._logger.exception(
                    "[Batch] op=%s id=%s chunk=%s/%s failed",
                    context.operation,
                    context.operation_id,
                    idx,
                    context.chunks,
                )
                raise BulkOperationRepositoryError(
                    error_message or f"{operation} failed"
                ) from exc
        duration_ms = self._duration_ms(start)
        self._logger.info(
            "[Batch] op=%s id=%s items=%s chunks=%s skipped=%s ms=%.2f",
            context.operation,
            context.operation_id,
            context.total_items,
            context.chunks,
            context.skipped,
            duration_ms,
        )
        return combine_results(results)


__all__ = [
    "BaseBatchOperation",
    "BatchContext",
    "BulkOperationError",
    "BulkOperationRepositoryError",
    "BulkOperationValidationError",
    "ERROR_CODE_BATCH_SIZE",
    "ERROR_CODE_REPOSITORY",
    "ERROR_CODE_VALIDATION",
]
