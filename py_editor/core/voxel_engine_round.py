"""
voxel_engine_round.py

Density generator for round (planet) voxel worlds. Builds a signed-distance-like
field whose zero crossing is the planet surface, then layers on Perlin / fbm /
ridged / voronoi / caves noise controlled by the object's ``voxel_layers`` and
carves multi-scale cellular caves when ``"caves"`` is in ``voxel_features``.

Kept as a separate module from the flat generator so each world type can evolve
its features independently without affecting the other.
"""
import numpy as np


def generate_round_density(NX, NY, NZ, LX, LY, LZ, *, resolution, seed,
                           radius, layers, features, center,
                           perlin_3d, layer_noise, cellular_caves,
                           gen_params=None):
    """Round (planet) density field.

    Parameters are the same coordinates prepared by the dispatcher so we don't
    duplicate meshgrid construction:
      - NX/NY/NZ : normalised coords (inside radius ≈ [-1, 1])
      - LX/LY/LZ : world-space offsets from the planet centre
      - perlin_3d / layer_noise / cellular_caves : shared noise helpers
    """
    dist    = np.sqrt(LX**2 + LY**2 + LZ**2, dtype=np.float32)
    density = (radius - dist).astype(np.float32)

    if layers:
        # Use a world-space amp scale that adapts to the planet's radius.
        # Scaling by radius**0.4 ensures mountains grow enough to be
        # significant on giant planets without getting out of control.
        amp_factor = (radius / 1000.0) ** 0.4
        amp_scale  = 50.0 * max(1.0, amp_factor)
        for layer in layers:
            # Layer Height Masking: restrict current noise based on
            # existing ground height (density).
            mask_thresh = float(layer.get('mask_threshold', 0.0))
            influence = 1.0
            if mask_thresh > 0:
                # Only apply noise where density > mask_thresh * scale.
                # Allows 'Mountains' to only spawn on 'Continents'.
                influence = np.clip((density - mask_thresh * 25.0) / 10.0, 0.0, 1.0)

            noise_val = layer_noise(NX, NY, NZ, layer, seed) * influence
            blend = layer.get('blend', 'add')
            if   blend == 'subtract': density -= noise_val * amp_scale
            elif blend == 'multiply': density *= (1.0 + noise_val)
            else:                     density += noise_val * amp_scale

    # --- Features pass (e.g. Caves) ---
    if features and "caves" in features:
        feature_scale = max(1.0, (radius / 1000.0) ** 0.4)
        big_scale   = 48.0 * feature_scale
        small_scale = 16.0 * feature_scale

        c_big   = cellular_caves(
            LX / big_scale,   LY / big_scale,   LZ / big_scale,   seed=seed + 500)
        c_small = cellular_caves(
            LX / small_scale, LY / small_scale, LZ / small_scale, seed=seed + 931)
        c_noise = np.maximum(c_big, c_small * 0.7).astype(np.float32)

        carve_depth = 8.0

        # Preserve a 3u-thick surface crust so we don't punch through the
        # ground. Allow caves all the way down to 25% of the planet radius.
        inner_r = max(0.25 * radius, 2.0)
        outer_r = max(radius - 3.0, inner_r + 1.0)
        surface_fade = np.clip((outer_r - dist) / 6.0, 0.0, 1.0)
        core_fade    = np.clip((dist - inner_r) / 6.0, 0.0, 1.0)
        depth_mask   = surface_fade * core_fade
        density -= c_noise * carve_depth * depth_mask

    # --- Coloring (Gray top, Brown dirt) ---
    res_x, res_y, res_z = density.shape
    colors = np.ones((res_x, res_y, res_z, 3), dtype=np.float32)
    # Default stony gray for planet surface
    colors[:] = [0.45, 0.45, 0.48]
    
    # Buried voxels (density > 1.0) become brown dirt/rock
    is_buried = density > 1.0
    colors[is_buried] = [0.35, 0.22, 0.15]

    return density.astype(np.float32), colors
