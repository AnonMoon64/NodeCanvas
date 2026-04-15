"""
explorer_panel.py

Extracted FileExplorerWidget from main.py.
"""
import json
import os
import sys
import shutil
import subprocess
from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTreeWidget,
    QTreeWidgetItem, QListWidget, QListWidgetItem, QScrollArea, QMenu, QInputDialog, QMessageBox,
    QFileDialog, QApplication
)
from PyQt6.QtCore import Qt, pyqtSignal, QMimeData
from PyQt6.QtGui import QDrag

from py_editor.core.mesh_converter import MeshConverter

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
    file_opened = pyqtSignal(str, str) # path, type
    
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
        self.file_tree.itemDoubleClicked.connect(self._on_item_double_clicked)
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

    def _on_item_double_clicked(self, item):
        path_str = item.data(0, Qt.ItemDataRole.UserRole)
        if not path_str: return
        path = Path(path_str)
        if path.is_dir(): return
        
        # Determine type
        if path.suffix == ".prefab":
            self.file_opened.emit(path_str, "prefab")
        elif path.suffix == ".mat":
            self.file_opened.emit(path_str, "material")
        elif path.suffix == ".logic":
            self.file_opened.emit(path_str, "logic")
        elif path.suffix == ".scene":
            # Open scenes in the Scene editor
            self.file_opened.emit(path_str, "scene")

    def _on_context_menu(self, pos):
        item = self.file_tree.itemAt(pos)
        selected_path = Path(item.data(0, Qt.ItemDataRole.UserRole)) if item else Path(self.root_path)

        menu = QMenu(self)
        menu.setStyleSheet("background-color: #252526; color: #ccc;")

        convert_mesh = None

        # If a file is selected, show file operations
        if selected_path and selected_path.exists() and not selected_path.is_dir():
            open_action = menu.addAction("Open")
            rename_action = menu.addAction("Rename")
            duplicate_action = menu.addAction("Duplicate")
            copy_path_action = menu.addAction("Copy Path")
            delete_action = menu.addAction("Delete")
            menu.addSeparator()
            if selected_path.suffix.lower() in ('.obj', '.fbx'):
                convert_mesh = menu.addAction("Create .mesh")
        else:
            # Directory selected — allow creating materials and prefabs
            target_dir = Path(selected_path) if selected_path and selected_path.is_dir() else Path(self.root_path)
            new_mat = menu.addAction("Create Material")
            new_prefab = menu.addAction("Create Prefab")
            menu.addSeparator()
            refresh_action = menu.addAction("Refresh")

        action = menu.exec(self.file_tree.mapToGlobal(pos))
        if not action: return

        # File actions
        if selected_path and selected_path.exists() and not selected_path.is_dir():
            if action == open_action:
                if selected_path.suffix == ".prefab":
                    self.file_opened.emit(str(selected_path), "prefab")
                elif selected_path.suffix == ".mat":
                    self.file_opened.emit(str(selected_path), "material")
                elif selected_path.suffix == ".logic":
                    self.file_opened.emit(str(selected_path), "logic")
                elif selected_path.suffix == ".scene":
                    # Open scenes inside the editor
                    self.file_opened.emit(str(selected_path), "scene")
                else:
                    try:
                        if os.name == 'nt':
                            os.startfile(str(selected_path))
                        elif sys.platform == 'darwin':
                            subprocess.Popen(['open', str(selected_path)])
                        else:
                            subprocess.Popen(['xdg-open', str(selected_path)])
                    except Exception:
                        QMessageBox.information(self, "Open", f"Cannot open: {selected_path}")
                return

            if action == rename_action:
                new_name, ok = QInputDialog.getText(self, "Rename", "New name:")
                if ok and new_name:
                    try:
                        target = selected_path.with_name(new_name)
                        selected_path.rename(target)
                        self.refresh()
                    except Exception as e:
                        QMessageBox.critical(self, "Error", f"Failed to rename: {e}")
                return

            if action == duplicate_action:
                base = selected_path.stem
                ext = selected_path.suffix
                it = 1
                new_name = f"{base}_Copy{ext}"
                target = selected_path.with_name(new_name)
                while target.exists():
                    new_name = f"{base}_Copy_{it}{ext}"
                    target = selected_path.with_name(new_name)
                    it += 1
                try:
                    shutil.copy2(str(selected_path), str(target))
                    self.refresh()
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Duplicate failed: {e}")
                return

            if action == copy_path_action:
                QApplication.clipboard().setText(str(selected_path))
                return

            if action == delete_action:
                ans = QMessageBox.question(self, "Delete", f"Delete {selected_path.name}?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                if ans == QMessageBox.StandardButton.Yes:
                    try:
                        if selected_path.is_dir():
                            shutil.rmtree(selected_path)
                        else:
                            selected_path.unlink()
                        self.refresh()
                    except Exception as e:
                        QMessageBox.critical(self, "Error", f"Delete failed: {e}")
                return

            if action == convert_mesh:
                self._handle_mesh_conversion(selected_path)
                return

        # Directory actions (create material/prefab, refresh)
        else:
            dir_path = Path(selected_path) if selected_path and selected_path.is_dir() else Path(self.root_path)
            if action == new_mat:
                name, ok = QInputDialog.getText(self, "Create Material", "Name:")
                if not ok or not name: return
                file_path = dir_path / f"{name}.mat"
                content = {"base_color": [1.0, 1.0, 1.0, 1.0], "roughness": 0.5, "metallic": 0.0}
                try:
                    with open(file_path, 'w') as f:
                        json.dump(content, f, indent=4)
                    self.refresh()
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Failed to create material: {e}")
                return

            if action == new_prefab:
                name, ok = QInputDialog.getText(self, "Create Prefab", "Name:")
                if not ok or not name: return
                file_path = dir_path / f"{name}.prefab"
                content = {
                    "type": "prefab",
                    "root": {
                        "name": name,
                        "type": "mesh",
                        "mesh_path": "",
                        "logic_list": []
                    }
                }
                try:
                    with open(file_path, 'w') as f:
                        json.dump(content, f, indent=4)
                    self.refresh()
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Failed to create prefab: {e}")
                return

            if action == refresh_action:
                self.refresh()
                return

    def _handle_mesh_conversion(self, src_path):
        dest_path, _ = QFileDialog.getSaveFileName(self, "Save .mesh", str(src_path.with_suffix(".mesh")), "Mesh Files (*.mesh)")
        if not dest_path: return
        
        try:
            if src_path.suffix.lower() == '.obj':
                MeshConverter.obj_to_mesh(str(src_path), dest_path)
                QMessageBox.information(self, "Success", f"Converted to: {Path(dest_path).name}")
            elif src_path.suffix.lower() == '.fbx':
                try:
                    MeshConverter.fbx_to_mesh(str(src_path), dest_path)
                    QMessageBox.information(self, "Success", f"Converted FBX to: {Path(dest_path).name}")
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"FBX conversion failed: {e}\n\nMake sure Blender is installed and on PATH, or set BLENDER_PATH env var.")
            else:
                QMessageBox.warning(self, "Warning", "Unsupported source format for .mesh conversion.")
            self.refresh()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Conversion failed: {str(e)}")

    def refresh(self): self._populate_tree()
