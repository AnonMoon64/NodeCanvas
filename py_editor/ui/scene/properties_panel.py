"""
properties_panel.py

The Right-side properties inspector with a unified layout.
"""
from pathlib import Path
from functools import partial
from typing import Optional
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QComboBox, QCheckBox, QDoubleSpinBox, QFrame, QSpinBox,
    QToolButton, QGroupBox, QSlider, QColorDialog, QGridLayout, QListWidget, QListWidgetItem,
    QScrollArea, QFileDialog, QInputDialog, QMenu
)
from PyQt6.QtGui import QDragEnterEvent, QDropEvent, QColor
from PyQt6.QtCore import Qt, pyqtSignal

from py_editor.ui.shared_styles import (
    PROPS_SS, SPIN_SS, COMBO_SS, BTN_SS, LIST_SS, LABEL_SS
)
from py_editor.ui.scene.object_system import SceneObject
from py_editor.ui.shader_manager import get_shader, get_shader_list
from py_editor.core import paths as asset_paths

class MaterialSlotWidget(QFrame):
    """A drop zone for material assets."""
    material_dropped = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setFixedHeight(24)
        self.setStyleSheet("background: #1e1e1e; border: 1px dashed #444; border-radius: 3px;")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 0, 4, 0)
        
        self.label = QLabel("None")
        self.label.setStyleSheet("border: none; background: transparent; color: #888; font-size: 11px;")
        layout.addWidget(self.label)
        layout.addStretch()
        self.btn = QPushButton("...")
        self.btn.setFixedSize(24, 20)
        self.btn.setStyleSheet("background: #333; border: 1px solid #555; border-radius: 2px; color: #ccc;")
        self.btn.clicked.connect(self._on_browse)
        layout.addWidget(self.btn)
        
    def _on_browse(self):
        from PyQt6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(self, "Select Material", "", "Material Files (*.material)")
        if path:
            # Emit with mat: prefix if expected by drop logic, though update_obj_prop usually takes raw path
            self.material_dropped.emit(path)

    def set_material(self, path):
        name = Path(path).name if path else "None"
        self.label.setText(name)
        self.label.setStyleSheet(f"border: none; background: transparent; color: {'#4fc3f7' if path else '#888'}; font-size: 11px;")

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasText() and event.mimeData().text().startswith("mat:"):
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        text = event.mimeData().text()
        if text.startswith("mat:"):
            self.material_dropped.emit(text[4:])
            event.acceptProposedAction()

class TextureSlotWidget(QFrame):
    """A drop zone for texture assets (.png, .jpg)."""
    texture_dropped = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setFixedHeight(24)
        self.setStyleSheet("background: #1e1e1e; border: 1px dashed #444; border-radius: 3px;")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 0, 4, 0)
        
        self.label = QLabel("None")
        self.label.setStyleSheet("border: none; background: transparent; color: #888; font-size: 11px;")
        layout.addWidget(self.label)
        layout.addStretch()
        self.btn = QPushButton("...")
        self.btn.setFixedSize(24, 20)
        self.btn.setStyleSheet("background: #333; border: 1px solid #555; border-radius: 2px; color: #ccc;")
        self.btn.clicked.connect(self._on_browse)
        layout.addWidget(self.btn)
        
    def _on_browse(self):
        from PyQt6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(self, "Select Texture", "", "Textures (*.png *.jpg *.jpeg *.tga)")
        if path:
            self.texture_dropped.emit(path)
        
    def set_texture(self, path):
        # Prevent crashes if a non-string (e.g. roughness float) is passed
        if path and not isinstance(path, str):
            path = None
        name = Path(path).name if path else "None"
        self.label.setText(name)
        self.label.setStyleSheet(f"border: none; background: transparent; color: {'#4fc3f7' if path else '#888'}; font-size: 11px;")

    def dragEnterEvent(self, event: QDragEnterEvent):
        text = event.mimeData().text().lower()
        if any(text.endswith(ext) for ext in ('.png', '.jpg', '.jpeg')):
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        text = event.mimeData().text()
        self.texture_dropped.emit(text)
        event.acceptProposedAction()

class MeshSlotWidget(QFrame):
    """A drop zone for mesh assets (.mesh)."""
    mesh_dropped = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setFixedHeight(24)
        self.setStyleSheet("background: #1e1e1e; border: 1px dashed #444; border-radius: 3px;")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 0, 4, 0)
        
        self.label = QLabel("None")
        self.label.setStyleSheet("border: none; background: transparent; color: #888; font-size: 11px;")
        layout.addWidget(self.label)
        layout.addStretch()
        self.btn = QPushButton("...")
        self.btn.setFixedSize(24, 20)
        self.btn.setStyleSheet("background: #333; border: 1px solid #555; border-radius: 2px; color: #ccc;")
        self.btn.clicked.connect(self._on_browse)
        layout.addWidget(self.btn)
        
    def _on_browse(self):
        from PyQt6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(self, "Select Mesh", "", "Mesh Files (*.mesh)")
        if path:
            self.mesh_dropped.emit(path)
        
    def set_mesh(self, path):
        name = Path(path).name if path else "None"
        self.label.setText(name)
        self.label.setStyleSheet(f"border: none; background: transparent; color: {'#4fc3f7' if path else '#888'}; font-size: 11px;")

    def dragEnterEvent(self, event: QDragEnterEvent):
        text = event.mimeData().text().lower()
        if text.endswith('.mesh'):
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        text = event.mimeData().text()
        self.mesh_dropped.emit(text)
        event.acceptProposedAction()

class PrefabListWidget(QListWidget):
    """A drop zone for prefab files."""
    prefab_dropped = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setStyleSheet(LIST_SS)

    def dragEnterEvent(self, event: QDragEnterEvent):
        text = event.mimeData().text()
        if text.lower().endswith('.prefab') or text.startswith('prefab:'):
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        text = event.mimeData().text()
        if text.startswith('prefab:'): text = text[7:]
        self.prefab_dropped.emit(text)
        event.acceptProposedAction()

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
        layout.addWidget(self.slider, 1); layout.addWidget(self.spin)
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

    def value(self): return self.spin.value()

    def _on_slider_changed(self, ival):
        if self._updating: return
        self._updating = True
        val = self.vmin + (ival / 1000.0) * (self.vmax - self.vmin)
        self.spin.setValue(val); self.valueChanged.emit(val); self._updating = False

    def _on_spin_changed(self, fval):
        if self._updating: return
        self._updating = True
        s_val = int((fval - self.vmin) / (self.vmax - self.vmin) * 1000) if self.vmax > self.vmin else 0
        self.slider.setValue(s_val);        self.spin.blockSignals(False)
        self._updating = False

class ColorPickerButton(QPushButton):
    """A button that displays and picks an RGB/RGBA color."""
    colorChanged = pyqtSignal(list)

    def __init__(self, color=[1.0, 1.0, 1.0, 1.0], parent=None):
        super().__init__(parent)
        self.setFixedWidth(80)
        self.setFixedHeight(22)
        self._color = list(color)
        self.clicked.connect(self._pick_color)
        self._update_style()

    def set_color(self, color):
        self._color = list(color)
        self._update_style()

    def _update_style(self):
        c = self._color
        r, g, b = int(c[0]*255), int(c[1]*255), int(c[2]*255)
        # Use a border to make light colors visible against gray
        self.setStyleSheet(f"background-color: rgb({r},{g},{b}); border: 1px solid #555; border-radius: 2px;")

    def _pick_color(self):
        c = self._color
        initial = QColor.fromRgbF(c[0], c[1], c[2], c[3])
        color = QColorDialog.getColor(initial, self, "Pick Color", QColorDialog.ColorDialogOption.ShowAlphaChannel)
        if color.isValid():
            new_color = [color.redF(), color.greenF(), color.blueF(), color.alphaF()]
            self.set_color(new_color)
            self.colorChanged.emit(new_color)

class ObjectPropertiesPanel(QWidget):
    """The Right-side properties inspector."""
    property_changed = pyqtSignal()   
    
    # Layer presets tuned for "No Man's Sky"-style terrain.
    # Frequencies are in normalised units (per-radius for round, per-100u for flat),
    # so the same preset yields analogous-looking features across modes.
    # For best results: stack Continents + Mountains (or Sharp Peaks), then
    # LOWER "Smoothing" to 0 or 1 when using Mountains/Sharp Peaks — smoothing
    # rounds off the ridges and makes peaks look like dunes.
    VOXEL_LAYER_PRESETS = {
        # Base landmass shape — 2-3 huge landmasses across the world
        "Continents":   {"noise_type": "fbm",     "freq": 0.35, "amp": 0.55, "blend": "add"},
        # Rolling hills on top of continents
        "Hills":        {"noise_type": "fbm",     "freq": 1.2,  "amp": 0.20, "blend": "add"},
        # Mountain chains — now with sharpened ridged noise and higher amplitude
        "Mountains":    {"noise_type": "ridged",  "freq": 2.2,  "amp": 0.75, "blend": "add", "mask_threshold": 0.25},
        # Dramatic individual peaks
        "Sharp Peaks":  {"noise_type": "ridged",  "freq": 3.8,  "amp": 0.85, "blend": "add", "mask_threshold": 0.35},
        # Fine rocky surface roughness
        "Rocky Detail": {"noise_type": "fbm",     "freq": 5.0,  "amp": 0.08, "blend": "add"},
        # Deep carved valleys / river systems
        "Canyons":      {"noise_type": "voronoi", "freq": 1.2,  "amp": 0.35, "blend": "subtract"},
        # Sparse large impact craters — NMS-style moons
        "Crater Moon":  {"noise_type": "voronoi", "freq": 0.8,  "amp": 0.25, "blend": "subtract"},
        # Underground cave networks
        "Caves":        {"noise_type": "caves",   "freq": 4.0,  "amp": 0.60, "blend": "subtract"},
    }
    
    VOXEL_BIOME_PRESETS = {
        "Deep Ocean":    {"range": [-1000.0, -5.0], "color": [0.05, 0.1,  0.3,  1.0], "rough": 0.1},
        "Shallow Water": {"range": [-5.0,    0.0],  "color": [0.1,  0.4,  0.6,  1.0], "rough": 0.2},
        "Beach":         {"range": [0.0,     2.0],  "color": [0.85, 0.8,  0.65, 1.0], "rough": 0.9},
        "Grassland":     {"range": [2.0,     15.0], "color": [0.25, 0.4,  0.1,  1.0], "rough": 0.8, "spawns": [
            {"kind": "object:cube", "density": 0.15, "shader_name": "shaders/grass.shader", "scale_min": 0.6, "scale_max": 1.4, "jitter": 0.4}
        ]},
        "Desert":        {"range": [0.0,     1000.0],"color": [0.9,  0.8,  0.5,  1.0], "rough": 1.0},
        "Snow Cap":      {"range": [45.0,    1000.0],"color": [0.95, 0.95, 1.0,  1.0], "rough": 0.3},
        "Mars Dust":     {"range": [-1000.0, 1000.0],"color": [0.8,  0.3,  0.1,  1.0], "rough": 0.9},
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: #252526;")
        self._current_objects = []
        self._current_prefab_path = None
        self._updating = False
        self._row_map = {} # widget -> row_container mapping for visibility toggle
        self._regen_timer = None # For throttling rapid changes
        # Main layout contains a scroll area so the properties panel stays fixed size
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Standalone editing header
        self.header_widget = QFrame()
        self.header_widget.setFixedHeight(30)
        self.header_widget.setStyleSheet("background-color: #3e3e42; border-bottom: 1px solid #555;")
        self.header_layout = QHBoxLayout(self.header_widget)
        self.header_layout.setContentsMargins(10, 0, 10, 0)
        self.header_label = QLabel("PROPERTIES")
        self.header_label.setStyleSheet("color: #4fc3f7; font-weight: bold; font-size: 11px; text-transform: uppercase;")
        self.header_layout.addWidget(self.header_label)
        self.header_layout.addStretch()
        layout.addWidget(self.header_widget)
        
        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        layout.addWidget(self._scroll)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(4,4,4,4); layout.setSpacing(4)

        self._title = QLabel("  No Selection")
        self._title.setFixedHeight(24)
        self._title.setStyleSheet("color: #888; font-size: 11px; font-weight: bold;")
        layout.addWidget(self._title)
        self._scroll.setWidget(content)

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
        self.pos_group = pos_group

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
        self.rot_group = rot_group

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
        self.scale_group = scale_group
        layout.addWidget(scale_group)
        
        # Initialize Sub-UIs
        self._init_mesh_mat_ui(layout)
        self._init_pbr_ui(layout)
        
        self.save_btn = QPushButton("💾 SAVE PREFAB")
        self.save_btn.setStyleSheet(BTN_SS + "background-color: #2e7d32; font-weight: bold; margin-top: 10px;")
        self.save_btn.clicked.connect(self._on_save_prefab)
        self.save_btn.setVisible(False)
        layout.addWidget(self.save_btn)
        
        # Atmosphere Section
        self.env_group = QGroupBox("Atmosphere Settings")
        self.env_group.setStyleSheet(PROPS_SS)
        eg = QVBoxLayout(self.env_group)
        self.time_slider = PropertySlider(0.25, 0.0, 1.0)
        self.time_slider.valueChanged.connect(lambda v: self.update_obj_prop('time_of_day', v))
        self._add_property_row(eg, "Time of Day", self.time_slider)
        
        self.sun_size = PropertySlider(1.0, 0.1, 10.0)
        self.sun_size.valueChanged.connect(lambda v: self.update_obj_prop('sun_size', v))
        self._add_property_row(eg, "Sun Size", self.sun_size)
        
        self.sun_intensity = PropertySlider(10.0, 0.0, 100.0)
        self.sun_intensity.valueChanged.connect(lambda v: self.update_obj_prop('sun_intensity', v))
        self._add_property_row(eg, "Sun Intensity", self.sun_intensity)

        self.planet_radius = PropertySlider(6371.0, 1.0, 300000.0)
        self.planet_radius.valueChanged.connect(lambda v: self.update_obj_prop('planet_radius', v))
        self._add_property_row(eg, "Planet Radius", self.planet_radius)

        self.atmo_thick = PropertySlider(1200.0, 1.0, 50000.0)
        self.atmo_thick.valueChanged.connect(lambda v: self.update_obj_prop('atmosphere_thickness', v))
        self._add_property_row(eg, "Atmo Thickness", self.atmo_thick)

        
        eg.addSpacing(6)
        lbl_lighting = QLabel("Global Illumination")
        lbl_lighting.setStyleSheet("color: #4fc3f7; font-weight: bold; font-size: 11px; margin-top: 4px;")
        eg.addWidget(lbl_lighting)

        self.sun_color_btn = ColorPickerButton()
        self.sun_color_btn.colorChanged.connect(lambda c: self.update_obj_prop('sun_color', c))
        self._add_property_row(eg, "Sun Color", self.sun_color_btn)

        self.moon_color_btn = ColorPickerButton()
        self.moon_color_btn.colorChanged.connect(lambda c: self.update_obj_prop('moon_color', c))
        self._add_property_row(eg, "Moon Color", self.moon_color_btn)

        self.amb_color_btn = ColorPickerButton()
        self.amb_color_btn.colorChanged.connect(lambda c: self.update_obj_prop('ambient_color', c))
        self._add_property_row(eg, "Ambient Color", self.amb_color_btn)

        self.moon_int = PropertySlider(1.0, 0.0, 10.0)
        self.moon_int.valueChanged.connect(lambda v: self.update_obj_prop('moon_intensity', v))
        self._add_property_row(eg, "Moon Power", self.moon_int)

        self.light_mode = QComboBox()
        self.light_mode.addItems(["Auto", "Manual Sun", "Manual Moon"])
        self.light_mode.currentIndexChanged.connect(lambda i: self.update_obj_prop('light_update_mode', self.light_mode.currentText()))
        self._add_property_row(eg, "Light Mode", self.light_mode)
        
        # Universe Specifics (Stars, Nebulas)
        eg.addSpacing(6)
        self.uni_lbl = QLabel("Universe Specifics")
        self.uni_lbl.setStyleSheet("color: #4fc3f7; font-weight: bold; font-size: 11px; margin-top: 4px;")
        eg.addWidget(self.uni_lbl)

        self.star_density = PropertySlider(1.0, 0.0, 5.0)
        self.star_density.valueChanged.connect(lambda v: self.update_obj_prop('star_density', v))
        self._add_property_row(eg, "Star Density", self.star_density)
        
        self.neb_intensity = PropertySlider(0.5, 0.0, 2.0)
        self.neb_intensity.valueChanged.connect(lambda v: self.update_obj_prop('nebula_intensity', v))
        self._add_property_row(eg, "Nebula Power", self.neb_intensity)

        layout.addWidget(self.env_group)
        
        self.save_btn = QPushButton("💾 SAVE PREFAB")
        self.save_btn.setStyleSheet(BTN_SS + "background-color: #2e7d32; font-weight: bold; margin-top: 10px;")
        self.save_btn.clicked.connect(self._on_save_prefab)
        self.save_btn.setVisible(False)
        layout.addWidget(self.save_btn)
        
        self._init_landscape_ui(layout)
        self._init_ocean_ui(layout)
        self._init_voxel_ui(layout)
        self._init_controller_ui(layout)
        self._init_weather_ui(layout)
        self._init_camera_ui(layout)
        self._init_shader_ui(layout)
        self._init_logic_ui(layout)
        self._init_spawner_ui(layout)
        
        layout.addStretch()

        layout.addStretch()
        
        # Ensure it starts empty
        self.set_objects([])

    def _init_mesh_mat_ui(self, layout):
        self.mesh_mat_group = QGroupBox("Mesh & Material")
        self.mesh_mat_group.setStyleSheet(PROPS_SS)
        mg = QVBoxLayout(self.mesh_mat_group)
        mg.setContentsMargins(10, 14, 10, 10); mg.setSpacing(6)
        
        # 1. Mesh Source
        self.mesh_slot = MeshSlotWidget()
        self.mesh_slot.mesh_dropped.connect(lambda p: self.update_obj_prop('mesh_path', p))
        self._add_property_row(mg, "Mesh Source", self.mesh_slot)
        
        # 2. Material Asset
        self.mat_slot = MaterialSlotWidget()
        self.mat_slot.material_dropped.connect(lambda p: self.update_obj_prop('material_path', p))
        self._add_property_row(mg, "Material (.material)", self.mat_slot)
        
        # 3. Base Color / Preset (Legacy)
        self.mat_preset = QComboBox()
        self.mat_preset.addItems(['Plastic', 'Glass', 'Metal', 'Water', 'Custom'])
        self.mat_preset.setStyleSheet(COMBO_SS)
        self.mat_preset_row = self._add_property_row(mg, "Preset", self.mat_preset)
        
        # 4. Legacy Texture
        self.tex_slot = TextureSlotWidget()
        self.tex_slot.texture_dropped.connect(lambda p: self.update_obj_prop('texture_path', p))
        self.tex_slot_row = self._add_property_row(mg, "Custom Tex", self.tex_slot)
        
        # 5. Opacity
        self.opacity_slider = PropertySlider(1.0, 0.0, 1.0)
        self.opacity_slider.valueChanged.connect(lambda v: self.update_obj_prop('alpha', v))
        self._add_property_row(mg, "Opacity", self.opacity_slider)
        
        layout.addWidget(self.mesh_mat_group)
        self.mesh_group = self.mesh_mat_group
        self.mat_group = self.mesh_mat_group
        
        layout.addWidget(self.mesh_group)

    def _init_spawner_ui(self, layout):
        self.spawner_group = QGroupBox("Spawner Settings")
        self.spawner_group.setStyleSheet(PROPS_SS)
        sg = QVBoxLayout(self.spawner_group)
        sg.setContentsMargins(10, 14, 10, 10); sg.setSpacing(6)

        self.spawn_count = QSpinBox()
        self.spawn_count.setStyleSheet(SPIN_SS); self.spawn_count.setRange(1, 1000)
        self.spawn_count.valueChanged.connect(lambda v: self.update_obj_prop('spawner_count', v))
        self._add_property_row(sg, "Count", self.spawn_count)

        self.spawn_radius = PropertySlider(10.0, 0.0, 1000.0)
        self.spawn_radius.valueChanged.connect(lambda v: self.update_obj_prop('spawner_radius', v))
        self._add_property_row(sg, "Radius", self.spawn_radius)

        self.spawn_ground = QCheckBox("Find Ground")
        self.spawn_ground.setStyleSheet(LABEL_SS)
        self.spawn_ground.toggled.connect(lambda v: self.update_obj_prop('spawner_find_ground', v))
        sg.addWidget(self.spawn_ground)
        
        # Boid Movement Controller Selector
        sg.addWidget(QLabel("Boid Movement Controller (AI):", styleSheet=LABEL_SS))
        scp_container = QWidget()
        scp_layout = QHBoxLayout(scp_container)
        scp_layout.setContentsMargins(0,0,0,0)
        
        self.spawner_controller_picker_lbl = QLabel("None")
        self.spawner_controller_picker_lbl.setStyleSheet("color: #ccc; border: 1px solid #555; border-radius: 4px; padding: 4px;")
        
        btn = QPushButton("Browse...")
        btn.setStyleSheet(BTN_SS)
        btn.clicked.connect(self._browse_spawner_controller)
        
        scp_layout.addWidget(self.spawner_controller_picker_lbl)
        scp_layout.addWidget(btn)
        sg.addWidget(scp_container)
        
        # We can add lists/ranges for offset and tint, or assume single value for simple use case
        # For full UI of array of prefabs:
        self.prefab_list_widget = PrefabListWidget()
        self.prefab_list_widget.setFixedHeight(80)
        self.prefab_list_widget.prefab_dropped.connect(self._on_add_spawner_prefab)
        sg.addWidget(QLabel("Prefabs (Drop .prefab files below):", styleSheet=LABEL_SS))
        sg.addWidget(self.prefab_list_widget)
        
        btn_layout = QHBoxLayout()
        self.add_prefab_btn = QPushButton("Add Prefab...")
        self.add_prefab_btn.setStyleSheet(BTN_SS + "background: #2d5a27;")
        self.add_prefab_btn.clicked.connect(self._on_browse_spawner_prefab)
        
        self.rem_prefab_btn = QPushButton("Remove Selected")
        self.rem_prefab_btn.setStyleSheet(BTN_SS)
        self.rem_prefab_btn.clicked.connect(self._on_remove_spawner_prefab)
        
        btn_layout.addWidget(self.add_prefab_btn)
        btn_layout.addWidget(self.rem_prefab_btn)
        sg.addLayout(btn_layout)

        self.respawn_btn = QPushButton("Respawn")
        self.respawn_btn.setStyleSheet(BTN_SS + "background: #3a5a8a;")
        self.respawn_btn.clicked.connect(self._on_respawn_spawner)
        sg.addWidget(self.respawn_btn)

        layout.addWidget(self.spawner_group)

    def _on_respawn_spawner(self):
        if not self._current_objects: return
        from py_editor.ui.scene.object_system import respawn_spawner
        # Walk up to the scene view to mutate the shared scene_objects list.
        sv = self.window()
        viewport = None
        for attr in ('viewport', 'scene_view', 'scene_editor'):
            target = getattr(sv, attr, None)
            if target is not None:
                viewport = getattr(target, 'viewport', target)
                break
        if viewport is None or not hasattr(viewport, 'scene_objects'):
            print("[PROPS] Respawn: could not locate viewport.scene_objects")
            return
        for spawner in self._current_objects:
            if getattr(spawner, 'obj_type', None) == 'spawner':
                respawn_spawner(spawner, viewport.scene_objects)
        try: viewport.update()
        except Exception: pass

    def _on_add_spawner_prefab(self, path):
        if not self._current_objects: return
        for obj in self._current_objects:
            if not hasattr(obj, 'spawner_prefabs'):
                obj.spawner_prefabs = []
            obj.spawner_prefabs.append(path)
        self.set_objects(self._current_objects)
        self.property_changed.emit()

    def _on_remove_spawner_prefab(self):
        if not self._current_objects: return
        row = self.prefab_list_widget.currentRow()
        if row < 0: return
        for obj in self._current_objects:
            if row < len(obj.spawner_prefabs):
                obj.spawner_prefabs.pop(row)
        self.set_objects(self._current_objects)
        self.property_changed.emit()

    def _on_browse_spawner_prefab(self):
        from PyQt6.QtWidgets import QFileDialog
        from py_editor.core import paths as _ap
        root = _ap.get_project_root()
        path, _ = QFileDialog.getOpenFileName(
            self, "Add Spawner Asset", str(root),
            "Spawnable Assets (*.prefab *.mesh *.fbx *.obj);;Prefab (*.prefab);;Mesh (*.mesh *.fbx *.obj)")
        if path:
            self._on_add_spawner_prefab(path)

    def _browse_spawner_controller(self):
        from PyQt6.QtWidgets import QFileDialog
        ctrl_dir = str(Path(__file__).parent.parent.parent.parent / "controllers")
        path, _ = QFileDialog.getOpenFileName(self, "Select Spawner Controller", ctrl_dir, "Controller Files (*.controller)")
        if path:
            self._on_spawner_controller_picked(path)

    def _on_spawner_controller_picked(self, name_or_path):
        if not self._current_objects: return
        self.update_obj_prop('spawner_controller_type', name_or_path)
        self.spawner_controller_picker_lbl.setText(Path(name_or_path).name if '.controller' in name_or_path else name_or_path)
        self.property_changed.emit()

    def _init_pbr_ui(self, layout):
        self.pbr_group = QGroupBox("PBR Material (Megascans)")
        self.pbr_group.setStyleSheet(PROPS_SS)
        pg = QVBoxLayout(self.pbr_group)
        pg.setContentsMargins(10, 14, 10, 10); pg.setSpacing(6)

        # Map Slots
        self.pbr_slots = {}
        maps = [
            ("Albedo", "albedo"), ("Normal", "normal"), 
            ("Metallic", "metallic"), ("Roughness", "roughness"),
            ("AO", "ao"), ("Displacement", "displacement")
        ]
        for label, m_type in maps:
            slot = TextureSlotWidget()
            slot.texture_dropped.connect(lambda p, t=m_type: self._on_pbr_map_dropped(t, p))
            self._add_property_row(pg, label, slot)
            self.pbr_slots[m_type] = slot
        
        # Auto Import
        self.auto_link_btn = QPushButton("📂 Auto-Link Megascans Folder")
        self.auto_link_btn.setStyleSheet(BTN_SS + "background: #2d5a27;")
        self.auto_link_btn.clicked.connect(self._on_megascans_import)
        pg.addWidget(self.auto_link_btn)

        # Settings
        self.pbr_tiling_x = PropertySlider(1.0, 0.1, 50.0)
        self.pbr_tiling_x.valueChanged.connect(lambda v: self._on_pbr_tiling_changed(v, 0))
        self._add_property_row(pg, "Tiling X", self.pbr_tiling_x)

        self.pbr_tiling_y = PropertySlider(1.0, 0.1, 50.0)
        self.pbr_tiling_y.valueChanged.connect(lambda v: self._on_pbr_tiling_changed(v, 1))
        self._add_property_row(pg, "Tiling Y", self.pbr_tiling_y)

        self.pbr_disp_scale = PropertySlider(0.05, 0.0, 0.5)
        self.pbr_disp_scale.valueChanged.connect(lambda v: self.update_obj_prop('pbr_displacement_scale', v))
        self._add_property_row(pg, "Disp Scale", self.pbr_disp_scale)

        layout.addWidget(self.pbr_group)

    def _on_pbr_map_dropped(self, m_type, path):
        if not self._current_objects: return
        # Immediate UI local update
        if m_type in self.pbr_slots:
            self.pbr_slots[m_type].set_texture(path)

        for obj in self._current_objects:
            if not hasattr(obj, 'pbr_maps') or obj.pbr_maps is None:
                obj.pbr_maps = {}
            obj.pbr_maps[m_type] = path
            
            # Sync to material for saving
            if not hasattr(obj, 'material') or not isinstance(obj.material, dict):
                obj.material = {}
            obj.material[m_type] = path

            # Auto-activate PBR shader when the first map is dropped
            if getattr(obj, 'shader_name', 'Standard') == 'Standard':
                obj.shader_name = 'PBR Material'
        self.property_changed.emit()

    def _on_pbr_tiling_changed(self, val, axis):
        if not self._current_objects: return
        for obj in self._current_objects:
            obj.pbr_tiling[axis] = val
        self.property_changed.emit()

    def _on_megascans_import(self):
        dir_path = QFileDialog.getExistingDirectory(self, "Select Megascans Folder")
        if not dir_path or not self._current_objects: return
        
        import os
        folder = Path(dir_path)
        mapping = {
            "albedo": ["albedo", "basecolor", "diffuse"],
            "normal": ["normal"],
            "metallic": ["metallic", "metalness"],
            "roughness": ["roughness"],
            "ao": ["ao", "ambientocclusion"],
            "displacement": ["displacement", "height", "disp"]
        }
        
        found = {}
        for file in os.listdir(dir_path):
            lower_name = file.lower()
            if not any(lower_name.endswith(ext) for ext in ('.jpg', '.jpeg', '.png', '.tga')):
                continue
            
            for m_type, keywords in mapping.items():
                if any(k in lower_name for k in keywords) and m_type not in found:
                    found[m_type] = str(folder / file)
                    break
        
        if found:
            for obj in self._current_objects:
                obj.pbr_maps.update(found)
                # Sync to material for saving
                if not hasattr(obj, 'material') or not isinstance(obj.material, dict):
                    obj.material = {}
                obj.material.update(found)
                obj.shader_name = "PBR Material"
            self.set_objects(self._current_objects)
            self.property_changed.emit()
            print(f"[PROPERTIES] Auto-linked {len(found)} PBR maps for {folder.name}")

    def _on_pos_changed(self):
        if self._updating or not self._current_objects: return
        for obj in self._current_objects:
            for i in range(3): obj.position[i] = self._pos_spins[i].value()
        self.property_changed.emit()

    def _on_rot_changed(self):
        if self._updating or not self._current_objects: return
        for obj in self._current_objects:
            for i in range(3): obj.rotation[i] = self._rot_spins[i].value()
        self.property_changed.emit()

    def _on_scale_changed(self):
        if self._updating or not self._current_objects: return
        for obj in self._current_objects:
            for i in range(3): obj.scale[i] = self._scale_spins[i].value()
        self.property_changed.emit()

    def update_obj_prop(self, prop, val):
        if not self._current_objects: return
        for obj in self._current_objects:
            setattr(obj, prop, val)
            # Sync to material for saving if in material editing mode
            if hasattr(obj, 'material') and isinstance(obj.material, dict):
                obj.material[prop] = val
            
            # Auto-apply textures from .mat asset
            if prop == 'material_path' and val and val.endswith('.material'):
                try:
                    import json
                    with open(val, 'r') as f:
                        data = json.load(f)
                    tex = data.get('albedo') or data.get('texture_path')
                    if tex:
                        obj.texture_path = tex
                        # Update UI
                        if hasattr(self, 'tex_slot'): self.tex_slot.set_texture(tex)
                    # If it's a PBR mat, update maps
                    if "albedo" in data or "normal" in data:
                        obj.pbr_maps = data
                        obj.shader_name = "PBR Material"
                except Exception as e:
                    print(f"[PROPERTIES] Failed to auto-apply material {val}: {e}")

        # Immediate UI Feedback
        if prop == 'mesh_path':
            self.mesh_slot.set_mesh(val)
        elif prop == 'texture_path':
            self.tex_slot.set_texture(val)
        elif prop == 'material_path':
            self.mat_slot.set_material(val)

        # Throttled regeneration for voxel world settings (freq, amp, seed etc)
        needs_throttle = prop.startswith('voxel_') or prop in ('sun_color', 'ambient_color')
        if needs_throttle:
            from PyQt6.QtCore import QTimer
            if self._regen_timer: self._regen_timer.stop()
            self._regen_timer = QTimer()
            self._regen_timer.setSingleShot(True)
            self._regen_timer.timeout.connect(self.property_changed.emit)
            self._regen_timer.start(150) # 150ms delay
        else:
            self.property_changed.emit()

    def update_shader_param(self, key, val):
        if not self._current_objects: return
        for obj in self._current_objects:
            if not hasattr(obj, 'shader_params'): obj.shader_params = {}
            obj.shader_params[key] = val
        self.property_changed.emit()

    def set_objects(self, objs: list[SceneObject]):
        if not objs:
            self.header_label.setText("PROPERTIES")
            self.header_widget.setStyleSheet("background-color: #3e3e42; border-bottom: 1px solid #555;")
            self.save_btn.setVisible(False)
            self._current_prefab_path = None
            self._current_mat_path = None
            self._current_spawner_path = None
            for group in [self.pos_group, self.rot_group, self.scale_group, self.mat_group, self.env_group, self.land_group, self.ocean_group, self.logic_group, self.shader_group, self.mesh_group, self.vox_group, self.cont_group, self.spawner_group]:
                group.setVisible(False)
            return

        primary = objs[0]
        
        # Header update
        if getattr(self, '_current_mat_path', None):
            self.header_label.setText(f"Editing Material: {Path(self._current_mat_path).name}")
            self.header_widget.setStyleSheet("background-color: #2d5a27; border-bottom: 1px solid #555;") # Green tint for standalone
        elif getattr(self, '_current_prefab_path', None):
            self.header_label.setText(f"Editing Prefab: {Path(self._current_prefab_path).name}")
            self.header_widget.setStyleSheet("background-color: #3a5a8a; border-bottom: 1px solid #555;") # Blue tint for standalone
        elif getattr(self, '_current_spawner_path', None):
            self.header_label.setText(f"Editing Spawner: {Path(self._current_spawner_path).name}")
            self.header_widget.setStyleSheet("background-color: #5a3a8a; border-bottom: 1px solid #555;") # Purple tint for standalone
        else:
            self.header_label.setText(f"Properties: {primary.name}")
            self.header_widget.setStyleSheet("background-color: #3e3e42; border-bottom: 1px solid #555;")

        self._updating = True
        
        self._current_objects = objs

        # If multiple objects selected, show common info or first object's info
        primary = objs[0]
        self._title.setText(f"  {primary.name if len(objs)==1 else f'{len(objs)} Objects'}  ({primary.obj_type})")
        self._updating = True
        
        # Visibility logic
        self.pos_group.show()
        self.logic_group.show()
        self.shader_group.show()
        
        is_infinite = primary.obj_type in ('ocean', 'atmosphere', 'universe')
        self.rot_group.setVisible(not is_infinite)
        self.scale_group.setVisible(not is_infinite)
        
        for i in range(3):
            self._pos_spins[i].setValue(primary.position[i])
            self._rot_spins[i].setValue(primary.rotation[i])
            self._scale_spins[i].setValue(primary.scale[i])
        
        is_renderable = primary.obj_type in ('cube', 'sphere', 'plane', 'landscape', 'mesh')
        
        # Determine if it's PBR mode
        s_name = getattr(primary, 'shader_name', '')
        is_pbr = "pbr_material" in s_name.lower() or s_name == "PBR Material"
        
        self.mat_group.setVisible(is_renderable)
        self.shader_group.setVisible(is_renderable)
        self.pbr_group.setVisible(is_renderable and is_pbr)
        
        # Hide legacy features in PBR mode
        preset_row = getattr(self, 'mat_preset_row', None)
        if preset_row: preset_row.setVisible(not is_pbr)
        
        tex_row = getattr(self, 'tex_slot_row', None)
        if tex_row: tex_row.setVisible(not is_pbr)

        self.env_group.setVisible(primary.obj_type in ('atmosphere', 'universe'))
        self.land_group.setVisible(primary.obj_type == 'landscape')
        self.ocean_group.setVisible(primary.obj_type in ('ocean', 'ocean_world'))
        self.cam_group.setVisible(primary.obj_type == 'camera')
        self.mesh_group.setVisible(primary.obj_type == 'mesh')
        self.voxel_group.setVisible(primary.obj_type in ('voxel_world', 'voxel_water'))
        self.controller_group.setVisible(primary.obj_type in ('cube', 'sphere', 'mesh', 'voxel_world'))
        self.weather_group.setVisible(primary.obj_type == 'weather')
        self.spawner_group.setVisible(primary.obj_type == 'spawner')
        
        if self.mat_group.isVisible():
            preset = primary.material.get('preset', 'Custom')
            idx = self.mat_preset.findText(preset)
            if idx != -1: self.mat_preset.setCurrentIndex(idx)
            
            self.opacity_slider.setValue(getattr(primary, 'alpha', 1.0))
            
        c_type = getattr(primary, 'controller_type', 'None')
        if hasattr(self, 'controller_picker_lbl'):
            self.controller_picker_lbl.setText(Path(c_type).name if '.controller' in c_type else c_type)
            
        s_c_type = getattr(primary, 'spawner_controller_type', 'None')
        if hasattr(self, 'spawner_controller_picker_lbl'):
            self.spawner_controller_picker_lbl.setText(Path(s_c_type).name if '.controller' in s_c_type else s_c_type)
            
        # PBR Sync — always sync when group is visible
        if self.pbr_group.isVisible():
                pbr_maps = getattr(primary, 'pbr_maps', {})
                for m_type, slot in self.pbr_slots.items():
                    slot.set_texture(pbr_maps.get(m_type))
                tiling = getattr(primary, 'pbr_tiling', [1.0, 1.0])
                self.pbr_tiling_x.setValue(tiling[0])
                self.pbr_tiling_y.setValue(tiling[1])
                self.pbr_disp_scale.setValue(getattr(primary, 'pbr_displacement_scale', 0.05))
        
        if self.mesh_group.isVisible():
            self.mesh_slot.set_mesh(primary.mesh_path if primary.mesh_path else "")
            self.tex_slot.set_texture(primary.texture_path)
            
        # Shader Sync
        if hasattr(self, 'shader_picker_lbl'):
            if s_name:
                self.shader_picker_lbl.setText(Path(s_name).name)
            else:
                self.shader_picker_lbl.setText("None")

        # ... (remaining sync logic uses 'primary' as reference)
        obj = primary
        if obj.obj_type == 'atmosphere' or obj.obj_type == 'universe':
            self.time_slider.setValue(getattr(obj, 'time_of_day', 0.25))
            self.sun_size.setValue(getattr(obj, 'sun_size', 1.0))
            self.sun_intensity.setValue(getattr(obj, 'sun_intensity', 10.0))
            self.planet_radius.setValue(getattr(obj, 'planet_radius', 6371.0))
            self.atmo_thick.setValue(getattr(obj, 'atmosphere_thickness', 1200.0))
            
            self.sun_color_btn.set_color(getattr(obj, 'sun_color', [1.0, 1.0, 0.9, 1.0]))
            self.moon_color_btn.set_color(getattr(obj, 'moon_color', [0.6, 0.7, 1.0, 1.0]))
            self.amb_color_btn.set_color(getattr(obj, 'ambient_color', [0.1, 0.1, 0.2, 1.0]))
            self.moon_int.setValue(getattr(obj, 'moon_intensity', 1.0))
            self.light_mode.setCurrentText(getattr(obj, 'light_update_mode', 'Auto'))

            is_universe = obj.obj_type == 'universe'
            self.uni_lbl.setVisible(is_universe)
            self._row_map[self.star_density].setVisible(is_universe)
            self._row_map[self.neb_intensity].setVisible(is_universe)
            
            if is_universe:
                self.star_density.setValue(getattr(obj, 'star_density', 1.0))
                self.neb_intensity.setValue(getattr(obj, 'nebula_intensity', 0.5))
        elif obj.obj_type == 'landscape':
            self.res_spin.setValue(getattr(obj, 'landscape_resolution', 32))
            self.seed_spin.setValue(getattr(obj, 'landscape_seed', 123))
            self.hscale_slider.setValue(getattr(obj, 'landscape_height_scale', 150.0))
            self.ocean_level_slider.setValue(getattr(obj, 'landscape_ocean_level', 0.08))
            self.ocean_flat_slider.setValue(getattr(obj, 'landscape_ocean_flattening', 0.4))
            self.tip_smooth_slider.setValue(getattr(obj, 'landscape_tip_smoothing', 0.1))
            self.spawn_enabled.setChecked(getattr(obj, 'landscape_spawn_enabled', False))
            self.visualize_climate.setChecked(getattr(obj, 'visualize_climate', False))
            
        if obj.obj_type == 'spawner':
            self.spawn_count.blockSignals(True)
            self.spawn_count.setValue(getattr(obj, 'spawner_count', 5))
            self.spawn_count.blockSignals(False)
            
            self.spawn_radius.setValue(getattr(obj, 'spawner_radius', 10.0))
            
            self.spawn_ground.blockSignals(True)
            self.spawn_ground.setChecked(getattr(obj, 'spawner_find_ground', False))
            self.spawn_ground.blockSignals(False)
            
            self.prefab_list_widget.clear()
            for p in getattr(obj, 'spawner_prefabs', []):
                self.prefab_list_widget.addItem(Path(p).name)

        if obj.obj_type == 'weather':
            pass
        elif obj.obj_type in ('ocean', 'ocean_world'):
            self.ocean_speed.setValue(getattr(obj, 'ocean_wave_speed', 5.0))
            self.ocean_intensity.setValue(getattr(obj, 'ocean_wave_intensity', 1.0))
            self.ocean_choppiness.setValue(getattr(obj, 'ocean_wave_choppiness', 1.5))
            self.ocean_steepness.setValue(getattr(obj, 'ocean_wave_steepness', 0.15))
            # Cascades
            self.ocean_cascade1_w.setValue(getattr(obj, 'ocean_cascade1_weight', 0.5))
            self.ocean_cascade2_w.setValue(getattr(obj, 'ocean_cascade2_weight', 0.3))
            # Hero waves
            self.ocean_hero_count.blockSignals(True)
            self.ocean_hero_count.setCurrentIndex(min(int(getattr(obj, 'ocean_hero_count', 1)), 3))
            self.ocean_hero_count.blockSignals(False)
            _hero_defaults = [(4.0, 350.0, 25.0, 0.25), (3.0, 180.0, 70.0, 0.35), (2.0, 90.0, 140.0, 0.5)]
            for i, (amp_s, wlen_s, dir_s, steep_s) in enumerate(self._hero_sliders):
                d = _hero_defaults[i]
                amp_s.setValue(getattr(obj, f'ocean_hero_amp_{i}',   d[0]))
                wlen_s.setValue(getattr(obj, f'ocean_hero_wlen_{i}', d[1]))
                dir_s.setValue(getattr(obj, f'ocean_hero_dir_{i}',   d[2]))
                steep_s.setValue(getattr(obj, f'ocean_hero_steep_{i}', d[3]))
            # Advanced visuals
            self.ocean_fresnel.setValue(getattr(obj, 'ocean_fresnel_strength', 0.3))
            self.ocean_specular.setValue(getattr(obj, 'ocean_specular_intensity', 1.0))
            self.ocean_peak_bright.setValue(getattr(obj, 'ocean_peak_brightness', 1.0))
            self.ocean_sss_str.setValue(getattr(obj, 'ocean_sss_strength', 1.0))
            # Foam settings
            self.ocean_foam_jacobian.setValue(getattr(obj, 'ocean_foam_jacobian', 1.0))
            self.ocean_foam_sharpness.setValue(getattr(obj, 'ocean_foam_sharpness', 2.5))
            self.ocean_foam_whitecap.setValue(getattr(obj, 'ocean_foam_whitecap', 1.0))
            self.ocean_foam_whitecap_thresh.setValue(getattr(obj, 'ocean_foam_whitecap_thresh', 0.5))
            self.ocean_foam_streak.setValue(getattr(obj, 'ocean_foam_streak', 1.0))
            self.ocean_foam_streak_speed.setValue(getattr(obj, 'ocean_foam_streak_speed', 1.5))
            # Surface detail
            self.ocean_detail_strength.setValue(getattr(obj, 'ocean_detail_strength', 0.4))
        elif obj.obj_type in ('voxel_world', 'voxel_water'):
            is_water = (obj.obj_type == 'voxel_water')
            
            # Hide/Show water-only vs world-only rows
            self.vox_water_level_row.setVisible(is_water)
            self.vox_water_speed_row.setVisible(is_water)
            self.vox_water_surge_row.setVisible(is_water)
            self.vox_world_height_row.setVisible(not is_water)
            
            if is_water:
                self.vox_water_level.setValue(getattr(obj, 'voxel_water_level', 0.0))
                self.vox_water_speed.setValue(getattr(obj, 'voxel_water_speed', 1.0))
                self.vox_water_surge.setValue(getattr(obj, 'voxel_water_surge', 0.5))

            # Radius: choose closest preset and apply
            radius_val = float(getattr(obj, 'voxel_radius', 0.5))
            try:
                idx = next(i for i, (_, v) in enumerate(self.vox_radius_presets_list) if float(v) == radius_val)
            except StopIteration:
                diffs = [abs(float(v) - radius_val) for (_, v) in self.vox_radius_presets_list]
                idx = int(min(range(len(diffs)), key=lambda i: diffs[i]))
            self.vox_radius.blockSignals(True)
            self.vox_radius.setCurrentIndex(idx)
            self._last_vox_radius_index = idx
            self.vox_radius.blockSignals(False)

            self.vox_smooth.setValue(getattr(obj, 'voxel_smooth_iterations', 2))

            # Detail: match closest preset to the internal voxel_block_size
            bval = float(getattr(obj, 'voxel_block_size', 1.0))
            try:
                bidx = next(i for i, (_, v) in enumerate(self.vox_detail_presets_list) if float(v) == bval)
            except StopIteration:
                b_diffs = [abs(float(v) - bval) for (_, v) in self.vox_detail_presets_list]
                bidx = int(min(range(len(b_diffs)), key=lambda i: b_diffs[i]))
            self.vox_detail_combo.blockSignals(True)
            self.vox_detail_combo.setCurrentIndex(bidx)
            self.vox_detail_combo.blockSignals(False)
            self.vox_seed.setValue(getattr(obj, 'voxel_seed', 123))
            self.vox_world_height.setValue(float(getattr(obj, 'voxel_world_height', 1.0)))
            self.vox_spawn_dist.setValue(float(getattr(obj, 'voxel_spawn_max_distance', 120.0)))
            v_type_str = getattr(obj, 'voxel_type', 'Round')
            
            # Use obj_type to determine flat/round for dedicated primitives
            obj_type_low = str(getattr(obj, 'obj_type', '')).lower()
            is_flat = "flat" in obj_type_low or "flat" in v_type_str.lower()
            
            # Hide redundant Mode and Radius rows
            self.vox_type_row.setVisible(False)
            self.vox_radius_row.setVisible(not is_flat)
            self.vox_world_height_row.setVisible(is_flat)
            
            idx = self.vox_type.findText("Flat" if is_flat else "Round")
            if idx != -1: self.vox_type.setCurrentIndex(idx)
            
            # Infinite-flat checkbox (sync state + hide for Round mode)
            self.vox_infinite_flat.blockSignals(True)
            self.vox_infinite_flat.setChecked(bool(getattr(obj, 'voxel_infinite_flat', True)))
            self.vox_infinite_flat.blockSignals(False)
            self.vox_infinite_flat.setVisible(is_flat)
            rs_idx = self.vox_render_style.findText(getattr(obj, 'voxel_render_style', 'Smooth'))
            if rs_idx != -1: self.vox_render_style.setCurrentIndex(rs_idx)
            # Prefetch and max chunk resolution (per-object overrides)
            self.vox_prefetch.blockSignals(True)
            self.vox_prefetch.setValue(int(getattr(obj, 'voxel_prefetch_neighborhood', 1)))
            self.vox_prefetch.blockSignals(False)

            self.vox_max_chunk_res.blockSignals(True)
            self.vox_max_chunk_res.setValue(int(getattr(obj, 'voxel_max_single_chunk_res', 128)))
            self.vox_max_chunk_res.blockSignals(False)
            # Hide terrain layers/biomes for water objects
            is_water = obj.obj_type == 'voxel_water'
            self.vox_layers_lbl.setVisible(not is_water)
            self.vox_layers_list.setVisible(not is_water)
            self.vox_biomes_lbl.setVisible(not is_water)
            self.vox_biomes_list.setVisible(not is_water)
            self.vox_spawn_dist.setVisible(not is_water)
            self._row_map[self.vox_spawn_dist].setVisible(not is_water)
            
            # Water Color Rows
            self.vox_water_deep_row.setVisible(is_water)
            self.vox_water_shallow_row.setVisible(is_water)
            if is_water:
                self.vox_water_deep_col.blockSignals(True)
                self.vox_water_deep_col.set_color(obj.material.get('base_color', [1,1,1,1]))
                self.vox_water_deep_col.blockSignals(False)
                self.vox_water_shallow_col.blockSignals(True)
                self.vox_water_shallow_col.set_color(obj.material.get('shallow_color', [1,1,1,1]))
                self.vox_water_shallow_col.blockSignals(False)
            
            # Layers — features (3D volumetric)
            self.vox_layers_list.clear()
            if not is_water:
                for f in getattr(obj, 'voxel_features', []):
                    self.vox_layers_list.addItem(f"[Feature] {f}")
                for l in getattr(obj, 'voxel_layers', []):
                    self.vox_layers_list.addItem(l.get('name', 'Layer'))
            self.v_layer_panel.setVisible(False)
            
            # Biomes
            self.vox_biomes_list.clear()
            if not is_water:
                for b in getattr(obj, 'voxel_biomes', []):
                    self.vox_biomes_list.addItem(b.get('name', 'Biome'))
            self.v_biome_panel.setVisible(False)
            self.v_caves_panel.setVisible(False)
        elif obj.obj_type == 'camera':
            self.cam_speed.setValue(getattr(obj, 'camera_speed', 10.0))
            self.cam_sens.setValue(getattr(obj, 'camera_sensitivity', 0.15))
            
        # Logic List Update
        self.logic_list_widget.clear()
        for l_path in getattr(obj, 'logic_list', []):
            item = QListWidgetItem(Path(l_path).name)
            item.setToolTip(l_path)
            self.logic_list_widget.addItem(item)
            
        self._updating = False

        # Refresh shader parameters UI after _updating is False
        if hasattr(self, 'shader_picker_lbl'):
            name = getattr(primary, 'shader_name', '')
            params = getattr(primary, 'shader_params', {})
            self._update_shader_params_ui(name, params)
        # Physics UI sync
        try:
            self.physics_chk.setChecked(bool(getattr(primary, 'physics_enabled', True)))
        except Exception:
            pass
        try:
            self.mass_spin.setValue(float(getattr(primary, 'mass', 1.0)))
        except Exception:
            pass
        # Collisions list
        try:
            self.coll_list.clear()
            cols = getattr(primary, 'collision_properties', []) or []
            for c in cols:
                tag = c.get('tag', 'col')
                shape = c.get('shape', 'sphere')
                radius = c.get('radius', 0.5)
                self.coll_list.addItem(f"{tag} ({shape}) r={radius}")
        except Exception:
            pass

    def set_object(self, obj):
        self.set_objects([obj] if obj else [])

    def _init_landscape_ui(self, layout):
        self.land_group = QGroupBox("Landscape Settings (Deprecated)")
        self.land_group.setStyleSheet(PROPS_SS)
        lg = QVBoxLayout(self.land_group)
        
        # Presets (UE5 Style)
        self.land_preset = QComboBox()
        self.land_preset.addItems(["Custom", "63 x 63", "127 x 127", "255 x 255", "511 x 511", "1023 x 1023"])
        self.land_preset.setStyleSheet(COMBO_SS)
        self.land_preset.currentIndexChanged.connect(self._on_land_preset_changed)
        self._add_property_row(lg, "Preset", self.land_preset)
        
        self.land_type = QComboBox()
        self.land_type.addItems(["Procedural", "Flat"])
        self.land_type.setStyleSheet(COMBO_SS)
        self.land_type.currentTextChanged.connect(lambda t: self.update_obj_prop('landscape_type', t.lower()))
        self._add_property_row(lg, "Type", self.land_type)
        
        self.land_seed = QSpinBox()
        self.land_seed.setRange(0, 999999); self.land_seed.setStyleSheet(SPIN_SS)
        self.land_seed.valueChanged.connect(lambda v: self.update_obj_prop('landscape_seed', v))
        self._add_property_row(lg, "Seed", self.land_seed)
        
        self.land_h_scale = PropertySlider(30.0, 1.0, 200.0)
        self.land_h_scale.valueChanged.connect(lambda v: self.update_obj_prop('landscape_height_scale', v))
        self._add_property_row(lg, "Height Scale", self.land_h_scale)
        
        self.land_res = QSpinBox()
        self.land_res.setRange(8, 2048); self.land_res.setValue(32); self.land_res.setStyleSheet(SPIN_SS)
        self.land_res.valueChanged.connect(lambda v: self.update_obj_prop('landscape_resolution', v))
        self._add_property_row(lg, "Detail", self.land_res)

        self.land_ocean_lvl = PropertySlider(0.0, -10.0, 50.0)
        self.land_ocean_lvl.valueChanged.connect(lambda v: self.update_obj_prop('landscape_ocean_level', v))
        self._add_property_row(lg, "Water Level", self.land_ocean_lvl)
        layout.addWidget(self.land_group)

    def _on_land_preset_changed(self, index):
        if index == 0: return # Custom
        values = [0, 63, 127, 255, 511, 1023]
        res = values[index]
        self.land_res.setValue(res)
        self.update_obj_prop('landscape_chunk_size', float(res))
        self.update_obj_prop('landscape_resolution', int(res / 4)) # Reduced detail for performance

    def _init_ocean_ui(self, layout):
        self.ocean_group = QGroupBox("Ocean Settings")
        self.ocean_group.setStyleSheet(PROPS_SS)
        og = QVBoxLayout(self.ocean_group)

        # Simulation Model
        self.ocean_model = QComboBox()
        self.ocean_model.addItems(["FFT (Advanced Storm)", "Gerstner (Stable Calm)"])
        self.ocean_model.setStyleSheet(COMBO_SS)
        self.ocean_model.currentIndexChanged.connect(lambda i: self.update_obj_prop('ocean_use_fft', i == 0))
        self._add_property_row(og, "Model", self.ocean_model)

        self.ocean_speed = PropertySlider(5.0, 0.0, 20.0)
        self.ocean_speed.valueChanged.connect(lambda v: self.update_obj_prop('ocean_wave_speed', v))
        self._add_property_row(og, "Wave Speed", self.ocean_speed)

        self.ocean_intensity = PropertySlider(1.0, 0.0, 5.0)
        self.ocean_intensity.valueChanged.connect(lambda v: self.update_obj_prop('ocean_wave_intensity', v))
        self._add_property_row(og, "Intensity", self.ocean_intensity)

        self.ocean_choppiness = PropertySlider(1.5, 0.0, 5.0)
        self.ocean_choppiness.valueChanged.connect(lambda v: self.update_obj_prop('ocean_wave_choppiness', v))
        self._add_property_row(og, "Choppiness", self.ocean_choppiness)

        self.ocean_steepness = PropertySlider(0.15, 0.0, 1.0)
        self.ocean_steepness.valueChanged.connect(lambda v: self.update_obj_prop('ocean_wave_steepness', v))
        self._add_property_row(og, "Steepness", self.ocean_steepness)

        # ---- CASCADES ----
        og.addSpacing(8)
        lbl_cas = QLabel("CASCADES")
        lbl_cas.setStyleSheet("color: #4fc3f7; font-size: 10px; font-weight: bold;")
        og.addWidget(lbl_cas)

        self.ocean_cascade1_w = PropertySlider(0.5, 0.0, 2.0)
        self.ocean_cascade1_w.valueChanged.connect(lambda v: self.update_obj_prop('ocean_cascade1_weight', v))
        self._add_property_row(og, "Mid Weight", self.ocean_cascade1_w)

        self.ocean_cascade2_w = PropertySlider(0.3, 0.0, 2.0)
        self.ocean_cascade2_w.valueChanged.connect(lambda v: self.update_obj_prop('ocean_cascade2_weight', v))
        self._add_property_row(og, "Small Weight", self.ocean_cascade2_w)

        # ---- HERO WAVES (Gerstner) ----
        og.addSpacing(8)
        lbl_hw = QLabel("HERO WAVES (Gerstner)")
        lbl_hw.setStyleSheet("color: #4fc3f7; font-size: 10px; font-weight: bold;")
        og.addWidget(lbl_hw)

        self.ocean_hero_count = QComboBox()
        self.ocean_hero_count.addItems(["0 — Disabled", "1 Wave", "2 Waves", "3 Waves"])
        self.ocean_hero_count.setStyleSheet(COMBO_SS)
        self.ocean_hero_count.currentIndexChanged.connect(lambda i: self.update_obj_prop('ocean_hero_count', i))
        self._add_property_row(og, "Count", self.ocean_hero_count)

        self._hero_sliders = []
        _hero_defaults = [(4.0, 350.0, 25.0, 0.25), (3.0, 180.0, 70.0, 0.35), (2.0, 90.0, 140.0, 0.5)]
        for wi in range(3):
            amp_d, wlen_d, dir_d, steep_d = _hero_defaults[wi]
            wlbl = QLabel(f"  Wave {wi + 1}")
            wlbl.setStyleSheet("color: #888; font-size: 10px; margin-top: 3px; font-style: italic;")
            og.addWidget(wlbl)

            amp_s = PropertySlider(amp_d, 0.0, 50.0)
            amp_s.valueChanged.connect(lambda v, i=wi: self.update_obj_prop(f'ocean_hero_amp_{i}', v))
            self._add_property_row(og, "  Amplitude", amp_s)

            wlen_s = PropertySlider(wlen_d, 10.0, 2000.0)
            wlen_s.valueChanged.connect(lambda v, i=wi: self.update_obj_prop(f'ocean_hero_wlen_{i}', v))
            self._add_property_row(og, "  Wavelength", wlen_s)

            dir_s = PropertySlider(dir_d, 0.0, 360.0, step=1.0, decimals=1)
            dir_s.valueChanged.connect(lambda v, i=wi: self.update_obj_prop(f'ocean_hero_dir_{i}', v))
            self._add_property_row(og, "  Direction °", dir_s)

            steep_s = PropertySlider(steep_d, 0.0, 1.0)
            steep_s.valueChanged.connect(lambda v, i=wi: self.update_obj_prop(f'ocean_hero_steep_{i}', v))
            self._add_property_row(og, "  Steepness", steep_s)

            self._hero_sliders.append((amp_s, wlen_s, dir_s, steep_s))

        # ---- ADVANCED VISUALS ----
        og.addSpacing(8)
        lbl_av = QLabel("ADVANCED VISUALS")
        lbl_av.setStyleSheet("color: #4fc3f7; font-size: 10px; font-weight: bold;")
        og.addWidget(lbl_av)

        self.ocean_fresnel = PropertySlider(0.3, 0.0, 1.0)
        self.ocean_fresnel.valueChanged.connect(lambda v: self.update_obj_prop('ocean_fresnel_strength', v))
        self._add_property_row(og, "Fresnel", self.ocean_fresnel)

        self.ocean_specular = PropertySlider(1.0, 0.0, 5.0)
        self.ocean_specular.valueChanged.connect(lambda v: self.update_obj_prop('ocean_specular_intensity', v))
        self._add_property_row(og, "Specular", self.ocean_specular)

        self.ocean_peak_bright = PropertySlider(1.0, 0.0, 3.0)
        self.ocean_peak_bright.valueChanged.connect(lambda v: self.update_obj_prop('ocean_peak_brightness', v))
        self._add_property_row(og, "Peak Bright", self.ocean_peak_bright)

        self.ocean_sss_str = PropertySlider(1.0, 0.0, 5.0)
        self.ocean_sss_str.valueChanged.connect(lambda v: self.update_obj_prop('ocean_sss_strength', v))
        self._add_property_row(og, "SSS Strength", self.ocean_sss_str)

        tint_btn = QPushButton("Select Tint")
        tint_btn.setStyleSheet(BTN_SS)
        tint_btn.clicked.connect(self._on_tint_clicked)
        self._add_property_row(og, "Reflection Tint", tint_btn)

        # ---- FOAM SETTINGS ----
        og.addSpacing(8)
        lbl_foam = QLabel("FOAM SETTINGS")
        lbl_foam.setStyleSheet("color: #4fc3f7; font-size: 10px; font-weight: bold;")
        og.addWidget(lbl_foam)

        self.ocean_foam_jacobian = PropertySlider(1.0, 0.0, 3.0)
        self.ocean_foam_jacobian.valueChanged.connect(lambda v: self.update_obj_prop('ocean_foam_jacobian', v))
        self._add_property_row(og, "Break Foam", self.ocean_foam_jacobian)

        self.ocean_foam_sharpness = PropertySlider(2.5, 0.5, 8.0)
        self.ocean_foam_sharpness.valueChanged.connect(lambda v: self.update_obj_prop('ocean_foam_sharpness', v))
        self._add_property_row(og, "Foam Sharpness", self.ocean_foam_sharpness)

        self.ocean_foam_whitecap = PropertySlider(1.0, 0.0, 3.0)
        self.ocean_foam_whitecap.valueChanged.connect(lambda v: self.update_obj_prop('ocean_foam_whitecap', v))
        self._add_property_row(og, "Whitecap", self.ocean_foam_whitecap)

        self.ocean_foam_whitecap_thresh = PropertySlider(0.5, 0.0, 1.0)
        self.ocean_foam_whitecap_thresh.valueChanged.connect(lambda v: self.update_obj_prop('ocean_foam_whitecap_thresh', v))
        self._add_property_row(og, "Whitecap Height", self.ocean_foam_whitecap_thresh)

        self.ocean_foam_streak = PropertySlider(1.0, 0.0, 3.0)
        self.ocean_foam_streak.valueChanged.connect(lambda v: self.update_obj_prop('ocean_foam_streak', v))
        self._add_property_row(og, "Streak Foam", self.ocean_foam_streak)

        self.ocean_foam_streak_speed = PropertySlider(1.5, 0.0, 3.0)
        self.ocean_foam_streak_speed.valueChanged.connect(lambda v: self.update_obj_prop('ocean_foam_streak_speed', v))
        self._add_property_row(og, "Streak Speed", self.ocean_foam_streak_speed)

        # ---- SURFACE DETAIL ----
        og.addSpacing(8)
        lbl_det = QLabel("SURFACE DETAIL")
        lbl_det.setStyleSheet("color: #4fc3f7; font-size: 10px; font-weight: bold;")
        og.addWidget(lbl_det)

        self.ocean_detail_strength = PropertySlider(0.4, 0.0, 4.0)
        self.ocean_detail_strength.valueChanged.connect(lambda v: self.update_obj_prop('ocean_detail_strength', v))
        self._add_property_row(og, "Micro Detail", self.ocean_detail_strength)

        layout.addWidget(self.ocean_group)
        
    def _init_logic_ui(self, layout):
        # --- Logic Assignment Section ---
        self.logic_group = QGroupBox("Logic Array")
        self.logic_group.setStyleSheet(PROPS_SS)
        lg = QVBoxLayout(self.logic_group)
        
        self.logic_list_widget = QListWidget()
        self.logic_list_widget.setStyleSheet("background: #1e1e1e; border: 1px solid #333; color: #aaa; font-size: 10px;")
        self.logic_list_widget.setFixedHeight(80)
        lg.addWidget(self.logic_list_widget)
        
        btn_row = QHBoxLayout()
        add_btn = QPushButton("+ Add Script")
        add_btn.setStyleSheet(BTN_SS)
        add_btn.clicked.connect(self._on_add_logic)
        
        rem_btn = QPushButton("- Remove")
        rem_btn.setStyleSheet(BTN_SS)
        rem_btn.clicked.connect(self._on_remove_logic)
        
        btn_row.addWidget(add_btn); btn_row.addWidget(rem_btn)
        lg.addLayout(btn_row)
        
        layout.addWidget(self.logic_group)

    def _init_camera_ui(self, layout):
        self.cam_group = QGroupBox("Camera View")
        self.cam_group.setStyleSheet(PROPS_SS)
        lg = QVBoxLayout(self.cam_group)
        
        self.cam_speed = PropertySlider(10.0, 1.0, 100.0)
        self.cam_speed.valueChanged.connect(lambda v: self.update_obj_prop('camera_speed', v))
        self._add_property_row(lg, "Move Speed", self.cam_speed)
        
        self.cam_sens = PropertySlider(0.15, 0.01, 1.0)
        self.cam_sens.valueChanged.connect(lambda v: self.update_obj_prop('camera_sensitivity', v))
        self._add_property_row(lg, "Sensitivity", self.cam_sens)
        
        layout.addWidget(self.cam_group)

    def _on_add_logic(self):
        if not self._current_objects: return
        path, _ = QFileDialog.getOpenFileName(self, "Select Logic File", str(Path.cwd()), "Logic (*.logic)")
        if path:
            for obj in self._current_objects:
                if not hasattr(obj, 'logic_list'): obj.logic_list = []
                if path not in obj.logic_list:
                    obj.logic_list.append(path)
            self.set_objects(self._current_objects)
            self.property_changed.emit()

    def _on_remove_logic(self):
        if not self._current_objects: return
        row = self.logic_list_widget.currentRow()
        if row < 0: return
        
        for obj in self._current_objects:
            if row < len(obj.logic_list):
                obj.logic_list.pop(row)
        self.set_objects(self._current_objects)
        self.property_changed.emit()
        
    def set_prefab(self, path, data):
        """Enter Prefab Editing mode."""
        if not data or not isinstance(data, dict):
            print(f"[PROPERTIES] Invalid prefab data for {path}")
            return
            
        root = data.get("root", {})
        obj = SceneObject.from_dict(root)
        obj.name = Path(path).stem
        
        self._updating = True
        self._current_prefab_path = path
        self._current_mat_path = None
        self.set_objects([obj])
        self.save_btn.setVisible(True)
        self.save_btn.setText("💾 SAVE PREFAB")
        self._updating = False

    def set_spawner(self, path, data):
        if not data or not isinstance(data, dict):
            print(f"[PROPERTIES] Invalid spawner data for {path}")
            return
            
        obj = SceneObject.from_dict({"type": "spawner", **data.get('settings', {})})
        obj.spawner_prefabs = data.get("prefabs", [])
        obj.name = Path(path).stem
        
        self._updating = True
        self._current_spawner_path = path
        self._current_prefab_path = None
        self._current_mat_path = None
        self.set_objects([obj])
        self.save_btn.setVisible(True)
        self.save_btn.setText("💾 SAVE SPAWNER")
        if hasattr(self, 'spawner_group'):
            self.spawner_group.setVisible(True)
            self.spawner_group.setFlat(False)
        self._updating = False

    def set_standalone_material(self, path, data):
        """Enter Standalone Material Editing mode."""
        if not data or not isinstance(data, dict):
            data = {"base_color": [1,1,1,1]}
            
        # Create a proxy sphere to hold the material properties
        obj = SceneObject(Path(path).stem, "sphere")
        obj.material = data
        
        # If the material dict has PBR maps at the root, move them into pbr_maps
        has_pbr = False
        pbr_keys = ["albedo", "normal", "roughness", "metallic", "ao", "displacement"]
        for k in pbr_keys:
            if k in data:
                has_pbr = True
                # Strictly speaking, only move them if they are likely to be paths (strings)
                # while scalar values (roughness/metallic as floats) remain handled by their own sliders logic
                if isinstance(data[k], str):
                    obj.pbr_maps[k] = data[k]
        
        if has_pbr:
            obj.shader_name = "PBR Material"
            
        self._updating = True
        self._current_prefab_path = None
        self._current_mat_path = path
        self.set_objects([obj])
        
        self.save_btn.setVisible(True)
        self.save_btn.setText("💾 SAVE MATERIAL")
        self._updating = False
        
    def _on_save_prefab(self):
        if not self._current_objects: return
        obj = self._current_objects[0]
        import json

        if getattr(self, '_current_prefab_path', None):
            data = {"type": "prefab", "root": obj.to_dict()}
            data = asset_paths.normalize_for_save(data)
            with open(self._current_prefab_path, 'w') as f:
                json.dump(data, f, indent=4)
            print(f"[PROPERTIES] Saved Prefab: {self._current_prefab_path}")
        elif getattr(self, '_current_spawner_path', None):
            prefabs_rel = [asset_paths.to_relative(p) if isinstance(p, str) else p for p in obj.spawner_prefabs]
            data = {
                "type": "spawner",
                "prefabs": prefabs_rel,
                "settings": {
                    "count": obj.spawner_count,
                    "radius": obj.spawner_radius,
                    "min_offset": obj.spawner_min_offset,
                    "max_offset": obj.spawner_max_offset,
                    "min_tint": obj.spawner_min_tint,
                    "max_tint": obj.spawner_max_tint,
                    "find_ground": obj.spawner_find_ground,
                    "controller_type": getattr(obj, "spawner_controller_type", "None")
                }
            }
            data = asset_paths.normalize_for_save(data)
            with open(self._current_spawner_path, 'w') as f:
                json.dump(data, f, indent=4)
            print(f"[PROPERTIES] Saved Spawner: {self._current_spawner_path}")
        elif getattr(self, '_current_mat_path', None) and self._current_mat_path:
            # Save material (PBR maps or basic material dict)
            data = dict(obj.material)
            if obj.shader_name == "PBR Material":
                for k, v in obj.pbr_maps.items():
                    if v: data[k] = v
            data = asset_paths.normalize_for_save(data)
            with open(self._current_mat_path, 'w') as f:
                json.dump(data, f, indent=4)
            print(f"[PROPERTIES] Saved Material: {self._current_mat_path}")

    def _on_tint_clicked(self):
        if not self._current_objects: return
        primary = self._current_objects[0]
        current = getattr(primary, 'ocean_reflection_tint', [0.5, 0.7, 1.0, 1.0])
        color = QColorDialog.getColor(QColor.fromRgbF(current[0], current[1], current[2]), self, "Reflection Tint")
        if color.isValid():
            for obj in self._current_objects:
                obj.ocean_reflection_tint = [color.redF(), color.greenF(), color.blueF(), 1.0]
            self.property_changed.emit()

    def _init_shader_ui(self, layout):
        self.shader_group = QGroupBox("Custom Shaders")
        self.shader_group.setStyleSheet(PROPS_SS)
        sg = QVBoxLayout(self.shader_group)
        
        # Shader Picker
        picker_container = QWidget()
        picker_layout = QHBoxLayout(picker_container)
        picker_layout.setContentsMargins(0,0,0,0)
        
        self.shader_picker_lbl = QLabel("None")
        self.shader_picker_lbl.setStyleSheet("color: #ccc; border: 1px solid #555; border-radius: 4px; padding: 4px;")
        
        btn = QPushButton("Browse...")
        btn.setStyleSheet(BTN_SS)
        btn.clicked.connect(self._browse_shader)
        
        picker_layout.addWidget(self.shader_picker_lbl)
        picker_layout.addWidget(btn)
        
        self._add_property_row(sg, "Shader File", picker_container)
        
        # Shader Parameter Sliders (Context Variable)
        self.shader_params_group = QFrame()
        self.sp_lay = QVBoxLayout(self.shader_params_group)
        self.sp_lay.setContentsMargins(0, 0, 0, 0)
        sg.addWidget(self.shader_params_group)
        
        layout.addWidget(self.shader_group)

    def _browse_shader(self):
        from PyQt6.QtWidgets import QFileDialog
        core_shaders_dir = str(Path(__file__).parent.parent.parent.parent / "shaders")
        path, _ = QFileDialog.getOpenFileName(self, "Select Shader", core_shaders_dir, "Shader Files (*.shader)")
        if path:

            self._on_shader_name_changed(path)

    def _on_shader_name_changed(self, name):
        if self._updating: return
        self.update_obj_prop('shader_name', name)
        self.shader_picker_lbl.setText(Path(name).name)
        
        # Initialize defaults if params are missing for this shader
        for obj in self._current_objects:
            if not obj.shader_params or ('speed' not in obj.shader_params and 'wave_speed' not in obj.shader_params):
                if "fish_swimming" in name.lower() or name == "Fish Swimming":
                    obj.shader_params.update({
                        "speed": 6.0, "freq": 3.0, "intensity": 1.0,
                        "yaw_amp": 0.4, "side_amp": 0.2, "roll_amp": 0.1, "flag_amp": 0.1,
                        "forward_axis": 0.0
                    })
                elif "flag_waving" in name.lower() or name == "Flag Waving":
                    obj.shader_params.update({"wave_speed": 3.0, "wave_amplitude": 0.1})
            
        self.property_changed.emit()
        
        # Refresh params UI based on first obj
        if self._current_objects:
            self._update_shader_params_ui(name, getattr(self._current_objects[0], 'shader_params', {}))

    def _browse_controller(self):
        from PyQt6.QtWidgets import QFileDialog
        ctrl_dir = str(Path(__file__).parent.parent.parent.parent / "controllers")
        path, _ = QFileDialog.getOpenFileName(self, "Select Controller File", ctrl_dir, "Controller Files (*.controller)")
        if path:
            self._on_controller_picked(path)

    def _on_controller_picked(self, name_or_path):
        if self._updating: return
        self.update_obj_prop('controller_type', name_or_path)
        self.controller_picker_lbl.setText(Path(name_or_path).name if '.controller' in name_or_path else name_or_path)
        self.property_changed.emit()

    def _update_shader_params_ui(self, shader_name, params):
        # Clear old
        while self.sp_lay.count():
            child = self.sp_lay.takeAt(0)
            if child.widget(): child.widget().deleteLater()
            
        shader_name_lower = shader_name.lower()
        
        if "fish_swimming" in shader_name_lower or shader_name == "Fish Swimming":
            # Forward Axis Selection
            axis_combo = QComboBox()
            axis_combo.addItems(["X-Forward", "Y-Forward", "Z-Forward"])
            axis_combo.setStyleSheet(COMBO_SS)
            axis_combo.setCurrentIndex(int(params.get("forward_axis", 0)))
            axis_combo.currentIndexChanged.connect(lambda i: self.update_shader_param("forward_axis", float(i)))
            self._add_property_row(self.sp_lay, "Forward Axis", axis_combo)
            
            invert_chk = QCheckBox()
            invert_chk.setChecked(bool(params.get("invert_axis", 0)))
            invert_chk.toggled.connect(lambda c: self.update_shader_param("invert_axis", float(c)))
            self._add_property_row(self.sp_lay, "Invert Axis", invert_chk)
            
            self._add_param_slider("Intensity", "intensity", params.get("intensity", 1.0), 0, 5)
            self._add_param_slider("Speed", "speed", params.get("speed", 5.0), 0, 20)
            self._add_param_slider("Freq", "freq", params.get("freq", 2.0), 0, 10)
            self._add_param_slider("Yaw Amp", "yaw_amp", params.get("yaw_amp", 0.1), 0, 1)
            self._add_param_slider("Side Amp", "side_amp", params.get("side_amp", 0.1), 0, 1)
            self._add_param_slider("Roll Amp", "roll_amp", params.get("roll_amp", 0.05), 0, 0.5)
            self._add_param_slider("Flag Amp", "flag_amp", params.get("flag_amp", 0.05), 0, 0.5)
        elif "flag_waving" in shader_name_lower or shader_name == "Flag Waving":
            invert_chk = QCheckBox()
            invert_chk.setChecked(bool(params.get("invert_axis", 0)))
            invert_chk.toggled.connect(lambda c: self.update_shader_param("invert_axis", float(c)))
            self._add_property_row(self.sp_lay, "Invert Axis", invert_chk)
            
            self._add_param_slider("Wave Speed", "wave_speed", params.get("wave_speed", 3.0), 0, 10)
            self._add_param_slider("Amplitude", "wave_amplitude", params.get("wave_amplitude", 0.1), 0, 0.5)

    def _add_param_slider(self, label, key, val, vmin, vmax):
        slider = PropertySlider(val, vmin, vmax)
        slider.valueChanged.connect(lambda v: self.update_shader_param(key, v))
        self._add_property_row(self.sp_lay, label, slider)

    def _add_property_row(self, layout, label_text, widget):
        container = QWidget()
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        lbl = QLabel(label_text); lbl.setFixedWidth(90); lbl.setStyleSheet(LABEL_SS)
        row.addWidget(lbl); row.addWidget(widget)
        layout.addWidget(container)
        self._row_map[widget] = container
        return container

    def _init_controller_ui(self, layout):
        self.cont_group = QGroupBox("Controller Settings")
        self.cont_group.setStyleSheet(PROPS_SS)
        self.controller_group = self.cont_group
        lg = QVBoxLayout(self.cont_group)
        
        # Controller Picker (Exact match for Shader Picker UI)
        picker_container = QWidget()
        picker_layout = QHBoxLayout(picker_container)
        picker_layout.setContentsMargins(0, 0, 0, 0)
        
        self.controller_picker_lbl = QLabel("None")
        self.controller_picker_lbl.setStyleSheet("color: #ccc; border: 1px solid #555; border-radius: 4px; padding: 4px;")
        
        self.browse_ctrl_btn = QPushButton("Browse...")
        self.browse_ctrl_btn.setStyleSheet(BTN_SS)
        self.browse_ctrl_btn.clicked.connect(self._browse_controller)
        
        picker_layout.addWidget(self.controller_picker_lbl)
        picker_layout.addWidget(self.browse_ctrl_btn)
        
        self._add_property_row(lg, "Controller File", picker_container)
        
        # Physics toggle
        self.physics_chk = QCheckBox("Physics Enabled")
        self.physics_chk.setChecked(False) # Off by default
        self.physics_chk.toggled.connect(lambda c: self.update_obj_prop('physics_enabled', bool(c)))
        self._add_property_row(lg, "Physics", self.physics_chk)

        # Mass for simple collision resolution
        self.mass_spin = QDoubleSpinBox()
        self.mass_spin.setRange(0.01, 10000.0); self.mass_spin.setDecimals(2)
        self.mass_spin.setValue(1.0); self.mass_spin.setStyleSheet(SPIN_SS)
        self.mass_spin.valueChanged.connect(lambda v: self.update_obj_prop('mass', float(v)))
        self._add_property_row(lg, "Mass", self.mass_spin)

        # Simple Collision Properties list (add/remove)
        self.coll_list = QListWidget()
        self.coll_list.setFixedHeight(80)
        self._add_property_row(lg, "Collisions", self.coll_list)
        btn_row = QHBoxLayout()
        add_c = QPushButton("+")
        rm_c = QPushButton("-")
        add_c.setFixedWidth(30); rm_c.setFixedWidth(30)
        add_c.setStyleSheet(BTN_SS); rm_c.setStyleSheet(BTN_SS)
        add_c.clicked.connect(self._on_add_collision)
        rm_c.clicked.connect(self._on_remove_collision)
        btn_row.addWidget(add_c); btn_row.addWidget(rm_c)
        lg.addLayout(btn_row)
        
        layout.addWidget(self.cont_group)

    def _init_voxel_ui(self, layout):
        import json, os

        self.vox_group = QGroupBox("Voxel World Settings")
        self.vox_group.setStyleSheet(PROPS_SS)
        self.voxel_group = self.vox_group
        vg = QVBoxLayout(self.vox_group)

        # Mode
        self.vox_type = QComboBox()
        self.vox_type.addItems(["Round", "Flat"])
        self.vox_type.setStyleSheet(COMBO_SS)
        self.vox_type.currentTextChanged.connect(self._on_vox_type_changed)
        self.vox_type_row = self._add_property_row(vg, "Mode", self.vox_type)

        # Infinite flat terrain — streams chunks around the camera for flat mode.
        # Hidden for Round mode (always bounded by radius).
        self.vox_infinite_flat = QCheckBox("Infinite (stream around camera)")
        self.vox_infinite_flat.setChecked(True)
        self.vox_infinite_flat.setStyleSheet("color: #ddd; font-size: 11px; padding: 2px 0;")
        self.vox_infinite_flat.setToolTip(
            "When on, flat voxel terrain streams chunks around the camera (no fixed size).\n"
            "Turn off to pin a 100u × 40u × 100u box around the object's position.")
        self.vox_infinite_flat.toggled.connect(
            lambda v: self.update_obj_prop('voxel_infinite_flat', bool(v)))
        vg.addWidget(self.vox_infinite_flat)

        # Render Style
        self.vox_render_style = QComboBox()
        self.vox_render_style.addItems(["Smooth", "Blocky"])
        self.vox_render_style.setStyleSheet(COMBO_SS)
        self.vox_render_style.setToolTip(
            "Smooth = No Man's Sky style (interpolated verts + smoothing)\n"
            "Blocky = Classic cube look (no smoothing, no interpolation)")
        self.vox_render_style.currentTextChanged.connect(
            lambda t: self.update_obj_prop('voxel_render_style', t))
        self._add_property_row(vg, "Style", self.vox_render_style)

        # Radius (preset dropdown) — safer than free slider
        # Ordered smallest → largest so names match real-world intuition:
        #   Pebble < Asteroid < Dwarf Planet < Moon < Planet
        self.vox_radius_presets_list = [
            ("Pebble (0.5 u)", 0.5),
            ("Asteroid (5 u) — Default", 5.0),
            ("Dwarf Planet (50 u)", 50.0),
            ("Moon (500 u)", 500.0),
            ("Small Planet (2,000 u)", 2000.0),
            ("Planet (10,000 u)", 10000.0),
            ("Large Planet (60,000 u)", 60000.0),
            ("Huge Planet (150,000 u) — extreme scale", 150000.0),
        ]
        self.vox_radius = QComboBox()
        for name, _ in self.vox_radius_presets_list:
            self.vox_radius.addItem(name)
        self.vox_radius.setToolTip("Select a world size preset. Large sizes may be heavy — they use chunked LOD generation.")
        self.vox_radius.currentIndexChanged.connect(self._on_vox_radius_changed)
        self._last_vox_radius_index = 1  # Default = Small Planet
        self.vox_radius_row = self._add_property_row(vg, "Radius", self.vox_radius)

        # Detail Level (preset dropdown) — maps to voxel block size internally.
        # block_size is the physical world-unit length of one voxel face.
        # Effective resolution = world_diameter / block_size, capped at 512.
        self.vox_detail_presets_list = [
            ("Draft (16.0 u/voxel)", 16.0),
            ("Low (4.0 u/voxel)", 4.0),
            ("Medium (1.0 u/voxel) — Default", 1.0),
            ("High (0.5 u/voxel)", 0.5),
            ("Ultra (0.1 u/voxel)", 0.1),
        ]
        self.vox_detail_combo = QComboBox()
        for name, _ in self.vox_detail_presets_list:
            self.vox_detail_combo.addItem(name)
        self.vox_detail_combo.setToolTip(
            "Voxel face size in world units. Smaller = finer terrain detail, heavier to generate.\n"
            "Minimum enforced by style: Smooth ≥ 0.5 u/voxel, Blocky ≥ 1.0 u/voxel.\n"
            "LOD tiles are generated automatically based on camera distance.")
        self.vox_detail_combo.currentIndexChanged.connect(self._on_vox_detail_changed)
        self._add_property_row(vg, "Detail", self.vox_detail_combo)

        # LOD is now always camera-distance-based — no manual toggle needed.
        # A small info label replaces the old checkbox.
        lod_info = QLabel("✓ Camera-distance LOD  (automatic)")
        lod_info.setStyleSheet("color: #4fc3f7; font-size: 10px; font-weight: bold; padding: 2px 0;")
        vg.addWidget(lod_info)

        # Smoothing passes (only used in Smooth style)
        self.vox_smooth = QSpinBox()
        self.vox_smooth.setRange(0, 8)
        self.vox_smooth.setStyleSheet(SPIN_SS)
        self.vox_smooth.setToolTip("Gaussian smoothing passes (Smooth style only). 2–4 is ideal.")
        self.vox_smooth.valueChanged.connect(lambda v: self.update_obj_prop('voxel_smooth_iterations', v))
        self._add_property_row(vg, "Smoothing", self.vox_smooth)

        # Seed
        self.vox_seed = QSpinBox()
        self.vox_seed.setRange(0, 999999)
        self.vox_seed.setStyleSheet(SPIN_SS)
        self.vox_seed.valueChanged.connect(lambda v: self.update_obj_prop('voxel_seed', v))
        self._add_property_row(vg, "Seed", self.vox_seed)

        # World Height — multiplier on layer amp_scale (flat mode).
        # 1.0 = stock, 5.0 lets mountains rise 5× higher.
        self.vox_world_height = PropertySlider(1.0, 0.1, 20.0)
        self.vox_world_height.valueChanged.connect(
            lambda v: self.update_obj_prop('voxel_world_height', float(v)))
        self.vox_world_height_row = self._add_property_row(vg, "World Height", self.vox_world_height)

        # Prefetch neighborhood for chunked LOD (per-object override)
        self.vox_prefetch = QSpinBox()
        self.vox_prefetch.setRange(0, 5)
        self.vox_prefetch.setStyleSheet(SPIN_SS)
        self.vox_prefetch.setToolTip("Number of neighboring chunks to prefetch around the camera.")
        self.vox_prefetch.valueChanged.connect(lambda v: self.update_obj_prop('voxel_prefetch_neighborhood', int(v)))
        self._add_property_row(vg, "Prefetch", self.vox_prefetch)

        # Spawn draw distance — keeps biome spawn density high up close without
        # paying to render thousands of grass meshes on distant chunks.
        self.vox_spawn_dist = PropertySlider(120.0, 20.0, 800.0)
        self.vox_spawn_dist.setToolTip("Max camera distance (meters) at which biome spawns are drawn.")
        self.vox_spawn_dist.valueChanged.connect(
            lambda v: self.update_obj_prop('voxel_spawn_max_distance', float(v)))
        self._add_property_row(vg, "Spawn Distance", self.vox_spawn_dist)

        # Max single-chunk resolution threshold
        self.vox_max_chunk_res = QSpinBox()
        self.vox_max_chunk_res.setRange(16, 512)
        self.vox_max_chunk_res.setStyleSheet(SPIN_SS)
        self.vox_max_chunk_res.setToolTip("Max resolution to keep as a single generation pass before chunking.")
        self.vox_max_chunk_res.valueChanged.connect(lambda v: self.update_obj_prop('voxel_max_single_chunk_res', int(v)))
        self._add_property_row(vg, "MaxChunkRes", self.vox_max_chunk_res)

        # --- Voxel Water Specifics ---
        self.vox_water_level = PropertySlider(0.0, -100.0, 100.0)
        self.vox_water_level.valueChanged.connect(lambda v: self.update_obj_prop('voxel_water_level', float(v)))
        self.vox_water_level_row = self._add_property_row(vg, "Water Level", self.vox_water_level)

        self.vox_water_speed = PropertySlider(1.0, 0.1, 10.0)
        self.vox_water_speed.valueChanged.connect(lambda v: self.update_obj_prop('voxel_water_speed', float(v)))
        self.vox_water_speed_row = self._add_property_row(vg, "Flow Speed", self.vox_water_speed)

        self.vox_water_surge = PropertySlider(0.5, 0.0, 5.0)
        self.vox_water_surge.valueChanged.connect(lambda v: self.update_obj_prop('voxel_water_surge', float(v)))
        self.vox_water_surge_row = self._add_property_row(vg, "Surge/Climb", self.vox_water_surge)
        
        # Color Controls
        self.vox_water_deep_col = ColorPickerButton([0.05, 0.45, 0.85, 0.8])
        self.vox_water_deep_col.colorChanged.connect(
            lambda c: self._update_vox_water_mat('base_color', list(c)))
        self.vox_water_deep_row = self._add_property_row(vg, "Water Color", self.vox_water_deep_col)
        
        self.vox_water_shallow_col = ColorPickerButton([0.1, 0.8, 0.9, 1.0])
        self.vox_water_shallow_col.colorChanged.connect(
            lambda c: self._update_vox_water_mat('shallow_color', list(c)))
        self.vox_water_shallow_row = self._add_property_row(vg, "Shallow Tint", self.vox_water_shallow_col)

        # ---- FEATURE LAYERS (context-menu driven) ----
        vg.addSpacing(8)
        self.vox_layers_lbl = QLabel("FEATURE LAYERS  (right-click to add / presets)")
        self.vox_layers_lbl.setStyleSheet("color: #4fc3f7; font-size: 10px; font-weight: bold;")
        vg.addWidget(self.vox_layers_lbl)

        self.vox_layers_list = QListWidget()
        self.vox_layers_list.setStyleSheet(
            "background: #1e1e1e; border: 1px solid #333; color: #aaa; font-size: 10px;")
        self.vox_layers_list.setFixedHeight(80)
        self.vox_layers_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.vox_layers_list.customContextMenuRequested.connect(self._on_vox_layer_context)
        self.vox_layers_list.currentRowChanged.connect(self._on_vox_layer_selected)
        vg.addWidget(self.vox_layers_list)

        # ---- Layer Detail Panel ----
        self.v_layer_panel = QFrame()
        self.v_layer_panel.setVisible(False)
        vlg = QVBoxLayout(self.v_layer_panel)
        vlg.setContentsMargins(0, 5, 0, 0)

        # Noise type
        self.vl_noise_type = QComboBox()
        self.vl_noise_type.addItems(["perlin", "fbm", "ridged", "voronoi", "caves"])
        self.vl_noise_type.setStyleSheet(COMBO_SS)
        self.vl_noise_type.currentTextChanged.connect(
            lambda v: self._update_selected_vox_layer('noise_type', v))
        self._add_property_row(vlg, "Noise Type", self.vl_noise_type)

        # Blend mode
        self.vl_blend = QComboBox()
        self.vl_blend.addItems(["add", "subtract", "multiply"])
        self.vl_blend.setStyleSheet(COMBO_SS)
        self.vl_blend.currentTextChanged.connect(
            lambda v: self._update_selected_vox_layer('blend', v))
        self._add_property_row(vlg, "Blend", self.vl_blend)

        # Frequency
        self.vl_freq = PropertySlider(1.0, 0.01, 20.0)
        self.vl_freq.valueChanged.connect(lambda v: self._update_selected_vox_layer('freq', v))
        self._add_property_row(vlg, "Frequency", self.vl_freq)

        # Amplitude
        self.vl_amp = PropertySlider(0.1, 0.0, 1.0)
        self.vl_amp.valueChanged.connect(lambda v: self._update_selected_vox_layer('amp', v))
        self._add_property_row(vlg, "Amplitude", self.vl_amp)

        # Mask Threshold (only grow in high ground)
        self.vl_mask = PropertySlider(0.0, 0.0, 1.0)
        self.vl_mask.valueChanged.connect(lambda v: self._update_selected_vox_layer('mask_threshold', v))
        self._add_property_row(vlg, "Mask", self.vl_mask)

        # Seed
        self.vl_seed = QSpinBox()
        self.vl_seed.setRange(0, 999999)
        self.vl_seed.setStyleSheet(SPIN_SS)
        self.vl_seed.valueChanged.connect(lambda v: self._update_selected_vox_layer('seed', v))
        self._add_property_row(vlg, "Seed", self.vl_seed)
        vg.addWidget(self.v_layer_panel)

        # ---- Caves Feature Detail Panel ----
        # Shown when the `[Feature] caves` row is selected in the list. Writes
        # directly to the voxel_cave_* object attributes (same object, not a
        # per-feature sub-dict) so existing scenes keep working.
        self.v_caves_panel = QFrame()
        self.v_caves_panel.setVisible(False)
        vcg = QVBoxLayout(self.v_caves_panel)
        vcg.setContentsMargins(0, 5, 0, 0)

        self.vc_tunnel_scale = PropertySlider(28.0, 4.0, 200.0)
        self.vc_tunnel_scale.valueChanged.connect(
            lambda v: self.update_obj_prop('voxel_cave_tunnel_scale', float(v)))
        self._add_property_row(vcg, "Tunnel Scale", self.vc_tunnel_scale)

        self.vc_tunnel_radius = PropertySlider(0.10, 0.02, 0.40)
        self.vc_tunnel_radius.valueChanged.connect(
            lambda v: self.update_obj_prop('voxel_cave_tunnel_radius', float(v)))
        self._add_property_row(vcg, "Tunnel Radius", self.vc_tunnel_radius)

        self.vc_cavern_scale = PropertySlider(60.0, 10.0, 400.0)
        self.vc_cavern_scale.valueChanged.connect(
            lambda v: self.update_obj_prop('voxel_cave_cavern_scale', float(v)))
        self._add_property_row(vcg, "Cavern Scale", self.vc_cavern_scale)

        self.vc_cavern_radius = PropertySlider(0.05, 0.0, 0.40)
        self.vc_cavern_radius.valueChanged.connect(
            lambda v: self.update_obj_prop('voxel_cave_cavern_radius', float(v)))
        self._add_property_row(vcg, "Cavern Radius", self.vc_cavern_radius)

        self.vc_waterline = PropertySlider(0.0, -500.0, 500.0)
        self.vc_waterline.valueChanged.connect(
            lambda v: self.update_obj_prop('voxel_cave_waterline', float(v)))
        self._add_property_row(vcg, "Waterline Y", self.vc_waterline)

        self.vc_max_depth = PropertySlider(512.0, 10.0, 4096.0)
        self.vc_max_depth.valueChanged.connect(
            lambda v: self.update_obj_prop('voxel_cave_max_depth', float(v)))
        self._add_property_row(vcg, "Max Depth", self.vc_max_depth)

        vg.addWidget(self.v_caves_panel)

        # ---- BIOMES (context-menu driven) ----
        vg.addSpacing(8)
        self.vox_biomes_lbl = QLabel("BIOMES  (right-click to add / presets)")
        self.vox_biomes_lbl.setStyleSheet("color: #4fc3f7; font-size: 10px; font-weight: bold;")
        vg.addWidget(self.vox_biomes_lbl)

        self.vox_biomes_list = QListWidget()
        self.vox_biomes_list.setStyleSheet(
            "background: #1e1e1e; border: 1px solid #333; color: #aaa; font-size: 10px;")
        self.vox_biomes_list.setFixedHeight(80)
        self.vox_biomes_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.vox_biomes_list.customContextMenuRequested.connect(self._on_vox_biome_context)
        self.vox_biomes_list.currentRowChanged.connect(self._on_vox_biome_selected)
        vg.addWidget(self.vox_biomes_list)

        # ---- Biome Detail Panel ----
        self.v_biome_panel = QFrame()
        self.v_biome_panel.setVisible(False)
        vbg = QVBoxLayout(self.v_biome_panel)
        vbg.setContentsMargins(0, 5, 0, 0)

        self.vb_material = QComboBox()
        self.vb_material.addItems(get_shader_list())
        self.vb_material.setStyleSheet(COMBO_SS)
        self.vb_material.currentTextChanged.connect(
            lambda n: self._update_selected_vox_biome('material', str(n)))
        self._add_property_row(vbg, "Material", self.vb_material)

        self.vb_color = ColorPickerButton([0.5, 0.5, 0.5, 1.0])
        self.vb_color.colorChanged.connect(
            lambda c: self._update_selected_vox_biome('color', list(c)))
        self._add_property_row(vbg, "Color", self.vb_color)

        self.vb_rough = PropertySlider(0.8, 0.0, 1.0)
        self.vb_rough.valueChanged.connect(
            lambda v: self._update_selected_vox_biome('roughness', float(v)))
        self._add_property_row(vbg, "Roughness", self.vb_rough)

        self.vb_metallic = PropertySlider(0.0, 0.0, 1.0)
        self.vb_metallic.valueChanged.connect(
            lambda v: self._update_selected_vox_biome('metallic', float(v)))
        self._add_property_row(vbg, "Metallic", self.vb_metallic)

        self.vb_h_min = PropertySlider(0.0, -1000.0, 1000.0)
        self.vb_h_min.valueChanged.connect(
            lambda v: self._update_selected_vox_biome('height_min', float(v)))
        self._add_property_row(vbg, "Height Min", self.vb_h_min)

        self.vb_h_max = PropertySlider(10.0, -1000.0, 1000.0)
        self.vb_h_max.valueChanged.connect(
            lambda v: self._update_selected_vox_biome('height_max', float(v)))
        self._add_property_row(vbg, "Height Max", self.vb_h_max)

        self.vb_s_min = PropertySlider(0.0, 0.0, 1.0)
        self.vb_s_min.valueChanged.connect(
            lambda v: self._update_selected_vox_biome('slope_min', float(v)))
        self._add_property_row(vbg, "Slope Min", self.vb_s_min)

        self.vb_s_max = PropertySlider(1.0, 0.0, 1.0)
        self.vb_s_max.valueChanged.connect(
            lambda v: self._update_selected_vox_biome('slope_max', float(v)))
        self._add_property_row(vbg, "Slope Max", self.vb_s_max)

        # ---- Spawners sub-panel (per biome) ----
        spawn_lbl = QLabel("Spawners")
        spawn_lbl.setStyleSheet(LABEL_SS)
        vbg.addWidget(spawn_lbl)

        self.vb_spawn_list = QListWidget()
        self.vb_spawn_list.setStyleSheet(LIST_SS)
        self.vb_spawn_list.setFixedHeight(70)
        self.vb_spawn_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.vb_spawn_list.customContextMenuRequested.connect(self._on_vb_spawn_context)
        self.vb_spawn_list.currentRowChanged.connect(self._on_vb_spawn_selected)
        vbg.addWidget(self.vb_spawn_list)

        self.vb_spawn_panel = QFrame()
        self.vb_spawn_panel.setVisible(False)
        spg = QVBoxLayout(self.vb_spawn_panel)
        spg.setContentsMargins(0, 2, 0, 0)

        self.vbs_kind = QComboBox()
        self.vbs_kind.addItems(["object:cube", "object:sphere", "object:plane",
                                "object:cylinder", "object:cone", "object:mesh",
                                "prefab"])
        self.vbs_kind.setStyleSheet(COMBO_SS)
        self.vbs_kind.currentTextChanged.connect(
            lambda v: self._update_selected_vb_spawn('kind', str(v)))
        self._add_property_row(spg, "Kind", self.vbs_kind)

        from PyQt6.QtWidgets import QHBoxLayout
        vbs_row = QWidget()
        vbs_rowl = QHBoxLayout(vbs_row)
        vbs_rowl.setContentsMargins(0, 0, 0, 0); vbs_rowl.setSpacing(4)
        self.vbs_prefab = QLineEdit()
        self.vbs_prefab.setPlaceholderText("Pick a .prefab / .mesh / .fbx / .obj…")
        self.vbs_prefab.editingFinished.connect(
            lambda: self._update_selected_vb_spawn('prefab_path', self.vbs_prefab.text()))
        vbs_browse = QPushButton("Browse…")
        vbs_browse.setStyleSheet(BTN_SS)
        vbs_browse.clicked.connect(self._on_browse_vb_spawn_asset)
        vbs_rowl.addWidget(self.vbs_prefab, 1)
        vbs_rowl.addWidget(vbs_browse)
        self._add_property_row(spg, "Asset", vbs_row)

        self.vbs_shader = QComboBox()
        self.vbs_shader.addItems(get_shader_list())
        self.vbs_shader.setStyleSheet(COMBO_SS)
        self.vbs_shader.currentTextChanged.connect(
            lambda v: self._update_selected_vb_spawn('shader_name', str(v)))
        self._add_property_row(spg, "Shader", self.vbs_shader)

        self.vbs_material = MaterialSlotWidget()
        self.vbs_material.material_dropped.connect(
            lambda v: self._update_selected_vb_spawn('material_path', str(v)))
        self._add_property_row(spg, "Material", self.vbs_material)

        self.vbs_density = PropertySlider(0.05, 0.0, 1.0)
        self.vbs_density.valueChanged.connect(
            lambda v: self._update_selected_vb_spawn('density', float(v)))
        self._add_property_row(spg, "Density", self.vbs_density)

        self.vbs_max_dist = PropertySlider(120.0, 10.0, 2000.0)
        self.vbs_max_dist.setToolTip("Max camera distance (meters) at which this spawner is drawn.")
        self.vbs_max_dist.valueChanged.connect(
            lambda v: self._update_selected_vb_spawn('max_distance', float(v)))
        self._add_property_row(spg, "Max Distance", self.vbs_max_dist)

        self.vbs_slope_min = PropertySlider(0.7, 0.0, 1.0)
        self.vbs_slope_min.valueChanged.connect(
            lambda v: self._update_selected_vb_spawn('slope_min', float(v)))
        self._add_property_row(spg, "Slope Min", self.vbs_slope_min)

        self.vbs_slope_max = PropertySlider(1.0, 0.0, 1.0)
        self.vbs_slope_max.valueChanged.connect(
            lambda v: self._update_selected_vb_spawn('slope_max', float(v)))
        self._add_property_row(spg, "Slope Max", self.vbs_slope_max)

        self.vbs_h_min = PropertySlider(-1000.0, -10000.0, 10000.0)
        self.vbs_h_min.valueChanged.connect(
            lambda v: self._update_selected_vb_spawn('height_min', float(v)))
        self._add_property_row(spg, "Height Min", self.vbs_h_min)

        self.vbs_h_max = PropertySlider(1000.0, -10000.0, 10000.0)
        self.vbs_h_max.valueChanged.connect(
            lambda v: self._update_selected_vb_spawn('height_max', float(v)))
        self._add_property_row(spg, "Height Max", self.vbs_h_max)

        self.vbs_scale_min = PropertySlider(0.8, 0.05, 20.0)
        self.vbs_scale_min.valueChanged.connect(
            lambda v: self._update_selected_vb_spawn('scale_min', float(v)))
        self._add_property_row(spg, "Scale Min", self.vbs_scale_min)

        self.vbs_scale_max = PropertySlider(1.2, 0.05, 20.0)
        self.vbs_scale_max.valueChanged.connect(
            lambda v: self._update_selected_vb_spawn('scale_max', float(v)))
        self._add_property_row(spg, "Scale Max", self.vbs_scale_max)

        self.vbs_jitter = PropertySlider(0.3, 0.0, 1.0)
        self.vbs_jitter.valueChanged.connect(
            lambda v: self._update_selected_vb_spawn('jitter', float(v)))
        self._add_property_row(spg, "Jitter", self.vbs_jitter)

        self.vbs_align = QCheckBox("Align to surface normal")
        self.vbs_align.stateChanged.connect(
            lambda s: self._update_selected_vb_spawn('align_to_normal', bool(s)))
        spg.addWidget(self.vbs_align)

        # Dynamic Shader Params Container
        self.vbs_param_container = QWidget()
        self.vbs_param_layout = QVBoxLayout(self.vbs_param_container)
        self.vbs_param_layout.setContentsMargins(0, 5, 0, 0)
        self.vbs_param_layout.setSpacing(4)
        spg.addWidget(self.vbs_param_container)

        vbg.addWidget(self.vb_spawn_panel)

        vg.addWidget(self.v_biome_panel)

        layout.addWidget(self.vox_group)


    def _on_vox_biome_context(self, pos):
        if not self._current_objects: return
        menu = QMenu(self)
        menu.setStyleSheet("background:#252526; color:#ccc;")
        
        add_blank = menu.addAction("Add Blank Biome")
        preset_menu = menu.addMenu("Add from Preset")
        for p_name in self.VOXEL_BIOME_PRESETS.keys():
            preset_menu.addAction(p_name)
            
        menu.addSeparator()
        row = self.vox_biomes_list.currentRow()
        ren_a  = menu.addAction("Rename...")
        del_a  = menu.addAction("Remove")
        ren_a.setEnabled(row >= 0)
        del_a.setEnabled(row >= 0)
        
        action = menu.exec(self.vox_biomes_list.mapToGlobal(pos))
        if not action: return
        
        if action == add_blank:
            for obj in self._current_objects:
                if not hasattr(obj, 'voxel_biomes'): obj.voxel_biomes = []
                obj.voxel_biomes.append({
                    "name": f"Biome {len(obj.voxel_biomes)}",
                    "height_range": [0.0, 10.0], "slope_range": [0.0, 1.0],
                    "surface": {"color": [0.5, 0.5, 0.5, 1.0], "roughness": 0.8, "metallic": 0.0}
                })
        elif action.parent() == preset_menu:
            p_name = action.text()
            p = self.VOXEL_BIOME_PRESETS[p_name]
            for obj in self._current_objects:
                if not hasattr(obj, 'voxel_biomes'): obj.voxel_biomes = []
                obj.voxel_biomes.append({
                    "name": p_name,
                    "height_range": p['range'], "slope_range": [0.0, 1.0],
                    "surface": {"color": p['color'], "roughness": p['rough'], "metallic": 0.0},
                    "spawns": p.get('spawns', [])
                })
        elif action == del_a:
            for obj in self._current_objects:
                if hasattr(obj, 'voxel_biomes') and row < len(obj.voxel_biomes):
                    obj.voxel_biomes.pop(row)
        elif action == ren_a:
            from PyQt6.QtWidgets import QInputDialog
            obj = self._current_objects[0]
            biomes = getattr(obj, 'voxel_biomes', [])
            cur = biomes[row]['name'] if row < len(biomes) else ''
            name, ok = QInputDialog.getText(self, "Rename Biome", "Name:", text=cur)
            if ok and name:
                for o in self._current_objects:
                    bio = getattr(o, 'voxel_biomes', [])
                    if row < len(bio): bio[row]['name'] = name
        
        self.set_objects(self._current_objects)
        self.property_changed.emit()

    def _on_vox_layer_context(self, pos):
        if not self._current_objects: return
        menu = QMenu(self)
        menu.setStyleSheet("background:#252526; color:#ccc;")
        
        add_blank = menu.addAction("Add Blank Layer")
        preset_menu = menu.addMenu("Add from Preset")
        for p_name in self.VOXEL_LAYER_PRESETS.keys():
            preset_menu.addAction(p_name)
            
        menu.addSeparator()
        row = self.vox_layers_list.currentRow()
        ren_a  = menu.addAction("Rename...")
        del_a  = menu.addAction("Remove")
        ren_a.setEnabled(row >= 0)
        del_a.setEnabled(row >= 0)
        
        action = menu.exec(self.vox_layers_list.mapToGlobal(pos))
        if not action: return
        
        if action == add_blank:
            for obj in self._current_objects:
                if not hasattr(obj, 'voxel_layers'): obj.voxel_layers = []
                obj.voxel_layers.append({"name": f"Layer {len(obj.voxel_layers)}", "freq": 1.0, "amp": 0.1, "seed": 123 + len(obj.voxel_layers)})
        elif action.parent() == preset_menu:
            p_name = action.text()
            p = self.VOXEL_LAYER_PRESETS[p_name]
            # "Caves" is a 3D subsurface feature, not a 2D heightmap layer.
            # Adding it as a layer raises the ground (the `caves` noise returns
            # negative values, blend='subtract' → height increases → mountains).
            # Route it to voxel_features so the engine carves real tunnels.
            if p.get('noise_type') == 'caves':
                for obj in self._current_objects:
                    if not hasattr(obj, 'voxel_features'): obj.voxel_features = []
                    if 'caves' not in obj.voxel_features:
                        obj.voxel_features.append('caves')
            else:
                for obj in self._current_objects:
                    if not hasattr(obj, 'voxel_layers'): obj.voxel_layers = []
                    obj.voxel_layers.append({
                        "name": p_name,
                        "noise_type": p.get('noise_type', 'perlin'),
                        "freq": p['freq'], "amp": p['amp'], "blend": p.get('blend', 'add'),
                        "seed": 123 + len(obj.voxel_layers)
                    })
        elif action == del_a:
            # Feature rows come first in the list; rows < n_features remove
            # features, later rows remove voxel_layers with an offset.
            for obj in self._current_objects:
                feats = getattr(obj, 'voxel_features', [])
                n_feats = len(feats)
                if row < n_feats:
                    feats.pop(row)
                else:
                    lrow = row - n_feats
                    if hasattr(obj, 'voxel_layers') and lrow < len(obj.voxel_layers):
                        obj.voxel_layers.pop(lrow)
        elif action == ren_a:
            from PyQt6.QtWidgets import QInputDialog
            obj = self._current_objects[0]
            n_feats = len(getattr(obj, 'voxel_features', []))
            if row < n_feats:
                # Features are fixed identifiers, not user-renamable.
                return
            lrow = row - n_feats
            layers = getattr(obj, 'voxel_layers', [])
            cur = layers[lrow]['name'] if lrow < len(layers) else ''
            name, ok = QInputDialog.getText(self, "Rename Layer", "Name:", text=cur)
            if ok and name:
                for o in self._current_objects:
                    lay = getattr(o, 'voxel_layers', [])
                    n_f = len(getattr(o, 'voxel_features', []))
                    lr = row - n_f
                    if 0 <= lr < len(lay): lay[lr]['name'] = name
                    
        self.set_objects(self._current_objects)
        self.property_changed.emit()
    def _on_add_collision(self):
        if not self._current_objects: return
        for obj in self._current_objects:
            if not hasattr(obj, 'collision_properties') or obj.collision_properties is None:
                obj.collision_properties = []
            obj.collision_properties.append({
                'tag': f'col{len(obj.collision_properties)}', 'shape': 'sphere', 'radius': 0.5, 'offset': [0.0,0.0,0.0], 'enabled': True
            })
        self.set_objects(self._current_objects)
        self.property_changed.emit()

    def _on_remove_collision(self):
        if not self._current_objects: return
        row = self.coll_list.currentRow()
        if row < 0: return
        for obj in self._current_objects:
            if hasattr(obj, 'collision_properties') and row < len(obj.collision_properties):
                obj.collision_properties.pop(row)
        self.set_objects(self._current_objects)
        self.property_changed.emit()

    def _on_vox_radius_changed(self, index):
        if self._updating: return
        _, val = self.vox_radius_presets_list[index]
        self._last_vox_radius_index = index
        self.update_obj_prop('voxel_radius', float(val))

    def _on_vox_detail_changed(self, index):
        if self._updating: return
        _, val = self.vox_detail_presets_list[index]
        self.update_obj_prop('voxel_block_size', float(val))

    def _on_vox_layer_selected(self, row):
        if row < 0 or not self._current_objects:
            self.v_layer_panel.setVisible(False)
            self.v_caves_panel.setVisible(False)
            return
        obj = self._current_objects[0]
        n_feats = len(getattr(obj, 'voxel_features', []))
        if row < n_feats:
            # Feature row: show the matching feature panel if we have one.
            self.v_layer_panel.setVisible(False)
            feat = obj.voxel_features[row]
            if feat == 'caves':
                self._updating = True
                self.vc_tunnel_scale.setValue(float(getattr(obj, 'voxel_cave_tunnel_scale',  28.0)))
                self.vc_tunnel_radius.setValue(float(getattr(obj, 'voxel_cave_tunnel_radius', 0.10)))
                self.vc_cavern_scale.setValue(float(getattr(obj, 'voxel_cave_cavern_scale',  60.0)))
                self.vc_cavern_radius.setValue(float(getattr(obj, 'voxel_cave_cavern_radius', 0.05)))
                self.vc_waterline.setValue(float(getattr(obj, 'voxel_cave_waterline', 0.0)))
                self.vc_max_depth.setValue(float(getattr(obj, 'voxel_cave_max_depth', 512.0)))
                self._updating = False
                self.v_caves_panel.setVisible(True)
            else:
                self.v_caves_panel.setVisible(False)
            return
        self.v_caves_panel.setVisible(False)
        lrow = row - n_feats
        layers = getattr(obj, 'voxel_layers', [])
        if lrow >= len(layers):
            self.v_layer_panel.setVisible(False)
            return
        row = lrow
        self.v_layer_panel.setVisible(True)
        l = layers[row]
        self._updating = True
        nt_idx = self.vl_noise_type.findText(l.get('noise_type', 'perlin'))
        if nt_idx >= 0: self.vl_noise_type.setCurrentIndex(nt_idx)
        bl_idx = self.vl_blend.findText(l.get('blend', 'add'))
        if bl_idx >= 0: self.vl_blend.setCurrentIndex(bl_idx)
        self.vl_freq.setValue(l.get('freq', 1.0))
        self.vl_amp.setValue(l.get('amp', 0.1))
        self.vl_mask.setValue(l.get('mask_threshold', 0.0))
        self.vl_seed.setValue(int(l.get('seed', 123)))
        self._updating = False

    def _on_vox_biome_selected(self, row):
        if row < 0 or not self._current_objects:
            self.v_biome_panel.setVisible(False)
            return
        obj = self._current_objects[0]
        biomes = getattr(obj, 'voxel_biomes', [])
        if row >= len(biomes):
            self.v_biome_panel.setVisible(False)
            return
        b = biomes[row]
        surf = b.get('surface', {})
        hrng = b.get('height_range', [0.0, 10.0])
        srng = b.get('slope_range', [0.0, 1.0])
        self._updating = True
        mat = surf.get('material', 'Standard')
        mi = self.vb_material.findText(mat)
        if mi >= 0: self.vb_material.setCurrentIndex(mi)
        self.vb_color.set_color(surf.get('color', [0.5, 0.5, 0.5, 1.0]))
        self.vb_rough.setValue(float(surf.get('roughness', 0.8)))
        self.vb_metallic.setValue(float(surf.get('metallic', 0.0)))
        self.vb_h_min.setValue(float(hrng[0]))
        self.vb_h_max.setValue(float(hrng[1]))
        self.vb_s_min.setValue(float(srng[0]))
        self.vb_s_max.setValue(float(srng[1]))
        # Spawn list
        self.vb_spawn_list.clear()
        for sp in b.get('spawns', []):
            self.vb_spawn_list.addItem(sp.get('kind', 'object:cube'))
        self.vb_spawn_panel.setVisible(False)
        self._updating = False
        self.v_biome_panel.setVisible(True)

    def _update_selected_vox_biome(self, key, val):
        if self._updating or not self._current_objects: return
        row = self.vox_biomes_list.currentRow()
        if row < 0: return

    def _update_vox_water_mat(self, key, val):
        """Update specialized water material properties."""
        if self._updating or not self._current_objects: return
        for obj in self._current_objects:
            if not hasattr(obj, 'material'): continue
            obj.material[key] = val
        # Trigger redraw (not full regen, since it's just colors)
        self.scene_view.update()
        for obj in self._current_objects:
            biomes = getattr(obj, 'voxel_biomes', [])
            if row >= len(biomes): continue
            b = biomes[row]
            if key in ('color', 'roughness', 'metallic', 'material'):
                b.setdefault('surface', {})[key] = val
            elif key == 'height_min':
                hr = b.setdefault('height_range', [0.0, 10.0]); hr[0] = val
            elif key == 'height_max':
                hr = b.setdefault('height_range', [0.0, 10.0]); hr[1] = val
            elif key == 'slope_min':
                sr = b.setdefault('slope_range', [0.0, 1.0]); sr[0] = val
            elif key == 'slope_max':
                sr = b.setdefault('slope_range', [0.0, 1.0]); sr[1] = val

        from PyQt6.QtCore import QTimer
        if self._regen_timer: self._regen_timer.stop()
        self._regen_timer = QTimer()
        self._regen_timer.setSingleShot(True)
        self._regen_timer.timeout.connect(self.property_changed.emit)
        self._regen_timer.start(150)

    def _on_vb_spawn_context(self, pos):
        if not self._current_objects: return
        brow = self.vox_biomes_list.currentRow()
        if brow < 0: return
        obj = self._current_objects[0]
        biomes = getattr(obj, 'voxel_biomes', [])
        if brow >= len(biomes): return
        menu = QMenu(self)
        menu.setStyleSheet("background:#252526; color:#ccc;")
        add = menu.addAction("Add Spawner")
        row = self.vb_spawn_list.currentRow()
        delete = menu.addAction("Remove") if row >= 0 else None
        action = menu.exec(self.vb_spawn_list.mapToGlobal(pos))
        if not action: return
        for o in self._current_objects:
            bio = getattr(o, 'voxel_biomes', [])
            if brow >= len(bio): continue
            spawns = bio[brow].setdefault('spawns', [])
            if action == add:
                spawns.append({
                    'kind': 'object:cube', 'prefab_path': '',
                    'density': 0.05,
                    'slope_min': 0.7, 'slope_max': 1.0,
                    'height_min': -1000.0, 'height_max': 1000.0,
                    'scale_min': 0.8, 'scale_max': 1.2,
                    'shader_name': 'Standard',
                    'jitter': 0.3, 'align_to_normal': False,
                })
            elif delete is not None and action == delete:
                if 0 <= row < len(spawns): spawns.pop(row)
        self.set_objects(self._current_objects)
        self.property_changed.emit()

    def _on_vb_spawn_selected(self, row):
        if row < 0 or not self._current_objects:
            self.vb_spawn_panel.setVisible(False); return
        brow = self.vox_biomes_list.currentRow()
        if brow < 0:
            self.vb_spawn_panel.setVisible(False); return
        obj = self._current_objects[0]
        biomes = getattr(obj, 'voxel_biomes', [])
        if brow >= len(biomes):
            self.vb_spawn_panel.setVisible(False); return
        spawns = biomes[brow].get('spawns', [])
        if row >= len(spawns):
            self.vb_spawn_panel.setVisible(False); return
        s = spawns[row]
        self._updating = True
        ki = self.vbs_kind.findText(s.get('kind', 'object:cube'))
        if ki >= 0: self.vbs_kind.setCurrentIndex(ki)
        self.vbs_prefab.setText(s.get('prefab_path', ''))
        self.vbs_density.setValue(float(s.get('density', 0.05)))
        self.vbs_max_dist.setValue(float(s.get('max_distance', 120.0)))
        self.vbs_slope_min.setValue(float(s.get('slope_min', 0.7)))
        self.vbs_slope_max.setValue(float(s.get('slope_max', 1.0)))
        self.vbs_h_min.setValue(float(s.get('height_min', -1000.0)))
        self.vbs_h_max.setValue(float(s.get('height_max', 1000.0)))
        self.vbs_scale_min.setValue(float(s.get('scale_min', 0.8)))
        self.vbs_scale_max.setValue(float(s.get('scale_max', 1.2)))
        self.vbs_jitter.setValue(float(s.get('jitter', 0.3)))
        si = self.vbs_shader.findText(s.get('shader_name', 'Standard'))
        if si >= 0: self.vbs_shader.setCurrentIndex(si)
        self.vbs_material.set_material(s.get('material_path', ''))
        self.vbs_align.setChecked(bool(s.get('align_to_normal', False)))
        self._refresh_vbs_params(s)
        self._updating = False
        self.vb_spawn_panel.setVisible(True)

    def _on_browse_vb_spawn_asset(self):
        from PyQt6.QtWidgets import QFileDialog
        from py_editor.core import paths as _ap
        path, _ = QFileDialog.getOpenFileName(
            self, "Pick Biome Spawn Asset", str(_ap.get_project_root()),
            "Spawnable Assets (*.prefab *.mesh *.fbx *.obj);;Prefab (*.prefab);;Mesh (*.mesh *.fbx *.obj)")
        if not path:
            return
        ext = Path(path).suffix.lower()
        # Auto-pick kind to match the file type so spawn rendering works.
        if ext == '.prefab':
            kind = 'prefab'
        elif ext in ('.mesh', '.fbx', '.obj'):
            kind = 'object:mesh'
        else:
            kind = self.vbs_kind.currentText()
        rel = _ap.to_relative(path)
        self.vbs_prefab.setText(rel)
        self._updating = True
        self.vbs_kind.setCurrentText(kind)
        self._updating = False
        self._update_selected_vb_spawn('kind', kind)
        self._update_selected_vb_spawn('prefab_path', rel)

    def _update_selected_vb_spawn(self, key, val):
        if self._updating or not self._current_objects: return
        brow = self.vox_biomes_list.currentRow()
        srow = self.vb_spawn_list.currentRow()
        if brow < 0 or srow < 0: return
        for obj in self._current_objects:
            biomes = getattr(obj, 'voxel_biomes', [])
            if brow >= len(biomes): continue
            spawns = biomes[brow].get('spawns', [])
            if srow >= len(spawns): continue
            spawns[srow][key] = val
        
        # UI Refresh for specific keys
        if key == 'material_path':
            self.vbs_material.set_material(val)
        elif key == 'prefab_path':
            self.vbs_prefab.setText(val)
        from PyQt6.QtCore import QTimer
        if self._regen_timer: self._regen_timer.stop()
        self._regen_timer = QTimer()
        self._regen_timer.setSingleShot(True)
        self._regen_timer.timeout.connect(self.property_changed.emit)
        self._regen_timer.start(150)
        
        if key == 'shader_name':
            # Refresh params if shader changed
            brow = self.vox_biomes_list.currentRow()
            srow = self.vb_spawn_list.currentRow()
            obj = self._current_objects[0]
            s = obj.voxel_biomes[brow]['spawns'][srow]
            self._refresh_vbs_params(s)

    def _refresh_vbs_params(self, spawn_dict):
        """Build dynamic UI for shader uniforms."""
        # Clear existing
        while self.vbs_param_layout.count():
            item = self.vbs_param_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()
            
        from py_editor.ui.shader_manager import get_shader_params
        shader_name = spawn_dict.get('shader_name', 'Standard')
        params = get_shader_params(shader_name)
        if not params: return
        
        spawn_dict.setdefault('shader_params', {})
        
        # Add Header
        lbl = QLabel("  SHADER PARAMETERS")
        lbl.setStyleSheet("background: #252526; color: #4fc3f7; font-size: 9px; font-weight: bold; min-height: 18px;")
        self.vbs_param_layout.addWidget(lbl)
        
        for p in params:
            name = p['name']
            p_type = p['type']
            
            # Use current value or default
            cur_val = spawn_dict['shader_params'].get(name, p['default'])
            spawn_dict['shader_params'][name] = cur_val # ensure it exists
            
            if p_type == 'float':
                # Map intensity, scale, freq to normalized or specific ranges
                min_v, max_v = 0.0, 1.0
                if 'speed' in name.lower() or 'frequency' in name.lower(): max_v = 10.0
                elif 'intensity' in name.lower() or 'amplitude' in name.lower(): max_v = 2.0
                elif 'scale' in name.lower(): max_v = 10.0
                
                slider = PropertySlider(float(cur_val), min_v, max_v)
                slider.valueChanged.connect(partial(self._update_vbs_shader_param, name))
                self._add_property_row(self.vbs_param_layout, name.replace('_', ' ').capitalize(), slider)
            elif p_type in ('vec3', 'vec4'):
                # Color picker if name looks like color
                if 'color' in name.lower() or 'tint' in name.lower():
                    picker = ColorPickerButton(cur_val)
                    picker.colorChanged.connect(partial(self._update_vbs_shader_param, name))
                    self._add_property_row(self.vbs_param_layout, name.replace('_', ' ').capitalize(), picker)
                else:
                    # Generic text or multi-slider (simplified to text for now)
                    line = QLineEdit(str(cur_val))
                    line.setStyleSheet(EDIT_SS)
                    line.editingFinished.connect(lambda n=name, l=line: 
                        self._update_vbs_shader_param(n, [float(x.strip()) for x in l.text().strip('[] ').split(',')]))
                    self._add_property_row(self.vbs_param_layout, name.replace('_', ' ').capitalize(), line)

    def _update_vbs_shader_param(self, key, val):
        if self._updating or not self._current_objects: return
        brow = self.vox_biomes_list.currentRow()
        srow = self.vb_spawn_list.currentRow()
        if brow < 0 or srow < 0: return
        for obj in self._current_objects:
            biomes = getattr(obj, 'voxel_biomes', [])
            if brow >= len(biomes): continue
            spawns = biomes[brow].get('spawns', [])
            if srow >= len(spawns): continue
            sp = spawns[srow]
            sp.setdefault('shader_params', {})[key] = val
            
        self.property_changed.emit()

    def _update_selected_vox_layer(self, key, val):
        if self._updating or not self._current_objects: return
        row = self.vox_layers_list.currentRow()
        if row < 0: return
        for obj in self._current_objects:
            n_feats = len(getattr(obj, 'voxel_features', []))
            if row < n_feats:
                continue  # Feature rows have no editable fields.
            lrow = row - n_feats
            if lrow < len(obj.voxel_layers):
                obj.voxel_layers[lrow][key] = val
        
        from PyQt6.QtCore import QTimer
        if self._regen_timer: self._regen_timer.stop()
        self._regen_timer = QTimer()
        self._regen_timer.setSingleShot(True)
        self._regen_timer.timeout.connect(self.property_changed.emit)
        self._regen_timer.start(150)

    def _on_vox_type_changed(self, t):
        self.update_obj_prop('voxel_type', t)
        # We now keep radius enabled as it controls proxy scale and LOD for both modes
        self.vox_radius.setEnabled(True)
        self.vox_infinite_flat.setVisible(str(t).lower() == 'flat')

    def _init_weather_ui(self, layout):
        self.weather_group = QGroupBox("Weather Simulator")
        self.weather_group.setStyleSheet(PROPS_SS)
        wg = QVBoxLayout(self.weather_group)
        wg.setContentsMargins(10, 14, 10, 10); wg.setSpacing(6)
        
        self.weather_type = QComboBox()
        self.weather_type.addItems(['Auto', 'Clear', 'Rain', 'Snow', 'Storm', 'Fog', 'Sandstorm'])
        self.weather_type.setStyleSheet(COMBO_SS)
        self.weather_type.currentIndexChanged.connect(lambda i: self.update_obj_prop('weather_type_override', self.weather_type.currentText()))
        self._add_property_row(wg, "Override", self.weather_type)
        
        self.weather_intensity = PropertySlider(0.8, 0.0, 1.0)
        self.weather_intensity.valueChanged.connect(lambda v: self.update_obj_prop('weather_intensity_override', v))
        self._add_property_row(wg, "Intensity", self.weather_intensity)
        
        self.weather_seed = QSpinBox()
        self.weather_seed.setRange(0, 9999); self.weather_seed.setValue(1234)
        self.weather_seed.setStyleSheet(SPIN_SS); self.weather_seed.setFixedWidth(80)
        self.weather_seed.valueChanged.connect(lambda v: self.update_obj_prop('weather_seed', v))
        self._add_property_row(wg, "Seed", self.weather_seed)
        
        layout.addWidget(self.weather_group)

