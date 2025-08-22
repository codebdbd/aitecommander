import logging


def validate_section_data(data: dict) -> bool:
    """Проверяет, что у раздела есть данные и не пустое имя."""
    if not data:
        logging.warning("Не удалось получить данные раздела")
        return False
    if not data.get('name'):
        logging.warning("Название раздела не может быть пустым")
        return False
    return True


# Универсальные проверки для имён сущностей структуры
def is_non_empty_name(name: str) -> bool:
    """Имя не пустое после trim."""
    return isinstance(name, str) and name.strip() != ""


def is_name_length_ok(name: str, max_len: int = 255) -> bool:
    """Имя не превышает ограничение длины."""
    try:
        return len(name) <= max_len
    except Exception:
        return False


def has_no_forbidden_chars(name: str, forbidden: str = '\\/:*?"<>|') -> bool:
    """Имя не содержит запрещённых символов для Windows-путей и файлов."""
    if not isinstance(name, str):
        return False
    return not any(ch in name for ch in forbidden)


def validate_category_data(data: dict) -> bool:
    """Проверяет, что у категории есть валидное имя (минимальные требования)."""
    if not isinstance(data, dict):
        return False
    name = data.get('name', '')
    return is_non_empty_name(name) and is_name_length_ok(name) and has_no_forbidden_chars(name)
