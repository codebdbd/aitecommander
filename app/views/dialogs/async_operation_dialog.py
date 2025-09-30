"""Диалог для отображения прогресса асинхронных операций с БД."""
import logging
from typing import Optional

from PyQt6.QtCore import Qt, pyqtSlot
from PyQt6.QtWidgets import (
    QDialog,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)


class AsyncOperationDialog(QDialog):
    """Диалог прогресса для асинхронных операций БД.
    
    Features:
    - Progress bar с процентами
    - Текстовое описание текущего этапа
    - Кнопка отмены (опционально)
    - Автозакрытие при успехе
    """
    
    def __init__(
        self,
        title: str = "Операция",
        message: str = "Выполняется...",
        cancelable: bool = False,
        parent: Optional[QWidget] = None
    ):
        """
        Args:
            title: Заголовок окна
            message: Начальное сообщение
            cancelable: Показывать ли кнопку отмены
            parent: Родительский виджет
        """
        super().__init__(parent)
        
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(400)
        
        self._cancelled = False
        self._auto_close = True
        
        # Layout
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        
        # Сообщение
        self.message_label = QLabel(message)
        self.message_label.setWordWrap(True)
        layout.addWidget(self.message_label)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        layout.addWidget(self.progress_bar)
        
        # Детали (текущий этап)
        self.detail_label = QLabel("")
        self.detail_label.setWordWrap(True)
        self.detail_label.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(self.detail_label)
        
        # Кнопка отмены
        if cancelable:
            self.cancel_button = QPushButton("Отмена")
            self.cancel_button.clicked.connect(self._on_cancel)
            layout.addWidget(self.cancel_button)
        else:
            self.cancel_button = None
        
        layout.addStretch()
    
    def set_auto_close(self, auto_close: bool):
        """Устанавливает автозакрытие при успешном завершении."""
        self._auto_close = auto_close
    
    @pyqtSlot(int, int, str)
    def update_progress(self, current: int, total: int, message: str = ""):
        """Обновляет прогресс операции.
        
        Args:
            current: Текущий прогресс
            total: Общее количество
            message: Сообщение о текущем этапе
        """
        if total > 0:
            percentage = int((current / total) * 100)
            self.progress_bar.setValue(percentage)
            self.progress_bar.setFormat(f"{percentage}% ({current}/{total})")
        
        if message:
            self.detail_label.setText(message)
    
    @pyqtSlot(object)
    def on_finished(self, result):
        """Вызывается при успешном завершении операции.
        
        Args:
            result: Результат операции
        """
        self.progress_bar.setValue(100)
        self.message_label.setText("✅ Операция завершена успешно")
        self.detail_label.setText("")
        
        if self.cancel_button:
            self.cancel_button.setEnabled(False)
        
        if self._auto_close:
            self.accept()
        else:
            # Меняем кнопку на "Закрыть"
            if self.cancel_button:
                self.cancel_button.setText("Закрыть")
                self.cancel_button.setEnabled(True)
                self.cancel_button.clicked.disconnect()
                self.cancel_button.clicked.connect(self.accept)
    
    @pyqtSlot(Exception, str)
    def on_error(self, exception: Exception, traceback: str):
        """Вызывается при ошибке.
        
        Args:
            exception: Исключение
            traceback: Traceback
        """
        self.progress_bar.setValue(0)
        self.message_label.setText(f"❌ Ошибка: {str(exception)}")
        self.detail_label.setText("")
        
        if self.cancel_button:
            self.cancel_button.setText("Закрыть")
            self.cancel_button.clicked.disconnect()
            self.cancel_button.clicked.connect(self.reject)
        
        logger.error("Ошибка асинхронной операции: %s\n%s", exception, traceback)
    
    @pyqtSlot()
    def on_cancelled(self):
        """Вызывается когда операция отменена."""
        self.message_label.setText("⚠️ Операция отменена")
        self.detail_label.setText("")
        self.reject()
    
    def _on_cancel(self):
        """Обработчик нажатия кнопки отмены."""
        self._cancelled = True
        self.message_label.setText("Отмена операции...")
        if self.cancel_button:
            self.cancel_button.setEnabled(False)
    
    def is_cancelled(self) -> bool:
        """Проверяет, отменена ли операция."""
        return self._cancelled
