from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTreeWidget,
    QTreeWidgetItem, QMenu, QInputDialog, QMessageBox, QComboBox, QLineEdit
)
from PyQt6.QtCore import Qt, pyqtSignal, QMimeData, QPoint
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
        self.tree.setColumnCount(4)
        self.tree.setHeaderLabels(["Name", "", "Type", "Value"])
        self.tree.setHeaderHidden(False)
        self.tree.setIndentation(0)
        self.tree.setColumnWidth(0, 110)
        self.tree.setColumnWidth(1, 40) # Container icon/selector
        self.tree.setColumnWidth(2, 70) # Base Type
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
        
        container_types = ["Single", "Array", "Map"]
        base_types = ["int", "float", "bool", "string", "vector2", "vector3", "any"]

        for name, info in self.canvas.graph_variables.items():
            full_type = info.get('type', 'float')
            
            # Split container:type or map:key:val
            container = "Single"
            base_type = full_type
            if full_type.startswith("array:"):
                container = "Array"
                base_type = full_type.split(":", 1)[1]
            elif full_type.startswith("map:"):
                container = "Map"
                base_type = full_type.split(":", 1)[1]
            
            val_data = info.get('value', '')
            val_display = "" if container != "Single" else str(val_data)
            
            item = QTreeWidgetItem([name, "", base_type, val_display])
            item.setData(0, Qt.ItemDataRole.UserRole, name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
            self.tree.addTopLevelItem(item)

            # Container Selector (Col 1)
            c_combo = QComboBox()
            c_combo.addItems(["●", "≡", "▦"]) # Single, Array, Map
            c_combo.setToolTip("Container Type (Single, Array, Map)")
            c_combo.setCurrentIndex(container_types.index(container) if container in container_types else 0)
            c_combo.setFixedWidth(28)
            c_combo.setStyleSheet("QComboBox { background: transparent; color: #ffcc00; border: none; font-weight: bold; } QComboBox::drop-down { border: none; }")
            
            def update_container(idx, n=name):
                info = self.canvas.graph_variables[n]
                old_type = info['type']
                cur_base = old_type.split(":")[-1]
                ct = container_types[idx]
                if ct == "Array": 
                    new_type = f"array:{cur_base}"
                    if not isinstance(info.get('value'), list): info['value'] = []
                elif ct == "Map": 
                    new_type = f"map:{cur_base}:any"
                    if not isinstance(info.get('value'), dict): info['value'] = {}
                else: 
                    new_type = cur_base
                    # If it was array, take first or default
                    if isinstance(info.get('value'), list):
                        info['value'] = info['value'][0] if info['value'] else 0
                
                if new_type != old_type:
                    info['type'] = new_type
                    self.variable_changed.emit()
                    self.refresh()
            
            c_combo.currentIndexChanged.connect(update_container)
            self.tree.setItemWidget(item, 1, c_combo)

            # Base Type Selector (Col 2)
            t_combo = QComboBox()
            t_combo.addItems(base_types)
            t_combo.setCurrentText(base_type)
            t_combo.setStyleSheet("QComboBox { background: transparent; color: #569cd6; border: none; } QComboBox::drop-down { border: none; }")
            
            def update_base_type(txt, n=name):
                info = self.canvas.graph_variables[n]
                old_type = info['type']
                if old_type.startswith("array:"): new_t = f"array:{txt}"
                elif old_type.startswith("map:"): new_t = f"map:{txt}:any"
                else: new_t = txt
                
                if new_t != old_type:
                    info['type'] = new_t
                    self.variable_changed.emit()
            
            t_combo.currentTextChanged.connect(update_base_type)
            self.tree.setItemWidget(item, 2, t_combo)

            # Special Value Handling for Array/Map
            if container == "Array":
                # Add a '+' button in Value column for the parent
                add_elem_btn = QPushButton("+")
                add_elem_btn.setFixedSize(16, 16)
                add_elem_btn.setStyleSheet("QPushButton { background: #3c3c3c; border: none; color: #fff; font-size: 10px; border-radius: 2px; } QPushButton:hover { background: #505050; }")
                def add_elem(checked, n=name):
                    v = self.canvas.graph_variables[n]
                    if not isinstance(v['value'], list): v['value'] = []
                    # push default based on base type
                    bt = v['type'].split(":")[-1]
                    def_val = 0 if bt == 'int' else 0.0 if bt == 'float' else ""
                    v['value'].append(def_val)
                    self.refresh()
                    self.variable_changed.emit()
                add_elem_btn.clicked.connect(add_elem)
                self.tree.setItemWidget(item, 3, add_elem_btn)
                
                # Add child items for each element
                item.setExpanded(True)
                for i, elem_val in enumerate(val_data if isinstance(val_data, list) else []):
                    child = QTreeWidgetItem([f"  Index {i}", "", "", str(elem_val)])
                    child.setFlags(child.flags() | Qt.ItemFlag.ItemIsEditable)
                    child.setData(0, Qt.ItemDataRole.UserRole, f"{name}:elem:{i}")
                    item.addChild(child)
                    
                    # Remove button for element
                    rem_btn = QPushButton("-")
                    rem_btn.setFixedSize(14, 14)
                    rem_btn.setStyleSheet("QPushButton { background: #442222; border: none; color: #fff; font-size: 10px; border-radius: 2px; }")
                    def rem_elem(checked, idx=i, n=name):
                        v = self.canvas.graph_variables[n]
                        if isinstance(v['value'], list) and idx < len(v['value']):
                            v['value'].pop(idx)
                            self.refresh()
                            self.variable_changed.emit()
                    rem_btn.clicked.connect(rem_elem)
                    # We can't easily put widget in Col 0 without layout, but we can put it in Col 2 or use a custom menu
                    # Let's just use column 1 for '-' on children
                    self.tree.setItemWidget(child, 1, rem_btn)

            elif container == "Map":
                # Simlar but with Key/Value
                add_pair_btn = QPushButton("+")
                add_pair_btn.setFixedSize(16, 16)
                add_pair_btn.setStyleSheet("QPushButton { background: #3c3c3c; border: none; color: #fff; font-size: 10px; border-radius: 2px; }")
                def add_pair(checked, n=name):
                    v = self.canvas.graph_variables[n]
                    if not isinstance(v['value'], dict): v['value'] = {}
                    new_key = "key_" + str(len(v['value']))
                    v['value'][new_key] = 0
                    self.refresh()
                    self.variable_changed.emit()
                add_pair_btn.clicked.connect(add_pair)
                self.tree.setItemWidget(item, 3, add_pair_btn)
                
                item.setExpanded(True)
                for k, v in (val_data.items() if isinstance(val_data, dict) else {}):
                    child = QTreeWidgetItem([f"  {k}", "", "", str(v)])
                    child.setFlags(child.flags() | Qt.ItemFlag.ItemIsEditable)
                    child.setData(0, Qt.ItemDataRole.UserRole, f"{name}:key:{k}")
                    item.addChild(child)

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
        if column == 0: # Name
            self.tree.editItem(item, 0)
        elif column == 3: # Value
            self.tree.editItem(item, 3)

    def on_item_changed(self, item, column):
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data: return
        
        new_val = item.text(column)
        
        # Handle child items (Array elements or Map keys/values)
        if ":" in data:
            parts = data.split(":")
            var_name = parts[0]
            var_info = self.canvas.graph_variables.get(var_name)
            if not var_info: return
            
            if parts[1] == "elem":
                idx = int(parts[2])
                if column == 3: # Value updated
                    try:
                        bt = var_info['type'].split(":")[-1]
                        if bt == 'int': var_info['value'][idx] = int(new_val)
                        elif bt == 'float': var_info['value'][idx] = float(new_val)
                        else: var_info['value'][idx] = new_val
                        self.variable_changed.emit()
                    except (ValueError, IndexError):
                        item.setText(3, str(var_info['value'][idx]))
            
            elif parts[1] == "key":
                orig_key = parts[2]
                if column == 0: # Rename Key
                    new_key = new_val.strip()
                    if new_key and new_key != orig_key:
                        val = var_info['value'].pop(orig_key)
                        var_info['value'][new_key] = val
                        item.setData(0, Qt.ItemDataRole.UserRole, f"{var_name}:key:{new_key}")
                        self.variable_changed.emit()
                elif column == 3: # Update Value
                    try:
                        var_info['value'][orig_key] = new_val
                        self.variable_changed.emit()
                    except Exception:
                        item.setText(3, str(var_info['value'][orig_key]))
            return

        old_name = data
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
            else:
                item.setText(0, old_name)
                
        elif column == 3: # Value
            var_info = self.canvas.graph_variables.get(old_name)
            if var_info:
                # Coerce value based on type
                full_type = var_info.get('type', 'any')
                if full_type.startswith("array:") or full_type.startswith("map:"):
                    return # Handled by child items
                
                v_type = full_type.split(":")[-1]
                try:
                    if v_type == 'int': var_info['value'] = int(new_val)
                    elif v_type == 'float': var_info['value'] = float(new_val)
                    elif v_type == 'bool': var_info['value'] = new_val.lower() in ('true', '1', 'yes')
                    else: var_info['value'] = new_val
                    self.variable_changed.emit()
                except ValueError:
                    item.setText(3, str(var_info['value']))

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

