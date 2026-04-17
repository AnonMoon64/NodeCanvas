"""
particle_system.py

NodeCanvas particle system.

- CPU/GPU-ready SoA pools with instanced billboard rendering.
- Rich forces (gravity, drag, wind, turbulence, vortex, attractor, curl noise).
- Animated size/color curves (piecewise-linear LUTs) baked from spec.
- Distance-based LOD + streaming (only spawns within player/camera radius).
- Trail + stretch modes for rain / sparks.
- Global "weather hook" so WeatherSystem primitives can drive emitters.

Emitters are registered by SceneObject id. WeatherSystem emitters register a
marker flag so they spawn *around the camera* each frame instead of a fixed
pivot (moving global weather).
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Tuple

import numpy as np
from OpenGL.GL import *


# ---------------------------------------------------------------------------
# Spec
# ---------------------------------------------------------------------------

@dataclass
class ParticleSpec:
    """Static configuration baked from a node graph or weather system."""
    backend: str = "cpu"
    rate: float = 200.0
    max_count: int = 4096
    lifetime: float = 1.5
    gravity_scale: float = 1.0
    plane_collision: bool = False
    sea_level: float = 0.0
    collision_event: str = "" # Event to trigger on parent logic (e.g. "OnImpact")
    lifetime_jitter: float = 0.2

    spawn_source: Optional[Callable] = None

    velocity_dir: Tuple[float, float, float] = (0.0, 1.0, 0.0)
    velocity_cone: float = math.radians(30.0)
    speed_min: float = 3.0
    speed_max: float = 6.0

    # forces: list of dicts. types: gravity|drag|wind|turbulence|vortex|attractor|curl
    forces: List[dict] = field(default_factory=list)

    # render
    size_start: float = 0.10
    size_end: float = 0.02
    color_start: Tuple[float, float, float, float] = (1.0, 1.0, 1.0, 0.95)
    color_end:   Tuple[float, float, float, float] = (0.85, 0.95, 1.0, 0.0)
    blend_mode: str = "alpha"

    # animated curves: list of (t, value) pairs. Override start/end if set.
    size_curve:  Optional[List[Tuple[float, float]]] = None
    alpha_curve: Optional[List[Tuple[float, float]]] = None

    # render mode: "billboard" | "stretch" (velocity-aligned strands for rain)
    render_mode: str = "billboard"
    stretch_length: float = 0.6       # multiplier along velocity
    soft_particles: bool = True       # fade near geometry via depth proxy

    # LOD / streaming
    stream_radius: float = 150.0      # spawn/update radius around camera (0 = always)
    cull_radius: float = 300.0        # alive particles beyond this fade out

    # Flags
    receive_weather: bool = False     # auto-tracks camera for global weather
    kill_height: float = -10000.0     # GPU culling height (e.g. ocean floor)
    gravity_scale: float = 1.0        # convenience multiplier


# ---------------------------------------------------------------------------
# Curve helper
# ---------------------------------------------------------------------------

def _sample_curve(curve, t):
    """Sample a piecewise-linear curve defined by [(ti, vi), …] at normalised t ∈ [0,1]."""
    if not curve:
        return None
    pts = np.asarray(curve, dtype=np.float32)
    ts, vs = pts[:, 0], pts[:, 1]
    return np.interp(t, ts, vs).astype(np.float32)


# ---------------------------------------------------------------------------
# Pool
# ---------------------------------------------------------------------------

class ParticlePool:
    """Fixed-size SoA pool. Dead slots recycled; no per-frame alloc."""

    def __init__(self, spec: ParticleSpec):
        self.spec = spec
        n = spec.max_count
        self.pos      = np.zeros((n, 3), dtype=np.float32)
        self.vel      = np.zeros((n, 3), dtype=np.float32)
        self.size     = np.zeros(n,      dtype=np.float32)
        self.rot      = np.random.uniform(0, 2*math.pi, n).astype(np.float32)
        self.rot_vel  = np.random.uniform(-2.0, 2.0, n).astype(np.float32)
        self.color    = np.zeros((n, 4), dtype=np.float32)
        self.life     = np.zeros(n, dtype=np.float32)
        self.age      = np.zeros(n, dtype=np.float32)
        self.seeds    = np.random.uniform(0, 100, n).astype(np.float32)
        self.alive    = np.zeros(n, dtype=bool)
        self.spawn_accum = 0.0

    def _free_slots(self, count):
        free = np.flatnonzero(~self.alive)
        return free[:count]

    def spawn(self, positions: np.ndarray, velocity_override: Optional[np.ndarray] = None):
        if positions is None or len(positions) == 0:
            return
        slots = self._free_slots(len(positions))
        if len(slots) == 0:
            return
        n = len(slots)
        positions = positions[:n]

        s = self.spec
        d = np.array(s.velocity_dir, dtype=np.float32)
        d = d / (np.linalg.norm(d) + 1e-6)
        up = np.array([0, 1, 0], dtype=np.float32) if abs(d[1]) < 0.99 else np.array([1, 0, 0], dtype=np.float32)
        tan = np.cross(up, d); tan /= (np.linalg.norm(tan) + 1e-6)
        bit = np.cross(d, tan)

        cone = s.velocity_cone
        theta = np.random.uniform(0.0, cone, n).astype(np.float32)
        phi   = np.random.uniform(0.0, 2 * math.pi, n).astype(np.float32)
        sin_t, cos_t = np.sin(theta), np.cos(theta)
        dirs = (cos_t[:, None] * d
                + (sin_t * np.cos(phi))[:, None] * tan
                + (sin_t * np.sin(phi))[:, None] * bit)
        speed = np.random.uniform(s.speed_min, s.speed_max, n).astype(np.float32)
        vel   = dirs * speed[:, None]
        if velocity_override is not None:
            vel = velocity_override[:n].astype(np.float32)

        life = s.lifetime * (1.0 + np.random.uniform(-s.lifetime_jitter, s.lifetime_jitter, n)).astype(np.float32)

        self.pos[slots]   = positions.astype(np.float32)
        self.vel[slots]   = vel
        self.age[slots]   = 0.0
        self.life[slots]  = life
        self.seeds[slots] = np.random.uniform(0, 100, n).astype(np.float32)
        self.alive[slots] = True

    def update(self, dt: float, cam_pos=None):
        idx_bool = self.alive
        if not idx_bool.any():
            return
        count = int(idx_bool.sum())
        accel = np.zeros((count, 3), dtype=np.float32)
        spec = self.spec
        for f in spec.forces:
            t = f.get("type")
            if t == "gravity":
                g = float(f.get("magnitude", 9.8)) * spec.gravity_scale
                accel[:, 1] -= g
            elif t == "drag":
                k = float(f.get("coefficient", 0.5))
                accel -= self.vel[idx_bool] * k
            elif t == "wind":
                w = np.array(f.get("vector", [0, 0, 0]), dtype=np.float32)
                accel += w
            elif t == "turbulence":
                strength = float(f.get("strength", 2.0))
                freq = float(f.get("frequency", 0.3))
                # cheap pseudo-noise per-particle from position + seeds + time
                p = self.pos[idx_bool]
                s_ = self.seeds[idx_bool]
                tm = time.time()
                nx = np.sin(p[:, 1] * freq + s_ * 1.3 + tm * 0.9)
                ny = np.sin(p[:, 2] * freq + s_ * 2.1 + tm * 0.7)
                nz = np.sin(p[:, 0] * freq + s_ * 3.7 + tm * 1.1)
                accel += np.stack([nx, ny, nz], axis=1) * strength
            elif t == "vortex":
                center = np.array(f.get("center", [0, 0, 0]), dtype=np.float32)
                axis = np.array(f.get("axis", [0, 1, 0]), dtype=np.float32)
                axis /= (np.linalg.norm(axis) + 1e-6)
                strength = float(f.get("strength", 3.0))
                r = self.pos[idx_bool] - center
                tangent = np.cross(axis[None, :], r)
                accel += tangent * strength * 0.1
            elif t == "attractor":
                center = np.array(f.get("center", [0, 0, 0]), dtype=np.float32)
                strength = float(f.get("strength", 5.0))
                radius = float(f.get("radius", 20.0))
                diff = center - self.pos[idx_bool]
                dist = np.linalg.norm(diff, axis=1, keepdims=True) + 1e-5
                falloff = np.clip(1.0 - dist / radius, 0.0, 1.0)
                accel += (diff / dist) * strength * falloff
            elif t == "curl":
                # Simple curl-noise approximation (divergence-free-ish wind eddies)
                strength = float(f.get("strength", 1.5))
                freq = float(f.get("frequency", 0.08))
                p = self.pos[idx_bool]
                tm = time.time() * 0.3
                cx = np.sin(p[:, 1] * freq + tm) - np.cos(p[:, 2] * freq - tm)
                cy = np.sin(p[:, 2] * freq + tm) - np.cos(p[:, 0] * freq - tm)
                cz = np.sin(p[:, 0] * freq + tm) - np.cos(p[:, 1] * freq - tm)
                accel += np.stack([cx, cy, cz], axis=1) * strength

        self.vel[idx_bool] += accel * dt
        self.pos[idx_bool] += self.vel[idx_bool] * dt
        
        # --- Plane Collision (Y-Intersect) ---
        if spec.plane_collision:
            p = self.pos[idx_bool]
            hits = p[:, 1] < spec.sea_level
            if hits.any():
                # Correct position to surface
                p[hits, 1] = spec.sea_level
                # Kill or bounce? Typically rain 'dies' on impact
                # We'll set life to 0 for hits
                self.age[np.flatnonzero(idx_bool)[hits]] = self.life[np.flatnonzero(idx_bool)[hits]]
                
        self.rot[idx_bool] += self.rot_vel[idx_bool] * dt
        self.age[idx_bool] += dt
        self.alive[idx_bool] &= (self.age[idx_bool] < self.life[idx_bool])

        # Cull far particles (LOD)
        if cam_pos is not None and spec.cull_radius > 0:
            cam = np.asarray(cam_pos, dtype=np.float32)
            alive_idx = np.flatnonzero(self.alive)
            if len(alive_idx):
                d = np.linalg.norm(self.pos[alive_idx] - cam, axis=1)
                cull = d > spec.cull_radius
                self.alive[alive_idx[cull]] = False

        idx = np.flatnonzero(self.alive)
        if len(idx) == 0:
            return

        t = (self.age[idx] / np.maximum(self.life[idx], 1e-6)).clip(0.0, 1.0)

        # Size: curve or linear blend
        if spec.size_curve:
            self.size[idx] = _sample_curve(spec.size_curve, t)
        else:
            self.size[idx] = (spec.size_start * (1 - t) + spec.size_end * t).astype(np.float32)

        # Color
        cs = np.array(spec.color_start, dtype=np.float32)
        ce = np.array(spec.color_end, dtype=np.float32)
        base_col = cs * (1 - t[:, None]) + ce * t[:, None]
        if spec.alpha_curve:
            base_col[:, 3] = _sample_curve(spec.alpha_curve, t)
        self.color[idx] = base_col.astype(np.float32)

    def alive_render_data(self) -> Optional[np.ndarray]:
        """Returns packed [x,y,z, size, r,g,b,a, seed, vx,vy,vz] per instance (12 floats)."""
        idx = np.flatnonzero(self.alive)
        if len(idx) == 0:
            return None
        data = np.empty((len(idx), 12), dtype=np.float32)
        data[:, 0:3] = self.pos[idx]
        data[:, 3] = self.size[idx]
        data[:, 4:8] = self.color[idx]
        data[:, 8] = self.seeds[idx]
        data[:, 9:12] = self.vel[idx]
        return data.copy()


class ParticleEmitter:
    def __init__(self, parent_obj, spec: ParticleSpec):
        self.parent = parent_obj
        self.spec = spec
        self.pool = ParticlePool(spec)
        self._burst_queue: List[int] = []

    def burst(self, count: int):
        self._burst_queue.append(int(count))

    def tick(self, dt: float, cam_pos=None):
        self.pool.update(dt, cam_pos=cam_pos)
        spec = self.spec

        # Streaming gate: skip spawning if camera is far from emitter pivot
        # (unless this is a weather emitter that tracks the camera)
        if (not spec.receive_weather) and spec.stream_radius > 0 and cam_pos is not None:
            pivot = np.asarray(getattr(self.parent, 'position', (0, 0, 0)), dtype=np.float32)
            if np.linalg.norm(pivot - np.asarray(cam_pos)) > spec.stream_radius * 3.0:
                return

        # Bursts
        while self._burst_queue:
            n = self._burst_queue.pop()
            if spec.spawn_source:
                pts = spec.spawn_source(self.parent, n, dt)
                if pts is not None and len(pts):
                    self.pool.spawn(np.asarray(pts, dtype=np.float32))

        # Regular spawning
        if spec.spawn_source:
            self.pool.spawn_accum += dt * spec.rate
            n_to_spawn = int(self.pool.spawn_accum)
            if n_to_spawn > 0:
                self.pool.spawn_accum -= n_to_spawn
                positions = spec.spawn_source(self.parent, n_to_spawn, dt)
                if positions is not None and len(positions):
                    self.pool.spawn(np.asarray(positions, dtype=np.float32))


# ---------------------------------------------------------------------------
# Global manager
# ---------------------------------------------------------------------------

_manager = None

def get_particle_manager():
    global _manager
    if _manager is None:
        _manager = ParticleManager()
    return _manager


class ParticleManager:
    def __init__(self):
        self.emitters = {}
        self._renderer = None
        self._last_t = time.time()

    def register(self, parent_obj, name: str, spec: ParticleSpec):
        key = (parent_obj.id, name)
        self.emitters[key] = ParticleEmitter(parent_obj, spec)
        return self.emitters[key]

    def unregister(self, parent_obj, name: str):
        key = (parent_obj.id, name)
        if key in self.emitters:
            del self.emitters[key]

    def get(self, parent_obj, name: str) -> Optional[ParticleEmitter]:
        return self.emitters.get((parent_obj.id, name))

    def unregister_all_for(self, parent_obj):
        for key in [k for k in self.emitters if k[0] == parent_obj.id]:
            del self.emitters[key]

    def update_and_draw(self, camera_pos, view_mat, proj_mat):
        now = time.time()
        dt = min(now - self._last_t, 0.1)
        self._last_t = now

        if self._renderer is None:
            self._renderer = _SpriteRenderer()

        for em in self.emitters.values():
            em.tick(dt, cam_pos=camera_pos)
            data = em.pool.alive_render_data()
            if data is not None and len(data):
                self._renderer._current_kill_height = em.spec.kill_height
                self._renderer.draw(data, camera_pos, em.spec.blend_mode, em.spec.render_mode,
                                    em.spec.stretch_length)


# ---------------------------------------------------------------------------
# Spawn sources
# ---------------------------------------------------------------------------

def spawn_at_center(offset=(0, 0, 0)):
    def _sample(parent, count, dt):
        pos = getattr(parent, 'position', (0, 0, 0))
        out = np.tile(np.array(pos, dtype=np.float32) + np.array(offset, dtype=np.float32), (count, 1))
        out += np.random.uniform(-0.05, 0.05, (count, 3))
        return out
    return _sample


def spawn_in_sphere(radius: float = 1.0):
    def _sample(parent, count, dt):
        pos = np.array(getattr(parent, 'position', (0, 0, 0)), dtype=np.float32)
        phi = np.random.uniform(0, 2*np.pi, count)
        cos_theta = np.random.uniform(-1, 1, count)
        sin_theta = np.sqrt(1 - cos_theta**2)
        r = radius * np.cbrt(np.random.uniform(0, 1, count))
        offsets = np.empty((count, 3), dtype=np.float32)
        offsets[:, 0] = r * sin_theta * np.cos(phi)
        offsets[:, 1] = r * sin_theta * np.sin(phi)
        offsets[:, 2] = r * cos_theta
        return pos + offsets
    return _sample


def spawn_in_disc(radius: float, height: float = 0.0, center_from_camera=True):
    """Spawn in a flat disc — perfect for rain/snow around the player."""
    def _sample(parent, count, dt):
        cam = getattr(parent, '_cam_pos_ref', None)
        if center_from_camera and cam is not None:
            cx, cy, cz = cam
        else:
            cx, cy, cz = getattr(parent, 'position', (0, 0, 0))
        r = radius * np.sqrt(np.random.uniform(0, 1, count))
        a = np.random.uniform(0, 2*np.pi, count)
        pts = np.empty((count, 3), dtype=np.float32)
        pts[:, 0] = cx + r * np.cos(a)
        pts[:, 1] = cy + height
        pts[:, 2] = cz + r * np.sin(a)
        return pts
    return _sample


def spawn_from_list(points: list):
    def _sample(parent, count, dt):
        if not points:
            return None
        size = min(count, len(points))
        if size == 0:
            return None
        indices = np.random.choice(len(points), size=size, replace=False)
        return np.array([points[i] for i in indices], dtype=np.float32)
    return _sample


def get_ocean_foam_points(parent, count=128, threshold=0.6, camera_pos=None):
    gen = getattr(parent, '_fft_gen_cascade0', None)
    if gen is None:
        return []
        
    # Track camera for infinite ocean exploration
    search_center = camera_pos if camera_pos else getattr(parent, '_last_grid_origin', (0.0, 0.0, 0.0))
    cx, _, cz = getattr(parent, '_last_grid_origin', (0.0, 0.0, 0.0))
    ocean_y = float(getattr(parent, 'landscape_ocean_level', 0.0))
    N, L = int(gen.N), float(gen.L)
    radius = 200.0
    cand_count = count * 6
    pts_x = search_center[0] + np.random.uniform(-radius, radius, cand_count).astype(np.float32)
    pts_z = search_center[2] + np.random.uniform(-radius, radius, cand_count).astype(np.float32)
    u = ((pts_x - cx) / L + 0.5) % 1.0
    v = ((pts_z - cz) / L + 0.5) % 1.0
    ix, iy = (u * N).astype(np.int32) % N, (v * N).astype(np.int32) % N
    foam = getattr(gen, 'foam_buffer', None)
    if foam is None:
        jac = getattr(gen, 'last_jacobian_cpu', None)
        if jac is None:
            return []
        jac_vals = jac[iy, ix]
        foam_mask = jac_vals < (1.0 - threshold)
    else:
        foam_vals = foam[iy, ix]
        foam_mask = foam_vals > 0.05
    accepted = np.flatnonzero(foam_mask)[:count]
    if len(accepted) == 0:
        return []
    disp = getattr(gen, 'disp_data', None)
    out = []
    for idx in accepted:
        h = disp[iy[idx], ix[idx], 1] if disp is not None else 0.0
        out.append([float(pts_x[idx]), float(ocean_y + h + 0.2), float(pts_z[idx])])
    return out


def spawn_from_ocean_foam(threshold: float = 0.6, scatter_radius: float = 50.0,
                          fallback_to_crests: bool = True, unconditional: bool = False):
    def _sample(parent, count, dt):
        gen = getattr(parent, '_fft_gen_cascade0', None)
        if gen is None:
            return spawn_at_center()(parent, count, dt)
        cx, _, cz = getattr(parent, '_last_grid_origin', (0.0, 0.0, 0.0))
        ocean_y = float(getattr(parent, 'landscape_ocean_level', 0.0))
        N = int(gen.N); L = float(gen.L)
        wc_prop = getattr(parent, 'ocean_foam_whitecap_thresh', 0.5)
        wc_thresh = 0.60 + 0.30 * wc_prop
        cand = max(count * 12, 128)
        offsets = np.random.uniform(-scatter_radius, scatter_radius, (cand, 2)).astype(np.float32)
        wx = cx + offsets[:, 0]; wz = cz + offsets[:, 1]
        u = (wx / L) % 1.0; v = (wz / L) % 1.0
        ix = (u * N).astype(np.int32) % N; iy = (v * N).astype(np.int32) % N
        accepted = None
        disp = getattr(gen, 'disp_data', None)
        if unconditional:
            accepted = np.arange(len(wx))[:count]
        else:
            if disp is not None:
                intense = getattr(parent, 'ocean_wave_intensity', 1.0)
                h_scale = max(intense * 5.0, 1.0)
                heights = disp[iy, ix, 1]
                h_norm = np.clip((heights + h_scale) / (h_scale * 2.0), 0.0, 1.0)
                crest_mask = h_norm > wc_thresh
                accepted = np.flatnonzero(crest_mask)[:count]
            if (accepted is None or len(accepted) == 0):
                jac = getattr(gen, 'last_jacobian_cpu', None)
                if jac is not None:
                    jac_vals = jac[iy, ix]
                    foam_mask = jac_vals < (1.0 - threshold)
                    accepted = np.flatnonzero(foam_mask)[:count]
        if accepted is None or len(accepted) == 0:
            return None
        out = np.empty((len(accepted), 3), dtype=np.float32)
        out[:, 0] = wx[accepted]
        wave_h = disp[iy[accepted], ix[accepted], 1] if disp is not None else np.zeros(len(accepted), dtype=np.float32)
        out[:, 1] = ocean_y + wave_h + np.random.uniform(0.1, 0.4, len(accepted))
        out[:, 2] = wz[accepted]
        return out
    return _sample


def get_spawn_source(name: str, **kwargs):
    if name == "OceanFoam": return spawn_from_ocean_foam(**kwargs)
    if name == "Sphere":    return spawn_in_sphere(**kwargs)
    if name == "Disc":      return spawn_in_disc(**kwargs)
    return spawn_at_center(**kwargs)


# ---------------------------------------------------------------------------
# Presets — richer defaults for Fire/Smoke/Rain/Snow/Dust/Sparks
# ---------------------------------------------------------------------------

PARTICLE_PRESETS = {
    "Spray": {
        "rate": 2200, "life": 1.6,
        "max_count": 10000,
        "size_start": 0.7, "size_end": 0.25,
        "color_start": [0.95, 0.99, 1.0, 0.90],
        "color_end":   [0.75, 0.88, 0.98, 0.0],
        "forces": [{"type": "gravity",    "magnitude": 28.0},
                   {"type": "drag",       "coefficient": 0.75},
                   {"type": "turbulence", "strength": 0.6, "frequency": 0.4}],
        "speed_min": 9.0, "speed_max": 26.0, "velocity_cone": 0.55,
        "velocity_dir": [0.0, 1.0, 0.0],
        "stretch_length": 0.4,
        "render_mode": "billboard",
    },
    "Fire": {
        "rate": 140, "life": 1.1,
        "size_start": 0.5, "size_end": 0.08,
        "color_start": [1.0, 0.7, 0.2, 0.95],
        "color_end":   [0.15, 0.02, 0.0, 0.0],
        "forces": [{"type": "gravity", "magnitude": -3.5},
                   {"type": "turbulence", "strength": 1.2, "frequency": 0.5}],
        "blend_mode": "additive",
    },
    "Smoke": {
        "rate": 80, "life": 4.5,
        "size_start": 0.5, "size_end": 3.5,
        "color_start": [0.35, 0.35, 0.38, 0.7],
        "color_end":   [0.10, 0.10, 0.12, 0.0],
        "forces": [{"type": "gravity", "magnitude": -1.2},
                   {"type": "curl", "strength": 0.8, "frequency": 0.08}],
    },
    "Mist": {
        "rate": 300, "life": 3.0,
        "size_start": 1.0, "size_end": 2.5,
        "color_start": [0.8, 0.8, 0.9, 0.2],
        "color_end":   [0.8, 0.8, 0.9, 0.0],
    },
    "Blood": {
        "rate": 50, "life": 0.5,
        "size_start": 0.1, "size_end": 0.3,
        "color_start": [0.8, 0.0, 0.0, 0.9],
        "color_end":   [0.4, 0.0, 0.0, 0.0],
        "forces": [{"type": "gravity", "magnitude": 9.8}],
    },
    "Rain": {
        "rate": 3000, "life": 1.8,
        "max_count": 12000,
        "size_start": 0.04, "size_end": 0.04,
        "color_start": [0.7, 0.8, 0.95, 0.55],
        "color_end":   [0.7, 0.8, 0.95, 0.40],
        "velocity_dir": (0.05, -1.0, 0.0),
        "velocity_cone": 0.05,
        "speed_min": 22.0, "speed_max": 30.0,
        "forces": [{"type": "gravity", "magnitude": 15.0},
                   {"type": "wind", "vector": [1.0, 0.0, 0.3]}],
        "render_mode": "stretch", "stretch_length": 1.8,
        "stream_radius": 45.0, "cull_radius": 60.0,
        "receive_weather": True,
    },
    "Snow": {
        "rate": 900, "life": 10.0,
        "max_count": 8000,
        "size_start": 0.10, "size_end": 0.10,
        "color_start": [1.0, 1.0, 1.0, 0.85],
        "color_end":   [1.0, 1.0, 1.0, 0.80],
        "velocity_dir": (0.0, -1.0, 0.0),
        "velocity_cone": 0.4,
        "speed_min": 1.2, "speed_max": 2.4,
        "forces": [{"type": "gravity", "magnitude": 0.6},
                   {"type": "turbulence", "strength": 0.7, "frequency": 0.2}],
        "stream_radius": 55.0, "cull_radius": 80.0,
        "receive_weather": True,
    },
    "Sparks": {
        "rate": 400, "life": 0.9,
        "size_start": 0.08, "size_end": 0.01,
        "color_start": [1.0, 0.9, 0.4, 1.0],
        "color_end":   [1.0, 0.2, 0.0, 0.0],
        "velocity_cone": 1.2,
        "speed_min": 5.0, "speed_max": 14.0,
        "forces": [{"type": "gravity", "magnitude": 18.0},
                   {"type": "drag", "coefficient": 0.6}],
        "blend_mode": "additive",
        "render_mode": "stretch", "stretch_length": 0.8,
    },
    "Dust": {
        "rate": 60, "life": 6.0,
        "size_start": 0.3, "size_end": 0.9,
        "color_start": [0.6, 0.55, 0.45, 0.18],
        "color_end":   [0.6, 0.55, 0.45, 0.0],
        "forces": [{"type": "curl", "strength": 0.4, "frequency": 0.06}],
    },
}


def spec_from_preset(name: str, overrides: Optional[dict] = None) -> ParticleSpec:
    """Build a ParticleSpec from a named preset with optional overrides."""
    d = dict(PARTICLE_PRESETS.get(name, {}))
    if overrides:
        d.update({k: v for k, v in overrides.items() if v is not None})
    spec = ParticleSpec()
    for k, v in d.items():
        if hasattr(spec, k):
            setattr(spec, k, v)
    return spec


# ---------------------------------------------------------------------------
# Sprite renderer — enhanced instance layout + stretch mode
# ---------------------------------------------------------------------------

_SPRITE_VS = """
#version 330 compatibility
layout(location=0) in vec2 quad_pos;
layout(location=1) in vec3 inst_pos;
layout(location=2) in float inst_size;
layout(location=3) in vec4 inst_color;
layout(location=4) in float inst_seed;
layout(location=5) in vec3 inst_vel;

uniform vec3 cam_right;
uniform vec3 cam_up;
uniform int  render_mode; // 0=billboard, 1=stretch
uniform float stretch_len;

out vec2 v_uv;
out vec4 v_color;
out float v_seed;
out vec3 v_world_pos;

void main() {
    vec3 right = cam_right;
    vec3 up    = cam_up;
    if (render_mode == 1) {
        // stretched rain/sparks: align long axis with velocity
        vec3 v = inst_vel;
        float vmag = length(v);
        if (vmag > 0.01) {
            up = v / vmag;
            // Cross velocity with cam_forward to ensure quad always faces camera
            vec3 cam_fwd = normalize(cross(cam_right, cam_up));
            right = normalize(cross(up, cam_fwd));
            if (length(right) < 0.001) right = cam_right;
        }
    }
    float sx = inst_size;
    float sy = (render_mode == 1) ? inst_size * stretch_len * 6.0 : inst_size;
    vec3 wpos = inst_pos
              + right * (quad_pos.x * sx)
              + up    * (quad_pos.y * sy);

    gl_Position = gl_ModelViewProjectionMatrix * vec4(wpos, 1.0);
    v_uv    = quad_pos + 0.5;
    v_color = inst_color;
    v_seed  = inst_seed;
    v_world_pos = wpos;
}
"""

_SPRITE_FS = """
#version 330 compatibility
in vec2 v_uv;
in vec4 v_color;
in float v_seed;
in vec3 v_world_pos;
out vec4 frag;

uniform int render_mode;
uniform float u_kill_height;

void main() {
    float kill_h = u_kill_height;
    if (v_world_pos.y < kill_h) discard;
    vec2 d = v_uv - vec2(0.5);
    float dist = length(d);
    
    if (render_mode == 0) {
        // --- SPLASH / DROPLET SHADER ---
        // Base droplet shape
        if (dist > 0.5) discard;
        
        // Elongate and distort based on seed + noise for a 'splash' look
        float angle = atan(d.y, d.x);
        float noise = sin(angle * 8.0 + v_seed * 10.0) * 0.15;
        float splash_dist = length(d * vec2(1.0, 1.4)) + noise;
        
        if (splash_dist > 0.48) discard;

        float ripple = 1.0 - smoothstep(0.35, 0.5, dist);
        float edge   = pow(dist * 2.0, 4.0);
        float core   = smoothstep(0.0, 0.25, dist);
        
        vec3 col = v_color.rgb * (0.82 + 0.18 * core);
        
        // Stronger glints for splashes
        float glint = pow(max(0.0, sin(v_seed * 20.0 + dist * 35.0)), 40.0);
        col += glint * 1.5;
        
        float a = v_color.a * (1.0 - edge) * ripple;
        if (a <= 0.01) discard;
        frag = vec4(col, a);
    } else {
        // stretched strand — narrow along u, soft along v
        float u = abs(d.x) * 2.0;
        float v = abs(d.y) * 2.0;
        if (u > 1.0 || v > 1.0) discard;
        float fall = (1.0 - u*u) * (1.0 - pow(v, 3.0));
        float a = v_color.a * fall;
        if (a <= 0.01) discard;
        frag = vec4(v_color.rgb, a);
    }
}
"""


class _SpriteRenderer:
    def __init__(self):
        from py_editor.ui.shader_manager import ShaderProgram
        self.shader = ShaderProgram(_SPRITE_VS, _SPRITE_FS)
        quad = np.array([
            -0.5, -0.5,
             0.5, -0.5,
            -0.5,  0.5,
             0.5,  0.5,
        ], dtype=np.float32)
        self.vao = glGenVertexArrays(1)
        glBindVertexArray(self.vao)

        self.quad_vbo = glGenBuffers(1)
        glBindBuffer(GL_ARRAY_BUFFER, self.quad_vbo)
        glBufferData(GL_ARRAY_BUFFER, quad.nbytes, quad, GL_STATIC_DRAW)
        glEnableVertexAttribArray(0)
        glVertexAttribPointer(0, 2, GL_FLOAT, GL_FALSE, 0, None)

        self.inst_vbo = glGenBuffers(1)
        self._inst_capacity = 0
        glBindBuffer(GL_ARRAY_BUFFER, self.inst_vbo)
        # 12 floats: pos(3) size(1) color(4) seed(1) vel(3)
        stride = 12 * 4
        glEnableVertexAttribArray(1); glVertexAttribPointer(1, 3, GL_FLOAT, GL_FALSE, stride, ctypes_offset(0));  glVertexAttribDivisor(1, 1)
        glEnableVertexAttribArray(2); glVertexAttribPointer(2, 1, GL_FLOAT, GL_FALSE, stride, ctypes_offset(3*4));  glVertexAttribDivisor(2, 1)
        glEnableVertexAttribArray(3); glVertexAttribPointer(3, 4, GL_FLOAT, GL_FALSE, stride, ctypes_offset(4*4));  glVertexAttribDivisor(3, 1)
        glEnableVertexAttribArray(4); glVertexAttribPointer(4, 1, GL_FLOAT, GL_FALSE, stride, ctypes_offset(8*4));  glVertexAttribDivisor(4, 1)
        glEnableVertexAttribArray(5); glVertexAttribPointer(5, 3, GL_FLOAT, GL_FALSE, stride, ctypes_offset(9*4));  glVertexAttribDivisor(5, 1)
        glBindVertexArray(0)
        glBindBuffer(GL_ARRAY_BUFFER, 0)

    def draw(self, instance_data, camera_pos, blend_mode, render_mode="billboard", stretch_length=0.6):
        n = len(instance_data)
        if n == 0:
            return
        mv = glGetFloatv(GL_MODELVIEW_MATRIX)
        if hasattr(mv, "reshape"):
            mv = mv.reshape((4, 4))
            cam_right = np.array([mv[0][0], mv[1][0], mv[2][0]], dtype=np.float32)
            cam_up    = np.array([mv[0][1], mv[1][1], mv[2][1]], dtype=np.float32)
        else:
            cam_right = np.array([mv[0], mv[4], mv[8]], dtype=np.float32)
            cam_up    = np.array([mv[1], mv[5], mv[9]], dtype=np.float32)

        glBindBuffer(GL_ARRAY_BUFFER, self.inst_vbo)
        if n > self._inst_capacity:
            glBufferData(GL_ARRAY_BUFFER, instance_data.nbytes, instance_data, GL_DYNAMIC_DRAW)
            self._inst_capacity = n
        else:
            glBufferSubData(GL_ARRAY_BUFFER, 0, instance_data.nbytes, instance_data)
        glBindBuffer(GL_ARRAY_BUFFER, 0)

        glEnable(GL_BLEND)
        if blend_mode == "additive":
            glBlendFunc(GL_SRC_ALPHA, GL_ONE)
        else:
            glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glDepthMask(GL_FALSE)
        glEnable(GL_DEPTH_TEST)

        self.shader.use()
        self.shader.set_uniform_v3("cam_right", *cam_right)
        self.shader.set_uniform_v3("cam_up",    *cam_up)
        self.shader.set_uniform_i("render_mode", 1 if render_mode == "stretch" else 0)
        self.shader.set_uniform_f("stretch_len", float(stretch_length))
        self.shader.set_uniform_f("u_kill_height", float(getattr(self, '_current_kill_height', -10000.0)))

        glBindVertexArray(self.vao)
        glDrawArraysInstanced(GL_TRIANGLE_STRIP, 0, 4, n)
        
        # Restore state
        glUseProgram(0)
        glDepthMask(GL_TRUE)
        glBindVertexArray(0)
        # Never disable global states like BLEND or DEPTH here, 
        # as the main viewport may rely on them being handled by the scene logic.


def ctypes_offset(offset: int):
    import ctypes
    return ctypes.c_void_p(offset)
