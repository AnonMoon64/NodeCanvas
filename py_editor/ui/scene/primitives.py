"""
primitives.py

The primitives tree for drag-and-drop object creation.
"""
from PyQt6.QtWidgets import QTreeWidget, QTreeWidgetItem
from PyQt6.QtCore import Qt, QMimeData
from PyQt6.QtGui import QDrag

class PrimitiveTree(QTreeWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.setDragEnabled(True)
        self._populate()

    def _populate(self):
        categories = {
            "Shapes": ["Cube", "Sphere", "Cylinder", "Plane"],
            "Environment": ["Landscape", "Ocean", "Ocean World", "Cloud Layer",
                            "Atmosphere", "Universe", "Voxel World"],
            "Lights": ["Point Light", "Directional Light"],
            "Camera": ["Camera"]
        }
        for cat, items in categories.items():
            root = QTreeWidgetItem([cat])
            root.setExpanded(True)
            for item in items:
                child = QTreeWidgetItem([item])
                child.setData(0, Qt.ItemDataRole.UserRole, item.lower().replace(" ", "_"))
                root.addChild(child)
            self.addTopLevelItem(root)

    def startDrag(self, actions):
        item = self.currentItem()
        if not item or not item.data(0, Qt.ItemDataRole.UserRole): return
        drag = QDrag(self)
        mime = QMimeData()
        mime.setText(f"prim:{item.data(0, Qt.ItemDataRole.UserRole)}")
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.CopyAction)
