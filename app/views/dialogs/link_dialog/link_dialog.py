"""
LinkDialog - диалог добавления/редактирования ссылки.

Интерфейсы контроллеров (для статической проверки):
- DialogControllerProtocol: предоставляет иерархические данные и валидацию/сохранение.
- LinkDataControllerProtocol: отвечает только за валидацию/сохранение данных формы.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol, Tuple, runtime_checkable

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QWidget,
)

from app.config_data import app_config
from app.models.link_type import LinkType
from app.utils.ui.icon.icon_resolver import resolve_icon_for_link
from app.utils.ui.icon.path_service import icon_path_service
from app.utils.ui.icon.ui_helpers import set_icon_to_button
from app.utils.ui.icon.validation import validate_config_for_icons
from app.views.effects.neon_effect import NeonEventFilter

from ..base_dialog import BaseDialog
from .link_dialog_handlers import LinkDialogHandlers
from .link_dialog_ui import LinkDialogUI

logger = logging.getLogger(__name__)


@runtime_checkable
class LinkDataControllerProtocol(Protocol):
    """Протокол контроллера данных ссылки (минимальный контракт).

    Ожидается реализация метода `validate_and_save`, который принимает
    словарь данных формы и возвращает словарь результата с ключом `is_valid`
    и необязательным списком `errors`.
    """

    def validate_and_save(self, form_data: Dict[str, Any]) -> Dict[str, Any]: ...


@runtime_checkable
class DialogControllerProtocol(LinkDataControllerProtocol, Protocol):
    """Протокол диалогового контроллера с иерархическими данными.

    Требуется предоставление списков разделов и категорий по идентификаторам.
    Элементы списков должны быть словарями с ключами как минимум `id` и `name`,
    опционально `icon_path`.
    """

    def get_sections_for_sphere(self, sphere_id: int) -> List[Dict[str, Any]]: ...

    def get_categories_for_section(self, section_id: int) -> List[Dict[str, Any]]: ...


class LinkDialog(BaseDialog):
    """Диалог добавления/редактирования ссылок с модульной структурой."""

    # Настраиваемая задержка дебаунса обработки пути (URL) в миллисекундах.
    # Используется таймером для отложенного старта парсинга пути при вводе пользователем,
    # чтобы не триггерить фоновые задачи на каждый символ. Вынесено из "магического"
    # значения для удобства настройки и тестирования.
    PATH_DEBOUNCE_MS: int = 300

    # --- Приватные геттеры UI-виджетов для устранения дублирования ---
    def _get_sphere_cb(self) -> QComboBox:
        """Возвращает комбобокс сфер (`QComboBox`)."""
        return self.ui.get_widget("sphere_cb")

    def _get_section_cb(self) -> QComboBox:
        """Возвращает комбобокс разделов (`QComboBox`)."""
        return self.ui.get_widget("section_cb")

    def _get_category_cb(self) -> QComboBox:
        """Возвращает комбобокс категорий (`QComboBox`)."""
        return self.ui.get_widget("category_cb")

    def _get_icon_btn(self) -> QPushButton:
        """Возвращает кнопку выбора иконки (`QPushButton`)."""
        return self.ui.get_widget("icon_btn")

    def _get_type_group(self) -> QButtonGroup:
        """Возвращает группу переключателей типов ссылки (`QButtonGroup`)."""
        return self.ui.get_widget("type_group")

    def _get_profile_btn(self) -> QPushButton:
        """Возвращает кнопку выбора профиля (`QPushButton`)."""
        return self.ui.get_widget("profile_btn")

    # Дополнительные геттеры для унификации доступа к UI
    def _get_url_le(self) -> QLineEdit:
        """Возвращает поле ввода URL (`QLineEdit`)."""
        return self.ui.get_widget("url_le")

    def _get_name_le(self) -> QLineEdit:
        """Возвращает поле ввода названия (`QLineEdit`)."""
        return self.ui.get_widget("name_le")

    def _get_args_le(self) -> QLineEdit:
        """Возвращает поле ввода аргументов (`QLineEdit`)."""
        return self.ui.get_widget("args_le")

    def _get_args_label(self) -> QLabel:
        """Возвращает метку аргументов (`QLabel`)."""
        return self.ui.get_widget("args_label")

    def _get_browse_btn(self) -> QPushButton:
        """Возвращает кнопку "Обзор" (`QPushButton`)."""
        return self.ui.get_widget("browse_btn")

    def _get_button_box(self) -> QDialogButtonBox:
        """Возвращает блок кнопок диалога (`QDialogButtonBox`)."""
        return self.ui.get_widget("button_box")

    def _get_fav_chk(self) -> QCheckBox:
        """Возвращает чекбокс избранного (`QCheckBox`)."""
        return self.ui.get_widget("fav_chk")

    def _get_notes_te(self) -> QTextEdit:
        """Возвращает поле заметок (`QTextEdit`)."""
        return self.ui.get_widget("notes_te")

    def __init__(
        self,
        initialization_data: Dict,
        dialog_controller: DialogControllerProtocol,
        link: Optional[Dict] = None,
        category_id: Optional[int] = None,
        parent: Optional[QWidget] = None,
        link_controller: Optional[LinkDataControllerProtocol] = None,
    ):
        super().__init__(parent)

        # Обеспечиваем существование директории пользовательских иконок
        # Перенесено из уровня модуля, чтобы исключить побочные эффекты при импорте
        icon_path_service.ensure_user_icons_dir()

        # Получаем типы ссылок из конфигурации
        self.link_types = app_config.settings.get_link_types()

        # Инициализация основных свойств
        self._init_core_properties(
            initialization_data, dialog_controller, link, category_id
        )

        # Опциональный контроллер для MVC архитектуры
        self.link_controller = link_controller

        # Инициализация компонентов
        self._init_components()

        # Проверка конфигурации
        if not self._validate_configuration():
            return

        # Настройка свойств UI и загрузка данных
        self._setup_ui_properties()
        self._load_initial()

    def _init_core_properties(
        self,
        initialization_data: Dict,
        dialog_controller,
        link: Optional[Dict],
        category_id: Optional[int],
    ) -> None:
        """Инициализирует основные свойства диалога."""
        self.initialization_data = initialization_data
        self.dialog_controller = dialog_controller
        self.link = link.copy() if link else {}
        self.initial_category = category_id
        self.link_type = self.link.get("type", "web")
        self.icon_name = self.link.get("icon_path", "")
        self.selected_profiles: List[Dict] = []

    def _init_components(self) -> None:
        """Инициализация UI и обработчиков."""
        # UI компоненты
        self.ui = LinkDialogUI(self)
        self.ui.build_ui(self.link_types)

        # Неоновое свечение для кнопок типов ссылок — как у кнопок сфер
        try:
            self._neon_link_filter = NeonEventFilter(
                color=QColor("#0194F0"), blur_radius=18
            )
            for btn in self._get_type_group().buttons():
                btn.installEventFilter(self._neon_link_filter)
        except (AttributeError, RuntimeError) as e:
            # Не блокируем диалог при ошибке эффекта
            logger.warning(
                "Ошибка установки neon эффекта на кнопки типов: %s", e, exc_info=True
            )

        # Обработчики событий
        self.handlers = LinkDialogHandlers(self)
        self.handlers.connect_signals()

        # Инициализация воркеров и таймеров
        self._init_workers_and_timers()

    def _init_workers_and_timers(self) -> None:
        """Инициализирует воркеры и таймеры для обработки ссылок."""
        self._processing_timer = QTimer(self)
        self._processing_timer.setSingleShot(True)
        self._processing_timer.timeout.connect(self.handlers._trigger_link_processing)

    def _validate_configuration(self) -> bool:
        """Проверяет конфигурацию диалога."""
        if not validate_config_for_icons(app_config):
            self.show_error(
                "Некорректная конфигурация иконок.",
                "Ошибка конфигурации",
                informative_text=(
                    "Не задан путь к каталогу иконок. Укажите путь в настройках приложения или конфиге."
                ),
                details="Параметр конфигурации для иконок отсутствует или пуст.",
            )
            self.close()
            return False
        return True

    def _setup_ui_properties(self) -> None:
        """Настраивает свойства UI диалога."""
        self.setWindowTitle("Редактировать ссылку" if self.link else "Добавить ссылку")
        self.setFixedSize(
            app_config.ui.get_link_dialog_width(),
            app_config.ui.get_link_dialog_height(),
        )

    def _load_initial(self) -> None:
        """Загружает начальные данные в форму."""
        logger.debug(
            "Инициализация формы: link_type=%s, category_id=%s, link_keys=%s",
            self.link_type,
            self.initial_category,
            list(self.link.keys()),
        )

        # Установка типа ссылки
        type_group = self._get_type_group()
        _lt = LinkType.from_value(self.link_type)
        for btn in type_group.buttons():
            if btn.property("link_type") == _lt.value:
                btn.setChecked(True)
                break

        # Загрузка данных формы
        form_data = {
            "url_le": self.link.get("url", ""),
            "name_le": self.link.get("name", ""),
            "args_le": self.link.get("args", ""),
            "notes_te": self.link.get("notes", ""),
            "fav_chk": bool(self.link.get("is_favorite", False)),
        }

        logger.debug("Исходные данные формы: %s", form_data)

        self.ui.set_form_data(form_data)

        logger.debug("Начальные значения установлены в UI; продолжаем установку иконки")

        # Установка иконки
        self._set_initial_icon()

        # Заполнение иерархии
        self._populate_hierarchy()

        # Загрузка мигрированных профилей
        if self.link and self.link.get("migrated_profiles"):
            self.selected_profiles = self.link["migrated_profiles"]
            profile_btn = self._get_profile_btn()
            profile_btn.setText(self._format_profile_text(self.selected_profiles))

        # Обновление состояния UI
        self.handlers._update_ui_state()

    def _set_initial_icon(self) -> None:
        """Устанавливает начальную иконку."""
        resolved, exists = self._resolve_and_apply_icon(
            LinkType.from_value(self.link_type).value, self.icon_name
        )
        if not exists:
            # Сообщаем один раз, что иконка не найдена
            self.show_warning(
                "Иконка по умолчанию не найдена.",
                "Проблема с иконкой",
                informative_text="Кнопка будет отображаться без иконки. Укажите корректный путь к иконкам в настройках.",
                details=f"Ожидался файл: {resolved}",
            )

    def _resolve_and_apply_icon(
        self, link_type: str, icon_name: str
    ) -> Tuple[Optional[str], bool]:
        """Резолвит путь к иконке и применяет её к кнопке, если файл существует.

        Возвращает кортеж `(resolved_path, exists)`, где `resolved_path` — строка
        с путём или None, а `exists` — флаг существования файла.
        """
        link_dict = {"type": link_type, "icon_path": icon_name}
        resolved = resolve_icon_for_link(link_dict)
        exists = bool(resolved and Path(resolved).exists())
        if exists:
            set_icon_to_button(self._get_icon_btn(), resolved)
        return resolved, exists

    def set_link_type(self, link_type: str) -> None:
        """Программно выбрать тип ссылки и обновить UI.

        Единая реализация находится в миксине `TypeChangeMixin` (через `LinkDialogHandlers`).
        Этот метод оставлен как стабильная точка входа для внешнего кода
        (например, `MainWindow.quick_add_link`) и делегирует выполнение обработчику.
        """
        # Делегируем централизованной реализации в обработчиках
        self.handlers.set_link_type(link_type)

    def _populate_hierarchy(self) -> None:
        """Заполняет иерархические списки (сферы/разделы/категории).

        Разделён на этапы:
        1) загрузка списка сфер из initialization_data,
        2) применение начального выбора (по category_hierarchy, если есть),
        3) делегирование обновления разделов/категорий миксину HierarchyMixin.
        """
        # 1) Загрузка сфер из initialization_data
        self._populate_spheres()

        sphere_cb = self._get_sphere_cb()
        section_cb = self._get_section_cb()
        category_cb = self._get_category_cb()

        # 2) Применение начального выбора (по ссылке/параметрам конструктора)
        cid = self.link.get("category_id") or self.initial_category
        if cid:
            hierarchy = self.initialization_data.get("category_hierarchy") or {}

            # Сначала выставляем сферу (если задана в иерархии)
            self._set_index_by_data(sphere_cb, hierarchy.get("sphere_id"))

            # Обновляем разделы под текущую сферу
            self.handlers._update_sections()

            # Устанавливаем раздел, если задан, иначе оставляем текущий (или первый, если ещё не выбран)
            section_id = hierarchy.get("section_id")
            if not self._set_index_by_data(section_cb, section_id):
                self._select_first_if_unset(section_cb)

            # Обновляем категории под текущий раздел
            self.handlers._update_categories()

            # Устанавливаем категорию, если задана, иначе оставляем текущую (или первую, если ещё не выбрана)
            category_id = hierarchy.get("category_id")
            if not self._set_index_by_data(category_cb, category_id):
                self._select_first_if_unset(category_cb)
        else:
            # Значения по умолчанию: первая сфера/раздел/категория
            self._apply_default_hierarchy_selection()
            self.handlers._update_sections()
            if section_cb.count() > 0:
                self._select_first_if_unset(section_cb)
                self.handlers._update_categories()
                if category_cb.count() > 0:
                    self._select_first_if_unset(category_cb)

    def _populate_spheres(self) -> None:
        """Заполняет список сфер из initialization_data (без иконок)."""
        sphere_cb = self._get_sphere_cb()
        sphere_cb.clear()
        for sp in self.initialization_data.get("spheres", []):
            sphere_cb.addItem(sp["name"], sp["id"])

    def _apply_default_hierarchy_selection(self) -> None:
        """Устанавливает выбор по умолчанию: первая сфера, первый раздел, первая категория."""
        sphere_cb = self._get_sphere_cb()
        if sphere_cb.count() > 0:
            sphere_cb.setCurrentIndex(0)

    def _set_index_by_data(self, combo: Any, data_id: Any) -> bool:
        """Безопасная установка текущего индекса комбобокса по значению data.

        Возвращает True, если индекс был успешно установлен. Возвращает False,
        если data_id равен None, совпадение не найдено или в процессе возникло
        исключение. Состояние комбобокса при этом не изменяется.
        """
        try:
            if data_id is None:
                return False
            idx = combo.findData(data_id)
            if idx >= 0:
                combo.setCurrentIndex(idx)
                return True
        except (AttributeError, RuntimeError, TypeError):
            # В спорных случаях не меняем состояние
            return False
        return False

    def _select_first_if_unset(self, combo: Any) -> bool:
        """Выбирает первый элемент комбобокса, если текущий индекс не установлен.

        Возвращает True в случае успешного выбора. Возвращает False, если
        элементов нет, индекс уже установлен или произошло исключение.
        """
        try:
            if combo.count() > 0 and combo.currentIndex() < 0:
                combo.setCurrentIndex(0)
                return True
        except (AttributeError, RuntimeError):
            return False
        return False

    def get_ui_icons_dir(self) -> Path:
        """Получает директорию UI иконок."""
        return icon_path_service.get_ui_icons_dir()

    def get_user_icons_dir(self) -> Path:
        """Получает директорию пользовательских иконок."""
        return icon_path_service.get_user_icons_dir()

    def _format_profile_text(self, profiles: List[Dict]) -> str:
        """Форматирует текст для отображения выбранных профилей."""
        emails = [p.get("email") or p.get("name") for p in profiles]
        if not emails:
            return "Профиль"
        elif len(emails) == 1:
            return f"Профиль: {emails[0]}"
        elif len(emails) == 2:
            return f"Профили: {emails[0]}, {emails[1]}"
        return f"Профили: {emails[0]}, {emails[1]} и ещё {len(emails) - 2}"

    def closeEvent(self, event) -> None:
        """Обработчик события закрытия окна."""
        # Если идёт обработка ссылки, попросим подтверждение у пользователя
        if self.handlers._is_processing or self.handlers._active_worker:
            path_info = self.handlers._last_processed_path or self.link.get("url", "")
            proceed = self.ask_confirmation(
                f"Идёт обработка ссылки '{path_info}'. Закрыть окно?",
                "Подтверждение закрытия",
            )
            if not proceed:
                event.ignore()
                return
        # Делегируем корректное завершение фоновой обработки централизованному методу
        self.handlers.cancel_processing()
        # Уничтожаем таймер, если он ещё жив
        try:
            if getattr(self, "_processing_timer", None):
                self._processing_timer.deleteLater()
        except (AttributeError, RuntimeError) as e:
            logger.debug(
                "closeEvent: ошибка при deleteLater таймера: %s", e, exc_info=True
            )
        super().closeEvent(event)
