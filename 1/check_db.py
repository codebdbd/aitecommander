import sqlite3

conn = sqlite3.connect(r'B:\osteen path\data\links.db')
cursor = conn.execute('SELECT id, name, icon_path, length(icon_path) as len FROM section WHERE sphere_id=3 LIMIT 10')
for row in cursor.fetchall():
    print(f"ID: {row[0]}, Name: {row[1]}, icon_path: '{row[2]}', len: {row[3]}")
conn.close()
