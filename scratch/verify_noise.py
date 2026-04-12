import sys
import os
import numpy as np
import math

# Add the project root to path
sys.path.append('c:/Users/AnonM/Desktop/NodeCanvas')

from py_editor.ui.procedural_system import sample_height

class MockObj:
    def __init__(self):
        self.landscape_type = 'procedural'
        self.landscape_seed = 42
        self.landscape_noise_layers = [
            {'amp': 10.0, 'freq': 0.1, 'octaves': 3, 'mode': 'ridged', 'exponent': 2.0, 'type': 'perlin'}
        ]

obj = MockObj()

# Test Single Point
h = sample_height(0.0, 0.0, obj)
print(f"Single point height: {h}")

# Test Vectorized
x = np.linspace(-10, 10, 5)
z = np.linspace(-10, 10, 5)
X, Z = np.meshgrid(x, z)
H = sample_height(X, Z, obj)
print(f"Vectorized height shape: {H.shape}")
print(f"Vectorized height sample [0,0]: {H[0,0]}")

assert H.shape == (5, 5)
assert isinstance(H, np.ndarray)

print("SUCCESS: Vectorized noise engine is functional.")
