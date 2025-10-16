# app/controllers/structure_modules/validation_result.py
from __future__ import annotations

from typing import List, Optional


class ValidationResult:
    """Data validation result.
    Compatible with previous implementation interface.
    """

    def __init__(
        self,
        is_valid: bool = True,
        errors: Optional[List[str]] = None,
        warnings: Optional[List[str]] = None,
    ) -> None:
        self.is_valid = is_valid
        self.errors = errors or []
        self.warnings = warnings or []

    def add_error(self, error: str) -> None:
        """Add validation error and mark result as invalid."""
        self.is_valid = False
        self.errors.append(error)

    def add_warning(self, warning: str) -> None:
        """Add warning without changing overall validity status."""
        self.warnings.append(warning)
