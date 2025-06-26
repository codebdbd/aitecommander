import sqlite3
from pathlib import Path
import shutil
import datetime

# Пути к файлам
SCHEMA_PATH = Path(__file__).parent / "schema.sql"
DB_PATH     = Path(__file__).parent.parent / "links.db"
BACKUP_DIR  = Path(__file__).parent.parent / "backups"

class Database:
    def __init__(self):
        BACKUP_DIR.mkdir(exist_ok=True)
        is_new = not DB_PATH.exists()
        self.conn = sqlite3.connect(str(DB_PATH))
        self.conn.row_factory = sqlite3.Row

        if is_new:
            self._init_schema()

        self._seed_spheres()

    def _init_schema(self):
        sql = SCHEMA_PATH.read_text(encoding="utf-8")
        self.conn.executescript(sql)
        self.conn.commit()

    def _seed_spheres(self):
        cur = self.conn.execute("SELECT COUNT(*) AS cnt FROM sphere")
        if cur.fetchone()["cnt"] == 0:
            try:
                self.conn.execute("ALTER TABLE sphere ADD COLUMN icon_path TEXT DEFAULT ''")
            except sqlite3.OperationalError:
                pass

            default = [
                ("AI",      0, "ai_icon.png"),
                ("Работа",  1, "work_icon.png"),
                ("Учеба",   2, "study_icon.png"),
                ("Личное",  3, "personal_icon.png"),
            ]
            self.conn.executemany(
                "INSERT INTO sphere(name, position, icon_path) VALUES(?,?,?)",
                default
            )
            self.conn.commit()

    def get_spheres(self):
        return self.conn.execute(
            "SELECT id, name, position, icon_path FROM sphere ORDER BY position"
        ).fetchall()

    def get_sections(self, sphere_id):
        return self.conn.execute(
            "SELECT id, name, sphere_id, position, icon_path FROM section "
            "WHERE sphere_id=? ORDER BY position",
            (sphere_id,)
        ).fetchall()

    def get_categories(self, section_id):
        return self.conn.execute(
            "SELECT id, name, section_id, position, icon_path FROM category "
            "WHERE section_id=? ORDER BY position",
            (section_id,)
        ).fetchall()

    def get_category_by_id(self, category_id: int):
        cursor = self.conn.execute("SELECT * FROM category WHERE id=?", (category_id,))
        return cursor.fetchone()

    def get_links(self, category_id):
        return self.conn.execute(
            "SELECT id, category_id, name, url, type, notes, "
            "is_favorite, last_used, icon_path, args, position "
            "FROM link WHERE category_id=? ORDER BY position",
            (category_id,)
        ).fetchall()

    def insert_section(self, data: dict):
        self.conn.execute(
            "INSERT INTO section (name, sphere_id, icon_path, position) VALUES (?, ?, ?, 0)",
            (data["name"], data["sphere_id"], data["icon_path"])
        )
        self.conn.commit()

    def update_section(self, section_id: int, data: dict):
        self.conn.execute(
            "UPDATE section SET name=?, sphere_id=?, icon_path=? WHERE id=?",
            (data["name"], data["sphere_id"], data["icon_path"], section_id)
        )
        self.conn.commit()

    def delete_section(self, section_id: int):
        self.conn.execute("DELETE FROM section WHERE id=?", (section_id,))
        self.conn.commit()

    def insert_category(self, data: dict):
        self.conn.execute(
            "INSERT INTO category (name, section_id, icon_path, position) VALUES (?, ?, ?, 0)",
            (data["name"], data["section_id"], data["icon_path"])
        )
        self.conn.commit()

    def update_category(self, category_id: int, data: dict):
        self.conn.execute(
            "UPDATE category SET name=?, section_id=?, icon_path=? WHERE id=?",
            (data["name"], data["section_id"], data["icon_path"], category_id)
        )
        self.conn.commit()

    def delete_category(self, category_id: int):
        self.conn.execute("DELETE FROM category WHERE id=?", (category_id,))
        self.conn.commit()

    def upsert_link(self, link: dict):
        args = link.get("args", "")
        position = link.get("position", 0)
        if link.get("id"):
            self.conn.execute(
                "UPDATE link SET "
                "category_id=?, name=?, url=?, type=?, notes=?, "
                "is_favorite=?, last_used=?, icon_path=?, args=?, position=? "
                "WHERE id=?",
                (
                    link["category_id"], link["name"], link["url"], link["type"],
                    link.get("notes", ""), int(link.get("is_favorite", 0)),
                    link.get("last_used"), link.get("icon_path", ""),
                    args, position, link["id"]
                )
            )
        else:
            self.conn.execute(
                "INSERT INTO link("
                "category_id, name, url, type, notes, "
                "is_favorite, last_used, icon_path, args, position"
                ") VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    link["category_id"], link["name"], link["url"], link["type"],
                    link.get("notes", ""), int(link.get("is_favorite", 0)),
                    link.get("last_used"), link.get("icon_path", ""),
                    args, position
                )
            )
        self.conn.commit()

    def delete_link(self, link_id: int):
        self.conn.execute("DELETE FROM link WHERE id=?", (link_id,))
        self.conn.commit()

    def backup(self):
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        dst = BACKUP_DIR / f"links_{timestamp}.db"
        shutil.copy2(DB_PATH, dst)

        max_bak = self._get_max_backups()
        files = sorted(BACKUP_DIR.glob("links_*.db"))
        while len(files) > max_bak:
            files.pop(0).unlink()

    def _get_max_backups(self) -> int:
        return 5
