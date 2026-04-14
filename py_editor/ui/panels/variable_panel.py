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
        self.add_btn.setStyleSheet("QPushButton { border: none; color: #ccc; } QPushButton:hover { background: #3c3c3c; }")
        self.add_btn.clicked.connect(self.add_variable)
        h_layout.addWidget(self.add_btn)
        
        layout.addWidget(header)
        
        # Tree
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(0)
        self.tree.setStyleSheet("""
            QTreeWidget { background: #1e1e1e; border: none; color: #ccc; }
            QTreeWidget::item { padding: 6px; border-bottom: 1px solid #2d2d2d; }
            QTreeWidget::item:hover { background: #2a2d2e; }
            QTreeWidget::item:selected { background: #37373d; }
        """)
        self.tree.setDragEnabled(True)
        self.tree.mouseMoveEvent = self._on_mouse_move
        self.tree.itemDoubleClicked.connect(self.edit_variable)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.show_context_menu)
        
        layout.addWidget(self.tree)
        self.refresh()

    def refresh(self):
        self.tree.clear()
        if not hasattr(self.canvas, 'graph_variables'): return
        
        for name, info in self.canvas.graph_variables.items():
            type_str = info.get('type', 'any')
            val = info.get('value', '')
            item = QTreeWidgetItem([f"{name} ({type_str}) : {val}"])
            item.setData(0, Qt.ItemDataRole.UserRole, name)
            self.tree.addTopLevelItem(item)

    def add_variable(self):
        name, ok = QInputDialog.getText(self, "New Variable", "Variable Name:")
        if ok and name:
            if not hasattr(self.canvas, 'graph_variables'): self.canvas.graph_variables = {}
            self.canvas.graph_variables[name] = {"type": "float", "value": 0.0}
            self.refresh()
            self.variable_changed.emit()

    def edit_variable(self, item):
        name = item.data(0, Qt.ItemDataRole.UserRole)
        # Simple for now - type selector + value
        msg = f"Edit variable: {name}"
        # In a real impl, we'd open a nicer dialog. For now, just type change
        new_type, ok = QInputDialog.getItem(self, "Variable Type", "Type:", ["int", "float", "bool", "string"], 1, False)
        if ok:
             self.canvas.graph_variables[name]['type'] = new_type
             self.refresh()
             self.variable_changed.emit()

    def show_context_menu(self, pos):
        item = self.tree.itemAt(pos)
        if not item: return
        name = item.data(0, Qt.ItemDataRole.UserRole)
        
        menu = QMenu()
        menu.setStyleSheet("background-color: #252526; color: #ccc;")
        
        dup_act = menu.addAction("Duplicate Variable")
        rename_act = menu.addAction("Rename...")
        menu.addSeparator()
        del_act = menu.addAction("Delete Variable")
        
        action = menu.exec(self.tree.mapToGlobal(pos))
        if action == del_act:
            self.delete_variable(name)
        elif action == rename_act:
            new_name, ok = QInputDialog.getText(self, "Rename Variable", "New Name:", text=name)
            if ok and new_name and new_name != name:
                # Basic rename logic
                info = self.canvas.graph_variables.pop(name)
                self.canvas.graph_variables[new_name] = info
                self.refresh()
                self.variable_changed.emit()
        elif action == dup_act:
             import copy
             info = copy.deepcopy(self.canvas.graph_variables[name])
             dup_name = name + "_Copy"
             # Increment if already exists
             it = 1
             while dup_name in self.canvas.graph_variables:
                 dup_name = f"{name}_Copy_{it}"
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
        drag = QDrag(self)
        mime = QMimeData()
        # Custom format for logic canvas drops
        mime.setText(f"variable:{name}")
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.CopyAction)
