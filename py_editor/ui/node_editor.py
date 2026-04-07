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
