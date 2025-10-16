# app/controllers/structure_modules/validation_core.py

"""Base data type validator."""

from typing import Any, Optional

from .validation_types import ValidationIssue, ValidationSeverity


class TypeValidator:
    """Data type validator."""

    @staticmethod
    def validate_string(
        value: Any,
        field_name: str,
        required: bool = True,
        min_length: int = 0,
        max_length: Optional[int] = None,
    ) -> list[ValidationIssue]:
        """Validate string field."""
        issues = []

        if value is None:
            if required:
                issues.append(
                    ValidationIssue(
                        field=field_name,
                        message=f"Field '{field_name}' is required",
                        severity=ValidationSeverity.ERROR,
                        value=value,
                        expected_type="str",
                    )
                )
            return issues

        if not isinstance(value, str):
            issues.append(
                ValidationIssue(
                    field=field_name,
                    message=f"Field '{field_name}' must be a string, got {type(value).__name__}",
                    severity=ValidationSeverity.ERROR,
                    value=value,
                    expected_type="str",
                )
            )
            return issues

        if len(value) < min_length:
            issues.append(
                ValidationIssue(
                    field=field_name,
                    message=f"Field '{field_name}' must be at least {min_length} characters long",
                    severity=ValidationSeverity.ERROR,
                    value=value,
                )
            )

        if max_length and len(value) > max_length:
            issues.append(
                ValidationIssue(
                    field=field_name,
                    message=f"Field '{field_name}' must be at most {max_length} characters long",
                    severity=ValidationSeverity.WARNING,
                    value=value,
                )
            )

        return issues

    @staticmethod
    def validate_integer(
        value: Any,
        field_name: str,
        required: bool = True,
        min_value: Optional[int] = None,
        max_value: Optional[int] = None,
    ) -> list[ValidationIssue]:
        """Validate integer field."""
        issues = []

        if value is None:
            if required:
                issues.append(
                    ValidationIssue(
                        field=field_name,
                        message=f"Field '{field_name}' is required",
                        severity=ValidationSeverity.ERROR,
                        value=value,
                        expected_type="int",
                    )
                )
            return issues

        if not isinstance(value, int):
            issues.append(
                ValidationIssue(
                    field=field_name,
                    message=f"Field '{field_name}' must be an integer, got {type(value).__name__}",
                    severity=ValidationSeverity.ERROR,
                    value=value,
                    expected_type="int",
                )
            )
            return issues

        if min_value is not None and value < min_value:
            issues.append(
                ValidationIssue(
                    field=field_name,
                    message=f"Field '{field_name}' must be at least {min_value}",
                    severity=ValidationSeverity.ERROR,
                    value=value,
                )
            )

        if max_value is not None and value > max_value:
            issues.append(
                ValidationIssue(
                    field=field_name,
                    message=f"Field '{field_name}' must be at most {max_value}",
                    severity=ValidationSeverity.WARNING,
                    value=value,
                )
            )

        return issues

    @staticmethod
    def validate_boolean(
        value: Any, field_name: str, required: bool = True
    ) -> list[ValidationIssue]:
        """Validate boolean field."""
        issues = []

        if value is None:
            if required:
                issues.append(
                    ValidationIssue(
                        field=field_name,
                        message=f"Field '{field_name}' is required",
                        severity=ValidationSeverity.ERROR,
                        value=value,
                        expected_type="bool",
                    )
                )
            return issues

        if not isinstance(value, bool):
            issues.append(
                ValidationIssue(
                    field=field_name,
                    message=f"Field '{field_name}' must be a boolean, got {type(value).__name__}",
                    severity=ValidationSeverity.ERROR,
                    value=value,
                    expected_type="bool",
                )
            )

        return issues
