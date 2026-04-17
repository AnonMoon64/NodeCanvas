"""
properties_panel.py

The Right-side properties inspector with a unified layout.
"""
from pathlib import Path
from typing import Optional
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QComboBox, QCheckBox, QDoubleSpinBox, QFrame, QSpinBox,
    QToolButton, QGroupBox, QSlider, QColorDialog, QGridLayout, QListWidget, QListWidgetItem,
    QScrollArea
)
from PyQt6.QtGui import QDragEnterEvent, QDropEvent, QColor
from PyQt6.QtCore import Qt, pyqtSignal

from py_editor.ui.shared_styles import (
    PROPS_SS, SPIN_SS, COMBO_SS, BTN_SS, LIST_SS, LABEL_SS
)
from py_editor.ui.scene.object_system import SceneObject
from py_editor.ui.shader_manager import SHADER_REGISTRY

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
        layout.addWidget(self.btn)
        
    def set_texture(self, path):
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
        self.slider.setValue(s_val); self.valueChanged.emit(fval); self._updating = False

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
        # Mountain chains — ridged noise, taller and higher-frequency than before
        # so they read as mountains rather than dunes after Gaussian smoothing.
        "Mountains":    {"noise_type": "ridged",  "freq": 2.5,  "amp": 0.65, "blend": "add"},
        # Dramatic individual peaks for very mountainous worlds
        "Sharp Peaks":  {"noise_type": "ridged",  "freq": 4.0,  "amp": 0.45, "blend": "add"},
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
        "Grassland":     {"range": [2.0,     15.0], "color": [0.25, 0.4,  0.1,  1.0], "rough": 0.8},
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
        # Main layout contains a scroll area so the properties panel stays fixed size
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0,0,0,0)
        main_layout.setSpacing(0)

        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        main_layout.addWidget(self._scroll)

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
        self._init_material_ui(layout)
        self._init_pbr_ui(layout)
        self._init_mesh_ui(layout)
        
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

        # Universe Specifics (in the same group if it's a universe object)
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
        self._init_camera_ui(layout)
        self._init_shader_ui(layout)
        self._init_logic_ui(layout)
        
        layout.addStretch()

        layout.addStretch()
        
        # Ensure it starts empty
        self.set_objects([])

    def _init_material_ui(self, layout):
        self.mat_group = QGroupBox("Material")
        self.mat_group.setStyleSheet(PROPS_SS)
        mg = QVBoxLayout(self.mat_group)
        mg.setContentsMargins(10, 14, 10, 10); mg.setSpacing(6)
        
        self.mat_preset = QComboBox()
        self.mat_preset.addItems(['Plastic', 'Glass', 'Metal', 'Water', 'Custom'])
        self.mat_preset.setStyleSheet(COMBO_SS)
        self._add_property_row(mg, "Preset", self.mat_preset)
        
        self.mat_slot = MaterialSlotWidget()
        self._add_property_row(mg, "Asset", self.mat_slot)
        layout.addWidget(self.mat_group)

    def _init_mesh_ui(self, layout):
        self.mesh_group = QGroupBox("Mesh Data")
        self.mesh_group.setStyleSheet(PROPS_SS)
        mg = QVBoxLayout(self.mesh_group)
        mg.setContentsMargins(10, 14, 10, 10); mg.setSpacing(6)
        
        self.mesh_path_label = QLineEdit()
        self.mesh_path_label.setReadOnly(True)
        self.mesh_path_label.setStyleSheet("background: #1e1e1e; color: #4fc3f7; border: 1px solid #333; font-size: 10px;")
        self._add_property_row(mg, "Source", self.mesh_path_label)
        
        self.tex_slot = TextureSlotWidget()
        self.tex_slot.texture_dropped.connect(lambda p: self.update_obj_prop('texture_path', p))
        self._add_property_row(mg, "Texture", self.tex_slot)
        
        layout.addWidget(self.mesh_group)

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
        for obj in self._current_objects:
            if not hasattr(obj, 'pbr_maps') or obj.pbr_maps is None:
                obj.pbr_maps = {}
            obj.pbr_maps[m_type] = path
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
        from PyQt6.QtWidgets import QFileDialog
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
        self.property_changed.emit()

    def update_shader_param(self, key, val):
        if not self._current_objects: return
        for obj in self._current_objects:
            if not hasattr(obj, 'shader_params'): obj.shader_params = {}
            obj.shader_params[key] = val
        self.property_changed.emit()

    def set_objects(self, objs: list[SceneObject]):
        self._current_objects = objs
        if not objs:
            self._title.setText("  No Selection")
            for group in [self.pos_group, self.rot_group, self.scale_group, self.mat_group, self.env_group, self.land_group, self.ocean_group, self.logic_group, self.shader_group, self.mesh_group, self.vox_group, self.cont_group]:
                group.hide()
            return

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
        
        self.mat_group.setVisible(primary.obj_type in ('cube', 'sphere', 'plane', 'landscape', 'mesh'))
        # Show PBR group for mesh/cube objects always — dragging a map in auto-switches the shader
        self.pbr_group.setVisible(primary.obj_type in ('cube', 'sphere', 'plane', 'mesh'))
        self.env_group.setVisible(primary.obj_type in ('atmosphere', 'universe'))
        self.land_group.setVisible(primary.obj_type == 'landscape')
        self.ocean_group.setVisible(primary.obj_type == 'ocean')
        self.cam_group.setVisible(primary.obj_type == 'camera')
        self.mesh_group.setVisible(primary.obj_type == 'mesh')
        self.voxel_group.setVisible(primary.obj_type == 'voxel_world')
        self.controller_group.setVisible(primary.obj_type in ('cube', 'sphere', 'mesh', 'voxel_world'))
        
        if self.mat_group.isVisible():
            preset = primary.material.get('preset', 'Custom')
            idx = self.mat_preset.findText(preset)
            if idx != -1: self.mat_preset.setCurrentIndex(idx)
            
            idx_cont = self.controller_combo.findText(getattr(primary, 'controller_type', 'None'))
            if idx_cont != -1: self.controller_combo.setCurrentIndex(idx_cont)
            self.opacity_slider.setValue(getattr(primary, 'alpha', 1.0))
            
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
            self.mesh_path_label.setText(Path(primary.mesh_path).name if primary.mesh_path else "None")
            self.tex_slot.set_texture(primary.texture_path)
        
        # Shader Sync
        idx = self.shader_combo.findText(getattr(primary, 'shader_name', 'Standard'))
        if idx != -1: self.shader_combo.setCurrentIndex(idx)

        # ... (remaining sync logic uses 'primary' as reference)
        obj = primary
        if obj.obj_type == 'atmosphere' or obj.obj_type == 'universe':
            self.time_slider.setValue(getattr(obj, 'time_of_day', 0.25))
            self.sun_size.setValue(getattr(obj, 'sun_size', 1.0))
            self.sun_intensity.setValue(getattr(obj, 'sun_intensity', 10.0))
            is_universe = obj.obj_type == 'universe'
            self.star_density.setVisible(is_universe)
            self.neb_intensity.setVisible(is_universe)
            if is_universe:
                self.star_density.setValue(getattr(obj, 'star_density', 1.0))
                self.neb_intensity.setValue(getattr(obj, 'nebula_intensity', 0.5))
        elif obj.obj_type == 'landscape':
            self.land_seed.setValue(getattr(obj, 'landscape_seed', 123))
            self.land_h_scale.setValue(getattr(obj, 'landscape_height_scale', 30.0))
            self.land_res.setValue(getattr(obj, 'landscape_resolution', 32))
            self.land_ocean_lvl.setValue(getattr(obj, 'landscape_ocean_level', 0.0))
            idx = self.land_type.findText(getattr(obj, 'landscape_type', 'procedural').capitalize())
            if idx != -1: self.land_type.setCurrentIndex(idx)
        elif obj.obj_type == 'ocean':
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
        elif obj.obj_type == 'voxel_world':
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
            idx = self.vox_type.findText(getattr(obj, 'voxel_type', 'Round'))
            if idx != -1: self.vox_type.setCurrentIndex(idx)
            # Infinite-flat checkbox (sync state + hide for Round mode)
            self.vox_infinite_flat.blockSignals(True)
            self.vox_infinite_flat.setChecked(bool(getattr(obj, 'voxel_infinite_flat', True)))
            self.vox_infinite_flat.blockSignals(False)
            self.vox_infinite_flat.setVisible(
                str(getattr(obj, 'voxel_type', 'Round')).lower() == 'flat')
            rs_idx = self.vox_render_style.findText(getattr(obj, 'voxel_render_style', 'Smooth'))
            if rs_idx != -1: self.vox_render_style.setCurrentIndex(rs_idx)
            # Prefetch and max chunk resolution (per-object overrides)
            self.vox_prefetch.blockSignals(True)
            self.vox_prefetch.setValue(int(getattr(obj, 'voxel_prefetch_neighborhood', 1)))
            self.vox_prefetch.blockSignals(False)

            self.vox_max_chunk_res.blockSignals(True)
            self.vox_max_chunk_res.setValue(int(getattr(obj, 'voxel_max_single_chunk_res', 128)))
            self.vox_max_chunk_res.blockSignals(False)
            # Layers
            self.vox_layers_list.clear()
            for l in getattr(obj, 'voxel_layers', []):
                self.vox_layers_list.addItem(l.get('name', 'Layer'))
            self.v_layer_panel.setVisible(False)
            # Biomes
            self.vox_biomes_list.clear()
            for b in getattr(obj, 'voxel_biomes', []):
                self.vox_biomes_list.addItem(b.get('name', 'Biome'))
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
        self.land_group = QGroupBox("Landscape Settings")
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
        from py_editor.ui.scene.object_system import SceneObject
        root = data.get("root", {})
        obj = SceneObject.from_dict(root)
        obj.name = Path(path).stem
        
        self._updating = True
        self._current_prefab_path = path
        self.set_objects([obj])
        self.save_btn.setVisible(True)
        self._updating = False
        
    def _on_save_prefab(self):
        if not self._current_prefab_path or not self._current_objects: return
        obj = self._current_objects[0]
        data = {
            "type": "prefab",
            "root": obj.to_dict()
        }
        with open(self._current_prefab_path, 'w') as f:
            import json
            json.dump(data, f, indent=4)
        print(f"[PROPERTIES] Saved Prefab: {self._current_prefab_path}")

    def _on_tint_clicked(self):
        if not self._current_objects: return
        primary = self._current_objects[0]
        current = getattr(primary, 'ocean_reflection_tint', [0.5, 0.7, 1.0, 1.0])
        from PyQt6.QtWidgets import QColorDialog
        color = QColorDialog.getColor(QColor.fromRgbF(current[0], current[1], current[2]), self, "Reflection Tint")
        if color.isValid():
            for obj in self._current_objects:
                obj.ocean_reflection_tint = [color.redF(), color.greenF(), color.blueF(), 1.0]
            self.property_changed.emit()

    def _init_shader_ui(self, layout):
        self.shader_group = QGroupBox("Custom Shaders")
        self.shader_group.setStyleSheet(PROPS_SS)
        sg = QVBoxLayout(self.shader_group)
        
        self.shader_combo = QComboBox()
        self.shader_combo.addItems(list(SHADER_REGISTRY.keys()))
        self.shader_combo.setStyleSheet(COMBO_SS)
        self.shader_combo.currentTextChanged.connect(self._on_shader_name_changed)
        self._add_property_row(sg, "Shader", self.shader_combo)
        
        # Shader Parameter Sliders (Context Variable)
        self.shader_params_group = QFrame()
        self.sp_lay = QVBoxLayout(self.shader_params_group)
        self.sp_lay.setContentsMargins(0, 0, 0, 0)
        sg.addWidget(self.shader_params_group)
        
        layout.addWidget(self.shader_group)

    def _on_shader_name_changed(self, name):
        if self._updating: return
        self.update_obj_prop('shader_name', name)
        
        # Initialize defaults if params are missing for this shader
        for obj in self._current_objects:
            if not obj.shader_params or 'speed' not in obj.shader_params:
                if name == "Fish Swimming":
                    obj.shader_params.update({
                        "speed": 2.0, "freq": 1.5, "intensity": 1.0,
                        "yaw_amp": 0.2, "side_amp": 0.1, "roll_amp": 0.05, "flag_amp": 0.05,
                        "forward_axis": 0.0
                    })
                elif name == "Flag Waving":
                    obj.shader_params.update({"wave_speed": 3.0, "wave_amplitude": 0.1})
        
        # Refresh params UI based on first obj
        if self._current_objects:
            self._update_shader_params_ui(name, getattr(self._current_objects[0], 'shader_params', {}))

    def _update_shader_params_ui(self, shader_name, params):
        # Clear old
        while self.sp_lay.count():
            child = self.sp_lay.takeAt(0)
            if child.widget(): child.widget().deleteLater()
        
        if shader_name == "Fish Swimming":
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
        elif shader_name == "Flag Waving":
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
        row = QHBoxLayout()
        lbl = QLabel(label_text); lbl.setFixedWidth(90); lbl.setStyleSheet(LABEL_SS)
        row.addWidget(lbl); row.addWidget(widget)
        layout.addLayout(row)

    def _init_controller_ui(self, layout):
        self.cont_group = QGroupBox("Controller Settings")
        self.cont_group.setStyleSheet(PROPS_SS)
        self.controller_group = self.cont_group
        lg = QVBoxLayout(self.cont_group)
        
        self.controller_combo = QComboBox()
        self.controller_combo.addItems(["None", "Player", "AI (CPU)", "AI (GPU Fish)", "AI (GPU Bird)"])
        self.controller_combo.setStyleSheet(COMBO_SS)
        self.controller_combo.currentTextChanged.connect(lambda t: self.update_obj_prop('controller_type', t))
        self._add_property_row(lg, "Type", self.controller_combo)
        
        # Physics toggle
        self.physics_chk = QCheckBox("Physics Enabled")
        self.physics_chk.setChecked(True)
        self.physics_chk.toggled.connect(lambda c: self.update_obj_prop('physics_enabled', bool(c)))
        self._add_property_row(lg, "Physics", self.physics_chk)

        # Mass for simple collision resolution
        from PyQt6.QtWidgets import QDoubleSpinBox
        self.mass_spin = QDoubleSpinBox()
        self.mass_spin.setRange(0.01, 10000.0); self.mass_spin.setDecimals(2)
        self.mass_spin.setValue(1.0); self.mass_spin.setStyleSheet(SPIN_SS)
        self.mass_spin.valueChanged.connect(lambda v: self.update_obj_prop('mass', float(v)))
        self._add_property_row(lg, "Mass", self.mass_spin)

        # Simple Collision Properties list (add/remove)
        from PyQt6.QtWidgets import QListWidget, QPushButton, QHBoxLayout
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
        from PyQt6.QtWidgets import QFileDialog, QInputDialog

        self.vox_group = QGroupBox("Voxel World Settings")
        self.vox_group.setStyleSheet(PROPS_SS)
        self.voxel_group = self.vox_group
        vg = QVBoxLayout(self.vox_group)

        # Mode
        self.vox_type = QComboBox()
        self.vox_type.addItems(["Round", "Flat"])
        self.vox_type.setStyleSheet(COMBO_SS)
        self.vox_type.currentTextChanged.connect(self._on_vox_type_changed)
        self._add_property_row(vg, "Mode", self.vox_type)

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
        self.vox_render_style.addItems(["Smooth", "Minecraft"])
        self.vox_render_style.setStyleSheet(COMBO_SS)
        self.vox_render_style.setToolTip(
            "Smooth = No Man's Sky style (interpolated verts + smoothing)\n"
            "Minecraft = Classic block look (no smoothing, no interpolation)")
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
            ("Planet (2000 u)", 2000.0),
        ]
        self.vox_radius = QComboBox()
        for name, _ in self.vox_radius_presets_list:
            self.vox_radius.addItem(name)
        self.vox_radius.setToolTip("Select a world size preset. Large sizes may be heavy — they use chunked LOD generation.")
        self.vox_radius.currentIndexChanged.connect(self._on_vox_radius_changed)
        self._last_vox_radius_index = 1  # Default = Small Planet
        self._add_property_row(vg, "Radius", self.vox_radius)

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
            "Minimum enforced by style: Smooth ≥ 0.5 u/voxel, Minecraft ≥ 1.0 u/voxel.\n"
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

        # Prefetch neighborhood for chunked LOD (per-object override)
        self.vox_prefetch = QSpinBox()
        self.vox_prefetch.setRange(0, 5)
        self.vox_prefetch.setStyleSheet(SPIN_SS)
        self.vox_prefetch.setToolTip("Number of neighboring chunks to prefetch around the camera.")
        self.vox_prefetch.valueChanged.connect(lambda v: self.update_obj_prop('voxel_prefetch_neighborhood', int(v)))
        self._add_property_row(vg, "Prefetch", self.vox_prefetch)

        # Max single-chunk resolution threshold
        self.vox_max_chunk_res = QSpinBox()
        self.vox_max_chunk_res.setRange(16, 512)
        self.vox_max_chunk_res.setStyleSheet(SPIN_SS)
        self.vox_max_chunk_res.setToolTip("Max resolution to keep as a single generation pass before chunking.")
        self.vox_max_chunk_res.valueChanged.connect(lambda v: self.update_obj_prop('voxel_max_single_chunk_res', int(v)))
        self._add_property_row(vg, "MaxChunkRes", self.vox_max_chunk_res)

        # ---- FEATURE LAYERS (context-menu driven) ----
        vg.addSpacing(8)
        lbl = QLabel("FEATURE LAYERS  (right-click to add / presets)")
        lbl.setStyleSheet("color: #4fc3f7; font-size: 10px; font-weight: bold;")
        vg.addWidget(lbl)

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

        # Seed
        self.vl_seed = QSpinBox()
        self.vl_seed.setRange(0, 999999)
        self.vl_seed.setStyleSheet(SPIN_SS)
        self.vl_seed.valueChanged.connect(lambda v: self._update_selected_vox_layer('seed', v))
        self._add_property_row(vlg, "Seed", self.vl_seed)
        vg.addWidget(self.v_layer_panel)

        # ---- BIOMES (context-menu driven) ----
        vg.addSpacing(8)
        bio_lbl = QLabel("BIOMES  (right-click to add / presets)")
        bio_lbl.setStyleSheet("color: #4fc3f7; font-size: 10px; font-weight: bold;")
        vg.addWidget(bio_lbl)

        self.vox_biomes_list = QListWidget()
        self.vox_biomes_list.setStyleSheet(
            "background: #1e1e1e; border: 1px solid #333; color: #aaa; font-size: 10px;")
        self.vox_biomes_list.setFixedHeight(80)
        self.vox_biomes_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.vox_biomes_list.customContextMenuRequested.connect(self._on_vox_biome_context)
        vg.addWidget(self.vox_biomes_list)

        layout.addWidget(self.vox_group)


    def _on_vox_biome_context(self, pos):
        if not self._current_objects: return
        from PyQt6.QtWidgets import QMenu
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
                    "surface": {"color": p['color'], "roughness": p['rough'], "metallic": 0.0}
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
        from PyQt6.QtWidgets import QMenu
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
            for obj in self._current_objects:
                if not hasattr(obj, 'voxel_layers'): obj.voxel_layers = []
                obj.voxel_layers.append({
                    "name": p_name,
                    "noise_type": p.get('noise_type', 'perlin'),
                    "freq": p['freq'], "amp": p['amp'], "blend": p.get('blend', 'add'),
                    "seed": 123 + len(obj.voxel_layers)
                })
        elif action == del_a:
            for obj in self._current_objects:
                if hasattr(obj, 'voxel_layers') and row < len(obj.voxel_layers):
                    obj.voxel_layers.pop(row)
        elif action == ren_a:
            from PyQt6.QtWidgets import QInputDialog
            obj = self._current_objects[0]
            layers = getattr(obj, 'voxel_layers', [])
            cur = layers[row]['name'] if row < len(layers) else ''
            name, ok = QInputDialog.getText(self, "Rename Layer", "Name:", text=cur)
            if ok and name:
                for o in self._current_objects:
                    lay = getattr(o, 'voxel_layers', [])
                    if row < len(lay): lay[row]['name'] = name
                    
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
            return
        obj = self._current_objects[0]
        layers = getattr(obj, 'voxel_layers', [])
        if row >= len(layers):
            self.v_layer_panel.setVisible(False)
            return
        self.v_layer_panel.setVisible(True)
        l = layers[row]
        self._updating = True
        nt_idx = self.vl_noise_type.findText(l.get('noise_type', 'perlin'))
        if nt_idx >= 0: self.vl_noise_type.setCurrentIndex(nt_idx)
        bl_idx = self.vl_blend.findText(l.get('blend', 'add'))
        if bl_idx >= 0: self.vl_blend.setCurrentIndex(bl_idx)
        self.vl_freq.setValue(l.get('freq', 1.0))
        self.vl_amp.setValue(l.get('amp', 0.1))
        self.vl_seed.setValue(int(l.get('seed', 123)))
        self._updating = False

    def _update_selected_vox_layer(self, key, val):
        if self._updating or not self._current_objects: return
        row = self.vox_layers_list.currentRow()
        if row < 0: return
        for obj in self._current_objects:
            if row < len(obj.voxel_layers):
                obj.voxel_layers[row][key] = val
        self.property_changed.emit()

    def _on_vox_type_changed(self, t):
        self.update_obj_prop('voxel_type', t)
        # We now keep radius enabled as it controls proxy scale and LOD for both modes
        self.vox_radius.setEnabled(True)
        self.vox_infinite_flat.setVisible(str(t).lower() == 'flat')

    def _init_mesh_ui(self, layout):
        self.mesh_group = QGroupBox("Mesh & Material")
        self.mesh_group.setStyleSheet(PROPS_SS)
        mg = QVBoxLayout(self.mesh_group)
        
        self.opacity_slider = PropertySlider(1.0, 0.0, 1.0)
        self.opacity_slider.valueChanged.connect(lambda v: self.update_obj_prop('alpha', v))
        self._add_property_row(mg, "Opacity", self.opacity_slider)
        
        self.mesh_path_label = QLabel("None")
        self.mesh_path_label.setStyleSheet("color: #aaa; font-size: 11px;")
        self._add_property_row(mg, "Source", self.mesh_path_label)
        
        self.tex_slot = TextureSlotWidget()
        self.tex_slot.texture_dropped.connect(self._on_texture_dropped)
        self._add_property_row(mg, "Texture", self.tex_slot)
        
        layout.addWidget(self.mesh_group)

    def _on_texture_dropped(self, path):
        if not self._current_objects: return
        for obj in self._current_objects:
            obj.texture_path = path
        self.tex_slot.set_texture(path)
        self.property_changed.emit()
