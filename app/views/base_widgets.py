"""Базовые виджеты для переиспользования в UI."""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QDrag, QDropEvent, QPixmap
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QLayout,
    QSizePolicy,
    QTableWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.config_data import app_config
from app.utils.ui.dnd.link import (
    extract_source_rows_from_mime as dnd_extract_source_rows,
)
from app.utils.ui.dnd.link import (
    get_current_order as dnd_get_current_order,
)
from app.utils.ui.dnd.link import (
    get_selected_rows as dnd_get_selected_rows,
)
from app.utils.ui.dnd.link import (
    move_rows_visually as dnd_move_rows_visually,
)
from app.utils.ui.dnd.mime import MimeDataParser, get_link_mime
from app.utils.ui.icon.icon_operations.creators import create_icon_from_path
from app.utils.ui.icon.icon_resolver import (
    get_default_icon_path,
    resolve_icon_for_link,
    resolve_icon_path,
)


class BasePanelWidget(QWidget):
    """Базовый виджет панели с цветным QFrame и layout."""
    
    def __init__(self):
        super().__init__()
        self.bg_frame = QFrame(self)
        self.bg_frame.setStyleSheet("border-radius: 0px;")
        self.layout = QHBoxLayout(self.bg_frame)
        self.layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(app_config.get_top_bar_buttons_spacing())
        self.layout.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self.bg_frame)


class BaseLinksPanelWidget(BasePanelWidget):
    """Базовый класс для панелей со ссылками."""
    
    linkClicked: pyqtSignal = pyqtSignal(object)
    
    def __init__(self, main_window=None, links_business=None):
        super().__init__()
        self._default_icon_path = None
    
    def _find_icon(self, icon_path: str) -> str:
        """Возвращает путь к иконке через общий резолвер с fallback."""
        if not icon_path:
            return str(self._get_default_icon_path())
        try:
            resolved = resolve_icon_path(icon_path)
            return resolved or str(self._get_default_icon_path())
        except Exception:
            return str(self._get_default_icon_path())

    def _create_link_button(self, link_data: Dict[str, Any]) -> QToolButton:
        """Создаёт кнопку ссылки с иконкой, синхронизированной с таблицей."""
        button = QToolButton()
        
        button_size = app_config.get_top_panel_button_size()
        icon_size = app_config.get_top_panel_icon_size()
        button.setFixedSize(button_size, button_size)
        button.setIconSize(icon_size)
        from PyQt6.QtWidgets import QSizePolicy
        button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        
        icon_path = resolve_icon_for_link(link_data)
        icon = create_icon_from_path(icon_path)
        button.setIcon(icon)
        
        button.setToolTip(link_data.get("name", "Неизвестная ссылка"))
        return button

    def _clear_layout(self):
        """Безопасно очищает layout от виджетов."""
        while self.layout.count():
            item = self.layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
    
    def _populate_panel(self, items: List[Dict[str, Any]], create_button_func) -> None:
        """Очищает панель и заполняет кнопками ссылок."""
        self._clear_layout()
        
        for link in items:
            try:
                button = create_button_func(link)
                if button is not None:
                    self.layout.addWidget(button)
            except Exception as exc:
                logging.warning("Не удалось создать кнопку для элемента панели: %s", exc)
                continue
        
        try:
            if self.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Expanding:
                self.layout.addStretch()
        except Exception:
            pass
    
    def _handle_link_click_base(self, link_info) -> None:
        """Эмитит сигнал `linkClicked` по клику по ссылке."""
        logging.debug("[BaseLinksPanelWidget] link clicked: %s", link_info)
        try:
            self.linkClicked.emit(link_info)
        except Exception as exc:
            logging.error("Не удалось эмитить сигнал linkClicked: %s", exc)
    
    def _get_default_icon_path(self) -> Path:
        """Возвращает путь к иконке по умолчанию."""
        return get_default_icon_path()


class BaseDragDropTableWidget(QTableWidget):
    """Базовый класс таблиц с поддержкой drag-and-drop."""
    
    items_reordered: pyqtSignal = pyqtSignal(list)
    
    MIME_TYPE = get_link_mime()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._sorting_enabled_before_drag = True
        self._setup_drag_drop()
    
    def _setup_drag_drop(self):
        """Настраивает параметры drag-and-drop."""
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSortingEnabled(True)
        self.setTabKeyNavigation(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    
    def mimeTypes(self):
        """Возвращает поддерживаемые MIME-типы."""
        return [self.MIME_TYPE]
    
    def mimeData(self, items):
        """Создаёт MIME-данные для перетаскивания."""
        try:
            item_ids = self._extract_item_ids_from_items(items)
            return MimeDataParser.create_mime_data(item_ids, self.MIME_TYPE)
        except Exception as e:
            logging.warning(f"Не удалось создать MIME данные: {e}")
            return None
    
    def _extract_item_ids_from_items(self, items) -> List[int]:
        """Извлекает ID из выбранных элементов."""
        raise NotImplementedError("Subclasses must implement _extract_item_ids_from_items")
    
    def startDrag(self, supportedActions):
        """Начинает операцию перетаскивания."""
        items = self.selectedItems()
        if not items:
            return
        
        self._sorting_enabled_before_drag = self.isSortingEnabled()
        if self._sorting_enabled_before_drag:
            self.setSortingEnabled(False)
            
        drag = QDrag(self)
        mime = self.mimeData(items)
        if mime is None:
            if self._sorting_enabled_before_drag:
                self.setSortingEnabled(True)
            return
            
        drag.setMimeData(mime)
        
        pixmap = self._create_drag_pixmap(items)
        if pixmap:
            drag.setPixmap(pixmap)
            drag.setHotSpot(pixmap.rect().center())
        
        drag.exec(supportedActions)
        
        if self._sorting_enabled_before_drag:
            self.setSortingEnabled(True)
    
    def dragEnterEvent(self, event):
        """Обрабатывает начало drag-операции."""
        if not hasattr(self, '_sorting_disabled_for_drag'):
            self._sorting_disabled_for_drag = self.isSortingEnabled()
            if self._sorting_disabled_for_drag:
                self.setSortingEnabled(False)
        super().dragEnterEvent(event)
    
    def dragLeaveEvent(self, event):
        """Обрабатывает выход из drag-зоны."""
        if hasattr(self, '_sorting_disabled_for_drag') and self._sorting_disabled_for_drag:
            self.setSortingEnabled(True)
            delattr(self, '_sorting_disabled_for_drag')
        super().dragLeaveEvent(event)
    
    def dropEvent(self, event: QDropEvent):
        """Обрабатывает drop для внутреннего перемещения строк."""
        if not self._is_internal_drop(event):
            super().dropEvent(event)
            return

        source_rows, target_row = self._get_drop_positions(event)
        if not self._is_valid_internal_drop(source_rows, target_row):
            event.ignore()
            return

        try:
            # Визуально перемещаем строки (поддержка множественного выделения)
            self._move_rows_visually(source_rows, target_row)
            event.acceptProposedAction()

            # Собираем ID в новом порядке и отправляем сигнал
            ids_in_order = self._get_current_order()
            if ids_in_order:
                self.items_reordered.emit(ids_in_order)
            else:
                logging.warning("[DROP] Не удалось собрать ID после перемещения")
                
        except Exception as e:
            logging.error(f"[DROP] Ошибка при перемещении строки: {e}")
            event.ignore()
        finally:
            if hasattr(self, '_sorting_disabled_for_drag') and self._sorting_disabled_for_drag:
                self.setSortingEnabled(True)
                delattr(self, '_sorting_disabled_for_drag')
    
    def _is_internal_drop(self, event) -> bool:
        """Проверяет, является ли это внутренним перемещением."""
        return event.source() == self
    
    def _get_selected_rows(self) -> List[int]:
        """Возвращает список выбранных строк."""
        return dnd_get_selected_rows(self)

    def _extract_source_rows_from_mime(self, event) -> List[int]:
        """Извлекает номера строк источника из MIME-данных."""
        return dnd_extract_source_rows(self, event, self.MIME_TYPE)

    def _extract_item_id_from_item(self, item) -> int:
        """Возвращает ID из элемента таблицы (переопределяется в наследниках)."""
        data = item.data(Qt.ItemDataRole.UserRole)
        if data is not None:
            try:
                if isinstance(data, int):
                    return data
                if isinstance(data, dict):
                    inner_id = data.get('id')
                    if inner_id is not None:
                        return int(inner_id)
                return int(str(data))
            except (TypeError, ValueError):
                logging.warning("[BaseTableView] Некорректный тип ID в UserRole: %r", data)
                raise NotImplementedError("Subclasses must implement _extract_item_id_from_item")
        raise NotImplementedError("Subclasses must implement _extract_item_id_from_item")

    def _get_drop_positions(self, event) -> tuple:
        """Возвращает позиции источника и цели для drop-операции."""
        if self._is_internal_drop(event):
            source_rows = self._extract_source_rows_from_mime(event)
            logging.debug(f"[DROP] extracted rows from MIME: {len(source_rows)}")
        else:
            source_rows = self._get_selected_rows()
            logging.debug(f"[DROP] selected rows: {len(source_rows)}")
        
        if not source_rows:
            return [], -1
        
        target_item = self.itemAt(event.position().toPoint())
        if not target_item:
            return source_rows, -1
            
        target_row = self.row(target_item)
        logging.debug(f"[DROP] target_row: {target_row}")
        return source_rows, target_row
    
    def _is_valid_internal_drop(self, source_rows: list, target_row: int) -> bool:
        """Проверяет валидность внутреннего перемещения."""
        if target_row == -1 or not source_rows:
            return False
        if target_row in source_rows:
            return False
        return True
    
    def _move_row_visually(self, source_row: int, target_row: int):
        """Визуально перемещает одну строку (переопределяется в наследниках)."""
        raise NotImplementedError("Subclasses must implement _move_row_visually")
    
    def _move_rows_visually(self, source_rows: list, target_row: int):
        """Визуально перемещает множество строк (централизовано)."""
        dnd_move_rows_visually(self, source_rows, target_row)
    
    def _get_current_order(self) -> List[int]:
        """Возвращает ID элементов в текущем порядке (централизовано)."""
        return dnd_get_current_order(self)
    
    def _create_drag_pixmap(self, items) -> Optional[QPixmap]:
        """Создаёт pixmap предпросмотра для drag-операции."""
        try:
            if items:
                rows = sorted(set(self.row(item) for item in items if item))
            else:
                rows = self._get_selected_rows()
            
            logging.debug(f"[PIXMAP] rows for drag pixmap: {len(rows)}")
            
            if not rows:
                return None
            
            row_count = len(rows)
            
            if row_count == 1:
                return self._create_single_row_pixmap(rows[0])
            else:
                return self._create_multi_row_pixmap(row_count)
                
        except Exception as e:
            logging.warning(f"Не удалось создать drag pixmap: {e}")
            return None
    
    def _create_single_row_pixmap(self, row: int) -> Optional[QPixmap]:
        """Создаёт pixmap для одной строки (первые колонки)."""
        try:
            texts = []
            max_cols = min(3, self.columnCount())
            
            for col in range(max_cols):
                item = self.item(row, col)
                if item and item.text().strip():
                    text = item.text()[:30]
                    if len(item.text()) > 30:
                        text += "..."
                    texts.append(text)
            
            if not texts:
                return self._create_default_pixmap()
            
            text = " | ".join(texts)
            return self._create_text_pixmap(text, single_row=True)
            
        except Exception as e:
            logging.warning(f"Ошибка создания single row pixmap: {e}")
            return self._create_default_pixmap()
    
    def _create_multi_row_pixmap(self, count: int) -> QPixmap:
        """Создаёт pixmap для множественного выделения со счётчиком."""
        text = f"{count} элементов"
        return self._create_text_pixmap(text, single_row=False)
    
    def _create_text_pixmap(self, text: str, single_row: bool = True) -> QPixmap:
        """Создаёт стилизованный pixmap с текстом."""
        from app.utils.ui.dnd.pixmap import create_text_pixmap
        return create_text_pixmap(text, single_row=single_row)
    
    def _create_default_pixmap(self) -> QPixmap:
        """Создаёт pixmap по умолчанию на случай ошибки."""
        from app.utils.ui.dnd.pixmap import create_default_pixmap
        return create_default_pixmap()
