import sys
import os
import time
import math
import numpy as np
from pathlib import Path
from unittest.mock import MagicMock

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from py_editor.ui.procedural_system import (
    draw_landscape_3d, 
    spawn_instances, 
    _pending_chunks, 
    _completed_chunk_data,
    _landscape_display_list_cache
)

class MockCamera:
    def __init__(self, pos=[0,0,0]):
        self.pos = pos
        self.yaw = 0
        self.pitch = 0
        self.fov = 45

class MockViewport:
    def __init__(self):
        self.scene_objects = []
        self._cam3d = MockCamera()
    def update(self): pass

class MockLandscapeProject:
    def __init__(self):
        self.id = "land_0"
        self.obj_type = "landscape"
        self.position = [0,0,0]
        self.rotation = [0,0,0]
        self.scale = [1,1,1]
        self.landscape_type = "procedural"
        self.landscape_size_mode = "infinite"
        self.landscape_chunk_size = 128.0
        self.landscape_grid_radius = 2  # (2*2+1)^2 = 25 chunks
        self.landscape_resolution = 32
        self.landscape_seed = 123
        self.landscape_noise_layers = [{'amp': 20, 'freq': 0.01, 'type': 'perlin'}]
        self.landscape_spawn_enabled = True
        self.landscape_render_bias = -0.02

def test_infinite_streaming():
    print("\n[TEST] Starting Headless Infinite Landscape Test...")
    vp = MockViewport()
    obj = MockLandscapeProject()
    
    # 1. INITIAL GENERATION
    print(f"[TEST] Phase 1: Initial Spawning at {vp._cam3d.pos}")
    
    # MOCK OPENGL.GL COMPLETELY
    mock_gl = MagicMock()
    sys.modules["OpenGL.GL"] = mock_gl
    sys.modules["OpenGL"] = MagicMock()

    # Call draw_landscape_3d
    draw_landscape_3d(obj, vp)
    
    time.sleep(1.0) # Wait for background tasks
    print(f"[TEST] Chunks pending: {len(_pending_chunks)}")
    print(f"[TEST] Chunks ready: {len(_completed_chunk_data)}")

    # 2. MOVEMENT TEST
    print("\n[TEST] Phase 2: Rapid Movement")
    vp._cam3d.pos = [1000, 0, 1000]
    draw_landscape_3d(obj, vp)
    
    # Check if more tasks are queued
    print(f"[TEST] Chunks pending after move: {len(_pending_chunks)}")
    
    # 3. SPAWNING THROTTLE TEST
    print("\n[TEST] Phase 3: Vegetation Spawning Throttle")
    # Reset objects
    if hasattr(obj, '_spawned_chunks'): del obj._spawned_chunks
    
    # Simulate move to a spot that needs 25 chunks
    spawn_instances(vp, obj, cam_pos=vp._cam3d.pos)
    spawned_count = len(getattr(obj, '_spawned_chunks', {}))
    print(f"[TEST] Chunks spawned after 1st call: {spawned_count}")
    
    spawn_instances(vp, obj, cam_pos=vp._cam3d.pos)
    spawned_count_2 = len(getattr(obj, '_spawned_chunks', {}))
    print(f"[TEST] Chunks spawned after 2nd call: {spawned_count_2}")
    
    if spawned_count == 1 and spawned_count_2 == 2:
        print("[TEST PASS] Liquid-Smooth Spawning Throttle is WORKING (1 chunk/frame).")
    else:
        print(f"[TEST FAIL] Throttle failed: expected 1 and 2, got {spawned_count} and {spawned_count_2}")

if __name__ == "__main__":
    test_infinite_streaming()
