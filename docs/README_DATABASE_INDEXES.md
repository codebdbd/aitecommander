# 🚀 Индексы базы данных - Краткая памятка

## ⚡ Быстрая проверка

```bash
# Проверить состояние индексов
python scripts/check_db_indexes.py
```

## 📋 Созданные индексы (миграция 0005)

### Таблица `link` (критичная)
| Индекс | Колонки | Назначение | Прирост |
|--------|---------|------------|---------|
| `idx_link_category_id` | category_id | Загрузка по категории | ⚡ Нет TEMP B-TREE |
| `idx_link_is_favorite` | is_favorite (WHERE =1) | Избранное | ⚡ 256x |
| `idx_link_last_used` | last_used DESC (WHERE NOT NULL) | Недавние | ⚡ 14x |
| `idx_link_category_position` | category_id, position | Загрузка + сортировка | ⚡ Covering index |
| `idx_link_category_name_url_args` | category_id, name, url, args | Поиск дубликатов | ⚡ Уникальность |
| `idx_link_type` | type | Фильтр по типу | ⚡ Группировка |

### Таблица `section`
- `idx_section_sphere_id` - загрузка разделов сферы
- `idx_section_sphere_position` - с сортировкой

### Таблица `category`
- `idx_category_section_id` - загрузка категорий раздела
- `idx_category_section_position` - с сортировкой

## 📊 Результаты (3837 ссылок)

```
БЫЛО:  ❌ SCAN link (3837 строк) - полное сканирование
СТАЛО: ✅ SEARCH idx_link_is_favorite (15 строк) - 256x быстрее!
```

## 🛠️ Команды

```bash
# Проверить индексы
python scripts/check_db_indexes.py

# Применить миграцию вручную (если нужно)
python scripts/apply_migration_0005.py

# Обновить статистику после массовой загрузки
sqlite3 path/to/links.db "ANALYZE"
```

## 📚 Полная документация

- **Технический аудит:** `TECHNICAL_AUDIT_PYQT6.md`
- **Детальный отчёт:** `DATABASE_PERFORMANCE_REPORT.md`
- **Миграция:** `app/models/migrations/0005_add_performance_indexes.py`

---

**Статус:** ✅ Оптимизация завершена | **Дата:** 2025-09-30
