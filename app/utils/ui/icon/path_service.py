# path_service.py
"""Централизованный сервис путей для иконок и ресурсов."""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Any, Optional, Tuple

from app.config_data import app_config

from .cache_manager import get_path, set_path
from .negative_cache import negative_cache
from .metrics import CacheMetrics
from .validation import (
    _validate_icon_name,
    is_valid_icon_file,
    validate_theme,
)

logger = logging.getLogger(__name__)


# Негативный кеш перенесён в unified модуль negative_cache

# Индекс иконок по темам: theme -> {lower_name: Path}
_THEME_ICON_INDEX: dict[str, dict[str, Path]] = {}
_INDEX_LOCK = threading.Lock()
_INDEX_TTL: float = 60.0
_THEME_INDEX_TS: dict[str, float] = {}
_THEME_DIR_MTIME: dict[str, float] = {}

# --- Метрики ---
_ICON_METRICS = CacheMetrics()
_METRICS_LAST_LOG: float = 0.0


def _maybe_log_metrics() -> None:
    global _METRICS_LAST_LOG
    # Получаем интервал логирования метрик с узкой обработкой ошибок
    try:
        raw_interval = getattr(app_config, "icon_metrics_report_interval_s", 60.0)
    except AttributeError:
        raw_interval = 60.0
    except Exception:
        logger.exception("_maybe_log_metrics: неожиданная ошибка доступа к app_config.icon_metrics_report_interval_s")
        raw_interval = 60.0
    try:
        interval = float(raw_interval)
    except (TypeError, ValueError):
        interval = 60.0
    except Exception:
        logger.exception("_maybe_log_metrics: неожиданная ошибка преобразования интервала в float")
        interval = 60.0
    now = time.time()
    if now - _METRICS_LAST_LOG >= interval:
        try:
            stats = _ICON_METRICS.get_stats()
            # Используем безопасный доступ к ключам, чтобы не падать по KeyError
            logger.info(
                "Icon metrics: hits=%s misses=%s hit_rate=%s disk_loads=%s not_found=%s avg_load_time=%s load_count=%s uptime=%s",
                stats.get("hits"),
                stats.get("misses"),
                stats.get("hit_rate"),
                stats.get("disk_loads"),
                stats.get("not_found"),
                stats.get("avg_load_time"),
                stats.get("load_count"),
                stats.get("uptime"),
            )
        except (AttributeError, TypeError, ValueError):
            logger.exception("_maybe_log_metrics: некорректный формат статистики метрик")
        except Exception:
            logger.exception("_maybe_log_metrics: неожиданная ошибка при логировании метрик")
        _METRICS_LAST_LOG = now


def _build_theme_index(theme: str) -> None:
    """Построить индекс иконок для темы.
    Кладёт только валидные файлы. Никаких побочных эффектов.
    """
    ui_dir = _icon_path_service.get_ui_icons_dir()
    theme_dir = ui_dir / theme
    mapping: dict[str, Path] = {}
    try:
        if theme_dir.is_dir():
            for p in theme_dir.iterdir():
                if p.is_file() and is_valid_icon_file(p):
                    mapping[p.name.lower()] = p
    except (OSError, PermissionError) as exc:
        logger.debug("Index build failed for theme %s due to filesystem error: %s", theme, exc)
        mapping = {}
    except Exception:
        logger.exception("_build_theme_index: неожиданная ошибка при обходе директории темы '%s'", theme)
        mapping = {}
    # Получаем mtime директории темы (если есть)
    try:
        dir_mtime = theme_dir.stat().st_mtime if theme_dir.is_dir() else 0.0
    except (OSError, PermissionError):
        dir_mtime = 0.0
    except Exception:
        logger.exception("_build_theme_index: неожиданная ошибка получения mtime для темы '%s'", theme)
        dir_mtime = 0.0
    with _INDEX_LOCK:
        _THEME_ICON_INDEX[theme] = mapping
        _THEME_INDEX_TS[theme] = time.time()
        _THEME_DIR_MTIME[theme] = dir_mtime


def _get_indexed_icon(theme: str, icon_name: str) -> Optional[Path]:
    """Вернуть Path из индекса или None. Создаёт/обновляет индекс по TTL."""
    name_key = icon_name.lower()
    ts = _THEME_INDEX_TS.get(theme, 0.0)
    index_ttl = getattr(app_config, "icon_index_ttl", _INDEX_TTL)
    # Проверяем изменение содержимого директории темы по mtime
    ui_dir = _icon_path_service.get_ui_icons_dir()
    theme_dir = ui_dir / theme
    try:
        current_mtime = theme_dir.stat().st_mtime if theme_dir.is_dir() else 0.0
    except Exception:  # noqa: BLE001
        current_mtime = 0.0
    stored_mtime = _THEME_DIR_MTIME.get(theme, -1.0)
    if (
        (time.time() - ts) > index_ttl
        or theme not in _THEME_ICON_INDEX
        or current_mtime != stored_mtime
    ):
        _build_theme_index(theme)
    with _INDEX_LOCK:
        mapping = _THEME_ICON_INDEX.get(theme, {})
        return mapping.get(name_key)


class IconPathService:
    """Singleton-сервис для управления путями к иконкам и ресурсам."""

    _instance: Optional["IconPathService"] = None

    def __new__(cls) -> "IconPathService":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if getattr(self, "_initialized", False):
            return
        self._initialized = True

        self._user_icons_dir: Optional[Path] = None
        self._ui_icons_dir: Optional[Path] = None
        self._user_data_dir: Optional[Path] = None

    # --- Папки пользователя и UI ---

    def get_user_icons_dir(self) -> Path:
        """Путь к папке пользовательских иконок (делегирует в PathConfig)."""
        if self._user_icons_dir is None:
            # Единый источник истины — PathConfig
            self._user_icons_dir = app_config.paths.get_link_icons_dir()
        return self._user_icons_dir

    def ensure_user_icons_dir(self) -> Path:
        """Создать папку пользовательских иконок (делегирует в PathConfig)."""
        app_config.paths.ensure_user_data_dirs()
        return self.get_user_icons_dir()

    def get_user_icon_path(self, filename: str) -> Path:
        """Полный путь к пользовательской иконке."""
        return self.get_user_icons_dir() / filename

    def get_ui_icons_dir(self) -> Path:
        """Путь к каталогу UI-иконок (делегирует в PathConfig)."""
        if self._ui_icons_dir is None:
            self._ui_icons_dir = app_config.paths.get_ui_icons_dir()
        return self._ui_icons_dir

    # --- Вспомогательные адреса ---

    def get_themed_icon_path(self, icon_name: str, theme: str = "light") -> Path:
        """Путь к иконке в указанной теме (без проверки существования)."""
        return self.get_ui_icons_dir() / theme / icon_name

    def get_ui_icon_path(self, icon_name: str, theme: str = "light") -> Optional[Path]:
        """Путь к существующей UI-иконке с fallback на light."""
        themed_path = self.get_themed_icon_path(icon_name, theme)
        if themed_path.exists():
            return themed_path

        if theme != "light":
            light_path = self.get_themed_icon_path(icon_name, "light")
            if light_path.exists():
                return light_path

        return None

    def get_web_icon_path(self, domain: str) -> Path:
        """Путь к пользовательской иконке сайта (кеш favicons)."""
        filename = f"web_{domain.replace('.', '_')}.png"
        return self.get_user_icon_path(filename)

    def get_favicon_cache_path(self) -> Path:
        """Путь к файлу кеша favicon."""
        return self.get_user_icon_path("favicon_cache.db")

    def get_folder_icon_path(self) -> Path:
        """Путь к иконке папки (предупреждает, если файла нет)."""
        folder_icon = self.get_ui_icons_dir() / "folder_icon.png"
        if not folder_icon.exists():
            logger.warning("Folder icon file does not exist: %s", folder_icon)
        return folder_icon

    # --- Директории приложения / ресурсов ---

    def _get_user_data_dir(self) -> Path:
        """Папка пользовательских данных (делегирует в PathConfig)."""
        if self._user_data_dir is None:
            self._user_data_dir = app_config.paths.get_user_data_dir()
        return self._user_data_dir

    def clear_cache(self) -> None:
        """Сбросить внутренние кеши путей."""
        self._user_icons_dir = None
        self._ui_icons_dir = None
        self._user_data_dir = None
        logger.debug("Icon path service caches cleared")


# --- Глобальный экземпляр и удобные прокси-функции ---

_icon_path_service = IconPathService()


# --- Разделение обязанностей: Resolver для кеша/поиска/конвертации ---


class IconPathResolver:
    """Отвечает за этапы: кеш/негативный кеш/метрики, поиск по индексам тем, конвертацию SVG→PNG.

    Методы:
    - resolve_from_cache: валидация имени, негативный кеш, hits/misses в кэше путей.
      Возвращает (path_or_none, terminal). Если terminal=True — результат окончательный.
    - find_source: быстрый поиск файлов иконок по индексам тем (с fallback на light).
    - convert_svg: попытка сконвертировать SVG в PNG (в теме и/или из light).
    """

    def __init__(self, service: IconPathService) -> None:
        self.service = service

    # --- Управление кешем и статистикой ---
    def resolve_from_cache(self, icon_name: str, theme: str) -> Tuple[Optional[str], bool]:
        if not _validate_icon_name(icon_name):
            logger.warning("Invalid icon name provided: %r", icon_name)
            set_path(icon_name, theme, None)  # негативное кеширование
            try:
                _ICON_METRICS.record_not_found()
                _ICON_METRICS.record_miss_without_increment(0.0)
            finally:
                _maybe_log_metrics()
            return None, True

        norm_theme = validate_theme(theme)
        key = f"{norm_theme}:{icon_name.lower()}"

        # быстрый негативный кеш (единый модуль)
        if negative_cache.is_negative(key):
            logger.debug("Negative cache HIT: %s", key)
            try:
                _ICON_METRICS.record_not_found()
                _ICON_METRICS.record_miss_without_increment(0.0)
            finally:
                _maybe_log_metrics()
            return None, True

        cached = get_path(icon_name, norm_theme)
        if cached is not None:
            logger.debug("Path cache HIT: %s (%s)", icon_name, norm_theme)
            try:
                _ICON_METRICS.record_hit()
            finally:
                _maybe_log_metrics()
            return cached, True

        logger.debug("Path cache MISS: %s (%s)", icon_name, norm_theme)
        return None, False

    # --- Поиск пути по индексу/темам ---
    def find_source(self, icon_name: str, theme: str) -> Optional[str]:
        norm_theme = validate_theme(theme)
        idx_hit = _get_indexed_icon(norm_theme, icon_name)
        if idx_hit is not None:
            path_str = str(idx_hit)
            set_path(icon_name, norm_theme, path_str)
            try:
                _ICON_METRICS.record_disk_load()
            finally:
                _maybe_log_metrics()
            return path_str

        if norm_theme != "light":
            light_idx = _get_indexed_icon("light", icon_name)
            if light_idx is not None:
                path_str = str(light_idx)
                set_path(icon_name, norm_theme, path_str)
                try:
                    _ICON_METRICS.record_disk_load()
                finally:
                    _maybe_log_metrics()
                return path_str
        return None

    # --- Конвертация иконок ---
    def convert_svg(self, icon_name: str, theme: str) -> Optional[str]:
        # Локальный импорт для избежания циклических зависимостей
        from .icon_operations.converters import convert_icon_to_png_128

        norm_theme = validate_theme(theme)
        ui_dir = self.service.get_ui_icons_dir()
        themed_path = ui_dir / norm_theme / icon_name

        # themed.svg → themed.png
        themed_svg = themed_path.with_suffix(".svg")
        if themed_svg.is_file() and is_valid_icon_file(themed_svg):
            themed_png = themed_path.with_suffix(".png")
            if themed_png.is_file():
                try:
                    if themed_png.stat().st_mtime >= themed_svg.stat().st_mtime:
                        path_str = str(themed_png)
                        set_path(icon_name, norm_theme, path_str)
                        logger.debug("Using up-to-date PNG: %s", themed_png)
                        try:
                            _ICON_METRICS.record_disk_load()
                        finally:
                            _maybe_log_metrics()
                        return path_str
                except Exception:  # noqa: BLE001
                    pass
            slow_ms = float(getattr(app_config, "icon_slow_convert_threshold_ms", 150.0))
            t0 = time.perf_counter()
            if convert_icon_to_png_128(str(themed_svg), str(themed_png)):
                dt_ms = (time.perf_counter() - t0) * 1000.0
                path_str = str(themed_png)
                set_path(icon_name, norm_theme, path_str)
                if dt_ms >= slow_ms:
                    logger.warning(
                        "Slow icon convert (%.1f ms): %s → %s",
                        dt_ms,
                        themed_svg,
                        themed_png,
                    )
                else:
                    logger.debug(
                        "Converted SVG to PNG (%.1f ms): %s → %s",
                        dt_ms,
                        themed_svg,
                        themed_png,
                    )
                try:
                    _ICON_METRICS.record_disk_load()
                    _ICON_METRICS.record_miss_without_increment(dt_ms / 1000.0)
                finally:
                    _maybe_log_metrics()
                return path_str

        # light.svg → themed.png
        if norm_theme != "light":
            light_svg = (ui_dir / "light" / icon_name).with_suffix(".svg")
            if light_svg.is_file() and is_valid_icon_file(light_svg):
                themed_png = themed_path.with_suffix(".png")
                if themed_png.is_file():
                    try:
                        if themed_png.stat().st_mtime >= light_svg.stat().st_mtime:
                            path_str = str(themed_png)
                            set_path(icon_name, norm_theme, path_str)
                            logger.debug(
                                "Using up-to-date PNG (from light SVG): %s", themed_png
                            )
                            try:
                                _ICON_METRICS.record_disk_load()
                            finally:
                                _maybe_log_metrics()
                            return path_str
                    except Exception:  # noqa: BLE001
                        pass
                slow_ms = float(
                    getattr(app_config, "icon_slow_convert_threshold_ms", 150.0)
                )
                t0 = time.perf_counter()
                if convert_icon_to_png_128(str(light_svg), str(themed_png)):
                    dt_ms = (time.perf_counter() - t0) * 1000.0
                    path_str = str(themed_png)
                    set_path(icon_name, norm_theme, path_str)
                    if dt_ms >= slow_ms:
                        logger.warning(
                            "Slow icon convert (fallback, %.1f ms): %s → %s",
                            dt_ms,
                            light_svg,
                            themed_png,
                        )
                    else:
                        logger.debug(
                            "Converted fallback SVG to PNG (%.1f ms): %s → %s",
                            dt_ms,
                            light_svg,
                            themed_png,
                        )
                    try:
                        _ICON_METRICS.record_disk_load()
                        _ICON_METRICS.record_miss_without_increment(dt_ms / 1000.0)
                    finally:
                        _maybe_log_metrics()
                    return path_str
        return None


# --- Поиск и кеширование пути к иконке ---


def get_icon_path(icon_name: str, theme: str = "light") -> Optional[str]:
    """Получить строковый путь к иконке. Тонкая обёртка вокруг IconPathResolver."""
    resolver = IconPathResolver(_icon_path_service)

    # 1) кеш/негативный кеш/валидация/метрики
    cached_or_none, terminal = resolver.resolve_from_cache(icon_name, theme)
    if terminal:
        return cached_or_none

    # 2) поиск по индексам тем
    found = resolver.find_source(icon_name, theme)
    if found is not None:
        return found

    # 3) конвертация SVG→PNG
    converted = resolver.convert_svg(icon_name, theme)
    if converted is not None:
        return converted

    # 4) негативное кеширование при полном отсутстви
    norm_theme = validate_theme(theme)
    key = f"{norm_theme}:{icon_name.lower()}"
    set_path(icon_name, norm_theme, None)
    negative_cache.mark_negative(key)
    logger.debug("Icon path not found, cached negative: %s (%s)", icon_name, norm_theme)
    try:
        _ICON_METRICS.record_not_found()
        _ICON_METRICS.record_actual_miss(0.0)
    finally:
        _maybe_log_metrics()
    return None


def get_qss_dir() -> Path:
    """Путь к директории QSS-тем."""
    return app_config.paths.get_qss_dir()

_CURRENT_THEME_CACHE: Optional[str] = None
_LAST_THEME_CHECK: float = 0.0
_THEME_CACHE_TTL: float = 3.0


def get_current_theme() -> str:
    """Получить текущую тему с кешем, при недоступности вернуть 'light'."""
    import time

    global _CURRENT_THEME_CACHE, _LAST_THEME_CHECK

    now = time.time()
    if (
        _CURRENT_THEME_CACHE is not None
        and (now - _LAST_THEME_CHECK) < _THEME_CACHE_TTL
    ):
        return _CURRENT_THEME_CACHE

    try:
        from PyQt6.QtWidgets import QApplication  # локальный импорт

        app = QApplication.instance()
        if app:
            for widget in app.topLevelWidgets():
                # ожидаем наличие settings.get_theme()
                settings = getattr(widget, "settings", None)
                if settings and hasattr(settings, "get_theme"):
                    theme = validate_theme(settings.get_theme())
                    _CURRENT_THEME_CACHE = theme
                    _LAST_THEME_CHECK = now
                    return theme
    except Exception as exc:  # noqa: BLE001
        logger.debug("Could not get current theme from GUI: %s", exc)

    _CURRENT_THEME_CACHE = "light"
    _LAST_THEME_CHECK = now
    return "light"


# Экспорт глобального сервиса
icon_path_service = _icon_path_service


# --- Публичные хелперы метрик ---
def get_icon_metrics_stats() -> dict[str, Any]:
    """Вернуть текущую сводку метрик подсистемы иконок."""
    return _ICON_METRICS.get_stats()


def reset_icon_metrics() -> None:
    """Сбросить метрики подсистемы иконок."""
    _ICON_METRICS.reset()


# --- Вспомогательные функции записи метрик для других модулей ---
def metrics_record_hit() -> None:
    try:
        _ICON_METRICS.record_hit()
    finally:
        _maybe_log_metrics()


def metrics_record_disk_load(duration_s: float = 0.0) -> None:
    try:
        _ICON_METRICS.record_disk_load()
        if duration_s and duration_s > 0:
            _ICON_METRICS.record_miss_without_increment(duration_s)
    finally:
        _maybe_log_metrics()


def metrics_record_not_found(duration_s: float = 0.0) -> None:
    try:
        _ICON_METRICS.record_not_found()
        _ICON_METRICS.record_actual_miss(duration_s if duration_s > 0 else 0.0)
    finally:
        _maybe_log_metrics()


def metrics_record_miss(duration_s: float = 0.0) -> None:
    try:
        _ICON_METRICS.record_actual_miss(duration_s if duration_s > 0 else 0.0)
    finally:
        _maybe_log_metrics()
