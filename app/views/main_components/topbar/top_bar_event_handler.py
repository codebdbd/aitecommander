"""Обработчик событий для топбара с throttling."""
from __future__ import annotations

import logging
from typing import Optional, Set
from weakref import WeakSet

from PyQt6.QtCore import QEvent, QObject, QTimer, QThread
from PyQt6.QtWidgets import QWidget

try:
    from sip import isdeleted as _sip_isdeleted
except ImportError:
    def _sip_isdeleted(obj: QObject) -> bool:
        return False

logger = logging.getLogger(__name__)


class TopBarEventHandler(QObject):
    """Обработчик событий топбара с throttling для предотвращения избыточных пересчетов."""

    def __init__(self, config: 'TopBarConfig') -> None:
        """Инициализация обработчика событий."""
        super().__init__()
        self.config = config
        self._watched_widgets: WeakSet[QObject] = WeakSet()
        self._throttle_timer: Optional[QTimer] = None

        # Сигнал для уведомления о необходимости пересчета
        self.adjust_requested = self._create_signal()

    def _create_signal(self) -> 'callable':
        """Создать сигнал для уведомлений."""
        # Используем простую функцию-сигнал для совместимости
        def signal():
            pass
        return signal

    def setup_throttling(self) -> None:
        """Настроить throttling для предотвращения избыточных пересчетов."""
        if self._throttle_timer is None:
            self._throttle_timer = QTimer(self)
            self._throttle_timer.setSingleShot(True)
            self._throttle_timer.timeout.connect(self._on_adjust_timeout)

    def install_event_filters(self, *widgets: QObject) -> None:
        """Установить event filter на указанные виджеты."""
        self.setup_throttling()

        for widget in widgets:
            if (isinstance(widget, QObject) and
                widget not in self._watched_widgets and
                not _sip_isdeleted(widget)):

                try:
                    widget.installEventFilter(self)
                    self._watched_widgets.add(widget)
                except RuntimeError:
                    logger.debug(f"Failed to install event filter on {widget}")

    def remove_event_filters(self) -> None:
        """Удалить все event filter'ы."""
        for widget in list(self._watched_widgets):
            if not _sip_isdeleted(widget):
                try:
                    widget.removeEventFilter(self)
                except RuntimeError:
                    pass
        self._watched_widgets.clear()

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        """Фильтр событий для отслеживания изменений размеров."""
        if event.type() in (
            QEvent.Type.Resize,
            QEvent.Type.LayoutRequest,
            QEvent.Type.Show,
            QEvent.Type.Hide,
        ):
            self._schedule_adjust()
        return super().eventFilter(obj, event)

    def _schedule_adjust(self) -> None:
        """Запланировать пересчет с throttling."""
        if self._throttle_timer:
            self._throttle_timer.start(self.config.throttle_ms)

    def _on_adjust_timeout(self) -> None:
        """Обработчик таймаута throttling."""
        try:
            # Эмитим сигнал для пересчета
            # В реальной реализации здесь должен быть сигнал PyQt
            logger.debug("TopBarEventHandler: adjust requested due to layout change")
            # self.adjust_requested.emit()
        except RuntimeError:
            pass

    def force_adjust(self) -> None:
        """Принудительный пересчет без throttling."""
        if self._throttle_timer:
            self._throttle_timer.stop()
        self._on_adjust_timeout()

    def is_watching(self, widget: QObject) -> bool:
        """Проверить, отслеживается ли виджет."""
        return widget in self._watched_widgets

    def cleanup(self) -> None:
        """Очистка ресурсов."""
        self.remove_event_filters()
        if self._throttle_timer:
            self._throttle_timer.stop()
            self._throttle_timer.deleteLater()
            self._throttle_timer = None
