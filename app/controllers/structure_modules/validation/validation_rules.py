# app/controllers/structure_modules/validation_rules.py

"""Правила валидации для структурных данных."""

import logging
from typing import Any, Dict, List

from ..models.types import StructureItemType
from .validation_types import DetailedValidationResult, ValidationIssue, ValidationSeverity
from .validation_core import TypeValidator

logger = logging.getLogger(__name__)


class StructureDataValidator:
    """Валидатор для структурных данных."""

    def __init__(self):
        self.type_validator = TypeValidator()

    def validate_sphere_create_data(self, data: Dict[str, Any]) -> DetailedValidationResult:
        """Валидирует данные для создания сферы."""
        issues = []

        # Обязательные поля
        issues.extend(self.type_validator.validate_string(
            data.get("name"), "name", required=True, min_length=1, max_length=255
        ))
        issues.extend(self.type_validator.validate_boolean(
            data.get("is_active"), "is_active", required=True
        ))

        # Опциональные поля
        if "description" in data and data["description"] is not None:
            issues.extend(self.type_validator.validate_string(
                data["description"], "description", required=False, max_length=1000
            ))

        if "color" in data and data["color"] is not None:
            issues.extend(self._validate_color(data["color"], "color"))

        if "icon" in data and data["icon"] is not None:
            issues.extend(self.type_validator.validate_string(
                data["icon"], "icon", required=False, max_length=100
            ))

        return DetailedValidationResult(
            is_valid=not any(issue.severity == ValidationSeverity.ERROR for issue in issues),
            issues=issues
        )

    def validate_section_create_data(self, data: Dict[str, Any]) -> DetailedValidationResult:
        """Валидирует данные для создания раздела."""
        issues = []

        # Обязательные поля
        issues.extend(self.type_validator.validate_string(
            data.get("name"), "name", required=True, min_length=1, max_length=255
        ))
        issues.extend(self.type_validator.validate_integer(
            data.get("sphere_id"), "sphere_id", required=True, min_value=1
        ))
        issues.extend(self.type_validator.validate_boolean(
            data.get("is_active"), "is_active", required=True
        ))

        # Опциональные поля
        if "description" in data and data["description"] is not None:
            issues.extend(self.type_validator.validate_string(
                data["description"], "description", required=False, max_length=1000
            ))

        if "position" in data and data["position"] is not None:
            issues.extend(self.type_validator.validate_integer(
                data["position"], "position", required=False, min_value=0
            ))

        return DetailedValidationResult(
            is_valid=not any(issue.severity == ValidationSeverity.ERROR for issue in issues),
            issues=issues
        )

    def validate_category_create_data(self, data: Dict[str, Any]) -> DetailedValidationResult:
        """Валидирует данные для создания категории."""
        issues = []

        # Обязательные поля
        issues.extend(self.type_validator.validate_string(
            data.get("name"), "name", required=True, min_length=1, max_length=255
        ))
        issues.extend(self.type_validator.validate_integer(
            data.get("section_id"), "section_id", required=True, min_value=1
        ))
        issues.extend(self.type_validator.validate_boolean(
            data.get("is_active"), "is_active", required=True
        ))

        # Опциональные поля
        if "description" in data and data["description"] is not None:
            issues.extend(self.type_validator.validate_string(
                data["description"], "description", required=False, max_length=1000
            ))

        if "position" in data and data["position"] is not None:
            issues.extend(self.type_validator.validate_integer(
                data["position"], "position", required=False, min_value=0
            ))

        if "color" in data and data["color"] is not None:
            issues.extend(self._validate_color(data["color"], "color"))

        if "icon" in data and data["icon"] is not None:
            issues.extend(self.type_validator.validate_string(
                data["icon"], "icon", required=False, max_length=100
            ))

        return DetailedValidationResult(
            is_valid=not any(issue.severity == ValidationSeverity.ERROR for issue in issues),
            issues=issues
        )

    def validate_update_data(self, data: Dict[str, Any], item_type: StructureItemType) -> DetailedValidationResult:
        """Валидирует данные для обновления (все поля опциональны)."""
        issues = []

        # Для update операций все поля опциональны, но если присутствуют - должны быть валидными
        if "name" in data:
            issues.extend(self.type_validator.validate_string(
                data["name"], "name", required=False, min_length=1, max_length=255
            ))

        if "is_active" in data:
            issues.extend(self.type_validator.validate_boolean(
                data["is_active"], "is_active", required=False
            ))

        if "description" in data:
            issues.extend(self.type_validator.validate_string(
                data["description"], "description", required=False, max_length=1000
            ))

        # Специфичные для типа поля
        if item_type in (StructureItemType.SECTION, StructureItemType.CATEGORY):
            if "position" in data:
                issues.extend(self.type_validator.validate_integer(
                    data["position"], "position", required=False, min_value=0
                ))

        if item_type == StructureItemType.SECTION and "sphere_id" in data:
            issues.extend(self.type_validator.validate_integer(
                data["sphere_id"], "sphere_id", required=False, min_value=1
            ))

        if item_type == StructureItemType.CATEGORY and "section_id" in data:
            issues.extend(self.type_validator.validate_integer(
                data["section_id"], "section_id", required=False, min_value=1
            ))

        if item_type in (StructureItemType.SPHERE, StructureItemType.CATEGORY):
            if "color" in data and data["color"] is not None:
                issues.extend(self._validate_color(data["color"], "color"))

            if "icon" in data and data["icon"] is not None:
                issues.extend(self.type_validator.validate_string(
                    data["icon"], "icon", required=False, max_length=100
                ))

        return DetailedValidationResult(
            is_valid=not any(issue.severity == ValidationSeverity.ERROR for issue in issues),
            issues=issues
        )

    def _validate_color(self, value: Any, field_name: str) -> List[ValidationIssue]:
        """Валидирует цветовое поле (hex код)."""
        issues = []

        if not isinstance(value, str):
            issues.append(ValidationIssue(
                field=field_name,
                message=f"Field '{field_name}' must be a string, got {type(value).__name__}",
                severity=ValidationSeverity.ERROR,
                value=value,
                expected_type="str (hex color)"
            ))
            return issues

        # Проверяем формат hex цвета
        if not (value.startswith("#") and len(value) in (4, 7) and
                all(c in "0123456789ABCDEFabcdef" for c in value[1:])):
            issues.append(ValidationIssue(
                field=field_name,
                message=f"Field '{field_name}' must be a valid hex color (e.g., #FF0000 or #F00)",
                severity=ValidationSeverity.ERROR,
                value=value,
                expected_type="str (hex color)"
            ))

        return issues
