# app/settings.py

import logging

from PyQt6.QtCore import QSettings, Qt

from .config_data import app_config

logger = logging.getLogger(__name__)


class AppSettings:
    def __init__(self):
        # Store settings in INI format under the user's profile
        self._qs = QSettings(
            QSettings.Format.IniFormat,
            QSettings.Scope.UserScope,
            app_config.get_org_name(),
            app_config.get_app_name(),
        )
        self.theme = self.get_theme()

    @staticmethod
    def _as_int(raw, default_value: int, key_name: str) -> int:
        """Safely cast a value to int with error logging.

        - Returns default_value if raw is None or empty string.
        - Logs a warning on failed cast.
        """
        if raw is None or (isinstance(raw, str) and raw.strip() == ""):
            return int(default_value)
        try:
            return int(raw)
        except (ValueError, TypeError) as e:
            logger.warning(
                "AppSettings: invalid numeric value for '%s' (%r), using default: %s. Error: %s",
                key_name,
                raw,
                default_value,
                e,
            )
            return int(default_value)

    def get_theme(self) -> str:
        return self._qs.value("Appearance/Theme", "light")

    def set_theme(self, theme: str):
        self._qs.setValue("Appearance/Theme", theme)
        self.theme = theme

    def get_max_backups(self) -> int:
        default_value = app_config.get_max_backups()
        raw = self._qs.value("Backup/MaxCopies", default_value)
        return self._as_int(raw, default_value, "Backup/MaxCopies")

    def set_max_backups(self, count: int):
        self._qs.setValue("Backup/MaxCopies", count)

    def get_font_size(self) -> int:
        default_value = app_config.get_default_font_size()
        raw = self._qs.value("UI/FontSize", default_value)
        return self._as_int(raw, default_value, "UI/FontSize")

    def set_font_size(self, size: int):
        self._qs.setValue("UI/FontSize", size)

    def get_hotkey(self, action: str, default: str) -> str:
        return self._qs.value(f"Hotkeys/{action}", default)

    def set_hotkey(self, action: str, sequence: str):
        self._qs.setValue(f"Hotkeys/{action}", sequence)

    def get_table_sort(self) -> tuple[int | None, Qt.SortOrder | None]:
        """Return last used table sort (column, order) if saved."""
        col_raw = self._qs.value("Table/SortColumn")
        order_raw = self._qs.value("Table/SortOrder")

        # Column
        col: int | None
        if col_raw is None or (isinstance(col_raw, str) and not col_raw.strip()):
            col = None
        else:
            col = self._as_int(col_raw, -1, "Table/SortColumn")
            if col < 0:
                col = None

        # Order
        order: Qt.SortOrder | None
        if order_raw is None or (isinstance(order_raw, str) and not order_raw.strip()):
            order = None
        else:
            try:
                order = Qt.SortOrder(int(order_raw))
            except Exception as e:  # pragma: no cover - defensive path
                logger.debug("AppSettings: invalid sort order %r: %s", order_raw, e)
                order = None

        return col, order

    def set_table_sort(self, column: int, order: Qt.SortOrder):
        """Persist table sort column/order."""
        if not isinstance(column, int) or column < 0:
            return
        try:
            order_val = int(order)
        except Exception:
            order_val = int(Qt.SortOrder.AscendingOrder)
        self._qs.setValue("Table/SortColumn", column)
        self._qs.setValue("Table/SortOrder", order_val)

    def get_last_tree_selection(self) -> tuple[str, int] | None:
        """Return last selected tree item (section/category, id)."""
        item_type = self._qs.value("Tree/LastItemType")
        raw_id = self._qs.value("Tree/LastItemId")
        if not item_type or not isinstance(item_type, str):
            return None
        try:
            item_id = int(raw_id)
        except Exception:
            return None
        if item_id <= 0:
            return None
        if item_type not in {"section", "category"}:
            return None
        return item_type, item_id

    def set_last_tree_selection(self, item_type: str, item_id: int) -> None:
        """Persist last selected tree item."""
        if item_type not in {"section", "category"}:
            return
        if not isinstance(item_id, int) or item_id <= 0:
            return
        self._qs.setValue("Tree/LastItemType", item_type)
        self._qs.setValue("Tree/LastItemId", int(item_id))
