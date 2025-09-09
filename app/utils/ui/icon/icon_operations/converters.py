# converters.py
"""Функции конвертации иконок с async поддержкой для I/O операций."""

from __future__ import annotations

import asyncio
import logging
import shutil
from pathlib import Path

from PIL import Image
from PIL.Image import Resampling
from PyQt6.QtCore import QBuffer, QByteArray, QIODevice, QRectF, QSize
from PyQt6.QtGui import QImage, QPainter
from PyQt6.QtSvg import QSvgRenderer

from ..validation import InvalidIconError, is_valid_icon_file

logger = logging.getLogger(__name__)


def _resize_image(img: Image.Image, size: int) -> Image.Image:
    """Вспомогательная функция для ресайза изображений с высоким качеством."""
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    return img.resize((size, size), Resampling.LANCZOS)


# === СИНХРОННЫЕ ФУНКЦИИ КОПИРОВАНИЯ ===


def _calculate_file_hash(file_path: Path) -> str:
    """Вычисляет SHA-256 хеш файла для проверки дублирования."""
    import hashlib

    hash_sha256 = hashlib.sha256()
    try:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_sha256.update(chunk)
        return hash_sha256.hexdigest()[
            :16
        ]  # Используем первые 16 символов для краткости
    except (OSError, IOError) as exc:
        logger.warning("Failed to calculate hash for %s: %s", file_path, exc)
        return ""


def _find_existing_icon_by_content(src_path: Path, dest_dir: Path) -> str | None:
    """Ищет существующую иконку с таким же содержимым в целевой директории."""
    if not dest_dir.exists():
        return None

    src_hash = _calculate_file_hash(src_path)
    if not src_hash:
        return None

    # Проверяем все файлы в директории пользовательских иконок
    for existing_file in dest_dir.iterdir():
        if existing_file.is_file() and existing_file.suffix.lower() in {
            ".png",
            ".ico",
            ".svg",
            ".jpg",
            ".jpeg",
        }:
            if _calculate_file_hash(existing_file) == src_hash:
                logger.debug(
                    "Found existing icon with same content: %s", existing_file.name
                )
                return existing_file.name

    return None


def copy_icon_smart(
    src_path: str, dest_dir: Path, avoid_duplicates: bool = True
) -> str:
    """Умное копирование иконки с проверкой дублирования по содержимому.

    Args:
        src_path: Путь к исходной иконке
        dest_dir: Директория назначения
        avoid_duplicates: Если True, проверяет существующие файлы по содержимому

    Returns:
        str: Имя файла в директории назначения
    """
    if not is_valid_icon_file(src_path):
        raise InvalidIconError(
            f"Невозможно скопировать невалидный файл иконки: {src_path}"
        )

    # Создаем директорию если она не существует
    dest_dir.mkdir(parents=True, exist_ok=True)

    src_path_obj = Path(src_path)

    # Проверяем дублирование по содержимому
    if avoid_duplicates:
        existing_icon = _find_existing_icon_by_content(src_path_obj, dest_dir)
        if existing_icon:
            logger.debug("Reusing existing icon: %s", existing_icon)
            return existing_icon

    # Если файл с таким именем уже существует, генерируем уникальное имя
    dst = dest_dir / src_path_obj.name
    if dst.exists():
        # Генерируем уникальное имя с суффиксом
        base_name = src_path_obj.stem
        extension = src_path_obj.suffix
        counter = 1
        while dst.exists():
            dst = dest_dir / f"{base_name}_{counter}{extension}"
            counter += 1

    try:
        shutil.copyfile(src_path_obj, dst)
        logger.debug("Copied icon to: %s", dst.name)
    except (OSError, IOError) as exc:
        raise InvalidIconError(f"Ошибка копирования файла: {exc}") from exc

    # Автоматическая конвертация SVG в PNG при копировании
    if src_path_obj.suffix.lower() == ".svg":
        png_dst = dest_dir / (dst.stem + ".png")
        if not png_dst.exists():
            # Конвертируем SVG в PNG размером 128x128
            if not convert_icon_to_png_128(str(dst), str(png_dst)):
                logger.warning("Failed to convert SVG to PNG: %s -> %s", dst, png_dst)
                # Если конвертация не удалась, возвращаем оригинальный SVG файл
                return dst.name
        # Возвращаем имя PNG файла для SVG
        return png_dst.name

    return dst.name


def copy_icon(src_path: str, dest_dir: Path) -> str:
    """Копировать иконку в директорию (обратная совместимость).

    Использует умное копирование с проверкой дублирования.
    """
    return copy_icon_smart(src_path, dest_dir, avoid_duplicates=True)


def copy_icon_to_path(src_path: str, dst_path: str) -> bool:
    """Копировать иконку из одного пути в другой.

    Args:
        src_path: Путь к исходной иконке
        dst_path: Путь к целевой иконке

    Returns:
        bool: True если копирование успешно, False в противном случае.
    """
    try:
        # Создаем родительскую директорию если она не существует
        dst_path_obj = Path(dst_path)
        dst_path_obj.parent.mkdir(parents=True, exist_ok=True)

        shutil.copy2(src_path, dst_path)
        logger.debug("Successfully copied icon from %s to %s", src_path, dst_path)
        return True
    except (OSError, IOError, shutil.Error) as exc:
        logger.error("Error copying icon from %s to %s: %s", src_path, dst_path, exc)
        return False
    except Exception as exc:
        logger.error(
            "Unexpected error copying icon from %s to %s: %s", src_path, dst_path, exc
        )
        return False


# === АСИНХРОННЫЕ ФУНКЦИИ КОПИРОВАНИЯ ===


async def copy_icon_async(src_path: str, dest_dir: Path) -> str:
    """Асинхронно копировать иконку в директорию."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, copy_icon, src_path, dest_dir)


async def copy_icon_to_path_async(src_path: str, dst_path: str) -> bool:
    """Асинхронно копировать иконку из одного пути в другой."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, copy_icon_to_path, src_path, dst_path)


# === СИНХРОННЫЕ ФУНКЦИИ КОНВЕРТАЦИИ ===


def convert_icon_to_png_128(src_path: str, dst_path: str, size: int = 128) -> bool:
    """Конвертировать иконку в PNG заданного размера (по умолчанию 128x128).

    Note:
        Эта функция работает с QImage и QPainter вне GUI-потока, что допустимо
        для операций рендеринга в QImage. Это отличается от создания QPixmap/QIcon,
        которые должны создаваться только в GUI-потоке.
    """
    try:
        src_path_obj = Path(src_path)
        ext = src_path_obj.suffix.lower()

        if ext == ".svg":
            # SVG → QImage → PNG (допустимо вне GUI-потока)
            with open(src_path, "rb") as f:
                svg_data = f.read()

            logger.debug("Creating QSvgRenderer for %s", src_path)
            renderer = QSvgRenderer(QByteArray(svg_data))
            logger.debug("QSvgRenderer isValid: %s", renderer.isValid())
            if not renderer.isValid():
                logger.error("Invalid SVG file: %s", src_path)
                return False

            # Создаем изображение с нужным размером и высоким качеством
            image = QImage(QSize(size, size), QImage.Format.Format_ARGB32_Premultiplied)
            image.fill(0)

            logger.debug("Created QImage with size %dx%d", size, size)
            painter = QPainter()

            if not painter.begin(image):
                logger.error("Failed to initialize QPainter")
                return False

            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

            try:
                # Рендерим SVG в изображение нужного размера
                logger.debug("Rendering SVG to image with size %dx%d", size, size)
                result = renderer.render(painter, QRectF(0, 0, size, size))
                logger.debug("SVG rendering result: %s", result)
            finally:
                painter.end()

            # Сохраняем изображение в буфер с высоким качеством
            buffer = QBuffer()
            buffer.open(QIODevice.OpenModeFlag.WriteOnly)

            # Используем максимальное качество PNG
            logger.debug("Saving image to buffer")
            if not image.save(buffer, "PNG", 100):
                logger.error("Failed to save image to buffer")
                return False

            # Создаем родительскую директорию если она не существует
            dst_path_obj = Path(dst_path)
            dst_path_obj.parent.mkdir(parents=True, exist_ok=True)

            # Записываем данные в файл
            logger.debug("Writing image data to %s", dst_path)
            with open(dst_path, "wb") as out:
                out.write(bytes(buffer.data()))
            logger.debug("Successfully converted SVG to PNG: %s", dst_path)
            return True

        # Любой другой формат через PIL
        dst_path_obj = Path(dst_path)
        dst_path_obj.parent.mkdir(parents=True, exist_ok=True)

        with Image.open(src_path) as img:
            img = _resize_image(img, size)
            img.save(dst_path, format="PNG")
        return True

    except (OSError, IOError, ValueError) as exc:
        logger.error("Error converting icon %s: %s", src_path, exc)
        return False
    except Exception as exc:
        logger.error("Unexpected error converting icon %s: %s", src_path, exc)
        return False


def convert_icon_to_png_32(src_path: str, dst_path: str, size: int = 32) -> bool:
    """Конвертировать иконку в PNG заданного размера (по умолчанию 32x32).

    Note:
        Это устаревшая функция для обратной совместимости.
        Используйте convert_icon_to_png_128.
    """
    return convert_icon_to_png_128(src_path, dst_path, size=size)


def convert_raster_icon_to_png(src_path: str, dst_path: str, size: int = 32) -> bool:
    """Конвертировать растровую иконку в PNG заданного размера (по умолчанию 32x32).

    Args:
        src_path: Путь к исходной иконке.
        dst_path: Путь к целевой иконке (должен заканчиваться на .png).
        size: Размер иконки (по умолчанию 32).

    Returns:
        bool: True если конвертация успешна, False в противном случае.
    """
    try:
        with Image.open(src_path) as img:
            # Ресайзим изображение
            img = _resize_image(img, size)

            # Создаем родительскую директорию если она не существует
            dst_path_obj = Path(dst_path)
            dst_path_obj.parent.mkdir(parents=True, exist_ok=True)

            # Сохраняем в PNG
            img.save(dst_path, "PNG")

        logger.debug(
            "Successfully converted raster icon from %s to %s", src_path, dst_path
        )
        return True
    except (OSError, IOError, ValueError) as exc:
        logger.error(
            "Error converting raster icon from %s to %s: %s", src_path, dst_path, exc
        )
        return False
    except Exception as exc:
        logger.error(
            "Unexpected error converting raster icon from %s to %s: %s",
            src_path,
            dst_path,
            exc,
        )
        return False


# === АСИНХРОННЫЕ ФУНКЦИИ КОНВЕРТАЦИИ ===


async def convert_icon_to_png_128_async(
    src_path: str, dst_path: str, size: int = 128
) -> bool:
    """Асинхронно конвертировать иконку в PNG заданного размера."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, convert_icon_to_png_128, src_path, dst_path, size
    )


async def convert_icon_to_png_32_async(
    src_path: str, dst_path: str, size: int = 32
) -> bool:
    """Асинхронно конвертировать иконку в PNG 32x32."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, convert_icon_to_png_32, src_path, dst_path, size
    )


async def convert_raster_icon_to_png_async(
    src_path: str, dst_path: str, size: int = 32
) -> bool:
    """Асинхронно конвертировать растровую иконку в PNG."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, convert_raster_icon_to_png, src_path, dst_path, size
    )


# === ПАКЕТНАЯ КОНВЕРТАЦИЯ ===


async def batch_convert_icons_async(
    conversions: list[tuple[str, str, int]], max_concurrent: int = 5
) -> dict[str, bool]:
    """Пакетная асинхронная конвертация иконок.

    Args:
        conversions: Список кортежей (src_path, dst_path, size)
        max_concurrent: Максимальное количество одновременных конвертаций

    Returns:
        dict: Словарь {src_path: success_status}
    """
    # Очередь задач, чтобы не создавать все корутины сразу
    queue: asyncio.Queue[tuple[str, str, int]] = asyncio.Queue()
    result_dict: dict[str, bool] = {}

    # Предзаполняем очередь входными заданиями
    for item in conversions:
        try:
            src_path, dst_path, size = item
        except Exception:  # защита от неправильного входа
            logger.error("Invalid conversion tuple: %s", item)
            continue
        queue.put_nowait((src_path, dst_path, size))

    async def worker(worker_id: int) -> None:
        while True:
            try:
                src_path, dst_path, size = await queue.get()
            except asyncio.CancelledError:
                break
            try:
                success = await convert_icon_to_png_128_async(src_path, dst_path, size)
                result_dict[src_path] = success
            except Exception as e:
                logger.error("Batch conversion error for %s: %s", src_path, e)
                result_dict[src_path] = False
            finally:
                queue.task_done()

    # Поднимаем ограниченное число воркеров
    workers = [
        asyncio.create_task(worker(i)) for i in range(max(1, int(max_concurrent)))
    ]

    # Ждём завершения всех задач в очереди
    await queue.join()

    # Останавливаем воркеров
    for w in workers:
        w.cancel()
    await asyncio.gather(*workers, return_exceptions=True)

    successful = sum(1 for success in result_dict.values() if success)
    logger.info(
        f"Batch conversion completed: {successful}/{len(conversions)} successful"
    )

    return result_dict
