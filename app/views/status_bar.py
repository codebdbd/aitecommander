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

    window.db_status_label = QLabel(app_config.get_db_connected_text())
    window.db_status_label.setObjectName("dbStatusLabel")
    window.path_label = QLabel("Путь: ")
    window.path_label.setObjectName("pathLabel")
    window.path_label.setMinimumWidth(app_config.get_path_label_min_width())
    window.links_count_label = QLabel(app_config.get_links_count_text())
    window.links_count_label.setObjectName("linksCountLabel")
    window.message_label = QLabel(app_config.get_status_ready_text())

    # Отступы внутри элементов для ровного визуала
    window.message_label.setContentsMargins(6, 0, 12, 0)
    window.path_label.setContentsMargins(0, 0, 12, 0)
    window.db_status_label.setContentsMargins(12, 0, 6, 0)
    window.links_count_label.setContentsMargins(6, 0, 6, 0)

    # Левая область: собственный контейнер с сообщением и путём, без перекрытия
    left_container = QWidget()
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
        # Счётчик ссылок
        links = getattr(window, "links", None)
        if links is not None:
            window.links_count_label.setText(f"Ссылок: {links.get_row_count()}")
        else:
            window.links_count_label.setText("Ссылок: 0")

        # Статус БД
        db = getattr(window, "db", None)
        if db is not None and db.is_connected():
            window.db_status_label.setText(app_config.get_db_connected_text())
        else:
            window.db_status_label.setText(app_config.get_db_disconnected_text())

        # Путь в дереве + активная сфера
        item = (
            getattr(window, "tree", None).currentItem()
            if hasattr(window, "tree") and window.tree
            else None
        )
        if item:
            parts = []
            node = item
            while node:
                text = node.text(0)
                if text:
                    parts.insert(0, text)
                node = node.parent()
            sb = getattr(window, "structure_business", None)
            if sb is not None and getattr(sb, "current_sphere_id", None):
                sphere_data = sb.get_sphere_by_id(sb.current_sphere_id)
                if sphere_data:
                    parts.insert(0, sphere_data["name"])

            # Добавляем имя выбранной ссылки из таблицы (колонка 1 — name), если есть выделение
            try:
                table = getattr(window, "table", None)
                if table is not None:
                    selection_model = table.selectionModel()
                    idx = (
                        table.currentIndex()
                        if table.currentIndex().isValid()
                        else (
                            selection_model.currentIndex() if selection_model else None
                        )
                    )
                    if idx and idx.isValid():
                        name_idx = idx.sibling(idx.row(), 1)
                        name_data = name_idx.data() if name_idx.isValid() else None
                        if isinstance(name_data, str) and name_data.strip():
                            parts.append(name_data.strip())
            except Exception:
                pass

            window.path_label.setText("Путь: " + " > ".join(parts))
        else:
            # Если нет текущего элемента — очищаем путь
            if hasattr(window, "path_label") and window.path_label:
                window.path_label.setText("Путь: ")
    except Exception:
        # В случае неожиданных ошибок не роняем UI, просто очищаем путь
        if hasattr(window, "path_label") and window.path_label:
            window.path_label.setText("Путь: ")
