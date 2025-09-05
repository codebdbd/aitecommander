import pytest


@pytest.mark.parametrize(
    "method_name,widget_key",
    [
        ("_get_sphere_cb", "sphere_cb"),
        ("_get_section_cb", "section_cb"),
        ("_get_category_cb", "category_cb"),
        ("_get_type_group", "type_group"),
        ("_get_profile_btn", "profile_btn"),
        ("_get_icon_btn", "icon_btn"),
    ],
)
def test_link_dialog_getters_call_ui_get_widget_with_expected_key(method_name, widget_key):
    # Создаём "голый" экземпляр без вызова __init__, чтобы избежать побочных эффектов UI
    from app.views.dialogs.link_dialog.link_dialog import LinkDialog

    ld = LinkDialog.__new__(LinkDialog)

    called = {"key": None}
    sentinel = object()

    class DummyUI:
        def get_widget(self, key):
            called["key"] = key
            return sentinel

    ld.ui = DummyUI()

    # Вызываем приватный геттер и проверяем, что он пробрасывает верный ключ
    getter = getattr(ld, method_name)
    result = getter()

    assert called["key"] == widget_key
    assert result is sentinel
