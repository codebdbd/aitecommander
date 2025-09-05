# app/views/main_components/init_steps_config.py
from __future__ import annotations

from typing import List, Tuple, Optional

# Тип конфигурации шага: (label, method_name, optional_post_hook_name)
StepConfig = Tuple[str, str, Optional[str]]

# Этапы до готовности БД
BEFORE_DB_STEP_CONFIG: List[StepConfig] = [
    ("Загрузка основного содержимого...", "_init_main_content", None),
    ("Инициализация нижней панели...", "_init_bottom_panel", None),
    ("Создание статус-бара...", "_init_status_bar", "_post_status_bar_init"),
    ("Применение настроек шрифта...", "_apply_user_font_size", None),
]

# Этапы после готовности БД
AFTER_DB_STEP_CONFIG: List[StepConfig] = [
    ("Настройка контроллеров...", "_init_controllers", "_post_controllers_init"),
    ("Завершение инициализации...", "_initialize_spheres", None),
]
