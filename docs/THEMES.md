# Additional Themes

This document describes how additional themes work in Aite Commander and how to create a theme package that the program can actually import.

## How theme installation works

The program supports two theme sources:

- bundled themes shipped with the app in `app/resources/themes`
- user themes installed into `%APPDATA%/Codebdbd/Aite Commander/themes`

Theme installation in the UI is implemented by:

- `ThemeImportService` for import, validation, overwrite/rename handling
- `ThemeRegistry` for discovery of bundled and user themes
- `ThemeController` for applying the selected theme
- `ThemeStylesheetService` for loading `common.qss` plus the selected theme QSS

In Settings, the user can:

- import a theme package from a `.zip`
- open the themes folder
- remove only user-installed themes

Manual installation also works: if a valid theme folder is copied into the user themes directory, it will be discovered after theme refresh/restart.

## Where user themes are stored

Default user themes directory:

```text
%APPDATA%/Codebdbd/Aite Commander/themes
```

Example on Windows:

```text
C:\Users\<user>\AppData\Roaming\Codebdbd\Aite Commander\themes
```

## Required package structure

The imported package root must contain `theme.json`.

Recommended structure:

```text
my-theme/
  theme.json
  qss/
    my-theme.qss
  icons/
    add_bd.svg
    add_category.svg
    ...
  preview.png            # optional
  README.md              # optional
```

The package may be imported:

- as a `.zip`
- as a folder copied manually into the user themes directory

If a zip contains one top-level folder, the importer uses that folder as the theme root. If the zip contains files directly at the root, that root is used.

## `theme.json` format

Minimal valid manifest:

```json
{
  "id": "my-theme",
  "name": "My Theme",
  "version": "1.0.0",
  "is_dark": true,
  "qss": "qss/my-theme.qss",
  "icons_dir": "icons",
  "preview": "preview.png"
}
```

Fields:

- `id` - required, lowercase identifier, must match `^[a-z0-9][a-z0-9_-]{1,63}$`
- `name` - required, display name in the theme selector
- `version` - optional, defaults to `1.0.0`
- `is_dark` - optional boolean, affects dark/light behavior
- `qss` - required, relative path to a `.qss` file inside the package
- `icons_dir` - required, relative path to the theme icon directory inside the package
- `preview` - optional, relative path to a preview image

Important constraints:

- paths must be relative
- absolute paths are rejected
- paths containing `..` are rejected
- `qss` must point to an existing `.qss` file
- `icons_dir` must point to an existing directory

## QSS behavior

When a theme is applied, the app does not use the theme QSS alone.

Actual load order is:

1. `app/resources/qss/common.qss`
2. the selected theme `.qss`
3. auto-generated QSS overrides from runtime configuration

This means a custom theme should override only what it needs and can rely on `common.qss` as the shared base.

## Icon requirements

This is the most important part.

The importer validates the theme against the icon file set of the bundled `light` theme. A user theme must provide the full required icon set, not just a few overridden files.

Validation rules:

- the importer reads the filenames from the bundled base theme icons directory
- every required icon filename must exist in the imported theme `icons_dir`
- validation is flat, not recursive; icons must be directly inside `icons_dir`
- supported icon extensions are:
  - `.ico`
  - `.png`
  - `.jpg`
  - `.jpeg`
  - `.bmp`
  - `.gif`
  - `.svg`
  - `.svgz`
  - `.webp`
- every icon file must pass `is_valid_icon_file()`

Practical consequence:

- the safest way to create a new theme is to copy the full icon set from `app/resources/ui_icons/light`
- then replace files one by one with your themed versions

If even one required icon is missing, import fails with a message like:

```text
Missing required icons. Examples: ...
```

## Allowed files inside a theme package

Allowed file types:

- `.json`
- `.qss`
- `.md`
- `.txt`
- supported icon/image formats listed above

Rejected:

- any other file extension
- invalid zip paths
- archive traversal attempts

Ignored:

- `.DS_Store`
- files starting with `._`
- `__MACOSX`

## Package limits

Current limits from runtime config:

- max zip size: `50 MB`
- max uncompressed size: `200 MB`
- max file count: `5000`

If any limit is exceeded, import fails.

## Theme ID conflicts

If the imported theme `id` already exists:

- bundled theme ids cannot be overwritten directly
- existing user themes can be:
  - replaced
  - renamed automatically
  - cancelled

In the UI, the conflict dialog offers:

- `Replace`
- `Rename`
- `Cancel`

If rename is chosen, the importer rewrites `theme.json` and generates a new id like:

```text
my-theme-2
my-theme-3
```

## How to create a new additional theme

Recommended workflow:

1. Create a new folder, for example `my-theme`.
2. Copy the full icon set from:

```text
app/resources/ui_icons/light
```

3. Put the copied icons into:

```text
my-theme/icons
```

4. Create your QSS file:

```text
my-theme/qss/my-theme.qss
```

5. Create `my-theme/theme.json` with correct relative paths.
6. Replace icon files and tune the QSS.
7. Zip the folder or copy it into the user themes directory.
8. Import it from Settings or restart/refresh themes.

## Minimal starter example

```text
my-theme/
  theme.json
  qss/
    my-theme.qss
  icons/
    ...all required icon files copied from light theme...
```

Example `theme.json`:

```json
{
  "id": "my-theme",
  "name": "My Theme",
  "version": "1.0.0",
  "is_dark": false,
  "qss": "qss/my-theme.qss",
  "icons_dir": "icons"
}
```

Example `qss/my-theme.qss`:

```css
QMainWindow {
    background: #f4f1ea;
}

QTreeView, QTableView, QListView {
    background: #fbf8f2;
    color: #2f241c;
}

QPushButton {
    background: #d9c3a5;
    color: #2f241c;
    border: 1px solid #a78662;
}
```

## How to install and test

### Option 1: import from UI

1. Open Settings.
2. Use the theme import action.
3. Select the `.zip` package.
4. Resolve conflict if the id already exists.
5. Select the imported theme in the combo box.

### Option 2: copy manually

1. Open the user themes folder.
2. Copy the whole theme folder there.
3. Restart the app or refresh the theme list through Settings.

## Removal behavior

- bundled themes cannot be removed
- user themes can be removed from Settings
- if the currently active user theme is removed, the app falls back to the default theme

## Common failure reasons

Import usually fails for one of these reasons:

- `theme.json` missing
- invalid `id`
- missing `name`
- invalid or missing `qss`
- invalid or missing `icons_dir`
- missing required icons
- unsupported file extension inside the package
- package too large
- zip contains unsafe paths

## Notes for developers

- Theme discovery is cached in `ThemeRegistry`; after changing installed themes, registry invalidation or app restart is needed.
- User theme QSS is loaded by absolute path from the imported theme folder.
- Bundled and user themes share the same logical theme system, but only bundled themes participate in Qt icon theme configuration.
