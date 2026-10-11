# TOP BAR QA AUDIT

Pre-release аудит верхней панели приложения Aite Commander.
Аудит проводился статическим анализом кода + прогоном существующих тестов.

---

## 1. Verdict

**PASS WITH ISSUES**

Top Bar в целом работоспособен, покрыт snapshot/prefill механизмом для быстрого старта, использует централизованный FocusManager и UIStateManager для навигации. Найдено **1 BLOCKER**, **3 CRITICAL**, **6 MAJOR**, **4 MINOR**, **3 COSMETIC** дефекта. Блокер должен быть исправлен до релиза.

---

## 2. Реальный состав Top Bar

| Элемент | Класс / Метод | Сигнал | Обработчик | Изменяемое состояние | Зависимые UI |
|---|---|---|---|---|---|
| **Toggle Sidebar** | `StructureActionsToolbarAdapter._toggle_action` | `triggered` | `_on_toggle_left_panel → window.toggle_left_panel` | видимость left_panel | `window.left_panel`, SpheresBar, tree |
| **Back (Alt+←)** | `StructureActionsToolbarAdapter._back_action` | `triggered` | `_on_navigate_back → window.navigate_back` | `_history_index -= 1` в UIStateManager | stack, tree selection, current_category_id |
| **Forward (Alt+→)** | `StructureActionsToolbarAdapter._forward_action` | `triggered` | `_on_navigate_forward → window.navigate_forward` | `_history_index += 1` в UIStateManager | stack, tree selection |
| **Sep: structure/tools** | `ToolbarSeparatorController._sep_add_tools` | — | `_update()` | visibility: `add_block>0 & (tools|recent|fav)>0` | — |
| **Add Section** | `StructureActionsToolbarAdapter._sec_action` | `triggered` | `_on_add_section → window.show_section_dialog` | New Section dialog | Structure tree, undo_stack |
| **Add Category** | `StructureActionsToolbarAdapter._cat_action` | `triggered` | `_on_add_category → window.add_new_category` | New Category dialog | Structure tree, tiles, undo_stack |
| **Quick Add (dropdown)** | `QuickAddToolbarAdapter._main_action` (+ per-type sub-actions) | `triggered` | `_on_quick_add(ct) → actionRequested {"type":"quick_add","link_type":...} → links_actions.on_action_requested` | New Link dialog | Links table, undo_stack |
| **Sep: tools/recent** | `ToolbarSeparatorController._sep_tools_recent` | — | `_update()` | visibility: `tools>0 & (recent|fav)>0` | — |
| **Tools (dropdown)** | `ToolsToolbarAdapter._main_action` | InstantPopup | Menu rebuilds each theme change | — | File Search dialog, Import dialog, Bad URLs check, Icon Refresh dialog |
| - Search files | `_create_tools_menu._on_file_search` | `triggered` | `→ window.show_file_search_dialog` | FileSearch dialog open | — |
| - Import bookmarks | `_create_tools_menu._on_import_bookmarks` | `triggered` | `→ window.handle_import_browser_bookmarks` | Import flow | DB, structure |
| - Check links | `_create_tools_menu._on_check_bad_urls` | `triggered` | `→ system_dialogs.handle_check_bad_urls` | BadURLs dialog | — |
| - Refresh icons | `_create_tools_menu._on_refresh_icons` | `triggered` | `→ system_dialogs.handle_refresh_icons` | IconRefresh dialog | Table/tree icons |
| **Sep: recent/fav** | `ToolbarSeparatorController._sep_recent_fav` | — | `_update()` | visibility: `recent>0 & fav>0` | — |
| **Recent Links (popup)** | `RecentHistoryToolbarAdapter._main_action` | `triggered` (menu item) | `_on_link → actionRequested {"type":"open_link",...} → links_actions.on_action_requested` | Link launch, `last_opened_at` | DB, selection |
| **Favorites (inline + More popup)** | `LinksToolbarAdapter.set_data` | per-link `triggered` | `_on_link → actionRequested → links_actions.open_link` | Link launch; fav DB mark | Table scroll |
| - Fav context menu: Edit | `LinksToolbarAdapter._show_context_menu` | `triggered` | `actionRequested {"type":"edit_link"} → links_actions` | Edit dialog open | Undo stack |
| - Fav context menu: Remove | `LinksToolbarAdapter._show_context_menu` | `triggered` | `actionRequested {"type":"remove_favorite"} → links_actions` | DB `is_favorite=0` | Top panels refresh |
| - More button (folded) | `LinksToolbarAdapter._more_action` | popup | menu rebuild on each `set_data` | — | — |
| **Overflow (ext button)** | `TopBarToolBar._centre_ext_button` | QToolBar built-in | Icon: `get_menu_icon("more", theme)` | Auto-centering on Resize | — |
| **Responsive filter (fold favs)** | `_ResponsiveTopBarFilter.eventFilter` | Resize on host | `set_folded(bool)` based on `_calc_needed()` | `_is_folded`, More visibility | — |
| **Search Field** | `window.search` (QLineEdit) | `textChanged` | `on_search → _search_timer (300ms) → _execute_search → links_actions.on_search → links.business.search_links` | Table model (filter), `_pending_search`, empty query → reload current category | Table scroll, selection |
| **Light theme (rotation)** | `light_theme_action` | `triggered` | `theme_ctrl.rotate_light_theme` | settings `theme.name` + full UI refresh via `apply_and_refresh_ui` | QSS, all icons, menu, tree, panels |
| **Dark theme (rotation)** | `dark_theme_action` | `triggered` | `theme_ctrl.rotate_dark_theme` | settings `theme.name` | То же |
| **Settings dialog** | `settings_action` | `triggered` | `window.show_settings_dialog` | Settings dialog open | — |
| **Cut (Ctrl+X)** | `action_controller.cut_action` (WidgetShortcut) | `triggered` | `cut_current()` (dispatches by focus: text → tree → tiles → table) | `_clipboard_is_cut`, `_cut_item_ids`, visuals (tree/tiles) | Clipboard, DB (on paste) |
| **Copy (Ctrl+C)** | `action_controller.copy_action` (WidgetShortcut) | `triggered` | `copy_current()` (context dispatch) | Clipboard payload (MIME JSON) | — |
| **Paste (Ctrl+V)** | `action_controller.paste_action` (WidgetShortcut) | `triggered` | `paste_current()` (dispatch: text → tree → tiles → table → fallback links paste) | DB inserts, PasteCategoriesCmd/PasteSectionsCmd, Merge/Move commands (Cut) | Undo stack, tree, table |
| **Delete (Del)** | `action_controller.delete_action` (WindowShortcut!) | `triggered` | `delete_current()` (text delete tree selection → tiles selection → table with confirm) | DB deletes, DeleteSectionCmd/DeleteCategoryCmd/delete_links_with_confirmation | Undo stack, selection |
| **Select All (Ctrl+A)** | `action_controller.select_all_action` (WidgetShortcut) | `triggered` | `select_all_current()` (text→tree→tiles→table) | QItemSelection | — |
| **Undo (Ctrl+Z)** | `undo_stack.createUndoAction` / `window.undo_action` | `triggered` | `undo_current()` (text or `undo_stack.undo()`) | `QUndoStack.index-1` | All data/UI connected to UndoStack |
| **Redo (Ctrl+Y / Ctrl+Shift+Z)** | `undo_stack.createRedoAction` / `window.redo_action` | `triggered` | `redo_current()` (text or `undo_stack.redo()`) | `QUndoStack.index+1` | — |

---

## 3. Automated tests

| Metric | Value |
|---|---|
| Найдено тестов, связанных с Top Bar | 34 (в 8 файлах) |
| Запущено | 34 |
| Passed | 33 |
| **Failed** | **1** (test_topbar_builder_prefills_before_manager) |
| Skipped | 0 |
| Добавлено новых в этом прогоне | 0 |

**Файлы тестов:** `test_top_bar_layout_spacings.py`, `test_topbar_button_theming.py`, `test_startup_regression_guards.py`, `test_favorite_context_menu.py`, `test_theme_action_icon_refresh.py`, `test_tree_snapshot_icon_perf.py`, `test_monolithic_hover_and_geometry.py`, `test_runtime_config_smoke.py`.

**Что покрывают тесты:** stretch layout, ext button центрирование, icon fallback, rich tooltip, prefills before manager (сломан), cleanup/shutdown guards, favorite context menu signal flow, theme action icon refresh order, theme QSS injection, snapshot icon fast path.

**Критические пробелы в покрытии:**
- Нет ни одного теста на enabled/disabled логику Cut/Copy/Paste/Delete по focus/selection.
- Нет тестов на navigation history Back/Forward (новая ветка, удаленный объект).
- Нет тестов на search stale-result race condition и debounce.
- Нет тестов на Back/Forward setEnabled (всегда кликабельно — см. DEFECT TB-002).
- Нет тестов на быстрые двойные клики toolbar buttons (race condition для диалогов).
- Нет тестов на responsive folded state.
- Нет тестов на signal/slot single invocation (двойные connect).

---

## 4. Functional test matrix

Статическая оценка + существующие тесты:

| Element | Click | Shortcut | Enabled state | Focus dispatching | Selection reacts | Error resilience | Stress clicks | Result |
|---|---|---|---|---|---|---|---|---|
| Toggle sidebar | OK | — | OK (always) | — | — | OK | OK | PASS |
| Back | OK works | Alt+Left OK | **BROKEN** (always enabled, no setEnabled) | OK via UIStateManager | — | OK (no crash on empty) | Dbl-click: 2x navigate possible | FAIL |
| Forward | OK works | Alt+Right OK | **BROKEN** (always enabled) | OK | — | OK | Dbl-click: 2x navigate possible | FAIL |
| Add Section | OK opens dialog | — | OK (always, логично) | — | — | OK | Duplicate dialog OK? | WARN |
| Add Category | OK opens dialog | — | OK (always) | — | — | OK | Duplicate dialog OK? | WARN |
| Quick Add (dropdown) | OK per type | — | OK | — | — | OK (category_id=None handled) | Duplicate dialog OK? | WARN |
| Tools menu | OK opens popup | — | OK | — | — | OK | OK | PASS |
| - Search files | OK | — | OK | — | — | — | — | PASS |
| - Import bookmarks | OK | — | OK | — | — | No race guard | — | WARN |
| - Check links | OK | — | OK | — | — | — | — | PASS |
| - Refresh icons | OK | — | OK | — | — | — | — | PASS |
| Recent Links popup | OK opens + click launches | — | OK | — | — | OK | OK | PASS |
| Favorites inline | OK click launches | — | OK | — | — | OK | OK | PASS |
| Fav context menu: Edit/Remove | OK signal flow | — | — | — | — | OK on None data | — | PASS |
| Search | OK debounce 300ms | Ctrl+F? → **NO: нет биндинга** | OK | OK | OK empty→reload | **Stale result NO GUARD** | Type fast: debounce OK | FAIL |
| Light theme rotate | OK | — | OK | — | — | OK on bad settings | OK | PASS |
| Dark theme rotate | OK | — | OK | — | — | OK | OK | PASS |
| Settings dialog | OK opens | — | OK | — | — | — | Duplicate dialog OK? | WARN |
| Cut | OK by focus | Ctrl+X OK WidgetShortcut | OK (selection-based) | **Minor bug: else branch no paste enable** | OK tree/table/tiles | OK | Repeat paste after — | WARN |
| Copy | OK | Ctrl+C OK | OK | OK | OK | OK | — | PASS |
| Paste | OK | Ctrl+V OK | **Paste enable absent in no-focus fallback** | OK | — | Conflict resolution OK | — | WARN |
| Delete | OK | Del OK WindowShortcut | OK | OK | OK | With confirmation OK on empty | — | PASS |
| Select All | OK | Ctrl+A OK | OK (only on focused) | OK only focused types | OK tree/table/tiles | OK on 0 rows | — | PASS |
| Undo | OK | Ctrl+Z OK | **OK: QUndoStack manages via createUndoAction** | OK text vs stack | — | OK | — | PASS |
| Redo | OK | Ctrl+Y OK | **OK: QUndoStack manages** | OK | — | OK | — | PASS |

---

## 5. Defects

### TB-001 BLOCKER — Favorites Toolbar Adapter: `set_data` не удаляет старые QAction из toolbar при повторном вызове, memory leak + duplicate buttons

**Severity:** BLOCKER
**Элемент:** Favorites toolbar (LinksToolbarAdapter)
**Файл:** [toolbar_adapters.py](file:///d:/01_Codebdbd/01_projects/aitecommander/app/views/main_components/ui/topbar/toolbar_adapters.py#L895-L944)
**Метод:** `LinksToolbarAdapter.set_data`

**Условия:** Любой повторный вызов `set_data()` (TopPanelsController refresh, theme change, data updated from DB).

**Шаги:**
1. Запустить приложение с непустыми избранными.
2. Дождаться snapshot-префилла (1st set_data).
3. Дождаться живого refresh от TopPanelsController (2nd set_data).
4. Переключить тему (3rd set_data).
5. Открыть Qt Inspector или посчитать `len(toolbar.actions())`.

**ФР:** В методе `set_data`:
```python
for act in self._link_actions:
    try:
        self._toolbar.removeAction(act)
        act.deleteLater()
```
Удаляется только `_link_actions`. Но `_add_action()` каждую иконку также добавляет в `self._actions` (ToolbarActionAdapter L284-285):
```python
self._actions.append(action)
```
При повторном `set_data()` **`self._actions` не очищается от старых link-actions** (только `_link_actions` пересоздается). Каждый `add_action` добавляет еще action в `self._actions`, а `_mark_last_button`/`_update_global_last_button` и `ToolbarSeparatorController` считают count не по `_link_actions`, а по `_actions`.

Итог: after N refreshes → `_actions` содержит `N*M` actions вместо `M` → O(N) утечка QAction/QToolButton, неправильный `_separator_controller.set_group_count("fav", count)`.

**ОР:** `set_data` должен перед добавлением новых элементов чищать И `_link_actions`, И старые действия из `_actions` (кроме `_more_action`).

**Причина:** `clear_actions()` не вызывается; частичное удаление только `_link_actions`.

**Исправление:** В начале `set_data`:
- для каждого `a` в `_link_actions`: `a in self._actions` → remove, deleteLater, pop из `_actions`;
- либо переиспользовать `clear_actions()` с сохранением `_more_action`.

**Regression test:** `set_data(3 items); set_data(5 items); assert len(adapter.actions) == N (with more button only when folded)`.

---

### TB-002 CRITICAL — Back/Forward buttons никогда не вызывают setEnabled, кликабельны даже при пустой истории; Alt+Left/Right исполняют лишний раз без guards

**Severity:** CRITICAL
**Элемент:** Back, Forward toolbar buttons
**Файл:** [toolbar_adapters.py](file:///d:/01_Codebdbd/01_projects/aitecommander/app/views/main_components/ui/topbar/toolbar_adapters.py#L544-L573)
**Метод:** `StructureActionsToolbarAdapter.update_navigation_state`

**Условия:** Любой запуск приложения, navigation state empty (first position, forward exhausted).

**Шаги:**
1. Новый запуск, категорий еще не переходили (history_index=-1).
2. Кликнуть Back кнопку в Top Bar.
3. Нажать Alt+Left.

**ФР:** `update_navigation_state` обновляет только `tooltip` и `setProperty("nav_available","false")` для QSS, но **не вызывает `self._back_action.setEnabled(can_back)`**. Бизнес-метод `navigate_back()` вернет False, но:
- кнопка визуально не disabled (только кастомный QSS по nav_available, если он описан);
- shortcut Alt+Left исполняет `_on_navigate_back → UIStateManager.navigate_back` без какого-либо pre-check guard вне функции; функция вернет False без видимого feedback, но вызов `can_navigate_back()` не защищен от параллельных состояний.
- быстрый двойной клик → 2 вызова подряд → index может уйти ниже 0 при гонке (маловероятно, но возможно при одновременном обновлении).

**ОР:** `self._back_action.setEnabled(can_back)` и то же для Forward. Shortcut должен отрабатывать только при enabled.

**Причина:** Забыт вызов `setEnabled` в `update_navigation_state`.

**Исправление:** В `update_navigation_state` добавить:
```python
self._back_action.setEnabled(bool(can_back))
self._forward_action.setEnabled(bool(can_forward))
```

**Regression test:** `adapter.update_navigation_state(False, False); assert not adapter._back_action.isEnabled() и not adapter._forward_action.isEnabled()`.

---

### TB-003 CRITICAL — Search: отсутствует stale-result guard; старый медленный асинхронный search перепишет более новый результат

**Severity:** CRITICAL
**Элемент:** Search field + business.search_links
**Файл:** [main_window.py](file:///d:/01_Codebdbd/01_projects/aitecommander/app/views/windows/main_window.py#L1183-L1195)
**Методы:** `on_search`, `_execute_search`; [controller.py](file:///d:/01_Codebdbd/01_projects/aitecommander/app/controllers/ui/links/controller.py#L125-L131)

**Условия:** Медленная БД, много записей. Быстрый ввод: "abc" → стираем → "xy".

**Шаги:**
1. В поиске быстро ввести "longquerythattriggersslowsearch".
2. В течение debounce + 100ms стереть и ввести "short".
3. Подождать завершения обоих запросов.

**ФР:** Debounce 300ms только откладывает запуск, но не защищает от порядка завершения. `links.business.search_links(text)` не имеет version/token. Если query A завершится позже query B, таблица будет в состоянии A, а текст поиска "short" (B) → несоответствие UI и результата.

**ОР:** Каждый вызов search_links должен инкрементировать `_search_generation`; callback (или signal) проверяет перед применением результата `generation == current_generation`.

**Причина:** Отсутствует query-versioning в search pipeline.

**Исправление:** generation/token counter в LinksController + business.

**Regression test:** Запустить два поиска с mock delays, убедиться что старый результат отбрасывается.

---

### TB-004 CRITICAL — StructureActionsToolbarAdapter navigation ShortcutContext `WidgetShortcut` + back/forward always-enabled → Alt+Left/Right может сработать во время открытого модального диалога и сломать состояние

**Severity:** CRITICAL
**Элемент:** Back/Forward shortcuts
**Файл:** [toolbar_adapters.py](file:///d:/01_Codebdbd/01_projects/aitecommander/app/views/main_components/ui/topbar/toolbar_adapters.py#L477-L505)

**Условия:** Открыт модальный диалог (Add Category, Settings, Edit Link) в главном окне.

**ФР:** Shortcut `Alt+Left` установлен как `back_action.setShortcut("Alt+Left")` с **дефолтным ShortcutContext = WidgetShortcut**. Т.к. back_action родитель toolbar (TopBarToolBar), а он дочерний main_window — при открытом QDialog (child of main_window) shortcut все равно срабатывает, и происходит `navigate_back()` в фоне пока диалог висит на экране. По закрытии диалога пользователь видит не ту категорию, в которой открывал редактирование.

**ОР:** Для navigation-actions ShortcutContext должен быть `WindowShortcut` с check `window.isActiveWindow()` — тогда при модальном QDialog как отдельном window-level виджете стандартно shortcut не должен триггериться, либо нужен явный guard на `QApplication.activeModalWidget()`.

**Причина:** Default ShortcutContext не переопределен; нет проверки на modal.

**Исправление:**
```python
back_action.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
# или guard в _on_navigate_back:
if QApplication.activeModalWidget() is not None: return
```

---

### TB-005 MAJOR — `ToolbarSeparatorController` неправильно включает separator `sep_add_tools` когда есть только navigation/toggle (без реальных add-действий)

**Severity:** MAJOR (UI grouping, visual regression risk)
**Файл:** [toolbar_adapters.py](file:///d:/01_Codebdbd/01_projects/aitecommander/app/views/main_components/ui/topbar/toolbar_adapters.py#L177-L190)
**Метод:** `ToolbarSeparatorController._update`

**ФР:** `add_block = structure + quick`. `structure` считает count всех не-separator actions StructureActionsToolbarAdapter: toggle sidebar + back + forward + add_section + add_category = 5. Даже если quick=0 и tools=0, а только `fav>0` и `recent>0`, то `sep_add_tools.setVisible(5+0>0 and (0|>0)) → True`. Получаем separator между navigation и recent/fav, когда он не несет никакой смысловой нагрузки (нет add-действий справа).

**ОР:** Separator должен группировать "add-like block" (add_section, add_category, quick_add) против "utilities" (tools/recent/fav). Navigation/toggle — отдельная группа.

**Исправление:** Разделить count: `navigation_and_views` (toggle/back/forward) отдельно от `structure_actions` (add_sec/add_cat). И тогда `add_block = structure_add_count + quick_count`.

---

### TB-006 MAJOR — ActionController: нет `paste_enabled=true` в безфокусной ветке `else` когда есть tree/table selection; paste через Top Bar может работать некорректно

**Severity:** MAJOR
**Файл:** [action_controller.py](file:///d:/01_Codebdbd/01_projects/aitecommander/app/controllers/ui/action_controller.py#L1299-L1310)
**Метод:** `update_action_states`

**ФР:**
```python
else:
    if tree_has_selection:
        selection_type = ...
        can_copy = bool(selection_type)
        can_cut  = bool(selection_type)
        can_delete = bool(selection_type)
        # can_paste — НЕ ОПРЕДЕЛЕНО! остается значение с предыдущей ветки:
        # widget is not None => can_paste=True was set for text widget
```
Если `widget` был не None (фокус в LineEdit somewhere?), потом фокус ушел в никуда (или пустой widget), но при этом есть `tree_has_selection` — значение `can_paste` останется как от предыдущей итерации (где-то `True`/`False` случайно). Состояние кнопки Paste не детерминировано.

**Исправление:** В else-ветке явно пересчитать `can_paste`:
```python
svc = self._get_structure_context_service()
can_paste = bool(svc and (svc.clipboard_has_pastable_category() or svc.clipboard_has_pastable_section()))
```

---

### TB-007 MAJOR — Favorites context menu (Link context) использует обычный `QMenu`, не `TopBarMenu`: нет выравнивания border, нет `menu_active` property; визуальное несовпадение с Quick/Tools/Recent

**Severity:** MAJOR (визуал, QSS несогласованность)
**Файл:** [toolbar_adapters.py](file:///d:/01_Codebdbd/01_projects/aitecommander/app/views/main_components/ui/topbar/toolbar_adapters.py#L945-L974)
**Метод:** `LinksToolbarAdapter._show_context_menu`

**ФР:** `menu = QMenu(self._toolbar)` вместо `TopBarMenu`. Потому нет:
- `set_target_button` → нет `menu_active=true` property на кнопке → нет accent-рамки как у других меню;
- нет `showEvent` выравнивания позиции по нижней границе кнопки → может прыгать в произвольное место (хотя позиция передается явно через `QPoint(mapToGlobal)`);
- нет `hideEvent` restore hover icon.

**Исправление:** Использовать `TopBarMenu(self._toolbar)` и `menu.set_target_button(button)` перед `exec`.

---

### TB-008 MAJOR — `_ResponsiveTopBarFilter` объявлен локально внутри top_bar_setup.py (внутренний класс модуля). Невозможно unit-testить отдельно, отсутствует type-hint, нет протокола. Согласно project_memory это антипаттерн.

**Severity:** MAJOR (quality/supportability)
**Файл:** [top_bar_setup.py](file:///d:/01_Codebdbd/01_projects/aitecommander/app/views/main_components/ui/topbar/top_bar_setup.py#L119-L166)

**Исправление:** Вынести в отдельный модуль `app/views/main_components/ui/topbar/responsive_filter.py`, покрыть тестами width thresholds.

---

### TB-009 MAJOR — `_mark_last_button` в ToolbarActionAdapter все еще O(N) цикл вместо O(1); lessons learned нарушен

**Severity:** MAJOR (perf regression на больших fav панелях + много раз на theme change)
**Файл:** [toolbar_adapters.py](file:///d:/01_Codebdbd/01_projects/aitecommander/app/views/main_components/ui/topbar/toolbar_adapters.py#L364-L376)
**Метод:** `ToolbarActionAdapter._mark_last_button`

**ФР:**
```python
def _mark_last_button(self) -> None:
    ...
    new_last = self._buttons[-1]
    previous_last = self._last_marked_button
    if previous_last is new_last: return
    if previous_last is not None and previous_last in self._buttons:
        self._set_button_last(previous_last, False)
    for button in self._buttons[:-1]:   # ← O(N) цикл ВСЕГДА!
        self._set_button_last(button, False)
    self._set_button_last(new_last, True)
```
При `_buttons[:-1]` все N-1 кнопок получают unpolish/polish. На 16 favorites + theme change/refresh это 15 лишних `style().unpolish()`/`polish()` и `update()`.

**Исправление:** Только previous_last и new_last:
```python
if previous_last is not None and previous_last is not new_last:
    self._set_button_last(previous_last, False)
if new_last is not None:
    self._set_button_last(new_last, True)
self._last_marked_button = new_last
```

---

### TB-010 MAJOR — action_controller: Delete имеет ShortcutContext=WindowShortcut, а Cut/Copy/Paste — WidgetShortcut. При фокусе в search поле QLineEdit Delete может удалить selected link вместо символа в поиске

**Severity:** MAJOR (data loss risk)
**Файл:** [action_controller.py](file:///d:/01_Codebdbd/01_projects/aitecommander/app/controllers/ui/action_controller.py#L160-L169)
**Метод:** `_configure_action`

**Условия:** User выделил link в таблице, потом кликнул в search и выделил текст мышкой (но фокус ушел из таблицы? Нет — фокус у search).

**ФР (анализ кода):** `delete_current()` первой строчкой проверяет `widget = self._get_text_widget()` и если QLineEdit с selection — выполняет `_delete_text_selection(widget)`. Логика правильная, **НО**: Delete shortcut имеет `WindowShortcut` — при фокусе в QDialog'овом поле ввода (например, Edit Link dialog, Name поле) Del нажатие удалит символ в поле (т.к. `_get_text_widget` найдет focus), **НО ОДНОВРЕМЕННО** может сработать delete link через WindowShortcut, если handler диалога не имеет явного ShortcutOverride? Нет — QDialog принимает WindowShortcut только если он дочерний, обычно нет. Но есть сценарий: search активен, фокус в search, Delete shortcut (WindowShortcut) триггерится ОДНОВРЕМЕННО с дефолтным keyPressEvent QLineEdit (del_). В Qt это обычно не происходит, но поведение не детерминировано для всех платформ.

**Исправление:** Для consistency установить Delete тоже WidgetShortcut или добавить `Qt.ShortcutContext.WidgetWithChildrenShortcut` — тогда Delete для search будет обрабатываться через `_delete_text_selection` той же функцией. В противном случае — нет, WindowShortcut для Delete нужен именно для "безфокусной ветки". Лучше оставить так, но добавить проверку priority: если `widget is not None` то shortcut всегда обрабатывается первым. Сейчас код в delete_current это делает — OK. Уровень дефекта MAJOR, потому что несогласованность shortcut context между edit-операциями источник future bugs.

---

### TB-011 MINOR — `action_controller._configure_action`: дублирование lambda-тел для delete vs остальных

**Severity:** MINOR (dead code path)
**Файл:** [action_controller.py](file:///d:/01_Codebdbd/01_projects/aitecommander/app/controllers/ui/action_controller.py#L166-L169)

```python
if shortcut_id == "global.delete":
    action.triggered.connect(lambda _checked=False: handler())
else:
    action.triggered.connect(lambda _checked=False: handler())
```
Тела веток **идентичны**. if/else не имеет смысла.

**Исправление:** Убрать ветвление, оставить один `.connect()`.

---

### TB-012 MINOR — `ThemeController._perform_ui_updates` — три копипастных блока light/dark/settings кнопок с идентичной логикой

**Severity:** MINOR (maintainability, risk of typo in one of three leading to broken icon)
**Файл:** [theme_controller.py](file:///d:/01_Codebdbd/01_projects/aitecommander/app/controllers/ui/theme_controller.py#L582-L637)

Вынести в helper: `_reload_theme_button(mw, "light", "light.svg", "light_theme_button", "light_theme_action")`.

---

### TB-013 MINOR — Navigation history хранит только category_id, не валидирует на "существует ли эта категория сейчас" (удалена, импортирована); при навигации обратно в удаленную категорию упадет switch_sphere или restore_category_selection

**Severity:** MINOR (требует ручной операции — удалить категорию, нажать Back)
**Файл:** [ui_state_manager.py](file:///d:/01_Codebdbd/01_projects/aitecommander/app/controllers/ui/state/ui_state_manager.py#L242-L277)
**Метод:** `_navigate_to_history_category`

Исправление: перед `get_category_hierarchy` сделать existence check и при отсутствии — выпрыгнуть invalidated из истории.

---

### TB-014 MINOR — Сломан regression test `test_topbar_builder_prefills_before_manager`: ConfigStub не определяет `get_topbar_separator_spacing`

**Severity:** MINOR (test failure; build CI)
**Файл:** [test_startup_regression_guards.py](file:///d:/01_Codebdbd/01_projects/aitecommander/tests/test_startup_regression_guards.py) строка ~258

Шаги воспроизведения: `pytest tests/test_startup_regression_guards.py::test_topbar_builder_prefills_before_manager`

ФР:
```
AttributeError: 'ConfigStub' object has no attribute 'get_topbar_separator_spacing'.
Did you mean: 'get_top_bar_buttons_spacing'?
```

ОР: Stub должен отражать текущий runtime app_config.ui API.

Исправление: Добавить методы `get_topbar_separator_spacing()` возвращающий int (например 4).

---

### TB-015 COSMETIC — Quick Add dropdown и Tools dropdown не выделяют separator через setProperty/setObjectName для unified theme matrix

**Severity:** COSMETIC

ToolsToolbarAdapter separator (item `(None, None, None, None)` в tools_items list) создает обычный `menu.addSeparator()` без explicit objectName/class property. При theme matrix, где separator в TopBarMenu может иметь токены ширины/цвета — они не применятся.

Исправление: получать separator action и `act.setProperty("class", "topbar_menu_separator")` после `menu.addSeparator()`.

---

### TB-016 COSMETIC — `TopBarToolBar._centre_ext_button`: свойство `toolbar_btn` и cursor ставятся только при первом `_centre_ext_button` вызове; если кнопка пересоздается QToolBar внутренне, свойство теряется.

**Severity:** COSMETIC

Исправление: Не guard on `if not btn.property("toolbar_btn")` — всегда переустанавливать, либо connect to toolbar layoutChanged.

---

### TB-017 COSMETIC — `LinksToolbarAdapter.set_data`: count для `ToolbarSeparatorController` считает `1 if folded else len(_link_actions)`. Но если folded=True и items пустой список — count=0, но `_apply_fold_visibility` устанавливает `_more_action.setVisible(False)` — неконсистентность подсчета separator (не страшно, separator скроется).

---

## 6. Focus / Selection problems

### FOC-001 (связан с TB-004) — Alt+Left во время модального диалога сломает navigation

**Условие:** focus — QLineEdit внутри Edit Link dialog (модальный).
- Back-action shortcut: WidgetShortcut по умолчанию.
- Т.к. диалог parent'ом имеет main_window, shortcut виден.
- `UIStateManager.navigate_back` выполняется синхронно пока диалог висит.
- Диалог содержит "link data loaded from old category id". Close dialog → user в другой категории. Ссылка может уже не принадлежать новой категории (если был merge). Риск: `edit_selected_link()` редактирует не тот объект.

### FOC-002 (связан с TB-006) — Paste disabled в no-focus fallback

Если `QApplication.focusWidget()` возвращает None (пользователь кликнул в свободную область, но визуально selection в таблице есть), то `update_action_states` идет в else-ветку:
- `tree_has_selection` → `can_paste` не пересчитывается → остается старое значение (random garbage от предыдущего состояния).
- Cut/Copy/Delete → OK, they are set from selection.
- Paste button может оказаться disabled, хотя data в буфере есть и paste был бы валиден.

### SEL-001 — `ActionController._table_has_selection` использует `links_actions.get_selected_rows()` (скорее всего rows-based). Тест кейс из аудита п.5: `selectedRows()` пустой, но `selectedIndexes()` выбранные ячейки есть. Focus и selection не синхронизированы для partial cell selection.

Нужно проверить сигнатуру `get_selected_rows()`. Если только whole-row selection mode — нет проблем. Если можно выбрать отдельную ячейку — `_table_has_selection` вернет False, а data реально выделена. Delete/Copy/Cut через toolbar будут disabled, хотя работают через контекстное меню.

---

## 7. Navigation problems

### NAV-001 (TB-002) — Back/Forward never disabled

### NAV-002 (TB-004) — shortcut triggers in modal dialogs

### NAV-003 (TB-013) — no category existence validation in history

### NAV-004 — Forward-stack truncation не тестирован
Пользовательский сценарий: A → B → C → D, затем Back×2 (D→C→B), затем перейти в X. Forward стек должен быть обрезан: [A,B,X], _history_index=2, can_forward=False.

Код: `UIStateManager._record_history` (L203-213):
```python
self._history = self._history[: self._history_index + 1]
self._history.append(category_id)
```
КОРРЕКТНО. Обрезка работает. Но нет теста. Добавить regression test.

### NAV-005 — Navigation history НЕ записывает sphere/section переходы. Переход: SectionA (tiles view) → SectionB (tiles view) → Back не работает, т.к. history только for categories.

Аудит п.6 требует "переход Sphere → Section → Category". В текущей реализации history хранит только `list[int]` category_id. Переключение на tiles-view для section не трогает историю.

Это design limitation, но стоит отметить как missing feature для scope Top Bar "Back to section list".

---

## 8. Signal / Slot problems

### SIG-001 (TB-001) — LinksToolbarAdapter set_data накапливает actions в self._actions, что приводит к росту списка и потенциально к множественному вызову triggered если сигналы не disconnectятся. В коде L925 `action.triggered.connect(lambda...)` — новая лямбда, старый action удаляется через deleteLater → сигнал отключается при уничтожении QObject, так что double-signal не произойдет, но растущий список `self._actions` → `_mark_last_button`/`_update_global_last_button` O(N) будет работать с устаревшими удаленными actions.

### SIG-002 — `MainMenuBuilder.create_undo_redo_actions` + `ActionController.setup_global_actions` + `ActionController._wire_undo_redo_actions` + `_discard_undo_redo_actions` могут создать двойное подключение для undo/redo.

Код `action_controller._wire_undo_redo_actions` L224-242 всегда делает `disconnect()` перед новым connect → OK. Нет double wiring.

### SIG-003 — TopPanelsController: `favorite_links_loaded`, `link_updated`, `link_deleted`, `items_batch_deleted`, `batch_updated` все подключены в `_connect_business_signals` ОДИН раз. cleanup правильно отключает. OK.

### SIG-004 — `window_ui_setup._on_language_changed` вызывает `adapter.refresh_actions()` для всех 5 адаптеров при смене языка. Ни один из адаптеров `refresh_actions()` **не переподключает triggered lambda с новым translated text** — потому что tooltip и text у QAction обновляются locale-автоматически через translate? QuickAdd `_build_quick_actions` вызывается только при отсутствии `_main_action`. НО: `main_action.setText(self.tr("Add Link"))` при смене языка не вызывается (т.к. `refresh_actions` только иконку обновляет).

Проблема: после retranslate toolbar dropdown у Quick/Tools (InstantPopup) показывает старые названия в buttons/menu items! Tools menu пересоздается полностью в refresh_actions → OK. Quick Add dropdown: `refresh_actions` только иконку обновляет L753-769, menu items не трогает! → **после смены языка Quick dropdown items stale untranslated**.

**Добавить дефект TB-018 MINOR.**

---

## 9. UI / Theme / i18n problems

### TB-018 MINOR (SIG-004) — Quick add dropdown menu items не retranslate при смене языка
`QuickAddToolbarAdapter.refresh_actions()` только меняет иконку `_main_action`. Sub-actions (file/folder/web/script/...) в меню были созданы со старым `label = tooltips.get(code, tooltip) or code` в `_build_quick_actions`, и при language_changed они остаются старыми.

Исправление: в `refresh_actions` перебить sub-action texts/tooltips через `QCoreApplication.translate` + dynamic re-read from settings.

### THEME-001 — Theme change rebuilds ToolsToolbarAdapter menu (L632-636) deleting old `old_menu.deleteLater()`. Если пользователь в момент смены темы держит меню открытым → menu удаляется через deleteLater + может быть сигнал segfault wrapped C/C++ object. Нет guard "если меню сейчас открыто/видимо — отложить".

### THEME-002 — StructureActionsToolbarAdapter.refresh_actions обновляет иконку toggle sidebar по `left_panel_close`, а в _build_actions тоже `left_panel_close`. Никогда не переключается на `left_panel_open` когда панель скрыта! Single icon state.

---

## 10. Regression risks

1. **Исправление TB-001 set_data** — риск потерять `_more_action` если не сохранить. Покрыть тестом.
2. **TB-002 setEnabled Back/Forward** + ShortcutContext — может сломать существующие shortcut если пользователь использовал Alt+Left в кастомных сценариях ShortcutOverride для редакторов.
3. **TB-003 search versioning** — высокая вероятность гонки если добавить generation наружу, не обновив все signal paths.
4. **TB-009 _mark_last_button O(1)** — риск остаться `toolbar_last=true` на двух кнопках одновременно при редком сценарии (например, когда _last_marked_button был вне `_buttons`).
5. **Theme change path** — любое добавление нового адаптера требует ручного добавления `refresh_actions` в 3 места: `_on_language_changed`, `_perform_ui_updates`, `main_menu_builder.update_theme`. Очень легко забыть → icon stale после theme/language change.
6. **Favorites responsive folded** — при изменении формулы `_calc_needed` легко сломать, нет ни одного теста на folding thresholds.

---

## 11. Release blockers

### TB-001 BLOCKER
LinksToolbarAdapter `set_data` leak + growing `_actions`. Любая операция refresh/theme/data change → toolbar растет → memory leak + incorrect separator counts. Должен быть исправлен **до релиза**.

### TB-002 CRITICAL
Back/Forward никогда не disabled. Пользователь не видит, когда навигация недоступна. QA не пропустит.

### TB-003 CRITICAL
Stale search result → пользователь видит данные не соответствующие строке поиска. Неприемлемо.

### TB-004 CRITICAL
Navigation shortcut срабатывает в модальном диалоге → data corruption risk при edit/delete другой категории.

---

## 12. Final recommendation

### TOP BAR READY FOR RELEASE: **NO**

До релиза необходимо исправить **1 BLOCKER (TB-001)** и **3 CRITICAL (TB-002, TB-003, TB-004)**.

Порядок приоритета:
1. TB-001 (favorites toolbar leak) — regression tests.
2. TB-002 (setEnabled back/forward) + ShortcutContext Window guard.
3. TB-003 (search versioning / generation token).
4. TB-004 (modal dialog check for shortcuts).

После исправления 4х дефектов — запустить full test suite повторно и добавить regression tests для NAV-004 (forward truncation) и FOC-002 (paste no-focus).

MAJOR дефекты (5—10) исправить в патч-релиз 0.x.1 в течение первой недели после rollout.
