import base64
import logging
from collections import defaultdict
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from app.config_data import app_config
from app.utils.ui.icon.icon_resolver import resolve_icon_for_link

logger = logging.getLogger(__name__)


def parse_browser_bookmarks(html_path):
    # Пытаемся определить корректную кодировку, чтобы избежать 
    # обрезанных символов (\ufffd) в названиях категорий.
    encodings_to_try = ("utf-8", "utf-8-sig", "cp1251", "latin-1")
    last_err = None
    text = None
    used_encoding = None
    for enc in encodings_to_try:
        try:
            with open(html_path, "r", encoding=enc) as f:
                text = f.read()
                used_encoding = enc
                break
        except Exception as e:
            last_err = e
            continue
    if text is None:
        # Последняя попытка — читаем байты и декодируем с заменой символов
        try:
            with open(html_path, "rb") as fb:
                raw = fb.read()
                text = raw.decode("utf-8", errors="replace")
                used_encoding = "utf-8(replace)"
        except Exception as e:
            raise last_err or e
    logger.debug(f"DEBUG: using encoding = {used_encoding}")
    logger.debug(f"DEBUG: file head = {text[:500]}")
    soup = BeautifulSoup(text, "html.parser")
    categories = defaultdict(list)
    icons_dir = app_config.paths.get_link_icons_dir()

    def save_icon_from_base64(icon_data, url):
        domain = ""
        if url:
            domain = urlparse(url).netloc.replace(":", "_").replace(".", "_")
        if domain:
            icon_fname = f"web_{domain}.png"
        else:
            icon_fname = "web_unknown.png"
        icon_file = icons_dir / icon_fname
        if not icon_file.exists():
            try:
                b64 = icon_data.split("base64,", 1)[-1]
                with open(icon_file, "wb") as f:
                    f.write(base64.b64decode(b64))
            except Exception:
                return ""
        return icon_fname

    root_dl = soup.find("dl")
    logger.debug(f"DEBUG: soup.find('dl') = {root_dl}")
    # Удалён лишний debug-код, оставлен только вызов walk_dl

    def process_node(node, current_cat):
        # Итерируемся по прямым дочерним элементам узла
        for child in node.find_all(recursive=False):
            if child.name == "h3":
                # Нашли папку, обновляем текущую категорию для следующих ссылок на этом уровне
                current_cat = child.get_text()
            elif child.name == "a":
                # Нашли ссылку, добавляем ее в текущую категорию
                if current_cat not in categories:
                    categories[current_cat] = []

                url = child.get("href")
                name = child.get_text() or url
                icon_data = child.get("icon")
                icon_path = ""
                if icon_data and icon_data.startswith("data:image/"):
                    icon_path = save_icon_from_base64(icon_data, url)

                link = {"name": name, "url": url, "icon_path": icon_path}
                categories[current_cat].append(link)
            elif child.name == "dl":
                # Нашли вложенный список, рекурсивно обрабатываем его
                # с текущим именем категории (которое могло быть установлено тегом h3 выше)
                process_node(child, current_cat)
            elif child.name in ["p", "dt"]:
                # Если встречаем теги-контейнеры, рекурсивно обрабатываем их содержимое
                process_node(child, current_cat)

    if root_dl:
        process_node(root_dl, "Без категории")
        total_links = sum(len(links) for links in categories.values())
        logger.debug(f"DEBUG: Всего найдено ссылок: {total_links}")
    return dict(categories)


def import_browser_bookmarks_to_db(
    structure_business_logic, parent_widget, links_business_logic=None
):
    from PyQt6.QtWidgets import QApplication, QDialog, QFileDialog

    from app.controllers.ui.dialogs.dialog_manager import DialogManager
    from app.views.dialogs.import_browser_dialog import ImportBrowserDialog

    path, _ = QFileDialog.getOpenFileName(
        parent_widget, "Импорт из браузера", "", "HTML Files (*.html *.htm)"
    )
    if not path:
        return False, "Файл не выбран"
    try:
        categories = parse_browser_bookmarks(path)
    except Exception as e:
        DialogManager.show_error(
            parent_widget,
            "Импорт из браузера",
            "Ошибка чтения HTML файла.",
            informative_text="Проверьте целостность файла и права доступа.",
            details=str(e),
        )
        return False, f"Ошибка чтения HTML: {e}"
    if not any(categories.values()):
        DialogManager.show_warning(
            parent_widget,
            "Импорт из браузера",
            "В файле не найдено ни одной ссылки.",
            informative_text="Экспортируйте закладки из браузера в формате HTML и выберите корректный файл.",
            details=f"file={path}",
        )
        return False, "В файле не найдено ни одной ссылки."

    dlg = ImportBrowserDialog(structure_business_logic, parent_widget)
    if dlg.exec() != QDialog.DialogCode.Accepted:
        return False, "Категория не выбрана"
    section_id = dlg.get_selected_section_id()
    if not section_id:
        DialogManager.show_warning(
            parent_widget,
            "Импорт из браузера",
            "Не выбран раздел для импорта.",
            informative_text="Выберите раздел, в который будут добавлены категории и ссылки.",
        )
        return False, "Не выбран раздел для импорта."
    # === Оптимизация: создаём недостающие категории пакетно ===
    # 1) Получаем список существующих категорий раздела единым запросом
    existing_categories = structure_business_logic.get_categories(section_id) or []
    existing_names = {c.get("name") for c in existing_categories}

    # 2) Определяем, какие категории отсутствуют
    incoming_names = set(categories.keys())
    missing_names = [n for n in incoming_names if n not in existing_names]

    # 3) Готовим батч для вставки недостающих категорий
    try:
        default_icon = resolve_icon_for_link({"type": "category", "icon_path": ""})
    except Exception:
        default_icon = ""
    bulk_items = [
        {"name": name, "section_id": section_id, "icon_path": default_icon}
        for name in missing_names
    ]
    if bulk_items:
        try:
            created = structure_business_logic.create_categories_bulk(bulk_items) or []
            logger.debug(
                f"DEBUG: Пакетно создано/подтверждено категорий: {len(created)} для раздела {section_id}"
            )
        except Exception as e:
            logger.error(f"ERROR: Пакетное создание категорий завершилось ошибкой: {e}")
            created = []
        QApplication.processEvents()
    else:
        created = []

    # 4) Строим маппинг имя -> id по актуальному состоянию (после bulk)
    #    Чтобы гарантированно иметь id для всех parsed категорий, перечитаем список
    categories_after = structure_business_logic.get_categories(section_id) or []
    name_to_id = {c.get("name"): c.get("id") for c in categories_after}

    added = 0
    for cat_name, links in categories.items():
        logger.debug(f"DEBUG: Обработка категории '{cat_name}', ссылок: {len(links)}")
        category_id = name_to_id.get(cat_name)
        if not category_id:
            logger.error(
                f"ERROR: Не найден ID категории '{cat_name}' после пакетной вставки; пропуск ссылок"
            )
            continue

        # Подготовим набор уже существующих (name, url) для быстрого поиска дубликатов
        existing_name_url = set()
        try:
            if links_business_logic:
                existing_links = links_business_logic.get_links_for_category(category_id)
            elif hasattr(structure_business_logic, "links_business"):
                existing_links = structure_business_logic.links_business.get_links_for_category(category_id)
            else:
                existing_links = []
        except Exception as e:
            logger.warning(
                f"Не удалось получить существующие ссылки для категории {category_id}: {e}"
            )
            existing_links = []

        for el in existing_links:
            try:
                existing_name_url.add((str(el.get("name", "")).strip(), str(el.get("url", "")).strip()))
            except Exception:
                # Игнорируем некорректные записи
                pass

        for link in links:
            QApplication.processEvents()
            icon_path = link.get("icon_path", "")
            url = link.get("url", "")
            name = link.get("name", "")

            logger.debug(
                f"DEBUG: Проверка дубликата: name='{name}', url='{url}', category_id={category_id}"
            )

            # Быстрая проверка на дубликат
            if (name.strip(), url.strip()) in existing_name_url:
                logger.debug(
                    f"DEBUG: Пропущен дубликат '{name}' ({url}) в категории '{cat_name}' (id={category_id})"
                )
                continue

            # Создаем ссылку через бизнес-логику
            link_data = {
                "category_id": category_id,
                "name": link.get("name", ""),
                "url": link.get("url", ""),
                "type": "web",
                "notes": "",
                "is_favorite": 0,
                "last_used": None,
                "icon_path": icon_path,
                "args": "",
            }

            try:
                # Используем LinksBusinessLogic если доступен, иначе fallback на прямой вызов модели
                if links_business_logic:
                    link_id = links_business_logic.create_link_for_import(link_data)
                else:
                    # Используем LinksService через бизнес-логику
                    link_id = (
                        structure_business_logic.links_business.create_link_for_import(
                            link_data
                        )
                        if hasattr(structure_business_logic, "links_business")
                        else None
                    )

                if link_id:
                    logger.debug(
                        f"DEBUG: Добавлена ссылка '{link.get('name', '')}' в категорию '{cat_name}' (id={category_id})"
                    )
                    added += 1
                else:
                    logger.error(
                        f"ERROR: Не удалось добавить ссылку '{link.get('name', '')}' в категорию '{cat_name}'"
                    )
            except Exception as e:
                logger.error(
                    f"ERROR: Не удалось добавить ссылку '{link.get('name', '')}' в категорию '{cat_name}': {e}"
                )
    return True, f"Добавлено ссылок: {added}"
