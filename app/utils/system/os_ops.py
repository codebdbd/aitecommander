import os
import platform
import subprocess


def open_file(file_path: str) -> bool:
    """Открыть файл системным приложением. Возвращает True при успехе."""
    try:
        if platform.system() == "Windows":
            os.startfile(file_path)  # type: ignore[attr-defined]
            return True
        elif platform.system() == "Darwin":
            subprocess.run(["open", file_path], check=False)
            return True
        else:
            subprocess.run(["xdg-open", file_path], check=False)
            return True
    except Exception:
        return False


def reveal_in_folder(file_path: str) -> bool:
    """Показать файл в проводнике/файндере. Возвращает True при успехе."""
    try:
        if platform.system() == "Windows":
            # Explorer ожидает ключ как один аргумент: /select,<path>.
            # Для путей с пробелами обязательно оборачиваем путь в кавычки.
            norm_path = os.path.normpath(file_path)
            subprocess.run(["explorer", f'/select,"{norm_path}"'], check=False)
            return True
        elif platform.system() == "Darwin":
            subprocess.run(["open", "-R", file_path], check=False)
            return True
        else:
            folder_path = os.path.dirname(file_path)
            subprocess.run(["xdg-open", folder_path], check=False)
            return True
    except Exception:
        return False
