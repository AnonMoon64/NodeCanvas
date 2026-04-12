from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QPlainTextEdit, QMessageBox
from PyQt6.QtCore import Qt
import sys
from pathlib import Path

# Add parent directories to path for imports
if __name__ == '__main__' or 'py_editor' not in sys.modules:
    parent_dir = Path(__file__).resolve().parent.parent
    if str(parent_dir) not in sys.path:
        sys.path.insert(0, str(parent_dir))

try:
    from py_editor.core import node_templates
except Exception:
    try:
        from ..core import node_templates
    except Exception:
        from core import node_templates

DEFAULT_TEMPLATE = '''# Name: MyNode
# Example node template. Fill `inputs` and `outputs` dictionaries
# and implement `process(**inputs)` to return outputs as a dict or a value

# display name for the node
name = "MyNode"

# inputs exposed by this node: name -> type (type is informational)
inputs = {
    "a": "float",
    "b": "float",
}

# outputs exposed by this node: name -> type
outputs = {
    "result": "float",
}

def process(a, b):
    """Return a single value or a dict of outputs.

    If you return a single value and `outputs` has one key,
    the value will be assigned to that output key.
    """
    # simple example: add two numbers
    return a + b
'''

class NodeEditorDialog(QDialog):
    def __init__(self, parent=None, template=None):
        super().__init__(parent)
        self.setWindowTitle('Node Editor')
        self.resize(700, 500)

        v = QVBoxLayout(self)

        hl = QHBoxLayout()
        hl.addWidget(QLabel('Name:'))
        self.name_edit = QLineEdit(self)
        hl.addWidget(self.name_edit)
        v.addLayout(hl)

        self.code = QPlainTextEdit(self)
        v.addWidget(self.code)

        btns = QHBoxLayout()
        self.save_btn = QPushButton('Save Node')
        self.cancel_btn = QPushButton('Cancel')
        btns.addWidget(self.save_btn)
        btns.addWidget(self.cancel_btn)
        v.addLayout(btns)

        self.save_btn.clicked.connect(self.on_save)
        self.cancel_btn.clicked.connect(self.reject)

        if template:
            self.name_edit.setText(template.get('name',''))
            self.code.setPlainText(template.get('code',''))
        else:
            self.code.setPlainText(DEFAULT_TEMPLATE)

    def on_save(self):
        name = self.name_edit.text().strip()
        code = self.code.toPlainText()
        if not name:
            QMessageBox.warning(self, 'Validation', 'Name is required')
            return

        # basic validation: execute in a restricted namespace and ensure required symbols
        ns = {}
        try:
            exec(code, {}, ns)
        except Exception as e:
            QMessageBox.critical(self, 'Validation Error', f'Error executing code:\n{e}')
            return

        if 'process' not in ns:
            QMessageBox.critical(self, 'Validation Error', 'process() function not found')
            return
        # store template (explicitly mark base type)
        data = {'name': name, 'code': code, 'type': 'base'}
        try:
            node_templates.save_template(data)
        except Exception as e:
            QMessageBox.critical(self, 'Save Error', str(e))
            return
        self.accept()

class TextEditorDialog(QDialog):
    """General purpose text editor for logic scripts, UI JSON, and scene files."""
    def __init__(self, parent=None, filepath=None):
        super().__init__(parent)
        self.filepath = filepath
        self.setWindowTitle(f"Text Editor: {Path(filepath).name}" if filepath else "Text Editor")
        self.resize(900, 700)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowMaximizeButtonHint)

        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        # Style context matching our dark theme
        self.setStyleSheet("""
            QDialog { background: #1e1e1e; font-family: 'Segoe UI', sans-serif; }
            QPlainTextEdit { 
                background: #111; 
                color: #dcdccc; 
                border: none; 
                font-family: 'Consolas', 'Courier New', monospace; 
                font-size: 14px; 
                padding: 12px;
            }
        """)

        self.editor = QPlainTextEdit(self)
        v.addWidget(self.editor)

        # Bottom bar for status and actions
        bb = QWidget()
        bb.setFixedHeight(45)
        bb.setStyleSheet("background: #252526; border-top: 1px solid #3c3c3c;")
        bbl = QHBoxLayout(bb)
        bbl.setContentsMargins(15, 0, 15, 0)

        self.status = QLabel("Ready")
        self.status.setStyleSheet("color: #777; border: none; font-size: 11px;")
        bbl.addWidget(self.status)

        bbl.addStretch()

        self.save_btn = QPushButton("Save (Ctrl+S)")
        self.save_btn.setFixedSize(110, 26)
        self.save_btn.setStyleSheet("""
            QPushButton { background: #007acc; color: white; border: none; border-radius: 4px; font-weight: bold; }
            QPushButton:hover { background: #0062a3; }
        """)
        
        self.close_btn = QPushButton("Close")
        self.close_btn.setFixedSize(80, 26)
        self.close_btn.setStyleSheet("""
            QPushButton { background: #3a3a3a; color: #ccc; border: 1px solid #555; border-radius: 4px; }
            QPushButton:hover { background: #454545; color: white; }
        """)

        bbl.addWidget(self.save_btn)
        bbl.addWidget(self.close_btn)
        v.addWidget(bb)

        self.save_btn.clicked.connect(self.on_save)
        self.close_btn.clicked.connect(self.accept)

        if filepath and Path(filepath).exists():
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    self.editor.setPlainText(f.read())
                self.status.setText(f"File loaded: {filepath}")
            except Exception as e:
                self.editor.setPlainText(f"Failed to load file:\n{e}")
                self.status.setText("Load error")

    def keyPressEvent(self, event):
        # Allow Ctrl+S to save
        if event.modifiers() == Qt.KeyboardModifier.ControlModifier and event.key() == Qt.Key.Key_S:
            self.on_save()
            return
        super().keyPressEvent(event)

    def on_save(self):
        if not self.filepath:
             QMessageBox.warning(self, "Save Error", "No file path specified.")
             return
        try:
            with open(self.filepath, 'w', encoding='utf-8') as f:
                f.write(self.editor.toPlainText())
            self.status.setText(f"Saved at {Path(self.filepath).name}")
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(3000, lambda: self.status.setText("Ready"))
        except Exception as e:
            QMessageBox.critical(self, "Save Error", f"Failed to save file:\n{e}")

