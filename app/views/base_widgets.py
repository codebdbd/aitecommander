"""Базовые виджеты для переиспользования в UI."""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QDrag, QDropEvent, QPixmap
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QLayout,
    QSizePolicy,
    QTableView,
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
        button.setIconSize(QSize(icon_size[0], icon_size[1]))
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
                logging.warning(
                    "Не удалось создать кнопку для элемента панели: %s", exc
                )
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


class BaseDragDropTableWidget(QTableView):
    """Базовый класс таблиц с поддержкой drag-and-drop (QTableView).

    Важно: класс сохраняет имя для обратной совместимости, но теперь наследуется от QTableView
    и использует модельно-индексный подход.
    """

    items_reordered: pyqtSignal = pyqtSignal(list)

    MIME_TYPE = get_link_mime()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._sorting_enabled_before_drag = True
        # Флаг состояния временного отключения сортировки во время DnD
        self._sorting_disabled_for_drag: bool = False
        self._setup_drag_drop()

    def _setup_drag_drop(self):
        """Настраивает параметры drag-and-drop."""
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        try:
            # Важно для QAbstractScrollArea-потомков: события приходят на viewport
            self.viewport().setAcceptDrops(True)
            # Перехватываем события DnD напрямую на viewport
            self.viewport().installEventFilter(self)
        except (AttributeError, RuntimeError) as e:
            logging.warning("_setup_drag_drop: viewport DnD setup failed: %s", e)
            # Критично: без viewport acceptDrops/eFilter DnD может работать некорректно
            # Пробрасываем дальше, чтобы не скрывать проблему окружения/платформы
            raise
        # Используем DragDrop: обработку перемещения делаем сами в dropEvent
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        # Не перезаписываем ячейки при дропе, а перемещаем строки
        try:
            self.setDragDropOverwriteMode(False)
        except (AttributeError, RuntimeError) as e:
            logging.warning("_setup_drag_drop: setDragDropOverwriteMode unsupported: %s", e)
        # По умолчанию перемещение
        try:
            self.setDefaultDropAction(Qt.DropAction.MoveAction)
        except (AttributeError, RuntimeError) as e:
            logging.warning("_setup_drag_drop: setDefaultDropAction unsupported: %s", e)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        try:
            self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        except (AttributeError, RuntimeError) as e:
            logging.warning("_setup_drag_drop: setSelectionMode unsupported: %s", e)
        try:
            self.setDropIndicatorShown(True)
        except (AttributeError, RuntimeError) as e:
            logging.warning("_setup_drag_drop: setDropIndicatorShown unsupported: %s", e)
        self.setSortingEnabled(True)
        self.setTabKeyNavigation(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def eventFilter(self, obj, event):
        """Форсируем обработку DnD-событий, приходящих на viewport().

        Некоторые реализации Qt отправляют drag/drop события непосредственно на viewport,
        поэтому перехватываем их и перенаправляем в наши обработчики.
        """
        try:
            from PyQt6.QtCore import QEvent
        except Exception:
            return super().eventFilter(obj, event)

        if obj is self.viewport():
            et = event.type()
            if et == QEvent.Type.DragEnter:
                self.dragEnterEvent(event)
                return event.isAccepted()
            if et == QEvent.Type.DragMove:
                self.dragMoveEvent(event)
                return event.isAccepted()
            if et == QEvent.Type.DragLeave:
                self.dragLeaveEvent(event)
                return True
            if et == QEvent.Type.Drop:
                self.dropEvent(event)
                return event.isAccepted()
        return super().eventFilter(obj, event)

    def mimeTypes(self):
        """Возвращает поддерживаемые MIME-типы."""
        return [self.MIME_TYPE]

    def mimeData(self, items):
        """Создаёт MIME-данные для перетаскивания.

        items может быть списком QModelIndex.
        """
        try:
            item_ids = self._extract_item_ids_from_items(items)
            return MimeDataParser.create_mime_data(item_ids, self.MIME_TYPE)
        except Exception as e:
            logging.warning(f"Не удалось создать MIME данные: {e}")
            return None

    def _extract_item_ids_from_items(self, items) -> List[int]:
        """Извлекает ID из выбранных элементов."""
        raise NotImplementedError(
            "Subclasses must implement _extract_item_ids_from_items"
        )

    def startDrag(self, supportedActions):
        """Начинает операцию перетаскивания."""
        sm = self.selectionModel()
        if not sm:
            return
        items = sm.selectedIndexes()
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

        # Форсируем поведение перемещения
        try:
            drag.exec(Qt.DropAction.MoveAction)
        except Exception:
            drag.exec(supportedActions)

        # Не включаем сортировку обратно здесь. Решение о состоянии сортировки
        # принимается в dropEvent():
        # - при успешном переносе сортировку оставляем ВЫКЛ, чтобы видно было ручной порядок
        # - при неуспешном переносе возвращаем в исходное состояние

    def dragEnterEvent(self, event):
        """Обрабатывает начало drag-операции."""
        if not self._sorting_disabled_for_drag:
            # Запоминаем, была ли включена сортировка, и временно отключаем её
            self._sorting_disabled_for_drag = self.isSortingEnabled()
            if self._sorting_disabled_for_drag:
                self.setSortingEnabled(False)
        # Явно принимаем наш MIME при внутреннем переносе
        try:
            if self._is_internal_drop(event) and event.mimeData() and event.mimeData().hasFormat(self.MIME_TYPE):
                logging.debug("[DROP] dragEnterEvent: accept internal with our MIME")
                event.acceptProposedAction()
                return
        except Exception as exc:
            # Диагностика MIME и параметров события для упрощения расследования
            try:
                md = event.mimeData() if hasattr(event, "mimeData") else None
                formats = list(md.formats()) if md and hasattr(md, "formats") else []
                has_our_mime = bool(md and hasattr(md, "hasFormat") and md.hasFormat(self.MIME_TYPE))
                pos = getattr(event, "position", None)
                pos_tuple = (int(pos.x()), int(pos.y())) if pos is not None else None
                proposed = getattr(event, "proposedAction", None)
                proposed_val = proposed() if callable(proposed) else proposed
            except Exception as info_exc:
                formats, has_our_mime, pos_tuple, proposed_val = [], False, None, None
                logging.debug("[DROP] dragEnterEvent: failed to collect diagnostic info: %s", info_exc)
            logging.warning(
                "[DROP] dragEnterEvent: handler error: %s; mime_formats=%r has_our_mime=%s pos=%r proposed=%r",
                exc,
                formats,
                has_our_mime,
                pos_tuple,
                proposed_val,
            )
            event.ignore()
            raise
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        """Поддержка перетаскивания внутри виджета."""
        try:
            if self._is_internal_drop(event) and event.mimeData() and event.mimeData().hasFormat(self.MIME_TYPE):
                logging.debug("[DROP] dragMoveEvent: accept internal with our MIME")
                event.acceptProposedAction()
                return
        except Exception as exc:
            # Диагностика MIME и параметров события для упрощения расследования
            try:
                md = event.mimeData() if hasattr(event, "mimeData") else None
                formats = list(md.formats()) if md and hasattr(md, "formats") else []
                has_our_mime = bool(md and hasattr(md, "hasFormat") and md.hasFormat(self.MIME_TYPE))
                pos = getattr(event, "position", None)
                pos_tuple = (int(pos.x()), int(pos.y())) if pos is not None else None
                proposed = getattr(event, "proposedAction", None)
                proposed_val = proposed() if callable(proposed) else proposed
            except Exception as info_exc:
                formats, has_our_mime, pos_tuple, proposed_val = [], False, None, None
                logging.debug("[DROP] dragMoveEvent: failed to collect diagnostic info: %s", info_exc)
            logging.warning(
                "[DROP] dragMoveEvent: handler error: %s; mime_formats=%r has_our_mime=%s pos=%r proposed=%r",
                exc,
                formats,
                has_our_mime,
                pos_tuple,
                proposed_val,
            )
            event.ignore()
            raise
        super().dragMoveEvent(event)

    def dragLeaveEvent(self, event):
        """Обрабатывает выход из drag-зоны."""
        if self._sorting_disabled_for_drag:
            # Возвращаем сортировку, если она была включена до начала DnD
            self.setSortingEnabled(True)
            self._sorting_disabled_for_drag = False
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent):
        """Обрабатывает drop для внутреннего перемещения строк."""
        if not self._is_internal_drop(event):
            super().dropEvent(event)
            return

        source_rows, target_row = self._get_drop_positions(event)
        logging.info(f"[DROP] dropEvent: source_rows={source_rows}, target_row={target_row}")
        if not self._is_valid_internal_drop(source_rows, target_row):
            logging.info("[DROP] dropEvent: invalid internal drop, ignoring")
            event.ignore()
            return

        moved = False
        try:
            # Визуально перемещаем строки (поддержка множественного выделения)
            self._move_rows_visually(source_rows, target_row)
            try:
                event.setDropAction(Qt.DropAction.MoveAction)
            except Exception:
                pass
            event.acceptProposedAction()
            moved = True

            # Собираем ID в новом порядке и отправляем сигнал
            ids_in_order = self._get_current_order()
            if ids_in_order:
                logging.info(f"[DROP] dropEvent: items_reordered -> {len(ids_in_order)} ids")
                self.items_reordered.emit(ids_in_order)
            else:
                logging.warning("[DROP] Не удалось собрать ID после перемещения")

        except Exception as e:
            logging.error(f"[DROP] Ошибка при перемещении строки: {e}")
            event.ignore()
        finally:
            # Если реально перемещали — оставляем сортировку отключенной,
            # чтобы пользователь видел результат ручного reorder
            if not moved and self._sorting_disabled_for_drag:
                self.setSortingEnabled(True)
            if hasattr(self, "horizontalHeader"):
                try:
                    # При успешном переносе можно скрыть индикатор сортировки
                    # чтобы визуально отразить режим ручного порядка
                    if moved:
                        self.horizontalHeader().setSortIndicatorShown(False)
                except Exception:
                    pass
            # Сбрасываем флаг независимо от результата
            self._sorting_disabled_for_drag = False

    def _is_internal_drop(self, event) -> bool:
        """Проверяет, является ли это внутренним перемещением.

        Учитываем, что source() указывает на viewport(), а не на сам QTableView.
        """
        src = event.source()
        try:
            return src is self or src is self.viewport()
        except Exception:
            return False

    def _get_selected_rows(self) -> List[int]:
        """Возвращает список выбранных строк."""
        return dnd_get_selected_rows(self)

    def _extract_source_rows_from_mime(self, event) -> List[int]:
        """Извлекает номера строк источника из MIME-данных."""
        return dnd_extract_source_rows(self, event, self.MIME_TYPE)

    def _extract_id_from_index(self, index) -> int:
        """Возвращает ID элемента из модели по переданному индексу (UserRole).

        Требование: модель в ``UserRole`` первой колонки хранит dict ссылки
        с ключом ``id`` или непосредственно целочисленный идентификатор.
        """
        if not index or not index.isValid():
            raise ValueError("Invalid model index")
        data = index.data(Qt.ItemDataRole.UserRole)
        if data is None:
            raise ValueError("UserRole data is None")
        try:
            if isinstance(data, int):
                return data
            if isinstance(data, dict):
                inner_id = data.get("id")
                if inner_id is not None:
                    return int(inner_id)
            # Фолбэк: попытка привести к int строковое значение
            return int(str(data))
        except (TypeError, ValueError) as e:
            logging.warning("[BaseTableView] Некорректные данные ID в UserRole: %r", data)
            raise ValueError("Cannot extract integer ID from UserRole data") from e

    def _get_drop_positions(self, event) -> tuple:
        """Возвращает позиции источника и цели для drop-операции.

        Учитывает позицию индикатора (Above/Below/OnItem) и дроп в пустую область
        (append в конец).
        """
        if self._is_internal_drop(event):
            source_rows = self._extract_source_rows_from_mime(event)
            logging.debug(f"[DROP] extracted rows from MIME: {len(source_rows)}")
        else:
            source_rows = self._get_selected_rows()
            logging.debug(f"[DROP] selected rows: {len(source_rows)}")

        if not source_rows:
            return [], -1

        target_index = self.indexAt(event.position().toPoint())
        # Дроп в пустое место: вставка в конец
        if not target_index.isValid():
            try:
                target_row = self.model().rowCount()
            except Exception:
                target_row = -1
            logging.debug(f"[DROP] target_row (viewport append): {target_row}")
            return source_rows, target_row

        target_row = target_index.row()
        # Корректируем по индикатору
        try:
            pos = self.dropIndicatorPosition()
        except Exception:
            pos = None
        if pos == QAbstractItemView.DropIndicatorPosition.AboveItem:
            pass  # уже корректно
        elif pos == QAbstractItemView.DropIndicatorPosition.BelowItem:
            target_row += 1
        # OnItem или Unknown — оставляем как есть

        # Если целевая позиция попадает внутрь выбранного диапазона — подправим к границе,
        # чтобы операция не считалась невалидной
        if source_rows:
            first, last = min(source_rows), max(source_rows)
            if first <= target_row <= last + 1:
                # Если дроп ниже — ставим после диапазона, иначе — перед диапазоном
                target_row = last + 1 if pos == QAbstractItemView.DropIndicatorPosition.BelowItem else first

        logging.debug(f"[DROP] target_row: {target_row}")
        return source_rows, target_row

    def _is_valid_internal_drop(self, source_rows: list, target_row: int) -> bool:
        """Проверяет валидность внутреннего перемещения (более либерально)."""
        if target_row == -1 or not source_rows:
            return False
        # Разрешаем цель, даже если она попадает внутрь исходного диапазона —
        # вставка будет скорректирована в _get_drop_positions
        return True

    def _move_row_visually(self, source_row: int, target_row: int):
        """Визуально перемещает одну строку (переопределяется в наследниках)."""
        raise NotImplementedError("Subclasses must implement _move_row_visually")

    def _move_rows_visually(self, source_rows: list, target_row: int):
        """Визуально перемещает множество строк (централизовано)."""
        dnd_move_rows_visually(self, source_rows, target_row)
        # Форсируем перерисовку после перемещения — на некоторых платформах
        # beginMoveRows/endMoveRows недостаточно быстро триггерит repaint
        try:
            if hasattr(self, "viewport") and self.viewport() is not None:
                self.viewport().update()
        except Exception:
            pass
        try:
            self.update()
        except Exception:
            pass

    def _get_current_order(self) -> List[int]:
        """Возвращает ID элементов в текущем порядке (централизовано)."""
        return dnd_get_current_order(self)

    def _create_drag_pixmap(self, items) -> Optional[QPixmap]:
        """Создаёт pixmap предпросмотра для drag-операции."""
        try:
            if items:
                rows = sorted({idx.row() for idx in items if idx and idx.isValid()})
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
            model = self.model()
            if model is None:
                return self._create_default_pixmap()
            max_cols = min(3, max(0, model.columnCount()))

            for col in range(max_cols):
                idx = model.index(row, col)
                if not idx.isValid():
                    continue
                val = model.data(idx, Qt.ItemDataRole.DisplayRole)
                s = str(val or "").strip()
                if s:
                    text = s[:30]
                    if len(s) > 30:
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
