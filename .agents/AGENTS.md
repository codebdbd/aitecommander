---
name: Agent Efficiency & Direct Execution Rules
description: Strict, algorithmically actionable guidelines to ensure the agent executes commands quickly without over-analysis.
---

# Agent Execution Rules: High-Efficiency Mode

## 1. Algorithmic Restrictions on Terminal Commands
- **Git Commit Workflow**: When requested to commit, you MUST execute exactly `git add -A` followed by `git commit -m "<message>"` and `git push`. Do NOT run `git status` or `git diff` first.
- **Banned Commands**: You MUST NEVER execute `pytest`, `ruff`, `flake8`, `mypy`, or any other linter/testing tool unless the user explicitly writes the word "проверь", "тест" or "lint".
- **Time Limits**: For any terminal command, set `WaitMsBeforeAsync` to no more than 5000 (5 seconds). If it takes longer, it must go to the background. DO NOT loop or poll endlessly.

## 2. Strict Positive Directives for Code Edits
- **Scope Containment**: Modify ONLY the exact lines of code required to fulfill the user's explicit request. 
- **Blindness to Context**: If you see an unrelated bug, an unused import, or poorly formatted code in the same file, you MUST LEAVE IT AS IS. 
- **No Refactoring**: You MUST NOT change variable names, extract functions, or reformat code unless specifically asked to refactor.
- **No Infrastructure Deletion**: NEVER delete, bypass, or replace existing calls to `app_config`, settings readers, signals, or configuration-driven logic with hardcoded values.

## 3. Communication Constraints
- **Zero Explanation Rule**: Upon completing a task, your response MUST be extremely brief. "Готово" (Done) is ideal. Do NOT list the files you changed. Do NOT explain your logic.
- **No Permissions**: If a file is missing or untracked during an operation (e.g., git commit), assume it is intentional and proceed. DO NOT stop to ask the user for permission.

## 4. Mandatory Workflow Rule (ОБЯЗАТЕЛЬНО К ИСПОЛНЕНИЮ)
- **Strict Order of Action**: Before touching ANY code, you MUST follow this strict sequence:
  1. **Причина**: Describe the exact root cause of the problem.
  2. **Решение**: Describe the proposed technical solution.
  3. **План**: Provide a detailed implementation plan containing the EXACT unified diff (code blocks showing exact lines to be removed `-` and added `+`). Never propose vague text summaries without the exact diff.
  4. **Согласование**: Wait for explicit user approval.
  5. **Смена кода**: ONLY after user approval, make code changes. NO EXCEPTIONS.

## 5. Frozen Subsystems: Shutdown Protection (ЗАПРЕТ НА ИЗМЕНЕНИЯ ШАТДАУНА)
- **Status: FROZEN / READ-ONLY**: Механизм закрытия приложения (`app_shutdown_controller.py`, метод `closeEvent` в `main_window.py`, логика shutdown в `runtime.py`) полностью заморожен.
- **Strict Prohibition**: Запрещено вносить любые правки, менять порядок вызовов, рефакторить, переписывать таймауты или оптимизировать процесс завершения.
- **No Theoretical Audits**: При любых вопросах о закрытии запрещено выдумывать теоретические проблемы и предлагать рефакторинг.

## 6. Frozen Subsystems: Spheres Bar & Dock Architecture (ЗАПРЕТ НА ИЗМЕНЕНИЕ ПАНЕЛИ СФЕР)
- **Status: FROZEN / READ-ONLY**: Дизайн, геометрия и физика панели сфер (`spheres_bar`), кнопок сфер (`SphereToolButton`) и контроллера (`SpheresBarController`) полностью зафиксированы.
- **Strict Parameters**:
  1. **Ширина левой панели**: строго **320 px** (`splitter_sizes: [320, 704]`).
  2. **Отступы и сетка**: `spheres_bar_spacing: 8`, `spheres_bar_margin_left: 8`, `spheres_bar_margin_right: 8`.
  3. **Высота панели**: `spheres_bar_height: 96`, `spheres_layout_margins: [8, 2, 8, 4]`.
  4. **Размер кнопок**: строго **70×88 px** (`icon_w + 6, icon_h + 24`).
  5. **Масштабирование macOS Dock**: формула `size = 56.0 + 14.0 * s` (56 px в покое, 70 px на пике), базовая линия `bottom_y = rect.height() - 14`.
  6. **Индикатор активной сферы**: круглая точка диаметром **5.0 px** на `y = rect.height() - dot_d - 3.0` строго при `isChecked()`. Без фонов и рамок.
  7. **Сглаживание**: рендеринг через `QRectF` и `painter.drawPixmap(icon_rect_f, pix, ...)`, шаг LERP `0.18`.
  8. **Поведение при нажатии (macOS Dock click)**: Полное отсутствие фоновых подложек, рамок или цветовых эффектов `:pressed` (строго `background: transparent; border: none;` во всех темах и `common.qss`). Иконка при зажатии остаётся монолитной и стабильной, без сжатий, дёрганий, рывков или затемнения/полупрозрачности.
- **Strict Prohibition**: Запрещено изменять размеры, отступы, базовую линию, формулу зума, возвращать фоновые подложки или добавлять смещения/сжатия/затемнения при нажатии кнопок сфер.

## 7. Frozen Subsystems: Scrollbar Styling (ЗАПРЕТ НА ИЗМЕНЕНИЕ СКРОЛЛБАРОВ)
- **Status: FROZEN / READ-ONLY**: Дизайн и геометрия скроллбаров (`QScrollBar`) полностью зафиксированы.
- **Strict Parameters**:
  1. **Стиль**: Минималистичный капсульный скроллбар (macOS / Fluent Capsule Style) строго в `app/resources/qss/common.qss`.
  2. **Ширина/высота**: строго **6 px** (`width: 6px;` вертикальный, `height: 6px;` горизонтальный).
  3. **Скругление бегунка**: строго **`border-radius: 3px`** (`min-height: 28px; min-width: 28px;`).
  4. **Цвета**: `background: rgba(140, 140, 140, 0.35)` в покое, `rgba(140, 140, 140, 0.65)` при hover, `rgba(140, 140, 140, 0.85)` при pressed.
  5. **Дорожка и стрелки**: `background: transparent; border: none;`, стрелки скрыты (`width: 0px; height: 0px;`).
  6. **Запрет на локальные стили**: Запрещено возвращать локальные `bar.setStyleSheet(...)` с инлайн-стилями скроллбаров в Python-код виджетов (`StructureTreeView`, `BaseDragDropTableWidget` и др.).
- **Strict Prohibition**: Запрещено изменять размеры, скругления, цвета, отступы скроллбаров или переопределять их локальными стилями.

## 8. Frozen Subsystems: Browser Bookmark Import (ЗАЩИТА ИМПОРТА ЗАКЛАДОК)
- **Status: FROZEN / READ-ONLY ARCHITECTURE**: Механизм импорта закладок браузера (`import_browser_html.py`, `import_browser_dialog.py`, методы импорта в `links_business.py`) зафиксирован.
- **Strict Architecture Rules**:
  1. **Разделение классов**: Класс `_NetscapeBookmarkParser(HTMLParser)` строго обязан находиться на уровне модуля **до** объявления `BrowserBookmarksImporter`. Запрещено объявлять его внутри других классов или нарушать отступы.
  2. **Публичный интерфейс**: Класс `BrowserBookmarksImporter` обязан сохранять методы: `select_file(parent_widget)`, `parse_bookmarks(html_path) -> dict`, `sync_to_db(...)`.
  3. **Стековый алгоритм HTML**: Разбор HTML-закладок Netscape ведётся строго через `HTMLParser` со стеком папок (`folder_stack`). При теге `<DL>` категория добавляется в стек, при `</DL>` — извлекается (`pop()`), возвращая контекст в родительскую категорию. Запрещено возвращать нестековый или DOM-рекурсивный парсинг через BeautifulSoup.
  4. **Сохранение данных при переполнении**:
     - `name`: при длине > 255 символов обрезается до 255, а полный исходный заголовок обязательно сохраняется в `notes`.
     - `url`: лимит 2048 символов.
     - `notes`: лимит 10 000 символов.
     - `category name`: лимит 255 символов.
  5. **Геометрия окна**: `ImportBrowserDialog` обязан иметь размер строго по содержимому через `vbox.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)`. Запрещено возвращать свободное растягивание окна пользователем или хардкод `resize()` с пустыми полями.
- **Strict Prohibition**: Запрещено ломать иерархию классов, убирать стековый возврат из папок, удалять сохранение длинных названий в заметки или возвращать растягивание диалога.

## 9. Architecture Standards: Internationalization (СТАНДАРТЫ ЛОКАЛИЗАЦИИ И ПЕРЕВОДОВ)
- **Status: FROZEN ARCHITECTURE / STRICT RULES**: Подсистема локализации (`i18n`, `LanguageService`, каталоги `app_*.ts/.qm`, `qtbase_*.qm`) полностью стандартизирована.
- **Strict AST Rules**:
  1. **Разметка внутри классов Qt**: строго `self.tr("Source Text")` внутри наследников `QObject`/`QWidget` (контекст определяется именем класса).
  2. **Разметка вне классов Qt**: строго `QCoreApplication.translate("LiteralContext", "Source Text")`. Контекст обязан быть строковым литералом! Запрещено передавать переменные в качестве имени контекста.
  3. **Запрет на кастомные функции-обёртки**: Запрещено объявлять функции `_tr()` или любые другие промежуточные обёртки. `pylupdate6` их не распознаёт.
  4. **Англоязычный Source Text**: Исходный текст (`<source>`) обязан быть на английском языке. Запрещено использовать русские строки в качестве `source`.
- **Strict Pluralization Rules**:
  1. **Нативный синтаксис `%n`**: Множественные числа оформляются строго через `%n` и передачу счётчика в третий параметр: `self.tr("%n item(s)", "", count)`.
  2. **Запрет ручной склейки**: Запрещено склеивать множественные числа через f-строки вида `f"{count} {unit}"`.
  3. **Формы `<numerusform>`**: В каталогах `.ts` для RU/UK строго 3 формы, для EN/DE/ES/FR строго 2 формы.
- **Strict CLI & CI/CD Gate**:
  1. **Единый инструмент управления**: Все операции ведутся строго через `python -m i18n` (`check`, `update`, `compile`, `all`, `add-language`). Запрещено использовать кастомные скрипты или прямой вызов `pyrcc6` для файлов переводов.
  2. **Zero-Defect Quality Gate**: Любые изменения обязаны проходить `python -m i18n check` с кодом выхода 0: строго 100% готовность, 0 `unfinished`, 0 `vanished` и 100% паритет по всем 6 языкам (`en`, `ru`, `uk`, `de`, `es`, `fr`).
- **Strict Dynamic Retranslation**:
  1. **Миксин `ReTranslatable`**: Виджеты и диалоги, поддерживающие смену языка на лету, обязаны наследоваться от `ReTranslatable` и реализовывать `retranslateUi()`.
  2. **Запрет на `changeEvent(LanguageChange)`**: Запрещено переопределять `changeEvent(LanguageChange)` в диалогах во избежание гонки состояний при двухэтапной установке системного (`qtbase`) и прикладного (`app`) переводчиков.

## 10. Frozen Subsystems: Quick Look Architecture (ЗАЩИТА АРХИТЕКТУРЫ QUICK LOOK)
- **Status: FROZEN ARCHITECTURE / STRICT RULES**: Подсистема быстрого просмотра файлов Quick Look (`quick_look_dialog.py`, методы вызова в `links/controller.py`) полностью зафиксирована.
- **Strict Lifecycle Rules**:
  1. **Singleton & Переиспользование**: `QuickLookDialog` создаётся один раз в контроллере (`_quick_look_dialog`) и переиспользуется через `set_link()`.
  2. **Очистка контекстных меню**: В начале метода `set_link()` строго обязателен вызов `self._cleanup_context_menus()`. Запрещено убирать вызов очистки во избежание утечки памяти меню при навигации стрелками вверх/вниз.
- **Strict Key Dispatching Rules**:
  1. **Единый обработчик событий**: Обработка горячих клавиш (`Space`, `Esc`, `Enter`, `F/F11`, `Ctrl+C`, `Ctrl+Shift+C`, `Ctrl+A`, `Ctrl+E`, зум `Ctrl+±/0`, `PageUp/Down`, `Home/End`, `Up/Down`) ведётся строго через `_handle_key_event(event: QKeyEvent) -> bool`. Запрещено дублировать код обработки клавиш раздельно в `eventFilter` и `keyPressEvent`.
- **Strict Memory & I/O Protection (OOM Guard)**:
  1. **Ограничение чтения текста**: Текстовые файлы читаются строго чанком до **64 KB** (`read(65536)`). Запрещено читать файлы целиком без лимита размера.
  2. **Лимит строк таблиц**: Для электронных таблиц (`.xlsx`, `.csv`) лимит предпросмотра строго **100 строк**.
  3. **Лимит списков архивов**: Для архивов (`.zip`, `.jar`) и папок лимит элементов списка строго **100 элементов**.
- **Strict Geometry & Error Handling Rules**:
  1. **Персистентность геометрии**: Сохранение геометрии ведётся строго в `QSettings` (`quick_look_geometry`) при `closeEvent` и восстанавливается через `restoreGeometry()`. Запрещено убирать сохранение геометрии.
  2. **Деликатная обработка ошибок**: При отсутствии файла на диске диалог отображает информационную карточку ошибки в стеке страниц. Запрещено выбрасывать модальные `QMessageBox` или вызывать системные звуковые сигналы.

## 11. Architecture Standards: Startup Preload & Spheres Bar (МГНОВЕННЫЙ СТАРТ ПАНЕЛИ СФЕР)
- **Status: FROZEN ARCHITECTURE / STRICT RULES**: Порядок инициализации панели сфер и предзагрузки зафиксирован для исключения задержек (pop-in / flicker).
- **Strict Startup Preload Rules**:
  1. **Синхронная предзагрузка сфер**: В `SpheresBarController.init()` сферы загружаются синхронно через `sb.get_spheres()` (<0.2 мс) и немедленно отрисовываются через `self.on_spheres_loaded_ui(spheres)` до вызова `window.show()`. Асинхронный вызов `sb.load_spheres_async()` используется строго как fallback при пустом результате.
  2. **Запрет на откладывание инициализации**: В `WindowInitializer._initialize_spheres()` запрещено откладывать инициализацию сфер через `QTimer.singleShot(0, ...)` при видимости окна — кнопки обязаны быть созданы синхронно на шаге `AFTER_DB_STEP_CONFIG`.

## 12. Architecture Standards: Structure Tree State & Expansion (СОХРАНЕНИЕ СОСТОЯНИЯ ДЕРЕВА)
- **Status: FROZEN ARCHITECTURE / STRICT RULES**: Механизм сохранения состояния свернутости/развернутости разделов и выбора элементов дерева зафиксирован.
- **Strict Expansion & Selection Rules**:
  1. **Персистентность раскрытых разделов**: Состояние раскрытых разделов сохраняется в `QSettings` (`Tree/ExpandedSections_{sphere_id}`) при сигналах дерева `expanded`/`collapsed` и восстанавливается при `initial_load` через `TreeManagement._after_snapshot_applied` -> `TreeStateService.restore_expanded_state()`. Запрещено обнулять `expanded_state` на старте.
  2. **Запрет на принудительное раскрытие разделов**: В `SelectionWorkflowService.restore_selection_after_load` строго запрещено вызывать `self._tree.expand(index)` при выборе раздела (`item_type == "section"`). Выбор раздела отображает его плитки в правой панели, но обязан сохранять свернутое или развернутое состояние ветки в дереве без изменений.
  3. **Раскрытие только предков для дочерних категорий**: Автоматическое раскрытие (`_expand_index_path` / `expand(parent_index)`) разрешено строго для родительских узлов при выборе дочерней категории, чтобы обеспечить видимость выбранного элемента в иерархии.

