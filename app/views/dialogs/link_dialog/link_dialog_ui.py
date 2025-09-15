"""
Модуль для создания UI диалога добавления/редактирования ссылки.

Класс `LinkDialogUI` инкапсулирует построение виджетов и хранит ссылки
на ключевые элементы через словарь `widgets`.
"""

import logging
from typing import Any, Dict, List, Tuple

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.config_data import app_config
from app.utils.ui.icon.icon_operations.creators import create_icon_from_path
from app.utils.ui.icon.icon_resolver import resolve_icon_for_link

logger = logging.getLogger(__name__)


class LinkDialogUI:
    """UI компоненты для LinkDialog."""

    def __init__(self, parent: QWidget) -> None:
        """Инициализация UI компонентов.

        :param parent: Родительский виджет (обычно экземпляр `LinkDialog`).
        """
        self.parent: QWidget = parent
        self.widgets: Dict[str, QWidget] = {}

    def build_ui(self, link_types: List[Tuple[str, str]]) -> None:
        """Построение пользовательского интерфейса.

        :param link_types: Список пар `(code, title)` для типов ссылок.
        """
        vbox = QVBoxLayout(self.parent)
        margins = app_config.ui.get_link_dialog_margins()
        vbox.setContentsMargins(margins, margins, margins, margins)
        vbox.setSpacing(app_config.ui.get_link_dialog_spacing())

        # Секции UI
        self._build_type_section(vbox, link_types)
        self._build_form_section(vbox)
        self._build_buttons(vbox)

        # Состояние кнопки "Сохранить": активно только если заполнены и Путь, и Имя
        self._update_save_button_state()
        try:
            self.url_le.textChanged.connect(lambda _t: self._update_save_button_state())
            self.name_le.textChanged.connect(
                lambda _t: self._update_save_button_state()
            )
        except (AttributeError, RuntimeError) as e:
            logger.warning("Ошибка подключения сигнала textChanged для name_le: %s", e)

        # Фокус устанавливается в LinkDialog в зависимости от типа ссылки

    def _build_type_section(
        self, container: QVBoxLayout, link_types: List[Tuple[str, str]]
    ) -> None:
        """Создаёт секцию выбора типа ссылки и добавляет её в контейнер."""
        container.addWidget(QLabel("Тип ссылки:"))
        self.type_group = QButtonGroup(self.parent)
        hl_type = QHBoxLayout()

        for code, txt in link_types:
            btn = QToolButton()
            btn.setCheckable(True)
            btn.setText(txt)
            # Включаем hover-события как у кнопок сфер/категорий
            try:
                btn.setMouseTracking(True)
                btn.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
            except Exception:
                pass
            try:
                icon_path = resolve_icon_for_link({"type": code, "icon_path": ""})
                if icon_path:
                    btn.setIcon(create_icon_from_path(str(icon_path)))
                    # Размер иконки типовой кнопки берём из UI-конфига
                    type_icon_size = app_config.ui.get_link_dialog_type_icon_size()
                    btn.setIconSize(QSize(type_icon_size, type_icon_size))
            except (AttributeError, RuntimeError) as e:
                logger.warning("Ошибка настройки размера иконки типа ссылки: %s", e)
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            # Height by content. Width expands to share space equally.
            btn.setObjectName("linkTypeBtn")
            btn.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
            )
            self.type_group.addButton(btn)
            btn.setProperty("link_type", code)
            hl_type.addWidget(btn, 1)

        container.addLayout(hl_type)
        self.widgets["type_group"] = self.type_group

    def _build_form_section(self, container: QVBoxLayout) -> None:
        """Создаёт секцию формы (поля URL/Имя/Аргументы/Иерархия/Заметки/Избранное)."""
        self.form = QFormLayout()
        self.form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # Построение строк формы по частям
        self._form_add_path_row()
        self._form_add_name_row()
        self._form_add_args_row()
        self._form_add_hierarchy_section()
        self._form_add_notes_and_fav()

        container.addLayout(self.form)

    def _form_add_path_row(self) -> None:
        """Добавляет строку URL/Путь с кнопками Обзор и Профиль."""
        self.url_le = QLineEdit()
        hl_path = QHBoxLayout()
        hl_path.addWidget(self.url_le, 1)

        self.browse_btn = QPushButton("Обзор…")
        self.browse_btn.setFixedWidth(app_config.ui.get_fixed_button_width())
        hl_path.addWidget(self.browse_btn)

        self.profile_btn = QPushButton("Профиль")
        self.profile_btn.setFixedWidth(app_config.ui.get_fixed_button_width())
        hl_path.addWidget(self.profile_btn)

        self.form.addRow("URL/Путь:", hl_path)
        self.widgets.update(
            {
                "url_le": self.url_le,
                "browse_btn": self.browse_btn,
                "profile_btn": self.profile_btn,
            }
        )

    def _form_add_name_row(self) -> None:
        """Добавляет строку Имя и кнопку выбора иконки."""
        self.name_le = QLineEdit()
        hl_name = QHBoxLayout()
        hl_name.addWidget(self.name_le, 1)

        self.icon_btn = QPushButton("Иконка")
        self.icon_btn.setFixedWidth(app_config.ui.get_fixed_button_width())
        try:
            default_icon = int(app_config.ui.get_default_icon_size())
            self.icon_btn.setIconSize(QSize(default_icon, default_icon))
        except (AttributeError, RuntimeError, ValueError) as e:
            logger.warning("Ошибка настройки размера иконки кнопки: %s", e)
        hl_name.addWidget(self.icon_btn)

        self.form.addRow("Имя:", hl_name)
        self.widgets.update({"name_le": self.name_le, "icon_btn": self.icon_btn})

    def _form_add_args_row(self) -> None:
        """Добавляет строку для ввода аргументов запуска."""
        self.args_le = QLineEdit()
        self.args_label = QLabel("Аргументы:")
        self.form.addRow(self.args_label, self.args_le)
        self.widgets.update({"args_le": self.args_le, "args_label": self.args_label})

    def _form_add_hierarchy_section(self) -> None:
        """Добавляет выпадающие списки иерархии: Сфера, Раздел, Категория."""
        self.sphere_cb = QComboBox()
        self.section_cb = QComboBox()
        self.category_cb = QComboBox()

        # Избежим перехвата фокуса этими комбобоксами при движении мыши —
        # оставим только фокус по клику/Tab
        try:
            for cb in (self.sphere_cb, self.section_cb, self.category_cb):
                cb.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        except Exception:
            pass

        self.form.addRow("Сфера:", self.sphere_cb)
        self.form.addRow("Раздел:", self.section_cb)
        self.form.addRow("Категория:", self.category_cb)

        self.widgets.update(
            {
                "sphere_cb": self.sphere_cb,
                "section_cb": self.section_cb,
                "category_cb": self.category_cb,
            }
        )

    def _form_add_notes_and_fav(self) -> None:
        """Добавляет поле заметок и чекбокс избранного."""
        self.notes_te = QTextEdit()
        try:
            self.notes_te.setTabChangesFocus(True)
        except (AttributeError, RuntimeError) as e:
            logger.warning("Ошибка настройки tabChangesFocus для notes_te: %s", e)
        self.form.addRow("Заметки:", self.notes_te)
        self.widgets["notes_te"] = self.notes_te

        self.fav_chk = QCheckBox("Добавить в избранное")
        fav_row = QHBoxLayout()
        fav_row.setContentsMargins(0, 0, 0, 0)
        fav_row.setSpacing(0)
        fav_row.addWidget(self.fav_chk)
        fav_row.addStretch(1)
        self.form.addRow("", fav_row)
        self.widgets["fav_chk"] = self.fav_chk

    def _build_buttons(self, container: QVBoxLayout) -> None:
        """Создаёт панель кнопок OK/Cancel и добавляет её в контейнер."""
        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        ok_btn = self.button_box.button(QDialogButtonBox.StandardButton.Ok)
        if ok_btn is not None:
            ok_btn.setText("Сохранить")
        # Убираем системный пунктирный фокус: запретим default/autoDefault и автофокус
        try:
            if ok_btn is not None:
                ok_btn.setAutoDefault(False)
                ok_btn.setDefault(False)
                ok_btn.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        except (AttributeError, RuntimeError) as e:
            logger.warning("Ошибка настройки фокуса для OK кнопки: %s", e)
        if ok_btn is not None:
            ok_btn.setFixedWidth(app_config.ui.get_fixed_button_width())

        cancel_btn = self.button_box.button(QDialogButtonBox.StandardButton.Cancel)
        if cancel_btn is not None:
            cancel_btn.setText("Отмена")
        try:
            if cancel_btn is not None:
                cancel_btn.setAutoDefault(False)
                cancel_btn.setDefault(False)
                cancel_btn.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        except (AttributeError, RuntimeError) as e:
            logger.warning("Ошибка настройки фокуса для Cancel кнопки: %s", e)
        if cancel_btn is not None:
            cancel_btn.setFixedWidth(app_config.ui.get_fixed_button_width())

        container.addWidget(self.button_box)
        self.widgets["button_box"] = self.button_box
        if ok_btn is not None:
            self.widgets["ok_btn"] = ok_btn

    def get_widget(self, name: str) -> QWidget | None:
        """Получить виджет по имени."""
        return self.widgets.get(name)

    def _update_save_button_state(self) -> None:
        """Включает кнопку "Сохранить" только если заполнены и URL/Путь, и Имя."""
        try:
            url_ok = bool(self.url_le.text().strip())
            name_ok = bool(self.name_le.text().strip())
            ok_btn = self.widgets.get("ok_btn") or self.button_box.button(
                QDialogButtonBox.StandardButton.Ok
            )
            if ok_btn is not None:
                ok_btn.setEnabled(url_ok and name_ok)
        except (AttributeError, RuntimeError) as e:
            logger.warning("Ошибка обновления состояния кнопки сохранения: %s", e)

    def set_form_data(self, data: Dict[str, Any]) -> None:
        """Установить данные формы из словаря."""
        for key, value in data.items():
            self.set_widget_value(key, value)

    def set_widget_value(self, name: str, value: Any) -> None:
        """Установить значение виджета."""
        widget = self.get_widget(name)
        if widget:
            if hasattr(widget, "setChecked"):
                widget.setChecked(bool(value))
            elif hasattr(widget, "setText"):
                widget.setText(str(value))
            elif hasattr(widget, "setPlainText"):
                widget.setPlainText(str(value))

    def get_widget_value(self, name: str) -> Any:
        """Получить значение виджета."""
        widget = self.get_widget(name)
        if widget:
            if hasattr(widget, "text"):
                return widget.text()
            elif hasattr(widget, "toPlainText"):
                return widget.toPlainText()
            elif hasattr(widget, "isChecked"):
                return widget.isChecked()
        return None
