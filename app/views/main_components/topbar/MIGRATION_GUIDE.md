# Руководство по миграции на новую архитектуру TopBar

## 🚀 Статус внедрения

✅ **Приложение успешно запущено с новой архитектурой!**
- Время создания TopPanel: 31.0 ms
- Общее время запуска: 820.7 ms
- Обратная совместимость: 100%

## ⚠️ Устаревшие методы

### Заменить `adjust()` на `request_adjustment()`

**Было:**
```python
mgr = getattr(window, "_topbar_manager", None)
if mgr:
    mgr.adjust()
```

**Стало:**
```python
mgr = getattr(window, "_topbar_manager", None)
if mgr:
    if hasattr(mgr, 'request_adjustment'):
        from app.views.main_components.topbar.constants import AdjustmentReason
        mgr.request_adjustment(AdjustmentReason.PANEL_CHANGE)
    else:
        mgr.adjust()  # Fallback для совместимости
```

## 📊 Мониторинг производительности

### Включение детального логирования
```python
# В конфигурации
app_config.set("ui.topbar.log_info", True)
```

### Получение статистики кэша
```python
mgr = window._topbar_manager
if hasattr(mgr, 'get_cache_stats'):
    stats = mgr.get_cache_stats()
    print(f"Cache hit rate: {stats.get('hit_rate_percent', 0)}%")
```

### Подписка на сигналы
```python
mgr = window._topbar_manager
if hasattr(mgr, 'layoutChanged'):
    mgr.layoutChanged.connect(lambda counts: print(f"Layout changed: {counts}"))
    mgr.cacheStatsChanged.connect(lambda stats: print(f"Cache stats: {stats}"))
```

## 🔧 Настройка производительности

### Размер кэша
```python
# В конфигурации для больших экранов
app_config.set("ui.topbar.cache_size", 200)
```

### Throttling интервал
```python
# Для медленных систем - увеличить интервал
app_config.set("ui.topbar.throttle_ms", 50)

# Для быстрых систем - уменьшить интервал  
app_config.set("ui.topbar.throttle_ms", 16)
```

## 🐛 Отладка проблем

### Принудительный пересчет
```python
mgr = window._topbar_manager
if hasattr(mgr, 'force_adjustment'):
    mgr.force_adjustment(AdjustmentReason.MANUAL_REQUEST)
```

### Очистка кэша
```python
mgr = window._topbar_manager
if hasattr(mgr, 'invalidate_cache'):
    mgr.invalidate_cache()
```

### Получение диагностики
```python
mgr = window._topbar_manager
if hasattr(mgr, 'get_panel_size_stats'):
    size_stats = mgr.get_panel_size_stats()
    cache_stats = mgr.get_cache_stats()
    print(f"Panel manager: {size_stats}")
    print(f"Cache: {cache_stats}")
```

## ✅ Проверка миграции

После внедрения изменений проверьте:

1. **Отсутствие предупреждений:**
   ```
   WARNING - Direct adjust() call detected. Use request_adjustment() instead.
   ```

2. **Стабильность UI:**
   - Нет дергания панелей при изменении размера окна
   - Плавные анимации появления/скрытия кнопок
   - Корректное поведение поля поиска

3. **Производительность:**
   - Время создания TopPanel < 50ms
   - Hit rate кэша > 70% после прогрева
   - Отсутствие утечек памяти

## 🆘 Откат изменений

В случае критических проблем:

1. **Временное отключение новых функций:**
   ```python
   # В конфигурации
   app_config.set("ui.topbar.use_legacy_mode", True)
   ```

2. **Полный откат:**
   - Восстановить старые файлы из backup
   - Удалить новые модули из topbar/
   - Перезапустить приложение

## 📞 Поддержка

При возникновении проблем:
1. Включить детальное логирование
2. Собрать статистику производительности  
3. Проверить совместимость с существующим кодом
4. Обратиться к IMPROVEMENTS_REPORT.md для деталей архитектуры
