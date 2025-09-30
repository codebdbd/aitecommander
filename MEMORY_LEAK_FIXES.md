# Критические исправления утечек памяти

## Проблема 1: Event Filters без очистки

### Файл: `custom_widgets.py`, lines 198-215

```python
# ❌ ПРОБЛЕМА:
self._neon_link_filter = NeonEventFilter(...)
for btn in self._get_type_group().buttons():
    btn.installEventFilter(self._neon_link_filter)
    # Если диалог удаляется, фильтр остается и держит ссылки на кнопки
```

### Решение:
```python
# ✅ ИСПРАВЛЕНИЕ:
def closeEvent(self, event):
    """Очистка ресурсов перед закрытием."""
    # Удаляем event filter
    if hasattr(self, '_neon_link_filter'):
        for btn in self._get_type_group().buttons():
            try:
                btn.removeEventFilter(self._neon_link_filter)
            except (RuntimeError, AttributeError):
                pass
        self._neon_link_filter = None
    
    super().closeEvent(event)
```

## Проблема 2: Сигналы в делегатах без отписки

### Файл: `link/base_table.py`, lines 271-276

```python
# ❌ ПРОБЛЕМА:
self.entered.connect(self._on_index_entered)
# При удалении view, connection может остаться
```

### Решение:
```python
# ✅ ИСПРАВЛЕНИЕ в LinksTableView:
def __del__(self):
    """Деструктор для очистки соединений."""
    try:
        if hasattr(self, 'entered'):
            self.entered.disconnect()
    except (RuntimeError, TypeError):
        pass

# ИЛИ использовать Qt::UniqueConnection при подключении:
self.entered.connect(self._on_index_entered, Qt.ConnectionType.UniqueConnection)
```

## Проблема 3: Кэш иконок в модели растет неограниченно

### Файл: `link/links_model.py`, lines 73-85

```python
# ❌ ПРОБЛЕМА:
# Кэш link["_icon"] никогда не очищается
icon = link.get("_icon")
if icon is None:
    icon = create_icon_from_path(...)
    link["_icon"] = icon  # Копится в памяти
```

### Решение:
```python
# ✅ ИСПРАВЛЕНИЕ - добавить LRU кэш:

from functools import lru_cache
from typing import Optional

class LinksTableModel(QAbstractTableModel):
    MAX_ICON_CACHE_SIZE = 500  # Лимит
    
    @lru_cache(maxsize=MAX_ICON_CACHE_SIZE)
    def _get_icon(self, icon_path: str) -> Optional[QIcon]:
        """Кэшированное получение иконки."""
        try:
            icon = create_icon_from_path(icon_path)
            return icon if not icon.isNull() else None
        except Exception:
            return None
    
    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        # ...
        if role == Qt.ItemDataRole.DecorationRole:
            if col == 1:
                resolved_path = resolve_icon_for_link(link)
                if resolved_path:
                    return self._get_icon(resolved_path)  # LRU кэш
```

## Проблема 4: Timer'ы не останавливаются

### Файл: `link_dialog.py`, lines 261-265

```python
# ❌ ПРОБЛЕМА:
self._processing_timer = QTimer(self)
# Если диалог закрывается во время работы таймера
```

### Решение:
```python
# ✅ УЖЕ ЕСТЬ в closeEvent (lines 521-527), но можно улучшить:

def closeEvent(self, event):
    # Остановить все таймеры
    if hasattr(self, '_processing_timer'):
        try:
            self._processing_timer.stop()
            self._processing_timer.timeout.disconnect()  # Отписаться от сигналов
            self._processing_timer.deleteLater()
        except (RuntimeError, AttributeError):
            pass
    
    super().closeEvent(event)
```

## Скрипт для автоматической проверки утечек

```python
#!/usr/bin/env python3
"""Проверка потенциальных утечек памяти."""

import ast
import sys
from pathlib import Path

class MemoryLeakChecker(ast.NodeVisitor):
    """AST visitor для поиска паттернов утечек."""
    
    def __init__(self):
        self.issues = []
        self.current_file = None
    
    def visit_Call(self, node):
        # Проверка installEventFilter без соответствующего removeEventFilter
        if isinstance(node.func, ast.Attribute):
            if node.func.attr == 'installEventFilter':
                self.issues.append({
                    'file': self.current_file,
                    'line': node.lineno,
                    'type': 'event_filter',
                    'message': 'installEventFilter без removeEventFilter в closeEvent'
                })
        
        self.generic_visit(node)
    
    def check_file(self, filepath: Path):
        self.current_file = filepath
        try:
            tree = ast.parse(filepath.read_text(encoding='utf-8'))
            self.visit(tree)
        except Exception as e:
            print(f"⚠️ Не удалось разобрать {filepath}: {e}")

def main():
    checker = MemoryLeakChecker()
    views_dir = Path("app/views")
    
    for py_file in views_dir.rglob("*.py"):
        checker.check_file(py_file)
    
    if checker.issues:
        print(f"❌ Найдено {len(checker.issues)} потенциальных утечек:\n")
        for issue in checker.issues:
            print(f"{issue['file']}:{issue['line']} - {issue['message']}")
        return 1
    else:
        print("✅ Утечек не обнаружено")
        return 0

if __name__ == "__main__":
    sys.exit(main())
```

## План действий

1. **День 1**: Исправить event filters (30 мин)
2. **День 1**: Добавить LRU кэш для иконок (1 час)
3. **День 2**: Проверить все Timer'ы (1 час)
4. **День 2**: Добавить тесты с memory profiler (2 часа)

## Тестирование утечек

```python
# tests/test_memory_leaks.py
import gc
import sys
from PyQt6.QtWidgets import QApplication
import pytest

@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication(sys.argv)
    yield app
    app.quit()

def test_link_dialog_no_leak(qapp):
    """Проверка, что LinkDialog освобождает память."""
    import weakref
    from app.views.dialogs.link_dialog import LinkDialog
    
    # Создаем диалог
    dialog = LinkDialog(...)
    weak_ref = weakref.ref(dialog)
    
    # Закрываем
    dialog.close()
    dialog.deleteLater()
    qapp.processEvents()
    
    # Принудительная сборка мусора
    del dialog
    gc.collect()
    
    # Проверяем, что объект удален
    assert weak_ref() is None, "LinkDialog не освобожден из памяти!"
```
