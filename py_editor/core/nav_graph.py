"""
nav_graph.py

Simple spherical-aware navigation helpers.

This module provides a tiny NavGraph class with a random-point sampler and
stubbed pathfinding. It is not a full voxel-graph implementation but provides
useful primitives for node-level GetRandomPointInNavigation and basic
pathfinding placeholders for MoveTo.
"""
import math
import random
from typing import Tuple, List


class NavGraph:
    def __init__(self):
        # Placeholder - in future this can hold a sampled voxel graph
        self.nodes = []

    def random_point_in_sphere(self, center: Tuple[float, float, float], radius: float) -> Tuple[float, float, float]:
        # Uniform sampling within sphere
        while True:
            x = random.uniform(-1.0, 1.0)
            y = random.uniform(-1.0, 1.0)
            z = random.uniform(-1.0, 1.0)
            if x*x + y*y + z*z <= 1.0:
                return (center[0] + x * radius, center[1] + y * radius, center[2] + z * radius)

    def random_point_on_surface_ring(self, center, radius, min_alt=0.0, max_alt=0.0):
        # For planets one may want surface points; keep simple: random point on sphere surface
        theta = random.uniform(0, 2 * math.pi)
        phi = math.acos(random.uniform(-1, 1))
        x = math.sin(phi) * math.cos(theta)
        y = math.sin(phi) * math.sin(theta)
        z = math.cos(phi)
        return (center[0] + x * radius, center[1] + y * radius, center[2] + z * radius)

    def find_path(self, start, goal) -> List[Tuple[float, float, float]]:
        # Very small stub: return straight-line waypoint list
        return [start, goal]


# Module-level instance convenience
_nav = None

def get_nav_graph():
    global _nav
    if _nav is None:
        _nav = NavGraph()
    return _nav
