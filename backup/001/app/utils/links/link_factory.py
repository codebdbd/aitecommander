from typing import Any, Dict, Optional


class LinkRecordFactory:
    """Фабрика для создания записей ссылок в стандартизированном формате."""

    @staticmethod
    def create_link_record(
        name: str,
        url: str,
        link_type: str,
        icon_name: str,
        notes: str,
        last_used: Any,
        position: int,
        category_id: Optional[int],
        args: str = "",
        is_favorite: int = 0,
        link_id: Optional[int] = None,
        browser_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Создает запись ссылки со всеми необходимыми полями.

        Args:
            name: Название ссылки
            url: URL или путь к ссылке
            link_type: Тип ссылки (web, file, folder, script, program, chromeapp)
            icon_name: Путь к иконке
            notes: Заметки к ссылке
            last_used: Время последнего использования
            position: Позиция в списке
            category_id: ID категории
            args: Аргументы командной строки
            is_favorite: Флаг избранного (0 или 1)
            link_id: ID ссылки (для обновления существующей)
            browser_key: Ключ браузера для веб-ссылок

        Returns:
            Словарь с данными ссылки
        """
        record = {
            "name": name,
            "url": url,
            "type": link_type,
            "icon_path": icon_name,
            "notes": notes,
            "last_used": last_used,
            "position": position,
            "category_id": category_id,
            "args": args,
            "is_favorite": is_favorite,
        }

        # Добавляем browser_key если указан
        if browser_key is not None:
            record["browser_key"] = browser_key

        # Добавляем ID если указан
        if link_id is not None:
            record["id"] = link_id

        return record


# Функции обратной совместимости
def make_link_record(
    name: str,
    url: str,
    link_type: str,
    icon_name: str,
    notes: str,
    last_used: Any,
    position: int,
    category_id: Optional[int],
    args: str,
    is_favorite: int,
    link_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Создает обычную запись ссылки (функция обратной совместимости)."""
    return LinkRecordFactory.create_link_record(
        name=name,
        url=url,
        link_type=link_type,
        icon_name=icon_name,
        notes=notes,
        last_used=last_used,
        position=position,
        category_id=category_id,
        args=args,
        is_favorite=is_favorite,
        link_id=link_id,
    )


def make_profile_link_record(
    link_name: str,
    url: str,
    link_type: str,
    icon_name: str,
    prof_args: str,
    notes: str,
    category_id: Optional[int],
    last_used: Any,
    position: int,
    link_id: Optional[int] = None,
    browser_key: Optional[str] = None,
) -> Dict[str, Any]:
    """Создает запись ссылки с профилем браузера (функция обратной совместимости)."""
    return LinkRecordFactory.create_link_record(
        name=link_name,
        url=url,
        link_type=link_type,
        icon_name=icon_name,
        notes=notes,
        last_used=last_used,
        position=position,
        category_id=category_id,
        args=prof_args,
        is_favorite=0,  # Профильные ссылки по умолчанию не в избранном
        link_id=link_id,
        browser_key=browser_key,
    )
