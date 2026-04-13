"""
Scene Editor — OpenGL-powered 2D/3D viewport for NodeCanvas.

Features:
- Mode selector: Pure | UI | 2D | 3D
- OpenGL grid rendering (2D orthographic / 3D perspective)
- UE5-style camera navigation (fly cam, orbit, pan, zoom)
- Transform gizmos (Move / Rotate / Scale)
- Scene explorer panel with primitives, project assets, outliner, and properties
- Drag-and-drop object creation
- Object selection and screen-proportional movement
- Inline UI Builder for UI mode
- Dark theme matching the Logic editor
"""

import math
import time
import os
import uuid
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QComboBox, QCheckBox, QDoubleSpinBox, QFrame, QSizePolicy, QSpinBox,
    QToolButton, QButtonGroup, QSpacerItem, QSplitter, QTabBar,
    QTreeWidget, QTreeWidgetItem, QListWidget, QListWidgetItem,
    QStackedWidget, QAbstractItemView, QMenu, QInputDialog,
    QScrollArea, QGridLayout, QGroupBox, QSlider, QColorDialog,
    QFormLayout, QMainWindow, QFileDialog, QDialog, QMessageBox, QLayout,
)
from PyQt6.QtGui import (
    QColor, QPainter, QFont, QSurfaceFormat, QMouseEvent,
    QWheelEvent, QKeyEvent, QDropEvent, QDragEnterEvent, QPen, QBrush, QCursor, QDrag,
    QIcon, QPixmap, QShortcut, QKeySequence
)
from PyQt6.QtCore import (
    Qt, QTimer, QSize, QPointF, pyqtSignal, QElapsedTimer,
    QMimeData, QPoint,
)
import json as _json

try:
    from PyQt6.QtOpenGLWidgets import QOpenGLWidget
except ImportError:
    QOpenGLWidget = None

try:
    from OpenGL.GL import *
    from OpenGL.GLU import *
    HAS_OPENGL = True
except ImportError:
    HAS_OPENGL = False
    
from .procedural_ocean import render_ocean_gpu, init_ocean_gpu


# ---------------------------------------------------------------------------
# Colour constants matching the Logic editor dark theme
# ---------------------------------------------------------------------------
BG_COLOR           = (0.102, 0.102, 0.102, 1.0)   # #1a1a1a
GRID_MINOR_COLOR   = (0.165, 0.165, 0.165, 0.5)   # #2a2a2a
GRID_MAJOR_COLOR   = (0.227, 0.227, 0.227, 0.7)   # #3a3a3a
AXIS_X_COLOR       = (0.878, 0.333, 0.333, 1.0)   # red
AXIS_Y_COLOR       = (0.333, 0.878, 0.333, 1.0)   # green
AXIS_Z_COLOR       = (0.333, 0.333, 0.878, 1.0)   # blue
ORIGIN_COLOR       = (1.0,   1.0,   1.0,   0.4)   # white dot
SELECT_COLOR       = (0.310, 0.765, 0.969, 1.0)    # #4fc3f7
OBJECT_COLOR       = (0.7,   0.7,   0.7,   0.8)    # default wireframe
OBJECT_FACE_COLOR  = (0.25,  0.25,  0.28,  0.4)    # subtle fill
GIZMO_ALPHA        = 0.9

# PBR Material Presets
MATERIAL_PRESETS = {
    'Plastic':    {'base_color': [0.8, 0.8, 0.8, 1.0], 'roughness': 0.7, 'metallic': 0.0, 'emissive_color': [0.0, 0.0, 0.0, 1.0]},
    'Glass':      {'base_color': [0.9, 0.95, 1.0, 0.4], 'roughness': 0.1, 'metallic': 0.0, 'emissive_color': [0.0, 0.0, 0.0, 1.0]},
    'Metal':      {'base_color': [0.8, 0.8, 0.85, 1.0], 'roughness': 0.3, 'metallic': 1.0, 'emissive_color': [0.0, 0.0, 0.0, 1.0]},
    'Water':      {'base_color': [0.0, 0.3, 0.6, 0.6], 'roughness': 0.05, 'metallic': 0.1, 'emissive_color': [0.0, 0.0, 0.0, 1.0]},
    'Green Glow': {'base_color': [0.1, 0.8, 0.2, 1.0], 'roughness': 0.5, 'metallic': 0.0, 'emissive_color': [0.1, 0.8, 0.2, 1.0]},
}
DEFAULT_MATERIAL = dict(MATERIAL_PRESETS['Plastic'])
DEFAULT_MATERIAL['preset'] = 'Plastic'

# Stylesheet fragments
TOOLBAR_SS = """
    QWidget#SceneToolbar {
        background: #2a2a2a;
        border-bottom: 1px solid #444;
    }
"""
BTN_SS = """
    QPushButton, QToolButton {
        background: #3a3a3a; border: 1px solid #555; border-radius: 4px;
        color: #e0e0e0; padding: 4px 10px; font-size: 11px;
    }
    QPushButton:hover, QToolButton:hover { background: #4a4a4a; }
    QPushButton:checked, QToolButton:checked {
        background: #4fc3f7; color: #1a1a1a; border-color: #4fc3f7;
    }
    QPushButton:disabled, QToolButton:disabled {
        color: #666; background: #2e2e2e; border-color: #444;
    }
"""
COMBO_SS = """
    QComboBox {
        background: #3a3a3a; border: 1px solid #555; border-radius: 4px;
        color: #e0e0e0; padding: 4px 8px; font-size: 11px; min-width: 80px;
    }
    QComboBox:hover { border-color: #4fc3f7; }
    QComboBox::drop-down { border: none; width: 20px; }
    QComboBox::down-arrow { image: none; border: none; }
    QComboBox QAbstractItemView {
        background: #2a2a2a; color: #e0e0e0;
        selection-background-color: #4fc3f7; selection-color: #1a1a1a;
        border: 1px solid #555;
    }
"""
PANEL_SS = """
    QWidget#ExplorerPanel {
        background: #252526;
        border-right: 1px solid #3c3c3c;
    }
"""
SECTION_HEADER_SS = """
    QPushButton {
        background-color: #252526; color: #e0e0e0; border: none;
        text-align: left; padding: 6px 8px; font-weight: bold; font-size: 11px;
    }
    QPushButton:hover { background-color: #2a2d2e; }
"""
LIST_SS = """
    QListWidget {
        background: #1e1e1e; border: none; color: #ccc;
        font-size: 12px; outline: none;
    }
    QListWidget::item { padding: 5px 8px; border: none; }
    QListWidget::item:hover { background: #2a2d2e; }
    QListWidget::item:selected, QListWidget::item:selected:!active { background: #094771; color: #fff; }
"""
TREE_SS = """
    QTreeWidget {
        background: #1e1e1e; border: none; color: #ccc;
        font-size: 12px; outline: none;
    }
    QTreeWidget::item { padding: 3px 4px; }
    QTreeWidget::item:hover { background: #2a2d2e; }
    QTreeWidget::item:selected, QTreeWidget::item:selected:!active { background: #094771; color: #fff; }
    QTreeWidget::branch { background: #1e1e1e; }
"""
PROPS_SS = """
    QGroupBox {
        background: #252526; border: 1px solid #3c3c3c; border-radius: 4px;
        margin-top: 8px; padding-top: 14px; color: #ccc; font-size: 11px;
    }
    QGroupBox::title {
        subcontrol-origin: margin; left: 8px; padding: 0 4px; color: #4fc3f7;
        font-weight: bold;
    }
"""
SPIN_SS = """
    QDoubleSpinBox {
        background: #333; border: 1px solid #555; border-radius: 3px;
        color: #e0e0e0; padding: 2px 4px; font-size: 11px;
    }
    QDoubleSpinBox:hover { border-color: #4fc3f7; }
    QDoubleSpinBox:focus { border-color: #4fc3f7; }
"""
LABEL_SS = "color: #888; font-size: 11px;"


# ===================================================================
# Scene Object
# ===================================================================

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
        self.parent_id = None
        self.children_ids = []
        self.ocean_opacity = 0.6
        if self.obj_type == 'ocean':
            self.material = dict(MATERIAL_PRESETS['Water'])
            self.material['preset'] = 'Water'
        else:
            self.material = dict(DEFAULT_MATERIAL)
        self.active = True
        self.visible = (obj_type not in ('camera', 'light_point', 'light_directional'))
        self.intensity = 1.0
        self.is_procedural = False # Flag for objects spawned by procedural systems
        self.range = 10.0  # For lights
        self.fov = 60.0    # For cameras
        # Landscape-specific properties (used when obj_type == 'landscape')
        self.landscape_type = 'procedural'         # 'flat' | 'procedural'
        self.landscape_size_mode = 'finite'     # 'finite' | 'infinite'
        self.landscape_chunk_size = 128         # 64 | 128 | 256
        self.landscape_grid_radius = 1         # 1=3x3, 2=5x5, etc.
        self.landscape_resolution = 32          # 16 | 32 | 64 | 128
        self.landscape_render_bias = -0.02
        self.landscape_seed = 123
        self.landscape_height_scale = 30.0
        self.landscape_ocean_level = 0.08
        self.landscape_ocean_flattening = 0.3
        self.landscape_tip_smoothing = 0.1
        self.landscape_noise_layers = [
            # Layer 1: Base Terrain (LFM) - Dominate Round Hills
            {'type': 'perlin', 'mode': 'fbm', 'amp': 1.0, 'freq': 0.007, 'octaves': 4, 'persistence': 0.45, 'lacunarity': 2.0, 'weight': 1.2, 'exponent': 1.0},
            # Layer 2: Mountain Peaks (Ridged) - Sparse Sharp Accents
            {'type': 'perlin', 'mode': 'ridged', 'amp': 0.65, 'freq': 0.012, 'octaves': 3, 'persistence': 0.5, 'lacunarity': 2.1, 'weight': 0.4, 'exponent': 2.5},
            # Layer 3: Detail Noise - Fine Variations
            {'type': 'perlin', 'mode': 'fbm', 'amp': 0.15, 'freq': 0.04, 'octaves': 3, 'persistence': 0.5, 'lacunarity': 2.0, 'weight': 0.15, 'exponent': 1.0}
        ]
        self.landscape_biomes = [
            {
                'name': 'Deep Ocean',
                'height_range': [-1000.0, -5.0], 'slope_range': [0.0, 1.0], 'temp_range': [0.0, 1.0], 'hum_range': [0.0, 1.0],
                'surface': {'color': [0.05, 0.1, 0.3, 1.0], 'roughness': 0.1, 'metallic': 0.2}, 'spawns': []
            },
            {
                'name': 'Shallow Water',
                'height_range': [-5.0, 0.0], 'slope_range': [0.0, 1.0], 'temp_range': [0.0, 1.0], 'hum_range': [0.0, 1.0],
                'surface': {'color': [0.1, 0.4, 0.6, 1.0], 'roughness': 0.2, 'metallic': 0.1}, 'spawns': []
            },
            {
                'name': 'Beach',
                'height_range': [0.0, 2.0], 'slope_range': [0.0, 0.2], 'temp_range': [0.4, 1.0], 'hum_range': [0.0, 1.0],
                'surface': {'color': [0.85, 0.8, 0.65, 1.0], 'roughness': 0.9, 'metallic': 0.0}, 'spawns': []
            },
            {
                'name': 'Grassland',
                'height_range': [2.0, 15.0], 'slope_range': [0.0, 0.15], 'temp_range': [0.3, 0.8], 'hum_range': [0.2, 0.7],
                'surface': {'color': [0.25, 0.4, 0.1, 1.0], 'roughness': 0.8, 'metallic': 0.0}, 'spawns': []
            },
            {
                'name': 'Forest',
                'height_range': [15.0, 35.0], 'slope_range': [0.15, 0.4], 'temp_range': [0.3, 0.7], 'hum_range': [0.5, 1.0],
                'surface': {'color': [0.1, 0.25, 0.05, 1.0], 'roughness': 0.9, 'metallic': 0.0}, 'spawns': []
            },
            {
                'name': 'Mountain',
                'height_range': [35.0, 1000.0], 'slope_range': [0.4, 1.0], 'temp_range': [0.0, 1.0], 'hum_range': [0.0, 1.0],
                'surface': {'color': [0.4, 0.4, 0.45, 1.0], 'roughness': 0.7, 'metallic': 0.0}, 'spawns': []
            },
            {
                'name': 'Snow Cap',
                'height_range': [45.0, 1000.0], 'slope_range': [0.0, 1.0], 'temp_range': [0.0, 0.2], 'hum_range': [0.0, 1.0],
                'surface': {'color': [0.95, 0.95, 1.0, 1.0], 'roughness': 0.3, 'metallic': 0.0}, 'spawns': []
            }
        ]
        self.landscape_spawn_enabled = False
        self.landscape_spawn_list = []          # Legacy list
        self.landscape_spawn_rows = 1
        self.landscape_spawn_cols = 1
        self.landscape_spawn_spacing = [10.0, 10.0] 
        self.visualize_climate = False
        # Ocean-specific properties (GPU Shader driven)
        self.ocean_wave_speed = 5.0
        self.ocean_wave_scale = 1.0
        self.ocean_wave_steepness = 0.15
        self.ocean_foam_amount = 0.1
        self.ocean_fft_resolution = 128
        self.ocean_wave_choppiness = 1.5
        self.ocean_wave_intensity = 1.0
        self.ocean_use_fft = True
        self.opacity = 0.8

    def get_render_color(self):
        """Get the effective face color from the material base_color."""
        bc = self.material.get('base_color', [0.7, 0.7, 0.7, 1.0])
        return tuple(bc)

    def get_emissive_color(self):
        ec = self.material.get('emissive_color', [0.0, 0.0, 0.0, 1.0])
        return tuple(ec)

    def to_dict(self) -> dict:
        return {
            'id': self.id, 'name': self.name, 'type': self.obj_type,
            'position': self.position, 'rotation': self.rotation, 'scale': self.scale,
            'color': self.color, 'file_path': self.file_path,
            'parent_id': self.parent_id, 'children_ids': self.children_ids.copy(),
            'material': dict(self.material),
            'active': self.active,
            'visible': self.visible,
            'intensity': self.intensity,
            'range': self.range,
            'fov': self.fov,
            # Landscape data
            'landscape_type': self.landscape_type,
            'landscape_size_mode': self.landscape_size_mode,
            'landscape_render_bias': self.landscape_render_bias,
            'landscape_seed': self.landscape_seed,
            'landscape_height_scale': self.landscape_height_scale,
            'landscape_ocean_level': self.landscape_ocean_level,
            'landscape_ocean_flattening': self.landscape_ocean_flattening,
            'landscape_tip_smoothing': self.landscape_tip_smoothing,
            'landscape_noise_layers': [dict(lyr) for lyr in self.landscape_noise_layers],
            'landscape_biomes': [dict(b) for b in self.landscape_biomes],
            'landscape_chunk_size': self.landscape_chunk_size,
            'landscape_grid_radius': self.landscape_grid_radius,
            'landscape_resolution': self.landscape_resolution,
            'landscape_spawn_enabled': self.landscape_spawn_enabled,
            'landscape_spawn_rows': self.landscape_spawn_rows,
            'landscape_spawn_cols': self.landscape_spawn_cols,
            'landscape_spawn_spacing': self.landscape_spawn_spacing,
            'visualize_climate': self.visualize_climate,
            'active': self.active,
            'is_procedural': self.is_procedural,
            'ocean_wave_speed': self.ocean_wave_speed,
            'ocean_wave_scale': self.ocean_wave_scale,
            'ocean_wave_steepness': self.ocean_wave_steepness,
            'ocean_foam_amount': self.ocean_foam_amount,
            'ocean_fft_resolution': self.ocean_fft_resolution,
            'ocean_wave_choppiness': self.ocean_wave_choppiness,
            'ocean_wave_intensity': self.ocean_wave_intensity,
            'ocean_use_fft': self.ocean_use_fft,
        }

    @staticmethod
    def from_dict(d: dict) -> 'SceneObject':
        obj = SceneObject(d['name'], d['type'], d.get('position'), d.get('rotation'), d.get('scale'))
        obj.id = d.get('id', obj.id)
        obj.color = d.get('color', obj.color)
        obj.file_path = d.get('file_path')
        obj.parent_id = d.get('parent_id')
        obj.children_ids = d.get('children_ids', [])
        obj.material = d.get('material', dict(DEFAULT_MATERIAL))
        obj.active = d.get('active', True)
        obj.intensity = d.get('intensity', 1.0)
        obj.range = d.get('range', 10.0)
        obj.fov = d.get('fov', 60.0)
        obj.is_procedural = d.get('is_procedural', False)
        # Landscape settings
        obj.landscape_type = d.get('landscape_type', 'flat')
        obj.landscape_size_mode = d.get('landscape_size_mode', 'finite')
        obj.landscape_render_bias = d.get('landscape_render_bias', -0.02)
        obj.landscape_seed = d.get('landscape_seed', 123)
        obj.landscape_height_scale = d.get('landscape_height_scale', 30.0)
        obj.landscape_ocean_level = d.get('landscape_ocean_level', 0.08)
        obj.landscape_ocean_flattening = d.get('landscape_ocean_flattening', 0.3)
        obj.landscape_tip_smoothing = d.get('landscape_tip_smoothing', 0.1)
        obj.landscape_chunk_size = d.get('landscape_chunk_size', 128.0)
        obj.landscape_grid_radius = d.get('landscape_grid_radius', 1)
        obj.landscape_resolution = d.get('landscape_resolution', 32)
        
        # Migration for Noise Layers
        if 'landscape_noise_layers' in d:
            obj.landscape_noise_layers = d['landscape_noise_layers']
        else:
            amp = d.get('landscape_procedural_amp', 0.5)
            freq = d.get('landscape_procedural_freq', 1.0)
            obj.landscape_noise_layers = [{'amp': amp, 'freq': freq, 'offset': [0.0, 0.0], 'octaves': 4}]
        
        # Migration for Biomes (Encapsulated)
        if 'landscape_biomes' in d:
            biomes = d['landscape_biomes']
            for b in biomes:
                if 'surface' not in b:
                    # Upgrade structure
                    b['surface'] = {
                        'color': b.get('color', [0.5, 0.5, 0.5, 1.0]),
                        'roughness': 0.7, 'metallic': 0.0,
                        'emissive': [0.0, 0.0, 0.0, 1.0]
                    }
                if 'slope_range' not in b:
                    b['slope_range'] = [0.0, 1.0]
            obj.landscape_biomes = biomes
        else:
            obj.landscape_biomes = [{
                'name': 'Default', 'height_range': [-1000.0, 1000.0], 'slope_range': [0.0, 1.0],
                'surface': {'color': [0.5, 0.5, 0.5, 1.0], 'roughness': 0.7, 'metallic': 0.0, 'emissive': [0.0, 0.0, 0.0, 1.0]},
                'spawns': []
            }]
        
        # Apply strict requirements for default landscape setup if empty or generic
        if not d.get('landscape_biomes') or len(obj.landscape_biomes) == 1 and obj.landscape_biomes[0]['name'] == 'Default':
            obj.landscape_biomes = [
                {'name': 'Deep Ocean', 'height_range': [-1000.0, -5.0],  'slope_range': [0, 1], 'surface': {'color': [0.05, 0.1, 0.4, 1.0], 'roughness': 0.1, 'metallic': 0.0}, 'spawns': []},
                {'name': 'Ocean',      'height_range': [-5.0, -1.0],   'slope_range': [0, 1], 'surface': {'color': [0.1, 0.2, 0.6, 1.0], 'roughness': 0.1, 'metallic': 0.0},  'spawns': []},
                {'name': 'Beach',      'height_range': [-1.0, 0.5],    'slope_range': [0, 0.2], 'surface': {'color': [0.8, 0.7, 0.4, 1.0], 'roughness': 0.9, 'metallic': 0.0}, 'spawns': []},
                {'name': 'Grassland',  'height_range': [0.5, 5.0],     'slope_range': [0, 0.3], 'surface': {'color': [0.2, 0.5, 0.1, 1.0], 'roughness': 0.8, 'metallic': 0.0}, 'spawns': []},
                {'name': 'Forest',     'height_range': [5.0, 15.0],    'slope_range': [0, 0.5], 'surface': {'color': [0.1, 0.3, 0.1, 1.0], 'roughness': 0.8, 'metallic': 0.0}, 'spawns': []},
                {'name': 'Mountain',   'height_range': [15.0, 25.0],   'slope_range': [0, 1.0], 'surface': {'color': [0.4, 0.3, 0.2, 1.0], 'roughness': 0.6, 'metallic': 0.0}, 'spawns': []},
                {'name': 'Snow',       'height_range': [25.0, 5000.0], 'slope_range': [0, 1.0], 'surface': {'color': [0.95, 0.95, 1.0, 1.0], 'roughness': 0.9, 'metallic': 0.0}, 'spawns': []},
            ]
        
        if not d.get('landscape_noise_layers'):
            obj.landscape_noise_layers = [
                {'type': 'perlin', 'amp': 1.0, 'freq': 1.0, 'octaves': 6, 'persistence': 0.5, 'lacunarity': 2.0},
                {'type': 'worley', 'amp': 0.2, 'freq': 4.0, 'octaves': 1}
            ]

        obj.landscape_spawn_enabled = d.get('landscape_spawn_enabled', False)

        obj.landscape_spawn_rows = d.get('landscape_spawn_rows', 1)
        obj.landscape_spawn_cols = d.get('landscape_spawn_cols', 1)
        obj.landscape_spawn_spacing = d.get('landscape_spawn_spacing', [10.0, 10.0])
        obj.visualize_climate = d.get('visualize_climate', False)
        # Ocean properties
        obj.ocean_wave_speed = d.get('ocean_wave_speed', 5.0)
        obj.ocean_wave_scale = d.get('ocean_wave_scale', 1.0)
        obj.ocean_wave_steepness = d.get('ocean_wave_steepness', 0.15)
        obj.ocean_foam_amount = d.get('ocean_foam_amount', 0.1)
        obj.ocean_fft_resolution = d.get('ocean_fft_resolution', 128)
        obj.ocean_wave_choppiness = d.get('ocean_wave_choppiness', 1.5)
        obj.ocean_wave_intensity = d.get('ocean_wave_intensity', 1.0)
        obj.ocean_use_fft = d.get('ocean_use_fft', True)
        return obj


# ===================================================================
# Camera helpers (pure math, no numpy dependency)
# ===================================================================

def _cross(a, b):
    return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])

def _normalize(v):
    ln = math.sqrt(v[0]*v[0]+v[1]*v[1]+v[2]*v[2])
    return (v[0]/ln, v[1]/ln, v[2]/ln) if ln > 1e-9 else (0,0,0)

def _normalize_2d(v):
    ln = math.sqrt(v[0]*v[0]+v[1]*v[1])
    return (v[0]/ln, v[1]/ln) if ln > 1e-9 else (0,0)

def _dot(a, b):
    return a[0]*b[0]+a[1]*b[1]+a[2]*b[2]

def _sub(a, b):
    return (a[0]-b[0], a[1]-b[1], a[2]-b[2])

def _add(a, b):
    return (a[0]+b[0], a[1]+b[1], a[2]+b[2])

def _scale_vec(v, s):
    return (v[0]*s, v[1]*s, v[2]*s)

def _length(v):
    return math.sqrt(v[0]*v[0]+v[1]*v[1]+v[2]*v[2])

def _dist_line_line(p1, d1, p2, d2):
    """Distance between two infinite lines. Returns (distance, t_on_line1, t_on_line2)."""
    w0 = _sub(p1, p2)
    a, b, c, d, e = _dot(d1,d1), _dot(d1,d2), _dot(d2,d2), _dot(d1,w0), _dot(d2,w0)
    denom = a*c - b*b
    if abs(denom) < 1e-9:
        return _length(_cross(d1, w0)) / (math.sqrt(a) if a > 0 else 1.0), 0, 0
    tc = (a*e - b*d) / denom
    sc = (b*tc - d) / a
    return _length(_sub(_add(p1, _scale_vec(d1, sc)), _add(p2, _scale_vec(d2, tc)))), sc, tc

def _ray_intersect_sphere(origin, direction, center, radius):
    L = _sub(center, origin)
    tca = _dot(L, direction)
    if tca < 0: return None
    d2 = _dot(L, L) - tca*tca
    r2 = radius*radius
    if d2 > r2: return None
    thc = math.sqrt(r2 - d2)
    return tca - thc

def _ray_intersect_aabb(origin, direction, amin, amax):
    tmin = -1e30; tmax = 1e30
    for i in range(3):
        if abs(direction[i]) < 1e-9:
            if origin[i] < amin[i] or origin[i] > amax[i]: return None
        else:
            inv_d = 1.0 / direction[i]
            t1 = (amin[i] - origin[i]) * inv_d
            t2 = (amax[i] - origin[i]) * inv_d
            if t1 > t2: t1, t2 = t2, t1
            tmin = max(tmin, t1); tmax = min(tmax, t2)
    if tmax < tmin or tmax < 0: return None
    return tmin

def _dist_point_ray(p, origin, direction):
    v = _sub(p, origin)
    t = _dot(v, direction)
    if t <= 0: return _length(v)
    proj_p = _add(origin, _scale_vec(direction, t))
    return _length(_sub(p, proj_p))

def _rotate_point_around_pivot(p, pivot, rot_mat):
    # p_local = p - pivot
    v = _sub(p, pivot)
    # v_rot = rot_mat * v
    v_rot = _mat_vec_mul(rot_mat, v)
    # p_rot = pivot + v_rot
    return _add(pivot, v_rot)

def _euler_to_matrix(ex, ey, ez):
    # Order: Y (Yaw) * X (Pitch) * Z (Roll) - Standard World-Space behavior
    rx, ry, rz = math.radians(ex), math.radians(ey), math.radians(ez)
    cx, sx = math.cos(rx), math.sin(rx)
    cy, sy = math.cos(ry), math.sin(ry)
    cz, sz = math.cos(rz), math.sin(rz)
    # Rotation Matrices
    Mx = [[1, 0, 0], [0, cx, -sx], [0, sx, cx]]
    My = [[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]]
    Mz = [[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]]
    # Product: R = My * Mx * Mz
    def __mul(A, B):
        C = [[0]*3 for _ in range(3)]
        for i in range(3):
            for j in range(3):
                for k in range(3): C[i][j] += A[i][k] * B[k][j]
        return C
    return __mul(My, __mul(Mx, Mz))

def _mat_vec_mul(M, v):
    return (
        M[0][0]*v[0] + M[0][1]*v[1] + M[0][2]*v[2],
        M[1][0]*v[0] + M[1][1]*v[1] + M[1][2]*v[2],
        M[2][0]*v[0] + M[2][1]*v[1] + M[2][2]*v[2]
    )

def _matrix_to_euler(M):
    # Recover YXZ-order Euler angles
    # M[1][2] = -sx -> sx = -M[1][2]
    try:
        rx = math.asin(-max(-1.0, min(1.0, M[1][2])))
        if abs(math.cos(rx)) > 1e-4:
            ry = math.atan2(M[0][2], M[2][2])
            rz = math.atan2(M[1][0], M[1][1])
        else:
            ry = math.atan2(-M[2][0], M[0][0])
            rz = 0.0
        return [math.degrees(rx), math.degrees(ry), math.degrees(rz)]
    except: return [0.0, 0.0, 0.0]

def _axis_angle_to_matrix(axis_vec, angle_deg):
    r = math.radians(angle_deg)
    c, s = math.cos(r), math.sin(r); t = 1-c
    x, y, z = _normalize(axis_vec)
    return [
        [t*x*x + c,   t*x*y - s*z, t*x*z + s*y],
        [t*x*y + s*z, t*y*y + c,   t*y*z - s*x],
        [t*x*z - s*y, t*y*z + s*x, t*z*z + c]
    ]

def _mat_mul_3x3(A, B):
    C = [[0]*3 for _ in range(3)]
    for i in range(3):
        for j in range(3):
            for k in range(3): C[i][j] += A[i][k] * B[k][j]
    return C


class Camera3D:
    """First-person / orbit camera with UE5-style controls."""
    def __init__(self):
        self.pos = [0.0, 5.0, 10.0]
        self.yaw = -90.0
        self.pitch = -25.0
        self.fov = 60.0
        self.near = 0.1
        self.far = 5000.0
        self.speed = 10.0
        self.sensitivity = 0.15

    @property
    def front(self):
        yr, pr = math.radians(self.yaw), math.radians(self.pitch)
        return _normalize((math.cos(yr)*math.cos(pr), math.sin(pr), math.sin(yr)*math.cos(pr)))

    @property
    def right(self):
        return _normalize(_cross(self.front, (0,1,0)))

    @property
    def up(self):
        return _normalize(_cross(self.right, self.front))

    def apply_gl(self, aspect):
        glMatrixMode(GL_PROJECTION); glLoadIdentity()
        gluPerspective(self.fov, aspect, self.near, self.far)
        glMatrixMode(GL_MODELVIEW); glLoadIdentity()
        f = self.front
        t = (self.pos[0]+f[0], self.pos[1]+f[1], self.pos[2]+f[2])
        u = self.up
        gluLookAt(self.pos[0],self.pos[1],self.pos[2], t[0],t[1],t[2], u[0],u[1],u[2])

    def move(self, forward, right, up, dt):
        f, r = self.front, self.right
        s = self.speed * dt
        self.pos[0] += (f[0]*forward+r[0]*right)*s
        self.pos[1] += up*s
        self.pos[2] += (f[2]*forward+r[2]*right)*s

    def rotate(self, dx, dy):
        self.yaw += dx*self.sensitivity
        self.pitch = max(-89.0, min(89.0, self.pitch - dy*self.sensitivity))

    def screen_to_ray(self, mx, my, vp_w, vp_h):
        """Get ray origin and direction from screen coordinates."""
        aspect = vp_w / max(vp_h, 1)
        fov_rad = math.radians(self.fov)
        half_h = math.tan(fov_rad / 2.0)
        half_w = half_h * aspect
        nx = (2.0 * mx / vp_w - 1.0) * half_w
        ny = (1.0 - 2.0 * my / vp_h) * half_h
        f, r, u = self.front, self.right, self.up
        direction = _normalize(_add(_add(_scale_vec(f, 1.0), _scale_vec(r, nx)), _scale_vec(u, ny)))
        return tuple(self.pos), direction

    def _get_view_proj_matrix(self, aspect):
        # Build simple projection and view matrices for world_to_screen
        # P = gluPerspective, V = gluLookAt
        f = self.front; r = self.right; u = self.up
        # View matrix (V)
        V = [
            [r[0], r[1], r[2], -_dot(r, self.pos)],
            [u[0], u[1], u[2], -_dot(u, self.pos)],
            [-f[0], -f[1], -f[2], _dot(f, self.pos)],
            [0, 0, 0, 1]
        ]
        # Proj matrix (P)
        fov_rad = math.radians(self.fov)
        h = 1.0 / math.tan(fov_rad / 2.0)
        w = h / aspect
        far, near = self.far, self.near
        P = [
            [w, 0, 0, 0],
            [0, h, 0, 0],
            [0, 0, -(far+near)/(far-near), -(2*far*near)/(far-near)],
            [0, 0, -1, 0]
        ]
        # Multiply P * V
        PV = [[0]*4 for _ in range(4)]
        for i in range(4):
            for j in range(4):
                for k in range(4):
                    PV[i][j] += P[i][k] * V[k][j]
        return PV

    def world_to_screen(self, world_pos, vp_w, vp_h):
        """Project world coordinates to screen space. Returns (x, y) or None."""
        aspect = vp_w / max(vp_h, 1)
        PV = self._get_view_proj_matrix(aspect)
        # Transform pos
        v = (world_pos[0], world_pos[1], world_pos[2], 1.0)
        out = [0.0]*4
        for i in range(4):
            for j in range(4):
                out[i] += PV[i][j] * v[j]
        if out[3] <= 0: return None # behind camera
        # NDC
        nx = out[0] / out[3]
        ny = out[1] / out[3]
        # Screen
        sx = (nx + 1.0) * 0.5 * vp_w
        sy = (1.0 - ny) * 0.5 * vp_h
        return (sx, sy)

    def ray_plane_intersect(self, mx, my, vp_w, vp_h, plane_point, plane_normal):
        """Intersect a screen ray with a world plane. Returns world point or None."""
        origin, direction = self.screen_to_ray(mx, my, vp_w, vp_h)
        denom = _dot(direction, plane_normal)
        if abs(denom) < 1e-9:
            return None
        diff = _sub(plane_point, origin)
        t = _dot(diff, plane_normal) / denom
        if t < 0:
            return None
        return _add(origin, _scale_vec(direction, t))


class Camera2D:
    """Ortho camera for 2D mode."""
    def __init__(self):
        self.x = 0.0
        self.y = 0.0
        self.zoom_level = 10.0

    def apply_gl(self, width, height):
        aspect = width / max(height, 1)
        hw, hh = self.zoom_level * aspect, self.zoom_level
        glMatrixMode(GL_PROJECTION); glLoadIdentity()
        glOrtho(self.x-hw, self.x+hw, self.y-hh, self.y+hh, -1.0, 1.0)
        glMatrixMode(GL_MODELVIEW); glLoadIdentity()

    def pan(self, dx, dy, width, height):
        aspect = width / max(height, 1)
        hw, hh = self.zoom_level * aspect, self.zoom_level
        self.x -= dx / max(width,1) * hw * 2
        self.y += dy / max(height,1) * hh * 2

    def zoom_by(self, delta):
        self.zoom_level *= (1.1 if delta < 0 else 0.9)
        self.zoom_level = max(0.5, min(10000, self.zoom_level))

    def screen_to_world(self, mx, my, width, height):
        aspect = width / max(height, 1)
        hw, hh = self.zoom_level * aspect, self.zoom_level
        wx = self.x + (2.0 * mx / width - 1.0) * hw
        wy = self.y + (1.0 - 2.0 * my / height) * hh
        return wx, wy

    def world_to_screen(self, pos, width, height):
        wx, wy = pos[0], pos[1]
        aspect = width / max(height, 1)
        hw, hh = self.zoom_level * aspect, self.zoom_level
        mx = ((wx - self.x) / hw + 1.0) / 2.0 * width
        my = (1.0 - (wy - self.y) / hh) / 2.0 * height
        return (mx, my)


# ===================================================================
# Wireframe primitive drawing helpers (legacy GL)
# ===================================================================

def _draw_wireframe_cube(sx=1, sy=1, sz=1, color=OBJECT_COLOR, fill_color=OBJECT_FACE_COLOR):
    hx, hy, hz = sx/2, sy/2, sz/2
    verts = [
        (-hx,-hy,-hz),(hx,-hy,-hz),(hx,hy,-hz),(-hx,hy,-hz),
        (-hx,-hy,hz),(hx,-hy,hz),(hx,hy,hz),(-hx,hy,hz),
    ]
    faces = [(0,1,2,3),(4,5,6,7),(0,1,5,4),(2,3,7,6),(0,3,7,4),(1,2,6,5)]
    normals = [(0,0,-1),(0,0,1),(0,-1,0),(0,1,0),(-1,0,0),(1,0,0)]
    edges = [(0,1),(1,2),(2,3),(3,0),(4,5),(5,6),(6,7),(7,4),(0,4),(1,5),(2,6),(3,7)]
    # If fill is translucent, enable blending and disable depth writes
    alpha = fill_color[3] if len(fill_color) > 3 else 1.0
    if alpha < 0.999:
        glEnable(GL_BLEND); glDepthMask(GL_FALSE)
    else:
        glDisable(GL_BLEND); glDepthMask(GL_TRUE)
    glColor4f(*fill_color)
    for i_f, f in enumerate(faces):
        glBegin(GL_QUADS)
        glNormal3f(*normals[i_f])
        for i in f: glVertex3f(*verts[i])
        glEnd()
    # Restore depth writing for outlines
    glDepthMask(GL_TRUE); glDisable(GL_BLEND)
    glDisable(GL_LIGHTING)
    glColor4f(*color); glLineWidth(1.5)
    glBegin(GL_LINES)
    for a, b in edges: glVertex3f(*verts[a]); glVertex3f(*verts[b])
    glEnd(); glLineWidth(1.0); glEnable(GL_LIGHTING)


def _draw_wireframe_sphere(radius=0.5, rings=12, segments=16, color=OBJECT_COLOR, fill_color=OBJECT_FACE_COLOR):
    # Fill
    alpha = fill_color[3] if len(fill_color) > 3 else 1.0
    if alpha < 0.999:
        glEnable(GL_BLEND); glDepthMask(GL_FALSE)
    else:
        glDisable(GL_BLEND); glDepthMask(GL_TRUE)
    glColor4f(*fill_color)
    for i in range(rings):
        phi1 = math.pi * i / rings
        phi2 = math.pi * (i + 1) / rings
        y1, r1 = radius * math.cos(phi1), radius * math.sin(phi1)
        y2, r2 = radius * math.cos(phi2), radius * math.sin(phi2)
        glBegin(GL_QUAD_STRIP)
        for j in range(segments + 1):
            theta = 2.0 * math.pi * j / segments
            cx, cz = math.cos(theta), math.sin(theta)
            glNormal3f(r1/radius * cx, y1/radius, r1/radius * cz)
            glVertex3f(r1 * cx, y1, r1 * cz)
            glNormal3f(r2/radius * cx, y2/radius, r2/radius * cz)
            glVertex3f(r2 * cx, y2, r2 * cz)
        glEnd()
    glDepthMask(GL_TRUE); glDisable(GL_BLEND)
    # Outline (disable lighting for wireframe)
    glDisable(GL_LIGHTING)
    glColor4f(*color); glLineWidth(1.5)
    for i in range(rings + 1):
        phi = math.pi * i / rings
        y = radius * math.cos(phi); r = radius * math.sin(phi)
        glBegin(GL_LINE_LOOP)
        for j in range(segments):
            theta = 2.0 * math.pi * j / segments
            glVertex3f(r * math.cos(theta), y, r * math.sin(theta))
        glEnd()
    glLineWidth(1.0); glEnable(GL_LIGHTING)


def _draw_wireframe_cylinder(radius=0.5, height=1.0, segments=16, color=OBJECT_COLOR, fill_color=OBJECT_FACE_COLOR):
    hh = height / 2
    # Fill faces
    alpha = fill_color[3] if len(fill_color) > 3 else 1.0
    if alpha < 0.999:
        glEnable(GL_BLEND); glDepthMask(GL_FALSE)
    else:
        glDisable(GL_BLEND); glDepthMask(GL_TRUE)
    glColor4f(*fill_color)
    # Side
    glBegin(GL_QUAD_STRIP)
    for i in range(segments + 1):
        a = 2.0 * math.pi * i / segments
        cx, cz = math.cos(a), math.sin(a)
        glNormal3f(cx, 0, cz)
        glVertex3f(radius * cx, hh, radius * cz)
        glVertex3f(radius * cx, -hh, radius * cz)
    glEnd()
    # Caps
    for y in [hh, -hh]:
        glBegin(GL_TRIANGLE_FAN)
        glNormal3f(0, 1 if y > 0 else -1, 0)
        glVertex3f(0, y, 0)
        for i in range(segments + 1):
            a = 2.0 * math.pi * (i if y > 0 else -i) / segments
            glVertex3f(radius * math.cos(a), y, radius * math.sin(a))
        glEnd()
    # Restore depth write and blending for outlines
    glDepthMask(GL_TRUE); glDisable(GL_BLEND)
    # Outline
    glDisable(GL_LIGHTING)
    glColor4f(*color); glLineWidth(1.5)
    glBegin(GL_LINE_LOOP)
    for i in range(segments):
        a = 2.0 * math.pi * i / segments
        glVertex3f(radius * math.cos(a), hh, radius * math.sin(a))
    glEnd()
    glBegin(GL_LINE_LOOP)
    for i in range(segments):
        a = 2.0 * math.pi * i / segments
        glVertex3f(radius * math.cos(a), -hh, radius * math.sin(a))
    glEnd()
    glBegin(GL_LINES)
    for i in range(0, segments, max(1, segments // 8)):
        a = 2.0 * math.pi * i / segments
        x, z = radius * math.cos(a), radius * math.sin(a)
        glVertex3f(x, hh, z); glVertex3f(x, -hh, z)
    glEnd(); glLineWidth(1.0); glEnable(GL_LIGHTING)


def _draw_wireframe_plane(sx=2, sz=2, color=OBJECT_COLOR, fill_color=OBJECT_FACE_COLOR, flip_winding: bool = False, y_offset: float = 0.0):
    hx, hz = sx/2, sz/2
    alpha = fill_color[3] if len(fill_color) > 3 else 1.0
    if alpha < 0.999:
        glEnable(GL_BLEND); glDepthMask(GL_FALSE)
    else:
        glDisable(GL_BLEND); glDepthMask(GL_TRUE)
    glColor4f(*fill_color)
    glBegin(GL_QUADS)
    glNormal3f(0, 1, 0)
    if flip_winding:
        # Emit vertices in reversed winding so the opposite face is considered front
        glVertex3f(-hx, y_offset, -hz); glVertex3f(-hx, y_offset, hz); glVertex3f(hx, y_offset, hz); glVertex3f(hx, y_offset, -hz)
    else:
        glVertex3f(-hx, y_offset, -hz); glVertex3f(hx, y_offset, -hz); glVertex3f(hx, y_offset, hz); glVertex3f(-hx, y_offset, hz)
    glEnd()
    glDepthMask(GL_TRUE); glDisable(GL_BLEND)
    glDisable(GL_LIGHTING)
    glColor4f(*color); glLineWidth(1.5)
    glBegin(GL_LINE_LOOP)
    if flip_winding:
        glVertex3f(-hx, y_offset, -hz); glVertex3f(-hx, y_offset, hz); glVertex3f(hx, y_offset, hz); glVertex3f(hx, y_offset, -hz)
    else:
        glVertex3f(-hx, y_offset, -hz); glVertex3f(hx, y_offset, -hz); glVertex3f(hx, y_offset, hz); glVertex3f(-hx, y_offset, hz)
    glEnd(); glLineWidth(1.0); glEnable(GL_LIGHTING)


def _draw_wireframe_cone(radius=0.5, height=1.0, segments=16, color=OBJECT_COLOR, fill_color=OBJECT_FACE_COLOR):
    hh = height / 2
    # Fill
    alpha = fill_color[3] if len(fill_color) > 3 else 1.0
    if alpha < 0.999:
        glEnable(GL_BLEND); glDepthMask(GL_FALSE)
    else:
        glDisable(GL_BLEND); glDepthMask(GL_TRUE)
    glColor4f(*fill_color)
    glBegin(GL_TRIANGLE_FAN)
    glNormal3f(0, 1, 0) # Normal for the slant is more complex, using Up for now
    glVertex3f(0, hh, 0)
    for i in range(segments + 1):
        a = 2.0 * math.pi * i / segments
        cx, cz = math.cos(a), math.sin(a)
        glNormal3f(cx, 0.5, cz) # Rough slant normal
        glVertex3f(radius * cx, -hh, radius * cz)
    glEnd()
    glBegin(GL_TRIANGLE_FAN)
    glNormal3f(0, -1, 0)
    glVertex3f(0, -hh, 0)
    for i in range(segments + 1):
        a = 2.0 * math.pi * (-i) / segments
        glVertex3f(radius * math.cos(a), -hh, radius * math.sin(a))
    glEnd()
    glDepthMask(GL_TRUE); glDisable(GL_BLEND)
    # Outline
    glDisable(GL_LIGHTING)
    glColor4f(*color); glLineWidth(1.5)
    glBegin(GL_LINE_LOOP)
    for i in range(segments):
        a = 2.0 * math.pi * i / segments
        glVertex3f(radius * math.cos(a), -hh, radius * math.sin(a))
    glEnd()
    glBegin(GL_LINES)
    for i in range(0, segments, max(1, segments // 8)):
        a = 2.0 * math.pi * i / segments
        glVertex3f(radius * math.cos(a), -hh, radius * math.sin(a)); glVertex3f(0, hh, 0)
    glEnd(); glLineWidth(1.0); glEnable(GL_LIGHTING)


def _draw_2d_rect(w=1, h=1, color=OBJECT_COLOR, fill_color=OBJECT_FACE_COLOR):
    hw, hh = w/2, h/2
    glColor4f(*fill_color)
    glBegin(GL_QUADS)
    glVertex2f(-hw,-hh); glVertex2f(hw,-hh); glVertex2f(hw,hh); glVertex2f(-hw,hh)
    glEnd()
    glColor4f(*color); glLineWidth(1.5)
    glBegin(GL_LINE_LOOP)
    glVertex2f(-hw,-hh); glVertex2f(hw,-hh); glVertex2f(hw,hh); glVertex2f(-hw,hh)
    glEnd(); glLineWidth(1.0)


def _draw_2d_circle(radius=0.5, segments=32, color=OBJECT_COLOR, fill_color=OBJECT_FACE_COLOR):
    glColor4f(*fill_color)
    glBegin(GL_TRIANGLE_FAN); glVertex2f(0, 0)
    for i in range(segments + 1):
        a = 2.0 * math.pi * i / segments
        glVertex2f(radius * math.cos(a), radius * math.sin(a))
    glEnd()
    glColor4f(*color); glLineWidth(1.5)
    glBegin(GL_LINE_LOOP)
    for i in range(segments):
        a = 2.0 * math.pi * i / segments
        glVertex2f(radius * math.cos(a), radius * math.sin(a))
    glEnd(); glLineWidth(1.0)


def _draw_billboard_bush(color=OBJECT_COLOR, fill_color=(0.2, 0.5, 0.1, 0.6)):
    """Draws a 3-plane 'Triple-X' billboard for high-fidelity 3D volume."""
    for i in range(3):
        angle = i * 60.0
        glPushMatrix()
        glRotatef(angle, 0, 1, 0)
        
        # Fill
        glColor4f(*fill_color)
        glBegin(GL_QUADS)
        glVertex3f(-0.5, 0, 0); glVertex3f(0.5, 0, 0); glVertex3f(0.5, 1.0, 0); glVertex3f(-0.5, 1.0, 0)
        glEnd()
        
        # Outline
        glDisable(GL_LIGHTING)
        glColor4f(*color); glLineWidth(1.0)
        glBegin(GL_LINES)
        glVertex3f(-0.5, 0, 0); glVertex3f(0.5, 1.0, 0); glVertex3f(0.5, 0, 0); glVertex3f(-0.5, 1.0, 0)
        glEnd()
        glEnable(GL_LIGHTING)
        
        glPopMatrix()


def _draw_billboard_tree(color=OBJECT_COLOR, fill_color=(0.15, 0.35, 0.1, 0.8)):
    """Draws a stylized tree with a 3-plane bushy top."""
    # Trunk (thicker)
    glColor4f(0.4, 0.25, 0.15, 1.0); _draw_wireframe_cylinder(0.2, 1.0, color=color, fill_color=(0.4, 0.25, 0.15, 1.0))
    # Canopy (Larger Triple-X)
    glPushMatrix(); glTranslatef(0, 2.5, 0); glScalef(2.5, 4.0, 2.5)
    _draw_billboard_bush(color, fill_color); glPopMatrix()


def _draw_proxy_rock(color=OBJECT_COLOR, fill_color=(0.4, 0.4, 0.4, 0.7)):
    """Draws a simplified rock placeholder."""
    glPushMatrix(); glScalef(1.2, 0.7, 1.1)
    _draw_wireframe_sphere(0.6, 6, 4, color, fill_color); glPopMatrix()


# ===================================================================
# Gizmo drawing helpers
# ===================================================================

def _draw_gizmo_move_3d(size=1.0, hover_part=None):
    """Draw UE5-style Move gizmo: 3 axis arrows (X=red, Y=green, Z=blue) + planes."""
    glDisable(GL_DEPTH_TEST)
    s = size

    def get_color(axis, base):
        if hover_part == axis: return (1.0, 1.0, 0.0, 1.0) # Yellow highlight
        return base

    # Axis shafts
    glLineWidth(4.0 if hover_part in ("X","Y","Z") else 2.5)
    glBegin(GL_LINES)
    glColor4f(*get_color("X", (0.95, 0.2, 0.2, GIZMO_ALPHA))); glVertex3f(0,0,0); glVertex3f(s,0,0)
    glColor4f(*get_color("Y", (0.2, 0.95, 0.2, GIZMO_ALPHA))); glVertex3f(0,0,0); glVertex3f(0,s,0)
    glColor4f(*get_color("Z", (0.3, 0.3, 0.95, GIZMO_ALPHA))); glVertex3f(0,0,0); glVertex3f(0,0,s)
    glEnd()

    # Arrowheads
    arrow = s * 0.18
    segs = 8
    for axis, color_tuple, tip, perp1, perp2 in [
        ("X", (0.95,0.2,0.2,GIZMO_ALPHA), (s,0,0), (0,1,0), (0,0,1)),
        ("Y", (0.2,0.95,0.2,GIZMO_ALPHA), (0,s,0), (1,0,0), (0,0,1)),
        ("Z", (0.3,0.3,0.95,GIZMO_ALPHA), (0,0,s), (1,0,0), (0,1,0)),
    ]:
        glColor4f(*get_color(axis, color_tuple))
        base_offset = [0,0,0]
        base_offset[{"X":0,"Y":1,"Z":2}[axis]] = s - arrow
        glBegin(GL_TRIANGLES)
        for i in range(segs):
            a1 = 2.0 * math.pi * i / segs
            a2 = 2.0 * math.pi * (i+1) / segs
            r = arrow * 0.25
            v1 = _add(base_offset, _add(_scale_vec(perp1, r*math.cos(a1)), _scale_vec(perp2, r*math.sin(a1))))
            v2 = _add(base_offset, _add(_scale_vec(perp1, r*math.cos(a2)), _scale_vec(perp2, r*math.sin(a2))))
            glVertex3f(*v1); glVertex3f(*v2); glVertex3f(*tip)
        glEnd()

    # Small planes
    ps = s * 0.3
    for part, color, v0, v1, v2, v3 in [
        ("XY", (0.95,0.95,0.2), (0,0,0), (ps,0,0), (ps,ps,0), (0,ps,0)),
        ("XZ", (0.95,0.2,0.95), (0,0,0), (ps,0,0), (ps,0,ps), (0,0,ps)),
        ("YZ", (0.2,0.95,0.95), (0,0,0), (0,ps,0), (0,ps,ps), (0,0,ps)),
    ]:
        alpha = 0.6 if hover_part == part else 0.15
        glColor4f(color[0], color[1], color[2], alpha)
        glBegin(GL_QUADS); glVertex3f(*v0); glVertex3f(*v1); glVertex3f(*v2); glVertex3f(*v3); glEnd()
        if hover_part == part:
            glColor4f(1, 1, 0, 0.8); glLineWidth(2.0)
            glBegin(GL_LINE_LOOP); glVertex3f(*v0); glVertex3f(*v1); glVertex3f(*v2); glVertex3f(*v3); glEnd()

    glLineWidth(1.0); glEnable(GL_DEPTH_TEST)


def _draw_gizmo_rotate_3d(size=1.0, hover_part=None):
    """Draw UE5-style Rotate gizmo: 3 circle rings (X=red, Y=green, Z=blue)."""
    glDisable(GL_DEPTH_TEST)
    segs = 64
    r = size * 0.9

    def get_color(axis, base):
        if hover_part == axis: return (1.0, 1.0, 0.0, 1.0)
        return base

    glLineWidth(3.5 if hover_part else 2.5)
    # X ring (YZ plane) — red
    glColor4f(*get_color("X", (0.95, 0.2, 0.2, GIZMO_ALPHA)))
    glBegin(GL_LINE_LOOP)
    for i in range(segs):
        a = 2.0 * math.pi * i / segs
        glVertex3f(0, r*math.cos(a), r*math.sin(a))
    glEnd()

    # Y ring (XZ plane) — green
    glColor4f(*get_color("Y", (0.2, 0.95, 0.2, GIZMO_ALPHA)))
    glBegin(GL_LINE_LOOP)
    for i in range(segs):
        a = 2.0 * math.pi * i / segs
        glVertex3f(r*math.cos(a), 0, r*math.sin(a))
    glEnd()

    # Z ring (XY plane) — blue
    glColor4f(*get_color("Z", (0.3, 0.3, 0.95, GIZMO_ALPHA)))
    glBegin(GL_LINE_LOOP)
    for i in range(segs):
        a = 2.0 * math.pi * i / segs
        glVertex3f(r*math.cos(a), r*math.sin(a), 0)
    glEnd()

    glLineWidth(1.0)
    glEnable(GL_DEPTH_TEST)


def _draw_gizmo_scale_3d(size=1.0, hover_part=None):
    """Draw Premium Modern Scale gizmo: Sleek shafts with solid-lit cubes."""
    glDisable(GL_DEPTH_TEST)
    s = size

    def get_color(axis, base):
        if hover_part == axis or (hover_part == "Uniform"): 
            return (1.0, 1.0, 0.4, 1.0) # Vibrant Golden highlight
        return base

    # Axis shafts - Thicker for premium feel
    glLineWidth(5.0 if hover_part else 3.5)
    glBegin(GL_LINES)
    # X - Modern Red
    glColor4f(*get_color("X", (1.0, 0.3, 0.3, GIZMO_ALPHA))); glVertex3f(0,0,0); glVertex3f(s,0,0)
    # Y - Modern Green
    glColor4f(*get_color("Y", (0.3, 1.0, 0.3, GIZMO_ALPHA))); glVertex3f(0,0,0); glVertex3f(0,s,0)
    # Z - Modern Blue
    glColor4f(*get_color("Z", (0.3, 0.4, 1.0, GIZMO_ALPHA))); glVertex3f(0,0,0); glVertex3f(0,0,s)
    glEnd()

    # Cube tips (Solid Cubes)
    cube_sz = s * 0.1
    for axis, color_tuple, center in [
        ("X", (1.0, 0.3, 0.3, GIZMO_ALPHA), (s,0,0)),
        ("Y", (0.3, 1.0, 0.3, GIZMO_ALPHA), (0,s,0)),
        ("Z", (0.3, 0.4, 1.0, GIZMO_ALPHA), (0,0,s)),
    ]:
        col = get_color(axis, color_tuple)
        cx, cy, cz = center
        glPushMatrix()
        glTranslatef(cx, cy, cz)
        # Draw solid cube at tip
        _draw_wireframe_cube(cube_sz, cube_sz, cube_sz, col, (col[0], col[1], col[2], 0.7))
        glPopMatrix()

    # Center box (Uniform Scale)
    center_sz = s * 0.15
    is_uni = (hover_part == "Uniform")
    uc = (1.0, 1.0, 0.4, 1.0) if is_uni else (1.0, 1.0, 1.0, 0.3)
    
    glPushMatrix()
    # Draw central glowing box
    _draw_wireframe_cube(center_sz, center_sz, center_sz, (uc[0], uc[1], uc[2], 0.9 if is_uni else 0.4), 
                        (uc[0], uc[1], uc[2], 0.5 if is_uni else 0.1))
    glPopMatrix()

    glLineWidth(1.0); glEnable(GL_DEPTH_TEST)


def _draw_gizmo_move_2d(size=1.0, hover_part=None):
    """Draw 2D move gizmo: X and Y arrows with XY plane handle."""
    glDisable(GL_DEPTH_TEST)
    s = size

    def get_color(axis, base):
        if hover_part == axis: return (1.0, 1.0, 0.0, 1.0)
        return base

    glLineWidth(3.5 if hover_part in ("X","Y","XY") else 2.5)
    glBegin(GL_LINES)
    # X axis
    glColor4f(*get_color("X", (0.95, 0.2, 0.2, GIZMO_ALPHA))); glVertex2f(0,0); glVertex2f(s,0)
    # Y axis (pointing up in 2D world coords)
    glColor4f(*get_color("Y", (0.2, 0.95, 0.2, GIZMO_ALPHA))); glVertex2f(0,0); glVertex2f(0,s)
    glEnd()

    # Arrowheads
    ah = s * 0.15
    glBegin(GL_TRIANGLES)
    glColor4f(*get_color("X", (0.95, 0.2, 0.2, GIZMO_ALPHA)))
    glVertex2f(s,0); glVertex2f(s-ah, ah*0.4); glVertex2f(s-ah, -ah*0.4)
    glColor4f(*get_color("Y", (0.2, 0.95, 0.2, GIZMO_ALPHA)))
    glVertex2f(0,s); glVertex2f(ah*0.4, s-ah); glVertex2f(-ah*0.4, s-ah)
    glEnd()

    # XY handle
    ps = s * 0.2
    c_xy = (0.9, 0.9, 0.3, 0.6 if hover_part == "XY" else 0.15)
    glColor4f(*c_xy)
    glBegin(GL_QUADS); glVertex2f(0,0); glVertex2f(ps,0); glVertex2f(ps,ps); glVertex2f(0,ps); glEnd()
    if hover_part == "XY":
        glColor4f(1, 1, 0, 0.8); glLineWidth(2.0)
        glBegin(GL_LINE_LOOP); glVertex2f(0,0); glVertex2f(ps,0); glVertex2f(ps,ps); glVertex2f(0,ps); glEnd()

    glLineWidth(1.0); glEnable(GL_DEPTH_TEST)


def _draw_gizmo_rotate_2d(size=1.0, hover_part=None):
    """Draw 2D rotate gizmo as a circle with a top handle."""
    glDisable(GL_DEPTH_TEST)
    r = size * 0.85
    segs = 48
    
    col = (1.0, 1.0, 0.0, 1.0) if hover_part == "Rotate" else (0.3, 0.3, 0.95, GIZMO_ALPHA)
    
    # Guideline circle
    glColor4f(col[0], col[1], col[2], 0.3); glLineWidth(1.0)
    glBegin(GL_LINE_LOOP)
    for i in range(segs):
        a = 2.0 * math.pi * i / segs
        glVertex2f(r*math.cos(a), r*math.sin(a))
    glEnd()
    # Center box
    glColor4f(0.9,0.9,0.9,GIZMO_ALPHA)
    ch = size * 0.08
    glBegin(GL_LINE_LOOP)
    glVertex2f(-ch,-ch); glVertex2f(ch,-ch); glVertex2f(ch,ch); glVertex2f(-ch,ch)
    glEnd()
    glLineWidth(1.0)
    glEnable(GL_DEPTH_TEST)

def _draw_gizmo_scale_2d(size=1.0, hover_part=None):
    """Draw 2D scale gizmo with solid squares at the ends."""
    glDisable(GL_DEPTH_TEST)
    s = size

    def get_color(axis, base):
        if hover_part == axis or (hover_part == "Uniform"): return (1.0, 1.0, 0.0, 1.0)
        return base

    glLineWidth(3.5 if hover_part in ("X","Y","Uniform") else 2.5)
    glBegin(GL_LINES)
    glColor4f(*get_color("X", (0.95, 0.2, 0.2, GIZMO_ALPHA))); glVertex2f(0,0); glVertex2f(s,0)
    glColor4f(*get_color("Y", (0.2, 0.95, 0.2, GIZMO_ALPHA))); glVertex2f(0,0); glVertex2f(0,s)
    glEnd()

    sq = s * 0.12
    col_x = get_color("X", (0.95, 0.2, 0.2, GIZMO_ALPHA))
    glColor4f(*col_x)
    glBegin(GL_QUADS); glVertex2f(s-sq,-sq); glVertex2f(s+sq,-sq); glVertex2f(s+sq,sq); glVertex2f(s-sq,sq); glEnd()
    
    col_y = get_color("Y", (0.2, 0.95, 0.2, GIZMO_ALPHA))
    glColor4f(*col_y)
    glBegin(GL_QUADS); glVertex2f(-sq,s-sq); glVertex2f(sq,s-sq); glVertex2f(sq,s+sq); glVertex2f(-sq,s+sq); glEnd()

    cu = s * 0.15
    col_u = get_color("Uniform", (0.9, 0.9, 0.3, GIZMO_ALPHA))
    glColor4f(col_u[0],col_u[1],col_u[2],0.6 if hover_part=="Uniform" else 0.15)
    glBegin(GL_QUADS); glVertex2f(0,0); glVertex2f(cu,0); glVertex2f(cu,cu); glVertex2f(0,cu); glEnd()
    if hover_part == "Uniform":
        glColor4f(1,1,0,0.8); glLineWidth(2.0)
        glBegin(GL_LINE_LOOP); glVertex2f(0,0); glVertex2f(cu,0); glVertex2f(cu,cu); glVertex2f(0,cu); glEnd()

    glLineWidth(1.0); glEnable(GL_DEPTH_TEST)


def _ray_intersect_aabb(origin, direction, aabb_min, aabb_max):
    """Simple ray-AABB intersection. Returns distance or None."""
    tmin = -1e30; tmax = 1e30
    for i in range(3):
        if abs(direction[i]) < 1e-9:
            if origin[i] < aabb_min[i] or origin[i] > aabb_max[i]:
                return None
        else:
            t1 = (aabb_min[i] - origin[i]) / direction[i]
            t2 = (aabb_max[i] - origin[i]) / direction[i]
            if t1 > t2: t1, t2 = t2, t1
            tmin = max(tmin, t1)
            tmax = min(tmax, t2)
            if tmin > tmax:
                return None
    return tmin if tmin >= 0 else (tmax if tmax >= 0 else None)


# ===================================================================
# OpenGL Viewport
# ===================================================================

if QOpenGLWidget and HAS_OPENGL:
    class SceneViewport(QOpenGLWidget):
        """OpenGL viewport with 2D/3D grid, scene objects, gizmos, and UE5 camera nav."""

        fps_updated = pyqtSignal(int)
        object_selected = pyqtSignal(object)      # SceneObject or None
        object_dropped = pyqtSignal(str, float, float, int, int)  # type, wx, wz, mx, my
        object_moved = pyqtSignal()                # after drag completes
        state_about_to_change = pyqtSignal()       # emitted BEFORE an operation starts for undo
        state_changed = pyqtSignal()               # after operation finishes

        def __init__(self, parent=None):
            fmt = QSurfaceFormat()
            fmt.setDepthBufferSize(24)
            fmt.setSamples(4)
            fmt.setSwapInterval(1)
            QSurfaceFormat.setDefaultFormat(fmt)
            super().__init__(parent)
            self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            self.setMouseTracking(True)
            self.setAcceptDrops(True)

            self._mode = "3D"
            self._cam3d = Camera3D()
            self._cam2d = Camera2D()

            self._keys = set()
            self._rmb = False
            self._mmb = False
            self._lmb = False
            self._last_mouse = None
            self._drag_object = None
            self._drag_start_pos = None
            self._drag_world_start = None  # world position under mouse at drag start

            self._frame_timer = QTimer(self)
            self._frame_timer.timeout.connect(self._tick)
            self._last_time = time.perf_counter()
            self._frame_count = 0
            self._fps_accum = 0.0
            self._current_fps = 0
            # Debug flag to print camera/light info once at startup
            self._debug_frame_logged = False
            self._elapsed_time = 0.0 # High-precision relative time for shaders
            self._mode = "3D"
            self.is_play_mode = False

            self.grid_size = 1.0
            self.grid_extent = 200
            self.show_grid = True
            self.snap_enabled = False

            self.scene_objects: List[SceneObject] = []
            self._transform_mode = "move"
            self._transform_space = "Global"
            self._hover_gizmo_part = None
            self._active_gizmo_part = None
            self._drag_obj_initial_rot = None
            self._drag_obj_initial_scale = None
            
            # Performance optimization: Throttle vegetation spawning during exploration
            self._spawn_frame_skip = 0
            self._last_spawn_cam_pos = [0, 0, 0]

        def set_mode(self, mode: str):
            self._mode = mode; self.update()
        def set_transform_mode(self, mode: str):
            self._transform_mode = mode; self.update()

        def set_transform_space(self, space: str):
            self._transform_space = space
            self.update()

        def _get_all_descendants(self, obj_id):
            descendants = []
            children = [o for o in self.scene_objects if o.parent_id == obj_id]
            for child in children:
                descendants.append(child)
                descendants.extend(self._get_all_descendants(child.id))
            return descendants

        def _get_selection_center(self):
            sel = [o for o in self.scene_objects if o.selected]
            if not sel: return
            
            center = self._get_selection_center()
            if self._mode == "3D":
                # Find bounding sphere radius
                max_d = 0.5 # minimum radius
                for o in sel:
                    d = _length(_sub(tuple(o.position), tuple(center)))
                    max_d = max(max_d, d + _length(o.scale)*0.5)
                
                # Move camera to view the sphere
                f = self._cam3d.front
                dist = max_d / math.tan(math.radians(self._cam3d.fov * 0.5))
                self._cam3d.pos = [center[0] - f[0]*dist*1.5, center[1] - f[1]*dist*1.5, center[2] - f[2]*dist*1.5]
            else:
                # 2D Bounding Box
                min_x, min_y = 1e9, 1e9
                max_x, max_y = -1e9, -1e9
                for o in sel:
                    hw, hh = o.scale[0]*0.5, o.scale[1]*0.5
                    min_x = min(min_x, o.position[0]-hw); max_x = max(max_x, o.position[0]+hw)
                    min_y = min(min_y, o.position[1]-hh); max_y = max(max_y, o.position[1]+hh)
                
                self._cam2d.x, self._cam2d.y = center[0], center[1]
                w, h = max_x - min_x, max_y - min_y
                self._cam2d.zoom_level = max(w, h) * 0.8
            self.update()

        def set_grid_size(self, size: float):
            self.grid_size = size; self.update()

        def set_snap_enabled(self, enabled: bool):
            self.snap_enabled = enabled; self.update()

        def set_mode(self, mode: str):
            """Switch between 2D and 3D modes."""
            if mode in ("2D", "3D"):
                self._mode = mode
                self.update()

        def set_show_grid(self, show: bool):

            self.show_grid = show; self.update()

        def start_render_loop(self):
            self._last_time = time.perf_counter()
            self._frame_timer.start(16)

        def stop_render_loop(self):
            self._frame_timer.stop()

        def _tick(self):
            now = time.perf_counter()
            dt = now - self._last_time; self._last_time = now
            self._frame_count += 1; self._fps_accum += dt
            if self._fps_accum >= 1.0:
                self._current_fps = self._frame_count
                self.fps_updated.emit(self._current_fps)
                self._frame_count = 0; self._fps_accum = 0.0

            if self._mode == "3D" and self._rmb:
                fwd = (1 if Qt.Key.Key_W in self._keys else 0) - (1 if Qt.Key.Key_S in self._keys else 0)
                rgt = (1 if Qt.Key.Key_D in self._keys else 0) - (1 if Qt.Key.Key_A in self._keys else 0)
                upd = (1 if Qt.Key.Key_E in self._keys else 0) - (1 if Qt.Key.Key_Q in self._keys else 0)
                if fwd or rgt or upd:
                    self._cam3d.move(fwd, rgt, upd, dt)

            self._elapsed_time += max(0.0, min(dt, 0.1)) # Update clock, clamp spikes to 100ms
            self.update()

        # ---- OpenGL ----
        def initializeGL(self):
            glClearColor(*BG_COLOR)
            glEnable(GL_DEPTH_TEST); glEnable(GL_BLEND)
            glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
            
            # Initialize specialized systems
            try:
                init_ocean_gpu()
            except Exception as e:
                print(f"[GL INIT ERROR] Failed to initialize GPU Ocean: {e}")
            glEnable(GL_LINE_SMOOTH); glHint(GL_LINE_SMOOTH_HINT, GL_NICEST)
            glEnable(GL_MULTISAMPLE)
            
            glEnable(GL_MULTISAMPLE)
            glEnable(GL_LIGHTING)
            glEnable(GL_COLOR_MATERIAL)
            glColorMaterial(GL_FRONT_AND_BACK, GL_AMBIENT_AND_DIFFUSE)
            glEnable(GL_NORMALIZE)
            glShadeModel(GL_SMOOTH)
            self._setup_scene_lighting()
            
            # Auto-start the high-precision animation loop once the context is live
            self.start_render_loop()

        def resizeGL(self, w, h):
            glViewport(0, 0, w, h)

        def contextMenuEvent(self, event):
            # Suppress right-click context menu during simulation as requested
            if getattr(self, 'is_play_mode', False):
                event.accept()
                return
            super().contextMenuEvent(event)

        def paintGL(self):
            if getattr(self, "is_play_mode", False):
                # Pure black background as requested
                glClearColor(0.0, 0.0, 0.0, 1.0)
            else:
                glClearColor(*BG_COLOR)
            glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)


            w, h = self.width(), self.height()
            if w < 1 or h < 1: return
            # One-time debug dump to help diagnose camera/light issues
            if not getattr(self, '_debug_frame_logged', False):
                try:
                    is_play = getattr(self, 'is_play_mode', False)
                    cam = getattr(self, '_cam3d', None)
                    lights = [o for o in self.scene_objects if o.active and 'light' in o.obj_type]
                    print(f"[VIEW DEBUG] play={is_play} vp={w}x{h} objects={len(self.scene_objects)} lights={len(lights)}")
                    if cam is not None:
                        try:
                            f = cam.front; u = cam.up
                        except Exception:
                            f, u = None, None
                        print(f"[VIEW DEBUG] cam.pos={cam.pos} yaw={cam.yaw} pitch={cam.pitch} fov={cam.fov} front={f} up={u}")
                    for i, L in enumerate(lights[:8]):
                        print(f"[VIEW DEBUG] light[{i}] type={L.obj_type} pos={L.position} rot={L.rotation} active={L.active} visible={L.visible}")
                    # GL error check (if available)
                    try:
                        err = glGetError()
                        if err != GL_NO_ERROR:
                            print(f"[VIEW DEBUG] GL_ERROR: {err}")
                    except Exception:
                        pass
                except Exception as e:
                    print(f"[VIEW DEBUG] failed to dump debug info: {e}")
                self._debug_frame_logged = True
            if self._mode == "3D":
                self._cam3d.apply_gl(w / max(h, 1))
                self._setup_scene_lighting() # Update positions each frame
                if not getattr(self, 'is_play_mode', False):
                    self._draw_grid_3d()
                self._draw_scene_objects_3d()
                self._draw_gizmo_for_selected_3d()
                if not getattr(self, 'is_play_mode', False):
                    self._draw_axis_gizmo_3d(w, h)
            elif self._mode == "2D":
                self._cam2d.apply_gl(w, h)
                self._draw_grid_2d()
                self._draw_scene_objects_2d()
                self._draw_gizmo_for_selected_2d()

            self._draw_overlay_2d(w, h)
            
            # --- QPainter Overlay for Diagnostics ---
            if getattr(self, "is_play_mode", False):
                painter = QPainter(self)
                painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                painter.setPen(QPen(QColor(255, 255, 255, 180)))
                font = QFont("Segoe UI", 12, QFont.Weight.Bold)
                painter.setFont(font)
                painter.drawText(10, 30, "● SIMULATION ENGINE ACTIVE")
                
                # Show camera name
                font.setWeight(QFont.Weight.Normal)
                font.setPointSize(9)
                painter.setFont(font)
                cam_name = getattr(self, "_active_cam_name", "Default Editor Camera")
                painter.drawText(10, 50, f"Camera: {cam_name}")
                painter.end()


        def _draw_overlay_2d(self, w, h):
            if getattr(self, '_drag_action', None) == "box_select" and getattr(self, '_select_start', None) and getattr(self, '_select_current', None):
                x1, y1 = self._select_start
                x2, y2 = self._select_current
                min_x = min(x1, x2); max_x = max(x1, x2)
                min_y = min(y1, y2); max_y = max(y1, y2)
                
                glMatrixMode(GL_PROJECTION)
                glPushMatrix()
                glLoadIdentity()
                glOrtho(0, w, h, 0, -1, 1)
                
                glMatrixMode(GL_MODELVIEW)
                glPushMatrix()
                glLoadIdentity()
                
                glDisable(GL_DEPTH_TEST)
                glEnable(GL_BLEND)
                
                # Fill
                glColor4f(0.3, 0.7, 1.0, 0.2)
                glBegin(GL_QUADS)
                glVertex2f(min_x, min_y)
                glVertex2f(max_x, min_y)
                glVertex2f(max_x, max_y)
                glVertex2f(min_x, max_y)
                glEnd()
                
                # Outline
                glColor4f(0.3, 0.7, 1.0, 0.8)
                glLineWidth(1.5)
                glBegin(GL_LINE_LOOP)
                glVertex2f(min_x, min_y)
                glVertex2f(max_x, min_y)
                glVertex2f(max_x, max_y)
                glVertex2f(min_x, max_y)
                glEnd()
                glLineWidth(1.0)
                
                glEnable(GL_DEPTH_TEST)
                
                glMatrixMode(GL_PROJECTION)
                glPopMatrix()
                glMatrixMode(GL_MODELVIEW)
                glPopMatrix()

        # ---- 3D Grid ----
        def _draw_grid_3d(self):
            if not self.show_grid: return
            extent = self.grid_extent; step = self.grid_size
            glDepthMask(GL_FALSE)
            cam_y = abs(self._cam3d.pos[1])
            adaptive_step = step
            if cam_y > 50: adaptive_step = step * 10
            elif cam_y > 20: adaptive_step = step * 5
            elif cam_y > 8: adaptive_step = step * 2
            glLineWidth(1.0); glBegin(GL_LINES)
            for i in range(-extent, extent + 1):
                v = i * adaptive_step
                if i == 0: continue
                glColor4f(*(GRID_MAJOR_COLOR if i % 10 == 0 else GRID_MINOR_COLOR))
                glVertex3f(-extent*adaptive_step, 0, v); glVertex3f(extent*adaptive_step, 0, v)
                glVertex3f(v, 0, -extent*adaptive_step); glVertex3f(v, 0, extent*adaptive_step)
            glEnd()
            half = extent * adaptive_step
            glLineWidth(2.0); glBegin(GL_LINES)
            glColor4f(*AXIS_X_COLOR); glVertex3f(-half,0.001,0); glVertex3f(half,0.001,0)
            glColor4f(*AXIS_Z_COLOR); glVertex3f(0,0.001,-half); glVertex3f(0,0.001,half)
            glEnd()
            glBegin(GL_LINES)
            glColor4f(*AXIS_Y_COLOR); glVertex3f(0,0,0); glVertex3f(0,half*0.1,0)
            glEnd()
            glLineWidth(1.0); glDepthMask(GL_TRUE)

        def _draw_axis_gizmo_3d(self, vp_w, vp_h):
            gs = 60; m = 10
            glMatrixMode(GL_PROJECTION); glPushMatrix(); glLoadIdentity()
            glOrtho(0, vp_w, 0, vp_h, -100, 100)
            glMatrixMode(GL_MODELVIEW); glPushMatrix(); glLoadIdentity()
            cx, cy = m + gs, m + gs; glTranslatef(cx, cy, 0)
            yr, pr = math.radians(self._cam3d.yaw), math.radians(self._cam3d.pitch)
            s = gs * 0.7
            xp = (math.cos(yr)*s, math.sin(pr)*math.sin(yr)*s*(-1))
            yp = (0, math.cos(pr)*s)
            zp = (math.sin(yr)*s, math.sin(pr)*math.cos(yr)*s)
            glDisable(GL_DEPTH_TEST); glLineWidth(2.5)
            glBegin(GL_LINES)
            glColor4f(*AXIS_X_COLOR); glVertex2f(0,0); glVertex2f(xp[0],-xp[1])
            glColor4f(*AXIS_Y_COLOR); glVertex2f(0,0); glVertex2f(yp[0],yp[1])
            glColor4f(*AXIS_Z_COLOR); glVertex2f(0,0); glVertex2f(zp[0],-zp[1])
            glEnd()
            glPointSize(6.0); glBegin(GL_POINTS)
            glColor4f(*AXIS_X_COLOR); glVertex2f(xp[0],-xp[1])
            glColor4f(*AXIS_Y_COLOR); glVertex2f(yp[0],yp[1])
            glColor4f(*AXIS_Z_COLOR); glVertex2f(zp[0],-zp[1])
            glEnd(); glPointSize(1.0)
            glEnable(GL_DEPTH_TEST); glLineWidth(1.0)
            glMatrixMode(GL_PROJECTION); glPopMatrix()
            glMatrixMode(GL_MODELVIEW); glPopMatrix()

        # ---- 2D Grid ----
        def _draw_grid_2d(self):
            if not self.show_grid: return
            zoom = self._cam2d.zoom_level; step = self.grid_size
            if zoom > 500: step = 100
            elif zoom > 100: step = 50
            elif zoom > 50: step = 10
            elif zoom > 20: step = 5
            elif zoom > 5: step = 1
            else: step = 0.5
            cx, cy = self._cam2d.x, self._cam2d.y
            half_w = zoom * (self.width() / max(self.height(), 1)); half_h = zoom
            xs = int((cx-half_w)/step-1)*step; xe = int((cx+half_w)/step+2)*step
            ys = int((cy-half_h)/step-1)*step; ye = int((cy+half_h)/step+2)*step
            glDisable(GL_DEPTH_TEST); glLineWidth(1.0); glBegin(GL_LINES)
            x = xs
            while x <= xe:
                if abs(x) < 1e-6: x += step; continue
                is_major = abs(round(x/(step*10))*(step*10)-x) < 1e-6
                glColor4f(*(GRID_MAJOR_COLOR if is_major else GRID_MINOR_COLOR))
                glVertex2f(x, ys); glVertex2f(x, ye); x += step
            y = ys
            while y <= ye:
                if abs(y) < 1e-6: y += step; continue
                is_major = abs(round(y/(step*10))*(step*10)-y) < 1e-6
                glColor4f(*(GRID_MAJOR_COLOR if is_major else GRID_MINOR_COLOR))
                glVertex2f(xs, y); glVertex2f(xe, y); y += step
            glEnd()
            glLineWidth(2.0); glBegin(GL_LINES)
            glColor4f(*AXIS_X_COLOR); glVertex2f(xs,0); glVertex2f(xe,0)
            glColor4f(*AXIS_Y_COLOR); glVertex2f(0,ys); glVertex2f(0,ye)
            glEnd()
            glPointSize(6.0); glBegin(GL_POINTS)
            glColor4f(*ORIGIN_COLOR); glVertex2f(0,0)
            glEnd(); glPointSize(1.0)
            glLineWidth(1.0); glEnable(GL_DEPTH_TEST)

        def _draw_single_object_3d(self, obj, is_play):
            # Must be active to exist, and visible (or we are in editor)
            if not obj.active: return
            if is_play and not obj.visible: return
            
            glPushMatrix()
            glTranslatef(*obj.position)
            glRotatef(obj.rotation[1], 0, 1, 0) # Yaw (Global Up)
            glRotatef(obj.rotation[0], 1, 0, 0) # Pitch
            glRotatef(obj.rotation[2], 0, 0, 1) # Roll
            glScalef(*obj.scale)
            # Ensure material override flags exist regardless of branch
            material_override = False
            was_color_mat = None

            if obj.selected:
                color = tuple(SELECT_COLOR)
                fill = (color[0]*0.3, color[1]*0.3, color[2]*0.3, 0.4)
            else:
                # Use material base_color for fill (respect alpha)
                bc = obj.get_render_color()
                base_alpha = bc[3] if len(bc) > 3 else 1.0
                color = (bc[0]*0.8, bc[1]*0.8, bc[2]*0.8, 0.9)
                fill = (bc[0], bc[1], bc[2], base_alpha)
                # Emissive glow — brighten the wireframe
                ec = obj.get_emissive_color()
                if ec[0] > 0.01 or ec[1] > 0.01 or ec[2] > 0.01:
                    color = (min(1, bc[0] + ec[0]*0.5), min(1, bc[1] + ec[1]*0.5), min(1, bc[2] + ec[2]*0.5), 1.0)

                # Basic fixed-function material mapping: map roughness -> shininess, metallic -> specular tint
                try:
                    mat = getattr(obj, 'material', {}) or {}
                    roughness = float(mat.get('roughness', 0.7))
                    metallic = float(mat.get('metallic', 0.0))
                    # Diffuse (base)
                    diffuse = (fill[0], fill[1], fill[2], fill[3])
                    # Specular color blends between a low dielectric spec and base color for metals
                    spec_base = 0.04
                    specular_color = (
                        spec_base * (1.0 - metallic) + diffuse[0] * metallic,
                        spec_base * (1.0 - metallic) + diffuse[1] * metallic,
                        spec_base * (1.0 - metallic) + diffuse[2] * metallic,
                    )
                    # Stronger, more visible specular mapping
                    spec_strength = max(0.02, (1.0 - roughness) * (0.4 + metallic * 0.8))
                    shininess = max(1.0, (1.0 - roughness) ** 2 * 256.0)

                    # Decide whether to override color-material with GL material (better for metals)
                    material_override = (metallic > 0.05)
                    if material_override:
                        # Reduce diffuse contribution for metals so specular dominates
                        diff_scale = max(0.05, 1.0 - 0.85 * metallic)
                        diffuse_adj = (diffuse[0] * diff_scale, diffuse[1] * diff_scale, diffuse[2] * diff_scale, diffuse[3])
                        try:
                            was_color_mat = glIsEnabled(GL_COLOR_MATERIAL)
                        except Exception:
                            was_color_mat = False
                        if was_color_mat:
                            glDisable(GL_COLOR_MATERIAL)
                        try:
                            glMaterialfv(GL_FRONT_AND_BACK, GL_AMBIENT_AND_DIFFUSE, diffuse_adj)
                            glMaterialfv(GL_FRONT_AND_BACK, GL_SPECULAR, (specular_color[0] * spec_strength, specular_color[1] * spec_strength, specular_color[2] * spec_strength, 1.0))
                            glMaterialf(GL_FRONT_AND_BACK, GL_SHININESS, shininess)
                            glMaterialfv(GL_FRONT_AND_BACK, GL_EMISSION, (ec[0], ec[1], ec[2], 1.0))
                        except Exception:
                            pass
                except Exception:
                    material_override = False
                    was_color_mat = None
            
            if not obj.active: # In editor mode, darken inactive
                color = (0.2, 0.2, 0.2, 0.4)
                fill = (0.1, 0.1, 0.1, 0.2)
            
            if obj.selected: glLineWidth(3.0)
            else: glLineWidth(1.0)
            t = obj.obj_type
            # If we applied a material override (for metals), draw while color-material is disabled
            def _call_draw(func, *args, **kwargs):
                try:
                    func(*args, **kwargs)
                finally:
                    # Re-enable color material if we disabled it earlier
                    try:
                        if material_override and was_color_mat:
                            glEnable(GL_COLOR_MATERIAL)
                    except Exception:
                        pass

            if t == 'cube':
                if material_override:
                    _call_draw(_draw_wireframe_cube, 1,1,1, color, fill)
                else:
                    _draw_wireframe_cube(1,1,1, color, fill)
            elif t == 'sphere':
                if material_override:
                    _call_draw(_draw_wireframe_sphere, 0.5, color=color, fill_color=fill)
                else:
                    _draw_wireframe_sphere(0.5, color=color, fill_color=fill)
            elif t == 'cylinder':
                if material_override:
                    _call_draw(_draw_wireframe_cylinder, 0.5, 1.0, color=color, fill_color=fill)
                else:
                    _draw_wireframe_cylinder(0.5, 1.0, color=color, fill_color=fill)
            elif t == 'plane':
                if material_override:
                    _call_draw(_draw_wireframe_plane, 2, 2, color, fill)
                else:
                    _draw_wireframe_plane(2, 2, color, fill)
            elif t == 'cone':
                if material_override:
                    _call_draw(_draw_wireframe_cone, 0.5, 1.0, color=color, fill_color=fill)
                else:
                    _draw_wireframe_cone(0.5, 1.0, color=color, fill_color=fill)
            elif t == 'mesh':
                # Smart Visualizer: Use representative billboards for vegetation and generic assets
                l_name = (obj.name + "_" + (obj.file_path or "")).lower()
                if "bush" in l_name:
                    if material_override: _call_draw(_draw_billboard_bush, color, fill)
                    else: _draw_billboard_bush(color, fill)
                elif "tree" in l_name:
                    if material_override: _call_draw(_draw_billboard_tree, color, fill)
                    else: _draw_billboard_tree(color, fill)
                elif "rock" in l_name or "stone" in l_name:
                    if material_override: _call_draw(_draw_proxy_rock, color, fill)
                    else: _draw_proxy_rock(color, fill)
                else:
                    if material_override: _call_draw(_draw_wireframe_cube, 1, 1, 1, color, fill)
                    else: _draw_wireframe_cube(1, 1, 1, color, fill)
            elif t == 'logic':
                 # Draw a diamond for logic component
                 glDisable(GL_LIGHTING)
                 glPushMatrix()
                 glScalef(0.4, 0.4, 0.4)
                 glRotatef(45, 1, 0, 1)
                 _draw_wireframe_cube(1, 1, 1, (0.3, 0.8, 1.0, 1.0), (0.1, 0.4, 0.6, 0.8))
                 glPopMatrix()
                 glEnable(GL_LIGHTING)
            elif t == 'light_point':
                 glDisable(GL_LIGHTING)
                 # Glowing yellow sphere
                 _draw_wireframe_sphere(0.2, 8, 8, (1.0, 1.0, 0.0, 1.0), (1.0, 0.9, 0.2, 0.8))
                 glEnable(GL_LIGHTING)
            elif t == 'light_directional':
                 glDisable(GL_LIGHTING)
                 # Sun icon: Central sphere + parallel rays
                 _draw_wireframe_sphere(0.15, 8, 8, (1.0, 0.9, 0.2, 1.0), (1.0, 0.9, 0.1, 0.4))
                 
                 # Draw 3 parallel "sun rays"
                 arr_color = (1.0, 1.0, 0.2, 1.0)
                 glColor4f(*arr_color)
                 glLineWidth(2.0)
                 offsets = [(0.15, 0.15), (-0.15, 0.15), (0, -0.2)]
                 for ox, oy in offsets:
                     glBegin(GL_LINES)
                     glVertex3f(ox, oy, 0); glVertex3f(ox, oy, -1.8)
                     glEnd()
                     # Small tips for rays
                     glPushMatrix()
                     glTranslatef(ox, oy, -1.8)
                     glRotatef(-90, 1, 0, 0) # Rotate Y-up cone to point along -Z
                     _draw_wireframe_cone(0.05, 0.2, 6, arr_color, arr_color)
                     glPopMatrix()

                 glEnable(GL_LIGHTING)

            elif t == 'landscape':
                 try:
                     from .procedural_system import draw_landscape_3d, ensure_spawned
                     draw_landscape_3d(obj, self)
                     if getattr(obj, 'landscape_spawn_enabled', False):
                         # LIQUID SMOOTH: Only check spawning logic every 15 frames or if the camera moved significantly.
                         # This eliminates the 'micro-stutter' when moving across chunks.
                         self._spawn_frame_skip += 1
                         curr_pos = getattr(self, '_cam3d', None).pos if hasattr(self, '_cam3d') else [0,0,0]
                         dist_sq = sum((a-b)**2 for a,b in zip(curr_pos, self._last_spawn_cam_pos))
                         
                         if self._spawn_frame_skip >= 15 or dist_sq > 4.0:
                             ensure_spawned(self, obj, cam_pos=curr_pos)
                             self._spawn_frame_skip = 0
                             self._last_spawn_cam_pos = list(curr_pos)
                 except Exception as e:
                     import traceback
                     traceback.print_exc()
                     print(f"[LANDSCAPE ERROR] {e}")

            elif t == 'ocean':
                 try:
                     # render_ocean_gpu imported at top of file
                     cam_pos = getattr(self, '_cam3d', None).pos if hasattr(self, '_cam3d') else [0,0,0]
                     render_ocean_gpu(cam_pos, obj, self._elapsed_time)
                 except Exception as e:
                     print(f"[OCEAN ERROR] {e}")

            elif t == 'camera':
                 glDisable(GL_LIGHTING)
                 # Iconic "Film Camera" look
                 # 1. Main body
                 glPushMatrix()
                 glScalef(0.4, 0.4, 0.3)
                 _draw_wireframe_cube(1, 1, 1, (0.6, 0.8, 1.0, 1.0), (0.2, 0.4, 0.6, 0.3))
                 glPopMatrix()
                 
                 # 2. Two top reels
                 reel_color = (0.5, 0.7, 1.0, 1.0)
                 for ox in [-0.15, 0.15]:
                     glPushMatrix()
                     glTranslatef(ox, 0.3, 0)
                     glRotatef(90, 0, 0, 1) # Lay reels flat on top
                     _draw_wireframe_cylinder(0.18, 0.05, 12, reel_color, (0.2, 0.3, 0.5, 0.5))
                     glPopMatrix()
                     
                 # 3. Lens (pointing along -Z)
                 glPushMatrix()
                 glTranslatef(0, 0, -0.25)
                 glRotatef(-90, 1, 0, 0) # Rotate to point -Z
                 _draw_wireframe_cylinder(0.12, 0.25, 12, (0.4, 0.7, 1.0, 1.0), (0.1, 0.3, 0.5, 0.6))
                 glPopMatrix()
                 
                 # Forward arrow
                 # Proper 3D shaft
                 glPushMatrix()
                 glTranslatef(0, 0, -1.25)
                 glRotatef(-90, 1, 0, 0)
                 _draw_wireframe_cylinder(0.02, 1.5, 6, (0.2, 0.9, 1.0, 1.0), (0.2, 0.9, 1.0, 0.4))
                 glPopMatrix()
                 # Arrow Head
                 glPushMatrix()
                 glTranslatef(0, 0, -2.0)
                 glRotatef(-90, 1, 0, 0) # Cone points -Z
                 _draw_wireframe_cone(0.1, 0.25, color=(0.2, 0.9, 1.0, 1.0), fill_color=(0.1, 0.4, 0.6, 0.6))
                 glPopMatrix()
                 
                 glEnable(GL_LIGHTING)

            glPopMatrix()

        # ---- Draw scene objects ----
        def _draw_scene_objects_3d(self):
            is_play = getattr(self, 'is_play_mode', False)
            
            # Pass 1: Opaque Ground/Landscapes first to establish depth base
            # This prevents translucent objects from failing occlusions if drawn first.
            for obj in self.scene_objects:
                if obj.obj_type == 'landscape':
                    self._draw_single_object_3d(obj, is_play)
            
            # Pass 2: Everything else
            for obj in self.scene_objects:
                if obj.obj_type != 'landscape':
                    self._draw_single_object_3d(obj, is_play)

        def _draw_scene_objects_2d(self):
            glDisable(GL_DEPTH_TEST)
            for obj in self.scene_objects:
                glPushMatrix()
                glTranslatef(obj.position[0], obj.position[1], 0)
                glRotatef(obj.rotation[2], 0, 0, 1)
                glScalef(obj.scale[0], obj.scale[1], 1)
                if obj.selected:
                    color = tuple(SELECT_COLOR)
                    fill = (color[0]*0.3, color[1]*0.3, color[2]*0.3, 0.3)
                else:
                    bc = obj.get_render_color()
                    color = (bc[0]*0.8, bc[1]*0.8, bc[2]*0.8, 0.9)
                    fill = (bc[0]*0.5, bc[1]*0.5, bc[2]*0.5, bc[3] if len(bc) > 3 else 0.4)
                t = obj.obj_type
                if t in ('rect', 'sprite', 'mesh'): _draw_2d_rect(1, 1, color, fill)
                elif t == 'circle': _draw_2d_circle(0.5, color=color, fill_color=fill)
                glPopMatrix()
            glEnable(GL_DEPTH_TEST)

        # ---- Gizmos ----
        def _get_selection_center(self):
            sel = [o for o in self.scene_objects if o.selected]
            if not sel: return (0,0,0)
            avg = [0.0, 0.0, 0.0]
            for o in sel:
                for i in range(3): avg[i] += o.position[i]
            return [v / len(sel) for v in avg]

        def _get_gizmo_size_3d(self, pos):
            """Compute gizmo size proportional to screen (constant apparent size)."""
            # Ensure pos is a tuple/list of 3 floats
            p = tuple(pos)
            dist = _length(_sub(p, tuple(self._cam3d.pos)))
            return max(0.3, dist * 0.08)

        def _get_gizmo_size_2d(self):
            return self._cam2d.zoom_level * 0.15

        def _draw_gizmo_for_selected_3d(self):
            sel = [o for o in self.scene_objects if o.selected]
            if not sel: return
            
            center = self._get_selection_center()
            # Debug: in play mode, dump GL state and object info to help diagnose
            if getattr(self, 'is_play_mode', False):
                try:
                    depth_test = glIsEnabled(GL_DEPTH_TEST)
                    depth_write = glGetBooleanv(GL_DEPTH_WRITEMASK)
                    blend = glIsEnabled(GL_BLEND)
                    poly_off = glIsEnabled(GL_POLYGON_OFFSET_FILL)
                    obj_report = sel[-1] if sel else None
                    print(f"[DRAW DEBUG] sel_count={len(sel)} obj={getattr(obj_report,'name',None)} type={getattr(obj_report,'obj_type',None)} pos={getattr(obj_report,'position',None)} depth_test={depth_test} depth_write={depth_write} blend={blend} poly_offset={poly_off}")
                except Exception as e:
                    print(f"[DRAW DEBUG] gl state query failed: {e}")
            glPushMatrix()
            glTranslatef(*center)
            
            # Local Rotation Basis
            if self._transform_space == "Local":
                # Use the last selected object's rotation
                obj = sel[-1]
                glRotatef(obj.rotation[1], 0, 1, 0) # Yaw (Global Up)
                glRotatef(obj.rotation[0], 1, 0, 0) # Pitch
                glRotatef(obj.rotation[2], 0, 0, 1) # Roll

            sz = self._get_gizmo_size_3d(center)
            if self._transform_mode == "move":
                _draw_gizmo_move_3d(sz, self._hover_gizmo_part or self._active_gizmo_part)
            elif self._transform_mode == "rotate":
                _draw_gizmo_rotate_3d(sz, self._hover_gizmo_part or self._active_gizmo_part)
            elif self._transform_mode == "scale":
                _draw_gizmo_scale_3d(sz, self._hover_gizmo_part or self._active_gizmo_part)
            glPopMatrix()

        def _draw_gizmo_for_selected_2d(self):
            sel = [o for o in self.scene_objects if o.selected]
            if not sel: return
            center = self._get_selection_center()
            glPushMatrix()
            glTranslatef(center[0], center[1], 0)
            
            if self._transform_space == "Local":
                obj = sel[-1]
                glRotatef(obj.rotation[2], 0, 0, 1)

            sz = self._get_gizmo_size_2d()
            hp = self._hover_gizmo_part or self._active_gizmo_part
            if self._transform_mode == "move":
                _draw_gizmo_move_2d(sz, hp)
            elif self._transform_mode == "rotate":
                _draw_gizmo_rotate_2d(sz, hp)
            elif self._transform_mode == "scale":
                _draw_gizmo_scale_2d(sz, hp)
            glPopMatrix()

        def _setup_scene_lighting(self):
            # Disable all lights first
            for i in range(8): glDisable(GL_LIGHT0 + i)
            
            # Atmospheric ambient: Muted blue for sky fill
            amb = [0.2, 0.22, 0.28, 1.0] if not getattr(self, "is_play_mode", False) else [0.3, 0.35, 0.4, 1.0]
            glLightModelfv(GL_LIGHT_MODEL_AMBIENT, amb)
            
            lights = [o for o in self.scene_objects if o.active and "light" in o.obj_type]
            for i, light in enumerate(lights[:8]):
                light_id = GL_LIGHT0 + i
                glEnable(light_id)
                
                color = list(light.get_render_color())
                intensity = getattr(light, 'intensity', 1.0)
                diffuse = [color[0]*intensity, color[1]*intensity, color[2]*intensity, 1.0]
                glLightfv(light_id, GL_DIFFUSE, diffuse)
                glLightfv(light_id, GL_SPECULAR, diffuse)
                
                if light.obj_type == 'light_point':
                    glLightfv(light_id, GL_POSITION, (*light.position, 1.0))
                    r = getattr(light, 'range', 10.0)
                    glLightf(light_id, GL_CONSTANT_ATTENUATION, 1.0)
                    glLightf(light_id, GL_LINEAR_ATTENUATION, 2.0 / r)
                    glLightf(light_id, GL_QUADRATIC_ATTENUATION, 1.0 / (r*r))
                elif light.obj_type == 'light_directional':
                    yr = math.radians(light.rotation[1] - 90.0)
                    pr = math.radians(-light.rotation[0])
                    dx = math.cos(yr) * math.cos(pr)
                    dy = math.sin(pr)
                    dz = math.sin(yr) * math.cos(pr)
                    glLightfv(light_id, GL_POSITION, (-dx, -dy, -dz, 0.0))
            
            if not lights:
                # Default Dual-Light setup for better form definition
                # 1. Main Sun
                glEnable(GL_LIGHT0)
                glLightfv(GL_LIGHT0, GL_POSITION, (1.0, 1.0, 0.5, 0.0)) # Directional
                glLightfv(GL_LIGHT0, GL_DIFFUSE, (1.0, 0.95, 0.9, 1.0))
                glLightfv(GL_LIGHT0, GL_SPECULAR, (0.5, 0.5, 0.5, 1.0))
                
                # 2. Soft Fill/Rim
                glEnable(GL_LIGHT1)
                glLightfv(GL_LIGHT1, GL_POSITION, (-1.0, 0.5, -0.5, 0.0)) # Opposing angle
                glLightfv(GL_LIGHT1, GL_DIFFUSE, (0.15, 0.15, 0.25, 1.0))
                glLightfv(GL_LIGHT1, GL_SPECULAR, (0.0, 0.0, 0.0, 1.0))

        # ---- Object picking ----
        def _pick_object_3d(self, mx, my) -> Optional[SceneObject]:
            origin, direction = self._cam3d.screen_to_ray(mx, my, self.width(), self.height())
            best, best_dist = None, 1e30
            for obj in self.scene_objects:
                if not obj.active and getattr(self, 'is_play_mode', False): continue
                p, s = obj.position, obj.scale
                half = [s[0]/2, s[1]/2, s[2]/2]
                amin = [p[0]-half[0], p[1]-half[1], p[2]-half[2]]
                amax = [p[0]+half[0], p[1]+half[1], p[2]+half[2]]
                dist = _ray_intersect_aabb(origin, direction, amin, amax)
                if dist is not None and dist < best_dist:
                    best, best_dist = obj, dist
            return best

        def _pick_object_2d(self, mx, my) -> Optional[SceneObject]:
            wx, wy = self._cam2d.screen_to_world(mx, my, self.width(), self.height())
            best = None
            for obj in self.scene_objects:
                p, s = obj.position, obj.scale
                hw, hh = s[0]/2, s[1]/2
                if p[0]-hw <= wx <= p[0]+hw and p[1]-hh <= wy <= p[1]+hh:
                    best = obj
            return best

        # ---- Input ----
        def _pick_gizmo_3d(self, mx, my):
            sel = [o for o in self.scene_objects if o.selected]
            if not sel: return None
            
            center = self._get_selection_center()
            origin, direction = self._cam3d.screen_to_ray(mx, my, self.width(), self.height())
            sz = self._get_gizmo_size_3d(center)
            
            # Simple analytical picking for move arrows
            if self._transform_mode == "move":
                # In Local space, we need to transform the ray? 
                # For now, let's stick to world-space picking for simplicity if Global,
                # or just use the center.
                axes = [("X", (1,0,0)), ("Y", (0,1,0)), ("Z", (0,0,1))]
                
                # If Local, get the axes from the last selected
            # Standard axes
            axes = [(1,0,0), (0,1,0), (0,0,1)]
            if self._transform_space == "Local":
                M = _euler_to_matrix(*primary.rotation)
                axes = [_mat_vec_mul(M, (1,0,0)), _mat_vec_mul(M, (0,1,0)), _mat_vec_mul(M, (0,0,1))]

            PICK_RADIUS = 24
            w, h = self.width(), self.height()
            def get_dist(wp):
                sp = self._cam3d.world_to_screen(wp, w, h)
                if not sp: return 1e9
                return math.sqrt((sp[0]-mx)**2 + (sp[1]-my)**2)

            if self._transform_mode == "move":
                # Axes tips
                best_axis, min_dist = None, PICK_RADIUS
                for i_idx, name in enumerate(["X", "Y", "Z"]):
                    tip = _add(tuple(center), _scale_vec(axes[i_idx], sz))
                    d = get_dist(tip)
                    if d < min_dist: min_dist = d; best_axis = name
                if best_axis: return best_axis

                # Planar centers
                planes = [("XY", 0, 1), ("XZ", 0, 2), ("YZ", 1, 2)]
                for name, i1, i2 in planes:
                    cp = _add(tuple(center), _scale_vec(_add(axes[i1], axes[i2]), sz * 0.4))
                    if get_dist(cp) < PICK_RADIUS: return name

            elif self._transform_mode == "rotate":
                best_axis, min_dist = None, PICK_RADIUS
                r_orbit = sz * 0.95
                for ax_idx, name in enumerate(["X", "Y", "Z"]):
                    for step in range(32):
                        ang = math.radians(step * 360 / 32)
                        if name == "X": lp = (0, math.cos(ang), math.sin(ang))
                        elif name == "Y": lp = (math.cos(ang), 0, math.sin(ang))
                        else: lp = (math.cos(ang), math.sin(ang), 0)
                        
                        p_world = lp
                        if self._transform_space == "Local":
                            M = _euler_to_matrix(*primary.rotation)
                            p_world = _mat_vec_mul(M, lp)
                        
                        d = get_dist(_add(tuple(center), _scale_vec(p_world, r_orbit)))
                        if d < min_dist: min_dist = d; best_axis = name
                return best_axis
            
            elif self._transform_mode == "scale":
                if get_dist(tuple(center)) < PICK_RADIUS * 1.2: return "Uniform"
                best_part, min_dist = None, PICK_RADIUS
                for i_idx, name in enumerate(["X", "Y", "Z"]):
                    tip = _add(tuple(center), _scale_vec(axes[i_idx], sz))
                    d = get_dist(tip)
                    if d < min_dist: min_dist = d; best_part = name
                return best_part

            return None
            return None

        def _pick_gizmo_2d(self, mx, my):
            sel = [o for o in self.scene_objects if o.selected]
            if not sel: return None
            center = self._get_selection_center()
            wx, wy = self._cam2d.screen_to_world(mx, my, self.width(), self.height())
            sz = self._get_gizmo_size_2d()
            
            # Hitbox sensitivity (scaled by current zoom/size)
            hit_sz = sz * 0.15

            def dist_to_segment(px, py, x1, y1, x2, y2):
                dx, dy = x2-x1, y2-y1
                if dx*dx + dy*dy < 1e-9: return math.sqrt((px-x1)**2 + (py-y1)**2)
                t = ((px-x1)*dx + (py-y1)*dy) / (dx*dx + dy*dy)
                t = max(0, min(1, t))
                return math.sqrt((px-(x1+t*dx))**2 + (py-(y1+t*dy))**2)

            # Center/Uniform
            if abs(wx - center[0]) < hit_sz and abs(wy - center[1]) < hit_sz:
                if self._transform_mode in ("move", "scale"): return "XY" if self._transform_mode=="move" else "Uniform"

            if self._transform_mode == "move":
                # Check X axis
                if dist_to_segment(wx, wy, center[0], center[1], center[0]+sz, center[1]) < hit_sz: return "X"
                # Check Y axis
                if dist_to_segment(wx, wy, center[0], center[1], center[0], center[1]+sz) < hit_sz: return "Y"

            elif self._transform_mode == "rotate":
                r = sz * 0.85
                dist_to_center = math.sqrt((wx - center[0])**2 + (wy - center[1])**2)
                if abs(dist_to_center - r) < hit_sz: return "Rotate"

            elif self._transform_mode == "scale":
                for part, cp in [("X", (center[0]+sz, center[1])), ("Y", (center[0], center[1]+sz))]:
                    if abs(wx - cp[0]) < hit_sz and abs(wy - cp[1]) < hit_sz: return part

            return None

        def _get_selection_center(self) -> Tuple[float, float, float]:
            sel = [o for o in self.scene_objects if o.selected]
            if not sel: return (0, 0, 0)
            avg = [0.0, 0.0, 0.0]
            for o in sel:
                for i in range(3): avg[i] += o.position[i]
            return (avg[0]/len(sel), avg[1]/len(sel), avg[2]/len(sel))

        def _get_selection_bounds(self) -> Tuple[Tuple[float, float, float], float]:
            """Returns (center, radius) of the selection bounding sphere."""
            sel = [o for o in self.scene_objects if o.selected]
            if not sel: return (0, 0, 0), 1.0
            center = self._get_selection_center()
            max_r = 1.0
            for o in sel:
                d = _length(_sub(o.position, center))
                # rough sphere radius from scale
                r = _length(o.scale) * 0.5
                max_r = max(max_r, d + r)
            return center, max_r

        def _focus_selected(self):
            sel = [o for o in self.scene_objects if o.selected]
            if not sel: return
            
            center, radius = self._get_selection_bounds()
            
            if self._mode == "3D":
                # Position camera back from center along current front vector
                f = self._cam3d.front
                # Perspective framing: distance = radius / sin(fov/2)
                # We use radius * 2.5 as a comfortable heuristic
                dist = radius * 2.5
                self._cam3d.pos = list(_sub(center, _scale_vec(f, dist)))
            else:
                self._cam2d.x, self._cam2d.y = center[0], center[1]
                # Adjust zoom to fit radius + margin
                self._cam2d.zoom_level = radius * 1.5
            
            self.update()

        def mousePressEvent(self, event: QMouseEvent):
            if getattr(self, 'is_play_mode', False): return
            btn = event.button()
            mx, my = event.pos().x(), event.pos().y()
            if btn == Qt.MouseButton.LeftButton:
                self._lmb = True
                mod = event.modifiers()
                is_multi = bool(mod & Qt.KeyboardModifier.ControlModifier or mod & Qt.KeyboardModifier.ShiftModifier)

                # Check gizmo first
                if self._mode == "3D": self._active_gizmo_part = self._pick_gizmo_3d(mx, my)
                else: self._active_gizmo_part = self._pick_gizmo_2d(mx, my)

                if self._active_gizmo_part:
                    self.state_about_to_change.emit() # Push undo before drag starts
                    sel = [o for o in self.scene_objects if o.selected]
                    if not sel: return
                    center = self._get_selection_center()
                    self._drag_object = sel[-1]
                    self._drag_start_pos = list(center)
                    self._drag_obj_initial_rot = list(self._drag_object.rotation)
                    self._drag_obj_initial_scale = list(self._drag_object.scale)
                    
                    self._drag_all_starts = {}
                    self._drag_all_rots = {}
                    self._drag_all_scales = {}
                    for o in sel:
                        self._drag_all_starts[o.id] = list(o.position)
                        self._drag_all_rots[o.id] = list(o.rotation)
                        self._drag_all_scales[o.id] = list(o.scale)
                        # Include descendants in drag so they follow parents
                        for desc in self._get_all_descendants(o.id):
                            self._drag_all_starts[desc.id] = list(desc.position)
                            self._drag_all_rots[desc.id] = list(desc.rotation)
                            self._drag_all_scales[desc.id] = list(desc.scale)
                    
                    if self._mode == "3D": self._init_drag_3d(mx, my)
                    else: self._init_drag_2d(mx, my)
                    return

                if self._mode == "3D": picked = self._pick_object_3d(mx, my)
                elif self._mode == "2D": picked = self._pick_object_2d(mx, my)
                else: picked = None
                
                if picked:
                    if is_multi: 
                        self.state_about_to_change.emit()
                        picked.selected = not picked.selected
                    else:
                        if not picked.selected: self.state_about_to_change.emit()
                        for o in self.scene_objects: o.selected = False
                        picked.selected = True

                    if picked.selected:
                        self._drag_object = picked
                        self._drag_start_pos = list(picked.position)
                        # Save starts for all selected to prevent flying away during multi-drag
                        sel = [o for o in self.scene_objects if o.selected]
                        self._drag_all_starts = {}
                        self._drag_all_rots = {}
                        self._drag_all_scales = {}
                        for o in sel:
                            self._drag_all_starts[o.id] = list(o.position)
                            self._drag_all_rots[o.id] = list(o.rotation)
                            self._drag_all_scales[o.id] = list(o.scale)
                            for desc in self._get_all_descendants(o.id):
                                self._drag_all_starts[desc.id] = list(desc.position)
                                self._drag_all_rots[desc.id] = list(desc.rotation)
                                self._drag_all_scales[desc.id] = list(desc.scale)
                        
                        if self._mode == "3D":
                            self._drag_world_start = self._cam3d.ray_plane_intersect(mx, my, self.width(), self.height(), tuple(picked.position), (0, 1, 0))
                        elif self._mode == "2D":
                            wx, wy = self._cam2d.screen_to_world(mx, my, self.width(), self.height())
                            self._drag_world_start = (wx, wy)
                    self.object_selected.emit(picked)
                else:
                    if not is_multi:
                        for o in self.scene_objects: o.selected = False
                    self._drag_object = None; self._drag_world_start = None
                    self._drag_action = "box_select"
                    self._select_start = (mx, my)
                    self._select_current = (mx, my)
                    self.object_selected.emit(None)
                self.update()
            elif btn == Qt.MouseButton.RightButton:
                self._rmb = True; self.setCursor(Qt.CursorShape.BlankCursor)
            elif btn == Qt.MouseButton.MiddleButton:
                self._mmb = True; self.setCursor(Qt.CursorShape.ClosedHandCursor)
            self._last_mouse = event.pos()
            event.accept()

        def _init_drag_3d(self, mx, my):
            center = self._get_selection_center()
            if self._transform_mode == "move":
                normal = (0,1,0)
                if self._transform_space == "Local":
                    obj = [o for o in self.scene_objects if o.selected][-1]
                    rot_mat = _euler_to_matrix(*obj.rotation)
                    if self._active_gizmo_part == "X": normal = tuple(rot_mat[1]) # Use Local Y as normal
                    elif self._active_gizmo_part == "Y": normal = tuple(rot_mat[0]) # Use Local X as normal
                    elif self._active_gizmo_part == "Z": normal = tuple(rot_mat[1]) # Use Local Y as normal
                else:
                    if self._active_gizmo_part in ("X","Z","XZ"): normal = (0,1,0)
                    elif self._active_gizmo_part == "YZ": normal = (1,0,0)
                    else: normal = (0,0,1)
                
                self._drag_world_start = self._cam3d.ray_plane_intersect(mx, my, self.width(), self.height(), tuple(center), normal)
            elif self._transform_mode == "rotate":
                self._drag_start_mouse = (mx, my)
                sz = self._get_gizmo_size_3d(center)
                # Compute screen-space tangent of the selected ring
                # Project two points along the ring tangent to screen
                c = tuple(center)
                axis_vec = {"X":(1,0,0), "Y":(0,1,0), "Z":(0,0,1)}.get(self._active_gizmo_part)
                if self._transform_space == "Local":
                    obj = [o for o in self.scene_objects if o.selected][-1]
                    rot_mat = _euler_to_matrix(*obj.rotation)
                    # Transform axis_vec by rot_mat
                    av = axis_vec
                    axis_vec = (
                        rot_mat[0][0]*av[0] + rot_mat[0][1]*av[1] + rot_mat[0][2]*av[2],
                        rot_mat[1][0]*av[0] + rot_mat[1][1]*av[1] + rot_mat[1][2]*av[2],
                        rot_mat[2][0]*av[0] + rot_mat[2][1]*av[1] + rot_mat[2][2]*av[2]
                    )

                
                # Find a point on the ring near the mouse
                wp = self._cam3d.ray_plane_intersect(mx, my, self.width(), self.height(), c, axis_vec)
                if wp:
                    rad_v = _sub(wp, c)
                    tan_v = _normalize((axis_vec[1]*rad_v[2] - axis_vec[2]*rad_v[1],
                                      axis_vec[2]*rad_v[0] - axis_vec[0]*rad_v[2],
                                      axis_vec[0]*rad_v[1] - axis_vec[1]*rad_v[0]))
                    p1 = self._cam3d.world_to_screen(wp, self.width(), self.height())
                    p2 = self._cam3d.world_to_screen(_add(wp, _scale_vec(tan_v, 0.1)), self.width(), self.height())
                    if p1 and p2:
                        self._drag_tangent = _normalize_2d((p2[0]-p1[0], p2[1]-p1[1]))
                    else:
                        self._drag_tangent = (1, 0)
                else:
                    self._drag_tangent = (1, 0)
            elif self._transform_mode == "scale":
                f = self._cam3d.front; normal = _normalize((f[0], 0, f[2]))
                self._drag_world_start = self._cam3d.ray_plane_intersect(mx, my, self.width(), self.height(), tuple(center), normal)
                if self._drag_world_start:
                    self._drag_initial_dist = _length(_sub(self._drag_world_start, tuple(center)))

        def _init_drag_2d(self, mx, my):
            center = self._get_selection_center()
            wx, wy = self._cam2d.screen_to_world(mx, my, self.width(), self.height())
            self._drag_world_start = (wx, wy)
            self._drag_initial_dist = math.sqrt((wx - center[0])**2 + (wy - center[1])**2)

        def mouseReleaseEvent(self, event: QMouseEvent):
            btn = event.button()
            if btn == Qt.MouseButton.LeftButton:
                if getattr(self, '_drag_action', None) == "box_select":
                    x1, y1 = self._select_start
                    x2, y2 = self._select_current
                    min_x, max_x = min(x1, x2), max(x1, x2)
                    min_y, max_y = min(y1, y2), max(y1, y2)
                    
                    mod = event.modifiers()
                    is_multi = bool(mod & Qt.KeyboardModifier.ControlModifier or mod & Qt.KeyboardModifier.ShiftModifier)
                    if not is_multi:
                        for o in self.scene_objects: o.selected = False
                        
                    for obj in self.scene_objects:
                        sx, sy = 0, 0
                        if self._mode == "3D": p = self._cam3d.world_to_screen(obj.position, self.width(), self.height())
                        else: p = self._cam2d.world_to_screen(obj.position, self.width(), self.height())
                        if p:
                            sx, sy = p
                            if min_x <= sx <= max_x and min_y <= sy <= max_y:
                                obj.selected = True
                                
                    sel = [o for o in self.scene_objects if o.selected]
                    self.object_selected.emit(sel[-1] if sel else None)
                    self._drag_action = None
                    self.update()
                elif self._lmb and self._drag_object:
                    self.object_moved.emit()
                    self.state_changed.emit()
                self._lmb = False; self._drag_object = None; self._drag_world_start = None
                self._active_gizmo_part = None
            elif btn == Qt.MouseButton.RightButton:
                if self._rmb:
                    # If it was a short click, could show menu, but we use contextMenuEvent
                    pass
                self._rmb = False; self.setCursor(Qt.CursorShape.ArrowCursor)
            elif btn == Qt.MouseButton.MiddleButton:
                self._mmb = False; self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()

        def mouseMoveEvent(self, event: QMouseEvent):
            if getattr(self, 'is_play_mode', False): return
            mx, my = event.pos().x(), event.pos().y()
            if getattr(self, '_drag_action', None) == "box_select" and self._lmb:
                self._select_current = (mx, my)
                self.update()
                return

            if self._last_mouse is None:
                self._last_mouse = event.pos(); return
            dx = mx - self._last_mouse.x()
            dy = my - self._last_mouse.y()
            self._last_mouse = event.pos()

            if self._mode == "3D":
                if self._rmb:
                    self._cam3d.rotate(dx, dy)
                elif self._mmb:
                    r, u = self._cam3d.right, self._cam3d.up
                    spd = self._cam3d.speed * 0.01
                    self._cam3d.pos[0] -= (r[0]*dx + u[0]*dy)*spd
                    self._cam3d.pos[1] -= (r[1]*dx + u[1]*dy)*spd
                    self._cam3d.pos[2] -= (r[2]*dx + u[2]*dy)*spd
                elif self._lmb and self._drag_object and self._transform_mode == "move":
                    sel_objs = [o for o in self.scene_objects if o.selected]
                    primary = sel_objs[-1] if sel_objs else self._drag_object
                    
                    # Determine plane for intersection based on active part
                    # Plane normal MUST NOT be parallel to the movement axis
                    normal = (0,1,0) 
                    if self._transform_space == "Local":
                        rot_mat = _euler_to_matrix(*primary.rotation)
                        if self._active_gizmo_part == "X": normal = tuple(rot_mat[1]) # Normal = Local Y
                        elif self._active_gizmo_part == "Y": normal = tuple(rot_mat[0]) # Normal = Local X
                        elif self._active_gizmo_part == "Z": normal = tuple(rot_mat[1]) # Normal = Local Y
                        elif self._active_gizmo_part == "XY": normal = tuple(rot_mat[2]) # Normal = Local Z
                        elif self._active_gizmo_part == "XZ": normal = tuple(rot_mat[1]) # Normal = Local Y
                        elif self._active_gizmo_part == "YZ": normal = tuple(rot_mat[0]) # Normal = Local X
                    else:
                        if self._active_gizmo_part == "X": normal = (0,1,0) # Moving X? Use Y-normal plane (stable)
                        elif self._active_gizmo_part == "Y": 
                            # If moving vertical Y, use a plane facing the camera horizontally
                            f = self._cam3d.front; normal = _normalize((f[0], 0, f[2]))
                        elif self._active_gizmo_part == "Z": normal = (0,1,0) # Moving Z? Use Y-normal plane (stable)
                    # 1. Determine best projection plane
                    # Use a plane that is stable relative to the camera and the movement direction
                    normal = (0, 1, 0) # Default ground plane
                    if self._active_gizmo_part == "XY": normal = (0, 0, 1)
                    elif self._active_gizmo_part == "XZ": normal = (0, 1, 0)
                    elif self._active_gizmo_part == "YZ": normal = (1, 0, 0)
                    elif self._active_gizmo_part in ("X", "Y", "Z"):
                        # Pick a plane containing the axis but most facing the camera
                        f = self._cam3d.front
                        if self._active_gizmo_part == "X": normal = (0, 1, 0) if abs(f[1]) < abs(f[2]) else (0, 0, 1)
                        elif self._active_gizmo_part == "Y": normal = (1, 0, 0) if abs(f[0]) < abs(f[2]) else (0, 0, 1)
                        else: normal = (0, 1, 0) if abs(f[1]) < abs(f[0]) else (1, 0, 0)
                    else:
                        # Free move: camera parallel
                        normal = _scale_vec(self._cam3d.front, -1.0)
                    
                    wp = self._cam3d.ray_plane_intersect(mx, my, self.width(), self.height(), tuple(self._drag_start_pos), normal)
                    if wp and getattr(self, '_drag_world_start', None):
                        world_delta = _sub(wp, self._drag_world_start)
                        sel_list = sel_objs
                        # primary already defined above
                        
                        # Project offset onto axis
                        local_axes = [(1,0,0), (0,1,0), (0,0,1)]
                        if self._transform_space == "Local":
                            rot_mat = _euler_to_matrix(*primary.rotation)
                            local_axes = [
                                (rot_mat[0][0], rot_mat[1][0], rot_mat[2][0]),
                                (rot_mat[0][1], rot_mat[1][1], rot_mat[2][1]),
                                (rot_mat[0][2], rot_mat[1][2], rot_mat[2][2])
                            ]

                        for obj_id, start_pos in self._drag_all_starts.items():
                            obj = next((o for o in self.scene_objects if o.id == obj_id), None)
                            if not obj: continue
                            
                            final_offset = [0,0,0]
                            for i, axis_name in enumerate(["X", "Y", "Z"]):
                                if self._active_gizmo_part == axis_name:
                                    dist = _dot(world_delta, local_axes[i])
                                    final_offset = _scale_vec(local_axes[i], dist)
                            
                            if self._active_gizmo_part == "XY":
                                d1 = _dot(world_delta, local_axes[0])
                                d2 = _dot(world_delta, local_axes[1])
                                final_offset = _add(_scale_vec(local_axes[0], d1), _scale_vec(local_axes[1], d2))
                            elif self._active_gizmo_part == "XZ":
                                d1 = _dot(world_delta, local_axes[0])
                                d3 = _dot(world_delta, local_axes[2])
                                final_offset = _add(_scale_vec(local_axes[0], d1), _scale_vec(local_axes[2], d3))
                            elif self._active_gizmo_part == "YZ":
                                d2 = _dot(world_delta, local_axes[1])
                                d3 = _dot(world_delta, local_axes[2])
                                final_offset = _add(_scale_vec(local_axes[1], d2), _scale_vec(local_axes[2], d3))
                            if not self._active_gizmo_part:
                                # Free move uses full offset from the stable intersection plane
                                final_offset = world_delta
                            else:
                                for i, axis_name in enumerate(["X", "Y", "Z"]):
                                    if self._active_gizmo_part == axis_name:
                                        dist = _dot(world_delta, local_axes[i])
                                        final_offset = _scale_vec(local_axes[i], dist)
                                
                                if self._active_gizmo_part == "XY":
                                    d1 = _dot(world_delta, local_axes[0]); d2 = _dot(world_delta, local_axes[1])
                                    final_offset = _add(_scale_vec(local_axes[0], d1), _scale_vec(local_axes[1], d2))
                                elif self._active_gizmo_part == "XZ":
                                    d1 = _dot(world_delta, local_axes[0]); d3 = _dot(world_delta, local_axes[2])
                                    final_offset = _add(_scale_vec(local_axes[0], d1), _scale_vec(local_axes[2], d3))
                                elif self._active_gizmo_part == "YZ":
                                    d2 = _dot(world_delta, local_axes[1]); d3 = _dot(world_delta, local_axes[2])
                                    final_offset = _add(_scale_vec(local_axes[1], d2), _scale_vec(local_axes[2], d3))
                            
                            new_pos = list(_add(start_pos, final_offset))
                            if self.snap_enabled:
                                for i in range(3): new_pos[i] = round(new_pos[i] / self.grid_size) * self.grid_size
                            obj.position[:] = new_pos
                        self.object_moved.emit()
                
                elif self._lmb and self._drag_object and self._transform_mode == "rotate":
                    if self._active_gizmo_part and hasattr(self, "_drag_tangent"):
                        idx = {"X":0, "Y":1, "Z":2}.get(self._active_gizmo_part)
                        
                        # Project mouse movement onto the screen-space tangent
                        m_dx = event.pos().x() - self._drag_start_mouse[0]
                        m_dy = event.pos().y() - self._drag_start_mouse[1]
                        
                        dist_along_tangent = m_dx * self._drag_tangent[0] + m_dy * self._drag_tangent[1]
                        # 0.5 degrees per pixel
                        angle_delta = dist_along_tangent * 0.5
                        if self.snap_enabled: angle_delta = round(angle_delta / 15.0) * 15.0
                        
                        # Apply Transformation Space Logic
                        axis_vec = {"X":(1,0,0), "Y":(0,1,0), "Z":(0,0,1)}.get(self._active_gizmo_part)
                        delta_mat = _axis_angle_to_matrix(axis_vec, angle_delta)
                        
                        pivot = tuple(self._drag_start_pos)
                        
                        for obj_id, start_pos in self._drag_all_starts.items():
                            obj = next((o for o in self.scene_objects if o.id == obj_id), None)
                            if not obj: continue
                            
                            # Orbit position around pivot
                            obj.position[:] = _rotate_point_around_pivot(tuple(start_pos), pivot, delta_mat)
                            
                            # Update orientation based on INTIAL rotation
                            initial_rot = self._drag_all_rots.get(obj.id, obj.rotation)
                            start_mat = _euler_to_matrix(*initial_rot)
                            
                            if self._transform_space == "Local":
                                new_mat = _mat_mul_3x3(start_mat, delta_mat)
                            else:
                                new_mat = _mat_mul_3x3(delta_mat, start_mat)
                            obj.rotation[:] = _matrix_to_euler(new_mat)
                        
                        self.object_moved.emit()
                    else:
                        # Fallback simple rotation (Y-axis only)
                        delta_rad = math.radians(dx * 0.5)
                        delta_mat = _axis_angle_to_matrix((0,1,0), dx * 0.5)
                        pivot = tuple(self._drag_start_pos)
                        for obj_id, start_pos in self._drag_all_starts.items():
                            obj = next((o for o in self.scene_objects if o.id == obj_id), None)
                            if not obj or obj.id not in self._drag_all_rots: continue
                            
                            obj.position[:] = _rotate_point_around_pivot(tuple(start_pos), pivot, delta_mat)
                            initial_rot = self._drag_all_rots[obj.id]
                            obj.rotation[1] = initial_rot[1] + dx * 0.5
                        self.object_moved.emit()
                        
                elif self._lmb and self._drag_object and self._transform_mode == "scale":
                    # Use world-distance ratio for scaling
                    f = self._cam3d.front; normal = _normalize((f[0], 0, f[2]))
                    center = tuple(self._drag_start_pos)
                    wp = self._cam3d.ray_plane_intersect(mx, my, self.width(), self.height(), center, normal)
                    if wp and hasattr(self, "_drag_initial_dist") and self._drag_initial_dist > 0.01:
                        v = _sub(wp, center)
                        ratio = _length(v) / self._drag_initial_dist
                        
                        pivot = center
                        
                        # Determine the active axis vector for the scale operation
                        active_axis_vec = None
                        if self._active_gizmo_part in ("X", "Y", "Z"):
                            idx = {"X":0, "Y":1, "Z":2}.get(self._active_gizmo_part)
                            if self._transform_space == "Local":
                                primary = [o for o in self.scene_objects if o.selected][-1]
                                M = _euler_to_matrix(*primary.rotation)
                                # Extract column 'idx' from matrix (local axis in world space)
                                active_axis_vec = (M[0][idx], M[1][idx], M[2][idx])
                            else:
                                active_axis_vec = [(1,0,0), (0,1,0), (0,0,1)][idx]

                        for obj_id, start_pos in self._drag_all_starts.items():
                            obj = next((o for o in self.scene_objects if o.id == obj_id), None)
                            if not obj or obj.id not in self._drag_all_scales: continue
                            
                            # Scale position from pivot
                            p_rel = _sub(tuple(start_pos), pivot)
                            if active_axis_vec:
                                # Scale only along the active axis
                                comp = _dot(p_rel, active_axis_vec)
                                offset = _scale_vec(active_axis_vec, comp * (ratio - 1.0))
                                obj.position[:] = _add(tuple(start_pos), offset)
                            else:
                                # Uniform scale
                                obj.position[:] = _add(pivot, _scale_vec(p_rel, ratio))
                            
                            # Scale size based on initial scales
                            initial_scale = self._drag_all_scales[obj.id]
                            if self._active_gizmo_part in ("X","Y","Z"):
                                idx = {"X":0, "Y":1, "Z":2}.get(self._active_gizmo_part)
                                obj.scale[idx] = max(0.01, initial_scale[idx] * ratio)
                            else:
                                for i in range(3):
                                    obj.scale[i] = max(0.01, initial_scale[i] * ratio)
                        self.object_moved.emit()
                    else:
                        # Fallback for scale if plane intersection fails
                        factor = 1.0 + dx * 0.02
                        pivot = tuple(self._drag_start_pos)
                        for obj_id, start_pos in self._drag_all_starts.items():
                            obj = next((o for o in self.scene_objects if o.id == obj_id), None)
                            if obj:
                                p_rel = _sub(tuple(start_pos), pivot)
                                obj.position[:] = _add(pivot, _scale_vec(p_rel, factor))
                                for i in range(3): obj.scale[i] *= factor
                        self.object_moved.emit()

                elif not self._lmb and self._mode == "3D":
                    # Update hover
                    self._hover_gizmo_part = self._pick_gizmo_3d(mx, my)
            elif self._mode == "2D":
                if self._mmb or self._rmb:
                    self._cam2d.pan(dx, dy, self.width(), self.height())
                elif self._lmb and self._drag_object:
                    wx, wy = self._cam2d.screen_to_world(mx, my, self.width(), self.height())
                    
                    if self._transform_mode == "move":
                        if self._drag_world_start:
                            ox, oy = wx - self._drag_world_start[0], wy - self._drag_world_start[1]
                            
                            to_move = list(self._drag_all_starts.items())
                            for obj_id, start_pos in to_move:
                                obj = next((o for o in self.scene_objects if o.id == obj_id), None)
                                if not obj: continue
                                
                                oox, ooy = ox, oy
                                if self._active_gizmo_part in ("X", "Y") and self._transform_space == "Local":
                                    # For multi-selection local move in 2D, we project onto the parent's local axes
                                    # which we already calculated as ox, oy.
                                    pass
                                
                                new_pos = [start_pos[0] + oox, start_pos[1] + ooy, start_pos[2]]
                                if self.snap_enabled:
                                    new_pos[0] = round(new_pos[0] / self.grid_size) * self.grid_size
                                    new_pos[1] = round(new_pos[1] / self.grid_size) * self.grid_size
                                obj.position[0] = new_pos[0]
                                obj.position[1] = new_pos[1]
                            self.object_moved.emit()
                            
                    elif self._transform_mode == "rotate":
                        cur_ang = math.atan2(wy - self._drag_object.position[1], wx - self._drag_object.position[0])
                        start_ang = math.atan2(self._drag_world_start[1] - self._drag_object.position[1], 
                                              self._drag_world_start[0] - self._drag_object.position[0])
                        diff = math.degrees(cur_ang - start_ang)
                        
                        pivot = (self._drag_object.position[0], self._drag_object.position[1])
                        angle_rad = math.radians(diff)
                        cos_a, sin_a = math.cos(angle_rad), math.sin(angle_rad)
                        
                        for obj_id, start_pos in self._drag_all_starts.items():
                            obj = next((o for o in self.scene_objects if o.id == obj_id), None)
                            if not obj or obj.id not in self._drag_all_rots: continue
                            
                            # Orbit in 2D
                            dx_rel, dy_rel = start_pos[0] - pivot[0], start_pos[1] - pivot[1]
                            rx = dx_rel * cos_a - dy_rel * sin_a
                            ry = dx_rel * sin_a + dy_rel * cos_a
                            obj.position[0] = pivot[0] + rx
                            obj.position[1] = pivot[1] + ry
                            obj.rotation[2] = self._drag_all_rots[obj.id][2] + diff
                        self.object_moved.emit()
                        
                    elif self._transform_mode == "scale":
                        if self._drag_initial_dist > 0.01:
                            dist = math.sqrt((wx - self._drag_object.position[0])**2 + (wy - self._drag_object.position[1])**2)
                            ratio = dist / self._drag_initial_dist
                            pivot = (self._drag_object.position[0], self._drag_object.position[1])
                            
                            for obj_id, start_pos in self._drag_all_starts.items():
                                obj = next((o for o in self.scene_objects if o.id == obj_id), None)
                                if not obj or obj.id not in self._drag_all_scales: continue
                                
                                # Pivot scale position
                                dx_rel, dy_rel = start_pos[0] - pivot[0], start_pos[1] - pivot[1]
                                obj.position[0] = pivot[0] + dx_rel * ratio
                                obj.position[1] = pivot[1] + dy_rel * ratio
                                
                                # Scale size from INITIAL
                                initial_scale = self._drag_all_scales[obj.id]
                                if self._active_gizmo_part == "X":
                                    obj.scale[0] = max(0.01, initial_scale[0] * ratio)
                                elif self._active_gizmo_part == "Y":
                                    obj.scale[1] = max(0.01, initial_scale[1] * ratio)
                                else:
                                    for i in range(2): obj.scale[i] = max(0.01, initial_scale[i] * ratio)
                        self.object_moved.emit()
                    self.object_moved.emit()
                else:
                    self._hover_gizmo_part = self._pick_gizmo_2d(event.pos().x(), event.pos().y())
            self.update()
            event.accept()
            event.accept()

        def wheelEvent(self, event: QWheelEvent):
            if getattr(self, 'is_play_mode', False):
                return
            delta = event.angleDelta().y()
            if self._mode == "3D":
                f = self._cam3d.front; spd = self._cam3d.speed * 0.3
                d = 1 if delta > 0 else -1
                for i in range(3): self._cam3d.pos[i] += f[i]*spd*d
                new_zoom = max(0.1, min(10.0, self._cam2d.zoom_level - delta * 0.001))
                self._cam2d.zoom_level = new_zoom
            else:
                new_zoom = max(0.1, min(10.0, self._cam2d.zoom_level - delta * 0.001))
                self._cam2d.zoom_level = new_zoom
            self.update()
            event.accept()

        def keyPressEvent(self, event: QKeyEvent):
            if getattr(self, 'is_play_mode', False): return
            key = event.key()
            self._keys.add(key)
            
            # F for Focus
            if key == Qt.Key.Key_F:
                self._focus_selected()
                event.accept()
                return

            if key == Qt.Key.Key_Delete or key == Qt.Key.Key_Backspace:
                sel = [o for o in self.scene_objects if o.selected]
                if sel:
                    # Save state for undo
                    parent = self.parent()
                    while parent and not hasattr(parent, '_save_state'): parent = parent.parent()
                    if parent: parent._save_state()
                    
                    for o in sel:
                        self.scene_objects.remove(o)
                    self.state_changed.emit()
                    self.update()
                event.accept()
                return

            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                if event.key() == Qt.Key.Key_D:
                    self._duplicate_selected()
                elif event.key() == Qt.Key.Key_C:
                    self._copy_selected()
                elif event.key() == Qt.Key.Key_V:
                    self._paste_selected()
                elif event.key() == Qt.Key.Key_A:
                    # Select All
                    for o in self.scene_objects: o.selected = True
                    self.update()
                    self.object_selected.emit(self.scene_objects[-1] if self.scene_objects else None)
                    
            event.accept()

        def keyReleaseEvent(self, event: QKeyEvent):
            self._keys.discard(event.key())
            if event.key() == Qt.Key.Key_Shift: self._cam3d.speed = 10.0
            event.accept()

        def _duplicate_selected(self):
            # Save state for undo
            parent = self.parent()
            while parent and not hasattr(parent, '_save_state'): parent = parent.parent()
            if parent: parent._save_state()

            sel = [o for o in self.scene_objects if o.selected]
            if not sel: return
            
            new_objs = []
            for obj in sel:
                new_obj = SceneObject(obj.name + "_copy", obj.obj_type, [v+1.0 for v in obj.position], list(obj.rotation), list(obj.scale))
                new_obj.color = list(obj.color)
                new_obj.file_path = obj.file_path
                new_obj.selected = True
                obj.selected = False
                new_objs.append(new_obj)
            
            self.scene_objects.extend(new_objs)
            self.state_changed.emit()
            self.update()
            self.object_selected.emit(new_objs[-1])
                
        def _copy_selected(self):
            self._clipboard = []
            for obj in self.scene_objects:
                if obj.selected:
                    d = obj.to_dict()
                    d['id'] = str(uuid.uuid4())[:8]
                    self._clipboard.append(d)

        def _paste_selected(self):
            if not getattr(self, '_clipboard', None): return
            new_objs = []
            for o in self.scene_objects: o.selected = False
            for d in self._clipboard:
                new_obj = SceneObject.from_dict(d)
                new_obj.position[0] += self.grid_size
                new_obj.position[2] += self.grid_size
                new_obj.name += "_copy"
                new_obj.id = str(uuid.uuid4())[:8]
                new_obj.selected = True
                new_objs.append(new_obj)
            if new_objs:
                self.scene_objects.extend(new_objs)
                self.object_selected.emit(new_objs[-1])
                self.state_changed.emit()
                self.update()

        def focusOutEvent(self, event):
            self._keys.clear(); self._rmb = False; self._mmb = False; self._lmb = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
            super().focusOutEvent(event)

        def contextMenuEvent(self, event):
            if getattr(self, "is_play_mode", False):
                return
            mx, my = event.pos().x(), event.pos().y()

            picked = self._pick_object_3d(mx, my) if self._mode == "3D" else self._pick_object_2d(mx, my)
            
            if picked:
                # Select the object if not already selected
                if not picked.selected:
                    for o in self.scene_objects: o.selected = False
                    picked.selected = True
                    self.object_selected.emit(picked)
                
                menu = QMenu(self)
                menu.setStyleSheet("""
                    QMenu { background: #2a2a2a; color: #e0e0e0; border: 1px solid #555; }
                    QMenu::item { padding: 6px 20px; }
                    QMenu::item:selected { background: #4fc3f7; color: #1a1a1a; }
                """)
                del_act = menu.addAction("Delete Object")
                dup_act = menu.addAction("Duplicate")
                ren_act = menu.addAction("Rename")
                action = menu.exec(event.globalPos())
                
                if action == del_act:
                    # Notify parent to delete
                    # We can directly modify it here and update outliner via signal if needed
                    # but easiest is to use the standard path
                    obj_id = picked.id
                    parent = self.parentWidget()
                    while parent and not hasattr(parent, '_on_outliner_action'):
                        parent = parent.parentWidget()
                    if parent:
                        parent._on_outliner_action(f"delete:{obj_id}")
                elif action == dup_act:
                    obj_id = picked.id
                    parent = self.parentWidget()
                    while parent and not hasattr(parent, '_on_outliner_action'):
                        parent = parent.parentWidget()
                    if parent:
                        parent._on_outliner_action(f"duplicate:{obj_id}")
                elif action == ren_act:
                    obj_id = picked.id
                    parent = self.parentWidget()
                    while parent and not hasattr(parent, '_on_outliner_action'):
                        parent = parent.parentWidget()
                    if parent:
                        parent._on_outliner_action(f"rename:{obj_id}")
            else:
                # Background context menu? (Add primitives at cursor?)
                pass

        # ---- Drag and drop from explorer ----
        def dragEnterEvent(self, event):
            if event.mimeData().hasText(): event.acceptProposedAction()

        def dragMoveEvent(self, event):
            event.acceptProposedAction()

        def dropEvent(self, event):
            import json as _json
            obj_type = event.mimeData().text()
            mx, my = event.position().x(), event.position().y()

            # Handle material drops — apply to object under cursor
            if obj_type.startswith("mat:"):
                mat_path = obj_type[4:]
                picked = self._pick_object_3d(int(mx), int(my)) if self._mode == "3D" else self._pick_object_2d(int(mx), int(my))
                if picked:
                    try:
                        with open(mat_path, 'r') as f:
                            mat_data = _json.load(f)
                        mat_data['file'] = mat_path
                        picked.material = mat_data
                        self.state_changed.emit()
                        self.update()
                    except Exception as e:
                        import traceback
                        traceback.print_exc()
                        print(f"[LANDSCAPE ERROR] {e}")
                event.acceptProposedAction()
                return
            # Calculate world coords first
            wx, wz = 0.0, 0.0
            if self._mode == "3D":
                origin, direction = self._cam3d.screen_to_ray(int(mx), int(my), self.width(), self.height())
                if abs(direction[1]) > 1e-9:
                    t = -origin[1] / direction[1]
                    if t > 0:
                        wx = origin[0] + direction[0]*t; wz = origin[2] + direction[2]*t
            elif self._mode == "2D":
                wx, wz = self._cam2d.screen_to_world(int(mx), int(my), self.width(), self.height())

            # Handle logic drops
            if obj_type.startswith("file:") and obj_type.endswith(".logic"):
                file_path = obj_type[5:]
                self.object_dropped.emit(f"logic:{file_path}", wx, wz, int(mx), int(my))
                event.acceptProposedAction()
                return

            if self._mode == "3D":
                self.object_dropped.emit(obj_type, wx, wz, int(mx), int(my))
            elif self._mode == "2D":
                self.object_dropped.emit(obj_type, wx, wz, int(mx), int(my))
            event.acceptProposedAction()

else:
    class SceneViewport(QWidget):
        fps_updated = pyqtSignal(int)
        object_selected = pyqtSignal(object)
        object_dropped = pyqtSignal(str, float, float)
        object_moved = pyqtSignal()
        state_changed = pyqtSignal()
        def __init__(self, parent=None):
            super().__init__(parent)
            self._mode = "3D"; self.show_grid = True; self.snap_enabled = False
            self.grid_size = 1.0; self.scene_objects = []; self._transform_mode = "move"
            self._transform_space = "Global"
        def set_mode(self, m): self._mode = m; self.update()
        def start_render_loop(self): pass
        def stop_render_loop(self): pass
        def set_show_grid(self, v): self.show_grid = v
        def set_snap_enabled(self, v): self.snap_enabled = v
        def set_grid_size(self, v): self.grid_size = v
        def set_transform_mode(self, m): self._transform_mode = m
        def set_transform_space(self, s): self._transform_space = s
        def paintEvent(self, event):
            p = QPainter(self); p.fillRect(self.rect(), QColor("#1a1a1a"))
            p.setPen(QColor("#888")); p.setFont(QFont("Segoe UI",14))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                       "OpenGL not available.\npip install PyOpenGL"); p.end()


# ===================================================================
# Material Slot Widget
# ===================================================================# ===================================================================
# Landscape Multi-Data Dialogs
# ===================================================================

class NoiseLayerDialog(QDialog):
    def __init__(self, layer_data, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Noise Layer")
        self.setStyleSheet(PROPS_SS)
        self.data = layer_data
        layout = QVBoxLayout(self)
        form = QFormLayout()
        
        self.type = QComboBox(); self.type.addItems(["perlin", "simplex", "worley"]); self.type.setCurrentText(self.data.get('type', 'perlin')); self.type.setStyleSheet(COMBO_SS)
        self.amp = QDoubleSpinBox(); self.amp.setRange(0, 1000); self.amp.setValue(self.data.get('amp', 1.0)); self.amp.setStyleSheet(SPIN_SS)
        self.freq = QDoubleSpinBox(); self.freq.setRange(0, 1000); self.freq.setValue(self.data.get('freq', 1.0)); self.freq.setStyleSheet(SPIN_SS)
        self.octaves = QSpinBox(); self.octaves.setRange(1, 10); self.octaves.setValue(self.data.get('octaves', 1)); self.octaves.setStyleSheet(SPIN_SS)
        self.persist = QDoubleSpinBox(); self.persist.setRange(0, 1); self.persist.setValue(self.data.get('persistence', 0.5)); self.persist.setSingleStep(0.1); self.persist.setStyleSheet(SPIN_SS)
        self.lacun = QDoubleSpinBox(); self.lacun.setRange(1, 4); self.lacun.setValue(self.data.get('lacunarity', 2.0)); self.lacun.setSingleStep(0.1); self.lacun.setStyleSheet(SPIN_SS)
        self.mode = QComboBox(); self.mode.addItems(["fbm", "ridged", "billow"]); self.mode.setCurrentText(self.data.get('mode', 'fbm')); self.mode.setStyleSheet(COMBO_SS)
        self.exp = QDoubleSpinBox(); self.exp.setRange(0.1, 5.0); self.exp.setValue(self.data.get('exponent', 1.0)); self.exp.setSingleStep(0.1); self.exp.setStyleSheet(SPIN_SS)

        form.addRow("Mode", self.mode)
        form.addRow("Type", self.type)
        form.addRow("Amplitude", self.amp)
        form.addRow("Frequency", self.freq)
        form.addRow("Octaves", self.octaves)
        form.addRow("Persistence", self.persist)
        form.addRow("Lacunarity", self.lacun)
        form.addRow("Redistribution (Exp)", self.exp)
        layout.addLayout(form)
        
        btns = QHBoxLayout()
        ok = QPushButton("Apply"); ok.setStyleSheet(BTN_SS); ok.clicked.connect(self.accept)
        cancel = QPushButton("Cancel"); cancel.setStyleSheet(BTN_SS); cancel.clicked.connect(self.reject)
        btns.addWidget(ok); btns.addWidget(cancel)
        layout.addLayout(btns)

    def get_data(self):
        return {
            'type': self.type.currentText(),
            'mode': self.mode.currentText(),
            'amp': self.amp.value(),
            'freq': self.freq.value(),
            'octaves': self.octaves.value(),
            'persistence': self.persist.value(),
            'lacunarity': self.lacun.value(),
            'exponent': self.exp.value(),
            'offset': self.data.get('offset', [0.0, 0.0])
        }

class BiomeDialog(QDialog):
    def __init__(self, biome_data, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Biome Structure")
        self.setMinimumWidth(350); self.setStyleSheet(PROPS_SS)
        self.data = biome_data
        layout = QVBoxLayout(self)
        
        # --- Criteria ---
        crit = QGroupBox("Climate Criteria (Height, Slope, Temp, Hum)")
        cl = QFormLayout(crit)
        self.h_min = QDoubleSpinBox(); self.h_min.setRange(-10000, 10000); self.h_min.setValue(self.data.get('height_range', [0,0])[0]); self.h_min.setStyleSheet(SPIN_SS)
        self.h_max = QDoubleSpinBox(); self.h_max.setRange(-10000, 10000); self.h_max.setValue(self.data.get('height_range', [0,0])[1]); self.h_max.setStyleSheet(SPIN_SS)
        self.s_min = QDoubleSpinBox(); self.s_min.setRange(0, 1); self.s_min.setValue(self.data.get('slope_range', [0,0])[0]); self.s_min.setStyleSheet(SPIN_SS)
        self.s_max = QDoubleSpinBox(); self.s_max.setRange(0, 1); self.s_max.setValue(self.data.get('slope_range', [0,0])[1]); self.s_max.setStyleSheet(SPIN_SS)
        self.t_min = QDoubleSpinBox(); self.t_min.setRange(0, 1); self.t_min.setValue(self.data.get('temp_range', [0,1])[0]); self.t_min.setStyleSheet(SPIN_SS)
        self.t_max = QDoubleSpinBox(); self.t_max.setRange(0, 1); self.t_max.setValue(self.data.get('temp_range', [0,1])[1]); self.t_max.setStyleSheet(SPIN_SS)
        self.hm_min = QDoubleSpinBox(); self.hm_min.setRange(0, 1); self.hm_min.setValue(self.data.get('hum_range', [0,1])[0]); self.hm_min.setStyleSheet(SPIN_SS)
        self.hm_max = QDoubleSpinBox(); self.hm_max.setRange(0, 1); self.hm_max.setValue(self.data.get('hum_range', [0,1])[1]); self.hm_max.setStyleSheet(SPIN_SS)
        
        cl.addRow("Min Height", self.h_min); cl.addRow("Max Height", self.h_max)
        cl.addRow("Min Slope", self.s_min); cl.addRow("Max Slope", self.s_max)
        cl.addRow("Min Temp", self.t_min); cl.addRow("Max Temp", self.t_max)
        cl.addRow("Min Hum", self.hm_min); cl.addRow("Max Hum", self.hm_max)
        layout.addWidget(crit)
        
        # --- Surface Material ---
        surf = QGroupBox("Surface Appearance")
        sl = QFormLayout(surf)
        s_data = self.data.get('surface', {})
        self.color_btn = QPushButton()
        c = s_data.get('color', [0.5, 0.5, 0.5, 1.0])
        self.color_btn.setStyleSheet(f"background: rgb({int(c[0]*255)}, {int(c[1]*255)}, {int(c[2]*255)}); height: 20px; border-radius: 4px;")
        self.color_btn.clicked.connect(self._pick_color)
        self.curr_color = list(c)
        
        self.rough = QDoubleSpinBox(); self.rough.setRange(0, 1); self.rough.setValue(s_data.get('roughness', 0.7)); self.rough.setStyleSheet(SPIN_SS)
        self.metal = QDoubleSpinBox(); self.metal.setRange(0, 1); self.metal.setValue(s_data.get('metallic', 0.0)); self.metal.setStyleSheet(SPIN_SS)
        sl.addRow("Base Color", self.color_btn)
        sl.addRow("Roughness", self.rough)
        sl.addRow("Metallic", self.metal)
        layout.addWidget(surf)
        
        # --- Spawns ---
        spw = QGroupBox("Spawning Rules")
        spl = QVBoxLayout(spw)
        self.spawn_list = QListWidget()
        self.spawn_list.setFixedHeight(80); self.spawn_list.setStyleSheet(LIST_SS)
        for s in self.data.get('spawns', []):
            self.spawn_list.addItem(f"{Path(s['assets'][0]).name} (D:{s['density']})")
        spl.addWidget(self.spawn_list)
        s_btns = QHBoxLayout()
        add_s = QPushButton("Add Spawn"); add_s.setStyleSheet(BTN_SS); add_s.clicked.connect(self._add_spawn)
        rem_s = QPushButton("Remove"); rem_s.setStyleSheet(BTN_SS); rem_s.clicked.connect(self._rem_spawn)
        s_btns.addWidget(add_s); s_btns.addWidget(rem_s)
        spl.addLayout(s_btns)
        layout.addWidget(spw)
        
        btns = QHBoxLayout()
        ok = QPushButton("Save Structure"); ok.setStyleSheet(BTN_SS); ok.clicked.connect(self.accept)
        cancel = QPushButton("Cancel"); cancel.setStyleSheet(BTN_SS); cancel.clicked.connect(self.reject)
        btns.addWidget(ok); btns.addWidget(cancel)
        layout.addLayout(btns)

    def _pick_color(self):
        c = QColorDialog.getColor(QColor(int(self.curr_color[0]*255), int(self.curr_color[1]*255), int(self.curr_color[2]*255)))
        if c.isValid():
            self.curr_color = [c.red()/255.0, c.green()/255.0, c.blue()/255.0, 1.0]
            self.color_btn.setStyleSheet(f"background: rgb({c.red()}, {c.green()}, {c.blue()}); height: 20px; border-radius: 4px;")

    def _add_spawn(self):
        asset, ok = QInputDialog.getText(self, "Add Spawn", "Asset Path:")
        if ok and asset:
            density, ok2 = QInputDialog.getDouble(self, "Add Spawn", "Density:", 0.1, 0, 1, 2)
            if ok2:
                self.spawn_list.addItem(f"{Path(asset).name} (D:{density})")
                if 'spawns' not in self.data: self.data['spawns'] = []
                self.data['spawns'].append({'assets': [asset], 'density': density})

    def _rem_spawn(self):
        it = self.spawn_list.currentItem()
        if it:
            idx = self.spawn_list.row(it)
            self.spawn_list.takeItem(idx)
            if 'spawns' in self.data: self.data['spawns'].pop(idx)

    def get_data(self):
        return {
            'name': self.data.get('name', 'Biome'),
            'height_range': [self.h_min.value(), self.h_max.value()],
            'slope_range': [self.s_min.value(), self.s_max.value()],
            'temp_range': [self.t_min.value(), self.t_max.value()],
            'hum_range': [self.hm_min.value(), self.hm_max.value()],
            'surface': {
                'color': self.curr_color,
                'roughness': self.rough.value(),
                'metallic': self.metal.value(),
                'emissive': [0,0,0,1]
            },
            'spawns': self.data.get('spawns', [])
        }



class MaterialSlotWidget(QWidget):
    material_dropped = pyqtSignal(str) # filepath
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setMinimumHeight(32)
        self.setObjectName("MaterialSlot")
        self.setStyleSheet("""
            QWidget#MaterialSlot { 
                background: #1e1e1e; border: 1px dashed #555; border-radius: 4px; 
            }
            QWidget#MaterialSlot:hover { border-color: #4fc3f7; }
        """)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 8, 0)
        
        self.label = QLabel("None")
        self.label.setStyleSheet("border: none; background: transparent; color: #888; font-size: 11px;")
        layout.addWidget(self.label)
        
        layout.addStretch()
        
        self.btn = QPushButton("...")
        self.btn.setFixedSize(24, 20)
        self.btn.setStyleSheet("background: #333; border: 1px solid #555; border-radius: 2px; color: #ccc;")
        layout.addWidget(self.btn)
        
    def set_material(self, name):
        self.label.setText(name if name else "None")
        self.label.setStyleSheet(f"border: none; background: transparent; color: {'#4fc3f7' if name else '#888'}; font-size: 11px;")

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasText() and event.mimeData().text().startswith("mat:"):
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        text = event.mimeData().text()
        if text.startswith("mat:"):
            path = text[4:]
            self.material_dropped.emit(path)
            event.acceptProposedAction()


# ===================================================================
# Object Properties Panel
# ===================================================================

# ===================================================================
# Property Editor Helpers
# ===================================================================

class PropertySlider(QWidget):
    """A synchronized Slider + SpinBox for precise control."""
    valueChanged = pyqtSignal(float)

    def __init__(self, value=0.0, vmin=0.0, vmax=1.0, step=0.01, decimals=2, parent=None):
        super().__init__(parent)
        self._updating = False
        self.vmin, self.vmax = vmin, vmax
        self.decimals = decimals
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(6)
        
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 1000)
        self.slider.setStyleSheet("""
            QSlider::groove:horizontal { background: #333; height: 6px; border-radius: 3px; }
            QSlider::handle:horizontal { background: #4fc3f7; width: 14px; margin: -4px 0; border-radius: 7px; }
        """)
        
        self.spin = QDoubleSpinBox()
        self.spin.setRange(vmin, vmax); self.spin.setDecimals(decimals); self.spin.setSingleStep(step)
        self.spin.setFixedWidth(65); self.spin.setStyleSheet(SPIN_SS)
        
        layout.addWidget(self.slider, 1)
        layout.addWidget(self.spin)
        
        self.slider.valueChanged.connect(self._on_slider_changed)
        self.spin.valueChanged.connect(self._on_spin_changed)
        self.setValue(value)

    def setValue(self, val):
        if self._updating: return
        self._updating = True
        self.spin.setValue(val)
        s_val = int((val - self.vmin) / (self.vmax - self.vmin) * 1000) if self.vmax > self.vmin else 0
        self.slider.setValue(s_val)
        self._updating = False

    def value(self):
        return self.spin.value()

    def _on_slider_changed(self, ival):
        if self._updating: return
        self._updating = True
        val = self.vmin + (ival / 1000.0) * (self.vmax - self.vmin)
        self.spin.setValue(val)
        self.valueChanged.emit(val)
        self._updating = False

    def _on_spin_changed(self, fval):
        if self._updating: return
        self._updating = True
        s_val = int((fval - self.vmin) / (self.vmax - self.vmin) * 1000) if self.vmax > self.vmin else 0
        self.slider.setValue(s_val)
        self.valueChanged.emit(fval)
        self._updating = False

class ObjectPropertiesPanel(QWidget):
    """The Right-side properties inspector with a unified layout."""
    
    property_changed = pyqtSignal()   # emitted when user edits a value

    def _add_property_row(self, layout, label_text, widget, tooltip=None):
        """Helper to add a standard property row with consistent spacing."""
        row = QHBoxLayout()
        row.setSpacing(10)
        lbl = QLabel(label_text)
        lbl.setFixedWidth(90) # Fixed label width to prevent overlapping
        lbl.setStyleSheet("color: #aaa; font-size: 11px;")
        if tooltip: lbl.setToolTip(tooltip)
        row.addWidget(lbl)
        
        if isinstance(widget, QLayout):
            row.addLayout(widget, 1)
        else:
            row.addWidget(widget, 1)
            
        layout.addLayout(row)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: #252526;")
        self._current_object = None
        self._updating = False  # guard against feedback loops

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4,4,4,4)
        layout.setSpacing(4)

        # Title
        self._title = QLabel("  No Selection")
        self._title.setFixedHeight(24)
        self._title.setStyleSheet("color: #888; font-size: 11px; font-weight: bold;")
        layout.addWidget(self._title)

        # Position
        pos_group = QGroupBox("Position")
        pos_group.setStyleSheet(PROPS_SS)
        pg = QGridLayout(pos_group)
        pg.setContentsMargins(8,6,8,6); pg.setSpacing(4)
        self._pos_spins = []
        for i, axis in enumerate(["X", "Y", "Z"]):
            lbl = QLabel(axis)
            lbl.setStyleSheet(f"color: {['#e55', '#5e5', '#55e'][i]}; font-weight: bold; font-size: 11px;")
            pg.addWidget(lbl, 0, i*2)
            spin = QDoubleSpinBox()
            spin.setRange(-9999, 9999); spin.setDecimals(2); spin.setSingleStep(0.1)
            spin.setStyleSheet(SPIN_SS); spin.setFixedWidth(70)
            spin.valueChanged.connect(self._on_pos_changed)
            pg.addWidget(spin, 0, i*2+1)
            self._pos_spins.append(spin)
        layout.addWidget(pos_group)

        # Rotation
        rot_group = QGroupBox("Rotation")
        rot_group.setStyleSheet(PROPS_SS)
        rg = QGridLayout(rot_group)
        rg.setContentsMargins(8,6,8,6); rg.setSpacing(4)
        self._rot_spins = []
        for i, axis in enumerate(["X", "Y", "Z"]):
            lbl = QLabel(axis)
            lbl.setStyleSheet(f"color: {['#e55', '#5e5', '#55e'][i]}; font-weight: bold; font-size: 11px;")
            rg.addWidget(lbl, 0, i*2)
            spin = QDoubleSpinBox()
            spin.setRange(-360, 360); spin.setDecimals(1); spin.setSingleStep(1.0)
            spin.setStyleSheet(SPIN_SS); spin.setFixedWidth(70)
            spin.valueChanged.connect(self._on_rot_changed)
            rg.addWidget(spin, 0, i*2+1)
            self._rot_spins.append(spin)
        layout.addWidget(rot_group)

        # Scale
        scale_group = QGroupBox("Scale")
        scale_group.setStyleSheet(PROPS_SS)
        sg = QGridLayout(scale_group)
        sg.setContentsMargins(8,6,8,6); sg.setSpacing(4)
        self._scale_spins = []
        for i, axis in enumerate(["X", "Y", "Z"]):
            lbl = QLabel(axis)
            lbl.setStyleSheet(f"color: {['#e55', '#5e5', '#55e'][i]}; font-weight: bold; font-size: 11px;")
            sg.addWidget(lbl, 0, i*2)
            spin = QDoubleSpinBox()
            spin.setRange(0.01, 999); spin.setDecimals(2); spin.setSingleStep(0.1); spin.setValue(1.0)
            spin.setStyleSheet(SPIN_SS); spin.setFixedWidth(70)
            spin.valueChanged.connect(self._on_scale_changed)
            sg.addWidget(spin, 0, i*2+1)
            self._scale_spins.append(spin)
        layout.addWidget(scale_group)
        # Keep references to top-level content groups so we can hide them when nothing is selected
        self._content_widgets = [pos_group, rot_group, scale_group]

        # ---- Material Section ----
        mat_group = QGroupBox("Material")
        mat_group.setStyleSheet(PROPS_SS)
        mg = QVBoxLayout(mat_group)
        mg.setContentsMargins(10, 14, 10, 10); mg.setSpacing(6)

        # Preset dropdown
        self._mat_preset = QComboBox()
        self._mat_preset.addItems(['Plastic', 'Glass', 'Metal', 'Green Glow', 'Custom'])
        self._mat_preset.setStyleSheet(COMBO_SS)
        self._mat_preset.currentTextChanged.connect(self._on_mat_preset_changed)
        self._add_property_row(mg, "Preset", self._mat_preset)

        # Material Slot
        self._mat_slot = MaterialSlotWidget()
        self._mat_slot.material_dropped.connect(self._on_material_slot_dropped)
        self._mat_slot.btn.clicked.connect(self._on_mat_slot_btn_clicked)
        self._add_property_row(mg, "Asset", self._mat_slot)

        # Base Color
        cl_row = QHBoxLayout()
        self._base_color_btn = QPushButton()
        self._base_color_btn.setFixedSize(60, 20)
        self._base_color_btn.setStyleSheet("background: #ccc; border: 1px solid #555; border-radius: 3px;")
        self._base_color_btn.clicked.connect(self._pick_base_color)
        cl_row.addWidget(self._base_color_btn); cl_row.addStretch()
        self._add_property_row(mg, "Base Color", cl_row)

        # Roughness & Metallic
        self._roughness_slider = PropertySlider(0.7, 0.0, 1.0)
        self._roughness_slider.valueChanged.connect(self._on_roughness_changed)
        self._add_property_row(mg, "Roughness", self._roughness_slider)

        self._metallic_slider = PropertySlider(0.0, 0.0, 1.0)
        self._metallic_slider.valueChanged.connect(self._on_metallic_changed)
        self._add_property_row(mg, "Metallic", self._metallic_slider)

        # Emissive
        em_row = QHBoxLayout()
        self._emissive_btn = QPushButton()
        self._emissive_btn.setFixedSize(60, 20)
        self._emissive_btn.setStyleSheet("background: #000; border: 1px solid #555; border-radius: 3px;")
        self._emissive_btn.clicked.connect(self._pick_emissive_color)
        em_row.addWidget(self._emissive_btn); em_row.addStretch()
        self._add_property_row(mg, "Emissive", em_row)

        self._mat_file_label = QLabel("")
        self._mat_file_label.setStyleSheet("color: #666; font-size: 10px; font-style: italic;")
        mg.addWidget(self._mat_file_label)

        layout.addWidget(mat_group)
        # include material group in content widgets
        self._content_widgets.append(mat_group)

        # Landscape panel
        self.land_group = QGroupBox("Landscape")
        self.land_group.setStyleSheet(PROPS_SS)
        lg = QVBoxLayout(self.land_group)
        lg.setContentsMargins(8,6,8,6); lg.setSpacing(6)

        # Basic Settings
        base_grid = QGridLayout()
        base_grid.setSpacing(4)
        base_grid.addWidget(QLabel("Type"), 0, 0)
        self._land_type = QComboBox()
        self._land_type.addItems(["Flat", "Procedural"])
        self._land_type.setStyleSheet(COMBO_SS)
        self._land_type.currentTextChanged.connect(self._on_land_type_changed)
        base_grid.addWidget(self._land_type, 0, 1)

        base_grid.addWidget(QLabel("Size Mode"), 1, 0)
        self._land_size_mode = QComboBox()
        self._land_size_mode.addItems(["Finite", "Infinite"])
        self._land_size_mode.setStyleSheet(COMBO_SS)
        self._land_size_mode.currentTextChanged.connect(self._on_land_size_mode_changed)
        base_grid.addWidget(self._land_size_mode, 1, 1)

        base_grid.addWidget(QLabel("Seed"), 2, 0)
        self._land_seed = QSpinBox()
        self._land_seed.setRange(0, 999999); self._land_seed.setStyleSheet(SPIN_SS)
        self._land_seed.valueChanged.connect(self._on_land_seed_changed)
        base_grid.addWidget(self._land_seed, 2, 1)

        base_grid.addWidget(QLabel("Height Scale"), 3, 0)
        self._land_height_scale = QDoubleSpinBox()
        self._land_height_scale.setRange(0.1, 500.0); self._land_height_scale.setSingleStep(1.0); self._land_height_scale.setStyleSheet(SPIN_SS)
        self._land_height_scale.valueChanged.connect(lambda v: self.update_obj_prop('landscape_height_scale', v))
        base_grid.addWidget(self._land_height_scale, 3, 1)
        lg.addLayout(base_grid)

        # Climate Visualization Toggle
        climate_row = QHBoxLayout()
        self._visualize_climate_cb = QCheckBox("Visualize Climate Heatmap")
        self._visualize_climate_cb.setStyleSheet("color: #4fc3f7; font-size: 11px; font-weight: bold;")
        self._visualize_climate_cb.toggled.connect(self._on_visualize_climate_toggled)
        climate_row.addWidget(self._visualize_climate_cb)
        lg.addLayout(climate_row)
        self.chunk_widget = QWidget()
        chunk_h = QHBoxLayout(self.chunk_widget); chunk_h.setContentsMargins(0,0,0,0)
        self._land_chunk_size = QComboBox()
        self._land_chunk_size.addItems(["32", "64", "128", "256"])
        self._land_chunk_size.setStyleSheet(COMBO_SS)
        self._land_chunk_size.currentTextChanged.connect(lambda v: self.update_obj_prop('landscape_chunk_size', int(v)))
        
        self._land_grid_radius = QSpinBox()
        self._land_grid_radius.setRange(1, 15); self._land_grid_radius.setStyleSheet(SPIN_SS)
        self._land_grid_radius.valueChanged.connect(lambda v: self.update_obj_prop('landscape_grid_radius', v))
        
        chunk_h.addWidget(self._land_chunk_size); chunk_h.addWidget(QLabel("Radius")); chunk_h.addWidget(self._land_grid_radius)
        self._add_property_row(lg, "Streaming", self.chunk_widget)

        # Detail Level
        self._land_res = QComboBox()
        self._land_res.addItems(["Low (16)", "Medium (32)", "High (64)", "Very High (128)"])
        self._land_res.setStyleSheet(COMBO_SS)
        self._land_res.currentTextChanged.connect(self._on_res_changed)
        self._add_property_row(lg, "LOD Detail", self._land_res)
        
        # Ocean & Peaks
        self._land_ocean_level = PropertySlider(0.08, -1.0, 1.0)
        self._land_ocean_level.valueChanged.connect(lambda v: self.update_obj_prop('landscape_ocean_level', v))
        self._add_property_row(lg, "Ocean lvl", self._land_ocean_level)
        
        self._land_ocean_flat = PropertySlider(0.3, 0.0, 1.0)
        self._land_ocean_flat.valueChanged.connect(lambda v: self.update_obj_prop('landscape_ocean_flattening', v))
        self._add_property_row(lg, "Coast Flat", self._land_ocean_flat)

        self._land_tip_smoothing = PropertySlider(0.1, 0.0, 1.0)
        self._land_tip_smoothing.valueChanged.connect(lambda v: self.update_obj_prop('landscape_tip_smoothing', v))
        self._add_property_row(lg, "Peak Smooth", self._land_tip_smoothing)

        # Noise Layers
        self._noise_layers_list = QListWidget()
        self._noise_layers_list.setFixedHeight(70); self._noise_layers_list.setStyleSheet(LIST_SS)
        lg.addWidget(self._noise_layers_list)
        nl_btns = QHBoxLayout()
        add_nl = QPushButton("Add"); add_nl.setStyleSheet(BTN_SS); add_nl.clicked.connect(self._on_noise_layer_add)
        rem_nl = QPushButton("Rem"); rem_nl.setStyleSheet(BTN_SS); rem_nl.clicked.connect(self._on_noise_layer_remove)
        edit_nl = QPushButton("Edit"); edit_nl.setStyleSheet(BTN_SS); edit_nl.clicked.connect(self._on_noise_layer_edit)
        nl_btns.addWidget(add_nl); nl_btns.addWidget(rem_nl); nl_btns.addWidget(edit_nl)
        lg.addLayout(nl_btns)

        # Biomes
        lg.addWidget(QLabel("Biomes & Surface"))
        self._biomes_list = QListWidget()
        self._biomes_list.setFixedHeight(70); self._biomes_list.setStyleSheet(LIST_SS)
        lg.addWidget(self._biomes_list)
        bm_btns = QHBoxLayout()
        add_bm = QPushButton("Add"); add_bm.setStyleSheet(BTN_SS); add_bm.clicked.connect(self._on_biome_add)
        rem_bm = QPushButton("Rem"); rem_bm.setStyleSheet(BTN_SS); rem_bm.clicked.connect(self._on_biome_remove)
        edit_bm = QPushButton("Edit"); edit_bm.setStyleSheet(BTN_SS); edit_bm.clicked.connect(self._on_biome_edit)
        bm_btns.addWidget(add_bm); bm_btns.addWidget(rem_bm); bm_btns.addWidget(edit_bm)
        lg.addLayout(bm_btns)

        # Spawning Control
        self._spawn_enabled = QCheckBox("Enable Spawning System")
        self._spawn_enabled.setStyleSheet("color: #4fc3f7; font-size: 11px; font-weight: bold;")
        self._spawn_enabled.toggled.connect(self._on_spawn_enabled_changed)
        lg.addWidget(self._spawn_enabled)

        self.spawn_grid_widget = QWidget()
        sg = QHBoxLayout(self.spawn_grid_widget); sg.setContentsMargins(0,0,0,0)
        self._spawn_rows = QSpinBox(); self._spawn_rows.setRange(1,500); self._spawn_rows.setStyleSheet(SPIN_SS)
        self._spawn_cols = QSpinBox(); self._spawn_cols.setRange(1,500); self._spawn_cols.setStyleSheet(SPIN_SS)
        self._spawn_spacing_x = QDoubleSpinBox(); self._spawn_spacing_x.setRange(0.1, 1000); self._spawn_spacing_x.setStyleSheet(SPIN_SS)
        self._spawn_spacing_z = QDoubleSpinBox(); self._spawn_spacing_z.setRange(0.1, 1000); self._spawn_spacing_z.setStyleSheet(SPIN_SS)
        self._spawn_rows.valueChanged.connect(self._on_spawn_counts_changed)
        self._spawn_cols.valueChanged.connect(self._on_spawn_counts_changed)
        self._spawn_spacing_x.valueChanged.connect(self._on_spawn_spacing_changed)
        self._spawn_spacing_z.valueChanged.connect(self._on_spawn_spacing_changed)
        
        sg.addWidget(QLabel("R")); sg.addWidget(self._spawn_rows)
        sg.addWidget(QLabel("C")); sg.addWidget(self._spawn_cols)
        sg.addWidget(QLabel("Gap")); sg.addWidget(self._spawn_spacing_x)
        lg.addWidget(self.spawn_grid_widget)

        layout.addWidget(self.land_group)
        self._content_widgets.append(self.land_group)
        
        self.setMinimumWidth(280)

        # ---- Component Section ----
        self.comp_group = QGroupBox("Component Properties")
        self.comp_group.setStyleSheet(PROPS_SS)
        cg = QVBoxLayout(self.comp_group)
        cg.setContentsMargins(10, 14, 10, 10); cg.setSpacing(6)
        
        self.active_check = QCheckBox("Active / Simulate")
        self.active_check.setStyleSheet("color: #ccc; font-size: 11px;")
        self.active_check.toggled.connect(self._on_active_changed)
        cg.addWidget(self.active_check)
        
        self.visible_check = QCheckBox("Visible in Viewport")
        self.visible_check.setStyleSheet("color: #ccc; font-size: 11px;")
        self.visible_check.toggled.connect(self._on_visible_changed)
        cg.addWidget(self.visible_check)
        
        self.intensity_spin = PropertySlider(1.0, 0.0, 1000.0, step=1.0)
        self.intensity_spin.valueChanged.connect(self._on_intensity_changed)
        self._add_property_row(cg, "Intensity", self.intensity_spin)
        
        self.range_spin = PropertySlider(10.0, 0.1, 2000.0, step=1.0)
        self.range_spin.valueChanged.connect(self._on_range_changed)
        self._add_property_row(cg, "Range/Radius", self.range_spin)
        
        self.fov_spin = PropertySlider(60.0, 1.0, 170.0, step=1.0)
        self.fov_spin.valueChanged.connect(self._on_fov_changed)
        self._add_property_row(cg, "Field of View", self.fov_spin)
        
        layout.addWidget(self.comp_group)
        self._content_widgets.append(self.comp_group)

        # ---- Ocean Section (GPU Waves) ----
        self.ocean_group = QGroupBox("Ocean (GPU Waves)")
        self.ocean_group.setStyleSheet(PROPS_SS)
        og = QVBoxLayout(self.ocean_group)
        og.setContentsMargins(10, 14, 10, 10); og.setSpacing(8)
        
        self._ocean_use_fft = QCheckBox("Enable FFT Simulation")
        self._ocean_use_fft.setStyleSheet("color: #eee; font-size: 11px;")
        self._ocean_use_fft.toggled.connect(lambda v: self.update_obj_prop('ocean_use_fft', v))
        og.addWidget(self._ocean_use_fft)
        
        # Wave Parameters
        self._ocean_scale = PropertySlider(1.0, 0.1, 10.0)
        self._ocean_scale.valueChanged.connect(lambda v: self.update_obj_prop('ocean_wave_scale', v))
        self._add_property_row(og, "Wave Scale", self._ocean_scale, "Overall size of the swells")

        self._ocean_speed = PropertySlider(5.0, 0.0, 20.0)
        self._ocean_speed.valueChanged.connect(lambda v: self.update_obj_prop('ocean_wave_speed', v))
        self._add_property_row(og, "Wave Speed", self._ocean_speed, "Speed of the wave animation")

        self._ocean_steepness = PropertySlider(0.15, 0.0, 1.0)
        self._ocean_steepness.valueChanged.connect(lambda v: self.update_obj_prop('ocean_wave_steepness', v))
        self._add_property_row(og, "Steepness", self._ocean_steepness, "Peakiness of the waves (Gerstner)")

        self._ocean_foam = PropertySlider(0.1, 0.0, 2.0)
        self._ocean_foam.valueChanged.connect(lambda v: self.update_obj_prop('ocean_foam_amount', v))
        self._add_property_row(og, "Foam Amount", self._ocean_foam, "Intensity of crest foam")

        self._ocean_choppiness = PropertySlider(1.5, 0.0, 5.0)
        self._ocean_choppiness.valueChanged.connect(lambda v: self.update_obj_prop('ocean_wave_choppiness', v))
        self._add_property_row(og, "Choppiness", self._ocean_choppiness, "Pitch/Sharpness of wave peaks (FFT displacement)")

        self._ocean_wave_intensity = PropertySlider(1.0, 0.1, 10.0, step=0.1)
        self._ocean_wave_intensity.valueChanged.connect(lambda v: self.update_obj_prop('ocean_wave_intensity', v))
        self._add_property_row(og, "Wave Intensity", self._ocean_wave_intensity, "Overall height multiplier for FFT waves")

        self._ocean_fft_res = QComboBox()
        self._ocean_fft_res.addItems(["128", "256", "512", "1024"])
        self._ocean_fft_res.setCurrentText("128")
        self._ocean_fft_res.setStyleSheet("background: #333; color: #eee; border: 1px solid #555;")
        self._ocean_fft_res.currentTextChanged.connect(lambda v: self.update_obj_prop('ocean_fft_resolution', int(v)))
        self._add_property_row(og, "FFT Detail", self._ocean_fft_res, "Resolution of the FFT simulation grid")
        
        # Opacity Slider
        self._ocean_opacity = PropertySlider(0.8, 0.0, 1.0)
        self._ocean_opacity.valueChanged.connect(lambda v: self.update_obj_prop('opacity', v))
        self._add_property_row(og, "Opacity", self._ocean_opacity, "Transparency of the water surface")

        layout.addWidget(self.ocean_group)
        self._content_widgets.append(self.ocean_group)

        layout.addStretch()
        # Start with an empty/hidden properties panel until an object is selected
        try:
            self.set_object(None)
        except Exception:
            pass

    def _on_res_changed(self, text):
        if self._updating or not self._current_object: return
        val = 32
        if "Low" in text: val = 16
        elif "Medium" in text: val = 32
        elif "High" in text: val = 64
        elif "Very High" in text: val = 128
        self.update_obj_prop('landscape_resolution', val)

    def _on_land_type_changed(self, text):
        if self._updating or not self._current_object: return
        val = text.lower()
        self.update_obj_prop('landscape_type', val)

    def _on_land_size_mode_changed(self, text):
        if self._updating or not self._current_object: return
        val = text.lower()
        self.update_obj_prop('landscape_size_mode', val)

    def _on_land_seed_changed(self, val):
        if self._updating or not self._current_object: return
        self._current_object.landscape_seed = val
        self.property_changed.emit()

    def _on_visualize_climate_toggled(self, val):
        if self._updating or not self._current_object: return
        self._current_object.visualize_climate = val
        self.property_changed.emit()

    def _on_active_changed(self, val):
        if self._updating or not self._current_object: return
        self._current_object.active = val
        self.property_changed.emit()

    def update_obj_prop(self, prop, val):
        if self._updating or not self._current_object: return
        setattr(self._current_object, prop, val)
        self.property_changed.emit()

    def _on_noise_layer_add(self):
        if not self._current_object: return
        # Default layer
        lyr = {'amp': 0.5, 'freq': 1.0, 'offset': [0.0, 0.0], 'octaves': 1, 'mode': 'fbm', 'exponent': 1.0, 'type': 'perlin'}
        self._current_object.landscape_noise_layers.append(lyr)
        self._sync_from_object()
        self.property_changed.emit()

    def _on_noise_layer_remove(self):
        idx = self._noise_layers_list.currentRow()
        if idx < 0 or not self._current_object: return
        if len(self._current_object.landscape_noise_layers) <= 1: return # Keep at least one
        self._current_object.landscape_noise_layers.pop(idx)
        self._sync_from_object()
        self.property_changed.emit()

    def _on_noise_layer_edit(self):
        idx = self._noise_layers_list.currentRow()
        if idx < 0 or not self._current_object: return
        lyr = self._current_object.landscape_noise_layers[idx]
        dlg = NoiseLayerDialog(lyr, self)
        if dlg.exec():
            self._sync_from_object()
            self.property_changed.emit()

    def _on_biome_add(self):
        if not self._current_object: return
        # Default biome template
        b = {
            'name': 'New Biome',
            'height_range': [0.0, 1.0], 'slope_range': [0.0, 1.0],
            'temp_range': [0.0, 1.0], 'hum_range': [0.0, 1.0],
            'surface': {'color': [0.5, 0.5, 0.5, 1.0], 'roughness': 0.7, 'metallic': 0.0},
            'spawns': []
        }
        self._current_object.landscape_biomes.append(b)
        self._sync_from_object()
        self.property_changed.emit()

    def _on_biome_remove(self):
        idx = self._biomes_list.currentRow()
        if idx < 0 or not self._current_object: return
        if len(self._current_object.landscape_biomes) <= 1: return
        self._current_object.landscape_biomes.pop(idx)
        self._sync_from_object()
        self.property_changed.emit()

    def _on_biome_edit(self):
        idx = self._biomes_list.currentRow()
        if idx < 0 or not self._current_object: return
        biome = self._current_object.landscape_biomes[idx]
        dlg = BiomeDialog(biome, self)
        if dlg.exec():
            # Update the reference
            self._current_object.landscape_biomes[idx] = dlg.get_data()
            self._sync_from_object()
            self.property_changed.emit()

    def set_object(self, obj: Optional[SceneObject]):
        """Set the selected object to display in the panel."""
        self._current_object = obj
        if obj:
            # Ensure the content area is visible when an object is selected
            try:
                for w in getattr(self, '_content_widgets', []):
                    w.setVisible(True)
            except Exception:
                pass
            self._title.setText(f"  {obj.name}  ({obj.obj_type})")
            self._title.setStyleSheet("color: #4fc3f7; font-size: 11px; font-weight: bold;")
            
            # Visibility of component properties
            is_light = "light" in obj.obj_type
            is_cam = obj.obj_type == "camera"
            is_land = obj.obj_type == 'landscape'
            is_ocean = obj.obj_type == 'ocean'
            self.comp_group.setVisible(is_light or is_cam or obj.obj_type == "logic")
            self.intensity_spin.setVisible(is_light)
            self.range_spin.setVisible(is_light)
            self.fov_spin.setVisible(is_cam)
            # Panel visibility
            self.land_group.setVisible(is_land)
            self.ocean_group.setVisible(is_ocean)
            
            if is_land:
                self._land_type.setCurrentText(obj.landscape_type.capitalize())
                self._land_size_mode.setCurrentText(obj.landscape_size_mode.capitalize())
                self._land_seed.setValue(obj.landscape_seed)
                self._land_height_scale.setValue(float(getattr(obj, 'landscape_height_scale', 30.0)))
                self._visualize_climate_cb.setChecked(getattr(obj, 'visualize_climate', False))
            elif is_ocean:
                # Sync ocean specific fields
                self._ocean_scale.setValue(getattr(obj, 'ocean_wave_scale', 1.0))
                self._ocean_speed.setValue(getattr(obj, 'ocean_wave_speed', 1.0))
                self._ocean_steepness.setValue(getattr(obj, 'ocean_wave_steepness', 0.5))
                self._ocean_foam.setValue(getattr(obj, 'ocean_foam_amount', 0.5))
                self._ocean_choppiness.setValue(getattr(obj, 'ocean_wave_choppiness', 1.5))
                self._ocean_wave_intensity.setValue(getattr(obj, 'ocean_wave_intensity', 1.0))
                self._ocean_fft_res.setCurrentText(str(getattr(obj, 'ocean_fft_resolution', 128)))
                self._ocean_use_fft.setChecked(getattr(obj, 'ocean_use_fft', True))
                self._ocean_opacity.setValue(int(getattr(obj, 'ocean_opacity', 0.8) * 100))
            
            self._sync_from_object()
        else:
            self._title.setText("  No Selection")
            self._title.setStyleSheet("color: #888; font-size: 11px; font-weight: bold;")
            self.comp_group.setVisible(False)
            # Hide landscape and reset material UI when nothing is selected
            try:
                for w in getattr(self, '_content_widgets', []):
                    w.setVisible(False)
            except Exception:
                pass
            try:
                if hasattr(self, '_mat_slot'):
                    self._mat_slot.set_material(None)
                if hasattr(self, '_base_color_btn'):
                    self._base_color_btn.setStyleSheet("background: #ccc; border: 1px solid #555; border-radius: 3px;")
            except Exception:
                pass
            self._clear_spins()

    def _sync_from_object(self):
        """Push object values into spinboxes without triggering change signals."""
        if not self._current_object: return
        self._updating = True
        obj = self._current_object
        for i in range(3):
            self._pos_spins[i].setValue(obj.position[i])
            self._rot_spins[i].setValue(obj.rotation[i])
            self._scale_spins[i].setValue(obj.scale[i])
        
        # Sync material UI
        mat = obj.material
        preset = mat.get('preset', 'Custom')
        idx = self._mat_preset.findText(preset)
        self._mat_preset.setCurrentIndex(idx if idx >= 0 else self._mat_preset.count() - 1)
        bc = mat.get('base_color', [0.8, 0.8, 0.8, 1.0])
        self._base_color_btn.setStyleSheet(
            f"background: rgb({int(bc[0]*255)},{int(bc[1]*255)},{int(bc[2]*255)}); border: 1px solid #555; border-radius: 3px;"
        )
        self._roughness_slider.setValue(mat.get('roughness', 0.7))
        self._metallic_slider.setValue(mat.get('metallic', 0.0))
        ec = mat.get('emissive_color', [0, 0, 0, 1])
        self._emissive_btn.setStyleSheet(
            f"background: rgb({int(ec[0]*255)},{int(ec[1]*255)},{int(ec[2]*255)}); border: 1px solid #555; border-radius: 3px;"
        )
        mat_file = mat.get('file', '')
        self._mat_file_label.setText(Path(mat_file).name if mat_file else '')
        self._mat_slot.set_material(Path(mat_file).name if mat_file else None)
        
        # Sync component values
        self.active_check.setChecked(obj.active)
        self.visible_check.setChecked(obj.visible)
        self.intensity_spin.setValue(obj.intensity)
        self.range_spin.setValue(obj.range)
        self.fov_spin.setValue(obj.fov)

        # Sync ocean values
        if obj.obj_type == 'ocean':
             try:
                 for w in (self._ocean_scale, self._ocean_speed, self._ocean_steepness, self._ocean_foam, self._ocean_opacity):
                     try: w.blockSignals(True)
                     except Exception: pass
                 
                 self._ocean_scale.setValue(getattr(obj, 'ocean_wave_scale', 1.0))
                 self._ocean_speed.setValue(getattr(obj, 'ocean_wave_speed', 5.0))
                 self._ocean_steepness.setValue(getattr(obj, 'ocean_wave_steepness', 0.15))
                 self._ocean_foam.setValue(getattr(obj, 'ocean_foam_amount', 0.1))
                 self._ocean_opacity.setValue(getattr(obj, 'opacity', 0.8))
                 
                 for w in (self._ocean_scale, self._ocean_speed, self._ocean_steepness, self._ocean_foam, self._ocean_opacity):
                     try: w.blockSignals(False)
                     except Exception: pass
             except Exception: pass

        # Sync landscape values when applicable
        if obj.obj_type == 'landscape':
            try:
                lmode = getattr(obj, 'landscape_size_mode', 'finite')
                lt_str = 'Procedural' if getattr(obj, 'landscape_type', 'flat') == 'procedural' else 'Flat'
                
                # Prevent signals while updating
                for w in (self._land_type, self._land_size_mode, self._land_chunk_size, self._land_grid_radius,
                          self._spawn_enabled, self._spawn_rows, self._spawn_cols, self._spawn_spacing_x, self._spawn_spacing_z,
                          self._land_seed, self._land_res, self._land_ocean_level, self._land_ocean_flat, self._land_height_scale,
                          self._land_tip_smoothing):
                    try: w.blockSignals(True)
                    except Exception: pass

                self._land_type.setCurrentText(lt_str)
                self._land_size_mode.setCurrentText(lmode.capitalize())

                # Sync Streaming, Chunking & Res
                if hasattr(self, 'chunk_widget'): self.chunk_widget.setVisible(True)
                
                self._land_chunk_size.setCurrentText(str(int(getattr(obj, 'landscape_chunk_size', 128))))
                self._land_grid_radius.setValue(int(getattr(obj, 'landscape_grid_radius', 1)))
                self._land_grid_radius.setEnabled(True) # Always allow changing radius
                
                res_val = int(getattr(obj, 'landscape_resolution', 32))
                res_map = {16: "Low (16)", 32: "Medium (32)", 64: "High (64)", 128: "Very High (128)"}
                self._land_res.setCurrentText(res_map.get(res_val, "Medium (32)"))
                
                self._land_height_scale.setValue(float(getattr(obj, 'landscape_height_scale', 30.0)))
                self._land_ocean_level.setValue(float(getattr(obj, 'landscape_ocean_level', 0.08)))
                self._land_ocean_flat.setValue(float(getattr(obj, 'landscape_ocean_flattening', 0.3)))
                self._land_tip_smoothing.setValue(float(getattr(obj, 'landscape_tip_smoothing', 0.1)))
                
                self._spawn_enabled.setChecked(getattr(obj, 'landscape_spawn_enabled', False))
                self._land_seed.setValue(int(getattr(obj, 'landscape_seed', 123)))
                
                # Check for climate heatmap sync
                self._visualize_climate_cb.setChecked(getattr(obj, 'visualize_climate', False))
                
                # Ensure the chunk widget is visible
                self.chunk_widget.setEnabled(True)
                self.chunk_widget.setVisible(True)

                # Sync Noise Layers List
                self._noise_layers_list.clear()
                for i, lyr in enumerate(getattr(obj, 'landscape_noise_layers', [])):
                    self._noise_layers_list.addItem(f"L{i}: Amp={lyr.get('amp')} Freq={lyr.get('freq')} Oct={lyr.get('octaves')}")
                
                # Sync Biomes List
                self._biomes_list.clear()
                for b in getattr(obj, 'landscape_biomes', []):
                    hr = b.get('height_range', [-1000, 1000]); sr = b.get('slope_range', [0,1])
                    self._biomes_list.addItem(f"{b.get('name')}: H[{hr[0]:.0f},{hr[1]:.0f}] S[{sr[0]:.1f},{sr[1]:.1f}]")

                self._spawn_rows.setValue(int(getattr(obj, 'landscape_spawn_rows', 1)))
                self._spawn_cols.setValue(int(getattr(obj, 'landscape_spawn_cols', 1)))
                sp = getattr(obj, 'landscape_spawn_spacing', [10.0, 10.0])
                self._spawn_spacing_x.setValue(sp[0]); self._spawn_spacing_z.setValue(sp[1])
            except Exception as e:
                print(f"Land sync error: {e}")
            finally:
                for w in (self._land_type, self._land_size_mode, self._land_chunk_size, self._land_grid_radius,
                          self._spawn_enabled, self._spawn_rows, self._spawn_cols, self._spawn_spacing_x, self._spawn_spacing_z,
                          self._land_seed, self._land_res):
                    try: w.blockSignals(False)
                    except Exception: pass

        if obj.obj_type == 'ocean':
            try:
                # Prevent signals while updating
                for w in (self._ocean_scale, self._ocean_speed, self._ocean_steepness, self._ocean_foam, self._ocean_choppiness, self._ocean_opacity, self._ocean_use_fft):
                    try: w.blockSignals(True)
                    except Exception: pass
                
                try: self._ocean_fft_res.blockSignals(True)
                except Exception: pass

                self._ocean_scale.setValue(getattr(obj, 'ocean_wave_scale', 1.0))
                self._ocean_speed.setValue(getattr(obj, 'ocean_wave_speed', 1.0))
                self._ocean_steepness.setValue(getattr(obj, 'ocean_wave_steepness', 0.5))
                self._ocean_foam.setValue(getattr(obj, 'ocean_foam_amount', 0.5))
                
                self._ocean_choppiness.blockSignals(True)
                self._ocean_choppiness.setValue(getattr(obj, 'ocean_wave_choppiness', 1.5))
                self._ocean_choppiness.blockSignals(False)

                self._ocean_wave_intensity.blockSignals(True)
                self._ocean_wave_intensity.setValue(getattr(obj, 'ocean_wave_intensity', 1.0))
                self._ocean_wave_intensity.blockSignals(False)
                
                self._ocean_fft_res.blockSignals(True)
                self._ocean_fft_res.setCurrentText(str(getattr(obj, 'ocean_fft_resolution', 128)))
                self._ocean_fft_res.blockSignals(False)
                
                self._ocean_use_fft.setChecked(getattr(obj, 'ocean_use_fft', True))
                self._ocean_opacity.setValue(int(getattr(obj, 'ocean_opacity', 0.8) * 100))
            except Exception as e:
                print(f"Ocean sync error: {e}")
            finally:
                for w in (self._ocean_scale, self._ocean_speed, self._ocean_steepness, self._ocean_foam, self._ocean_choppiness, self._ocean_opacity, self._ocean_use_fft):
                    try: w.blockSignals(False)
                    except Exception: pass
                try: self._ocean_fft_res.blockSignals(False)
                except Exception: pass
        
        self._updating = False

    def _on_active_changed(self, val):
        if self._updating or not self._current_object: return
        self._current_object.active = val
        self.property_changed.emit()

    def _on_visible_changed(self, val):
        if self._updating or not self._current_object: return
        self._current_object.visible = val
        self.property_changed.emit()

    def _on_intensity_changed(self, val):
        if self._updating or not self._current_object: return
        self._current_object.intensity = val; self.property_changed.emit()

    def _on_range_changed(self, val):
        if self._updating or not self._current_object: return
        self._current_object.range = val; self.property_changed.emit()

    def _on_fov_changed(self, val):
        if self._updating or not self._current_object: return
        self._current_object.fov = val; self.property_changed.emit()

    def refresh_from_object(self):
        """Re-sync from object (called after drag moves etc.)."""
        self._sync_from_object()

    def _clear_spins(self):
        self._updating = True
        for s in self._pos_spins + self._rot_spins + self._scale_spins:
            s.setValue(0)
        # Also clear material UI to default/empty state
        try:
            if hasattr(self, '_mat_preset'):
                try:
                    self._mat_preset.blockSignals(True)
                    self._mat_preset.setCurrentText('Custom')
                finally:
                    self._mat_preset.blockSignals(False)
            if hasattr(self, '_mat_slot'):
                self._mat_slot.set_material(None)
            if hasattr(self, '_base_color_btn'):
                self._base_color_btn.setStyleSheet("background: #ccc; border: 1px solid #555; border-radius: 3px;")
            if hasattr(self, '_roughness_slider'):
                self._roughness_slider.setValue(70); self._roughness_val.setText("0.70")
            if hasattr(self, '_metallic_slider'):
                self._metallic_slider.setValue(0); self._metallic_val.setText("0.00")
            if hasattr(self, '_emissive_btn'):
                self._emissive_btn.setStyleSheet("background: #000; border: 1px solid #555; border-radius: 3px;")
            if hasattr(self, '_mat_file_label'):
                self._mat_file_label.setText("")
            if hasattr(self, 'land_group'):
                self.land_group.setVisible(False)
        except Exception:
            pass
        self._updating = False

    def _on_pos_changed(self):
        if self._updating or not self._current_object: return
        for i in range(3):
            self._current_object.position[i] = self._pos_spins[i].value()
        self.property_changed.emit()

    def _on_rot_changed(self):
        if self._updating or not self._current_object: return
        for i in range(3):
            self._current_object.rotation[i] = self._rot_spins[i].value()
        self.property_changed.emit()

    def _on_scale_changed(self):
        if self._updating or not self._current_object: return
        for i in range(3):
            self._current_object.scale[i] = self._scale_spins[i].value()
        self.property_changed.emit()

    # ---- Material handlers ----
    def _on_mat_preset_changed(self, preset_name):
        if self._updating or not self._current_object: return
        if preset_name in MATERIAL_PRESETS:
            self._current_object.material = dict(MATERIAL_PRESETS[preset_name])
            self._current_object.material['preset'] = preset_name
            self._sync_from_object()
            self.property_changed.emit()

    def _on_material_slot_dropped(self, filepath):
        if not self._current_object: return
        import json as _json
        try:
            with open(filepath, 'r') as f:
                data = _json.load(f)
            self._current_object.material = data
            self._current_object.material['file'] = filepath
            self._sync_from_object()
            self.property_changed.emit()
        except Exception as e:
            print(f"Failed to load material from slot: {e}")
            
    def _on_mat_slot_btn_clicked(self):
        # We need workspace root, typically passed from parent or access via search
        root = ""
        # Try to find workspace root from SceneEditor if possible
        filepath, _ = QFileDialog.getOpenFileName(self, "Select Material", root, "Materials (*.material)")
        if filepath:
            self._on_material_slot_dropped(filepath)

    def _pick_base_color(self):
        if not self._current_object: return
        bc = self._current_object.material.get('base_color', [0.8, 0.8, 0.8, 1.0])
        color = QColorDialog.getColor(QColor(int(bc[0]*255), int(bc[1]*255), int(bc[2]*255)), self, "Base Color")
        if color.isValid():
            self._current_object.material['base_color'] = [color.redF(), color.greenF(), color.blueF(), bc[3] if len(bc) > 3 else 1.0]
            self._current_object.material['preset'] = 'Custom'
            self._sync_from_object()
            self.property_changed.emit()

    def _on_roughness_changed(self, val):
        if self._updating or not self._current_object: return
        self._current_object.material['roughness'] = val / 100.0
        self._current_object.material['preset'] = 'Custom'
        self._roughness_val.setText(f"{val / 100.0:.2f}")
        self._mat_preset.blockSignals(True)
        self._mat_preset.setCurrentText('Custom')
        self._mat_preset.blockSignals(False)
        self.property_changed.emit()

    def _on_metallic_changed(self, val):
        if self._updating or not self._current_object: return
        self._current_object.material['metallic'] = val / 100.0
        self._current_object.material['preset'] = 'Custom'
        self._metallic_val.setText(f"{val / 100.0:.2f}")
        self._mat_preset.blockSignals(True)
        self._mat_preset.setCurrentText('Custom')
        self._mat_preset.blockSignals(False)
        self.property_changed.emit()

    def _pick_emissive_color(self):
        if not self._current_object: return
        ec = self._current_object.material.get('emissive_color', [0, 0, 0, 1])
        color = QColorDialog.getColor(QColor(int(ec[0]*255), int(ec[1]*255), int(ec[2]*255)), self, "Emissive Color")
        if color.isValid():
            self._current_object.material['emissive_color'] = [color.redF(), color.greenF(), color.blueF(), 1.0]
            self._current_object.material['preset'] = 'Custom'
            self._sync_from_object()
            self.property_changed.emit()

    # ---- Landscape handlers ----
    def _on_land_type_changed(self, text):
        if self._updating or not self._current_object: return
        self._current_object.landscape_type = 'procedural' if text.lower().startswith('p') else 'flat'
        self.property_changed.emit()

    def _on_land_size_mode_changed(self, text):
        if self._updating or not self._current_object: return
        mode = 'infinite' if text.lower().startswith('i') else 'finite'
        self._current_object.landscape_size_mode = mode
        # Toggle widgets
        if hasattr(self, 'size_widget'): self.size_widget.setVisible(mode == 'finite')
        if hasattr(self, 'spawn_grid_widget'): self.spawn_grid_widget.setVisible(mode == 'finite')
        self.property_changed.emit()

    def _on_land_size_changed(self, _val=None):
        if self._updating or not self._current_object: return
        self._current_object.landscape_size = [self._land_width.value(), self._land_depth.value()]
        self.property_changed.emit()

    def _on_spawn_enabled_changed(self, val):
        if self._updating or not self._current_object: return
        self._current_object.landscape_spawn_enabled = bool(val)
        self.property_changed.emit()
        # Manage spawn lifecycle on the active viewport if available
        parent = self.parent()
        while parent and not hasattr(parent, 'viewport'):
            parent = parent.parent()
        vp = getattr(parent, 'viewport', None)
        if vp:
            try:
                from .procedural_system import ensure_spawned, clear_spawns
                if val: ensure_spawned(vp, self._current_object)
                else: clear_spawns(vp, self._current_object)
            except Exception as e:
                print(f"[LANDSCAPE SPAWN] {e}")

    def _on_spawn_add(self):
        if not self._current_object: return
        root = getattr(self, '_workspace_root', '')
        files, _ = QFileDialog.getOpenFileNames(self, "Add Spawn Assets", root or "", "Assets (*.*)")
        if not files: return
        lst = getattr(self._current_object, 'landscape_spawn_list', []) or []
        for f in files:
            lst.append(f)
            it = QListWidgetItem(Path(f).name)
            it.setData(Qt.ItemDataRole.UserRole, f)
            self._spawn_list.addItem(it)
        self._current_object.landscape_spawn_list = lst
        self.property_changed.emit()
        # If enabled, spawn newly added assets
        if getattr(self._current_object, 'landscape_spawn_enabled', False):
            parent = self.parent()
            while parent and not hasattr(parent, 'viewport'):
                parent = parent.parent()
            vp = getattr(parent, 'viewport', None)
            if vp:
                try:
                    from .procedural_system import ensure_spawned
                    ensure_spawned(vp, self._current_object)
                except Exception as e:
                    print(f"[LANDSCAPE SPAWN] {e}")

    def _on_spawn_remove(self):
        if not self._current_object: return
        sel = self._spawn_list.selectedItems()
        if not sel: return
        for it in sel:
            p = it.data(Qt.ItemDataRole.UserRole)
            try:
                self._current_object.landscape_spawn_list.remove(p)
            except Exception:
                pass
            self._spawn_list.takeItem(self._spawn_list.row(it))
        self.property_changed.emit()
        # Refresh spawned instances
        parent = self.parent()
        while parent and not hasattr(parent, 'viewport'):
            parent = parent.parent()
        vp = getattr(parent, 'viewport', None)
        if vp:
            try:
                from .procedural_system import clear_spawns, ensure_spawned
                clear_spawns(vp, self._current_object)
                if getattr(self._current_object, 'landscape_spawn_enabled', False):
                    ensure_spawned(vp, self._current_object)
            except Exception as e:
                print(f"[LANDSCAPE SPAWN] {e}")

    def _on_spawn_counts_changed(self, _val=None):
        if self._updating or not self._current_object: return
        self._current_object.landscape_spawn_rows = int(self._spawn_rows.value())
        self._current_object.landscape_spawn_cols = int(self._spawn_cols.value())
        self.property_changed.emit()
        # respawn if needed
        parent = self.parent()
        while parent and not hasattr(parent, 'viewport'):
            parent = parent.parent()
        vp = getattr(parent, 'viewport', None)
        if vp and getattr(self._current_object, 'landscape_spawn_enabled', False):
            try:
                from .procedural_system import clear_spawns, ensure_spawned
                clear_spawns(vp, self._current_object); ensure_spawned(vp, self._current_object)
            except Exception as e:
                print(f"[LANDSCAPE SPAWN] {e}")

    def _on_spawn_spacing_changed(self, _val=None):
        if self._updating or not self._current_object: return
        self._current_object.landscape_spawn_spacing = [self._spawn_spacing_x.value(), self._spawn_spacing_z.value()]
        self.property_changed.emit()
        parent = self.parent()
        while parent and not hasattr(parent, 'viewport'):
            parent = parent.parent()
        vp = getattr(parent, 'viewport', None)
        if vp and getattr(self._current_object, 'landscape_spawn_enabled', False):
            try:
                from .procedural_system import clear_spawns, ensure_spawned
                clear_spawns(vp, self._current_object); ensure_spawned(vp, self._current_object)
            except Exception as e:
                print(f"[LANDSCAPE SPAWN] {e}")

    def _on_proc_params_changed(self, _val=None):
        if self._updating or not self._current_object: return
        self._current_object.landscape_procedural_amp = float(self._proc_amp.value())
        self._current_object.landscape_procedural_freq = float(self._proc_freq.value())
        self.property_changed.emit()

class OutlinerTreeWidget(QTreeWidget):
    """Custom tree widget for the scene outliner with drag-and-drop parenting."""
    reparent_requested = pyqtSignal(str, str) # child_id, parent_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.setStyleSheet(TREE_SS)

    def startDrag(self, supported_actions):
        item = self.currentItem()
        if not item: return
        
        obj_id = item.data(0, Qt.ItemDataRole.UserRole)
        # Primitives also use UserRole but they are not scene objects
        # Scene objects have IDs (uuid strings usually)
        if not obj_id or not isinstance(obj_id, str): return
        
        # Get object name from label (strip the icon prefix)
        label = item.text(0)
        obj_name = label.split(' ', 1)[1] if ' ' in label else label
        
        drag = QDrag(self)
        mime = QMimeData()
        
        # Format for Logic Graph
        mime_text = f"scene_object:{obj_id}:{obj_name}"
        # We use both text and a specific format for robustness
        mime.setText(mime_text)
        mime.setData("application/x-nodecanvas-scene-object", mime_text.encode('utf-8'))
        
        drag.setMimeData(mime)
        
        # Create a tiny pixmap for the drag icon
        px = QPixmap(140, 24); px.fill(QColor("#333"))
        p = QPainter(px)
        # Use a nice blue highlight for scene references
        p.setPen(QColor("#4fc3f7")); p.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        p.drawText(px.rect(), Qt.AlignmentFlag.AlignCenter, label); p.end()
        drag.setPixmap(px)
        
        drag.exec(Qt.DropAction.CopyAction)

    def dragEnterEvent(self, event):
        if event.source() == self:
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.source() == self:
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event: QDropEvent):
        target_item = self.itemAt(event.position().toPoint())
        dropped_items = self.selectedItems()
        if not dropped_items:
            super().dropEvent(event); return

        parent_id = target_item.data(0, Qt.ItemDataRole.UserRole) if target_item else ""
        
        for item in dropped_items:
            child_id = item.data(0, Qt.ItemDataRole.UserRole)
            if child_id:
                self.reparent_requested.emit(child_id, parent_id)
        
        event.accept()

class AssetsTreeWidget(QTreeWidget):
    """Custom tree widget for the assets explorer with drag support."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setDragEnabled(True)
        self.setAcceptDrops(False)
        self.setStyleSheet(self.styleSheet() or TREE_SS)

    def startDrag(self, supported_actions):
        item = self.currentItem()
        if not item: return
        
        filepath = item.data(0, Qt.ItemDataRole.UserRole)
        import os
        if not filepath or not os.path.isfile(filepath): return
        
        from pathlib import Path
        p = Path(filepath)
        ext = p.suffix.lower()
        
        drag = QDrag(self)
        mime = QMimeData()
        
        abs_path = os.path.abspath(filepath)
        
        if ext == '.logic':
            mime.setData("application/x-nodecanvas-graph", abs_path.encode('utf-8'))
            mime.setText(f"logic:{abs_path}")
        elif ext == '.material':
            mime.setData("application/x-nodecanvas-material", abs_path.encode('utf-8'))
            mime.setText(f"mat:{abs_path}")
        else:
            mime.setText(f"file:{abs_path}")
        
        from PyQt6.QtCore import QUrl
        mime.setUrls([QUrl.fromLocalFile(abs_path)])
        drag.setMimeData(mime)
        
        label = item.text(0)
        px = QPixmap(160, 24); px.fill(QColor(40, 45, 55, 200))
        ptr = QPainter(px)
        ptr.setPen(QColor("#4fc3f7")); ptr.setFont(QFont("Segoe UI", 9))
        ptr.drawText(px.rect(), Qt.AlignmentFlag.AlignCenter, label)
        ptr.end()
        drag.setPixmap(px)
        
        drag.exec(Qt.DropAction.CopyAction)



# ===================================================================
# Scene Explorer Panel
# ===================================================================

class _CollapsibleSection(QWidget):
    """Collapsible section matching Logic tab explorer style."""
    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.is_collapsed = False
        self._title = title
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0,0,0,0); layout.setSpacing(0)
        self.header = QPushButton(f" v  {title}")
        self.header.setStyleSheet(SECTION_HEADER_SS)
        self.header.clicked.connect(self.toggle)
        layout.addWidget(self.header)
        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(0,0,0,0); self.content_layout.setSpacing(0)
        layout.addWidget(self.content)

    def toggle(self):
        self.set_collapsed(not self.is_collapsed)

    def set_collapsed(self, value):
        self.is_collapsed = value
        self.content.setVisible(not self.is_collapsed)
        arrow = ">" if self.is_collapsed else "v"
        self.header.setText(f" {arrow}  {self._title}")



class SceneExplorerPanel(QWidget):
    """Left-side explorer panel for the Viewport tab."""

    primitive_dragged = pyqtSignal(str)
    object_select_requested = pyqtSignal(str)
    material_open_requested = pyqtSignal(str)  # emitted with .material filepath
    mode_changed = pyqtSignal(str)   # emitted when sub-mode tabs change (3D/2D...)

    ASSET_3D_EXTS = {'.fbx', '.obj', '.gltf', '.glb', '.dae', '.stl', '.ply'}
    ASSET_2D_EXTS = {'.png', '.jpg', '.jpeg', '.webp', '.gif', '.svg', '.bmp', '.tga'}
    MATERIAL_EXTS = {'.material'}
    LOGIC_EXTS = {'.logic'}
    SCENE_EXTS = {'.scene'}
    ALL_ASSET_EXTS = ASSET_3D_EXTS | ASSET_2D_EXTS | MATERIAL_EXTS | LOGIC_EXTS | SCENE_EXTS
    # Folders and extensions to skip entirely
    SKIP_DIRS = {'__pycache__', 'node_modules', '.git', '.gemini', '.vscode', '.idea', 'venv', 'env', 'dist', 'build'}
    SKIP_EXTS = {'.pyc', '.pyo', '.lock'} # Show .py, .json, .anim, .ui etc.

    file_selected = pyqtSignal(str)
    object_select_requested = pyqtSignal(str)
    mode_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ExplorerPanel")
        self.setMinimumWidth(200)
        self.setStyleSheet(PANEL_SS)
        self._mode = "3D"
        self._workspace_root = None

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0,0,0,0); main_layout.setSpacing(0)

        # Explorer header (VS Code style)
        header_widget = QWidget()
        header_widget.setStyleSheet("background: #252526; border-bottom: 1px solid #3c3c3c;")
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(8, 0, 8, 0)
        header_layout.setSpacing(4)
        header_widget.setFixedHeight(28)
        
        title = QLabel("EXPLORER")
        title.setStyleSheet("color: #888; font-size: 11px; font-weight: bold; border: none;")
        header_layout.addWidget(title)
        header_layout.addStretch()
        
        # Action buttons
        open_folder_btn = QPushButton("📁")
        open_folder_btn.setFixedSize(20, 20)
        open_folder_btn.setToolTip("Open Folder (Set Workspace)")
        open_folder_btn.setStyleSheet("QPushButton { background: transparent; color: #888; border: none; } QPushButton:hover { color: #fff; }")
        open_folder_btn.clicked.connect(self._open_folder)
        header_layout.addWidget(open_folder_btn)
        
        refresh_btn = QPushButton("↻")
        refresh_btn.setFixedSize(20, 20)
        refresh_btn.setToolTip("Refresh")
        refresh_btn.setStyleSheet("QPushButton { background: transparent; color: #888; border: none; } QPushButton:hover { color: #fff; }")
        refresh_btn.clicked.connect(self.refresh_assets)
        header_layout.addWidget(refresh_btn)
        
        new_file_btn = QPushButton("+")
        new_file_btn.setFixedSize(20, 20)
        new_file_btn.setToolTip("New File")
        new_file_btn.setStyleSheet("QPushButton { background: transparent; color: #888; border: none; } QPushButton:hover { color: #fff; }")
        new_file_btn.clicked.connect(self._new_file)
        header_layout.addWidget(new_file_btn)
        
        main_layout.addWidget(header_widget)

        # Content area (scrollable sections)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: #252526; }")
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(0,0,0,0); scroll_layout.setSpacing(0)

        # ---- Project Assets section ----
        self._assets_section = _CollapsibleSection("PROJECT FILES")
        self.assets_tree = AssetsTreeWidget(self)
        self._assets_section.content_layout.addWidget(self.assets_tree)
        scroll_layout.addWidget(self._assets_section)
        self.assets_tree.startDrag = self._start_asset_drag
        self.assets_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.assets_tree.customContextMenuRequested.connect(self._assets_context_menu)
        self.assets_tree.itemDoubleClicked.connect(self._on_asset_double_clicked)

        # ---- Outliner section ----
        self._outliner_section = _CollapsibleSection("SCENE OUTLINER")
        self.outliner_tree = OutlinerTreeWidget()
        self.outliner_tree.setHeaderHidden(True)
        self.outliner_tree.setStyleSheet(TREE_SS)
        self.outliner_tree.setDragEnabled(True)
        self.outliner_tree.setAcceptDrops(True)
        self.outliner_tree.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.outliner_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.outliner_tree.customContextMenuRequested.connect(self._outliner_context_menu)
        self.outliner_tree.itemSelectionChanged.connect(self._on_outliner_select)
        self.outliner_tree.itemDoubleClicked.connect(self._on_outliner_rename)
        self.outliner_tree.reparent_requested.connect(
            lambda c, p: self.object_select_requested.emit(f"reparent:{c}:{p}")
        )
        self._outliner_section.content_layout.addWidget(self.outliner_tree)
        scroll_layout.addWidget(self._outliner_section)

        # ---- Primitives section ----
        self._primitives_section = _CollapsibleSection("PRIMITIVES")
        
        prims_container = QWidget()
        prims_layout = QVBoxLayout(prims_container)
        prims_layout.setContentsMargins(0,0,0,0); prims_layout.setSpacing(0)
        
        self.primitive_search = QLineEdit()
        self.primitive_search.setPlaceholderText("Search primitives...")
        self.primitive_search.setStyleSheet("""
            QLineEdit { background: #1e1e1e; color: #ccc; border: none; padding: 4px 8px; font-size: 10px; border-bottom: 1px solid #333; }
        """)
        self.primitive_search.textChanged.connect(self._populate_primitives)
        prims_layout.addWidget(self.primitive_search)
        
        self.primitives_tree = QTreeWidget()
        self.primitives_tree.setHeaderHidden(True)
        self.primitives_tree.setStyleSheet(TREE_SS)
        self.primitives_tree.setDragEnabled(True)
        self.primitives_tree.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        self.primitives_tree.setMinimumHeight(180)
        self.primitives_tree.startDrag = self._start_primitive_drag
        prims_layout.addWidget(self.primitives_tree)
        
        self._primitives_section.content_layout.addWidget(prims_container)
        scroll_layout.addWidget(self._primitives_section)
        self._populate_primitives()

        scroll_layout.addStretch()
        scroll.setWidget(scroll_content)
        main_layout.addWidget(scroll, 1)

    def set_workspace_root(self, path):
        self._workspace_root = Path(path) if path else None
        self.refresh_assets()

    def _open_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Open Folder", str(self._workspace_root or ""))
        if folder:
            self.set_workspace_root(folder)

    def _new_file(self):
        name, ok = QInputDialog.getText(self, "New File", "File name:")
        if ok and name:
            folder = self._workspace_root or Path(".")
            item = self.assets_tree.currentItem()
            if item:
                p = Path(item.data(0, Qt.ItemDataRole.UserRole))
                if p.is_dir(): folder = p
                else: folder = p.parent
            
            path = folder / name
            try:
                path.touch()
                self.refresh_assets()
            except Exception as e:
                print(f"Failed to create file: {e}")

    def _on_mode_tab_changed(self, idx):
        modes = ["3D", "2D", "Pure", "UI"]
        mode = modes[idx]
        self._mode = mode
        self.mode_changed.emit(mode)
        # Visibility logic for sections
        is_vp = mode in ("2D", "3D")
        self._primitives_section.setVisible(is_vp)
        self._outliner_section.setVisible(is_vp)

    def set_mode(self, mode):
        self._mode = mode
        self._populate_primitives()
        self.refresh_assets()

    def _populate_primitives(self):
        self.primitives_tree.clear()
        search_text = self.primitive_search.text().lower()
        
        if self._mode == "3D":
             categories = {
                 "Basic Shapes": [("Cube","cube"),("Sphere","sphere"),("Cylinder","cylinder"),("Plane","plane"),("Landscape","landscape"),("Ocean","ocean"),("Cone","cone")],
                 "Lighting": [("Point Light","light_point"),("Directional Light","light_directional")],
                 "Camera": [("Camera","camera")]
             }
        elif self._mode == "2D":
             categories = {
                 "Shapes": [("Rectangle","rect"),("Circle","circle"),("Sprite","sprite")]
             }
        else:
             categories = {}
             
        for cat_name, items in categories.items():
            cat_item = QTreeWidgetItem([cat_name])
            cat_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            cat_item.setForeground(0, QColor("#888"))
            cat_item.setBackground(0, QColor("#2d2d2d"))
            cat_item.setFont(0, QFont("Segoe UI", 8, QFont.Weight.Bold))
            
            visible_count = 0
            for display_name, type_name in items:
                if search_text and search_text not in display_name.lower():
                    continue
                item = QTreeWidgetItem(cat_item, [f"  {display_name}"])
                item.setData(0, Qt.ItemDataRole.UserRole, type_name)
                item.setToolTip(0, f"Drag onto viewport to create a {display_name}")
                visible_count += 1
            
            if visible_count > 0:
                self.primitives_tree.addTopLevelItem(cat_item)
                cat_item.setExpanded(True)

    def _start_primitive_drag(self, supported_actions):
        item = self.primitives_tree.currentItem()
        if not item or not item.data(0, Qt.ItemDataRole.UserRole): return
        drag = QDrag(self.primitives_tree)
        mime = QMimeData()
        mime.setText(item.data(0, Qt.ItemDataRole.UserRole))
        drag.setMimeData(mime)
        px = QPixmap(100, 24); px.fill(QColor("#333"))
        p = QPainter(px)
        p.setPen(QColor("#4fc3f7")); p.setFont(QFont("Segoe UI", 10))
        p.drawText(px.rect(), Qt.AlignmentFlag.AlignCenter, item.text(0).strip()); p.end()
        drag.setPixmap(px)
        drag.exec(Qt.DropAction.CopyAction)

    def _start_asset_drag(self, supported_actions):
        item = self.assets_tree.currentItem()
        if not item: return
        file_path = item.data(0, Qt.ItemDataRole.UserRole)
        if not file_path: return
        drag = QDrag(self.assets_tree)
        mime = QMimeData()
        # Prefix .material files with 'mat:' so viewport can differentiate
        if file_path.endswith('.material'):
            mime.setText(f"mat:{file_path}")
        else:
            mime.setText(f"file:{file_path}")
        drag.setMimeData(mime)
        px = QPixmap(140, 24); px.fill(QColor("#333"))
        p = QPainter(px)
        p.setPen(QColor("#4fc3f7")); p.setFont(QFont("Segoe UI", 9))
        p.drawText(px.rect(), Qt.AlignmentFlag.AlignCenter, Path(file_path).name); p.end()
        drag.setPixmap(px)
        drag.exec(Qt.DropAction.CopyAction)

    def refresh_assets(self):
        """Build a full project folder tree, showing ALL folders and files
        fitting current context (filters skipped extensions)."""
        self.assets_tree.clear()
        root = self._workspace_root
        if not root or not root.exists():
            no_item = QTreeWidgetItem(self.assets_tree, ["No project folder"])
            no_item.setFlags(Qt.ItemFlag.NoItemFlags)
            return

        # Show project root name
        root_item = QTreeWidgetItem(self.assets_tree, [f"📁 {root.name}"])
        root_item.setData(0, Qt.ItemDataRole.UserRole, str(root))
        root_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        root_item.setExpanded(True)

        self._scan_dir_full(root, root_item)
        self.assets_tree.expandToDepth(0)

    def _scan_dir_full(self, path: Path, parent_item, depth=0):
        """Recursively scan directories for the Master Explorer."""
        if depth > 8: return
        try:
            entries = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except PermissionError:
            return
        for entry in entries:
            if entry.name.startswith('.') or entry.name in self.SKIP_DIRS:
                continue
            if entry.is_dir():
                dir_item = QTreeWidgetItem(parent_item, [f"📁 {entry.name}"])
                dir_item.setData(0, Qt.ItemDataRole.UserRole, str(entry))
                dir_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                self._scan_dir_full(entry, dir_item, depth + 1)
            else:
                ext = entry.suffix.lower()
                if ext in self.SKIP_EXTS:
                    continue
                
                icon = "📄 "
                if ext == '.logic': icon = "⚙️ "
                elif ext == '.scene': icon = "🎬 "
                elif ext == '.material': icon = "🎨 "
                elif ext in self.ASSET_3D_EXTS: icon = "🧊 "
                elif ext in self.ASSET_2D_EXTS: icon = "🖼️ "
                elif ext == '.anim': icon = "🎬 "
                elif ext == '.ui': icon = "🖼️ "
                
                file_item = QTreeWidgetItem(parent_item, [f"{icon}{entry.name}"])
                file_item.setData(0, Qt.ItemDataRole.UserRole, str(entry))
                file_item.setToolTip(0, str(entry))
                file_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsDragEnabled)

    def _prune_empty(self, item):
        """Recursively remove child tree items that are folders with no children."""
        i = 0
        while i < item.childCount():
            child = item.child(i)
            if not child.data(0, Qt.ItemDataRole.UserRole):  # it's a folder
                self._prune_empty(child)
                if child.childCount() == 0:
                    item.removeChild(child)
                    continue
            i += 1

    # ---- Asset double-click ----
    def _on_asset_double_clicked(self, item, col):
        file_path = item.data(0, Qt.ItemDataRole.UserRole)
        if not file_path: return
        p = Path(file_path)
        if p.is_file():
            self.file_selected.emit(file_path)
            
            # Auto-open editor for text-like files
            ext = p.suffix.lower()
            if ext in ('.py', '.logic', '.scene', '.json', '.txt', '.material'):
                self._open_in_text_editor(file_path)
            elif ext == '.material':
                self.material_open_requested.emit(file_path)

    def _open_in_text_editor(self, filepath):
        from .node_editor import TextEditorDialog
        dlg = TextEditorDialog(self.window(), filepath)
        dlg.show() # Non-modal so we can keep working
        self._active_editors = getattr(self, '_active_editors', [])
        self._active_editors.append(dlg)

    # ---- Assets context menu ----
    def _assets_context_menu(self, pos):
        import json as _json
        item = self.assets_tree.itemAt(pos)
        path_str = item.data(0, Qt.ItemDataRole.UserRole) if item else None
        
        menu = QMenu(self)
        menu.setStyleSheet(PANEL_SS + " QMenu::item { padding: 4px 20px; }")

        if path_str:
            p = Path(path_str)
            if p.is_file():
                # Edit action
                edit_act = menu.addAction("📝 Edit File")
                edit_act.triggered.connect(lambda: self._open_in_text_editor(path_str))
                menu.addSeparator()

                open_act = menu.addAction("Open")
                open_act.triggered.connect(lambda: self._on_asset_double_clicked(item, 0))
                menu.addSeparator()
            
            rename_act = menu.addAction("Rename")
            delete_act = menu.addAction("Delete")
            menu.addSeparator()

        new_file_act = menu.addAction("New File")
        new_folder_act = menu.addAction("New Folder")
        menu.addSeparator()
        create_mat_act = menu.addAction("Create Material Item")
        menu.addSeparator()
        refresh_act = menu.addAction("Refresh")

        action = menu.exec(self.assets_tree.mapToGlobal(pos))
        
        if action == refresh_act:
            self.refresh_assets()
        elif action == new_file_act:
            self._new_file()
        elif action == new_folder_act:
            self._new_folder()
        elif action == create_mat_act:
            self._create_material_at(path_str)
        elif path_str:
            if 'delete_act' in locals() and action == delete_act:
                self._delete_path(path_str)
            elif 'rename_act' in locals() and action == rename_act:
                self._rename_path(item, path_str)

    def _new_folder(self):
        name, ok = QInputDialog.getText(self, "New Folder", "Folder name:")
        if ok and name:
            folder = self._workspace_root or Path(".")
            item = self.assets_tree.currentItem()
            if item:
                p = Path(item.data(0, Qt.ItemDataRole.UserRole))
                folder = p if p.is_dir() else p.parent
            try:
                (folder / name).mkdir(exist_ok=True)
                self.refresh_assets()
            except Exception as e: QMessageBox.warning(self, "Error", f"Failed: {e}")

    def _rename_path(self, item, path_str):
        p = Path(path_str)
        name, ok = QInputDialog.getText(self, "Rename", "New name:", text=p.name)
        if ok and name:
            new_p = p.parent / name
            try:
                p.rename(new_p)
                self.refresh_assets()
            except Exception as e: QMessageBox.warning(self, "Error", f"Failed: {e}")

    def _delete_path(self, path_str):
        p = Path(path_str)
        if not p.exists(): return
        res = QMessageBox.question(self, "Delete", f"Are you sure you want to delete {p.name}?", 
                                 QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if res == QMessageBox.StandardButton.Yes:
            try:
                if p.is_dir():
                    import shutil
                    shutil.rmtree(p)
                else:
                    p.unlink()
                self.refresh_assets()
            except Exception as e: QMessageBox.warning(self, "Error", f"Failed: {e}")

    def _create_material_at(self, path_str):
        import json as _json
        folder = Path(path_str) if path_str and Path(path_str).is_dir() else self._workspace_root
        if not folder: return
        i = 1
        while (folder / f"material_{i:03d}.material").exists(): i += 1
        path = folder / f"material_{i:03d}.material"
        
        from .scene_editor import MATERIAL_PRESETS # Use presets if available
        try:
            mat_data = dict(MATERIAL_PRESETS['Green Glow'])
            mat_data['name'] = path.stem
            with open(str(path), 'w') as f: _json.dump(mat_data, f, indent=2)
            self.refresh_assets()
        except Exception as e: print(f"Failed to create material: {e}")

    def add_open_graph(self, file_path: str):
        p = Path(file_path)
        for i in range(self.graphs_list.count()):
            if self.graphs_list.item(i).data(Qt.ItemDataRole.UserRole) == file_path:
                self.graphs_list.setCurrentRow(i); return
        icon = "⚙️ " if p.suffix == '.logic' else ("🎬" if p.suffix == '.anim' else "🖼️ ")
        item = QListWidgetItem(f"{icon}{p.name}")
        item.setData(Qt.ItemDataRole.UserRole, file_path)
        self.graphs_list.addItem(item)
        self.graphs_list.setCurrentItem(item)

    def update_library(self, lib_root):
        lib_root.takeChildren()
        for prim in ["Cube", "Sphere", "Cylinder", "Plane", "Cone", "Landscape", "Ocean"]:
            item = QTreeWidgetItem([prim])
            item.setData(0, Qt.ItemDataRole.UserRole, prim.lower())
            item.setIcon(0, QIcon()) # TODO: Add primitive icons
            lib_root.addChild(item)

    def update_graph_outline(self, nodes):
        self.graph_outline_tree.clear()
        for node in nodes:
            node_type = getattr(node, 'node_type', 'Node')
            icon = "⚡" if 'Event' in node_type else "⬢"
            item = QTreeWidgetItem([f"{icon} {node_type}"])
            item.setData(0, Qt.ItemDataRole.UserRole, node)
            self.graph_outline_tree.addTopLevelItem(item)
    # ---- Outliner ----
    def update_outliner(self, objects: List[SceneObject]):
        self.outliner_tree.blockSignals(True)
        self.outliner_tree.clear()

        obj_map = {obj.id: obj for obj in objects}
        item_map = {}

        def get_item(obj: SceneObject):
            if obj.id in item_map: return item_map[obj.id]
            icon_map = {
                'cube':'[C]','sphere':'[S]','cylinder':'[Y]','plane':'[P]',
                'cone':'[N]','rect':'[R]','circle':'[O]','sprite':'[I]','mesh':'[M]',
            }
            prefix = icon_map.get(obj.obj_type, '[?]')
            label = f"{prefix} {obj.name}"
            item = QTreeWidgetItem([label])
            item.setData(0, Qt.ItemDataRole.UserRole, obj.id)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsDragEnabled | Qt.ItemFlag.ItemIsDropEnabled)
            if obj.selected:
                item.setForeground(0, QColor("#4fc3f7"))
                item.setSelected(True)
            item_map[obj.id] = item
            return item

        # First pass: Create all items
        for obj in objects:
            get_item(obj)

        # Second pass: Build hierarchy
        for obj in objects:
            item = item_map[obj.id]
            if obj.parent_id and obj.parent_id in item_map:
                parent_item = item_map[obj.parent_id]
                parent_item.addChild(item)
            else:
                self.outliner_tree.addTopLevelItem(item)

        self.outliner_tree.expandAll()
        self.outliner_tree.blockSignals(False)

    def _on_outliner_select(self):
        sel = self.outliner_tree.selectedItems()
        if sel: self.object_select_requested.emit(sel[0].data(0, Qt.ItemDataRole.UserRole))
        else: self.object_select_requested.emit(None)

    def _on_outliner_rename(self, item, col):
        obj_id = item.data(0, Qt.ItemDataRole.UserRole)
        if obj_id: self.object_select_requested.emit(f"rename:{obj_id}")

    def _outliner_context_menu(self, pos):
        item = self.outliner_tree.itemAt(pos)
        if not item: return
        obj_id = item.data(0, Qt.ItemDataRole.UserRole)
        if not obj_id: return

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background: #2a2a2a; color: #e0e0e0; border: 1px solid #555; }
            QMenu::item { padding: 6px 20px; }
            QMenu::item:selected { background: #4fc3f7; color: #1a1a1a; }
        """)
        rename_act = menu.addAction("Rename")
        delete_act = menu.addAction("Delete")
        menu.addSeparator()
        ref_act = menu.addAction("Create Logic Reference")
        
        action = menu.exec(self.outliner_tree.mapToGlobal(pos))
        
        if action == rename_act:
            self.object_select_requested.emit(f"rename:{obj_id}")
        elif action == delete_act:
            self.object_select_requested.emit(f"delete:{obj_id}")
        elif action == ref_act:
            self.object_select_requested.emit(f"create_ref:{obj_id}")


# ===================================================================
# Scene Toolbar
# ===================================================================

class SceneToolbar(QWidget):
    mode_changed = pyqtSignal(str)
    grid_toggled = pyqtSignal(bool)
    snap_toggled = pyqtSignal(bool)
    grid_size_changed = pyqtSignal(float)
    transform_changed = pyqtSignal(str)

    play_clicked = pyqtSignal()   # New!

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SceneToolbar"); self.setFixedHeight(32)
        self.setStyleSheet(TOOLBAR_SS)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8,0,8,0); layout.setSpacing(6)

        self.play_btn = QToolButton(); self.play_btn.setText("▶ Play")
        self.play_btn.setStyleSheet("""
            QToolButton { background: #4caf50; color: white; border: none; border-radius: 4px; padding: 4px 10px; font-weight: bold; margin-right: 5px; }
            QToolButton:hover { background: #66bb6a; }
        """)
        self.play_btn.clicked.connect(self.play_clicked.emit)
        layout.addWidget(self.play_btn)

        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["3D", "2D", "Pure", "UI"])
        self.mode_combo.setStyleSheet(COMBO_SS)
        self.mode_combo.currentTextChanged.connect(self.mode_changed.emit)
        layout.addWidget(self.mode_combo)

        sep1 = QFrame(); sep1.setFrameShape(QFrame.Shape.VLine); sep1.setStyleSheet("color:#555;")
        layout.addWidget(sep1)

        self.move_btn = QToolButton(); self.move_btn.setText("Move"); self.move_btn.setCheckable(True); self.move_btn.setChecked(True)
        self.move_btn.setStyleSheet(BTN_SS); layout.addWidget(self.move_btn)
        self.rotate_btn = QToolButton(); self.rotate_btn.setText("Rotate"); self.rotate_btn.setCheckable(True)
        self.rotate_btn.setStyleSheet(BTN_SS); layout.addWidget(self.rotate_btn)
        self.scale_btn = QToolButton(); self.scale_btn.setText("Scale"); self.scale_btn.setCheckable(True)
        self.scale_btn.setStyleSheet(BTN_SS); layout.addWidget(self.scale_btn)
        self._tg = QButtonGroup(self); self._tg.setExclusive(True)
        self._tg.addButton(self.move_btn); self._tg.addButton(self.rotate_btn); self._tg.addButton(self.scale_btn)
        self._tg.buttonClicked.connect(self._on_transform_btn)

        sep2 = QFrame(); sep2.setFrameShape(QFrame.Shape.VLine); sep2.setStyleSheet("color:#555;")
        layout.addWidget(sep2)

        self.grid_check = QCheckBox("Grid"); self.grid_check.setChecked(True)
        self.grid_check.setStyleSheet("color:#ccc;font-size:11px;")
        self.grid_check.toggled.connect(self.grid_toggled.emit); layout.addWidget(self.grid_check)
        self.snap_check = QCheckBox("Snap"); self.snap_check.setChecked(False)
        self.snap_check.setStyleSheet("color:#ccc;font-size:11px;")
        self.snap_check.toggled.connect(self.snap_toggled.emit); layout.addWidget(self.snap_check)
        
        self.space_combo = QComboBox()
        self.space_combo.addItems(["Global", "Local"])
        self.space_combo.setStyleSheet(COMBO_SS)
        layout.addWidget(self.space_combo)

        grid_lbl = QLabel("Grid:"); grid_lbl.setStyleSheet(LABEL_SS); layout.addWidget(grid_lbl)
        self.grid_spin = QDoubleSpinBox()
        self.grid_spin.setRange(0.1,100.0); self.grid_spin.setValue(1.0); self.grid_spin.setSingleStep(0.5)
        self.grid_spin.setDecimals(1); self.grid_spin.setSuffix(" u"); self.grid_spin.setFixedWidth(80)
        self.grid_spin.setStyleSheet("QDoubleSpinBox{background:#3a3a3a;border:1px solid #555;border-radius:4px;color:#e0e0e0;padding:2px 4px;font-size:11px;}QDoubleSpinBox:hover{border-color:#4fc3f7;}")
        self.grid_spin.valueChanged.connect(self.grid_size_changed.emit); layout.addWidget(self.grid_spin)

        layout.addStretch()

        sep3 = QFrame(); sep3.setFrameShape(QFrame.Shape.VLine); sep3.setStyleSheet("color:#555;")
        layout.addWidget(sep3)
        self.cam_label = QLabel("Pos: 0, 5, 10  |  FPS: --")
        self.cam_label.setStyleSheet(LABEL_SS); layout.addWidget(self.cam_label)

        sep4 = QFrame(); sep4.setFrameShape(QFrame.Shape.VLine); sep4.setStyleSheet("color:#555;")
        layout.addWidget(sep4)
        
        self.cam_preset_combo = QComboBox()
        self.cam_preset_combo.addItems(["Perspective", "Top", "Front", "Right"])
        self.cam_preset_combo.setStyleSheet(COMBO_SS)
        layout.addWidget(self.cam_preset_combo)

        sep5 = QFrame(); sep5.setFrameShape(QFrame.Shape.VLine); sep5.setStyleSheet("color:#555;")
        layout.addWidget(sep5)
        self.play_btn = QPushButton("Play"); self.play_btn.setStyleSheet(BTN_SS)
        self.play_btn.setToolTip("Play scene (future)"); self.play_btn.setEnabled(False)
        layout.addWidget(self.play_btn)

    def _on_mode_tab_changed(self, idx):
        modes = ["3D", "2D", "Pure", "UI"]
        text = modes[idx]
        self.mode_changed.emit(text)
        is_vp = text in ("2D", "3D")
        for w in (self.move_btn, self.rotate_btn, self.scale_btn, self.grid_check, self.snap_check, self.grid_spin, self.space_combo):
            w.setEnabled(is_vp)

    def _on_transform_btn(self, btn):
        m = {"Move":"move","Rotate":"rotate","Scale":"scale"}
        self.transform_changed.emit(m.get(btn.text(), "move"))

    def update_cam_info(self, pos_str, fps):
        self.cam_label.setText(f"Pos: {pos_str}  |  FPS: {fps}")


# ===================================================================
# Pure mode placeholder
# ===================================================================

class PurePlaceholder(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: #1e1e1e;")
        layout = QVBoxLayout(self); layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon = QLabel("<<>>"); icon.setStyleSheet("font-size: 48px; color: #4fc3f7;")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter); layout.addWidget(icon)
        title = QLabel("Pure Logic Mode")
        title.setStyleSheet("font-size: 22px; font-weight: bold; color: #e0e0e0;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter); layout.addWidget(title)
        desc = QLabel("No scene viewport -- this project uses logic graphs only.\nSwitch to 2D or 3D to open the scene editor.")
        desc.setStyleSheet("font-size: 13px; color: #888; margin-top: 8px;")
        desc.setWordWrap(True); desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(desc)


# ===================================================================
# Material Editor Panel (opens when double-clicking .material files)
# ===================================================================

class MaterialEditorPanel(QWidget):
    """Inline material property editor for .material JSON files."""
    material_saved = pyqtSignal(str)  # emitted with filepath after save

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: #252526;")
        self._file_path = None
        self._mat_data = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Header
        self._title = QLabel("Material Editor")
        self._title.setStyleSheet("color: #4fc3f7; font-size: 14px; font-weight: bold;")
        layout.addWidget(self._title)

        self._file_label = QLabel("")
        self._file_label.setStyleSheet("color: #888; font-size: 10px;")
        layout.addWidget(self._file_label)

        # Preset
        preset_row = QHBoxLayout()
        preset_row.addWidget(QLabel("Preset"))
        self._preset_combo = QComboBox()
        self._preset_combo.addItems(['Plastic', 'Glass', 'Metal', 'Green Glow', 'Custom'])
        self._preset_combo.setStyleSheet(COMBO_SS)
        self._preset_combo.currentTextChanged.connect(self._on_preset_changed)
        preset_row.addWidget(self._preset_combo, 1)
        layout.addLayout(preset_row)

        # Base Color
        bc_row = QHBoxLayout()
        bc_row.addWidget(QLabel("Base Color"))
        self._bc_btn = QPushButton()
        self._bc_btn.setFixedSize(60, 20)
        self._bc_btn.setStyleSheet("background: #ccc; border: 1px solid #555; border-radius: 3px;")
        self._bc_btn.clicked.connect(self._pick_base_color)
        bc_row.addWidget(self._bc_btn)
        layout.addLayout(bc_row)

        # Roughness
        r_row = QHBoxLayout()
        r_row.addWidget(QLabel("Roughness"))
        self._r_slider = QSlider(Qt.Orientation.Horizontal)
        self._r_slider.setRange(0, 100); self._r_slider.setValue(70)
        self._r_slider.setStyleSheet("QSlider::groove:horizontal{background:#333;height:6px;border-radius:3px;}QSlider::handle:horizontal{background:#4fc3f7;width:14px;margin:-4px 0;border-radius:7px;}")
        self._r_slider.valueChanged.connect(self._on_value_changed)
        r_row.addWidget(self._r_slider, 1)
        self._r_val = QLabel("0.70")
        self._r_val.setFixedWidth(32)
        r_row.addWidget(self._r_val)
        layout.addLayout(r_row)

        # Metallic
        m_row = QHBoxLayout()
        m_row.addWidget(QLabel("Metallic"))
        self._m_slider = QSlider(Qt.Orientation.Horizontal)
        self._m_slider.setRange(0, 100); self._m_slider.setValue(0)
        self._m_slider.setStyleSheet(self._r_slider.styleSheet())
        self._m_slider.valueChanged.connect(self._on_value_changed)
        m_row.addWidget(self._m_slider, 1)
        self._m_val = QLabel("0.00")
        self._m_val.setFixedWidth(32)
        m_row.addWidget(self._m_val)
        layout.addLayout(m_row)

        # Emissive
        e_row = QHBoxLayout()
        e_row.addWidget(QLabel("Emissive"))
        self._ec_btn = QPushButton()
        self._ec_btn.setFixedSize(60, 20)
        self._ec_btn.setStyleSheet("background: #000; border: 1px solid #555; border-radius: 3px;")
        self._ec_btn.clicked.connect(self._pick_emissive_color)
        e_row.addWidget(self._ec_btn)
        layout.addLayout(e_row)

        # Save button
        save_btn = QPushButton("Save Material")
        save_btn.setStyleSheet("""
            QPushButton { background: #4CAF50; color: white; border: none;
                         padding: 8px; border-radius: 4px; font-weight: bold; }
            QPushButton:hover { background: #66BB6A; }
        """)
        save_btn.clicked.connect(self._save)
        layout.addWidget(save_btn)

        layout.addStretch()

        # Style all labels
        for child in self.findChildren(QLabel):
            if child != self._title and child != self._file_label:
                child.setStyleSheet("color: #aaa; font-size: 11px;")

    def load_material(self, filepath):
        import json as _json
        self._file_path = filepath
        try:
            with open(filepath, 'r') as f:
                self._mat_data = _json.load(f)
        except Exception:
            self._mat_data = dict(DEFAULT_MATERIAL)
        self._file_label.setText(Path(filepath).name)
        self._title.setText(f"Material: {self._mat_data.get('name', Path(filepath).stem)}")
        self._sync_ui()

    def _sync_ui(self):
        d = self._mat_data
        idx = self._preset_combo.findText(d.get('preset', 'Custom'))
        self._preset_combo.blockSignals(True)
        self._preset_combo.setCurrentIndex(idx if idx >= 0 else self._preset_combo.count() - 1)
        self._preset_combo.blockSignals(False)
        bc = d.get('base_color', [0.8, 0.8, 0.8, 1.0])
        self._bc_btn.setStyleSheet(f"background: rgb({int(bc[0]*255)},{int(bc[1]*255)},{int(bc[2]*255)}); border: 1px solid #555; border-radius: 3px;")
        self._r_slider.blockSignals(True); self._r_slider.setValue(int(d.get('roughness', 0.7) * 100)); self._r_slider.blockSignals(False)
        self._r_val.setText(f"{d.get('roughness', 0.7):.2f}")
        self._m_slider.blockSignals(True); self._m_slider.setValue(int(d.get('metallic', 0.0) * 100)); self._m_slider.blockSignals(False)
        self._m_val.setText(f"{d.get('metallic', 0.0):.2f}")
        ec = d.get('emissive_color', [0, 0, 0, 1])
        self._ec_btn.setStyleSheet(f"background: rgb({int(ec[0]*255)},{int(ec[1]*255)},{int(ec[2]*255)}); border: 1px solid #555; border-radius: 3px;")

    def _on_preset_changed(self, name):
        if name in MATERIAL_PRESETS:
            self._mat_data = dict(MATERIAL_PRESETS[name])
            self._mat_data['preset'] = name
            self._mat_data['name'] = Path(self._file_path).stem if self._file_path else 'material'
            self._sync_ui()

    def _pick_base_color(self):
        bc = self._mat_data.get('base_color', [0.8, 0.8, 0.8, 1.0])
        color = QColorDialog.getColor(QColor(int(bc[0]*255), int(bc[1]*255), int(bc[2]*255)), self, "Base Color")
        if color.isValid():
            self._mat_data['base_color'] = [color.redF(), color.greenF(), color.blueF(), 1.0]
            self._mat_data['preset'] = 'Custom'
            self._sync_ui()

    def _pick_emissive_color(self):
        ec = self._mat_data.get('emissive_color', [0, 0, 0, 1])
        color = QColorDialog.getColor(QColor(int(ec[0]*255), int(ec[1]*255), int(ec[2]*255)), self, "Emissive Color")
        if color.isValid():
            self._mat_data['emissive_color'] = [color.redF(), color.greenF(), color.blueF(), 1.0]
            self._mat_data['preset'] = 'Custom'
            self._sync_ui()

    def _on_value_changed(self):
        self._mat_data['roughness'] = self._r_slider.value() / 100.0
        self._mat_data['metallic'] = self._m_slider.value() / 100.0
        self._r_val.setText(f"{self._mat_data['roughness']:.2f}")
        self._m_val.setText(f"{self._mat_data['metallic']:.2f}")
        self._mat_data['preset'] = 'Custom'
        self._preset_combo.blockSignals(True)
        self._preset_combo.setCurrentText('Custom')
        self._preset_combo.blockSignals(False)

    def _save(self):
        import json as _json
        if not self._file_path: return
        try:
            with open(self._file_path, 'w') as f:
                _json.dump(self._mat_data, f, indent=2)
            self.material_saved.emit(self._file_path)
        except Exception as e:
            print(f"Failed to save material: {e}")


# ===================================================================
# Main Scene Editor Container
# ===================================================================

class SceneEditorWidget(QWidget):
    """
    The Viewport tab: toolbar + [explorer | viewport/UI builder].
    Replaces both the old Game tab and the standalone UI tab.
    """

    mode_changed = pyqtSignal(str)
    create_reference_requested = pyqtSignal(str)
    state_about_to_change = pyqtSignal()
    state_changed = pyqtSignal()

    def __init__(self, parent=None, explorer=None, properties=None):
        super().__init__(parent)
        self.setObjectName("SceneEditor")
        self._current_mode = "3D"
        self._logic_data = {}
        self._scene_file = None
        self._object_counter = {}

        self.undo_stack = []
        self.redo_stack = []
        self._is_undoing = False
        self.max_undo_steps = 50

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0,0,0,0); outer.setSpacing(0)

        # Central area: Toolbar + Stack
        self.central_container = QWidget()
        central_layout = QVBoxLayout(self.central_container)
        central_layout.setContentsMargins(0,0,0,0); central_layout.setSpacing(0)
        
        self.toolbar = SceneToolbar(self)
        central_layout.addWidget(self.toolbar)

        self._stack = QStackedWidget(self)
        self._stack.setStyleSheet("background: #1e1e1e;")
        central_layout.addWidget(self._stack, 1)
        
        outer.addWidget(self.central_container)

        self.viewport = SceneViewport(self)
        self._stack.addWidget(self.viewport)         # 0
        self.toolbar.play_clicked.connect(self._on_play_clicked)

        self.pure_placeholder = PurePlaceholder(self)
        self._stack.addWidget(self.pure_placeholder)  # 1

        self._ui_placeholder = QLabel("UI Builder not loaded")
        self._ui_placeholder.setStyleSheet("color: #888; font-size: 14px; background: #1e1e1e;")
        self._ui_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._stack.addWidget(self._ui_placeholder)   # 2

        # Use injected global panels or fallback (fallback only for safety)
        self.explorer = explorer
        self.properties = properties
        if self.explorer:
            self.explorer.properties = properties
        self.properties_stack = QStackedWidget()
        if self.properties:
            self.properties_stack.addWidget(self.properties)
        self.properties_stack.setMinimumWidth(220)

        # FPS timer
        self._fps_timer = QTimer(self)
        self._fps_timer.timeout.connect(self._update_cam_info)
        self._fps_timer.start(250)
        self._current_fps = 0
        if hasattr(self.viewport, 'fps_updated'):
            self.viewport.fps_updated.connect(lambda f: setattr(self, '_current_fps', f))

        # Outliner refresh timer
        self._outliner_timer = QTimer(self)
        self._outliner_timer.timeout.connect(self._refresh_outliner)
        self._outliner_timer.start(1000)
        self._outliner_dirty = True

        # Connect signals
        self.toolbar.grid_toggled.connect(self.viewport.set_show_grid)
        self.toolbar.snap_toggled.connect(self.viewport.set_snap_enabled)
        self.toolbar.grid_size_changed.connect(self.viewport.set_grid_size)
        self.toolbar.transform_changed.connect(self.viewport.set_transform_mode)
        self.toolbar.space_combo.currentTextChanged.connect(self.viewport.set_transform_space)
        self.toolbar.cam_preset_combo.currentTextChanged.connect(self._on_cam_preset)

        self.viewport.object_dropped.connect(self._on_object_dropped)
        self.viewport.object_selected.connect(self._on_object_selected)
        self.viewport.object_moved.connect(self._on_object_moved)
        self.viewport.state_about_to_change.connect(self._save_state)
        self.state_about_to_change.connect(self._save_state)
        # self.viewport.state_changed.connect(...) -> removed, we save BEFORE now

        self.explorer.object_select_requested.connect(self._on_outliner_action)
        self.explorer.outliner_tree.reparent_requested.connect(self._on_reparent_requested)
        self.explorer.material_open_requested.connect(self._open_material_editor)
        self.toolbar.mode_changed.connect(self._on_mode_changed)
        self.properties.property_changed.connect(self._on_property_changed)

        # Material editor (lazy)
        self._material_editor = None

        # Undo/Redo shortcuts
        QShortcut(QKeySequence("Ctrl+Z"), self).activated.connect(self.undo)
        QShortcut(QKeySequence("Ctrl+Y"), self).activated.connect(self.redo)
        
        QTimer.singleShot(0, self._save_state)

    def _on_property_changed(self):
        self.viewport.update()
        self._save_state()

    def _open_material_editor(self, filepath):
        """Open material editor in the property stack."""
        if not self._material_editor:
            self._material_editor = MaterialEditorPanel(self)
            self._material_editor.material_saved.connect(lambda fp: self.explorer.refresh_assets())
            self.properties_stack.addWidget(self._material_editor)
        self._material_editor.load_material(filepath)
        self.properties_stack.setCurrentWidget(self._material_editor)

    def _show_properties_panel(self):
        """Restore the object properties panel."""
        self.properties_stack.setCurrentWidget(self.properties)

    def set_ui_builder(self, builder):
        self._ui_builder = builder
        old = self._stack.widget(2)
        self._stack.removeWidget(old); old.deleteLater()
        self._stack.insertWidget(2, builder)

    def _on_cam_preset(self, text):
        if not hasattr(self.viewport, '_cam3d'): return
        c = self.viewport._cam3d
        c2 = self.viewport._cam2d
        if text == "Perspective":
            c.pos = [0.0, 5.0, 10.0]; c.pitch = -20.0; c.yaw = -90.0
        elif text == "Top":
            c.pos = [0.0, 20.0, 0.0]; c.pitch = -89.9; c.yaw = -90.0
            c2.x = 0; c2.y = 0;
        elif text == "Front":
            c.pos = [0.0, 0.0, 15.0]; c.pitch = 0.0; c.yaw = -90.0
        elif text == "Right":
            c.pos = [15.0, 0.0, 0.0]; c.pitch = 0.0; c.yaw = 180.0
        self.viewport.update()

    def _on_mode_changed(self, mode):
        self._current_mode = mode
        self.mode_changed.emit(mode)
        self.explorer.set_mode(mode)
        if mode == "Pure":
            self.viewport.stop_render_loop(); self._stack.setCurrentIndex(1); return
        if mode == "UI":
            self.viewport.stop_render_loop(); self._stack.setCurrentIndex(2); return
        self._stack.setCurrentIndex(0)
        self.viewport.set_mode(mode); self.viewport.start_render_loop()

    def _on_transform_changed(self, mode):
        self.viewport.set_transform_mode(mode)

    def _next_name(self, obj_type):
        count = self._object_counter.get(obj_type, 0)
        self._object_counter[obj_type] = count + 1
        display = obj_type.capitalize()
        return f"{display}_{count}" if count > 0 else display

    def _save_state(self):
        if self._is_undoing: return
        # Filter out procedurally spawned objects so they don't bloat undo history
        state = [obj.to_dict() for obj in self.viewport.scene_objects if not getattr(obj, 'is_procedural', False)]
        self.undo_stack.append(state)
        if len(self.undo_stack) > self.max_undo_steps:
            self.undo_stack.pop(0)
        self.redo_stack.clear()
        self._outliner_dirty = True
        self._refresh_outliner()
        
    def undo(self):
        if not self.undo_stack: return
        self._is_undoing = True
        
        # Save where we are now to redo stack (filtering out procedural objects)
        current_state = [obj.to_dict() for obj in self.viewport.scene_objects if not getattr(obj, 'is_procedural', False)]
        
        # Pop the most recent state
        last_state = self.undo_stack.pop()
        
        # If the state we just popped is exactly where we are now (e.g. Save was called AFTER change),
        # we need to go back one more level to actually "undo" something.
        if last_state == current_state and self.undo_stack:
            self.redo_stack.append(last_state)
            last_state = self.undo_stack.pop()
        else:
            self.redo_stack.append(current_state)

        self.viewport.scene_objects = [SceneObject.from_dict(d) for d in last_state]
        self.explorer.update_outliner(self.viewport.scene_objects)
        selected = [o for o in self.viewport.scene_objects if o.selected]
        if selected: self.properties.set_object(selected[-1])
        else: self.properties.set_object(None)
        self.viewport.update()
        self._is_undoing = False
        
    def redo(self):
        if not self.redo_stack: return
        self._is_undoing = True
        current_state = [obj.to_dict() for obj in self.viewport.scene_objects if not getattr(obj, 'is_procedural', False)]
        self.undo_stack.append(current_state)
        next_state = self.redo_stack.pop()
        self.viewport.scene_objects = [SceneObject.from_dict(d) for d in next_state]
        self.explorer.update_outliner(self.viewport.scene_objects)
        selected = [o for o in self.viewport.scene_objects if o.selected]
        if selected: self.properties.set_object(selected[-1])
        else: self.properties.set_object(None)
        self.viewport.update()
        self._is_undoing = False

    def _on_object_dropped(self, type_str, wx, wz, mx, my):
        self.state_about_to_change.emit()
        if self.viewport.snap_enabled:
            gs = self.viewport.grid_size
            wx = round(wx / gs) * gs; wz = round(wz / gs) * gs
        
        # Pick target for parenting
        picked = self.viewport._pick_object_3d(mx, my) if self._current_mode == "3D" else self.viewport._pick_object_2d(mx, my)

        if type_str.startswith("logic:"):
            file_path = type_str[6:]
            obj = SceneObject(Path(file_path).stem, "logic")
            obj.file_path = file_path
            # Logic components are small diamond icons
            obj.scale = [0.5, 0.5, 0.5]
            obj.position = [wx, 0.5 if self._current_mode == "3D" else wz, wz if self._current_mode == "3D" else 0.0]
            
            if picked: obj.parent_id = picked.id
        elif type_str.startswith("file:"):
            name = self._next_name(type_str)
            obj = SceneObject(name, type_str)
            if self._current_mode == "3D":
                y_pos = 0.5 if type_str != 'plane' else 0.0
                if self.viewport.snap_enabled: y_pos = round(y_pos / self.viewport.grid_size) * self.viewport.grid_size
                obj.position = [wx, y_pos, wz]
            else:
                obj.position = [wx, wz, 0.0]
        else:
            # Basic primitives (cube, sphere, light_point, camera, etc.)
            name = self._next_name(type_str)
            obj = SceneObject(name, type_str)
            if self._current_mode == "3D":
                # Default elevation for 3D
                y_pos = 1.0 if "light" in type_str or type_str == "camera" else 0.5
                if type_str in ("plane", "landscape", "ocean"): y_pos = 0.0
                obj.position = [wx, y_pos, wz]
            else:
                obj.position = [wx, wz, 0.0]
        self.viewport.scene_objects.append(obj)
        for o in self.viewport.scene_objects: o.selected = False
        obj.selected = True
        self.viewport.object_selected.emit(obj)
        self._outliner_dirty = True
        self._refresh_outliner()

    def _on_object_selected(self, obj):
        self._show_properties_panel()
        self.properties.set_object(obj)
        self._refresh_outliner()

    def _on_reparent_requested(self, child_id, parent_id):
        # Update SceneObject hierarchy
        child = next((o for o in self.viewport.scene_objects if o.id == child_id), None)
        if not child: return
        
        # Prevent cycles
        if parent_id:
            curr = next((o for o in self.viewport.scene_objects if o.id == parent_id), None)
            while curr:
                if curr.id == child_id: return
                curr = next((o for o in self.viewport.scene_objects if o.id == curr.parent_id), None) if curr.parent_id else None

        child.parent_id = parent_id if parent_id else None
        self._outliner_dirty = True
        self._refresh_outliner()
        self._save_state()

    def _select_object_by_id(self, obj_id):
        for o in self.viewport.scene_objects:
            o.selected = (o.id == obj_id)
        selected = next((o for o in self.viewport.scene_objects if o.selected), None)
        self.properties.set_object(selected)

    def _on_play_clicked(self):
        """Open a live simulation window."""
        # Pass `self` so SimulationWindow can fall back to the editor camera
        # if the scene contains no camera object.
        self.sim = SimulationWindow(self.viewport.scene_objects, parent=self)
        self.sim.show()



    def _on_object_moved(self):
        """Called after user finishes dragging an object — sync properties panel."""
        sel = [o for o in self.viewport.scene_objects if o.selected]
        if sel:
            self.properties.refresh_from_object()

    def _refresh_outliner(self):
        if not hasattr(self, "_outliner_dirty") or not self._outliner_dirty:
            return
            
        # Don't refresh if user is dragging an item in the outliner
        if self.explorer.outliner_tree.state() != QAbstractItemView.State.NoState:
            return
            
        # Don't refresh if user is currently transforming an object in the viewport
        if self.viewport._lmb or self.viewport._rmb or self.viewport._mmb:
            return

        self.explorer.update_outliner(self.viewport.scene_objects)
        self._outliner_dirty = False

    def _on_outliner_action(self, action_str):
        if action_str.startswith("rename:"):
            obj_id = action_str[7:]
            for obj in self.viewport.scene_objects:
                if obj.id == obj_id:
                    new_name, ok = QInputDialog.getText(self, "Rename Object", "Name:", text=obj.name)
                    if ok and new_name.strip():
                        obj.name = new_name.strip()
                        self._save_state(); self._refresh_outliner()
                    return
        elif action_str.startswith("delete:"):
            sel = [o for o in self.viewport.scene_objects if o.selected]
            obj_id = action_str[7:]
            # If the deleted ID is part of selection, delete all
            if any(o.id == obj_id for o in sel):
                ids_to_del = {o.id for o in sel}
                self.viewport.scene_objects = [o for o in self.viewport.scene_objects if o.id not in ids_to_del]
            else:
                self.viewport.scene_objects = [o for o in self.viewport.scene_objects if o.id != obj_id]
            self.properties.set_object(None)
            self._save_state(); self._refresh_outliner(); return
        elif action_str.startswith("duplicate:"):
            obj_id = action_str[10:]
            sel = [o for o in self.viewport.scene_objects if o.selected]
            # Batch duplicate if the target is in the selection
            targets = sel if any(o.id == obj_id for o in sel) else [o for o in self.viewport.scene_objects if o.id == obj_id]
            
            new_selection = []
            for obj in list(targets):
                new_obj = SceneObject(obj.name + "_copy", obj.obj_type, [v+1.0 for v in obj.position], list(obj.rotation), list(obj.scale))
                new_obj.color = list(obj.color)
                new_obj.file_path = obj.file_path
                self.viewport.scene_objects.append(new_obj)
                new_selection.append(new_obj)
            
            for o in self.viewport.scene_objects: o.selected = False
            for o in new_selection: o.selected = True
            if new_selection: self.properties.set_object(new_selection[-1])
            self.viewport.update()
            self._outliner_dirty = True; self._refresh_outliner(); self._save_state(); return
        elif action_str.startswith("reparent:"):
            _, child_id, parent_id = action_str.split(":", 2)
            c_obj = next((o for o in self.viewport.scene_objects if o.id == child_id), None)
            if not c_obj: return
            
            # Remove from old parent
            if c_obj.parent_id:
                p_old = next((o for o in self.viewport.scene_objects if o.id == c_obj.parent_id), None)
                if p_old and child_id in p_old.children_ids: p_old.children_ids.remove(child_id)
            
            # Loop prevention
            curr_p = parent_id
            while curr_p:
                if curr_p == child_id: return
                p_obj = next((o for o in self.viewport.scene_objects if o.id == curr_p), None)
                curr_p = p_obj.parent_id if p_obj else None

            c_obj.parent_id = parent_id if parent_id else None
            if parent_id:
                p_new = next((o for o in self.viewport.scene_objects if o.id == parent_id), None)
                if p_new and child_id not in p_new.children_ids: p_new.children_ids.append(child_id)
                
            self._save_state(); self._refresh_outliner()
            return
        elif action_str.startswith("unparent:"):
            obj_id = action_str.split(":", 1)[1]
            c_obj = next((o for o in self.viewport.scene_objects if o.id == obj_id), None)
            if c_obj and c_obj.parent_id:
                p_old = next((o for o in self.viewport.scene_objects if o.id == c_obj.parent_id), None)
                if p_old and obj_id in p_old.children_ids: p_old.children_ids.remove(obj_id)
                c_obj.parent_id = None
                self._save_state(); self._refresh_outliner()
            return
        elif action_str.startswith("create_ref:"):
            obj_id = action_str.split(":", 1)[1]
            self.create_reference_requested.emit(obj_id)
        else:
            for o in self.viewport.scene_objects:
                o.selected = (o.id == action_str)
                if o.selected:
                    self.properties.set_object(o)
            self.viewport.update(); self._refresh_outliner()

    def _update_cam_info(self):
        if self._current_mode == "3D" and hasattr(self.viewport, '_cam3d'):
            c = self.viewport._cam3d
            s = f"{c.pos[0]:.1f}, {c.pos[1]:.1f}, {c.pos[2]:.1f}"
        elif self._current_mode == "2D" and hasattr(self.viewport, '_cam2d'):
            c = self.viewport._cam2d
            s = f"{c.x:.1f}, {c.y:.1f}  Z: {c.zoom_level:.1f}"
        else: s = "--"
        self.toolbar.update_cam_info(s, self._current_fps)

    def on_tab_activated(self):
        if self._current_mode in ("2D", "3D"): self.viewport.start_render_loop()

    def on_tab_deactivated(self):
        self.viewport.stop_render_loop()

    def get_scene_data(self) -> dict:
        data = {
            'mode': self._current_mode,
            'objects': [o.to_dict() for o in self.viewport.scene_objects if not getattr(o, 'is_procedural', False)]
        }
        
        # Save camera state
        if hasattr(self.viewport, '_cam3d'):
             data['camera_3d'] = {
                 'pos': list(self.viewport._cam3d.pos),
                 'yaw': self.viewport._cam3d.yaw,
                 'pitch': self.viewport._cam3d.pitch,
                 'fov': getattr(self.viewport._cam3d, 'fov', 60.0)
             }
        if hasattr(self.viewport, '_cam2d'):
             data['camera_2d'] = {
                 'x': self.viewport._cam2d.x,
                 'y': self.viewport._cam2d.y,
                 'zoom': self.viewport._cam2d.zoom_level
             }
             
        return data

    def load_scene_data(self, data: dict):
        self._current_mode = data.get('mode', '3D')
        self.toolbar.mode_combo.setCurrentText(self._current_mode)
        self.viewport.scene_objects = [SceneObject.from_dict(d) for d in data.get('objects', [])]
        
        # Load camera state
        if 'camera_3d' in data and hasattr(self.viewport, '_cam3d'):
            c = data['camera_3d']
            self.viewport._cam3d.pos = list(c.get('pos', [0,5,10]))
            self.viewport._cam3d.yaw = c.get('yaw', -90.0)
            self.viewport._cam3d.pitch = c.get('pitch', -25.0)
            if 'fov' in c: self.viewport._cam3d.fov = c['fov']
            
        if 'camera_2d' in data and hasattr(self.viewport, '_cam2d'):
            c = data['camera_2d']
            self.viewport._cam2d.x = c.get('x', 0)
            self.viewport._cam2d.y = c.get('y', 0)
            self.viewport._cam2d.zoom_level = c.get('zoom', 1.0)
            
        # Force outliner refresh
        self._outliner_dirty = True
        self._refresh_outliner()
        self.viewport.update()


# ===================================================================
# Simulation Runner
# ===================================================================

class SimulationWindow(QMainWindow):
    def __init__(self, scene_objects, parent=None):
        super().__init__(None)  # No parent to make it a top-level window
        self.setWindowTitle("Live Scene - NodeCanvas")
        self.resize(1024, 768)
        
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0,0,0,0)
        layout.setSpacing(0)
        
        # Add Toolbar for View Control
        toolbar = QWidget()
        toolbar.setFixedHeight(32)
        toolbar.setStyleSheet("background: #333; border-bottom: 1px solid #444;")
        tb_layout = QHBoxLayout(toolbar)
        tb_layout.setContentsMargins(10, 0, 10, 0)
        
        reset_btn = QPushButton("Reset View")
        reset_btn.setFixedWidth(100)
        reset_btn.setStyleSheet("background: #444; color: #eee; border: 1px solid #555; padding: 2px;")
        reset_btn.clicked.connect(self.reset_view)
        tb_layout.addWidget(reset_btn)
        tb_layout.addStretch()
        
        layout.addWidget(toolbar)
        
        self.viewport = SceneViewport(self)
        self.viewport.is_play_mode = True
        self.viewport.set_show_grid(False)
        self.viewport.set_mode("3D") # Default simulation to 3D
        self.viewport.set_transform_mode(None)
        
        # Try to match parent editor mode if provided
        if parent and hasattr(parent, 'viewport'):
             self.viewport.set_mode(parent.viewport._mode)
            
        layout.addWidget(self.viewport)
        
        # Deep copy objects for simulation
        self.viewport.scene_objects = [SceneObject.from_dict(o.to_dict()) for o in scene_objects]
        print(f"[SIM DEBUG] Cloned {len(self.viewport.scene_objects)} objects for simulation.")
        for o in self.viewport.scene_objects:
             print(f"  - Obj: {o.name} Type: {o.obj_type} Visible: {o.visible} Active: {o.active}")

        # Prefer an explicit camera object from the scene. If none exists,
        # fall back to the editor camera (if a parent editor was provided).
        cam_obj = next((o for o in self.viewport.scene_objects if o.obj_type == 'camera'), None)
        if cam_obj:
            # Use the scene camera position/rotation
            self.viewport._cam3d.pos = [float(x) for x in cam_obj.position]
            # Rotation stored as [pitch, yaw, roll] in scene objects.
            # Use -90 to align the scene camera forward vector with the in-scene yaw axis.
            # Negate yaw (rotation[1]) as it is inverted relative to the camera controller.
            self.viewport._cam3d.yaw = -float(cam_obj.rotation[1]) - 90.0
            # Flip pitch sign to match scene rotation convention (down/up)
            self.viewport._cam3d.pitch = float(cam_obj.rotation[0])
            self.viewport._cam3d.fov = float(getattr(cam_obj, 'fov', 60.0))
            self.viewport._active_cam_name = cam_obj.name
            print(f"[RE-DEBUG] Possessing camera '{cam_obj.name}' at {self.viewport._cam3d.pos}")
            try:
                print(f"[RE-DEBUG] cam.front={self.viewport._cam3d.front} cam.up={self.viewport._cam3d.up}")
            except Exception as _e:
                print(f"[RE-DEBUG] failed to compute cam vectors: {_e}")
        elif parent and hasattr(parent, 'viewport') and hasattr(parent.viewport, '_cam3d'):
            # No scene camera — copy the editor camera so the simulation view matches
            src = parent.viewport._cam3d
            self.viewport._cam3d.pos = list(src.pos)
            self.viewport._cam3d.yaw = float(src.yaw)
            self.viewport._cam3d.pitch = float(src.pitch)
            self.viewport._cam3d.fov = float(getattr(src, 'fov', 60.0))
            self.viewport._active_cam_name = getattr(parent.viewport, '_active_cam_name', 'Editor Camera')
            print(f"[RE-DEBUG] No scene camera found — using editor camera at {self.viewport._cam3d.pos}")
            try:
                print(f"[RE-DEBUG] cam.front={self.viewport._cam3d.front} cam.up={self.viewport._cam3d.up}")
            except Exception as _e:
                print(f"[RE-DEBUG] failed to compute cam vectors: {_e}")
        else:
            # No scene camera and no editor parent camera — use defaults from Camera3D
            self.viewport._active_cam_name = "Default Editor"
            print("[RE-DEBUG] No camera found in scene or editor; using default camera.")
        
        # In Play mode, we hide non-visible objects
        for o in self.viewport.scene_objects: 
            o.selected = False
        
        self.setCentralWidget(container)
        # Ensure focus and immediate update
        self.viewport.setFocus()
        
        # Immediate kickstart for the GL context
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(100, self.viewport.update)
        
    def reset_view(self):
        """Emergency reset of the camera view"""
        self.viewport._cam3d.pos = [0.0, 5.0, 10.0]
        self.viewport._cam3d.yaw = -90.0
        self.viewport._cam3d.pitch = -25.0
        self.viewport.update()
        print("Simulation View Reset to [0, 5, 10]")

    def closeEvent(self, event):
        self.viewport.stop_render_loop()
        print("--- Simulation Ended ---")
        event.accept()

# ===================================================================
# Specialized Data Structure Dialogs
# ===================================================================

class NoiseLayerDialog(QDialog):
    def __init__(self, data, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Noise Layer Settings")
        self.setStyleSheet(PANEL_SS + SPIN_SS + COMBO_SS + BTN_SS)
        self.resize(320, 400)
        self.data = dict(data)
        
        layout = QVBoxLayout(self)
        form = QFormLayout()
        
        self.type_cb = QComboBox()
        self.type_cb.addItems(["perlin", "simplex", "worley"])
        self.type_cb.setCurrentText(self.data.get('type', 'perlin'))
        form.addRow("Noise Algorithm", self.type_cb)
        
        self.amp_spin = QDoubleSpinBox()
        self.amp_spin.setRange(0, 1000); self.amp_spin.setValue(self.data.get('amp', 1.0))
        form.addRow("Amplitude", self.amp_spin)
        
        self.freq_spin = QDoubleSpinBox()
        self.freq_spin.setDecimals(4); self.freq_spin.setRange(0.0001, 10.0); self.freq_spin.setValue(self.data.get('freq', 1.0))
        form.addRow("Frequency/Scale", self.freq_spin)
        
        self.oct_spin = QSpinBox()
        self.oct_spin.setRange(1, 12); self.oct_spin.setValue(self.data.get('octaves', 1))
        form.addRow("Octaves", self.oct_spin)
        
        self.pers_spin = QDoubleSpinBox()
        self.pers_spin.setRange(0.0, 1.0); self.pers_spin.setValue(self.data.get('persistence', 0.5))
        form.addRow("Persistence", self.pers_spin)
        
        self.lac_spin = QDoubleSpinBox()
        self.lac_spin.setRange(1.0, 4.0); self.lac_spin.setValue(self.data.get('lacunarity', 2.0))
        form.addRow("Lacunarity", self.lac_spin)
        
        self.mode_cb = QComboBox()
        self.mode_cb.addItems(["fbm", "ridged", "billow"])
        self.mode_cb.setCurrentText(self.data.get('mode', 'fbm'))
        form.addRow("Generation Mode", self.mode_cb)

        self.exp_spin = QDoubleSpinBox()
        self.exp_spin.setRange(0.1, 5.0); self.exp_spin.setValue(self.data.get('exponent', 1.0))
        form.addRow("Redistribution (Exp)", self.exp_spin)

        self.weight_spin = QDoubleSpinBox()
        self.weight_spin.setRange(0.0, 2.0); self.weight_spin.setSingleStep(0.05); self.weight_spin.setValue(self.data.get('weight', 1.0))
        form.addRow("Blending Weight", self.weight_spin)
        
        layout.addLayout(form)
        
        btns = QHBoxLayout()
        ok = QPushButton("Save Settings"); ok.clicked.connect(self.accept)
        cancel = QPushButton("Cancel"); cancel.clicked.connect(self.reject)
        btns.addWidget(ok); btns.addWidget(cancel)
        layout.addLayout(btns)

    def exec(self):
        if super().exec():
            self.data['type'] = self.type_cb.currentText()
            self.data['mode'] = self.mode_cb.currentText()
            self.data['amp'] = self.amp_spin.value()
            self.data['freq'] = self.freq_spin.value()
            self.data['octaves'] = self.oct_spin.value()
            self.data['persistence'] = self.pers_spin.value()
            self.data['lacunarity'] = self.lac_spin.value()
            self.data['exponent'] = self.exp_spin.value()
            self.data['weight'] = self.weight_spin.value()
            return True
        return False

class BiomeDialog(QDialog):
    def __init__(self, data, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Biome Ecological Rule Editor")
        self.setStyleSheet(PANEL_SS + SPIN_SS + BTN_SS)
        self.resize(400, 550)
        self.data = _json.loads(_json.dumps(data)) # Deep copy
        
        import json as _json_local
        self._json_mod = _json_local

        layout = QVBoxLayout(self)
        
        # Identity
        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("Biome Name:"))
        self.name_edit = QLineEdit(self.data.get('name', 'New Biome'))
        name_row.addWidget(self.name_edit)
        layout.addLayout(name_row)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        form = QFormLayout(content)
        
        # Ranges
        def add_range_row(label, key, parent_form):
            row = QHBoxLayout()
            r = self.data.get(key, [0, 1])
            s1 = QDoubleSpinBox(); s1.setRange(-5000, 5000); s1.setValue(r[0])
            s2 = QDoubleSpinBox(); s2.setRange(-5000, 5000); s2.setValue(r[1])
            row.addWidget(s1); row.addWidget(QLabel("to")); row.addWidget(s2)
            parent_form.addRow(label, row)
            return s1, s2

        self.h1, self.h2 = add_range_row("Height Range", "height_range", form)
        self.s1, self.s2 = add_range_row("Slope (0-1)", "slope_range", form)
        self.t1, self.t2 = add_range_row("Temp (0-1)", "temp_range", form)
        self.hm1, self.hm2 = add_range_row("Hum (0-1)", "hum_range", form)
        
        # Surface
        form.addRow(QLabel("<b>Surface Aesthetics</b>"))
        surf = self.data.get('surface', {})
        
        self.color_btn = QPushButton()
        self.color_btn.setFixedHeight(20)
        c = surf.get('color', [0.5, 0.5, 0.5, 1.0])
        self.color_btn.setStyleSheet(f"background: rgba({int(c[0]*255)}, {int(c[1]*255)}, {int(c[2]*255)}, 255);")
        self.color_btn.clicked.connect(self._pick_color)
        form.addRow("Surface Color", self.color_btn)
        
        self.rough_spin = QDoubleSpinBox(); self.rough_spin.setRange(0, 1); self.rough_spin.setValue(surf.get('roughness', 0.7))
        form.addRow("Roughness", self.rough_spin)
        
        self.met_spin = QDoubleSpinBox(); self.met_spin.setRange(0, 1); self.met_spin.setValue(surf.get('metallic', 0.0))
        form.addRow("Metallic", self.met_spin)

        # Spawns
        form.addRow(QLabel("<b>Vegetation / Assets</b>"))
        self.spawn_list = QListWidget()
        for layer in self.data.get('spawns', []):
            d = layer.get('density', 0.1)
            count = len(layer.get('assets', []))
            self.spawn_list.addItem(f"Layer ({count} meshes, {int(d*100)}% density)")
        form.addRow(self.spawn_list)
        
        s_btns = QHBoxLayout()
        add_s = QPushButton("Add Mesh"); add_s.clicked.connect(self._add_spawn)
        rem_s = QPushButton("Remove"); rem_s.clicked.connect(self._rem_spawn)
        s_btns.addWidget(add_s); s_btns.addWidget(rem_s)
        form.addRow(s_btns)
        
        scroll.setWidget(content)
        layout.addWidget(scroll)
        
        btns = QHBoxLayout()
        ok = QPushButton("Save Biome Structure"); ok.clicked.connect(self.accept)
        cancel = QPushButton("Discard"); cancel.clicked.connect(self.reject)
        btns.addWidget(ok); btns.addWidget(cancel)
        layout.addLayout(btns)

    def _pick_color(self):
        c = self.data['surface'].get('color', [0.5, 0.5, 0.5, 1.0])
        color = QColorDialog.getColor(QColor(int(c[0]*255), int(c[1]*255), int(c[2]*255)), self)
        if color.isValid():
            self.data['surface']['color'] = [color.redF(), color.greenF(), color.blueF(), 1.0]
            self.color_btn.setStyleSheet(f"background: {color.name()};")

    def _add_spawn(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Select Mesh Assets", "", "Meshes (*.fbx *.obj *.glb)")
        if files:
            # We add a new "spawn layer" for these assets with default density
            layer = {'assets': files, 'density': 0.1}
            self.data.setdefault('spawns', []).append(layer)
            self.spawn_list.addItem(f"Layer ({len(files)} meshes, 10% density)")

    def _rem_spawn(self):
        idx = self.spawn_list.currentRow()
        if idx >= 0:
            # Note: This is a bit simplified; removing from a list that shows all assets in all layers
            # requires slightly more complex index mapping. For now, we'll clear the layer or item.
            # Real implementation would allow editing the layer directly.
            self.data['spawns'].pop(idx) if idx < len(self.data['spawns']) else None
            self.spawn_list.takeItem(idx)

    def get_data(self):
        self.data['name'] = self.name_edit.text()
        self.data['height_range'] = [self.h1.value(), self.h2.value()]
        self.data['slope_range'] = [self.s1.value(), self.s2.value()]
        self.data['temp_range'] = [self.t1.value(), self.t2.value()]
        self.data['hum_range'] = [self.hm1.value(), self.hm2.value()]
        self.data['surface']['roughness'] = self.rough_spin.value()
        self.data['surface']['metallic'] = self.met_spin.value()
        return self.data
