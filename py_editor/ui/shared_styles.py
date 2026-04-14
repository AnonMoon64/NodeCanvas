"""
shared_styles.py

Centralized stylesheets and UI constants for NodeCanvas.
"""
from PyQt6.QtGui import QColor

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
OBJECT_FACE_COLOR  = (0.25,  0.25,  0.28,  1.0)    # Opaque fill
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
    QListWidget::item:selected { background: #094771; color: #fff; }
"""
TREE_SS = """
    QTreeWidget {
        background: #1e1e1e; border: none; color: #ccc;
        font-size: 12px; outline: none;
    }
    QTreeWidget::item { padding: 3px 4px; }
    QTreeWidget::item:hover { background: #2a2d2e; }
    QTreeWidget::item:selected { background: #094771; color: #fff; }
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
