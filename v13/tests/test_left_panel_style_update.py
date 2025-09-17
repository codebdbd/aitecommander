import types

import pytest

from app.views.main_window import MainWindow


class StyleStub:
    def __init__(self):
        self.polish_calls = 0
        self.unpolish_calls = 0

    def polish(self, widget):
        self.polish_calls += 1

    def unpolish(self, widget):
        # Должен НЕ вызываться после оптимизации; если вызвался — счетчик увеличится и тест упадет
        self.unpolish_calls += 1


class LeftPanelStub:
    def __init__(self):
        self._props = {}
        self._updates_enabled = True
        self._style = StyleStub()

    # API свойств Qt
    def setProperty(self, name, value):
        self._props[name] = value

    def property(self, name):
        return self._props.get(name)

    # API обновлений
    def setUpdatesEnabled(self, enabled: bool):
        self._updates_enabled = bool(enabled)

    # API стиля
    def style(self):
        return self._style

    # На всякий случай, если где-то зовётся
    def update(self):
        pass


@pytest.fixture()
def window_like():
    # Создаём объект, совместимый по интерфейсу с MainWindow в части нужного метода
    left_panel = LeftPanelStub()
    win = types.SimpleNamespace(left_panel=left_panel)
    return win


def test_update_left_panel_style_polishes_without_unpolish(window_like):
    # Первый вызов с новой сферой приводит к изменению свойства и одному polish
    MainWindow._update_left_panel_style(window_like, 5)

    assert window_like.left_panel.property("sphere") == "5"
    assert window_like.left_panel.style().polish_calls == 1
    # Проверяем, что unpolish не вызывался
    assert window_like.left_panel.style().unpolish_calls == 0

    # Повторный вызов с тем же значением ничего не делает
    MainWindow._update_left_panel_style(window_like, 5)
    assert window_like.left_panel.style().polish_calls == 1

    # Изменение сферы вызывает еще один polish
    MainWindow._update_left_panel_style(window_like, 7)
    assert window_like.left_panel.property("sphere") == "7"
    assert window_like.left_panel.style().polish_calls == 2
