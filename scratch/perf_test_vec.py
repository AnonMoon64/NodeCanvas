import time
import sys
from pathlib import Path
import numpy as np

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from py_editor.ui.procedural_system import sample_height

class MockObj:
    def __init__(self):
        self.landscape_type = "procedural"
        self.landscape_seed = 123
        self.landscape_noise_layers = [
            {'amp': 20, 'freq': 0.01, 'type': 'perlin', 'octaves': 6},
            {'amp': 5, 'freq': 0.05, 'type': 'simplex', 'octaves': 4},
            {'amp': 2, 'freq': 0.1, 'type': 'worley', 'octaves': 3}
        ]
        self.landscape_height_scale = 30.0

obj = MockObj()

print("[PERF] Vectorized test: 1 chunk (32x32 = 1024 points)...")
rows, cols = 32, 32
c_range = np.linspace(-0.5, 0.5, cols + 1)
r_range = np.linspace(-0.5, 0.5, rows + 1)
C, R = np.meshgrid(c_range, r_range)

start = time.perf_counter()
sample_height(C, R, obj)
end = time.perf_counter()
print(f"[PERF] 1024 points (Vectorized) took: {(end-start)*1000:.2f}ms")

print("[PERF] Vectorized test: 121 drafts (121 * 4x4 = 1936 points)...")
C_bulk = np.random.random((121, 4, 4))
R_bulk = np.random.random((121, 4, 4))
start = time.perf_counter()
sample_height(C_bulk, R_bulk, obj)
end = time.perf_counter()
print(f"[PERF] 1936 points (Vectorized) took: {(end-start)*1000:.2f}ms")
