import sys
import os
import time
import numpy as np
from pathlib import Path
from unittest.mock import MagicMock

# Add project root to sys.path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

# Mock OpenGL since we are running without a GL context
sys.modules['OpenGL'] = MagicMock()
sys.modules['OpenGL.GL'] = MagicMock()
sys.modules['OpenGL.GLU'] = MagicMock()

from py_editor.ui.procedural_ocean import FFTOceanWaveGenerator

def profile_ocean():
    print("Profiling FFTOceanWaveGenerator (CPU side)...")
    res = 128
    gen = FFTOceanWaveGenerator(resolution=res, size=1000.0)
    
    iters = 100
    start = time.perf_counter()
    for i in range(iters):
        gen.update(i * 0.01)
    end = time.perf_counter()
    
    avg_ms = (end - start) / iters * 1000
    print(f"Resolution {res}x{res} average update time: {avg_ms:.2f} ms")

    res2 = 256
    gen2 = FFTOceanWaveGenerator(resolution=res2, size=1000.0)
    start = time.perf_counter()
    for i in range(iters):
        gen2.update(i * 0.01)
    end = time.perf_counter()
    
    avg_ms2 = (end - start) / iters * 1000
    print(f"Resolution {res2}x{res2} average update time: {avg_ms2:.2f} ms")

if __name__ == "__main__":
    profile_ocean()
