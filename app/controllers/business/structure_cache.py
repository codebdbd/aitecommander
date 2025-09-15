# app/controllers/business/structure_cache.py

from __future__ import annotations

import logging
from typing import Callable, Optional


class StructureCache:
    """Фасад для операций с кэшем структуры.

    Не хранит ссылок на БД/сервисы, работает поверх переданного cache_manager.
    Позволяет изолировать логику инвалидирования и упростить тестирование.
    """

    def __init__(
        self,
        *,
        cache_manager: object,
        get_current_sphere_id: Callable[[], Optional[int]],
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self._cache = cache_manager
        self._get_current_sphere_id = get_current_sphere_id
        self._logger = logger or logging.getLogger(__name__)

    # Публичные методы для использования из Business-слоя
    def invalidate_structure(self) -> None:
        """Инвалидирует кэш структуры и разделов для текущей сферы."""
        sphere_id = self._get_current_sphere_id()
        if not sphere_id:
            return

        keys = (
            f"structure_{sphere_id}",
            f"sections_{sphere_id}",
            f"first_category_id:{sphere_id}",
        )

        for key in keys:
            try:
                self._cache.invalidate(key)
            except (AttributeError, RuntimeError) as e:
                # Ожидаемые ошибки работы с кэшем глушим по-ключу, чтобы не ломать бизнес-поток,
                # но оставляем диагностическое сообщение.
                self._logger.debug(
                    "StructureCache.invalidate_structure failed (expected): %s (key=%s)",
                    e,
                    key,
                    exc_info=True,
                )
                continue
            except Exception as e:  # noqa: BLE001 - здесь намеренно повторно пробрасываем
                # Неожиданные ошибки логируем и пробрасываем выше для корректной диагностики.
                self._logger.exception(
                    "StructureCache.invalidate_structure unexpected error for key '%s': %s",
                    key,
                    e,
                )
                raise

    def invalidate_categories(self, section_id: Optional[int]) -> None:
        """Инвалидирует кэш категорий раздела и связанную структуру."""
        # 1) Инвалидируем кэш категорий раздела (если задан section_id)
        if section_id:
            key = f"categories_{section_id}"
            try:
                self._cache.invalidate(key)
            except (AttributeError, RuntimeError) as e:
                # Ожидаемые ошибки среды кэша — логируем и продолжаем
                self._logger.debug(
                    "StructureCache.invalidate_categories failed (expected): %s (key=%s)",
                    e,
                    key,
                    exc_info=True,
                )
            except Exception as e:  # noqa: BLE001 — намеренно пробрасываем неожиданные
                self._logger.exception(
                    "StructureCache.invalidate_categories unexpected error for key '%s': %s",
                    key,
                    e,
                )
                raise

        # 2) Структура зависит от категорий — инвалидируем всегда
        try:
            self.invalidate_structure()
        except Exception:
            # invalidate_structure уже дифференцирует ожидаемые/неожиданные по ключам и
            # может пробрасывать только неожиданные — здесь лишь фиксируем контекст
            self._logger.exception(
                "StructureCache.invalidate_categories: unexpected error while invalidating structure"
            )
            raise

    # Утилиты прямого доступа (на случай тестов/расширений)
    def get(self, key: str):  # type: ignore[no-untyped-def]
        return self._cache.get(key)

    def set(self, key: str, value):  # type: ignore[no-untyped-def]
        return self._cache.set(key, value)

    def clear_all(self) -> None:
        try:
            self._cache.invalidate()
        except (AttributeError, RuntimeError) as e:
            self._logger.debug(
                "StructureCache.clear_all failed (expected): %s", e, exc_info=True
            )
        except Exception as e:  # noqa: BLE001
            self._logger.exception(
                "StructureCache.clear_all unexpected error: %s", e
            )
            raise
