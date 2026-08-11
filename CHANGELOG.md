# Changelog

All notable changes to **Aite Commander** will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

---

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
- **UI & Custom Dialogs**:
  - Refined table widgets, bad URL cleanup dialog, browser profile dialogs, and language selector.
- **About dialog and localization**:
  - Replaced the legacy message box with a structured About dialog.
  - Added localized About resources for English, Ukrainian, Russian, French, Spanish, and German.

---

## [1.0.0] - 2026-08-10

### Added
- Initial release of **Aite Commander**.
- Hierarchical 4-level link and category management (Sphere, Category, Subcategory, Link).
- Modern UI with 6 distinct themes (Dark, Light, Dreamy Room, Violet Pulse, Matrix, etc.).
- Multi-language support (English, Russian, etc.).
- Import/Export browser bookmarks and profiles.
- Integrated search and hotkey navigation.
