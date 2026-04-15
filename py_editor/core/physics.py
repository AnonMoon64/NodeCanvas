"""
physics.py

Basic physics utilities: simple collision resolution and helpers.
This is intentionally lightweight: sphere-sphere collision resolution
with positional separation and simple velocity impulses.
"""
import math
from typing import List


def resolve_collisions(scene_objects: List[object], dt: float, restitution: float = 0.15):
    """Resolve simple sphere collisions for objects that have physics enabled.

    - Uses the first entry of `collision_properties` for each object as the
      primary collision primitive.
    - Moves objects apart proportionally to inverse mass and applies a
      simple impulse to their velocity.
    """
    objs = [o for o in scene_objects if getattr(o, 'physics_enabled', True)]
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
                # Perfect overlap: nudge along X axis
                dist = 1e-6
                nx, ny, nz = 1.0, 0.0, 0.0
            else:
                dist = math.sqrt(dist2)
                nx, ny, nz = dx / dist, dy / dist, dz / dist

            overlap = (ra + rb) - dist
            if overlap > 0.0:
                # Positional correction (split by inverse mass ratio)
                inv_total = (1.0 / ma) + (1.0 / mb) if (ma + mb) > 0 else 1.0
                if inv_total == 0:
                    continue

                # Move amounts
                move_a = (1.0 / ma) / inv_total * overlap
                move_b = (1.0 / mb) / inv_total * overlap

                # Apply small position corrections (push out along normal)
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

                # Ensure velocity attributes exist
                va = list(getattr(a, 'velocity', [0.0, 0.0, 0.0]))
                vb = list(getattr(b, 'velocity', [0.0, 0.0, 0.0]))

                # Relative velocity along normal
                rel_v = (va[0] - vb[0]) * nx + (va[1] - vb[1]) * ny + (va[2] - vb[2]) * nz

                # Apply impulse if objects are approaching
                if rel_v < 0:
                    j_impulse = -(1.0 + restitution) * rel_v / inv_total
                    # Delta v
                    da = j_impulse / ma
                    db = j_impulse / mb
                    va[0] += nx * da; va[1] += ny * da; va[2] += nz * da
                    vb[0] -= nx * db; vb[1] -= ny * db; vb[2] -= nz * db

                    # Commit back
                    try:
                        a.velocity = va
                    except Exception:
                        pass
                    try:
                        b.velocity = vb
                    except Exception:
                        pass

    # End resolve_collisions
