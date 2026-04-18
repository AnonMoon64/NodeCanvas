"""
scene_editor.py - Refactored Shell

This file now orchestrates the Scene Editor by importing modular components.
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QStackedWidget,
    QToolButton, QFrame
)
import math
from pathlib import Path
from PyQt6.QtCore import pyqtSignal, Qt, QTimer

# Local imports from the scene submodule
from .scene.scene_view import SceneViewport
from .scene.object_system import SceneObject
from .scene.properties_panel import ObjectPropertiesPanel
from .scene.primitives import PrimitiveTree
from .scene.outliner import SceneOutliner
from py_editor.core.simulation_controller import SimulationController
from py_editor.core.node_templates import get_all_templates
from py_editor.core.mesh_converter import MeshConverter

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
        
        # Start Simulation automatically (Live mode)
        QTimer.singleShot(500, self.start_live_simulation)
        
        # Signal forwarding
        self.object_selected = self.viewport.object_selected
        self.viewport.object_dropped.connect(self._on_object_dropped)

    def start_live_simulation(self):
        """Initializes the live simulation state."""
        if not self.sim.is_running:
            graph_data = self.main_window.logic_editor.export_graph()
            vars = self.main_window.logic_editor.graph_variables
            templates = get_all_templates()
            self.sim.start(graph_data, templates, vars)
            self.viewport.is_play_mode = True

    def toggle_simulation(self):
        """Legacy support - Toggles pause state in live mode."""
        self.sim.pause(not self.sim.is_paused)
        self.viewport.is_play_mode = not self.sim.is_paused

    def stop_simulation(self):
        """Only used for developer reset."""
        self.sim.stop()
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

    def _on_object_dropped(self, prim_type, wx, wz, mx, my, file_path=""):
        # Auto-convert FBX / OBJ to .mesh if needed (scene_view may have already done
        # this, but handle the case where the call came from another code path)
        if prim_type == "mesh" and file_path:
            fp = Path(file_path)
            if fp.suffix.lower() in ('.fbx', '.obj'):
                mesh_out = fp.with_suffix('.mesh')
                try:
                    if fp.suffix.lower() == '.fbx':
                        MeshConverter.fbx_to_mesh(str(fp), str(mesh_out))
                    else:
                        MeshConverter.obj_to_mesh(str(fp), str(mesh_out))
                    file_path = str(mesh_out)
                except Exception as e:
                    print(f"[SCENE] Auto-convert failed for {fp.name}: {e}")

        # Voxel World variants: two primitives, one obj_type. The drop sets
        # voxel_type to "Flat" or "Round" so the renderer dispatches correctly.
        voxel_variant = None
        if prim_type == "voxel_world_flat":
            voxel_variant = "Flat"
            prim_type = "voxel_world"
        elif prim_type == "voxel_world_round":
            voxel_variant = "Round"
            prim_type = "voxel_world"

        # Create a new SceneObject at the drop location
        base_name = Path(file_path).stem if file_path else prim_type.capitalize()
        name = f"{base_name}_{len(self.viewport.scene_objects)}"
        obj = SceneObject(name, prim_type, position=[wx, 0, wz])
        if voxel_variant is not None:
            obj.voxel_type = voxel_variant
        
        # --- AUTO-PARENTING LOGIC ---
        # Detect closest planet (Voxel World) for parenting
        planets = [o for o in self.viewport.scene_objects if o.obj_type == 'voxel_world']
        closest_planet = None
        min_dist = float('inf')
        for p in planets:
            d = math.sqrt((obj.position[0]-p.position[0])**2 + (obj.position[1]-p.position[1])**2 + (obj.position[2]-p.position[2])**2)
            if d < min_dist:
                min_dist = d
                closest_planet = p
        
        if closest_planet:
            # Atmosphere specifically links and matches radius
            if prim_type == 'atmosphere':
                obj.parent_id = closest_planet.id
                obj.planet_mode = True
                rad = getattr(closest_planet, 'voxel_radius', 60000.0)
                obj.planet_radius = rad
                obj.atmosphere_thickness = max(100.0, rad * 0.02)
                obj.planet_center = [0, 0, 0] # Local center for parented atmo
                obj.position = [0, 0, 0]
                obj.rotation = [0, 0, 0]
                print(f"[SCENE] Linked Atmosphere to Planet {closest_planet.name}")
            else:
                # General objects parent and reset local transform for surface sticking
                obj.parent_id = closest_planet.id
                # World to Local: p_local = p_world - parent_world
                obj.position = [wx - closest_planet.position[0], 0, wz - closest_planet.position[2]]
                
                # Auto-scale based on planet size
                if getattr(closest_planet, 'voxel_radius', 0) > 10000:
                    obj.scale = [10.0, 10.0, 10.0]
                print(f"[SCENE] Parented {obj.name} to {closest_planet.name}")

        if prim_type == "mesh":
            obj.mesh_path = file_path
            # Auto-link PBR maps from .material sidecar if present
            if file_path:
                try:
                    pbr = MeshConverter.load_material_sidecar(file_path)
                    if pbr:
                        obj.pbr_maps.update(pbr)
                        obj.shader_name = "PBR Material"
                        print(f"[SCENE] Auto-linked {len(pbr)} PBR maps from sidecar for {obj.name}")
                except Exception:
                    pass
        elif file_path:
            obj.logic_path = file_path
        
        # Add to scene
        self.viewport.scene_objects.append(obj)
        
        # Live refresh Simulation
        if self.sim.is_running:
            self.sim.refresh()
        
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
            elif obj.obj_type == 'voxel_world':
                 nd['voxel_block_size'] = getattr(obj, 'voxel_block_size', 0.025)
                 nd['voxel_render_style'] = getattr(obj, 'voxel_render_style', 'Smooth')
                 nd['voxel_seed'] = getattr(obj, 'voxel_seed', 123)
                 nd['voxel_type'] = getattr(obj, 'voxel_type', 'Round')
                 nd['voxel_radius'] = getattr(obj, 'voxel_radius', 5.0)
                 nd['voxel_lod_enabled'] = getattr(obj, 'voxel_lod_enabled', True)
                 nd['voxel_smooth_iterations'] = getattr(obj, 'voxel_smooth_iterations', 2)
                 nd['voxel_layers'] = getattr(obj, 'voxel_layers', [])
                 nd['voxel_biomes'] = getattr(obj, 'voxel_biomes', [])
            elif obj.obj_type == 'ocean_world':
                 nd['voxel_radius'] = getattr(obj, 'voxel_radius', 0.5)
                 nd['ocean_world_radius'] = getattr(obj, 'ocean_world_radius', 0.48)
                 nd['ocean_world_wave_speed'] = getattr(obj, 'ocean_world_wave_speed', 3.0)
                 nd['ocean_world_wave_intensity'] = getattr(obj, 'ocean_world_wave_intensity', 0.015)
                 nd['ocean_world_color'] = getattr(obj, 'ocean_world_color', [0.05, 0.25, 0.6, 0.85])
            # Always persist mesh path, texture, PBR maps and shader for mesh/cube objects
            if obj.obj_type in ('mesh', 'cube', 'sphere', 'plane'):
                if getattr(obj, 'mesh_path', None):
                    nd['mesh_path'] = obj.mesh_path
                if getattr(obj, 'texture_path', None):
                    nd['texture_path'] = obj.texture_path
                if getattr(obj, 'pbr_maps', None):
                    nd['pbr_maps'] = obj.pbr_maps
                if getattr(obj, 'pbr_tiling', None):
                    nd['pbr_tiling'] = obj.pbr_tiling
                nd['pbr_displacement_scale'] = getattr(obj, 'pbr_displacement_scale', 0.05)
                nd['shader_name'] = getattr(obj, 'shader_name', 'Standard')
            nodes.append(nd)
        return {"nodes": nodes}
        
        self.viewport.update()
        # Trigger global update (via MainWindow)
        self.viewport.object_selected.emit(None)
