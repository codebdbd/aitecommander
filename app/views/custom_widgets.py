from PyQt6.QtCore import Qt, QMimeData, QByteArray
from PyQt6.QtWidgets import QTreeWidget, QAbstractItemView, QTableWidget, QTableWidgetItem
from PyQt6.QtGui import QDrag
import json

from app.models.db import Database


class LinksTableWidget(QTableWidget):
    """
    QTableWidget with drag support for links.
    """
    MIME_TYPE = 'application/x-link-id'

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)

    def mimeTypes(self):
        return [self.MIME_TYPE]

    def mimeData(self, items):
        print("[LinksTableWidget] mimeData called, items:", items)
        if not items:
            items = self.selectedItems()
        if not items:
            print("[LinksTableWidget] No items to drag.")
            return None
        row = items[0].row()
        link_data = self.item(row, 0).data(Qt.ItemDataRole.UserRole)
        print(f"[LinksTableWidget] Dragging link id={link_data.get('id')} data={link_data}")
        mime = QMimeData()
        payload = json.dumps({'id': link_data['id']}).encode('utf-8')
        mime.setData(self.MIME_TYPE, QByteArray(payload))
        return mime

    def startDrag(self, supportedActions):
        print("[LinksTableWidget] startDrag called")
        items = self.selectedItems()
        if not items:
            print("[LinksTableWidget] No items selected for drag.")
            return
        drag = QDrag(self)
        mime = self.mimeData(items)
        if mime is None:
            print("[LinksTableWidget] mimeData returned None, aborting drag.")
            return
        drag.setMimeData(mime)
        print("[LinksTableWidget] Starting drag operation.")
        drag.exec(supportedActions)

    def supportedDropActions(self):
        return Qt.DropAction.MoveAction | Qt.DropAction.CopyAction

class StructureTreeWidget(QTreeWidget):
    """
    A custom QTreeWidget that enforces drag-and-drop rules for the application's
    structure (Sections and Categories) and updates the database on successful drops.
    - Prevents dropping any item onto a 'category' item.
    - Updates a category's parent section in the DB when it's moved.
    - Accepts links from LinksTableWidget.
    """
    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        print("[StructureTreeWidget] dragEnterEvent")
        mime = event.mimeData()
        if mime.hasFormat(LinksTableWidget.MIME_TYPE):
            print("[StructureTreeWidget] dragEnterEvent: Accepting external link drag")
            event.acceptProposedAction()
        elif mime.hasFormat('application/x-category-id'):
            print("[StructureTreeWidget] dragEnterEvent: Accepting external category drag")
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        print("[StructureTreeWidget] dragMoveEvent")
        mime = event.mimeData()
        pos = event.position().toPoint() if hasattr(event, 'position') else event.pos()
        target_item = self.itemAt(pos)
        if mime.hasFormat(LinksTableWidget.MIME_TYPE):
            if target_item:
                target_type, _ = target_item.data(0, Qt.ItemDataRole.UserRole)
                if target_type == 'category':
                    print("[StructureTreeWidget] dragMoveEvent: Accepting drag over category")
                    event.acceptProposedAction()
                    return
            print("[StructureTreeWidget] dragMoveEvent: Not a category, ignoring")
            event.ignore()
        elif mime.hasFormat('application/x-category-id'):
            if target_item:
                target_type, _ = target_item.data(0, Qt.ItemDataRole.UserRole)
                if target_type == 'section':
                    print("[StructureTreeWidget] dragMoveEvent: Accepting drag over section for category")
                    event.acceptProposedAction()
                    return
            print("[StructureTreeWidget] dragMoveEvent: Not a section, ignoring category drop")
            event.ignore()
        else:
            super().dragMoveEvent(event)

    def _get_link_by_id(self, link_id):
        # Helper: fetch link row as dict by id
        cur = self.db.conn.execute("SELECT * FROM link WHERE id=?", (link_id,))
        row = cur.fetchone()
        return dict(row) if row else None

    def dropEvent(self, event):
        print("[StructureTreeWidget] dropEvent called")
        # --- External drop from CategoryTiles ---
        mime = event.mimeData()
        if mime.hasFormat('application/x-category-id'):
            print('[StructureTreeWidget] External category drop detected')
            target_item = self.itemAt(event.position().toPoint())
            if not target_item:
                print('[StructureTreeWidget] No target under drop for category')
                event.ignore()
                return
            target_type, target_id = target_item.data(0, Qt.ItemDataRole.UserRole)
            print(f'[StructureTreeWidget] Category drop target type={target_type} id={target_id}')
            if target_type != 'section':
                print('[StructureTreeWidget] Target is not section, ignore')
                event.ignore()
                return
            try:
                cat_id = int(bytes(mime.data('application/x-category-id')).decode('utf-8'))
            except Exception as e:
                print(f'[StructureTreeWidget] Failed to parse category id: {e}')
                event.ignore()
                return
            category_data = self.db.get_category_by_id(cat_id)
            if not category_data:
                print(f'[StructureTreeWidget] Category {cat_id} not in DB')
                event.ignore()
                return
            updated = dict(category_data)
            updated['section_id'] = target_id
            self.db.update_category(cat_id, updated)
            print(f'[StructureTreeWidget] Category {cat_id} moved to section {target_id}')
            # Refresh tree view if parent provides method
            # Try to refresh entire UI via MainWindow
            main_win = self.window()
            if hasattr(main_win, 'switch_sphere'):
                main_win.switch_sphere(main_win.current_sphere_id)
            if hasattr(main_win, 'load_section'):
                main_win.load_section(target_id)
            # Also keep legacy custom refresh if provided
            if hasattr(self.parent(), 'reload_tree'):
                self.parent().reload_tree()
            event.setDropAction(Qt.DropAction.MoveAction)
            event.accept()
            return
        mime = event.mimeData()
        if mime.hasFormat(LinksTableWidget.MIME_TYPE):
            print("[StructureTreeWidget] Drop from LinksTableWidget detected.")
            target_item = self.itemAt(event.position().toPoint())
            if not target_item:
                print("[StructureTreeWidget] No target item under drop.")
                event.ignore()
                return
            target_type, target_id = target_item.data(0, Qt.ItemDataRole.UserRole)
            print(f"[StructureTreeWidget] Drop target type={target_type} id={target_id}")
            if target_type != 'category':
                print("[StructureTreeWidget] Drop target is not a category, ignoring.")
                event.ignore()
                return
            try:
                payload = json.loads(bytes(mime.data(LinksTableWidget.MIME_TYPE)).decode('utf-8'))
                link_id = payload['id']
                print(f"[StructureTreeWidget] Parsed link id from MIME: {link_id}")
            except Exception as e:
                print(f"[StructureTreeWidget] Failed to parse MIME data: {e}")
                event.ignore()
                return
            link = self._get_link_by_id(link_id)
            if not link:
                print(f"[StructureTreeWidget] No link found in DB for id {link_id}")
                event.ignore()
                return
            updated = dict(link)
            updated['category_id'] = target_id
            print(f"[StructureTreeWidget] Updating link {link_id} to category {target_id}")
            self.db.upsert_link(updated)
            if hasattr(self.parent(), 'load_category'):
                print(f"[StructureTreeWidget] Refreshing UI for category {target_id}")
                self.parent().load_category(target_id)
            event.accept()
            print("[StructureTreeWidget] Drop from table accepted.")
            return

        # Standard internal move (sections/categories)
        target_item = self.itemAt(event.position().toPoint())
        source_item = self.currentItem()

        # Pre-drop validation
        if not source_item:
            event.ignore()
            return

        source_type, source_id = source_item.data(0, Qt.ItemDataRole.UserRole)
        target_type, target_id = (None, None)
        if target_item:
            target_type, target_id = target_item.data(0, Qt.ItemDataRole.UserRole)

        # Запретить любые дропы разделов (section)
        if source_type == 'section':
            event.ignore()
            return

        # Категории можно перемещать только на разделы
        if source_type == 'category':
            if not target_item or target_type != 'section':
                event.ignore()
                return

        # Ссылки можно перемещать только на категории
        if source_type == 'link':
            if not target_item or target_type != 'category':
                event.ignore()
                return

        super().dropEvent(event)

        if source_type == 'category':
            new_parent = source_item.parent()
            if new_parent:
                parent_type, parent_id = new_parent.data(0, Qt.ItemDataRole.UserRole)
                if parent_type == 'section':
                    category_data = self.db.get_category_by_id(source_id)
                    if category_data:
                        updated_data = dict(category_data)
                        updated_data['section_id'] = parent_id
                        self.db.update_category(source_id, updated_data)
    # Note: Reordering of sections or categories within a section is not persisted
    # as it would require an 'order' column in the database schema.
    # The visual reordering will work for the current session.
