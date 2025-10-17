"""Check icon_path values in database."""
import sys
sys.path.insert(0, r'B:\osteen path')

from app.models.db import Database

db = Database()
db.initialize_or_migrate()

# Check sections in sphere 3
cursor = db.connection.execute(
    "SELECT id, name, icon_path FROM section WHERE sphere_id=3 LIMIT 20"
)
print("=== SECTIONS (sphere_id=3) ===")
for row in cursor.fetchall():
    icon_path = row[2]
    print(f"ID: {row[0]:3d} | Name: {row[1]:30s} | icon_path: '{icon_path}' | repr: {repr(icon_path)} | len: {len(icon_path) if icon_path else 0}")

# Check categories in sphere 3
cursor = db.connection.execute(
    """SELECT c.id, c.name, c.icon_path 
       FROM category c 
       JOIN section s ON c.section_id = s.id 
       WHERE s.sphere_id=3 LIMIT 20"""
)
print("\n=== CATEGORIES (sphere_id=3) ===")
for row in cursor.fetchall():
    icon_path = row[2]
    print(f"ID: {row[0]:3d} | Name: {row[1]:30s} | icon_path: '{icon_path}' | repr: {repr(icon_path)} | len: {len(icon_path) if icon_path else 0}")

db.close()
