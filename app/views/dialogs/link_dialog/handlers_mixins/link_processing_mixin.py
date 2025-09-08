"""
Миксин для асинхронной обработки пути/ссылки в LinkDialogHandlers.
"""
import logging
from pathlib import Path
from typing import Any, Dict

from PyQt6.QtGui import QIcon

from app.config_data import app_config
from app.models.link_type import LinkType
from app.utils.db.api import run_db
from app.utils.links.link_parser import parse_local_link
from app.utils.links.parser.fetcher import fetch_web_link_info
from app.utils.ui.icon.icon_resolver import resolve_icon_for_link
from app.utils.ui.icon.ui_helpers import set_icon_to_button

logger = logging.getLogger(__name__)


class LinkProcessingMixin:
    def _on_path_changed(self, text: str) -> None:
        """Обработчик изменения пути."""
        self.dialog._processing_timer.stop()
        # Используем настраиваемую задержку дебаунса из диалога (с фолбэком на 300 мс)
        try:
            debounce_ms = getattr(self.dialog, "PATH_DEBOUNCE_MS", 300)
        except (AttributeError, TypeError):
            debounce_ms = 300
        self.dialog._processing_timer.start(int(debounce_ms) if debounce_ms else 300)

    def trigger_link_processing(self, path: str) -> None:
        """Запуск обработки информации о ссылке."""
        if not path or self._is_processing:
            return

        if path == self._last_processed_path:
            return

        self._last_processed_path = path
        self._is_processing = True

        # Защита от race condition
        self._worker_task_id += 1
        _task_id = self._worker_task_id

        # Отмена активной задачи
        if self._active_worker:
            try:
                self._active_worker.cancel()
            except (AttributeError, RuntimeError) as e:
                # Логируем ошибку отмены воркера, но продолжаем выполнение
                logger.debug("Ошибка при отмене воркера: %s", e)

        lt = LinkType.from_value(self.dialog.link_type)
        args_val = self.dialog._get_args_le().text().strip()

        def _emit_if_current(payload: Dict[str, Any]) -> None:
            # Эмитим результат только если задача всё ещё актуальна
            if _task_id == self._worker_task_id:
                self.signals.link_info_finished.emit(payload)

        def _emit_error_if_current(message: str) -> None:
            if _task_id == self._worker_task_id:
                self.signals.simple_error.emit(message)

        def _do_work() -> Dict[str, Any]:
            if lt == LinkType.WEB:
                # Иконку подберём отложенно, чтобы не блокировать UI
                info = fetch_web_link_info(
                    path,
                    app_config,
                    force_refresh=False,
                    defer_icon=True,
                    on_icon_ready=lambda icon_path: _emit_if_current({"title": "", "icon": icon_path}),
                )
                return {"title": info.get("title"), "icon": info.get("icon")}
            # Локальные пути
            info = parse_local_link(lt.value, path, app_config, args=args_val)
            return info or {"name": "", "icon": ""}

        handle = run_db(
            _do_work,
            description=f"link_info:{lt.value}",
            on_finished=lambda info: _emit_if_current(info),
            on_error=lambda e: _emit_error_if_current(str(e)),
        )

        # Сохраняем handle активного воркера
        self._active_worker = handle

    def _trigger_link_processing(self) -> None:
        """Внутренний метод для запуска обработки ссылки из таймера."""
        url = self.dialog._get_url_le().text().strip()
        self.trigger_link_processing(url)

    def _on_link_info_fetched(self, info: Dict) -> None:
        """Обработка полученной информации о ссылке."""
        self._is_processing = False
        self._active_worker = None

        title = info.get("title") or info.get("name")
        if title and not self.dialog._get_name_le().text().strip():
            self.dialog.ui.set_widget_value("name_le", title)

        icon_path_str = info.get("icon")
        if icon_path_str and Path(icon_path_str).exists():
            self.dialog.icon_name = Path(icon_path_str).name
            set_icon_to_button(self.dialog._get_icon_btn(), icon_path_str)
        else:
            # Фолбек через централизованный резолвер
            try:
                resolved_icon_path = resolve_icon_for_link(
                    {
                        "type": self.dialog.link_type,
                        "icon_path": self.dialog.icon_name or "",
                    }
                )
            except (AttributeError, KeyError, ValueError) as e:
                logger.warning("Ошибка резолвинга иконки для ссылки: %s", e)
                resolved_icon_path = ""
            if resolved_icon_path and Path(resolved_icon_path).exists():
                set_icon_to_button(
                    self.dialog._get_icon_btn(), resolved_icon_path
                )
            else:
                self.dialog._get_icon_btn().setIcon(QIcon())

        if LinkType.from_value(self.dialog.link_type) in (LinkType.PROGRAM, LinkType.SCRIPT, LinkType.CHROMEAPP):
            args = info.get("args", "")
            if not self.dialog._get_args_le().text().strip():
                self.dialog.ui.set_widget_value("args_le", args)

        self._is_processing = False

    def _on_link_info_error(self, error_message: str) -> None:
        """Обработка ошибки получения информации.

        Теперь метод не только сбрасывает внутреннее состояние, но и:
        - логирует ошибку через logger.error с деталями контекста (тип ссылки, последний путь);
        - уведомляет пользователя через диалоговое окно `show_error(...)` с подробностями.

        :param error_message: Текст ошибки, полученный из фоновой задачи.
        """
        # Сброс внутреннего состояния обработки
        self._is_processing = False
        self._active_worker = None

        # Логирование для диагностики
        try:
            link_type = getattr(self.dialog, "link_type", None) or "<unknown>"
            last_path = self._last_processed_path or (
                getattr(self.dialog, "link", {}) or {}
            ).get("url", "")
        except (AttributeError, TypeError, RuntimeError):
            link_type = "<unknown>"
            last_path = ""

        logger.error(
            "Ошибка получения информации о ссылке (type=%s, path=%s): %s",
            link_type,
            last_path,
            error_message,
        )

        # Дружелюбное уведомление пользователя с подробностями для диагностики
        try:
            self.dialog.show_error(
                "Не удалось получить информацию о ссылке.",
                "Ошибка обработки ссылки",
                informative_text=(
                    "Проверьте корректность пути/URL и доступность ресурса."
                ),
                details=str(error_message),
                silent=True,
            )
        except (AttributeError, RuntimeError) as e:
            # Даже если уведомить пользователя не получилось, зафиксируем это в логах
            logger.warning(
                "Не удалось показать окно ошибки пользователю: %s", e
            )
