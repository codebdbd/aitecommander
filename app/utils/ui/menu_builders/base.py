from app.utils.ui.icon.icon_operations.cache_proxy import icon_cache


def get_menu_icon(name: str, theme: str):
    """Возвращает иконку для контекстного меню с учётом темы.
    Централизованная точка для кеширования и будущих изменений.
    """
    return icon_cache.get_icon(name, theme, 'context_menu')
