# test_icon_thread_safety.py
"""Тесты потокобезопасности модуля app.utils.ui.icon.

Проверяет:
- Создание QIcon только в GUI-потоке
- Корректную работу async функций
- Защиту от вызовов из фоновых потоков
"""

from __future__ import annotations

import threading
from pathlib import Path

import pytest
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

from app.utils.ui.icon.cache_manager import get_cached_category_icon
from app.utils.ui.icon.icon_operations.creators import (
    create_icon_from_path,
    create_icon_from_path_async,
    themed_icon,
)
from app.utils.ui.icon.selection import choose_icon_and_copy


class TestThreadSafety:
    """Проверка создания QIcon только в GUI-потоке."""

    def test_themed_icon_from_gui_thread_works(self, qapp):
        """themed_icon из GUI-потока должен работать корректно."""
        # Вызов из GUI-потока (текущий поток в pytest-qt)
        icon = themed_icon("test.svg", "light", "test")
        assert isinstance(icon, QIcon)

    def test_themed_icon_from_worker_thread_raises(self, qapp):
        """themed_icon из фонового потока должен выбрасывать RuntimeError."""
        exception_caught = []
        
        def worker():
            try:
                themed_icon("add.svg", "light")
            except RuntimeError as e:
                exception_caught.append(str(e))
        
        thread = threading.Thread(target=worker)
        thread.start()
        thread.join()
        
        assert len(exception_caught) == 1
        assert "non-GUI thread" in exception_caught[0]

    def test_create_icon_from_path_from_gui_thread(self, qapp, tmp_path):
        """create_icon_from_path из GUI-потока должен работать."""
        icon_file = tmp_path / "test.png"
        icon_file.write_bytes(
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
            b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
        )

        icon = create_icon_from_path(str(icon_file))
        assert isinstance(icon, QIcon)

    def test_create_icon_from_path_from_worker_thread_raises(
        self, qapp, tmp_path
    ):
        """create_icon_from_path из фонового потока должен выбрасывать RuntimeError."""
        icon_file = tmp_path / "test.png"
        icon_file.write_bytes(
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
            b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
        )

        exception_caught = []

        def worker():
            try:
                create_icon_from_path(str(icon_file))
            except RuntimeError as e:
                exception_caught.append(str(e))

        thread = threading.Thread(target=worker)
        thread.start()
        thread.join()

        assert len(exception_caught) == 1
        assert "non-GUI thread" in exception_caught[0]

    def test_choose_icon_and_copy_from_worker_raises(self, qapp, tmp_path):
        """choose_icon_and_copy из фонового потока должен выбросить RuntimeError."""
        exception_caught = []

        def worker():
            try:
                choose_icon_and_copy(None, tmp_path)
            except RuntimeError as e:
                if "must be called from GUI thread" in str(e):
                    exception_caught.append(True)
                else:
                    exception_caught.append(False)
            except Exception:
                exception_caught.append(False)

        thread = threading.Thread(target=worker)
        thread.start()
        thread.join()

        assert len(exception_caught) == 1
        assert (
            exception_caught[0] is True
        ), "Должно быть выброшено RuntimeError с правильным сообщением"

    def test_get_cached_category_icon_from_gui_thread(self, qapp, tmp_path):
        """get_cached_category_icon из GUI-потока должен работать."""
        icon_file = tmp_path / "category.png"
        icon_file.write_bytes(
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
            b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
        )

        icon = get_cached_category_icon(str(icon_file))
        assert isinstance(icon, QIcon)

    def test_get_cached_category_icon_from_worker_returns_empty(self, qapp, tmp_path):
        """get_cached_category_icon из фонового потока должен вернуть пустую иконку."""
        icon_file = tmp_path / "category.png"
        icon_file.write_bytes(
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
            b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
        )

        result = []

        def worker():
            icon = get_cached_category_icon(str(icon_file))
            result.append(icon.isNull())

        thread = threading.Thread(target=worker)
        thread.start()
        thread.join()

        assert len(result) == 1
        assert result[0] is True


@pytest.mark.asyncio
class TestAsyncIconCreation:
    """Проверка async создания иконок."""

    async def test_create_icon_from_path_async_creates_in_gui_thread(
        self, qapp, tmp_path
    ):
        """create_icon_from_path_async должен создавать QIcon в GUI-потоке."""
        icon_file = tmp_path / "test.png"
        # Создаём минимальный валидный PNG
        icon_file.write_bytes(
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
            b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
        )

        icon = await create_icon_from_path_async(str(icon_file))

        # Проверяем, что иконка создана
        assert isinstance(icon, QIcon)
        # Для валидного PNG иконка не должна быть null
        assert not icon.isNull()

    async def test_create_icon_from_path_async_nonexistent_file(self, qapp, tmp_path):
        """create_icon_from_path_async для несуществующего файла должен вернуть пустую иконку."""
        icon_file = tmp_path / "nonexistent.png"

        icon = await create_icon_from_path_async(str(icon_file))

        assert isinstance(icon, QIcon)
        assert icon.isNull()

    async def test_create_icon_from_path_async_uses_cache(self, qapp, tmp_path):
        """create_icon_from_path_async должен использовать кэш."""
        icon_file = tmp_path / "cached.png"
        icon_file.write_bytes(
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
            b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
        )

        # Первый вызов - загрузка
        icon1 = await create_icon_from_path_async(str(icon_file))
        # Второй вызов - из кэша
        icon2 = await create_icon_from_path_async(str(icon_file))

        assert isinstance(icon1, QIcon)
        assert isinstance(icon2, QIcon)
        # Оба должны быть валидными
        assert not icon1.isNull()
        assert not icon2.isNull()


@pytest.fixture
def qapp():
    """Фикстура для QApplication (pytest-qt)."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app
    # Cleanup не нужен, QApplication singleton
