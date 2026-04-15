"""
scene_view.py

OpenGL viewport with 2D/3D grid, scene objects, gizmos, and navigation.
"""
import time
import math
import threading
import numpy as np
from pathlib import Path
from typing import List, Optional, Dict
from PyQt6.QtWidgets import QWidget, QMenu, QHBoxLayout
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QPoint, QPointF
from PyQt6.QtGui import QMouseEvent, QWheelEvent, QKeyEvent, QSurfaceFormat, QPainter, QColor, QFont, QPen

try:
    from PyQt6.QtOpenGLWidgets import QOpenGLWidget
except ImportError:
    QOpenGLWidget = None

try:
    from OpenGL.GL import *
    from OpenGL.GLU import *
except ImportError:
    pass

from py_editor.ui.shared_styles import BG_COLOR, GRID_MAJOR_COLOR, GRID_MINOR_COLOR, AXIS_X_COLOR, AXIS_Y_COLOR, AXIS_Z_COLOR, ORIGIN_COLOR
from py_editor.ui.scene.object_system import SceneObject
from py_editor.ui.scene.render_manager import Camera3D, Camera2D, _length, _sub, _add, _dot, _scale_vec, _normalize
from py_editor.core.boid_system_gpu import GPUBoidManager
from py_editor.core.mesh_converter import MeshConverter
from py_editor.core.voxel_engine import VoxelEngine
from py_editor.core.controller import AIController, PlayerController, AIGPUFishController, AIGPUBirdController
from py_editor.ui.shader_manager import get_shader

class SceneViewport(QOpenGLWidget):
    """OpenGL viewport with 2D/3D grid, scene objects, and navigation."""

    fps_updated = pyqtSignal(int)
    object_selected = pyqtSignal(object)
    object_dropped = pyqtSignal(str, float, float, int, int, str) # logic_path as last arg
    object_moved = pyqtSignal()
    state_about_to_change = pyqtSignal()
    state_changed = pyqtSignal()

    def __init__(self, parent=None):
        if QOpenGLWidget:
            fmt = QSurfaceFormat()
            fmt.setDepthBufferSize(24)
            fmt.setSamples(4)
            fmt.setSwapInterval(1)
            QSurfaceFormat.setDefaultFormat(fmt)
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setAcceptDrops(True)

        self._mode = "3D"
        self._cam3d = Camera3D()
        self._cam2d = Camera2D()

        self._lmb = False
        self._rmb = False
        self._keys = set()
        self._last_mouse = None
        self._elapsed_time = 0.0
        self._gizmo_axis = None # 'x', 'y', 'z' or None
        
        self.mesh_cache = {} # path -> {vao, vbo, ibo, count}
        self.texture_cache = {} # path -> tex_id
        
        self._drag_start_pos = None
        self._drag_obj_start_pos = None
        self._drag_multi_starts = {}
        self._drag_multi_rot_starts = {}
        self._drag_multi_scale_starts = {}
        
        # UI Overlays
        self._screen_logs = [] # List of (message, timestamp)
        
        # Mode Selector UI
        from PyQt6.QtWidgets import QComboBox
        self._mode_combo = QComboBox(self)
        self._mode_combo.addItems(["3D Perspective", "2D Ortho"])
        self._mode_combo.setStyleSheet("""
            QComboBox { background: rgba(40, 40, 45, 200); color: #ccc; border: 1px solid #444; border-radius: 4px; padding: 2px 10px; font-size: 11px; }
            QComboBox::drop-down { border: none; }
        """)
        self._mode_combo.currentIndexChanged.connect(self._on_mode_combo_changed)
        self._mode_combo.move(10, 10)
        self._mode_combo.setFixedWidth(120)
        
        # Camera View Selector (Top, Left, etc)
        self._view_combo = QComboBox(self)
        self._view_combo.addItems(["Perspective", "Top", "Bottom", "Left", "Right", "Front", "Back"])
        self._view_combo.setStyleSheet(self._mode_combo.styleSheet())
        self._view_combo.currentIndexChanged.connect(self._on_view_combo_changed)
        self._view_combo.setFixedWidth(120)
        self._update_view_combo_pos()

        # Transformation HUD
        from PyQt6.QtWidgets import QFrame, QPushButton, QButtonGroup
        self._hud = QFrame(self)
        self._hud.setStyleSheet("background: rgba(40, 40, 45, 180); border: 1px solid #444; border-radius: 6px;")
        self._hud.move(140, 10); self._hud.setFixedHeight(30)
        hud_lay = QHBoxLayout(self._hud)
        hud_lay.setContentsMargins(4, 2, 4, 2); hud_lay.setSpacing(4)
        
        self._gizmo_mode = "translate" # "translate", "rotate", "scale"
        self._btns = QButtonGroup(self)
        for mode in ["Move", "Rotate", "Scale"]:
            btn = QPushButton(mode)
            btn.setCheckable(True)
            btn.setChecked(mode == "Move")
            btn.setFixedSize(60, 22)
            btn.setStyleSheet("""
                QPushButton { background: none; border: none; color: #aaa; font-size: 10px; font-weight: bold; }
                QPushButton:checked { background: #4fc3f7; color: #000; border-radius: 3px; }
                QPushButton:hover { color: #fff; }
            """)
            btn.clicked.connect(lambda _, m=mode.lower(): self.set_gizmo_mode(m))
            hud_lay.addWidget(btn)
            self._btns.addButton(btn)

        # Speed Slider HUD (Top Right)
        from PyQt6.QtWidgets import QSlider, QLabel
        self._speed_hud = QFrame(self)
        self._speed_hud.setStyleSheet("background: rgba(40, 40, 45, 180); border: 1px solid #444; border-radius: 6px;")
        self._speed_hud.setFixedWidth(150); self._speed_hud.setFixedHeight(30)
        speed_lay = QHBoxLayout(self._speed_hud)
        speed_lay.setContentsMargins(8, 2, 8, 2); speed_lay.setSpacing(6)
        
        lbl = QLabel("Speed")
        lbl.setStyleSheet("color: #ccc; font-size: 10px; font-weight: bold; border: none;")
        speed_lay.addWidget(lbl)
        
        self._speed_slider = QSlider(Qt.Orientation.Horizontal)
        self._speed_slider.setRange(1, 100)
        self._speed_slider.setValue(int(self._cam3d.speed))
        self._speed_slider.setStyleSheet("""
            QSlider::groove:horizontal { background: #333; height: 4px; border-radius: 2px; }
            QSlider::handle:horizontal { background: #4fc3f7; width: 10px; height: 10px; margin: -3px 0; border-radius: 5px; }
        """)
        self._speed_slider.valueChanged.connect(self._on_speed_slider_changed)
        speed_lay.addWidget(self._speed_slider)

        self._frame_timer = QTimer(self)
        self._frame_timer.timeout.connect(self._tick)
        self._last_time = time.perf_counter()
        self._elapsed_time = 0.0
        self.is_play_mode = False

        self.grid_size = 1.0
        self.grid_extent = 200
        self.show_grid = True
        self.scene_objects: List[SceneObject] = []
        self._editor_controllers: Dict[str, object] = {} # obj_id -> Controller
        # Voxel generation / streaming tuning
        self.voxel_max_single_chunk_res = 256
        self.voxel_prefetch_neighborhood = 3 # Increased default to avoid "cut off" look in large worlds
        # Pending CPU-generated chunk meshes (chunk_key -> (verts, idx, norms))
        self._pending_voxel_chunks = {}
        # Track generation in progress to avoid duplicate threads
        self._voxel_generation_in_progress = set()
        self._voxel_gen_lock = threading.Lock()

    def set_mode(self, mode: str):
        self._mode = mode
        self.update()

    def start_render_loop(self):
        self._last_time = time.perf_counter()
        self._frame_timer.start(16)

    def stop_render_loop(self):
        self._frame_timer.stop()

    def load_scene_data(self, data: dict):
        """Load scene objects from a data dictionary (from export_scene_data)."""
        self.scene_objects.clear()
        nodes = data.get("nodes", data.get("objects", []))
        
        for nd in nodes:
            obj = SceneObject(
                name=nd.get("name", "Object"),
                obj_type=nd.get("type", nd.get("obj_type", "cube")),
                position=nd.get("position", [0, 0, 0]),
                rotation=nd.get("rotation", [0, 0, 0]),
                scale=nd.get("scale", [1, 1, 1])
            )
            obj.active = nd.get("active", True)
            obj.visible = nd.get("visible", True)
            obj.logic_path = nd.get("logic_path", "")
            
            # Restore specialized props
            for k, v in nd.items():
                if k not in ("name", "type", "obj_type", "position", "rotation", "scale", "active", "visible", "logic_path"):
                    setattr(obj, k, v)
            
            self.scene_objects.append(obj)
        
        print(f"[VIEWPORT] Loaded {len(self.scene_objects)} objects into standalone")
        self.update()

    def _on_mode_combo_changed(self, index):
        self._mode = "3D" if index == 0 else "2D"
        self.update()

    def set_gizmo_mode(self, mode):
        self._gizmo_mode = mode
        print(f"[VIEWPORT] Gizmo Mode: {mode}")
        self.update()

    def _on_speed_slider_changed(self, val):
        self._cam3d.speed = float(val)
        # Update selected camera speed if any
        for obj in self.scene_objects:
            if obj.selected and obj.obj_type == 'camera':
                obj.camera_speed = float(val)
        self.update()

    def sync_ui_to_selection(self):
        """Update HUD elements based on currently selected objects."""
        selected_cam = next((o for o in self.scene_objects if o.selected and o.obj_type == 'camera'), None)
        if selected_cam:
            speed = getattr(selected_cam, 'camera_speed', 10.0)
            self._cam3d.speed = speed
            # Block signals to avoid feedback loop
            self._speed_slider.blockSignals(True)
            self._speed_slider.setValue(int(speed))
            self._speed_slider.blockSignals(False)

    def _tick(self):
        now = time.perf_counter()
        dt = now - self._last_time
        self._last_time = now

        if self._mode == "3D" and self._rmb:
            fwd = (1 if Qt.Key.Key_W in self._keys else 0) - (1 if Qt.Key.Key_S in self._keys else 0)
            rgt = (1 if Qt.Key.Key_D in self._keys else 0) - (1 if Qt.Key.Key_A in self._keys else 0)
            upd = (1 if Qt.Key.Key_E in self._keys else 0) - (1 if Qt.Key.Key_Q in self._keys else 0)
            if fwd or rgt or upd:
                self._cam3d.move(fwd, rgt, upd, dt, self._cam3d.speed)

        # Update ocean time
        self._elapsed_time += max(0.0, min(dt, 0.1))
        
        # Fade out logs
        cur_time = time.time()
        self._screen_logs = [log for log in self._screen_logs if cur_time - log.get('timestamp', 0) < 5.0]
        
        self.update()
        
        # Update Editor-time Controllers
        if not self.is_play_mode:
            self._sync_editor_controllers()
            dt_sim = min(dt, 0.1)
            for ctrl in self._editor_controllers.values():
                try:
                    ctrl.update(dt_sim)
                except Exception: pass
            # Update controller-derived physics (velocity/acceleration) and resolve collisions
            for ctrl in self._editor_controllers.values():
                try:
                    ctrl.update_physics(dt_sim)
                except Exception:
                    pass
            try:
                from py_editor.core.physics import resolve_collisions
                resolve_collisions(self.scene_objects, dt_sim)
            except Exception:
                pass

        # GPU Boid simulation tick
        if hasattr(self, 'boid_mgr'):
            # Use current universe position as dynamic target if any
            universe_obj = next((o for o in self.scene_objects if o.obj_type == 'universe'), None)
            target = universe_obj.position if universe_obj else (0,0,0)
            self.boid_mgr.update(dt, self._elapsed_time, target)
        
        self.update()

    def initializeGL(self):
        glClearColor(*BG_COLOR)
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_CULL_FACE)
        glCullFace(GL_BACK)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        try:
            from py_editor.ui.procedural_ocean import init_ocean_gpu
            init_ocean_gpu()
        except Exception: pass
        
        # Initialize GPU Boids
        self.boid_mgr = GPUBoidManager.get_instance()
        self.boid_mgr.init_gpu()
        self._init_boid_render_mesh()

        self.start_render_loop()

    def _process_pending_voxel_chunks(self):
        """Create VAOs for any pending CPU-generated chunk meshes.

        This must be called from the GL thread (e.g. inside paintGL) because
        VAO/VBO creation requires a current GL context.
        """
        if not self._pending_voxel_chunks:
            return

        keys = list(self._pending_voxel_chunks.keys())
        for key in keys:
            data = None
            try:
                data = self._pending_voxel_chunks.pop(key)
            except KeyError:
                continue
            if not data:
                continue
            verts, idx, norms = data
            try:
                new_vao = self._create_voxel_vao(verts, idx, norms)
            except Exception as e:
                print(f"[VOXEL] Failed to create VAO for {key}: {e}")
                continue

            # If an older VAO exists for this key, delete GL resources
            old = self.mesh_cache.get(key)
            if isinstance(old, dict):
                try:
                    glDeleteVertexArrays(1, [old['vao']])
                except Exception:
                    pass
                try:
                    glDeleteBuffers(1, [old['vbo']])
                except Exception:
                    pass
                try:
                    glDeleteBuffers(1, [old['ibo']])
                except Exception:
                    pass

            self.mesh_cache[key] = new_vao

    def keyPressEvent(self, event: QKeyEvent):
        self._keys.add(event.key())
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event: QKeyEvent):
        if event.key() in self._keys:
            self._keys.remove(event.key())
        super().keyReleaseEvent(event)

    def mousePressEvent(self, event):
        self.setFocus()
        mx, my = int(event.position().x()), int(event.position().y())
        ctrl = event.modifiers() & Qt.KeyboardModifier.ControlModifier
        
        if event.button() == Qt.MouseButton.LeftButton:
            self._lmb = True
            
            # 1. Try picking Gizmo first
            selected_objs = [o for o in self.scene_objects if o.selected]
            sel = selected_objs[-1] if selected_objs else None
            if sel:
                axis = self._pick_gizmo_axis(mx, my, sel.position)
                if axis:
                    self._gizmo_axis = axis
                    self._drag_start_pos = (mx, my)
                    self._drag_obj_start_pos = list(sel.position)
                    self._drag_multi_starts = {o: list(o.position) for o in selected_objs}
                    self._drag_multi_rot_starts = {o: list(o.rotation) for o in selected_objs}
                    self._drag_multi_scale_starts = {o: list(o.scale) for o in selected_objs}
                    print(f"[VIEWPORT] Dragging axis: {axis} for {len(selected_objs)} objects")
                    return
            
            # 2. Pick Object
            found = self._pick_object(mx, my)
            if ctrl:
                if found:
                    found.selected = not found.selected
            else:
                for o in self.scene_objects:
                    o.selected = (o == found)
            
            new_sel = [o for o in self.scene_objects if o.selected]
            self.sync_ui_to_selection()
            self.object_selected.emit(new_sel)
        elif event.button() == Qt.MouseButton.RightButton:
            self._rmb = True
            self._last_mouse = event.position()
            self.setCursor(Qt.CursorShape.BlankCursor)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton: 
            self._lmb = False
            self._gizmo_axis = None
        elif event.button() == Qt.MouseButton.RightButton:
            self._rmb = False
            self.setCursor(Qt.CursorShape.ArrowCursor)

    def wheelEvent(self, event):
        if self._mode == "3D":
            # Move camera forward/back based on wheel delta
            delta = event.angleDelta().y() / 120.0  # Normalized clicks
            # Use a slightly faster movement for wheel
            speed_mult = 5.0
            self._cam3d.move(delta * speed_mult, 0, 0, 0.1) # Simulate a 0.1s dt
            self.update()
        else:
            # Plan 2D zoom if needed, but primarily for 3D navigation
            delta = event.angleDelta().y() / 120.0
            self._cam2d.zoom_level = max(0.1, self._cam2d.zoom_level - delta)
            self.update()
        super().wheelEvent(event)

    def mouseMoveEvent(self, event):
        mx, my = int(event.position().x()), int(event.position().y())
        if self._lmb and self._gizmo_axis:
            selected_objs = [o for o in self.scene_objects if o.selected]
            if selected_objs:
                dx = mx - self._drag_start_pos[0]
                dy = my - self._drag_start_pos[1]
                factor = 0.1
                rot_factor = 0.5
                scale_factor = 0.01
                
                r, u = self._cam3d.right, self._cam3d.up
                
                for sel in selected_objs:
                    start_pos = self._drag_multi_starts.get(sel, sel.position)
                    start_rot = self._drag_multi_rot_starts.get(sel, sel.rotation)
                    start_scale = self._drag_multi_scale_starts.get(sel, sel.scale)
                    
                    if self._gizmo_mode == "translate":
                        if self._gizmo_axis == 'x':
                            sel.position[0] = start_pos[0] + dx * factor * r[0] - dy * factor * u[0]
                        elif self._gizmo_axis == 'y':
                            sel.position[1] = start_pos[1] - dy * factor
                        elif self._gizmo_axis == 'z':
                            sel.position[2] = start_pos[2] + dx * factor * r[2] - dy * factor * u[2]
                    
                    elif self._gizmo_mode == "rotate":
                        delta = dx - dy
                        if self._gizmo_axis == 'x': sel.rotation[0] = start_rot[0] + delta * rot_factor
                        elif self._gizmo_axis == 'y': sel.rotation[1] = start_rot[1] + delta * rot_factor
                        elif self._gizmo_axis == 'z': sel.rotation[2] = start_rot[2] + delta * rot_factor
                    
                    elif self._gizmo_mode == "scale":
                        delta = (dx - dy) * scale_factor
                        if self._gizmo_axis == 'x': sel.scale[0] = max(0.01, start_scale[0] + delta)
                        elif self._gizmo_axis == 'y': sel.scale[1] = max(0.01, start_scale[1] + delta)
                        elif self._gizmo_axis == 'z': sel.scale[2] = max(0.01, start_scale[2] + delta)

                self.update()
                return

        if self._rmb and self._last_mouse:
            curr = event.position()
            dx = curr.x() - self._last_mouse.x()
            dy = curr.y() - self._last_mouse.y()
            self._cam3d.rotate(dx, dy)
            self._last_mouse = curr
            self.update()
        super().mouseMoveEvent(event)

    def resizeGL(self, w, h):
        glViewport(0, 0, w, h)
        self._update_view_combo_pos()

    def _update_view_combo_pos(self):
        w = self.width()
        self._view_combo.move(w - 130, 10)
        if hasattr(self, '_speed_hud'):
            self._speed_hud.move(w - 290, 10)

    def paintGL(self):
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_CULL_FACE)
        glCullFace(GL_BACK)
        w, h = self.width(), self.height()
        if w < 1 or h < 1: return

        # Process any pending CPU-generated chunk meshes and create VAOs
        try:
            self._process_pending_voxel_chunks()
        except Exception:
            pass

        if self._mode == "3D":
            self._cam3d.apply_gl(w / h)
            
            # --- Environment Rendering ---
            # 1. Universe
            universe_obj = next((o for o in self.scene_objects if o.obj_type == 'universe' and o.active), None)
            if universe_obj:
                from py_editor.ui.procedural_universe import render_universe
                render_universe(self._cam3d.pos, universe_obj)
            
            # 2. Atmosphere
            atmosphere_obj = next((o for o in self.scene_objects if o.obj_type == 'atmosphere' and o.active), None)
            time_val = getattr(atmosphere_obj, 'time_of_day', 0.25) if atmosphere_obj else 0.25
            if atmosphere_obj:
                from py_editor.ui.procedural_atmosphere import render_atmosphere
                render_atmosphere(self._cam3d.pos, atmosphere_obj)
            
            # 2.5 Cloud Layer (World Space)
            cloud_obj = next((o for o in self.scene_objects if (o.obj_type == 'clouds' or o.obj_type == 'cloud_layer') and o.active), None)
            if cloud_obj:
                from py_editor.ui.procedural_clouds import render_clouds
                render_clouds(self._cam3d.pos, cloud_obj, time_val)
            
            if not self.is_play_mode: self._draw_grid_3d()
            
            # 3. Landscape
            for obj in self.scene_objects:
                if obj.obj_type == 'landscape' and obj.active:
                    from py_editor.ui.procedural_system import draw_landscape_3d
                    draw_landscape_3d(obj, self)
            
            # 4. Ocean (flat) + Ocean World (spherical)
            for obj in self.scene_objects:
                if obj.obj_type == 'ocean' and obj.active:
                    from py_editor.ui.procedural_ocean import render_ocean_gpu
                    render_ocean_gpu(self._cam3d.pos, obj, self._elapsed_time)
                elif obj.obj_type == 'ocean_world' and obj.active:
                    from py_editor.ui.procedural_ocean_world import render_ocean_world
                    render_ocean_world(self._cam3d.pos, obj, self._elapsed_time)
            
            # 5. Primitives
            self._draw_scene_objects_3d()
            
            # 5.5 GPU Boids (Instanced)
            self._draw_gpu_boids()
            
            # 6. Gizmos (Restored)
            from py_editor.ui.scene.render_manager import _draw_gizmo
            selected_obj = next((o for o in self.scene_objects if o.selected), None)
            if selected_obj:
                _draw_gizmo(selected_obj.position, selected_axis=self._gizmo_axis)
            
            # --- Viewport Overlay ---
            self._draw_viewport_overlay(w, h)
        else:
            self._cam2d.apply_gl(w, h)
            self._draw_grid_2d()
            self._draw_scene_objects_2d()

    def _draw_viewport_overlay(self, w, h):
        # Draw Orientation Widget and Logs
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # 1. Orientation Widget (Bottom Left - The "L" thing)
        self._draw_orientation_widget(painter, w, h)
        
        # 2. UE5 Style On-Screen Logs (Top Left)
        self._draw_onscreen_logs(painter, w, h)
        
        painter.end()

    def _draw_onscreen_logs(self, painter, w, h):
        if not self._screen_logs: return
        
        painter.setFont(QFont("Consolas", 10))
        y_offset = 50
        for log in self._screen_logs:
            # Subtle background for readability
            text = log['text']
            rect = painter.fontMetrics().boundingRect(text)
            rect.adjust(-5, -2, 5, 2)
            rect.translate(20, y_offset - rect.height() + 5)
            
            painter.setBrush(QColor(0, 0, 0, 100))
            painter.setPen(Qt.GlobalColor.transparent)
            painter.drawRect(rect)
            
            painter.setPen(log['color'])
            painter.drawText(20, y_offset, text)
            y_offset += 20

        # Input to Speed
        new_speed = None
        if Qt.Key.Key_1 in self._keys: new_speed = 2.0
        elif Qt.Key.Key_2 in self._keys: new_speed = 10.0
        elif Qt.Key.Key_3 in self._keys: new_speed = 50.0
        elif Qt.Key.Key_4 in self._keys: new_speed = 200.0
        elif Qt.Key.Key_5 in self._keys: new_speed = 1000.0
        
        if new_speed is not None and self._cam3d.speed != new_speed:
            self._cam3d.speed = new_speed
            self._speed_slider.blockSignals(True)
            self._speed_slider.setValue(int(new_speed))
            self._speed_slider.blockSignals(False)
            # Also update selected camera
            for obj in self.scene_objects:
                if obj.selected and obj.obj_type == 'camera':
                    obj.camera_speed = new_speed

    def _draw_orientation_widget(self, painter, w, h):
        # Draw small XYZ axes in corner
        cx, cy = 60, h - 60
        
        # Calculate rotation based on camera yaw/pitch
        yaw_rad = math.radians(self._cam3d.yaw + 90)
        pitch_rad = math.radians(self._cam3d.pitch)
        
        def project(vec):
            # 3D to 2D projections for the widget
            x2d = vec[0] * math.cos(yaw_rad) - vec[2] * math.sin(yaw_rad)
            z_rot = vec[0] * math.sin(yaw_rad) + vec[2] * math.cos(yaw_rad)
            y2d = vec[1] * math.cos(pitch_rad) - z_rot * math.sin(pitch_rad)
            return QPointF(cx + x2d * 30, cy - y2d * 30)

        # Draw Axes
        axes = [
            ((1, 0, 0), QColor(255, 60, 60), "X"),
            ((0, 1, 0), QColor(60, 255, 60), "Y"),
            ((0, 0, 1), QColor(60, 60, 255), "Z")
        ]
        
        for vec, color, label in axes:
            end_pt = project(vec)
            painter.setPen(QPen(color, 2))
            painter.drawLine(QPointF(cx, cy), end_pt)
            painter.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
            painter.drawText(int(end_pt.x() - 4), int(end_pt.y() + 4), label)

    def _draw_grid_3d(self):
        if not self.show_grid: return
        extent = 50 # Local extent around camera
        step = self.grid_size
        
        # Snap grid to camera X and Z
        off_x = (self._cam3d.pos[0] // step) * step
        off_z = (self._cam3d.pos[2] // step) * step
        
        glBegin(GL_LINES)
        for i in range(-extent, extent + 1):
            vx = off_x + i * step
            vz = off_z + i * step
            
            # X lines
            glColor4f(*(GRID_MAJOR_COLOR if int(vx) % 10 == 0 else GRID_MINOR_COLOR))
            glVertex3f(vx, 0, off_z - extent*step); glVertex3f(vx, 0, off_z + extent*step)
            
            # Z lines
            glColor4f(*(GRID_MAJOR_COLOR if int(vz) % 10 == 0 else GRID_MINOR_COLOR))
            glVertex3f(off_x - extent*step, 0, vz); glVertex3f(off_x + extent*step, 0, vz)
        glEnd()

    def _draw_scene_objects_3d(self):
        from py_editor.ui.scene.render_manager import (
            _draw_wireframe_cube, _draw_wireframe_sphere, 
            _draw_camera_icon, _draw_light_icon
        )
        from py_editor.ui.shader_manager import get_shader
        import math
        
        # 1. Calculate Sun Direction from Atmosphere
        atmo = next((o for o in self.scene_objects if o.obj_type == 'atmosphere' and o.active), None)
        time_tod = getattr(atmo, 'time_of_day', 0.25)
        sol_angle = (time_tod - 0.5) * 6.28318
        sun_dir = (math.sin(sol_angle), math.cos(sol_angle), 0.2)
        
        for obj in self.scene_objects:
            # Skip procedural large scale primitives (handled elsewhere)
            if obj.obj_type in ('atmosphere', 'ocean', 'landscape', 'universe', 'clouds', 'cloud_layer'):
                continue
            
            glPushMatrix()
            glTranslatef(*obj.position)
            glRotatef(obj.rotation[0], 1, 0, 0)
            glRotatef(obj.rotation[1], 0, 1, 0)
            glRotatef(obj.rotation[2], 0, 0, 1)
            glScalef(*obj.scale)
            
            if obj.visible:
                s_name = getattr(obj, 'shader_name', 'Standard')
                active_shader = get_shader(s_name)
                if active_shader:
                    active_shader.use()
                    active_shader.set_uniform_f("time", self._elapsed_time)
                    active_shader.set_uniform_v3("sunDir", *sun_dir)
                    
                    # Material Props
                    col = list(obj.color)
                    col[3] = getattr(obj, 'alpha', 1.0)
                    active_shader.set_uniform_v4("base_color", *col)
                    
                    params = getattr(obj, 'shader_params', {})
                    # Modulate fish/anim shader 'speed' by object acceleration magnitude
                    try:
                        acc = getattr(obj, 'acceleration', None)
                        if acc:
                            acc_mag = math.sqrt(acc[0]*acc[0] + acc[1]*acc[1] + acc[2]*acc[2])
                            params['speed'] = params.get('speed', 2.0) + acc_mag * 2.0
                    except Exception:
                        pass
                    active_shader.set_uniform_f("invert_axis", params.get("invert_axis", 0.0))
                    
                    if s_name == "PBR Material":
                        # PBR specific uniforms
                        active_shader.set_uniform_v4("u_base_color", *col)
                        active_shader.set_uniform_f("u_metallic", getattr(obj, 'pbr_metallic', 0.0))
                        active_shader.set_uniform_f("u_roughness", getattr(obj, 'pbr_roughness', 0.5))
                        active_shader.set_uniform_v2("u_tiling", *(getattr(obj, 'pbr_tiling', [1.0, 1.0])))
                        active_shader.set_uniform_v3("cam_pos", *self._cam3d.pos)
                    
                    for pk, pv in params.items():
                        if isinstance(pv, (int, float)):
                            active_shader.set_uniform_f(pk, pv)
                        elif isinstance(pv, list) and len(pv) == 4:
                            active_shader.set_uniform_v4(pk, *pv)
                    
                    # DRAW PRIMITIVES
                    if obj.obj_type in ('cube', 'plane'):
                        _draw_wireframe_cube()
                    elif obj.obj_type == 'sphere':
                        _draw_wireframe_sphere()
                    elif obj.obj_type == 'mesh' and obj.mesh_path:
                        alpha = col[3]
                        if alpha >= 0.99: glDisable(GL_BLEND)
                        else: 
                            glEnable(GL_BLEND)
                            glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
                        self._draw_custom_mesh(obj, shader_active=True)
                        glEnable(GL_BLEND) 
                    elif obj.obj_type == 'voxel_world':
                        self._draw_voxel_world(obj, shader_active=True)
                    
                    active_shader.stop()
                else:
                    # Fallback fixed function
                    if obj.obj_type in ('cube', 'plane'):
                        _draw_wireframe_cube()
                    elif obj.obj_type == 'sphere':
                        _draw_wireframe_sphere()
                    elif obj.obj_type == 'mesh' and obj.mesh_path:
                        self._draw_custom_mesh(obj, shader_active=False)
                    elif obj.obj_type == 'voxel_world':
                        self._draw_voxel_world(obj, shader_active=False)
            
            # Icons for specialty objects always show
            if obj.obj_type == 'camera':
                _draw_camera_icon(color=(0.3, 0.7, 1.0, 1.0) if obj.selected else (0.1, 0.4, 0.6, 0.8))
            elif obj.obj_type in ('light_directional', 'light_point'):
                _draw_light_icon(color=(1, 1, 0.4, 1.0) if obj.selected else (0.6, 0.6, 0.0, 0.8))
                
            glPopMatrix()

    def _on_view_combo_changed(self, index):
        view_names = ["Perspective", "Top", "Bottom", "Left", "Right", "Front", "Back"]
        view = view_names[index]
        if view == "Perspective":
            self._mode = "3D"
            self._mode_combo.setCurrentIndex(0)
        else:
            self._mode = "2D"
            self._mode_combo.setCurrentIndex(1)
            # Adjust Camera2D orientation (simplified: we just switch the mode)
            # In a full engine, we'd lock the camera rotation. 
            print(f"[VIEWPORT] Switched to {view} view")
        self.update()

    def _draw_grid_2d(self):
        if not self.show_grid: return
        extent = 50
        step = self.grid_size
        glColor4f(*(GRID_MINOR_COLOR))
        glBegin(GL_LINES)
        for i in range(-extent, extent + 1):
            val = i * step
            glVertex2f(val, -extent * step); glVertex2f(val, extent * step)
            glVertex2f(-extent * step, val); glVertex2f(extent * step, val)
        glEnd()

    def _draw_scene_objects_2d(self):
        """Simplistic 2D representation of scene objects"""
        for obj in self.scene_objects:
            if not obj.visible: continue
            glPushMatrix()
            # In 2D ortho, we typically look down Y or side X/Z.
            # Projecting 3D pos to 2D for simplicity:
            glTranslatef(obj.position[0], obj.position[2], 0) 
            glScalef(obj.scale[0], obj.scale[2], 1.0)
            
            # Draw a simple square for all
            glBegin(GL_LINE_LOOP)
            glVertex2f(-0.5, -0.5); glVertex2f(0.5, -0.5)
            glVertex2f(0.5, 0.5); glVertex2f(-0.5, 0.5)
            glEnd()
            glPopMatrix()

    def _pick_gizmo_axis(self, mx, my, pos):
        """Hit test for the transformation gizmo axes."""
        # Project axis endpoints to screen and check proximity
        # This is a robust heuristic for 3D selection without heavy math
        def dist_to_segment(p, a, b):
            # p: mouse point, a: axis start (screen), b: axis end (screen)
            import numpy as np
            p = np.array([p.x(), p.y()])
            a = np.array([a.x(), a.y()])
            b = np.array([b.x(), b.y()])
            pa, ba = p - a, b - a
            h = np.clip(np.dot(pa, ba) / np.dot(ba, ba), 0.0, 1.0)
            return np.linalg.norm(pa - ba * h)

        w, h = self.width(), self.height()
        s_pos = self._cam3d.world_to_screen(pos, w, h)
        if not s_pos: return None
        s_pos = QPointF(*s_pos)
        
        axes = {'x': [pos[0]+2, pos[1], pos[2]], 'y': [pos[0], pos[1]+2, pos[2]], 'z': [pos[0], pos[1], pos[2]+2]}
        best_axis, min_dist = None, 20.0 # Tolerance in pixels
        
        for name, end_world in axes.items():
            s_end = self._cam3d.world_to_screen(end_world, w, h)
            if not s_end: continue
            d = dist_to_segment(QPointF(mx, my), s_pos, QPointF(*s_end))
            if d < min_dist:
                min_dist, best_axis = d, name
                
        return best_axis

    def _pick_object(self, mx, my) -> Optional[SceneObject]:
        """Perform ray-sphere intersection for object picking."""
        from py_editor.ui.scene.render_manager import _sub, _dot
        origin, direction = self._cam3d.screen_to_ray(mx, my, self.width(), self.height())
        best_t, found = float('inf'), None
        for obj in self.scene_objects:
            oc = [_sub(origin, obj.position)[i] for i in range(3)]
            b = _dot(oc, direction)
            # Sphere proxy
            c = _dot(oc, oc) - (1.0 * max(obj.scale))**2
            h = b*b - c
            if h >= 0:
                t = -b - math.sqrt(h)
                if 0 < t < best_t:
                    best_t, found = t, obj
        return found

    def dragEnterEvent(self, event):
        text = event.mimeData().text()
        if text.startswith("prim:") or text.startswith("logic:") or any(text.lower().endswith(ext) for ext in ('.obj', '.fbx', '.mesh')):
            event.acceptProposedAction()

    def dropEvent(self, event):
        text = event.mimeData().text()
        mx, my = event.position().x(), event.position().y()
        
        # Calculate world position
        pos = self._cam3d.ray_plane_intersect(mx, my, self.width(), self.height(), (0,0,0), (0,1,0))
        wx, wz = (pos[0], pos[2]) if pos else (0, 0)

        if text.startswith("prim:"):
            prim_type = text[5:]
            self.object_dropped.emit(prim_type, wx, wz, int(mx), int(my), "")
            event.acceptProposedAction()
        elif any(text.lower().endswith(ext) for ext in ('.obj', '.fbx', '.mesh')):
            path = Path(text)
            if path.suffix.lower() in ('.obj', '.fbx'):
                # Auto-convert FBX / OBJ → .mesh on drop, sidecar .mat written too
                mesh_path = path.with_suffix('.mesh')
                try:
                    self.add_screen_log(f"Converting {path.name} → .mesh …", Qt.GlobalColor.yellow)
                    if path.suffix.lower() == '.fbx':
                        MeshConverter.fbx_to_mesh(str(path), str(mesh_path))
                    else:
                        MeshConverter.obj_to_mesh(str(path), str(mesh_path))
                    self.add_screen_log(f"Converted → {mesh_path.name}", Qt.GlobalColor.green)
                    self.object_dropped.emit("mesh", wx, wz, int(mx), int(my), str(mesh_path))
                except Exception as e:
                    self.add_screen_log(f"Convert failed: {e}", Qt.GlobalColor.red)
                    print(f"[VIEWPORT] Auto-convert failed for {path.name}: {e}")
            elif path.suffix.lower() == '.mesh':
                self.object_dropped.emit("mesh", wx, wz, int(mx), int(my), str(path))
            event.acceptProposedAction()
        elif text.startswith("logic:"):
            logic_path = text[6:]
            # Check if we dropped on an object
            target_obj = self._pick_object(int(mx), int(my))
            if target_obj:
                target_obj.logic_path = logic_path
                print(f"[VIEWPORT] Assigned logic {Path(logic_path).name} to {target_obj.name}")
            else:
                # Create new Logic Object Actor
                self.object_dropped.emit("logic", wx, wz, int(mx), int(my), logic_path)
                print(f"[VIEWPORT] Created Logic Actor from {Path(logic_path).name}")
            event.acceptProposedAction()
            self.update()
    def add_screen_log(self, text, color=Qt.GlobalColor.cyan):
        """Add a UE5-style on-screen log message."""
        self._screen_logs.append({
            'text': str(text),
            'timestamp': time.time(),
            'color': color
        })
        # Keep only last 10 logs
        if len(self._screen_logs) > 10:
            self._screen_logs.pop(0)
        self.update()

    def _init_boid_render_mesh(self):
        """Prepare a simple shard mesh for boid instances."""
        import numpy as np
        from pathlib import Path
        # Simple pyramid-like shard: 5 vertices
        verts = np.array([
             0.0,  0.0,  0.5,   0, 0, 1,
            -0.1, -0.1, -0.5,  -1,-1,-1,
             0.1, -0.1, -0.5,   1,-1,-1,
             0.1,  0.1, -0.5,   1, 1,-1,
            -0.1,  0.1, -0.5,  -1, 1,-1
        ], dtype=np.float32)
        
        indices = np.array([
            0,1,2, 0,2,3, 0,3,4, 0,4,1, 1,2,3, 1,3,4
        ], dtype=np.uint32)
        
        self.boid_vbo = glGenBuffers(1)
        glBindBuffer(GL_ARRAY_BUFFER, self.boid_vbo)
        glBufferData(GL_ARRAY_BUFFER, verts.nbytes, verts, GL_STATIC_DRAW)
        
        self.boid_ibo = glGenBuffers(1)
        glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, self.boid_ibo)
        glBufferData(GL_ELEMENT_ARRAY_BUFFER, indices.nbytes, indices, GL_STATIC_DRAW)
        self.num_boid_indices = len(indices)

        from py_editor.ui.shader_manager import ShaderProgram
        shader_dir = Path(__file__).parent.parent.parent / "core" / "shaders"
        v_src = (shader_dir / "boid_render.glsl").read_text()
        f_src = """#version 430 core
            in vec3 v_normal; in vec3 v_color;
            out vec4 outColor;
            void main() {
                vec3 n = normalize(v_normal);
                float diff = max(dot(n, vec3(0.5, 1.0, 0.2)), 0.3);
                outColor = vec4(v_color * diff, 1.0);
            }
        """
        self.boid_render_prog = ShaderProgram(v_src, f_src)
        
        # Sync indirect command
        self.boid_mgr.sync_indirect_buffer(self.num_boid_indices)

    def _draw_custom_mesh(self, obj, shader_active=False):
        path = obj.mesh_path
        if not path: return
        
        if path not in self.mesh_cache:
            self._load_mesh_to_gpu(path)
        
        mesh = self.mesh_cache.get(path)
        if not mesh: return
        
        # Texture handle
        if obj.shader_name == "PBR Material":
            self._bind_pbr_textures(obj, shader_active)
        else:
            tex_id = 0
            if obj.texture_path:
                if obj.texture_path not in self.texture_cache:
                    self._load_texture(obj.texture_path)
                tex_id = self.texture_cache.get(obj.texture_path, 0)

            if tex_id:
                glEnable(GL_TEXTURE_2D)
                glBindTexture(GL_TEXTURE_2D, tex_id)
                if not shader_active: glColor4f(1, 1, 1, 1)
            elif not shader_active:
                glColor4f(*obj.color)

        glBindVertexArray(mesh['vao'])
        glDrawElements(GL_TRIANGLES, mesh['count'], GL_UNSIGNED_INT, None)
        glBindVertexArray(0)
        
        # Cleanup textures
        if obj.shader_name == "PBR Material":
            for i in range(6):
                glActiveTexture(GL_TEXTURE0 + i)
                glBindTexture(GL_TEXTURE_2D, 0)
            glActiveTexture(GL_TEXTURE0)
        else:
            glBindTexture(GL_TEXTURE_2D, 0)
            glDisable(GL_TEXTURE_2D)

    def _bind_pbr_textures(self, obj, shader_active):
        shader = get_shader("PBR Material")
        
        map_types = ["albedo", "normal", "metallic", "roughness", "ao", "displacement"]
        shader_map_names = ["albedoMap", "normalMap", "metallicMap", "roughnessMap", "aoMap", "displacementMap"]
        has_map_names = ["hasAlbedo", "hasNormal", "hasMetallic", "hasRoughness", "hasAO", "hasDisplacement"]
        
        for i, (m_type, s_name, h_name) in enumerate(zip(map_types, shader_map_names, has_map_names)):
            path = obj.pbr_maps.get(m_type)
            if path:
                if path not in self.texture_cache:
                    self._load_texture(path)
                tex_id = self.texture_cache.get(path, 0)
                
                glActiveTexture(GL_TEXTURE0 + i)
                glBindTexture(GL_TEXTURE_2D, tex_id)
                shader.set_uniform_i(s_name, i)
                shader.set_uniform_i(h_name, 1)
            else:
                shader.set_uniform_i(h_name, 0)
        
        glActiveTexture(GL_TEXTURE0)

    def _load_mesh_to_gpu(self, path):
        try:
            v_data, i_data = MeshConverter.load_mesh(path)
            
            vao = glGenVertexArrays(1)
            glBindVertexArray(vao)
            
            vbo = glGenBuffers(1)
            glBindBuffer(GL_ARRAY_BUFFER, vbo)
            glBufferData(GL_ARRAY_BUFFER, v_data.nbytes, v_data, GL_STATIC_DRAW)
            
            ibo = glGenBuffers(1)
            glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, ibo)
            glBufferData(GL_ELEMENT_ARRAY_BUFFER, i_data.nbytes, i_data, GL_STATIC_DRAW)
            
            # Attribs: 0=pos(3f), 2=norm(3f), 8=uv(2f) -> Stride 8*4
            # Mapped to standard legacy attribute indices for compatibility
            glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, 32, ctypes.c_void_p(0))
            glEnableVertexAttribArray(0)
            glVertexAttribPointer(2, 3, GL_FLOAT, GL_FALSE, 32, ctypes.c_void_p(12))
            glEnableVertexAttribArray(2)
            glVertexAttribPointer(8, 2, GL_FLOAT, GL_FALSE, 32, ctypes.c_void_p(24))
            glEnableVertexAttribArray(8)
            
            glBindVertexArray(0)
            self.mesh_cache[path] = {'vao': vao, 'vbo': vbo, 'ibo': ibo, 'count': len(i_data)}
            print(f"[VIEWPORT] Loaded mesh: {Path(path).name}")
        except Exception as e:
            print(f"[VIEWPORT ERROR] Failed to load mesh {path}: {e}")
            self.mesh_cache[path] = None

    def _load_texture(self, path):
        from PyQt6.QtGui import QImage
        img = QImage(path)
        if img.isNull():
            print(f"[VIEWPORT ERROR] Failed to load texture: {path}")
            return
        
        img = img.convertToFormat(QImage.Format.Format_RGBA8888).mirrored()
        w, h = img.width(), img.height()
        ptr = img.bits()
        ptr.setsize(img.sizeInBytes())
        
        tex = glGenTextures(1)
        glBindTexture(GL_TEXTURE_2D, tex)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, w, h, 0, GL_RGBA, GL_UNSIGNED_BYTE, ptr.asstring())
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR_MIPMAP_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glGenerateMipmap(GL_TEXTURE_2D)
        
        self.texture_cache[path] = tex
        print(f"[VIEWPORT] Loaded texture: {Path(path).name}")

    def _draw_gpu_boids(self):
        """Draw GPU-simulated boids using indirect drawing."""
        if not hasattr(self, 'boid_mgr') or self.boid_mgr.num_boids == 0: return
        import ctypes
        self.boid_render_prog.use()
        
        aspect = self.width() / max(self.height(), 1)
        proj = np.array(self._get_perspective_matrix(60, aspect, 0.1, 5000.0), dtype=np.float32)
        view = np.array(self._get_view_matrix(), dtype=np.float32)
        
        self.boid_render_prog.set_uniform_matrix4("projection", proj)
        self.boid_render_prog.set_uniform_matrix4("view", view)
        self.boid_render_prog.set_uniform_f("time", self._elapsed_time)

        glBindBufferBase(GL_SHADER_STORAGE_BUFFER, 0, self.boid_mgr.ssbo_boids)
        glBindBuffer(GL_ARRAY_BUFFER, self.boid_vbo)
        glEnableVertexAttribArray(0); glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, 24, ctypes.c_void_p(0))
        glEnableVertexAttribArray(1); glVertexAttribPointer(1, 3, GL_FLOAT, GL_FALSE, 24, ctypes.c_void_p(12))
        
        # Indirect Draw call: Truly GPU-driven
        glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, self.boid_ibo)
        glBindBuffer(GL_DRAW_INDIRECT_BUFFER, self.boid_mgr.indirect_buffer)
        glDrawElementsIndirect(GL_TRIANGLES, GL_UNSIGNED_INT, None)
        
        glDisableVertexAttribArray(0); glDisableVertexAttribArray(1)
        glBindBuffer(GL_DRAW_INDIRECT_BUFFER, 0)
        self.boid_render_prog.stop()

    def _get_perspective_matrix(self, fov, aspect, near, far):
        f = 1.0 / math.tan(math.radians(fov) / 2.0)
        return [f/aspect, 0, 0, 0, 0, f, 0, 0, 0, 0, (far+near)/(near-far), -1, 0, 0, (2*far*near)/(near-far), 0]

    def _get_view_matrix(self):
        from OpenGL.GL import glGetFloatv, GL_MODELVIEW_MATRIX
        return glGetFloatv(GL_MODELVIEW_MATRIX)
    def _sync_editor_controllers(self):
        """Ensure all objects with AI/Player controllers have them active in the editor."""
        active_ids = {obj.id for obj in self.scene_objects if getattr(obj, 'controller_type', 'None') != 'None'}
        
        # Cleanup
        for oid in list(self._editor_controllers.keys()):
            if oid not in active_ids:
                del self._editor_controllers[oid]
        
        # Create & Update Flock
        current_ai_controllers = [c for c in self._editor_controllers.values() if isinstance(c, AIController)]
        for obj in self.scene_objects:
            if obj.id not in self._editor_controllers and getattr(obj, 'controller_type', 'None') != 'None':
                ctype = obj.controller_type
                if ctype == "AI (CPU)": 
                    ctrl = AIController(obj)
                    self._editor_controllers[obj.id] = ctrl
                    current_ai_controllers.append(ctrl)
                elif ctype == "Player": self._editor_controllers[obj.id] = PlayerController(obj)
                elif ctype == "AI (GPU Fish)": self._editor_controllers[obj.id] = AIGPUFishController(obj)
                elif ctype == "AI (GPU Bird)": self._editor_controllers[obj.id] = AIGPUBirdController(obj)
        
        # Synchronize flock for all AI
        for ctrl in current_ai_controllers:
            ctrl.flock = current_ai_controllers

    def _draw_voxel_world(self, obj, shader_active=False):
        """Stable, single-mesh rendering for Voxel Worlds."""
        v_type      = str(getattr(obj, 'voxel_type', 'Round')).strip()
        v_radius    = float(getattr(obj, 'voxel_radius', 5.0))
        seed        = int(getattr(obj, 'voxel_seed', 123))
        smooth      = int(getattr(obj, 'voxel_smooth_iterations', 2))
        block_size  = float(getattr(obj, 'voxel_block_size', 0.15))
        render_style= str(getattr(obj, 'voxel_render_style', 'Smooth'))
        layers      = getattr(obj, 'voxel_layers', [])
        obj_pos     = np.array(obj.position, dtype=np.float32)

        # Compute resolution from block_size + planet extent
        if v_type.lower() == "round":
            extent     = v_radius * 1.5
            world_size = extent * 2.0
            res = max(16, min(512, round(world_size / block_size)))
        else:
            res = max(16, min(512, round(100.0 / max(block_size, 0.1))))

        # Override smoothing for Minecraft style (none) vs Smooth (from prop)
        if render_style == 'Minecraft':
            smooth = 0

        layers_hash = hash(str(layers))
        cache_key = (f"voxel_{obj.id}_{seed}_{v_type}_{v_radius}"
                     f"_{block_size}_{smooth}_{render_style}_{layers_hash}")
        # Simple chunking strategy: avoid generating a single huge grid for
        # large world sizes. Break the volume into smaller chunks around the
        # camera and generate only those chunks (with simple LOD).
        res_limit = getattr(obj, 'voxel_max_single_chunk_res', getattr(self, 'voxel_max_single_chunk_res', 128))

        if cache_key not in self.mesh_cache:
            if v_type.lower() == "round":
                extent = v_radius * 1.5
                min_p  = obj_pos - extent
                max_p  = obj_pos + extent
                size   = np.array([extent * 2] * 3, dtype=np.float32)
            else:
                min_p = obj_pos + np.array([-50, -20, -50], dtype=np.float32)
                max_p = obj_pos + np.array([ 50,  20,  50], dtype=np.float32)
                size  = np.array([100.0, 40.0, 100.0], dtype=np.float32)

            # Generate mesh in a background thread so we never block the render loop.
            # Even for small single-chunk planets (res≤128) the numpy calculation
            # can take 1–4 s; running it async keeps the viewport responsive.
            if res <= res_limit or not getattr(obj, 'voxel_lod_enabled', True):
                # Mark as in-progress so we don't schedule it twice
                if cache_key not in self._voxel_generation_in_progress:
                    self.mesh_cache[cache_key] = None   # placeholder
                    with self._voxel_gen_lock:
                        self._voxel_generation_in_progress.add(cache_key)

                    def _gen_single(cache_key_local, min_p_local, max_p_local, size_local):
                        try:
                            # Use a small margin even for single chunks to avoid edge artifacts
                            margin = 2
                            vox_step = size_local / max(1, res - 1)
                            p_min = min_p_local - margin * vox_step
                            p_max = max_p_local + margin * vox_step
                            padded_r = res + 2 * margin

                            grid = VoxelEngine.generate_density_grid(
                                resolution=padded_r, seed=seed, mode=v_type,
                                radius=v_radius, layers=layers,
                                center=obj_pos, min_p=p_min, max_p=p_max
                            )
                            if smooth > 0:
                                grid = VoxelEngine.smooth_grid(grid, iterations=smooth)
                            if render_style == 'Minecraft':
                                verts_s, idx_s, norms_s = VoxelEngine.blocky_mesh(grid)
                            else:
                                verts_s, idx_s, norms_s = VoxelEngine.surface_nets(grid)
                            if len(verts_s) > 0:
                                p_size = p_max - p_min
                                p_offset = (p_min + p_max) * 0.5 - obj_pos
                                verts_out = np.ascontiguousarray(verts_s * p_size + p_offset, dtype=np.float32)
                                norms_out = np.ascontiguousarray(norms_s, dtype=np.float32)
                                with self._voxel_gen_lock:
                                    self._pending_voxel_chunks[cache_key_local] = (verts_out, idx_s, norms_out)
                        except Exception as e:
                            print(f"[VOXEL] Single-chunk generation failed: {e}")
                        finally:
                            with self._voxel_gen_lock:
                                self._voxel_generation_in_progress.discard(cache_key_local)

                    t = threading.Thread(target=_gen_single,
                                         args=(cache_key, min_p, max_p, size),
                                         daemon=True)
                    t.start()
            else:
                # VOXEL-ALIGNED CHUNKING:
                # Instead of dividing the world radius by N, we force each chunk to 
                # span a fixed integer number of voxels (res_limit).
                # This ensures boundaries are perfectly synchronized.
                vox_step = float(block_size)
                chunk_vox_size = float(res_limit) * vox_step
                
                min_p = np.array(min_p, dtype=np.float32)
                max_p = np.array(max_p, dtype=np.float32)
                
                # Number of chunks needed to cover the extent
                nx = int(np.ceil((max_p[0] - min_p[0]) / chunk_vox_size))
                ny = int(np.ceil((max_p[1] - min_p[1]) / chunk_vox_size))
                nz = int(np.ceil((max_p[2] - min_p[2]) / chunk_vox_size))

                # Camera-local chunk indices
                cam_pos = np.array(self._cam3d.pos, dtype=np.float32)
                rel = cam_pos - min_p
                cam_ix = int(np.clip(int(np.floor(rel[0] / chunk_vox_size)), 0, nx - 1))
                cam_iy = int(np.clip(int(np.floor(rel[1] / chunk_vox_size)), 0, ny - 1))
                cam_iz = int(np.clip(int(np.floor(rel[2] / chunk_vox_size)), 0, nz - 1))

                neighborhood = int(getattr(obj, 'voxel_prefetch_neighborhood', getattr(self, 'voxel_prefetch_neighborhood', 1)))
                chunk_keys = []
                for ix in range(max(0, cam_ix - neighborhood), min(nx, cam_ix + neighborhood + 1)):
                    for iy in range(max(0, cam_iy - neighborhood), min(ny, cam_iy + neighborhood + 1)):
                        for iz in range(max(0, cam_iz - neighborhood), min(nz, cam_iz + neighborhood + 1)):
                            cmin = min_p + np.array([ix, iy, iz], dtype=np.float32) * chunk_vox_size
                            cmax = cmin + chunk_vox_size
                            ccenter = (cmin + cmax) * 0.5

                            # LOD: reduce resolution for distant chunks
                            dist = np.linalg.norm(ccenter - cam_pos)
                            if dist > v_radius * 2.5:
                                lod_factor = 4
                            elif dist > v_radius:
                                lod_factor = 2
                            else:
                                lod_factor = 1
                            
                            # Voxel-aligned resolution for this LOD level
                            per_res = max(4, int(res_limit // lod_factor) + 1)

                            chunk_cache_key = f"{cache_key}_c_{ix}_{iy}_{iz}_{per_res}"
                            if chunk_cache_key not in self.mesh_cache:
                                # Schedule background generation for this chunk.
                                with self._voxel_gen_lock:
                                    if chunk_cache_key in self._voxel_generation_in_progress:
                                        pass
                                    else:
                                        self._voxel_generation_in_progress.add(chunk_cache_key)
                                        # mark mesh_cache placeholder so render knows it's scheduled
                                        self.mesh_cache[chunk_cache_key] = None

                                        def _gen_chunk(cmin, cmax, ccenter, per_res, chunk_cache_key, chunk_size_local):
                                            try:
                                                # Progressive: generate a quick low-res pass first
                                                per_res_low = max(8, int(per_res // 4))
                                                res_list = [per_res_low] if per_res_low < per_res else []
                                                res_list.append(per_res)

                                                for r in res_list:
                                                    # SEAMLESS STRATEGY: 
                                                    # Generate a grid slightly larger than the actual chunk (overlap).
                                                    # This ensures smoothing and Surface Nets have context for neighbors.
                                                    margin = 2 # 2 voxel overlap
                                                    padded_r = r + 2 * margin
                                                    
                                                    # Calculate world-space voxel size
                                                    vox_step = chunk_size_local / max(1, r - 1)
                                                    p_min = cmin - margin * vox_step
                                                    p_max = cmax + margin * vox_step
                                                    
                                                    grid = VoxelEngine.generate_density_grid(
                                                        resolution=padded_r, seed=seed, mode=v_type,
                                                        radius=v_radius, layers=layers,
                                                        center=obj_pos, min_p=p_min, max_p=p_max
                                                    )
                                                    if smooth > 0:
                                                        grid = VoxelEngine.smooth_grid(grid, iterations=smooth)

                                                    if render_style == 'Minecraft':
                                                        verts_c, idx_c, norms_c = VoxelEngine.blocky_mesh(grid)
                                                    else:
                                                        # Use SEAMLESS mode (pad=False) to avoid capping at margins
                                                        verts_c, idx_c, norms_c = VoxelEngine.surface_nets(grid, pad=False)

                                                    if len(verts_c) > 0:
                                                        # verts_c are in [-0.5, 0.5] range of the PADDED grid.
                                                        # Project them to world space using the PADDED bounds.
                                                        p_size = p_max - p_min
                                                        p_offset = (p_min + p_max) * 0.5 - obj_pos
                                                        verts_w = verts_c * p_size + p_offset
                                                        
                                                        # STRICT CLIPPING:
                                                        # Only keep triangles whose centroid is inside the core chunk bounds.
                                                        # This ensures only one chunk renders the shared boundary, 
                                                        # eliminating Z-fighting and precision gaps.
                                                        cmin_rel = cmin - obj_pos
                                                        cmax_rel = cmax - obj_pos
                                                        
                                                        indices_out = []
                                                        for t in range(0, len(idx_c), 3):
                                                            i1, i2, i3 = idx_c[t], idx_c[t+1], idx_c[t+2]
                                                            v1, v2, v3 = verts_w[i1], verts_w[i2], verts_w[i3]
                                                            centroid = (v1 + v2 + v3) / 3.0
                                                            
                                                            # HALF-OPEN INTERVAL CLIPPING: [min, max)
                                                            # Ensures exactly one chunk owns any boundary triangle.
                                                            if (np.all(centroid >= cmin_rel) and 
                                                                np.all(centroid < cmax_rel)):
                                                                indices_out.extend([i1, i2, i3])
                                                        
                                                        if len(indices_out) > 0:
                                                            verts_out = np.ascontiguousarray(verts_w, dtype=np.float32)
                                                            idx_out   = np.array(indices_out, dtype=np.uint32)
                                                            norms_out = np.ascontiguousarray(norms_c, dtype=np.float32)
                                                            
                                                            with self._voxel_gen_lock:
                                                                self._pending_voxel_chunks[chunk_cache_key] = (verts_out, idx_out, norms_out)

                                            except Exception as e:
                                                print(f"[VOXEL] Chunk generation failed {chunk_cache_key}: {e}")
                                            finally:
                                                with self._voxel_gen_lock:
                                                    if chunk_cache_key in self._voxel_generation_in_progress:
                                                        self._voxel_generation_in_progress.remove(chunk_cache_key)

                                        t = threading.Thread(target=_gen_chunk, args=(cmin, cmax, ccenter, per_res, chunk_cache_key, chunk_vox_size), daemon=True)
                                        t.start()

                            chunk_keys.append(chunk_cache_key)

                # Store the list of chunk keys for this object so rendering can
                # iterate over them later.
                self.mesh_cache[cache_key] = chunk_keys
                
        data = self.mesh_cache.get(cache_key)
        if isinstance(data, list):
            # chunked cache: iterate each chunk VAO. 
            # Disable culling so we can see the interior of caves/planets.
            glDisable(GL_CULL_FACE)
            for ck in data:
                d = self.mesh_cache.get(ck)
                if not d:
                    continue
                glBindVertexArray(d['vao'])
                glDrawElements(GL_TRIANGLES, d['count'], GL_UNSIGNED_INT, None)
                # Draw wireframe overlay for Minecraft/Blocky style to show seams
                if render_style == 'Minecraft':
                    try:
                        glPolygonMode(GL_FRONT_AND_BACK, GL_LINE)
                        glDisable(GL_CULL_FACE)
                        glLineWidth(1.0)
                        glDrawElements(GL_TRIANGLES, d['count'], GL_UNSIGNED_INT, None)
                    except Exception:
                        pass
                    finally:
                        try:
                            glPolygonMode(GL_FRONT_AND_BACK, GL_FILL)
                        except Exception:
                            pass

                glBindVertexArray(0)
            glEnable(GL_CULL_FACE)
        elif data:
            glDisable(GL_CULL_FACE)
            glBindVertexArray(data['vao'])
            glDrawElements(GL_TRIANGLES, data['count'], GL_UNSIGNED_INT, None)
            if render_style == 'Minecraft':
                try:
                    glPolygonMode(GL_FRONT_AND_BACK, GL_LINE)
                    glDisable(GL_CULL_FACE)
                    glLineWidth(1.0)
                    glDrawElements(GL_TRIANGLES, data['count'], GL_UNSIGNED_INT, None)
                except Exception:
                    pass
                finally:
                    try:
                        glPolygonMode(GL_FRONT_AND_BACK, GL_FILL)
                    except Exception:
                        pass
            glBindVertexArray(0)
            glEnable(GL_CULL_FACE)

    def _create_voxel_vao(self, verts, idx, norms):
        """Create a VAO for voxel mesh with high-precision gradient normals."""
        vao = glGenVertexArrays(1)
        glBindVertexArray(vao)
        
        vbo = glGenBuffers(1)
        glBindBuffer(GL_ARRAY_BUFFER, vbo)
        glBufferData(GL_ARRAY_BUFFER, verts.nbytes, verts, GL_STATIC_DRAW)
        glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, 12, None)
        glEnableVertexAttribArray(0)
        
        nvbo = glGenBuffers(1)
        glBindBuffer(GL_ARRAY_BUFFER, nvbo)
        glBufferData(GL_ARRAY_BUFFER, norms.nbytes, norms, GL_STATIC_DRAW)
        glVertexAttribPointer(2, 3, GL_FLOAT, GL_FALSE, 12, None)
        glEnableVertexAttribArray(2)
        
        ibo = glGenBuffers(1)
        glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, ibo)
        glBufferData(GL_ELEMENT_ARRAY_BUFFER, idx.nbytes, idx, GL_STATIC_DRAW)
        
        glBindVertexArray(0)
        return {'vao': vao, 'vbo': vbo, 'ibo': ibo, 'count': len(idx)}
