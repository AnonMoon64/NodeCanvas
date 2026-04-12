"""
Scene Editor ΓÇö OpenGL-powered 2D/3D viewport for NodeCanvas.

Features:
- Mode selector: Pure | UI | 2D | 3D
- OpenGL grid rendering (2D orthographic / 3D perspective)
- UE5-style camera navigation (fly cam, orbit, pan, zoom)
- Transform gizmos (Move / Rotate / Scale)
- Scene explorer panel with primitives, project assets, outliner, and properties
- Drag-and-drop object creation
- Object selection and screen-proportional movement
- Inline UI Builder for UI mode
- Dark theme matching the Logic editor
"""

import math
import time
import os
import uuid
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QCheckBox, QDoubleSpinBox, QFrame, QSizePolicy,
    QToolButton, QButtonGroup, QSpacerItem, QSplitter,
    QTreeWidget, QTreeWidgetItem, QListWidget, QListWidgetItem,
    QStackedWidget, QAbstractItemView, QMenu, QInputDialog,
    QScrollArea, QGridLayout, QGroupBox,
)
from PyQt6.QtGui import (
    QColor, QPainter, QFont, QSurfaceFormat, QMouseEvent,
    QWheelEvent, QKeyEvent, QPen, QBrush, QCursor, QDrag,
    QIcon, QPixmap,
)
from PyQt6.QtCore import (
    Qt, QTimer, QSize, QPointF, pyqtSignal, QElapsedTimer,
    QMimeData, QPoint,
)

try:
    from PyQt6.QtOpenGLWidgets import QOpenGLWidget
except ImportError:
    QOpenGLWidget = None

try:
    from OpenGL.GL import *
    from OpenGL.GLU import *
    HAS_OPENGL = True
except ImportError:
    HAS_OPENGL = False


# ---------------------------------------------------------------------------
# Colour constants matching the Logic editor dark theme
# ---------------------------------------------------------------------------
BG_COLOR           = (0.102, 0.102, 0.102, 1.0)   # #1a1a1a
GRID_MINOR_COLOR   = (0.165, 0.165, 0.165, 0.5)   # #2a2a2a
GRID_MAJOR_COLOR   = (0.227, 0.227, 0.227, 0.7)   # #3a3a3a
AXIS_X_COLOR       = (0.878, 0.333, 0.333, 1.0)   # red
AXIS_Y_COLOR       = (0.333, 0.878, 0.333, 1.0)   # green
AXIS_Z_COLOR       = (0.333, 0.333, 0.878, 1.0)   # blue
ORIGIN_COLOR       = (1.0,   1.0,   1.0,   0.4)   # white dot
SELECT_COLOR       = (0.310, 0.765, 0.969, 1.0)    # #4fc3f7
OBJECT_COLOR       = (0.7,   0.7,   0.7,   0.8)    # default wireframe
OBJECT_FACE_COLOR  = (0.25,  0.25,  0.28,  0.4)    # subtle fill
GIZMO_ALPHA        = 0.9

# Stylesheet fragments
TOOLBAR_SS = """
    QWidget#SceneToolbar {
        background: #2a2a2a;
        border-bottom: 1px solid #444;
    }
"""
BTN_SS = """
    QPushButton, QToolButton {
        background: #3a3a3a; border: 1px solid #555; border-radius: 4px;
        color: #e0e0e0; padding: 4px 10px; font-size: 11px;
    }
    QPushButton:hover, QToolButton:hover { background: #4a4a4a; }
    QPushButton:checked, QToolButton:checked {
        background: #4fc3f7; color: #1a1a1a; border-color: #4fc3f7;
    }
    QPushButton:disabled, QToolButton:disabled {
        color: #666; background: #2e2e2e; border-color: #444;
    }
"""
COMBO_SS = """
    QComboBox {
        background: #3a3a3a; border: 1px solid #555; border-radius: 4px;
        color: #e0e0e0; padding: 4px 8px; font-size: 11px; min-width: 80px;
    }
    QComboBox:hover { border-color: #4fc3f7; }
    QComboBox::drop-down { border: none; width: 20px; }
    QComboBox::down-arrow { image: none; border: none; }
    QComboBox QAbstractItemView {
        background: #2a2a2a; color: #e0e0e0;
        selection-background-color: #4fc3f7; selection-color: #1a1a1a;
        border: 1px solid #555;
    }
"""
PANEL_SS = """
    QWidget#ExplorerPanel {
        background: #252526;
        border-right: 1px solid #3c3c3c;
    }
"""
SECTION_HEADER_SS = """
    QPushButton {
        background-color: #252526; color: #e0e0e0; border: none;
        text-align: left; padding: 6px 8px; font-weight: bold; font-size: 11px;
    }
    QPushButton:hover { background-color: #2a2d2e; }
"""
LIST_SS = """
    QListWidget {
        background: #1e1e1e; border: none; color: #ccc;
        font-size: 12px; outline: none;
    }
    QListWidget::item { padding: 5px 8px; border: none; }
    QListWidget::item:hover { background: #2a2d2e; }
    QListWidget::item:selected { background: #094771; color: #fff; }
"""
TREE_SS = """
    QTreeWidget {
        background: #1e1e1e; border: none; color: #ccc;
        font-size: 12px; outline: none;
    }
    QTreeWidget::item { padding: 3px 4px; }
    QTreeWidget::item:hover { background: #2a2d2e; }
    QTreeWidget::item:selected { background: #094771; color: #fff; }
    QTreeWidget::branch { background: #1e1e1e; }
"""
PROPS_SS = """
    QGroupBox {
        background: #252526; border: 1px solid #3c3c3c; border-radius: 4px;
        margin-top: 8px; padding-top: 14px; color: #ccc; font-size: 11px;
    }
    QGroupBox::title {
        subcontrol-origin: margin; left: 8px; padding: 0 4px; color: #4fc3f7;
        font-weight: bold;
    }
"""
SPIN_SS = """
    QDoubleSpinBox {
        background: #333; border: 1px solid #555; border-radius: 3px;
        color: #e0e0e0; padding: 2px 4px; font-size: 11px;
    }
    QDoubleSpinBox:hover { border-color: #4fc3f7; }
    QDoubleSpinBox:focus { border-color: #4fc3f7; }
"""
LABEL_SS = "color: #888; font-size: 11px;"


# ===================================================================
# Scene Object
# ===================================================================

class SceneObject:
    """Represents an entity in the scene."""

    def __init__(self, name: str, obj_type: str, position=None, rotation=None, scale=None):
        self.id = str(uuid.uuid4())[:8]
        self.name = name
        self.obj_type = obj_type
        self.position = list(position or [0.0, 0.0, 0.0])
        self.rotation = list(rotation or [0.0, 0.0, 0.0])
        self.scale = list(scale or [1.0, 1.0, 1.0])
        self.selected = False
        self.color = list(OBJECT_COLOR)
        self.file_path = None

    def to_dict(self) -> dict:
        return {
            'id': self.id, 'name': self.name, 'type': self.obj_type,
            'position': self.position, 'rotation': self.rotation, 'scale': self.scale,
            'color': self.color, 'file_path': self.file_path,
        }

    @staticmethod
    def from_dict(d: dict) -> 'SceneObject':
        obj = SceneObject(d['name'], d['type'], d.get('position'), d.get('rotation'), d.get('scale'))
        obj.id = d.get('id', obj.id)
        obj.color = d.get('color', obj.color)
        obj.file_path = d.get('file_path')
        return obj


# ===================================================================
# Camera helpers (pure math, no numpy dependency)
# ===================================================================

def _cross(a, b):
    return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])

def _normalize(v):
    ln = math.sqrt(v[0]*v[0]+v[1]*v[1]+v[2]*v[2])
    return (v[0]/ln, v[1]/ln, v[2]/ln) if ln > 1e-9 else (0,0,0)

def _dot(a, b):
    return a[0]*b[0]+a[1]*b[1]+a[2]*b[2]

def _sub(a, b):
    return (a[0]-b[0], a[1]-b[1], a[2]-b[2])

def _add(a, b):
    return (a[0]+b[0], a[1]+b[1], a[2]+b[2])

def _scale_vec(v, s):
    return (v[0]*s, v[1]*s, v[2]*s)

def _length(v):
    return math.sqrt(v[0]*v[0]+v[1]*v[1]+v[2]*v[2])

def _dist_line_line(p1, d1, p2, d2):
    """Distance between two infinite lines. Returns (distance, t_on_line1, t_on_line2)."""
    w0 = _sub(p1, p2)
    a, b, c, d, e = _dot(d1,d1), _dot(d1,d2), _dot(d2,d2), _dot(d1,w0), _dot(d2,w0)
    denom = a*c - b*b
    if abs(denom) < 1e-9:
        return _length(_cross(d1, w0)) / (math.sqrt(a) if a > 0 else 1.0), 0, 0
    tc = (a*e - b*d) / denom
    sc = (b*tc - d) / a
    return _length(_sub(_add(p1, _scale_vec(d1, sc)), _add(p2, _scale_vec(d2, tc)))), sc, tc

def _ray_intersect_sphere(origin, direction, center, radius):
    L = _sub(center, origin)
    tca = _dot(L, direction)
    if tca < 0: return None
    d2 = _dot(L, L) - tca*tca
    r2 = radius*radius
    if d2 > r2: return None
    thc = math.sqrt(r2 - d2)
    return tca - thc

def _ray_intersect_aabb(origin, direction, amin, amax):
    tmin = -1e30; tmax = 1e30
    for i in range(3):
        if abs(direction[i]) < 1e-9:
            if origin[i] < amin[i] or origin[i] > amax[i]: return None
        else:
            inv_d = 1.0 / direction[i]
            t1 = (amin[i] - origin[i]) * inv_d
            t2 = (amax[i] - origin[i]) * inv_d
            if t1 > t2: t1, t2 = t2, t1
            tmin = max(tmin, t1); tmax = min(tmax, t2)
    if tmax < tmin or tmax < 0: return None
    return tmin

def _euler_to_matrix(ex, ey, ez):
    # Order: Y (Yaw) * X (Pitch) * Z (Roll) - Standard World-Space behavior
    rx, ry, rz = math.radians(ex), math.radians(ey), math.radians(ez)
    cx, sx = math.cos(rx), math.sin(rx)
    cy, sy = math.cos(ry), math.sin(ry)
    cz, sz = math.cos(rz), math.sin(rz)
    # Rotation Matrices
    Mx = [[1, 0, 0], [0, cx, -sx], [0, sx, cx]]
    My = [[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]]
    Mz = [[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]]
    # Product: R = My * Mx * Mz
    def __mul(A, B):
        C = [[0]*3 for _ in range(3)]
        for i in range(3):
            for j in range(3):
                for k in range(3): C[i][j] += A[i][k] * B[k][j]
        return C
    return __mul(My, __mul(Mx, Mz))

def _matrix_to_euler(M):
    # Recover YXZ-order Euler angles
    # M[1][2] = -sx -> sx = -M[1][2]
    try:
        rx = math.asin(-max(-1.0, min(1.0, M[1][2])))
        if abs(math.cos(rx)) > 1e-4:
            ry = math.atan2(M[0][2], M[2][2])
            rz = math.atan2(M[1][0], M[1][1])
        else:
            ry = math.atan2(-M[2][0], M[0][0])
            rz = 0.0
        return [math.degrees(rx), math.degrees(ry), math.degrees(rz)]
    except: return [0.0, 0.0, 0.0]

def _axis_angle_to_matrix(axis_vec, angle_deg):
    r = math.radians(angle_deg)
    c, s = math.cos(r), math.sin(r); t = 1-c
    x, y, z = _normalize(axis_vec)
    return [
        [t*x*x + c,   t*x*y - s*z, t*x*z + s*y],
        [t*x*y + s*z, t*y*y + c,   t*y*z - s*x],
        [t*x*z - s*y, t*y*z + s*x, t*z*z + c]
    ]

def _mat_mul_3x3(A, B):
    C = [[0]*3 for _ in range(3)]
    for i in range(3):
        for j in range(3):
            for k in range(3): C[i][j] += A[i][k] * B[k][j]
    return C


class Camera3D:
    """First-person / orbit camera with UE5-style controls."""
    def __init__(self):
        self.pos = [0.0, 5.0, 10.0]
        self.yaw = -90.0
        self.pitch = -25.0
        self.fov = 60.0
        self.near = 0.1
        self.far = 5000.0
        self.speed = 10.0
        self.sensitivity = 0.15

    @property
    def front(self):
        yr, pr = math.radians(self.yaw), math.radians(self.pitch)
        return _normalize((math.cos(yr)*math.cos(pr), math.sin(pr), math.sin(yr)*math.cos(pr)))

    @property
    def right(self):
        return _normalize(_cross(self.front, (0,1,0)))

    @property
    def up(self):
        return _normalize(_cross(self.right, self.front))

    def apply_gl(self, aspect):
        glMatrixMode(GL_PROJECTION); glLoadIdentity()
        gluPerspective(self.fov, aspect, self.near, self.far)
        glMatrixMode(GL_MODELVIEW); glLoadIdentity()
        f = self.front
        t = (self.pos[0]+f[0], self.pos[1]+f[1], self.pos[2]+f[2])
        u = self.up
        gluLookAt(self.pos[0],self.pos[1],self.pos[2], t[0],t[1],t[2], u[0],u[1],u[2])

    def move(self, forward, right, up, dt):
        f, r = self.front, self.right
        s = self.speed * dt
        self.pos[0] += (f[0]*forward+r[0]*right)*s
        self.pos[1] += up*s
        self.pos[2] += (f[2]*forward+r[2]*right)*s

    def rotate(self, dx, dy):
        self.yaw += dx*self.sensitivity
        self.pitch = max(-89.0, min(89.0, self.pitch - dy*self.sensitivity))

    def screen_to_ray(self, mx, my, vp_w, vp_h):
        """Get ray origin and direction from screen coordinates."""
        aspect = vp_w / max(vp_h, 1)
        fov_rad = math.radians(self.fov)
        half_h = math.tan(fov_rad / 2.0)
        half_w = half_h * aspect
        nx = (2.0 * mx / vp_w - 1.0) * half_w
        ny = (1.0 - 2.0 * my / vp_h) * half_h
        f, r, u = self.front, self.right, self.up
        direction = _normalize(_add(_add(_scale_vec(f, 1.0), _scale_vec(r, nx)), _scale_vec(u, ny)))
        return tuple(self.pos), direction

    def _get_view_proj_matrix(self, aspect):
        # Build simple projection and view matrices for world_to_screen
        # P = gluPerspective, V = gluLookAt
        f = self.front; r = self.right; u = self.up
        # View matrix (V)
        V = [
            [r[0], r[1], r[2], -_dot(r, self.pos)],
            [u[0], u[1], u[2], -_dot(u, self.pos)],
            [-f[0], -f[1], -f[2], _dot(f, self.pos)],
            [0, 0, 0, 1]
        ]
        # Proj matrix (P)
        fov_rad = math.radians(self.fov)
        h = 1.0 / math.tan(fov_rad / 2.0)
        w = h / aspect
        far, near = self.far, self.near
        P = [
            [w, 0, 0, 0],
            [0, h, 0, 0],
            [0, 0, -(far+near)/(far-near), -(2*far*near)/(far-near)],
            [0, 0, -1, 0]
        ]
        # Multiply P * V
        PV = [[0]*4 for _ in range(4)]
        for i in range(4):
            for j in range(4):
                for k in range(4):
                    PV[i][j] += P[i][k] * V[k][j]
        return PV

    def world_to_screen(self, world_pos, vp_w, vp_h):
        """Project world coordinates to screen space. Returns (x, y) or None."""
        aspect = vp_w / max(vp_h, 1)
        PV = self._get_view_proj_matrix(aspect)
        # Transform pos
        v = (world_pos[0], world_pos[1], world_pos[2], 1.0)
        out = [0.0]*4
        for i in range(4):
            for j in range(4):
                out[i] += PV[i][j] * v[j]
        if out[3] <= 0: return None # behind camera
        # NDC
        nx = out[0] / out[3]
        ny = out[1] / out[3]
        # Screen
        sx = (nx + 1.0) * 0.5 * vp_w
        sy = (1.0 - ny) * 0.5 * vp_h
        return (sx, sy)

    def ray_plane_intersect(self, mx, my, vp_w, vp_h, plane_point, plane_normal):
        """Intersect a screen ray with a world plane. Returns world point or None."""
        origin, direction = self.screen_to_ray(mx, my, vp_w, vp_h)
        denom = _dot(direction, plane_normal)
        if abs(denom) < 1e-9:
            return None
        diff = _sub(plane_point, origin)
        t = _dot(diff, plane_normal) / denom
        if t < 0:
            return None
        return _add(origin, _scale_vec(direction, t))


class Camera2D:
    """Ortho camera for 2D mode."""
    def __init__(self):
        self.x = 0.0
        self.y = 0.0
        self.zoom_level = 10.0

    def apply_gl(self, width, height):
        aspect = width / max(height, 1)
        hw, hh = self.zoom_level * aspect, self.zoom_level
        glMatrixMode(GL_PROJECTION); glLoadIdentity()
        glOrtho(self.x-hw, self.x+hw, self.y-hh, self.y+hh, -1.0, 1.0)
        glMatrixMode(GL_MODELVIEW); glLoadIdentity()

    def pan(self, dx, dy, width, height):
        aspect = width / max(height, 1)
        hw, hh = self.zoom_level * aspect, self.zoom_level
        self.x -= dx / max(width,1) * hw * 2
        self.y += dy / max(height,1) * hh * 2

    def zoom_by(self, delta):
        self.zoom_level *= (1.1 if delta < 0 else 0.9)
        self.zoom_level = max(0.5, min(10000, self.zoom_level))

    def screen_to_world(self, mx, my, width, height):
        aspect = width / max(height, 1)
        hw, hh = self.zoom_level * aspect, self.zoom_level
        wx = self.x + (2.0 * mx / width - 1.0) * hw
        wy = self.y + (1.0 - 2.0 * my / height) * hh
        return wx, wy


# ===================================================================
# Wireframe primitive drawing helpers (legacy GL)
# ===================================================================

def _draw_wireframe_cube(sx=1, sy=1, sz=1, color=OBJECT_COLOR, fill_color=OBJECT_FACE_COLOR):
    hx, hy, hz = sx/2, sy/2, sz/2
    verts = [
        (-hx,-hy,-hz),(hx,-hy,-hz),(hx,hy,-hz),(-hx,hy,-hz),
        (-hx,-hy,hz),(hx,-hy,hz),(hx,hy,hz),(-hx,hy,hz),
    ]
    faces = [(0,1,2,3),(4,5,6,7),(0,1,5,4),(2,3,7,6),(0,3,7,4),(1,2,6,5)]
    edges = [(0,1),(1,2),(2,3),(3,0),(4,5),(5,6),(6,7),(7,4),(0,4),(1,5),(2,6),(3,7)]
    glColor4f(*fill_color)
    for f in faces:
        glBegin(GL_QUADS)
        for i in f: glVertex3f(*verts[i])
        glEnd()
    glColor4f(*color); glLineWidth(1.5)
    glBegin(GL_LINES)
    for a, b in edges: glVertex3f(*verts[a]); glVertex3f(*verts[b])
    glEnd(); glLineWidth(1.0)


def _draw_wireframe_sphere(radius=0.5, rings=12, segments=16, color=OBJECT_COLOR):
    glColor4f(*color); glLineWidth(1.5)
    for i in range(rings + 1):
        phi = math.pi * i / rings
        y = radius * math.cos(phi); r = radius * math.sin(phi)
        glBegin(GL_LINE_LOOP)
        for j in range(segments):
            theta = 2.0 * math.pi * j / segments
            glVertex3f(r * math.cos(theta), y, r * math.sin(theta))
        glEnd()
    for j in range(segments):
        theta = 2.0 * math.pi * j / segments
        glBegin(GL_LINE_STRIP)
        for i in range(rings + 1):
            phi = math.pi * i / rings
            y = radius * math.cos(phi); r = radius * math.sin(phi)
            glVertex3f(r * math.cos(theta), y, r * math.sin(theta))
        glEnd()
    glLineWidth(1.0)


def _draw_wireframe_cylinder(radius=0.5, height=1.0, segments=16, color=OBJECT_COLOR):
    hh = height / 2
    glColor4f(*color); glLineWidth(1.5)
    glBegin(GL_LINE_LOOP)
    for i in range(segments):
        a = 2.0 * math.pi * i / segments
        glVertex3f(radius * math.cos(a), hh, radius * math.sin(a))
    glEnd()
    glBegin(GL_LINE_LOOP)
    for i in range(segments):
        a = 2.0 * math.pi * i / segments
        glVertex3f(radius * math.cos(a), -hh, radius * math.sin(a))
    glEnd()
    glBegin(GL_LINES)
    for i in range(0, segments, max(1, segments // 8)):
        a = 2.0 * math.pi * i / segments
        x, z = radius * math.cos(a), radius * math.sin(a)
        glVertex3f(x, hh, z); glVertex3f(x, -hh, z)
    glEnd(); glLineWidth(1.0)


def _draw_wireframe_plane(sx=2, sz=2, color=OBJECT_COLOR, fill_color=OBJECT_FACE_COLOR):
    hx, hz = sx/2, sz/2
    glColor4f(*fill_color)
    glBegin(GL_QUADS)
    glVertex3f(-hx,0,-hz); glVertex3f(hx,0,-hz); glVertex3f(hx,0,hz); glVertex3f(-hx,0,hz)
    glEnd()
    glColor4f(*color); glLineWidth(1.5)
    glBegin(GL_LINE_LOOP)
    glVertex3f(-hx,0,-hz); glVertex3f(hx,0,-hz); glVertex3f(hx,0,hz); glVertex3f(-hx,0,hz)
    glEnd(); glLineWidth(1.0)


def _draw_wireframe_cone(radius=0.5, height=1.0, segments=16, color=OBJECT_COLOR):
    hh = height / 2
    glColor4f(*color); glLineWidth(1.5)
    glBegin(GL_LINE_LOOP)
    for i in range(segments):
        a = 2.0 * math.pi * i / segments
        glVertex3f(radius * math.cos(a), -hh, radius * math.sin(a))
    glEnd()
    glBegin(GL_LINES)
    for i in range(0, segments, max(1, segments // 8)):
        a = 2.0 * math.pi * i / segments
        glVertex3f(radius * math.cos(a), -hh, radius * math.sin(a)); glVertex3f(0, hh, 0)
    glEnd(); glLineWidth(1.0)


def _draw_2d_rect(w=1, h=1, color=OBJECT_COLOR, fill_color=OBJECT_FACE_COLOR):
    hw, hh = w/2, h/2
    glColor4f(*fill_color)
    glBegin(GL_QUADS)
    glVertex2f(-hw,-hh); glVertex2f(hw,-hh); glVertex2f(hw,hh); glVertex2f(-hw,hh)
    glEnd()
    glColor4f(*color); glLineWidth(1.5)
    glBegin(GL_LINE_LOOP)
    glVertex2f(-hw,-hh); glVertex2f(hw,-hh); glVertex2f(hw,hh); glVertex2f(-hw,hh)
    glEnd(); glLineWidth(1.0)


def _draw_2d_circle(radius=0.5, segments=32, color=OBJECT_COLOR, fill_color=OBJECT_FACE_COLOR):
    glColor4f(*fill_color)
    glBegin(GL_TRIANGLE_FAN); glVertex2f(0, 0)
    for i in range(segments + 1):
        a = 2.0 * math.pi * i / segments
        glVertex2f(radius * math.cos(a), radius * math.sin(a))
    glEnd()
    glColor4f(*color); glLineWidth(1.5)
    glBegin(GL_LINE_LOOP)
    for i in range(segments):
        a = 2.0 * math.pi * i / segments
        glVertex2f(radius * math.cos(a), radius * math.sin(a))
    glEnd(); glLineWidth(1.0)


# ===================================================================
# Gizmo drawing helpers
# ===================================================================

def _draw_gizmo_move_3d(size=1.0, hover_part=None):
    """Draw UE5-style Move gizmo: 3 axis arrows (X=red, Y=green, Z=blue) + planes."""
    glDisable(GL_DEPTH_TEST)
    s = size

    def get_color(axis, base):
        if hover_part == axis: return (1.0, 1.0, 0.0, 1.0) # Yellow highlight
        return base

    # Axis shafts
    glLineWidth(4.0 if hover_part in ("X","Y","Z") else 2.5)
    glBegin(GL_LINES)
    glColor4f(*get_color("X", (0.95, 0.2, 0.2, GIZMO_ALPHA))); glVertex3f(0,0,0); glVertex3f(s,0,0)
    glColor4f(*get_color("Y", (0.2, 0.95, 0.2, GIZMO_ALPHA))); glVertex3f(0,0,0); glVertex3f(0,s,0)
    glColor4f(*get_color("Z", (0.3, 0.3, 0.95, GIZMO_ALPHA))); glVertex3f(0,0,0); glVertex3f(0,0,s)
    glEnd()

    # Arrowheads
    arrow = s * 0.18
    segs = 8
    for axis, color_tuple, tip, perp1, perp2 in [
        ("X", (0.95,0.2,0.2,GIZMO_ALPHA), (s,0,0), (0,1,0), (0,0,1)),
        ("Y", (0.2,0.95,0.2,GIZMO_ALPHA), (0,s,0), (1,0,0), (0,0,1)),
        ("Z", (0.3,0.3,0.95,GIZMO_ALPHA), (0,0,s), (1,0,0), (0,1,0)),
    ]:
        glColor4f(*get_color(axis, color_tuple))
        base_offset = [0,0,0]
        base_offset[{"X":0,"Y":1,"Z":2}[axis]] = s - arrow
        glBegin(GL_TRIANGLES)
        for i in range(segs):
            a1 = 2.0 * math.pi * i / segs
            a2 = 2.0 * math.pi * (i+1) / segs
            r = arrow * 0.25
            v1 = _add(base_offset, _add(_scale_vec(perp1, r*math.cos(a1)), _scale_vec(perp2, r*math.sin(a1))))
            v2 = _add(base_offset, _add(_scale_vec(perp1, r*math.cos(a2)), _scale_vec(perp2, r*math.sin(a2))))
            glVertex3f(*v1); glVertex3f(*v2); glVertex3f(*tip)
        glEnd()

    # Small planes
    ps = s * 0.3
    for part, color, v0, v1, v2, v3 in [
        ("XY", (0.95,0.95,0.2), (0,0,0), (ps,0,0), (ps,ps,0), (0,ps,0)),
        ("XZ", (0.95,0.2,0.95), (0,0,0), (ps,0,0), (ps,0,ps), (0,0,ps)),
        ("YZ", (0.2,0.95,0.95), (0,0,0), (0,ps,0), (0,ps,ps), (0,0,ps)),
    ]:
        alpha = 0.6 if hover_part == part else 0.15
        glColor4f(color[0], color[1], color[2], alpha)
        glBegin(GL_QUADS); glVertex3f(*v0); glVertex3f(*v1); glVertex3f(*v2); glVertex3f(*v3); glEnd()
        if hover_part == part:
            glColor4f(1, 1, 0, 0.8); glLineWidth(2.0)
            glBegin(GL_LINE_LOOP); glVertex3f(*v0); glVertex3f(*v1); glVertex3f(*v2); glVertex3f(*v3); glEnd()

    glLineWidth(1.0); glEnable(GL_DEPTH_TEST)


def _draw_gizmo_rotate_3d(size=1.0, hover_part=None):
    """Draw UE5-style Rotate gizmo: 3 circle rings (X=red, Y=green, Z=blue)."""
    glDisable(GL_DEPTH_TEST)
    segs = 64
    r = size * 0.9

    def get_color(axis, base):
        if hover_part == axis: return (1.0, 1.0, 0.0, 1.0)
        return base

    glLineWidth(3.5 if hover_part else 2.5)
    # X ring (YZ plane) ΓÇö red
    glColor4f(*get_color("X", (0.95, 0.2, 0.2, GIZMO_ALPHA)))
    glBegin(GL_LINE_LOOP)
    for i in range(segs):
        a = 2.0 * math.pi * i / segs
        glVertex3f(0, r*math.cos(a), r*math.sin(a))
    glEnd()

    # Y ring (XZ plane) ΓÇö green
    glColor4f(*get_color("Y", (0.2, 0.95, 0.2, GIZMO_ALPHA)))
    glBegin(GL_LINE_LOOP)
    for i in range(segs):
        a = 2.0 * math.pi * i / segs
        glVertex3f(r*math.cos(a), 0, r*math.sin(a))
    glEnd()

    # Z ring (XY plane) ΓÇö blue
    glColor4f(*get_color("Z", (0.3, 0.3, 0.95, GIZMO_ALPHA)))
    glBegin(GL_LINE_LOOP)
    for i in range(segs):
        a = 2.0 * math.pi * i / segs
        glVertex3f(r*math.cos(a), r*math.sin(a), 0)
    glEnd()

    glLineWidth(1.0)
    glEnable(GL_DEPTH_TEST)


def _draw_gizmo_scale_3d(size=1.0, hover_part=None):
    """Draw UE5-style Scale gizmo: 3 axis lines with solid cubes at the tips."""
    glDisable(GL_DEPTH_TEST)
    s = size

    def get_color(axis, base):
        if hover_part == axis or (hover_part == "Uniform"): return (1.0, 1.0, 0.0, 1.0)
        return base

    # Axis shafts
    glLineWidth(4.0 if hover_part else 2.5)
    glBegin(GL_LINES)
    glColor4f(*get_color("X", (0.95, 0.2, 0.2, GIZMO_ALPHA))); glVertex3f(0,0,0); glVertex3f(s,0,0)
    glColor4f(*get_color("Y", (0.2, 0.95, 0.2, GIZMO_ALPHA))); glVertex3f(0,0,0); glVertex3f(0,s,0)
    glColor4f(*get_color("Z", (0.3, 0.3, 0.95, GIZMO_ALPHA))); glVertex3f(0,0,0); glVertex3f(0,0,s)
    glEnd()

    # Cube tips (UE5-style solid wireframe cubes)
    cube_half = s * 0.08
    for axis, color_tuple, center in [
        ("X", (0.95,0.2,0.2,GIZMO_ALPHA), (s,0,0)),
        ("Y", (0.2,0.95,0.2,GIZMO_ALPHA), (0,s,0)),
        ("Z", (0.3,0.3,0.95,GIZMO_ALPHA), (0,0,s)),
    ]:
        col = get_color(axis, color_tuple)
        glColor4f(*col)
        cx, cy, cz = center
        # Draw filled-ish wireframe cube
        _draw_wireframe_cube(cube_half*2, cube_half*2, cube_half*2, col, (col[0], col[1], col[2], 0.4))

    glLineWidth(3.5 if hover_part in ("X","Y","XY") else 2.5)
    glBegin(GL_LINES)
    # X axis
    glColor4f(*get_color("X", (0.95, 0.2, 0.2, GIZMO_ALPHA))); glVertex2f(0,0); glVertex2f(s,0)
    # Y axis (pointing up in 2D world coords)
    glColor4f(*get_color("Y", (0.2, 0.95, 0.2, GIZMO_ALPHA))); glVertex2f(0,0); glVertex2f(0,s)
    glEnd()

    # Arrowheads
    ah = s * 0.15
    glBegin(GL_TRIANGLES)
    glColor4f(*get_color("X", (0.95, 0.2, 0.2, GIZMO_ALPHA)))
    glVertex2f(s,0); glVertex2f(s-ah, ah*0.4); glVertex2f(s-ah, -ah*0.4)
    glColor4f(*get_color("Y", (0.2, 0.95, 0.2, GIZMO_ALPHA)))
    glVertex2f(0,s); glVertex2f(ah*0.4, s-ah); glVertex2f(-ah*0.4, s-ah)
    glEnd()

    # XY handle
    ps = s * 0.2
    c_xy = (0.9, 0.9, 0.3, 0.6 if hover_part == "XY" else 0.15)
    glColor4f(*c_xy)
    glBegin(GL_QUADS); glVertex2f(0,0); glVertex2f(ps,0); glVertex2f(ps,ps); glVertex2f(0,ps); glEnd()
    if hover_part == "XY":
        glColor4f(1, 1, 0, 0.8); glLineWidth(2.0)
        glBegin(GL_LINE_LOOP); glVertex2f(0,0); glVertex2f(ps,0); glVertex2f(ps,ps); glVertex2f(0,ps); glEnd()

    glLineWidth(1.0); glEnable(GL_DEPTH_TEST)


def _draw_gizmo_rotate_2d(size=1.0, hover_part=None):
    """Draw 2D rotate gizmo as a circle with a top handle."""
    glDisable(GL_DEPTH_TEST)
    r = size * 0.85
    segs = 48
    
    col = (1.0, 1.0, 0.0, 1.0) if hover_part == "Rotate" else (0.3, 0.3, 0.95, GIZMO_ALPHA)
    
    # Guideline circle
    glColor4f(col[0], col[1], col[2], 0.3); glLineWidth(1.0)
    glBegin(GL_LINE_LOOP)
    for i in range(segs):
        a = 2.0 * math.pi * i / segs
        glVertex2f(r*math.cos(a), r*math.sin(a))
    glEnd()
    # Center box
    glColor4f(0.9,0.9,0.9,GIZMO_ALPHA)
    ch = s * 0.08
    glBegin(GL_LINE_LOOP)
    glVertex2f(-ch,-ch); glVertex2f(ch,-ch); glVertex2f(ch,ch); glVertex2f(-ch,ch)
    glEnd()
    glLineWidth(1.0)
    glEnable(GL_DEPTH_TEST)


def _ray_intersect_aabb(origin, direction, aabb_min, aabb_max):
    """Simple ray-AABB intersection. Returns distance or None."""
    tmin = -1e30; tmax = 1e30
    for i in range(3):
        if abs(direction[i]) < 1e-9:
            if origin[i] < aabb_min[i] or origin[i] > aabb_max[i]:
                return None
        else:
            t1 = (aabb_min[i] - origin[i]) / direction[i]
            t2 = (aabb_max[i] - origin[i]) / direction[i]
            if t1 > t2: t1, t2 = t2, t1
            tmin = max(tmin, t1)
            tmax = min(tmax, t2)
            if tmin > tmax:
                return None
    return tmin if tmin >= 0 else (tmax if tmax >= 0 else None)


# ===================================================================
# OpenGL Viewport
# ===================================================================

if QOpenGLWidget and HAS_OPENGL:
    class SceneViewport(QOpenGLWidget):
        """OpenGL viewport with 2D/3D grid, scene objects, gizmos, and UE5 camera nav."""

        fps_updated = pyqtSignal(int)
        object_selected = pyqtSignal(object)      # SceneObject or None
        object_dropped = pyqtSignal(str, float, float)  # type, world_x, world_y/z
        object_moved = pyqtSignal()                # after drag completes

        def __init__(self, parent=None):
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

            self._keys = set()
            self._rmb = False
            self._mmb = False
            self._lmb = False
            self._last_mouse = None
            self._drag_object = None
            self._drag_start_pos = None
            self._drag_world_start = None  # world position under mouse at drag start

            self._frame_timer = QTimer(self)
            self._frame_timer.timeout.connect(self._tick)
            self._last_time = time.perf_counter()
            self._frame_count = 0
            self._fps_accum = 0.0
            self._current_fps = 0

            self.grid_size = 1.0
            self.grid_extent = 200
            self.show_grid = True
            self.snap_enabled = False

            self.scene_objects: List[SceneObject] = []
            self._transform_mode = "move"
            self._transform_space = "Global"
            self._hover_gizmo_part = None
            self._active_gizmo_part = None
            self._drag_obj_initial_rot = None
            self._drag_obj_initial_scale = None

        def set_mode(self, mode: str):
            self._mode = mode; self.update()

        def set_transform_mode(self, mode: str):
            self._transform_mode = mode; self.update()

        def set_grid_size(self, size: float):
            self.grid_size = size; self.update()

        def set_snap_enabled(self, enabled: bool):
            self.snap_enabled = enabled; self.update()

        def set_show_grid(self, show: bool):
            self.show_grid = show; self.update()

        def start_render_loop(self):
            self._last_time = time.perf_counter()
            self._frame_timer.start(16)

        def stop_render_loop(self):
            self._frame_timer.stop()

        def _tick(self):
            now = time.perf_counter()
            dt = now - self._last_time; self._last_time = now
            self._frame_count += 1; self._fps_accum += dt
            if self._fps_accum >= 1.0:
                self._current_fps = self._frame_count
                self.fps_updated.emit(self._current_fps)
                self._frame_count = 0; self._fps_accum = 0.0
            if self._mode == "3D" and self._rmb:
                fwd = (1 if Qt.Key.Key_W in self._keys else 0) - (1 if Qt.Key.Key_S in self._keys else 0)
                rgt = (1 if Qt.Key.Key_D in self._keys else 0) - (1 if Qt.Key.Key_A in self._keys else 0)
                upd = (1 if Qt.Key.Key_E in self._keys else 0) - (1 if Qt.Key.Key_Q in self._keys else 0)
                if fwd or rgt or upd:
                    self._cam3d.move(fwd, rgt, upd, dt)
            self.update()

        # ---- OpenGL ----
        def initializeGL(self):
            glClearColor(*BG_COLOR)
            glEnable(GL_DEPTH_TEST); glEnable(GL_BLEND)
            glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
            glEnable(GL_LINE_SMOOTH); glHint(GL_LINE_SMOOTH_HINT, GL_NICEST)
            glEnable(GL_MULTISAMPLE)

        def resizeGL(self, w, h):
            glViewport(0, 0, w, h)

        def paintGL(self):
            glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
            w, h = self.width(), self.height()
            if w < 1 or h < 1: return
            if self._mode == "3D":
                self._cam3d.apply_gl(w / max(h, 1))
                self._draw_grid_3d()
                self._draw_scene_objects_3d()
                self._draw_gizmo_for_selected_3d()
                self._draw_axis_gizmo_3d(w, h)
            elif self._mode == "2D":
                self._cam2d.apply_gl(w, h)
                self._draw_grid_2d()
                self._draw_scene_objects_2d()
                self._draw_gizmo_for_selected_2d()

        # ---- 3D Grid ----
        def _draw_grid_3d(self):
            if not self.show_grid: return
            extent = self.grid_extent; step = self.grid_size
            glDepthMask(GL_FALSE)
            cam_y = abs(self._cam3d.pos[1])
            adaptive_step = step
            if cam_y > 50: adaptive_step = step * 10
            elif cam_y > 20: adaptive_step = step * 5
            elif cam_y > 8: adaptive_step = step * 2
            glLineWidth(1.0); glBegin(GL_LINES)
            for i in range(-extent, extent + 1):
                v = i * adaptive_step
                if i == 0: continue
                glColor4f(*(GRID_MAJOR_COLOR if i % 10 == 0 else GRID_MINOR_COLOR))
                glVertex3f(-extent*adaptive_step, 0, v); glVertex3f(extent*adaptive_step, 0, v)
                glVertex3f(v, 0, -extent*adaptive_step); glVertex3f(v, 0, extent*adaptive_step)
            glEnd()
            half = extent * adaptive_step
            glLineWidth(2.0); glBegin(GL_LINES)
            glColor4f(*AXIS_X_COLOR); glVertex3f(-half,0.001,0); glVertex3f(half,0.001,0)
            glColor4f(*AXIS_Z_COLOR); glVertex3f(0,0.001,-half); glVertex3f(0,0.001,half)
            glEnd()
            glBegin(GL_LINES)
            glColor4f(*AXIS_Y_COLOR); glVertex3f(0,0,0); glVertex3f(0,half*0.1,0)
            glEnd()
            glLineWidth(1.0); glDepthMask(GL_TRUE)

        def _draw_axis_gizmo_3d(self, vp_w, vp_h):
            gs = 60; m = 10
            glMatrixMode(GL_PROJECTION); glPushMatrix(); glLoadIdentity()
            glOrtho(0, vp_w, 0, vp_h, -100, 100)
            glMatrixMode(GL_MODELVIEW); glPushMatrix(); glLoadIdentity()
            cx, cy = m + gs, m + gs; glTranslatef(cx, cy, 0)
            yr, pr = math.radians(self._cam3d.yaw), math.radians(self._cam3d.pitch)
            s = gs * 0.7
            xp = (math.cos(yr)*s, math.sin(pr)*math.sin(yr)*s*(-1))
            yp = (0, math.cos(pr)*s)
            zp = (math.sin(yr)*s, math.sin(pr)*math.cos(yr)*s)
            glDisable(GL_DEPTH_TEST); glLineWidth(2.5)
            glBegin(GL_LINES)
            glColor4f(*AXIS_X_COLOR); glVertex2f(0,0); glVertex2f(xp[0],-xp[1])
            glColor4f(*AXIS_Y_COLOR); glVertex2f(0,0); glVertex2f(yp[0],yp[1])
            glColor4f(*AXIS_Z_COLOR); glVertex2f(0,0); glVertex2f(zp[0],-zp[1])
            glEnd()
            glPointSize(6.0); glBegin(GL_POINTS)
            glColor4f(*AXIS_X_COLOR); glVertex2f(xp[0],-xp[1])
            glColor4f(*AXIS_Y_COLOR); glVertex2f(yp[0],yp[1])
            glColor4f(*AXIS_Z_COLOR); glVertex2f(zp[0],-zp[1])
            glEnd(); glPointSize(1.0)
            glEnable(GL_DEPTH_TEST); glLineWidth(1.0)
            glMatrixMode(GL_PROJECTION); glPopMatrix()
            glMatrixMode(GL_MODELVIEW); glPopMatrix()

        # ---- 2D Grid ----
        def _draw_grid_2d(self):
            if not self.show_grid: return
            zoom = self._cam2d.zoom_level; step = self.grid_size
            if zoom > 500: step = 100
            elif zoom > 100: step = 50
            elif zoom > 50: step = 10
            elif zoom > 20: step = 5
            elif zoom > 5: step = 1
            else: step = 0.5
            cx, cy = self._cam2d.x, self._cam2d.y
            half_w = zoom * (self.width() / max(self.height(), 1)); half_h = zoom
            xs = int((cx-half_w)/step-1)*step; xe = int((cx+half_w)/step+2)*step
            ys = int((cy-half_h)/step-1)*step; ye = int((cy+half_h)/step+2)*step
            glDisable(GL_DEPTH_TEST); glLineWidth(1.0); glBegin(GL_LINES)
            x = xs
            while x <= xe:
                if abs(x) < 1e-6: x += step; continue
                is_major = abs(round(x/(step*10))*(step*10)-x) < 1e-6
                glColor4f(*(GRID_MAJOR_COLOR if is_major else GRID_MINOR_COLOR))
                glVertex2f(x, ys); glVertex2f(x, ye); x += step
            y = ys
            while y <= ye:
                if abs(y) < 1e-6: y += step; continue
                is_major = abs(round(y/(step*10))*(step*10)-y) < 1e-6
                glColor4f(*(GRID_MAJOR_COLOR if is_major else GRID_MINOR_COLOR))
                glVertex2f(xs, y); glVertex2f(xe, y); y += step
            glEnd()
            glLineWidth(2.0); glBegin(GL_LINES)
            glColor4f(*AXIS_X_COLOR); glVertex2f(xs,0); glVertex2f(xe,0)
            glColor4f(*AXIS_Y_COLOR); glVertex2f(0,ys); glVertex2f(0,ye)
            glEnd()
            glPointSize(6.0); glBegin(GL_POINTS)
            glColor4f(*ORIGIN_COLOR); glVertex2f(0,0)
            glEnd(); glPointSize(1.0)
            glLineWidth(1.0); glEnable(GL_DEPTH_TEST)

        # ---- Draw scene objects ----
        def _draw_scene_objects_3d(self):
            for obj in self.scene_objects:
                glPushMatrix()
                glTranslatef(*obj.position)
                glRotatef(obj.rotation[1], 0, 1, 0) # Yaw (Global Up)
                glRotatef(obj.rotation[0], 1, 0, 0) # Pitch
                glRotatef(obj.rotation[2], 0, 0, 1) # Roll
                glScalef(*obj.scale)
                color = tuple(SELECT_COLOR) if obj.selected else tuple(obj.color)
                fill = (color[0]*0.3, color[1]*0.3, color[2]*0.3, 0.3) if obj.selected else OBJECT_FACE_COLOR
                t = obj.obj_type
                if t == 'cube': _draw_wireframe_cube(1,1,1, color, fill)
                elif t == 'sphere': _draw_wireframe_sphere(0.5, color=color)
                elif t == 'cylinder': _draw_wireframe_cylinder(0.5, 1.0, color=color)
                elif t == 'plane': _draw_wireframe_plane(2, 2, color, fill)
                elif t == 'cone': _draw_wireframe_cone(0.5, 1.0, color=color)
                elif t == 'mesh': _draw_wireframe_cube(1,1,1, color, fill)
                glPopMatrix()

        def _draw_scene_objects_2d(self):
            glDisable(GL_DEPTH_TEST)
            for obj in self.scene_objects:
                glPushMatrix()
                glTranslatef(obj.position[0], obj.position[1], 0)
                glRotatef(obj.rotation[2], 0, 0, 1)
                glScalef(obj.scale[0], obj.scale[1], 1)
                color = tuple(SELECT_COLOR) if obj.selected else tuple(obj.color)
                fill = (color[0]*0.3, color[1]*0.3, color[2]*0.3, 0.3) if obj.selected else OBJECT_FACE_COLOR
                t = obj.obj_type
                if t in ('rect', 'sprite', 'mesh'): _draw_2d_rect(1, 1, color, fill)
                elif t == 'circle': _draw_2d_circle(0.5, color=color, fill_color=fill)
                glPopMatrix()
            glEnable(GL_DEPTH_TEST)

        # ---- Gizmos ----
        def _get_gizmo_size_3d(self, obj):
            """Compute gizmo size proportional to screen (constant apparent size)."""
            dist = _length(_sub(tuple(obj.position), tuple(self._cam3d.pos)))
            return max(0.3, dist * 0.08)

        def _get_gizmo_size_2d(self):
            return self._cam2d.zoom_level * 0.15

        def _draw_gizmo_for_selected_3d(self):
            sel = [o for o in self.scene_objects if o.selected]
            if not sel: return
            obj = sel[0]
            glPushMatrix()
            glTranslatef(*obj.position)
            sz = self._get_gizmo_size_3d(obj)
            if self._transform_mode == "move":
                _draw_gizmo_move_3d(sz, self._hover_gizmo_part or self._active_gizmo_part)
            elif self._transform_mode == "rotate":
                _draw_gizmo_rotate_3d(sz, self._hover_gizmo_part or self._active_gizmo_part)
            elif self._transform_mode == "scale":
                _draw_gizmo_scale_3d(sz, self._hover_gizmo_part or self._active_gizmo_part)
            glPopMatrix()

        def _draw_gizmo_for_selected_2d(self):
            sel = [o for o in self.scene_objects if o.selected]
            if not sel: return
            obj = sel[0]
            glPushMatrix()
            glTranslatef(obj.position[0], obj.position[1], 0)
            sz = self._get_gizmo_size_2d()
            hp = self._hover_gizmo_part or self._active_gizmo_part
            if self._transform_mode == "move":
                _draw_gizmo_move_2d(sz, hp)
            elif self._transform_mode == "rotate":
                _draw_gizmo_rotate_2d(sz, hp)
            elif self._transform_mode == "scale":
                _draw_gizmo_scale_2d(sz, hp)
            glPopMatrix()

        # ---- Object picking ----
        def _pick_object_3d(self, mx, my) -> Optional[SceneObject]:
            origin, direction = self._cam3d.screen_to_ray(mx, my, self.width(), self.height())
            best, best_dist = None, 1e30
            for obj in self.scene_objects:
                p, s = obj.position, obj.scale
                half = [s[0]/2, s[1]/2, s[2]/2]
                amin = [p[0]-half[0], p[1]-half[1], p[2]-half[2]]
                amax = [p[0]+half[0], p[1]+half[1], p[2]+half[2]]
                dist = _ray_intersect_aabb(origin, direction, amin, amax)
                if dist is not None and dist < best_dist:
                    best, best_dist = obj, dist
            return best

        def _pick_object_2d(self, mx, my) -> Optional[SceneObject]:
            wx, wy = self._cam2d.screen_to_world(mx, my, self.width(), self.height())
            best = None
            for obj in self.scene_objects:
                p, s = obj.position, obj.scale
                hw, hh = s[0]/2, s[1]/2
                if p[0]-hw <= wx <= p[0]+hw and p[1]-hh <= wy <= p[1]+hh:
                    best = obj
            return best

        # ---- Input ----
        def _pick_gizmo_3d(self, mx, my):
            sel = [o for o in self.scene_objects if o.selected]
            if not sel: return None
            obj = sel[0]
            origin, direction = self._cam3d.screen_to_ray(mx, my, self.width(), self.height())
            sz = self._get_gizmo_size_3d(obj)
            
            # Simple analytical picking for move arrows
            if self._transform_mode == "move":
                axes = [("X", (1,0,0)), ("Y", (0,1,0)), ("Z", (0,0,1))]
                best_part, best_dist = None, 0.15 * sz
                for name, axis_vec in axes:
                    dist, t_ray, t_axis = _dist_line_line(origin, direction, tuple(obj.position), axis_vec)
                    if dist < best_dist and 0 <= t_axis <= sz:
                        best_part = name; best_dist = dist
                if best_part: return best_part
                
                # Planar handles (simple AABB-like checks in local space)
                ps = sz * 0.3
                for part, normal in [("XY", (0,0,1)), ("XZ", (0,1,0)), ("YZ", (1,0,0))]:
                    wp = self._cam3d.ray_plane_intersect(mx, my, self.width(), self.height(), tuple(obj.position), normal)
                    if wp:
                        off = _sub(wp, tuple(obj.position))
                        if part == "XY" and 0 <= off[0] <= ps and 0 <= off[1] <= ps: return "XY"
                        if part == "XZ" and 0 <= off[0] <= ps and 0 <= off[2] <= ps: return "XZ"
                        if part == "YZ" and 0 <= off[1] <= ps and 0 <= off[2] <= ps: return "YZ"
            
            elif self._transform_mode == "rotate":
                # Screen-space Rotate picking for "thick" hit detection
                best_axis = None; min_dist = 999.0
                center = tuple(obj.position)
                r_orbit = sz * 0.9
                w, h = self.width(), self.height()
                
                # Transform click point into local space if in Local mode
                l_mx, l_my = mx, my
                if self._transform_space == "Local":
                    # For simplicity in screen-space picking, we don't transform l_mx
                    # but we sample world points in LOCAL space below
                    pass

                for axis in ["X", "Y", "Z"]:
                    # Sample 16 points along the ring (aligned to Local or World)
                    for i in range(16):
                        ang = math.radians(i * 360 / 16)
                        if axis == "X": p = (0, math.cos(ang)*r_orbit, math.sin(ang)*r_orbit)
                        elif axis == "Y": p = (math.cos(ang)*r_orbit, 0, math.sin(ang)*r_orbit)
                        else: p = (math.cos(ang)*r_orbit, math.sin(ang)*r_orbit, 0)
                        
                        if self._transform_space == "Local":
                            # Transform local point p to world space
                            M = _euler_to_matrix(*obj.rotation)
                            p_rot = (M[0][0]*p[0] + M[0][1]*p[1] + M[0][2]*p[2],
                                     M[1][0]*p[0] + M[1][1]*p[1] + M[1][2]*p[2],
                                     M[2][0]*p[0] + M[2][1]*p[1] + M[2][2]*p[2])
                            p_world = _add(center, p_rot)
                        else:
                            p_world = _add(center, p)
                        
                        p_screen = self._cam3d.world_to_screen(p_world, w, h)
                        if p_screen:
                            d = math.sqrt((p_screen[0] - mx)**2 + (p_screen[1] - my)**2)
                            if d < 18: # 18-pixel thick hitbox
                                if d < min_dist:
                                    min_dist = d; best_axis = axis
                if best_axis: return best_axis
            
            elif self._transform_mode == "scale":
                # Scale boxes at tips
                axes = [("X", (1,0,0)), ("Y", (0,1,0)), ("Z", (0,0,1))]
                best_part, best_dist = None, 1e30
                box_sz = sz * 0.18
                for name, axis_vec in axes:
                    tip = _add(tuple(obj.position), _scale_vec(axis_vec, sz))
                    amin = [tip[i] - box_sz/2 for i in range(3)]
                    amax = [tip[i] + box_sz/2 for i in range(3)]
                    dist = _ray_intersect_aabb(origin, direction, amin, amax)
                    if dist is not None and dist < best_dist:
                        best_part = name; best_dist = dist
                if best_part: return best_part
                
                # Center box
                c_sz = sz * 0.2
                c_min = [obj.position[i] - c_sz/2 for i in range(3)]
                c_max = [obj.position[i] + c_sz/2 for i in range(3)]
                if _ray_intersect_aabb(origin, direction, c_min, c_max) is not None:
                    return "Uniform"
            return None

        def _pick_gizmo_2d(self, mx, my):
            sel = [o for o in self.scene_objects if o.selected]
            if not sel: return None
            obj = sel[0]
            wx, wy = self._cam2d.screen_to_world(mx, my, self.width(), self.height())
            sz = self._get_gizmo_size_2d()
            
            # Hitbox sensitivity (scaled by current zoom/size)
            hit_sz = sz * 0.15

            def dist_to_segment(px, py, x1, y1, x2, y2):
                dx, dy = x2-x1, y2-y1
                if dx*dx + dy*dy < 1e-9: return math.sqrt((px-x1)**2 + (py-y1)**2)
                t = ((px-x1)*dx + (py-y1)*dy) / (dx*dx + dy*dy)
                t = max(0, min(1, t))
                return math.sqrt((px-(x1+t*dx))**2 + (py-(y1+t*dy))**2)

            # Center/Uniform
            if abs(wx - obj.position[0]) < hit_sz and abs(wy - obj.position[1]) < hit_sz:
                if self._transform_mode in ("move", "scale"): return "XY" if self._transform_mode=="move" else "Uniform"

            if self._transform_mode == "move":
                # Check X axis
                if dist_to_segment(wx, wy, obj.position[0], obj.position[1], obj.position[0]+sz, obj.position[1]) < hit_sz: return "X"
                # Check Y axis
                if dist_to_segment(wx, wy, obj.position[0], obj.position[1], obj.position[0], obj.position[1]+sz) < hit_sz: return "Y"

            elif self._transform_mode == "rotate":
                r = sz * 0.85
                dist_to_center = math.sqrt((wx - obj.position[0])**2 + (wy - obj.position[1])**2)
                if abs(dist_to_center - r) < hit_sz: return "Rotate"

            elif self._transform_mode == "scale":
                for part, cp in [("X", (obj.position[0]+sz, obj.position[1])), ("Y", (obj.position[0], obj.position[1]+sz))]:
                    if abs(wx - cp[0]) < hit_sz and abs(wy - cp[1]) < hit_sz: return part

            return None

        def mousePressEvent(self, event: QMouseEvent):
            btn = event.button()
            mx, my = event.pos().x(), event.pos().y()
            if btn == Qt.MouseButton.LeftButton:
                self._lmb = True
                # Check gizmo first
                if self._mode == "3D":
                    self._active_gizmo_part = self._pick_gizmo_3d(mx, my)
                else:
                    self._active_gizmo_part = self._pick_gizmo_2d(mx, my)

                if self._active_gizmo_part:
                    sel = [o for o in self.scene_objects if o.selected][0]
                    self._drag_object = sel
                    self._drag_start_pos = list(sel.position)
                    self._drag_obj_initial_rot = list(sel.rotation)
                    self._drag_obj_initial_scale = list(sel.scale)
                    
                    # Store world start for movement/rotation/scaling math
                    if self._mode == "3D":
                        self._init_drag_3d(mx, my, sel)
                    else:
                        self._init_drag_2d(mx, my, sel)
                    return

                if self._mode == "3D": picked = self._pick_object_3d(mx, my)
                elif self._mode == "2D": picked = self._pick_object_2d(mx, my)
                else: picked = None
                
                for o in self.scene_objects: o.selected = False
                if picked:
                    picked.selected = True
                    self._drag_object = picked
                    self._drag_start_pos = list(picked.position)
                    if self._mode == "3D":
                        self._drag_world_start = self._cam3d.ray_plane_intersect(mx, my, self.width(), self.height(), tuple(picked.position), (0, 1, 0))
                    elif self._mode == "2D":
                        wx, wy = self._cam2d.screen_to_world(mx, my, self.width(), self.height())
                        self._drag_world_start = (wx, wy)
                else:
                    self._drag_object = None; self._drag_world_start = None
                self.object_selected.emit(picked)
                self.update() # Ensure immediate visual update
            elif btn == Qt.MouseButton.RightButton:
                self._rmb = True; self.setCursor(Qt.CursorShape.BlankCursor)
            elif btn == Qt.MouseButton.MiddleButton:
                self._mmb = True; self.setCursor(Qt.CursorShape.ClosedHandCursor)
            self._last_mouse = event.pos()
            event.accept()

        def _init_drag_3d(self, mx, my, sel):
            if self._transform_mode == "move":
                normal = (0,1,0) if self._active_gizmo_part in ("X","Z","XZ") else (0,0,1)
                if self._active_gizmo_part == "YZ": normal = (1,0,0)
                self._drag_world_start = self._cam3d.ray_plane_intersect(mx, my, self.width(), self.height(), tuple(sel.position), normal)
            elif self._transform_mode == "rotate":
                self._drag_start_mouse = (mx, my)
                sz = self._get_gizmo_size_3d(sel)
                # Compute screen-space tangent of the selected ring
                # Project two points along the ring tangent to screen
                c = tuple(sel.position)
                axis_vec = {"X":(1,0,0), "Y":(0,1,0), "Z":(0,0,1)}.get(self._active_gizmo_part)
                
                # If local space, transform axis
                if self._transform_space == "Local":
                    M = _euler_to_matrix(*sel.rotation)
                    axis_vec = _mat_vec_mul(M, axis_vec)
                
                # Find a point on the ring near the mouse
                wp = self._cam3d.ray_plane_intersect(mx, my, self.width(), self.height(), c, axis_vec)
                if wp:
                    rad_v = _sub(wp, c)
                    tan_v = _normalize((axis_vec[1]*rad_v[2] - axis_vec[2]*rad_v[1],
                                      axis_vec[2]*rad_v[0] - axis_vec[0]*rad_v[2],
                                      axis_vec[0]*rad_v[1] - axis_vec[1]*rad_v[0]))
                    p1 = self._cam3d.world_to_screen(wp, self.width(), self.height())
                    p2 = self._cam3d.world_to_screen(_add(wp, _scale_vec(tan_v, 0.1)), self.width(), self.height())
                    if p1 and p2:
                        self._drag_tangent = _normalize((p2[0]-p1[0], p2[1]-p1[1]))
                    else:
                        self._drag_tangent = (1, 0)
                else:
                    self._drag_tangent = (1, 0)
            elif self._transform_mode == "scale":
                f = self._cam3d.front; normal = _normalize((f[0], 0, f[2]))
                self._drag_world_start = self._cam3d.ray_plane_intersect(mx, my, self.width(), self.height(), tuple(sel.position), normal)
                if self._drag_world_start:
                    self._drag_initial_dist = _length(_sub(self._drag_world_start, tuple(sel.position)))

        def _init_drag_2d(self, mx, my, sel):
            wx, wy = self._cam2d.screen_to_world(mx, my, self.width(), self.height())
            self._drag_world_start = (wx, wy)
            self._drag_initial_dist = math.sqrt((wx - sel.position[0])**2 + (wy - sel.position[1])**2)

        def mouseReleaseEvent(self, event: QMouseEvent):
            btn = event.button()
            if btn == Qt.MouseButton.LeftButton:
                if self._lmb and self._drag_object:
                    self.object_moved.emit()
                self._lmb = False; self._drag_object = None; self._drag_world_start = None
                self._active_gizmo_part = None
            elif btn == Qt.MouseButton.RightButton:
                if self._rmb:
                    # If it was a short click, could show menu, but we use contextMenuEvent
                    pass
                self._rmb = False; self.setCursor(Qt.CursorShape.ArrowCursor)
            elif btn == Qt.MouseButton.MiddleButton:
                self._mmb = False; self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()

        def mouseMoveEvent(self, event: QMouseEvent):
            if self._last_mouse is None:
                self._last_mouse = event.pos(); return
            dx = event.pos().x() - self._last_mouse.x()
            dy = event.pos().y() - self._last_mouse.y()
            self._last_mouse = event.pos()

            if self._mode == "3D":
                if self._rmb:
                    self._cam3d.rotate(dx, dy)
                elif self._mmb:
                    r, u = self._cam3d.right, self._cam3d.up
                    spd = self._cam3d.speed * 0.01
                    self._cam3d.pos[0] -= (r[0]*dx + u[0]*dy)*spd
                    self._cam3d.pos[1] -= (r[1]*dx + u[1]*dy)*spd
                    self._cam3d.pos[2] -= (r[2]*dx + u[2]*dy)*spd
                elif self._lmb and self._drag_object and self._transform_mode == "move":
                    mx, my = event.pos().x(), event.pos().y()
                    # Determine plane for intersection based on active part
                    normal = (0,1,0)
                    if self._active_gizmo_part == "Y": 
                        # For vertical axis, use plane facing camera
                        f = self._cam3d.front
                        normal = _normalize((f[0], 0, f[2])) 
                    elif self._active_gizmo_part == "XY": normal = (0,0,1)
                    elif self._active_gizmo_part == "YZ": normal = (1,0,0)
                    
                    wp = self._cam3d.ray_plane_intersect(mx, my, self.width(), self.height(), tuple(self._drag_start_pos), normal)
                    if wp and self._drag_world_start:
                        offset = _sub(wp, self._drag_world_start)
                        for i, axis in enumerate(["X", "Y", "Z"]):
                            if self._active_gizmo_part == axis:
                                val = self._drag_start_pos[i] + offset[i]
                                if self.snap_enabled: val = round(val / self.grid_size) * self.grid_size
                                self._drag_object.position[i] = val
                        
                        if self._active_gizmo_part == "XY":
                            for i in range(2):
                                val = self._drag_start_pos[i] + offset[i]
                                if self.snap_enabled: val = round(val / self.grid_size) * self.grid_size
                                self._drag_object.position[i] = val
                        elif self._active_gizmo_part == "XZ":
                            for i in (0, 2):
                                val = self._drag_start_pos[i] + offset[i]
                                if self.snap_enabled: val = round(val / self.grid_size) * self.grid_size
                                self._drag_object.position[i] = val
                        elif self._active_gizmo_part == "YZ":
                            for i in (1, 2):
                                val = self._drag_start_pos[i] + offset[i]
                                if self.snap_enabled: val = round(val / self.grid_size) * self.grid_size
                                self._drag_object.position[i] = val
                        elif not self._active_gizmo_part:
                            for i in (0, 2):
                                val = self._drag_start_pos[i] + offset[i]
                                if self.snap_enabled: val = round(val / self.grid_size) * self.grid_size
                                self._drag_object.position[i] = val
                        self.object_moved.emit() # Update props panel
                
                elif self._lmb and self._drag_object and self._transform_mode == "rotate":
                    if self._active_gizmo_part and hasattr(self, "_drag_tangent"):
                        idx = {"X":0, "Y":1, "Z":2}.get(self._active_gizmo_part)
                        
                        # Project mouse movement onto the screen-space tangent
                        m_dx = event.pos().x() - self._drag_start_mouse[0]
                        m_dy = event.pos().y() - self._drag_start_mouse[1]
                        
                        dist_along_tangent = m_dx * self._drag_tangent[0] + m_dy * self._drag_tangent[1]
                        # 0.5 degrees per pixel
                        angle_delta = dist_along_tangent * 0.5
                        if self.snap_enabled: angle_delta = round(angle_delta / 15.0) * 15.0
                        
                        # Apply Transformation Space Logic
                        axis_vec = {"X":(1,0,0), "Y":(0,1,0), "Z":(0,0,1)}.get(self._active_gizmo_part)
                        delta_mat = _axis_angle_to_matrix(axis_vec, angle_delta)
                        start_mat = _euler_to_matrix(*self._drag_obj_initial_rot)
                        
                        if self._transform_space == "Local":
                            # Local rotation: Initial * Delta
                            new_mat = _mat_mul_3x3(start_mat, delta_mat)
                        else:
                            # World rotation: Delta * Initial
                            new_mat = _mat_mul_3x3(delta_mat, start_mat)
                            
                        self._drag_object.rotation = _matrix_to_euler(new_mat)
                        self.object_moved.emit()
                    else:
                        # Fallback for old simple rotate or if tangent missing
                        self._drag_object.rotation[1] += dx * 0.5
                        if self.snap_enabled:
                            self._drag_object.rotation[1] = round(self._drag_object.rotation[1] / 15.0) * 15.0
                        self.object_moved.emit()
                        
                elif self._lmb and self._drag_object and self._transform_mode == "scale":
                    # Use world-distance ratio for scaling
                    f = self._cam3d.front; normal = _normalize((f[0], 0, f[2]))
                    wp = self._cam3d.ray_plane_intersect(event.pos().x(), event.pos().y(), self.width(), self.height(), tuple(self._drag_object.position), normal)
                    if wp and hasattr(self, "_drag_initial_dist") and self._drag_initial_dist > 0.01:
                        v = _sub(wp, tuple(self._drag_object.position))
                        ratio = _length(v) / self._drag_initial_dist
                        if self._active_gizmo_part in ("X","Y","Z"):
                            idx = {"X":0, "Y":1, "Z":2}.get(self._active_gizmo_part)
                            new_val = self._drag_obj_initial_scale[idx] * ratio
                            if self.snap_enabled: new_val = max(0.01, round(new_val / 0.1) * 0.1)
                            self._drag_object.scale[idx] = max(0.01, new_val)
                        else:
                            # Uniform
                            for i in range(3):
                                new_val = self._drag_obj_initial_scale[i] * ratio
                                if self.snap_enabled: new_val = max(0.01, round(new_val / 0.1) * 0.1)
                                self._drag_object.scale[i] = max(0.01, new_val)
                        self.object_moved.emit()
                    else:
                        # Fallback for scale if plane intersection fails
                        factor = 1.0 + dx * 0.02
                        for i in range(3):
                            self._drag_object.scale[i] *= factor
                        self.object_moved.emit()

                elif not self._lmb and self._mode == "3D":
                    # Update hover
                    self._hover_gizmo_part = self._pick_gizmo_3d(event.pos().x(), event.pos().y())
            elif self._mode == "2D":
                if self._mmb or self._rmb:
                    self._cam2d.pan(dx, dy, self.width(), self.height())
                elif self._lmb and self._drag_object:
                    mx, my = event.pos().x(), event.pos().y()
                    wx, wy = self._cam2d.screen_to_world(mx, my, self.width(), self.height())
                    
                    if self._transform_mode == "move":
                        if self._drag_world_start:
                            ox, oy = wx - self._drag_world_start[0], wy - self._drag_world_start[1]
                            
                            if self._active_gizmo_part in ("X", "Y") and self._transform_space == "Local":
                                # Project onto local axes
                                rad = math.radians(self._drag_object.rotation[2])
                                lx = ox*math.cos(rad) + oy*math.sin(rad)
                                ly = -ox*math.sin(rad) + oy*math.cos(rad)
                                if self._active_gizmo_part == "X": ox, oy = lx*math.cos(rad), lx*math.sin(rad)
                                else: ox, oy = -ly*math.sin(rad), ly*math.cos(rad)
                            elif self._active_gizmo_part == "X": oy = 0
                            elif self._active_gizmo_part == "Y": ox = 0
                            
                            valx = self._drag_start_pos[0] + ox
                            valy = self._drag_start_pos[1] + oy
                            if self.snap_enabled:
                                valx = round(valx / self.grid_size) * self.grid_size
                                valy = round(valy / self.grid_size) * self.grid_size
                            self._drag_object.position[0] = valx
                            self._drag_object.position[1] = valy
                            
                    elif self._transform_mode == "rotate":
                        cur_ang = math.atan2(wy - self._drag_object.position[1], wx - self._drag_object.position[0])
                        start_ang = math.atan2(self._drag_world_start[1] - self._drag_object.position[1], 
                                              self._drag_world_start[0] - self._drag_object.position[0])
                        diff = math.degrees(cur_ang - start_ang)
                        new_rot = self._drag_obj_initial_rot[2] + diff
                        if self.snap_enabled: new_rot = round(new_rot / 15.0) * 15.0
                        self._drag_object.rotation[2] = new_rot
                        
                    elif self._transform_mode == "scale":
                        if self._drag_initial_dist > 0.01:
                            dist = math.sqrt((wx - self._drag_object.position[0])**2 + (wy - self._drag_object.position[1])**2)
                            ratio = dist / self._drag_initial_dist
                            if self._active_gizmo_part == "X":
                                self._drag_object.scale[0] = max(0.01, self._drag_obj_initial_scale[0] * ratio)
                            elif self._active_gizmo_part == "Y":
                                self._drag_object.scale[1] = max(0.01, self._drag_obj_initial_scale[1] * ratio)
                            else:
                                for i in range(2): self._drag_object.scale[i] = max(0.01, self._drag_obj_initial_scale[i] * ratio)
                    self.object_moved.emit()
                else:
                    self._hover_gizmo_part = self._pick_gizmo_2d(event.pos().x(), event.pos().y())
            self.update()
            event.accept()
            event.accept()

        def wheelEvent(self, event: QWheelEvent):
            delta = event.angleDelta().y()
            if self._mode == "3D":
                f = self._cam3d.front; spd = self._cam3d.speed * 0.3
                d = 1 if delta > 0 else -1
                for i in range(3): self._cam3d.pos[i] += f[i]*spd*d
                new_zoom = max(0.1, min(10.0, self._cam2d.zoom - delta * 0.001))
                self._cam2d.zoom = new_zoom
            self.update()
            event.accept()

        def keyPressEvent(self, event: QKeyEvent):
            self._keys.add(event.key())
            if event.key() == Qt.Key.Key_Shift: self._cam3d.speed = 30.0
            if event.key() == Qt.Key.Key_Delete:
                self.scene_objects = [o for o in self.scene_objects if not o.selected]
                self.object_selected.emit(None)
            event.accept()

        def keyReleaseEvent(self, event: QKeyEvent):
            self._keys.discard(event.key())
            if event.key() == Qt.Key.Key_Shift: self._cam3d.speed = 10.0
            event.accept()

        def focusOutEvent(self, event):
            self._keys.clear(); self._rmb = False; self._mmb = False; self._lmb = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
            super().focusOutEvent(event)

        def contextMenuEvent(self, event):
            mx, my = event.pos().x(), event.pos().y()
            picked = self._pick_object_3d(mx, my) if self._mode == "3D" else self._pick_object_2d(mx, my)
            
            if picked:
                # Select the object if not already selected
                if not picked.selected:
                    for o in self.scene_objects: o.selected = False
                    picked.selected = True
                    self.object_selected.emit(picked)
                
                menu = QMenu(self)
                menu.setStyleSheet("""
                    QMenu { background: #2a2a2a; color: #e0e0e0; border: 1px solid #555; }
                    QMenu::item { padding: 6px 20px; }
                    QMenu::item:selected { background: #4fc3f7; color: #1a1a1a; }
                """)
                del_act = menu.addAction("Delete Object")
                ren_act = menu.addAction("Rename")
                action = menu.exec(event.globalPos())
                
                if action == del_act:
                    # Notify parent to delete
                    # We can directly modify it here and update outliner via signal if needed
                    # but easiest is to use the standard path
                    obj_id = picked.id
                    parent = self.parentWidget()
                    while parent and not hasattr(parent, '_on_outliner_action'):
                        parent = parent.parentWidget()
                    if parent:
                        parent._on_outliner_action(f"delete:{obj_id}")
                elif action == ren_act:
                    obj_id = picked.id
                    parent = self.parentWidget()
                    while parent and not hasattr(parent, '_on_outliner_action'):
                        parent = parent.parentWidget()
                    if parent:
                        parent._on_outliner_action(f"rename:{obj_id}")
            else:
                # Background context menu? (Add primitives at cursor?)
                pass

        # ---- Drag and drop from explorer ----
        def dragEnterEvent(self, event):
            if event.mimeData().hasText(): event.acceptProposedAction()

        def dragMoveEvent(self, event):
            event.acceptProposedAction()

        def dropEvent(self, event):
            obj_type = event.mimeData().text()
            mx, my = event.position().x(), event.position().y()
            if self._mode == "3D":
                origin, direction = self._cam3d.screen_to_ray(int(mx), int(my), self.width(), self.height())
                if abs(direction[1]) > 1e-9:
                    t = -origin[1] / direction[1]
                    if t > 0:
                        wx = origin[0] + direction[0]*t; wz = origin[2] + direction[2]*t
                        self.object_dropped.emit(obj_type, wx, wz)
                    else: self.object_dropped.emit(obj_type, 0, 0)
                else: self.object_dropped.emit(obj_type, 0, 0)
            elif self._mode == "2D":
                wx, wy = self._cam2d.screen_to_world(int(mx), int(my), self.width(), self.height())
                self.object_dropped.emit(obj_type, wx, wy)
            event.acceptProposedAction()

else:
    class SceneViewport(QWidget):
        fps_updated = pyqtSignal(int)
        object_selected = pyqtSignal(object)
        object_dropped = pyqtSignal(str, float, float)
        object_moved = pyqtSignal()
        def __init__(self, parent=None):
            super().__init__(parent)
            self._mode = "3D"; self.show_grid = True; self.snap_enabled = False
            self.grid_size = 1.0; self.scene_objects = []; self._transform_mode = "move"
        def set_mode(self, m): self._mode = m; self.update()
        def start_render_loop(self): pass
        def stop_render_loop(self): pass
        def paintEvent(self, event):
            p = QPainter(self); p.fillRect(self.rect(), QColor("#1a1a1a"))
            p.setPen(QColor("#888")); p.setFont(QFont("Segoe UI",14))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                       "OpenGL not available.\npip install PyOpenGL"); p.end()


# ===================================================================
# Object Properties Panel
# ===================================================================

class ObjectPropertiesPanel(QWidget):
    """Shows position/rotation/scale spinboxes for the selected object."""

    property_changed = pyqtSignal()   # emitted when user edits a value

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: #252526;")
        self._current_object = None
        self._updating = False  # guard against feedback loops

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4,4,4,4)
        layout.setSpacing(4)

        # Title
        self._title = QLabel("  No Selection")
        self._title.setFixedHeight(24)
        self._title.setStyleSheet("color: #888; font-size: 11px; font-weight: bold;")
        layout.addWidget(self._title)

        # Position
        pos_group = QGroupBox("Position")
        pos_group.setStyleSheet(PROPS_SS)
        pg = QGridLayout(pos_group)
        pg.setContentsMargins(8,6,8,6); pg.setSpacing(4)
        self._pos_spins = []
        for i, axis in enumerate(["X", "Y", "Z"]):
            lbl = QLabel(axis)
            lbl.setStyleSheet(f"color: {['#e55', '#5e5', '#55e'][i]}; font-weight: bold; font-size: 11px;")
            pg.addWidget(lbl, 0, i*2)
            spin = QDoubleSpinBox()
            spin.setRange(-9999, 9999); spin.setDecimals(2); spin.setSingleStep(0.1)
            spin.setStyleSheet(SPIN_SS); spin.setFixedWidth(70)
            spin.valueChanged.connect(self._on_pos_changed)
            pg.addWidget(spin, 0, i*2+1)
            self._pos_spins.append(spin)
        layout.addWidget(pos_group)

        # Rotation
        rot_group = QGroupBox("Rotation")
        rot_group.setStyleSheet(PROPS_SS)
        rg = QGridLayout(rot_group)
        rg.setContentsMargins(8,6,8,6); rg.setSpacing(4)
        self._rot_spins = []
        for i, axis in enumerate(["X", "Y", "Z"]):
            lbl = QLabel(axis)
            lbl.setStyleSheet(f"color: {['#e55', '#5e5', '#55e'][i]}; font-weight: bold; font-size: 11px;")
            rg.addWidget(lbl, 0, i*2)
            spin = QDoubleSpinBox()
            spin.setRange(-360, 360); spin.setDecimals(1); spin.setSingleStep(1.0)
            spin.setStyleSheet(SPIN_SS); spin.setFixedWidth(70)
            spin.valueChanged.connect(self._on_rot_changed)
            rg.addWidget(spin, 0, i*2+1)
            self._rot_spins.append(spin)
        layout.addWidget(rot_group)

        # Scale
        scale_group = QGroupBox("Scale")
        scale_group.setStyleSheet(PROPS_SS)
        sg = QGridLayout(scale_group)
        sg.setContentsMargins(8,6,8,6); sg.setSpacing(4)
        self._scale_spins = []
        for i, axis in enumerate(["X", "Y", "Z"]):
            lbl = QLabel(axis)
            lbl.setStyleSheet(f"color: {['#e55', '#5e5', '#55e'][i]}; font-weight: bold; font-size: 11px;")
            sg.addWidget(lbl, 0, i*2)
            spin = QDoubleSpinBox()
            spin.setRange(0.01, 999); spin.setDecimals(2); spin.setSingleStep(0.1); spin.setValue(1.0)
            spin.setStyleSheet(SPIN_SS); spin.setFixedWidth(70)
            spin.valueChanged.connect(self._on_scale_changed)
            sg.addWidget(spin, 0, i*2+1)
            self._scale_spins.append(spin)
        layout.addWidget(scale_group)

        layout.addStretch()

    def set_object(self, obj: Optional[SceneObject]):
        """Set the selected object to display in the panel."""
        self._current_object = obj
        if obj:
            self._title.setText(f"  {obj.name}  ({obj.obj_type})")
            self._title.setStyleSheet("color: #4fc3f7; font-size: 11px; font-weight: bold;")
            self._sync_from_object()
        else:
            self._title.setText("  No Selection")
            self._title.setStyleSheet("color: #888; font-size: 11px; font-weight: bold;")
            self._clear_spins()

    def _sync_from_object(self):
        """Push object values into spinboxes without triggering change signals."""
        if not self._current_object: return
        self._updating = True
        obj = self._current_object
        for i in range(3):
            self._pos_spins[i].setValue(obj.position[i])
            self._rot_spins[i].setValue(obj.rotation[i])
            self._scale_spins[i].setValue(obj.scale[i])
        self._updating = False

    def refresh_from_object(self):
        """Re-sync from object (called after drag moves etc.)."""
        self._sync_from_object()

    def _clear_spins(self):
        self._updating = True
        for s in self._pos_spins + self._rot_spins + self._scale_spins:
            s.setValue(0)
        self._updating = False

    def _on_pos_changed(self):
        if self._updating or not self._current_object: return
        for i in range(3):
            self._current_object.position[i] = self._pos_spins[i].value()
        self.property_changed.emit()

    def _on_rot_changed(self):
        if self._updating or not self._current_object: return
        for i in range(3):
            self._current_object.rotation[i] = self._rot_spins[i].value()
        self.property_changed.emit()

    def _on_scale_changed(self):
        if self._updating or not self._current_object: return
        for i in range(3):
            self._current_object.scale[i] = self._scale_spins[i].value()
        self.property_changed.emit()


# ===================================================================
# Scene Explorer Panel
# ===================================================================

class _CollapsibleSection(QWidget):
    """Collapsible section matching Logic tab explorer style."""
    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.is_collapsed = False
        self._title = title
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0,0,0,0); layout.setSpacing(0)
        self.header = QPushButton(f" v  {title}")
        self.header.setStyleSheet(SECTION_HEADER_SS)
        self.header.clicked.connect(self.toggle)
        layout.addWidget(self.header)
        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(0,0,0,0); self.content_layout.setSpacing(0)
        layout.addWidget(self.content)

    def toggle(self):
        self.is_collapsed = not self.is_collapsed
        self.content.setVisible(not self.is_collapsed)
        arrow = ">" if self.is_collapsed else "v"
        self.header.setText(f" {arrow}  {self._title}")


class SceneExplorerPanel(QWidget):
    """Left-side explorer panel for the Viewport tab."""

    primitive_dragged = pyqtSignal(str)
    object_select_requested = pyqtSignal(str)

    ASSET_3D_EXTS = {'.fbx', '.obj', '.gltf', '.glb', '.dae', '.stl', '.ply'}
    ASSET_2D_EXTS = {'.png', '.jpg', '.jpeg', '.webp', '.gif', '.svg', '.bmp', '.tga'}
    ALL_ASSET_EXTS = ASSET_3D_EXTS | ASSET_2D_EXTS
    # Folders and extensions to skip entirely
    SKIP_DIRS = {'__pycache__', 'node_modules', '.git', '.gemini', '.vscode', '.idea', 'venv', 'env'}
    SKIP_EXTS = {'.py', '.pyc', '.pyo', '.md', '.txt', '.json', '.logic', '.anim', '.ui', '.cfg', '.ini', '.yml', '.yaml', '.toml', '.lock'}

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ExplorerPanel")
        self.setMinimumWidth(200)
        self.setStyleSheet(PANEL_SS)
        self._mode = "3D"
        self._workspace_root = None

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0,0,0,0); main_layout.setSpacing(0)

        # Title bar
        title = QLabel("  SCENE EXPLORER")
        title.setFixedHeight(28)
        title.setStyleSheet("background: #252526; color: #888; font-size: 11px; font-weight: bold; border-bottom: 1px solid #3c3c3c;")
        main_layout.addWidget(title)

        # Vertical splitter for explorer sections above and properties below
        self._panel_splitter = QSplitter(Qt.Orientation.Vertical, self)
        self._panel_splitter.setStyleSheet("QSplitter::handle { background: #3c3c3c; height: 2px; }")
        main_layout.addWidget(self._panel_splitter, 1)

        # Upper section: scroll area with primitives, assets, outliner
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: #252526; }")
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(0,0,0,0); scroll_layout.setSpacing(0)

        # ---- Primitives section ----
        self._primitives_section = _CollapsibleSection("PRIMITIVES")
        self.primitives_list = QListWidget()
        self.primitives_list.setStyleSheet(LIST_SS)
        self.primitives_list.setDragEnabled(True)
        self.primitives_list.setDefaultDropAction(Qt.DropAction.CopyAction)
        self.primitives_list.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        self.primitives_list.setMaximumHeight(140)
        self._primitives_section.content_layout.addWidget(self.primitives_list)
        scroll_layout.addWidget(self._primitives_section)
        self._populate_primitives()
        self.primitives_list.startDrag = self._start_primitive_drag

        # ---- Project Assets section ----
        self._assets_section = _CollapsibleSection("PROJECT FILES")
        self.assets_tree = QTreeWidget()
        self.assets_tree.setHeaderHidden(True)
        self.assets_tree.setStyleSheet(TREE_SS)
        self.assets_tree.setDragEnabled(True)
        self.assets_tree.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        self.assets_tree.setMinimumHeight(150)
        self._assets_section.content_layout.addWidget(self.assets_tree)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.setStyleSheet("""
            QPushButton { background: #333; color: #aaa; border: 1px solid #444;
                         border-radius: 3px; padding: 3px; font-size: 10px; margin: 2px 4px; }
            QPushButton:hover { background: #444; color: #fff; }
        """)
        refresh_btn.clicked.connect(self.refresh_assets)
        self._assets_section.content_layout.addWidget(refresh_btn)
        scroll_layout.addWidget(self._assets_section)
        self.assets_tree.startDrag = self._start_asset_drag

        # ---- Outliner section ----
        self._outliner_section = _CollapsibleSection("OUTLINER")
        self.outliner_list = QListWidget()
        self.outliner_list.setStyleSheet(LIST_SS)
        self.outliner_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.outliner_list.customContextMenuRequested.connect(self._outliner_context_menu)
        self.outliner_list.currentRowChanged.connect(self._on_outliner_select)
        self.outliner_list.itemDoubleClicked.connect(self._on_outliner_rename)
        self._outliner_section.content_layout.addWidget(self.outliner_list)
        scroll_layout.addWidget(self._outliner_section)

        scroll_layout.addStretch()
        scroll.setWidget(scroll_content)
        self._panel_splitter.addWidget(scroll)

        # Lower section: Properties panel
        self.properties = ObjectPropertiesPanel(self)
        self._panel_splitter.addWidget(self.properties)

        self._panel_splitter.setSizes([400, 250])

    def set_workspace_root(self, path):
        self._workspace_root = Path(path) if path else None
        self.refresh_assets()

    def set_mode(self, mode):
        self._mode = mode
        self._populate_primitives()
        self.refresh_assets()

    def _populate_primitives(self):
        self.primitives_list.clear()
        if self._mode == "3D":
            items = [("Cube","cube"),("Sphere","sphere"),("Cylinder","cylinder"),("Plane","plane"),("Cone","cone")]
        elif self._mode == "2D":
            items = [("Rectangle","rect"),("Circle","circle"),("Sprite","sprite")]
        else:
            items = []
        for display_name, type_name in items:
            item = QListWidgetItem(f"  {display_name}")
            item.setData(Qt.ItemDataRole.UserRole, type_name)
            item.setToolTip(f"Drag onto viewport to create a {display_name}")
            self.primitives_list.addItem(item)

    def _start_primitive_drag(self, supported_actions):
        item = self.primitives_list.currentItem()
        if not item: return
        drag = QDrag(self.primitives_list)
        mime = QMimeData()
        mime.setText(item.data(Qt.ItemDataRole.UserRole))
        drag.setMimeData(mime)
        px = QPixmap(100, 24); px.fill(QColor("#333"))
        p = QPainter(px)
        p.setPen(QColor("#4fc3f7")); p.setFont(QFont("Segoe UI", 10))
        p.drawText(px.rect(), Qt.AlignmentFlag.AlignCenter, item.text().strip()); p.end()
        drag.setPixmap(px)
        drag.exec(Qt.DropAction.CopyAction)

    def _start_asset_drag(self, supported_actions):
        item = self.assets_tree.currentItem()
        if not item: return
        file_path = item.data(0, Qt.ItemDataRole.UserRole)
        if not file_path: return
        drag = QDrag(self.assets_tree)
        mime = QMimeData()
        mime.setText(f"file:{file_path}")
        drag.setMimeData(mime)
        px = QPixmap(140, 24); px.fill(QColor("#333"))
        p = QPainter(px)
        p.setPen(QColor("#4fc3f7")); p.setFont(QFont("Segoe UI", 9))
        p.drawText(px.rect(), Qt.AlignmentFlag.AlignCenter, Path(file_path).name); p.end()
        drag.setPixmap(px)
        drag.exec(Qt.DropAction.CopyAction)

    def refresh_assets(self):
        """Build a full project folder tree, showing ALL folders but only
        asset files that match the current mode (3D or 2D extensions)."""
        self.assets_tree.clear()
        root = self._workspace_root
        if not root or not root.exists():
            no_item = QTreeWidgetItem(self.assets_tree, ["No project folder"])
            no_item.setFlags(Qt.ItemFlag.NoItemFlags)
            return

        if self._mode not in ("2D", "3D"):
            return

        # Show project root name
        root_item = QTreeWidgetItem(self.assets_tree, [root.name])
        root_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
        root_item.setExpanded(True)

        exts = self.ASSET_3D_EXTS if self._mode == "3D" else self.ASSET_2D_EXTS
        self._scan_dir_full(root, root_item, exts)

        # Remove empty child folders (keeps the root even if empty)
        self._prune_empty(root_item)
        self.assets_tree.expandAll()

    def _scan_dir_full(self, path: Path, parent_item, asset_exts, depth=0):
        """Recursively scan directories, showing the full folder structure
        but only listing files whose extension is in `asset_exts`."""
        if depth > 6: return
        try:
            entries = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except PermissionError:
            return
        for entry in entries:
            if entry.name.startswith('.') or entry.name in self.SKIP_DIRS:
                continue
            if entry.is_dir():
                dir_item = QTreeWidgetItem(parent_item, [entry.name])
                dir_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                self._scan_dir_full(entry, dir_item, asset_exts, depth + 1)
            elif entry.suffix.lower() in asset_exts:
                file_item = QTreeWidgetItem(parent_item, [entry.name])
                file_item.setData(0, Qt.ItemDataRole.UserRole, str(entry))
                file_item.setToolTip(0, str(entry))

    def _prune_empty(self, item):
        """Recursively remove child tree items that are folders with no children."""
        i = 0
        while i < item.childCount():
            child = item.child(i)
            if not child.data(0, Qt.ItemDataRole.UserRole):  # it's a folder
                self._prune_empty(child)
                if child.childCount() == 0:
                    item.removeChild(child)
                    continue
            i += 1

    # ---- Outliner ----
    def update_outliner(self, objects: List[SceneObject]):
        current_id = None
        sel = self.outliner_list.currentItem()
        if sel: current_id = sel.data(Qt.ItemDataRole.UserRole)

        self.outliner_list.blockSignals(True)
        self.outliner_list.clear()
        for obj in objects:
            icon_map = {
                'cube':'[C]','sphere':'[S]','cylinder':'[Y]','plane':'[P]',
                'cone':'[N]','rect':'[R]','circle':'[O]','sprite':'[I]','mesh':'[M]',
            }
            prefix = icon_map.get(obj.obj_type, '[?]')
            label = f"{prefix} {obj.name}"
            if obj.selected: label = f"> {label}"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, obj.id)
            if obj.selected: item.setForeground(QColor("#4fc3f7"))
            self.outliner_list.addItem(item)

        if current_id:
            for i in range(self.outliner_list.count()):
                if self.outliner_list.item(i).data(Qt.ItemDataRole.UserRole) == current_id:
                    self.outliner_list.setCurrentRow(i); break
        self.outliner_list.blockSignals(False)

    def _on_outliner_select(self, row):
        if row < 0: return
        item = self.outliner_list.item(row)
        if item: self.object_select_requested.emit(item.data(Qt.ItemDataRole.UserRole))

    def _on_outliner_rename(self, item):
        obj_id = item.data(Qt.ItemDataRole.UserRole)
        if obj_id: self.object_select_requested.emit(f"rename:{obj_id}")

    def _outliner_context_menu(self, pos):
        item = self.outliner_list.itemAt(pos)
        if not item: return
        obj_id = item.data(Qt.ItemDataRole.UserRole)
        if not obj_id: return

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background: #2a2a2a; color: #e0e0e0; border: 1px solid #555; }
            QMenu::item { padding: 6px 20px; }
            QMenu::item:selected { background: #4fc3f7; color: #1a1a1a; }
        """)
        rename_act = menu.addAction("Rename")
        delete_act = menu.addAction("Delete")
        
        # Blocking call - list might refresh while this is open
        action = menu.exec(self.outliner_list.mapToGlobal(pos))
        
        if action == rename_act:
            self.object_select_requested.emit(f"rename:{obj_id}")
        elif action == delete_act:
            self.object_select_requested.emit(f"delete:{obj_id}")


# ===================================================================
# Scene Toolbar
# ===================================================================

class SceneToolbar(QWidget):
    mode_changed = pyqtSignal(str)
    grid_toggled = pyqtSignal(bool)
    snap_toggled = pyqtSignal(bool)
    grid_size_changed = pyqtSignal(float)
    transform_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SceneToolbar"); self.setFixedHeight(40)
        self.setStyleSheet(TOOLBAR_SS)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8,4,8,4); layout.setSpacing(6)

        mode_label = QLabel("Mode:"); mode_label.setStyleSheet(LABEL_SS)
        layout.addWidget(mode_label)
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Pure", "UI", "2D", "3D"])
        self.mode_combo.setCurrentText("3D"); self.mode_combo.setStyleSheet(COMBO_SS)
        self.mode_combo.currentTextChanged.connect(self._on_mode_changed)
        layout.addWidget(self.mode_combo)

        sep1 = QFrame(); sep1.setFrameShape(QFrame.Shape.VLine); sep1.setStyleSheet("color:#555;")
        layout.addWidget(sep1)

        self.move_btn = QToolButton(); self.move_btn.setText("Move"); self.move_btn.setCheckable(True); self.move_btn.setChecked(True)
        self.move_btn.setStyleSheet(BTN_SS); layout.addWidget(self.move_btn)
        self.rotate_btn = QToolButton(); self.rotate_btn.setText("Rotate"); self.rotate_btn.setCheckable(True)
        self.rotate_btn.setStyleSheet(BTN_SS); layout.addWidget(self.rotate_btn)
        self.scale_btn = QToolButton(); self.scale_btn.setText("Scale"); self.scale_btn.setCheckable(True)
        self.scale_btn.setStyleSheet(BTN_SS); layout.addWidget(self.scale_btn)
        self._tg = QButtonGroup(self); self._tg.setExclusive(True)
        self._tg.addButton(self.move_btn); self._tg.addButton(self.rotate_btn); self._tg.addButton(self.scale_btn)
        self._tg.buttonClicked.connect(self._on_transform_btn)

        sep2 = QFrame(); sep2.setFrameShape(QFrame.Shape.VLine); sep2.setStyleSheet("color:#555;")
        layout.addWidget(sep2)

        self.grid_check = QCheckBox("Grid"); self.grid_check.setChecked(True)
        self.grid_check.setStyleSheet("color:#ccc;font-size:11px;")
        self.grid_check.toggled.connect(self.grid_toggled.emit); layout.addWidget(self.grid_check)
        self.snap_check = QCheckBox("Snap"); self.snap_check.setChecked(False)
        self.snap_check.setStyleSheet("color:#ccc;font-size:11px;")
        self.snap_check.toggled.connect(self.snap_toggled.emit); layout.addWidget(self.snap_check)
        
        self.space_combo = QComboBox()
        self.space_combo.addItems(["Global", "Local"])
        self.space_combo.setStyleSheet(COMBO_SS)
        layout.addWidget(self.space_combo)

        grid_lbl = QLabel("Grid:"); grid_lbl.setStyleSheet(LABEL_SS); layout.addWidget(grid_lbl)
        self.grid_spin = QDoubleSpinBox()
        self.grid_spin.setRange(0.1,100.0); self.grid_spin.setValue(1.0); self.grid_spin.setSingleStep(0.5)
        self.grid_spin.setDecimals(1); self.grid_spin.setSuffix(" u"); self.grid_spin.setFixedWidth(80)
        self.grid_spin.setStyleSheet("QDoubleSpinBox{background:#3a3a3a;border:1px solid #555;border-radius:4px;color:#e0e0e0;padding:2px 4px;font-size:11px;}QDoubleSpinBox:hover{border-color:#4fc3f7;}")
        self.grid_spin.valueChanged.connect(self.grid_size_changed.emit); layout.addWidget(self.grid_spin)

        layout.addStretch()

        sep3 = QFrame(); sep3.setFrameShape(QFrame.Shape.VLine); sep3.setStyleSheet("color:#555;")
        layout.addWidget(sep3)
        self.cam_label = QLabel("Pos: 0, 5, 10  |  FPS: --")
        self.cam_label.setStyleSheet(LABEL_SS); layout.addWidget(self.cam_label)

        sep4 = QFrame(); sep4.setFrameShape(QFrame.Shape.VLine); sep4.setStyleSheet("color:#555;")
        layout.addWidget(sep4)
        self.play_btn = QPushButton("Play"); self.play_btn.setStyleSheet(BTN_SS)
        self.play_btn.setToolTip("Play scene (future)"); self.play_btn.setEnabled(False)
        layout.addWidget(self.play_btn)

    def _on_mode_changed(self, text):
        self.mode_changed.emit(text)
        is_vp = text in ("2D", "3D")
        for w in (self.move_btn, self.rotate_btn, self.scale_btn, self.grid_check, self.snap_check, self.grid_spin, self.space_combo):
            w.setEnabled(is_vp)

    def _on_transform_btn(self, btn):
        m = {"Move":"move","Rotate":"rotate","Scale":"scale"}
        self.transform_changed.emit(m.get(btn.text(), "move"))

    def update_cam_info(self, pos_str, fps):
        self.cam_label.setText(f"Pos: {pos_str}  |  FPS: {fps}")


# ===================================================================
# Pure mode placeholder
# ===================================================================

class PurePlaceholder(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: #1e1e1e;")
        layout = QVBoxLayout(self); layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon = QLabel("<<>>"); icon.setStyleSheet("font-size: 48px; color: #4fc3f7;")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter); layout.addWidget(icon)
        title = QLabel("Pure Logic Mode")
        title.setStyleSheet("font-size: 22px; font-weight: bold; color: #e0e0e0;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter); layout.addWidget(title)
        desc = QLabel("No scene viewport -- this project uses logic graphs only.\nSwitch to 2D or 3D to open the scene editor.")
        desc.setStyleSheet("font-size: 13px; color: #888; margin-top: 8px;")
        desc.setWordWrap(True); desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(desc)


# ===================================================================
# Main Scene Editor Container
# ===================================================================

class SceneEditorWidget(QWidget):
    """
    The Viewport tab: toolbar + [explorer | viewport/UI builder].
    Replaces both the old Game tab and the standalone UI tab.
    """

    mode_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: #1e1e1e;")
        self._current_mode = "3D"
        self._ui_builder = None
        self._object_counter = {}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0,0,0,0); outer.setSpacing(0)

        self.toolbar = SceneToolbar(self)
        outer.addWidget(self.toolbar)

        self._splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self._splitter.setStyleSheet("QSplitter::handle { background: #3c3c3c; width: 2px; }")
        outer.addWidget(self._splitter, 1)

        self.explorer = SceneExplorerPanel(self)
        self._splitter.addWidget(self.explorer)

        self._stack = QStackedWidget(self)
        self._stack.setStyleSheet("background: #1e1e1e;")
        self._splitter.addWidget(self._stack)

        self.viewport = SceneViewport(self)
        self._stack.addWidget(self.viewport)         # 0

        self.pure_placeholder = PurePlaceholder(self)
        self._stack.addWidget(self.pure_placeholder)  # 1

        self._ui_placeholder = QLabel("UI Builder not loaded")
        self._ui_placeholder.setStyleSheet("color: #888; font-size: 14px; background: #1e1e1e;")
        self._ui_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._stack.addWidget(self._ui_placeholder)   # 2

        self._splitter.setSizes([240, 800])

        # FPS timer
        self._fps_timer = QTimer(self)
        self._fps_timer.timeout.connect(self._update_cam_info)
        self._fps_timer.start(250)
        self._current_fps = 0
        if hasattr(self.viewport, 'fps_updated'):
            self.viewport.fps_updated.connect(lambda f: setattr(self, '_current_fps', f))

        # Outliner refresh timer
        self._outliner_timer = QTimer(self)
        self._outliner_timer.timeout.connect(self._refresh_outliner)
        self._outliner_timer.start(500)

        # Connect signals
        self.toolbar.mode_changed.connect(self._on_mode_changed)
        self.toolbar.grid_toggled.connect(self.viewport.set_show_grid)
        self.toolbar.snap_toggled.connect(self.viewport.set_snap_enabled)
        self.toolbar.grid_size_changed.connect(self.viewport.set_grid_size)
        self.toolbar.transform_changed.connect(self.viewport.set_transform_mode)
        self.toolbar.space_combo.currentTextChanged.connect(self.viewport.set_transform_space)

        self.viewport.object_dropped.connect(self._on_object_dropped)
        self.viewport.object_selected.connect(self._on_object_selected)
        self.viewport.object_moved.connect(self._on_object_moved)

        self.explorer.object_select_requested.connect(self._on_outliner_action)
        self.explorer.properties.property_changed.connect(lambda: self.viewport.update())

        # Set workspace root for asset scanning
        try:
            ws = Path(__file__).resolve().parents[2]
            self.explorer.set_workspace_root(ws)
        except Exception:
            pass

    def set_ui_builder(self, builder):
        self._ui_builder = builder
        old = self._stack.widget(2)
        self._stack.removeWidget(old); old.deleteLater()
        self._stack.insertWidget(2, builder)

    def _on_mode_changed(self, mode):
        self._current_mode = mode
        self.mode_changed.emit(mode)
        self.explorer.set_mode(mode)
        if mode == "Pure":
            self.viewport.stop_render_loop(); self._stack.setCurrentIndex(1); return
        if mode == "UI":
            self.viewport.stop_render_loop(); self._stack.setCurrentIndex(2); return
        self._stack.setCurrentIndex(0)
        self.viewport.set_mode(mode); self.viewport.start_render_loop()

    def _on_transform_changed(self, mode):
        self.viewport.set_transform_mode(mode)

    def _next_name(self, obj_type):
        count = self._object_counter.get(obj_type, 0)
        self._object_counter[obj_type] = count + 1
        display = obj_type.capitalize()
        return f"{display}_{count}" if count > 0 else display

    def _on_object_dropped(self, type_str, wx, wz):
        if self.viewport.snap_enabled:
            gs = self.viewport.grid_size
            wx = round(wx / gs) * gs; wz = round(wz / gs) * gs

        if type_str.startswith("file:"):
            file_path = type_str[5:]
            obj = SceneObject(Path(file_path).stem, "mesh")
            obj.file_path = file_path
            if self._current_mode == "3D": obj.position = [wx, 0.0, wz]
            else: obj.position = [wx, wz, 0.0]
        else:
            name = self._next_name(type_str)
            obj = SceneObject(name, type_str)
            if self._current_mode == "3D":
                y_pos = 0.5 if type_str != 'plane' else 0.0
                if self.viewport.snap_enabled: y_pos = round(y_pos / self.viewport.grid_size) * self.viewport.grid_size
                obj.position = [wx, y_pos, wz]
            else:
                obj.position = [wx, wz, 0.0]
        self.viewport.scene_objects.append(obj)
        for o in self.viewport.scene_objects: o.selected = False
        obj.selected = True
        self.viewport.object_selected.emit(obj)
        self._refresh_outliner()

    def _on_object_selected(self, obj):
        self.explorer.properties.set_object(obj)
        self._refresh_outliner()

    def _on_object_moved(self):
        """Called after user finishes dragging an object ΓÇö sync properties panel."""
        sel = [o for o in self.viewport.scene_objects if o.selected]
        if sel:
            self.explorer.properties.refresh_from_object()

    def _refresh_outliner(self):
        self.explorer.update_outliner(self.viewport.scene_objects)

    def _on_outliner_action(self, action_str):
        if action_str.startswith("rename:"):
            obj_id = action_str[7:]
            for obj in self.viewport.scene_objects:
                if obj.id == obj_id:
                    new_name, ok = QInputDialog.getText(self, "Rename Object", "Name:", text=obj.name)
                    if ok and new_name.strip():
                        obj.name = new_name.strip(); self._refresh_outliner()
                    return
        elif action_str.startswith("delete:"):
            obj_id = action_str[7:]
            self.viewport.scene_objects = [o for o in self.viewport.scene_objects if o.id != obj_id]
            self.explorer.properties.set_object(None)
            self._refresh_outliner(); return
        else:
            for o in self.viewport.scene_objects:
                o.selected = (o.id == action_str)
                if o.selected:
                    self.explorer.properties.set_object(o)
            self.viewport.update(); self._refresh_outliner()

    def _update_cam_info(self):
        if self._current_mode == "3D" and hasattr(self.viewport, '_cam3d'):
            c = self.viewport._cam3d
            s = f"{c.pos[0]:.1f}, {c.pos[1]:.1f}, {c.pos[2]:.1f}"
        elif self._current_mode == "2D" and hasattr(self.viewport, '_cam2d'):
            c = self.viewport._cam2d
            s = f"{c.x:.1f}, {c.y:.1f}  Z: {c.zoom_level:.1f}"
        else: s = "--"
        self.toolbar.update_cam_info(s, self._current_fps)

    def on_tab_activated(self):
        if self._current_mode in ("2D", "3D"): self.viewport.start_render_loop()

    def on_tab_deactivated(self):
        self.viewport.stop_render_loop()

    def get_scene_data(self) -> dict:
        return {'mode': self._current_mode, 'objects': [o.to_dict() for o in self.viewport.scene_objects]}

    def load_scene_data(self, data: dict):
        self._current_mode = data.get('mode', '3D')
        self.toolbar.mode_combo.setCurrentText(self._current_mode)
        self.viewport.scene_objects = [SceneObject.from_dict(d) for d in data.get('objects', [])]
        self._refresh_outliner()
