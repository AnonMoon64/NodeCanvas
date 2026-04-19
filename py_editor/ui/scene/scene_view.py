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
    objects_changed = pyqtSignal()
    state_about_to_change = pyqtSignal()
    state_changed = pyqtSignal()

    def __init__(self, parent=None):
        if QOpenGLWidget:
            fmt = QSurfaceFormat()
            fmt.setDepthBufferSize(24)
            fmt.setSamples(4)
            fmt.setSwapInterval(0) # 0 = VSync Off (uncaps framerate), 1 = VSync On
            QSurfaceFormat.setDefaultFormat(fmt)
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setAcceptDrops(True)

        self._mode = "3D"
        self._cam3d = Camera3D()
        self._cam2d = Camera2D()
        self._follow_enabled = False
        self._follow_target = None

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
        # self._update_view_combo_pos() # MOVED TO END

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

        # Snap toggle
        self._snap_enabled = True
        self._snap_btn = QPushButton("Snap")
        self._snap_btn.setCheckable(True)
        self._snap_btn.setChecked(True)
        self._snap_btn.setFixedSize(50, 22)
        self._snap_btn.setStyleSheet("""
            QPushButton { background: none; border: none; color: #aaa; font-size: 10px; font-weight: bold; }
            QPushButton:checked { background: #4fc3f7; color: #000; border-radius: 3px; }
            QPushButton:hover { color: #fff; }
        """)
        self._snap_btn.clicked.connect(lambda c: setattr(self, '_snap_enabled', bool(c)))
        hud_lay.addWidget(self._snap_btn)

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
        
        # FPS Counter UI (Top Right)
        from PyQt6.QtWidgets import QLabel
        self._fps_label = QLabel("0 FPS", self)
        self._fps_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._fps_label.setStyleSheet("""
            QLabel {
                background: rgba(40, 40, 45, 180); 
                color: #4fc3f7; 
                border: 1px solid #444; 
                border-radius: 6px;
                font-size: 10px;
                font-weight: bold;
                padding: 0px 4px;
            }
        """)
        self._fps_label.setFixedHeight(30)
        self._fps_label.setFixedWidth(60)
        
        self._fps_counter = 0
        self._fps_accumulator = 0.0
        self._current_fps = 0
        
        # Finally position all HUD elements
        self._update_view_combo_pos()

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
        # Static-batch cache for spawner children (one draw call per mesh_path)
        from py_editor.ui.scene.spawner_batcher import SpawnerBatchCache, ChunkSpawnBatchCache
        self._spawner_batches = SpawnerBatchCache()
        self._chunk_spawn_batches = ChunkSpawnBatchCache()

    def get_selected_objects(self):
        return [o for o in self.scene_objects if o.selected]

    def set_mode(self, mode: str):
        self._mode = mode
        self.update()

    def start_render_loop(self):
        self._last_time = time.perf_counter()
        self._frame_timer.start(0)

    def stop_render_loop(self):
        self._frame_timer.stop()

    def load_scene_data(self, data: dict):
        """Load scene objects from a data dictionary (from export_scene_data)."""
        from py_editor.core import paths as _ap
        data = _ap.resolve_on_load(data)
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
        dt = max(now - self._last_time, 0.001) # Avoid zero-delta issues
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
        
        # Update FPS
        self._fps_counter += 1
        self._fps_accumulator += dt
        if self._fps_accumulator >= 1.0:
            fps = int(self._fps_counter / self._fps_accumulator)
            self._current_fps = fps
            self._fps_label.setText(f"{fps} FPS")
            self.fps_updated.emit(fps)
            self._fps_counter = 0
            self._fps_accumulator = 0.0
            
        self.update()
        
        # Accumulate sim dt for paintGL — controller updates, GPU boid sim,
        # and readbacks all issue GL calls that require the widget's GL context
        # to be current. QTimer fires outside paintGL so calling them here
        # silently corrupts the heap on Windows (0xc0000374) and leaves boids
        # pinned at (0,0,0). paintGL consumes _pending_sim_dt each frame.
        self._pending_sim_dt = getattr(self, '_pending_sim_dt', 0.0) + min(dt, 0.1)
        
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

        # Per-frame budget: cap BOTH chunk count and total vertex bytes.
        # Blocky chunks can be 50-100× the vertex count of smooth ones, so a
        # fixed 4-chunks-per-frame was still enough to spike to 6 fps. Byte-cap
        # at ~4MB/frame (≈130k interleaved verts) keeps the GL upload bounded.
        MAX_CHUNKS = 4
        MAX_BYTES = 4 * 1024 * 1024
        uploaded_bytes = 0
        uploaded_chunks = 0
        keys_all = list(self._pending_voxel_chunks.keys())
        keys = keys_all[:MAX_CHUNKS]
        for key in keys:
            if uploaded_chunks >= MAX_CHUNKS or uploaded_bytes >= MAX_BYTES:
                break
            data = None
            try:
                data = self._pending_voxel_chunks.pop(key)
            except KeyError:
                continue
            # Empty-dict sentinel: chunk was generated but produced no geometry.
            # Store the sentinel in mesh_cache so the scheduler sees it as "done"
            # (isinstance(existing, dict) is True) and never reschedules it.
            if isinstance(data, dict):
                self.mesh_cache[key] = {}
                continue
            if not data:
                continue
            colors = None
            spawns = []
            if len(data) == 5:
                verts, idx, norms, colors, spawns = data
            elif len(data) == 4:
                verts, idx, norms, colors = data
            else:
                verts, idx, norms = data
            try:
                new_vao = self._create_voxel_vao(verts, idx, norms, colors)
                new_vao['verts_cpu'] = verts
                new_vao['idx_cpu']   = idx.reshape(-1, 3)
                if spawns:
                    new_vao['spawns'] = spawns
                uploaded_bytes += int(verts.nbytes) + int(idx.nbytes)
                uploaded_chunks += 1
            except Exception as e:
                print(f"[VOXEL] Failed to create VAO for {key}: {e}")
                continue

            # If an older VAO exists for this key, delete GL resources
            old = self.mesh_cache.get(key)
            if isinstance(old, dict) and 'vao' in old:
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
                if old.get('cvbo') is not None:
                    try:
                        glDeleteBuffers(1, [old['cvbo']])
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
            
            # Double click to follow
            if found:
                now = time.time()
                if hasattr(self, '_last_click_time') and now - self._last_click_time < 0.3:
                    if self._follow_target == found:
                        self._follow_enabled = not self._follow_enabled
                    else:
                        self._follow_enabled = True
                        self._follow_target = found
                    print(f"[VIEWPORT] Camera Follow: {'ON' if self._follow_enabled else 'OFF'} for {found.name}")
                self._last_click_time = now

            new_sel = [o for o in self.scene_objects if o.selected]
            self.sync_ui_to_selection()
            self.object_selected.emit(new_sel)
            self.update()
        elif event.button() == Qt.MouseButton.RightButton:
            self._rmb = True
            self._last_mouse = event.position()
            self.setCursor(Qt.CursorShape.BlankCursor)

    def mouseDoubleClickEvent(self, event):
        """On double click, center and zoom in on the object."""
        mx, my = int(event.position().x()), int(event.position().y())
        found = self._pick_object(mx, my)
        if found:
            # Focus camera on the object
            radius = max(found.scale) if hasattr(found, 'scale') else 1.0
            self._cam3d.focus_on(found.position, radius)
            # Ensure it becomes selected as well
            for o in self.scene_objects:
                o.selected = (o == found)
            self.sync_ui_to_selection()
            self.object_selected.emit([found])
            self.update()

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
                        if getattr(self, '_snap_enabled', False) and self.grid_size > 0:
                            gs = self.grid_size
                            ai = {'x': 0, 'y': 1, 'z': 2}[self._gizmo_axis]
                            sel.position[ai] = round(sel.position[ai] / gs) * gs
                    
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
        if hasattr(self, '_fps_label'):
            self._fps_label.move(w - 360, 10)

    def paintGL(self):
        # Run controller + GPU boid sim here so the widget's GL context is
        # guaranteed current. See note in _tick on why this can't live there.
        dt_sim = getattr(self, '_pending_sim_dt', 0.0)
        self._pending_sim_dt = 0.0
        if dt_sim > 0.0:
            try:
                self._sync_editor_controllers()
                for ctrl in self._editor_controllers.values():
                    try: ctrl.update(dt_sim)
                    except Exception: pass
                for ctrl in self._editor_controllers.values():
                    try: ctrl.update_physics(dt_sim)
                    except Exception: pass
                try:
                    from py_editor.core.physics import resolve_collisions, resolve_terrain_collision, integrate_gravity
                    integrate_gravity(self.scene_objects, dt_sim)
                    resolve_collisions(self.scene_objects, dt_sim)
                    # Ground / terrain / mesh-AABB collision
                    vox_objs  = [o for o in self.scene_objects if o.obj_type == 'voxel_world']
                    land_objs = [o for o in self.scene_objects if o.obj_type == 'landscape']
                    resolve_terrain_collision(
                        self.scene_objects, self.mesh_cache,
                        voxel_objects=vox_objs,
                        landscape_objects=land_objs)
                except Exception: pass
                if hasattr(self, 'boid_mgr'):
                    universe_obj = next((o for o in self.scene_objects if o.obj_type == 'universe'), None)
                    target = universe_obj.position if universe_obj else (0, 0, 0)
                    self.boid_mgr.update(dt_sim, self._elapsed_time, target)
            except Exception as e:
                if getattr(self, '_last_sim_err', None) != str(e):
                    print(f"[SIM] {e}")
                    self._last_sim_err = str(e)

        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glEnable(GL_CULL_FACE)
        glCullFace(GL_BACK)
        try: glDisable(GL_FOG)
        except Exception: pass
        
        # Global state reset for stability
        glUseProgram(0)
        glBindBuffer(GL_ARRAY_BUFFER, 0)
        glBindVertexArray(0)
        for i in range(8):
            glActiveTexture(GL_TEXTURE0 + i)
            glBindTexture(GL_TEXTURE_2D, 0)
        glActiveTexture(GL_TEXTURE0)
        
        w, h = self.width(), self.height()
        if w < 1 or h < 1: return

        # Process any pending CPU-generated chunk meshes and create VAOs
        try:
            self._process_pending_voxel_chunks()
        except Exception:
            pass

        if self._mode == "3D":
            # --- Camera Follow Logic ---
            if self._follow_enabled and self._follow_target:
                target = self._follow_target
                pos = target.position
                
                # If we don't have an offset yet, calculate it
                if not hasattr(self, '_follow_offset') or self._last_follow_id != target.id:
                    self._follow_offset = _sub(self._cam3d.pos, pos)
                    self._last_follow_id = target.id
                
                # Maintain the offset (Smooth follow)
                new_pos = _add(pos, self._follow_offset)
                self._cam3d.pos = [new_pos[0], new_pos[1], new_pos[2]]
                
                # Optionally keep looking at it
                self._cam3d.focus_on(pos, getattr(target, 'radius', 1.0))
                # Recalculate offset after focus_on as it might change the distance
                self._follow_offset = _sub(self._cam3d.pos, pos)
            
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
            
            # Always draw grid in editor – help spatial awareness
            self._draw_grid_3d()
            
            # 3. Landscape
            for obj in self.scene_objects:
                if obj.obj_type == 'landscape' and obj.active:
                    from py_editor.ui.procedural_system import draw_landscape_3d
                    draw_landscape_3d(obj, self)
            
            # 4. Ocean (flat) + Ocean World (spherical)
            weather_obj = next((o for o in self.scene_objects
                                if o.obj_type == 'weather' and o.active), None)
            
            for obj in self.scene_objects:
                if obj.obj_type == 'ocean' and obj.active:
                    from py_editor.ui.procedural_ocean import render_ocean_gpu
                    render_ocean_gpu(self._cam3d.pos, obj, self._elapsed_time, weather_obj)
                elif obj.obj_type == 'ocean_world' and obj.active:
                    from py_editor.ui.procedural_ocean_world import render_ocean_world
                    render_ocean_world(self._cam3d.pos, obj, self._elapsed_time, weather_obj)
            
            # 5. Primitives
            self._draw_scene_objects_3d()
            
            # 5.5 GPU Boids (Instanced)
            self._draw_gpu_boids()

            # 5.55 Weather primitives (global, procedural) — drive particles
            try:
                weather_obj = next((o for o in self.scene_objects
                                    if o.obj_type == 'weather' and o.active), None)
                if weather_obj:
                    from py_editor.core.weather_system import update_weather
                    # dt derived from the particle manager clock is inside update_weather
                    update_weather(weather_obj, self.scene_objects, self._cam3d.pos, 0.0)
            except Exception:
                pass

            # 5.6 Particles (CPU sim + instanced billboard sprites)
            try:
                from py_editor.core.particle_system import get_particle_manager
                glPushMatrix()
                try:
                    # Particles are world-space, so we only want the camera view transform
                    get_particle_manager().update_and_draw(self._cam3d.pos, None, None)
                finally:
                    glPopMatrix()
            except Exception as e:
                if getattr(self, '_last_render_err', None) != str(e):
                    print(f"[RENDER ERROR] Particles: {e}")
                    self._last_render_err = str(e)
                pass # Silencing log bloat but keeping one-time report
            
            # 6. Gizmos (Restored)
            from py_editor.ui.scene.render_manager import _draw_gizmo
            selected_obj = next((o for o in self.scene_objects if o.selected), None)
            if selected_obj:
                _draw_gizmo(selected_obj.position, selected_axis=self._gizmo_axis,
                            mode=self._gizmo_mode, camera=self._cam3d)
            
            # --- Underwater post-effect ---
            try:
                self._draw_underwater_overlay()
            except Exception as e:
                if getattr(self, '_last_uw_err', None) != str(e):
                    print(f"[RENDER] Underwater overlay: {e}")
                    self._last_uw_err = str(e)

            # --- Viewport Overlay ---
            self._draw_viewport_overlay(w, h)
        else:
            self._cam2d.apply_gl(w, h)
            self._draw_grid_2d()
            self._draw_scene_objects_2d()

    def _draw_underwater_overlay(self):
        """Seamless underwater tint/fog when the camera dips below an ocean.

        Supports both flat ``ocean`` objects (plane at ``landscape_ocean_level``)
        and ``ocean_world`` planets (sphere of water around a centre). The
        depth below the surface drives both the tint strength and an
        exponential-depth fog, so the transition is smooth rather than
        flipping on at Y=waterline.

        Uses fixed-function pipeline so it works alongside the compat-profile
        shaders without needing a dedicated post shader.
        """
        cam = self._cam3d.pos
        cam_y = float(cam[1])
        depth = 0.0
        tint = None  # RGB tuple when underwater

        for o in self.scene_objects:
            if not getattr(o, 'active', False): continue
            if o.obj_type == 'ocean':
                lvl = float(getattr(o, 'landscape_ocean_level', 0.0)) + float(o.position[1])
                # Sample the live FFT displacement at camera XZ so the waterline
                # tracks actual wave crests/troughs instead of a flat Y plane —
                # otherwise the overlay snaps on/off when waves roll past the
                # camera instead of blending seamlessly at the surface.
                wave_h = 0.0
                gen = getattr(o, '_fft_gen_cascade0', None)
                if gen is not None:
                    try:
                        wave_h = float(gen.get_height_at(cam[0], cam[2]))
                    except Exception:
                        wave_h = 0.0
                surface_y = lvl + wave_h
                if cam_y < surface_y:
                    d = surface_y - cam_y
                    if d > depth:
                        depth = d
                        tint = getattr(o, 'ocean_color', [0.05, 0.25, 0.35, 1.0])
            elif o.obj_type == 'ocean_world':
                c = np.array(o.position, dtype=np.float32)
                r = float(getattr(o, 'ocean_radius',
                                   getattr(o, 'planet_radius', 100.0)))
                dist = float(np.linalg.norm(np.array(cam, dtype=np.float32) - c))
                if dist < r:
                    d = r - dist
                    if d > depth:
                        depth = d
                        tint = getattr(o, 'ocean_color', [0.04, 0.20, 0.30, 1.0])

        if tint is None or depth <= 0.0:
            try: glDisable(GL_FOG)
            except Exception: pass
            return

        # Exponential saturation: shallow water barely tints, deep water fully
        # swallows the view. Tuned so 1u depth ≈ 12%, 15u ≈ 80%.
        tint_alpha = 1.0 - np.exp(-depth / 6.0)
        tint_alpha = float(np.clip(tint_alpha * 0.85, 0.0, 0.92))
        tr, tg, tb = float(tint[0]), float(tint[1]), float(tint[2])

        # Distance fog — blends scene geometry with the water colour so far
        # objects fade out behind a wall of murk.
        try:
            glFogi(GL_FOG_MODE, GL_EXP2)
            glFogfv(GL_FOG_COLOR, (tr, tg, tb, 1.0))
            glFogf(GL_FOG_DENSITY, float(np.clip(0.008 + depth * 0.0015, 0.008, 0.06)))
            glEnable(GL_FOG)
        except Exception:
            pass

        # Fullscreen tint quad drawn in clip space (no matrix setup needed).
        glUseProgram(0)
        glDisable(GL_DEPTH_TEST)
        glDisable(GL_CULL_FACE)
        glDisable(GL_LIGHTING)
        glDisable(GL_TEXTURE_2D)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glMatrixMode(GL_PROJECTION); glPushMatrix(); glLoadIdentity()
        glMatrixMode(GL_MODELVIEW);  glPushMatrix(); glLoadIdentity()
        glColor4f(tr, tg, tb, tint_alpha)
        glBegin(GL_QUADS)
        glVertex3f(-1.0, -1.0, 0.0)
        glVertex3f( 1.0, -1.0, 0.0)
        glVertex3f( 1.0,  1.0, 0.0)
        glVertex3f(-1.0,  1.0, 0.0)
        glEnd()
        glMatrixMode(GL_PROJECTION); glPopMatrix()
        glMatrixMode(GL_MODELVIEW);  glPopMatrix()
        glColor4f(1.0, 1.0, 1.0, 1.0)
        glEnable(GL_DEPTH_TEST)

    def _draw_viewport_overlay(self, w, h):
        # Ensure 2D overlay isn't culled or depth-tested against 3D scene
        glDisable(GL_DEPTH_TEST)
        glDisable(GL_CULL_FACE)
        glUseProgram(0)
        
        # Draw Orientation Widget and Logs
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # 1. Orientation Widget (Bottom Left - The "L" thing)
        self._draw_orientation_widget(painter, w, h)
        
        # 2. UE5 Style On-Screen Logs (Top Left)
        self._draw_onscreen_logs(painter, w, h)

        # 3. FPS overlay was removed (moved to HUD)
        
        painter.end()

    def _draw_onscreen_logs(self, painter, w, h):
        # Add a warning if any landscape is in the scene
        has_landscape = any(o.obj_type == 'landscape' for o in self.scene_objects)
        if has_landscape:
            painter.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            painter.setPen(QColor(255, 80, 80))
            painter.drawText(20, 30, "⚠️ WARNING: Landscape primitive is DEPRECATED. Use Voxel World instead.")

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
        painter.save()
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

        # Origin hub (Fully opaque for maximum visibility)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(120, 120, 120, 255))
        painter.drawEllipse(QPointF(cx, cy), 5, 5)
        
        # Draw Axes
        axes = [
            ((1, 0, 0), QColor(255, 60, 60, 255), "X"),
            ((0, 1, 0), QColor(60, 255, 60, 255), "Y"),
            ((0, 0, 1), QColor(60, 60, 255, 255), "Z")
        ]
        
        for vec, color, label in axes:
            end_pt = project(vec)
            # Thicker, solid color pen for visibility. 
            # Disable AA for the line itself to avoid 'thinning' artifacts on some drivers
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
            painter.setPen(QPen(color, 3, Qt.PenStyle.SolidLine))
            painter.drawLine(QPointF(cx, cy), end_pt)
            
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            painter.drawText(int(end_pt.x() - 4), int(end_pt.y() + 4), label)
            
        painter.restore()

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
        
        atmo = next((o for o in self.scene_objects if o.obj_type == 'atmosphere' and o.active), None)
        from py_editor.ui.procedural_atmosphere import get_sun_direction, get_sun_color, get_ambient_color
        sun_dir = get_sun_direction(atmo)
        sun_color = get_sun_color(atmo)
        amb_color = get_ambient_color(atmo)

        # Legacy fixed-function light setup
        try:
            glEnable(GL_LIGHT0)
            from OpenGL.GL import glLightfv, GL_LIGHT0, GL_POSITION, GL_DIFFUSE, GL_AMBIENT, GL_SPECULAR
            glLightfv(GL_LIGHT0, GL_POSITION, (sun_dir[0], sun_dir[1], sun_dir[2], 0.0))
            glLightfv(GL_LIGHT0, GL_DIFFUSE,  (sun_color[0], sun_color[1], sun_color[2], 1.0))
            glLightfv(GL_LIGHT0, GL_SPECULAR, (sun_color[0], sun_color[1], sun_color[2], 1.0))
            glLightfv(GL_LIGHT0, GL_AMBIENT,  (amb_color[0], amb_color[1], amb_color[2], 1.0))
        except Exception: pass

        # Sort objects by hierarchy: render parents before children
        # We'll use a recursive renderer to handle nested transforms correctly.
        lookup = {obj.id: obj for obj in self.scene_objects}
        top_level = [obj for obj in self.scene_objects if getattr(obj, 'parent_id', None) not in lookup]
        
        def render_hierarchy(obj_list, sun_direction):
            for obj in obj_list:
                # Skip procedural primitives handled by main loop (Atmosphere, Universe, etc.)
                is_proc = obj.obj_type in ('atmosphere', 'ocean', 'landscape', 'universe', 'clouds', 'cloud_layer', 'weather')
                
                glPushMatrix()
                glTranslatef(*obj.position)
                glRotatef(obj.rotation[0], 1, 0, 0)
                glRotatef(obj.rotation[1], 0, 1, 0)
                glRotatef(obj.rotation[2], 0, 0, 1)
                glScalef(*obj.scale)
                
                if not is_proc:
                    if obj.visible:
                        s_name = getattr(obj, 'shader_name', 'Standard')
                        active_shader = get_shader(s_name)
                        if active_shader:
                            active_shader.use()
                            # Default vertex attribute 3 (gl_Color in compat profile)
                            # to (0,0,0,0) so Standard shader's mix() picks base_color
                            # unless a voxel VAO overrides with per-vertex biome color.
                            try: glVertexAttrib4f(3, 0.0, 0.0, 0.0, 0.0)
                            except Exception: pass
                            active_shader.set_uniform_f("time", self._elapsed_time)
                            active_shader.set_uniform_v3("sunDir", *sun_direction)
                            active_shader.set_uniform_v3("sunColor", *sun_color)
                            active_shader.set_uniform_v3("ambientColor", *amb_color)
                            col = list(obj.color); col[3] = getattr(obj, 'alpha', 1.0)
                            active_shader.set_uniform_v4("base_color", *col)
                            
                            if "pbr_material" in s_name.lower() or s_name == "PBR Material":
                                active_shader.set_uniform_v4("u_base_color", *col)
                                active_shader.set_uniform_f("u_metallic", getattr(obj, 'pbr_metallic', 0.0))
                                active_shader.set_uniform_f("u_roughness", getattr(obj, 'pbr_roughness', 0.5))
                                active_shader.set_uniform_v2("u_tiling", *(getattr(obj, 'pbr_tiling', [1.0, 1.0])))
                                active_shader.set_uniform_v3("cam_pos", *self._cam3d.pos)

                            # Upload all custom shader parameters from obj.shader_params
                            params = getattr(obj, 'shader_params', {})
                            for k, v in params.items():
                                if isinstance(v, (int, float)):
                                    active_shader.set_uniform_f(k, float(v))
                                elif isinstance(v, (list, tuple)) and len(v) == 4:
                                    active_shader.set_uniform_v4(k, *v)

                            if obj.obj_type in ('cube', 'plane'): _draw_wireframe_cube()
                            elif obj.obj_type == 'sphere': _draw_wireframe_sphere()
                            elif obj.obj_type == 'mesh' and obj.mesh_path:
                                self._draw_custom_mesh(obj, shader_active=True)
                            elif obj.obj_type == 'voxel_world':
                                self._draw_voxel_world(obj, shader_active=True, 
                                                       sun_dir=sun_direction, 
                                                       sun_color=sun_color, 
                                                       amb_color=amb_color)
                            active_shader.stop()
                        else:
                            if obj.obj_type in ('cube', 'plane'): _draw_wireframe_cube()
                            elif obj.obj_type == 'sphere': _draw_wireframe_sphere()
                            elif obj.obj_type == 'mesh' and obj.mesh_path:
                                self._draw_custom_mesh(obj, shader_active=False)
                            elif obj.obj_type == 'voxel_world':
                                self._draw_voxel_world(obj, shader_active=False,
                                                       sun_dir=sun_direction, 
                                                       sun_color=sun_color, 
                                                       amb_color=amb_color)

                    # Highlight
                    if obj.selected and obj.visible:
                        glDisable(GL_LIGHTING); glPolygonMode(GL_FRONT_AND_BACK, GL_LINE); glLineWidth(2.5)
                        glColor4f(1.0, 0.8, 0.2, 1.0)
                        if obj.obj_type in ('cube', 'plane'): _draw_wireframe_cube(color=(1, 0.8, 0.2, 1), fill_color=(0,0,0,0))
                        elif obj.obj_type == 'sphere': _draw_wireframe_sphere(color=(1, 0.8, 0.2, 1))
                        elif obj.obj_type == 'mesh': self._draw_custom_mesh(obj, shader_active=False)
                        glPolygonMode(GL_FRONT_AND_BACK, GL_FILL); glLineWidth(1.0); glEnable(GL_LIGHTING)

                    # Icons
                    if obj.obj_type == 'camera':
                        _draw_camera_icon(color=(0.3, 0.7, 1.0, 1.0) if obj.selected else (0.1, 0.4, 0.6, 0.8))
                    elif obj.obj_type in ('light_directional', 'light_point'):
                        _draw_light_icon(color=(1, 1, 0.4, 1.0) if obj.selected else (0.6, 0.6, 0.0, 0.8))

                # Special Highlight for Procedural types if selected (rendered in their own space/coordinate system locally)
                if is_proc and obj.selected and obj.obj_type in ('ocean', 'landscape'):
                     # (Already implemented earlier, keeping it localized to the object transform)
                     pass 

                # RENDER CHILDREN
                children = [o for o in self.scene_objects if getattr(o, 'parent_id', None) == obj.id]
                if children:
                    if getattr(obj, 'obj_type', None) == 'spawner':
                        # Static-batch children that share a mesh into one draw call.
                        batches, unbatched = self._spawner_batches.get_batches(obj, children)
                        if batches:
                            active_shader = get_shader(getattr(obj, 'shader_name', 'Standard'))
                            if active_shader:
                                active_shader.use()
                                try: glVertexAttrib4f(3, 0.0, 0.0, 0.0, 0.0)
                                except Exception: pass
                                active_shader.set_uniform_f("time", self._elapsed_time)
                                active_shader.set_uniform_v3("sunDir", *sun_direction)
                                active_shader.set_uniform_v3("sunColor", *sun_color)
                                active_shader.set_uniform_v3("ambientColor", *amb_color)
                                active_shader.set_uniform_v4("base_color", 1.0, 1.0, 1.0, 1.0)
                                for b in batches:
                                    b.draw()
                                active_shader.stop()
                            else:
                                for b in batches:
                                    b.draw()
                        if unbatched:
                            render_hierarchy(unbatched, sun_direction)
                    else:
                        render_hierarchy(children, sun_direction)
                
                glPopMatrix()

        render_hierarchy(top_level, sun_dir)

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

        # Match the scale used in _draw_gizmo so picking lines up with what's drawn.
        from py_editor.ui.scene.render_manager import _gizmo_screen_scale
        gs = _gizmo_screen_scale(pos, self._cam3d) * 2.0  # axes are 2 units long pre-scale

        axes = {'x': [pos[0]+gs, pos[1], pos[2]],
                'y': [pos[0], pos[1]+gs, pos[2]],
                'z': [pos[0], pos[1], pos[2]+gs]}
        best_axis, min_dist = None, 20.0 # Tolerance in pixels
        
        for name, end_world in axes.items():
            s_end = self._cam3d.world_to_screen(end_world, w, h)
            if not s_end: continue
            d = dist_to_segment(QPointF(mx, my), s_pos, QPointF(*s_end))
            if d < min_dist:
                min_dist, best_axis = d, name
                
        return best_axis

    def _pick_object(self, mx, my) -> Optional[SceneObject]:
        """Perform accurate raycasting for objects and procedural primitives."""
        from py_editor.ui.scene.render_manager import _sub, _dot, _add, _scale_vec
        origin, direction = self._cam3d.screen_to_ray(mx, my, self.width(), self.height())
        best_t, found = float('inf'), None
        
        for obj in self.scene_objects:
            # 1. SPECIAL CASE: Procedural Planes (Ocean, Landscape Flat)
            if obj.obj_type in ('ocean', 'landscape'):
                # Handle as infinite horizontal plane for selection ease
                plane_normal = (0.0, 1.0, 0.0)
                denom = _dot(direction, plane_normal)
                if abs(denom) > 1e-6:
                    t = _dot(_sub(obj.position, origin), plane_normal) / denom
                    if 0 < t < best_t:
                        # Only pick if looking "down" or "at" the plane
                        best_t, found = t, obj
                continue

            # 2. DEFAULT CASE: Sphere proxy
            oc = [_sub(origin, obj.position)[i] for i in range(3)]
            b = _dot(oc, direction)
            # Use radius relative to scale with a minimum size of 0.5 for icons
            radius = max(0.5, max(obj.scale) if hasattr(obj, 'scale') else 1.0)
            c = _dot(oc, oc) - radius**2
            h = b*b - c
            if h >= 0:
                t = -b - math.sqrt(h)
                if 0 < t < best_t:
                    best_t, found = t, obj
        return found

    def dragEnterEvent(self, event):
        text = event.mimeData().text()
        if text.startswith("prim:") or text.startswith("logic:") or any(text.lower().endswith(ext) for ext in ('.obj', '.fbx', '.mesh', '.prefab', '.spawner')):
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
            self.objects_changed.emit()
            event.acceptProposedAction()
        elif any(text.lower().endswith(ext) for ext in ('.obj', '.fbx', '.mesh', '.prefab', '.spawner')):
            # Strip type prefixes (e.g., 'spawner:', 'material:') if present
            if ":" in text and not (len(text) > 1 and text[1] == ":" and text[2] == "\\"):
                # If there's a colon but it's not a Windows drive path (e.g. C:\)
                if text.count(":") > 1: # 'spawner:C:\path' case
                    text = text.split(":", 1)[1]
                elif not (text[1] == ":" or text[1] == "/"): # 'material:path' case
                    text = text.split(":", 1)[1]

            path = Path(text)
            if path.suffix.lower() in ('.obj', '.fbx'):
                # Auto-convert FBX / OBJ → .mesh on drop. Show import dialog so
                # the user can pick up-axis / scale / rotation before baking.
                mesh_path = path.with_suffix('.mesh')
                try:
                    from py_editor.ui.panels.explorer_panel import MeshImportDialog
                    scale, rot = 1.0, (0.0, 0.0, 0.0)
                    dlg = MeshImportDialog(self)
                    dlg.setWindowTitle(f"Import {path.name}")
                    if dlg.exec():
                        scale, rot = dlg.get_values()
                    self.add_screen_log(f"Converting {path.name} → .mesh …", Qt.GlobalColor.yellow)
                    if path.suffix.lower() == '.fbx':
                        MeshConverter.fbx_to_mesh(str(path), str(mesh_path), scale=scale, rotation=rot)
                    else:
                        MeshConverter.obj_to_mesh(str(path), str(mesh_path), scale=scale, rotation=rot)
                    self.add_screen_log(f"Converted → {mesh_path.name}", Qt.GlobalColor.green)
                    self.object_dropped.emit("mesh", wx, wz, int(mx), int(my), str(mesh_path))
                except Exception as e:
                    self.add_screen_log(f"Convert failed: {e}", Qt.GlobalColor.red)
                    print(f"[VIEWPORT] Auto-convert failed for {path.name}: {e}")
            elif path.suffix.lower() == '.mesh':
                self.object_dropped.emit("mesh", wx, wz, int(mx), int(my), str(path))
            elif path.suffix.lower() == '.prefab':
                self.object_dropped.emit("prefab", wx, wz, int(mx), int(my), str(path))
            elif path.suffix.lower() == '.spawner':
                self.object_dropped.emit("spawner", wx, wz, int(mx), int(my), str(path))
            self.objects_changed.emit()
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
            self.objects_changed.emit()
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
        
        # Invalidate cache if the .mesh file on disk has been rewritten
        # (e.g. user re-ran FBX→.mesh conversion with a new rotation).
        try:
            import os as _os
            mt = _os.path.getmtime(path)
        except OSError:
            mt = None
        cached = self.mesh_cache.get(path)
        if cached is not None and mt is not None and cached.get('mtime') != mt:
            try:
                from OpenGL.GL import glDeleteVertexArrays, glDeleteBuffers
                if cached.get('vao'): glDeleteVertexArrays(1, [cached['vao']])
                if cached.get('vbo'): glDeleteBuffers(1, [cached['vbo']])
                if cached.get('ibo'): glDeleteBuffers(1, [cached['ibo']])
            except Exception:
                pass
            self.mesh_cache.pop(path, None)
            print(f"[VIEWPORT] Mesh changed on disk, reloading: {Path(path).name}")

        if path not in self.mesh_cache:
            self._load_mesh_to_gpu(path)

        mesh = self.mesh_cache.get(path)
        if not mesh: return
        
        # Texture handle
        if "pbr_material" in (obj.shader_name or "").lower() or obj.shader_name == "PBR Material":
            self._bind_pbr_textures(obj, shader_active)
        else:
            tex_id = 0
            if obj.texture_path:
                if obj.texture_path not in self.texture_cache:
                    self._load_texture(obj.texture_path)
                tex_id = self.texture_cache.get(obj.texture_path, 0)

            if tex_id:
                glEnable(GL_TEXTURE_2D)
                glActiveTexture(GL_TEXTURE0)
                glBindTexture(GL_TEXTURE_2D, tex_id)
                if not shader_active: 
                    glColor4f(1, 1, 1, 1)
                else:
                    # Supply uniforms to custom shaders (Standard, Fish, etc)
                    prog = get_shader(obj.shader_name)
                    if prog:
                        prog.set_uniform_i("u_tex0", 0)
                        prog.set_uniform_f("u_has_tex", 1.0)
            elif not shader_active:
                glColor4f(*obj.color)
            else:
                # If shader is active but no texture, ensure shader knows
                prog = get_shader(obj.shader_name)
                if prog:
                    prog.set_uniform_f("u_has_tex", 0.0)

        glBindVertexArray(mesh['vao'])
        glDrawElements(GL_TRIANGLES, mesh['count'], GL_UNSIGNED_INT, None)
        glBindVertexArray(0)
        
        # Cleanup textures
        if "pbr_material" in (obj.shader_name or "").lower() or obj.shader_name == "PBR Material":
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

            # Compute AABB from vertex positions (stride 8, positions at [0:3])
            import numpy as _np
            pos = v_data.reshape(-1, 8)[:, :3]   # Nx3 positions
            aabb_min = pos.min(axis=0).tolist()
            aabb_max = pos.max(axis=0).tolist()

            import os as _os
            try:
                mt = _os.path.getmtime(path)
            except OSError:
                mt = None
            self.mesh_cache[path] = {
                'vao': vao, 'vbo': vbo, 'ibo': ibo, 'count': len(i_data),
                'aabb': (aabb_min, aabb_max), 'mtime': mt,
            }
            print(f"[VIEWPORT] Loaded mesh: {Path(path).name} "
                  f"AABB [{[round(v,2) for v in aabb_min]}] – [{[round(v,2) for v in aabb_max]}]")
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
    def _maybe_respawn_moved_spawners(self):
        """Detect spawners that have been dragged and respawn them once the
        user has stopped moving (position stable for ~0.4s). This keeps the
        shoal aligned with the spawner without thrashing mid-drag."""
        import time as _t
        tracker = getattr(self, '_spawner_pos_track', None)
        if tracker is None:
            tracker = {}
            self._spawner_pos_track = tracker

        now = _t.time()
        live_ids = set()
        for obj in self.scene_objects:
            if getattr(obj, 'obj_type', None) != 'spawner':
                continue
            live_ids.add(obj.id)
            pos = tuple(obj.position)
            entry = tracker.get(obj.id)
            if entry is None:
                tracker[obj.id] = {'pos': pos, 'last_move': 0.0, 'pending': False}
                continue
            if pos != entry['pos']:
                entry['pos'] = pos
                entry['last_move'] = now
                entry['pending'] = True
            elif entry['pending'] and (now - entry['last_move']) > 0.4:
                entry['pending'] = False
                try:
                    from py_editor.ui.scene.object_system import respawn_spawner
                    respawn_spawner(obj, self.scene_objects)
                except Exception as e:
                    print(f"[SPAWNER] Auto-respawn failed: {e}")

        # Drop trackers for spawners that no longer exist.
        for oid in list(tracker.keys()):
            if oid not in live_ids:
                del tracker[oid]

    def _sync_editor_controllers(self):
        """Ensure all objects with AI/Player controllers have them active in the editor."""
        self._maybe_respawn_moved_spawners()
        active_ids = {obj.id for obj in self.scene_objects if getattr(obj, 'controller_type', 'None') != 'None'}
        
        # Cleanup
        for oid in list(self._editor_controllers.keys()):
            if oid not in active_ids:
                del self._editor_controllers[oid]
        
        # Create & Update Flock
        def is_ai(c): return "AI" in c.__class__.__name__
        current_ai_controllers = [c for c in self._editor_controllers.values() if is_ai(c)]
        for obj in self.scene_objects:
            if obj.id not in self._editor_controllers and getattr(obj, 'controller_type', 'None') != 'None':
                ctype = obj.controller_type
                try:
                    from py_editor.core.controller_manager import create_controller
                    ctrl = create_controller(ctype, obj)
                    if ctrl:
                        # Let the controller resolve parent objects when
                        # converting world↔local positions (e.g. fish parented
                        # under a spawner).
                        try: obj._scene_objects_ref = self.scene_objects
                        except Exception: pass
                        self._editor_controllers[obj.id] = ctrl
                        if is_ai(ctrl):
                            current_ai_controllers.append(ctrl)
                except Exception as e:
                    print(f"[SCENE_VIEW] Error creating controller {ctype}: {e}")
        
        # Synchronize flock for all AI
        for ctrl in current_ai_controllers:
            ctrl.flock = current_ai_controllers

    def _draw_voxel_world(self, obj, shader_active=False, sun_dir=None, sun_color=None, amb_color=None):
        """Chunk-streamed voxel world with full-planet camera-distance LOD.

        Seam fixes:
        · total_samples = per_res + 2*margin + 1  makes linspace step == vox_step
          exactly, so every chunk samples density at globally-aligned world positions.
          Adjacent same-LOD chunks share boundary sample positions → identical vertices
          at edges → no cracks.
        · Half-open clip [cmin, cmax): every triangle belongs to exactly one chunk,
          preventing both double-rendering (z-fighting) and missed triangles.
        · LOD uses camera-AABB distance (not chunk-centre distance).  Face-adjacent
          chunks can differ in AABB-distance by at most one chunk-width, which is less
          than every threshold gap, so no two neighbours ever jump more than one LOD
          tier — no explicit smoothing pass needed.

        Full-planet rendering:
        · All chunks across the entire planet are considered every frame (vectorised).
        · 5 LOD tiers keep generation load proportional to distance regardless of size.
        · Thread throttle (≤6 concurrent) prevents memory blowout on Moon/Planet.
        """
        v_type       = str(getattr(obj, 'voxel_type', 'Round')).strip()
        v_radius     = float(getattr(obj, 'voxel_radius', 5.0))
        seed         = int(getattr(obj, 'voxel_seed', 123))
        smooth       = int(getattr(obj, 'voxel_smooth_iterations', 2))
        block_size   = float(getattr(obj, 'voxel_block_size', 1.0))
        render_style = str(getattr(obj, 'voxel_render_style', 'Smooth'))
        layers       = getattr(obj, 'voxel_layers', [])
        features     = getattr(obj, 'voxel_features', [])
        obj_pos      = np.array(obj.position, dtype=np.float32)

        # Enforce minimum voxel size per style
        if render_style in ('Minecraft', 'Blocky'):
            smooth     = 0
            block_size = max(block_size, 1.0)   # blocky: ≥1 unit/voxel
        else:
            block_size = max(block_size, 0.5)   # smooth: ≥0.5 units/voxel

        res_limit = int(getattr(obj, 'voxel_max_single_chunk_res',
                                getattr(self, 'voxel_max_single_chunk_res', 128)))

        # Camera position needed early for infinite-flat streaming bounds.
        cam_pos = np.array(self._cam3d.pos, dtype=np.float32)

        # World bounds
        dist_to_center = np.linalg.norm(obj_pos - cam_pos)
        if v_type.lower() == "round":
            # 1. ALWAYS draw a smooth proxy base if outside or near the surface.
            # This prevents the planet from "vanishing" or showing shards at distance.
            if dist_to_center > v_radius * 0.9:
                try:
                    glEnable(GL_DEPTH_TEST); glEnable(GL_CULL_FACE); glCullFace(GL_BACK)
                    glPushMatrix()
                    glTranslatef(float(obj_pos[0]), float(obj_pos[1]), float(obj_pos[2]))
                    # Slightly smaller (99.2%) so the voxel terrain draws OVER it.
                    s = v_radius * 0.992
                    glScalef(s, s, s)
                    
                    # Basic directional lighting simulation for the proxy
                    atmo = next((o for o in self.scene_objects if o.obj_type == 'atmosphere'), None)
                    if atmo:
                        t = getattr(atmo, 'time_of_day', 0.5)
                        # cos-based noon brightness (0.5 is noon, 0.0 is midnight)
                        lum = max(0.12, float(np.cos((t - 0.5) * 3.14159)))
                        c = atmo.sun_color
                        glColor4f(c[0]*lum, c[1]*lum, c[2]*lum, 1.0)
                    else:
                        glColor4f(0.5, 0.5, 0.5, 1.0)

                    q = gluNewQuadric()
                    gluSphere(q, 1.0, 128, 128)
                    gluDeleteQuadric(q)
                    glPopMatrix()
                except: pass

            # 2. Skip voxels entirely if VERY far away (save CPU/GPU)
            if dist_to_center > v_radius * 4.0:
                return

            # Optimization: Window the chunk search grid around the camera.
            # For low-detail zoom (distant view), we expand the window significantly
            # so continents are visible all the way to the horizon silhouette.
            window = 120.0 * 64.0
            if dist_to_center > v_radius * 1.1:
                # Expand search to cover the whole world silhouette for cheap low-res tiers
                window = v_radius * 2.2
                
            world_min     = np.maximum(obj_pos - v_radius * 1.1, cam_pos - window)
            world_max     = np.minimum(obj_pos + v_radius * 1.1, cam_pos + window)
            world_span    = v_radius * 2.2 # For chunk size calc
            extent        = v_radius * 1.2 # Bounding sphere for voxel selection
            
            target_chunks_across = 24.0
            chunk_vox_size = float(max(block_size * 8.0,
                                       world_span / target_chunks_across))
        else:
            # Flat mode: multi-LOD camera-centered ring so the world extends to
            # the horizon on zoom-out without looking like a square box.
            extent   = None
            infinite = bool(getattr(obj, 'voxel_infinite_flat', True))
            chunk_vox_size = float(max(block_size * 32.0, 64.0))

            if infinite:
                # Grow the ring with camera altitude — far from ground, show more.
                alt = abs(float(cam_pos[1] - obj_pos[1]))
                horiz_extent = float(max(300.0, 250.0 + alt * 3.0))
                horiz_extent = min(horiz_extent, 4000.0)  # hard ceiling
                vert_extent  = 96.0

                world_min = cam_pos - horiz_extent
                world_max = cam_pos + horiz_extent
                world_min[1] = obj_pos[1] - vert_extent
                world_max[1] = obj_pos[1] + vert_extent
                world_span = 2.0 * horiz_extent
                # Used later to clip the AABB-grid to a circle so the world's
                # outer silhouette is round, not cubic.
                _flat_ring_radius = horiz_extent
            else:
                world_span = 100.0
                world_min  = obj_pos + np.array([-50, -20, -50], dtype=np.float32)
                world_max  = obj_pos + np.array([ 50,  20,  50], dtype=np.float32)
                _flat_ring_radius = None

        biomes       = getattr(obj, 'voxel_biomes', []) or []
        layers_hash = hash(str(layers))
        features_hash = hash(str(features))
        biomes_hash = hash(str(biomes))
        gp_hash = hash((
            round(float(getattr(obj, 'voxel_world_height',       1.0)),  4),
            round(float(getattr(obj, 'voxel_cave_tunnel_scale', 28.0)),  4),
            round(float(getattr(obj, 'voxel_cave_tunnel_radius', 0.10)), 4),
            round(float(getattr(obj, 'voxel_cave_cavern_scale', 60.0)),  4),
            round(float(getattr(obj, 'voxel_cave_cavern_radius', 0.05)), 4),
            round(float(getattr(obj, 'voxel_cave_waterline',     0.0)),  4),
            round(float(getattr(obj, 'voxel_cave_max_depth',   512.0)),  4),
        ))
        cache_key = (f"voxel_{obj.id}_{seed}_{v_type}_{v_radius}"
                     f"_{block_size}_{smooth}_{render_style}"
                     f"_{layers_hash}_{features_hash}_{biomes_hash}_{gp_hash}")

        world_grid_min = np.floor(world_min / chunk_vox_size).astype(int)
        world_grid_max = np.ceil(world_max  / chunk_vox_size).astype(int)

        if cache_key not in self.mesh_cache:
            self.mesh_cache[cache_key] = []

        # ── Vectorised chunk selection (all planet chunks in one numpy pass) ──
        ixs = np.arange(int(world_grid_min[0]), int(world_grid_max[0]))
        iys = np.arange(int(world_grid_min[1]), int(world_grid_max[1]))
        izs = np.arange(int(world_grid_min[2]), int(world_grid_max[2]))

        # Sanity cap: prevent crash/hang if meshgrid indices explode (max 10,000 chunks)
        if len(ixs) * len(iys) * len(izs) > 10000:
            return

        IX, IY, IZ = np.meshgrid(ixs, iys, izs, indexing='ij')
        IX = IX.ravel(); IY = IY.ravel(); IZ = IZ.ravel()

        cmin_all = np.stack([IX, IY, IZ], axis=1).astype(np.float32) * chunk_vox_size
        cmax_all = cmin_all + chunk_vox_size

        # Sphere-AABB overlap: closest point on each chunk box to the planet centre.
        # This is correct for any planet-to-chunk size ratio (small planet, large chunk).
        if v_type.lower() == "round":
            closest_planet = np.clip(obj_pos, cmin_all, cmax_all)           # (N,3)
            dist_planet    = np.linalg.norm(closest_planet - obj_pos, axis=1)  # (N,)
            in_planet      = dist_planet <= extent
        else:
            # Circular clip for flat mode: drops corner chunks so the world's
            # silhouette is round instead of looking like a 500m cube.
            _ring_r = locals().get('_flat_ring_radius')
            if _ring_r is not None:
                chunk_centers_xz = (cmin_all[:, [0, 2]] + cmax_all[:, [0, 2]]) * 0.5
                cam_xz = cam_pos[[0, 2]]
                dxz = np.linalg.norm(chunk_centers_xz - cam_xz, axis=1)
                in_planet = dxz <= _ring_r
            else:
                in_planet = np.ones(len(IX), dtype=bool)

        # Camera-AABB distance for LOD tier: nearest point on chunk AABB to camera.
        closest_cam = np.clip(cam_pos, cmin_all, cmax_all)
        dist_cam    = np.linalg.norm(closest_cam - cam_pos, axis=1)
        d_ch        = dist_cam / chunk_vox_size  # distance in chunk-units

        # Final selection mask:
        # 1. Sphere overlap (in_planet)
        # 2. Surface-shell optimization (for massive worlds): only keep chunks
        #    near the surface to avoid processing millions of core chunks.
        if v_type.lower() == "round" and v_radius > 5000:
            # Shell = surface ± 2.5 chunks thick (wider buffer for steep mountains/valleys)
            shell_mask = (dist_planet > (v_radius - chunk_vox_size * 2.5)) & \
                         (dist_planet < (v_radius + chunk_vox_size * 2.5))
            in_planet = in_planet & shell_mask

        # LOD tiers. Flat mode forces single LOD 0.
        lod_arr = np.full(len(IX), -1, np.int8)
        if v_type.lower() == "round":
            # Scale thresholds for massive planets (radius up to 150,000+)
            radius_scale = max(1.0, (v_radius / 1000.0) ** 0.5)
            # Expanded thresholds for smoother transitions at extreme scales
            thresh = [2.0, 4.0, 8.0, 15.0, 25.0, 40.0, 60.0, 90.0, 130.0, 180.0, 250.0, 350.0]
            thresh = [t * radius_scale for t in thresh]
            
            # Tier 0 (Highest)
            lod_arr[in_planet & (d_ch < thresh[0])] = 0
            # Intermediate Tiers
            for i in range(1, len(thresh)):
                lod_arr[in_planet & (d_ch >= thresh[i-1]) & (d_ch < thresh[i])] = i
            # Lowest Tier
            lod_arr[in_planet & (d_ch >= thresh[-1])] = len(thresh)
        else:
            # Flat mode LOD: near chunks full-res, mid half-res, far quarter-res.
            # Uses horizontal chunk-distance so elevation above the ground doesn't
            # promote everything to LOD 0 (which is why zoomed-out views stalled).
            lod_arr[in_planet & (d_ch < 3.0)]                      = 0
            lod_arr[in_planet & (d_ch >= 3.0) & (d_ch < 7.0)]      = 1
            lod_arr[in_planet & (d_ch >= 7.0) & (d_ch < 14.0)]     = 2
            lod_arr[in_planet & (d_ch >= 14.0)]                    = 3

        vis = lod_arr >= 0
        if not np.any(vis):
            glEnable(GL_CULL_FACE)
            return

        # ── Priority Scheduling ──
        # Sort chunks by distance to camera so things in front of you load first.
        vis_idx = np.where(vis)[0]
        sorted_idx = vis_idx[np.argsort(dist_cam[vis_idx])]
        
        chunk_lods = []
        for i in sorted_idx:
            chunk_lods.append(((int(IX[i]), int(IY[i]), int(IZ[i])), int(lod_arr[i])))

        # Snapshot layers NOW so threads always use the state at scheduling time,
        # not a mutated version that may arrive after the thread starts.
        layers_snap = list(layers)
        features_snap = list(features)
        biomes_snap = list(biomes)
        # Per-object generation tuning (world height, cave params). Snapshotted
        # so threads see stable values across the generation lifetime.
        gen_params = {
            'world_height':  float(getattr(obj, 'voxel_world_height', 1.0)),
            'tunnel_scale':  float(getattr(obj, 'voxel_cave_tunnel_scale', 28.0)),
            'tunnel_radius': float(getattr(obj, 'voxel_cave_tunnel_radius', 0.10)),
            'cavern_scale':  float(getattr(obj, 'voxel_cave_cavern_scale', 60.0)),
            'cavern_radius': float(getattr(obj, 'voxel_cave_cavern_radius', 0.05)),
            'waterline':     float(getattr(obj, 'voxel_cave_waterline', 0.0)),
            'max_depth':     float(getattr(obj, 'voxel_cave_max_depth', 512.0)),
        }

        # ── Schedule generation & collect active chunk keys ──
        chunk_keys = []
        with self._voxel_gen_lock:
            active_count = len(self._voxel_generation_in_progress)

        # Per-frame new-thread budget. Without this, 10 generator threads can
        # be spawned in a single frame; the GIL + numpy allocations stall the
        # main thread hard (the 113→6 fps drop during flat-world loading).
        # 2/frame drains a 100-chunk backlog in ~0.8s without starving render.
        new_threads_this_frame = 0
        NEW_THREAD_BUDGET = 2
        ACTIVE_THREAD_CAP = 4

        for (ix, iy, iz), lod_level in chunk_lods:
            lod_factor = 1 << lod_level               # 1, 2, 4, 8, or 16
            # base_per_res: scale to match chunk size, but hard-cap at 40 so that
            # large-chunk planets (Moon, Planet) never generate >47^3 ≈ 104K samples
            # per thread.  Dwarf Planet (per_res=37) is unchanged; Asteroid uses 8.
            base_per_res = max(8, min(40, min(res_limit, int(chunk_vox_size / block_size))))
            # Ensure per_res doesn't drop to 0 for very high LOD tiers
            per_res      = max(4, base_per_res // lod_factor)
            vox_step     = chunk_vox_size / per_res

            chunk_cache_key = f"{cache_key}_c_{ix}_{iy}_{iz}_{lod_level}"

            # Schedule if: no VAO yet (absent or None/failed) AND not already running.
            # Using isinstance(…, dict) lets empty/failed chunks retry on next frame
            # so a settings change (layers added, noise params tweaked) always re-runs.
            existing = self.mesh_cache.get(chunk_cache_key)
            if not isinstance(existing, dict):
                # Intensity scaling for caves
                # Use a higher base intensity for Flat worlds to overcome terrain noise
                carve_depth = 10.0 if v_type.lower() == "round" else 18.0
                
                # Rate-limit both concurrent threads and per-frame new spawns.
                if active_count < ACTIVE_THREAD_CAP and new_threads_this_frame < NEW_THREAD_BUDGET:
                    with self._voxel_gen_lock:
                        if chunk_cache_key not in self._voxel_generation_in_progress:
                            self._voxel_generation_in_progress.add(chunk_cache_key)
                            self.mesh_cache[chunk_cache_key] = None   # in-progress marker
                            active_count += 1
                            new_threads_this_frame += 1

                            cmin_loc = np.array([ix, iy, iz], dtype=np.float32) * chunk_vox_size
                            cmax_loc = cmin_loc + chunk_vox_size

                            def _gen_chunk(cmin, cmax, per_res, cck, vs, lsnap, fsnap,
                                           gp=gen_params, bsnap=biomes_snap, opy=float(obj_pos[1])):
                                produced = False
                                try:
                                    # Each smoothing iteration pulls from one more neighbor
                                    # cell per axis. Margin must cover ALL iterations plus a
                                    # cell for surface-nets gradient sampling, otherwise the
                                    # outer cells fall back to edge-padding and their density
                                    # diverges from what the neighboring chunk sees → seams.
                                    margin = max(4, int(smooth) + 2)
                                    p_min  = cmin - margin * vs
                                    p_max  = cmax + margin * vs
                                    # per_res + 2*margin + 1 samples → linspace step == vs
                                    # → globally-aligned density grid → seamless edges
                                    total_samples = per_res + 2 * margin + 1

                                    grid = VoxelEngine.generate_density_grid(
                                        resolution=total_samples, seed=seed, mode=v_type,
                                        radius=v_radius, layers=lsnap, features=fsnap,
                                        center=obj_pos, min_p=p_min, max_p=p_max,
                                        gen_params=gp)
                                    if smooth > 0:
                                        grid = VoxelEngine.smooth_grid(grid, iterations=smooth)
                                    if render_style in ('Minecraft', 'Blocky'):
                                        verts_c, idx_c, norms_c = VoxelEngine.blocky_mesh(grid)
                                    else:
                                        verts_c, idx_c, norms_c = VoxelEngine.surface_nets(
                                            grid, pad=False)

                                    if len(verts_c) > 0 and len(idx_c) > 0:
                                        p_size   = p_max - p_min
                                        p_offset = (p_min + p_max) * 0.5 - obj_pos
                                        verts_w  = verts_c * p_size + p_offset

                                        # Implement LOD skirts via overlapping clip boundaries
                                        # Extending the clip bounds by `vs` allows mismatched LOD 
                                        # edges to intersect slightly rather than leaving a gap.
                                        clip_min = cmin - obj_pos - vs
                                        clip_max = cmax - obj_pos + vs
                                        tri_arr   = idx_c.reshape(-1, 3)
                                        centroids = verts_w[tri_arr].mean(axis=1)
                                        keep      = (np.all(centroids >= clip_min, axis=1) &
                                                     np.all(centroids  < clip_max, axis=1))
                                        idx_out   = tri_arr[keep].flatten()

                                        if len(idx_out) > 0:
                                            verts_w_c = np.ascontiguousarray(verts_w, dtype=np.float32)
                                            norms_c_c = np.ascontiguousarray(norms_c, dtype=np.float32)
                                            idx_c_out = np.array(idx_out, dtype=np.uint32)
                                            colors_c  = np.ascontiguousarray(
                                                _compute_biome_colors(verts_w_c, opy, norms_c_c, bsnap),
                                                dtype=np.float32)
                                            # Deterministic seed per (object_seed, chunk_key) so
                                            # regenerations reproduce the exact same scatter.
                                            chunk_spawns = _compute_biome_spawns(
                                                verts_w_c, idx_c_out, norms_c_c,
                                                obj_pos, bsnap,
                                                seed_hash=hash((seed, cck)))
                                            with self._voxel_gen_lock:
                                                self._pending_voxel_chunks[cck] = (
                                                    verts_w_c,
                                                    idx_c_out,
                                                    norms_c_c,
                                                    colors_c,
                                                    chunk_spawns,
                                                )
                                                produced = True
                                except Exception as e:
                                    print(f"[VOXEL] Chunk {cck}: {e}")
                                finally:
                                    # Chunks entirely inside/outside the density surface produce
                                    # no geometry.  Emit an empty-dict sentinel so the scheduler
                                    # treats them as "done" and stops endlessly rescheduling —
                                    # without this, empty chunks starve real chunks of threads.
                                    if not produced:
                                        with self._voxel_gen_lock:
                                            self._pending_voxel_chunks[cck] = {}
                                    with self._voxel_gen_lock:
                                        self._voxel_generation_in_progress.discard(cck)

                            threading.Thread(
                                target=_gen_chunk,
                                args=(cmin_loc, cmax_loc, per_res,
                                      chunk_cache_key, vox_step, layers_snap, features_snap),
                                daemon=True).start()

            chunk_keys.append(chunk_cache_key)

        # ── High-Confidence LOD Switching ──
        # To prevent "holes" or "flickering" while chunks load in the background,
        # we only commit to the new chunk set if a high percentage of them are 
        # already ready. If the new set is too sparse, we keep rendering the 
        # previous successful set.
        
        # Count ready chunks (dict sentinels or full VAOs)
        num_required = len(chunk_keys)
        ready_count = 0
        if num_required > 0:
            for ck in chunk_keys:
                d = self.mesh_cache.get(ck)
                # We count valid dicts (either populated with a VAO OR an empty-box sentinel)
                if isinstance(d, dict):
                    ready_count += 1
        
        # Switch threshold (e.g., 90%). 
        # If the move was small, 90% of a 100-chunk set is likely already cached.
        # If the move was large (teleporting across the world), we fall back 
        # to the old set until the new landscape "fills in".
        confidence = (ready_count / num_required) if num_required > 0 else 1.0
        
        if confidence < 0.90 and hasattr(obj, '_last_chunk_keys'):
            chunk_keys = obj._last_chunk_keys
        else:
            obj._last_chunk_keys = chunk_keys

        self.mesh_cache[cache_key] = chunk_keys

        # ── Rendering Cleanup ──
        try:
            glEnable(GL_DEPTH_TEST)
            glEnable(GL_CULL_FACE)
            glCullFace(GL_BACK)
        except Exception:
            pass

        # ── Render all chunks with a ready VAO ──
        glDisable(GL_CULL_FACE)
        for ck in chunk_keys:
            d = self.mesh_cache.get(ck)
            if not isinstance(d, dict) or 'vao' not in d:
                continue  # skips in-progress (None) and known-empty ({}) chunks
            glBindVertexArray(d['vao'])
            glDrawElements(GL_TRIANGLES, d['count'], GL_UNSIGNED_INT, None)
            if render_style in ('Minecraft', 'Blocky'):
                try:
                    glPolygonMode(GL_FRONT_AND_BACK, GL_LINE)
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

        # ── Biome spawner draws ──
        # Each chunk's spawns are stored on its VAO entry. We render them as
        # simple fixed-function primitives (cube/sphere/cone/…) so they follow
        # the existing shader without per-object state churn. Prefabs are
        # rendered as bounding cubes — loading the actual prefab mesh on the
        # render thread would stall, and the prefab streaming system isn't
        # plumbed through voxel gen yet.
        try:
            from py_editor.ui.scene.render_manager import (
                _draw_wireframe_cube, _draw_wireframe_sphere,
                _draw_wireframe_plane, _draw_wireframe_cylinder, _draw_wireframe_cone)
            from py_editor.ui.shader_manager import get_shader
            glEnable(GL_DEPTH_TEST)
            # Reset color state so spawns don't inherit "dirty" color from terrain biomes
            glColor4f(1.0, 1.0, 1.0, 1.0)
            
            # Spawn meshes have inconsistent winding — disable culling so all sides show.
            glDisable(GL_CULL_FACE)
            
            # Distance cull — skip spawn batches for chunks beyond this radius.
            spawn_max_d = float(getattr(obj, 'voxel_spawn_max_distance', 120.0))
            spawn_max_d2 = spawn_max_d * spawn_max_d
            
            # Fix: Source camera position from self._cam3d.pos (self.camera_pos was incorrect)
            cam_p = np.array(self._cam3d.pos, dtype=np.float32)
            obj_p = np.array(obj.position, dtype=np.float32)

            last_sn = None

            for ck in chunk_keys:
                d = self.mesh_cache.get(ck)
                if not isinstance(d, dict): continue
                sps = d.get('spawns') or []
                if not sps: continue

                # Chunk-level distance cull
                first = sps[0]['pos']
                dx = (first[0] + obj_p[0]) - cam_p[0]
                dy = (first[1] + obj_p[1]) - cam_p[1]
                       # Render instance batches (Prefabs/Meshes)
                batches, leftovers = self._chunk_spawn_batches.get_batches(ck, sps)
                for b in batches:
                    sn = b.shader_name or 'Standard'
                    mat_path = getattr(b, 'material_path', '')
                    
                    s = get_shader(sn)
                    if not s: continue
                    
                    if sn != last_sn:
                        s.use()
                        # Pass common Lighting/Environment uniforms
                        s.set_uniform_v3("sunDir",        *(sun_dir or (0.5, 0.7, 0.2)))
                        s.set_uniform_v3("sunColor",      *(sun_color or (1, 1, 1)))
                        s.set_uniform_v3("ambientColor",  *(amb_color or (0.1, 0.1, 0.1)))
                        s.set_uniform_v3("cam_pos",       *cam_p)
                        
                        t_val = getattr(self, '_elapsed_time', 0.0)
                        s.set_uniform_f("time",   t_val)
                        s.set_uniform_f("u_time", t_val)
                        last_sn = sn
                    else:
                        # Ensure we are using the right program even if sn hasn't changed
                        # (in case some other render call changed it)
                        s.use()

                    # --- Apply material/batch-specific overrides (Must happen per batch) ---
                    # Reset texture to 0/None initially
                    s.set_uniform_f("u_has_tex", 0.0)
                    
                    if mat_path:
                        try:
                            import json
                            from py_editor.core import paths as _ap
                            abs_mat = _ap.resolve(mat_path)
                            with open(abs_mat, 'r') as f:
                                m_data = json.load(f)
                            # PBR Texture Auto-Link
                            tex = m_data.get('albedo') or m_data.get('texture_path')
                            if tex:
                                from py_editor.ui.shader_manager import get_texture
                                tid = get_texture(tex)
                                if tid:
                                    from OpenGL.GL import glActiveTexture, glBindTexture, GL_TEXTURE0, GL_TEXTURE_2D
                                    glActiveTexture(GL_TEXTURE0)
                                    glBindTexture(GL_TEXTURE_2D, tid)
                                    s.set_uniform_i("u_tex0", 0)
                                    s.set_uniform_f("u_has_tex", 1.0)
                            # Material Properties
                            for k, v in m_data.items():
                                if k == 'base_color':
                                    if len(v) == 3: s.set_uniform_v4(k, v[0], v[1], v[2], 1.0)
                                    else: s.set_uniform_v4(k, *v)
                                elif isinstance(v, (int, float)): s.set_uniform_f(k, float(v))
                                elif isinstance(v, list) and len(v) in (3, 4):
                                    if len(v) == 3: s.set_uniform_v3(k, *v)
                                    else: s.set_uniform_v4(k, *v)
                        except: pass
                    else:
                        # Reset to default if no material
                        if sn == 'Standard':
                            s.set_uniform_v4("base_color", 1.0, 1.0, 1.0, 1.0)
                        elif sn == 'grass.shader':
                            # Restore shader default green
                            s.set_uniform_v4("base_color", 0.15, 0.45, 0.1, 1.0)

                    # Spawner-specific param overrides
                    p = getattr(b, 'shader_params', {})
                    for k, v in p.items():
                        if isinstance(v, (int, float)): s.set_uniform_f(k, float(v))
                        elif isinstance(v, list) and len(v) in (3, 4):
                            if len(v) == 3: s.set_uniform_v3(k, *v)
                            else: s.set_uniform_v4(k, *v)

                    b.draw()

                # Fallback primitives use the global spawn shader
                global_sn = getattr(obj, 'shader_name', 'Standard')
                for sp in leftovers:
                    # Sync shader for fallback primitives
                    sn = sp.get('shader_name', global_sn)
                    mat_path = sp.get('material_path', '')
                    if sn != last_sn:
                        s = get_shader(sn)
                        if s:
                            s.use()
                            s.set_uniform_v3("sunDir",        *(sun_dir or (0.5, 0.7, 0.2)))
                            s.set_uniform_v3("sunColor",      *(sun_color or (1, 1, 1)))
                            s.set_uniform_v3("ambientColor",  *(amb_color or (0.1, 0.1, 0.1)))
                            s.set_uniform_v3("cam_pos",       *cam_p)
                            t_val = getattr(self, '_elapsed_time', 0.0)
                            s.set_uniform_f("time", t_val); s.set_uniform_f("u_time", t_val)
                            
                            if mat_path:
                                try:
                                    import json
                                    with open(mat_path, 'r') as f: m_data = json.load(f)
                                    tex = m_data.get('albedo') or m_data.get('texture_path')
                                    if tex:
                                        from py_editor.ui.shader_manager import get_texture
                                        tid = get_texture(tex)
                                        if tid:
                                            from OpenGL.GL import glActiveTexture, glBindTexture, GL_TEXTURE0, GL_TEXTURE_2D
                                            glActiveTexture(GL_TEXTURE0); glBindTexture(GL_TEXTURE_2D, tid)
                                            s.set_uniform_i("u_tex0", 0); s.set_uniform_f("u_has_tex", 1.0)
                                    for k, v in m_data.items():
                                        if k == 'base_color':
                                            if len(v) == 3: s.set_uniform_v4(k, v[0], v[1], v[2], 1.0)
                                            else: s.set_uniform_v4(k, *v)
                                        elif isinstance(v, (int, float)): s.set_uniform_f(k, float(v))
                                except: pass
                            else:
                                if sn == 'Standard': s.set_uniform_v4("base_color", 1.0, 1.0, 1.0, 1.0)

                        last_sn = sn
                    
                    # Apply spawner-specific params if any
                    active_s = get_shader(sn)
                    if active_s:
                        p = sp.get('shader_params', {})
                        for k, v in p.items():
                            if isinstance(v, (int, float)): active_s.set_uniform_f(k, float(v))
                            elif isinstance(v, (list, tuple)) and len(v) == 4: active_s.set_uniform_v4(k, *v)

                    glPushMatrix()
                    glTranslatef(*sp['pos'])
                    glRotatef(sp['rot'][0], 1, 0, 0)
                    glRotatef(sp['rot'][1], 0, 1, 0)
                    glRotatef(sp['rot'][2], 0, 0, 1)
                    glScalef(*sp['scale'])

                    kind = sp.get('kind', 'object:cube')
                    if kind == 'object:sphere': _draw_wireframe_sphere()
                    elif kind == 'object:plane': _draw_wireframe_plane()
                    elif kind == 'object:cylinder': _draw_wireframe_cylinder()
                    elif kind == 'object:cone': _draw_wireframe_cone()
                    else: _draw_wireframe_cube()
                    glPopMatrix()
            
            # Cleanup shader state
            glUseProgram(0)
            glEnable(GL_CULL_FACE)
        except Exception as e:
            print(f"[VOXEL SPAWN] {e}")

    def _create_voxel_vao(self, verts, idx, norms, colors=None):
        """Create a VAO for voxel mesh with high-precision gradient normals.

        If ``colors`` (Nx4 float32 RGBA) is given, uploads it to attribute
        location 3 — which in the OpenGL compatibility profile aliases
        ``gl_Color``. The Standard shader uses the alpha channel as a mask
        (0 = use base_color, 1 = use vertex color) so biome tints blend in
        without affecting objects that don't upload a color buffer.
        """
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

        cvbo = None
        if colors is not None and len(colors) == len(verts):
            cvbo = glGenBuffers(1)
            glBindBuffer(GL_ARRAY_BUFFER, cvbo)
            glBufferData(GL_ARRAY_BUFFER, colors.nbytes, colors, GL_STATIC_DRAW)
            glVertexAttribPointer(3, 4, GL_FLOAT, GL_FALSE, 16, None)
            glEnableVertexAttribArray(3)

        ibo = glGenBuffers(1)
        glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, ibo)
        glBufferData(GL_ELEMENT_ARRAY_BUFFER, idx.nbytes, idx, GL_STATIC_DRAW)

        glBindVertexArray(0)
        return {'vao': vao, 'vbo': vbo, 'ibo': ibo, 'cvbo': cvbo, 'count': len(idx)}


def _compute_biome_spawns(verts_w, idx, norms, obj_pos, biomes, seed_hash):
    """Place spawner instances on surface triangles.

    For every biome × spawner, build a per-triangle probability mask from the
    spawner's slope/height gates, then pick triangles using a hash-seeded RNG
    so the same chunk always produces identical spawns (stable across
    regenerations and cache misses).

    Returns a list of dicts: {'kind', 'prefab_path', 'pos'(3), 'rot'(3), 'scale'(3)}.
    """
    spawns_out = []
    if not biomes or len(idx) == 0 or len(verts_w) == 0:
        return spawns_out

    try:
        tri = idx.reshape(-1, 3)
        v0 = verts_w[tri[:, 0]]
        v1 = verts_w[tri[:, 1]]
        v2 = verts_w[tri[:, 2]]
        centroid = (v0 + v1 + v2) / 3.0
        # Triangle normal — use face normal (cross of edges) for slope, consistent
        # across smooth/flat shading.
        e1 = v1 - v0
        e2 = v2 - v0
        fn = np.cross(e1, e2)
        fn_len = np.linalg.norm(fn, axis=1, keepdims=True) + 1e-8
        fn_unit = fn / fn_len
        area = 0.5 * fn_len.squeeze(-1)
        world_y = centroid[:, 1] + float(obj_pos[1])
        slope = np.clip(fn_unit[:, 1], 0.0, 1.0)
    
        rng = np.random.default_rng(int(seed_hash) & 0x7FFFFFFF)

        for b in biomes:
            hr = b.get('height_range', [-1e9, 1e9])
            sr = b.get('slope_range',  [0.0, 1.0])
            biome_mask = ((world_y >= float(hr[0])) & (world_y <= float(hr[1])) &
                          (slope   >= float(sr[0])) & (slope   <= float(sr[1])))
            if not np.any(biome_mask):
                continue
            for sp in b.get('spawns', []) or []:
                density = float(sp.get('density', 0.0))
                if density <= 0.0: continue
                
                # Inherit biome color for instance tinting
                b_color = b.get('surface', {}).get('color', (1.0, 1.0, 1.0, 1.0))
                shr = sp.get('height_range',
                             [float(sp.get('height_min', -1e9)),
                              float(sp.get('height_max',  1e9))])
                ssr = sp.get('slope_range',
                             [float(sp.get('slope_min', 0.0)),
                              float(sp.get('slope_max', 1.0))])
                m = (biome_mask &
                     (world_y >= float(shr[0])) & (world_y <= float(shr[1])) &
                     (slope   >= float(ssr[0])) & (slope   <= float(ssr[1])))
                cand = np.where(m)[0]
                if len(cand) == 0: continue
                # Area-weighted sampling so bigger tris get proportionally more
                # spawns — keeps density perceptually uniform.
                probs = area[cand] * density
                hits = rng.random(len(cand)) < np.clip(probs, 0.0, 0.95)
                picks = cand[hits]
                num_picks = len(picks)
                if num_picks == 0: continue
                
                jitter = float(sp.get('jitter', 0.0))
                smin = float(sp.get('scale_min', 1.0))
                smax = max(smin, float(sp.get('scale_max', 1.0)))
                # Boost fallback scales so primitive spawners aren't micro-tiny
                if smax <= 0.1: smax = 1.0
                
                align = bool(sp.get('align_to_normal', False))
                kind = sp.get('kind', 'object:cube')
                prefab_path = sp.get('prefab_path', '')
                shader_name = sp.get('shader_name', 'Standard')

                # Vectorized computation of barycentric coordinates and positions
                bary = rng.random((num_picks, 3)).astype(np.float32)
                bary /= bary.sum(axis=1, keepdims=True)
                
                p_arr = (v0[picks] * bary[:, 0:1] + 
                         v1[picks] * bary[:, 1:2] + 
                         v2[picks] * bary[:, 2:3])
                
                if jitter > 0.0:
                    edge_lens = np.linalg.norm(v1[picks] - v0[picks], axis=1, keepdims=True)
                    p_arr += (rng.random((num_picks, 3)).astype(np.float32) - 0.5) * (edge_lens * jitter)
                    
                s_arr = rng.uniform(smin, smax, size=num_picks)
                
                if align:
                    n_arr = fn_unit[picks]
                    yaw_arr = np.degrees(np.arctan2(n_arr[:, 0], n_arr[:, 2]))
                    pitch_arr = np.degrees(np.arcsin(-n_arr[:, 1])) + 90.0
                    rot_arr = np.column_stack((pitch_arr, yaw_arr, np.zeros(num_picks)))
                else:
                    yaw_arr = rng.uniform(0.0, 360.0, size=num_picks)
                    rot_arr = np.column_stack((np.zeros(num_picks), yaw_arr, np.zeros(num_picks)))

                # Only iterate at the final packing stage
                for i in range(num_picks):
                    s_val = float(s_arr[i])
                    spawns_out.append({
                        'kind': kind,
                        'prefab_path': prefab_path,
                        'shader_name': shader_name,
                        'material_path': sp.get('material_path', ''),
                        'shader_params': sp.get('shader_params', {}),
                        'pos':   [float(p_arr[i, 0]), float(p_arr[i, 1]), float(p_arr[i, 2])],
                        'rot':   [float(rot_arr[i, 0]), float(rot_arr[i, 1]), float(rot_arr[i, 2])],
                        'scale': [s_val, s_val, s_val],
                        'color': b_color,
                    })
                
    except Exception as e:
        print(f"[BIOME SPAWNER ERROR] Vectorization math fault: {e}")

    return spawns_out


def _compute_biome_colors(verts_w, obj_pos_y, normals, biomes):
    """Per-vertex RGBA from biome rules. Alpha=1 where a biome matched, else 0.

    verts_w: (N,3) float32 — positions relative to obj_pos
    normals: (N,3) float32
    biomes:  list of {'height_range':[lo,hi], 'slope_range':[lo,hi],
                      'surface':{'color':[r,g,b,a],...}}
    Biomes are checked in order; first match wins so users can layer rules.
    """
    N = len(verts_w)
    out = np.zeros((N, 4), dtype=np.float32)
    if not biomes or N == 0:
        return out
    world_y = verts_w[:, 1] + float(obj_pos_y)
    slope   = np.clip(normals[:, 1], 0.0, 1.0)
    unassigned = np.ones(N, dtype=bool)
    for b in biomes:
        hr = b.get('height_range', [-1e9, 1e9])
        sr = b.get('slope_range',  [0.0, 1.0])
        col = b.get('surface', {}).get('color', [0.5, 0.5, 0.5, 1.0])
        m = (unassigned &
             (world_y >= float(hr[0])) & (world_y <= float(hr[1])) &
             (slope   >= float(sr[0])) & (slope   <= float(sr[1])))
        if np.any(m):
            out[m] = np.array([col[0], col[1], col[2], 1.0], dtype=np.float32)
            unassigned &= ~m
    return out
