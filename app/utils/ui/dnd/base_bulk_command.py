"""Базовый класс для команд массовых операций."""

from abc import abstractmethod
from typing import Any, Dict, List, Optional
import logging

from app.controllers.ui.undo.base import BaseCommand

logger = logging.getLogger(__name__)


class BaseBulkCommand(BaseCommand):
    """Базовый класс для всех команд массовых операций."""
    
    def __init__(self, text: str, main_window: object, item_type: str):
        super().__init__(text, main_window)
        self.item_type = item_type
        self._original_state: Dict[Any, Any] = {}
        self._target_state: Dict[Any, Any] = {}
        self._prepared = False
        self._last_operation: str = "redo"
    
    @abstractmethod
    def _prepare_data(self) -> None:
        """Подготовка данных для операции."""
        pass
    
    @abstractmethod
    def _execute_operation(self) -> bool:
        """Выполнение основной операции."""
        pass
    
    @abstractmethod
    def _restore_original_state(self) -> bool:
        """Восстановление исходного состояния."""
        pass
    
    def prepare_if_needed(self) -> None:
        """Подготовка данных при необходимости."""
        if not self._prepared:
            self._prepare_data()
            self._prepared = True
    
    def _refresh_ui(self, affected_items: List[Any] = None) -> None:
        """Обновление UI после операции."""
        # Базовая реализация - переопределяется в наследниках
        if affected_items:
            logger.debug(f"Refreshing UI for {len(affected_items)} {self.item_type}(s)")
    
    def redo(self) -> None:
        """Выполнение команды."""
        self._last_operation = "redo"
        self.prepare_if_needed()
        success = self._execute_operation()
        if success:
            self._refresh_ui()
    
    def undo(self) -> None:
        """Отмена команды."""
        self._last_operation = "undo"
        success = self._restore_original_state()
        if success:
            self._refresh_ui()
    
    def set_obsolete(self, value: bool = True) -> None:
        """Пометить команду как устаревшую."""
        try:
            self.setObsolete(value)
        except Exception:
            pass
