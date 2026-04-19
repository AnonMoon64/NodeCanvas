"""
spawner_batcher.py

Static-batches spawner children that share a mesh_path into a single
interleaved VBO, reducing N per-object draw calls to one.

Cache is keyed on (spawner.id, signature). `signature` captures the set of
(child.id, position, rotation, scale, mesh_path) tuples so any respawn or
child edit invalidates the batch.

The batched VBO stores world-relative positions in the SPAWNER's local
space, so the render loop's existing glPushMatrix for the spawner still
applies. Each child's TRS is baked into its vertices at build time.

Skips pbr/custom shader state (uses Standard). The spawned "grass/fish/tree"
instances all share one material — if a project needs per-instance tinting,
extend _InstanceBatch to upload a per-instance color attribute.
"""
from __future__ import annotations

import math
import ctypes
import numpy as np
from OpenGL.GL import (
    glGenVertexArrays, glGenBuffers, glBindVertexArray, glBindBuffer,
    glBufferData, glVertexAttribPointer, glEnableVertexAttribArray,
    glDeleteVertexArrays, glDeleteBuffers, glDrawElements,
    GL_ARRAY_BUFFER, GL_ELEMENT_ARRAY_BUFFER, GL_STATIC_DRAW,
    GL_FLOAT, GL_FALSE, GL_TRIANGLES, GL_UNSIGNED_INT,
)

from py_editor.core.mesh_converter import MeshConverter


def _euler_matrix(rx, ry, rz):
    """Rotation matrix matching the glRotatef X,Y,Z order used in scene_view."""
    cx, sx = math.cos(math.radians(rx)), math.sin(math.radians(rx))
    cy, sy = math.cos(math.radians(ry)), math.sin(math.radians(ry))
    cz, sz = math.cos(math.radians(rz)), math.sin(math.radians(rz))
    Rx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]], dtype=np.float32)
    Ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]], dtype=np.float32)
    Rz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]], dtype=np.float32)
    return Rx @ Ry @ Rz


def _child_signature(children):
    parts = []
    for c in children:
        parts.append((
            getattr(c, 'id', ''),
            tuple(getattr(c, 'position', (0, 0, 0))),
            tuple(getattr(c, 'rotation', (0, 0, 0))),
            tuple(getattr(c, 'scale', (1, 1, 1))),
            getattr(c, 'mesh_path', None),
            tuple(getattr(c, 'color', (1, 1, 1, 1))),
        ))
    return hash(tuple(parts))


class _InstanceBatch:
    """Single mesh + many transforms merged into one VAO."""

    __slots__ = ('vao', 'vbo', 'ibo', 'count', 'mesh_path', 'shader_name', 'material_path', 'shader_params', 'max_distance')

    def __init__(self, mesh_path, shader_name, material_path, shader_params, children, max_distance=120.0):
        """`children` is either a list of SceneObject or a list of
        (position, rotation, scale) float tuples."""
        self.mesh_path = mesh_path
        self.shader_name = shader_name
        self.max_distance = float(max_distance)
        self.material_path = material_path
        self.shader_params = shader_params
        
        if mesh_path and mesh_path.startswith("__PRIMITIVE:"):
            v_data, i_data = _get_primitive_mesh(mesh_path)
        else:
            v_data, i_data = MeshConverter.load_mesh(mesh_path)
            
        # Raw mesh data is always 8 floats: pos(3), norm(3), uv(2)
        mesh_stride = 8
        verts = v_data.reshape(-1, mesh_stride)
        pos = verts[:, 0:3]
        nrm = verts[:, 3:6]
        uv  = verts[:, 6:8]
        n_base = pos.shape[0]

        n_inst = len(children)
        if n_inst > 0:
            first = children[0]
            has_color = (isinstance(first, tuple) and len(first) >= 4) or hasattr(first, 'color')
        else:
            has_color = False

        stride = 12 if has_color else 8  # Output stride: pos(3) + norm(3) + uv(2) + [col(4)]
        
        out_pos = np.empty((n_base * n_inst, 3), dtype=np.float32)
        out_nrm = np.empty((n_base * n_inst, 3), dtype=np.float32)
        out_uv  = np.tile(uv, (n_inst, 1)).astype(np.float32)
        out_col = np.empty((n_base * n_inst, 4), dtype=np.float32) if has_color else None
        out_idx_parts = []

        for k, c in enumerate(children):
            if isinstance(c, tuple):
                cp, cr, cs = c[0:3]
                cc = c[3] if len(c) >= 4 else (1, 1, 1, 1)
            else:
                cp, cr, cs = c.position, c.rotation, c.scale
                cc = getattr(c, 'color', (1, 1, 1, 1))
            
            M = _euler_matrix(*cr)
            S = np.array(cs, dtype=np.float32)
            T = np.array(cp, dtype=np.float32)
            scaled = pos * S
            xformed = scaled @ M.T + T
            out_pos[k * n_base:(k + 1) * n_base] = xformed
            out_nrm[k * n_base:(k + 1) * n_base] = nrm @ M.T
            if has_color:
                out_col[k * n_base:(k + 1) * n_base] = np.tile(cc, (n_base, 1))
            out_idx_parts.append(i_data + k * n_base)

        out_idx = np.concatenate(out_idx_parts).astype(np.uint32)
        interleaved = np.empty((out_pos.shape[0], stride), dtype=np.float32)
        interleaved[:, 0:3] = out_pos
        interleaved[:, 3:6] = out_nrm
        interleaved[:, 6:8] = out_uv
        if has_color:
            interleaved[:, 8:12] = out_col
        interleaved = np.ascontiguousarray(interleaved)

        self.vao = glGenVertexArrays(1)
        glBindVertexArray(self.vao)

        self.vbo = glGenBuffers(1)
        glBindBuffer(GL_ARRAY_BUFFER, self.vbo)
        glBufferData(GL_ARRAY_BUFFER, interleaved.nbytes, interleaved, GL_STATIC_DRAW)

        self.ibo = glGenBuffers(1)
        glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, self.ibo)
        glBufferData(GL_ELEMENT_ARRAY_BUFFER, out_idx.nbytes, out_idx, GL_STATIC_DRAW)

        glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, stride * 4, ctypes.c_void_p(0))
        glEnableVertexAttribArray(0)
        glVertexAttribPointer(2, 3, GL_FLOAT, GL_FALSE, stride * 4, ctypes.c_void_p(12))
        glEnableVertexAttribArray(2)
        glVertexAttribPointer(8, 2, GL_FLOAT, GL_FALSE, stride * 4, ctypes.c_void_p(24))
        glEnableVertexAttribArray(8)
        if has_color:
            # Attribute 3 aliases gl_Color in compat profile
            glVertexAttribPointer(3, 4, GL_FLOAT, GL_FALSE, stride * 4, ctypes.c_void_p(32))
            glEnableVertexAttribArray(3)

        glBindVertexArray(0)
        self.count = len(out_idx)

    def draw(self):
        glBindVertexArray(self.vao)
        glDrawElements(GL_TRIANGLES, self.count, GL_UNSIGNED_INT, None)
        glBindVertexArray(0)

    def release(self):
        try:
            glDeleteVertexArrays(1, [self.vao])
            glDeleteBuffers(1, [self.vbo])
            glDeleteBuffers(1, [self.ibo])
        except Exception:
            pass


class SpawnerBatchCache:
    def __init__(self):
        # spawner.id -> {'sig': int, 'batches': list[_InstanceBatch]}
        self._cache = {}

    def get_batches(self, spawner, children):
        """Return a list of _InstanceBatch for the given spawner.

        Children that aren't custom_mesh with a mesh_path are left to fall
        back to individual rendering (returned in `unbatched`).
        """
        batchable = []
        unbatched = []
        for c in children:
            if getattr(c, 'obj_type', None) == 'custom_mesh' and getattr(c, 'mesh_path', None):
                batchable.append(c)
            else:
                unbatched.append(c)

        if not batchable:
            # Drop any old entry so memory doesn't linger after a respawn.
            self._invalidate(spawner.id)
            return [], unbatched

        sig = _child_signature(batchable)
        entry = self._cache.get(spawner.id)
        if entry and entry['sig'] == sig:
            return entry['batches'], unbatched

        self._invalidate(spawner.id)
        # Group by mesh_path so each unique mesh produces one batch.
        groups = {}
        for c in batchable:
            groups.setdefault(c.mesh_path, []).append(c)
        batches = []
        for path, group in groups.items():
            try:
                # Regular spawners inherit settings from the spawner object
                sn = getattr(spawner, 'shader_name', 'Standard')
                mat = getattr(spawner, 'material_path', '')
                params = getattr(spawner, 'shader_params', {})
                batches.append(_InstanceBatch(path, sn, mat, params, group))
            except Exception as e:
                print(f"[SPAWNER BATCH] Failed to batch {path}: {e}")
                # Fall back: these children render individually.
                unbatched.extend(group)

        self._cache[spawner.id] = {'sig': sig, 'batches': batches}
        return batches, unbatched

    def _invalidate(self, spawner_id):
        entry = self._cache.pop(spawner_id, None)
        if entry:
            for b in entry['batches']:
                b.release()

    def clear(self):
        for sid in list(self._cache.keys()):
            self._invalidate(sid)


# --- Voxel biome spawn batching ---------------------------------------------

_PREFAB_MESH_CACHE = {}  # prefab_path -> resolved mesh_path (or None)
_PRIMITIVE_MESH_CACHE = {} # kind -> (v_data, i_data)

def _get_primitive_mesh(kind):
    if kind in _PRIMITIVE_MESH_CACHE:
        return _PRIMITIVE_MESH_CACHE[kind]
        
    v_data = np.zeros((24, 8), dtype=np.float32)
    i_data = np.zeros(36, dtype=np.uint32)
    
    # Generic solid bounding cube construction
    faces = [
        ([ 0, 0, 1],  [[-.5,-.5, .5], [.5,-.5, .5], [.5, .5, .5], [-.5, .5, .5]]),
        ([ 0, 0,-1],  [[ .5,-.5,-.5], [-.5,-.5,-.5], [-.5, .5,-.5], [ .5, .5,-.5]]),
        ([ 1, 0, 0],  [[ .5,-.5, .5], [ .5,-.5,-.5], [ .5, .5,-.5], [ .5, .5, .5]]),
        ([-1, 0, 0],  [[-.5,-.5,-.5], [-.5,-.5, .5], [-.5, .5, .5], [-.5, .5,-.5]]),
        ([ 0, 1, 0],  [[-.5, .5, .5], [ .5, .5, .5], [ .5, .5,-.5], [-.5, .5,-.5]]),
        ([ 0,-1, 0],  [[-.5,-.5,-.5], [ .5,-.5,-.5], [ .5,-.5, .5], [-.5,-.5, .5]])
    ]
    
    idx_p = 0; idx_tri = 0
    for norm, quad in faces:
        for j, p in enumerate(quad):
            v_data[idx_p + j, 0:3] = p
            v_data[idx_p + j, 3:6] = norm
            if j == 0: v_data[idx_p + j, 6:8] = [0, 0]
            elif j == 1: v_data[idx_p + j, 6:8] = [1, 0]
            elif j == 2: v_data[idx_p + j, 6:8] = [1, 1]
            elif j == 3: v_data[idx_p + j, 6:8] = [0, 1]
        
        i_data[idx_tri:idx_tri+6] = [idx_p, idx_p+1, idx_p+2, idx_p, idx_p+2, idx_p+3]
        idx_p += 4; idx_tri += 6
        
    _PRIMITIVE_MESH_CACHE[kind] = (v_data, i_data)
    return v_data, i_data


def _resolve_spawn_mesh_path(sp):
    """Return a mesh file path for a spawn dict, or the static primitive token."""
    from py_editor.core import paths as _ap
    kind = sp.get('kind', 'object:cube')
    raw = sp.get('prefab_path') or ''
    # Route fallbacks to dynamic primitives rather than immediate-mode drawing
    if not raw or kind in ('object:cube', 'object:sphere', 'object:cylinder', 'object:cone'):
        return f"__PRIMITIVE:{kind}__"
        
    abs_path = _ap.resolve(raw)
    ext = abs_path.lower().rsplit('.', 1)[-1]
    if kind == 'prefab' or ext == 'prefab':
        if abs_path in _PREFAB_MESH_CACHE:
            return _PREFAB_MESH_CACHE[abs_path]
        try:
            import json
            with open(abs_path, 'r') as f:
                pdata = json.load(f)
            pdata = _ap.resolve_on_load(pdata)
            root = pdata.get('root', {})
            mp = root.get('mesh_path') or None
        except Exception:
            mp = None
            
        mp = mp if mp else f"__PRIMITIVE:{kind}__"
        _PREFAB_MESH_CACHE[abs_path] = mp
        return mp
        
    if ext in ('mesh', 'fbx', 'obj'):
        return abs_path
    return f"__PRIMITIVE:{kind}__"


class ChunkSpawnBatchCache:
    """Per-voxel-chunk batches. Key = chunk_cache_key. Signature = hash of
    (mesh_path, pos, rot, scale) tuples so a respawn invalidates automatically.
    """

    def __init__(self):
        self._cache = {}  # chunk_key -> {'sig': int, 'batches': [...], 'leftovers': [...]}

    def get_batches(self, chunk_key, spawns):
        if not spawns:
            self.invalidate(chunk_key)
            return [], []

        # Short-circuit signature checks instantly if already processed
        # Voxel chunks are geometrically static once spawned.
        entry = self._cache.get(chunk_key)
        if entry:
            return entry['batches'], entry['leftovers']

        # Group by mesh_path — include max_distance so spawners with different
        # per-spawner distances end up in separate batches for independent culling.
        groups = {}
        group_origs = {}
        leftovers = []
        for sp in spawns:
            mp = _resolve_spawn_mesh_path(sp)
            sn = sp.get('shader_name', 'Standard')
            if mp is None:
                leftovers.append(sp)
                continue
            mat = sp.get('material_path', '')
            params = sp.get('shader_params', {})
            max_d = float(sp.get('max_distance', 120.0))
            key = (mp, sn, mat, max_d, tuple(sorted(params.items())))
            groups.setdefault(key, []).append((
                tuple(sp['pos']), tuple(sp['rot']), tuple(sp['scale']),
                tuple(sp.get('color', (1, 1, 1, 1)))
            ))
            group_origs.setdefault(key, []).append(sp)

        self.invalidate(chunk_key)
        batches = []
        for (mp, sn, mat, max_d, p_tuple), xs in groups.items():
            try:
                params = dict(p_tuple)
                batches.append(_InstanceBatch(mp, sn, mat, params, xs, max_distance=max_d))
            except Exception as e:
                print(f"[CHUNK BATCH] Failed to batch {mp} ({sn}, {mat}): {e}")
                leftovers.extend(group_origs[(mp, sn, mat, max_d, p_tuple)])
        self._cache[chunk_key] = {'batches': batches, 'leftovers': leftovers}
        return batches, leftovers

    def invalidate(self, chunk_key):
        entry = self._cache.pop(chunk_key, None)
        if entry:
            for b in entry['batches']:
                b.release()
