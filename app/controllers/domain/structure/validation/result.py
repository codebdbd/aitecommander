from __future__ import annotations

from typing import List, Optional


class ValidationResult:
    """Результат валидации данных."""

    def __init__(self, is_valid: bool = True, errors: Optional[List[str]] = None):
        self.is_valid = is_valid
        self.errors = errors or []

    def add_error(self, error: str) -> None:
        """Добавляет ошибку валидации."""
        self.is_valid = False
        self.errors.append(error)
