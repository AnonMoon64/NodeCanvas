"""
scene_editor.py - Refactored Shell

This file now orchestrates the Scene Editor by importing modular components.
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QStackedWidget,
    QToolButton, QFrame
)
from PyQt6.QtCore import pyqtSignal, Qt

# Local imports from the scene submodule
from .scene.scene_view import SceneViewport
from .scene.object_system import SceneObject
from .scene.properties_panel import ObjectPropertiesPanel
from .scene.primitives import PrimitiveTree
from .scene.outliner import SceneOutliner
from py_editor.core.simulation_controller import SimulationController
from py_editor.core.node_templates import get_all_templates

class SceneEditorWidget(QWidget):
    """Orchestrator for the Scene Editor - Shell version (Viewport only)."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_window = parent
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.viewport = SceneViewport(self)
        layout.addWidget(self.viewport)

        # Simulation Controller
        self.sim = SimulationController(self)
        self.sim.logger = self.viewport.add_screen_log
        
        # Viewport HUD (Floating Overlay)
        # Signal forwarding
        self.object_selected = self.viewport.object_selected
        self.viewport.object_dropped.connect(self._on_object_dropped)

    def toggle_simulation(self):
        if not self.sim.is_running:
            # Start
            graph_data = self.main_window.logic_editor.export_graph()
            vars = self.main_window.logic_editor.graph_variables
            templates = get_all_templates()
            self.sim.start(graph_data, templates, vars)
            self.btn_play.setText("⏸ PAUSE")
            self.viewport.is_play_mode = True
        else:
            self.sim.pause(not self.sim.is_paused)
            self.btn_play.setText("▶ RESUME" if self.sim.is_paused else "⏸ PAUSE")

    def stop_simulation(self):
        self.sim.stop()
        self.btn_play.setText("▶ PLAY")
        self.viewport.is_play_mode = False

    def _set_left_tab(self, index):
        self.left_stack.setCurrentIndex(index)
        self.btn_prim.setChecked(index == 0)
        self.btn_out.setChecked(index == 1)

    def _on_object_selected(self, obj):
        # Forwarding selection state to viewport
        for o in self.viewport.scene_objects: o.selected = False
        if obj: obj.selected = True
        self.viewport.update()

    def _on_property_changed(self):
        self.viewport.update()

    def _on_object_deleted(self, obj):
        if obj in self.viewport.scene_objects:
            self.viewport.scene_objects.remove(obj)
            self.viewport.update()

    def _on_object_dropped(self, prim_type, wx, wz, mx, my, logic_path=""):
        # Create a new SceneObject at the drop location
        base_name = Path(logic_path).stem if logic_path else prim_type.capitalize()
        name = f"{base_name}_{len(self.viewport.scene_objects)}"
        obj = SceneObject(name, prim_type, position=[wx, 0, wz])
        if logic_path:
            obj.logic_path = logic_path
        
        # Add to scene
        self.viewport.scene_objects.append(obj)
        
        # Selection logic is now handled via signals connected to MainWindow
        # We just inform the viewport to update and select the new object
        for o in self.viewport.scene_objects: o.selected = False
        obj.selected = True
        self.viewport.update()
        
        # Re-emit selection to update docks
        self.viewport.object_selected.emit(obj)

    def on_tab_activated(self):
        self.viewport.start_render_loop()

    def on_tab_deactivated(self):
        self.viewport.stop_render_loop()

    def load_scene_data(self, data):
        # Implementation for loading .scene files
        if not isinstance(data, dict): return
        
        # Restore camera if present
        if "camera_3d" in data:
            cam = data["camera_3d"]
            self.viewport._cam3d.pos = cam.get("pos", [0, 25, 50])
            self.viewport._cam3d.yaw = cam.get("yaw", -90.0)
            self.viewport._cam3d.pitch = cam.get("pitch", -20.0)
        
        # Clear existing
        self.viewport.scene_objects.clear()
        
        # Load objects (Actual .scene files use "objects" key)
        nodes = data.get("objects", data.get("nodes", []))
        for nd in nodes:
            obj = SceneObject(
                name=nd.get("name", "Object"),
                obj_type=nd.get("obj_type", nd.get("type", "cube")),
                position=nd.get("position", [0,0,0]),
                rotation=nd.get("rotation", [0,0,0]),
                scale=nd.get("scale", [1,1,1])
            )
            # ... rest of restoration logic ...
            obj.active = nd.get("active", True)
            obj.visible = nd.get("visible", True)
            
            # Restore specialized props
            for k, v in nd.items():
                if k not in ("name", "type", "position", "rotation", "scale", "active", "visible"):
                    setattr(obj, k, v)
            
            self.viewport.scene_objects.append(obj)
            
    def export_scene_data(self):
        # Package objects into JSON-ready dict
        nodes = []
        for obj in self.viewport.scene_objects:
            nd = {
                "name": obj.name,
                "type": obj.obj_type,
                "position": obj.position,
                "rotation": obj.rotation,
                "scale": obj.scale,
                "active": obj.active,
                "visible": obj.visible
            }
            # Special props
            if obj.obj_type == 'atmosphere':
                nd['time_of_day'] = getattr(obj, 'time_of_day', 0.25)
            elif obj.obj_type == 'landscape':
                nd['landscape_seed'] = getattr(obj, 'landscape_seed', 123)
                nd['landscape_height_scale'] = getattr(obj, 'landscape_height_scale', 30.0)
                nd['landscape_resolution'] = getattr(obj, 'landscape_resolution', 32)
            elif obj.obj_type == 'ocean':
                 nd['ocean_wave_speed'] = getattr(obj, 'ocean_wave_speed', 5.0)
                 nd['ocean_wave_intensity'] = getattr(obj, 'ocean_wave_intensity', 1.0)
            nodes.append(nd)
        return {"nodes": nodes}
        
        self.viewport.update()
        # Trigger global update (via MainWindow)
        self.viewport.object_selected.emit(None)
