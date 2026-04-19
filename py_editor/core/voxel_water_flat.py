"""
voxel_water_flat.py

Density generator for flat voxel water. Creates a perfectly flat horizontal 
plane at a specified height.
"""
import numpy as np

def generate_water_flat_density(NX, NY, NZ, LX, LY, LZ, *, resolution, seed,
                               radius, layers, features, center,
                               perlin_3d, layer_noise, cellular_caves,
                               gen_params=None):
    """Procedural dynamic water density at a fixed height."""
    gp = gen_params or {}
    level = float(gp.get('water_level', 0.0))
    
    # Simple constant flat density based on water level
    density = (level - LY).astype(np.float32)
    
    # Simple water blue color
    colors = np.ones((*density.shape, 3), dtype=np.float32)
    colors[:] = [0.1, 0.4, 0.8]
    
    return density, colors
