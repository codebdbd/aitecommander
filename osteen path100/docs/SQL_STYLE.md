# SQL Style Guide (Project-wide)

Цель: единый и безопасный стиль написания SQL в проекте. Правила обязательны для всех новых и изменяемых запросов.

## Основные правила

- **Алиасы для агрегатов и выражений**
  Присваивайте понятные имена вычисляемым столбцам и агрегатам.
  
  Примеры:
  - `SELECT COUNT(*) AS cnt FROM link ...`
  - `SELECT COALESCE(MAX(position), 0) + 1 AS next_pos FROM link ...`
  - `SELECT MAX(position) AS max_pos FROM category ...`

- **Доступ к полям результата только по ключам**
  Не используйте позиционный доступ `row[0]`. Работайте с именованными ключами, либо сразу приводите `sqlite3.Row` к `dict` на границе метода.
  
  Примеры:
  - `row = cur.fetchone(); total = int(row["cnt"]) if row else 0`
  - `rows = cur.fetchall(); return [dict(r) for r in rows]`

- **Единый путь выполнения запросов в моделях**
  Используйте `DatabaseBase._execute_with_error_handling()` и глобальную блокировку `db_lock`. Это обеспечивает логирование ошибок и потокобезопасность.
  
  Пример:
  ```python
  rows = self._execute_with_error_handling(
      "SELECT id, name FROM category WHERE section_id=? ORDER BY position",
      (section_id,),
      fetch_method="all",
  )
  return [dict(r) for r in rows] if rows else []
  ```

- **Чёткая семантика методов**
  - Методы чтения (`get_*`) возвращают нормализованные структуры: списки `dict` или `dict | None`.
  - Методы подсчёта (`count_*`) возвращают `int` с алиасом `AS cnt`.
  - Методы вычисления позиции используют `AS next_pos`/`AS max_pos` и читают по ключу.

- **Типизация**
  Аннотируйте возвращаемые типы у публичных методов моделей:
  - `-> list[dict[str, Any]]`
  - `-> dict[str, Any] | None`
  - `-> int`, `-> bool`

## Чек-лист код‑ревью

- **Алиасы присутствуют** у агрегатов и выражений.
- **Нет позиционного доступа** к результатам SQL (`row[0]`, `row[1]`, ...).
- **В моделях** нет прямых `connection.execute(...)` там, где нужно централизованное логирование/обработка через `_execute_with_error_handling`.
- **Типы методов** возвращают ожидаемые структуры (`list[dict]`, `dict | None`, `int`).

## Быстрые примеры

Плохо (нельзя):
```python
row = cur.fetchone()
return row[0] if row else 0
```

Хорошо:
```python
row = cur.fetchone()
return int(row["cnt"]) if row else 0
```

Плохо (нельзя):
```python
row = self.connection.execute("SELECT MAX(position) FROM category").fetchone()
max_pos = row[0] if row else None
```

Хорошо:
```python
row = self.connection.execute(
    "SELECT MAX(position) AS max_pos FROM category"
).fetchone()
max_pos = dict(row).get("max_pos") if row else None
```

## Рекомендации для CI (опционально)

Добавьте простой линт-шаг поиска позиционного доступа в SQL‑слое. Базовый вариант — проверять только каталоги, где есть доступ к БД (например, `app/models/` и, если потребуется, `app/services/`).

Пример PowerShell‑скрипта (Windows runner):
```powershell
# Ищем потенциальные позиционные чтения row[<число>] в моделях
$pattern = "\[[0-9]+\]"
$paths = @("app/models/**/*.py")

$hasIssues = $false
foreach ($p in $paths) {
  $matches = Select-String -Path $p -Pattern $pattern -AllMatches -CaseSensitive
  foreach ($m in $matches) {
    # Исключаем случаи, когда это явно не SQL-результат (при необходимости, через более точные фильтры)
    Write-Host "Possible positional access: $($m.Path):$($m.LineNumber): $($m.Line.Trim())"
    $hasIssues = $true
  }
}

if ($hasIssues) {
  Write-Error "Found positional index usages in SQL layer. Please replace with aliased key access."
  exit 1
}
```

Примечания:
- Исключения и уточнение фильтров могут потребоваться, если в коде встречаются легитимные индексные доступы, не связанные с SQL (UI/парсеры и т.п.).
- В идеале — запускать проверку только по путям с SQL‑кодом.
