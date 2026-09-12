# Aite Commander

Hierarchical bookmark and link manager for Windows. Organize your web links, files, programs, and scripts in a 4-level structure: **Sphere > Section > Category > Link**.

## Features

- **4-level hierarchy** — Spheres, Sections, Categories, Links with drag & drop reordering
- **5 link types** — Web, File, Folder, Program, Script
- **Favorites & Recents** — Quick-access panels in the top bar
- **Full-text search** — Search by name, URL, notes, and arguments
- **Undo/Redo** — Full undo stack for all operations
- **Drag & Drop** — Move items between categories and reorder within the tree
- **6 themes** — Light, Dark, Dreamy Room, Matrix, Violet Pulse, and more bundled presets
- **6 languages** — English, Ukrainian, Russian, French, Spanish, German
- **40+ keyboard shortcuts** — Fully customizable hotkeys
- **Browser import** — Import bookmarks from Chrome, Edge, Firefox HTML exports
- **Social sharing** — Share links via Telegram, X, Facebook, LinkedIn, WhatsApp, Email
- **Favicon auto-fetch** — Background icon downloading for web links
- **Bad URL checking** — Detect and remove unreachable links
- **Database backup/restore** — Automatic backups with configurable limits
- **Import/Export** — Full structure, section-level, or category-level as ZIP archives
- **HiDPI support** — High DPI scaling

## Requirements

- Windows 10/11
- Python 3.12+

## Installation

```powershell
# Clone the repository
git clone https://github.com/codebdbd/aitecommander.git
cd aitecommander

# Create an isolated Python 3.12 environment
py -3.12 -m venv .venv

# Install dependencies using the project's interpreter
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Use the project's interpreter explicitly to avoid installing or running in another
environment on `PATH`. If you use uv, `uv sync --locked` creates and synchronizes
`.venv` from `uv.lock`; add `--extra dev` to include development tools.

## Running

```powershell
.\.venv\Scripts\python.exe -m app.main
```

Or run `.\.venv\Scripts\python.exe main.py`, or double-click `aitecommander.bat`.

### Command-line options

| Option | Description |
|--------|-------------|
| `--debug` | Enable debug mode |
| `--log-level LEVEL` | Set log level (DEBUG, INFO, WARNING, ERROR) |
| `--no-gui` | Run without graphical interface |
| `--version` | Show version and exit |

## Building from source

```bash
# Install build tools
pip install hatchling

# Build package
python -m build
```

## Building the Windows installer

Install [Inno Setup 6](https://jrsoftware.org/isinfo.php), then build the PyInstaller
application folder and compile the installer:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_installer.ps1
```

If `dist\AiteCommander` already exists, skip the PyInstaller step:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_installer.ps1 -SkipPyInstaller
```

The installer is written to `dist\installer\AiteCommander-Setup-1.1.6.exe`.

Pushing a release tag such as `v1.1.6` also triggers the GitHub Actions workflow in
`.github/workflows/release.yml`, which runs tests, builds the Windows installer, and
uploads the generated `.exe` to the corresponding GitHub Release.

## Development

```powershell
# Install dev dependencies
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"

# Run linter
.\.venv\Scripts\python.exe -m ruff check app/

# Run formatter
.\.venv\Scripts\python.exe -m ruff format app/

# Run type checker
.\.venv\Scripts\python.exe -m mypy app/

# Run tests
.\.venv\Scripts\python.exe -m pytest
```

## Project structure

```
aitecommander/
├── app/
│   ├── core/           # Database, logging, settings, error handling
│   ├── controllers/    # Business logic, UI controllers, undo/redo
│   ├── models/         # Entities, managers, migrations, workers
│   ├── views/          # Windows, widgets, dialogs, tree/table models
│   ├── services/       # Theme, share, bulk operations, structure
│   ├── utils/          # Browser import, icons, drag & drop, validators
│   ├── resources/      # Themes (QSS), icons, logos
│   ├── startup/        # App initialization, argument parsing
│   └── config_data/    # Configuration payload and adapters
├── i18n/               # Translation files (.ts/.qm)
├── scripts/            # Utility scripts
├── tests/              # Test suite
└── pyproject.toml      # Project metadata and build config
```

## License

[MIT](LICENSE)
