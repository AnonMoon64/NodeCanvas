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
print("[PERF] Testing 36 samples (1 chunk spawn)...")
start = time.perf_counter()
for _ in range(36):
    sample_height(np.random.random()*1000, np.random.random()*1000, obj)
end = time.perf_counter()
print(f"[PERF] 36 samples took: {(end-start)*1000:.2f}ms")

print("[PERF] Testing 121 chunks * 16 samples (Drafts)...")
start = time.perf_counter()
for _ in range(121 * 16):
    sample_height(np.random.random()*1000, np.random.random()*1000, obj)
end = time.perf_counter()
print(f"[PERF] 1936 samples took: {(end-start)*1000:.2f}ms")
