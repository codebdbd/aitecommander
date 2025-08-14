import logging
from urllib.parse import urlparse


def validate_name_and_url(name: str, url: str) -> bool:
    """Проверка: имя и путь/URL не пустые."""
    return bool(name) and bool(url)


def validate_web_url(url: str) -> bool:
    parsed_url = urlparse(url)
    return bool(parsed_url.netloc) and ('.' in parsed_url.netloc)


def validate_favorite_limit(db, want_fav: bool, is_edit: bool, was_fav: bool) -> bool:
    if want_fav and (not is_edit or not was_fav):
        fav_count = db.links.count_favorites()
        if fav_count >= 20:
            return False
    return True


def validate_link_duplicate(url: str, link_type: str, args: str, existing_links: list, 
                          current_link_id: int = None) -> bool:
    """Проверяет, нет ли дубликата ссылки в категории."""
    logger = logging.getLogger(__name__)
    for link in existing_links:
        # Пропускаем текущую редактируемую ссылку
        if current_link_id and link['id'] == current_link_id:
            continue
            
        # Проверяем совпадение URL, типа и аргументов
        link_args = link.get('args') if hasattr(link, 'get') else link['args'] if 'args' in link else ''
        if (link['url'] == url and 
            link['type'] == link_type and 
            (link_args == args)):
            try:
                logger.info(
                    f"validate_link_duplicate: найден дубликат id={link.get('id')} name='{link.get('name', '')}' "
                    f"url='{url}' type='{link_type}' args='{args}' (current_link_id={current_link_id})"
                )
            except Exception:
                pass
            return True  # Найден дубликат
    
    return False  # Дубликат не найден


def validate_chrome_profile_name(profile_name: str) -> str:
    """Очищает и валидирует имя Chrome профиля."""
    if not profile_name:
        return "Chrome"
    
    # Убираем email домен если есть
    if "@" in profile_name:
        profile_name = profile_name.split("@")[0]
    
    return profile_name if profile_name != "Chrome" else "Chrome"


def extract_base_name_from_profile_name(name: str) -> str:
    """Извлекает базовое имя из имени с профилем."""
    import re
    match = re.match(r"^(.*?)\s*\(.*\)$", name)
    if match:
        return match.group(1).strip()
    return name


def validate_link_form_data(name: str, url: str, link_type: str) -> bool:
    """Комплексная валидация данных формы ссылки."""
    # 1. Проверяем обязательные поля
    if not validate_name_and_url(name, url):
        return False
    
    # 2. Проверяем тип ссылки
    from .basic_validators import validate_link_type, validate_path
    if not validate_link_type(link_type):
        return False
    
    # 3. Проверяем путь для файловых ссылок
    if link_type in ("file", "folder"):
        if not validate_path(url):
            return False
    
    # 4. Проверяем web URL
    if link_type == "web" and not validate_web_url(url):
        return False
    
    return True
