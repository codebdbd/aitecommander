---
name: Agent Efficiency & Direct Execution Rules
description: Strict, algorithmically actionable guidelines to ensure the agent executes commands quickly without over-analysis.
---

# Agent Execution Rules: High-Efficiency Mode

## 0. Meta-Rule: Rule Precedence & Conflict Resolution
- **Rule Superseding**: При возникновении расхождений между разделами приоритет имеет более глобальный и поздний утверждённый контракт (§53 Sharp Geometry, §55 323px Left Panel, §56 Active Context & Model/View). Одновременно действующие взаимоисключающие правила категорически запрещены. Старые формулировки обязаны приводиться в соответствие с действующим контрактом приложения.

## 1. Algorithmic Restrictions on Terminal Commands
- **Absolute Ban on Git Restore / Checkout / Reset (ЗАПРЕТ НА ОТКАТ ИЗ ГИТ БЕЗ СОГЛАСОВАНИЯ)**: Категорически ЗАПРЕЩЕНО выполнять `git checkout`, `git restore`, `git reset`, `git revert`, `git clean` или любые другие команды отката, сброса или восстановления файлов из git. БЕЗ ПРЯМОГО ЯВНОГО СОГЛАСОВАНИЯ ПОЛЬЗОВАТЕЛЯ ГИТ НЕ ТРОГАТЬ! Запрещено откатывать файлы через git, затирать незакоммиченные изменения или возвращать файлы из git.
- **Git Commit Workflow**: When requested to commit, you MUST run `git status` to verify what files are changed, ensure no caches/dumps are accidentally staged, then execute `git add -A`, `git commit -m "<message>"` and `git push`.
- **Banned Commands**: You MUST NEVER execute `pytest`, `ruff`, `flake8`, `mypy`, or any other linter/testing tool unless the user explicitly writes the word "проверь", "тест" or "lint".
- **Time Limits**: For any terminal command, set `WaitMsBeforeAsync` to no more than 5000 (5 seconds). If it takes longer, it must go to the background. DO NOT loop or poll endlessly.

## 2. Strict Positive Directives for Code Edits
- **Scope Containment**: Modify ONLY the exact lines of code required to fulfill the user's explicit request. 
- **Blindness to Context**: If you see an unrelated bug, an unused import, or poorly formatted code in the same file, you MUST LEAVE IT AS IS. 
- **No Refactoring**: You MUST NOT change variable names, extract functions, or reformat code unless specifically asked to refactor.
- **No Infrastructure Deletion**: NEVER delete, bypass, or replace existing calls to `app_config`, settings readers, signals, or configuration-driven logic with hardcoded values.
- **Contract-Driven Test Updates (ЗАПРЕТ НА ЛОМКУ КОДА РАДИ ТЕСТОВ)**: Боевой код и утверждённые контракты приложения первичны. Категорически ЗАПРЕЩЕНО менять, ломать или откатывать рабочий код приложения ради прохождения устаревших тестов. При изменении контракта или логики программы обновляться ОБЯЗАНЫ ТЕСТЫ под новый контракт, а не рабочий код!

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
  1. **Ширина левой панели**: строго **323 px** (`splitter_sizes: [323, 701]`).
  2. **Отступы и сетка**: `spheres_bar_spacing: 8`, `spheres_bar_margin_left: 8`, `spheres_bar_margin_right: 8`.
  3. **Высота панели**: `spheres_bar_height: 96`, `spheres_layout_margins: [8, 2, 8, 4]`.
  4. **Размер кнопок**: строго **70×88 px** (`icon_w + 6, icon_h + 24`).
  5. **Масштабирование macOS Dock**: формула `size = 56.0 + 14.0 * s` (56 px в покое, 70 px на пике), базовая линия `bottom_y = rect.height() - 14`.
  6. **Индикатор активной сферы**: круглая точка диаметром **5.0 px** на `y = rect.height() - dot_d - 3.0` строго при `isChecked()`. Без фонов и рамок.
  7. **Сглаживание**: рендеринг через `QRectF` и `painter.drawPixmap(icon_rect_f, pix, ...)`, шаг LERP `0.18`.
  8. **Поведение при нажатии (macOS Dock click)**: Полное отсутствие фоновых подложек, рамок или цветовых эффектов `:pressed` (строго `background: transparent; border: none;` во всех темах и `common.qss`). Иконка при зажатии остаётся монолитной и стабильной, без сжатий, дёрганий, рывков или затемнения/полупрозрачности.
  9. **Компоновка левой панели (Left Panel Monolith & Native Scroll)**: Панель сфер располагается строго внизу левой панели с фиксированной высотой **96 px** (`setFixedHeight(96)`). Дерево (`StructureTreeView`) монолитно занимает всё пространство от верхнего разделителя до панели сфер без искусственных отступов (`setContentsMargins` строго 0, `spacing: 0`). Прокрутка дерева ведётся строго нативным методом `ScrollPerItem` с шагом колеса по целым строкам (`wheelEvent`). Категорически запрещено внедрять динамические фильтры геометрии, искусственные отступы-заглушки или вмешиваться в нативный рендеринг строк дерева.
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
- **Strict Menu Naming & Typography Rules**: Категорически запрещено использовать троеточия (`...`) в названиях пунктов меню (`MenuTexts`, `QAction`, контекстные и главные меню). Все пункты меню, обозначающие действия, обязаны быть строго глаголами в неопределенной форме (инфинитивы): «Импортировать категорию», «Экспортировать раздел», «Добавить категорию», «Редактировать раздел» (запрещено смешивать существительные вроде «Импорт/Экспорт» с глаголами).

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
  1. **WCAG-расчет цвета символа**: В кастомных чекбоксах (`ProfileCheckBox` и др.) контрастность галочки/номера проверяется по стандарту относительной яркости WCAG 2.1 (Relative Luminance) и контрастности не ниже 4.5:1 к фону индикатора в соответствии с §27. Для светлых акцентов используется глубокий темный цвет `#121212`, для темных — чистый белый `#FFFFFF`. Запрещено использовать наивный `lightness() < 220`, вызывающий исчезновение элементов на желтых, зеленых и розовых акцентах.
  2. **Динамическая генерация `check.svg`**: В `ThemeStylesheetService._tint_svg_for_qss` цвет `check.svg` обязан строго учитывать цвет фона индикатора в QSS: для темных фонов (`industrial_yellow` на `#4D3800` и др.) строго `#FFFFFF`, а для светлых и ярких фонов (`matrix`, `nord_light`, `sage_light`, `pearl_gray`, `pastel_bloom`) строго `#121212` с контрастом >= 4.5:1.
  3. **Монолитная геометрия**: Индикаторы чекбоксов подчиняются стандарту §53 и отрисовываются строго прямоугольными `drawRect(box_rect)` с нативной векторной отрисовкой пути пера 1.8px без скругления.

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
  1. **Защита стилизации QSS**: В Qt/PyQt вызов `widget.setStyle(QProxyStyle/QStyle)` на отдельном экземпляре виджета вступает в прямой конфликт с глобальным менеджером тем и каскадом QSS, приводя к визуальным дефектам оформления темы.
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
   7. **Монолитный сегментированный бар типов (`linkTypeContainer`)**: Кнопки типов ссылок скомпонованы в монолитный горизонтальный контейнер `QFrame#linkTypeContainer` с `setContentsMargins(0, 0, 0, 0)` и `setSpacing(0)`. В `common.qss` кнопки имеют `border-radius: 0; outline: none; border-bottom: 2px solid transparent;`. В активном состоянии (`:checked`) нижняя граница подсвечивается цветом акцента темы (`border-bottom: 2px solid <accent>`).
   8. **Скрытие бара типов при фиксированном типе / редактировании**: При `_is_type_fixed = True` (редактирование существующей ссылки или добавление с заранее заданным типом) строка кнопок типов скрывается, освобождая вертикальное пространство, а тип ресурса отображается в заголовке окна.
   9. **Эргономика и компоновка полей**: Поле `URL/Путь` занимает полную ширину строки для обеспечения читаемости длинных адресов. Поле `Название` спарено на одной строке с кнопкой `Иконка`. Поле `Профиль` спарено на одной строке с кнопкой `Выбрать`. Поле `Аргументы` расположено на отдельной строке. Запрещено сжимать `URL/Путь` в полустроку или нарушать зафиксированную гармоничную сетку полей.

## 26. Architecture Standards: Category Tiles Styling & State Aesthetics (СТАНДАРТ СТИЛИЗАЦИИ ПЛИТОК КАТЕГОРИЙ)
- **Status: FROZEN ARCHITECTURE / STRICT RULES**: Карточный дизайн и состояния плиток категорий (`categoryTiles`, `CategoryTilesDelegate`, `QSS`) во всех 16 темах полностью зафиксированы.
- **Strict Tile Aesthetics Rules**:
  1. **Запрет на сплошную заливку**: Категорически запрещено заливать фон выбранных или наведенных плиток плотными, непрозрачными акцентными цветами или включать `categoryTiles` в групповые селекторы строк таблиц/деревьев (`QTableView::item:selected`).
  2. **Геометрия и скругление**: Каждая плитка подчиняется стандарту монолитной геометрии §53 и обязана иметь **`border-radius: 0`** и прозрачную рамку в покое (`border: 1px solid transparent;`).
  3. **Состояние Hover**: В тёмных темах мягкая нейтральная подсветка **`rgba(255, 255, 255, 0.05)`**, в светлых темах — **`rgba(0, 0, 0, 0.04)`**, `border-color: transparent;`.
  4. **Состояние Selected / Active**: В тёмных темах деликатная дымка **`rgba(255, 255, 255, 0.08)`** (при hover `0.12`), в светлых темах — **`rgba(0, 0, 0, 0.07)`** (при hover `0.10`). Контур строго в **1 px** цвета акцента конкретной темы (`border: 1px solid <accent_border>;`).
  5. **Типографика**: Текст под иконкой строго наследует штатный цвет текста темы **`color: palette(text);`**. Запрещено принудительно затирать цвет текста белым `#FFFFFF` или иными статическими значениями.

## 27. Architecture Standards: Theme Quality Gate & Import Protection (КОНТРОЛЬ КАЧЕСТВА ТЕМ И WCAG 2.1)
- **Status: FROZEN ARCHITECTURE / STRICT RULES**: Стандарт контроля контрастности тем оформления (`app/utils/theme_checker.py`) и защита импорта сторонних тем (`app/services/theme_import_service.py`) полностью зафиксированы.
- **Strict Theme Quality Rules**:
  1. **Стандарт контрастности WCAG 2.1**: Каждая встроенная или импортируемая тема обязана проходить автоматическую проверку относительной яркости (Relative Luminance) и коэффициента контрастности (Contrast Ratio) не ниже **4.5 : 1** для нормального текста.
  2. **Защита импорта сторонних тем**: Сервис `ThemeImportService` обязан автоматически валидировать контрастность при импорте архивов `.zip` и файлов `.qss`. При нарушении порога контрастности операция прерывается с `ThemeValidationError`. Запрещено импортировать нечитаемые темы.
  3. **Соответствие флага `is_dark`**: Флаг темы `is_dark` обязан строго соответствовать реальной вычисленной яркости фона (фон < 0.5 для тёмных тем, >= 0.5 для светлых тем).
  4. **Автоматический запуск**: Доступна CLI-проверка `python -m app.utils.theme_checker`, проверяющая все темы репозитория со 100% успехом.

## 28. Architecture Standards: Tree & Category Drag-and-Drop Architecture (АРХИТЕКТУРНЫЙ СТАНДАРТ ПЕРЕТАСКИВАНИЯ В ДЕРЕВЕ СТРУКТУРЫ)
- **Status: FROZEN ARCHITECTURE / STRICT RULES**: Архитектура перетаскивания (DnD) элементов дерева структуры (`app/utils/ui/dnd/tree.py`, `app/utils/ui/dnd/categories_command.py`, `StructureTreeModel`) полностью зафиксирована.
- **Strict DnD Priority & Targeting Rules**:
  1. **Приоритет внутреннего перетаскивания**: В `DragDropHandler.handle_drop_event` проверка внутреннего источника `event.source() == self.tree_widget` обязана выполняться на первом месте до любых проверок MIME-типов (`get_category_mime_type()`). Внутренний сброс строго направляется в `_handle_internal_drop_event_index`. Внешний обработчик `_handle_category_drop_index` вызывается строго при `event.source() != self.tree_widget` (дроп из плиток категорий).
  2. **Симметричный расчет направления UP/DOWN**: При наведении на категорию или раздел `determine_target` рассчитывает позицию по вертикальной половине элемента:
     - Верхняя половина (`is_upper_half` / `AboveItem`): целевая строка строго `base_row = target_row` (перемещение выше целевого элемента).
     - Нижняя половина (`not is_upper_half` / `BelowItem`): целевая строка строго `base_row = target_row + 1` (перемещение ниже целевого элемента).
  3. **Синхронизация семантики Qt `beginMoveRows`**: В `StructureTreeModel.move_category` при перемещении вниз внутри одного раздела (`src_parent is dst_parent and new_row > src_row`) параметр `dest_child` в Qt `beginMoveRows` строго равен `new_row + 1`, а вставка в `dst_parent.children` выполняется по индексу `new_row`. При перемещении вверх `dest_child` строго равен `new_row`.
  4. **Атомарная синхронизация порядка категорий (`reorder_categories`)**: Для множественного перетаскивания и исключения рассинхрона между БД и UI модель дерева обязана предоставлять метод `reorder_categories(section_id, ordered_category_ids)`. В `CategoriesCommand._apply_tree_model_moves` порядок в затронутых разделах синхронизируется вызовом `model.reorder_categories` с актуальным списком ID из базы данных.
  5. **Автораскрытие закрытых разделов при перетаскивании ссылок (Spring-Loaded Sections)**:
     - При наведении ссылки (внутренней из таблицы или внешней URL) на свёрнутый раздел (`target_type == "section"` и `not isExpanded(target_index)`) событие принимается (`acceptProposedAction`), раздел подсвечивается (`OnItem`), и запускается таймер удержания на **500 мс** (`_arm_auto_expand_timer`) с защитой через `QPersistentModelIndex`.
     - По истечении 500 мс раздел раскрывается (`expand`), а первый дочерний элемент гарантированно прокручивается в видимую область (`scrollTo(first_child, EnsureVisible)`).
     - При уводе курсора с раздела раньше 500 мс, переходе на категорию, выходе за пределы дерева (`dragLeaveEvent`) или сбросе (`dropEvent`) таймер обязан немедленно аннулироваться (`_cancel_auto_expand_timer`), предотвращая паразитное раскрытие дерева.

## 29. Architecture Standards: Unified Backup & Restore Bundle (АРХИТЕКТУРНЫЙ СТАНДАРТ ЕДИНОГО БАНДЛА РЕЗЕРВНОЙ КОПИИ)
- **Status: FROZEN ARCHITECTURE / STRICT RULES**: Архитектура экспорта и импорта резервной копии данных (`DatabaseController`, `DatabaseRestoreWorker`, `DatabaseDialogs`) полностью зафиксирована.
- **Strict Backup & Restore Rules**:
  1. **Единый переносимый контейнер (Single Bundle Archive)**: Экспорт резервной копии пользователя выполняется строго в виде защищенного архива `.zip`, содержащего `database.db` (снимок SQLite через `conn.backup()`), `manifest.json` (версия формата, timestamp, количество иконок) и папку `icons/`.
  2. **Умная фильтрация иконок (Referenced Icons Only)**: В архив упаковываются исключительно те иконки, на которые есть ссылки в активных сущностях (`link`, `category`, `section`, `sphere`), определяемые через `IconReferenceService.get_referenced_icons()`. Архивирование неиспользуемых кэшей или посторонних файлов запрещено.
  3. **Двухфазный изолированный Staging (Fail-Fast Guard)**: Распаковка архива при восстановлении/подключении выполняется строго во временный каталог внутри системной папки БД (`db_path.parent / f".restore_staging_{uuid4().hex}"`). Проверка целостности SQLite и накат миграций проводятся **до** каких-либо изменений живой базы данных.
  4. **Атомарная замена и откат**: Замена рабочего файла базы данных сопровождается созданием временной копии (`.orig_bak`) с автоматическим откатом при сбое замены или верификации. Публикация иконок ведется под `icon_files_lock()`, с обязательным вызовом `clear_icon_cache()`.
  5. **Защита от Zip Slip и DoS-атак**: Извлечение файлов из архива выполняется строго по базовым именам без использования каталогов из архива. Лимиты безопасности: не более **2000 иконок**, не более **10 МБ** на один файл, суммарный распакованный объем не более **100 МБ**.
  6. **Полная обратная совместимость**: Сохранение и подключение классических сырых файлов SQLite (`.db`) обязано сохранять полную работоспособность как при ручном вводе расширения, так и при автоматических системных бэкапах.

## 30. Architecture Standards: Structure Share System & Safe Packaging (АРХИТЕКТУРНЫЙ СТАНДАРТ СИСТЕМЫ ШАРИНГА И БЕЗОПАСНЫХ ПАКЕТОВ)
- **Status: FROZEN ARCHITECTURE / STRICT RULES**: Архитектура экспорта и импорта пакетов сущностей (`StructureShareService`, `MainWindow._export_structure_package`, `MainWindow.import_archive_file`) полностью зафиксирована.
- **Strict Share & Packaging Rules**:
  1. **2 канонических формата пакетов**: Для экспорта/импорта строго используются 2 расширения: `.aitesec` (раздел) и `.aitecat` (категория). Устаревший `.aitepack` поддерживается исключительно как legacy-алиас на чтение.
  2. **Структура архивного пакета**: Пакет строго содержит `manifest.json` (`schema_version: 1`, `package_type`, `item_name`, `export_timestamp`, словарь чексамм `files`), иерархический `data.json`, каталог пользовательских иконок `icons/` и вложенных файлов `workspace_files/`.
  3. **Защита от ZIP-бомб и DoS (OOM Guard)**: Чтение архивов ведется строго чанками через `_safe_read_entry`. Установлены жесткие лимиты:
     - Общий распакованный объем: строго не более **50 МБ** (`MAX_TOTAL_UNCOMPRESSED_SIZE`).
     - Размер одного файла иконки/воркспейса: не более **15 МБ** (`MAX_FILE_SIZE`).
     - Размер `manifest.json`: не более **1 МБ** (`MAX_MANIFEST_SIZE`).
  4. **Защита от Path Traversal (Zip Slip)**: Извлечение файлов и директорий пакета ведётся с сохранением внутренней структуры каталогов при условии валидации: целевой путь `(staging_dir / member_name).resolve()` обязан строго находиться внутри `staging_dir.resolve()`. Применение путей с `../`, абсолютных путей или небезопасное схлопывание структуры каталогов категорически запрещено.
  5. **Валидация манифеста и целостности**: Манифест обязан валидироваться по типу пакета (`expected_type`), а `data.json` обязан строго проходить проверку контрольной суммы SHA-256 (`_validate_checksums`).
  6. **Унифицированные каналы импорта**: Импорт пакетов обязан бесшовно поддерживать 4 точки входа:
     - Контекстные меню и главное меню приложения;
     - Drag & Drop архивов на дерево структуры (`externalLinkDropped`);
     - IPC-канал `SingleInstanceGuard` (`OPEN:<path>`) при открытии файлов через зарегистрированные файловые ассоциации ОС;
     - Аргументы командной строки при холодном старте (`file_to_open`).
  7. **Автоматический ремаппинг путей**: При импорте пути к иконкам и файлам воркспейса обязаны динамически перенаправляться в локальные постоянные каталоги пользователя с сохранением целостности ссылок.

## 31. Architecture Standards: Name Conflict Resolution (АРХИТЕКТУРНЫЙ СТАНДАРТ РАЗРЕШЕНИЯ КОНФЛИКТОВ ИМЕН)
- **Status: FROZEN ARCHITECTURE / STRICT RULES**: Архитектура выявления и разрешения конфликтов совпадения имен при вставке (`paste`), перемещении (`move`, `DnD`) и импорте сущностей (`ImportConflictDialog`, `ActionController`, `LinksUIClipboard`, `MoveOperationsHandler`, `StructureShareService`) полностью зафиксирована.
- **Strict Conflict Resolution Rules**:
  1. **Изолированный UI-контракт**: Диалог `ImportConflictDialog` (бывший `DuplicateItemDialog`) инкапсулирует 3 режима работы (`"import"`, `"move"`, `"copy"`), фиксированную ширину **520 px** и автоматический расчет высоты по содержимому.
  2. **Единое интерактивное поведение (Правило 1)**: Во всех интерактивных сценариях пользователя (вставка разделов, категорий и ссылок `Ctrl+V`, перетаскивание ссылок и категорий мышкой `DnD`, перемещение между сферами/разделами, ручной импорт архивов) при возникновении коллизии имён **обязан** вызываться `ImportConflictDialog`. Категорически запрещено молча вслепую объединять или авто-переименовывать сущности в фоновом режиме без подтверждения пользователя.
  3. **3 канонические стратегии разрешения коллизий**:
     - `merge` («Объединить содержимое» / «Заменить существующий»): при совпадении имени раздела или категории родительская сущность не дублируется; все вложенные дочерние категории и ссылки аккуратно переносятся/импортируются в существующий узел. Для ссылок обновляются параметры существующей записи.
     - `copy` / `rename` («Сохранить оба (создать копию «{name}»)»): исходная сущность сохраняется, а импортируемая/перемещаемая сущность автоматически получает уникальное суффиксное имя через `generate_unique_name` (например, `Категория (1)`).
     - `cancel` (Отмена): операция немедленно прерывается без внесения изменений в базу данных.
  4. **Слабая связанность (Callback-контракт)**: Сервисы импорта и перемещения принимают независимый колбэк `conflict_resolver: Callable[[str, str, str], str]`. Запрещено инстанциировать UI-диалоги напрямую внутри сервисных и модельных классов (`StructureShareService`, `StructureService`).
  5. **Размещение утилит именования (Zero Circular Dependencies)**: Функция `generate_unique_name` строго размещается в модуле `app/utils/naming.py` без зависимостей от слоёв `models` и `services`, предотвращая циклические импорты при обращении из `DuplicateResolver`, менеджеров данных и сервисов.

## 32. Architecture Standards: Icon Subsystem & Cache Integrity (АРХИТЕКТУРНЫЙ СТАНДАРТ ПОДСИСТЕМЫ ИКОНОК И ЦЕЛОСТНОСТИ КЭША)
- **Status: FROZEN ARCHITECTURE / STRICT RULES**: Архитектура фасада иконок, кэширования в памяти и на диске полностью зафиксирована.
- **Strict Icon Architecture Rules**:
  1. **Канонический путь кэша фавиконов**: Кэш фавиконов хранится строго по относительному пути `icon_cache/favicon_cache.db` (`get_favicon_cache_path()`). Запрещено плодить альтернативные имена файлов или использовать устаревшие абсолютные пути.
  2. **Защита от отравления кэша (Cache Poisoning Guard)**: В `IconCacheManager` категорически запрещено кэшировать пустые экземпляры `QIcon` при отсутствии файла на диске или ошибках загрузки. Кэшированию подлежат исключительно валидные непустые иконки (`not icon.isNull()`).
  3. **Изоляция пространств имён кэша (Namespace Isolation)**: В `IconLoadingService` кэширование иконок категорий и общих иконок строго разделено через префикс `f"cat_{path}"`. Запрещено смешивать ключи кэша категорий и ссылок.
  4. **Многоуровневый LRU-кэш**: В `links_model.py` получение иконок защищено декоратором `@lru_cache(maxsize=1024)`. В `HighQualityTreeDelegate` лимит кэша пиксмапов строго зафиксирован на уровне **512** с инвалидацией при превышении лимита и защитой от коллизий `id(icon)`.
  5. **Единый фасад без мертвого кода**: В `path_service.py` и смежных модулях запрещено использовать устаревшие классы Qt (`QDir`, `QFile`) и QRC-пути (`:/icons`) для пользовательских иконок. Все дисковые операции выполняются строго через стандартный `pathlib.Path`.
  6. **Синхронизация фоллбэков**: Модули фонового извлечения (`fetcher.py`) и визуальных заглушек (`icon_fallback.py`) обязаны возвращать строго идентичные эталонные иконки по умолчанию для каждого из 5 типов ссылок.

## 33. Architecture Standards: Empty Area Context Menus & Action Parity (АРХИТЕКТУРНЫЙ СТАНДАРТ КОНТЕКСТНЫХ МЕНЮ ПУСТЫХ ОБЛАСТЕЙ)
- **Status: FROZEN ARCHITECTURE / STRICT RULES**: Паритет и эргономика контекстных меню свободных пространств во всех рабочих областях приложения зафиксированы.
- **Strict Empty Area Menu Rules**:
  1. **Трехкомпонентный паритет**: Контекстное меню при правом клике на пустом пространстве обязано поддерживаться во всех трех областях:
     - **Дерево структуры (`StructureTreeView`)**: «Добавить раздел», «Импортировать раздел», разделитель, «Вставить», разделитель, «Выбрать все» / «Снять выделение», разделитель, «Отменить» / «Повторить».
     - **Плитка категорий (`CategoryTiles` / `CategoryListView`)**: «Добавить категорию», «Импортировать категорию», разделитель, «Вставить», разделитель, «Выбрать все» / «Снять выделение», разделитель, «Отменить» / «Повторить».
     - **Таблица ссылок (`LinksTableView`)**: «Добавить ссылку», разделитель, «Вставить», разделитель, «Выбрать все» / «Снять выделение», разделитель, «Отменить» / «Повторить».
  2. **Сигнальный контракт плиток категорий**: При клике на пустое место (`not index.isValid()` или `item_id is None`) `CategoryTiles` обязан вычислять глобальные координаты и эмитить `contextMenuRequested(0, global_pos)`.
  3. **Фасадные методы главного окна**: `MainWindow` и `MainWindowProtocol` обязаны предоставлять метод `import_category_to_current_section()`, определяющий активный раздел через `ensure_section_for_category()` / `get_target_section_id()` и вызывающий `import_category_to_section()`.
  4. **Типографика и глаголы**: Названия пунктов меню подчиняются **Правилу 13** — строго инфинитивы глаголов («Добавить категорию», «Импортировать категорию», «Вставить», «Выбрать все») без троеточий (`...`).

## 34. Architecture Standards: Links Table Drag-and-Drop & Row Reordering (СТАНДАРТ ПЕРЕМЕЩЕНИЯ СТРОК В ТАБЛИЦЕ ССЫЛОК)
- **Status: FROZEN ARCHITECTURE / STRICT RULES**: Подсистема перетаскивания и ручного упорядочивания ссылок в таблице (`LinksTableView`, `LinksTableModel`, `DragDropHandlerMixin`) полностью стандартизирована.
- **Strict Method Delegation Rules**:
  1. **Явное делегирование `_get_drop_positions`**: Класс `LinksTableView` обязан явно переопределять метод `_get_drop_positions(self, event)`, делегируя вызов в `DragDropHandlerMixin._get_drop_positions(self, event)`. Запрещено допускать вызов базовой заглушки `BaseDragDropTableWidget._get_drop_positions` (`[], -1`) из-за порядка разрешения MRO.
- **Strict Visual Feedback Rules**:
  1. **Линия вставки (Drop Indicator Line)**: Во время внутреннего перетаскивания строк в `LinksTableView.dragMoveEvent` обязан рассчитываться индекс целевой строки и положение курсора относительно центра строки (`AboveItem` / `BelowItem`).
  2. **Отрисовка в `paintEvent`**: Разделительная линия обязана отрисовываться на всю ширину `viewport` таблицы: 2px акцентная линия (`QPalette.ColorRole.Highlight`) с мягким ореолом (ambient glow 4px, alpha 60) — в строгом стилевом паритете с деревом разделов `StructureTreeView`.
  3. **Гарантированный сброс состояния**: В методах `dragLeaveEvent` и `dropEvent` состояние индикатора (`_drop_indicator_row`, `_drop_indicator_pos`) обязано сбрасываться в `None` с вызовом `viewport().update()`.
- **Strict Model Renumbering Rules**:
  1. **Атомарная переномерация колонки `#`**: В `LinksTableModel.move_rows` после физического изменения порядка строк модель обязана эмитировать `self.dataChanged` для колонки `0` (`ORDER`) на весь диапазон строк `0..N-1`, гарантируя мгновенное синхронное отображение номеров `1, 2, 3... N` без пересоздания или мерцания таблицы.
- **Strict Selection & Persistence Rules**:
  1. **Сохранение выделения и текущего индекса**: В `LinksTableView.dropEvent` после вызова базового `dropEvent` выделение обязано автоматически восстанавливаться на перемещенных строках по их `id` через `selectionModel().select(...)`, а текущий индекс (`setCurrentIndex`) в модели выбора обязан устанавливаться на первую перемещенную строку без отбирания фокуса клавиатуры у других виджетов.
  2. **Сигнальный поток в базу данных**: Завершение перемещения обязано порождать цепочку сигналов: `items_reordered(ids)` -> `links_reordered` -> `handlers._on_links_reordered` -> `business.update_link_order(ids)` для атомарного сохранения нового порядка в базе данных SQLite.

## 35. Architecture Standards: Dialog Geometry & Equalized Button Box Standard (АРХИТЕКТУРНЫЙ СТАНДАРТ ГЕОМЕТРИИ ДИАЛОГОВ И СИММЕТРИИ КНОПОК)
- **Status: FROZEN ARCHITECTURE / STRICT RULES**: Геометрия диалоговых окон, адаптивность к локализации и симметрия кнопок действий полностью зафиксированы.
- **Strict Dialog Sizing Rules**:
  1. **Категория А (Формы и карточки — Fixed Content)**: В диалогах `SectionDialog`, `CategoryDialog`, `SphereRenameDialog`, `ImportConflictDialog`, `SettingsDialog`, `AboutDialog`, `ChromeProfileDialog`, `AsyncOperationDialog`, `IconRefreshDialog`, `LinkDialog` фиксированная проектная ширина строго задаётся через `self.setFixedWidth(width)` (`600 px` для ссылок, `400 px` для сущностей) с последующим `self.adjustSize()`. Любое растягивание окон по горизонтали исключено аппаратно на уровне ОС, а высота рассчитывается по содержимому без пустых полей. Запрещено использовать `QLayout.SizeConstraint.SetFixedSize` на лейаутах окон с заданной фиксированной шириной во избежание схлопывания геометрии.
  2. **Категория Б (Окна с таблицами и списками данных — Data Viewers)**: Диалоги `FileSearchDialog`, `InstalledAppsDialog`, `BadUrlCleanupDialog`, `RestoreDbDialog`, `BrowserProfileDialog`, `QuickLookDialog` сохраняют свободный ресайз окна для комфортного просмотра больших объемов данных.
- **Strict Button Box Equalization & i18n Rules**:
  1. **Симметрия парных кнопок футера**: В `QDialogButtonBox` ширина всех кнопок действий («Сохранить» / «Отмена», «Восстановить» / «Отмена», «Применить» / «Отмена») строго обязана выравниваться через `BaseDialog.equalize_button_box()` по формуле `max(min_width, max_text_width)`. Запрещено задавать парным кнопкам в футере разную ширину.
  2. **Стандарт ширины кнопок диалогов**: Минимальная ширина любых кнопок действий и инлайн-кнопок в диалогах строго **115 px** (`fixed_button_width: 115` в `app_config.json`, `ui_config.py`, `common.qss`, `BaseDialog`). Запрещено использовать базу менее 115 px. Высота строго **32 px**.
  3. **Нулевой клиппинг при ретрансляции**: Все диалоги в методах `retranslateUi()` обязаны вызывать актуализацию размеров кнопок через `equalize_button_box()` / `adjust_button_width()`, гарантируя 100% отсутствие обрезания переведённого текста многоточием на всех поддерживаемых языках.

## 36. Architecture Standards: Section & Structure Deletion Safety (АРХИТЕКТУРНЫЙ СТАНДАРТ БЕЗОПАСНОСТИ УДАЛЕНИЯ СТРУКТУРЫ И РАЗДЕЛОВ)
- **Status: FROZEN ARCHITECTURE / STRICT RULES**: Поведение подсистемы удаления разделов и элементов структуры (`ItemDeletionService`, `ItemOperations`) полностью стандартизировано.
- **Strict Deletion Confirmation Rules**:
  1. **Запрет на тихое удаление разделов (Silent Deletion Ban)**: В `ItemDeletionService._delete_section` категорически запрещено обходить диалог подтверждения при `links_count == 0`. Раздел является корневым структурным контейнером в дереве.
  2. **Обязательное подтверждение (Mandatory Confirmation)**: Удаление любого раздела (одиночного или множественного) обязано всегда запрашивать подтверждение пользователя через `DialogManager.ask_confirmation` (`_confirm_section_deletion`) независимо от количества вложенных категорий и ссылок.
  3. **Защита от регрессий**: Сервис `ItemDeletionService` обязан сопровождаться модульными тестами, подтверждающими вызов диалога подтверждения даже при 0 ссылок и 0 категорий.
## 37. Architecture Standards: Settings Dialog & Input Context Semantics (СТАНДАРТ ЧИСТОТЫ НАСТРОЕК И СЕМАНТИКИ ВВОДА)
- **Status: FROZEN ARCHITECTURE / STRICT RULES**: Архитектура диалога настроек и динамическая семантика полей ввода ссылок полностью стандартизированы.
- **Strict Settings Dialog Cleanliness Rules**:
  1. **Компактная строка выбора темы**: Кнопки импорта (`add_thema`) и удаления (`delete`) тем оформляются строго как компактные квадратные кнопки **32×32 px** с иконками, расположенные в одну горизонтальную строку с выпадающим списком тем (`theme_combo`). Иконки загружаются строго через централизованный фасад `icon_cache.get_icon()`. Запрещено создавать отдельную строку «Действия с темами:» с громоздкими текстовыми кнопками или использовать прямые файловые пути в обход кэша иконок.
  2. **Исключение системных ассоциаций из настроек**: В диалоге общих настроек (`SettingsDialog`) категорически запрещено размещать чекбоксы регистрации расширений файлов (`.aitepack` и др.) в реестре Windows. Регистрация ассоциаций типов файлов возлагается строго на инсталлятор дистрибутива. В окне настроек допустимы строго параметры повседневного пользовательского опыта: язык интерфейса, тема, размер шрифта, лимит резервных копий.
- **Strict Link Dialog Input Context Semantics**:
  1. **Запрет на сдвоенные метки («URL/Path:» Ban)**: В диалоге добавления и редактирования ссылок (`LinkDialogUI`) категорически запрещено использовать неточные компромиссные подписи вида «URL/Path:» («URL/Путь:»).
  2. **Строгая контекстная семантика**: Метка поля ввода обязана быть динамической (`update_path_label(link_type)`):
     - Для веб-ссылок (`LinkType.WEB`) — строго **«URL:»**.
     - Для локальных сущностей (`LinkType.FILE`, `LinkType.FOLDER`, `LinkType.PROGRAM`, `LinkType.SCRIPT`) — строго **«Путь:»** («Path:» в EN, «Pfad:» в DE, «Ruta:» в ES, «Chemin :» в FR, «Шлях:» в UK).
  3. **Синхронизация при смене типов и локализации**: Обновление текста метки поля ввода обязано выполняться мгновенно как при переключении типа сущности (`TypeChangeMixin._update_ui_state`), так и при динамической ретрансляции интерфейса (`LinkDialogUI._retranslate_path_row`).

## 38. Architecture Standards: Internationalized Button Metrics & Installed Apps Layout (СТАНДАРТ АДАПТИВНОЙ ШИРИНЫ КНОПОК И ДИАЛОГА ПРОГРАММ)
- **Status: FROZEN ARCHITECTURE / STRICT RULES**: Механизм динамического расчета ширины кнопок с учетом шрифтовых метрик и компоновка диалога выбора установленных программ зафиксированы.
- **Strict Dynamic Button Metrics Rules**:
  1. **Запрет на обнуление ширины кнопок**: В `BaseDialog.equalize_button_box` категорически запрещено устанавливать `setMinimumWidth(0)`. Ширина всех кнопок в `QDialogButtonBox` обязана рассчитываться как `max_needed = max(min_width, max(text_w + icon_w + padding))` на основе `fontMetrics().horizontalAdvance(btn.text())` на текущем активном языке с базовым `padding >= 28 px`.
  2. **Учет иконок и внутренних отступов в `adjust_button_width`**: В `BaseDialog.adjust_button_width` ширина кнопки обязана рассчитываться с учетом отступа `padding >= 28 px` (покрывающего QSS padding) и ширины иконки `iconSize.width() + 8 px` при наличии иконки. Запрещено игнорировать ширину иконки и внутренние отступы кнопки.
- **Strict Installed Apps Dialog Layout Rules**:
  1. **Полноразмерная чистая строка поиска**: Поле поиска (`search_le`) размещается строго на всю ширину диалога (`layout.addWidget(self.search_le)`). Счетчик приложений исключен для устранения визуального шума и сохранения минималистичного нативного стиля Windows.
  2. **Чистый футер действий и оптическая центровка**: В нижней строке (`bottom_layout`) диалога `InstalledAppsDialog` допустимы строго: слева кнопка поиска на диске `[ 📁 Найти на компьютере ]` (`IconTextPushButton` с центрированной иконкой папки `app/resources/ui_icons/folder_icon.png` и типографической центровкой базовой линии `baseline = int(round(mid_y + (fm.ascent() - fm.descent()) / 2.0))`), далее пружина-разделитель `addStretch(1)` и справа парные кнопки `[ Выбрать ] [ Отмена ]` в `QDialogButtonBox`.
  3. **Минимальная геометрия**: Диалог установленных программ имеет минимальный размер строго `setMinimumSize(560, 560)` со стартовым `resize(580, 620)`, гарантируя полное отсутствие обрезания текста кнопок во всех 6 языковых локалях (RU, EN, UK, DE, ES, FR).

## 39. Architecture Standards: Dialog Tables & Lists Clean Border Styling (АРХИТЕКТУРНЫЙ СТАНДАРТ РАМОК ТАБЛИЦ И СПИСКОВ В ДИАЛОГАХ)
- **Status: FROZEN ARCHITECTURE / STRICT RULES**: Стандарт оформления внешних границ таблиц (`QTableView`, `QTableWidget`) и списков (`QListView`, `QListWidget`) в диалоговых окнах зафиксирован.
- **Strict Prohibition on Wrapper Frames (Запрет на виджеты-обёртки)**:
  1. **Запрет на контейнеры-обёртки**: Категорически запрещено оборачивать таблицы и списки в диалогах во внешние контейнеры (`QFrame`) ради задания границ. Внутренний скроллбар, шапка и геометрия таблиц обязаны оставаться нативными без двойных рамок в шапке, разрывов на углах у скроллбара и внутренних зазоров.
- **Strict QSS Viewport & Frame Rules**:
  1. **Нативная 1px рамка через прозрачность фрейма**: В `common.qss` для `QDialog QTableView`, `QDialog QTableWidget`, `QDialog QListView`, `QDialog QListWidget` и их `> QWidget#qt_scrollarea_viewport` строго обязателен `background-color: transparent`. Внешний 1px-бордер фрейма рисуется движком Qt непрерывно по всему внешнему контуру, не перекрываясь фоном скролл-области.
  2. **100% паритет всех тем**: Цвета рамок для диалоговых таблиц и списков берутся строго из правил тем `QDialog QTableView, QDialog QTableWidget { border-color: ... }` и автоматически расширяются на `QListView, QListWidget` через `ThemeStylesheetService`. Запрещено хардкодить цвета рамок в Python-коде диалогов.

## 40. Architecture Standards: Database Backup & Recovery Engine (АРХИТЕКТУРНЫЙ СТАНДАРТ БЭКАПОВ И ВОССТАНОВЛЕНИЯ)
- **Status: FROZEN ARCHITECTURE / STRICT RULES**: Архитектура создания, валидации и ротации резервных копий базы данных зафиксирована.
- **Strict Backup Pipeline Rules**:
  1. **SQLite Online Backup API**: Создание резервных копий выполняется строго через постраничный `connection.backup(dest_conn)`. Запрещено выполнять прямое файловое копирование активной базы данных в обход SQLite Backup API.
  2. **Обязательный WAL Checkpoint**: Перед созданием снимка обязательно выполнение `PRAGMA wal_checkpoint(FULL)` для переноса зафиксированных транзакций.
  3. **Атомарная публикация и очистка мусора**: Запись бэкапа ведётся во временный файл `.tmp` с последующим атомарным `replace()`. В `purge_old_backups` строго обязательна очистка брошенных временных файлов (`aite_bd_*.tmp`).
  4. **Пост-валидация целостности**: Перед публикацией нового файла бэкапа обязательно выполнение `PRAGMA quick_check` на `dest_conn`. Любой сбой проверки бракует бэкап и удаляет временный файл.
  5. **Хронологическая ротация по mtime**: Ротация и удаление устаревших копий сверх `max_backups` ведётся строго по времени модификации файлов (`st_mtime`), а не по лексикографическому порядку строк.
- **Strict Restore Dialog Rules**:
  1. **Нативная таблица без костылей**: Диалог `RestoreDbDialog` использует `QTableWidget` с чистой 1px рамкой темы, скрытым вертикальным заголовком и автоматическим определением форматов (`.db`, `.zip`, `.bak`). Запрещено возвращать рудименты отдельных файлов (`links.db.bak`) в виде специальных методов или костылей.

## 41. Architecture Standards: File Dialog Navigation & Path Resolution (АРХИТЕКТУРНЫЙ СТАНДАРТ НАВИГАЦИИ И ПУТЕЙ ДИАЛОГОВ ФАЙЛОВ)
- **Status: FROZEN ARCHITECTURE / STRICT RULES**: Логика открытия системных файловых диалогов (`QFileDialog`) и каталогов по умолчанию стандартизирована.
- **Strict Default Directory Rules**:
  1. **Запрет на открытие корня приложения**: Категорически запрещено открывать корень проекта или исполняемого файла приложения по умолчанию при вызове `QFileDialog`.
  2. **Стандарт каталога «Загрузки» (Downloads Standard)**: Для всех операций импорта/экспорта данных, резервных копий базы данных и миграционных архивов (бэкапы, HTML-закладки браузеров, дампы) стартовой директорией по умолчанию выступает папка «Загрузки» пользователя ОС (`QStandardPaths.StandardLocation.DownloadLocation`).
  3. **Стандарт каталога программ (Applications Standard)**: Для диалогов выбора исполняемых файлов приложений (`InstalledAppsDialog`, выбор `.exe`) на Windows стартовой директорией выступает системная папка `Program Files` (`os.environ.get("ProgramFiles")` или `ProgramFiles(x86)`), а на остальных ОС — `QStandardPaths.StandardLocation.ApplicationsLocation`.
  4. **Неприкосновенность каталога пользовательских иконок**: Выбор локальных пользовательских иконок закладок строго привязан к специализированному хранилищу `user_icons_dir` (`app/resources/icons/user/`). Запрещено перенаправлять выбор иконок в общие папки ОС.
- **Strict Context-Aware Directory Persistence**:
  1. **Запоминание последнего выбора**: Через централизованный сервис `DialogPathService` путь выбранного файла/папки сохраняется в реестр `QSettings` по контексту (`DialogPaths/{context}`) методом `remember_dir(context, chosen_path)`.
  2. **Приоритет последнего выбора**: При повторном открытии диалога в том же контексте (`backup_export`, `backup_import`, `browser_import`, `installed_apps`) диалог открывает последнюю успешно использованную пользователем папку, если она всё ещё существует на диске.

## 42. Architecture Standards: Advanced File Search Dialog (АРХИТЕКТУРНЫЙ СТАНДАРТ ДИАЛОГА ПОИСКА ФАЙЛОВ)
- **Status: FROZEN ARCHITECTURE / STRICT RULES**: Архитектура расширенного поиска файлов (`FileSearchDialog`, `_SearchResultsModel`, `FileSearchWorker`) зафиксирована.
- **Strict Table Model & Performance Rules**:
  1. **Информативная 4-колоночная структура**: Таблица результатов обязана отображать 4 видимые колонки: «Имя» (со значком `QFileIconProvider`), «Папка», «Размер» (человекочитаемый формат B/KB/MB/GB), «Дата изменения» (YYYY-MM-DD HH:MM). Запрещено скрывать заголовки или схлопывать таблицу в одну колонку сырого пути.
  2. **Сортировка заголовков**: В модели обязана быть реализована сортировка (`sort(column, order)`), а заголовок таблицы обязан поддерживать клик по колонкам (`setSortingEnabled(True)`). По завершении поиска активная сортировка автоматически переприменяется.
  3. **Пакетная вставка (Batch Insertion Guard)**: Вставка результатов обязана выполняться батчами через `add_results_batch` с единичным вызовом `beginInsertRows(QModelIndex(), start, end)` на весь батч. Категорически запрещено вызывать `beginInsertRows` поштучно на каждый отдельный файл.
  4. **Чистый стиль таблицы и индикатора**: Таблица оформляется без сетки (`setShowGrid(False)`), а индикатор прогресса поиска выполнен тонкой 4px-полосой (`setFixedHeight(4)`, `setTextVisible(False)`).
- **Strict Keyboard Navigation & Hotkey Rules**:
  1. **Быстрый старт поиска по Enter**: Во всех полях ввода (`regex_le`, `root_le`, `pattern_le`, `content_le`) сигнал `returnPressed` обязан запускать поиск без необходимости клика мышью.
  2. **Синхронизация Enter и двойного клика**: Нажатие Enter на строке и двойной клик мыши вызывают одно действие — добавление файлов в базу (`files_selected.emit(paths)`).
  3. **Интеграция Quick Look (`Space`)**: Нажатие Пробела на выбранной строке (в том числе при фокусе в таблице через `eventFilter`) обязано вызывать/переключать предпросмотр `QuickLookDialog` с поддержкой навигации стрелками `Up`/`Down`.
  4. **Буфер обмена (`Ctrl+C`)**: Копирование путей всех выделенных файлов в буфер обмена Windows.
  5. **Остановка по Esc**: При активном поиске первое нажатие `Esc` останавливает сканирование, сохраняя найденные файлы, а повторное закрывает диалог.
- **Strict Context Menu & Footer Architecture**:
  1. **Контекстное меню таблицы**: Таблица обязана поддерживать меню по правому клику (`CustomContextMenu`) с действиями «Добавить как ссылку», «Быстрый просмотр», «Открыть в проводнике» и «Копировать путь».
  2. **Унификация футера**: Кнопка «Открыть в проводнике» выносится в левую часть футера, а в `QDialogButtonBox` размещаются строго парные симметричные кнопки «Добавить как ссылку» и «Закрыть».
- **Strict Decoupled Signal Architecture**:
  1. **Контракт сигналов `files_selected`**: Добавление ссылок из диалога поиска в базу программы обязано выполняться строго через эмиссию сигнала `files_selected.emit(paths)` с последующим `accept()`. Категорически запрещено пробивать инкапсуляцию через `parent().parent().links_actions`.
- **Strict Thread Lifecycle & Persistence Rules**:
  1. **Остановка воркеров при закрытии (Zombie Guard)**: В методах `closeEvent` и `reject` диалог обязан принудительно вызывать `search_worker.stop()`, исключая фоновое сканирование диска после закрытия окна.
  2. **Персистентность геометрии**: Сохранение геометрии ведётся строго в `QSettings` (`FileSearch/geometry`) при закрытии и восстанавливается через `restoreGeometry()`.
  3. **Интеграция с `DialogPathService`**: Кнопка «Browse» обязана использовать `DialogPathService.get_downloads_dir("file_search")` и запоминать выбор через `DialogPathService.remember_dir("file_search", path)`.

## 43. Architecture Standards: High-Performance Content Search & Document Extraction Pipeline (АРХИТЕКТУРНЫЙ СТАНДАРТ ПОИСКА ПО СОДЕРЖИМОМУ ФАЙЛОВ И СНИППЕТОВ)
- **Status: FROZEN ARCHITECTURE / STRICT RULES**: Архитектура движка поиска по содержимому (`search_worker.py`, `text_extractors.py`, `file_search_dialog.py`) зафиксирована.
- **Strict Streaming & OOM Guard Rules**:
  1. **Потоковое чтение блоками (Streaming Chunked Reading)**: Чтение текстовых файлов ведётся потоково блоками строго по 256 KB (`_SEARCH_CHUNK_SIZE = 262144`) с перекрытием (`_OVERLAP_SIZE = 1024`), исключая пропуск слов на стыке чанков и предотвращая загрузку гигабайтных файлов в память.
  2. **Защита от OOM (OOM Guard Limit)**: Для глубокого извлечения текста из сложных форматов действует жёсткий лимит размера файла строго **20 MB** (`_MAX_DOC_EXTRACT_SIZE = 20 * 1024 * 1024`). Файлы большего размера пропускаются без сбоев памяти процесса.
  3. **Многоуровневый декодер кодировок**: Потоковое чтение текста поддерживает каскадное декодирование `UTF-8 -> CP1251 -> Latin-1 (fallback)` без аварийного завершения на бинарных байтах (`errors="replace"`).
- **Strict Document Extraction Rules**:
  1. **Нативное бессерверное извлечение текста документов (`text_extractors.py`)**:
     - `docx`: прямое чтение `word/document.xml` через нативный `zipfile` и регулярные выражения `<w:t[^>]*>(.*?)</w:t>` без сторонних тяжеловесных библиотек.
     - `xlsx`: чтение `xl/sharedStrings.xml` через `zipfile`.
     - `pptx`: чтение `ppt/slides/slide*.xml` через `zipfile`.
     - `odt`, `ods`, `odp`: чтение `content.xml` из OpenDocument zip-контейнеров.
     - `pdf`: безопасное постраничное извлечение текста через `pypdf`/`pdfplumber` с ранним выходом при первом совпадении.
     - `fb2`: быстрое регулярное извлечение текстовых блоков из XML без разбора полного DOM-дерева.
     - `rtf`: удаление управляющих RTF-последовательностей и декодирование шестнадцатеричных символов (`\'hh`).
     - `doc`, `xls`: быстрое бинарное извлечение ASCII/Unicode-цепочек символов.
- **Strict Snippets & Match Options Rules**:
  1. **Контекстные сниппеты совпадений (Match Snippets)**: Извлечение окрестности совпадения радиусом 40–50 символов с экранированием переводов строк в пробелы и добавлением многоточий (`...`).
  2. **Опции сопоставления**: Поддержка поиска «С учётом регистра» (`case_sensitive`) и «Слово целиком» (`whole_words` через границы слов `\b` в регулярных выражениях).
  3. **Пятая колонка сниппетов и нижняя информационная панель**: Таблица результатов отображает 5-ю колонку со сниппетом при поиске по содержимому (`SearchResultsItem.snippet`), а в нижней панели диалога отображается подробный контекст найденной строки.
  4. **Запрет на захламление интерфейса (Clean Search UI)**: Запрещено перегружать интерфейс поиска нестилизованными спинбоксами и виджетами дат — параметры фильтрации обязаны сохранять лаконичность и монолитный стиль приложения.

## 44. Architecture Standards: Background Structure Icon Resolution & Zero-Lag Tree Snapshot Application (АРХИТЕКТУРНЫЙ СТАНДАРТ ФОНОВОГО ПРЕ-РЕЗОЛВА ИКОНОК И МГНОВЕННОГО ПРИМЕНЕНИЯ ДЕРЕВА)
- **Status: FROZEN ARCHITECTURE / STRICT RULES**: Архитектура загрузки структуры сфер и применения снапшота дерева зафиксирована.
- **Strict Background Resolution Rules**:
  1. **Фоновый пред-резолв иконок (`AsyncOperations._fetch`)**: В фоновом потоке загрузки структуры базы данных (`async_operations.py`) все относительные и символические пути иконок разделов и категорий резолвятся в абсолютные пути к дисковым файлам через `IconPathService.resolve_icon_path(raw_icon)` ДО передачи снапшота в UI-поток.
  2. **Прогрев кэша файловой системы**: Фоновый резолв прогревает потокобезопасный LRU-кэш `_resolve_filesystem` в памяти, исключая дисковые операции `os.path.exists()` и `Path.resolve()` в главном потоке.
- **Strict UI Thread Fast-Path Rules**:
  1. **Мгновенный Fast-Path в UI-потоке (`TreeSnapshotService._preprocess_snapshot`)**: Если путь иконки уже является абсолютным (`":" in icon_path or icon_path.startswith("/")`), метод возвращает его немедленно за 0.00 мс без обращения к диску, валидации PIL или повторного вызова `resolve_icon_path`.
  2. **Гарантия нулевых задержек переключения сфер (Sub-millisecond Preprocessing)**: Время выполнения `TreeSnapshotService.preprocess` на UI-потоке строго обязано составлять **< 1 мс** (включая сферы с 200+ категориями). Категорически запрещено выполнять синхронный поиск файлов иконок на диске в основном потоке интерфейса.

## 45. Architecture Standards: Links Table Header Sort Chevrons (АРХИТЕКТУРНЫЙ СТАНДАРТ ШЕВРОНОВ СОРТИРОВКИ ТАБЛИЦЫ ССЫЛОК)
- **Status: FROZEN ARCHITECTURE / STRICT RULES**: Контракт шевронов сортировки в заголовке таблицы закладок (`ExplorerHeaderView`, `ExplorerHeaderStyle`, `columns.py`, `links_model.py`) полностью зафиксирован.
- **Strict Column Chevrons Matrix**:
  1. **Колонка 0 (`ORDER` / `#`)**: строго `sortable = True`, `chevron_padding = False`. Узкая 36px колонка ручного порядка; клик возвращает ручную сортировку без отображения шеврона.
  2. **Колонка 1 (`GROUP_LAUNCH`)**: строго `sortable = False`, `chevron_padding = False`. Служебная кнопка запуска группы; сортировка запрещена.
  3. **Колонки 2 (`NAME` / «Имя»), 3 (`LAUNCH` / «Запуск»), 4 (`NOTES` / «Заметки»), 5 (`TYPE` / «Тип»)**: строго `sortable = True`, `chevron_padding = True`. Все четыре контентные колонки обязаны иметь Windows Explorer style шеврон сортировки.
- **Strict Rendering & Geometry Rules**:
  1. **Постоянная видимость активной сортировки (Persistent Indicator)**: Активно отсортированная колонка (`sorted_sec`) обязана ВСЕГДА отображать шеврон направления (ASC: острием вверх, DESC: острием вниз) даже после того, как курсор мыши покинул область заголовка (`leaveEvent`). Запрещено скрывать шеврон при `hovered_sec < 0`.
  2. **Ховер-подсветка и превью (Interactive Hover Preview)**: При наведении курсора мыши на любую сортируемую колонку (`NAME`, `LAUNCH`, `NOTES`, `TYPE`) заголовок подсвечивается (`table_hover_color`), а в зоне шеврона (24px) отображается шеврон-превью.
  3. **Раздельная геометрия отступов заголовка (`ExplorerHeaderStyle`)**:
     - Для центрированных колонок (`LAUNCH` / `centered = True`): отступ под шеврон выполняется симметрично `(px, 0, -px, 0)` для идеального центрирования текста.
     - Для выровненных по левому краю колонок (`NAME`, `NOTES`, `TYPE` / `centered = False`): отступ резервируется строго справа `(0, 0, -px, 0)`, исключая нежелательный сдвиг текста от левой границы.





## 46. Architecture Standards: Semantic Typography & Theme Tokens Contract (АРХИТЕКТУРНЫЙ СТАНДАРТ СЕМАНТИЧЕСКИХ ТОКЕНОВ И ТИПОГРАФИКИ)
- **Status: FROZEN ARCHITECTURE / STRICT RULES**: Контракт семантических токенов тем оформления и иерархии текста (`theme.json`, `theme_registry.py`, `theme_stylesheet_service.py`) полностью зафиксирован.
- **Strict Theme Tokens Matrix**:
  1. **Минимальный набор токенов (7 токенов)**: Каждая тема в `theme.json` строго обязана содержать секцию `"tokens"`:
     - `text_primary`: основной цвет текста (высокий контраст к фону).
     - `text_secondary`: вторичный цвет текста (вспомогательные подписи, метаданные, порядок, типы). Контрастность откалибрована с чётким визуальным разделением от `text_primary`.
     - `text_muted`: приглушённый цвет для disabled-элементов и плейсхолдеров.
     - `text_accent`: акцентный цвет бренда/темы для хоткеев, фокусов и ключевых индикаторов.
     - `text_on_accent`: цвет текста поверх акцентных заливок (всегда контрастен `text_accent`/`selection_bg`).
     - `selection_bg`: фон выделения элементов списка и таблицы.
     - `selection_fg`: цвет текста выделенных элементов.
  2. **Реестр и Fallback**: `theme_registry.get_theme_tokens(theme_id)` гарантирует возврат полного набора токенов с автоматическим fallback на `DEFAULT_DARK_TOKENS` или `DEFAULT_LIGHT_TOKENS`.
  3. **Прямое чтение токенов в Python-делегатах**: Из-за особенностей Qt QSS (правило `QWidget { color }` сбрасывает динамические `qproperty`), делегаты (`TableDelegate`) обязаны читать токены напрямую через `theme_registry.get_theme_tokens(get_current_theme())`.

## 47. Architecture Standards: Links Table Header Group Launch Checkbox & Bulk Toggle (АРХИТЕКТУРНЫЙ СТАНДАРТ ЧЕКБОКСА ГРУППОВОГО ЗАПУСКА В ШАПКЕ)
- **Status: FROZEN ARCHITECTURE / STRICT RULES**: Механизм чекбокса группового запуска в шапке таблицы закладок (`TableFilterHeader.paintSection`, `LinksTableView._toggle_all_group_launch`, `LinksTableModel.set_all_group_launch`) полностью зафиксирован.
- **Strict Rendering Rules**:
  1. **Идентичность стилизации ячейкам (`QTableView::indicator`)**: Чекбокс в заголовке рисуется строго через `style.drawPrimitive(PE_IndicatorItemViewItemCheck, cb_opt, painter, table)`. В качестве целевого виджета передаётся строго сама таблица `table` (`LinksTableView = self.parent()`), а не `viewport` и не `self`. Опция `cb_opt` инициализируется через `table.initViewItemOption(cb_opt)` с флагом `features = HasCheckIndicator`.
  2. **Три состояния индикатора**: `State_On` (`Qt.CheckState.Checked`) — все строки выбраны; `State_Off` (`Qt.CheckState.Unchecked`) — ни одной строки не выбрано; `State_NoChange` (`Qt.CheckState.PartiallyChecked`) — выбрана часть строк.
  3. **Синхронизация состояния на лету**: При изменении данных строк (`_on_model_data_changed`) заголовок таблицы немедленно перерисовывается через `header.viewport().update()`.
- **Strict Bulk Toggle Rules**:
  1. **Клик по шапке**: Клик по заголовку колонки `GROUP_LAUNCH` перехватывается в `_on_sort_clicked` до контроллера сортировки и вызывает `_toggle_all_group_launch()`.
  2. **Логика переключения**: Если все строки отмечены — снимаются все; если хотя бы одна не отмечена — отмечаются все строки.
  3. **Пакетное обновление модели и БД**: Метод `LinksTableModel.set_all_group_launch(val_int)` синхронно обновляет строки модели, испускает один общий `dataChanged` на весь диапазон колонки и для каждой записи испускает сигнал `groupLaunchToggled(link_id, val_int)` для асинхронного сохранения в БД.

## 48. Architecture Standards: Font Rendering, Unicode Tile Layout & Adaptive Tree Rows (КОНТРАКТ РЕНДЕРИНГА ШРИФТОВ, UNICODE И ВЫСОТЫ СТРОК)
- **Status: FIXED BEHAVIOR / REGRESSION PROTECTION**: Зафиксировано поведение `app/startup/app_factory.py`, `app/views/widgets/tiles/delegate.py`, `app/views/widgets/custom_widgets.py`, `app/views/widgets/link/base_table.py` и правил типографики в `app/services/theme_stylesheet_service.py`. Изменения этих компонентов обязаны сохранять описанные ниже свойства.
- **Font Policy & Table Metrics**:
  1. Базовый шрифт приложения использует `QFont.StyleStrategy.PreferAntialias` и `QFont.HintingPreference.PreferVerticalHinting`. Запрещено возвращать принудительный `PreferFullHinting` или отключать сглаживание без отдельного запроса пользователя. Семейство и размеры продолжают поступать из существующих настроек и `app_config`.
  2. При изменении размера шрифта дерева и таблицы сохраняется политика рендеринга базового шрифта. В `TableDelegate._apply_column_font_size` изменение `opt.font` обязательно сопровождается обновлением `opt.fontMetrics = QFontMetrics(f)` до расчёта сокращения текста.
  3. В генерируемых стилях заголовков таблицы сохраняется `font-weight: normal` для обычного состояния, `hover`, `pressed` и `checked`. Смена состояния не должна менять толщину текста.
- **Category Tile Text Layout**:
  1. Подписи плиток рассчитываются через `QTextLayout` с `WrapAtWordBoundaryOrAnywhere`, горизонтальным центрированием и выравниванием сверху. Готовые строки выводятся через `QTextLine.draw(painter, text_origin)`; запрещено повторно рисовать обычные строки через `drawText` с ручным разбиением Python-строки.
  2. `QTextLayout` и `QFontMetricsF` используют фактический шрифт и `option.widget` как устройство метрик. Координаты и накопленная высота строк сохраняются дробными (`QPointF`, сумма `line.height()`). Округление вверх через `ceil` выполняется при формировании итоговой высоты `QSize` в `sizeHint`, а не для каждой строки.
  3. `QTextLine.textStart()` и `textLength()` выражены в кодовых единицах UTF-16. Запрещено непосредственно применять их к срезам Python `str`. При извлечении последней видимой строки используется соответствующий срез UTF-16 LE с последующим декодированием; emoji и другие символы вне BMP не должны сдвигать границы строк.
  4. Если превышен `get_tile_text_max_lines()`, последняя видимая строка получает многоточие и сокращается через `QFontMetricsF.elidedText(..., ElideRight, available_w)`. Она рисуется отдельным `QTextLayout` в режиме `NoWrap`, с сохранением центрирования и базовой линии исходной строки (`line.y() + line.ascent() - elided_line.ascent()`).
  5. `paint` и `sizeHint` сохраняют согласованность шрифта, доступной ширины, переноса и лимита строк из конфигурации. Запрещено заменять конфигурацию фиксированным числом строк или масштабировать готовый растровый снимок подписи вместо повторного рендеринга текста.
- **Adaptive Structure Tree Rows**:
  1. `ui.row_height` является минимальной высотой, а не фиксированным ограничением. `HighQualityTreeDelegate.sizeHint` инициализирует актуальный `QStyleOptionViewItem` через `initStyleOption` и возвращает высоту `max(row_h, base.height(), ceil(QFontMetricsF(opt.font, opt.widget).height()) + 4, max(0, opt.decorationSize.height()) + 4)`.
  2. После применения нового размера шрифта `StructureTreeView.update_font_size` вызывает `doItemsLayout()` перед обновлением viewport. Увеличение и последующее уменьшение шрифта обязаны пересчитывать геометрию строк; запрещено ограничиваться перерисовкой старых прямоугольников.
  3. Сохраняются существующие fallback конфигурации, настройки иконок и `setUniformRowHeights(True)`. Не следует изменять дизайн дерева, скроллбаров или панели сфер ради исправления метрик текста.
- **Regression Coverage**:
  1. `tests/test_text_rendering_geometry.py` защищает сравнение вывода плиток с эталонным `QTextLayout` для латиницы, кириллицы и emoji при DPR `1.0`, `1.25`, `1.5`, `1.75`, `2.0`; сокращение последней строки с многоточием; достаточность `sizeHint`; увеличение и уменьшение высоты строк дерева; размещение крупной иконки.
  2. Проверки геометрии дерева изолируют отложенную установку branch proxy style через тестовый `monkeypatch`, чтобы она не меняла владение общим Qt-стилем других тестов. Это изоляция тестового окружения, а не разрешение менять механизм стиля в приложении.
  3. Прохождение рендер-тестов с заданным DPR не заменяет визуальную проверку на реальных мониторах и не является гарантией одинакового сглаживания на любых дисплеях. При изменении этого контракта должны сохраняться перечисленные регрессионные сценарии; запуск проверок выполняется с учётом разрешения пользователя на тестирование.
## 49. Architecture Standards: Top Bar & Menu Bar Lifecycle Protection (ЗАЩИТА ЖИЗНЕННОГО ЦИКЛА ВИДЖЕТОВ ВЕРХНЕЙ ПАНЕЛИ И МЕНЮ)
- **Status: FROZEN ARCHITECTURE / STRICT RULES**: Жизненный цикл виджетов верхней панели (главное меню `QMenuBar`, адаптеры тулбара `FavoritesToolbarAdapter`, `RecentHistoryToolbarAdapter`) зафиксирован для полного исключения мерцания и скачков компоновки (layout jitter/flicker) при смене темы оформления и обновлении данных.
- **Strict Lifecycle Rules**:
  1. **Персистентность главного меню (`MenuController`)**: Виджет `menu_bar_widget` (`QMenuBar`) создаётся один раз при инициализации окна. В методе `rebuild_after_theme_change()` категорически запрещено вызывать `deleteLater()`, пересоздавать виджет меню или повторно вызывать `install_menu_bar_widget`. Обновление иконок действий меню при смене темы оформления выполняется строго in-place через `MainMenuBuilder.update_theme(theme)` без пересоздания виджета менюбара. Стили меню обновляются автоматически движком QSS Qt.
  2. **Персистентность кнопок тулбара (`_main_action`)**: В `FavoritesToolbarAdapter` и `RecentHistoryToolbarAdapter` кнопки тулбара (`_main_action`) создаются один раз при старте. Категорически запрещено удалять `_main_action` из тулбара (`clear_actions()`, `removeAction()`, `deleteLater()`) при получении новых данных (`set_data()`) или смене темы.
  3. **In-place обновление выпадающих меню**: При поступлении обновленного списка закладок или смене темы оформления в адаптерах тулбара (`FavoritesToolbarAdapter`, `RecentHistoryToolbarAdapter`, `ToolsToolbarAdapter`) выпадающее меню (`TopBarMenu`) подменяется строго на лету через `self._main_action.setMenu(new_menu)` с обязательным удалением предыдущего меню через `old_menu.deleteLater()`. Виджет кнопки на тулбаре обязан оставаться физически неподвижным, а все подпункты выпадающего меню обязаны получать актуальные иконки в цвете новой темы.
  4. **In-place обновление иконок**: При переключении темы иконки на кнопках тулбара обновляются строго in-place через `refresh_actions()` -> `_main_action.setIcon(new_icon)` без пересоздания экшенов.

## 50. Architecture Standards: Caching Architecture, Concurrency & Batching Standards (АРХИТЕКТУРНЫЙ СТАНДАРТ КЭШИРОВАНИЯ И ПАКЕТНОЙ ОБРАБОТКИ)
- **Status: FROZEN ARCHITECTURE / STRICT RULES**: Архитектура многоуровневого кэширования (`LinksBusinessLogic`, `StructureBusinessLogic`, `NegativeCache`, `ThreadSafeIconCache`, `FaviconCache`) зафиксирована для предотвращения гонок состояний, утечек памяти, деградации производительности и повреждения файлов базы данных кэша.
- **Strict Concurrency & Data Freshness Rules**:
  1. **Защита от устаревших асинхронных ответов (Request Generation)**: В `LinksBusinessLogic` метод `_invalidate_cache()` обязан атомарно инкрементировать поколение запросов (`_request_generation += 1`). Метод `_cache_links_and_emit()` обязан принимать `expected_generation` и отбрасывать любые ответы от фоновых воркеров, если текущее поколение изменилось во время выполнения запроса к БД.
  2. **Защита предзагрузки структуры (Preload Generation Token)**: В `StructureBusinessLogic` инвалидация сбрасывает активный токен предзагрузки (`_structure_preload_active_token = None`), а `_on_structure_snapshot_ready()` применяет снапшот структуры строго при совпадении токена и отсутствии флага `dirty`.
- **Strict Memory Management & LRU Rules**:
  1. **Очистка метаданных и компакция кучи (`NegativeCache`)**: При вытеснении устаревших записей по TTL или переполнению размера словарь поколений обязан очищаться (`self._gen.pop(key, None)`). При накоплении «мертвых» ключей в куче (`len(self._heap) > self.max_size * 2`) обязательна компакция кучи пересозданием списка актуальных записей и вызовом `heapq.heapify()`.
  2. **Полноценный LRU и защита от полных сканирований (`ThreadSafeIconCache`)**: При вызовах `get_path()` и `get_qicon()` обязан обновляться порядок актуальности в LRU (`self._path_lru.access(key)`, `self._qicon_lru.access(key)`). Запрещено вызывать тяжелые полные сканирования словарей (`_sync_*_structs()`) на чтении кэша.
- **Strict Disk Storage, FileLock & Batching Rules**:
  1. **Защита от повреждения файла базы данных (`FaviconCache`)**: При таймауте получения межпроцессного файлового лока контекстный менеджер `_file_lock()` обязан возбуждать исключение `FaviconLockTimeoutError`. Категорически запрещено продолжать работу без блокировки (fall-through в `yield None` без локов). Публичные методы `get()`, `set()`, `invalidate()` обязаны деликатно перехватывать таймаут блокировки.
  2. **Дедупликация дисковой синхронизации и фоновая очистка**: В `FaviconCache` периодическая очистка (`_maybe_cleanup`) интегрирована в сохранение записей (`_store_entry_in_db`). Вызов синхронизации `_sync_db()` строго дедуплицирован и вызывается один раз в конце транзакции сохранения.
  3. **Пакетный режим массовой записи (Batch Writing)**: Для массовых операций импорта и фонового обновления фавиконов (`IconRefreshWorker`) обязателен метод пакетного контекста `cache.batch(max_size=50)` или `cache.set_many(entries)`. Запрещено выполнять запись и синхронизацию индекса поштучно на каждую ссылку в циклах фоновых воркеров.

## 51. Architecture Standards: Contract-Driven Testing & Test Synchronization (СИНХРОНИЗАЦИЯ ТЕСТОВ С КОНТРАКТОМ ПРИЛОЖЕНИЯ)
- **Status: STRICT QUALITY RULE / MANDATORY ARCHITECTURE STANDARD**: Правило разрешения противоречий между боевым кодом приложения и тестовым сьютом.
- **Strict Rules**:
  1. **Первичность рабочего функционала и контракта**: Боевой код приложения, утверждённые правила поведения и пользовательские контракты первичны. Категорически запрещено переписывать, ломать, ухудшать или адаптировать рабочую логику программы под ожидания устаревших моков или старых тестов ради получения зелёного статуса `pytest`.
  2. **Обязанность актуализации тестов при изменении контракта**: При внедрении нового поведения программы (например, замена тихого авто-переименования/пропуска на интерактивный диалог разрешения коллизий, унификация команд Undo/Redo, изменение структуры данных) актуализации подлежат строго ТЕСТОВЫЕ файлы (`tests/`). Тесты обязаны быть переписаны под новый контракт.
  3. **Запрет на возврат технического долга в боевой код**: Если тест падает из-за того, что ожидает старое поведение (признанное техдолгом или заменённое новым контрактом), запрещено возвращать это старое поведение в боевой код — исправляется и приводится к контракту сам тест.

## 52. Architecture Standards: Unified Top Bar Icon Coloring Architecture (СТАНДАРТ ЕДИНОГО МЕХАНИЗМА ОКРАШИВАНИЯ ИКОНОК ВЕРХНЕЙ ПАНЕЛИ)
- **Status: FROZEN ARCHITECTURE / STRICT RULES**: Архитектура отрисовки и окрашивания иконок верхней панели зафиксирована. Категорически запрещено создание параллельных/ad-hoc механизмов раскрашивания.
- **Strict Single Source of Truth Rules**:
  1. **Единый источник цвета и кэширования**: Все иконки кнопок верхней панели обязаны создаваться и окрашиваться строго через канонический пайплайн `get_menu_icon(name, theme)` -> `icon_cache` с цветом из `theme_registry.get_theme_icon_color(theme)`.
  2. **Категорический запрет на локальную перекраску SVG**: В модулях верхней панели (`toolbar_adapters.py`, `top_bar_setup.py`, контроллерах тулбара) запрещено реализовывать самодельные функции раскраски SVG через регулярные выражения, подмену атрибутов `fill`/`stroke`, прямой вызов `QSvgRenderer` или использование цвета `text_secondary` для иконок кнопок.
  3. **Запрет на подмену иконок по наведению (`hover_icon` / `rest_icon`)**: Иконка кнопки остаётся монолитной и стабильной. Категорически запрещено переопределять `Enter`/`Leave` для циклической замены `setIcon(hover_icon)` / `setIcon(rest_icon)`. Стилизация ховера кнопок тулбара осуществляется исключительно средствами CSS/QSS темы оформления.
  4. **Автоматическая синхронизация Qt Action**: Кнопки тулбара получают иконки через штатную связку Qt `widgetForAction(action)`. При смене темы `refresh_actions()` обновляет `action.setIcon()`, не внедряя скрытых фильтров или сторонних объектов в кнопку.
  5. **100% Паритет окрашивания главного и выпадающих меню**: Иконки действий в главном меню (`QMenuBar`) и выпадающих меню тулбара (`topBarToolsMenu` и др.) обязаны на 100% соответствовать активному цвету `theme_registry.get_theme_icon_color(theme)`. Запрещено оставлять устаревшие иконки от предыдущей темы при динамическом переключении тем оформления.
  6. **Векторный рендеринг тинтованных SVG (`TintedSvgIconEngine`)**: Тинтованные SVG-иконки приложения обязаны создаваться строго через нативный векторный движок `TintedSvgIconEngine(QIconEngine)` с отрисовкой в `paint(painter, rect)` без предварительной растровой нарезки в фиксированные `QPixmap(sz, sz)`. При запросе растра через `pixmap(size)` размер пиксмапа обязан масштабироваться на текущий `devicePixelRatio` экрана с вызовом `pm.setDevicePixelRatio(dpr)`.

## 53. Architecture Standards: Monolithic Hover & Sharp Geometry (ЕДИНЫЙ ХОВЕР И МОНОЛИТНАЯ ГЕОМЕТРИЯ)
- **Status: FROZEN ARCHITECTURE / STRICT RULES**: Архитектурный стандарт монолитного прямоугольного дизайна без скруглений и единого системного фона наведения (`hover_bg`).
- **Strict Sharp Geometry Rules**:
  1. **Категорический запрет на скругления**: Во всех интерактивных элементах приложения (кнопки верхнего тулбара, кнопки нижнего бара, плитки категорий `categoryTiles`, элементы дерева, таблиц, списков) строго запрещены любые скругления (`border-radius > 0`). Геометрия обязана оставаться строго монолитной, плоской и прямоугольной (`border-radius: 0`).
  2. **Запрет на локальные скругления в QSS**: Запрещено возвращать `border-radius: 6px` или любые другие радиусы в `common.qss`, файлах тем `.qss` или коде виджетов.
  3. **Единственное системное исключение (Scrollbar Exception)**: Скроллбар `QScrollBar` с `border-radius: 3px` в `common.qss` (согласно §7) является единственным зафиксированным исключением из правила монолитной геометрии (стиль капсульного скроллбара Fluent / macOS).
- **Strict Unified Hover Token Rules**:
  1. **Единый источник фона ховера (`hover_bg`)**: Фон при наведении для элементов управления (`QWidget#topBarHost QToolButton`, `QWidget#topBarHost QPushButton`, `QWidget#bottomBarContainer QPushButton`, `QDialog QPushButton`, `QTreeView::item:!selected:hover`, `QListView#categoryTiles::item:hover`, `QMenuBar::item:hover`) обязан использовать системный токен активной темы `@hover_bg` (или сгенерированный `{bg_hover}`).
  2. **Запрет на хардкодные цвета ховера**: Запрещено использовать фиксированные HEX-цвета (вроде `#252D3A`), конфликтующие с палитрой активной темы оформления.
  3. **Синхронизация верхнего и нижнего тулбаров**: В `ThemeStylesheetService._adapt_qss_for_topbar_buttons` кнопки нижнего тулбара (`bottomBarContainer QPushButton`) обязаны стилизоваться совместно с кнопками верхнего тулбара, гарантируя одинаковый цвет фона наведения и нажатия.
  4. **Контракт таблицы данных**: Таблица закладок `LinksTableView` получает цвет ховера строки строго через свойство `qproperty-hoverRowColor: {hover_bg}`, обеспечивая паритет с деревом структуры.

## 54. Architecture Standards: Unified Top Bar Button Styling & Theme Color Isolation (ЕДИНОЕ МЕСТО ОПРЕДЕЛЕНИЯ СТИЛЕЙ КНОПОК ВЕРХНЕЙ ПАНЕЛИ)
- **Status: FROZEN ARCHITECTURE / STRICT RULES**: Архитектурный стандарт полной изоляции стилей и цветов кнопок верхней панели.
- **Strict Single Source of Styling Rules**:
  1. **Все стили кнопок верхней панели в одном месте**: Все правила стилей, геометрия, размеры (`min-width/height`, `max-width/height`), отступы (`margin`, `padding`), границы и структурное поведение всех кнопок верхней панели (`QWidget#topBarHost QToolButton`, `QWidget#topBarHost QPushButton`) определяются строго и исключительно в одном месте — в `app/resources/qss/common.qss`. В коде Python запрещено переопределять размеры кнопок через `setFixedSize`.
  2. **В темах — строго только цвета**: Файлы тем оформления (`*.qss`), токены и `ThemeStylesheetService` имеют право определять **исключительно цветовые параметры** (`background`, `background-color`, `color`, `border-color` для состояний normal, `:hover`, `:pressed`, `menu_active`).
  3. **Категорический запрет на изменение геометрии и размеров в темах**: Запрещено в файлах тем или генераторах динамического QSS переопределять размеры кнопок (`min-width`, `max-width`, `min-height`, `max-height`), применять вычитания пикселей (`- 2`), менять отступы или вмешиваться в блочную модель.
  4. **Абсолютная идентичность поведения**: Все кнопки верхней панели управляются единым базовым правилом `QWidget#topBarHost QToolButton`. Запрещено разделять поведение, геометрию или реакцию на наведение по отдельным ID кнопок.
  5. **Зафиксированная геометрия кнопок и сетки панели**:
     - Размер контента кнопок: строго **32×32 px** (`min-width: 32px; max-width: 32px; min-height: 32px; max-height: 32px;`).
     - Рамка кнопок: строго **1 px** (`border: 1px solid transparent;`).
     - Полный габарит кнопки с обводкой: строго **34×34 px** (34 с обводкой, 32 без обводки).
     - Межкнопочный отступ: строго **4 px** (`spacing: 4`).
     - Разделители тулбара: строго **1 px** (`width: 1px;`).
     - Левый отступ тулбара: строго **4 px** (`top_bar.setContentsMargins(4, 0, ...)`).
     - Отступ перед разделителем поиска: строго **4 px**.
     - Верхняя панель адаптивна по ширине окна; искусственная привязка ширины кнопок тулбара к ширине левой панели строго запрещена.


## 55. Architecture Standards: Links Table Performance & 323px Left Panel Contract (СТАНДАРТЫ ТАБЛИЦЫ ССЫЛОК И ПАНЕЛИ 323 PX)
- **Status: FROZEN ARCHITECTURE / STRICT RULES**: Архитектурные стандарты производительности таблицы ссылок и геометрии левой панели.
- **Strict Left Panel Width & Auto-Hide Contract**:
  1. **Ширина левой панели**: строго **323 px** (`left_panel.setMinimumWidth(323)` и базовая геометрия сплиттера `[323, ...]`). Категорически запрещено сбрасывать или уменьшать ширину левой панели в покое.
  2. **Защита разворачивания окна на весь экран**: При вызове `isMaximized()` в `_AutoHideTreeFilter` запрещено скрывать левую панель. Если панель была свернута, она обязана восстанавливаться в 323 px.
  3. **Сплиттер**: При сворачивании `left_panel.setMinimumWidth(0)`, при восстановлении `left_panel.setMinimumWidth(323)` с восстановлением сохраненного размера `[323, ...]`.
- **Strict Table Delegate & Header Performance Contract**:
  1. **Канонический `initStyleOption`**: Настройка шрифтов, цветов, элизии названий и исключение флага `HasCheckIndicator` производятся строго внутри `TableDelegate.initStyleOption`. Запрещено дублировать эти вызовы в `paint()`.
  2. **Одинарный проход отрисовки `paint()`**: В `TableDelegate.paint()` запрещено вручную повторно вызывать `self.initStyleOption()` или создавать дублирующие копии `QStyleOptionViewItem`. Базовый вызов `super().paint(painter, option, index)` выполняет ровно один проход инициализации в ядре C++.
  3. **Отрисовка чекбокса `GROUP_LAUNCH`**: Отрисовывается строго через `super().initStyleOption(check_opt, index)` и `style.drawPrimitive(PE_IndicatorItemViewItemCheck, check_opt, painter, widget)`.
  4. **Фиксация высоты заголовка**: В `ExplorerHeaderView._sync_row_height` высота фиксируется строго через `self.setFixedHeight(h)`. Категорически запрещено вызывать `setDefaultSectionSize`, `setMinimumSectionSize` (перезаписывающие ширину колонок) или `updateGeometry()` внутри `resizeEvent`.
- **Strict Columns Declarative Contract**:
  1. **Индексы колонок**: строго `ORDER = 0`, `GROUP_LAUNCH = 1`, `NAME = 2`, `LAUNCH = 3`, `NOTES = 4`, `TYPE = 5`.
  2. **Режимы изменения размера**: `ORDER` — fixed (36 px), `GROUP_LAUNCH` — fixed (32 px), `NAME` — interactive, `LAUNCH` — fixed, `NOTES` — stretch (`min_width = 0`), `TYPE` — interactive (104 px).
  3. **Тултипы**: `NAME` обязан иметь `tooltip_builder="_tooltip_name"`, `TYPE` обязан иметь `tooltip_builder="_tooltip_type"`, `NOTES` обязан иметь `tooltip_builder="_tooltip_notes"`.

## 56. Architecture Standards: Active Context, Selection & Navigation Lifecycle Contract (СТАНДАРТЫ АКТИВНОГО КОНТЕКСТА, НАВИГАЦИИ И Model/View СОСТОЯНИЯ)
- **Status: FROZEN ARCHITECTURE / STRICT RULES**: Архитектурные стандарты управления активным контекстом (`current item`), выделением (`selection`), фокусом ввода (`keyboard focus`) и сигналами моделей.
- **Strict Separation of Concerns (Разделение понятий Qt 6)**:
  1. **Active Entity**: Идентификатор бизнес-логики (`entity_id`: `section_id`, `category_id`, `link_id`) — единственный источник истины.
  2. **Current Item**: `QItemSelectionModel.currentIndex()` — единичный активный элемент представления, управляющий контекстом правой панели и стрелочной навигацией.
  3. **Selection**: `QItemSelectionModel.selection()` — множество выбранных элементов для групповых операций (`batch delete/move/copy`).
  4. **Keyboard Focus**: `QWidget.focusWidget() / setFocus()` — виджет, перехватывающий ввод. Смена `currentIndex()` категорически не имеет права принудительно вызывать `setFocus()` на родительский `QAbstractItemView`, если активен инлайн-редактор (`QLineEdit`, `F2`), поле поиска или модальный диалог.
- **Strict Stable Entity Identity Principle (Принцип стабильной идентичности)**:
  1. **Запрет на `row` в памяти и настройках**: Номер строки (`row`) является временной визуальной координатой и никогда не используется для долговременной идентификации.
  2. **Персистентность**: В `QSettings` сохраняются строго постоянные ID сущностей: `CurrentSelection_{sphere_id}` = `entity_id`, `ExpandedSections_{sphere_id}` = `[entity_id, ...]`.
  3. **Proxy Translation**: При наличии `QSortFilterProxyModel` перевод выполняется строго через `proxy.mapToSource()` и `proxy.mapFromSource()`. Запрещено восстанавливать индекс после сортировки или переименования по старому `row`.
- **Strict Granular Model Signals (Запрет на `modelReset`)**:
  1. **Запрет на `modelReset()`**: Категорически запрещено вызывать `beginResetModel() / endResetModel()` для локальных CRUD-операций, перемещения (DnD), переименования, смены порядка или вставки элементов, если изменение выразимо гранулярными сигналами.
  2. **Обязательные сигналы**: Создание/вставка — строго `beginInsertRows`/`endInsertRows`; удаление — строго `beginRemoveRows`/`endRemoveRows`; перемещение — строго `beginMoveRows`/`endMoveRows`; редактирование — строго `dataChanged(topLeft, bottomRight, roles)`; сортировка — строго `layoutAboutToBeChanged` $\rightarrow$ перенос `QPersistentModelIndex` $\rightarrow$ `layoutChanged`.
- **Strict Single Source of Context Synchronization**:
  1. **Шина `currentChanged`**: Правая панель подписывается строго на `currentChanged` (или `activeEntityChanged(entity_id)`), а не на сырой `selectionChanged`.
  2. **Запрет циклических сигналов**: `ActiveContextCoordinator` централизованно изолирует события выбора во избежание взаимных триггеров между деревом, плитками и таблицей.
- **Strict Operation Matrix & Fallback Cascade**:
  1. **Созидательные операции (`Create`, `Paste`, `Import`, `Duplicate`)**: Сущность получает постоянный `entity_id`, вставляется через `beginInsertRows`, транслируется в `proxy_index`, получает `setCurrentIndex(index, ClearAndSelect | Rows)` и отображается через штатный reveal (`scrollTo(..., EnsureVisible)` / `ensureWidgetVisible()`).
  2. **Деструктивные операции (`Delete`, `Multi-Delete`)**:
     - Одиночное удаление: целевая строка $\text{target\_row} = \min(\text{old\_row},\, \text{rowCount} - 1)$.
     - Групповое удаление: целевой становится первый выживший элемент после удаленного диапазона (если нет — последний выживший перед диапазоном).
     - При опустошении контейнера: категория $\rightarrow$ родительский `section_id`; раздел $\rightarrow$ соседний раздел сферы; пустая сфера $\rightarrow$ штатный детерминированный `empty_sphere_state`.
  3. **Стек отмены (`Undo / Redo`)**:
     - Классы `QUndoCommand` категорически не хранят ссылок на `QWidget` (`QTreeView`, `LinksTableView`). Команда оперирует только данными модели/репозитория и передает `affected_entity_id` навигационному контроллеру.
     - `Cut` (`Ctrl+X`) помечает элементы `pending_cut`, а `Paste` (`Ctrl+V`) формирует атомарную команду переноса `MoveEntitiesCommand`, отменяемую одним нажатием `Ctrl+Z`.
  4. **Переключение сфер**: Чтение `entity_id` из `QSettings` $\rightarrow$ поиск `source_index` $\rightarrow$ `mapFromSource()`. При отсутствии — fallback: `Saved Category ID` $\rightarrow$ `Parent Section ID` $\rightarrow$ `First Selectable Section` $\rightarrow$ `Empty Sphere State`.


## 57. Architecture Standards: Single-Step Atomic Undo for Cut & Paste / Move (СТАНДАРТ АТОМАРНОГО UNDO ДЛЯ ВЫРЕЗАНИЯ И ВСТАВКИ)
- **Status: FROZEN ARCHITECTURE / STRICT RULES**: Механизм отмены (`Undo` / `Ctrl+Z`) и повтора (`Redo` / `Ctrl+Y`) операций вырезания и вставки (`Cut & Paste` / `Move`) для всех сущностей приложения (разделы, категории, ссылки) строго обязан выполняться за **ровно 1 шаг (одно нажатие `Ctrl+Z`)**. Категорически запрещена необходимость повторного (двойного) нажатия `Ctrl+Z` для отмены перемещения сущностей.
- **Strict Command Merging Contract**:
  1. **Идентификаторы слияния (`id()`)**:
     - Категории: `_CUT_PASTE_CATEGORY_CMD_ID = 2001`
     - Разделы: `_CUT_PASTE_SECTION_CMD_ID = 2002`
     - Ссылки: `_CUT_PASTE_LINK_CMD_ID = 2003`
     Команды удаления (`DeleteLinkCmd`, `BatchDeleteLinksCmd`, `DeleteCategoryCmd`, `BatchDeleteCategoriesCmd`, `DeleteSectionCmd`, `DeleteSectionsCmd`) и сохранения/вставки (`SaveLinkCmd`, `BatchSaveLinksCmd`, `PasteCategoriesCmd`, `PasteSectionsCmd`) при `is_cut=True` обязаны возвращать соответствующий константный ID из метода `id() -> int`.
  2. **Атомарное слияние через `mergeWith()`**:
     Команды удаления при `is_cut=True` реализуют `mergeWith(other: Any) -> bool`. При совпадении ID слияния команда вставки сохраняется как `self._paste_cmd = other`, и возвращается `True`.
  3. **Делегирование `redo()` и `undo()`**:
     - При вызове `undo()` команды удаления: строго сначала вызывается `self._paste_cmd.undo()` (удаление сущностей из целевого контейнера), затем восстанавливаются удаленные сущности в исходном контейнере.
     - При повторе `redo()`: после удаления из исходного контейнера строго вызывается `self._paste_cmd.redo()` (повторная вставка в целевой контейнер).
  4. **Запрет на `undo_stack.macro()` для вырезания и вставки**:
     В `LinksUIClipboard` (и аналогичных контроллерах) категорически запрещено оборачивать вызовы команд `Delete` и `Save` в `with undo_stack.macro(...)` при операциях вырезания/вставки, так как макрос Qt создает анонимный составной контейнер без ID, блокируя механизм `mergeWith()` в `QUndoStack`.


## 58. Architecture Standards: State Mutation & Presentation Reload Contract (КОНТРАКТ ОБНОВЛЕНИЯ ДАННЫХ И UNDO/REDO)
- **Status: FROZEN ARCHITECTURE / STRICT RULES**: Архитектурный контракт обновления отображения после мутаций данных (Undo, Redo, Paste, DnD).
- **Strict Mutation Reload Rules**:
  1. **Разделение навигации и обновления данных**: При операциях отката/наката (Undo/Redo) или пакетных мутациях данных в пределах текущей категории запрещено полагаться на навигационные методы дерева (`select_*`), отсекающие повторные переходы.
  2. **Централизованный `force_reload`**: Принудительное обновление представления при изменении данных в активной категории обязано вызываться через `ui_state_manager.load_category(category_id, force_reload=True)`.
  3. **Запрет на искажение геометрии при починке данных**: Категорически запрещено изменять параметры сплиттеров, тулбара, размеры панелей или фильтры ресайза окна (`WindowStateChange`, `Resize`) для решения задач обновления списков или отката действий.

## 59. Architecture Standards: Single-Click & Selection Model Contract (ГАРАНТИЯ НАДЁЖНОСТИ ВЫДЕЛЕНИЯ И ДЕЙСТВИЙ)
- **Status: FROZEN ARCHITECTURE / STRICT RULES**: Контракт обработки выделения и активации действий с первого клика полностью зафиксирован.
- **Strict Rules**:
  1. **Fallback для строк (`roles.get_selected_rows`)**: Метод `get_selected_rows(view)` обязан использовать fallback на `selectedIndexes()`, если `selectedRows()` возвращает пустой список при наличии `hasSelection()`. Запрещено полагаться исключительно на `selectedRows()`, так как клик по отдельной ячейке не включает флаг полной строки.
  2. **Сохранение выделения при обновлении (`PopulationManagerMixin._capture_ui_state`)**: Захват выбранных строк перед обновлением таблицы обязан выполняться строго через `get_selected_rows(table)` во избежание сброса выделения в `[]`.
  3. **Стек представления в `ActionController`**: Определение доступности действий таблицы ссылок (`can_copy`, `can_cut`, `can_delete`, `can_paste`, `select_all_action`) в `update_action_states`, `select_all_current` и `clear_selection_current` обязано проверять `_is_table_focused() or _is_table_stack_active()`. Запрещено требовать исключительного фокуса на таблице.
  4. **Правый клик по дереву (`StructureUIController._on_context_menu`)**: При вызове контекстного меню по валидному элементу дерева строка обязана немедленно выбираться через `sel_model.setCurrentIndex(item, ClearAndSelect | Rows)`, если она ещё не выбрана.
  5. **Клик по активному узлу (`SelectionHandling._on_single_click`)**: Сигнал `tree.clicked` обязан быть подключён к `_on_single_click`. Если нажатая категория отличается от отображаемой в таблице (например, после поиска или режима плиток), категория обязана загружаться с первого клика.


## 60. Architecture Standards: Unified Data Mutation, Clipboard, DnD & Undo/Redo Lifecycle Contract (КОНТРАКТ ОПЕРАЦИЙ БУФЕРА, DND, СЛИЯНИЯ И ОТКАТА)
- **Status: FROZEN ARCHITECTURE / STRICT RULES**: Полный регламент жизненного цикла операций буфера обмена (Cut/Copy/Paste), Drag & Drop, удаления с восстановлением, разрешения коллизий имён и сброса кэшей для всех сущностей (разделы, категории, ссылки).
- **Strict Entity Operation Rules**:
  1. **Разделы (Sections: Cut, Paste, Merge & Undo)**:
     - При вырезании (`Ctrl+X`) раздел визуально помечается полупрозрачным (`_cut_item_ids`). Данные раздела и всего вложенного дерева копируются в буфер.
     - При вставке (`Ctrl+V`) в ту же или другую сферу без коллизии выполняется `MoveSectionsToSphereCommand`: обновляется `sphere_id`, синхронно сбрасывается кэш структуры (`_invalidate_structure_cache`), происходит переход в целевую сферу с выделением раздела.
     - При совпадении имён вызывается сессия разрешения коллизий. При выборе «Объединить» (`merge`) операция маршрутизируется строго в `MergeSectionToSphereCommand`: все категории и ссылки переносятся в целевой раздел с переименованием дубликатов категорий при необходимости, исходный раздел удаляется, кэши обеих сфер инвалидируются, а UI обновляется.
     - При `Undo` (`Ctrl+Z`) слияния исходный раздел восстанавливается в SQLite, категории возвращаются назад с исходными именами, кэши обеих сфер инвалидируются, а фокус восстанавливается на исходном разделе.
  2. **Категории (Categories: Cut, Paste, Merge & Undo)**:
     - При вырезании категория помечается полупрозрачной в дереве и плитках.
     - При вставке в раздел без коллизий выполняется `MoveCategoriesCommand`: обновляется `section_id`, синхронно сбрасывается кэш категорий (`_invalidate_categories_cache`), обновляется дерево и вызывается `refresh_section_tiles`.
     - При совпадении имён и выборе «Объединить» выполняется `MergeCategoriesCommand`: ссылки переносятся в целевую категорию, исходная пустая категория удаляется, кэши обоих разделов сбрасываются, плитки перерисовываются.
     - При `Undo` категория возвращается в исходный раздел со своими исходными ссылками и позицией, кэши структуры сбрасываются, дерево и плитки синхронно обновляются.
  3. **Ссылки (Links: Cut, Paste, Replace & Undo)**:
     - При вырезании строки таблицы помечаются полупрозрачными (`set_cut_link_ids`).
     - При перемещении или переименовании выполняется `MoveLinksCommand` или `BatchSaveLinksCmd`: обновляется `category_id` и позиции, синхронно инвалидируется кэш ссылок (`_invalidate_links_cache` в `links_business`) и таблица немедленно перезагружается через `table.load_links`.
     - При замене ссылок старые данные сохраняются в снапшоте. При `Undo` вызывается `batch_create_or_update_links`, полностью восстанавливая все поля заменённых ссылок (`notes`, `url`, `name`, `type`), кэш инвалидируется и таблица обновляется.
  4. **Маршрутизация вставки ссылок из дерева и плиток**:
     - В `ActionController._paste_into_tree()` и `_paste_into_tiles()`: если в буфере обмена ссылки или URL-текст (нет категорий и разделов), а в дереве или плитках выбрана категория, операция `Ctrl+V` обязана маршрутизироваться в `links_actions.paste_link(target_category_id=...)` для немедленной вставки ссылок в выбранную категорию.
  5. **Drag & Drop**:
     - Перетаскивание категорий между разделами дерева или изменение порядка оформляется через `MoveCategoriesCommand` с обязательной инвалидацией кэша и перерисовкой плиток.
     - Перетаскивание ссылок внутри таблицы или на узел категории в дереве оформляется через `MoveLinksCommand` с поддержкой атомарного Undo.
     - Запрещено модифицировать панель сфер `spheres_bar` под жесты перетаскивания (действует запрет §6). Перемещение разделов между сферами выполняется строго через буфер обмена (`Ctrl+X` $\rightarrow$ переход $\rightarrow$ `Ctrl+V`).
  6. **Удаление с восстановлением (Subtree Deletion & Undo Guard)**:
     - Перед удалением раздела или категории обязательно формируется полный экспорт поддерева (`export_section_tree` / `export_category_tree`).
     - При `Undo` поддерево импортируется в базу в рамках единой команды отката, кэш сбрасывается, структура дерева и плитки разделов полностью восстанавливаются.
     - При удалении ссылок откат восстанавливает удалённые записи через `batch_create_or_update_links` с инвалидацией кэша.
  7. **Импорт браузера и архивов (Import Safety & Refresh Guard)**:
     - Импорт браузерных закладок HTML ведётся строго стековым парсером по контракту §8 с созданием обязательного снапшота базы данных перед записью (`_backup_before_import`).
     - После любого импорта (HTML или архивов `.aitesec`/`.aitecat`) обязательна очистка кэша иконок (`clear_icon_cache`), инвалидация кэшей структуры (`_invalidate_categories_cache` / `_invalidate_structure_cache`) и планирование немедленной перезагрузки представления через `schedule_structure_reload(0)` и `links_table_controller.reload()`.



## 61. Architecture Standards: Installed Applications Discovery & Persistent Cache Contract (ДИАЛОГ И КЭШИРОВАНИЕ УСТАНОВЛЕННЫХ ПРОГРАММ)
- **Status: FROZEN ARCHITECTURE / STRICT RULES**: Архитектура обнаружения установленных приложений Windows (`installed_apps_service.py`), дискового кэширования метаданных и иконок (`AppsCacheManager`) и диалога выбора (`InstalledAppsDialog`).
- **Strict Discovery & Cache Rules**:
  1. **Персистентный дисковый кэш метаданных**: Распарсенный список программ сериализуется в JSON-файл `%APPDATA%/.../cache/installed_apps.json` с фиксацией меток времени `mtime` системных каталогов меню «Пуск» (`%PROGRAMDATA%\Microsoft\Windows\Start Menu\Programs` и `%APPDATA%\Microsoft\Windows\Start Menu\Programs`). При совпадении `mtime` список загружается мгновенно (<5 мс) без повторного сканирования файловой системы и COM-интерфейсов.
  2. **Персистентный дисковый кэш системных иконок**: Извлечённые системные иконки сохраняются в PNG в директории кэша `%APPDATA%/.../cache/app_icons/{md5_hash}.png`. При повторных обращениях иконка считывается напрямую из PNG без дорогостоящих вызовов Shell API (`SHGetFileInfoW` / `ExtractIconExW`).
  3. **Двухуровневая автоматическая инвалидация**: 
     - В рантайме: через `QFileSystemWatcher` на системные каталоги меню «Пуск» при любых изменениях состава файлов.
     - При обращении: через сравнение текущих `mtime` директорий меню «Пуск» с сохранёнными в JSON кэша.
  4. **Приоритет видимой области (Visible Viewport First)**: В фоновом потоке `_AppsLoaderThread` извлечение и назначение иконок сначала выполняется для первых 25 видимых элементов списка, обеспечивая мгновенную отзывчивость интерфейса, а остальные элементы догружаются в фоне.
  5. **Бесшовный UI и скрытие индикаторов**: Индикатор загрузки (`loading_bar` и `loading_label`) скрывается немедленно в `_on_apps_loaded` при получении списка программ, не дожидаясь фоновой расстановки иконок. При наличии валидного кэша индикатор загрузки не показывается вовсе.
  6. **Горячая клавиша принудительного обновления**: Диалог `InstalledAppsDialog` поддерживает горячую клавишу `F5` для принудительного полного пересканирования системы (`force_refresh=True`).

## 62. Architecture Standards: External Drag-and-Drop & System OLE Contract (ВНЕШНИЙ DRAG & DROP ССЫЛОК)
- **Status: FROZEN ARCHITECTURE / STRICT RULES**: Архитектура перетаскивания ссылок из таблицы `LinksTableView` во внешние системные приложения (AiteBar, Проводник Windows, браузеры, текстовые редакторы).
- **Strict OLE Actions Rules**:
  1. **Снятие монополии MoveAction**: В `BaseDragDropTableWidget.startDrag` вызов `drag.exec()` обязан разрешать комбинацию действий `Qt.DropAction.CopyAction | Qt.DropAction.MoveAction | Qt.DropAction.LinkAction`. Запрещено ограничивать перетаскивание только внутренним `MoveAction`.
- **Strict Multi-Format Payload Rules**:
  1. **Двухуровневый QMimeData**: Метод `LinksTableView.mimeData` обязан сохранять внутренний служебный формат `application/x-aite-links` (через `super().mimeData`) для внутренней сортировки и переноса по категориям.
  2. **Системный текстовый формат (CF_UNICODETEXT)**: Через `mime_data.setText(...)` передаётся список чистых URL/путей (разделитель `\n`) для текстовых редакторов, веб-полей и AiteBar.
  3. **Формат списков URI и файлов (CF_HDROP / text/uri-list)**: Через `mime_data.setUrls(...)` локальные пути передаются строго как `QUrl.fromLocalFile(...)`, а веб-ссылки — с валидированной схемой (`https://`). Обязательна очистка обрамляющих кавычек путей (`strip('"\'')`).
  4. **Сохранение целостности OLE**: Запрещено удалять или повреждать внутренний JSON-формат `ids` при наполнении стандартных MIME-форматов.

## 63. Architecture Standards: Database Single-Instance Guard & Restore Conflict Resolution Contract (ЗАЩИТА БАЗЫ ДАННЫХ ОТ КОНФЛИКТОВ И БЛОКИРОВОК)
- **Status: FROZEN ARCHITECTURE / STRICT RULES**: Полный регламент защиты SQLite базы данных профиля от параллельного доступа, предотвращения зомби-процессов и интерактивного разрешения конфликтов при восстановлении из резервной копии.
- **Strict Single-Instance & Headless Rules**:
  1. **Глобальный SingleInstanceGuard**: Применяется ко всем режимам запуска приложения (`GUI`, `HEADLESS`). Запрещено запускать второй процесс над рабочей базой профиля. Повторный процесс обязан через IPC активировать существующий экземпляр (или передать открываемый файл) и штатно завершаться с `ExitCode.SUCCESS` без открытия базы данных SQLite.
  2. **Предотвращение зависания Headless-режима**: Режим `HEADLESS` без переданных файлов и без `auto_quit` обязан немедленно завершаться после завершения задач инициализации, не оставаясь в памяти в бесконечном цикле `app.exec()`.
- **Strict Database Restore Rules**:
  1. **Порядок PRAGMA перед заменой файлов**: В `DatabaseRestoreWorker._switch_journal_mode_for_restore` вызов `PRAGMA wal_checkpoint(TRUNCATE)` обязан выполняться строго **до** `PRAGMA journal_mode = DELETE` для гарантированного сброса страниц WAL в основной файл.
  2. **Диагностика блокирующих процессов**: При возникновении `WinError 32` на файлах базы или WAL `_get_locking_processes_info` опрашивает Windows Restart Manager (`rstrtmgr.dll`) и включает имена и PID блокирующих процессов в сообщение об ошибке.
  3. **Интерактивное разрешение конфликтов**: `DatabaseController` при перехвате ошибки с блокирующим процессом приложения (`python`, `aite`, `commander`) показывает диалог `confirm_terminate_locking_process`. При согласии пользователя конфликтующий процесс безопасно завершается, и восстановление автоматически повторяется с защитой от повторного зацикливания (`_restore_retry_count < 1`).
