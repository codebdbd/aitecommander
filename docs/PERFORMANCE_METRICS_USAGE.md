# 📊 Performance Metrics Usage Guide

## Обзор

Система метрик производительности позволяет отслеживать время выполнения операций, cache hit/miss rate и другие показатели для оптимизации приложения.

---

## 🚀 Быстрый старт

### Измерение времени выполнения

```python
from app.utils.metrics import measure_time

class MyBusinessLogic:
    @measure_time("load_data", log_threshold_ms=200)
    def load_data(self, item_id: int) -> dict:
        """Загружает данные с автоматическим измерением времени."""
        # Ваш код здесь
        return data
```

### Получение статистики

```python
from app.utils.metrics import get_metrics

# Получить метрики
metrics = get_metrics()

# Статистика по операции
stats = metrics.get_stats("load_data")
print(f"Average: {stats['avg']:.2f}ms")
print(f"Min: {stats['min']:.2f}ms")
print(f"Max: {stats['max']:.2f}ms")
print(f"Count: {stats['count']}")

# Статистика кэша
cache_stats = metrics.get_cache_stats("categories_cache")
print(f"Hit rate: {cache_stats['hit_rate']:.1f}%")
print(f"Hits: {cache_stats['hits']}")
print(f"Misses: {cache_stats['misses']}")
```

### Логирование сводки

```python
from app.utils.metrics import log_performance_summary

# В конце сессии или при закрытии приложения
log_performance_summary()
```

**Вывод**:
```
============================================================
PERFORMANCE METRICS SUMMARY
============================================================

📊 EXECUTION TIMES:
  load_data: avg=45.23ms, min=12.45ms, max=234.56ms, count=150
  create_section: avg=78.90ms, min=45.12ms, max=156.78ms, count=25
  search_links: avg=123.45ms, min=67.89ms, max=345.67ms, count=42

💾 CACHE STATISTICS:
  categories_cache: hit_rate=85.3%, hits=256, misses=44
  sections_cache: hit_rate=92.1%, hits=412, misses=35
  spheres_cache: hit_rate=98.5%, hits=987, misses=15

📞 CALL COUNTS:
  load_data: 150 calls
  get_categories: 300 calls
  get_sections: 447 calls
============================================================
```

---

## 📈 Интеграция в существующий код

### Business Layer

Метрики уже добавлены в:
- ✅ `links_business.py` — load_links, search_links, create_link, update_link
- ✅ `crud_service.py` — все CRUD операции
- ✅ `cache_service.py` — отслеживание cache hit/miss

### Добавление метрик в новый код

```python
from app.utils.metrics import measure_time

class NewService:
    @measure_time("my_operation", log_threshold_ms=100)
    def my_operation(self, param: int) -> str:
        """Операция с автоматическим измерением времени.
        
        Если выполнение займёт > 100ms, будет залогирован warning.
        """
        # Ваш код
        return result
```

---

## 🎯 Мониторинг кэша

### Автоматическое отслеживание

```python
from app.utils.metrics import get_metrics

_metrics = get_metrics()

def get_cached_data(self, key: str) -> Optional[dict]:
    """Получает данные с отслеживанием cache hit/miss."""
    cached = self._cache.get(key)
    
    if cached is not None:
        _metrics.record_cache_hit("my_cache")
        return cached
    
    _metrics.record_cache_miss("my_cache")
    data = self._fetch_from_db()
    self._cache.set(key, data)
    return data
```

### Анализ эффективности кэша

```python
from app.utils.metrics import get_metrics

metrics = get_metrics()

# Проверка всех кэшей
all_stats = metrics.get_all_stats()
for cache_name, stats in all_stats['caches'].items():
    if stats['hit_rate'] < 70:
        print(f"⚠️ Low hit rate for {cache_name}: {stats['hit_rate']:.1f}%")
        print(f"   Consider: increasing TTL or cache size")
```

---

## 🔧 Настройка

### Изменение порога логирования

```python
# Для быстрых операций
@measure_time("quick_operation", log_threshold_ms=50)
def quick_operation(self):
    pass

# Для медленных операций
@measure_time("slow_operation", log_threshold_ms=1000)
def slow_operation(self):
    pass
```

### Отключение метрик

```python
from app.utils.metrics import get_metrics

# Временно отключить
metrics = get_metrics()
metrics.disable()

# Включить обратно
metrics.enable()

# Проверка состояния
if metrics.enabled:
    print("Metrics collection is active")
```

### Сброс метрик

```python
from app.utils.metrics import get_metrics

metrics = get_metrics()

# Сброс всех метрик
metrics.reset()

# Полезно для тестирования или начала новой сессии
```

---

## 📊 Анализ производительности

### Выявление узких мест

```python
from app.utils.metrics import get_metrics

metrics = get_metrics()
all_stats = metrics.get_all_stats()

# Топ-10 самых медленных операций
slow_operations = sorted(
    all_stats['timings'].items(),
    key=lambda x: x[1]['avg'],
    reverse=True
)[:10]

print("🐌 Slowest operations:")
for op, stats in slow_operations:
    print(f"  {op}: avg={stats['avg']:.2f}ms, max={stats['max']:.2f}ms")
```

### Мониторинг в реальном времени

```python
from PyQt6.QtCore import QTimer
from app.utils.metrics import get_metrics

class PerformanceMonitor:
    def __init__(self):
        self.metrics = get_metrics()
        self.timer = QTimer()
        self.timer.timeout.connect(self.log_stats)
        self.timer.start(60000)  # Каждую минуту
    
    def log_stats(self):
        """Периодическое логирование статистики."""
        stats = self.metrics.get_stats("load_links")
        if stats['count'] > 0:
            print(f"load_links: avg={stats['avg']:.2f}ms, calls={stats['count']}")
```

---

## 🧪 Тестирование с метриками

### Unit тесты

```python
import pytest
from app.utils.metrics import get_metrics

def test_operation_performance():
    # Arrange
    metrics = get_metrics()
    metrics.reset()
    
    # Act
    my_service.load_data(123)
    
    # Assert
    stats = metrics.get_stats("load_data")
    assert stats['count'] == 1
    assert stats['avg'] < 200  # Должно быть быстрее 200ms
```

### Benchmark тесты

```python
def test_cache_effectiveness():
    metrics = get_metrics()
    metrics.reset()
    
    # Первый вызов - cache miss
    service.get_categories(1)
    
    # Второй вызов - cache hit
    service.get_categories(1)
    
    cache_stats = metrics.get_cache_stats("categories_cache")
    assert cache_stats['hit_rate'] >= 50  # Минимум 50% hit rate
```

---

## 📋 Чеклист оптимизации

### Когда метрики показывают проблемы

**Медленные операции (avg > threshold)**:
- [ ] Проверить N+1 запросы к БД
- [ ] Добавить индексы в БД
- [ ] Использовать batch операции
- [ ] Добавить кэширование
- [ ] Оптимизировать SQL запросы

**Низкий cache hit rate (< 70%)**:
- [ ] Увеличить TTL кэша
- [ ] Увеличить размер кэша
- [ ] Проверить частоту инвалидации
- [ ] Пересмотреть стратегию кэширования

**Высокий max time (> 10x avg)**:
- [ ] Проверить блокировки БД
- [ ] Проверить сетевые задержки
- [ ] Добавить таймауты
- [ ] Логировать outliers

---

## 🎓 Best Practices

### 1. Измеряйте критичные операции

```python
# ✅ ПРАВИЛЬНО: Измеряем важные операции
@measure_time("load_structure", log_threshold_ms=200)
def load_structure_async(self, sphere_id: int):
    pass

# ❌ НЕПРАВИЛЬНО: Не измеряем тривиальные операции
@measure_time("get_name")  # Слишком быстро, не нужно
def get_name(self):
    return self._name
```

### 2. Устанавливайте разумные пороги

```python
# ✅ ПРАВИЛЬНО: Порог соответствует ожиданиям
@measure_time("db_query", log_threshold_ms=100)  # БД должна быть быстрой
@measure_time("api_call", log_threshold_ms=1000)  # API может быть медленнее

# ❌ НЕПРАВИЛЬНО: Слишком низкий порог
@measure_time("complex_calculation", log_threshold_ms=1)  # Будет спамить логи
```

### 3. Регулярно анализируйте метрики

```python
# Добавьте в shutdown приложения
def shutdown(self):
    from app.utils.metrics import log_performance_summary
    log_performance_summary()
    # Остальной cleanup
```

### 4. Используйте метрики для A/B тестирования

```python
# Версия A
@measure_time("algorithm_v1")
def algorithm_v1(data):
    pass

# Версия B
@measure_time("algorithm_v2")
def algorithm_v2(data):
    pass

# Сравнение
stats_v1 = metrics.get_stats("algorithm_v1")
stats_v2 = metrics.get_stats("algorithm_v2")
print(f"V1 avg: {stats_v1['avg']:.2f}ms")
print(f"V2 avg: {stats_v2['avg']:.2f}ms")
```

---

## 🔗 Связанные документы

- [Business Layer Guide](BUSINESS_LAYER_GUIDE.md)
- [Cache Strategy](CACHE_STRATEGY.md)
- [Performance Optimization](PERFORMANCE_OPTIMIZATION.md)

---

**Версия документа**: 1.0  
**Последнее обновление**: 2025-10-06
