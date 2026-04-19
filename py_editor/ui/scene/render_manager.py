"""
render_manager.py

GL drawing helpers, Gizmos, and Camera system.
"""
import math
from OpenGL.GL import *
from OpenGL.GLU import *
from py_editor.ui.shared_styles import OBJECT_COLOR, OBJECT_FACE_COLOR, AXIS_X_COLOR, AXIS_Y_COLOR, AXIS_Z_COLOR, GIZMO_ALPHA

# ---- Math Helpers ----
def _cross(a, b):
    return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])

def _normalize(v):
    ln = math.sqrt(v[0]*v[0]+v[1]*v[1]+v[2]*v[2])
    return (v[0]/ln, v[1]/ln, v[2]/ln) if ln > 1e-9 else (0,0,0)

def _normalize_2d(v):
    ln = math.sqrt(v[0]*v[0]+v[1]*v[1])
    return (v[0]/ln, v[1]/ln) if ln > 1e-9 else (0,0)

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

def _mat_vec_mul(M, v):
    return (
        M[0][0]*v[0] + M[0][1]*v[1] + M[0][2]*v[2],
        M[1][0]*v[0] + M[1][1]*v[1] + M[1][2]*v[2],
        M[2][0]*v[0] + M[2][1]*v[1] + M[2][2]*v[2]
    )

def _euler_to_matrix(ex, ey, ez):
    rx, ry, rz = math.radians(ex), math.radians(ey), math.radians(ez)
    cx, sx = math.cos(rx), math.sin(rx); cy, sy = math.cos(ry), math.sin(ry); cz, sz = math.cos(rz), math.sin(rz)
    Mx = [[1, 0, 0], [0, cx, -sx], [0, sx, cx]]
    My = [[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]]
    Mz = [[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]]
    def __mul(A, B):
        C = [[0]*3 for _ in range(3)]
        for i in range(3):
            for j in range(3):
                for k in range(3): C[i][j] += A[i][k] * B[k][j]
        return C
    return __mul(My, __mul(Mx, Mz))

# ---- Camera Classes ----
class Camera3D:
    def __init__(self):
        self.pos = [0.0, 5.0, 10.0]
        self.yaw = -90.0
        self.pitch = -25.0
        self.fov = 60.0
        self.near = 0.1
        self.far = 5000.0
        self.speed = 10.0
        self.sensitivity = 0.15
        self.rotation_limits = []

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
        f = self.front; u = self.up
        t = (self.pos[0]+f[0], self.pos[1]+f[1], self.pos[2]+f[2])
        gluLookAt(self.pos[0],self.pos[1],self.pos[2], t[0],t[1],t[2], u[0],u[1],u[2])

    def rotate(self, dx, dy):
        self.yaw += dx * self.sensitivity
        new_pitch = self.pitch - dy * self.sensitivity
        for limit in self.rotation_limits:
            axis = limit.get('axis', '').lower()
            mn, mx = limit.get('min', -360), limit.get('max', 360)
            if axis == 'x': new_pitch = max(mn, min(mx, new_pitch))
            elif axis == 'y': self.yaw = max(mn, min(mx, self.yaw))
        self.pitch = max(-89.9, min(89.9, new_pitch))

    def move(self, forward, right, up, dt, speed=None):
        if speed is None: speed = self.speed
        f, r = self.front, self.right; s = speed * dt
        # Use full 3D front vector for 6DOF movement (Fly mode)
        self.pos[0] += (f[0]*forward + r[0]*right)*s
        self.pos[1] += (f[1]*forward + up)*s
        self.pos[2] += (f[2]*forward + r[2]*right)*s

    def focus_on(self, target_pos, target_radius=1.0):
        """Center camera on target and zoom to a comfortable distance."""
        # Calculate direction from current camera to target
        direction = _sub(self.pos, target_pos)
        dist = _length(direction)
        
        # Avoid zero-length vector
        if dist < 0.01:
            direction = (0, 0, 1)
        else:
            direction = _normalize(direction)
            
        # Target distance based on object size
        target_dist = max(2.5, target_radius * 5.0)
        
        # Position camera at target_dist away from object in the original relative direction
        self.pos[0] = target_pos[0] + direction[0] * target_dist
        self.pos[1] = target_pos[1] + direction[1] * target_dist
        self.pos[2] = target_pos[2] + direction[2] * target_dist
        
        # Calculate new yaw/pitch to look at target
        dx, dy, dz = _sub(target_pos, self.pos)
        self.yaw = math.degrees(math.atan2(dz, dx))
        # Pitch: angle relative to X-Z plane
        self.pitch = math.degrees(math.atan2(dy, math.sqrt(dx*dx + dz*dz)))

    def screen_to_ray(self, mx, my, vp_w, vp_h):
        aspect = vp_w / max(vp_h, 1)
        fov_rad = math.radians(self.fov)
        half_h = math.tan(fov_rad / 2.0); half_w = half_h * aspect
        nx = (2.0 * mx / vp_w - 1.0) * half_w
        ny = (1.0 - 2.0 * my / vp_h) * half_h
        f, r, u = self.front, self.right, self.up
        direction = _normalize(_add(_add(_scale_vec(f, 1.0), _scale_vec(r, nx)), _scale_vec(u, ny)))
        return tuple(self.pos), direction

    def world_to_screen(self, world_pos, vp_w, vp_h):
        aspect = vp_w / max(vp_h, 1)
        f = self.front; r = self.right; u = self.up
        V = [[r[0], r[1], r[2], -_dot(r, self.pos)], [u[0], u[1], u[2], -_dot(u, self.pos)], [-f[0], -f[1], -f[2], _dot(f, self.pos)], [0, 0, 0, 1]]
        fov_rad = math.radians(self.fov); h = 1.0 / math.tan(fov_rad / 2.0); w = h / aspect
        far, near = self.far, self.near
        P = [[w, 0, 0, 0], [0, h, 0, 0], [0, 0, -(far+near)/(far-near), -(2*far*near)/(far-near)], [0, 0, -1, 0]]
        PV = [[0]*4 for _ in range(4)]
        for i in range(4):
            for j in range(4):
                for k in range(4): PV[i][j] += P[i][k] * V[k][j]
        v = (world_pos[0], world_pos[1], world_pos[2], 1.0)
        out = [0.0]*4
        for i in range(4):
            for j in range(4): out[i] += PV[i][j] * v[j]
        if out[3] <= 0: return None
        nx, ny = out[0] / out[3], out[1] / out[3]
        return (nx + 1.0) * 0.5 * vp_w, (1.0 - ny) * 0.5 * vp_h

    def ray_plane_intersect(self, mx, my, vp_w, vp_h, plane_point, plane_normal):
        origin, direction = self.screen_to_ray(mx, my, vp_w, vp_h)
        denom = _dot(direction, plane_normal)
        if abs(denom) < 1e-9: return None
        t = _dot(_sub(plane_point, origin), plane_normal) / denom
        return _add(origin, _scale_vec(direction, t)) if t >= 0 else None

class Camera2D:
    def __init__(self):
        self.x = 0.0; self.y = 0.0; self.zoom_level = 10.0
    def apply_gl(self, width, height):
        aspect = width / max(height, 1); hw, hh = self.zoom_level * aspect, self.zoom_level
        glMatrixMode(GL_PROJECTION); glLoadIdentity()
        glOrtho(self.x-hw, self.x+hw, self.y-hh, self.y+hh, -1.0, 1.0)
        glMatrixMode(GL_MODELVIEW); glLoadIdentity()
    def screen_to_world(self, mx, my, width, height):
        aspect = width / max(height, 1); hw, hh = self.zoom_level * aspect, self.zoom_level
        return self.x + (2.0 * mx / width - 1.0) * hw, self.y + (1.0 - 2.0 * my / height) * hh

# ---- Primitive Drawing Helpers ----
def _draw_wireframe_cube(sx=1, sy=1, sz=1, color=OBJECT_COLOR, fill_color=OBJECT_FACE_COLOR):
    hx, hy, hz = sx/2, sy/2, sz/2
    verts = [(-hx,-hy,-hz),(hx,-hy,-hz),(hx,hy,-hz),(-hx,hy,-hz),
             (-hx,-hy,hz),(hx,-hy,hz),(hx,hy,hz),(-hx,hy,hz)]
    faces = [
        (0,1,2,3, (0,0,-1)), # Back
        (4,5,6,7, (0,0, 1)), # Front
        (0,1,5,4, (0,-1,0)), # Bottom
        (2,3,7,6, (0,1, 0)), # Top
        (0,3,7,4, (-1,0,0)), # Left
        (1,2,6,5, (1, 0,0))  # Right
    ]
    edges = [(0,1),(1,2),(2,3),(3,0),(4,5),(5,6),(6,7),(7,4),(0,4),(1,5),(2,6),(3,7)]
    glColor4f(*fill_color)
    for f in faces:
        glBegin(GL_QUADS)
        glNormal3f(*f[4])
        for i in f[:4]: glVertex3f(*verts[i])
        glEnd()
    glColor4f(*color); glLineWidth(1.5); glBegin(GL_LINES)
    for a, b in edges: glVertex3f(*verts[a]); glVertex3f(*verts[b])
    glEnd(); glLineWidth(1.0)

def _draw_wireframe_sphere(radius=0.5, rings=12, segments=16, color=OBJECT_COLOR, fill_color=OBJECT_FACE_COLOR):
    # Fill
    glColor4f(*fill_color)
    for i in range(rings):
        phi1 = math.pi * i / rings
        phi2 = math.pi * (i + 1) / rings
        glBegin(GL_QUAD_STRIP)
        for j in range(segments + 1):
            theta = 2 * math.pi * j / segments
            x1, y1, z1 = radius * math.sin(phi1) * math.cos(theta), radius * math.cos(phi1), radius * math.sin(phi1) * math.sin(theta)
            x2, y2, z2 = radius * math.sin(phi2) * math.cos(theta), radius * math.cos(phi2), radius * math.sin(phi2) * math.sin(theta)
            glNormal3f(x1/radius, y1/radius, z1/radius)
            glVertex3f(x1, y1, z1); glVertex3f(x2, y2, z2)
        glEnd()

    # Edges
    glLineWidth(1.5); glColor4f(*color)
    for i in range(rings + 1):
        phi = math.pi * i / rings; y = radius * math.cos(phi); r = radius * math.sin(phi)
        glBegin(GL_LINE_LOOP)
        for j in range(segments):
            theta = 2*math.pi*j/segments
            glVertex3f(r * math.cos(theta), y, r * math.sin(theta))
        glEnd()
    for j in range(segments):
        theta = 2*math.pi*j/segments
        glBegin(GL_LINE_STRIP)
        for i in range(rings+1):
            phi = math.pi * i / rings
            nx, ny, nz = math.sin(phi)*math.cos(theta), math.cos(phi), math.sin(phi)*math.sin(theta)
            glVertex3f(radius*nx, radius*ny, radius*nz)
        glEnd()
    glLineWidth(1.0)
    
def _draw_wireframe_plane(sx=1, sz=1, color=OBJECT_COLOR, fill_color=OBJECT_FACE_COLOR):
    hx, hz = sx/2, sz/2
    verts = [(-hx, 0, -hz), (hx, 0, -hz), (hx, 0, hz), (-hx, 0, hz)]
    # Fill
    glColor4f(*fill_color)
    glBegin(GL_QUADS)
    glNormal3f(0, 1, 0)
    for v in verts: glVertex3f(*v)
    glEnd()
    # Edges
    glColor4f(*color); glLineWidth(1.5); glBegin(GL_LINE_LOOP)
    for v in verts: glVertex3f(*v)
    glEnd(); glLineWidth(1.0)

def _draw_wireframe_cylinder(radius=0.5, height=1.0, segments=16, color=OBJECT_COLOR, fill_color=OBJECT_FACE_COLOR):
    hh = height / 2.0
    # Fill
    glColor4f(*fill_color)
    # Sides
    glBegin(GL_QUAD_STRIP)
    for i in range(segments + 1):
        theta = 2 * math.pi * i / segments
        x, z = radius * math.cos(theta), radius * math.sin(theta)
        glNormal3f(math.cos(theta), 0, math.sin(theta))
        glVertex3f(x, -hh, z); glVertex3f(x, hh, z)
    glEnd()
    # Caps
    for y in [-hh, hh]:
        glBegin(GL_TRIANGLE_FAN)
        glNormal3f(0, 1 if y > 0 else -1, 0)
        glVertex3f(0, y, 0)
        for i in range(segments + 1):
            theta = 2 * math.pi * i / segments
            glVertex3f(radius * math.cos(theta), y, radius * math.sin(theta))
        glEnd()
    # Edges
    glColor4f(*color); glLineWidth(1.5)
    for y in [-hh, hh]:
        glBegin(GL_LINE_LOOP)
        for i in range(segments):
            theta = 2 * math.pi * i / segments
            glVertex3f(radius * math.cos(theta), y, radius * math.sin(theta))
        glEnd()
    glBegin(GL_LINES)
    for i in [0, segments//4, segments//2, 3*segments//4]:
        theta = 2 * math.pi * i / segments
        x, z = radius * math.cos(theta), radius * math.sin(theta)
        glVertex3f(x, -hh, z); glVertex3f(x, hh, z)
    glEnd()
    glLineWidth(1.0)

def _draw_wireframe_cone(radius=0.5, height=1.0, segments=16, color=OBJECT_COLOR, fill_color=OBJECT_FACE_COLOR):
    hh = height / 2.0
    # Fill
    glColor4f(*fill_color)
    glBegin(GL_TRIANGLE_FAN)
    glNormal3f(0, 1, 0) # Inaccurate but fine for wireframe
    glVertex3f(0, hh, 0)
    for i in range(segments + 1):
        theta = 2 * math.pi * i / segments
        glVertex3f(radius * math.cos(theta), -hh, radius * math.sin(theta))
    glEnd()
    # Bottom
    glBegin(GL_TRIANGLE_FAN)
    glNormal3f(0, -1, 0)
    glVertex3f(0, -hh, 0)
    for i in range(segments + 1):
        theta = 2 * math.pi * i / segments
        glVertex3f(radius * math.cos(theta), -hh, radius * math.sin(theta))
    glEnd()
    # Edges
    glColor4f(*color); glLineWidth(1.5)
    glBegin(GL_LINE_LOOP)
    for i in range(segments):
        theta = 2 * math.pi * i / segments
        glVertex3f(radius * math.cos(theta), -hh, radius * math.sin(theta))
    glEnd()
    glBegin(GL_LINES)
    for i in [0, segments//4, segments//2, 3*segments//4]:
        theta = 2 * math.pi * i / segments
        glVertex3f(0, hh, 0); glVertex3f(radius * math.cos(theta), -hh, radius * math.sin(theta))
    glEnd()
    glLineWidth(1.0)


def _gizmo_screen_scale(pos, camera=None):
    """Scale gizmo so its length feels consistent at any camera distance."""
    if camera is None:
        return 1.0
    d = _length(_sub(pos, camera.pos))
    # Map distance → world-length so gizmo occupies roughly constant screen space.
    return max(0.5, d * 0.12)

def _draw_gizmo(pos, selected_axis=None, mode="translate", camera=None):
    """Draw professional 3D transformation gizmo at position.

    mode: "translate" | "rotate" | "scale"
    """
    from py_editor.ui.shared_styles import AXIS_X_COLOR, AXIS_Y_COLOR, AXIS_Z_COLOR, GIZMO_ALPHA
    glDisable(GL_DEPTH_TEST)
    glDisable(GL_CULL_FACE)
    glEnable(GL_BLEND)
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
    # Smooth lines / points for a cleaner look
    try:
        glEnable(GL_LINE_SMOOTH)
        glHint(GL_LINE_SMOOTH_HINT, GL_NICEST)
    except Exception:
        pass

    glUseProgram(0)
    glPushMatrix()
    glTranslatef(*pos)

    s = _gizmo_screen_scale(pos, camera)
    glScalef(s, s, s)

    axes = [
        ('x', AXIS_X_COLOR, (1, 0, 0), (90, 0, 0, -1)),
        ('y', AXIS_Y_COLOR, (0, 1, 0), None),
        ('z', AXIS_Z_COLOR, (0, 0, 1), (90, 1, 0, 0)),
    ]

    # Small filled centre sphere
    glColor4f(1.0, 1.0, 1.0, 0.55)
    q = gluNewQuadric()
    gluSphere(q, 0.08, 12, 8)
    gluDeleteQuadric(q)

    if mode == "rotate":
        segs = 64
        for name, col, axis_vec, _ in axes:
            is_sel = (selected_axis == name)
            a = 1.0 if is_sel else GIZMO_ALPHA
            # Glow pass (thick, low-alpha)
            glColor4f(col[0], col[1], col[2], a * 0.35)
            glLineWidth(6.0 if is_sel else 4.5)
            glBegin(GL_LINE_LOOP)
            for i in range(segs):
                t = 2 * math.pi * i / segs
                cs, sn = math.cos(t) * 2.0, math.sin(t) * 2.0
                if name == 'x':   glVertex3f(0, cs, sn)
                elif name == 'y': glVertex3f(cs, 0, sn)
                else:             glVertex3f(cs, sn, 0)
            glEnd()
            # Solid pass
            glColor4f(col[0], col[1], col[2], a)
            glLineWidth(2.5 if is_sel else 1.8)
            glBegin(GL_LINE_LOOP)
            for i in range(segs):
                t = 2 * math.pi * i / segs
                cs, sn = math.cos(t) * 2.0, math.sin(t) * 2.0
                if name == 'x':   glVertex3f(0, cs, sn)
                elif name == 'y': glVertex3f(cs, 0, sn)
                else:             glVertex3f(cs, sn, 0)
            glEnd()
        glLineWidth(1.0)
        glPopMatrix()
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_CULL_FACE)
        return

    # translate / scale: axis shafts with a glow underlay
    for name, col, axis_vec, _ in axes:
        is_sel = (selected_axis == name)
        a = 1.0 if is_sel else GIZMO_ALPHA
        tip = (axis_vec[0]*1.85, axis_vec[1]*1.85, axis_vec[2]*1.85)
        # Glow
        glColor4f(col[0], col[1], col[2], a * 0.3)
        glLineWidth(7.0 if is_sel else 5.0)
        glBegin(GL_LINES); glVertex3f(0, 0, 0); glVertex3f(*tip); glEnd()
        # Core
        glColor4f(col[0], col[1], col[2], a)
        glLineWidth(3.0 if is_sel else 2.0)
        glBegin(GL_LINES); glVertex3f(0, 0, 0); glVertex3f(*tip); glEnd()

    # axis tips: smooth cones (translate) or rounded cubes (scale)
    for name, col, axis_vec, rot in axes:
        is_sel = (selected_axis == name)
        a = 1.0 if is_sel else GIZMO_ALPHA
        # Highlight selected tip with extra brightness
        bright = 1.2 if is_sel else 1.0
        tip_col = (min(col[0]*bright, 1.0), min(col[1]*bright, 1.0), min(col[2]*bright, 1.0))
        glColor4f(tip_col[0], tip_col[1], tip_col[2], a)
        glPushMatrix()
        glTranslatef(axis_vec[0]*1.85, axis_vec[1]*1.85, axis_vec[2]*1.85)
        if mode == "scale":
            hx = 0.16
            verts = [(-hx,-hx,-hx),(hx,-hx,-hx),(hx,hx,-hx),(-hx,hx,-hx),
                     (-hx,-hx,hx),(hx,-hx,hx),(hx,hx,hx),(-hx,hx,hx)]
            faces = [(0,1,2,3),(4,5,6,7),(0,1,5,4),(2,3,7,6),(0,3,7,4),(1,2,6,5)]
            glBegin(GL_QUADS)
            for f in faces:
                for vi in f: glVertex3f(*verts[vi])
            glEnd()
            # Edge outline
            glColor4f(tip_col[0]*0.4, tip_col[1]*0.4, tip_col[2]*0.4, a)
            glLineWidth(1.5)
            edges = [(0,1),(1,2),(2,3),(3,0),(4,5),(5,6),(6,7),(7,4),(0,4),(1,5),(2,6),(3,7)]
            glBegin(GL_LINES)
            for aidx, bidx in edges:
                glVertex3f(*verts[aidx]); glVertex3f(*verts[bidx])
            glEnd()
        else:
            if rot: glRotatef(*rot)
            _draw_wireframe_cone(radius=0.15, height=0.45, segments=20, 
                                 color=(*tip_col, a), fill_color=(*tip_col, a))
        glPopMatrix()

    glLineWidth(1.0)
    glPopMatrix()
    glEnable(GL_DEPTH_TEST)
    glEnable(GL_CULL_FACE)
    try:
        glDisable(GL_LINE_SMOOTH)
    except Exception:
        pass
def _draw_camera_icon(color=(1, 1, 0, 1)):
    # Simple pyramid for camera look
    glLineWidth(2.0); glColor4f(*color)
    glBegin(GL_LINES)
    glVertex3f(0,0,0); glVertex3f(-0.3, 0.3, -0.6)
    glVertex3f(0,0,0); glVertex3f(0.3, 0.3, -0.6)
    glVertex3f(0,0,0); glVertex3f(0.3, -0.3, -0.6)
    glVertex3f(0,0,0); glVertex3f(-0.3, -0.3, -0.6)
    glVertex3f(-0.3, 0.3, -0.6); glVertex3f(0.3, 0.3, -0.6)
    glVertex3f(0.3, 0.3, -0.6); glVertex3f(0.3, -0.3, -0.6)
    glVertex3f(0.3, -0.3, -0.6); glVertex3f(-0.3, -0.3, -0.6)
    glVertex3f(-0.3, -0.3, -0.6); glVertex3f(-0.3, 0.3, -0.6)
    glEnd(); glLineWidth(1.0)

def _draw_light_icon(color=(1, 1, 0, 1)):
    # Simple diamond for light
    glLineWidth(2.0); glColor4f(*color)
    glBegin(GL_LINES)
    glVertex3f(0, 0.4, 0); glVertex3f(0.2, 0, 0.2)
    glVertex3f(0, 0.4, 0); glVertex3f(-0.2, 0, 0.2)
    glVertex3f(0, 0.4, 0); glVertex3f(0.2, 0, -0.2)
    glVertex3f(0, 0.4, 0); glVertex3f(-0.2, 0, -0.2)
    glVertex3f(0, -0.4, 0); glVertex3f(0.2, 0, 0.2)
    glVertex3f(0, -0.4, 0); glVertex3f(-0.2, 0, 0.2)
    glVertex3f(0, -0.4, 0); glVertex3f(0.2, 0, -0.2)
    glVertex3f(0, -0.4, 0); glVertex3f(-0.2, 0, -0.2)
    glEnd(); glLineWidth(1.0)
