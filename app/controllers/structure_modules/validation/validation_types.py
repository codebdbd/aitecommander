# app/controllers/structure_modules/validation_types.py

"""Базовые типы и исключения для системы валидации."""

from typing import Any, List, Optional
from dataclasses import dataclass
from enum import Enum

from .validation_result import ValidationResult


class ValidationError(Exception):
    """Исключение для ошибок валидации."""

    def __init__(self, message: str, field: Optional[str] = None, value: Any = None):
        super().__init__(message)
        self.field = field
        self.value = value
        self.message = message


class ValidationSeverity(Enum):
    """Уровни серьезности ошибок валидации."""
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class ValidationIssue:
    """Отдельная проблема валидации."""
    field: str
    message: str
    severity: ValidationSeverity
    value: Any = None
    expected_type: Optional[str] = None


@dataclass
class DetailedValidationResult:
    """Детальный результат валидации."""
    is_valid: bool
    issues: List[ValidationIssue]

    @property
    def errors(self) -> List[ValidationIssue]:
        """Только ошибки."""
        return [issue for issue in self.issues if issue.severity == ValidationSeverity.ERROR]

    @property
    def warnings(self) -> List[ValidationIssue]:
        """Только предупреждения."""
        return [issue for issue in self.issues if issue.severity == ValidationSeverity.WARNING]

    def to_simple_result(self) -> ValidationResult:
        """Преобразует в простой ValidationResult для обратной совместимости."""
        return ValidationResult(
            is_valid=self.is_valid,
            errors=[issue.message for issue in self.errors],
            warnings=[issue.message for issue in self.warnings]
        )
