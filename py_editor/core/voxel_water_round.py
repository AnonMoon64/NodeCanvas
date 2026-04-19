"""
voxel_water_round.py

Density generator for round (planet) voxel water. Creates a spherical 
shell around the planet center.
"""
import numpy as np

def generate_water_round_density(NX, NY, NZ, LX, LY, LZ, *, resolution, seed,
                                radius, layers, features, center,
                                perlin_3d, layer_noise, cellular_caves,
                                gen_params=None):
    """Procedural dynamic spherical water density with 'uphill' surge logic."""
    gp = gen_params or {}
    level  = float(gp.get('water_level', 0.0)) # radius offset
    speed  = float(gp.get('water_speed', 1.0))
    surge  = float(gp.get('water_surge', 0.5))
    u_time = float(gp.get('u_time', 0.0))
    
    dist = np.sqrt(LX**2 + LY**2 + LZ**2, dtype=np.float32)
    
    # Static shell around the planet radius
    target_radius = radius + level
    density = (target_radius - dist).astype(np.float32)
    
    # Water blue
    colors = np.ones((*density.shape, 3), dtype=np.float32)
    colors[:] = [0.1, 0.4, 0.8]
    
    return density, colors
