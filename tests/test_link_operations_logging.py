import logging
import pytest

from app.controllers.ui.dialogs.link_operations_controller import LinkOperationsController


@pytest.fixture()
def controller():
    # db, undo_stack, main_window не используются в тестируемых методах
    return LinkOperationsController(db=None, undo_stack=None, main_window=None)


def _raise(*args, **kwargs):
    raise RuntimeError("subscriber failed")


@pytest.mark.parametrize(
    "method_name, signal_attr, args, expected_msg",
    [
        ("emit_links_changed", "links_changed", (123,), "emit_links_changed: failed to emit signal"),
        ("emit_favorites_changed", "favorites_changed", tuple(), "emit_favorites_changed: failed to emit signal"),
        ("emit_recents_changed", "recents_changed", tuple(), "emit_recents_changed: failed to emit signal"),
        ("emit_link_saved", "link_saved", ({"id": 1},), "emit_link_saved: failed to emit signal"),
        ("emit_link_deleted", "link_deleted", ({"id": 1},), "emit_link_deleted: failed to emit signal"),
    ],
)
def test_logs_exception_when_subscriber_raises(controller, method_name, signal_attr, args, expected_msg, caplog):
    # Подписчик выбрасывает исключение
    getattr(controller, signal_attr).connect(_raise)

    with caplog.at_level(logging.ERROR):
        getattr(controller, method_name)(*args)

    # Проверяем, что зафиксировано исключение с ожидаемым сообщением
    messages = "\n".join(r.message for r in caplog.records)
    assert expected_msg in messages
