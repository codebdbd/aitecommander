# Устранение блокировок UI-потока

## Проблема 1: Синхронная обработка в _retry_forward_search

### Файл: `main_window.py`, lines 408-429

```python
# ❌ ПРОБЛЕМА:
def _retry_forward_search(self) -> None:
    # Выполняется в UI-потоке
    la.on_search(txt)  # Может быть медленным при большом количестве ссылок
    QTimer.singleShot(SEARCH_RETRY_INTERVAL_MS, self._retry_forward_search)
```

### Решение:
```python
# ✅ ИСПРАВЛЕНИЕ - использовать debounce правильно:
from PyQt6.QtCore import QTimer

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self._search_timer = QTimer()
        self._search_timer.setSingleShot(True)
        self._search_timer.timeout.connect(self._execute_search)
        self._pending_search_text = ""
    
    def on_search(self, text: str) -> None:
        """Откладывает поиск на 300ms."""
        self._pending_search_text = text
        self._search_timer.start(300)  # Перезапускает таймер
    
    def _execute_search(self):
        """Выполняет поиск после задержки."""
        la = getattr(self, "links_actions", None)
        if la:
            la.on_search(self._pending_search_text)
```

## Проблема 2: Массовое заполнение таблицы блокирует UI

### Файл: `base_widgets.py`, lines 111-161

```python
# ❌ ПРОБЛЕМА:
def _populate_panel(self, items: List[Dict], create_button_func):
    self.setUpdatesEnabled(False)
    for link in items:  # Если items = 1000+, UI зависает
        button = create_button_func(link)
        self.panel_layout.addWidget(button)
    self.setUpdatesEnabled(True)
```

### Решение:
```python
# ✅ ИСПРАВЛЕНИЕ - батчинг с QTimer:
from PyQt6.QtCore import QTimer

BATCH_SIZE = 50  # Обрабатываем по 50 за раз

def _populate_panel(self, items: List[Dict], create_button_func):
    """Заполняет панель батчами, не блокируя UI."""
    self._pending_items = list(items)
    self._create_button_func = create_button_func
    self.setUpdatesEnabled(False)
    self._populate_batch()

def _populate_batch(self):
    """Обрабатывает один батч."""
    if not self._pending_items:
        self.setUpdatesEnabled(True)
        self.updateGeometry()
        return
    
    # Берем следующий батч
    batch = self._pending_items[:BATCH_SIZE]
    self._pending_items = self._pending_items[BATCH_SIZE:]
    
    # Обрабатываем батч
    for link in batch:
        try:
            button = self._create_button_func(link)
            if button:
                self.panel_layout.addWidget(button)
        except Exception:
            logger.exception("Failed to create button")
    
    # Планируем следующий батч
    QTimer.singleShot(0, self._populate_batch)
```

## Проблема 3: Синхронная загрузка иконок

### Файл: `link/links_model.py`, lines 77-85

```python
# ❌ ПРОБЛЕМА:
def data(self, index, role):
    if role == Qt.ItemDataRole.DecorationRole:
        # Синхронно читает файл с диска
        resolved_path = resolve_icon_for_link(link)
        icon = create_icon_from_path(resolved_path)  # Блокирует
```

### Решение:
```python
# ✅ ИСПРАВЛЕНИЕ - асинхронная загрузка:
from PyQt6.QtCore import QThreadPool, QRunnable, pyqtSignal, QObject

class IconLoaderSignals(QObject):
    """Сигналы для IconLoader."""
    loaded = pyqtSignal(int, object)  # row, QIcon

class IconLoader(QRunnable):
    """Загрузчик иконок в фоновом потоке."""
    
    def __init__(self, row: int, icon_path: str):
        super().__init__()
        self.row = row
        self.icon_path = icon_path
        self.signals = IconLoaderSignals()
    
    def run(self):
        try:
            icon = create_icon_from_path(self.icon_path)
            self.signals.loaded.emit(self.row, icon)
        except Exception as e:
            logger.exception(f"Failed to load icon: {self.icon_path}")

class LinksTableModel(QAbstractTableModel):
    def __init__(self):
        super().__init__()
        self._thread_pool = QThreadPool()
        self._thread_pool.setMaxThreadCount(4)
    
    def data(self, index, role):
        if role == Qt.ItemDataRole.DecorationRole and col == 1:
            icon = link.get("_icon")
            if icon:
                return icon
            
            # Запускаем асинхронную загрузку
            resolved_path = resolve_icon_for_link(link)
            if resolved_path:
                loader = IconLoader(index.row(), resolved_path)
                loader.signals.loaded.connect(self._on_icon_loaded)
                self._thread_pool.start(loader)
                
                # Возвращаем placeholder
                return self._get_placeholder_icon()
    
    def _on_icon_loaded(self, row: int, icon: QIcon):
        """Вызывается когда иконка загружена."""
        if 0 <= row < len(self._links):
            self._links[row]["_icon"] = icon
            idx = self.index(row, 1)
            self.dataChanged.emit(idx, idx, [Qt.ItemDataRole.DecorationRole])
```

## Проблема 4: Drag & Drop с большим количеством элементов

### Файл: `base_widgets.py`, lines 591-613

```python
# ❌ ПРОБЛЕМА:
def _create_drag_pixmap(self, items):
    # Создание pixmap на лету может быть медленным
    for row in rows:
        texts = []
        for col in range(max_cols):
            val = model.data(idx, Qt.ItemDataRole.DisplayRole)
            # Много обращений к модели
```

### Решение:
```python
# ✅ ИСПРАВЛЕНИЕ - кэширование pixmap:
from functools import lru_cache

@lru_cache(maxsize=100)
def _get_cached_pixmap(self, text: str, is_multi: bool) -> QPixmap:
    """Кэшированное создание pixmap."""
    return create_text_pixmap(text, single_row=not is_multi)

def _create_drag_pixmap(self, items):
    # Ограничиваем количество обрабатываемых элементов
    rows = sorted({idx.row() for idx in items if idx.isValid()})[:10]
    
    if len(rows) == 1:
        # Быстрый путь для одного элемента
        text = self._get_row_text(rows[0])
        return self._get_cached_pixmap(text, is_multi=False)
    else:
        # Просто показываем количество
        text = f"{len(rows)} элементов"
        return self._get_cached_pixmap(text, is_multi=True)
```

## Инструменты для профилирования

```python
# tools/profile_ui.py
"""Профилировщик производительности UI."""

import cProfile
import pstats
from functools import wraps
from PyQt6.QtCore import QElapsedTimer

def profile_method(func):
    """Декоратор для профилирования методов."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        profiler = cProfile.Profile()
        profiler.enable()
        
        result = func(*args, **kwargs)
        
        profiler.disable()
        stats = pstats.Stats(profiler)
        stats.sort_stats('cumulative')
        stats.print_stats(20)  # Top 20
        
        return result
    return wrapper

def time_method(threshold_ms: int = 16):
    """Декоратор для измерения времени выполнения.
    
    Логирует предупреждение если метод выполняется дольше threshold_ms.
    60 FPS = 16ms на кадр.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            timer = QElapsedTimer()
            timer.start()
            
            result = func(*args, **kwargs)
            
            elapsed = timer.elapsed()
            if elapsed > threshold_ms:
                logger.warning(
                    f"⚠️ Slow method: {func.__name__} took {elapsed}ms "
                    f"(threshold: {threshold_ms}ms)"
                )
            
            return result
        return wrapper
    return decorator

# Использование:
class LinksTableView(BaseDragDropTableWidget):
    
    @time_method(threshold_ms=16)
    def populate_items(self, items):
        """Заполнение таблицы."""
        ...
```

## Чек-лист проверки

- [ ] Нет операций файлового I/O в обработчиках событий
- [ ] Циклы > 100 итераций выполняются батчами
- [ ] Тяжелые операции вынесены в QRunnable/QThread
- [ ] Используется debounce для частых событий (search, resize)
- [ ] Drag pixmap создается быстро (< 16ms)
- [ ] Модель не блокирует при data()

## Тестирование производительности

```python
# tests/test_performance.py
import pytest
from PyQt6.QtCore import QElapsedTimer

def test_populate_panel_performance():
    """Проверка скорости заполнения панели."""
    panel = BaseLinksPanelWidget()
    items = [{"id": i, "name": f"Link {i}"} for i in range(1000)]
    
    timer = QElapsedTimer()
    timer.start()
    
    panel.populate_panel(items, lambda x: QPushButton(x["name"]))
    
    elapsed = timer.elapsed()
    assert elapsed < 500, f"populate_panel слишком медленный: {elapsed}ms"

@pytest.mark.benchmark
def test_model_data_speed(benchmark):
    """Бенчмарк скорости data() модели."""
    model = LinksTableModel([...])
    index = model.index(0, 1)
    
    result = benchmark(model.data, index, Qt.ItemDataRole.DecorationRole)
    
    # Должно быть < 1ms на вызов
    assert benchmark.stats.mean < 0.001
```
