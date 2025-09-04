"""
Обработчики событий для LinkDialog.
Содержит логику обработки пользовательских действий.
"""

import logging

from .link_dialog_signals import LinkDialogSignals
from .handlers_mixins.icons_mixin import IconsMixin
from .handlers_mixins.profiles_mixin import ProfilesMixin
from .handlers_mixins.file_dialog_mixin import FileDialogMixin
from .handlers_mixins.type_change_mixin import TypeChangeMixin
from .handlers_mixins.hierarchy_mixin import HierarchyMixin
from .handlers_mixins.form_data_mixin import FormDataMixin
from .handlers_mixins.validation_mixin import ValidationMixin
from .handlers_mixins.link_processing_mixin import LinkProcessingMixin

logger = logging.getLogger(__name__)


class LinkDialogHandlers(
    TypeChangeMixin,
    FileDialogMixin,
    IconsMixin,
    ProfilesMixin,
    HierarchyMixin,
    FormDataMixin,
    ValidationMixin,
    LinkProcessingMixin,
):
    """Обработчики событий для LinkDialog."""

    def __init__(self, dialog):
        """Инициализация обработчиков."""
        self.dialog = dialog
        self._last_processed_path = ""
        self._is_processing = False
        self._worker_task_id = 0
        self._active_worker = None
        # Локальные сигналы (замена StructureWorkerSignals)
        self.signals = LinkDialogSignals()
        # Подключаем сигналы
        self.signals.link_info_finished.connect(
            lambda info: self._on_link_info_fetched(info)
        )
        self.signals.simple_error.connect(lambda error: self._on_link_info_error(error))

    def connect_signals(self) -> None:
        """Подключение сигналов к слотам."""
        # Тип ссылки
        self.dialog.ui.type_group.buttonClicked.connect(
            lambda b: self.on_type_changed(b.property("link_type"))
        )

        # URL изменение
        url_widget = self.dialog.ui.get_widget("url_le")
        url_widget.textChanged.connect(self._on_path_changed)
        # Немедленный триггер при завершении редактирования (Enter/потеря фокуса)
        try:
            url_widget.editingFinished.connect(self._trigger_link_processing)
        except (AttributeError, RuntimeError) as e:
            logger.warning(f"Ошибка подключения сигнала editingFinished для url_widget: {e}")

        # Кнопки
        self.dialog.ui.get_widget("browse_btn").clicked.connect(self._on_browse)
        self.dialog.ui.get_widget("profile_btn").clicked.connect(self._on_profile)
        self.dialog.ui.get_widget("icon_btn").clicked.connect(self._on_choose_icon)

        # Иерархия
        self.dialog.ui.get_widget("sphere_cb").currentIndexChanged.connect(
            self._update_sections
        )
        self.dialog.ui.get_widget("section_cb").currentIndexChanged.connect(
            self._update_categories
        )

        # Кнопки диалога
        self.dialog.ui.get_widget("button_box").accepted.connect(self._on_accept)
        self.dialog.ui.get_widget("button_box").rejected.connect(self.dialog.reject)

  
    def _on_accept(self) -> None:
        """Обработчик подтверждения диалога (orchestration логика)."""
        form_data = self._build_form_data()
        result = self._validate_and_save_data(form_data)
        
        if result["is_valid"]:
            self.dialog.accept()
        else:
            self._handle_validation_errors(form_data, result)

    