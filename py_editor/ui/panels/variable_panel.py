from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTreeWidget,
    QTreeWidgetItem, QMenu, QInputDialog, QMessageBox, QComboBox
)
from PyQt6.QtCore import Qt, pyqtSignal, QMimeData
from PyQt6.QtGui import QDrag, QColor

class VariablePanel(QWidget):
    """List of graph-level variables for logic editing."""
    variable_changed = pyqtSignal()
    
    def __init__(self, canvas, parent=None):
        super().__init__(parent)
        self.canvas = canvas
        self.main_window = parent
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Header
        header = QWidget()
        header.setStyleSheet("background-color: #252526; border-bottom: 1px solid #3c3c3c;")
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(10, 6, 8, 6)
        
        lbl = QLabel("VARIABLES")
        lbl.setStyleSheet("font-weight: bold; color: #aaa; font-size: 10px;")
        h_layout.addWidget(lbl)
        h_layout.addStretch()
        
        self.add_btn = QPushButton("+")
        self.add_btn.setFixedSize(20, 20)
        self.add_btn.setStyleSheet("QPushButton { border: none; color: #ccc; font-size: 14px; } QPushButton:hover { background: #3c3c3c; }")
        self.add_btn.setToolTip("Add Variable")
        self.add_btn.clicked.connect(self.add_variable)
        h_layout.addWidget(self.add_btn)
        
        layout.addWidget(header)
        
        # Tree
        self.tree = QTreeWidget()
        self.tree.setColumnCount(3)
        self.tree.setHeaderLabels(["Name", "Type", "Value"])
        self.tree.setHeaderHidden(False)
        self.tree.setIndentation(0)
        self.tree.setColumnWidth(0, 100)
        self.tree.setColumnWidth(1, 60)
        self.tree.setStyleSheet("""
            QTreeWidget { background: #1e1e1e; border: none; color: #ccc; outline: none; }
            QTreeWidget::item { padding: 4px; border-bottom: 1px solid #2d2d2d; }
            QTreeWidget::item:hover { background: #2a2d2e; }
            QTreeWidget::item:selected { background: #37373d; }
            QHeaderView::section { 
                background-color: #252526; color: #aaa; 
                padding: 4px; border: none; border-right: 1px solid #3c3c3c;
                font-size: 10px; font-weight: bold;
            }
        """)
        self.tree.setDragEnabled(True)
        self.tree.mouseMoveEvent = self._on_mouse_move
        self.tree.itemDoubleClicked.connect(self.on_item_double_clicked)
        self.tree.itemChanged.connect(self.on_item_changed)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.show_context_menu)
        
        layout.addWidget(self.tree)
        self.refresh()
        
        # Connect to canvas changes
        if hasattr(self.canvas, 'value_changed'):
            self.canvas.value_changed.connect(self.refresh)
        if hasattr(self.canvas, 'graph_changed'):
            self.canvas.graph_changed.connect(self.refresh)

    def refresh(self):
        self.tree.blockSignals(True)
        self.tree.clear()
        if not hasattr(self.canvas, 'graph_variables'): 
             self.tree.blockSignals(False)
             return
        
        for name, info in self.canvas.graph_variables.items():
            type_str = info.get('type', 'any')
            val = str(info.get('value', ''))
            
            item = QTreeWidgetItem([name, type_str, val])
            item.setData(0, Qt.ItemDataRole.UserRole, name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
            # Make type column look slightly different or just allow edit
            item.setForeground(1, QColor("#569cd6")) # Blue-ish for type
            
            self.tree.addTopLevelItem(item)
        self.tree.blockSignals(False)

    def add_variable(self):
        """Create a new variable with a default name, UE5-style."""
        if not hasattr(self.canvas, 'graph_variables'): 
            self.canvas.graph_variables = {}
        
        # Find unique name
        base_name = "NewVar"
        idx = 0
        name = base_name
        while name in self.canvas.graph_variables:
            name = f"{base_name}_{idx}"
            idx += 1
            
        self.canvas.graph_variables[name] = {"type": "float", "value": 0.0}
        self.refresh()
        self.variable_changed.emit()
        
        # Trigger rename on the new item
        items = self.tree.findItems(name, Qt.MatchFlag.MatchExactly, 0)
        if items:
            self.tree.editItem(items[0], 0)

    def on_item_double_clicked(self, item, column):
        if column == 1:
            # Type column - show a quick selector or just let them type
            # UE5 uses a dropdown, but for now we can just use the default edit or a small menu
            self.show_type_selector(item)
        else:
            self.tree.editItem(item, column)

    def show_type_selector(self, item):
        name = item.data(0, Qt.ItemDataRole.UserRole)
        types = ["int", "float", "bool", "string", "any"]
        current = self.canvas.graph_variables[name]['type']
        
        new_type, ok = QInputDialog.getItem(self, "Variable Type", "Select Type:", types, types.index(current) if current in types else 0, False)
        if ok and new_type != current:
            self.canvas.graph_variables[name]['type'] = new_type
            # Reset value to default for new type
            defaults = {"int": 0, "float": 0.0, "bool": False, "string": "", "any": None}
            self.canvas.graph_variables[name]['value'] = defaults.get(new_type)
            self.refresh()
            self.variable_changed.emit()

    def on_item_changed(self, item, column):
        old_name = item.data(0, Qt.ItemDataRole.UserRole)
        new_val = item.text(column)
        
        if column == 0: # Rename
            if new_val and new_val != old_name:
                if new_val in self.canvas.graph_variables:
                    QMessageBox.warning(self, "Rename Error", f"Variable '{new_val}' already exists.")
                    self.refresh()
                    return
                
                info = self.canvas.graph_variables.pop(old_name)
                self.canvas.graph_variables[new_val] = info
                item.setData(0, Qt.ItemDataRole.UserRole, new_val)
                self.variable_changed.emit()
                print(f"Renamed variable: {old_name} -> {new_val}")
            else:
                item.setText(0, old_name)
                
        elif column == 2: # Value
            var_info = self.canvas.graph_variables.get(old_name)
            if var_info:
                # Coerce value based on type
                v_type = var_info.get('type', 'any')
                try:
                    if v_type == 'int': var_info['value'] = int(new_val)
                    elif v_type == 'float': var_info['value'] = float(new_val)
                    elif v_type == 'bool': var_info['value'] = new_val.lower() in ('true', '1', 'yes')
                    else: var_info['value'] = new_val
                    self.variable_changed.emit()
                    print(f"Updated variable {old_name} value to {var_info['value']}")
                except ValueError:
                    item.setText(2, str(var_info['value']))

    def show_context_menu(self, pos):
        item = self.tree.itemAt(pos)
        if not item: return
        name = item.data(0, Qt.ItemDataRole.UserRole)
        
        menu = QMenu()
        menu.setStyleSheet("QMenu { background-color: #252526; color: #ccc; border: 1px solid #3c3c3c; } QMenu::item:selected { background-color: #37373d; }")
        
        edit_act = menu.addAction("Edit...")
        rename_act = menu.addAction("Rename")
        dup_act = menu.addAction("Duplicate")
        menu.addSeparator()
        del_act = menu.addAction("Delete")
        
        action = menu.exec(self.tree.mapToGlobal(pos))
        if action == del_act:
            self.delete_variable(name)
        elif action == rename_act:
            self.tree.editItem(item, 0)
        elif action == edit_act:
            self.on_item_double_clicked(item, 0)
        elif action == dup_act:
             import copy
             info = copy.deepcopy(self.canvas.graph_variables[name])
             base_name = f"{name}_Copy"
             dup_name = base_name
             it = 1
             while dup_name in self.canvas.graph_variables:
                 dup_name = f"{base_name}_{it}"
                 it += 1
             self.canvas.graph_variables[dup_name] = info
             self.refresh()
             self.variable_changed.emit()

    def delete_variable(self, name):
        if name in self.canvas.graph_variables:
            del self.canvas.graph_variables[name]
            self.refresh()
            self.variable_changed.emit()

    def _on_mouse_move(self, event):
        if event.buttons() != Qt.MouseButton.LeftButton: return
        item = self.tree.currentItem()
        if not item: return
        
        name = item.data(0, Qt.ItemDataRole.UserRole)
        info = self.canvas.graph_variables.get(name, {})
        v_type = info.get('type', 'any')
        
        drag = QDrag(self)
        mime = QMimeData()
        # Custom format: variable:name:type
        mime.setText(f"variable:{name}:{v_type}")
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.CopyAction)

