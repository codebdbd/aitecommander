"""Find actual database path."""
import sys
sys.path.insert(0, r'B:\osteen path')

from app.config_data import app_config

db_path = app_config.paths.get_db_path()
print(f"Database path: {db_path}")
print(f"Exists: {db_path.exists()}")
