---
name: Agent Efficiency & Direct Execution Rules
description: Strict, algorithmically actionable guidelines to ensure the agent executes commands quickly without over-analysis.
---

# Agent Execution Rules: High-Efficiency Mode

## 1. Algorithmic Restrictions on Terminal Commands
- **Absolute Ban on Git Restore / Checkout / Reset (ЗАПРЕТ НА ОТКАТ ИЗ ГИТ БЕЗ СОГЛАСОВАНИЯ)**: Категорически ЗАПРЕЩЕНО выполнять `git checkout`, `git restore`, `git reset`, `git revert`, `git clean` или любые другие команды отката, сброса или восстановления файлов из git. БЕЗ ПРЯМОГО ЯВНОГО СОГЛАСОВАНИЯ ПОЛЬЗОВАТЕЛЯ ГИТ НЕ ТРОГАТЬ! Запрещено откатывать файлы через git, затирать незакоммиченные изменения или возвращать файлы из git.
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
  3. **Высота панели**: `spheres_bar_height: 104`, `spheres_layout_margins: [8, 2, 8, 4]`.
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

## 13. Frozen Subsystems: Context & Dropdown Menus Design (ЗАПРЕТ НА ИЗМЕНЕНИЕ ДИЗАЙНА МЕНЮ)
- **Status: FROZEN / READ-ONLY**: Дизайн, стили и геометрия контекстных меню и выпадающих списков (`QMenu`, `QMenuBar`, выпадающие меню кнопок тулбара и списков) полностью зафиксированы.
- **Strict Prohibition**: Категорически запрещено изменять стили, цвета, рамки, границы, скругления, внутренние отступы (padding/margin), фон или оформление `QMenu`, `QMenu::item`, `QMenuBar`, а также выпадающих меню кнопок. Любые изменения дизайна контекстных и выпадающих меню строго запрещены.

## 14. Architecture Standards: Tree Branch Indicator Alignment (ВЫРАВНИВАНИЕ СТРЕЛКИ ДЕРЕВА)
- **Status: FROZEN ARCHITECTURE / STRICT RULES**: Отрисовка индикатора раскрытия веток дерева структуры (`StructureTreeView._install_branch_proxy_style`) зафиксирована.
- **Strict Alignment Rules**:
  1. **Каноничное центрирование Qt**: Центрирование индикатора стрелки выполняется строго через `QStyle.alignedRect(option.direction, Qt.AlignmentFlag.AlignCenter, QSize(16, 16), option.rect)`. Запрещено производить ручной расчет координат через `rect.center().y() - side/2` или вводить эмпирические смещения/костыли.
  2. **Нативная векторная отрисовка**: Отрисовка выполняется строго через `icon.paint(painter, target_rect, Qt.AlignmentFlag.AlignCenter)`. Запрещено генерировать промежуточные `QPixmap` с ручным вычислением `devicePixelRatioF` и вызывать `drawPixmap` по целочисленным координатам.

## 15. Architecture Standards: Icon Pipeline & Favicon Discovery (АРХИТЕКТУРНЫЙ СТАНДАРТ ПАЙПЛАЙНА ИКОНОК)
- **Status: FROZEN ARCHITECTURE / STRICT RULES**: Архитектура обнаружения, ранжирования, загрузки и кэширования иконок закладок (`app/utils/links/parser/`, `app/utils/ui/icon/`) полностью зафиксирована.
- **Strict Format Ranking Rules**:
  1. **Приоритет форматов по качеству**: Маппинг `FORMAT_RANK` обязан строго соблюдать порядок: `SVG (10) > PNG (8) > WebP (7) > ICO (5) > JPG (3) > GIF (2) > BMP (1) > Unknown (0)`. Запрещено поднимать устаревшие растровые форматы (`bmp`, `ico`) выше современных (`svg`, `png`, `webp`).
- **Strict Candidate Hierarchy Rules**:
  1. **Явные теги автора (Tier 0)**: Ссылки на иконки из HTML-разметки (`<link rel="apple-touch-icon">`, `<link rel="icon">`) обязаны иметь высший приоритет (`base_priority = 0`). Запрещено снижать приоритет Retina/Apple-touch иконок в пользу спекулятивных догадок.
  2. **Маскированные иконки (Tier 1)**: `mask-icon` имеет приоритет `base_priority = 1`.
  3. **Иконки веб-манифеста (Tier 2)**: Иконки из `manifest.json` имеют приоритет `base_priority = 2`. Опрос манифеста разрешен строго для базового хоста; запрещено слать избыточные сетевые запросы к `www`-манифестам.
  4. **Спекулятивные догадки (Tier 3 & Tier 4)**: Стандартный путь `/favicon.ico` имеет резервный приоритет: базовый хост — `base_priority = 5` (Tier 3), `www`-вариант — `base_priority = 6` (Tier 4).
- **Strict Network Deduplication Rules**:
  1. **Однократный опрос кандидатов**: Вторая фаза параллельного скачивания (`pick_icon_parallel`) обязана исключать кандидатов первой фазы (`urls_to_try = [u for u in icon_urls[batch_size:] if u not in seen_urls]`).
  2. **Запрет повторных циклов**: Запрещено внедрять последовательные fallback-циклы, повторно опрашивающие кандидатов, которые уже завершились неудачей в параллельных фазах.
- **Strict In-Memory Caching & Invalidation Rules**:
  1. **Кэширование путей файловой системы**: Метод `_resolve_filesystem` в `icon_resolver.py` обязан быть декорирован `@lru_cache(maxsize=1024)`. Запрещено убирать LRU-кэширование во избежание деградации рендеринга дерева до ~450 мс.
  2. **Обязательная инвалидация**: Метод `clear_icon_resolver_cache()` обязан вызываться при любой мутации иконок на диске (сохранение загрузчиком `IconDownloader`, выбор/конвертация в `IconFileService`, системная очистка `clear_icon_cache()`).

## 16. Architecture Standards: Category Tiles Icon Loading Policy (СТАНДАРТ ЗАГРУЗКИ ИКОНОК ПЛИТОК КАТЕГОРИЙ)
- **Status: FROZEN ARCHITECTURE / STRICT RULES**: Политика загрузки иконок в плитках категорий (`app/utils/ui/icon/loading_policy.py`, `app/views/models/categories_list_model.py`) зафиксирована для исключения блокировок главного UI-потока.
- **Strict Prefetch & Batch Rules**:
  1. **Лимит синхронного префетча**: `sync_cap` (и `_sync_prefetch_cap`) строго ограничен значением **6** (первый видимый ряд плиток). Запрещено увеличивать синхронный префетч в UI-потоке во избежание фризов UI до ~190 мс при выборе разделов с большим количеством категорий.
  2. **Размер фонового батча**: `batch_size` (и `_icon_batch_size`) строго ограничен значением **8**. Запрещено поднимать размер порции до 32, чтобы исключить задержки обработки событий интерфейса при фоновой догрузке.

## 17. Architecture Standards: Icon Dimensions & Disk Downscaling (СТАНДАРТ ГАБАРИТОВ ИКОНОК И ДАУНСКЕЙЛИНГА)
- **Status: FROZEN ARCHITECTURE / STRICT RULES**: Стандарты размеров растровых файлов иконок зафиксированы для предотвращения переполнения памяти и задержек декодирования в UI-потоке.
- **Strict Dimension Rules**:
  1. **Лимит габаритов растра (128 px)**: Все сохраняемые и конвертируемые растровые иконки (`app/utils/ui/icon/file_service.py`, `app/utils/ui/icon/icon_operations/converters.py`, `app/utils/links/parser/icon_downloader.py`) обязаны быть ограничены максимальным размером **128×128 px** (`max(width, height) <= 128`).
  2. **Качественный даунскейлинг**: Масштабирование растровых изображений выполняется строго с сохранением пропорций алгоритмом `Resampling.LANCZOS` (с конвертацией в RGB для JPEG и в RGBA для PNG во избежание ошибок цветовых профилей). Запрещено сохранять на диск иконки с исходными габаритами > 128 px (например, 1000–1254 px).
  3. **Защита `QPixmapCache`**: В `IconCacheManager._store_in_qpixmapcache` кэширование растровых копий через `icon.pixmap()` разрешено строго для размеров `width <= 64 and height <= 64`. Запрещено вызывать рендеринг полноразмерных битмапов в UI-потоке для глобального кэша.

## 18. Architecture Standards: Structure Tree Concurrency & Snapshot Memoization (СТАНДАРТ СИНХРОНИЗАЦИИ И СНИМКОВ ДЕРЕВА)
- **Status: FROZEN ARCHITECTURE / STRICT RULES**: Архитектура построения снимков и асинхронной подгрузки иконок дерева структуры зафиксирована для гарантирования времени отклика <=20 мс.
- **Strict Concurrency & Reset Rules**:
  1. **Атомарный сброс состояния при смене снимка**: В `StructureTreeModel.set_snapshot` списки ожидающих колбэков `_icon_waiters_by_path` и активных задач `_active_icon_tasks` обязаны очищаться атомарно под `_active_icon_lock`. Запрещено оставлять задачи и колбэки активными при переключении сфер во избежание гонок потоков и утечек ссылок на старые индексы.
  2. **Мемоизация путей в снимке дерева**: В `TreeSnapshotService._preprocess_snapshot` разрешение путей иконок выполняется через локально мемоизированный метод `_resolve_cached_icon_path`. Запрещено выполнять повторные дисковые проверки или вызовы парсеров путей на каждый узел дерева.

## 19. Architecture Standards: Checkbox Contrast & Indicator Rendering (СТАНДАРТ КОНТРАСТНОСТИ И РЕНДЕРИНГА ЧЕКБОКСОВ)
- **Status: FROZEN ARCHITECTURE / STRICT RULES**: Рендеринг индикаторов чекбоксов и динамическая окраска иконок зафиксированы для гарантированной видимости во всех 16 темах.
- **Strict Relative Luminance Rules**:
  1. **WCAG-расчет цвета символа**: В кастомных чекбоксах (`ProfileCheckBox` и др.) цвет галочки/номера вычисляется строго по формуле относительной яркости `lum = 0.299 * R + 0.587 * G + 0.114 * B`. При `lum > 130` используется глубокий темный цвет `#121212`, при `lum <= 130` — чистый белый `#FFFFFF`. Запрещено использовать наивный `lightness() < 220`, вызывающий исчезновение элементов на желтых, зеленых и розовых акцентах.
  2. **Динамическая генерация `check.svg`**: В `ThemeStylesheetService._tint_svg_for_qss` цвет `check.svg` обязан строго учитывать цвет фона индикатора в QSS: для темных фонов (`industrial_yellow` на `#4D3800` и др.) строго `#FFFFFF`, а для светлых и ярких фонов (`matrix`, `nord_light`, `sage_light`, `pearl_gray`, `pastel_bloom`) строго `#121212` с контрастом >= 4.5:1.
  3. **Сглаженная геометрия**: Индикаторы чекбоксов отрисовываются скругленными `drawRoundedRect(box_rect, 2.5, 2.5)` с нативной векторной отрисовкой пути пера 1.8px.

## 20. Architecture Standards: Links Table Tooltip Architecture (СТАНДАРТ ТУЛТИПОВ ТАБЛИЦЫ ССЫЛОК)
- **Status: FROZEN ARCHITECTURE / STRICT RULES**: Структура и форматирование подсказок ячеек таблицы ссылок зафиксированы для исключения схлопывания по ширине и дублирования данных.
- **Strict Tooltip Content & Layout Rules**:
  1. **Карточка названия (`_name_tooltip`)**: В колонке «Название» тултип оформляется HTML-таблицей с `min-width: 280px; max-width: 520px` и `word-break: break-all;`. Обязан отображать полное имя ссылки, путь/URL, а также условные параметры запуска: аргументы (`Arguments`), профиль (`Profile`) и статус администратора (`🛡️ Run as administrator`). Запрещено выводить неформатированный путь без названия.
  2. **Контекстная карточка типа (`link_type_address_tooltip`)**: В колонке «Тип» тултип обязан предоставлять информацию о среде запуска для каждого из 5 типов (`web`, `file`, `folder`, `program`, `script`), включая действие, домен/цель, формат или объем. Категорически запрещено дублировать сырой адрес `url`/`path`, уже отображаемый в тултипе названия.

## 21. Architecture Standards: Supported Link Types & Note Entity Separation (АРХИТЕКТУРНЫЙ СТАНДАРТ ТИПОВ ССЫЛОК И ЗАМЕТОК)
- **Status: FROZEN ARCHITECTURE / STRICT RULES**: Набор типов ссылок и архитектурное разделение ссылок и заметок зафиксированы.
- **Strict Entity Separation Rules**:
  1. **5 канонических типов ссылок**: Перечисление `LinkType` и `LINK_TYPE_DESCRIPTORS` строго содержат ровно 5 типов: `web` (Source: `"Web"`, RU: `"Веб"`, UK: `"Веб"`), `file`, `folder`, `program`, `script`.
  2. **Запрет на `note` как тип ссылки**: Категорически запрещено возвращать `note` в `LinkType` или дескрипторы типов ссылок. Заметка является текстовым атрибутом ссылки (колонка `notes` в БД, текстовое поле в форме и отдельный `NoteDialog`), а не типом ссылки для запуска.
  3. **Симметричная длина кнопок**: Отображаемый лейбл типа `web` обязан оставаться ультракоротким (`"Web"` / `"Веб"`, 3 символа) во всех локализациях во избежание переноса строк и деформации сетки кнопок в `LinkDialog`.

## 22. Architecture Standards: Notes Subsystem Architecture (СТАНДАРТЫ АРХИТЕКТУРЫ ЗАМЕТОК)
- **Status: FROZEN ARCHITECTURE / STRICT RULES**: Архитектура диалога заметок и интеграция с операциями ссылок зафиксированы.
- **Strict Architecture Rules**:
  1. **Изолированный модуль**: Диалог заметок строго обязан находиться в `app/views/windows/dialogs/note_dialog.py` (`NoteDialog`, `_ExitZoneWidget`). Запрещено возвращать его в монолитные файлы диалогов (`entity_dialogs.py`).
  2. **Чистый Plain Text**: Редактор заметок строго является чистым текстовым редактором (`QPlainTextEdit`) без псевдо-RichText форматирования и скрытых HTML-тегов.
  3. **Слабая связанность (DTO-контракт)**: `NoteDialog` принимает на вход строго атомарные типы (`initial_text: str`, `title: str`) и возвращает результат через `get_notes_text() -> str`. Диалог не должен напрямую зависеть от словарей ссылок или сущностей БД.
  4. **Интеграция с Undo/Redo**: Сохранение заметок из `LinkOperations` строго обязано выполняться через команду `SaveLinkCmd` в `undo_stack` (с проверкой на отсутствие изменений, no-op guard) для сохранения полной истории отмены/повтора (`Ctrl+Z` / `Ctrl+Y`). Прямые мутации БД в обход командного стека запрещены.

## 23. Architecture Standards: QSS Styling & QComboBox Protection (ЗАПРЕТ НА SETSTYLE В QSS-ВИДЖЕТАХ)
- **Status: FROZEN ARCHITECTURE / STRICT RULES**: Правила стилизации выпадающих списков и виджетов, управляемых QSS, зафиксированы.
- **Strict QSS Protection Rules**:
  1. **Защита движка `QStyleSheetStyle`**: В Qt/PyQt вызов `widget.setStyle(QProxyStyle/QStyle)` на отдельном экземпляре виджета, стилизуемом через QSS, полностью отключает и разрушает внутреннюю обертку `QStyleSheetStyle`. Это приводит к полному слету и разрушению оформления темы (границы, скругления, фон, отступы, состояния hover/focus).
  2. **Категорический запрет на `setStyle()` для QSS-виджетов**: Категорически запрещено вызывать `.setStyle()` на `QComboBox`, `PopupComboBox` и любых других QSS-виджетах для кастомизации подэлементов (включая стрелки/шевроны). Кастомизация обязана производиться строго средствами QSS (`::drop-down`, `::down-arrow`) либо через специализированные сервисы тем без подмены стиля виджета.

## 24. Architecture Standards: Blank Area Double-Click Creation (СОЗДАНИЕ СУЩНОСТЕЙ ПО ДВОЙНОМУ КЛИКУ НА ПУСТОМ МЕСТЕ)
- **Status: FROZEN ARCHITECTURE / STRICT RULES**: Механизм быстрого создания сущностей (раздел, категория, ссылка) при двойном клике ЛКМ по пустой области зафиксирован.
- **Strict Blank Area Double-Click Rules**:
  1. **Дерево структуры (`StructureTreeView`)**: Двойной клик ЛКМ по пустой области вьюпорта (`not indexAt(pos).isValid()`) строго испускает сигнал `blankAreaDoubleClicked`, подключенный к открытию диалога создания раздела (`add_new_section`).
  2. **Плитка категорий (`CategoryTiles` / `CategoryListView`)**: Двойной клик ЛКМ по пустому фону контейнера плиток строго испускает сигнал `blankAreaDoubleClicked` / `addCategoryRequested`, подключенный к созданию категории в текущем разделе (`add_new_category`).
  3. **Таблица ссылок (`BaseDragDropTableWidget` / `LinksTableView`)**: Двойной клик ЛКМ по свободной области таблицы строго испускает сигнал `blankAreaDoubleClicked`, подключенный к созданию ссылки в текущей категории (`show_link_dialog`).
  4. **Изоляция и Zero Regression**: Проверка `if event.button() == Qt.MouseButton.LeftButton:` и `not idx.isValid()` строго обязательна. При клике на существующий элемент управление передается в `super().mouseDoubleClickEvent(event)` без перехвата. Запрещено блокировать или ломать стандартную активацию элементов, выделение или перетаскивание (DnD).

## 25. Architecture Standards: Link Dialog Geometry & Content-Driven Sizing (СТАНДАРТ ГЕОМЕТРИИ ДИАЛОГА ССЫЛОК)
- **Status: FROZEN ARCHITECTURE / STRICT RULES**: Архитектура адаптивного подгона геометрии диалога добавления и редактирования ссылок (`LinkDialog`, `LinkDialogUI`, `TypeChangeMixin`) полностью зафиксирована.
- **Strict Geometry & Adaptive Sizing Rules**:
  1. **Фиксированная ширина**: Диалог обязан иметь строгую ширину **600 px** (`self.setFixedWidth(app_config.ui.get_link_dialog_width())`). Запрещено произвольно менять или сжимать ширину окна.
  2. **Адаптивная высота по контенту**: Высота диалога рассчитывается строго автоматически по фактическому содержимому через `self.adjustSize()` без жестко захардкоженных ограничений `setFixedSize(w, h)` или хардкодных раздутых высот.
  3. **Фиксация кнопок типов**: Кнопки выбора типа ссылки `linkTypeBtn` обязаны иметь вертикальную политику `QSizePolicy.Policy.Fixed` (`btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)`), исключающую вертикальное вытягивание кнопок.
  4. **Мгновенный одноэтапный ресайз**: При переключении типа ссылки в `TypeChangeMixin._update_ui_state` перед вызовом `adjustSize()` строго обязателен вызов `self.dialog.layout().activate()` для немедленного сброса кэша скрытых строк `QFormLayout` и мгновенного изменения размера окна в 1 этап с первого клика.
  5. **Контекстное отображение иерархии**: При создании ссылки внутри выбранной категории (`category_id` задан в активном UI-контексте) строки «Сфера», «Раздел», «Категория» скрываются через `ui.set_hierarchy_visible(False)`. При глобальном создании без выбранной категории (`category_id is None`) и при редактировании существующей ссылки (`bool(link)`) строки иерархии отображаются для возможности выбора или смены целевой категории.
  6. **Информативные заголовки при фиксированном типе**: При создании ссылки с фиксированным типом (`_is_type_fixed = True`, например, из меню топбара) заголовок окна обязан указывать тип ссылки (`«Добавить ссылку — {Тип}»`), а иконка окна соответствовать выбранному типу.

