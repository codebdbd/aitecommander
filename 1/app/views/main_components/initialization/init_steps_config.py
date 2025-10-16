# app/views/main_components/init_steps_config.py
from __future__ import annotations

from typing import Optional

# Step config structure: (label, method_name, optional_post_hook_name)
StepConfig = tuple[str, str, Optional[str]]

# Steps executed before the database is ready
BEFORE_DB_STEP_CONFIG: list[StepConfig] = [
    ("Loading primary content...", "_init_main_content", None),
    ("Initializing bottom panel...", "_init_bottom_panel", None),
    ("Creating status bar...", "_init_status_bar", "_post_status_bar_init"),
    ("Applying font preferences...", "_apply_user_font_size", None),
]

# Steps executed after the database is ready
AFTER_DB_STEP_CONFIG: list[StepConfig] = [
    ("Configuring controllers...", "_init_controllers", "_post_controllers_init"),
    ("Finalizing initialization...", "_initialize_spheres", None),
]
