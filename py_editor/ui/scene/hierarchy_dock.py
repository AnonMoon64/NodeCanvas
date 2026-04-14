from PyQt6.QtWidgets import QWidget, QVBoxLayout, QSplitter, QLabel
from PyQt6.QtCore import Qt
from py_editor.ui.scene.primitives import PrimitiveTree
from py_editor.ui.scene.outliner import SceneOutliner

class HierarchyDock(QWidget):
    """Combined panel for scene construction and management."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_window = parent
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.splitter = QSplitter(Qt.Orientation.Vertical)
        
        # Add Section
        add_container = QWidget()
        add_layout = QVBoxLayout(add_container)
        add_layout.setContentsMargins(0, 0, 0, 0)
        lbl_add = QLabel("  ADD PRIMITIVES")
        lbl_add.setStyleSheet("background: #252526; color: #aaa; font-weight: bold; font-size: 10px; min-height: 20px;")
        add_layout.addWidget(lbl_add)
        self.primitives = PrimitiveTree(self)
        add_layout.addWidget(self.primitives)
        
        self.splitter.addWidget(add_container)
        
        # Scene Section
        scene_container = QWidget()
        scene_layout = QVBoxLayout(scene_container)
        scene_layout.setContentsMargins(0, 0, 0, 0)
        lbl_scene = QLabel("  SCENE OUTLINER")
        lbl_scene.setStyleSheet("background: #252526; color: #aaa; font-weight: bold; font-size: 10px; min-height: 20px;")
        scene_layout.addWidget(lbl_scene)
        self.outliner = SceneOutliner(self)
        scene_layout.addWidget(self.outliner)
        
        self.splitter.addWidget(scene_container)
        
        # Set initial sizes
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 2)
        
        layout.addWidget(self.splitter)
