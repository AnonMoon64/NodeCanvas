from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QScrollArea, QGroupBox, QLineEdit, QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal

PROPS_SS = """
QGroupBox {
    color: #4fc3f7;
    font-weight: bold;
    border: 1px solid #3c3c3c;
    margin-top: 1.1em;
    padding-top: 5px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 3px 0 3px;
}
"""

class NodePropertiesPanel(QWidget):
    """The Right-side properties inspector for Logic Nodes."""
    property_changed = pyqtSignal()
    
    def __init__(self, logic_editor, parent=None):
        super().__init__(parent)
        self.logic_editor = logic_editor
        self._current_node = None
        self._updating = False
        
        self.setStyleSheet("background: #252526;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        layout.addWidget(self._scroll)
        
        content = QWidget()
        self.content_layout = QVBoxLayout(content)
        self.content_layout.setContentsMargins(4, 4, 4, 4)
        self.content_layout.setSpacing(8)
        
        self._title = QLabel("  No Node Selected")
        self._title.setFixedHeight(24)
        self._title.setStyleSheet("color: #888; font-size: 11px; font-weight: bold;")
        self.content_layout.addWidget(self._title)
        
        self.meta_group = QGroupBox("Node Meta")
        self.meta_group.setStyleSheet(PROPS_SS)
        self.mg_layout = QVBoxLayout(self.meta_group)
        self.content_layout.addWidget(self.meta_group)
        self.meta_group.hide()
        
        self.variadic_group = QGroupBox("Variadic Inputs")
        self.variadic_group.setStyleSheet(PROPS_SS)
        self.vg_layout = QVBoxLayout(self.variadic_group)
        self.content_layout.addWidget(self.variadic_group)
        self.variadic_group.hide()
        
        self.content_layout.addStretch()
        self._scroll.setWidget(content)
        
    def set_node(self, node):
        self._current_node = node
        if not node:
            self._title.setText("  No Node Selected")
            self.variadic_group.hide()
            return
            
        self._updating = True
        tname = getattr(node, 'template_name', 'Node')
        self._title.setText(f"  {tname} (ID: {node.id})")
        
        # Metadata
        self.meta_group.show()
        self._refresh_meta_ui()

        is_variadic = tname in ('SelectInt', 'StringAppend')
        if is_variadic:
            self.variadic_group.show()
            self._refresh_variadic_ui()
        else:
            self.variadic_group.hide()
            
        self._updating = False

    def _refresh_meta_ui(self):
        # Clear
        while self.mg_layout.count():
            item = self.mg_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()
            elif item.layout():
                while item.layout().count():
                    child = item.layout().takeAt(0)
                    if child.widget(): child.widget().deleteLater()
        
        node = self._current_node
        
        # Category Row
        row = QHBoxLayout()
        row.addWidget(QLabel("Category:"))
        cat_edit = QLineEdit(getattr(node, 'category', 'General'))
        cat_edit.setStyleSheet("background: #1e1e1e; color: #ccc; border: 1px solid #3c3c3c;")
        def update_cat(v):
            node.category = v
            self.logic_editor.value_changed.emit()
        cat_edit.textChanged.connect(update_cat)
        row.addWidget(cat_edit)
        self.mg_layout.addLayout(row)
        
        save_btn = QPushButton("Save to Template")
        save_btn.setStyleSheet("background: #3c3c3c; color: #ccc; margin-top: 5px;")
        def save_meta():
            try:
                from py_editor.core.node_templates import get_template, save_template
                tmpl = get_template(node.template_name)
                if tmpl:
                    tmpl['category'] = node.category
                    save_template(tmpl)
                    QMessageBox.information(self, "Success", f"Updated template '{node.template_name}' category to '{node.category}'")
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to save template: {e}")
        save_btn.clicked.connect(save_meta)
        self.mg_layout.addWidget(save_btn)
        
    def _refresh_variadic_ui(self):
        # Clear
        while self.vg_layout.count():
            child = self.vg_layout.takeAt(0)
            if child.widget(): child.widget().deleteLater()
            elif child.layout():
                while child.layout().count():
                    item = child.layout().takeAt(0)
                    if item.widget(): item.widget().deleteLater()
        
        node = self._current_node
        tname = node.template_name
        prefix = 'option' if tname == 'SelectInt' else 'str'
        dyn_pins = sorted([p for p in node.inputs if p.startswith(prefix)], 
                         key=lambda x: int(x.replace(prefix, '')))
        
        for p in dyn_pins:
            row = QHBoxLayout()
            lbl = QLabel(p)
            lbl.setStyleSheet("color: #aaa; font-size: 10px;")
            row.addWidget(lbl)
            
            # Show connection status or value
            val = node.pin_values.get(p, '')
            edit = QLineEdit(str(val))
            edit.setFixedWidth(80)
            edit.setStyleSheet("background: #1e1e1e; color: #ccc; border: 1px solid #3c3c3c; font-size: 9px;")
            def update_val(v, pin=p):
                node.pin_values[pin] = v
                self._updating = True
                self.property_changed.emit()
                self._updating = False
            edit.textChanged.connect(update_val)
            row.addWidget(edit)
            
            del_btn = QPushButton("X")
            del_btn.setFixedSize(20, 20)
            del_btn.setStyleSheet("background: #442222; color: white; border: none; font-weight: bold;")
            del_btn.clicked.connect(lambda _, pin=p: self._remove_input(pin))
            row.addWidget(del_btn)
            
            self.vg_layout.addLayout(row)
            
        add_btn = QPushButton("+ Add Input")
        add_btn.setStyleSheet("background: #2d5a27; color: white; padding: 4px; border-radius: 3px;")
        add_btn.clicked.connect(self._add_input)
        self.vg_layout.addWidget(add_btn)
        
    def _add_input(self):
        node = self._current_node
        tname = node.template_name
        prefix = 'option' if tname == 'SelectInt' else 'str'
        pin_type = 'any' if tname == 'SelectInt' else 'string'
        idx = 0
        while f"{prefix}{idx}" in node.inputs:
            idx += 1
        node.inputs[f"{prefix}{idx}"] = pin_type
        node.setup_pins(node.inputs, node.outputs)
        self.logic_editor.update_connections_for_node(node)
        self.logic_editor.value_changed.emit()
        self._refresh_variadic_ui()
        
    def _remove_input(self, pin_name):
        node = self._current_node
        if pin_name in node.inputs:
            # Disconnect
            for conn in list(self.logic_editor.connections):
                if conn.to_node == node and conn.to_pin == pin_name:
                    conn.remove()
                    self.logic_editor.connections.remove(conn)
            del node.inputs[pin_name]
            node.setup_pins(node.inputs, node.outputs)
            self.logic_editor.update_connections_for_node(node)
            self.logic_editor.value_changed.emit()
            self._refresh_variadic_ui()
