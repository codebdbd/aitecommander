# app/controllers/structure_modules/validation_result.py
from __future__ import annotations

from typing import List, Optional


class ValidationResult:
    """Результат валидации данных.
    Совместим по интерфейсу с прежней реализацией.
    """

    def __init__(self, is_valid: bool = True, errors: Optional[List[str]] = None):
        self.is_valid = is_valid
        self.errors = errors or []

    def add_error(self, error: str) -> None:
        """Добавляет ошибку валидации и помечает результат как невалидный."""
        self.is_valid = False
        self.errors.append(error)
