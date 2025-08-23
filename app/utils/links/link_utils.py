"""
Улучшенный модуль для открытия различных типов ссылок

Поддерживает:
- Веб-ссылки (включая открытие в разных профилях Chrome)
- Файлы и папки
- Скрипты (.ps1, .py, .bat, .cmd)
- Программы
- Chrome приложения

Примеры использования Chrome профилей:
- args: "--profile-directory=Profile 1"
- args: "--profile-directory=Default"
- args: "--incognito"
- args: "--new-window --profile-directory=Work"
"""

import logging
import os
import platform
import re
import shlex
import subprocess
import webbrowser
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class LinkType(Enum):
    """Типы ссылок для обработки"""
    WEB = "web"
    FILE = "file"
    FOLDER = "folder"
    SCRIPT = "script"
    PROGRAM = "program"
    CHROMEAPP = "chromeapp"

@dataclass
class LinkInfo:
    """Структура для хранения информации о ссылке"""
    id: Optional[int]
    link_type: LinkType
    path: str
    args: str = ""
    category_id: Optional[int] = None
    browser_key: Optional[str] = None
    
    @classmethod
    def from_dict(cls, link_dict: Dict[str, Any]) -> 'LinkInfo':
        """Создает объект LinkInfo из словаря"""
        logger.debug("Creating LinkInfo from dict")
        
        # Безопасное преобразование типа ссылки
        link_type_str = link_dict.get("type", "web")
        
        try:
            link_type = LinkType(link_type_str)
        except ValueError:
            # Обратная совместимость
            type_mapping = {
                "url": LinkType.WEB,
                "app": LinkType.PROGRAM,
            }
            link_type = type_mapping.get(link_type_str, LinkType.WEB)
        
        # Извлекаем browser_key: сначала из поля, потом из аргументов
        browser_key_from_field = link_dict.get("browser_key")
        browser_key_from_args = cls._extract_browser_key_from_args(link_dict.get("args", ""))
        browser_key = browser_key_from_field or browser_key_from_args
        
        return cls(
            id=link_dict.get("id"),
            link_type=link_type,
            path=link_dict.get("url") or link_dict.get("path", ""),
            args=link_dict.get("args", ""),
            category_id=link_dict.get("category_id"),
            browser_key=browser_key
        )
    
    @staticmethod
    def _extract_browser_key_from_args(args: str) -> Optional[str]:
        """Извлекает browser_key из аргументов для обратной совместимости"""
        if not args:
            return None
        
        # Простое определение по Chrome-аргументам
        if "--profile-directory" in args or "--incognito" in args:
            return "chrome"
        
        return None

class SecurityValidator:
    """Улучшенная валидация безопасности"""
    
    # Более строгие паттерны для разных типов аргументов
    CHROME_ARG_PATTERN = re.compile(r'^--[\w-]+(=[\w\s\-_./:\\"]+)?$')
    PATH_PATTERN = re.compile(r'^[a-zA-Z]:[\\\/][\w\s\-_./\\:()]+$|^[\w\s\-_./()]+$')
    URL_PATTERN = re.compile(r'^https?://[^\s<>"{}|\\^`\[\]]+$')
    
    # Белый список разрешенных Chrome аргументов
    ALLOWED_CHROME_ARGS = {
        '--profile-directory', '--incognito', '--new-window', '--app',
        '--disable-web-security', '--user-data-dir', '--window-size',
        '--window-position', '--start-maximized', '--start-fullscreen'
    }
    
    # Черный список опасных символов (убран '&' для поддержки валидных URL)
    DANGEROUS_CHARS = {'|', ';', '\u003e', '\u003c', '`', '$', '(', ')', '{', '}'}
    
    @classmethod
    def sanitize_url(cls, url: str) -> str:
        """Возвращает очищенный URL.
        
        - Убирает префикс "view-source:" если после него идёт допустимая схема (http/https/chrome/chrome-extension).
        """
        if not url:
            return url
        try:
            s = url.strip()
            low = s.lower()
            prefix = 'view-source:'
            if low.startswith(prefix):
                candidate = s[len(prefix):].lstrip()
                low_cand = candidate.lower()
                if low_cand.startswith(('http://', 'https://', 'chrome://', 'chrome-extension://')):
                    return candidate
            return s
        except Exception:
            return url

    @classmethod
    def is_safe_url(cls, url: str) -> bool:
        """Проверяет безопасность URL"""
        if not url:
            return False
        
        # Проверяем на опасные символы
        if any(char in url for char in cls.DANGEROUS_CHARS):
            return False
        
        # Проверяем соответствие паттерну URL
        return bool(cls.URL_PATTERN.match(url))
    
    @classmethod
    def is_safe_path(cls, path: str) -> bool:
        """Проверяет безопасность файлового пути"""
        if not path:
            return False
        
        # Проверяем на опасные символы (кроме разрешенных для путей)
        dangerous_for_paths = cls.DANGEROUS_CHARS - {'(', ')'}
        if any(char in path for char in dangerous_for_paths):
            return False
        
        # Для Windows путей проверяем базовые требования безопасности
        # Разрешаем обычные пути к программам
        if platform.system() == "Windows":
            # Проверяем, что это похоже на Windows путь
            if len(path) >= 3 and path[1:3] == ':\\':
                return True
            if len(path) >= 3 and path[1:3] == ':/':
                return True
        
        # Проверяем соответствие паттерну пути
        return bool(cls.PATH_PATTERN.match(path))
    
    @classmethod
    def validate_chrome_args(cls, args: str) -> List[str]:
        """Валидирует Chrome аргументы"""
        if not args:
            return []
        
        try:
            parsed = shlex.split(args)
        except ValueError:
            logger.warning(f"Failed to parse arguments: {args}")
            return []
        
        validated = []
        has_incognito = False
        has_new_window = False
        
        for arg in parsed:
            # Проверяем формат аргумента
            if not cls.CHROME_ARG_PATTERN.match(arg):
                logger.warning(f"Invalid argument format: {arg}")
                continue
            
            # Извлекаем имя аргумента
            arg_name = arg.split('=')[0]
            
            # Проверяем белый список
            if arg_name in cls.ALLOWED_CHROME_ARGS:
                validated.append(arg)
                if arg_name == '--incognito':
                    has_incognito = True
                elif arg_name == '--new-window':
                    has_new_window = True
            else:
                logger.warning(f"Argument not in whitelist: {arg_name}")
        
        # Если есть --incognito но нет --new-window, добавляем --new-window для принудительного создания нового окна
        if has_incognito and not has_new_window:
            validated.insert(0, '--new-window')  # Добавляем в начало для правильного порядка
        
        return validated
    
    @classmethod
    def validate_args(cls, args: str) -> List[str]:
        """Универсальная валидация аргументов (для обратной совместимости)"""
        if not args:
            return []
        
        try:
            return shlex.split(args)
        except ValueError:
            logger.warning(f"Failed to parse arguments: {args}")
            return []

class BrowserConfig:
    """Конфигурация браузеров"""
    
    def __init__(self):
        from app.config_data import app_config
        self._config = app_config.get_browser_config()
        self._cache = {}
    
    def get_browser_command(self, browser_key: str, url: str, args: List[str]) -> List[str]:
        """Получает команду для запуска браузера"""
        if browser_key not in self._config:
            browser_key = "chrome"  # Fallback
        
        config = self._config[browser_key]
        executable = config["executable"]
        template = config["command_template"]
        
        # Заменяем плейсхолдеры
        command = []
        for part in template:
            if part == "{executable}":
                command.append(executable)
            elif part == "{url}":
                command.append(url)
            else:
                command.append(part)
        
        # Добавляем аргументы
        command.extend(args)
        
        return command

class LinkHandler(ABC):
    """Базовый класс для обработчиков ссылок"""
    
    def __init__(self, logger: logging.Logger):
        self.logger = logger
    
    @abstractmethod
    def can_handle(self, link_info: LinkInfo) -> bool:
        """Проверяет, может ли обработчик работать с данным типом ссылки"""
        pass
    
    @abstractmethod
    def open(self, link_info: LinkInfo) -> None:
        """Открывает ссылку"""
        pass

class WebLinkHandler(LinkHandler):
    """Обработчик веб-ссылок"""
    
    def __init__(self, logger: logging.Logger, browser_config: BrowserConfig):
        super().__init__(logger)
        self.browser_config = browser_config
    
    def can_handle(self, link_info: LinkInfo) -> bool:
        return link_info.link_type == LinkType.WEB
    
    def open(self, link_info: LinkInfo) -> None:
        """Открывает веб-ссылку"""
        # Очистка и валидация URL
        sanitized = SecurityValidator.sanitize_url(link_info.path)
        link_info.path = sanitized
        if not SecurityValidator.is_safe_url(link_info.path):
            raise ValueError(f"Unsafe URL: {link_info.path}")
        
        # Определяем браузер
        browser_key = link_info.browser_key or self._extract_browser_key(link_info.args) or "chrome"
        
        # Валидируем аргументы
        validated_args = SecurityValidator.validate_chrome_args(link_info.args)
        
        # Создаем команду
        command = self.browser_config.get_browser_command(browser_key, link_info.path, validated_args)
        
        try:
            # Используем shell=False для безопасности
            subprocess.Popen(command, shell=False)
            self.logger.info(f"Successfully opened URL {link_info.path} with {browser_key}")
        except Exception as e:
            self.logger.error(f"Failed to open URL with {browser_key}: {e}")
            # Fallback на системный браузер
            webbrowser.open(link_info.path)
    
    def _extract_browser_key(self, args: str) -> Optional[str]:
        """Извлекает browser_key из аргументов"""
        if not args:
            return None
        
        if "--profile-directory" in args or "--incognito" in args:
            return "chrome"
        
        return None

class FileLinkHandler(LinkHandler):
    """Обработчик файлов и папок"""
    
    def can_handle(self, link_info: LinkInfo) -> bool:
        return link_info.link_type in (LinkType.FILE, LinkType.FOLDER)
    
    def open(self, link_info: LinkInfo) -> None:
        """Открывает файл или папку"""
        # Валидация пути
        if not SecurityValidator.is_safe_path(link_info.path):
            raise ValueError(f"Unsafe path: {link_info.path}")
        
        if not os.path.exists(link_info.path):
            raise FileNotFoundError(f"Файл или папка не найдена: {link_info.path}")
        
        try:
            if platform.system() == "Windows":
                os.startfile(link_info.path)
            else:
                subprocess.Popen(['xdg-open', link_info.path])
            
            self.logger.info(f"Successfully opened: {link_info.path}")
        except OSError as e:
            self.logger.error(f"Failed to open {link_info.path}: {e}")
            raise

class ScriptLinkHandler(LinkHandler):
    """Обработчик скриптов"""
    
    def __init__(self, logger: logging.Logger, powershell_path: str = None):
        super().__init__(logger)
        self.powershell_path = powershell_path or self._get_powershell_path()
    
    def _get_powershell_path(self) -> str:
        """Получает путь к PowerShell"""
        try:
            from app.config_data import app_config
            return app_config.get_powershell_path()
        except ImportError:
            return "powershell.exe"
    
    def can_handle(self, link_info: LinkInfo) -> bool:
        return link_info.link_type == LinkType.SCRIPT
    
    def open(self, link_info: LinkInfo) -> None:
        """Открывает скрипт"""
        if not SecurityValidator.is_safe_path(link_info.path):
            raise ValueError(f"Unsafe script path: {link_info.path}")
        
        if not os.path.exists(link_info.path):
            raise FileNotFoundError(f"Скрипт не найден: {link_info.path}")
        
        path = Path(link_info.path)
        ext = path.suffix.lower()
        arg_list = SecurityValidator.validate_args(link_info.args)
        
        script_handlers = {
            '.ps1': self._create_powershell_command,
            '.py': self._create_python_command,
            '.bat': self._create_batch_command,
            '.cmd': self._create_batch_command,
        }
        
        handler = script_handlers.get(ext)
        if handler:
            cmd = handler(link_info.path, arg_list)
            flags = 0 if ext in ('.bat', '.cmd') else subprocess.CREATE_NEW_CONSOLE
            subprocess.Popen(cmd, creationflags=flags)
        else:
            # Для неизвестных расширений используем системный обработчик
            if platform.system() == "Windows":
                os.startfile(link_info.path)
            else:
                subprocess.Popen(['xdg-open', link_info.path])
    
    def _create_powershell_command(self, path: str, args: List[str]) -> List[str]:
        """Создает команду для PowerShell скрипта"""
        cmd_args = ['-ExecutionPolicy', 'Bypass', '-Command', f'& "{path}"']
        if args:
            cmd_args.extend(args)
        return [self.powershell_path] + cmd_args
    
    def _create_python_command(self, path: str, args: List[str]) -> List[str]:
        """Создает команду для Python скрипта"""
        return ['python', path] + args
    
    def _create_batch_command(self, path: str, args: List[str]) -> List[str]:
        """Создает команду для batch файла"""
        return ['cmd.exe', '/c', 'start', '""', path] + args

class ProgramLinkHandler(LinkHandler):
    """Обработчик программ"""
    
    def can_handle(self, link_info: LinkInfo) -> bool:
        return link_info.link_type == LinkType.PROGRAM
    
    def open(self, link_info: LinkInfo) -> None:
        """Открывает программу"""
        if not SecurityValidator.is_safe_path(link_info.path):
            raise ValueError(f"Unsafe program path: {link_info.path}")
        
        if not os.path.exists(link_info.path):
            raise FileNotFoundError(f"Программа не найдена: {link_info.path}")
        
        try:
            # Для программ используем простое разбиение аргументов без строгой валидации Chrome
            arg_list = []
            if link_info.args:
                try:
                    arg_list = shlex.split(link_info.args)
                except ValueError:
                    self.logger.warning(f"Failed to parse program arguments: {link_info.args}")
                    arg_list = []
            
            subprocess.Popen([link_info.path] + arg_list)
            self.logger.info(f"Successfully launched program: {link_info.path} with args: {arg_list}")
        except (OSError, subprocess.SubprocessError) as e:
            self.logger.error(f"Failed to launch program {link_info.path}: {e}")
            raise

class ChromeAppLinkHandler(LinkHandler):
    """Обработчик Chrome приложений"""
    
    def can_handle(self, link_info: LinkInfo) -> bool:
        return link_info.link_type == LinkType.CHROMEAPP
    
    def open(self, link_info: LinkInfo) -> None:
        """Открывает Chrome приложение"""
        try:
            webbrowser.open(link_info.path)
            self.logger.info(f"Successfully opened Chrome app: {link_info.path}")
        except Exception as e:
            self.logger.error(f"Failed to open Chrome app {link_info.path}: {e}")
            raise

class LinkOpener:
    """Основной класс для открытия различных типов ссылок"""
    
    def __init__(self, powershell_path: str = None):
        self.logger = logging.getLogger(__name__)
        self.browser_config = BrowserConfig()
        
        # Инициализация обработчиков
        self.handlers: List[LinkHandler] = [
            WebLinkHandler(self.logger, self.browser_config),
            FileLinkHandler(self.logger),
            ScriptLinkHandler(self.logger, powershell_path),
            ProgramLinkHandler(self.logger),
            ChromeAppLinkHandler(self.logger),
        ]
    
    def _build_chrome_command(self, url: str, args: List[str]) -> List[str]:
        """Создает команду для запуска Chrome (для обратной совместимости)"""
        return self.browser_config.get_browser_command("chrome", url, args)
    
    def _build_browser_command(self, browser_key: str, url: str, args: List[str]) -> List[str]:
        """Создает команду для запуска браузера (для обратной совместимости)"""
        return self.browser_config.get_browser_command(browser_key, url, args)
    
    def _open_web_link(self, link_info: LinkInfo) -> None:
        """Открывает веб-ссылку (для обратной совместимости)"""
        handler = WebLinkHandler(self.logger, self.browser_config)
        handler.open(link_info)
    
    def _open_file_or_folder(self, link_info: LinkInfo) -> None:
        """Открывает файл или папку (для обратной совместимости)"""
        handler = FileLinkHandler(self.logger)
        handler.open(link_info)
    
    def _open_script(self, link_info: LinkInfo) -> None:
        """Открывает скрипт (для обратной совместимости)"""
        handler = ScriptLinkHandler(self.logger)
        handler.open(link_info)
    
    def _open_program(self, link_info: LinkInfo) -> None:
        """Открывает программу (для обратной совместимости)"""
        handler = ProgramLinkHandler(self.logger)
        handler.open(link_info)
    
    def _open_chrome_app(self, link_info: LinkInfo) -> None:
        """Открывает Chrome приложение (для обратной совместимости)"""
        handler = ChromeAppLinkHandler(self.logger)
        handler.open(link_info)
    
    def open_link(self, link_info) -> None:
        """Открывает ссылку в зависимости от её типа"""
        # Валидация входных данных
        if not link_info:
            raise ValueError("ЛинкИнфо не может быть None")
        
        # Преобразуем словарь в LinkInfo, если нужно
        if isinstance(link_info, dict):
            link_info = LinkInfo.from_dict(link_info)
        elif not isinstance(link_info, LinkInfo):
            raise ValueError(f"Неподдерживаемый тип link_info: {type(link_info)}")
        
        if not link_info.path or not link_info.path.strip():
            raise ValueError("Путь к ссылке не может быть пустым")
        
        if not isinstance(link_info.link_type, LinkType):
            raise ValueError(f"Некорректный тип ссылки: {link_info.link_type}")
        
        self.logger.debug(f"Opening link: {link_info.link_type.value} - {link_info.path}")
        
        # Поиск подходящего обработчика
        for handler in self.handlers:
            if handler.can_handle(link_info):
                try:
                    handler.open(link_info)
                    return
                except Exception as e:
                    self.logger.error(f"Handler {handler.__class__.__name__} failed: {e}")
                    raise
        
        # Если обработчик не найден
        raise ValueError(f"Неподдерживаемый тип ссылки: {link_info.link_type}")

# Утилитарные функции для удобства использования (обратная совместимость)
def create_link_opener(powershell_path: str = None) -> LinkOpener:
    """Создает экземпляр LinkOpener с настройками по умолчанию."""
    return LinkOpener(powershell_path)

def open_link_from_dict(link_dict: Dict[str, Any], powershell_path: str = None) -> None:
    """
    Открывает ссылку из словаря данных.
    
    Args:
        link_dict: Словарь с данными ссылки
        powershell_path: Путь к PowerShell (опционально)
    """
    link_info = LinkInfo.from_dict(link_dict)
    opener = LinkOpener(powershell_path)
    opener.open_link(link_info)

def get_value(link: Dict[str, Any], key: str, default: Any = None) -> Any:
    """
    Безопасно извлекает значение из словаря ссылки.
    
    Args:
        link: Словарь с данными ссылки
        key: Ключ для извлечения
        default: Значение по умолчанию
        
    Returns:
        Значение из словаря или значение по умолчанию
    """
    if hasattr(link, 'get'):
        return link.get(key, default)
    elif isinstance(link, dict):
        return link.get(key, default)
    else:
        return getattr(link, key, default)

def validate_link_path(path: str, link_type: LinkType) -> bool:
    """
    Валидирует путь ссылки в зависимости от её типа.
    
    Args:
        path: Путь к ссылке
        link_type: Тип ссылки
        
    Returns:
        True если путь валиден, False иначе
    """
    if not path or not path.strip():
        return False
    
    if link_type == LinkType.WEB:
        # Убираем префикс view-source: и затем валидируем
        path = SecurityValidator.sanitize_url(path)
        return SecurityValidator.is_safe_url(path) or '.' in path
    elif link_type in (LinkType.FILE, LinkType.FOLDER, LinkType.SCRIPT, LinkType.PROGRAM):
        return SecurityValidator.is_safe_path(path) and os.path.exists(path)
    elif link_type == LinkType.CHROMEAPP:
        return path.startswith(('chrome://', 'chrome-extension://', 'http://', 'https://'))
    
    return True

def get_link_type_from_path(path: str) -> LinkType:
    """
    Определяет тип ссылки по её пути.
    
    Args:
        path: Путь к ссылке
        
    Returns:
        Предполагаемый тип ссылки
    """
    if not path:
        return LinkType.WEB
    
    # Очищаем специальные префиксы вроде view-source:
    path = SecurityValidator.sanitize_url(path)
    path_lower = path.lower()
    
    # Веб-ссылки
    if path_lower.startswith(('http://', 'https://', 'ftp://')):
        return LinkType.WEB
    
    # Chrome приложения
    if path_lower.startswith(('chrome://', 'chrome-extension://')):
        return LinkType.CHROMEAPP
    
    # Файловые пути
    if os.path.exists(path):
        if os.path.isdir(path):
            return LinkType.FOLDER
        elif os.path.isfile(path):
            ext = Path(path).suffix.lower()
            if ext in ('.ps1', '.py', '.bat', '.cmd', '.sh'):
                return LinkType.SCRIPT
            elif ext in ('.exe', '.msi', '.app'):
                return LinkType.PROGRAM
            else:
                return LinkType.FILE
    
    # По умолчанию считаем веб-ссылкой
    return LinkType.WEB