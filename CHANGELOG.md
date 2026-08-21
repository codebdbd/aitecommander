# Changelog

All notable changes to **Aite Commander** will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

---

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
