"""Диалог прогресса обновления иконок."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import QCoreApplication, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.config_data.runtime_config import runtime_app_config as app_config
from app.utils.i18n.common import tr as tr_common
from app.views.windows.dialogs.base_dialog import BaseDialog

if TYPE_CHECKING:
    from app.controllers.services.icon_refresh_service import IconRefreshService

logger = logging.getLogger(__name__)

_TR_CONTEXT = "IconRefreshDialog"


def _tr(text: str, disambiguation: str | None = None) -> str:
    return QCoreApplication.translate(_TR_CONTEXT, text, disambiguation)


class IconRefreshDialog(BaseDialog):
    """Диалог для отображения прогресса обновления иконок.
    
    Показывает прогресс-бар и статистику обновления иконок.
    Позволяет отменить операцию или скрыть диалог в фоновый режим.
    """

    refresh_started = pyqtSignal()
    
    def __init__(
        self,
        service: IconRefreshService,
        parent=None,
        *,
        allow_background: bool = True,
        start_options: dict[str, Any] | None = None,
    ):
        """
        Args:
            service: Сервис обновления иконок
            parent: Родительский виджет
            allow_background: Разрешить скрытие диалога в фон
            start_options: Параметры запуска сервиса
        """
        self.service = service
        self.allow_background = allow_background
        self._start_options = start_options or {}
        self._has_started = False
        self._is_finished = False
        self._cancel_requested = False
        
        super().__init__(parent)
        
        self.setModal(False)  # Немодальный диалог
        self.setMinimumWidth(app_config.ui.get_icon_refresh_dialog_min_width())
        self.setWindowTitle(tr_common("Icon Refresh"))  # Устанавливаем заголовок сразу
        
        self._setup_ui()
        self._connect_signals()
        
        # Теперь вызываем retranslateUi когда все виджеты созданы
        self.retranslateUi()
    
    def _setup_ui(self):
        """Настроить UI компоненты."""
        layout = QVBoxLayout(self)
        
        # Заголовок (с начальным текстом)
        self.title_label = QLabel(QCoreApplication.translate("IconRefreshDialog", "Refreshing icons for imported links"))
        self.title_label.setWordWrap(True)
        layout.addWidget(self.title_label)
        
        # Прогресс-бар
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)
        
        # Статус (с начальным текстом)
        self.status_label = QLabel(QCoreApplication.translate("IconRefreshDialog", "Click Refresh to start icon parsing"))
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        
        # Статистика
        self.stats_label = QLabel("")
        self.stats_label.setWordWrap(True)
        layout.addWidget(self.stats_label)
        
        # Кнопки
        # Блок кнопок с ручным контролем порядка
        self.button_box = QWidget()
        buttons_layout = QHBoxLayout(self.button_box)
        buttons_layout.setContentsMargins(0, 0, 0, 0)
        buttons_layout.setSpacing(app_config.ui.get_icon_refresh_buttons_spacing())
        buttons_layout.addStretch(1)

        # Старт обновления
        self.refresh_button = QPushButton(QCoreApplication.translate("IconRefreshDialog", "Refresh"))
        self.refresh_button.clicked.connect(self._on_refresh_clicked)
        buttons_layout.addWidget(self.refresh_button)
        
        # Кнопка отмены (с начальным текстом)
        self.cancel_button = QPushButton(tr_common("Cancel"))
        self.cancel_button.clicked.connect(self._on_cancel_clicked)
        self.cancel_button.setEnabled(False)
        buttons_layout.addWidget(self.cancel_button)

        # Кнопка "В фон" (если разрешено, с начальным текстом)
        if self.allow_background:
            self.background_button = QPushButton(QCoreApplication.translate("IconRefreshDialog", "Hide to Background"))
            self.background_button.clicked.connect(self._on_background_clicked)
            self.background_button.setEnabled(False)
            buttons_layout.addWidget(self.background_button)

        # Кнопка "Закрыть" (последняя в ряду)
        self.close_button = QPushButton(QCoreApplication.translate("IconRefreshDialog", "Close"))
        self.close_button.clicked.connect(self.accept)
        buttons_layout.addWidget(self.close_button)

        layout.addWidget(self.button_box)
        
        self.setLayout(layout)
    
    def _connect_signals(self):
        """Подключить сигналы сервиса."""
        self.service.progress.connect(self._on_progress)
        self.service.finished.connect(self._on_finished)
        self.service.error.connect(self._on_error)
    
    def _on_progress(self, current: int, total: int, message: str):
        """Обработчик прогресса."""
        if not self._has_started:
            self._has_started = True

        if total > 0:
            percentage = int((current / total) * 100)
            self.progress_bar.setValue(percentage)
        
        self.status_label.setText(message)
        
        # Обновляем статистику (если есть в сообщении)
        if "обновлено:" in message.lower():
            self.stats_label.setText(message)
    
    def _on_finished(self, stats: dict):
        """Обработчик завершения."""
        self._is_finished = True
        self._cancel_requested = False
        self._has_started = False
        
        updated = stats.get("updated", 0)
        skipped = stats.get("skipped", 0)
        failed = stats.get("failed", 0)
        total = stats.get("total", 0)
        
        # Проверяем была ли отмена (обработано меньше чем total)
        processed = updated + skipped + failed
        was_cancelled = processed < total
        
        if was_cancelled:
            # Отменено пользователем
            percentage = int(processed / total * 100) if total > 0 else 0
            self.progress_bar.setValue(percentage)
            self.status_label.setText(QCoreApplication.translate("IconRefreshDialog", "Cancelled by user"))
            self.stats_label.setText(
                QCoreApplication.translate("IconRefreshDialog", "Processed: {0}/{1}\nUpdated: {2}\nSkipped: {3}\nFailed: {4}").format(
                    processed, total, updated, skipped, failed
                )
            )
        else:
            # Завершено успешно
            self.progress_bar.setValue(100)
            self.status_label.setText(QCoreApplication.translate("IconRefreshDialog", "Refresh completed"))
            self.stats_label.setText(
                QCoreApplication.translate("IconRefreshDialog", "Processed: {0}\nUpdated: {1}\nSkipped: {2}\nFailed: {3}").format(
                    total, updated, skipped, failed
                )
            )
        
        # Скрываем кнопки отмены/фона, активируем кнопку закрытия
        self.refresh_button.setEnabled(False)
        self.cancel_button.setVisible(False)
        if self.allow_background:
            self.background_button.setVisible(False)
        self.close_button.setEnabled(True)
        
        logger.info("[icon_refresh_dialog] Refresh completed: %s", stats)
    
    def _on_error(self, error_message: str):
        """Обработчик ошибки."""
        self._is_finished = True
        self._cancel_requested = False
        
        self.progress_bar.setValue(0)
        self.status_label.setText(QCoreApplication.translate("IconRefreshDialog", "Error: {0}").format(error_message))
        self.stats_label.setText("")
        
        # Скрываем кнопки отмены/фона, активируем кнопку закрытия
        self.refresh_button.setEnabled(True)
        self.cancel_button.setVisible(False)
        if self.allow_background:
            self.background_button.setVisible(False)
        self.close_button.setEnabled(True)
        
        logger.error("[icon_refresh_dialog] Refresh error: %s", error_message)
    
    def _request_cancel(self):
        """Отправить запрос на отмену без блокировки UI."""
        if self._is_finished or self._cancel_requested:
            return
        self._cancel_requested = True
        self.status_label.setText(QCoreApplication.translate("IconRefreshDialog", "Stopping..."))
        self.cancel_button.setEnabled(False)
        if self.allow_background and hasattr(self, "background_button"):
            self.background_button.setEnabled(False)
        self.refresh_button.setEnabled(False)
        try:
            self.service.cancel_refresh()
            logger.info("[icon_refresh_dialog] Cancellation requested")
        except Exception as e:
            logger.warning("[icon_refresh_dialog] Failed to request cancel: %s", e)
    
    def _on_cancel_clicked(self):
        """Обработчик нажатия кнопки отмены."""
        if not self._is_finished:
            self._request_cancel()
    
    def _on_background_clicked(self):
        """Обработчик нажатия кнопки "В фон"."""
        if self._cancel_requested:
            logger.info("[icon_refresh_dialog] Background hide ignored during cancel")
            return
        self.hide()
        logger.info("[icon_refresh_dialog] Hidden to background")
    
    def closeEvent(self, event):
        """Обработчик закрытия диалога."""
        if not self._is_finished and not self._cancel_requested and self.service.is_running():
            self._request_cancel()
            logger.info("[icon_refresh_dialog] Close requested, cancelling refresh")
        super().closeEvent(event)

    def showEvent(self, event):
        """При повторном открытии возвращаем возможность запуска."""
        super().showEvent(event)
        if self.service.is_running():
            return
        if self._is_finished or self._cancel_requested:
            self._reset_idle_ui()
    
    def retranslateUi(self):
        """Update UI translations."""
        # Защита от вызова до полной инициализации
        if not hasattr(self, 'title_label'):
            return
        
        self.setWindowTitle(tr_common("Icon Refresh"))
        self.title_label.setText(QCoreApplication.translate("IconRefreshDialog", "Refreshing icons for imported links"))
        
        if not self._is_finished:
            if self._has_started:
                self.status_label.setText(QCoreApplication.translate("IconRefreshDialog", "Initializing..."))
            else:
                self.status_label.setText(QCoreApplication.translate("IconRefreshDialog", "Click Refresh to start icon parsing"))
        
        self.refresh_button.setText(QCoreApplication.translate("IconRefreshDialog", "Refresh"))
        self.cancel_button.setText(tr_common("Cancel"))
        
        if self.allow_background and hasattr(self, "background_button"):
            self.background_button.setText(QCoreApplication.translate("IconRefreshDialog", "Hide to Background"))
        
        self.close_button.setText(QCoreApplication.translate("IconRefreshDialog", "Close"))

    def _on_refresh_clicked(self):
        """Запустить парсинг иконок по запросу пользователя."""
        if self.service.is_running() or self._cancel_requested:
            return
        self.refresh_button.setEnabled(False)
        self.status_label.setText(QCoreApplication.translate("IconRefreshDialog", "Starting refresh..."))
        try:
            started = self.service.start_refresh(**self._start_options)
        except Exception as exc:
            logger.error("[icon_refresh_dialog] Failed to start refresh: %s", exc)
            started = False

        if started:
            self._has_started = True
            self.cancel_button.setVisible(True)
            self.cancel_button.setEnabled(True)
            if self.allow_background and hasattr(self, "background_button"):
                self.background_button.setVisible(True)
                self.background_button.setEnabled(True)
            self.refresh_started.emit()
            logger.info("[icon_refresh_dialog] Refresh started on demand")
        else:
            self.status_label.setText(QCoreApplication.translate("IconRefreshDialog", "Failed to start refresh"))
            self.refresh_button.setEnabled(True)
            logger.warning("[icon_refresh_dialog] Refresh start rejected")

    def _reset_idle_ui(self):
        """Вернуть диалог в исходное состояние для повторного запуска."""
        self._has_started = False
        self._is_finished = False
        self._cancel_requested = False
        self.progress_bar.setValue(0)
        self.status_label.setText(QCoreApplication.translate("IconRefreshDialog", "Click Refresh to start icon parsing"))
        self.stats_label.setText("")
        self.refresh_button.setEnabled(True)
        self.cancel_button.setVisible(True)
        self.cancel_button.setEnabled(False)
        if self.allow_background and hasattr(self, "background_button"):
            self.background_button.setVisible(True)
            self.background_button.setEnabled(False)


__all__ = ["IconRefreshDialog"]
