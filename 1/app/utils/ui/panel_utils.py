from functools import partial

from PyQt6.QtCore import QSize
from PyQt6.QtWidgets import QToolButton

from app.config_data import app_config


def create_link_button(link_data, default_icon_path, click_handler, icon_creator, icon_dir):
    button = QToolButton()
    
    # Используем единые параметры для всех кнопок топпанели
    button_size = app_config.get_top_panel_button_size()
    icon_size = app_config.get_top_panel_icon_size()
    button.setFixedSize(button_size, button_size)
    button.setIconSize(icon_size)
    
    # Создаем иконку
    icon_name = link_data.get("icon_path", "")
    if icon_name:
        icon_path = icon_dir / icon_name
        if icon_path.exists():
            button.setIcon(icon_creator(str(icon_path)))
        else:
            button.setIcon(icon_creator(str(default_icon_path)))
    else:
        button.setIcon(icon_creator(str(default_icon_path)))
    
    button.setToolTip(link_data.get("name", "Неизвестная ссылка"))
    try:
        button.clicked.connect(partial(click_handler, link_data))
    except Exception:
        button.setEnabled(False)
    return button

def update_panel(widget, links, create_button_func):
    widget._clear_layout()
    for link in links:
        button = create_button_func(link)
        widget.layout.addWidget(button)
    widget.layout.addStretch()
