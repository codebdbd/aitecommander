# Build & Release Guide

## 1. Environment Setup

```bash
python -m venv .venv
.venv\Scripts\activate  # Windows
source .venv/bin/activate  # Linux/macOS

pip install --upgrade pip
pip install -r requirements-dev.txt
```

## 2. Run Tests & Linters

```bash
pytest

ruff check app tests
mypy app
```

All checks must pass before cutting a release.

## 3. Update Translations (when UI text changes)

```bash
pylupdate6 app --ts i18n/app_en.ts --ts i18n/app_ru.ts --ts i18n/app_uk.ts --ts i18n/app_fr.ts --ts i18n/app_es.ts --ts i18n/app_de.ts

# Translate new entries, then rebuild QM bundles
for lang in en ru uk fr es de; do
    pyrcc6 "i18n/app_${lang}.ts" -qm "i18n/app_${lang}.qm"
done
```

## 4. Development Run

```bash
python main.py
```

## 5. Packaging with PyInstaller

```bash
pip install pyinstaller
pyinstaller pyinstaller.spec
```

Artifacts appear in `dist/OsteenPath/`.  The spec bundles `app/resources/**` and
`i18n/*.qm`, so no additional manual steps are required.

## 6. Release Checklist

- [ ] `git status` is clean
- [ ] `pytest` passes
- [ ] Translations rebuilt (`i18n/app_*.qm`)
- [ ] Manual smoke-test (language switch, menus, toolbar, backup)
- [ ] Version metadata updated (`app_config`)

See [docs/PACKAGING.md](docs/PACKAGING.md) for platform-specific signing/publishing notes.
