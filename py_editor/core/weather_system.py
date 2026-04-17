"""
weather_system.py

Global weather driver for NodeCanvas.

The Weather primitive is *not* a local particle emitter — it is a controller
that decides the current weather over a large region and uses the particle
system to render only what is near the player/camera.

Features
--------
- Weather types: Clear, Rain, Snow, Storm, Fog, Sandstorm (extensible).
- Two world modes:
    * "flat"      — infinite flat world. Weather cells tile on an XZ grid.
    * "spherical" — round planet. Cells are driven by lat/lon-like coords.
- Procedural weather selection: a location + date + time-of-day triple is
  hashed into a deterministic seed; noise over that seed picks the active
  weather + intensity for a cell.
- Weather "moves" by translating the cell grid offset over time (wind).
- Atmospheric sync: auto-finds an active Atmosphere object to pull
  time_of_day and date from; falls back to its own clock if none.

Wire-up
-------
`update_weather(weather_obj, scene_objects, camera_pos, dt)` is called every
frame from scene_view. It:
  1. Resolves time/date (from Atmosphere if present).
  2. Hashes (cell_ix, cell_iz, day_index, time_bucket) → (type, intensity).
  3. Ensures a particle emitter is registered around the camera for the
     current weather type; updates rate with intensity.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Optional, Tuple

import numpy as np

from py_editor.core.particle_system import (
    get_particle_manager, ParticleSpec, PARTICLE_PRESETS, spec_from_preset,
    spawn_in_disc,
)


WEATHER_TYPES = ["Clear", "Rain", "Snow", "Storm", "Fog", "Sandstorm"]


def _hash3(a: int, b: int, c: int) -> int:
    """Small 3-integer mixing hash — deterministic across runs."""
    x = (a * 374761393) ^ (b * 668265263) ^ (c * 2147483647)
    x = (x ^ (x >> 13)) * 1274126177
    return (x ^ (x >> 16)) & 0xFFFFFFFF


def _value_noise_2d(ix: int, iz: int, seed: int) -> float:
    """Cheap value-noise at integer lattice (ix,iz)."""
    return (_hash3(ix, iz, seed) & 0xFFFF) / 65535.0


def pick_weather_for_cell(ix: int, iz: int, day_index: int, time_bucket: int,
                          world_seed: int = 1234) -> Tuple[str, float]:
    """Deterministic weather for a (cell, day, time-bucket).

    Returns (weather_name, intensity 0-1).
    """
    h = _hash3(ix + day_index * 31, iz - day_index * 17, world_seed ^ time_bucket * 997)
    r = (h & 0xFFFF) / 65535.0
    intensity = ((h >> 16) & 0xFFFF) / 65535.0

    # Bias: most of the world should be Clear.
    if r < 0.55:
        return "Clear", 0.0
    if r < 0.75:
        return "Rain", 0.4 + intensity * 0.6
    if r < 0.85:
        return "Snow", 0.3 + intensity * 0.7
    if r < 0.92:
        return "Storm", 0.6 + intensity * 0.4
    if r < 0.97:
        return "Fog", 0.3 + intensity * 0.5
    return "Sandstorm", 0.5 + intensity * 0.5


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _find_atmosphere(scene_objects):
    for o in scene_objects:
        if getattr(o, 'obj_type', '') == 'atmosphere' and getattr(o, 'active', True):
            return o
    return None


def _resolve_time_date(weather_obj, scene_objects):
    atmo = _find_atmosphere(scene_objects)
    if atmo is not None:
        return (float(getattr(atmo, 'time_of_day', 0.5)),
                int(getattr(atmo, 'date_day_index', 0)))
    # fallback — use weather clock
    t = time.time() * getattr(weather_obj, 'weather_time_rate', 0.005)
    day = int(t)
    tod = t - day
    return tod, day


def _cell_coords_flat(cam_pos, cell_size):
    ix = int(math.floor(cam_pos[0] / cell_size))
    iz = int(math.floor(cam_pos[2] / cell_size))
    return ix, iz


def _cell_coords_spherical(cam_pos, planet_center, planet_radius, cell_count=64):
    """Convert camera to lat/lon buckets on a sphere."""
    dx = cam_pos[0] - planet_center[0]
    dy = cam_pos[1] - planet_center[1]
    dz = cam_pos[2] - planet_center[2]
    r = math.sqrt(dx*dx + dy*dy + dz*dz) + 1e-6
    lat = math.asin(dy / r)           # -pi/2 .. pi/2
    lon = math.atan2(dz, dx)          # -pi .. pi
    ix = int((lon + math.pi) / (2 * math.pi) * cell_count)
    iz = int((lat + math.pi/2) / math.pi * cell_count)
    return ix, iz


_EMITTER_NAME = "weather_primary"


def _preset_for(weather: str) -> Optional[str]:
    if weather == "Rain":      return "Rain"
    if weather == "Snow":      return "Snow"
    if weather == "Storm":     return "Rain"
    if weather == "Fog":       return "Mist"
    if weather == "Sandstorm": return "Dust"
    return None


def update_weather(weather_obj, scene_objects, camera_pos, dt: float):
    """Called every frame by scene_view; maintains global weather state."""
    if weather_obj is None or not getattr(weather_obj, 'active', True):
        return

    # 1. Resolve clock
    tod, day_idx = _resolve_time_date(weather_obj, scene_objects)
    time_bucket = int(tod * 4)  # 4 buckets per day

    # 2. Pick cell (type depends on world mode)
    mode = getattr(weather_obj, 'weather_mode', 'flat')  # 'flat' | 'spherical'
    world_seed = int(getattr(weather_obj, 'weather_seed', 1234))
    wind = np.array(getattr(weather_obj, 'weather_wind', [8.0, 0.0, 0.0]), dtype=np.float32)

    # Slide weather with wind: apply an offset derived from time_bucket*dt*wind
    t_now = time.time()
    offs_x = wind[0] * t_now * 0.05
    offs_z = wind[2] * t_now * 0.05
    shifted_cam = (camera_pos[0] - offs_x, camera_pos[1], camera_pos[2] - offs_z)

    if mode == 'spherical':
        centre = getattr(weather_obj, 'planet_center', [0.0, 0.0, 0.0])
        radius = float(getattr(weather_obj, 'planet_radius', 5000.0))
        ix, iz = _cell_coords_spherical(shifted_cam, centre, radius)
    else:
        cell_size = float(getattr(weather_obj, 'weather_cell_size', 800.0))
        ix, iz = _cell_coords_flat(shifted_cam, cell_size)

    # 3. Manual override takes priority
    override = getattr(weather_obj, 'weather_type_override', 'Auto')
    if override and override != 'Auto':
        weather = override
        intensity = float(getattr(weather_obj, 'weather_intensity_override', 0.8))
    else:
        weather, intensity = pick_weather_for_cell(ix, iz, day_idx, time_bucket, world_seed)

    weather_obj._current_weather = weather
    weather_obj._current_intensity = intensity

    # 3.5 MODULAR: Attach logic based on weather type
    weather_logic_map = {
        "Rain":  "py_editor/nodes/graphs/RainImpact.logic",
        "Storm": "py_editor/nodes/graphs/RainImpact.logic",
    }
    target_logic = weather_logic_map.get(weather, "")
    # Only update if changed to avoid re-booting IR every frame
    existing_logics = getattr(weather_obj, 'logic_list', [])
    if target_logic:
        if existing_logics != [target_logic]:
            weather_obj.logic_list = [target_logic]
    elif existing_logics:
        weather_obj.logic_list = []

    # 4. Register / update the particle emitter near the camera
    mgr = get_particle_manager()
    preset = _preset_for(weather)
    existing = mgr.emitters.get((weather_obj.id, _EMITTER_NAME))

    if preset is None or intensity <= 0.01:
        # Clear weather — tear down
        if existing:
            mgr.unregister(weather_obj, _EMITTER_NAME)
        return

    # Build spec
    overrides = {}
    base_rate = PARTICLE_PRESETS[preset].get('rate', 500)
    overrides['rate'] = float(base_rate * (0.4 + 1.2 * intensity))
    if weather == "Storm":
        # Heavier rain + stronger wind
        overrides['speed_min'] = 30.0
        overrides['speed_max'] = 45.0
        overrides['forces'] = [
            {"type": "gravity", "magnitude": 22.0},
            {"type": "wind", "vector": [wind[0] * 1.2, 0.0, wind[2] * 1.2]},
        ]
    elif weather == "Rain":
        overrides['forces'] = [
            {"type": "gravity", "magnitude": 15.0},
            {"type": "wind", "vector": [wind[0] * 0.3, 0.0, wind[2] * 0.3]},
        ]
    elif weather == "Snow":
        overrides['forces'] = [
            {"type": "gravity", "magnitude": 0.6},
            {"type": "wind", "vector": [wind[0] * 0.2, 0.0, wind[2] * 0.2]},
            {"type": "turbulence", "strength": 0.7, "frequency": 0.2},
        ]

    spec = spec_from_preset(preset, overrides)

    # 4.5 Environmental Culling: Don't let rain go through the ocean
    ocean_obj = next((o for o in scene_objects if getattr(o, 'obj_type', '') == 'ocean' and getattr(o, 'active', True)), None)
    if ocean_obj:
        # Pad slightly to ensure quads don't flicker at exactly 0
        spec.kill_height = float(getattr(ocean_obj, 'landscape_ocean_level', 0.0)) - 0.2

    # Spawn disc pinned to camera for truly global weather
    cam_height_offset = 30.0 if weather in ("Rain", "Storm", "Snow") else 8.0
    # Increased radius to 500 to cover full viewport and prevent outrunning even at high speed
    disc_radius = float(spec.stream_radius) if spec.stream_radius > 0 else 500.0
    # Attach reference to camera via weather_obj so spawn_source can read it
    weather_obj._cam_pos_ref = tuple(camera_pos)
    spec.spawn_source = spawn_in_disc(radius=disc_radius, height=cam_height_offset, center_from_camera=True)
    spec.receive_weather = True

    if existing:
        existing.spec = spec
        existing.pool.spec = spec
    else:
        mgr.register(weather_obj, _EMITTER_NAME, spec)
