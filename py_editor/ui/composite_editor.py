from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QLineEdit, QMessageBox, QApplication, QComboBox, QInputDialog
from PyQt6.QtCore import QPointF
import traceback
try:
    from py_editor.core import node_templates
    from py_editor.ui.canvas import CanvasView, ConnectionItem, NodeItem
except Exception:
    try:
        from ..core import node_templates
        from .canvas import CanvasView, ConnectionItem, NodeItem
    except Exception:
        import sys
        from pathlib import Path
        parent_dir = Path(__file__).resolve().parent.parent
        if str(parent_dir) not in sys.path:
            sys.path.insert(0, str(parent_dir))
        from core import node_templates
        from ui.canvas import CanvasView, ConnectionItem, NodeItem

class CompositeEditorDialog(QDialog):
    def __init__(self, parent=None, template=None):
        super().__init__(parent)
        self.setWindowTitle('Composite Node Editor')
        self.resize(900, 600)
        self.template = template

        v = QVBoxLayout(self)
        hl = QHBoxLayout()
        hl.addWidget(QLabel('Name:'))
        self.name_edit = QLineEdit(self)
        hl.addWidget(self.name_edit)
        v.addLayout(hl)
        
        hl2 = QHBoxLayout()
        hl2.addWidget(QLabel('Category:'))
        self.category_edit = QLineEdit(self)
        self.category_edit.setPlaceholderText('e.g., Math, Logic, Utilities')
        hl2.addWidget(self.category_edit)
        v.addLayout(hl2)

        self.canvas = CanvasView(parent=self, is_subcanvas=True, host_template=self.template)
        v.addWidget(self.canvas)

        btns = QHBoxLayout()
        self.save_btn = QPushButton('Save Composite')
        self.cancel_btn = QPushButton('Cancel')
        btns.addWidget(self.save_btn)
        btns.addWidget(self.cancel_btn)
        v.addLayout(btns)

        self.save_btn.clicked.connect(self.on_save)
        self.cancel_btn.clicked.connect(self.reject)

        if template:
            self.name_edit.setText(template.get('name',''))
            self.category_edit.setText(template.get('category',''))
            # load graph if present - this will load all nodes including composite I/O nodes
            graph = template.get('graph')
            if graph:
                self.canvas.load_graph(graph)
            # After loading, restore external_name from input/output mappings
            try:
                inputs = template.get('inputs', {}) or {}
                outputs = template.get('outputs', {}) or {}
                
                # Find composite I/O nodes and set their external names from the mapping
                for ext_name, info in inputs.items():
                    if isinstance(info, dict):
                        target_id = info.get('node')
                        if target_id is not None:
                            node = next((n for n in self.canvas.nodes if getattr(n, 'id', None) == target_id), None)
                            if node:
                                node.external_name = ext_name
                                
                for ext_name, info in outputs.items():
                    if isinstance(info, dict):
                        target_id = info.get('node')
                        if target_id is not None:
                            node = next((n for n in self.canvas.nodes if getattr(n, 'id', None) == target_id), None)
                            if node:
                                node.external_name = ext_name
            except Exception:
                traceback.print_exc()

    def on_save(self):
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, 'Validation', 'Name is required')
            return
        # export graph and build input/output mappings from special nodes
        graph = self.canvas.export_graph()

        inputs_map = {}
        outputs_map = {}
        try:
            for node in list(self.canvas.nodes):
                try:
                    tname = getattr(node, 'template_name', None)
                    if tname == '__composite_input__':
                        # use external_name for the composite interface, internal pin for connections
                        pins = list(node.output_pins.keys())
                        if pins:
                            internal_pin = pins[0]  # Always 'out0'
                            external_name = getattr(node, 'external_name', internal_pin)
                            # Get pin type from node metadata if available
                            pin_type = getattr(node, 'pin_type', 'any')
                            inputs_map[external_name] = {'node': node.id, 'pin': internal_pin, 'type': pin_type}
                    elif tname == '__composite_output__':
                        pins = list(node.input_pins.keys())
                        if pins:
                            internal_pin = pins[0]  # Always 'in0'
                            external_name = getattr(node, 'external_name', internal_pin)
                            # Get pin type from node metadata if available
                            pin_type = getattr(node, 'pin_type', 'any')
                            outputs_map[external_name] = {'node': node.id, 'pin': internal_pin, 'type': pin_type}
                except Exception:
                    pass
        except Exception:
            pass

        category = self.category_edit.text().strip()
        data = {
            'type': 'composite',
            'name': name,
            'category': category if category else 'Other',
            'graph': graph,
            'inputs': inputs_map,
            'outputs': outputs_map,
        }
        try:
            node_templates.save_template(data)
            try:
                # reload templates in memory so other canvases see the update
                try:
                    node_templates.load_templates()
                except Exception:
                    pass

                # refresh any open CanvasView instances so composite pins update immediately
                try:
                    app = QApplication.instance()
                    if app:
                        for w in app.topLevelWidgets():
                            try:
                                cvs = w.findChildren(CanvasView)
                                for cv in cvs:
                                    try:
                                        if getattr(cv, 'reload_nodes_from_template', None):
                                            cv.reload_nodes_from_template(name)
                                    except Exception:
                                        traceback.print_exc()
                            except Exception:
                                pass
                except Exception:
                    traceback.print_exc()
            except Exception:
                traceback.print_exc()
        except Exception as e:
            QMessageBox.critical(self, 'Save Error', str(e))
            return
        self.accept()
