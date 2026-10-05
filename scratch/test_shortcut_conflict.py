import sys
from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget
from PyQt6.QtGui import QAction, QKeySequence, QShortcut
from PyQt6.QtCore import Qt

app = QApplication.instance() or QApplication(sys.argv)
win = QMainWindow()

calls = []

def undo_func():
    calls.append("undo_func")
    print("UNDO CALLED! Total calls:", len(calls))

# Suppose an action has shortcut Ctrl+Z
act = QAction(win)
act.setShortcut(QKeySequence("Ctrl+Z"))
act.triggered.connect(undo_func)
win.addAction(act)

# And suppose QShortcut also has Ctrl+Z
sc = QShortcut(QKeySequence("Ctrl+Z"), win)
sc.activated.connect(undo_func)

print("Simulating Ctrl+Z via QShortcut activation:")
sc.activated.emit()
print("Simulating Ctrl+Z via QAction trigger:")
act.trigger()
