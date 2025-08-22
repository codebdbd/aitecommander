"""
UI компоненты для LinkDialog.
Содержит только UI элементы и их первичную настройку.
"""

from typing import Any, Dict

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
)

from app.config_data import app_config
from app.utils.ui.icon.icon_operations.creators import create_icon_from_path
from app.utils.ui.icon.icon_resolver import resolve_icon_for_link


class LinkDialogUI:
    """UI компоненты для LinkDialog."""
    
    def __init__(self, parent):
        """Инициализация UI компонентов."""
        self.parent = parent
        self.widgets = {}
        
    def build_ui(self, link_types: list) -> None:
        """Построение пользовательского интерфейса."""
        vbox = QVBoxLayout(self.parent)
        margins = app_config.get('ui.link_dialog_margins', 20)
        vbox.setContentsMargins(margins, margins, margins, margins)
        vbox.setSpacing(app_config.get('ui.link_dialog_spacing', 10))

        # Тип ссылки
        vbox.addWidget(QLabel("Тип ссылки:"))
        self.type_group = QButtonGroup(self.parent)
        hl_type = QHBoxLayout()
        
        for code, txt in link_types:
            btn = QToolButton()
            btn.setCheckable(True)
            btn.setText(txt)
            try:
                icon_path = resolve_icon_for_link({"type": code, "icon_path": ""})
                if icon_path:
                    btn.setIcon(create_icon_from_path(str(icon_path)))
                    btn.setIconSize(QSize(32, 32))
            except Exception:
                pass
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            # Height by content. Width expands to share space equally.
            btn.setObjectName("linkTypeBtn")
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            self.type_group.addButton(btn)
            btn.setProperty("link_type", code)
            hl_type.addWidget(btn, 1)
            
        vbox.addLayout(hl_type)
        self.widgets['type_group'] = self.type_group

        # Форма
        self.form = QFormLayout()
        self.form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # URL/Путь
        self.url_le = QLineEdit()
        hl_path = QHBoxLayout()
        hl_path.addWidget(self.url_le, 1)
        
        self.browse_btn = QPushButton("Обзор…")
        self.browse_btn.setFixedWidth(app_config.get('ui.fixed_button_width', 100))
        hl_path.addWidget(self.browse_btn)
        
        self.profile_btn = QPushButton("Профиль")
        self.profile_btn.setFixedWidth(app_config.get('ui.fixed_button_width', 100))
        hl_path.addWidget(self.profile_btn)
        
        self.form.addRow("URL/Путь:", hl_path)
        self.widgets.update({
            'url_le': self.url_le,
            'browse_btn': self.browse_btn,
            'profile_btn': self.profile_btn
        })

        # Имя
        self.name_le = QLineEdit()
        hl_name = QHBoxLayout()
        hl_name.addWidget(self.name_le, 1)
        
        self.icon_btn = QPushButton("Иконка")
        self.icon_btn.setFixedWidth(app_config.get('ui.fixed_button_width', 100))
        hl_name.addWidget(self.icon_btn)
        
        self.form.addRow("Имя:", hl_name)
        self.widgets.update({
            'name_le': self.name_le,
            'icon_btn': self.icon_btn
        })

        # Аргументы
        self.args_le = QLineEdit()
        self.args_label = QLabel("Аргументы:")
        self.form.addRow(self.args_label, self.args_le)
        self.widgets.update({
            'args_le': self.args_le,
            'args_label': self.args_label
        })

        # Иерархия
        self.sphere_cb = QComboBox()
        self.section_cb = QComboBox()
        self.category_cb = QComboBox()
        
        self.form.addRow("Сфера:", self.sphere_cb)
        self.form.addRow("Раздел:", self.section_cb)
        self.form.addRow("Категория:", self.category_cb)
        
        self.widgets.update({
            'sphere_cb': self.sphere_cb,
            'section_cb': self.section_cb,
            'category_cb': self.category_cb
        })

        # Заметки
        self.notes_te = QTextEdit()
        # Не перехватывать Tab внутри многострочного поля — пусть переключает фокус
        try:
            self.notes_te.setTabChangesFocus(True)
        except Exception:
            pass
        self.form.addRow("Заметки:", self.notes_te)
        self.widgets['notes_te'] = self.notes_te

        # Избранное (не растягивать на всю ширину)
        self.fav_chk = QCheckBox("Добавить в избранное")
        fav_row = QHBoxLayout()
        fav_row.setContentsMargins(0, 0, 0, 0)
        fav_row.setSpacing(0)
        fav_row.addWidget(self.fav_chk)
        fav_row.addStretch(1)  # фиксирует чекбокс слева, без растяжения
        self.form.addRow("", fav_row)
        self.widgets['fav_chk'] = self.fav_chk

        vbox.addLayout(self.form)

        # Кнопки
        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        ok_btn = self.button_box.button(QDialogButtonBox.StandardButton.Ok)
        ok_btn.setText("Сохранить")
        # Убираем системный пунктирный фокус: запретим default/autoDefault и автофокус
        try:
            ok_btn.setAutoDefault(False)
            ok_btn.setDefault(False)
            ok_btn.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        except Exception:
            pass
        ok_btn.setFixedWidth(app_config.get('ui.fixed_button_width', 100))

        cancel_btn = self.button_box.button(QDialogButtonBox.StandardButton.Cancel)
        cancel_btn.setText("Отмена")
        try:
            cancel_btn.setAutoDefault(False)
            cancel_btn.setDefault(False)
            cancel_btn.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        except Exception:
            pass
        cancel_btn.setFixedWidth(app_config.get('ui.fixed_button_width', 100))
        
        vbox.addWidget(self.button_box)
        self.widgets['button_box'] = self.button_box
        self.widgets['ok_btn'] = ok_btn

        # Состояние кнопки "Сохранить": активно только если заполнены и Путь, и Имя
        self._update_save_button_state()
        try:
            self.url_le.textChanged.connect(lambda _t: self._update_save_button_state())
            self.name_le.textChanged.connect(lambda _t: self._update_save_button_state())
        except Exception:
            pass

        # Начальный фокус ставим на поле URL/Путь (а не на кнопку)
        try:
            self.url_le.setFocus(Qt.FocusReason.ActiveWindowFocusReason)
        except Exception:
            pass

    def get_widget(self, name: str):
        """Получить виджет по имени."""
        return self.widgets.get(name)

    def _update_save_button_state(self) -> None:
        """Включает кнопку "Сохранить" только если заполнены и URL/Путь, и Имя."""
        try:
            url_ok = bool(self.url_le.text().strip())
            name_ok = bool(self.name_le.text().strip())
            ok_btn = self.widgets.get('ok_btn') or self.button_box.button(QDialogButtonBox.StandardButton.Ok)
            ok_btn.setEnabled(url_ok and name_ok)
        except Exception:
            pass

    def set_form_data(self, data: Dict[str, Any]) -> None:
        """Установить данные формы из словаря."""
        for key, value in data.items():
            self.set_widget_value(key, value)

    def set_widget_value(self, name: str, value: Any) -> None:
        """Установить значение виджета."""
        widget = self.get_widget(name)
        if widget:
            if hasattr(widget, 'setChecked'):
                widget.setChecked(bool(value))
            elif hasattr(widget, 'setText'):
                widget.setText(str(value))
            elif hasattr(widget, 'setPlainText'):
                widget.setPlainText(str(value))

    def get_widget_value(self, name: str) -> Any:
        """Получить значение виджета."""
        widget = self.get_widget(name)
        if widget:
            if hasattr(widget, 'text'):
                return widget.text()
            elif hasattr(widget, 'toPlainText'):
                return widget.toPlainText()
            elif hasattr(widget, 'isChecked'):
                return widget.isChecked()
        return None
