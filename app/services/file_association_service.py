"""Windows file association service for .aitepack packages."""
from __future__ import annotations

import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

EXTENSIONS = [
    {
        "ext": ".aitesec",
        "prog_id": "AiteCommander.Section",
        "desc": "AiteCommander Section",
    },
    {
        "ext": ".aitecat",
        "prog_id": "AiteCommander.Category",
        "desc": "AiteCommander Category",
    },
    {
        "ext": ".aitepack",
        "prog_id": "AiteCommander.Package",
        "desc": "AiteCommander Package",
    },
]


def _get_open_command() -> str:
    """Return the shell open command string for the current executable."""
    if getattr(sys, "frozen", False):
        exe = sys.executable
        return f'"{exe}" "%1"'
    py_exe = sys.executable
    pythonw = Path(py_exe).parent / "pythonw.exe"
    if pythonw.is_file():
        py_exe = str(pythonw)
    main_script = str(Path(__file__).resolve().parent.parent / "main.py")
    return f'"{py_exe}" "{main_script}" "%1"'



def _get_default_icon() -> str:
    """Return the icon path string for file association."""
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).parent
        pkg_icon = exe_dir / "_internal" / "app" / "resources" / "package_icon.ico"
        if pkg_icon.is_file():
            return f'"{pkg_icon}",0'
        pkg_icon_root = exe_dir / "package_icon.ico"
        if pkg_icon_root.is_file():
            return f'"{pkg_icon_root}",0'
        return f'"{sys.executable}",0'
    pkg_icon = Path(__file__).resolve().parent.parent / "resources" / "package_icon.ico"
    if pkg_icon.is_file():
        return f'"{pkg_icon}",0'
    return f'"{sys.executable}",0'


def is_file_association_registered() -> bool:
    """Check if .aitepack is registered in HKCU."""
    if sys.platform != "win32":
        return False
    import winreg

    expected_cmd = _get_open_command()
    expected_icon = _get_default_icon()
    try:
        for item in EXTENSIONS:
            ext = item["ext"]
            prog_id = item["prog_id"]
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, rf"Software\Classes\{ext}") as key:
                val, _ = winreg.QueryValueEx(key, "")
                if val != prog_id:
                    return False
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, rf"Software\Classes\{prog_id}\shell\open\command"
            ) as key:
                val, _ = winreg.QueryValueEx(key, "")
                if val != expected_cmd:
                    return False
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, rf"Software\Classes\{prog_id}\DefaultIcon"
            ) as key:
                val, _ = winreg.QueryValueEx(key, "")
                if val != expected_icon:
                    return False
        return True
    except OSError:
        return False


def register_file_associations() -> bool:
    """Register .aitepack in HKCU without requiring admin privileges."""
    if sys.platform != "win32":
        return False
    import ctypes
    import winreg

    open_cmd = _get_open_command()
    default_icon = _get_default_icon()
    try:
        for item in EXTENSIONS:
            ext = item["ext"]
            prog_id = item["prog_id"]
            desc = item["desc"]

            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"Software\Classes\{ext}") as key:
                winreg.SetValueEx(key, "", 0, winreg.REG_SZ, prog_id)

            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"Software\Classes\{prog_id}") as key:
                winreg.SetValueEx(key, "", 0, winreg.REG_SZ, desc)

            with winreg.CreateKey(
                winreg.HKEY_CURRENT_USER, rf"Software\Classes\{prog_id}\shell\open\command"
            ) as key:
                winreg.SetValueEx(key, "", 0, winreg.REG_SZ, open_cmd)

            with winreg.CreateKey(
                winreg.HKEY_CURRENT_USER, rf"Software\Classes\{prog_id}\DefaultIcon"
            ) as key:
                winreg.SetValueEx(key, "", 0, winreg.REG_SZ, default_icon)

        # Notify Windows shell (SHCNE_ASSOCCHANGED = 0x08000000)
        ctypes.windll.shell32.SHChangeNotify(0x08000000, 0x0000, None, None)
        return True
    except Exception as exc:
        logger.warning("Failed to register file associations: %s", exc)
        return False


def unregister_file_associations() -> bool:
    """Unregister .aitepack from HKCU."""
    if sys.platform != "win32":
        return False
    import ctypes
    import winreg

    def _delete_key_recursive(root, subkey):
        try:
            with winreg.OpenKey(root, subkey, 0, winreg.KEY_ALL_ACCESS) as key:
                while True:
                    try:
                        child = winreg.EnumKey(key, 0)
                        _delete_key_recursive(key, child)
                    except OSError:
                        break
            winreg.DeleteKey(root, subkey)
        except OSError:
            pass

    try:
        for item in EXTENSIONS:
            _delete_key_recursive(winreg.HKEY_CURRENT_USER, rf"Software\Classes\{item['ext']}")
            _delete_key_recursive(winreg.HKEY_CURRENT_USER, rf"Software\Classes\{item['prog_id']}")

        ctypes.windll.shell32.SHChangeNotify(0x08000000, 0x0000, None, None)
        return True
    except Exception as exc:
        logger.warning("Failed to unregister file associations: %s", exc)
        return False
