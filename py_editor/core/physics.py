"""
physics.py

Physics utilities for NodeCanvas:
  - integrate_gravity            — Euler-step velocity + position under gravity
  - resolve_collisions           — sphere-sphere separation with velocity impulses
  - resolve_terrain_collision    — real per-chunk sphere-vs-triangle ground / wall collision
  - get_mesh_aabb_half_extents   — helper for .mesh AABB data
"""
import math
import numpy as np
from typing import List

GRAVITY = -9.81  # m/s² along -Y

def integrate_gravity(scene_objects: List[object], dt: float,
                      gravity: float = GRAVITY, linear_damping: float = 0.0):
    """Apply gravity and integrate velocity → position for physics-enabled objects.

    Only objects without an AI controller are integrated here; AI-driven objects
    handle their own motion in `controller.update_physics`. Children inherit the
    parent transform for rendering but physics is applied in local space so a
    free-falling cube drops relative to its parent.
    """
    for obj in scene_objects:
        if not getattr(obj, 'physics_enabled', False):
            continue
        ct = getattr(obj, 'controller_type', 'None') or 'None'
        if ct != 'None':
            continue  # AI controllers own their own integration
        vel = list(getattr(obj, 'velocity', [0.0, 0.0, 0.0]))
        acc = list(getattr(obj, 'acceleration', [0.0, 0.0, 0.0]))
        # Gravity
        vel[1] += (gravity + acc[1]) * dt
        vel[0] += acc[0] * dt
        vel[2] += acc[2] * dt
        # Damping
        if linear_damping > 0.0:
            k = max(0.0, 1.0 - linear_damping * dt)
            vel = [v * k for v in vel]
        # Integrate position
        pos = list(obj.position)
        pos[0] += vel[0] * dt
        pos[1] += vel[1] * dt
        pos[2] += vel[2] * dt
        obj.position = pos
        obj.velocity = vel

# ─────────────────────────────────────────────────────────────────────────────
# Sphere-Sphere Collision
# ─────────────────────────────────────────────────────────────────────────────

def resolve_collisions(scene_objects: List[object], dt: float, restitution: float = 0.15):
    """Resolve simple sphere collisions for objects that have physics enabled.

    - Uses the first entry of `collision_properties` for each object as the
      primary collision primitive.
    - Moves objects apart proportionally to inverse mass and applies a
      simple impulse to their velocity.
    """
    # Safe snapshot: avoid crash if scene_objects is modified during iteration
    objs = [o for o in list(scene_objects) if getattr(o, 'physics_enabled', False)]
    n = len(objs)
    if n < 2:
        return

    for i in range(n):
        a = objs[i]
        props_a = getattr(a, 'collision_properties', None)
        if not props_a:
            continue
        prop_a = props_a[0]
        offset_a = prop_a.get('offset', [0.0, 0.0, 0.0])
        pa = [a.position[0] + offset_a[0], a.position[1] + offset_a[1], a.position[2] + offset_a[2]]
        ra = float(prop_a.get('radius', 0.5)) * max(getattr(a, 'scale', [1.0, 1.0, 1.0]))
        ma = float(getattr(a, 'mass', 1.0)) if getattr(a, 'mass', None) is not None else 1.0

        for j in range(i + 1, n):
            b = objs[j]
            props_b = getattr(b, 'collision_properties', None)
            if not props_b:
                continue
            prop_b = props_b[0]
            offset_b = prop_b.get('offset', [0.0, 0.0, 0.0])
            pb = [b.position[0] + offset_b[0], b.position[1] + offset_b[1], b.position[2] + offset_b[2]]
            rb = float(prop_b.get('radius', 0.5)) * max(getattr(b, 'scale', [1.0, 1.0, 1.0]))
            mb = float(getattr(b, 'mass', 1.0)) if getattr(b, 'mass', None) is not None else 1.0

            dx = pa[0] - pb[0]; dy = pa[1] - pb[1]; dz = pa[2] - pb[2]
            dist2 = dx * dx + dy * dy + dz * dz
            if dist2 <= 1e-9:
                dist = 1e-6
                nx, ny, nz = 1.0, 0.0, 0.0
            else:
                dist = math.sqrt(dist2)
                nx, ny, nz = dx / dist, dy / dist, dz / dist

            overlap = (ra + rb) - dist
            if overlap > 0.0:
                inv_total = (1.0 / ma) + (1.0 / mb) if (ma + mb) > 0 else 1.0
                if inv_total == 0:
                    continue

                move_a = (1.0 / ma) / inv_total * overlap
                move_b = (1.0 / mb) / inv_total * overlap

                try:
                    a.position[0] += nx * move_a
                    a.position[1] += ny * move_a
                    a.position[2] += nz * move_a
                except Exception:
                    pass
                try:
                    b.position[0] -= nx * move_b
                    b.position[1] -= ny * move_b
                    b.position[2] -= nz * move_b
                except Exception:
                    pass

                va = list(getattr(a, 'velocity', [0.0, 0.0, 0.0]))
                vb = list(getattr(b, 'velocity', [0.0, 0.0, 0.0]))

                rel_v = (va[0] - vb[0]) * nx + (va[1] - vb[1]) * ny + (va[2] - vb[2]) * nz

                if rel_v < 0:
                    j_impulse = -(1.0 + restitution) * rel_v / inv_total
                    da = j_impulse / ma
                    db = j_impulse / mb
                    va[0] += nx * da; va[1] += ny * da; va[2] += nz * da
                    vb[0] -= nx * db; vb[1] -= ny * db; vb[2] -= nz * db

                    try:
                        a.velocity = va
                    except Exception:
                        pass
                    try:
                        b.velocity = vb
                    except Exception:
                        pass

    # End resolve_collisions


# ─────────────────────────────────────────────────────────────────────────────
# Mesh AABB Helper
# ─────────────────────────────────────────────────────────────────────────────

def get_mesh_aabb_half_extents(mesh_cache_entry: dict) -> list:
    """Return [hx, hy, hz, cy_offset] of a .mesh from its stored AABB.

    cy_offset is the Y centre of the AABB relative to the mesh origin.
    Falls back to unit half-extents if no 'aabb' key present.
    """
    if mesh_cache_entry and 'aabb' in mesh_cache_entry:
        mn, mx = mesh_cache_entry['aabb']
        hx = (mx[0] - mn[0]) * 0.5
        hy = (mx[1] - mn[1]) * 0.5
        hz = (mx[2] - mn[2]) * 0.5
        cy = mn[1] + hy
        return [hx, hy, hz, cy]
    return [0.5, 0.5, 0.5, 0.0]


# ─────────────────────────────────────────────────────────────────────────────
# Triangle Collision Helpers (vectorised NumPy)
# ─────────────────────────────────────────────────────────────────────────────

def _closest_point_on_triangles(p: np.ndarray,
                                 v0: np.ndarray,
                                 v1: np.ndarray,
                                 v2: np.ndarray) -> np.ndarray:
    """Vectorised closest-point-on-triangle for one sphere centre p vs N triangles.

    Uses the Christer Ericson "Real-Time Collision Detection" method (§5.1.5).

    Parameters
    ----------
    p   : (3,)   query point
    v0,v1,v2 : (N,3)  triangle vertices

    Returns
    -------
    closest : (N,3)  closest point on each triangle to p
    """
    ab = v1 - v0
    ac = v2 - v0
    ap = p - v0

    d1 = (ab * ap).sum(axis=1)
    d2 = (ac * ap).sum(axis=1)

    # Region A (vertex v0)
    mask0 = (d1 <= 0) & (d2 <= 0)

    bp = p - v1
    d3 = (ab * bp).sum(axis=1)
    d4 = (ac * bp).sum(axis=1)

    # Region B (vertex v1)
    mask1 = (d3 >= 0) & (d4 <= d3)

    cp = p - v2
    d5 = (ab * cp).sum(axis=1)
    d6 = (ac * cp).sum(axis=1)

    # Region C (vertex v2)
    mask2 = (d6 >= 0) & (d5 <= d6)

    # Edge AB
    vc = d1 * d4 - d3 * d2
    mask_ab = (vc <= 0) & (d1 >= 0) & (d3 <= 0)
    t_ab = np.where(mask_ab & (d1 - d3 > 1e-9),
                    d1 / (d1 - d3 + 1e-12), 0.0)

    # Edge AC
    vb = d5 * d2 - d1 * d6
    mask_ac = (vb <= 0) & (d2 >= 0) & (d6 <= 0)
    t_ac = np.where(mask_ac & (d2 - d6 > 1e-9),
                    d2 / (d2 - d6 + 1e-12), 0.0)

    # Edge BC
    va = d3 * d6 - d5 * d4
    mask_bc = (va <= 0) & ((d4 - d3) >= 0) & ((d5 - d6) >= 0)
    denom_bc = (d4 - d3) + (d5 - d6)
    t_bc = np.where(mask_bc & (denom_bc > 1e-9),
                    (d4 - d3) / (denom_bc + 1e-12), 0.0)

    # Face interior
    denom_f = 1.0 / (vc + vb + va + 1e-12)
    v_f = vb * denom_f
    w_f = vc * denom_f

    # Assemble result: start with face interior, then override with edge/vertex cases
    # Shape: (N,3)
    result = v0 + (ab * v_f[:, None]) + (ac * w_f[:, None])

    result[mask_ab] = v0[mask_ab] + ab[mask_ab] * t_ab[mask_ab, None]
    result[mask_ac] = v0[mask_ac] + ac[mask_ac] * t_ac[mask_ac, None]
    result[mask_bc] = v1[mask_bc] + (v2[mask_bc] - v1[mask_bc]) * t_bc[mask_bc, None]
    result[mask2]   = v2[mask2]
    result[mask1]   = v1[mask1]
    result[mask0]   = v0[mask0]

    return result


def _sphere_vs_chunk_triangles(center: np.ndarray, radius: float,
                                verts_cpu: np.ndarray,
                                idx_cpu: np.ndarray,
                                obj_world_pos: np.ndarray) -> tuple:
    """Test a sphere against all triangles in a voxel chunk.

    Parameters
    ----------
    center        : (3,) world-space sphere centre
    radius        : sphere radius
    verts_cpu     : (V,3) float32, relative to obj_world_pos (voxel object origin)
    idx_cpu       : (M,3) uint32 triangle vertex indices
    obj_world_pos : (3,) float64 — voxel SceneObject.position

    Returns
    -------
    push_vec : (3,) total push vector to apply to the sphere, or None if no hit
    """
    if verts_cpu is None or idx_cpu is None or len(idx_cpu) == 0:
        return None

    # Convert verts to world space
    verts_world = verts_cpu.astype(np.float64) + obj_world_pos

    # Broad phase: AABB of chunk vs sphere
    chunk_min = verts_world.min(axis=0) - radius
    chunk_max = verts_world.max(axis=0) + radius
    if np.any(center < chunk_min) or np.any(center > chunk_max):
        return None

    tri = idx_cpu      # (M,3)
    v0 = verts_world[tri[:, 0]]
    v1 = verts_world[tri[:, 1]]
    v2 = verts_world[tri[:, 2]]

    # Narrow-phase AABB cull per triangle
    tri_min = np.minimum(np.minimum(v0, v1), v2) - radius
    tri_max = np.maximum(np.maximum(v0, v1), v2) + radius
    in_range = np.all(center >= tri_min, axis=1) & np.all(center <= tri_max, axis=1)
    if not np.any(in_range):
        return None

    v0c = v0[in_range]; v1c = v1[in_range]; v2c = v2[in_range]

    closest = _closest_point_on_triangles(center, v0c, v1c, v2c)
    diff    = center - closest                      # (K,3)
    dist2   = (diff * diff).sum(axis=1)             # (K,)

    hits = dist2 < (radius * radius)
    if not np.any(hits):
        return None

    # Accumulate push vectors from all penetrating triangles
    d2h  = dist2[hits]
    dirh = diff[hits]                               # (H,3)
    dlen = np.sqrt(d2h)[:, None] + 1e-12
    norm = dirh / dlen                              # unit push direction
    pen  = radius - np.sqrt(d2h)                   # penetration depth

    # Total push: weight by penetration depth so deep hits dominate
    push = (norm * pen[:, None]).sum(axis=0)       # (3,)
    return push


# ─────────────────────────────────────────────────────────────────────────────
# Main Terrain / Static-mesh Collision
# ─────────────────────────────────────────────────────────────────────────────

# Controller type substrings that indicate water/air creatures — these should
# NEVER be pushed by terrain collision (they navigate intentionally).
_EXEMPT_CONTROLLER_SUBSTRINGS = ('Fish', 'Bird', 'GPU')


def get_world_position(obj, scene_map: dict, visited=None) -> np.ndarray:
    """Recursively calculate the world-space position of a parented object.
    
    scene_map: dict of id -> SceneObject
    """
    pos = np.array(obj.position, dtype=np.float64)
    if not obj.parent_id or obj.parent_id == "None":
        return pos
        
    if visited is None: visited = set()
    if obj.id in visited: return pos # Circular parenting guard
    visited.add(obj.id)
    
    parent = scene_map.get(obj.parent_id)
    if parent:
        # Simple translation-only parenting for now (matching SceneEditorWidget)
        return pos + get_world_position(parent, scene_map, visited)
    return pos

def resolve_terrain_collision(scene_objects: list, mesh_cache: dict,
                               voxel_objects: list = None,
                               landscape_objects: list = None):
    """Push physics-enabled objects out of static terrain and .mesh geometry.
    """
    # Safe snapshots to prevent 'access violation' if lists change during loop
    scene_list = list(scene_objects)
    cache_items = list(dict(mesh_cache).items())
    
    scene_map = {o.id: o for o in scene_list}

    dynamics = [
        o for o in scene_list
        if getattr(o, 'physics_enabled', False)
        and not _is_exempt(o)
    ]
    if not dynamics:
        return

    voxels    = voxel_objects    or []
    landscapes = landscape_objects or []

    # Collect all ready chunk VAO entries for voxel objects
    voxel_chunks = []   # list of (verts_cpu, idx_cpu, obj_world_pos_array)
    for vox in voxels:
        # Voxel object world pos (assuming voxel worlds aren't deeply parented, 
        # but using get_world_position for consistency)
        obj_pos = get_world_position(vox, scene_map)
        oid     = vox.id
        for key, entry in cache_items:
            # chunk keys contain the voxel object id
            if not isinstance(key, str) or oid not in key:
                continue
            if not isinstance(entry, dict):
                continue
            vc = entry.get('verts_cpu')
            ic = entry.get('idx_cpu')
            if vc is None or ic is None:
                continue
            voxel_chunks.append((vc, ic, obj_pos))

    has_terrain = bool(voxel_chunks) or bool(landscapes)

    for obj in dynamics:
        col_props = getattr(obj, 'collision_properties', None) or []
        prop      = col_props[0] if col_props else {}
        radius    = float(prop.get('radius', 0.5)) * max(getattr(obj, 'scale', [1, 1, 1]))
        
        # Determine world-space center for parented objects
        center    = get_world_position(obj, scene_map)
        total_push = np.zeros(3, dtype=np.float64)

        # ── 1. Voxel chunk triangle collision ─────────────────────────────
        for (vc, ic, obj_pos) in voxel_chunks:
            push = _sphere_vs_chunk_triangles(center, radius, vc, ic, obj_pos)
            if push is not None:
                total_push += push

        # ── 2. Landscape (deprecated) heightmap ───────────────────────────
        for land in landscapes:
            try:
                from py_editor.ui.procedural_system import sample_height
                h   = float(sample_height(obj.position[0], obj.position[2], land))
                floor_y = float(land.position[1]) + h + radius
                if obj.position[1] < floor_y:
                    total_push[1] = max(total_push[1], floor_y - obj.position[1])
            except Exception:
                pass

        # ── Apply accumulated push ─────────────────────────────────────────
        if np.any(total_push != 0):
            obj.position[0] += float(total_push[0])
            obj.position[1] += float(total_push[1])
            obj.position[2] += float(total_push[2])

            # Kill velocity components that point INTO the surface
            if hasattr(obj, 'velocity'):
                push_len = float(np.linalg.norm(total_push))
                if push_len > 1e-6:
                    push_norm = total_push / push_len
                    vel = np.array(obj.velocity, dtype=np.float64)
                    proj = float(np.dot(vel, push_norm))
                    if proj < 0:
                        obj.velocity = (vel - push_norm * proj).tolist()

        # ── 3. Static .mesh AABB collision ────────────────────────────────
        statics = [o for o in scene_objects
                   if not getattr(o, 'physics_enabled', False)
                   and getattr(o, 'obj_type', '') == 'mesh'
                   and getattr(o, 'mesh_path', None)]

        for stat in statics:
            entry = mesh_cache.get(getattr(stat, 'mesh_path', None))
            if not entry or 'aabb' not in entry:
                continue

            hx, hy, hz, cy_off = get_mesh_aabb_half_extents(entry)
            sx, sy, sz = getattr(stat, 'scale', [1, 1, 1])
            hx *= sx; hy *= sy; hz *= sz; cy_off *= sy

            # World-space AABB centre
            cx  = stat.position[0]
            cy_w = stat.position[1] + cy_off
            cz  = stat.position[2]

            dx = abs(obj.position[0] - cx) - (hx + radius)
            dy = abs(obj.position[1] - cy_w) - (hy + radius)
            dz = abs(obj.position[2] - cz) - (hz + radius)

            if dx < 0 and dy < 0 and dz < 0:
                # Resolve along minimum penetration axis only
                axes = [('x', dx), ('y', dy), ('z', dz)]
                axis, _ = max(axes, key=lambda a: a[1])
                if axis == 'x':
                    sign = math.copysign(1, obj.position[0] - cx)
                    obj.position[0] = cx + (hx + radius) * sign
                    if hasattr(obj, 'velocity'):
                        obj.velocity[0] = 0.0
                elif axis == 'y':
                    sign = math.copysign(1, obj.position[1] - cy_w)
                    obj.position[1] = cy_w + (hy + radius) * sign
                    if hasattr(obj, 'velocity') and obj.velocity[1] < 0:
                        obj.velocity[1] = 0.0
                else:
                    sign = math.copysign(1, obj.position[2] - cz)
                    obj.position[2] = cz + (hz + radius) * sign
                    if hasattr(obj, 'velocity'):
                        obj.velocity[2] = 0.0

        # ── 4. Fallback ground plane Y = 0 (no terrain at all) ───────────
        if not has_terrain:
            floor_y = radius
            if obj.position[1] < floor_y:
                obj.position[1] = floor_y
                if hasattr(obj, 'velocity') and obj.velocity[1] < 0:
                    obj.velocity[1] = 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _is_exempt(obj) -> bool:
    """Return True if the object should never be pushed by terrain collision.

    GPU fish and birds have their own spatial logic (swim below spawner Y,
    flock in 3-D). Applying terrain push would fight the GPU simulation.
    """
    ctrl = str(getattr(obj, 'controller_type', 'None'))
    for sub in _EXEMPT_CONTROLLER_SUBSTRINGS:
        if sub in ctrl:
            return True
    return False
