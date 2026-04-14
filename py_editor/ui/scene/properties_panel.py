"""
properties_panel.py

The Right-side properties inspector with a unified layout.
"""
from pathlib import Path
from typing import Optional
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QComboBox, QCheckBox, QDoubleSpinBox, QFrame, QSpinBox,
    QToolButton, QGroupBox, QSlider, QColorDialog, QGridLayout, QListWidget
)
from PyQt6.QtGui import QDragEnterEvent, QDropEvent, QColor
from PyQt6.QtCore import Qt, pyqtSignal

from py_editor.ui.shared_styles import (
    PROPS_SS, SPIN_SS, COMBO_SS, BTN_SS, LIST_SS, LABEL_SS
)
from py_editor.ui.scene.object_system import SceneObject

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

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: #252526;")
        self._current_object = None
        self._updating = False  
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4,4,4,4); layout.setSpacing(4)
        
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
        
        # Initialize Sub-UIs correctly within __init__
        self._init_material_ui(layout)
        
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
        
        self._init_landscape_ui(layout)
        self._init_ocean_ui(layout)
        self._init_camera_ui(layout)

        layout.addStretch()
        
        # Ensure it starts empty
        self.set_object(None)

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

    def _on_pos_changed(self):
        if self._updating or not self._current_object: return
        for i in range(3): self._current_object.position[i] = self._pos_spins[i].value()
        self.property_changed.emit()

    def _on_rot_changed(self):
        if self._updating or not self._current_object: return
        for i in range(3): self._current_object.rotation[i] = self._rot_spins[i].value()
        self.property_changed.emit()

    def _on_scale_changed(self):
        if self._updating or not self._current_object: return
        for i in range(3): self._current_object.scale[i] = self._scale_spins[i].value()
        self.property_changed.emit()

    def update_obj_prop(self, prop, val):
        if not self._current_object: return
        setattr(self._current_object, prop, val)
        self.property_changed.emit()

    def set_object(self, obj: Optional[SceneObject]):
        self._current_object = obj
        if not obj:
            self._title.setText("  No Selection")
            self.pos_group.hide()
            self.rot_group.hide()
            self.scale_group.hide()
            self.mat_group.hide()
            self.env_group.hide()
            self.land_group.hide()
            self.ocean_group.hide()
            self.logic_group.hide()
            return

        self._title.setText(f"  {obj.name}  ({obj.obj_type})")
        self._updating = True
        
        # Show standard groups based on object type
        self.pos_group.show()
        self.logic_group.show()
        
        # Infinite objects like Ocean/Atmosphere don't need scale/rotation
        is_infinite = obj.obj_type in ('ocean', 'atmosphere', 'universe')
        self.rot_group.setVisible(not is_infinite)
        self.scale_group.setVisible(not is_infinite)
        
        for i in range(3):
            self._pos_spins[i].setValue(obj.position[i])
            self._rot_spins[i].setValue(obj.rotation[i])
            self._scale_spins[i].setValue(obj.scale[i])
        
        # Visibility logic
        self.mat_group.setVisible(obj.obj_type in ('cube', 'sphere', 'plane', 'landscape'))
        self.env_group.setVisible(obj.obj_type in ('atmosphere', 'universe'))
        self.land_group.setVisible(obj.obj_type == 'landscape')
        self.ocean_group.setVisible(obj.obj_type == 'ocean')
        self.cam_group.setVisible(obj.obj_type == 'camera')
        
        # Sync Material Preset
        if self.mat_group.isVisible():
            preset = obj.material.get('preset', 'Custom')
            idx = self.mat_preset.findText(preset)
            if idx != -1: self.mat_preset.setCurrentIndex(idx)
        
        if obj.obj_type == 'atmosphere' or obj.obj_type == 'universe':
            self.time_slider.setValue(getattr(obj, 'time_of_day', 0.25))
            self.sun_size.setValue(getattr(obj, 'sun_size', 1.0))
            self.sun_intensity.setValue(getattr(obj, 'sun_intensity', 10.0))
            
            # Show/Hide star specifics
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
            
            # Advanced Visuals
            self.ocean_fresnel.setValue(getattr(obj, 'ocean_fresnel_strength', 0.3))
            self.ocean_specular.setValue(getattr(obj, 'ocean_specular_intensity', 1.0))
        elif obj.obj_type == 'camera':
            self.cam_speed.setValue(getattr(obj, 'camera_speed', 10.0))
            self.cam_sens.setValue(getattr(obj, 'camera_sensitivity', 0.15))
            
        # Update logic path
        self.logic_val.setText(Path(obj.logic_path).name if obj.logic_path else "None")
            
        self._updating = False

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

        og.addSpacing(10)
        lbl = QLabel("ADVANCED VISUALS")
        lbl.setStyleSheet("color: #4fc3f7; font-size: 10px; font-weight: bold; margin-top: 5px;")
        og.addWidget(lbl)
        
        self.ocean_fresnel = PropertySlider(0.3, 0.0, 1.0)
        self.ocean_fresnel.valueChanged.connect(lambda v: self.update_obj_prop('ocean_fresnel_strength', v))
        self._add_property_row(og, "Fresnel", self.ocean_fresnel)
        
        self.ocean_specular = PropertySlider(1.0, 0.0, 5.0)
        self.ocean_specular.valueChanged.connect(lambda v: self.update_obj_prop('ocean_specular_intensity', v))
        self._add_property_row(og, "Specular", self.ocean_specular)
        
        tint_btn = QPushButton("Select Tint")
        tint_btn.setStyleSheet(BTN_SS)
        tint_btn.clicked.connect(self._on_tint_clicked)
        self._add_property_row(og, "Reflection Tint", tint_btn)

        layout.addWidget(self.ocean_group)
        
        # --- Logic Assignment Section ---
        self.logic_group = QGroupBox("General Logic")
        self.logic_group.setStyleSheet(PROPS_SS)
        lg = QVBoxLayout(self.logic_group)
        
        row = QHBoxLayout()
        self.logic_val = QLabel("None")
        self.logic_val.setStyleSheet("color: #aaa; font-size: 11px;")
        row.addWidget(self.logic_val); row.addStretch()
        
        assign_btn = QPushButton("...")
        assign_btn.setFixedSize(24, 20)
        assign_btn.setStyleSheet(BTN_SS)
        assign_btn.clicked.connect(self._on_assign_logic)
        row.addWidget(assign_btn)
        lg.addLayout(row)
        
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

    def _on_assign_logic(self):
        if not self._current_object: return
        from PyQt6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(self, "Select Logic File", str(Path.cwd()), "Logic (*.logic)")
        if path:
            self._current_object.logic_path = path
            self.set_object(self._current_object) # Refresh
            self.property_changed.emit()

    def _on_tint_clicked(self):
        if not self._current_object: return
        current = getattr(self._current_object, 'ocean_reflection_tint', [0.5, 0.7, 1.0, 1.0])
        from PyQt6.QtWidgets import QColorDialog
        color = QColorDialog.getColor(QColor.fromRgbF(current[0], current[1], current[2]), self, "Reflection Tint")
        if color.isValid():
            self._current_object.ocean_reflection_tint = [color.redF(), color.greenF(), color.blueF(), 1.0]
            self.property_changed.emit()

    def _add_property_row(self, layout, label_text, widget):
        row = QHBoxLayout()
        lbl = QLabel(label_text); lbl.setFixedWidth(90); lbl.setStyleSheet(LABEL_SS)
        row.addWidget(lbl); row.addWidget(widget)
        layout.addLayout(row)
