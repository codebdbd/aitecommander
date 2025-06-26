PRAGMA foreign_keys = ON;

-- Сферы (верхний уровень)
CREATE TABLE IF NOT EXISTS sphere (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT    NOT NULL UNIQUE,
    position   INTEGER NOT NULL DEFAULT 0,
    icon_path  TEXT    DEFAULT ''
);

-- Разделы (внутри сферы)
CREATE TABLE IF NOT EXISTS section (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    sphere_id  INTEGER NOT NULL REFERENCES sphere(id) ON DELETE CASCADE,
    name       TEXT    NOT NULL,
    icon_path  TEXT    DEFAULT '',
    position   INTEGER NOT NULL DEFAULT 0,
    UNIQUE(sphere_id, name)
);

-- Категории (внутри раздела)
CREATE TABLE IF NOT EXISTS category (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    section_id INTEGER NOT NULL REFERENCES section(id) ON DELETE CASCADE,
    name       TEXT    NOT NULL,
    icon_path  TEXT    DEFAULT '',
    position   INTEGER NOT NULL DEFAULT 0,
    UNIQUE(section_id, name)
);

-- Ссылки (внутри категории)
CREATE TABLE IF NOT EXISTS link (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id  INTEGER NOT NULL REFERENCES category(id) ON DELETE CASCADE,
    name         TEXT    NOT NULL,
    url          TEXT    NOT NULL,
    type         TEXT    NOT NULL CHECK(type IN ('web','file','program','script','chromeapp','folder')),
    notes        TEXT    DEFAULT '',
    is_favorite  INTEGER NOT NULL CHECK(is_favorite IN (0,1)) DEFAULT 0,
    last_used    TEXT    DEFAULT NULL,
    icon_path    TEXT    NOT NULL,
    args         TEXT    DEFAULT '',
    position     INTEGER NOT NULL DEFAULT 0
);

-- Резервные копии базы
CREATE TABLE IF NOT EXISTS backup (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT    NOT NULL,
    file_path  TEXT    NOT NULL
);
