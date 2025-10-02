"""
Утилиты для работы с иконками в диалоге ссылок.
"""

import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

from PyQt6.QtGui import QIcon

from app.utils.ui.icon.path_service import icon_path_service

logger = logging.getLogger(__name__)


class IconErrorKind(Enum):
    NOT_FOUND = "not_found"
    PERMISSION_DENIED = "permission_denied"
    OS_ERROR = "os_error"
    INVALID_PATH = "invalid_path"
    UNEXPECTED_ERROR = "unexpected_error"


@dataclass
class IconResult:
    success: bool
    icon: Optional[QIcon]
    resolved_path: Optional[Path]
    error_kind: Optional[IconErrorKind] = None
    error: Optional[Exception] = None
    message: str = ""


def make_icon_result(
    icon_path_str: str, *, raise_on_critical: bool = False
) -> IconResult:
    """Пытается создать QIcon и возвращает типизированный результат.

    Критические ситуации (ошибки доступа/ОС) могут поднимать исключения,
    если указан параметр raise_on_critical=True.
    """
    if not icon_path_str:
        return IconResult(
            False, None, None, IconErrorKind.INVALID_PATH, None, "Пустой путь к иконке"
        )

    candidates: list[Path]
    try:
        p = Path(icon_path_str)
        candidates = [p]
    except Exception as e:
        # Неверный формат пути
        if raise_on_critical:
            raise
        return IconResult(
            False,
            None,
            None,
            IconErrorKind.INVALID_PATH,
            e,
            f"Некорректный путь: {icon_path_str}",
        )

    # Добавляем относительные варианты
    try:
        candidates.append(icon_path_service.get_user_icons_dir() / icon_path_str)
    except (OSError, PermissionError) as e:
        if raise_on_critical:
            raise
        return IconResult(
            False,
            None,
            None,
            IconErrorKind.OS_ERROR,
            e,
            "Ошибка доступа к пользовательской папке иконок",
        )
    try:
        candidates.append(icon_path_service.get_ui_icons_dir() / icon_path_str)
    except (OSError, PermissionError) as e:
        if raise_on_critical:
            raise
        return IconResult(
            False,
            None,
            None,
            IconErrorKind.OS_ERROR,
            e,
            "Ошибка доступа к UI-папке иконок",
        )

    # Поиск первого существующего кандидата
    try:
        for c in candidates:
            try:
                if c.exists():
                    # Здесь QIcon не бросает, но оставим на случай будущих проверок
                    return IconResult(True, QIcon(str(c)), c, None, None, "")
            except PermissionError as e:
                if raise_on_critical:
                    raise
                return IconResult(
                    False,
                    None,
                    c,
                    IconErrorKind.PERMISSION_DENIED,
                    e,
                    f"Нет доступа к файлу: {c}",
                )
            except OSError as e:
                if raise_on_critical:
                    raise
                return IconResult(
                    False,
                    None,
                    c,
                    IconErrorKind.OS_ERROR,
                    e,
                    f"Ошибка ОС при проверке файла: {c}",
                )
    except Exception as e:
        if raise_on_critical:
            raise
        return IconResult(
            False,
            None,
            None,
            IconErrorKind.UNEXPECTED_ERROR,
            e,
            f"Неожиданная ошибка: {e}",
        )

    # Ничего не найдено
    return IconResult(
        False,
        None,
        None,
        IconErrorKind.NOT_FOUND,
        None,
        f"Иконка не найдена: {icon_path_str}",
    )


def make_icon(icon_path_str: str) -> Optional[QIcon]:
    """Создаёт QIcon из пути (абсолютного или относительного к папкам иконок).

    Возвращает QIcon или None, а также логирует детальные причины отказа:
    - not_found: путь отсутствует во всех проверенных местах
    - permission_denied: нет доступа к файлу/директории
    - os_error: системная ошибка при проверке
    - invalid_path: некорректный формат пути
    - unexpected_error: иные исключения
    """
    result = make_icon_result(icon_path_str, raise_on_critical=False)
    if result.success:
        return result.icon

    # Детализированное логирование по типам
    if result.error_kind == IconErrorKind.NOT_FOUND:
        logger.info("Иконка не найдена: %s", icon_path_str)
    elif result.error_kind == IconErrorKind.PERMISSION_DENIED:
        logger.warning("Нет доступа к иконке '%s': %s", icon_path_str, result.message)
    elif result.error_kind == IconErrorKind.OS_ERROR:
        logger.warning(
            "Ошибка ОС при доступе к иконке '%s': %s", icon_path_str, result.message
        )
    elif result.error_kind == IconErrorKind.INVALID_PATH:
        logger.warning(
            "Некорректный путь к иконке '%s': %s", icon_path_str, result.message
        )
    elif result.error_kind == IconErrorKind.UNEXPECTED_ERROR:
        logger.exception(
            "Неожиданная ошибка при создании иконки '%s': %s",
            icon_path_str,
            result.message,
        )

    return None
