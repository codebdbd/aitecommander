import pytest

from app.views.dialogs.link_dialog.link_dialog_ui import LinkDialogUI

try:
    from PyQt6.QtWidgets import QApplication, QWidget
except Exception:  # pragma: no cover - PyQt import guard for environments without Qt
    QApplication = None  # type: ignore
    QWidget = None  # type: ignore


@pytest.mark.skipif(
    QApplication is None,
    reason="PyQt6 is not available in the test environment",
)
class TestSaveButtonState:
    def setup_method(self):
        # Инициализация QApplication (если ещё не создан)
        self.app = QApplication.instance() or QApplication([])
        self.parent = QWidget()
        self.ui = LinkDialogUI(self.parent)
        self.ui.build_ui([("web", "Веб"), ("file", "Файл")])
        self.ok_btn = self.ui.widgets.get("ok_btn")
        assert self.ok_btn is not None, "ok_btn должен существовать после build_ui"

    def teardown_method(self):
        # Чистка созданного окна
        self.parent.deleteLater()

    def _apply_and_pump(self):
        # Форсируем обновление состояния кнопки на случай, если сигналы не сработали
        self.ui._update_save_button_state()
        # Обрабатываем очередь событий Qt
        self.app.processEvents()

    def test_initially_disabled(self):
        # При пустых URL и Имя кнопка должна быть выключена
        self._apply_and_pump()
        assert self.ok_btn.isEnabled() is False

    def test_only_url_filled_disabled(self):
        # Заполняем только URL
        self.ui.url_le.setText("https://example.com")
        self.ui.name_le.setText("")
        self._apply_and_pump()
        assert self.ok_btn.isEnabled() is False

    def test_only_name_filled_disabled(self):
        # Заполняем только Имя
        self.ui.url_le.setText("")
        self.ui.name_le.setText("Example")
        self._apply_and_pump()
        assert self.ok_btn.isEnabled() is False

    def test_both_filled_enabled(self):
        # Заполняем оба поля
        self.ui.url_le.setText("https://example.com")
        self.ui.name_le.setText("Example")
        self._apply_and_pump()
        assert self.ok_btn.isEnabled() is True

    def test_clear_one_field_disables(self):
        # Сначала активируем
        self.ui.url_le.setText("https://example.com")
        self.ui.name_le.setText("Example")
        self._apply_and_pump()
        assert self.ok_btn.isEnabled() is True
        # Очищаем имя — должно выключиться
        self.ui.name_le.setText("")
        self._apply_and_pump()
        assert self.ok_btn.isEnabled() is False
