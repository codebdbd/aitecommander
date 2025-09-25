# app/controllers/structure_modules/validators.py

"""Runtime валидация для structure_modules - PyQt6 Best Practices.

Этот модуль предоставляет runtime валидацию для всех TypedDict структур
и входных данных. Использует встроенные возможности Python без внешних
зависимостей для максимальной совместимости.
"""

import logging
from typing import Any, Dict, List, Optional, Union, get_type_hints
from dataclasses import dataclass
from enum import Enum

from .types import (
    SphereData, SectionData, CategoryData, LinkData,
    SphereCreateData, SectionCreateData, CategoryCreateData,
    SphereUpdateData, SectionUpdateData, CategoryUpdateData,
    StructureItemType, SignalType, ValidationResult
)

logger = logging.getLogger(__name__)


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


class TypeValidator:
    """Валидатор типов данных."""
    
    @staticmethod
    def validate_string(value: Any, field_name: str, required: bool = True, 
                       min_length: int = 0, max_length: Optional[int] = None) -> List[ValidationIssue]:
        """Валидирует строковое поле."""
        issues = []
        
        if value is None:
            if required:
                issues.append(ValidationIssue(
                    field=field_name,
                    message=f"Field '{field_name}' is required",
                    severity=ValidationSeverity.ERROR,
                    value=value,
                    expected_type="str"
                ))
            return issues
        
        if not isinstance(value, str):
            issues.append(ValidationIssue(
                field=field_name,
                message=f"Field '{field_name}' must be a string, got {type(value).__name__}",
                severity=ValidationSeverity.ERROR,
                value=value,
                expected_type="str"
            ))
            return issues
        
        if len(value) < min_length:
            issues.append(ValidationIssue(
                field=field_name,
                message=f"Field '{field_name}' must be at least {min_length} characters long",
                severity=ValidationSeverity.ERROR,
                value=value
            ))
        
        if max_length and len(value) > max_length:
            issues.append(ValidationIssue(
                field=field_name,
                message=f"Field '{field_name}' must be at most {max_length} characters long",
                severity=ValidationSeverity.WARNING,
                value=value
            ))
        
        return issues
    
    @staticmethod
    def validate_integer(value: Any, field_name: str, required: bool = True,
                        min_value: Optional[int] = None, max_value: Optional[int] = None) -> List[ValidationIssue]:
        """Валидирует целочисленное поле."""
        issues = []
        
        if value is None:
            if required:
                issues.append(ValidationIssue(
                    field=field_name,
                    message=f"Field '{field_name}' is required",
                    severity=ValidationSeverity.ERROR,
                    value=value,
                    expected_type="int"
                ))
            return issues
        
        if not isinstance(value, int):
            issues.append(ValidationIssue(
                field=field_name,
                message=f"Field '{field_name}' must be an integer, got {type(value).__name__}",
                severity=ValidationSeverity.ERROR,
                value=value,
                expected_type="int"
            ))
            return issues
        
        if min_value is not None and value < min_value:
            issues.append(ValidationIssue(
                field=field_name,
                message=f"Field '{field_name}' must be at least {min_value}",
                severity=ValidationSeverity.ERROR,
                value=value
            ))
        
        if max_value is not None and value > max_value:
            issues.append(ValidationIssue(
                field=field_name,
                message=f"Field '{field_name}' must be at most {max_value}",
                severity=ValidationSeverity.WARNING,
                value=value
            ))
        
        return issues
    
    @staticmethod
    def validate_boolean(value: Any, field_name: str, required: bool = True) -> List[ValidationIssue]:
        """Валидирует булево поле."""
        issues = []
        
        if value is None:
            if required:
                issues.append(ValidationIssue(
                    field=field_name,
                    message=f"Field '{field_name}' is required",
                    severity=ValidationSeverity.ERROR,
                    value=value,
                    expected_type="bool"
                ))
            return issues
        
        if not isinstance(value, bool):
            issues.append(ValidationIssue(
                field=field_name,
                message=f"Field '{field_name}' must be a boolean, got {type(value).__name__}",
                severity=ValidationSeverity.ERROR,
                value=value,
                expected_type="bool"
            ))
        
        return issues


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


# Глобальный экземпляр валидатора
_validator = StructureDataValidator()


def validate_create_data(data: Dict[str, Any], item_type: StructureItemType) -> DetailedValidationResult:
    """Валидирует данные для создания элемента структуры."""
    if item_type == StructureItemType.SPHERE:
        return _validator.validate_sphere_create_data(data)
    elif item_type == StructureItemType.SECTION:
        return _validator.validate_section_create_data(data)
    elif item_type == StructureItemType.CATEGORY:
        return _validator.validate_category_create_data(data)
    else:
        raise ValueError(f"Unsupported item type: {item_type}")


def validate_update_data(data: Dict[str, Any], item_type: StructureItemType) -> DetailedValidationResult:
    """Валидирует данные для обновления элемента структуры."""
    return _validator.validate_update_data(data, item_type)


def validate_and_raise(data: Dict[str, Any], item_type: StructureItemType, is_update: bool = False) -> None:
    """Валидирует данные и выбрасывает исключение при ошибках."""
    if is_update:
        result = validate_update_data(data, item_type)
    else:
        result = validate_create_data(data, item_type)
    
    if not result.is_valid:
        error_messages = [issue.message for issue in result.errors]
        raise ValidationError(
            f"Validation failed for {item_type.value}: {'; '.join(error_messages)}"
        )
    
    # Логируем предупреждения
    if result.warnings:
        warning_messages = [issue.message for issue in result.warnings]
        logger.warning(
            "Validation warnings for %s: %s", 
            item_type.value, 
            "; ".join(warning_messages)
        )


def safe_validate(data: Dict[str, Any], item_type: StructureItemType, is_update: bool = False) -> ValidationResult:
    """Безопасная валидация, возвращающая результат без исключений."""
    try:
        if is_update:
            result = validate_update_data(data, item_type)
        else:
            result = validate_create_data(data, item_type)
        
        return result.to_simple_result()
    except Exception as e:
        logger.exception("Unexpected error during validation: %s", e)
        return ValidationResult(
            is_valid=False,
            errors=[f"Validation error: {str(e)}"],
            warnings=[]
        )
