# app/views/main_components/init_steps_config.py
from __future__ import annotations

from typing import List, Optional
from dataclasses import dataclass

@dataclass(frozen=True)
class StepConfig:
    """Конфигурация шага инициализации.

    label: отображаемая подпись шага (для статуса/метрик)
    method_name: имя метода WindowInitializer, выполняющего шаг
    post_hook_name: опциональное имя метода, вызываемого сразу после шага
    """
    label: str
    method_name: str
    post_hook_name: Optional[str] = None

# Этапы до готовности БД
BEFORE_DB_STEP_CONFIG: List[StepConfig] = [
    StepConfig("Загрузка основного содержимого...", "_init_main_content"),
    StepConfig("Инициализация нижней панели...", "_init_bottom_panel"),
    StepConfig("Создание статус-бара...", "_init_status_bar", "_post_status_bar_init"),
    StepConfig("Применение настроек шрифта...", "_apply_user_font_size"),
]

# Этапы после готовности БД
AFTER_DB_STEP_CONFIG: List[StepConfig] = [
    StepConfig("Настройка контроллеров...", "_init_controllers", "_post_controllers_init"),
    StepConfig("Завершение инициализации...", "_initialize_spheres"),
]
