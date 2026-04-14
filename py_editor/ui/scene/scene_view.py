"""
scene_view.py

OpenGL viewport with 2D/3D grid, scene objects, gizmos, and navigation.
"""
import time
import math
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
        self._drag_start_pos = None
        self._drag_obj_start_pos = None
        
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
        self.update()

    def _tick(self):
        now = time.perf_counter()
        dt = now - self._last_time
        self._last_time = now

        if self._mode == "3D" and self._rmb:
            fwd = (1 if Qt.Key.Key_W in self._keys else 0) - (1 if Qt.Key.Key_S in self._keys else 0)
            rgt = (1 if Qt.Key.Key_D in self._keys else 0) - (1 if Qt.Key.Key_A in self._keys else 0)
            upd = (1 if Qt.Key.Key_E in self._keys else 0) - (1 if Qt.Key.Key_Q in self._keys else 0)
            if fwd or rgt or upd:
                # Use dynamic speed from viewport or active camera settings
                speed = getattr(self, 'camera_speed', 10.0) 
                self._cam3d.move(fwd, rgt, upd, dt, speed)

        # Update ocean time
        self._elapsed_time += max(0.0, min(dt, 0.1))
        
        # Fade out logs
        cur_time = time.time()
        self._screen_logs = [log for log in self._screen_logs if cur_time - log.get('timestamp', 0) < 5.0]
        
        self.update()

    def initializeGL(self):
        glClearColor(*BG_COLOR)
        glEnable(GL_DEPTH_TEST); glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        try:
            from py_editor.ui.procedural_ocean import init_ocean_gpu
            init_ocean_gpu()
        except Exception: pass
        self.start_render_loop()

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
        if event.button() == Qt.MouseButton.LeftButton:
            self._lmb = True
            
            # 1. Try picking Gizmo first
            sel = next((o for o in self.scene_objects if o.selected), None)
            if sel:
                axis = self._pick_gizmo_axis(mx, my, sel.position)
                if axis:
                    self._gizmo_axis = axis
                    self._drag_start_pos = (mx, my)
                    self._drag_obj_start_pos = list(sel.position)
                    print(f"[VIEWPORT] Dragging axis: {axis}")
                    return # Skip object picking if we hit gizmo
            
            # 2. Pick Object
            found = self._pick_object(mx, my)
            self.object_selected.emit(found)
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
            sel = next((o for o in self.scene_objects if o.selected), None)
            if sel:
                dx = mx - self._drag_start_pos[0]
                dy = my - self._drag_start_pos[1]
                factor = 0.1 # Movement sensitivity
                rot_factor = 0.5 # Degrees per pixel
                scale_factor = 0.01 # Scale per pixel
                
                # Camera vectors for reference
                r, u, f = self._cam3d.right, self._cam3d.up, self._cam3d.front
                
                if self._gizmo_mode == "translate":
                    if self._gizmo_axis == 'x':
                        sel.position[0] = self._drag_obj_start_pos[0] + dx * factor * r[0] - dy * factor * u[0]
                    elif self._gizmo_axis == 'y':
                        sel.position[1] = self._drag_obj_start_pos[1] - dy * factor
                    elif self._gizmo_axis == 'z':
                        sel.position[2] = self._drag_obj_start_pos[2] + dx * factor * r[2] - dy * factor * u[2]
                
                elif self._gizmo_mode == "rotate":
                    # Dragging horizontally/vertically rotates around the axis
                    delta = dx - dy
                    if self._gizmo_axis == 'x': sel.rotation[0] += delta * rot_factor
                    elif self._gizmo_axis == 'y': sel.rotation[1] += delta * rot_factor
                    elif self._gizmo_axis == 'z': sel.rotation[2] += delta * rot_factor
                
                elif self._gizmo_mode == "scale":
                    # Dragging adds to current scale
                    delta = (dx - dy) * scale_factor
                    if self._gizmo_axis == 'x': sel.scale[0] = max(0.01, self._drag_obj_start_pos[0] + delta)
                    elif self._gizmo_axis == 'y': sel.scale[1] = max(0.01, self._drag_obj_start_pos[1] + delta)
                    elif self._gizmo_axis == 'z': sel.scale[2] = max(0.01, self._drag_obj_start_pos[2] + delta)

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
        w, h = self.width(), self.height()
        if w < 1 or h < 1: return

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
            
            # 4. Ocean
            for obj in self.scene_objects:
                if obj.obj_type == 'ocean' and obj.active:
                    from py_editor.ui.procedural_ocean import render_ocean_gpu
                    render_ocean_gpu(self._cam3d.pos, obj, self._elapsed_time)
            
            # 5. Primitives
            self._draw_scene_objects_3d()
            
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
        if Qt.Key.Key_1 in self._keys: self._cam3d.speed = 2.0
        elif Qt.Key.Key_2 in self._keys: self._cam3d.speed = 10.0
        elif Qt.Key.Key_3 in self._keys: self._cam3d.speed = 50.0
        elif Qt.Key.Key_4 in self._keys: self._cam3d.speed = 200.0
        elif Qt.Key.Key_5 in self._keys: self._cam3d.speed = 1000.0

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
        for obj in self.scene_objects:
            # Render invisible objects as icons if they aren't 'visible'
            glPushMatrix()
            glTranslatef(*obj.position)
            glRotatef(obj.rotation[0], 1, 0, 0)
            glRotatef(obj.rotation[1], 0, 1, 0)
            glRotatef(obj.rotation[2], 0, 0, 1)
            glScalef(*obj.scale)
            
            if obj.visible:
                if obj.obj_type in ('cube', 'plane'):
                    _draw_wireframe_cube()
                elif obj.obj_type == 'sphere':
                    _draw_wireframe_sphere()
            
            # Icons for specialty objects
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
        if text.startswith("prim:") or text.startswith("logic:"):
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
