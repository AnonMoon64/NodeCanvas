"""
outliner.py

A tree-based hierarchy explorer for scene objects.
"""
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QTreeWidget, QTreeWidgetItem, QMenu
from PyQt6.QtCore import Qt, pyqtSignal
from py_editor.ui.scene.object_system import SceneObject

class SceneOutliner(QWidget):
    """Hierarchy view for managing and selecting scene objects."""
    object_selected = pyqtSignal(object)
    object_deleted = pyqtSignal(object)
    object_renamed = pyqtSignal(object, str)
    object_duplicated = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
        self.tree.setStyleSheet("""
            QTreeWidget { background: #252526; border: none; color: #ccc; }
            QTreeWidget::item { padding: 4px; border-bottom: 1px solid #2a2d2e; }
            QTreeWidget::item:selected { background: #37373d; color: #fff; }
        """)
        
        self.tree.itemSelectionChanged.connect(self._on_selection_changed)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._on_context_menu)
        
        self.layout.addWidget(self.tree)
        
        # Enable dragging for scene objects
        self.tree.setDragEnabled(True)
        self.tree.setDragDropMode(QTreeWidget.DragDropMode.DragOnly)
        self.tree.startDrag = self._start_drag
        
        self._objects = []
        self._updating = False

    def set_objects(self, objects):
        if self._updating: return
        self._updating = True
        
        self.tree.blockSignals(True)
        # Differential update: only clear if count or identity changed
        if len(objects) != self.tree.topLevelItemCount():
            self.tree.clear()
            for obj in objects:
                item = QTreeWidgetItem([f"{self._get_icon(obj.obj_type)} {obj.name}"])
                item.setData(0, Qt.ItemDataRole.UserRole, obj)
                self.tree.addTopLevelItem(item)
                item.setSelected(obj.selected)
        else:
            # Sync selection state without clearing
            for i in range(self.tree.topLevelItemCount()):
                item = self.tree.topLevelItem(i)
                obj = item.data(0, Qt.ItemDataRole.UserRole)
                # Ensure name matches (in case it changed)
                item.setText(0, f"{self._get_icon(obj.obj_type)} {obj.name}")
                if item.isSelected() != obj.selected:
                    item.setSelected(obj.selected)
        
        self.tree.blockSignals(False)
        self._updating = False

    def _start_drag(self, actions):
        item = self.tree.currentItem()
        if not item: return
        obj = item.data(0, Qt.ItemDataRole.UserRole)
        if not obj: return
        
        from PyQt6.QtCore import QMimeData
        from PyQt6.QtGui import QDrag
        
        mime_data = QMimeData()
        # Set a custom format consistent with what canvas.py expects
        data_str = f"scene_object:{obj.id}:{obj.name}"
        mime_data.setData("application/x-nodecanvas-scene-object", data_str.encode('utf-8'))
        mime_data.setText(data_str) # Fallback for text drops
        
        drag = QDrag(self)
        drag.setMimeData(mime_data)
        drag.exec(Qt.DropAction.CopyAction)

    def _get_icon(self, otype):
        icons = {
            'cube': '📦', 'sphere': '⚪', 'plane': '▭', 'cylinder': '⬡',
            'ocean': '🌊', 'ocean_world': '🌐', 'landscape': '🌍',
            'atmosphere': '🌌', 'universe': '🌌', 'voxel_world': '🏔️',
            'cloud_layer': '☁', 'clouds': '☁',
            'camera': '🎥', 'light_point': '💡', 'light_directional': '☀',
        }
        return icons.get(otype, '📄')

    def _on_selection_changed(self):
        if self._updating: return
        items = self.tree.selectedItems()
        # Always emit — even with one item, the scene needs to know
        if items:
            obj = items[0].data(0, Qt.ItemDataRole.UserRole)
            if obj is not None:
                self.object_selected.emit(obj)
            else:
                self.object_selected.emit(None)
        else:
            self.object_selected.emit(None)

    def _on_context_menu(self, pos):
        item = self.tree.itemAt(pos)
        if not item: return
        obj = item.data(0, Qt.ItemDataRole.UserRole)
        
        menu = QMenu(self)
        menu.setStyleSheet("background-color: #252526; color: #ccc;")
        
        dup_action = menu.addAction(f"Duplicate {obj.name}")
        rename_action = menu.addAction(f"Rename...")
        menu.addSeparator()
        del_action = menu.addAction(f"Delete")
        
        action = menu.exec(self.tree.mapToGlobal(pos))
        if action == del_action:
            self.object_deleted.emit(obj)
        elif action == rename_action:
            from PyQt6.QtWidgets import QInputDialog
            new_name, ok = QInputDialog.getText(self, "Rename Object", "New Name:", text=obj.name)
            if ok and new_name:
                self.object_renamed.emit(obj, new_name)
        elif action == dup_action:
            self.object_duplicated.emit(obj)
