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
    object_focused = pyqtSignal(object) # New for double click

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
        self.tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._on_context_menu)
        
        self.layout.addWidget(self.tree)
        
        # Enable dragging and dropping for scene objects (parenting)
        self.tree.setDragEnabled(True)
        self.tree.setAcceptDrops(True)
        self.tree.setDragDropMode(QTreeWidget.DragDropMode.DragDrop)
        self.tree.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.tree.setDropIndicatorShown(True)
        self.tree.setDragEnabled(True)
        
        self._objects = []
        self._updating = False

    def set_objects(self, objects):
        if self._updating: return
        self._updating = True
        self._objects = objects
        
        self.tree.blockSignals(True)
        self.tree.clear()
        
        # Build hierarchy
        lookup = {obj.id: obj for obj in objects}
        items = {}
        
        # 1. Create all items
        for obj in objects:
            item = QTreeWidgetItem([f"{self._get_icon(obj.obj_type)} {obj.name}"])
            item.setData(0, Qt.ItemDataRole.UserRole, obj)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsDragEnabled | Qt.ItemFlag.ItemIsDropEnabled)
            items[obj.id] = item
            
        # 2. Arrange in tree
        for obj in objects:
            item = items[obj.id]
            parent_id = getattr(obj, 'parent_id', None)
            if parent_id and parent_id in items:
                items[parent_id].addChild(item)
            else:
                self.tree.addTopLevelItem(item)
                
            # Sync selection
            if obj.selected:
                item.setSelected(True)
                # Ensure parent is expanded if selected
                p = item.parent()
                while p:
                    p.setExpanded(True)
                    p = p.parent()
        
        self.tree.blockSignals(False)
        self._updating = False

    def _is_descendant(self, parent_obj_id, child_obj_id):
        """Recursively check if child_obj_id is an ancestor of parent_obj_id."""
        if not parent_obj_id or not child_obj_id: return False
        
        # Build child->parent map
        cmap = {o.id: getattr(o, 'parent_id', None) for o in self._objects}
        
        curr = cmap.get(parent_obj_id)
        while curr:
            if curr == child_obj_id: return True
            curr = cmap.get(curr)
        return False

    def dropEvent(self, event):
        """Handle parenting/unparenting with cycle detection."""
        target_item = self.tree.itemAt(event.position().toPoint())
        selected_items = self.tree.selectedItems()
        if not selected_items: return
        
        target_obj = target_item.data(0, Qt.ItemDataRole.UserRole) if target_item else None
        
        changed = False
        for item in selected_items:
            obj = item.data(0, Qt.ItemDataRole.UserRole)
            if not obj: continue
            
            # Avoid self-parenting
            if target_obj and target_obj.id == obj.id: continue
            
            # Avoid cycles (don't parent to child)
            if target_obj and self._is_descendant(target_obj.id, obj.id):
                print(f"[OUTLINER] Cycle blocked: {obj.name} -> {target_obj.name}")
                continue
                
            old_p = getattr(obj, 'parent_id', None)
            new_p = target_obj.id if target_obj else None
            
            if old_p != new_p:
                obj.parent_id = new_p
                changed = True

        if changed:
            # Rebuild tree with new hierarchy.
            # CRITICAL: We MUST defer this call using a timer. Calling self.tree.clear()
            # while the QTreeWidget is still processing the dropEvent causes a 
            # Windows Access Violation because the internal drag manager 
            # tries to access the items after we've deleted them.
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(0, lambda: self.set_objects(self._objects))
            
        event.acceptProposedAction()

    def _on_item_double_clicked(self, item, column):
        obj = item.data(0, Qt.ItemDataRole.UserRole)
        if obj:
            self.object_focused.emit(obj)

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
        if not items:
            self.object_selected.emit(None)
            return

        # Use a safe access pattern in case items are being garbage collected
        item = items[0]
        try:
            obj = item.data(0, Qt.ItemDataRole.UserRole)
            if isinstance(obj, SceneObject):
                self.object_selected.emit(obj)
            else:
                self.object_selected.emit(None)
        except (RuntimeError, AttributeError):
            # Happens if the item's underlying C++ object is already deleted
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
