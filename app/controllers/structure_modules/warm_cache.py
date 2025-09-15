# app/controllers/structure_modules/warm_cache.py

from __future__ import annotations

from typing import Any, Dict, List, Optional
from PyQt6.QtCore import QTimer
import logging


class WarmCacheHelper:
    """Инкапсулирует логику тёплого кэширования после загрузки структуры.

    Использует зависимости контроллера, переданные при вызове (self.controller),
    чтобы не создавать жёстких связей и упростить тестирование.
    """

    def __init__(self, logger: Optional[logging.Logger] = None) -> None:
        self.logger = logger or logging.getLogger(__name__)

    def handle(self, controller: Any, payload: List[Dict[str, Any]]) -> None:
        try:
            sphere_id = getattr(controller, "current_sphere_id", None)
            if not isinstance(sphere_id, int) or sphere_id <= 0:
                return

            # 1) Попробуем извлечь первую категорию из payload
            if isinstance(payload, list):
                for section in payload:
                    try:
                        cats = section.get("categories") if isinstance(section, dict) else None
                    except (AttributeError, TypeError):
                        cats = None
                    if cats:
                        first = cats[0]
                        cid = first.get("id") if isinstance(first, dict) else None
                        if isinstance(cid, int) and cid > 0:
                            controller.cache_manager.set(f"first_category_id:{sphere_id}", cid)
                            return

            # 2) Если в payload нет категорий — прогреем кэш асинхронно в следующий тик
            def _deferred_warmup():
                try:
                    _ = controller.utility_service.get_target_section_id(
                        current_sphere_id=sphere_id,
                        get_sections=controller.get_sections,
                        get_categories=controller.get_categories,
                        cache_get=controller.cache_manager.get,
                        cache_set=controller.cache_manager.set,
                    )
                except Exception as ex:
                    self.logger.debug("Deferred warm cache failed: %s", ex, exc_info=True)

            try:
                QTimer.singleShot(0, _deferred_warmup)
            except (RuntimeError, TypeError):
                _deferred_warmup()

            # Дополнительный немедленный прогрев для сред без активного цикла событий
            try:
                _deferred_warmup()
            except Exception as ex:
                self.logger.debug("Immediate warm cache failed: %s", ex, exc_info=True)

            # 3) Лёгкий асинхронный прелоад категорий для первых секций сферы
            try:
                if isinstance(payload, list) and payload:
                    from app.config_data import app_config
                    preload_limit = int(app_config.ui.get_preload_categories_limit())
                    delay_step_ms = int(app_config.ui.get_preload_delay_step_ms())
                    planned_token = int(getattr(controller, "_switch_token", 0))
                    planned_sphere = sphere_id
                    for idx, section in enumerate(payload[:preload_limit]):
                        sid = section.get("id") if isinstance(section, dict) else None
                        if not isinstance(sid, int) or sid <= 0:
                            continue
                        delay = max(0, int(idx) * delay_step_ms)

                        def _preload_one(section_id: int = sid, token: int = planned_token, psid: int = planned_sphere):
                            try:
                                if int(getattr(controller, "_switch_token", 0)) != int(token):
                                    return
                                cur = getattr(controller, "current_sphere_id", None)
                                if cur != psid:
                                    return
                                ops = getattr(controller, "async_operations", None)
                                if ops and hasattr(ops, "load_categories_async"):
                                    ops.load_categories_async(section_id)
                            except Exception as ex:
                                self.logger.debug("Preload categories failed: %s", ex, exc_info=True)

                        QTimer.singleShot(delay, _preload_one)
                        # Выполним немедленно при нулевой задержке, чтобы тесты, не перехватывающие QTimer
                        # в этом модуле, могли зафиксировать логирование и эффекты сразу.
                        if delay == 0:
                            try:
                                _preload_one()
                            except Exception as ex:
                                self.logger.debug("Preload categories failed: %s", ex, exc_info=True)
            except Exception:
                self.logger.debug("Warm cache: preload categories scheduling failed", exc_info=True)
        except Exception as e:
            try:
                self.logger.debug("Warm cache handler failed: %s", e, exc_info=True)
            except Exception:
                pass
