"""
object_system.py

All scene objects (Landscape, Ocean, Atmosphere, Universe) and their properties.
"""
import uuid
from typing import List, Tuple, Optional
from py_editor.ui.shared_styles import MATERIAL_PRESETS, DEFAULT_MATERIAL, OBJECT_COLOR

class SceneObject:
    """Represents an entity in the scene."""

    def __init__(self, name: str, obj_type: str, position=None, rotation=None, scale=None):
        self.id = str(uuid.uuid4())[:8]
        self.name = name
        self.obj_type = obj_type
        self.position = list(position or [0.0, 0.0, 0.0])
        self.rotation = list(rotation or [0.0, 0.0, 0.0])
        self.scale = list(scale or [1.0, 1.0, 1.0])
        self.selected = False
        self.color = list(OBJECT_COLOR)
        self.file_path = None
        self.mesh_path = None
        self.texture_path = None
        self.pbr_maps = {
            "albedo": None,
            "normal": None,
            "roughness": None,
            "metallic": None,
            "ao": None,
            "displacement": None
        }
        self.pbr_tiling = [1.0, 1.0]
        self.pbr_displacement_scale = 0.05
        self.parent_id = None
        self._parent = None # Cached reference for fast matrix calc
        self.children_ids = []
        self.ocean_opacity = 0.6
        if self.obj_type == 'ocean':
            self.material = dict(MATERIAL_PRESETS['Water'])
            self.material['preset'] = 'Water'
            # Auto-attach base volumetric spray logic
            self.logic_list = ["py_editor/nodes/graphs/OceanSpray.logic"]
        else:
            self.material = dict(DEFAULT_MATERIAL)
        self.active = True
        self.visible = (obj_type not in ('camera', 'light_point', 'light_directional'))
        self.intensity = 1.0
        self.is_procedural = False 
        self.range = 10.0  
        self.fov = 60.0    
        self.camera_speed = 10.0
        self.camera_sensitivity = 0.15
        self.controller_type = "None"
        self.alpha = 1.0
        
        # --- Environment & Unified Lighting ---
        self.sun_color = [1.0, 1.0, 0.9, 1.0]
        self.moon_color = [0.6, 0.7, 1.0, 1.0]
        self.ambient_color = [0.1, 0.1, 0.2, 1.0]
        self.moon_intensity = 1.0
        self.light_update_mode = "Auto" # "Auto", "Manual Sun", "Manual Moon"
        
        # Atmosphere Properties (Existing)
        self.time_of_day = 0.25 # 0.0 is midnight, 0.5 is noon
        self.sky_density = 1.0
        self.cloud_density = 0.5
        self.time_speed = 0.0           # auto-advance time_of_day per second (0 = manual)
        self.date_day_index = 0          # integer day counter for procedural weather seeding
        # Planet / spherical-atmosphere support
        self.planet_mode = False         # Atmosphere: wrap onto a sphere (planet)
        self.planet_radius = 6371.0
        self.atmosphere_thickness = 1200.0
        self.planet_center = [0.0, 0.0, 0.0]
        self.ground_albedo = [0.25, 0.3, 0.2]
        self.rayleigh_strength = 1.0
        self.mie_strength = 1.0
        self.god_rays_strength = 0.6
        self.exposure = 1.0
        # 3D volumetric cloud properties
        self.cloud_coverage = 0.5
        self.cloud_absorption = 0.8
        self.cloud_anvil = 0.3
        self.cloud_wind = [6.0, 0.0, 2.0]
        self.cloud_steps = 48
        self.cloud_layer_bottom = 900.0
        self.cloud_layer_top = 2200.0
        # Weather primitive properties
        self.weather_mode = 'flat'          # 'flat' | 'spherical'
        self.weather_type_override = 'Auto' # 'Auto'|'Clear'|'Rain'|'Snow'|'Storm'|'Fog'|'Sandstorm'
        self.weather_intensity_override = 0.8
        self.weather_seed = 1234
        self.weather_cell_size = 800.0
        self.weather_wind = [8.0, 0.0, 0.0]
        self.weather_time_rate = 0.005
        self._current_weather = 'Clear'
        self._current_intensity = 0.0
        
        # Sun & Universe
        self.sun_size = 1.0            # 1.0 is "Standard"
        self.sun_intensity = 10.0
        self.star_density = 1.0
        self.star_brightness = 1.0
        self.nebula_intensity = 0.5

        # Landscape-specific properties
        self.landscape_type = 'procedural'
        self.landscape_size_mode = 'finite'
        self.landscape_chunk_size = 128
        self.landscape_grid_radius = 1
        self.landscape_resolution = 32
        self.landscape_render_bias = -0.02
        self.landscape_seed = 123
        self.landscape_height_scale = 150.0
        self.landscape_ocean_level = 0.08
        self.landscape_ocean_flattening = 0.4
        self.landscape_tip_smoothing = 0.1
        self.landscape_noise_layers = [
            {'type': 'perlin', 'mode': 'fbm', 'amp': 1.0, 'freq': 0.007, 'octaves': 4, 'persistence': 0.45, 'lacunarity': 2.0, 'weight': 1.2, 'exponent': 1.0},
            {'type': 'perlin', 'mode': 'ridged', 'amp': 0.65, 'freq': 0.012, 'octaves': 3, 'persistence': 0.5, 'lacunarity': 2.1, 'weight': 0.4, 'exponent': 2.5},
            {'type': 'perlin', 'mode': 'fbm', 'amp': 0.15, 'freq': 0.04, 'octaves': 3, 'persistence': 0.5, 'lacunarity': 2.0, 'weight': 0.15, 'exponent': 1.0}
        ]
        self.landscape_biomes = [
            {'name': 'Deep Ocean', 'height_range': [-1000.0, -5.0], 'slope_range': [0.0, 1.0], 'surface': {'color': [0.05, 0.1, 0.3, 1.0], 'roughness': 0.1, 'metallic': 0.2}},
            {'name': 'Shallow Water', 'height_range': [-5.0, 0.0], 'slope_range': [0.0, 1.0], 'surface': {'color': [0.1, 0.4, 0.6, 1.0], 'roughness': 0.2, 'metallic': 0.1}},
            {'name': 'Beach', 'height_range': [0.0, 2.0], 'slope_range': [0.0, 0.2], 'surface': {'color': [0.85, 0.8, 0.65, 1.0], 'roughness': 0.9, 'metallic': 0.0}},
            {'name': 'Grassland', 'height_range': [2.0, 15.0], 'slope_range': [0.0, 0.15], 'surface': {'color': [0.25, 0.4, 0.1, 1.0], 'roughness': 0.8, 'metallic': 0.0}},
            {'name': 'Forest', 'height_range': [15.0, 35.0], 'slope_range': [0.15, 0.4], 'surface': {'color': [0.1, 0.25, 0.05, 1.0], 'roughness': 0.9, 'metallic': 0.0}},
            {'name': 'Mountain', 'height_range': [35.0, 1000.0], 'slope_range': [0.4, 1.0], 'surface': {'color': [0.4, 0.4, 0.45, 1.0], 'roughness': 0.7, 'metallic': 0.0}},
            {'name': 'Snow Cap', 'height_range': [45.0, 1000.0], 'slope_range': [0.0, 1.0], 'surface': {'color': [0.95, 0.95, 1.0, 1.0], 'roughness': 0.3, 'metallic': 0.0}}
        ]
        self.landscape_spawn_enabled = False
        self.landscape_spawn_rows = 1
        self.landscape_spawn_cols = 1
        self.landscape_spawn_spacing = [10.0, 10.0] 
        self.visualize_climate = False
        self.landscape_features = [] # List of strings: ["caves", "ores", etc.]
        # Ocean properties
        self.ocean_wave_speed = 3.5
        self.ocean_wave_scale = 1.0
        self.ocean_wave_steepness = 0.3
        self.ocean_foam_amount = 0.1
        self.ocean_fft_resolution = 256
        self.ocean_wave_choppiness = 1.5
        self.ocean_wave_intensity = 1.0
        self.ocean_use_fft = True
        
        # Advanced Ocean Visuals
        self.ocean_fresnel_strength = 0.3
        self.ocean_specular_intensity = 1.0
        self.ocean_reflection_tint = [0.5, 0.7, 1.0, 1.0] # Sky blue tint
        
        # Logic assignment (Array/List of scripts)
        if not hasattr(self, 'logic_list'):
            self.logic_list = [] # List of paths to .logic files
        
        # Voxel World Specifics
        self.voxel_type = "Round"    # "Round" or "Flat"
        self.voxel_radius = 60000.0    # Default "Large"
        self.voxel_block_size = 1.0
        self.voxel_seed = 123
        # voxel_lod_enabled kept for backwards compatibility with saved scenes;
        # the engine now always uses camera-distance LOD and ignores this value.
        self.voxel_lod_enabled = True
        self.voxel_lod_layers = 6
        self.voxel_octree_depth = 8
        self.voxel_smooth_iterations = 2
        self.voxel_render_style = "Smooth"
        # Flat voxel worlds stream around the camera when enabled (on by default).
        # Disable to pin a fixed 100u terrain box around the object's position.
        self.voxel_infinite_flat = True
        self.voxel_layers = []
        self.voxel_biomes = []
        self.voxel_features = [] # ["caves"]
        # Flat-world vertical scale multiplier. 1.0 = current default (±50u peaks
        # from layer amp=1.0). Raise to let mountains go higher.
        self.voxel_world_height = 1.0
        # Cave feature parameters (used when 'caves' is in voxel_features).
        # Tunnel radius / scale control passage width; cavern control wide rooms.
        # Waterline Y gates cave carving — caves don't generate below this level
        # so they don't flood when the world has water below Y=0.
        self.voxel_cave_tunnel_scale  = 28.0
        self.voxel_cave_tunnel_radius = 0.10
        self.voxel_cave_cavern_scale  = 60.0
        self.voxel_cave_cavern_radius = 0.05
        self.voxel_cave_waterline     = 0.0
        self.voxel_cave_max_depth     = 512.0

        # Ocean World (spherical ocean on round planets)
        self.ocean_world_radius = 0.48      # Slightly inside planet radius
        self.ocean_world_wave_speed = 3.0
        self.ocean_world_wave_intensity = 0.015
        self.ocean_world_color = [0.05, 0.25, 0.6, 0.85]
        
        # Custom Shader Support
        self.shader_name = "Standard"
        self.shader_params = {
            "speed": 2.0, "freq": 1.5, "intensity": 1.0,
            "yaw_amp": 0.2, "side_amp": 0.1, "roll_amp": 0.05, "flag_amp": 0.05,
            "wave_speed": 3.0, "wave_amplitude": 0.1,
            "forward_axis": 0.0, "invert_axis": 0.0,
            "base_color": [1.0, 1.0, 1.0, 1.0]
        }

        # Physics properties (base)
        self.velocity = [0.0, 0.0, 0.0]
        self.acceleration = [0.0, 0.0, 0.0]
        self.physics_enabled = True
        self.mass = 1.0
        # Collision properties: list of dicts {tag, shape, radius, offset, enabled}
        self.collision_properties = [
            {"tag": "default", "shape": "sphere", "radius": 0.5 * max(self.scale), "offset": [0.0, 0.0, 0.0], "enabled": True}
        ]

    def to_dict(self) -> dict:
        d = self.__dict__.copy()
        return d

    @staticmethod
    def from_dict(d: dict) -> 'SceneObject':
        obj = SceneObject(d['name'], d['type'], d.get('position'), d.get('rotation'), d.get('scale'))
        for k, v in d.items():
            if k == 'logic_path' and 'logic_list' not in d:
                obj.logic_list = [v] if v else []
            elif k == 'logic_list':
                # Special migration: If it's an ocean and we have a new default logic, 
                # don't overwrite with an empty saved list.
                if obj.obj_type == 'ocean' and not v:
                    continue # Keep the default ["...OceanSpray.logic"] set in __init__
                obj.logic_list = list(v)
            elif hasattr(obj, k):
                setattr(obj, k, v)
        return obj
