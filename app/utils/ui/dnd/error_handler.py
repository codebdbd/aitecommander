"""Центральная система обработки ошибок для массовых операций."""

from enum import Enum
from typing import Dict, Any, Optional
import logging
import time

class BulkOperationErrorType(Enum):
    VALIDATION_ERROR = "validation"
    DATABASE_ERROR = "database"
    DUPLICATE_ERROR = "duplicate"
    PERMISSION_ERROR = "permission"
    NETWORK_ERROR = "network"
    TIMEOUT_ERROR = "timeout"

class BulkOperationErrorHandler:
    """Центральная система обработки ошибок для массовых операций."""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def handle_error(self, error: Exception, context: Dict[str, Any]) -> Dict[str, Any]:
        """Обработка ошибки с созданием отчета."""
        error_type = self._classify_error(error)
        error_report = {
            "type": error_type.value,
            "message": str(error),
            "context": context,
            "timestamp": time.time(),
            "handled": True
        }
        
        self._log_error(error_report)
        return error_report
    
    def _classify_error(self, error: Exception) -> BulkOperationErrorType:
        """Классификация типа ошибки."""
        error_str = str(error).lower()
        
        if "duplicate" in error_str or "unique constraint" in error_str:
            return BulkOperationErrorType.DUPLICATE_ERROR
        elif "validation" in error_str or "invalid" in error_str:
            return BulkOperationErrorType.VALIDATION_ERROR
        elif "database" in error_str or "sql" in error_str:
            return BulkOperationErrorType.DATABASE_ERROR
        elif "permission" in error_str or "access denied" in error_str:
            return BulkOperationErrorType.PERMISSION_ERROR
        elif "timeout" in error_str:
            return BulkOperationErrorType.TIMEOUT_ERROR
        elif "network" in error_str or "connection" in error_str:
            return BulkOperationErrorType.NETWORK_ERROR
        else:
            return BulkOperationErrorType.DATABASE_ERROR  # По умолчанию
    
    def _log_error(self, error_report: Dict[str, Any]) -> None:
        """Логирование ошибки."""
        self.logger.error(
            f"Bulk operation error: {error_report['type']} - {error_report['message']}, "
            f"context: {error_report['context']}"
        )
    
    def handle_validation_error(self, message: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Обработка ошибки валидации."""
        error = ValueError(message)
        return self.handle_error(error, context)
    
    def handle_duplicate_error(self, message: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Обработка ошибки дубликата."""
        error = ValueError(f"Duplicate error: {message}")
        return self.handle_error(error, context)