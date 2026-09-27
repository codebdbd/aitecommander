# Changelog

All notable changes to **Aite Commander** will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Structure Share System & Safe Packaging (`.aitesec`, `.aitecat`, `.aitelink`)**:
  - Native export and import of structure packages for sections (`.aitesec`), categories (`.aitecat`), and individual links (`.aitelink`).
  - Packaging and automated extraction of associated workspace files (`workspace_files/`) with local path remapping.
  - Strict OOM & Zip Slip guards: 50 MB total uncompressed limit, 15 MB per-file limit, 1 MB manifest limit, and path normalization via `Path(name).name`.
  - Messenger sharing via Windows clipboard (`CF_HDROP`) for Telegram, WhatsApp, Viber, and Email.
- **Windows File Associations & SingleInstance IPC**:
  - Registered file associations for `.aitesec`, `.aitecat`, and `.aitelink` in `HKCU\Software\Classes` with dedicated `package_icon.ico` and Inno Setup integration.
  - SingleInstanceGuard local socket IPC protocol (`OPEN:<path>`) for opening packages in already-running instances without duplicate processes.
  - Positional CLI argument `[file]` support for importing packages on cold startup.
- **Interactive Name Conflict Resolution (`ImportConflictDialog`)**:
  - Unified dialog for resolving name collisions during `import`, `move`, and `copy` operations.
  - Three canonical strategies: `merge` (merge child items into existing container), `copy` (keep both with automatic unique suffix), and `cancel`.
  - Decoupled `conflict_resolver` callback contract isolating UI from core business services.
- **Unified Backup & Restore Bundle**:
  - Single portable `.zip` backup archive combining `database.db`, `manifest.json`, and referenced `icons/` extracted via `IconReferenceService`.
  - Isolated two-phase staging (`.restore_staging_{uuid}`) with SQLite integrity pre-verification and `.orig_bak` automatic rollback guard.
- **Empty Area Context Menus & Action Parity**:
  - Full context menu parity across all three workspace views: Structure Tree, Category Tiles, and Links Table.
  - Signal contract `contextMenuRequested(0, pos)` in `CategoryTiles` wiring to `CategoryMenuBuilder` empty area actions.
  - Blank area double-click entity creation (Section in Tree, Category in Tiles, Link in Table).
- **Unified Browser Profile Selection (`BrowserProfileDialog`)**:
  - Interactive profile selector supporting three distinct modes: Single Profile, Profile Rotation, and Batch Launch.
  - Live rotation order numbering (`1`, `2`, `3`...) inside indicators with dynamic count status (`Selected: N of M`).
  - Read-only profile preview field in `LinkDialog` with one-click clear button and direct selector trigger.
- **Informative Table Tooltips**:
  - Structured HTML card tooltip for the "Name" column with full title, un-squeezed path/URL, arguments, browser profile, and administrator execution status (`🛡️ Run as administrator`).
  - Contextual launcher card for the "Type" column detailing the action, domain/target, format, or character count.
- **macOS-style Quick Look Dialog (`Space`)**:
  - Instant preview for table items triggered by pressing `Space`.
  - Native PDF document viewer powered by `QtPdf` with multi-page navigation (`Page Up`, `Page Down`, `Home`, `End`) and interactive footer switcher (`◀ N / M ▶`).
  - Rich viewers for spreadsheets (`.xlsx`, `.xlsm`, `.csv`), Word documents (`.docx`), archives (`.zip`, `.jar`, `.whl`, `.apk`), markdown (`.md`), code/text, and images.
  - Universal zoom system with `Ctrl + Plus`, `Ctrl + Minus`, `Ctrl + 0`, and `Ctrl + MouseWheel`.
  - Fast "Show in Windows Explorer" shortcut (`Ctrl+E` / `Ctrl+У`) with non-blocking file selection.
  - Live keyboard navigation (`Up` / `Down`) through links while Quick Look stays open.
  - Fullscreen / maximize toggle via `F` or `F11` across all keyboard layouts.

### Improved
- **Icon Subsystem Modernization & Cache Integrity**:
  - Canonicalized favicon cache path to relative `icon_cache/favicon_cache.db`.
  - Implemented Cache Poisoning Guard preventing `isNull()` icons from being stored in memory or disk cache.
  - Isolated category cache namespace with `cat_{path}` prefix.
  - Multi-tiered LRU caching: 1024 items in links model, 512 pixmaps in `HighQualityTreeDelegate` with ID collision prevention.
  - Removed ~250 lines of dead QRC code and obsolete Qt classes (`QDir`, `QFile`) from `path_service.py`.
- **LinkDialog Geometry & Adaptive Sizing**:
  - Modern segmented link type container (`QFrame#linkTypeContainer`) with accent bottom border.
  - Single-stage content-driven adaptive window resizing via `layout().activate()` and `adjustSize()`.
  - Context-aware hierarchy row visibility and fixed-type window titles.
- **Theme Quality Gate**:
  - Automated WCAG 2.1 relative luminance and contrast ratio verification (>= 4.5:1) for bundled and imported ZIP/QSS themes via `python -m app.utils.theme_checker`.
- **Delicate Error Handling for Missing Files**:
  - Replaced loud system chimes with silent notifications and warning cards when files are moved or deleted.

### Fixed
- **Tree Category Drag & Drop Priority**:
  - Fixed internal vs external drop dispatch order in `DragDropHandler.handle_drop_event`.
  - Symmetrical UP/DOWN target row calculation and Qt `beginMoveRows` contract synchronization with `reorder_categories`.
- **Checkbox Indicator Contrast across 16 Themes**:
  - Implemented WCAG relative luminance standard (`lum = 0.299*R + 0.587*G + 0.114*B`) for custom checkbox indicators, eliminating invisible white marks on bright yellow, green, pink, and cyan backgrounds.
  - Dynamically tinted `check.svg` in `ThemeStylesheetService` to match theme indicator backgrounds (including high-contrast `#FFFFFF` for dark brown in `industrial_yellow`, and `#121212` for `matrix` and pastel light themes).
- **StructureTreeView Branch Indicator Alignment**:
  - Fixed vertical alignment of tree expansion arrows using canonical `QStyle.alignedRect` and `QIcon.paint` instead of manual coordinate math.


---

## [1.1.8] - 2026-09-08

### Fixed
- Fixed tree branch indicator (expansion toggle) vertical alignment on HiDPI displays (e.g. 125% scale).
- Centered branch toggle strictly along the row and folder icon axis using device-pixel-ratio aware sizing.
- Ensured COM STA initialisation when extracting Windows Shell file icons in background worker threads.
- Prevented default Qt file-type placeholders from being cached when system icons are available.

## [1.1.7] - 2026-09-07

### Fixed
- Fixed category drag and drop between sections in the structure tree view.
- Re-enabled drop indicator calculations while cleanly suppressing the default Qt drop line via proxy style.
- Allowed category drops onto cross-section targets and categories.
- Ensure target section child nodes are populated when moving categories into collapsed sections.

## [1.1.6] - 2026-09-06

### Fixed
- Restore sphere button icons on clean installations and when saved icons are missing.
- Complete missing Ukrainian translations in controllers, confirmations, dates, and the About dialog.
- Translate default sphere tooltips and the URL table hint.
- Add release regression checks for relocated bundled icons, translation coverage, compiled catalogs, and placeholders.

## [1.1.5] - 2026-08-21

### Fixed
- Uniform ComboBox row height across all dialogs.
- Updated installer to version 1.1.5.

### Added
- (No additional features in this release)


## [1.1.0] - 2026-08-11

### Fixed
- **PyInstaller Windowed Mode Crash (`sys.stderr is None`)**:
  - Redirected `sys.stdout` and `sys.stderr` to `os.devnull` when running in `--noconsole` mode to prevent runtime crashes when streams are accessed.
  - Safely wrapped `faulthandler.enable()` in a `try...except` block with a null check.
- **PyQt6 DLL Loading Failure (`ImportError: DLL load failed while importing QtCore`)**:
  - Registered `sys._MEIPASS` and `pywin32_system32` in Windows DLL search paths via `os.add_dll_directory()` upon frozen application initialization.
- **PyWin32 `win32ui` Import Crash**:
  - Made `win32ui` import safe with null checks and added automatic fallback to Qt `QFileIconProvider` when `win32ui` MFC runtime initialization fails in frozen builds.
- **PyWin32 Build Resolution**:
  - Resolved `pythoncom` and `pywintypes` import resolution issues during PyInstaller analysis.

### Added
- **Inno Setup Installer Support**:
  - Automated installer creation producing `AiteCommanderSetup-1.1.0.exe` in `dist/installer/`.

### Improved
- **Drag & Drop & Tree Management**:
  - Enhanced MIME data handling and link hierarchy tree updates.
  - Added fast link creation via drag and drop with immediate item insertion into the target category.
  - Improved move/update behavior so structure refresh and focus restoration work more reliably after edits.
- **UI & Custom Dialogs**:
  - Refined table widgets, bad URL cleanup dialog, browser profile dialogs, and language selector.
- **About dialog and localization**:
  - Replaced the legacy message box with a structured About dialog.
  - Added localized About resources for English, Ukrainian, Russian, French, Spanish, and German.
- **Icon handling**:
  - Added icon reset and reassignment flow for links.
  - Improved background icon parsing and fallback behavior for links, files, applications, sections, and categories.
  - Hardened icon cache/meta writes under concurrent updates on Windows.

---

## [1.0.0] - 2026-08-10

### Added
- Initial release of **Aite Commander**.
- Hierarchical 4-level link and category management (Sphere, Category, Subcategory, Link).
- Modern UI with 6 distinct themes (Dark, Light, Dreamy Room, Violet Pulse, Matrix, etc.).
- Multi-language support (English, Russian, etc.).
- Import/Export browser bookmarks and profiles.
- Integrated search and hotkey navigation.
