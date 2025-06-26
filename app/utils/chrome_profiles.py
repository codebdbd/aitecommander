import os
import json
import re
from app.config import *

def find_chrome_profiles():
    """
    Находит профили Chrome и возвращает список словарей с email и аргументом запуска.
    Пример возвращаемого значения:
    [
        {"email": "ostten@gmail.com", "args": "--profile-directory=\"Profile 1\""},
        ...
    ]
    """
    profiles = []
    chrome_base = CHROME_PROFILES_DIR
    if not os.path.exists(chrome_base):
        return profiles
    
    try:
        for entry in os.listdir(chrome_base):
            profile_path = os.path.join(chrome_base, entry)
            if os.path.isdir(profile_path) and (entry.startswith("Profile") or entry == "Default"):
                # Ищем email в Preferences
                pref_path = os.path.join(profile_path, "Preferences")
                email = None
                if os.path.exists(pref_path):
                    try:
                        with open(pref_path, "r", encoding="utf-8") as f:
                            prefs = json.load(f)
                        email = prefs.get("account_info", [{}])[0].get("email")
                        if not email:
                            # Иногда email лежит в другой структуре
                            gaia = prefs.get("gaia_info", {})
                            email = gaia.get("email")
                    except Exception:
                        continue
                if email:
                    args = f'--profile-directory="{entry}"'
                    profiles.append({"email": email, "args": args})
    except Exception:
        pass
    return profiles