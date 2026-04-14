"""Result infrastructure for service and business layers."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Generic, TypeVar


class ResultStatus(str, Enum):
    """Enumeration of supported result states."""

    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL = "partial"


@dataclass(slots=True, frozen=True)
class InvalidateRegion:
    """Represents a UI region that must be refreshed."""

    scope: str
    identifier: str | int | None = None
    payload: dict[str, Any] | None = None


@dataclass(slots=True, frozen=True)
class ErrorNotification:
    """Describes a user-facing error notification request."""

    context: str
    title: str
    message: str
    details: str | None = None


TValue = TypeVar("TValue")


@dataclass(slots=True, frozen=True)
class Result(Generic[TValue]):
    """Structured outcome for service and business logic calls."""

    status: ResultStatus
    value: TValue | None = None
    error: Exception | None = None
    warnings: tuple[str, ...] = field(default_factory=tuple)
    invalidate_regions: tuple[InvalidateRegion, ...] = field(default_factory=tuple)
    notifications: tuple[ErrorNotification, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        """Validate invariants for the result instance."""

        if self.status is ResultStatus.SUCCESS:
            if self.error is not None:
                raise ValueError("Success result cannot contain an error instance")
        elif self.status is ResultStatus.FAILURE:
            if self.error is None:
                raise ValueError("Failure result must contain an error instance")
        else:  # PARTIAL
            if self.error is None and not self.warnings:
                raise ValueError(
                    "Partial result requires warnings or an error description"
                )

    def is_success(self) -> bool:
        """Return True when the result represents a successful execution."""

        return self.status is ResultStatus.SUCCESS

    def is_failure(self) -> bool:
        """Return True when the result represents a failed execution."""

        return self.status is ResultStatus.FAILURE

    def require_value(self) -> TValue:
        """Return the underlying value or raise the stored error."""

        if self.is_failure():
            if self.error:
                raise self.error
            raise RuntimeError("Failure result does not contain an error instance")
        if self.value is None:
            raise RuntimeError("Success result does not contain a value")
        return self.value

    def merge(self, other: Result[TValue]) -> Result[TValue]:
        """Combine metadata from another result, preserving this instance's status."""

        if self.value != other.value:
            combined_value = self.value or other.value
        else:
            combined_value = self.value

        combined_warnings = self.warnings + other.warnings
        combined_invalidate = self.invalidate_regions + other.invalidate_regions
        combined_notifications = self.notifications + other.notifications

        if self.status is ResultStatus.FAILURE or other.status is ResultStatus.FAILURE:
            error = self.error or other.error
            return Result[
                TValue
            ](
                status=ResultStatus.FAILURE,
                value=combined_value,
                error=error or RuntimeError("Aggregated failure without error detail"),
                warnings=combined_warnings,
                invalidate_regions=combined_invalidate,
                notifications=combined_notifications,
            )

        if (
            self.status is ResultStatus.PARTIAL
            or other.status is ResultStatus.PARTIAL
            or combined_warnings
        ):
            return Result[
                TValue
            ](
                status=ResultStatus.PARTIAL,
                value=combined_value,
                error=self.error or other.error,
                warnings=combined_warnings,
                invalidate_regions=combined_invalidate,
                notifications=combined_notifications,
            )

        return Result[
            TValue
        ](
            status=ResultStatus.SUCCESS,
            value=combined_value,
            warnings=combined_warnings,
            invalidate_regions=combined_invalidate,
            notifications=combined_notifications,
        )

    @classmethod
    def success(
        cls,
        value: TValue | None = None,
        *,
        warnings: Sequence[str] | None = None,
        invalidate: Iterable[InvalidateRegion] | None = None,
        notifications: Iterable[ErrorNotification] | None = None,
    ) -> Result[TValue]:
        """Create a successful result."""

        return cls(
            status=ResultStatus.SUCCESS,
            value=value,
            warnings=tuple(warnings or ()),
            invalidate_regions=tuple(invalidate or ()),
            notifications=tuple(notifications or ()),
        )

    @classmethod
    def failure(
        cls,
        error: Exception,
        *,
        value: TValue | None = None,
        warnings: Sequence[str] | None = None,
        invalidate: Iterable[InvalidateRegion] | None = None,
        notifications: Iterable[ErrorNotification] | None = None,
    ) -> Result[TValue]:
        """Create a failed result."""

        return cls(
            status=ResultStatus.FAILURE,
            value=value,
            error=error,
            warnings=tuple(warnings or ()),
            invalidate_regions=tuple(invalidate or ()),
            notifications=tuple(notifications or ()),
        )

    @classmethod
    def partial(
        cls,
        value: TValue | None,
        *,
        error: Exception | None = None,
        warnings: Sequence[str] | None = None,
        invalidate: Iterable[InvalidateRegion] | None = None,
        notifications: Iterable[ErrorNotification] | None = None,
    ) -> Result[TValue]:
        """Create a partial result that combines success data with issues."""

        warnings_tuple = tuple(warnings or ())
        if error is None and not warnings_tuple:
            raise ValueError("Partial result requires error or warnings")
        return cls(
            status=ResultStatus.PARTIAL,
            value=value,
            error=error,
            warnings=warnings_tuple,
            invalidate_regions=tuple(invalidate or ()),
            notifications=tuple(notifications or ()),
        )


__all__ = [
    "ErrorNotification",
    "InvalidateRegion",
    "Result",
    "ResultStatus",
]
