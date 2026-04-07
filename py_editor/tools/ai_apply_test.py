import sys
import json
import traceback
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer

# Import main app
try:
    from py_editor.main import MainWindow
except Exception:
    from main import MainWindow

SAMPLE_RESPONSE = '''I will add the nodes and UI as requested.\n\n```apply
{
"nodes": [
{"type": "ConstString", "x": 100, "y": 100, "properties": {"value": "Goblin"}},
{"type": "ConstString", "x": 100, "y": 150, "properties": {"value": "Troll"}},
{"type": "ConstString", "x": 100, "y": 200, "properties": {"value": "Dragon"}}
],
"connections": [],
"ui_widgets": [
{"type": "Dropdown", "x": 50, "y": 50, "properties": {"options": ["Goblin", "Troll", "Dragon"], "selected_option": "Goblin"}}
]
}
```\nDone.
'''


def dump_state(win: MainWindow):
    try:
        canvas = win.canvas
        nodes = []
        for n in canvas.nodes:
            nodes.append({
                'id': getattr(n, 'id', None),
                'title': getattr(n, 'title').toPlainText() if getattr(n, 'title', None) else None,
                'inputs': getattr(n, 'inputs', {}),
                'outputs': getattr(n, 'outputs', {}),
                'pin_values': getattr(n, 'pin_values', {})
            })
        vars = getattr(canvas, 'graph_variables', {})
        ui_widgets = []
        try:
            uic = win.ui_builder.canvas
            for w in uic.widgets:
                ui_widgets.append({'id': getattr(w, 'id', None), 'type': getattr(w, 'widget_type', None), 'pos': (w.x(), w.y()), 'properties': getattr(w, 'properties', {})})
        except Exception:
            ui_widgets = []
        print('\n--- DUMPED STATE ---')
        print('Nodes:')
        print(json.dumps(nodes, indent=2))
        print('Variables:')
        print(json.dumps(vars, indent=2))
        print('UI Widgets:')
        print(json.dumps(ui_widgets, indent=2))
        print('--------------------\n')
    except Exception:
        traceback.print_exc()


def run_test():
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()

    # Inject the response after startup with verbose logging
    def inject():
        print('TEST: injecting sample response into AI chat...')
        try:
            win.ai_chat._process_response(SAMPLE_RESPONSE)
            print('TEST: injection complete')
        except Exception:
            traceback.print_exc()

    QTimer.singleShot(1200, inject)
    # Dump state after another delay
    QTimer.singleShot(2600, lambda: (print('TEST: dumping state...'), dump_state(win)))
    # Quit after short delay
    QTimer.singleShot(3600, lambda: (print('TEST: quitting app'), app.quit()))
    sys.exit(app.exec())

if __name__ == '__main__':
    run_test()
