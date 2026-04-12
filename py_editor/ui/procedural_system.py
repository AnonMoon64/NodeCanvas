"""
procedural_system.py

Helpers for landscape primitives and spawning instances.
This module is intentionally lightweight and avoids importing SceneEditor
at module import time to prevent circular imports. Functions import
helpers from `scene_editor` only when they're executed at runtime.
"""
import math
import random
import threading
import concurrent.futures
import numpy as np
from pathlib import Path
from typing import List, Tuple, Union


class VectorizedNoise:
    """NumPy-optimized noise engine for high-performance landscape generation."""
    def __init__(self, seed=0):
        # Use a local RNG to avoid global state side-effects
        rng = np.random.RandomState(seed)
        self.p = np.arange(256, dtype=int)
        rng.shuffle(self.p)
        self.p = np.tile(self.p, 2)
        
    def fade(self, t): return t * t * t * (t * (t * 6 - 15) + 10)
    
    def lerp(self, t, a, b): return a + t * (b - a)
    
    def grad(self, hash, x, y):
        h = hash & 15
        u = np.where(h < 8, x, y)
        v = np.where(h < 4, y, np.where((h == 12) | (h == 14), x, 0))
        return np.where(h & 1 == 0, u, -u) + np.where(h & 2 == 0, v, -v)

    def noise(self, x, y):
        # Optimized for NumPy arrays
        X = np.floor(x).astype(int) & 255
        Y = np.floor(y).astype(int) & 255
        x = x - np.floor(x); y = y - np.floor(y)
        u, v = self.fade(x), self.fade(y)
        A = self.p[X] + Y
        B = self.p[X + 1] + Y
        
        # We need to ensure we don't index out of bounds even with tile(2)
        # B+1 can be 255+1+255 = 511, which fits in 512.
        res = self.lerp(v, self.lerp(u, self.grad(self.p[self.p[A]], x, y), 
                                        self.grad(self.p[self.p[B]], x-1, y)),
                            self.lerp(u, self.grad(self.p[self.p[A+1]], x, y-1), 
                                        self.grad(self.p[self.p[B+1]], x-1, y-1)))
        return res

class PerlinNoise:
    """Legacy single-point Perlin noise (kept for sparse spawning)."""
    def __init__(self, seed=0):
        self.p = list(range(256))
        random.seed(seed)
        random.shuffle(self.p); self.p += self.p
    def lerp(self, t, a, b): return a + t * (b - a)
    def fade(self, t): return t * t * t * (t * (t * 6 - 15) + 10)
    def grad(self, hash, x, y):
        h = hash & 15; u = x if h < 8 else y
        v = y if h < 4 else (x if h in [12, 14] else 0)
        return (u if (h & 1) == 0 else -u) + (v if (h & 2) == 0 else -v)
    def noise(self, x, y):
        X = int(math.floor(x)) & 255; Y = int(math.floor(y)) & 255
        x -= math.floor(x); y -= math.floor(y); u, v = self.fade(x), self.fade(y)
        A = self.p[X]+Y; B = self.p[X+1]+Y
        return self.lerp(v, self.lerp(u, self.grad(self.p[self.p[A]], x, y), self.grad(self.p[self.p[B]], x-1, y)),
                           self.lerp(u, self.grad(self.p[self.p[A+1]], x, y-1), self.grad(self.p[self.p[B+1]], x-1, y-1)))

class SimplexNoise:
    """Standard 2D Simplex noise implementation."""
    def __init__(self, seed=0):
        self.p = list(range(256))
        random.seed(seed)
        random.shuffle(self.p)
        self.p += self.p
        self.grad3 = [(1,1,0),(-1,1,0),(1,-1,0),(-1,-1,0),(1,0,1),(-1,0,1),(1,0,-1),(-1,0,-1),(0,1,1),(0,-1,1),(0,1,-1),(0,-1,-1)]

    def dot(self, g, x, y): return g[0]*x + g[1]*y
    def fade(self, t): return t * t * t * (t * (t * 6 - 15) + 10)

    def noise(self, xin, yin):
        F2 = 0.5*(math.sqrt(3.0)-1.0); s = (xin+yin)*F2; i = int(math.floor(xin+s)); j = int(math.floor(yin+s))
        G2 = (3.0-math.sqrt(3.0))/6.0; t = (i+j)*G2; X0 = i-t; Y0 = j-t; x0 = xin-X0; y0 = yin-Y0
        if x0 > y0: i1=1; j1=0
        else: i1=0; j1=1
        x1 = x0 - i1 + G2; y1 = y0 - j1 + G2; x2 = x0 - 1.0 + 2.0*G2; y2 = y0 - 1.0 + 2.0*G2
        ii = i & 255; jj = j & 255; gi0 = self.p[ii+self.p[jj]] % 12; gi1 = self.p[ii+i1+self.p[jj+j1]] % 12; gi2 = self.p[ii+1+self.p[jj+1]] % 12
        t0 = 0.5 - x0*x0 - y0*y0
        if t0 < 0: n0 = 0.0
        else: t0 *= t0; n0 = t0 * t0 * self.dot(self.grad3[gi0], x0, y0)
        t1 = 0.5 - x1*x1 - y1*y1
        if t1 < 0: n1 = 0.0
        else: t1 *= t1; n1 = t1 * t1 * self.dot(self.grad3[gi1], x1, y1)
        t2 = 0.5 - x2*x2 - y2*y2
        if t2 < 0: n2 = 0.0
        else: t2 *= t2; n2 = t2 * t2 * self.dot(self.grad3[gi2], x2, y2)
        return 70.0 * (n0 + n1 + n2)

class WorleyNoise:
    """Optimized grid-based Worley (Cellular) noise."""
    def __init__(self, seed=0):
        self.seed = seed
        self.points_cache = {} # (cell_x, cell_z) -> [(px, pz)]

    def get_points(self, cx, cz):
        if (cx, cz) not in self.points_cache:
            # Use a deterministic hash to prevent seams between chunks in different sessions
            # Python's built-in hash() is randomized per process
            h = (cx * 73856093 ^ cz * 19349663 ^ self.seed * 83492791) & 0xFFFFFFFF
            st = random.getstate()
            random.seed(h)
            self.points_cache[(cx, cz)] = [(random.random(), random.random()) for _ in range(random.randint(1,2))]
            random.setstate(st)
        return self.points_cache[(cx, cz)]

    def noise(self, x, z):
        cx, cz = int(math.floor(x)), int(math.floor(z))
        min_dist = 10.0
        for i in range(-1, 2):
            for j in range(-1, 2):
                pts = self.get_points(cx + i, cz + j)
                for px, pz in pts:
                    dx = (cx + i + px) - x
                    dz = (cz + j + pz) - z
                    dist = math.sqrt(dx*dx + dz*dz)
                    if dist < min_dist: min_dist = dist
        return min_dist # 0 to ~1.4

_noise_cache = {}
_noise_lock = threading.Lock()
_landscape_display_list_cache = {} # (ox, oz, sw, sd, rows, cols, seed, layers_hash) -> list_id
_pending_chunks = {} # cache_key -> future
_completed_chunk_data = {} # cache_key -> (grid_h, grid_nx, grid_ny, grid_nz)
_gen_executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)

def get_noise(seed: int, ntype: str = "perlin", vectorized: bool = False) -> object:
    key = (seed, ntype, vectorized)
    with _noise_lock:
        if key not in _noise_cache:
            if vectorized:
                _noise_cache[key] = VectorizedNoise(seed)
            else:
                if ntype == "perlin": _noise_cache[key] = PerlinNoise(seed)
                elif ntype == "simplex": _noise_cache[key] = SimplexNoise(seed)
                elif ntype == "worley": _noise_cache[key] = WorleyNoise(seed)
                else: _noise_cache[key] = PerlinNoise(seed)
        return _noise_cache[key]


def sample_height(x: Union[float, np.ndarray], z: Union[float, np.ndarray], obj=None) -> Union[float, np.ndarray]:
    """Sample procedural height by accumulating multiple noise layers.
    Supports both single points and vectorized NumPy arrays.
    """
    if obj is None: return 0.0 if isinstance(x, float) else np.zeros_like(x)
    
    if getattr(obj, 'landscape_type', 'procedural') == 'flat':
        return 0.0 if isinstance(x, float) else np.zeros_like(x)

    layers = getattr(obj, 'landscape_noise_layers', [])
    if not layers: return 0.0 if isinstance(x, float) else np.zeros_like(x)

    is_vec = isinstance(x, np.ndarray)
    total_h = np.zeros_like(x) if is_vec else 0.0
    base_seed = getattr(obj, 'landscape_seed', 123)
    
    for layer in layers:
        amp = layer.get('amp', 1.0)
        freq = layer.get('freq', 1.0)
        off = layer.get('offset', [0.0, 0.0])
        octaves = layer.get('octaves', 1)
        ntype = layer.get('type', 'perlin')
        persistence = layer.get('persistence', 0.5)
        lacunarity = layer.get('lacunarity', 2.0)
        exponent = layer.get('exponent', 1.0)
        mode = layer.get('mode', 'fbm') # fbm, ridged, billow
        
        layer_h = np.zeros_like(x) if is_vec else 0.0
        cur_amp = amp; cur_freq = freq
        pn = get_noise(base_seed, ntype, vectorized=is_vec)
        
        for _ in range(octaves):
            vx, vz = (x + off[0]) * cur_freq, (z + off[1]) * cur_freq
            val = pn.noise(vx, vz)
            
            if mode == 'ridged':
                val = 1.0 - np.abs(val) if is_vec else 1.0 - abs(val)
                val = val * val # Extra sharpness
            elif mode == 'billow':
                val = np.abs(val) if is_vec else abs(val)

            layer_h += val * cur_amp
            cur_amp *= persistence
            cur_freq *= lacunarity
            
        # Power redistribution (The 'Realism' trick)
        if exponent != 1.0:
            if is_vec:
                layer_h = np.sign(layer_h) * (np.abs(layer_h) ** exponent)
            else:
                layer_h = (math.copysign(1, layer_h) * (abs(layer_h) ** exponent))
                
        # Apply layer weight
        weight = layer.get('weight', 1.0)
        total_h += layer_h * weight
        
    # Rebase for Ocean level (0.0 will be the shoreline)
    ocean_level = getattr(obj, 'landscape_ocean_level', 0.1)
    total_h -= ocean_level

    # Ocean Flattening (Apply only to negative depths)
    ocean_flattening = getattr(obj, 'landscape_ocean_flattening', 0.3)
    if is_vec:
        total_h = np.where(total_h < 0, total_h * ocean_flattening, total_h)
    else:
        if total_h < 0:
            total_h *= ocean_flattening
            
    # Apply global height scale last
    height_scale = getattr(obj, 'landscape_height_scale', 30.0)
    total_h *= height_scale

    return total_h


def generate_grid_heights(obj, width: float, depth: float, rows: int, cols: int):
    """Generate vertex heights for a grid covering +/- width/2 x +/- depth/2.

    Returns a (rows+1) x (cols+1) list of heights.
    """
    heights = [[0.0 for _ in range(cols + 1)] for _ in range(rows + 1)]
    if rows <= 0 or cols <= 0:
        return heights
    sx = float(width); sz = float(depth)
    for r in range(rows + 1):
        for c in range(cols + 1):
            x = (c / max(cols, 1) - 0.5) * sx
            z = (r / max(rows, 1) - 0.5) * sz
            heights[r][c] = sample_height(x, z, obj)
    return heights


def _compute_normal(x0, y0, z0, x1, y1, z1, x2, y2, z2):
    ux, uy, uz = x1-x0, y1-y0, z1-z0
    vx, vy, vz = x2-x0, y2-y0, z2-z0
    nx = uy * vz - uz * vy
    ny = uz * vx - ux * vz
    nz = ux * vy - uy * vx
    l = math.sqrt(nx*nx + ny*ny + nz*nz)
    if l < 1e-9: return (0.0, 1.0, 0.0)
    return (nx/l, ny/l, nz/l)




def get_climate(x: float, z: float, height: float, obj) -> Tuple[float, float]:
    """Calculate temperature and humidity at a given location.
    Temp = 1.0 - elevation*0.5 - abs(z)*0.0001 (Latitudinal drop)
    Humidity = noise(x, z) - elevation*0.2
    """
    base_seed = getattr(obj, 'landscape_seed', 123)
    # Use a fixed offset or hashed seed for humidity to distinguish it from height
    humidity_pn = get_noise(base_seed + 999, "perlin")
    
    # 1. Temperature logic
    # Scale latitudinal drop over 2500 units for larger world feel
    lat_factor = abs(z) * (1.0 / 2500.0) 
    elevation_factor = max(0.0, height) * 0.01 
    temp = 1.0 - lat_factor - elevation_factor
    temp = max(0.0, min(1.0, temp))
    
    # 2. Humidity logic
    # Fluctuates via noise, drops slightly at high altitude
    hum_noise = (humidity_pn.noise(x * 0.01, z * 0.01) + 1.0) * 0.5 
    humidity = hum_noise - (elevation_factor * 0.5)
    humidity = max(0.0, min(1.0, humidity))
    
    return temp, humidity

def get_biome_at(obj, height: float, slope: float, x: float, z: float) -> dict:
    """Return the biome configuration for a given height, slope, temperature, and humidity."""
    biomes = getattr(obj, 'landscape_biomes', [])
    temp, hum = get_climate(x, z, height, obj)
    
    if not biomes:
        return {
            'name': 'Default',
            'height_range': [-1000.0, 1000.0], 'slope_range': [0.0, 1.0],
            'temp_range': [0.0, 1.0], 'hum_range': [0.0, 1.0],
            'surface': {'color': [0.5, 0.5, 0.5, 1.0], 'roughness': 0.7, 'metallic': 0.0},
            'spawns': []
        }
    
    for b in biomes:
        h_range = b.get('height_range', [-1000.0, 1000.0])
        s_range = b.get('slope_range', [0.0, 1.0])
        t_range = b.get('temp_range', [0.0, 1.0])
        hm_range = b.get('hum_range', [0.0, 1.0])
        
        if (h_range[0] <= height <= h_range[1] and 
            s_range[0] <= slope <= s_range[1] and
            t_range[0] <= temp <= t_range[1] and
            hm_range[0] <= hum <= hm_range[1]):
            return b
            
    return biomes[0] if biomes else {
        'surface': {'color': [0.5, 0.5, 0.5, 1.0]}
    }

def draw_landscape_3d(obj, viewport):
    """Draw a landscape for the given object into the current GL context."""
    try:
        from OpenGL.GL import (
            glBegin, glEnd, glVertex3f, glNormal3f, glColor4f,
            glEnable, glDisable, glCullFace, glPolygonOffset, glDepthMask, glMaterialfv, glMaterialf,
            glGenLists, glNewList, glEndList, glCallList, glDeleteLists,
            GL_QUADS, GL_CULL_FACE, GL_BACK, GL_POLYGON_OFFSET_FILL, GL_DEPTH_TEST, GL_TRUE,
            GL_FRONT_AND_BACK, GL_AMBIENT_AND_DIFFUSE, GL_SPECULAR, GL_SHININESS, GL_EMISSION, GL_COMPILE
        )
    except Exception:
        return

    glEnable(GL_DEPTH_TEST); glDepthMask(GL_TRUE)
    bias = float(getattr(obj, 'landscape_render_bias', -0.02))
    size_mode = getattr(obj, 'landscape_size_mode', 'finite')

    # CHUNKED RENDERING SETTINGS
    chunk_size = float(getattr(obj, 'landscape_chunk_size', 128.0))
    CHUNK_RES = int(getattr(obj, 'landscape_resolution', 32))
    
    glEnable(GL_CULL_FACE); glCullFace(GL_BACK)
    try:
        glEnable(GL_POLYGON_OFFSET_FILL); glPolygonOffset(2.0, 2.0)
    except Exception:
        pass

    def _generate_chunk_data_task(ox, oz, sw, sd, rows, cols, obj, bias):
        """Background task for heavy NumPy noise calculations."""
        # 1. VECTORIZED GENERATION (FAST)
        c_range = np.linspace(-0.5, 0.5, cols + 1) * sw
        r_range = np.linspace(-0.5, 0.5, rows + 1) * sd
        C, R = np.meshgrid(c_range, r_range)
        
        # Batch sample heights
        grid_h = sample_height(ox + C, oz + R, obj) + bias
        
        # Batch sample smooth normals using finite differences
        eps = 0.5
        h_r = sample_height(ox + C + eps, oz + R, obj) + bias
        h_l = sample_height(ox + C - eps, oz + R, obj) + bias
        h_u = sample_height(ox + C, oz + R + eps, obj) + bias
        h_d = sample_height(ox + C, oz + R - eps, obj) + bias
        
        nx = (h_l - h_r) / (2 * eps)
        nz = (h_d - h_u) / (2 * eps)
        ny = np.ones_like(nx)
        mag = np.sqrt(nx**2 + ny**2 + nz**2)
        return grid_h, nx/mag, ny/mag, nz/mag, c_range, r_range

    def _render_chunk(ox, oz, sw, sd, rows, cols):
        """Render a single terrain grid using background generation and Display List caching."""
        seed = getattr(obj, 'landscape_seed', 123)
        layers = getattr(obj, 'landscape_noise_layers', [])
        h_scale = getattr(obj, 'landscape_height_scale', 30.0)
        o_level = getattr(obj, 'landscape_ocean_level', 0.08)
        o_flat = getattr(obj, 'landscape_ocean_flattening', 0.3)
        
        # Hash all visual parameters to ensure cache invalidation on adjustment
        layers_hash = hash(str(layers) + str(h_scale) + str(o_level) + str(o_flat))
        cache_key = (ox, oz, sw, sd, rows, cols, seed, layers_hash)
        
        # 1. ALREADY CACHED IN VRAM? (FAST)
        if cache_key in _landscape_display_list_cache:
            glCallList(_landscape_display_list_cache[cache_key])
            return

        # 2. DATA READY FOR COMPILATION? (MAIN THREAD ONLY)
        if cache_key in _completed_chunk_data:
            grid_h, gnx, gny, gnz, c_range, r_range = _completed_chunk_data.pop(cache_key)
            list_id = glGenLists(1)
            glNewList(list_id, GL_COMPILE)
            
            viz_climate = getattr(obj, 'visualize_climate', False)
            glBegin(GL_QUADS)
            for r in range(rows):
                for c in range(cols):
                    lx0, lz0 = c_range[c], r_range[r]
                    lx1, lz1 = c_range[c+1], r_range[r+1]
                    y00, y10, y11, y01 = grid_h[r, c], grid_h[r, c+1], grid_h[r+1, c+1], grid_h[r+1, c]
                    nx00, ny00, nz00 = gnx[r, c], gny[r, c], gnz[r, c]
                    nx10, ny10, nz10 = gnx[r, c+1], gny[r, c+1], gnz[r, c+1]
                    nx11, ny11, nz11 = gnx[r+1, c+1], gny[r+1, c+1], gnz[r+1, c+1]
                    nx01, ny01, nz01 = gnx[r+1, c], gny[r+1, c], gnz[r+1, c]

                    wx, wz = ox + (lx0+lx1)*0.5, oz + (lz0+lz1)*0.5
                    slope = 1.0 - (ny00 + ny10 + ny11 + ny01) * 0.25
                    
                    if viz_climate:
                        temp, hum = get_climate(wx, wz, y00, obj)
                        # Smooth Multi-Point Gradient: Blue (Cold) -> Green (Neutral) -> Red (Hot)
                        # This ensures no sharp snapping borders
                        if temp < 0.5:
                            # 0.0 (Blue) -> 0.5 (Green)
                            t = temp * 2.0
                            bc = [0.0, t, 1.0 - t, 1.0]
                        else:
                            # 0.5 (Green) -> 1.0 (Red)
                            t = (temp - 0.5) * 2.0
                            bc = [t, 1.0 - t, 0.0, 1.0]
                        glColor4f(*bc)
                    else:
                        biome = get_biome_at(obj, y00, slope, wx, wz)
                        surf = biome.get('surface', {})
                        bc = surf.get('color', [0.5, 0.5, 0.5, 1.0])
                        try:
                            glMaterialfv(GL_FRONT_AND_BACK, GL_AMBIENT_AND_DIFFUSE, bc)
                            glMaterialfv(GL_FRONT_AND_BACK, GL_SPECULAR, (0.2, 0.2, 0.2, 1.0))
                        except Exception:
                            glColor4f(*bc)

                    glNormal3f(nx00, ny00, nz00); glVertex3f(ox + lx0, y00, oz + lz0)
                    glNormal3f(nx01, ny01, nz01); glVertex3f(ox + lx0, y01, oz + lz1)
                    glNormal3f(nx11, ny11, nz11); glVertex3f(ox + lx1, y11, oz + lz1)
                    glNormal3f(nx10, ny10, nz10); glVertex3f(ox + lx1, y10, oz + lz0)
            glEnd()
            glEndList()
            _landscape_display_list_cache[cache_key] = list_id
            glCallList(list_id)
            return

        # 3. PENDING IN BACKGROUND?
        if cache_key in _pending_chunks:
            future = _pending_chunks[cache_key]
            if future.done():
                try:
                    _completed_chunk_data[cache_key] = future.result()
                    del _pending_chunks[cache_key]
                    # Don't recursive call, just wait for next frame or fall back to placeholder
                except Exception as e:
                    print(f"Chunk gen error: {e}")
                    del _pending_chunks[cache_key]
            
            # Show Placeholder (Flat Plate)
            glColor4f(0.2, 0.25, 0.2, 1.0)
            glBegin(GL_QUADS)
            glNormal3f(0,1,0)
            glVertex3f(ox-sw*0.5, bias, oz-sd*0.5)
            glVertex3f(ox-sw*0.5, bias, oz+sd*0.5)
            glVertex3f(ox+sw*0.5, bias, oz+sd*0.5)
            glVertex3f(ox+sw*0.5, bias, oz-sd*0.5)
            glEnd()
            return

        # 4. START NEW GENERATION TASK
        _pending_chunks[cache_key] = _gen_executor.submit(_generate_chunk_data_task, ox, oz, sw, sd, rows, cols, obj, bias)
        return

    if size_mode == 'infinite':
        # Infinite mode: render a grid of chunks around camera based on radius
        cp = getattr(viewport._cam3d, 'pos', [0,0,0])
        rad = int(getattr(obj, 'landscape_grid_radius', 1))
        # Grid snapping for chunk selection
        cx = round(cp[0] / chunk_size) * chunk_size
        cz = round(cp[2] / chunk_size) * chunk_size
        
        for ix in range(-rad, rad + 1):
            for iz in range(-rad, rad + 1):
                ox = cx + ix * chunk_size
                oz = cz + iz * chunk_size
                _render_chunk(ox, oz, chunk_size, chunk_size, CHUNK_RES, CHUNK_RES)
    else:
        # Finite mode: render a single chunk at object position of chunk_size
        _render_chunk(0.0, 0.0, chunk_size, chunk_size, CHUNK_RES, CHUNK_RES)

    try: glDisable(GL_POLYGON_OFFSET_FILL)
    except Exception: pass
    glDisable(GL_CULL_FACE)

def spawn_instances(viewport, land_obj, cam_pos=None):
    """Spawn instances across the landscape. Handles both Finite (static) and Infinite (rolling) modes."""
    if not getattr(land_obj, 'landscape_spawn_enabled', False):
        return []

    from .scene_editor import SceneObject
    size_mode = getattr(land_obj, 'landscape_size_mode', 'finite')
    bias = float(getattr(land_obj, 'landscape_render_bias', -0.02))
    seed = getattr(land_obj, 'landscape_seed', 123)
    
    if size_mode == 'infinite':
        if cam_pos is None:
            return []
            
        # Initialize tracking on land_obj
        if not hasattr(land_obj, '_spawned_chunks'):
            land_obj._spawned_chunks = {} # (gx, gz) -> [ids]

        chunk_size = float(getattr(land_obj, 'landscape_chunk_size', 128.0))
        rad = int(getattr(land_obj, 'landscape_grid_radius', 1))
        gx_center = round(cam_pos[0] / chunk_size)
        gz_center = round(cam_pos[2] / chunk_size)
        
        current_coords = set()
        for ix in range(-rad, rad + 1):
            for iz in range(-rad, rad + 1):
                current_coords.add((int(gx_center + ix), int(gz_center + iz)))
        
        # 1. Despawn chunks out of range
        to_despawn = [c for c in land_obj._spawned_chunks if c not in current_coords]
        for c in to_despawn:
            ids = land_obj._spawned_chunks.pop(c)
            # Remove objects matched by ID
            viewport.scene_objects[:] = [o for o in viewport.scene_objects if o.id not in ids]
            
        # 2. Spawn new chunks
        for c in current_coords:
            if c in land_obj._spawned_chunks:
                continue
            
            gx, gz = c
            ox, oz = gx * chunk_size, gz * chunk_size
            
            # Sparse spawning for performance
            rows, cols = 6, 6
            spx, spz = chunk_size/max(1,cols), chunk_size/max(1,rows)
            base_x = ox - chunk_size*0.5
            base_z = oz - chunk_size*0.5
            
            chunk_ids = []
            for r in range(rows):
                for c_idx in range(cols):
                    wx = base_x + c_idx * spx
                    wz = base_z + r * spz
                    h = sample_height(wx, wz, land_obj)
                    
                    # Slope
                    eps = 0.5
                    h_nx = sample_height(wx + eps, wz, land_obj)
                    h_nz = sample_height(wx, wz + eps, land_obj)
                    nx = -(h_nx - h) / eps; nz = -(h_nz - h) / eps
                    ny = 1.0; l = math.sqrt(nx*nx + 1.0 + nz*nz); ny /= l
                    slope = 1.0 - ny
                    
                    biome = get_biome_at(land_obj, h, slope, wx, wz)
                    spawns = biome.get('spawns', [])
                    random.seed(hash((wx, wz, seed)) % 1000000)
                    
                    for layer in spawns:
                        assets = layer.get('assets', [])
                        density = layer.get('density', 0.1)
                        if not assets or random.random() > density: continue
                        
                        asset = random.choice(assets)
                        wy = land_obj.position[1] + h + bias
                        off_x = (random.random()-0.5)*spx
                        off_z = (random.random()-0.5)*spz
                        
                        o = SceneObject(Path(asset).stem, 'mesh', [wx+off_x, wy, wz+off_z], [0, random.random()*360, 0], [1,1,1])
                        o.file_path = asset
                        o.is_procedural = True # Mark as procedural so it doesn't save to file
                        viewport.scene_objects.append(o)
                        chunk_ids.append(o.id)
            
            land_obj._spawned_chunks[c] = chunk_ids
        return []

    else:
        # FINITE MODE
        if getattr(land_obj, '_landscape_spawned', False):
            return getattr(land_obj, '_landscape_spawned_ids', [])

        created = []
        rows = max(1, int(getattr(land_obj, 'landscape_spawn_rows', 1)))
        cols = max(1, int(getattr(land_obj, 'landscape_spawn_cols', 1)))
        self.landscape_spawn_spacing = [10.0, 10.0] # Increased default spacing
        self.visualize_climate = False
        spx, spz = getattr(land_obj, 'landscape_spawn_spacing', [10.0, 10.0])
        
        base_x = land_obj.position[0] - (cols - 1) * spx * 0.5
        base_z = land_obj.position[2] - (rows - 1) * spz * 0.5
        
        for r in range(rows):
            for c_idx in range(cols):
                wx = base_x + c_idx * spx
                wz = base_z + r * spz
                h = sample_height(wx - land_obj.position[0], wz - land_obj.position[2], land_obj)
                
                eps = 0.5
                h_nx = sample_height(wx - land_obj.position[0] + eps, wz - land_obj.position[2], land_obj)
                h_nz = sample_height(wx - land_obj.position[0], wz - land_obj.position[2] + eps, land_obj)
                nx = -(h_nx - h) / eps; nz = -(h_nz - h) / eps
                ny = 1.0; l = math.sqrt(nx*nx + 1.0 + nz*nz); ny /= l
                slope = 1.0 - ny
                
                biome = get_biome_at(land_obj, h, slope, wx, wz)
                biome_spawns = biome.get('spawns', [])
                
                random.seed(hash((wx, wz, seed)) % 1000000)
                for layer in biome_spawns:
                    assets = layer.get('assets', [])
                    density = layer.get('density', 0.1)
                    if not assets or random.random() > density: continue
                    
                    asset = random.choice(assets)
                    wy = land_obj.position[1] + h + bias
                    off_x = (random.random() - 0.5) * spx * 0.5
                    off_z = (random.random() - 0.5) * spz * 0.5
                    
                    o = SceneObject(Path(asset).stem, 'mesh', [wx + off_x, wy, wz + off_z], [0.0, random.random() * 360.0, 0.0], [1.0, 1.0, 1.0])
                    o.file_path = asset
                    o.is_procedural = True
                    viewport.scene_objects.append(o)
                    created.append(o)

        land_obj._landscape_spawned = True
        land_obj._landscape_spawned_ids = [o.id for o in created]
        return created

def ensure_spawned(viewport, land_obj, cam_pos=None):
    return spawn_instances(viewport, land_obj, cam_pos)

def clear_spawns(viewport, land_obj):
    ids = getattr(land_obj, '_landscape_spawned_ids', []) or []
    if hasattr(land_obj, '_spawned_chunks'):
        for chunk_ids in land_obj._spawned_chunks.values():
            ids.extend(chunk_ids)
        land_obj._spawned_chunks = {}

    if not ids: return
    viewport.scene_objects[:] = [o for o in viewport.scene_objects if o.id not in ids]
    land_obj._landscape_spawned = False
    land_obj._landscape_spawned_ids = []
