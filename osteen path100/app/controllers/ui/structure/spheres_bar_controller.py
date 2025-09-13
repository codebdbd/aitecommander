# app/controllers/ui/structure/spheres_bar_controller.py
from __future__ import annotations

from typing import Any, Dict, List

from PyQt6.QtCore import QSize
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QToolButton

from app.config_data import app_config
from app.utils.db.synchronization import signal_guard
from app.utils.ui.icon.icon_operations.creators import create_icon_from_path
from app.utils.ui.icon.path_service import icon_path_service
from app.utils.ui.updates import suspend_updates
 


class SpheresBarController:
    """Контроллер UI панели сфер.

    Перенесено из методов MainWindow:
      - _init_spheres_ui
      - _on_spheres_loaded_ui
      - _update_active_sphere_button
      - _switch_sphere (как приватная логика вызова structure.switch_sphere)
    """

    def __init__(self, window: Any):
        self.w = window  # Главное окно (QMainWindow с нужными атрибутами)

        # Не используем неон для кнопок сфер

    def init(self) -> None:
        """Подписка на сигнал загрузки сфер и запуск асинхронной загрузки."""
        sb = self.w.structure_business
        sb.spheres_loaded.connect(self.on_spheres_loaded_ui)
        sb.load_spheres_async()

    def switch_sphere(self, sphere_id: int) -> None:
        """Переключить активную сферу через контроллер структуры."""
        self.w.structure.switch_sphere(sphere_id)

    

    def _clear_spheres_bar(self) -> None:
        # Очистка группы кнопок
        for button in list(self.w.sphere_group.buttons()):
            self.w.sphere_group.removeButton(button)
        # Очистка лейаута
        s_layout = self.w.spheres_bar.layout()
        for i in reversed(range(s_layout.count())):
            widget = s_layout.itemAt(i).widget()
            if widget:
                widget.setParent(None)
                widget.deleteLater()
        self.w.sphere_buttons.clear()
        self.w.sphere_group.setExclusive(True)

    def _build_button(self, sphere: Dict[str, Any]) -> QToolButton:
        btn = QToolButton()
        sphere_id = sphere["id"]
        btn.setCheckable(True)
        icon_name = sphere.get("icon_path")
        if icon_name:
            icon_path = icon_path_service.get_ui_icons_dir() / icon_name
            if icon_path.exists():
                btn.setIcon(create_icon_from_path(str(icon_path)))
            else:
                btn.setIcon(QIcon())
        else:
            btn.setIcon(QIcon())
        # Фиксируем квадратный размер кнопки сфер
        btn.setFixedSize(62, 62)
        # Убираем внутренние отступы на уровне виджета
        try:
            btn.setContentsMargins(0, 0, 0, 0)
        except Exception:
            pass
        # Размер иконки берём из конфигурации UI, отступ 4px задан QSS padding'ом
        try:
            _sz = app_config.get_sphere_button_icon_size()
            btn.setIconSize(QSize(_sz[0], _sz[1]))
        except Exception:
            pass
        btn.setToolTip(sphere["name"])
        self.w.sphere_group.addButton(btn, sphere_id)
        btn.clicked.connect(lambda _=False, sid=sphere_id: self.switch_sphere(sid))
        # Убедимся, что на кнопке нет графических эффектов (неон и т.п.)
        try:
            btn.setGraphicsEffect(None)
        except Exception:
            pass
        self.w.sphere_buttons[sphere_id] = btn
        return btn

    def on_spheres_loaded_ui(self, spheres: List[Dict[str, Any]]):
        """Построение кнопок сфер в панели."""
        with suspend_updates(self.w.spheres_bar):
            self._clear_spheres_bar()
            s_layout = self.w.spheres_bar.layout()
            for sp in spheres:
                btn = self._build_button(sp)
                s_layout.addWidget(btn)
            # Явное обновление после массовых операций
            self.w.spheres_bar.update()

        # Устанавливаем визуальное состояние и/или активную сферу
        if spheres:
            try:
                sb = getattr(self.w, "structure_business", None)
                current_id = getattr(sb, "current_sphere_id", None) if sb else None
            except Exception:
                current_id = None

            if isinstance(current_id, int) and current_id > 0:
                # Сфера уже выбрана — только обновим кнопку и фокус
                self.update_active_sphere_button(int(current_id))
            else:
                # Текущая сфера не задана — выберем первую и запустим переключение
                first_id = spheres[0].get("id")
                if isinstance(first_id, int) and first_id > 0:
                    self.switch_sphere(int(first_id))

    @signal_guard("update_active_sphere_button")
    def update_active_sphere_button(self, sphere_id: int):
        """Обновляет состояние кнопок сфер и фокус."""
        for button in self.w.sphere_buttons.values():
            # Снимаем любые графические эффекты, чтобы неон не оставался на активной кнопке
            try:
                button.setGraphicsEffect(None)
            except Exception:
                pass
            button.setChecked(False)
        button = self.w.sphere_buttons.get(sphere_id)
        if button:
            button.setChecked(True)
            button.setFocus()
