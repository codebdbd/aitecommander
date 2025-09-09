# app/views/status_bar.py

from PyQt6.QtWidgets import QHBoxLayout, QLabel, QStatusBar, QWidget

from app.config_data import app_config


def setup_status_bar(window) -> QStatusBar:
    """Создаёт и настраивает статус-бар главного окна.

    Добавляет постоянные виджеты:
    - db_status_label: статус соединения с БД
    - path_label: путь по иерархии структуры
    - links_count_label: количество ссылок в текущем представлении

    Возвращает созданный QStatusBar.
    """
    status = QStatusBar(window)
    window.setStatusBar(status)
    # Внешние отступы статус-бара: слева/справа 6px
    status.setContentsMargins(6, 0, 6, 0)

    window.db_status_label = QLabel(app_config.ui.get_db_connected_text())
    window.db_status_label.setObjectName("dbStatusLabel")
    window.path_label = QLabel("Путь: ")
    window.path_label.setObjectName("pathLabel")
    window.path_label.setMinimumWidth(app_config.ui.get_path_label_min_width())
    window.links_count_label = QLabel(app_config.ui.get_links_count_text())
    window.links_count_label.setObjectName("linksCountLabel")
    window.message_label = QLabel(app_config.ui.get_status_ready_text())

    # Отступы внутри элементов для ровного визуала
    window.message_label.setContentsMargins(6, 0, 12, 0)
    window.path_label.setContentsMargins(0, 0, 12, 0)
    window.db_status_label.setContentsMargins(12, 0, 6, 0)
    window.links_count_label.setContentsMargins(6, 0, 6, 0)

    # Левая область: собственный контейнер с сообщением и путём, без перекрытия
    # Создаём контейнер сразу с родителем статус-бара, чтобы исключить кратковременный top-level показ
    left_container = QWidget(status)
    left_layout = QHBoxLayout(left_container)
    left_layout.setContentsMargins(0, 0, 0, 0)
    left_layout.setSpacing(0)
    left_layout.addWidget(window.message_label)
    left_layout.addWidget(window.path_label, 1)
    status.addWidget(left_container, 1)
    # Правая область: статус БД, счётчик ссылок
    status.addPermanentWidget(window.db_status_label)
    status.addPermanentWidget(window.links_count_label)

    return status


def update_status_bar(window) -> None:
    """Обновляет содержимое статус-бара для переданного окна.

    - Обновляет счётчик ссылок
    - Обновляет статус подключения к БД
    - Формирует путь текущего элемента структуры и активной сферы
    """
    try:
        def _set_text_if_changed(label, text: str) -> None:
            try:
                if label is None:
                    return
                current = label.text() if hasattr(label, "text") else None
                if current != text:
                    label.setText(text)
            except Exception:
                # Никогда не роняем UI из‑за статус‑бара
                pass

        # Счётчик: если активен режим плиток категорий — показываем количество категорий,
        # иначе показываем количество ссылок в таблице
        try:
            stack = getattr(window, "stack", None)
            tiles_active = False
            if stack is not None:
                tiles_index = app_config.ui.get_stack_index_tiles()
                try:
                    current_index = stack.currentIndex()
                except Exception:
                    current_index = None
                tiles_active = current_index == tiles_index
            if tiles_active and hasattr(window, "tiles") and window.tiles:
                try:
                    cats = int(window.tiles.get_categories_count())
                except Exception:
                    cats = 0
                _set_text_if_changed(window.links_count_label, f"Категорий: {cats}")
            else:
                links = getattr(window, "links", None)
                if links is not None:
                    _set_text_if_changed(
                        window.links_count_label, f"Ссылок: {links.get_row_count()}"
                    )
                else:
                    _set_text_if_changed(window.links_count_label, "Ссылок: 0")
        except Exception:
            # На случай непредвиденных ошибок — не роняем UI и показываем 0
            _set_text_if_changed(window.links_count_label, "Ссылок: 0")

        # Статус БД (через DatabaseController)
        dc = getattr(window, "database_controller", None)
        db = getattr(dc, "db", None)
        if db is not None and getattr(db, "is_connected", lambda: False)():
            _set_text_if_changed(
                window.db_status_label, app_config.ui.get_db_connected_text()
            )
        else:
            _set_text_if_changed(
                window.db_status_label, app_config.ui.get_db_disconnected_text()
            )

        # Путь в дереве + активная сфера (QTreeView-only)
        parts = []
        tree = getattr(window, "tree", None)
        try:
            if tree is not None:
                # Используем currentIndex и обходим родителей
                idx = tree.currentIndex()
                if idx and idx.isValid():
                    cur = idx
                    while cur.isValid():
                        text = cur.data()
                        if isinstance(text, str) and text:
                            parts.insert(0, text)
                        cur = cur.parent()
        except Exception:
            # Игнорируем сбои в построении пути
            parts = []

        # Префикс: активная сфера
        try:
            sb = getattr(window, "structure_business", None)
            if sb is not None and getattr(sb, "current_sphere_id", None):
                sphere_data = sb.get_sphere_by_id(sb.current_sphere_id)
                if sphere_data and isinstance(sphere_data.get("name"), str):
                    parts.insert(0, sphere_data["name"])
        except Exception:
            pass

        # Добавляем имя выбранной ссылки из таблицы (колонка 1 — name), если есть выделение
        try:
            table = getattr(window, "table", None)
            if table is not None:
                selection_model = table.selectionModel()
                idx = (
                    table.currentIndex()
                    if table.currentIndex().isValid()
                    else (selection_model.currentIndex() if selection_model else None)
                )
                if idx and idx.isValid():
                    name_idx = idx.sibling(idx.row(), 1)
                    name_data = name_idx.data() if name_idx.isValid() else None
                    if isinstance(name_data, str) and name_data.strip():
                        parts.append(name_data.strip())
        except Exception:
            pass

        if parts:
            _set_text_if_changed(window.path_label, "Путь: " + " > ".join(parts))
        else:
            if hasattr(window, "path_label") and window.path_label:
                _set_text_if_changed(window.path_label, "Путь: ")
    except Exception:
        # В случае неожиданных ошибок не роняем UI, просто очищаем путь
        if hasattr(window, "path_label") and window.path_label:
            try:
                _set_text_if_changed(window.path_label, "Путь: ")
            except Exception:
                pass
