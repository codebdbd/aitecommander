# creators.py
"""Функции создания иконок с async поддержкой и thread safety."""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path

from PyQt6.QtCore import QRectF, QSize, Qt, QThread
from PyQt6.QtGui import QGuiApplication, QIcon, QImage, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import QApplication

from app.config_data import app_config
from app.utils.ui.icon.inflight import (
    enter_async,
    enter_sync,
    leave_async_error,
    leave_async_success,
    leave_sync,
)
from app.utils.ui.qt.gui_exec import is_gui_thread, run_in_gui_thread_async

from ..cache_manager import (
    get_icon,
    record_actual_miss,
    record_disk_load,
    record_not_found,
    set_icon,
)
from ..path_service import (
    get_icon_path,
    metrics_record_disk_load,
    metrics_record_hit,
    metrics_record_miss,
    metrics_record_not_found,
)
from ..validation import (
    InvalidIconError,
    _validate_icon_name,
    is_valid_icon_file,
    validate_theme,
)

logger = logging.getLogger(__name__)


def _ensure_gui_thread(context: str = "") -> bool:
    """Убедиться, что код выполняется в GUI-потоке. True, если в GUI-потоке.

    Note:
      QImage и QPainter могут использоваться вне GUI-потока для рендеринга в QImage.
      QPixmap и QIcon должны создаваться только в GUI-потоке.
    """
    if not is_gui_thread():
        try:
            app = QApplication.instance()
            if app:
                logger.debug(
                    "Попытка выполнения %s не в GUI-потоке. Current thread: %s, GUI thread: %s",
                    context,
                    QThread.currentThread(),
                    app.thread(),
                )
                # Откладываем выполнение в GUI-поток
                # Возвращаем False, чтобы вызывающая функция могла принять решение
                return False
            logger.warning(
                "Попытка выполнения %s до инициализации QApplication", context
            )
        except (ImportError, RuntimeError):
            logger.warning(
                "Попытка выполнения %s до инициализации QApplication (ImportError/RuntimeError)",
                context,
            )
        return False
    return True


# === СОЗДАНИЕ SVG ИКОНОК ===


def _create_svg_icon(svg_path: str) -> QIcon:
    """Создать QIcon из SVG файла.

    Note:
        QImage и QPainter могут использоваться вне GUI-потока для рендеринга в QImage.
        QPixmap и QIcon должны создаваться только в GUI-потоке.
    """
    try:
        renderer = QSvgRenderer(svg_path)
        if not renderer.isValid():
            raise InvalidIconError(f"Invalid SVG file: {svg_path}")

        # Рендерим в QImage вместо QPixmap для потокобезопасности
        # Учитываем HiDPI: растеризуем в физических пикселях и выставляем DPR у Pixmap
        base_size = app_config.get_default_icon_size()
        try:
            screen = QGuiApplication.primaryScreen()
            dpr = float(screen.devicePixelRatio()) if screen is not None else 1.0
        except Exception:
            dpr = 1.0

        render_w = max(1, int(round(base_size * dpr)))
        render_h = max(1, int(round(base_size * dpr)))
        image = QImage(
            QSize(render_w, render_h), QImage.Format.Format_ARGB32_Premultiplied
        )
        image.fill(Qt.GlobalColor.transparent)

        painter = QPainter()
        if not painter.begin(image):
            raise InvalidIconError(f"Failed to initialize painter for: {svg_path}")

        # Set render hints for better quality
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        try:
            renderer.render(painter, QRectF(0, 0, render_w, render_h))
            # Конвертируем QImage в QPixmap и выставляем DPR
            pixmap = QPixmap.fromImage(image)
            try:
                pixmap.setDevicePixelRatio(dpr)
            except Exception:
                pass
            return QIcon(pixmap)
        finally:
            painter.end()

    except (OSError, RuntimeError) as exc:
        raise InvalidIconError(
            f"Error creating SVG icon from {svg_path}: {exc}"
        ) from exc
    except Exception as exc:
        raise InvalidIconError(
            f"Unexpected error creating SVG icon from {svg_path}: {exc}"
        ) from exc


async def _create_svg_icon_async(svg_path: str) -> QIcon:
    """Асинхронно создать QIcon из SVG файла."""
    # Создание QPixmap/QIcon должно происходить в GUI-потоке
    return await run_in_gui_thread_async(lambda: _create_svg_icon(svg_path))


def _create_icon_from_file_path(file_path: str) -> QIcon:
    """Общая функция создания иконки из файла с высоким качеством."""
    path_obj = Path(file_path)

    if path_obj.suffix.lower() == ".svg":
        # Специальная обработка SVG
        try:
            icon = _create_svg_icon(str(path_obj))
            if not icon.isNull():
                return icon
        except InvalidIconError as exc:
            logger.debug("Error creating SVG icon from %s: %s", file_path, exc)

        # Fallback на PNG версию иконки
        png_path = path_obj.with_suffix(".png")
        if png_path.exists() and is_valid_icon_file(str(png_path)):
            logger.debug("Falling back to PNG version: %s", png_path)
            return _create_icon_from_file_path(str(png_path))

        return QIcon()
    else:
        # Обычные форматы изображений - создаем QIcon напрямую
        if path_obj.exists() and is_valid_icon_file(str(path_obj)):
            # Простое создание иконки без масштабирования
            return QIcon(str(path_obj))
        else:
            logger.debug("Invalid or non-existent icon file: %s", path_obj)
            return QIcon()


async def _create_icon_from_file_path_async(file_path: str) -> QIcon:
    """Асинхронная версия общей функции создания иконки из файла."""
    path_obj = Path(file_path)

    if path_obj.suffix.lower() == ".svg":
        # Специальная обработка SVG
        try:
            icon = await _create_svg_icon_async(str(path_obj))
            if not icon.isNull():
                return icon
        except InvalidIconError as exc:
            logger.debug("Error creating SVG icon from %s: %s", file_path, exc)

        # Fallback на PNG версию иконки
        png_path = path_obj.with_suffix(".png")
        if png_path.exists() and is_valid_icon_file(str(png_path)):
            logger.debug("Falling back to PNG version: %s", png_path)
            # Создаем иконку строго в GUI-потоке
            return await run_in_gui_thread_async(lambda: QIcon(str(png_path)))

        # Если PNG версия недоступна, возвращаем пустую иконку
        return QIcon()
    else:
        # Обычные форматы изображений - создаем строго в GUI-потоке
        return await run_in_gui_thread_async(
            lambda: _create_icon_from_file_path(str(path_obj))
        )


# === ОСНОВНЫЕ ФУНКЦИИ СОЗДАНИЯ ИКОНОК ===


def themed_icon(icon_name: str, theme: str = "light", source: str = "unknown") -> QIcon:
    """Создать QIcon с кешированием и поддержкой SVG."""
    # Проверка на потокобезопасность: QIcon должен создаваться только в GUI-потоке
    if not _ensure_gui_thread(f"создания themed_icon ({icon_name})"):
        logger.warning(
            "themed_icon called from non-GUI thread for %s, returning empty icon",
            icon_name,
        )
        return QIcon()

    # Валидация параметров
    if not _validate_icon_name(icon_name):
        logger.warning("Invalid icon name provided from %s", source)
        return QIcon()

    theme = validate_theme(theme)

    # Проверяем кеш
    cached_icon = get_icon(icon_name, theme)
    if cached_icon is not None:
        try:
            metrics_record_hit()
        finally:
            pass
        return cached_icon

    # Начинаем замер времени загрузки
    start_time = time.time()

    # In-flight дедупликация (sync)
    key = (icon_name, theme)
    leader, ev = enter_sync(key)
    if not leader:
        ev.wait()
        cached_after = get_icon(icon_name, theme)
        return cached_after if cached_after is not None else QIcon()

    try:
        # Получаем путь к иконке
        path = get_icon_path(icon_name, theme)
        if not path:
            # Файл не найден — записываем промах и кэшируем негативную запись
            load_time = time.time() - start_time
            record_actual_miss(load_time)
            record_not_found()
            logger.debug(
                "Icon not found: %s (theme: %s, source: %s)", icon_name, theme, source
            )
            # Кэшируем пустую иконку как негативную, чтобы повторные запросы
            # быстро отдавали результат до истечения короткого TTL
            set_icon(icon_name, theme, None, negative=True)
            return QIcon()

        # Используем общую функцию создания иконки
        icon = _create_icon_from_file_path(path)

        # Замеряем время загрузки и записываем успешную загрузку с диска
        load_time = time.time() - start_time
        metrics_record_disk_load(load_time)

        # Кешируем результат
        set_icon(icon_name, theme, icon)
        if (
            load_time > 0.1
        ):  # Если загрузка заняла более 100 мс, логируем на уровне INFO
            logger.info(
                "Slow disk load: icon '%s' for theme '%s' took %.2fms",
                icon_name,
                theme,
                load_time * 1000,
            )
        else:
            logger.debug(
                "Loaded and cached icon '%s' for theme '%s' in %.2fms",
                icon_name,
                theme,
                load_time * 1000,
            )
        return icon

    except InvalidIconError as exc:
        # Замеряем время неудачной загрузки
        load_time = time.time() - start_time
        metrics_record_not_found(load_time)

        logger.error("Error creating icon '%s' from %s: %s", icon_name, source, exc)
        # Кэшируем пустую иконку с флагом negative=True и отдельным TTL
        set_icon(icon_name, theme, None, negative=True)
        return QIcon()
    except Exception as exc:
        # Замеряем время неудачной загрузки
        load_time = time.time() - start_time
        metrics_record_miss(load_time)

        logger.error(
            "Unexpected error creating icon '%s' from %s: %s", icon_name, source, exc
        )
        # Кэшируем пустую иконку с флагом negative=True и отдельным TTL
        set_icon(icon_name, theme, None, negative=True)
        return QIcon()
    finally:
        leave_sync(key)


async def themed_icon_async(
    icon_name: str, theme: str = "light", source: str = "unknown"
) -> QIcon:
    """Асинхронно создать QIcon с кешированием и поддержкой SVG."""
    # Валидация параметров
    if not _validate_icon_name(icon_name):
        logger.warning("Invalid icon name provided from %s", source)
        return QIcon()

    theme = validate_theme(theme)

    # Проверяем кеш (синхронно, так как это быстрая операция)
    cached_icon = get_icon(icon_name, theme)
    if cached_icon is not None:
        try:
            metrics_record_hit()
        finally:
            pass
        return cached_icon

    # Начинаем замер времени загрузки
    start_time = time.time()

    # In-flight дедупликация (async)
    akey = (icon_name, theme)
    leader, fut = enter_async(akey)
    if not leader:
        try:
            icon_res = await fut
        except Exception:
            return QIcon()
        cached_after = get_icon(icon_name, theme)
        return (
            cached_after
            if cached_after is not None
            else (icon_res if icon_res is not None else QIcon())
        )

    try:
        # Асинхронно получаем путь к иконке
        loop = asyncio.get_event_loop()
        path = await loop.run_in_executor(None, get_icon_path, icon_name, theme)
        if not path:
            load_time = time.time() - start_time
            metrics_record_not_found(load_time)
            logger.debug(
                "Icon not found: %s (theme: %s, source: %s)", icon_name, theme, source
            )
            leave_async_success(akey, None)
            return QIcon()

        # Используем общую асинхронную функцию создания иконки
        icon = await _create_icon_from_file_path_async(path)

        # Замеряем время загрузки и записываем успешную загрузку с диска
        load_time = time.time() - start_time
        metrics_record_disk_load(load_time)

        # Кешируем результат
        set_icon(icon_name, theme, icon)
        if load_time > 0.1:
            logger.info(
                "Slow async disk load: icon '%s' for theme '%s' took %.2fms",
                icon_name,
                theme,
                load_time * 1000,
            )
        else:
            logger.debug(
                "Loaded and cached icon '%s' for theme '%s' async in %.2fms",
                icon_name,
                theme,
                load_time * 1000,
            )
        leave_async_success(akey, icon)
        return icon

    except InvalidIconError as exc:
        # Замеряем время неудачной загрузки
        load_time = time.time() - start_time
        record_actual_miss(load_time)
        record_not_found()

        logger.error(
            "Error creating async icon '%s' from %s: %s", icon_name, source, exc
        )
        # Кэшируем пустую иконку с флагом negative=True и отдельным TTL
        set_icon(icon_name, theme, None, negative=True)
        leave_async_error(akey, exc)
        return QIcon()
    except Exception as exc:
        # Замеряем время неудачной загрузки
        load_time = time.time() - start_time
        record_actual_miss(load_time)
        record_not_found()

        logger.error(
            "Unexpected error creating async icon '%s' from %s: %s",
            icon_name,
            source,
            exc,
        )
        # Кэшируем пустую иконку с флагом negative=True и отдельным TTL
        set_icon(icon_name, theme, None, negative=True)
        leave_async_error(akey, exc)
        return QIcon()


# === СОЗДАНИЕ ИКОНОК ИЗ АБСОЛЮТНЫХ ПУТЕЙ ===


def create_icon_from_path(icon_path: str) -> QIcon:
    """Создать QIcon из пути к файлу с кэшированием."""
    # Проверка на потокобезопасность: QIcon должен создаваться только в GUI-потоке
    if not _ensure_gui_thread(f"создания иконки из пути ({icon_path})"):
        logger.warning(
            "create_icon_from_path called from non-GUI thread for %s, returning empty icon",
            icon_path,
        )
        return QIcon()

    # Используем namespaced ключ чтобы избежать коллизий
    cache_key = f"abspath::{icon_path}"
    # Проверяем кэш - логика TTL уже реализована в cache_manager
    cached_icon = get_icon(cache_key, "__abs__")

    if cached_icon is not None:
        logger.debug("Cache HIT for absolute path icon: %s", icon_path)
        return cached_icon
    logger.debug("Cache MISS for absolute path icon: %s", icon_path)

    # Замеряем время загрузки
    start_time = time.time()

    # Создаем новую иконку с высоким качеством
    exists = Path(icon_path).exists()
    if exists:
        icon = _create_icon_from_file_path(icon_path)
        logger.debug("Created high-quality icon from existing file: %s", icon_path)
    else:
        icon = QIcon()
        logger.debug("Created empty icon for non-existent file: %s", icon_path)

    # Замеряем время загрузки и записываем успешную загрузку с диска
    load_time = time.time() - start_time
    record_disk_load()

    # Кэшируем результат с отметкой negative для отсутствующих файлов
    set_icon(cache_key, "__abs__", icon, negative=not exists)

    # Логируем медленные операции
    if load_time > 0.1:  # Если загрузка заняла более 100 мс, логируем на уровне INFO
        logger.info(
            "Slow disk load: absolute path icon '%s' took %.2fms",
            icon_path,
            load_time * 1000,
        )
    else:
        logger.debug(
            "Cached icon for absolute path: %s with TTL in %.2fms",
            icon_path,
            load_time * 1000,
        )
    return icon


async def create_icon_from_path_async(icon_path: str) -> QIcon:
    """Асинхронно создать QIcon из пути к файлу с кэшированием."""
    # Используем namespaced ключ чтобы избежать коллизий
    cache_key = f"abspath::{icon_path}"
    # Проверяем кэш - логика TTL уже реализована в cache_manager
    cached_icon = get_icon(cache_key, "__abs__")

    if cached_icon is not None:
        logger.debug("Cache HIT for absolute path icon: %s", icon_path)
        return cached_icon
    logger.debug("Cache MISS for absolute path icon: %s", icon_path)

    # Замеряем время загрузки
    start_time = time.time()

    # Асинхронно создаем новую иконку
    loop = asyncio.get_event_loop()

    def create_icon():
        if Path(icon_path).exists():
            return QIcon(icon_path)
        else:
            logger.debug("Created empty icon for non-existent file: %s", icon_path)
            return QIcon()

    icon = await loop.run_in_executor(None, create_icon)

    # Замеряем время загрузки и записываем успешную загрузку с диска
    load_time = time.time() - start_time
    record_disk_load()

    # Кэшируем результат с отметкой negative для отсутствующих файлов
    set_icon(cache_key, "__abs__", icon, negative=not Path(icon_path).exists())

    # Логируем медленные операции
    if load_time > 0.1:
        logger.info(
            "Slow async disk load: absolute path icon '%s' took %.2fms",
            icon_path,
            load_time * 1000,
        )
    else:
        logger.debug(
            "Cached icon for absolute path: %s with TTL async in %.2fms",
            icon_path,
            load_time * 1000,
        )
    return icon


def _create_icon_from_path_deferred(icon_path: str) -> QIcon:
    """Отложенная версия create_icon_from_path для выполнения в GUI-потоке."""
    # Используем namespaced ключ чтобы избежать коллизий
    cache_key = f"abspath::{icon_path}"
    # Проверяем кэш - логика TTL уже реализована в cache_manager
    cached_icon = get_icon(cache_key, "__abs__")

    if cached_icon is not None:
        logger.debug("Cache HIT for absolute path icon: %s", icon_path)
        return cached_icon
    logger.debug("Cache MISS for absolute path icon: %s", icon_path)

    # Замеряем время загрузки
    start_time = time.time()

    # Создаем новую иконку
    exists = Path(icon_path).exists()
    if exists:
        icon = QIcon(icon_path)
    else:
        logger.warning("Icon file not found: %s", icon_path)
        icon = QIcon()  # Возвращаем пустую иконку если файл не найден

    # Замеряем время загрузки и записываем успешную загрузку с диска
    load_time = time.time() - start_time
    record_disk_load()

    # Кэшируем результат с отметкой negative для отсутствующих файлов
    set_icon(cache_key, "__abs__", icon, negative=not exists)

    # Логируем медленные операции
    if load_time > 0.1:  # Если загрузка заняла более 100 мс, логируем на уровне INFO
        logger.info(
            "Slow disk load: absolute path icon '%s' took %.2fms",
            icon_path,
            load_time * 1000,
        )
    else:
        logger.debug(
            "Cached icon for absolute path: %s with TTL in %.2fms",
            icon_path,
            load_time * 1000,
        )
    return icon
