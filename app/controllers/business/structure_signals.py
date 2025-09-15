# app/controllers/business/structure_signals.py

from __future__ import annotations

import logging
from typing import Any, Optional

from PyQt6.QtCore import QObject, QTimer


class StructureSignalsManager(QObject):
    """Компонент для подключения обработчиков бизнес-сигналов и управления
    дебаунсом перезагрузки структуры.

    - Подключает обработчики к сигналам владельца (StructureBusinessLogic)
    - Хранит собственный QTimer для коалесцированной перезагрузки
    - Вызовы в БД и инвалидирование выполняет через owner (композиция)
    """

    def __init__(self, owner: Any, logger: Optional[logging.Logger] = None) -> None:
        super().__init__(parent=owner if isinstance(owner, QObject) else None)
        self.owner = owner
        self.logger = logger or logging.getLogger(__name__)

        # Таймер перезагрузки структуры
        self._structure_reload_timer: QTimer = QTimer(self)
        self._structure_reload_timer.setSingleShot(True)
        self._structure_reload_timer.timeout.connect(self._perform_structure_reload)

    # ------- Публичный API -------
    def connect(self) -> None:
        """Подключает обработчики к сигналам владельца."""
        # Подключаем обязательные сигналы по одному, чтобы не прерывать остальные
        for attr_name, handler in (
            ("item_added", self._on_item_added),
            ("item_updated", self._on_item_updated),
            ("item_deleted", self._on_item_deleted),
            ("items_batch_deleted", self._on_items_batch_deleted),
        ):
            try:
                getattr(self.owner, attr_name).connect(handler)
            except (AttributeError, RuntimeError) as e:
                # Ожидаемые ошибки наличия/доступности сигнала — логируем и продолжаем
                self.logger.debug(
                    "connect: failed (expected) to attach '%s': %s", attr_name, e, exc_info=True
                )
                continue
            except Exception as e:  # noqa: BLE001 — намеренно пробрасываем неожиданное
                self.logger.exception(
                    "connect: unexpected error attaching '%s': %s", attr_name, e
                )
                raise

        # Опциональный сигнал для прогрева кэша
        try:
            self.owner.structure_loaded.connect(self._on_structure_loaded_warm_cache)
        except (AttributeError, RuntimeError) as e:
            self.logger.debug(
                "Не удалось подключить прогрев кэша к structure_loaded: %s", e, exc_info=True
            )
        except Exception as e:  # noqa: BLE001
            self.logger.exception(
                "connect: unexpected error attaching 'structure_loaded': %s", e
            )
            raise

        self.logger.info("[Signals] Handlers connected for business id=%s", id(self.owner))

    def schedule_structure_reload(self, delay_ms: int = 200) -> None:
        try:
            if not isinstance(delay_ms, int) or delay_ms < 0:
                delay_ms = 200
            if self._structure_reload_timer.isActive():
                self._structure_reload_timer.stop()
            self._structure_reload_timer.start(delay_ms)
        except (RuntimeError, ValueError, TypeError) as e:
            # Ожидаемые ошибки среды/данных — логируем и выходим
            self.logger.warning(
                "schedule_structure_reload: failed to schedule: %s", e, exc_info=True
            )
        except Exception:
            # Неожиданная программная ошибка — не скрываем
            self.logger.exception("schedule_structure_reload: unexpected error")
            raise

    # ------- Внутреннее -------
    def _perform_structure_reload(self) -> None:
        try:
            # Инвалидируем кэш структуры
            self.owner._invalidate_structure_cache()
            sphere_id = getattr(self.owner, "current_sphere_id", None)
            if isinstance(sphere_id, int) and sphere_id > 0:
                self.owner.async_operations.load_structure_async(sphere_id)
        except (RuntimeError, ValueError, TypeError) as e:
            self.logger.error("_perform_structure_reload: %s", e, exc_info=True)
        except Exception:
            self.logger.exception("_perform_structure_reload: unexpected error")
            raise

    # Обработчики сигналов (повторяют логику из Business, но изолированы)
    def _on_item_added(self, item_type: str, parent_id: int, item_data: dict) -> None:
        try:
            self.logger.info("[BL] item_added: type=%s, parent_id=%s", item_type, parent_id)
            if item_type == "link":
                category_id = item_data.get("category_id") if isinstance(item_data, dict) else None
                self.owner._invalidate_categories_cache(category_id)
                self.schedule_structure_reload(200)
                return
            if item_type == "category":
                section_id = parent_id or (item_data.get("section_id") if isinstance(item_data, dict) else None)
                self.owner._invalidate_categories_cache(section_id)
                if isinstance(section_id, int) and section_id > 0:
                    self.owner.async_operations.load_categories_async(section_id)
            self.owner._invalidate_structure_cache()
            self.schedule_structure_reload(0)
        except (ValueError, TypeError, KeyError, RuntimeError) as e:
            self.logger.error("Ошибка в _on_item_added (signals mgr): %s", e, exc_info=True)
        except Exception:
            self.logger.exception("_on_item_added: unexpected error")
            raise

    def _on_item_updated(self, item_type: str, item_id: int, item_data: dict) -> None:
        try:
            self.logger.info("[BL] item_updated: type=%s, id=%s", item_type, item_id)
            if item_type == "link":
                category_id = item_data.get("category_id") if isinstance(item_data, dict) else None
                self.owner._invalidate_categories_cache(category_id)
                return
            if item_type == "category":
                section_id = item_data.get("section_id") if isinstance(item_data, dict) else None
                self.owner._invalidate_categories_cache(section_id)
                if getattr(self.owner, "_batch_mode", False):
                    try:
                        if isinstance(section_id, int) and section_id > 0:
                            self.owner._batch_touched_sections.add(int(section_id))
                    except Exception as ex:
                        self.logger.debug("batch: failed to add touched section id=%s: %s", section_id, ex, exc_info=True)
                    return
                if isinstance(section_id, int) and section_id > 0:
                    self.owner.async_operations.load_categories_async(section_id)
            self.owner._invalidate_structure_cache()
            self.schedule_structure_reload(0)
        except (ValueError, TypeError, KeyError, RuntimeError) as e:
            self.logger.error("Ошибка в _on_item_updated (signals mgr): %s", e, exc_info=True)
        except Exception:
            self.logger.exception("_on_item_updated: unexpected error")
            raise

    def _on_item_deleted(self, item_type: str, item_id: int) -> None:
        try:
            self.logger.info("[BL] item_deleted: type=%s, id=%s", item_type, item_id)
            if item_type == "link":
                self.schedule_structure_reload(200)
                return
            self.owner._invalidate_structure_cache()
            self.schedule_structure_reload(0)
        except (ValueError, TypeError, KeyError, RuntimeError) as e:
            self.logger.error("Ошибка в _on_item_deleted (signals mgr): %s", e, exc_info=True)
        except Exception:
            self.logger.exception("_on_item_deleted: unexpected error")
            raise

    def _on_items_batch_deleted(self, item_type: str, ids: list) -> None:
        try:
            total = len(ids) if isinstance(ids, (list, tuple)) else 0
            self.logger.info("[BL] items_batch_deleted: type=%s, count=%s", item_type, total)
            if item_type == "link":
                self.schedule_structure_reload(200)
                return
            self.owner._invalidate_structure_cache()
            self.schedule_structure_reload(0)
        except (ValueError, TypeError, KeyError, RuntimeError) as e:
            self.logger.error("Ошибка в _on_items_batch_deleted (signals mgr): %s", e, exc_info=True)
        except Exception:
            self.logger.exception("_on_items_batch_deleted: unexpected error")
            raise

    def _on_structure_loaded_warm_cache(self, payload: list) -> None:
        """Прокси к методу владельца для прогрева кэша после загрузки структуры."""
        try:
            # вызывать приватный метод владельца для сохранения логики/тестов
            self.owner._on_structure_loaded_warm_cache(payload)
        except (RuntimeError, ValueError, TypeError, KeyError) as e:
            self.logger.debug("Warm cache proxy failed: %s", e, exc_info=True)
        except Exception:
            self.logger.exception("Warm cache proxy: unexpected error")
            raise
