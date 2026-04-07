import os
import sys
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer

from py_editor.composite_editor import CompositeEditorDialog
from py_editor.node_templates import list_templates

app = QApplication(sys.argv)
print('available templates:', list_templates())
# make a composite template that references existing basic templates
graph = {
    'nodes': [
        {'id': 1, 'template': 'Add', 'pos': [-100, 0], 'title': 'AddNode'},
        {'id': 2, 'template': 'ConstInt', 'pos': [100, 0], 'title': 'ConstIntNode'},
    ],
    'connections': [
        {'from': 2, 'from_pin': 'value', 'to': 1, 'to_pin': 'a'}
    ],
}
template = {'type': 'composite', 'name': 'TestComposite', 'graph': graph, 'inputs': {}, 'outputs': {}}

# open dialog
dlg = CompositeEditorDialog(None, template=template)
QTimer.singleShot(50, lambda: (print('nodes in dialog canvas:', len(dlg.canvas.nodes)), dlg.reject()))
rc = dlg.exec()
print('dialog exec rc', rc)
QTimer.singleShot(50, app.quit)
app.exec()
print('done')
