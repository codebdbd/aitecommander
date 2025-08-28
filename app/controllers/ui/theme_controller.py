import json
import logging
import re
from collections import OrderedDict
from pathlib import Path
from threading import RLock
from typing import Any, Dict, List, Optional, Tuple

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

from app.config_data import app_config
from app.utils.ui.icon.cache_manager import clear_icon_cache

logger = logging.getLogger(__name__)


class ThemeController:
    def __init__(
        self,
        settings,
        main_window=None,
        logger=None,
        stylesheet_applier: Optional[callable] = None,
        gui_scheduler: Optional[callable] = None,
    ):
        """Инициализация контроллера тем."""
        # Deprecated: параметр logger больше не используется; логирование ведётся модульным логгером
        self._deprecated_logger_param = logger
        self.settings = settings
        self.main_window = main_window
        self._qss_cache: OrderedDict[str, str] = OrderedDict()
        self._common_qss: Optional[str] = None
        self._themes: List[Dict[str, Any]] = []
        # Ограничение размера кэша (конфигурируемое)
        try:
            self._max_cache_size = int(getattr(app_config, "qss_cache_size", 10))
        except Exception:
            self._max_cache_size = 10
        # Блокировка для потокобезопасности работы с кэшем
        self._cache_lock = RLock()
        # Инъекция зависимостей для тестируемости
        self._stylesheet_applier = stylesheet_applier  # Callable[[str], None]
        self._gui_scheduler = gui_scheduler  # Callable[[Callable[[], None]], None]

        self._load_themes_manifest()

    def _normalize_theme_input(self, name: Optional[str]) -> str:
        """Нормализует входное имя темы: обрезает пробелы, приводит к нижнему регистру,
        маппит известные синонимы на канонические имена (напр. русские варианты)."""
        if not name:
            return ""
        v = str(name).strip().lower()
        # Небольшая таблица синонимов
        synonyms = {
            "темная": "dark",
            "тёмная": "dark",
            "темный": "dark",
            "тёмный": "dark",
            "dark": "dark",
            "светлая": "light",
            "light": "light",
        }
        return synonyms.get(v, v)

    def _load_themes_manifest(self) -> None:
        """Загружает темы из файла манифеста или использует значения по умолчанию."""
        try:
            manifest_path = app_config.get_themes_manifest_path()
            if manifest_path.exists():
                try:
                    with manifest_path.open("r", encoding="utf-8") as f:
                        data = json.load(f)

                    # Проверяем структуру данных
                    if not isinstance(data, dict):
                        logger.error("Неверный формат манифеста тем: ожидается объект")
                        self._load_default_themes()
                        return

                    themes = data.get("themes", [])
                    if not isinstance(themes, list):
                        logger.error(
                            "Неверный формат тем в манифесте: ожидается массив"
                        )
                        self._load_default_themes()
                        return

                    # Проверяем каждую тему на корректность
                    validated_themes = []
                    seen_names_lc = set()
                    for i, theme in enumerate(themes):
                        if not isinstance(theme, dict):
                            logger.warning(
                                "Пропущена неверная тема #%d: ожидается объект", i
                            )
                            continue
                        # Централизованная валидация конфигурации
                        if not self._validate_theme_config(theme):
                            logger.warning(
                                "Тема #%d не прошла валидацию и будет пропущена", i
                            )
                            continue
                        # Проверяем уникальность имени (без учета регистра)
                        name_lc = str(theme.get("name", "")).lower()
                        if name_lc in seen_names_lc:
                            logger.warning(
                                "Пропущен дубликат темы #%d (%s): имя уже встречалось",
                                i,
                                theme.get("name", "без имени"),
                            )
                            continue
                        seen_names_lc.add(name_lc)
                        validated_themes.append(theme)

                    self._themes = validated_themes
                    logger.info(
                        "Загружено %d тем из манифеста (валидных: %d)",
                        len(themes),
                        len(validated_themes),
                    )
                except json.JSONDecodeError as exc:
                    logger.error("Ошибка декодирования JSON манифеста тем: %s", exc)
                    self._load_default_themes()
                except PermissionError as exc:
                    logger.error("Ошибка доступа к файлу манифеста тем: %s", exc)
                    self._load_default_themes()
                except OSError as exc:
                    logger.error("Ошибка загрузки манифеста тем: %s", exc)
                    self._load_default_themes()
                except Exception as exc:
                    logger.error(
                        "Неожиданная ошибка при загрузке манифеста тем: %s", exc
                    )
                    self._load_default_themes()
            else:
                logger.info(
                    "Манифест тем не найден, используются значения по умолчанию"
                )
                self._load_default_themes()
        except Exception as exc:
            logger.error("Неожиданная ошибка при проверке манифеста тем: %s", exc)
            self._load_default_themes()

    def _load_default_themes(self) -> None:
        """Загружает конфигурацию тем по умолчанию."""
        self._themes = [
            {
                "name": "light",
                "display_name": "Светлая",
                "qss_file": "light.qss",
                "is_dark": False,
            },
            {
                "name": "dark",
                "display_name": "Тёмная",
                "qss_file": "dark.qss",
                "is_dark": True,
            },
        ]

    def _is_safe_filename(self, filename: str) -> bool:
        """Проверяет, является ли имя файла безопасным (предотвращает path traversal)."""
        # Проверяем, что имя файла не содержит опасных символов
        if not filename or re.search(r'[<>:"/\\|?*]', filename):
            return False
        # Проверяем, что путь не содержит подкаталогов
        if ".." in filename or "/" in filename or "\\" in filename:
            return False
        # Проверяем, что расширение файла .qss
        if not filename.endswith(".qss"):
            return False
        return True

    def _manage_cache_size(self) -> None:
        """Управляет размером кэша по политике LRU: удаляет самые старые записи."""
        with self._cache_lock:
            removed = 0
            while len(self._qss_cache) > self._max_cache_size:
                key, _ = self._qss_cache.popitem(last=False)  # удаляем LRU
                removed += 1
            if removed:
                logger.debug("Кэш тем уменьшен по LRU, удалено %d записей", removed)

    def is_dark(self) -> bool:
        """Проверяет, является ли текущая тема тёмной."""
        try:
            current_theme = self.settings.get_theme()
            if not current_theme:
                logger.warning(
                    "Текущая тема не установлена, используется светлая тема по умолчанию"
                )
                return False
            # Нормализуем имя и пытаемся найти конфиг
            norm = self._normalize_theme_input(current_theme)
            theme_config = self._get_theme_by_name(norm)
            if theme_config:
                return theme_config.get("is_dark", False)
            # Если тема не найдена в конфигурации, определяем по нормализованному имени
            return norm == "dark"
        except Exception as exc:
            logger.error("Ошибка при определении темной темы: %s", exc)
            return False

    def _get_theme_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Получает словарь темы по имени (без учета регистра)."""
        if not name:
            return None
        name_lc = str(name).lower()
        return next(
            (
                theme
                for theme in self._themes
                if str(theme.get("name", "")).lower() == name_lc
            ),
            None,
        )

    def available(self) -> List[Tuple[str, str]]:
        """Получает список доступных тем."""
        try:
            if not self._themes:
                logger.warning("Список тем пуст, возвращаются темы по умолчанию")
                return [("light", "Светлая"), ("dark", "Тёмная")]
            result: List[Tuple[str, str]] = []
            for theme in self._themes:
                name = theme.get("name")
                if not name:
                    # Пропускаем некорректные записи
                    logger.warning("Пропущена тема без имени в конфигурации")
                    continue
                display_name = theme.get("display_name")
                if not display_name:
                    # Fallback для известных тем, иначе — красивое представление имени
                    if name == "light":
                        display_name = "Светлая"
                    elif name == "dark":
                        display_name = "Тёмная"
                    else:
                        display_name = str(name).replace("_", " ").title()
                    logger.warning(
                        "Тема '%s' не имеет display_name в манифесте, использовано значение по умолчанию: %s",
                        name,
                        display_name,
                    )
                result.append((name, display_name))
            return result
        except Exception as exc:
            logger.error("Ошибка при получении списка тем: %s", exc)
            # Возвращаем темы по умолчанию в случае ошибки
            return [("light", "Светлая"), ("dark", "Тёмная")]

    def _load_common_qss(self) -> bool:
        """Загружает общие QSS стили."""
        with self._cache_lock:
            if self._common_qss is not None:
                return True
        common_path = app_config.paths.get_qss_dir() / "common.qss"
        if not common_path.exists():
            logger.warning("Файл общих стилей не найден: %s", common_path)
            with self._cache_lock:
                self._common_qss = ""
            return False
        try:
            with common_path.open("r", encoding="utf-8") as f:
                content = f.read()
            with self._cache_lock:
                self._common_qss = content
            logger.debug("Загружены общие стили из %s", common_path)
            return True
        except UnicodeDecodeError as exc:
            logger.error("Ошибка декодирования файла общих стилей: %s", exc)
            with self._cache_lock:
                self._common_qss = ""
            return False
        except PermissionError as exc:
            logger.error("Ошибка доступа к файлу общих стилей: %s", exc)
            with self._cache_lock:
                self._common_qss = ""
            return False
        except OSError as exc:
            logger.error("Ошибка загрузки общих стилей: %s", exc)
            with self._cache_lock:
                self._common_qss = ""
            return False
        except Exception as exc:
            logger.error("Неожиданная ошибка при загрузке общих стилей: %s", exc)
            with self._cache_lock:
                self._common_qss = ""
            return False

    def _load_theme_qss(self, theme_name: str, theme_path: Path) -> Optional[str]:
        """Загружает и кэширует QSS темы."""
        with self._cache_lock:
            if theme_name in self._qss_cache:
                # Помечаем как недавно использованную запись (LRU)
                self._qss_cache.move_to_end(theme_name, last=True)
                return self._qss_cache[theme_name]

        # Управляем размером кэша
        self._manage_cache_size()

        if not theme_path.exists():
            logger.error("Файл темы не найден: %s", theme_path)
            return None
        try:
            with theme_path.open("r", encoding="utf-8") as f:
                theme_qss = f.read()
            self._load_common_qss()
            with self._cache_lock:
                # Комбинируем общие стили и стили темы
                combined_qss = f"{self._common_qss}\n{theme_qss}"

                # Добавляем перекрывающий блок QSS с параметрами из конфигурации.
                # Это гарантирует применение размеров шрифтов меню/меню-бара и размеров иконок/индикаторов,
                # даже если они захардкожены в файле темы. Поздние правила с одинаковой специфичностью побеждают.
                try:
                    overrides = self._build_config_overrides_qss()
                    if overrides:
                        combined_qss = f"{combined_qss}\n\n/* ==== AppConfig overrides (auto-generated) ==== */\n{overrides}"
                except Exception as exc:
                    # Не валим применение темы из‑за ошибок построения оверрайдов
                    logger.warning(
                        "Не удалось построить QSS-оверрайды из конфигурации: %s", exc
                    )
                self._qss_cache[theme_name] = combined_qss
                # Помечаем как недавно использованную и следим за размером
                self._qss_cache.move_to_end(theme_name, last=True)
                self._manage_cache_size()
            logger.debug("Загружена и кэширована тема: %s", theme_name)
            return combined_qss
        except UnicodeDecodeError as exc:
            logger.error("Ошибка декодирования файла темы %s: %s", theme_name, exc)
            return None
        except PermissionError as exc:
            logger.error("Ошибка доступа к файлу темы %s: %s", theme_name, exc)
            return None
        except OSError as exc:
            logger.error("Ошибка загрузки темы %s: %s", theme_name, exc)
            return None
        except Exception as exc:
            logger.error("Неожиданная ошибка при загрузке темы %s: %s", theme_name, exc)
            return None

    def apply(self, name: str) -> bool:
        """Применяет тему по имени и сохраняет в настройки."""
        normalized_name = self._normalize_theme_input(name)
        theme_config = self._get_theme_by_name(normalized_name)
        if not theme_config:
            logger.error("Тема не найдена: %s", name)
            return False
        qss_file = theme_config.get("qss_file")
        if not qss_file:
            logger.error("QSS файл не указан для темы: %s", name)
            return False

        # Проверяем, что имя файла безопасно
        if not self._is_safe_filename(qss_file):
            logger.error("Небезопасное имя файла темы: %s", qss_file)
            return False

        theme_path = app_config.paths.get_qss_dir() / qss_file

        # Дополнительная проверка пути
        try:
            # Проверяем, что путь находится внутри директории тем
            qss_dir = app_config.paths.get_qss_dir().resolve()
            full_path = theme_path.resolve()
            if not str(full_path).startswith(str(qss_dir)):
                logger.error(
                    "Попытка доступа к файлу вне директории тем: %s", theme_path
                )
                return False
        except Exception as exc:
            logger.error("Ошибка проверки пути к файлу темы %s: %s", theme_path, exc)
            return False

        # Кэшируем и ищем по каноническому имени, чтобы избежать дублей ключей
        canonical_name = theme_config.get("name", normalized_name)
        # ВАЖНО: инвалидируем кэш общих/темовых QSS перед загрузкой,
        # чтобы гарантированно подхватывать изменения файлов стилей
        # (особенно common.qss) без перезапуска приложения.
        # Это безопасно: кэш восстановится при чтении ниже.
        self.clear_cache()
        qss_content = self._load_theme_qss(canonical_name, theme_path)
        if qss_content is None:
            logger.error("Не удалось загрузить QSS для темы: %s", name)
            return False

        try:
            # Применяем QSS
            if self._stylesheet_applier is not None:
                self._stylesheet_applier(qss_content)
            else:
                app = QApplication.instance()
                if not app:
                    logger.error("QApplication instance не найден")
                    return False
                app.setStyleSheet(qss_content)

            # Инициализируем тему иконок Qt
            try:
                self._apply_qt_icon_theme(canonical_name)
            except Exception as icon_exc:
                logger.warning("Не удалось применить тему иконок Qt: %s", icon_exc)

            # Обновляем настройки и окно
            logger.info("Применена тема: %s", canonical_name)
            self.settings.set_theme(canonical_name)
            if self.main_window and hasattr(self.main_window, "update_theme"):
                self.main_window.update_theme()
            return True
        except Exception as exc:
            logger.error("Ошибка применения темы %s: %s", name, exc)
            return False

    def clear_cache(self) -> None:
        """Очищает кэш QSS."""
        with self._cache_lock:
            cache_size = len(self._qss_cache)
            self._qss_cache.clear()
            self._common_qss = None
        logger.debug("Кэш тем очищен, удалено %d записей", cache_size)

    def apply_and_refresh_ui(self) -> None:
        """Централизованно обновляет UI после применения темы.

        Делает следующее:
        - Очищает кэш иконок
        - Пересобирает главное меню
        - Перезагружает иконки дерева структуры
        - Обновляет верхние панели (Избранное/Недавние)
        """
        try:
            clear_icon_cache()
        except Exception as exc:
            logger.warning("Не удалось очистить кэш иконок: %s", exc)

        mw = getattr(self, "main_window", None)
        if not mw:
            return

        # Пересоздание главного меню
        try:
            menu_ctrl = getattr(mw, "menu_controller", None)
            if menu_ctrl:
                menu_ctrl.rebuild_after_theme_change()
        except Exception as exc:
            logger.warning("Ошибка пересборки меню после смены темы: %s", exc)

        # Перезагрузка иконок в структуре
        try:
            structure = getattr(mw, "structure", None)
            if structure and hasattr(structure, "reload_icons"):
                structure.reload_icons()
        except Exception as exc:
            logger.warning("Ошибка перезагрузки иконок структуры: %s", exc)

        # Обновление верхних панелей
        try:
            top_ctrl = getattr(mw, "top_panels_controller", None)
            if top_ctrl and hasattr(top_ctrl, "refresh_all"):
                top_ctrl.refresh_all()
        except Exception as exc:
            logger.warning("Ошибка обновления верхних панелей: %s", exc)

        # ВАЖНО: сохраняем пользовательский размер шрифта ТОЛЬКО для нужных виджетов
        # Не меняем глобальный шрифт приложения, чтобы не ломать диалоги и прочие элементы
        try:
            app = QApplication.instance()
            if app and hasattr(self, "settings") and hasattr(self.settings, "get_font_size"):
                try:
                    from PyQt6.QtGui import QFont
                    fs = int(self.settings.get_font_size())
                except Exception:
                    fs = None
                if fs:
                    # Локально на часто используемых виджетах (если доступны)
                    try:
                        tree = getattr(mw, "tree", None)
                        if tree and hasattr(tree, "update_font_size"):
                            tree.update_font_size(fs)
                    except Exception:
                        pass
                    try:
                        table = getattr(mw, "table", None)
                        if table and hasattr(table, "update_font_size"):
                            table.update_font_size(fs)
                    except Exception:
                        pass
        except Exception as exc:
            logger.warning("Не удалось переустановить размер шрифта после смены темы: %s", exc)

    def _validate_theme_config(self, theme: Dict[str, Any]) -> bool:
        """Проверяет корректность конфигурации темы."""
        try:
            if not isinstance(theme, dict):
                logger.warning("Конфигурация темы должна быть словарем")
                return False

            # Проверяем обязательные поля
            if not theme.get("name"):
                logger.warning("Отсутствует имя темы")
                return False
            # display_name допускается отсутствующим — available() подставит fallback
            if not theme.get("display_name"):
                logger.warning(
                    "Отсутствует отображаемое имя темы — будет использовано значение по умолчанию"
                )

            qss_file = theme.get("qss_file")
            if not qss_file:
                logger.warning(
                    "Отсутствует файл QSS для темы %s", theme.get("name", "без имени")
                )
                return False

            # Проверяем, что имя файла безопасно
            if not self._is_safe_filename(qss_file):
                logger.warning(
                    "Небезопасное имя файла QSS для темы %s",
                    theme.get("name", "без имени"),
                )
                return False

            # Проверяем опциональные поля
            is_dark = theme.get("is_dark")
            if is_dark is not None and not isinstance(is_dark, bool):
                logger.warning(
                    "Поле is_dark должно быть булевым для темы %s", theme["name"]
                )
                return False

            return True
        except Exception as exc:
            logger.error("Ошибка валидации конфигурации темы: %s", exc)
            return False

    def _apply_qt_icon_theme(self, theme_name: str) -> None:
        """Устанавливает тему и пути поиска иконок Qt для корректного отображения стандартных иконок.
        Выполнять в GUI-потоке до показа первых меню/диалогов."""
        if not theme_name:
            return
        # Формируем пути поиска: UI-иконки приложения как тема Qt
        ui_icons_dir = app_config.paths.get_ui_icons_dir()
        if not ui_icons_dir.exists():
            logger.debug("UI icons dir does not exist: %s", ui_icons_dir)
            return
        # Проверяем наличие директории темы, при отсутствии — используем fallback 'light'
        theme_dir = ui_icons_dir / theme_name
        if not theme_dir.exists():
            fallback = "light"
            fallback_dir = ui_icons_dir / fallback
            if fallback_dir.exists():
                logger.warning(
                    "Тема иконок '%s' не найдена, используется fallback '%s'",
                    theme_name,
                    fallback,
                )
                theme_name = fallback
            else:
                logger.warning(
                    "Директория темы иконок не найдена: %s, fallback 'light' также отсутствует",
                    theme_dir,
                )
        search_paths = [str(ui_icons_dir)]
        try:
            # Добавляем существующие ранее пути поиска, чтобы не терять системные
            current_paths = QIcon.themeSearchPaths()
            for p in current_paths:
                if p not in search_paths:
                    search_paths.append(p)
        except Exception:
            pass
        QIcon.setThemeSearchPaths(search_paths)
        # Имя темы — каноническое имя, ожидая поддиректории ui_icons_dir/<theme_name>
        QIcon.setThemeName(theme_name)

    def _build_config_overrides_qss(self) -> str:
        """Формирует блок QSS c параметрами из конфигурации для перекрытия темовых значений.

        Возвращает строку QSS. Пустая строка, если нечего перекрывать.
        """
        try:
            menu_font_size = int(app_config.get_menu_font_size())
        except Exception:
            menu_font_size = None
        try:
            menubar_font_size = int(app_config.get_menubar_font_size())
        except Exception:
            menubar_font_size = None
        try:
            menubar_item_height = int(app_config.get_menubar_item_height())
        except Exception:
            menubar_item_height = None
        try:
            menu_icon_size = int(app_config.get_menu_icon_size())
        except Exception:
            menu_icon_size = None
        try:
            menu_indicator_size = int(app_config.get_menu_indicator_size())
        except Exception:
            menu_indicator_size = None

        lines = []

        # Диалоги: принудительно используем системный (по умолчанию Qt) размер шрифта приложения,
        # чтобы избежать нежелательных изменений из тем/стилей. Это не меняет семейство шрифта.
        try:
            app = QApplication.instance()
            dialog_font_size = app.font().pointSize() if app else None
        except Exception:
            dialog_font_size = None
        if dialog_font_size and dialog_font_size > 0:
            # Распространяем на содержимое диалога, чтобы вложенные виджеты не переопределяли случайно
            lines.append(f"QDialog {{ font-size: {dialog_font_size}pt; }}")
            lines.append(f"QDialog * {{ font-size: {dialog_font_size}pt; }}")

        # Меню (QMenu)
        if menu_font_size:
            # Используем pt, чтобы соответствовать глобальному шрифту приложения и DPI
            lines.append(f"QMenu {{ font-size: {menu_font_size}pt; }}")
            # Применяем размер шрифта ко всем состояниям пунктов меню, чтобы перекрыть темовые состояния
            lines.append(f"QMenu::item {{ font-size: {menu_font_size}pt; }}")
            lines.append(f"QMenu::item:selected {{ font-size: {menu_font_size}pt; }}")
            lines.append(f"QMenu::item:hover {{ font-size: {menu_font_size}pt; }}")
            lines.append(f"QMenu::item:pressed {{ font-size: {menu_font_size}pt; }}")
            lines.append(f"QMenu::item:disabled {{ font-size: {menu_font_size}pt; }}")

        if menu_icon_size:
            # set both width and height; padding-left already defined in common
            lines.append(
                f"QMenu::icon {{ width: {menu_icon_size}px; height: {menu_icon_size}px; }}"
            )

        if menu_indicator_size:
            lines.append(
                f"QMenu::indicator {{ width: {menu_indicator_size}px; height: {menu_indicator_size}px; }}"
            )

        # Меню-бар (QMenuBar)
        menubar_rules = []
        if menubar_font_size:
            # Тоже используем pt для соответствия системному масштабу
            menubar_rules.append(f"font-size: {menubar_font_size}pt;")
        if menubar_rules:
            lines.append("QMenuBar { " + " ".join(menubar_rules) + " }")
        item_rules = []
        if menubar_font_size:
            item_rules.append(f"font-size: {menubar_font_size}pt;")
        if menubar_item_height:
            item_rules.append(f"min-height: {menubar_item_height}px;")
        if item_rules:
            # Базовое правило для пункта меню-бара
            lines.append("QMenuBar::item { " + " ".join(item_rules) + " }")
            # Дублируем для состояний, чтобы избежать переопределения темой
            if menubar_font_size or menubar_item_height:
                lines.append("QMenuBar::item:selected { " + " ".join(item_rules) + " }")
                lines.append("QMenuBar::item:hover { " + " ".join(item_rules) + " }")
                lines.append("QMenuBar::item:pressed { " + " ".join(item_rules) + " }")
        return "\n".join(lines)

    def get_cache_stats(self) -> Dict[str, Any]:
        """Возвращает статистику кэша тем."""
        with self._cache_lock:
            return {
                "cache_size": len(self._qss_cache),
                "max_size": self._max_cache_size,
                "cached_themes": list(self._qss_cache.keys()),
                "common_qss_loaded": self._common_qss is not None,
            }
