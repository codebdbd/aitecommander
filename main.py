import os
import sys

from app.main import main

if __name__ == "__main__":
    code = main()
    try:
        sys.stdout.flush()
        sys.stderr.flush()
    except Exception:
        pass
    if sys.platform == "win32":
        try:
            import pythoncom

            pythoncom.CoUninitialize()
        except Exception:
            pass
        try:
            import ctypes

            ctypes.windll.kernel32.ExitProcess(int(code))
        except Exception:
            os._exit(code)
    else:
        os._exit(code)
