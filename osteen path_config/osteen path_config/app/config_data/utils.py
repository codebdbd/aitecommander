# app/config_data/utils.py
from typing import Any, Dict


def get_by_path(config: Dict[str, Any], key_path: str, default: Any = None) -> Any:
    """Возвращает значение из словаря по пути через точки.
    Пример: key_path="ui.window.width"
    Возвращает default при отсутствии ключа или неверной структуре.
    """
    keys = key_path.split('.') if key_path else []
    value: Any = config
    try:
        for key in keys:
            value = value[key]
        return value
    except (KeyError, TypeError):
        return default
