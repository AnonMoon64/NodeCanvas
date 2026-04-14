"""
explorer_panel.py

Extracted FileExplorerWidget from main.py.
"""
import json
from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTreeWidget,
    QTreeWidgetItem, QListWidget, QListWidgetItem, QScrollArea, QMenu, QInputDialog, QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal, QMimeData
from PyQt6.QtGui import QDrag

class CollapsibleSection(QWidget):
    """VS Code-style collapsible section with arrow indicator"""
    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.is_collapsed = False
        layout = QVBoxLayout(self); layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(0)
        self.header = QPushButton(f"▼ {title}")
        self.header.setStyleSheet("""
            QPushButton { background-color: #252526; color: #e0e0e0; border: none; text-align: left; padding: 6px 8px; font-weight: bold; font-size: 11px; }
            QPushButton:hover { background-color: #2a2d2e; }
        """)
        self.header.clicked.connect(self.toggle)
        self.title = title; layout.addWidget(self.header)
        self.content = QWidget(); self.content_layout = QVBoxLayout(self.content); self.content_layout.setContentsMargins(0, 0, 0, 0); self.content_layout.setSpacing(0)
        layout.addWidget(self.content)
    def toggle(self):
        self.is_collapsed = not self.is_collapsed
        self.content.setVisible(not self.is_collapsed)
        self.header.setText(f"{'▶' if self.is_collapsed else '▼'} {self.title}")
    def add_widget(self, widget): self.content_layout.addWidget(widget)

class FileExplorerWidget(QWidget):
    """VS Code-style file explorer."""
    file_selected = pyqtSignal(str)
    
    def __init__(self, root_path, parent=None):
        super().__init__(parent)
        self.root_path = Path(root_path); self.main_window = parent
        layout = QVBoxLayout(self); layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(0)
        
        # Explorer header
        header = QWidget(); h_layout = QHBoxLayout(header); h_layout.setContentsMargins(8, 6, 8, 6)
        h_layout.addWidget(QLabel("EXPLORER")); h_layout.addStretch()
        
        # Simplified Actions
        refresh_btn = QPushButton("↻"); refresh_btn.setFixedSize(20, 20); refresh_btn.clicked.connect(self.refresh)
        h_layout.addWidget(refresh_btn); layout.addWidget(header)
        
        # Scroll Area sections
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setStyleSheet("background-color: #252526; border: none;")
        scroll_content = QWidget(); self.sections_layout = QVBoxLayout(scroll_content)
        
        self.files_section = CollapsibleSection("PROJECT FILES")
        self.file_tree = QTreeWidget(); self.file_tree.setHeaderHidden(True)
        self.files_section.add_widget(self.file_tree)
        self.sections_layout.addWidget(self.files_section)
        
        self.sections_layout.addStretch(); scroll.setWidget(scroll_content); layout.addWidget(scroll)
        
        self.file_tree.itemExpanded.connect(self._on_item_expanded)
        self.file_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.file_tree.customContextMenuRequested.connect(self._on_context_menu)
        self._populate_tree()
        
        # Drag support
        self.file_tree.setDragEnabled(True)
        self.file_tree.mouseMoveEvent = self._on_mouse_move

    def _on_mouse_move(self, event):
        if event.buttons() != Qt.MouseButton.LeftButton: return
        item = self.file_tree.currentItem()
        if not item: return
        
        path_str = item.data(0, Qt.ItemDataRole.UserRole)
        if not path_str: return
        
        path = Path(path_str)
        if path.is_dir(): return
        
        drag = QDrag(self)
        mime = QMimeData()
        
        if path.suffix == '.logic':
            mime.setData("application/x-nodecanvas-graph", path_str.encode('utf-8'))
            mime.setText(f"logic:{path_str}")
        elif path.suffix == '.scene':
             mime.setText(f"scene:{path_str}")
        else:
             mime.setText(path_str)
             
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.CopyAction)

    def _populate_tree(self):
        self.file_tree.clear()
        root = QTreeWidgetItem([f"📁 {self.root_path.name}"])
        root.setData(0, Qt.ItemDataRole.UserRole, str(self.root_path))
        self.file_tree.addTopLevelItem(root)
        self._add_dummy(root)
        root.setExpanded(True)

    def _add_dummy(self, item):
        item.addChild(QTreeWidgetItem(["Loading..."]))

    def _on_item_expanded(self, item):
        path_str = item.data(0, Qt.ItemDataRole.UserRole)
        if not path_str: return
        
        path = Path(path_str)
        # Clear dummy/existing
        item.takeChildren()
        
        try:
            for entry in sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
                if entry.name.startswith('.'): continue
                child = QTreeWidgetItem([f"{'📁' if entry.is_dir() else '📄'} {entry.name}"])
                child.setData(0, Qt.ItemDataRole.UserRole, str(entry))
                item.addChild(child)
                if entry.is_dir():
                    self._add_dummy(child)
        except PermissionError:
            error_item = QTreeWidgetItem(["🚫 Permission Denied"])
            error_item.setForeground(0, Qt.GlobalColor.red)
            item.addChild(error_item)
        except Exception as e:
            item.addChild(QTreeWidgetItem([f"❌ Error: {str(e)}"]))

    def _on_context_menu(self, pos):
        item = self.file_tree.itemAt(pos)
        path_str = item.data(0, Qt.ItemDataRole.UserRole) if item else str(self.root_path)
        path = Path(path_str)
        if not path.is_dir(): path = path.parent
        
        menu = QMenu(self)
        menu.setStyleSheet("background-color: #252526; color: #ccc;")
        
        new_logic = menu.addAction("New Logic Graph")
        new_scene = menu.addAction("New Scene")
        menu.addSeparator()
        new_mat = menu.addAction("Create Material")
        new_prefab = menu.addAction("Create Prefab")
        
        action = menu.exec(self.file_tree.mapToGlobal(pos))
        if not action: return
        
        name, ok = QInputDialog.getText(self, "New File", "Name:")
        if not ok or not name: return
        
        if action == new_logic:
            file_path = path / f"{name}.logic"
            content = {"nodes": [], "connections": [], "variables": {}}
        elif action == new_scene:
            file_path = path / f"{name}.scene"
            content = {"objects": []}
        elif action == new_mat:
            file_path = path / f"{name}.mat"
            content = {"base_color": [1.0, 1.0, 1.0, 1.0], "roughness": 0.5, "metallic": 0.0}
        elif action == new_prefab:
            file_path = path / f"{name}.prefab"
            content = {"type": "prefab", "root": {}}
        else: return
        
        with open(file_path, 'w') as f:
            json.dump(content, f, indent=4)
        self.refresh()

    def refresh(self): self._populate_tree()
