"""Service for registering and managing Windows file associations for .aitesec and .aitecat."""
from __future__ import annotations

import ctypes
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

SHCNE_ASSOCCHANGED = 0x08000000
SHCNF_IDLIST = 0x0000


class FileAssociationService:
    """Manages file associations in Windows Registry (HKCU\\Software\\Classes)."""

    EXTENSIONS = (".aitesec", ".aitecat")
    PROG_IDS = {
        ".aitesec": ("aitecommander.section", "AiteCommander Section Archive"),
        ".aitecat": ("aitecommander.category", "AiteCommander Category Archive"),
    }

    @classmethod
    def is_supported(cls) -> bool:
        return sys.platform == "win32"

    @classmethod
    def _get_open_command(cls) -> str:
        if getattr(sys, "frozen", False):
            exe_path = sys.executable
            return f'"{exe_path}" "%1"'
        python_exe = sys.executable
        pythonw = Path(python_exe).with_name("pythonw.exe")
        if pythonw.exists():
            python_exe = str(pythonw)
        main_py = Path(__file__).resolve().parents[2] / "main.py"
        return f'"{python_exe}" "{main_py}" "%1"'

    @classmethod
    def _get_icon_path(cls) -> str:
        icon_path = Path(__file__).resolve().parents[1] / "resources" / "package_icon.ico"
        if icon_path.exists():
            return str(icon_path)
        if getattr(sys, "frozen", False):
            return f'"{sys.executable}",0'
        return ""

    @classmethod
    def is_registered(cls) -> bool:
        if not cls.is_supported():
            return False
        import winreg

        try:
            for ext in cls.EXTENSIONS:
                prog_id, _ = cls.PROG_IDS[ext]
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, f"Software\\Classes\\{ext}") as key:
                    val, _ = winreg.QueryValueEx(key, "")
                    if val != prog_id:
                        return False
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, f"Software\\Classes\\{prog_id}\\shell\\open\\command") as key:
                    cmd_val, _ = winreg.QueryValueEx(key, "")
                    if not cmd_val:
                        return False
            return True
        except OSError:
            return False

    @classmethod
    def register_associations(cls) -> bool:
        if not cls.is_supported():
            return False
        import winreg

        try:
            cmd = cls._get_open_command()
            icon = cls._get_icon_path()

            for ext, (prog_id, description) in cls.PROG_IDS.items():
                with winreg.CreateKey(winreg.HKEY_CURRENT_USER, f"Software\\Classes\\{ext}") as key:
                    winreg.SetValueEx(key, "", 0, winreg.REG_SZ, prog_id)

                with winreg.CreateKey(winreg.HKEY_CURRENT_USER, f"Software\\Classes\\{prog_id}") as key:
                    winreg.SetValueEx(key, "", 0, winreg.REG_SZ, description)

                if icon:
                    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, f"Software\\Classes\\{prog_id}\\DefaultIcon") as key:
                        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, icon)

                with winreg.CreateKey(winreg.HKEY_CURRENT_USER, f"Software\\Classes\\{prog_id}\\shell\\open\\command") as key:
                    winreg.SetValueEx(key, "", 0, winreg.REG_SZ, cmd)

            cls._notify_shell()
            logger.info("File associations successfully registered in HKCU")
            return True
        except Exception as exc:
            logger.error("Failed to register file associations: %s", exc, exc_info=True)
            return False

    @classmethod
    def unregister_associations(cls) -> bool:
        if not cls.is_supported():
            return False
        import winreg

        try:
            for ext, (prog_id, _) in cls.PROG_IDS.items():
                cls._delete_subkeys(winreg.HKEY_CURRENT_USER, f"Software\\Classes\\{prog_id}")
                cls._delete_subkeys(winreg.HKEY_CURRENT_USER, f"Software\\Classes\\{ext}")

            cls._notify_shell()
            logger.info("File associations successfully unregistered from HKCU")
            return True
        except Exception as exc:
            logger.error("Failed to unregister file associations: %s", exc, exc_info=True)
            return False

    @classmethod
    def _delete_subkeys(cls, root: int, subkey: str) -> None:
        import winreg

        try:
            with winreg.OpenKey(root, subkey, 0, winreg.KEY_ALL_ACCESS) as key:
                while True:
                    try:
                        child = winreg.EnumKey(key, 0)
                        cls._delete_subkeys(root, f"{subkey}\\{child}")
                    except OSError:
                        break
            winreg.DeleteKey(root, subkey)
        except OSError:
            pass

    @classmethod
    def _notify_shell(cls) -> None:
        try:
            ctypes.windll.shell32.SHChangeNotify(SHCNE_ASSOCCHANGED, SHCNF_IDLIST, 0, 0)
        except Exception as exc:
            logger.debug("SHChangeNotify failed: %s", exc)
