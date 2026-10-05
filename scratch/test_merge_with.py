import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QUndoStack, QUndoCommand

app = QApplication.instance() or QApplication(sys.argv)

class CutCmd(QUndoCommand):
    def __init__(self):
        super().__init__("Cut category")
        self._paste_cmd = None

    def id(self):
        return 1001

    def mergeWith(self, other):
        if other.id() == 1001:
            self._paste_cmd = other
            self.setText("Move category")
            print("mergeWith called! Merged successfully.")
            return True
        return False

    def redo(self):
        print("CutCmd redo (delete original)")
        if self._paste_cmd:
            self._paste_cmd.redo()

    def undo(self):
        print("CutCmd undo:")
        if self._paste_cmd:
            print("  1. Undo paste (remove from new section)")
            self._paste_cmd.undo()
        print("  2. Undo cut (restore to old section)")

class PasteCmd(QUndoCommand):
    def __init__(self):
        super().__init__("Paste category")

    def id(self):
        return 1001

    def redo(self):
        print("PasteCmd redo (insert into new section)")

    def undo(self):
        print("PasteCmd undo (delete from new section)")

stack = QUndoStack()
print("1. Pushing CutCmd:")
cut = CutCmd()
stack.push(cut)
print("Stack count after Cut:", stack.count())

print("\n2. Pushing PasteCmd:")
paste = PasteCmd()
stack.push(paste)
print("Stack count after Paste:", stack.count())

print("\n3. Calling stack.undo():")
stack.undo()
print("Stack index after undo:", stack.index())
print("Can undo further?", stack.canUndo())
