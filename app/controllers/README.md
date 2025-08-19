# Контроллеры: новая структура и правила импортов

Этот README описывает новую структуру контроллеров, цели рефакторинга и единые правила импортов.

## Цели рефакторинга
- Разделить UI и доменную логику.
- Перейти на предсказуемые фасады (реэкспорт), чтобы безопасно менять пути импортов.
- Сохранить стабильность приложения во время переноса.

## Дерево директорий
- `app/controllers/ui/`
  - `dialogs/` — контроллеры диалогов (LinkDialog и т.п.)
  - `links/` — UI контроллеры панели ссылок
  - `structure/` — UI контроллеры структуры (сферы/разделы/категории)
- `app/controllers/domain/`
  - `structure/`
    - `commands/` — команды (Command pattern) для операций над структурой/ссылками
    - `business.py` — фасад бизнес‑логики структуры (реэкспорт класса)
    - `structure_business.py` — бизнес‑логика структуры (сферы, разделы, категории)
- `app/controllers/structure_modules/` — модули и вспомогательные компоненты для бизнес‑логики структуры
- Прочие (например, `keyboard/`) — без изменений

## Единые правила импортов
- UI диалоги:
  ```python
  from app.controllers.ui.dialogs import LinkDialogController  # пример
  ```
- UI ссылки:
  ```python
  from app.controllers.ui.links import LinksUIController
  ```
- UI структура:
  ```python
  from app.controllers.ui.structure import StructureUIController  # пример
  ```
- Команды домена:
  ```python
  from app.controllers.domain.structure.commands import SaveLinkCommand  # пример
  ```
- Бизнес‑логика структуры:
  ```python
  from app.controllers.domain.structure.business import StructureBusinessLogic
  ```

Примечание: внутренние импорты в `structure_business.py` используют `app.controllers.structure_modules.*`.

## Чек‑лист после изменений
- Импортный дым‑тест:
  ```pwsh
  python -c "import sys; sys.path.insert(0, r'b:\osteen path'); mods=['app.controllers.bootstrap','app.controllers.ui.dialogs','app.controllers.ui.links','app.controllers.ui.structure','app.controllers.domain.structure.commands','app.controllers.domain.structure.business']; [__import__(m) for m in mods]; print('IMPORT_OK')"
  ```
- Запуск приложения: главное окно отображается, тема применяется, без `ImportError`.
- UI смоук:
  - Диалоги открываются.
  - Структура загружается, переключаются сферы, добавляются/редактируются разделы и категории.
  - Операции со ссылками (открытие/сохранение/фокус) работают.

## Почему есть «пустые» папки
Каталоги с `__init__.py` — пакетные корни, они выглядят пустыми, но нужны для импортов (`ui/`, `domain/`, `domain/structure/`). Удаляйте только реально пустые хвосты после переноса.

## Команды PowerShell для чистки
- Удалить все `__pycache__` под `controllers/`:
  ```pwsh
  Get-ChildItem "b:\osteen path\app\controllers" -Recurse -Force -Directory -Filter "__pycache__" | Remove-Item -Force -Recurse
  ```
- Показать пустые директории:
  ```pwsh
  Get-ChildItem "b:\osteen path\app\controllers" -Recurse -Force -Directory | Where-Object { -not (Get-ChildItem $_.FullName -Force) }
  ```
- Удалить пустые директории:
  ```pwsh
  Get-ChildItem "b:\osteen path\app\controllers" -Recurse -Force -Directory | Where-Object { -not (Get-ChildItem $_.FullName -Force) } | Remove-Item -Force -Recurse
  ```

## Миграционные заметки
- Старые пути вида `app.controllers.dialog`, `app.controllers.links_ui`, `app.controllers.structure` (UI), `app.controllers.commands` не должны использоваться.
- Используйте фасады выше. Это упрощает дальнейшие перемещения без каскадных правок.

## Контакты
Если в логах появились `ModuleNotFoundError`/`ImportError` — проверьте импортный чек‑лист и соответствие путей примерам выше.
