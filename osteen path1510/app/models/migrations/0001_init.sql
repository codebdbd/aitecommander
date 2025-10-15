PRAGMA foreign_keys = ON;

-- Spheres (top level)
CREATE TABLE IF NOT EXISTS sphere (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT    NOT NULL UNIQUE,
    position   INTEGER NOT NULL DEFAULT 0,
    icon_path  TEXT    DEFAULT ''
);

-- Sections (within sphere)
CREATE TABLE IF NOT EXISTS section (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    sphere_id  INTEGER NOT NULL REFERENCES sphere(id) ON DELETE CASCADE,
    name       TEXT    NOT NULL,
    icon_path  TEXT    DEFAULT '',
    position   INTEGER NOT NULL DEFAULT 0,
    UNIQUE(sphere_id, name)
);

-- Categories (within section)
CREATE TABLE IF NOT EXISTS category (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    section_id INTEGER NOT NULL REFERENCES section(id) ON DELETE CASCADE,
    name       TEXT    NOT NULL,
    icon_path  TEXT    DEFAULT '',
    position   INTEGER NOT NULL DEFAULT 0,
    UNIQUE(section_id, name)
);

-- Links (within category)
CREATE TABLE IF NOT EXISTS link (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id  INTEGER NOT NULL REFERENCES category(id) ON DELETE CASCADE,
    name         TEXT    NOT NULL,
    url          TEXT    NOT NULL,
    type         TEXT    NOT NULL CHECK(type IN ('web','file','program','script','chromeapp','folder')),
    notes        TEXT    DEFAULT '',
    is_favorite  INTEGER NOT NULL CHECK(is_favorite IN (0,1)) DEFAULT 0,
    last_used    TEXT    DEFAULT NULL,
    icon_path    TEXT    NOT NULL DEFAULT 'default.ico',
    args         TEXT    DEFAULT '',
    browser_key  TEXT    DEFAULT NULL,
    position     INTEGER NOT NULL DEFAULT 0,
    UNIQUE(category_id, name, url, args)
);

-- Database backups
CREATE TABLE IF NOT EXISTS backup (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT    NOT NULL,
    file_path  TEXT    NOT NULL
);
