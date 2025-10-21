import PyQt6
import pathlib
qt_dir = pathlib.Path(PyQt6.__file__).resolve().parent
print('PyQt6 module path:', qt_dir)
found = False
for path in qt_dir.rglob('lrelease.exe'):
    print('Found:', path)
    found = True
    break
if not found:
    print('No lrelease.exe found')
