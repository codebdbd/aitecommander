# app/views/base_widgets.py

"""
Базовые виджеты для переиспользования в UI.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from PyQt6.QtCore import Qt, QEvent, pyqtSignal
from PyQt6.QtGui import QDrag, QDropEvent, QPixmap, QKeySequence, QGuiApplication
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
from app.utils.ui.dnd.mime import MimeDataParser
from app.utils.ui.icon.icon_operations.creators import create_icon_from_path
from app.utils.ui.icon.path_service import icon_path_service


class BasePanelWidget(QWidget):
    """Базовый виджет панели с цветным QFrame и layout."""
    
    def __init__(self):
        super().__init__()
        self.bg_frame = QFrame(self)
        self.bg_frame.setStyleSheet("border-radius: 0px;")
        self.layout = QHBoxLayout(self.bg_frame)
        self.layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self.layout.setContentsMargins(0, 0, 0, 0)
        # Унификация spacing панелей с верхним тулбаром
        self.layout.setSpacing(app_config.get_top_bar_buttons_spacing())
        # ВАЖНО: фиксируем размер по содержимому, чтобы spacing между кнопками никогда не менялся
        self.layout.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)
        # По умолчанию панель не растягивается, размеры определяются содержимым
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self.bg_frame)


class BaseLinksPanelWidget(BasePanelWidget):
    """Базовый класс для панелей со ссылками."""
    
    # Сигнал слабой связанности: виджет сообщает наружу о клике по ссылке.
    # Передает исходный объект/словарь ссылки без привязки к доменным типам.
    linkClicked: pyqtSignal = pyqtSignal(object)
    
    def __init__(self, main_window=None, links_business=None):
        super().__init__()
        # Поля оставлены для обратной совместимости, но внутри класса не используются.
        self.main_window = main_window  # deprecated: не используется
        self.links_business = links_business  # deprecated: не используется
        self.link_opener = None
        self._default_icon_path = None
    
    def _find_icon(self, icon_path: str) -> str:
        """Находит путь к иконке, проверяя пользовательские, системные и дефолтные пути."""
        if not icon_path:
            return str(self._get_default_icon_path())
        
        # Проверяем пользовательскую иконку
        user_icon_path = icon_path_service.get_user_icons_dir() / icon_path
        if user_icon_path.exists():
            return str(user_icon_path)
        
        # Проверяем системную иконку
        ui_icon_path = icon_path_service.get_ui_icons_dir() / icon_path
        if ui_icon_path.exists():
            return str(ui_icon_path)
        
        # Fallback на дефолтную иконку
        return str(self._get_default_icon_path())

    def _create_link_button(self, link_data: Dict[str, Any]) -> QToolButton:
        """Общий метод создания кнопки ссылки."""
        button = QToolButton()
        
        # Используем единые параметры для всех кнопок топпанели
        button_size = app_config.get_top_panel_button_size()
        icon_size = app_config.get_top_panel_icon_size()
        button.setFixedSize(button_size, button_size)
        button.setIconSize(icon_size)
        # Не позволяем лейаутам сжимать кнопку — она фиксированная
        from PyQt6.QtWidgets import QSizePolicy
        button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        
        # Находим и создаем иконку
        icon_path = self._find_icon(link_data.get("icon_path", ""))
        icon = create_icon_from_path(icon_path)
        button.setIcon(icon)
        
        button.setToolTip(link_data.get("name", "Неизвестная ссылка"))
        return button

    def _clear_layout(self):
        """Безопасно удаляет все виджеты из layout."""
        while self.layout.count():
            item = self.layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
    
    def _handle_link_click_base(self, link_info) -> None:
        """Базовый обработчик клика по кнопке ссылки.
        
        Больше не выполняет действий сам: только эмитит сигнал `linkClicked`.
        Обработчик (главное окно/контроллер) принимает решение, что делать.
        """
        logging.info("[BaseLinksPanelWidget] link clicked: %s", link_info)
        try:
            self.linkClicked.emit(link_info)
        except Exception as exc:
            logging.error("Не удалось эмитить сигнал linkClicked: %s", exc)
    
    def _get_default_icon_path(self) -> Path:
        """Получает путь к иконке по умолчанию."""
        return icon_path_service.get_ui_icons_dir() / "star.ico"


class BaseDragDropTableWidget(QTableWidget):
    """Базовый класс для таблиц с drag-and-drop функциональностью."""
    
    # Сигналы
    items_reordered: pyqtSignal = pyqtSignal(list)  # List[int] - ID элементов в новом порядке
    external_os_drop: pyqtSignal = pyqtSignal(list)  # List[str] - строки/URI из внешнего DnD
    
    # Константы
    MIME_TYPE = app_config.get('settings.mime_types.internal_item', 'application/x-item-id')
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._sorting_enabled_before_drag = True
        self._setup_drag_drop()
    
    def _setup_drag_drop(self):
        """Настройка параметров drag-and-drop."""
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        # Важно для QAbstractItemView: события dnd приходят на viewport
        try:
            self.viewport().setAcceptDrops(True)
            # Устанавливаем фильтр событий, чтобы гарантированно ловить drag/drop на viewport
            self.viewport().installEventFilter(self)
        except Exception:
            pass
        # Разрешаем как внутренние перемещения, так и внешние drop'ы
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        # Показываем индикатор допустимого места для дропа
        try:
            self.setDropIndicatorShown(True)
        except Exception:
            pass
        # Для внешних дропов из ОС по умолчанию корректно использовать Copy
        try:
            self.setDefaultDropAction(Qt.DropAction.CopyAction)
        except Exception:
            pass
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSortingEnabled(True)
        self.setTabKeyNavigation(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    
    def mimeTypes(self):
        """Возвращает поддерживаемые MIME типы."""
        return [self.MIME_TYPE]
    
    def mimeData(self, items):
        """Создает MIME данные для перетаскиваемых элементов."""
        try:
            item_ids = self._extract_item_ids_from_items(items)
            
            # Используем централизованный парсер для создания MIME данных
            return MimeDataParser.create_mime_data(item_ids, self.MIME_TYPE)
        except Exception as e:
            logging.warning(f"Не удалось создать MIME данные: {e}")
            return None
    
    def _extract_item_ids_from_items(self, items) -> List[int]:
        """Извлекает ID элементов из выбранных элементов."""
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
        
        result = drag.exec(supportedActions)
        
        if self._sorting_enabled_before_drag:
            self.setSortingEnabled(True)
    
    def dragEnterEvent(self, event):
        """Обрабатывает начало drag операции над виджетом."""
        if not hasattr(self, '_sorting_disabled_for_drag'):
            self._sorting_disabled_for_drag = self.isSortingEnabled()
            if self._sorting_disabled_for_drag:
                self.setSortingEnabled(False)

        mime = event.mimeData()
        # Разрешаем внешние OS-дропы (urls/text/html), помимо внутренних
        if mime and (mime.hasUrls() or mime.hasText() or getattr(mime, 'hasHtml', lambda: False)()):
            try:
                logging.info("[DnD] dragEnter: formats=%s, hasUrls=%s, hasText=%s, hasHtml=%s",
                              getattr(mime, 'formats', lambda: [])(),
                              mime.hasUrls(), mime.hasText(), getattr(mime, 'hasHtml', lambda: False)())
            except Exception:
                pass
            try:
                event.setDropAction(Qt.DropAction.CopyAction)
            except Exception:
                pass
            event.acceptProposedAction()
            return

        super().dragEnterEvent(event)
    
    def dragLeaveEvent(self, event):
        """Обрабатывает выход из drag зоны."""
        if hasattr(self, '_sorting_disabled_for_drag') and self._sorting_disabled_for_drag:
            self.setSortingEnabled(True)
            delattr(self, '_sorting_disabled_for_drag')
        super().dragLeaveEvent(event)

    def dragMoveEvent(self, event):
        """Принимаем перемещение для внешних OS-дропов, иначе будет 'знак стоп'."""
        mime = event.mimeData()
        if mime and (mime.hasUrls() or mime.hasText() or getattr(mime, 'hasHtml', lambda: False)()):
            try:
                logging.info("[DnD] dragMove: formats=%s, hasUrls=%s, hasText=%s, hasHtml=%s",
                              getattr(mime, 'formats', lambda: [])(),
                              mime.hasUrls(), mime.hasText(), getattr(mime, 'hasHtml', lambda: False)())
            except Exception:
                pass
            try:
                event.setDropAction(Qt.DropAction.CopyAction)
            except Exception:
                pass
            event.acceptProposedAction()
            return
        # По умолчанию — стандартное поведение для внутренних перемещений
        super().dragMoveEvent(event)

    def eventFilter(self, obj, event):
        """Гарантированная обработка DnD на viewport для внешних источников."""
        try:
            if obj is self.viewport():
                if event.type() == QEvent.Type.DragEnter:
                    mime = event.mimeData()
                    if mime and (mime.hasUrls() or mime.hasText() or getattr(mime, 'hasHtml', lambda: False)()):
                        try:
                            logging.info("[DnD] viewport DragEnter: formats=%s", getattr(mime, 'formats', lambda: [])())
                        except Exception:
                            pass
                        try:
                            event.setDropAction(Qt.DropAction.CopyAction)
                        except Exception:
                            pass
                        event.acceptProposedAction()
                        return True
                elif event.type() == QEvent.Type.DragMove:
                    mime = event.mimeData()
                    if mime and (mime.hasUrls() or mime.hasText() or getattr(mime, 'hasHtml', lambda: False)()):
                        try:
                            logging.info("[DnD] viewport DragMove: formats=%s", getattr(mime, 'formats', lambda: [])())
                        except Exception:
                            pass
                        try:
                            event.setDropAction(Qt.DropAction.CopyAction)
                        except Exception:
                            pass
                        event.acceptProposedAction()
                        return True
                elif event.type() == QEvent.Type.Drop:
                    mime = event.mimeData()
                    if mime and not self._is_internal_drop(event) and (mime.hasUrls() or mime.hasText() or getattr(mime, 'hasHtml', lambda: False)()):
                        try:
                            strings = self._extract_strings_from_mime(mime)
                            if strings:
                                self.external_os_drop.emit(strings)
                        except Exception:
                            logging.exception("[DnD] Ошибка обработки внешнего drop на viewport")
                        event.acceptProposedAction()
                        return True
        except Exception:
            logging.exception("[DnD] Ошибка в eventFilter")
        return super().eventFilter(obj, event)
    
    def dropEvent(self, event: QDropEvent):
        """Обрабатывает событие drop. Поддерживает внутренний move и внешний OS drop (urls/text)."""
        # Внешний дроп из ОС (файлы/URL/текст)
        mime = event.mimeData()
        if mime and not self._is_internal_drop(event) and (mime.hasUrls() or mime.hasText() or getattr(mime, 'hasHtml', lambda: False)()):
            try:
                strings = self._extract_strings_from_mime(mime)
                if strings:
                    self.external_os_drop.emit(strings)
                    event.acceptProposedAction()
                    return
                else:
                    event.ignore()
                    return
            except Exception as e:
                logging.error(f"[DROP] Ошибка обработки внешнего дропа: {e}")
                event.ignore()
                return

        # Внутреннее перемещение строк
        if not self._is_internal_drop(event):
            super().dropEvent(event)
            return

        source_rows, target_row = self._get_drop_positions(event)
        if not self._is_valid_internal_drop(source_rows, target_row):
            event.ignore()
            return

        try:
            # Визуально перемещаем строки (обрабатываем множественное выделение)
            self._move_rows_visually(source_rows, target_row)
            event.acceptProposedAction()

            # Собираем все ID в новом порядке и отправляем сигнал
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

    def keyPressEvent(self, event):
        """Поддержка вставки ссылок из буфера обмена (Ctrl+V)."""
        try:
            # Проверяем стандартное соответствие комбинации вставки
            if hasattr(event, 'matches') and event.matches(QKeySequence.StandardKey.Paste):
                cb = QGuiApplication.clipboard()
                mime = cb.mimeData() if cb else None
                if mime:
                    try:
                        strings = self._extract_strings_from_mime(mime)
                        if strings:
                            self.external_os_drop.emit(strings)
                            event.accept()
                            return
                    except Exception:
                        logging.exception("[DnD] Ошибка обработки вставки из буфера обмена")
        except Exception:
            # Никогда не ломаем стандартную обработку клавиш
            pass
        super().keyPressEvent(event)

    def _extract_strings_from_mime(self, mime) -> List[str]:
        """Извлекает список строк из QMimeData (urls, текст построчно, html)."""
        results: List[str] = []
        try:
            if mime.hasUrls():
                for qurl in mime.urls():
                    try:
                        # toString сохраняет схему для http/https/file
                        url_str = qurl.toString()
                        if url_str:
                            results.append(url_str)
                    except Exception:
                        continue
            if mime.hasText():
                try:
                    text = mime.text()
                    if text:
                        for line in text.splitlines():
                            line = line.strip()
                            if line:
                                results.append(line)
                except Exception:
                    pass
            # Некоторые браузеры дают только HTML
            if getattr(mime, 'hasHtml', lambda: False)():
                try:
                    html = mime.html()
                    if html:
                        # Простой парсер ссылок из HTML
                        import re
                        for m in re.finditer(r"href=[\"']([^\"']+)[\"']", html, re.IGNORECASE):
                            href = m.group(1).strip()
                            if href:
                                results.append(href)
                except Exception:
                    pass
        except Exception as e:
            logging.debug(f"_extract_strings_from_mime error: {e}")
        return results
    
    def _is_internal_drop(self, event) -> bool:
        """Проверяет, является ли это внутренним перемещением."""
        return event.source() == self
    
    def _get_selected_rows(self) -> List[int]:
        """Получает список выбранных строк более надежным способом."""
        # Используем selectionModel для получения выбранных строк
        selection_model = self.selectionModel()
        if not selection_model:
            return []
        
        selected_rows = set()
        
        # Получаем все выбранные индексы
        selected_indexes = selection_model.selectedIndexes()
        for index in selected_indexes:
            if index.isValid():
                selected_rows.add(index.row())
        
        # Альтернативный способ через selectedRanges
        if not selected_rows:
            for selection_range in selection_model.selectedRanges():
                for row in range(selection_range.top(), selection_range.bottom() + 1):
                    selected_rows.add(row)
        
        return sorted(list(selected_rows))

    def _extract_source_rows_from_mime(self, event) -> List[int]:
        """Извлекает номера строк источника из MIME данных."""
        try:
            # Используем централизованный парсер
            from app.utils.ui.dnd.mime import MimeDataParser
            
            item_ids = MimeDataParser.extract_item_ids(event.mimeData(), self.MIME_TYPE)
            if not item_ids:
                return []
            
            # Находим строки для этих ID
            source_rows = []
            for row in range(self.rowCount()):
                item = self.item(row, 0)
                if item:
                    try:
                        # Извлекаем ID из элемента (должно быть реализовано в наследниках)
                        item_id = self._extract_item_id_from_item(item)
                        if item_id in item_ids:
                            source_rows.append(row)
                    except:
                        continue
            
            return sorted(source_rows)
            
        except Exception as e:
            logging.warning(f"[DROP] Ошибка извлечения строк из MIME: {e}")
            # Fallback к текущему выделению
            return self._get_selected_rows()

    def _extract_item_id_from_item(self, item) -> int:
        """Извлекает ID из элемента таблицы. Должен быть переопределен в наследниках."""
        # Базовая реализация - пытаемся получить ID из data()
        data = item.data(Qt.ItemDataRole.UserRole)
        if data is not None:
            try:
                # 1) Если это уже целое число
                if isinstance(data, int):
                    return data
                # 2) Если это словарь с ключом 'id'
                if isinstance(data, dict):
                    inner_id = data.get('id')
                    if inner_id is not None:
                        return int(inner_id)
                # 3) Если это строка, попробуем преобразовать
                return int(str(data))
            except (TypeError, ValueError):
                logging.warning("[BaseTableView] Некорректный тип ID в UserRole: %r", data)
                # Сохраняем контракт базового класса: требуется переопределение
                raise NotImplementedError("Subclasses must implement _extract_item_id_from_item")
        raise NotImplementedError("Subclasses must implement _extract_item_id_from_item")

    def _get_drop_positions(self, event) -> tuple:
        """Получает позиции источника и цели для drop операции."""
        # Для внутреннего drop получаем информацию из MIME данных
        if self._is_internal_drop(event):
            source_rows = self._extract_source_rows_from_mime(event)
            logging.info(f"[DROP] Extracted from MIME: {len(source_rows)} rows: {source_rows}")
        else:
            # Для внешнего drop используем текущее выделение
            source_rows = self._get_selected_rows()
            logging.info(f"[DROP] _get_selected_rows() returned {len(source_rows)} rows: {source_rows}")
        
        if not source_rows:
            return [], -1
        
        target_item = self.itemAt(event.position().toPoint())
        if not target_item:
            return source_rows, -1
            
        target_row = self.row(target_item)
        logging.info(f"[DROP] target_row: {target_row}")
        return source_rows, target_row
    
    def _is_valid_internal_drop(self, source_rows: list, target_row: int) -> bool:
        """Проверяет валидность внутреннего перемещения."""
        if target_row == -1 or not source_rows:
            return False
        
        # Нельзя перемещать строку саму на себя
        if target_row in source_rows:
            return False
            
        return True
    
    def _move_row_visually(self, source_row: int, target_row: int):
        """Визуально перемещает одну строку в таблице.
        
        Этот метод должен быть переопределен в наследующих классах
        для корректного перемещения строк с учетом специфики данных.
        """
        raise NotImplementedError("Subclasses must implement _move_row_visually")
    
    def _move_rows_visually(self, source_rows: list, target_row: int):
        """Визуально перемещает множество строк в таблице."""
        if len(source_rows) == 1:
            self._move_row_visually(source_rows[0], target_row)
        else:
            offset = 0
            for i, source_row in enumerate(reversed(source_rows)):
                adjusted_target = target_row + (len(source_rows) - 1 - i)
                if source_row < target_row:
                    adjusted_target -= 1
                self._move_row_visually(source_row, adjusted_target)
    
    def _get_current_order(self) -> List[int]:
        """
        Возвращает ID всех элементов в текущем порядке отображения.
        
        Вызывается после drag-and-drop для эмиссии сигнала items_reordered.
        Должен быть переопределен в наследующих классах.
        
        Returns:
            List[int]: ID элементов от первой до последней строки
        """
        raise NotImplementedError(
            "Subclasses must implement _get_current_order to return a list of all item IDs "
            "in their current table order. This is used to emit the items_reordered signal "
            "after successful drag-and-drop operations."
        )
    
    def _create_drag_pixmap(self, items) -> Optional[QPixmap]:
        """Создает визуальное представление для drag операции."""
        try:
            # Если items переданы, извлекаем строки из них
            if items:
                rows = sorted(set(self.row(item) for item in items if item))
            else:
                # Иначе используем надежный способ получения выбранных строк
                rows = self._get_selected_rows()
            
            logging.info(f"[PIXMAP] Using {len(rows)} rows for drag pixmap: {rows}")
            
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
        """Создает pixmap для одной строки с содержимым первых колонок."""
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
        """Создает pixmap для множественного выделения с счетчиком."""
        text = f"{count} элементов"
        return self._create_text_pixmap(text, single_row=False)
    
    def _create_text_pixmap(self, text: str, single_row: bool = True) -> QPixmap:
        """Создает стилизованный pixmap с текстом."""
        from app.utils.ui.dnd.pixmap import create_text_pixmap
        return create_text_pixmap(text, single_row=single_row)
    
    def _create_default_pixmap(self) -> QPixmap:
        """Создает pixmap по умолчанию для случаев ошибки."""
        from app.utils.ui.dnd.pixmap import create_default_pixmap
        return create_default_pixmap()
