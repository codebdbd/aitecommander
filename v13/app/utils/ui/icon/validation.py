# validation.py
"""Валидация иконок и проверочные утилиты.

Особенности:
- Жёсткая фильтрация имён иконок без слэшей для защиты от traversal.
- Акуратная проверка SVG/SVGZ (по содержимому, с ограничением размера чтения).
- Проверка растров через PIL без лишних открытий файлов.
- Поддержка конфигурации через app_config.

Соответствует PEP 8.
"""

from __future__ import annotations

import logging
import os
import re
from enum import Enum
from pathlib import Path
from typing import Iterable

from PIL import Image, UnidentifiedImageError

from app.config_data import app_config

logger = logging.getLogger(__name__)


# === Конфигурационные прокси (обновляются динамически) ===


def get_max_icon_size() -> int:
    """Максимальный размер файла иконки в байтах (из конфигурации)."""
    return int(app_config.get_max_icon_size())


def get_supported_icon_formats() -> Iterable[str]:
    """Набор поддерживаемых растровых расширений (включая .png, .jpg и т.п.)."""
    return app_config.get_supported_icon_formats()


def get_valid_themes() -> Iterable[str]:
    """Список валидных названий тем."""
    return app_config.get_valid_themes()


# === Перечисления / исключения ===


class Theme(Enum):
    """Тема оформления."""

    LIGHT = "light"
    DARK = "dark"

    @classmethod
    def from_string(cls, theme_str: str) -> "Theme":
        s = (theme_str or "").lower().strip()
        return cls.DARK if s == "dark" else cls.LIGHT


class IconError(Exception):
    """Базовое исключение для ошибок иконок."""


class IconNotFoundError(IconError):
    """Иконка не найдена."""


class InvalidIconError(IconError):
    """Файл иконки/параметры некорректны."""


# === Внутренние валидаторы для векторных форматов ===


def _safe_decode_bytes_preview(data: bytes) -> str | None:
    """Попытка декодирования первых байт файла в строку.

    Порядок кодировок: utf-8 → utf-16 → latin-1.
    Возвращает None, если декодировать не удалось.
    """
    for enc in ("utf-8", "utf-16", "latin-1"):
        try:
            return data.decode(enc, errors="strict")
        except UnicodeDecodeError:
            continue
    return None


def _is_valid_svg(path: Path) -> bool:
    """Проверка корректности SVG по структуре тегов."""
    try:
        max_read_size = min(get_max_icon_size(), 1024 * 1024)  # не более 1 МБ
        with path.open("rb") as f:
            content = f.read(max_read_size)

        text = _safe_decode_bytes_preview(content)
        if text is None:
            logger.debug("SVG decode failed: %s", path)
            return False

        open_tag = re.search(r"<\s*svg\b[^>]*>", text, re.IGNORECASE | re.DOTALL)
        close_tag = re.search(r"<\s*/\s*svg\s*>", text, re.IGNORECASE)
        if not open_tag or not close_tag:
            logger.debug("SVG tags missing in: %s", path)
            return False
        return True
    except Exception as exc:  # noqa: BLE001
        logger.debug("SVG validation error for %s: %s", path, exc)
        return False


def _is_valid_svgz(path: Path) -> bool:
    """Проверка корректности SVGZ (gzip + валидный SVG внутри)."""
    import gzip

    try:
        # быстрая сигнатура gzip
        with path.open("rb") as f:
            sig = f.read(2)
            if len(sig) < 2 or sig[0] != 0x1F or sig[1] != 0x8B:
                logger.debug("Not a gzip file: %s", path)
                return False

        max_read_size = min(get_max_icon_size(), 1024 * 1024)
        with gzip.open(path, "rb") as f:
            content = f.read(max_read_size)

        text = _safe_decode_bytes_preview(content)
        if text is None:
            logger.debug("SVGZ inner decode failed: %s", path)
            return False

        open_tag = re.search(r"<\s*svg\b[^>]*>", text, re.IGNORECASE | re.DOTALL)
        close_tag = re.search(r"<\s*/\s*svg\s*>", text, re.IGNORECASE)
        return bool(open_tag and close_tag)
    except (OSError, gzip.BadGzipFile) as exc:
        logger.debug("SVGZ validation error for %s: %s", path, exc)
        return False
    except Exception as exc:  # noqa: BLE001
        logger.warning("Unexpected SVGZ error for %s: %s", path, exc)
        return False


# === Публичные валидаторы ===


def _validate_icon_name(icon_name: str) -> bool:
    """Проверка имени иконки.

    Требования:
    - Строка непустая.
    - Разрешённые символы: латиница, цифры, `_`, `-`, `.`.
    - Запрещены пути/подпапки и traversal (`/`, `\\`, `..`), чтобы не обращаться вне ожидаемой папки.
    """
    if not icon_name or not isinstance(icon_name, str):
        return False

    if "../" in icon_name or "..\\" in icon_name:
        return False

    # никаких слэшей — иконки ищутся только в ожидаемых темовых папках сервисом путей
    if "/" in icon_name or "\\" in icon_name:
        return False

    return bool(re.match(r"^[a-zA-Z0-9_.-]+$", icon_name))


def validate_theme(theme: str) -> str:
    """Нормализация названия темы. Non-str или неизвестная → 'light'."""
    if not theme or not isinstance(theme, str):
        return "light"
    t = theme.lower().strip()
    if t in get_valid_themes():
        return t
    logger.warning("Invalid theme '%s', using 'light'", theme)
    return "light"


def is_valid_icon_file(file_path: str | Path) -> bool:
    """Проверка, является ли путь допустимым файлом иконки.

    Поддержка:
    - SVG / SVGZ (структурная проверка).
    - Растровые форматы из конфигурации (через PIL.Image.verify()).
    - Ограничение размера файла из конфигурации.

    Возвращает:
        True, если файл приемлем; False — иначе.
    """
    if not file_path:
        return False

    path = Path(file_path)
    if not (path.exists() and path.is_file()):
        return False

    # лимит размера
    try:
        file_size = path.stat().st_size
    except OSError as exc:
        logger.debug("stat() failed for %s: %s", path, exc)
        return False

    max_size = get_max_icon_size()
    if file_size > max_size:
        logger.debug("File too large %s (%s > %s)", path, file_size, max_size)
        return False

    ext = path.suffix.lower()

    if ext == ".svg":
        return _is_valid_svg(path)

    if ext == ".svgz":
        return _is_valid_svgz(path)

    if ext not in set(map(str.lower, get_supported_icon_formats())):
        logger.debug("Unsupported raster format %s for %s", ext, path)
        return False

    # Растры: быстрая проверка целостности
    try:
        with Image.open(path) as img:
            img.verify()  # не загружает в память полностью
        return True
    except (UnidentifiedImageError, OSError) as exc:
        logger.debug("PIL verify failed for %s: %s", path, exc)
        return False
    except Exception as exc:  # noqa: BLE001
        logger.warning("Unexpected raster validation error for %s: %s", path, exc)
        return False


def validate_config_for_icons(config) -> bool:
    """Проверяет, что конфиг поддерживает директории иконок.

    Минимальная проверка UI-иконок: наличие метода get_link_icons_dir.
    Держим в UI-слое, чтобы не тянуть UI-зависимость в общий validators.
    """
    return hasattr(config, "get_link_icons_dir")


def is_cached_icon_valid(save_path: str | Path, source_path: str | Path) -> bool:
    """Проверяет, актуальна ли кэшированная иконка по времени модификации.

    Возвращает True, если save_path существует, является валидным файлом иконки
    и его mtime не меньше, чем у исходного файла.
    """
    try:
        save_path = str(save_path)
        source_path = str(source_path)
        if not (os.path.exists(save_path) and is_valid_icon_file(save_path)):
            return False
        return os.path.getmtime(save_path) >= os.path.getmtime(source_path)
    except OSError:
        return False


# === Стартап-валидация окружения иконок ===


def validate_ui_icon_environment() -> bool:
    """Проверяет базовую готовность окружения иконок.

    Проверки:
    - Существует базовая директория UI-иконок из конфигурации (`app_config.paths.get_ui_icons_dir()`).
    - Существуют подпапки для всех валидных тем (`app_config.get_valid_themes()`).

    Возвращает True, если все проверки пройдены; иначе False.
    Логи пишет сам (error/warning/info).
    """
    ok = True
    try:
        base_dir = app_config.paths.get_ui_icons_dir()
    except Exception as exc:  # noqa: BLE001
        logger.error("Не удалось получить путь к UI-иконкам из конфигурации: %s", exc)
        return False

    if not base_dir or not isinstance(base_dir, (str, Path)):
        logger.error("Некорректный путь к UI-иконкам в конфигурации: %r", base_dir)
        return False

    base_dir = Path(base_dir)
    if not base_dir.exists() or not base_dir.is_dir():
        logger.error("Директория UI-иконок не найдена: %s", base_dir)
        ok = False
    else:
        logger.info("Директория UI-иконок: %s", base_dir)

    # Проверка тем
    try:
        themes = list(get_valid_themes())
    except Exception as exc:  # noqa: BLE001
        logger.warning("Не удалось получить список валидных тем: %s", exc)
        themes = ["light", "dark"]

    for t in themes:
        theme_dir = base_dir / t
        if not theme_dir.exists() or not theme_dir.is_dir():
            logger.error("Папка темы не найдена: %s", theme_dir)
            ok = False
        else:
            # Небольшая информационная сводка
            try:
                count = sum(1 for _ in theme_dir.iterdir())
                logger.info("Тема '%s': %s (элементов: %d)", t, theme_dir, count)
            except OSError as exc:  # noqa: BLE001
                logger.debug(
                    "Не удалось просканировать папку темы %s: %s", theme_dir, exc
                )

    return ok


def validate_and_log_ui_icons_startup() -> bool:
    """Запускает проверку окружения иконок на старте и пишет сводку в лог.

    Возвращает результат `validate_ui_icon_environment()` без прерывания запуска.
    """
    result = validate_ui_icon_environment()
    if result:
        logger.info("Проверка окружения UI-иконок: OK")
    else:
        logger.warning(
            "Проверка окружения UI-иконок завершена с ошибками. Проверьте путь и темы."
        )
    return result
