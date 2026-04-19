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
    QFileDialog, QApplication, QDialog, QDoubleSpinBox, QDialogButtonBox, QComboBox, QCheckBox
)
from PyQt6.QtCore import Qt, pyqtSignal, QMimeData
from PyQt6.QtGui import QDrag

from py_editor.core.mesh_converter import MeshConverter

class MeshImportDialog(QDialog):
    """Small popup to set scale/rotation before mesh conversion."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Import Settings")
        self.setFixedWidth(280)
        self.setStyleSheet("background-color: #252526; color: #eee; border: 1px solid #444;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        SPIN_SS = "background: #1e1e1e; border: 1px solid #333; color: #4fc3f7; padding: 2px;"

        def add_row(label):
            row = QHBoxLayout()
            lbl = QLabel(label); lbl.setFixedWidth(80)
            row.addWidget(lbl)
            return row

        # Scale
        scale_row = add_row("Global Scale:")
        self.scale_spin = QDoubleSpinBox()
        self.scale_spin.setRange(0.00001, 10000.0); self.scale_spin.setValue(1.0); self.scale_spin.setDecimals(5)
        self.scale_spin.setStyleSheet(SPIN_SS)
        scale_row.addWidget(self.scale_spin)
        layout.addLayout(scale_row)

        # Up-axis preset — the common "upside-down" source is a Z-up FBX
        # being dropped into our Y-up scene. Choosing Z-up bakes a -90° X
        # rotation into the mesh so the model stands upright.
        ax_row = add_row("Up Axis (source):")
        self.up_axis = QComboBox()
        self.up_axis.addItems(["Y-up (default)", "Z-up → rotate -90° X", "-Z-up → rotate +90° X"])
        self.up_axis.setStyleSheet(SPIN_SS)
        ax_row.addWidget(self.up_axis)
        layout.addLayout(ax_row)

        self.flip_chk = QCheckBox("Flip upside-down (extra 180° around X)")
        layout.addWidget(self.flip_chk)

        layout.addWidget(QLabel("Extra Rotation (Euler XYZ Degrees):"))
        h = QHBoxLayout()
        self.rx = QDoubleSpinBox(); self.ry = QDoubleSpinBox(); self.rz = QDoubleSpinBox()
        for s in [self.rx, self.ry, self.rz]:
            s.setRange(-360, 360); s.setStyleSheet(SPIN_SS)
        h.addWidget(self.rx); h.addWidget(self.ry); h.addWidget(self.rz)
        layout.addLayout(h)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_values(self):
        # Compose Up-axis preset + flip + manual offsets into a single XYZ tuple.
        rx, ry, rz = self.rx.value(), self.ry.value(), self.rz.value()
        idx = self.up_axis.currentIndex()
        if idx == 1:    # Z-up → rotate -90° around X
            rx += -90.0
        elif idx == 2:  # -Z-up → +90°
            rx += 90.0
        if self.flip_chk.isChecked():
            rx += 180.0
        return self.scale_spin.value(), (rx, ry, rz)

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
        elif path.suffix == '.spawner':
             mime.setText(f"spawner:{path_str}")
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

    def _get_expanded_paths(self):
        """Recursively gather paths of all expanded items."""
        expanded = set()
        def _walk(item):
            if item.isExpanded():
                path = item.data(0, Qt.ItemDataRole.UserRole)
                if path: expanded.add(path)
                for i in range(item.childCount()):
                    _walk(item.child(i))
        
        for i in range(self.file_tree.topLevelItemCount()):
            _walk(self.file_tree.topLevelItem(i))
        return expanded

    def _restore_expanded_state(self, item, expanded_paths):
        """Recursively re-expand items in the saved set."""
        if not item: return
        path = item.data(0, Qt.ItemDataRole.UserRole)
        if path in expanded_paths:
            item.setExpanded(True)
            # Children are populated by the itemExpanded signal
            for i in range(item.childCount()):
                self._restore_expanded_state(item.child(i), expanded_paths)

    def _get_expanded_paths(self):
        """Recursively gather paths of all expanded items."""
        expanded = set()
        def _walk(item):
            if item.isExpanded():
                path = item.data(0, Qt.ItemDataRole.UserRole)
                if path: expanded.add(path)
                for i in range(item.childCount()):
                    _walk(item.child(i))
        
        for i in range(self.file_tree.topLevelItemCount()):
            _walk(self.file_tree.topLevelItem(i))
        return expanded

    def _restore_expanded_state(self, item, expanded_paths):
        """Recursively re-expand items in the saved set."""
        if not item: return
        path = item.data(0, Qt.ItemDataRole.UserRole)
        if path in expanded_paths:
            item.setExpanded(True)
            # Children are populated by the itemExpanded signal
            for i in range(item.childCount()):
                self._restore_expanded_state(item.child(i), expanded_paths)

    def _on_item_double_clicked(self, item):
        path_str = item.data(0, Qt.ItemDataRole.UserRole)
        if not path_str: return
        path = Path(path_str)
        if path.is_dir(): return
        
        # Determine type
        if path.suffix == ".prefab":
            self.file_opened.emit(path_str, "prefab")
        elif path.suffix == ".material":
            self.file_opened.emit(path_str, "material")
        elif path.suffix == ".logic":
            self.file_opened.emit(path_str, "logic")
        elif path.suffix == ".scene":
            # Open scenes in the Scene editor
            self.file_opened.emit(path_str, "scene")
        elif path.suffix == ".spawner":
            self.file_opened.emit(path_str, "spawner")

    def _on_context_menu(self, pos):
        item = self.file_tree.itemAt(pos)
        selected_path = Path(item.data(0, Qt.ItemDataRole.UserRole)) if item else Path(self.root_path)

        menu = QMenu(self)
        menu.setStyleSheet("background-color: #252526; color: #ccc;")

        convert_mesh = None

        is_dir = selected_path.is_dir()
        is_root = (selected_path == self.root_path)

        open_action = None
        rename_action = None
        duplicate_action = None
        copy_path_action = None
        delete_action = None
        new_folder = None
        new_logic = None
        new_mat = None
        new_prefab = None
        new_spawner = None
        refresh_action = None

        if not is_root:
            if not is_dir:
                open_action = menu.addAction("Open")
            rename_action = menu.addAction("Rename")
            if not is_dir:
                duplicate_action = menu.addAction("Duplicate")
            copy_path_action = menu.addAction("Copy Path")
            delete_action = menu.addAction("Delete")
            menu.addSeparator()

        if is_dir:
            new_folder = menu.addAction("New Folder")
            new_logic = menu.addAction("New Logic")
            new_mat = menu.addAction("Create Material")
            new_prefab = menu.addAction("Create Prefab")
            new_spawner = menu.addAction("Create Spawner")
            menu.addSeparator()

        if is_dir:
            if is_root or not any([open_action, rename_action]):
                 # if nothing else was added, add at least refresh
                 pass
        refresh_action = menu.addAction("Refresh")

        # Context-aware creations
        create_prefab_from_mesh = None
        create_material_from_texture = None
        
        if not is_dir:
            ext = selected_path.suffix.lower()
            if ext in ('.obj', '.fbx'):
                convert_mesh = menu.addAction("Create .mesh")
            elif ext == '.mesh':
                create_prefab_from_mesh = menu.addAction("Create Prefab from Mesh")
            elif ext in ('.png', '.jpg', '.jpeg', '.tga', '.dds'):
                create_material_from_texture = menu.addAction("Create Material from Texture")

        action = menu.exec(self.file_tree.mapToGlobal(pos))
        if not action: return

        # File actions
        # Actions that apply to both files AND folders
        if action == rename_action:
            new_name, ok = QInputDialog.getText(self, "Rename", "New name:", text=selected_path.name)
            if ok and new_name:
                try:
                    target = selected_path.with_name(new_name)
                    selected_path.rename(target)
                    self.refresh()
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Failed to rename: {e}")
            return

        if action == delete_action:
            ans = QMessageBox.question(self, "Delete", f"Delete {selected_path.name} (and all contents)?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
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

        if action == copy_path_action:
            QApplication.clipboard().setText(str(selected_path))
            return

        # File-only actions
        if not is_dir:
            if action == open_action:
                if selected_path.suffix == ".prefab":
                    self.file_opened.emit(str(selected_path), "prefab")
                elif selected_path.suffix == ".material":
                    self.file_opened.emit(str(selected_path), "material")
                elif selected_path.suffix == ".logic":
                    self.file_opened.emit(str(selected_path), "logic")
                elif selected_path.suffix == ".scene":
                    self.file_opened.emit(str(selected_path), "scene")
                elif selected_path.suffix == ".spawner":
                    self.file_opened.emit(str(selected_path), "spawner")
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

            if action == convert_mesh:
                self._handle_mesh_conversion(selected_path)
                return
            
            if action == create_prefab_from_mesh:
                self._handle_create_prefab_from_mesh(selected_path)
                return
                
            if action == create_material_from_texture:
                self._handle_create_material_from_texture(selected_path)
                return

        # Directory-only actions
        else:
            dir_path = selected_path
            if action == new_folder:
                name, ok = QInputDialog.getText(self, "New Folder", "Folder name:")
                if ok and name:
                    try:
                        (dir_path / name).mkdir(parents=True, exist_ok=True)
                        self.refresh()
                    except Exception as e:
                        QMessageBox.warning(self, "Error", f"Failed to create folder: {e}")
                return

            if action == new_logic:
                name, ok = QInputDialog.getText(self, "New Logic", "File name:")
                if ok and name:
                    try:
                        file_path = dir_path / (f"{name}.logic" if not name.endswith(".logic") else name)
                        with open(file_path, 'w') as f:
                            json.dump({"nodes": [], "connections": []}, f, indent=4)
                        self.refresh()
                    except Exception as e:
                        QMessageBox.warning(self, "Error", f"Failed to create logic: {e}")
                return

            if action == new_mat:
                name, ok = QInputDialog.getText(self, "Create Material", "Name:")
                if not ok or not name: return
                file_path = dir_path / (f"{name}.material" if not name.endswith(".material") else name)
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

            if action == new_spawner:
                name, ok = QInputDialog.getText(self, "Create Spawner", "Name:")
                if not ok or not name: return
                file_path = dir_path / f"{name}.spawner"
                content = {
                    "type": "spawner",
                    "prefabs": [],
                    "settings": {
                        "count": 5,
                        "radius": 10.0,
                        "min_offset": [0.0, 0.0, 0.0],
                        "max_offset": [0.0, 0.0, 0.0],
                        "min_tint": [1.0, 1.0, 1.0, 1.0],
                        "max_tint": [1.0, 1.0, 1.0, 1.0],
                        "find_ground": False
                    }
                }
                try:
                    with open(file_path, 'w') as f:
                        json.dump(content, f, indent=4)
                    self.refresh()
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Failed to create spawner: {e}")
                return

            if action == refresh_action:

                self.refresh()
                return

    def _handle_mesh_conversion(self, src_path):
        dest_path, _ = QFileDialog.getSaveFileName(self, "Save .mesh", str(src_path.with_suffix(".mesh")), "Mesh Files (*.mesh)")
        if not dest_path: return
        
        try:
            diag = MeshImportDialog(self)
            if not diag.exec():
                return
            
            scale, rot = diag.get_values()
            
            if src_path.suffix.lower() == '.obj':
                MeshConverter.obj_to_mesh(str(src_path), dest_path, scale=scale, rotation=rot)
                QMessageBox.information(self, "Success", f"Converted to: {Path(dest_path).name}")
            elif src_path.suffix.lower() == '.fbx':
                try:
                    MeshConverter.fbx_to_mesh(str(src_path), dest_path, scale=scale, rotation=rot)
                    QMessageBox.information(self, "Success", f"Converted FBX to: {Path(dest_path).name}")
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"FBX conversion failed: {e}")
            else:
                QMessageBox.warning(self, "Warning", "Unsupported source format for .mesh conversion.")
            self.refresh()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Conversion failed: {str(e)}")

    def _handle_create_prefab_from_mesh(self, mesh_path):
        from py_editor.core import paths as asset_paths
        rel_mesh = asset_paths.to_relative(str(mesh_path))
        prefab_path = mesh_path.with_suffix(".prefab")
        
        # Build minimal prefab
        content = {
            "type": "prefab",
            "root": {
                "name": mesh_path.stem,
                "type": "mesh",
                "mesh_path": rel_mesh,
                "logic_list": []
            }
        }
        
        try:
            with open(prefab_path, 'w') as f:
                json.dump(content, f, indent=4)
            self.refresh()
            QMessageBox.information(self, "Success", f"Created Prefab: {prefab_path.name}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to create prefab: {e}")

    def _handle_create_material_from_texture(self, tex_path):
        from py_editor.core import paths as asset_paths
        rel_tex = asset_paths.to_relative(str(tex_path))
        mat_path = tex_path.with_suffix(".material")
        
        # Build PBR-ready material
        content = {
            "base_color": [1.0, 1.0, 1.0, 1.0],
            "roughness": 0.5,
            "metallic": 0.0,
            "albedo": rel_tex
        }
        
        try:
            with open(mat_path, 'w') as f:
                json.dump(content, f, indent=4)
            self.refresh()
            QMessageBox.information(self, "Success", f"Created Material: {mat_path.name}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to create material: {e}")

    def refresh(self): 
        expanded = self._get_expanded_paths()
        self._populate_tree()
        for i in range(self.file_tree.topLevelItemCount()):
            self._restore_expanded_state(self.file_tree.topLevelItem(i), expanded)

    def set_root_path(self, path):
        """Repoint the explorer at a new project root and rebuild the tree."""
        self.root_path = Path(path)
        self._populate_tree()
