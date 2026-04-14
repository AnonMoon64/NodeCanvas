"""
procedural_system.py

Helpers for landscape primitives and spawning instances.
Optimized for ZERO-LATENCY infinite exploration via Bulk Discovery Vectorization.
"""
import math
import random
import threading
import concurrent.futures
import numpy as np
import os
from pathlib import Path
from typing import List, Tuple, Union


class VectorizedNoise:
    """NumPy-optimized noise engine for high-performance landscape generation."""
    def __init__(self, seed=0):
        rng = np.random.RandomState(seed); self.p = np.tile(np.arange(256, dtype=int), 2); rng.shuffle(self.p[:256]); self.p[256:] = self.p[:256]
    def fade(self, t): return t * t * t * (t * (t * 6 - 15) + 10)
    def lerp(self, t, a, b): return a + t * (b - a)
    def grad(self, hash, x, y):
        h = hash & 15; u = np.where(h < 8, x, y); v = np.where(h < 4, y, np.where((h == 12) | (h == 14), x, 0))
        return np.where(h & 1 == 0, u, -u) + np.where(h & 2 == 0, v, -v)
    def noise(self, x, y):
        X, Y = np.floor(x).astype(int) & 255, np.floor(y).astype(int) & 255; x, y = x - np.floor(x), y - np.floor(y); u, v = self.fade(x), self.fade(y); A, B = self.p[X] + Y, self.p[X + 1] + Y
        return self.lerp(v, self.lerp(u, self.grad(self.p[self.p[A]], x, y), self.grad(self.p[self.p[B]], x-1, y)),
                            self.lerp(u, self.grad(self.p[self.p[A+1]], x, y-1), self.grad(self.p[self.p[B+1]], x-1, y-1)))

class PerlinNoise:
    """Legacy single-point Perlin noise."""
    def __init__(self, seed=0): self.p = list(range(256)); random.seed(seed); random.shuffle(self.p); self.p += self.p
    def lerp(self, t, a, b): return a + t * (b - a)
    def fade(self, t): return t * t * t * (t * (t * 6 - 15) + 10)
    def grad(self, hash, x, y): h = hash & 15; u = x if h < 8 else y; v = y if h < 4 else (x if h in [12, 14] else 0); return (u if (h & 1) == 0 else -u) + (v if (h & 2) == 0 else -v)
    def noise(self, x, y):
        X, Y = int(math.floor(x)) & 255, int(math.floor(y)) & 255; x -= math.floor(x); y -= math.floor(y); u, v = self.fade(x), self.fade(y); A, B = self.p[X]+Y, self.p[X+1]+Y
        return self.lerp(v, self.lerp(u, self.grad(self.p[self.p[A]], x, y), self.grad(self.p[self.p[B]], x-1, y)),
                           self.lerp(u, self.grad(self.p[self.p[A+1]], x, y-1), self.grad(self.p[self.p[B+1]], x-1, y-1)))

_noise_cache, _noise_lock = {}, threading.Lock()
_landscape_display_list_cache = {} 
_draft_display_list_cache = {}     
_stale_landscape_cache = {}        
_pending_chunks, _completed_chunk_data = {}, {}
_gen_executor = concurrent.futures.ThreadPoolExecutor(max_workers=max(12, os.cpu_count() or 4))

def get_noise(seed: int, ntype: str = "perlin", vectorized: bool = False) -> object:
    key = (seed, ntype, vectorized)
    with _noise_lock:
        if key not in _noise_cache:
            if vectorized: _noise_cache[key] = VectorizedNoise(seed)
            else: _noise_cache[key] = PerlinNoise(seed)
        return _noise_cache[key]

def sample_height(x: Union[float, np.ndarray], z: Union[float, np.ndarray], obj=None) -> Union[float, np.ndarray]:
    """SAMPLES procedural height. optimized for bulk NumPy arrays."""
    if obj is None or getattr(obj, 'landscape_type', 'procedural') == 'flat': return 0.0 if isinstance(x, float) else np.zeros_like(x)
    layers = getattr(obj, 'landscape_noise_layers', [])
    if not layers: return 0.0 if isinstance(x, float) else np.zeros_like(x)

    is_vec = isinstance(x, np.ndarray); total_h = np.zeros_like(x) if is_vec else 0.0; base_seed = getattr(obj, 'landscape_seed', 123)
    for layer in layers:
        amp, freq = layer.get('amp', 1.0), layer.get('freq', 1.0); off, octaves = layer.get('offset', [0.0, 0.0]), layer.get('octaves', 1); ntype, pers, lacun = layer.get('type', 'perlin'), layer.get('persistence', 0.5), layer.get('lacunarity', 2.0); exp, mode = layer.get('exponent', 1.0), layer.get('mode', 'fbm'); layer_h = np.zeros_like(x) if is_vec else 0.0; cur_amp, cur_freq = amp, freq; pn = get_noise(base_seed, ntype, vectorized=is_vec)
        for i in range(octaves):
            ox_off = (base_seed * 19349663 ^ i * 83492791) % 10000; oz_off = (base_seed * 73856093 ^ i * 19349663) % 10000; vx, vz = (x + off[0] + ox_off) * cur_freq, (z + off[1] + oz_off) * cur_freq; val = pn.noise(vx, vz)
            if mode == 'ridged': val = (1.0 - np.abs(val))**2 if is_vec else (1.0 - abs(val))**2
            elif mode == 'billow': val = np.abs(val) if is_vec else abs(val)
            layer_h += val * cur_amp; cur_amp *= pers; cur_freq *= lacun
        if exp != 1.0: layer_h = (np.sign(layer_h) * (np.abs(layer_h)**exp)) if is_vec else (math.copysign(1, layer_h) * (abs(layer_h)**exp))
        total_h += layer_h * layer.get('weight', 1.0)
    total_h -= getattr(obj, 'landscape_ocean_level', 0.1); o_flat = getattr(obj, 'landscape_ocean_flattening', 0.3)
    if is_vec: total_h = np.where(total_h < 0, total_h * o_flat, total_h)
    elif total_h < 0: total_h *= o_flat
    return total_h * getattr(obj, 'landscape_height_scale', 30.0)

def get_climate_vec(x, z, h, seed):
    humidity_pn = get_noise(seed + 999, "perlin", vectorized=True); lat_f = np.abs(z) * (1.0 / 2500.0); elev_f = np.maximum(0.0, h) * 0.01; temp = np.clip(1.0 - lat_f - elev_f, 0, 1); hum = np.clip((humidity_pn.noise(x * 0.01, z * 0.01) + 1.0) * 0.5 - (elev_f * 0.5), 0, 1); return temp, hum

def get_biome_colors_vec(obj, h, s, x, z):
    biomes = getattr(obj, 'landscape_biomes', []); seed = getattr(obj, 'landscape_seed', 123)
    temp, hum = get_climate_vec(x, z, h, seed)
    if not biomes: return np.full((*h.shape, 4), 0.5)
    out_colors = np.full((*h.shape, 4), [0.5, 0.5, 0.5, 1.0])
    for b in biomes:
        hr, sr, tr, ur = b.get('height_range', [-1000,1000]), b.get('slope_range', [0,1]), b.get('temp_range', [0,1]), b.get('hum_range', [0,1])
        mask = (h >= hr[0]) & (h <= hr[1]) & (s >= sr[0]) & (s <= sr[1]) & (temp >= tr[0]) & (temp <= tr[1]) & (hum >= ur[0]) & (hum <= ur[1])
        out_colors[mask] = b.get('surface', {}).get('color', [0.5,0.5,0.5,1.0])
    return out_colors

def get_biome_at(obj, height: float, slope: float, x: float, z: float) -> dict:
    biomes = getattr(obj, 'landscape_biomes', []); seed = getattr(obj, 'landscape_seed', 123)
    temp, hum = get_climate_vec(np.array([x]), np.array([z]), np.array([height]), seed); temp, hum = temp[0], hum[0]
    if not biomes: return {'surface': {'color': [0.5, 0.5, 0.5, 1.0]}}
    for b in biomes:
        hr, sr, tr, ur = b.get('height_range', [-1000,1000]), b.get('slope_range', [0,1]), b.get('temp_range', [0,1]), b.get('hum_range', [0,1])
        if hr[0] <= height <= hr[1] and sr[0] <= slope <= sr[1] and tr[0] <= temp <= tr[1] and ur[0] <= hum <= ur[1]: return b
    return biomes[0]

def draw_landscape_3d(obj, viewport):
    """Draw a landscape into the current GL context."""
    from OpenGL.GL import (glBegin, glEnd, glVertex3f, glNormal3f, glColor4f, glEnable, glDisable, glCullFace, glPolygonOffset, glDepthMask, glMaterialfv, glGenLists, glNewList, glEndList, glCallList, glDeleteLists, GL_QUADS, GL_CULL_FACE, GL_BACK, GL_POLYGON_OFFSET_FILL, GL_DEPTH_TEST, GL_TRUE, GL_FRONT_AND_BACK, GL_AMBIENT_AND_DIFFUSE, GL_SPECULAR, GL_COMPILE)
    glEnable(GL_DEPTH_TEST); glDepthMask(GL_TRUE); bias = float(getattr(obj, 'landscape_render_bias', -0.02)); size_mode, chunk_size, CHUNK_RES = getattr(obj, 'landscape_size_mode', 'finite'), float(getattr(obj, 'landscape_chunk_size', 128.0)), int(getattr(obj, 'landscape_resolution', 32)); glEnable(GL_CULL_FACE); glCullFace(GL_BACK); 
    try: glEnable(GL_POLYGON_OFFSET_FILL); glPolygonOffset(2.0, 2.0)
    except Exception: pass
    from PyQt6.QtGui import QOpenGLContext
    ctx = QOpenGLContext.currentContext(); ctx_id = hash(ctx) if ctx else 0; layers_hash = hash(str(getattr(obj, 'landscape_noise_layers', []))); render_state = {'compiled_this_frame': False}

    def _generate_chunk_data_task(ox, oz, sw, sd, rows, cols, obj, bias):
        c_range, r_range = np.linspace(-0.5, 0.5, cols + 1) * sw, np.linspace(-0.5, 0.5, rows + 1) * sd; C, R = np.meshgrid(c_range, r_range)
        wx, wz = ox + C, oz + R; grid_h = sample_height(wx, wz, obj) + bias; eps = 3.0
        h_r, h_l = sample_height(wx + eps, wz, obj) + bias, sample_height(wx - eps, wz, obj) + bias
        h_u, h_d = sample_height(wx, wz + eps, obj) + bias, sample_height(wx, wz - eps, obj) + bias
        nx, nz = (h_l - h_r) / (2 * eps), (h_d - h_u) / (2 * eps); ny = np.ones_like(nx); mag = np.sqrt(nx**2+ny**2+nz**2); nx, ny, nz = nx/mag, ny/mag, nz/mag
        color_grid = get_biome_colors_vec(obj, grid_h, 1.0 - ny, wx, wz); return grid_h, nx, ny, nz, color_grid, c_range, r_range

    def _render_chunk(ox, oz, sw, sd, rows, cols, l_hash, c_id, state):
        seed = getattr(obj, 'landscape_seed', 123); cache_key = (ox, oz, sw, sd, rows, cols, seed, l_hash, c_id); pos_key = (ox, oz, c_id)
        if cache_key in _landscape_display_list_cache: glCallList(_landscape_display_list_cache[cache_key]); _stale_landscape_cache[pos_key] = _landscape_display_list_cache[cache_key]; return
        if cache_key in _completed_chunk_data and not state['compiled_this_frame']:
            state['compiled_this_frame'] = True; grid_h, gnx, gny, gnz, color_grid, c_range, r_range = _completed_chunk_data.pop(cache_key); list_id = glGenLists(1)
            if pos_key in _stale_landscape_cache:
                try: glDeleteLists(_stale_landscape_cache[pos_key], 1)
                except Exception: pass
            glNewList(list_id, GL_COMPILE); glBegin(GL_QUADS)
            for r in range(rows):
                for c in range(cols):
                    lx0, lz0, lx1, lz1 = c_range[c], r_range[r], c_range[c+1], r_range[r+1]; bc = color_grid[r,c]
                    try: glMaterialfv(GL_FRONT_AND_BACK, GL_AMBIENT_AND_DIFFUSE, bc); glMaterialfv(GL_FRONT_AND_BACK, GL_SPECULAR, (0.1,0.1,0.1,1.0))
                    except Exception: glColor4f(*bc)
                    glNormal3f(gnx[r,c],gny[r,c],gnz[r,c]); glVertex3f(ox+lx0, grid_h[r,c], oz+lz0); glNormal3f(gnx[r+1,c],gny[r+1,c],gnz[r+1,c]); glVertex3f(ox+lx0, grid_h[r+1,c], oz+lz1); glNormal3f(gnx[r+1,c+1],gny[r+1,c+1],gnz[r+1,c+1]); glVertex3f(ox+lx1, grid_h[r+1,c+1], oz+lz1); glNormal3f(gnx[r,c+1],gny[r,c+1],gnz[r,c+1]); glVertex3f(ox+lx1, grid_h[r,c+1], oz+lz0)
            glEnd(); glEndList(); _landscape_display_list_cache[cache_key] = list_id; _stale_landscape_cache[pos_key] = list_id; glCallList(list_id); return
        if pos_key in _pending_chunks:
            fut, pk = _pending_chunks[pos_key]
            if pk == cache_key:
                if fut.done():
                    try: _completed_chunk_data[cache_key] = fut.result(); del _pending_chunks[pos_key]
                    except Exception: del _pending_chunks[pos_key]
            elif fut.done(): del _pending_chunks[pos_key]
        if pos_key in _stale_landscape_cache: glCallList(_stale_landscape_cache[pos_key]); return
        if pos_key not in _pending_chunks: _pending_chunks[pos_key] = (_gen_executor.submit(_generate_chunk_data_task, ox,oz,sw,sd,rows,cols,obj,bias), cache_key)
        if pos_key in _draft_display_list_cache: glCallList(_draft_display_list_cache[pos_key])

    # --- BULK DISCOVERY VECTORIZATION ---
    cp = getattr(viewport._cam3d, 'pos', [0,0,0]); rad = int(getattr(obj, 'landscape_grid_radius', 3)); cx, cz = round(cp[0]/chunk_size)*chunk_size, round(cp[2]/chunk_size)*chunk_size; chunks = []
    for ix in range(-rad, rad + 1):
        for iz in range(-rad, rad + 1): chunks.append((cx+ix*chunk_size, cz+iz*chunk_size))
    
    new_draft_targets = [(ox, oz) for ox, oz in chunks if (ox, oz, ctx_id) not in _draft_display_list_cache]
    if new_draft_targets:
        res = 4; sw, sd = chunk_size, chunk_size; c_r, r_r = np.linspace(-0.5, 0.5, res + 1) * sw, np.linspace(-0.5, 0.5, res + 1) * sd; C, R = np.meshgrid(c_r, r_r)
        batch_ox = np.array([t[0] for t in new_draft_targets]); batch_oz = np.array([t[1] for t in new_draft_targets])
        # Grid positions for the whole batch: (N, res+1, res+1)
        WX = batch_ox[:, None, None] + C[None, :, :]; WZ = batch_oz[:, None, None] + R[None, :, :]
        # Sampler Height for entire batch in ONE call
        GRID_H = sample_height(WX, WZ, obj) + bias; COLOR_GRID = get_biome_colors_vec(obj, GRID_H, np.zeros_like(GRID_H), WX, WZ)
        
        for i, (ox, oz) in enumerate(new_draft_targets):
            list_id = glGenLists(1); glNewList(list_id, GL_COMPILE); glBegin(GL_QUADS)
            gh = GRID_H[i]; cg = COLOR_GRID[i]
            for r in range(res):
                for c in range(res):
                    lx0, lz0, lx1, lz1 = c_r[c], r_r[r], c_r[c+1], r_r[r+1]; bc = cg[r,c]
                    # NO saturation boost here — let it look like natural terrain
                    glColor4f(*bc); glNormal3f(0, 1, 0); glVertex3f(ox+lx0, gh[r,c], oz+lz0); glVertex3f(ox+lx0, gh[r+1,c], oz+lz1); glVertex3f(ox+lx1, gh[r+1,c+1], oz+lz1); glVertex3f(ox+lx1, gh[r,c+1], oz+lz0)
            glEnd(); glEndList(); _draft_display_list_cache[(ox, oz, ctx_id)] = list_id

    # --- Draw Chunks ---
    chunks.sort(key=lambda p: (p[0]-cp[0])**2 + (p[1]-cp[2])**2)
    for ox, oz in chunks: _render_chunk(ox, oz, chunk_size, chunk_size, CHUNK_RES, CHUNK_RES, layers_hash, ctx_id, render_state)
    try: glDisable(GL_POLYGON_OFFSET_FILL)
    except Exception: pass
    glDisable(GL_CULL_FACE)

def spawn_instances(viewport, land_obj, cam_pos=None):
    if not getattr(land_obj, 'landscape_spawn_enabled', False): return []
    from .scene_editor import SceneObject
    sm, bias, seed = getattr(land_obj, 'landscape_size_mode', 'finite'), float(getattr(land_obj, 'landscape_render_bias', -0.02)), getattr(land_obj, 'landscape_seed', 123)
    if sm == 'infinite':
        if cam_pos is None: return []
        if not hasattr(land_obj, '_spawned_chunks'): land_obj._spawned_chunks = {}
        cs, rad = float(getattr(land_obj, 'landscape_chunk_size', 128.0)), int(getattr(land_obj, 'landscape_grid_radius', 1))
        gxc, gzc = round(cam_pos[0]/cs), round(cam_pos[2]/cs); cur_c = set()
        for ix in range(-rad, rad+1):
            for iz in range(-rad, rad+1): cur_c.add((int(gxc+ix), int(gzc+iz)))
        for c in [c for c in land_obj._spawned_chunks if c not in cur_c]: ids = land_obj._spawned_chunks.pop(c); viewport.scene_objects[:] = [o for o in viewport.scene_objects if o.id not in ids]
        # Optimization: Spawn up to 3 missing chunks per tick to fill the grid faster without killing FPS
        chunks_spawned_this_tick = 0
        for c in cur_c:
            if c in land_obj._spawned_chunks: continue
            
            gx, gz = c; ox, oz = gx*cs, gz*cs; rows, cols = 5, 5; spx, spz = cs/max(1,cols), cs/max(1,rows); bx, bz = ox-cs*0.5, oz-cs*0.5
            cx_r, rz_r = np.linspace(bx, bx+cs-spx, cols), np.linspace(bz, bz+cs-spz, rows); CX, RZ = np.meshgrid(cx_r, rz_r)
            grid_h = sample_height(CX, RZ, land_obj); eps = 0.5; hnx, hnz = sample_height(CX+eps, RZ, land_obj), sample_height(CX, RZ+eps, land_obj)
            NX, NZ = -(hnx-grid_h)/eps, -(hnz-grid_h)/eps; NY=1.0; L=np.sqrt(NX**2+1.0+NZ**2); SLP=1.0-(NY/L); cids = []
            
            for r in range(rows):
                for col in range(cols):
                    wx, wz, h, slp = bx+col*spx, bz+r*spz, grid_h[r,col], SLP[r,col]; biome = get_biome_at(land_obj, h, slp, wx, wz); random.seed(hash((bx+col*spx, bz+r*spz, seed)) % 1000000)
                    for ly in biome.get('spawns', []):
                        if not ly.get('assets', []) or random.random() > ly.get('density', 0.1): continue
                        asset = random.choice(ly['assets'])
                        sc = 1.0 + random.random() * 0.5
                        o = SceneObject(Path(asset).stem, 'mesh', [wx+(random.random()-0.5)*spx, land_obj.position[1]+h+bias, wz+(random.random()-0.5)*spz], [0, random.random()*360, 0], [sc, sc, sc])
                        o.file_path, o.is_procedural = asset, True; viewport.scene_objects.append(o); cids.append(o.id)
            
            land_obj._spawned_chunks[c] = cids
            chunks_spawned_this_tick += 1
            if chunks_spawned_this_tick >= 3:
                break
        return []
    return []

def ensure_spawned(viewport, land_obj, cam_pos=None): return spawn_instances(viewport, land_obj, cam_pos)
def clear_spawns(viewport, land_obj):
    ids = getattr(land_obj, '_landscape_spawned_ids', []) or []; [ids.extend(c) for c in getattr(land_obj, '_spawned_chunks', {}).values()]; land_obj._spawned_chunks = {}
    if not ids: return
    viewport.scene_objects[:] = [o for o in viewport.scene_objects if o.id not in ids]; land_obj._landscape_spawned, land_obj._landscape_spawned_ids = False, []
