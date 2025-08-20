import base64
import logging
import os
from collections import defaultdict
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from app.config_data import app_config


def parse_browser_bookmarks(html_path):
    with open(html_path, 'r', encoding='utf-8') as f:
        text = f.read()
        logging.getLogger(__name__).debug(f"DEBUG: file head = {text[:500]}")
    soup = BeautifulSoup(text, 'html.parser')
    categories = defaultdict(list)
    icons_dir = app_config.paths.get_link_icons_dir()

    def save_icon_from_base64(icon_data, url):
        domain = ''
        if url:
            domain = urlparse(url).netloc.replace(':', '_').replace('.', '_')
        if domain:
            icon_fname = f'web_{domain}.png'
        else:
            icon_fname = 'web_unknown.png'
        icon_file = icons_dir / icon_fname
        if not icon_file.exists():
            try:
                b64 = icon_data.split('base64,', 1)[-1]
                with open(icon_file, 'wb') as f:
                    f.write(base64.b64decode(b64))
            except Exception:
                return ''
        return icon_fname

    root_dl = soup.find('dl')
    logging.getLogger(__name__).debug(f"DEBUG: soup.find('dl') = {root_dl}")
    # Удалён лишний debug-код, оставлен только вызов walk_dl

    def process_node(node, current_cat):
        # Итерируемся по прямым дочерним элементам узла
        for child in node.find_all(recursive=False):
            if child.name == 'h3':
                # Нашли папку, обновляем текущую категорию для следующих ссылок на этом уровне
                current_cat = child.get_text()
            elif child.name == 'a':
                # Нашли ссылку, добавляем ее в текущую категорию
                if current_cat not in categories:
                    categories[current_cat] = []
                
                url = child.get('href')
                name = child.get_text() or url
                icon_data = child.get('icon')
                icon_path = ''
                if icon_data and icon_data.startswith('data:image/'):
                    icon_path = save_icon_from_base64(icon_data, url)

                link = {'name': name, 'url': url, 'icon_path': icon_path}
                categories[current_cat].append(link)
            elif child.name == 'dl':
                # Нашли вложенный список, рекурсивно обрабатываем его
                # с текущим именем категории (которое могло быть установлено тегом h3 выше)
                process_node(child, current_cat)
            elif child.name in ['p', 'dt']:
                 # Если встречаем теги-контейнеры, рекурсивно обрабатываем их содержимое
                 process_node(child, current_cat)

    if root_dl:
        process_node(root_dl, 'Без категории')
        total_links = sum(len(links) for links in categories.values())
        logging.getLogger(__name__).debug(f"DEBUG: Всего найдено ссылок: {total_links}")
    return dict(categories)


def import_browser_bookmarks_to_db(structure_business_logic, parent_widget, links_business_logic=None):
    from PyQt6.QtWidgets import QApplication, QDialog, QFileDialog

    from app.controllers.ui.dialogs.dialog_manager import DialogManager
    from app.views.dialogs.import_browser_dialog import ImportBrowserDialog

    path, _ = QFileDialog.getOpenFileName(parent_widget, "Импорт из браузера", "", "HTML Files (*.html)")
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
    added = 0
    for cat_name, links in categories.items():
        logging.getLogger(__name__).debug(f"DEBUG: Обработка категории '{cat_name}', ссылок: {len(links)}")
        
        # Получаем существующие категории через бизнес-логику
        categories_list = structure_business_logic.get_categories(section_id)
        cat_row = next((c for c in categories_list if c['name'] == cat_name and c['section_id'] == section_id), None)
        
        if not cat_row:
            logging.getLogger(__name__).debug(f"DEBUG: Категория '{cat_name}' не найдена, создаю новую...")
            from app.config_data import app_config
            category_icon = app_config.get_default_icons().get('category', 'category.png')
            
            # Создаем категорию через бизнес-логику
            category_data = {
                'name': cat_name,
                'section_id': section_id,
                'icon_path': category_icon
            }
            
            try:
                category_id = structure_business_logic.create_category_for_import(category_data)
                if category_id:
                    cat_row = {'id': category_id, 'name': cat_name, 'section_id': section_id}
                    logging.getLogger(__name__).debug(f"DEBUG: Категория '{cat_name}' создана: {cat_row}")
                else:
                    logging.getLogger(__name__).error(f"ERROR: Не удалось создать категорию '{cat_name}'!")
                    continue
            except Exception as e:
                logging.getLogger(__name__).error(f"ERROR: Ошибка создания категории '{cat_name}': {e}")
                continue
            QApplication.processEvents()
        else:
            logging.getLogger(__name__).debug(f"DEBUG: Категория '{cat_name}' уже существует: {cat_row}")
            category_id = cat_row['id']
        for link in links:
            QApplication.processEvents()
            icon_path = link.get('icon_path', '')
            url = link.get('url', '')
            name = link.get('name', '')
            
            logging.getLogger(__name__).debug(f"DEBUG: Проверка дубликата: name='{name}', url='{url}', category_id={category_id}")
            
            # Проверка на дубликат через бизнес-логику
            existing_links = structure_business_logic.get_links(category_id)
            existing = next((l for l in existing_links if l['url'] == url and l['name'] == name), None)
            
            logging.getLogger(__name__).debug(f"DEBUG: Результат поиска дубликата: {existing}")
            if existing:
                logging.getLogger(__name__).debug(f"DEBUG: Пропущен дубликат '{name}' ({url}) в категории '{cat_name}' (id={category_id})")
                continue
                
            # Создаем ссылку через бизнес-логику
            link_data = {
                'category_id': category_id,
                'name': link.get('name', ''),
                'url': link.get('url', ''),
                'type': 'web',
                'notes': '',
                'is_favorite': 0,
                'last_used': None,
                'icon_path': icon_path,
                'args': ''
            }
            
            try:
                # Используем LinksBusinessLogic если доступен, иначе fallback на прямой вызов модели
                if links_business_logic:
                    link_id = links_business_logic.create_link_for_import(link_data)
                else:
                    # Fallback: прямой вызов модели структуры для обратной совместимости
                    link_id = structure_business_logic.structure_model.create_link(link_data)
                    
                if link_id:
                    logging.getLogger(__name__).debug(f"DEBUG: Добавлена ссылка '{link.get('name', '')}' в категорию '{cat_name}' (id={category_id})")
                    added += 1
                else:
                    logging.getLogger(__name__).error(f"ERROR: Не удалось добавить ссылку '{link.get('name', '')}' в категорию '{cat_name}'")
            except Exception as e:
                logging.getLogger(__name__).error(f"ERROR: Не удалось добавить ссылку '{link.get('name', '')}' в категорию '{cat_name}': {e}")
    return True, f"Добавлено ссылок: {added}"

