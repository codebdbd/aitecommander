# app/controllers/structure_modules/validation_types.py

"""Basic types and exceptions for validation system."""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

from .validation_result import ValidationResult


class ValidationError(Exception):
    """Exception for validation errors."""

    def __init__(self, message: str, field: Optional[str] = None, value: Any = None):
        super().__init__(message)
        self.field = field
        self.value = value
        self.message = message


class ValidationSeverity(Enum):
    """Validation error severity levels."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class ValidationIssue:
    """Individual validation issue."""

    field: str
    message: str
    severity: ValidationSeverity
    value: Any = None
    expected_type: Optional[str] = None


@dataclass
class DetailedValidationResult:
    """Detailed validation result."""

    is_valid: bool
    issues: list[ValidationIssue]

    @property
    def errors(self) -> list[ValidationIssue]:
        """Errors only."""
        return [
            issue for issue in self.issues if issue.severity == ValidationSeverity.ERROR
        ]

    @property
    def warnings(self) -> list[ValidationIssue]:
        """Warnings only."""
        return [
            issue
            for issue in self.issues
            if issue.severity == ValidationSeverity.WARNING
        ]

    def to_simple_result(self) -> ValidationResult:
        """Converts to simple ValidationResult for backward compatibility."""
        return ValidationResult(
            is_valid=self.is_valid,
            errors=[issue.message for issue in self.errors],
            warnings=[issue.message for issue in self.warnings],
        )
