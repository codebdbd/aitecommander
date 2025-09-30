"""Утилиты для валидации пользовательского ввода в диалогах.

Предоставляет функции для проверки корректности данных перед их обработкой.
"""

import re
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import urlparse


def validate_url(url: str) -> Tuple[bool, Optional[str]]:
    """Проверяет корректность URL.
    
    Args:
        url: URL для проверки
        
    Returns:
        Tuple[bool, Optional[str]]: (валиден, сообщение об ошибке)
        
    Example:
        >>> valid, error = validate_url("https://example.com")
        >>> if not valid:
        ...     print(error)
    """
    if not url or not url.strip():
        return False, "URL не может быть пустым"
    
    url = url.strip()
    
    try:
        result = urlparse(url)
        
        # Проверяем наличие схемы и netloc
        if not all([result.scheme, result.netloc]):
            return False, "URL должен содержать протокол (http://, https://) и домен"
        
        # Проверяем поддерживаемые схемы
        if result.scheme not in ('http', 'https', 'ftp', 'file'):
            return False, f"Неподдерживаемый протокол: {result.scheme}"
        
        return True, None
        
    except ValueError as e:
        return False, f"Некорректный URL: {str(e)}"


def validate_file_path(path: str, must_exist: bool = False) -> Tuple[bool, Optional[str]]:
    """Проверяет корректность пути к файлу.
    
    Args:
        path: Путь к файлу
        must_exist: Если True, файл должен существовать
        
    Returns:
        Tuple[bool, Optional[str]]: (валиден, сообщение об ошибке)
    """
    if not path or not path.strip():
        return False, "Путь не может быть пустым"
    
    path = path.strip()
    
    try:
        path_obj = Path(path)
        
        # Проверяем существование, если требуется
        if must_exist and not path_obj.exists():
            return False, f"Файл не найден: {path}"
        
        # Проверяем, что это файл, а не директория
        if must_exist and path_obj.is_dir():
            return False, "Указан путь к папке, а не к файлу"
        
        return True, None
        
    except (ValueError, OSError) as e:
        return False, f"Некорректный путь: {str(e)}"


def validate_folder_path(path: str, must_exist: bool = False) -> Tuple[bool, Optional[str]]:
    """Проверяет корректность пути к папке.
    
    Args:
        path: Путь к папке
        must_exist: Если True, папка должна существовать
        
    Returns:
        Tuple[bool, Optional[str]]: (валиден, сообщение об ошибке)
    """
    if not path or not path.strip():
        return False, "Путь не может быть пустым"
    
    path = path.strip()
    
    try:
        path_obj = Path(path)
        
        # Проверяем существование, если требуется
        if must_exist and not path_obj.exists():
            return False, f"Папка не найдена: {path}"
        
        # Проверяем, что это директория
        if must_exist and not path_obj.is_dir():
            return False, "Указан путь к файлу, а не к папке"
        
        return True, None
        
    except (ValueError, OSError) as e:
        return False, f"Некорректный путь: {str(e)}"


def validate_name(name: str, min_length: int = 1, max_length: int = 255) -> Tuple[bool, Optional[str]]:
    """Проверяет корректность названия (категории, раздела, ссылки).
    
    Args:
        name: Название для проверки
        min_length: Минимальная длина
        max_length: Максимальная длина
        
    Returns:
        Tuple[bool, Optional[str]]: (валиден, сообщение об ошибке)
    """
    if not name or not name.strip():
        return False, "Название не может быть пустым"
    
    name = name.strip()
    
    if len(name) < min_length:
        return False, f"Название слишком короткое (минимум {min_length} символ)"
    
    if len(name) > max_length:
        return False, f"Название слишком длинное (максимум {max_length} символов)"
    
    # Проверяем на недопустимые символы для имён файлов (опционально)
    invalid_chars = r'[<>:"|?*]'
    if re.search(invalid_chars, name):
        return False, "Название содержит недопустимые символы: < > : \" | ? *"
    
    return True, None


def validate_icon_path(path: str, supported_formats: Optional[list] = None) -> Tuple[bool, Optional[str]]:
    """Проверяет корректность пути к иконке.
    
    Args:
        path: Путь к иконке
        supported_formats: Список поддерживаемых расширений (например, ['.ico', '.png'])
        
    Returns:
        Tuple[bool, Optional[str]]: (валиден, сообщение об ошибке)
    """
    if not path or not path.strip():
        # Пустой путь допустим (будет использована иконка по умолчанию)
        return True, None
    
    path = path.strip()
    
    # Проверяем существование файла
    valid, error = validate_file_path(path, must_exist=True)
    if not valid:
        return False, error
    
    # Проверяем расширение
    if supported_formats:
        path_obj = Path(path)
        if path_obj.suffix.lower() not in supported_formats:
            formats_str = ", ".join(supported_formats)
            return False, f"Неподдерживаемый формат иконки. Поддерживаются: {formats_str}"
    
    return True, None


def validate_email(email: str) -> Tuple[bool, Optional[str]]:
    """Проверяет корректность email адреса.
    
    Args:
        email: Email для проверки
        
    Returns:
        Tuple[bool, Optional[str]]: (валиден, сообщение об ошибке)
    """
    if not email or not email.strip():
        return False, "Email не может быть пустым"
    
    email = email.strip()
    
    # Простая regex проверка email
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    
    if not re.match(email_pattern, email):
        return False, "Некорректный формат email адреса"
    
    return True, None


def validate_port(port: str) -> Tuple[bool, Optional[str]]:
    """Проверяет корректность номера порта.
    
    Args:
        port: Порт для проверки (строка)
        
    Returns:
        Tuple[bool, Optional[str]]: (валиден, сообщение об ошибке)
    """
    if not port or not port.strip():
        return False, "Порт не может быть пустым"
    
    try:
        port_num = int(port.strip())
        
        if port_num < 1 or port_num > 65535:
            return False, "Порт должен быть в диапазоне 1-65535"
        
        return True, None
        
    except ValueError:
        return False, "Порт должен быть числом"


def sanitize_filename(filename: str) -> str:
    """Очищает имя файла от недопустимых символов.
    
    Args:
        filename: Исходное имя файла
        
    Returns:
        str: Очищенное имя файла
        
    Example:
        >>> sanitize_filename("file:name?.txt")
        'file_name_.txt'
    """
    # Заменяем недопустимые символы на подчёркивание
    invalid_chars = r'[<>:"|?*/\\]'
    cleaned = re.sub(invalid_chars, '_', filename)
    
    # Удаляем множественные подчёркивания
    cleaned = re.sub(r'_+', '_', cleaned)
    
    # Удаляем подчёркивания в начале и конце
    cleaned = cleaned.strip('_')
    
    return cleaned if cleaned else "unnamed"
