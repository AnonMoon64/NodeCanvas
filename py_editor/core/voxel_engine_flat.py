"""
voxel_engine_flat.py

Density generator for flat voxel worlds — a heightmap surface with optional
Minecraft-style tunnel caves carved underneath.

The cave system here is intentionally different from the round-planet generator:
flat worlds want long, horizontally-sprawling cylindrical tunnels (the classic
"spaghetti caves" look) rather than blobby chambers. We achieve that by
intersecting two independent ridged-perlin fields with heavy Y-compression —
where both fields cross zero simultaneously, a 1D tunnel line exists in 3D.
"""
import numpy as np


# --------------------------------------------------------------------------- #
#  Minecraft-style tunnels                                                    #
# --------------------------------------------------------------------------- #

def _mc_tunnel_distance(x, y, z, seed, perlin_3d):
    """Distance-to-tunnel-centerline field in perlin input units.

    Two horizontally-stretched perlin fields; the tunnel centerline is where
    both are zero. ``max(|p1|, |p2|)`` is a reasonable proxy for distance to
    that 1D curve — small near the centerline, growing outward.
    """
    y_sq = y * 0.35
    p1 = perlin_3d(x,               y_sq,         z,               seed=seed)
    p2 = perlin_3d(x * 1.1 + 17.0,  y_sq * 1.2,   z * 0.9 + 31.0,  seed=seed + 71)
    return np.maximum(np.abs(p1), np.abs(p2)).astype(np.float32)


def _mc_cavern_distance(x, y, z, seed, perlin_3d):
    """Distance-to-cavern-center field: rare wide rooms."""
    p = perlin_3d(x * 0.55, y * 0.55, z * 0.55, seed=seed + 233)
    return np.abs(p).astype(np.float32)


# --------------------------------------------------------------------------- #
#  Density                                                                    #
# --------------------------------------------------------------------------- #

def generate_flat_density(NX, NY, NZ, LX, LY, LZ, *, resolution, seed,
                          radius, layers, features, center,
                          perlin_3d, layer_noise, cellular_caves,
                          gen_params=None):
    """Flat-world density field (positive underground, zero at the surface)."""
    gp = gen_params or {}
    world_height = float(gp.get('world_height', 1.0))
    if layers:
        # Extract a 2D slice from the 3D grid: LX is (res, res, res).
        # LX[:, 0, :] gives a (res, res) array holding the X coordinates.
        LX2 = LX[:, 0, :]
        LZ2 = LZ[:, 0, :]
        
        # Feature-scale normalisation: fixed reference of 100u horizontal.
        ref_scale = 100.0
        # Amplitude budget: matches round-mode `noise_val * radius` semantics.
        amp_scale = ref_scale * 0.5 * world_height
        
        height2 = np.zeros_like(LX2, dtype=np.float32)
        for layer in layers:
            mask_thresh = float(layer.get('mask_threshold', 0.0))
            influence = 1.0
            if mask_thresh > 0:
                influence = np.clip((height2 - mask_thresh * 15.0) / 10.0, 0.0, 1.0)

            lx_flat = LX2 / ref_scale
            lz_flat = LZ2 / ref_scale
            raw = layer_noise(lx_flat, np.zeros_like(lx_flat),
                              lz_flat, layer, seed) * influence
            val = raw * amp_scale
            blend = layer.get('blend', 'add')
            if   blend == 'subtract': height2 -= val
            elif blend == 'multiply': height2 *= (1.0 + raw * 0.5)
            else:                     height2 += val
            
        # Broadcast the 2D heightmap (X, Z) back to 3D (X, Y, Z) and apply Y depth.
        # height2 is (res, res). Reshape to (res, 1, res) to broadcast against LY.
        density = height2[:, np.newaxis, :] - LY
    else:
        density = (-LY).astype(np.float32)   # Pure flat at Y = 0

    # --- Features pass ---
    if features and "caves" in features:
        # User-tunable cave params (see SceneObject voxel_cave_* defaults).
        tunnel_scale  = float(gp.get('tunnel_scale',  28.0))
        tunnel_r      = float(gp.get('tunnel_radius',  0.10))
        cavern_scale  = float(gp.get('cavern_scale',  60.0))
        cavern_r      = float(gp.get('cavern_radius',  0.05))
        waterline     = float(gp.get('waterline',      0.0))
        max_depth     = float(gp.get('max_depth',    512.0))
        # Transition width (input units): small → sharp walls.
        wall_w = 0.025

        # Early out: flat worlds stream ±80u vertically around the surface, so
        # roughly half the chunks sit entirely above ground (density < 0
        # everywhere) and cannot contain caves. Computing 3 perlin_3d fields
        # on a 41³ grid costs ~50ms; skipping it for all-air chunks takes the
        # cave-chunk budget from ~52ms to ~4ms. Also skip if the chunk sits
        # entirely below the waterline — caves are gated above that.
        if not ((density.max() > 0.0) and (density.min() < max_depth)):
            return density.astype(np.float32)
        if LY.max() < waterline:
            return density.astype(np.float32)
        # Minecraft-style tunnel network. Distance-field carve with a narrow
        # gradient band: constant deep negative inside, linear wall, solid
        # outside. Keeps walls cylindrical (no rolling hills from gradient
        # carve) without stair-steps (no binary edges).
        t_dist = _mc_tunnel_distance(
            LX / tunnel_scale, LY / tunnel_scale, LZ / tunnel_scale,
            seed=seed + 500, perlin_3d=perlin_3d)
        c_dist = _mc_cavern_distance(
            LX / cavern_scale, LY / cavern_scale, LZ / cavern_scale,
            seed=seed + 931, perlin_3d=perlin_3d)

        t_strength = np.clip((tunnel_r - t_dist) / wall_w, 0.0, 1.0)
        c_strength = np.clip((cavern_r - c_dist) / wall_w, 0.0, 1.0)
        carve_strength = np.maximum(t_strength, c_strength).astype(np.float32)

        # Gates: only carve underground (density > 0), above the waterline Y,
        # and above the max_depth floor. A short fade around each boundary
        # prevents a hard band from tearing the mesh.
        depth_fade = np.clip((max_depth - density) / 10.0, 0.0, 1.0)
        water_fade = np.clip((LY - waterline) / 3.0, 0.0, 1.0)
        above_ground = density < 0.0

        carve_depth = 60.0
        delta = carve_strength * carve_depth * depth_fade * water_fade
        density = np.where(above_ground, density, density - delta)

    return density.astype(np.float32)
