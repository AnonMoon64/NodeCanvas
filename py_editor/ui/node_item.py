from PyQt6.QtWidgets import (
    QGraphicsView,
    QGraphicsScene,
    QGraphicsItem,
    QGraphicsRectItem,
    QGraphicsEllipseItem,
    QGraphicsPathItem,
    QGraphicsTextItem,
    QGraphicsProxyWidget,
    QGraphicsPolygonItem,
    QMenu,
    QMessageBox,
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QLineEdit,
    QInputDialog,
    QWidgetAction,
    QComboBox,
    QGraphicsDropShadowEffect,
    QApplication,
    QWidget,
)
from PyQt6.QtGui import QPainterPath, QPen, QBrush, QColor, QPainter, QFont, QAction, QLinearGradient, QPolygonF, QKeyEvent
from PyQt6.QtCore import Qt, QPointF, QRectF, QTimer, pyqtSignal, QObject
import traceback
import importlib

# Debug: when True, run deferred removals immediately to surface exceptions
# Set to True to force synchronous removal (useful for debugging crashes).
DEBUG_FORCE_IMMEDIATE_REMOVAL = False

try:
    from py_editor.ui.node_editor import NodeEditorDialog
    from py_editor.core.node_templates import (
        list_templates,
        get_template,
        save_template,
        load_templates,
        get_all_templates,
    )
except Exception:
    try:
        from .node_editor import NodeEditorDialog
        from ..core.node_templates import (
            list_templates,
            get_template,
            save_template,
            load_templates,
            get_all_templates,
        )
    except Exception:
        import sys
        from pathlib import Path
        parent_dir = Path(__file__).resolve().parent.parent
        if str(parent_dir) not in sys.path:
            sys.path.insert(0, str(parent_dir))
        from ui.node_editor import NodeEditorDialog
        from core.node_templates import (
            list_templates,
            get_template,
            save_template,
            load_templates,
            get_all_templates,
        )



class NodeItem(QGraphicsRectItem):
    # NOTE (debug history):
    # During a recent change I introduced a QGraphicsDropShadowEffect on nodes
    # to make them look nicer. That exposed a native Qt lifetime/race where
    # removing nodes via the context-menu (while the menu/event stack was
    # active) could cause an access violation inside Qt's C++ code. The root
    # cause was the graphics effect being referenced by Qt while its Python
    # wrapper could be finalized — leading to a use-after-free.
    #
    # Fix applied: I reverted to simple node visuals (no QGraphicsEffect).
    # Removing the effect restored stability immediately. I left the
    # defensive removal instrumentation (deferred cleanup and mark-for-removal)
    # in place to avoid timing races. Debug logging was kept for verification.
    # If you want to reintroduce prettier shadows, do it by painting shadows
    # inside the item's paint() method rather than using QGraphicsEffect.

    def __init__(self, id_, title="Node", canvas=None):
        super().__init__(-120, -48, 240, 96)
        self.id = id_
        self.setPen(QPen(Qt.PenStyle.NoPen))
        self.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        self.is_compact = False
        self.header_color = QColor(40, 45, 55)
        self.node_width = 240
        self.node_height = 96
            # Revert to simple styling (no QGraphicsEffect) for stability.
            # Drop shadows previously caused native crashes in some Qt builds
            # when items were removed while the effect was still referenced.
            # Keep visuals simple: a gradient fill and a pen.
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(
            QGraphicsItem.GraphicsItemFlag.ItemSendsScenePositionChanges,
            True,
        )
        self.title = QGraphicsTextItem(title, self)
        self.title.setDefaultTextColor(QColor(255, 255, 255))
        title_font = QFont("Segoe UI Semibold", 10)
        self.title.setFont(title_font)
        # Position centered above node
        title_rect = self.title.boundingRect()
        self.title.setPos(-title_rect.width()/2, -self.node_height/2 - title_rect.height() - 4)
        self.input_pins = {}
        self.output_pins = {}
        self.pin_labels = []
        self.value_widgets = {}  # Map input pin name -> proxy widget for value entry
        self.pin_values = {}  # Store values for pins without connections
        self.process = None
        self.inputs = {}
        self.outputs = {}
        self.composite_graph = None
        self.category = "General"
        self.canvas = canvas
        self.has_error = False
        self.error_message = None
        self.error_badge = None  # Error indicator badge
        
        # Execution state for debugging
        self.execution_state = "idle"  # idle, executing, completed, breakpoint
        self.computed_value = None  # Last computed value
        self.has_breakpoint = False  # Whether this node has a breakpoint
        self.breakpoint_badge = None  # Red dot for breakpoint indicator
        
        self.setCacheMode(QGraphicsItem.CacheMode.DeviceCoordinateCache)
        
        self.setup_pins({"in0": {}}, {"out0": {}})

    def set_error(self, error_message: str):
        """Set error state for this node"""
        self.has_error = True
        self.error_message = error_message
        # Change border color to red
        self.setPen(QPen(QColor(220, 50, 50), 3))
        # Add error badge if not already present
        if not self.error_badge:
            self.error_badge = QGraphicsEllipseItem(100, -40, 20, 20, self)
            self.error_badge.setBrush(QBrush(QColor(220, 50, 50)))
            self.error_badge.setPen(QPen(QColor(255, 255, 255), 2))
            # Add "!" text
            error_text = QGraphicsTextItem("!", self.error_badge)
            error_text.setDefaultTextColor(QColor(255, 255, 255))
            error_text.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
            error_text.setPos(6, 0)
            self.error_badge.setToolTip(error_message)
        self.update()
    
    def clear_error(self):
        """Clear error state for this node"""
        self.has_error = False
        self.error_message = None
        # Restore normal border color based on execution state
        self._update_border_color()
        # Remove error badge
        if self.error_badge:
            self.error_badge.setParentItem(None)
            if self.error_badge.scene():
                self.error_badge.scene().removeItem(self.error_badge)
            self.error_badge = None
        self.update()
    
    def set_execution_state(self, state: str, value=None):
        """Set execution state: 'idle', 'executing', 'completed', 'breakpoint'"""
        self.execution_state = state
        self.computed_value = value
        self._update_border_color()
        
        # Update tooltip to show computed value
        if value is not None and state in ('completed', 'breakpoint'):
            value_str = str(value)
            if len(value_str) > 100:
                value_str = value_str[:100] + "..."
            self.setToolTip(f"Computed Value: {value_str}")
        elif state == 'idle':
            self.setToolTip("")
        
        self.update()
    
    def _update_border_color(self):
        """Update border color based on current state"""
        if self.has_error:
            self.setPen(QPen(QColor(220, 50, 50), 3))  # Red for errors
        elif self.execution_state == "executing":
            self.setPen(QPen(QColor(255, 200, 50), 3))  # Yellow/orange for currently executing
        elif self.execution_state == "completed":
            self.setPen(QPen(QColor(50, 220, 120), 3))  # Green for completed
        elif self.execution_state == "breakpoint":
            self.setPen(QPen(QColor(220, 100, 50), 3))  # Orange for breakpoint hit
        else:
            self.setPen(QPen(QColor(80, 120, 190), 2))  # Normal blue
    
    def toggle_breakpoint(self):
        """Toggle breakpoint on this node"""
        self.has_breakpoint = not self.has_breakpoint
        
        if self.has_breakpoint:
            # Add red dot indicator
            if not self.breakpoint_badge:
                self.breakpoint_badge = QGraphicsEllipseItem(-125, -45, 12, 12, self)
                self.breakpoint_badge.setBrush(QBrush(QColor(220, 50, 50)))
                self.breakpoint_badge.setPen(QPen(QColor(150, 30, 30), 1))
                self.breakpoint_badge.setToolTip("Breakpoint: Execution will pause here")
        else:
            # Remove breakpoint indicator
            if self.breakpoint_badge:
                self.breakpoint_badge.setParentItem(None)
                if self.breakpoint_badge.scene():
                    self.breakpoint_badge.scene().removeItem(self.breakpoint_badge)
                self.breakpoint_badge = None
        
        self.update()
        return self.has_breakpoint
    
    def clear_execution_state(self):
        """Clear execution state back to idle"""
        self.execution_state = "idle"
        self.computed_value = None
        self._update_border_color()
        self.update()

    def boundingRect(self):
        """Expand bounding rect to include pins protruding from the sides and floating title above."""
        rect = super().boundingRect()
        # Pins extend 12px out; add a bit of padding (16px) to be safe.
        # Title floats ~20px above; add 30px to top margin.
        return rect.adjusted(-16, -32, 16, 2)

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect()

        # 1. Shadow
        painter.setPen(QPen(Qt.PenStyle.NoPen))
        shadow_rect = rect.translated(2, 4)
        painter.setBrush(QColor(0, 0, 0, 80))
        painter.drawRoundedRect(shadow_rect, 6, 6)

        # 2. Main Body Gradient
        grad = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        grad.setColorAt(0, QColor(28, 33, 43, 230))
        grad.setColorAt(1, QColor(20, 24, 32, 230))
        painter.setBrush(QBrush(grad))
        
        # 3. Border Color
        if self.isSelected():
            painter.setPen(QPen(QColor(255, 200, 50, 240), 2))
        elif self.has_error:
            painter.setPen(QPen(QColor(220, 50, 50), 2))
        elif self.execution_state == "executing":
            painter.setPen(QPen(QColor(255, 200, 50), 2))
        elif self.execution_state == "completed":
            painter.setPen(QPen(QColor(50, 220, 120), 2))
        else:
            painter.setPen(QPen(QColor(45, 55, 65, 255), 1))
            
        painter.drawRoundedRect(rect, 6, 6)
        
        # 4. Floating Header removal: 
        # User requested names float above node instead of in it.
        # We no longer draw the header bar path here.
    
    def mouseDoubleClickEvent(self, event):
        """Enable renaming on double-click."""
        if event.button() == Qt.MouseButton.LeftButton:
            # Check if we clicked the title
            if self.title.contains(self.title.mapFromItem(self, event.pos())):
                self.rename_node()
        super().mouseDoubleClickEvent(event)

    def rename_node(self):
        new_title, ok = QInputDialog.getText(None, "Rename Node", "New Title:", text=self.title.toPlainText())
        if ok and new_title:
            self.title.setPlainText(new_title)
            self.title.setPos(-self.title.boundingRect().width()/2, -self.node_height/2 - self.title.boundingRect().height() - 4)
            if hasattr(self.canvas, 'graph_changed'):
                self.canvas.graph_changed.emit()


    def _clear_pin_items(self):
        for pin in list(self.input_pins.values()) + list(self.output_pins.values()):
            pin.setParentItem(None)
            if pin.scene():
                pin.scene().removeItem(pin)
        for label in list(self.pin_labels):
            label.setParentItem(None)
            if label.scene():
                label.scene().removeItem(label)
        # Clean up value widgets
        for proxy in list(self.value_widgets.values()):
            if proxy.scene():
                proxy.scene().removeItem(proxy)
        self.input_pins.clear()
        self.output_pins.clear()
        self.pin_labels.clear()
        self.value_widgets.clear()
    
    def setup_pins(self, inputs, outputs):
        self._clear_pin_items()
        self.inputs = inputs or {}
        self.outputs = outputs or {}
        input_defs = list(self.inputs.keys())
        output_defs = list(self.outputs.keys())
    
        has_exec = False
        for p_dict in [self.inputs, self.outputs]:
            for p_name, p_val in p_dict.items():
                p_type = p_val if isinstance(p_val, str) else p_val.get('type')
                if p_type == 'exec':
                    has_exec = True
    
        self.is_compact = not has_exec
        self.node_width = 180 if self.is_compact else 240
        spacing = 20 if self.is_compact else 24
        header_height = 0 if self.is_compact else 26
        
        max_pins = max(len(input_defs), len(output_defs))
        self.node_height = max(32 if self.is_compact else 64, header_height + (max_pins * spacing) + 16)
        self.setRect(-self.node_width/2, -self.node_height/2, self.node_width, self.node_height)
    
        # Update title position and style (Now floating above)
        if self.is_compact:
            self.title.setFont(QFont("Segoe UI Semibold", 8))
            self.title.setDefaultTextColor(QColor(180, 180, 180))
        else:
            self.title.setFont(QFont("Segoe UI Semibold", 10))
            self.title.setDefaultTextColor(QColor(255, 255, 255))
        
        # Recenter title above node
        title_rect = self.title.boundingRect()
        self.title.setPos(-title_rect.width()/2, -self.node_height/2 - title_rect.height() - 4)
    
        y_offset = -self.node_height/2 + header_height + 14
    
        for idx, name in enumerate(input_defs):
            y = y_offset + idx * spacing
            
            # Get pin type
            pin_type = None
            if isinstance(self.inputs[name], str):
                pin_type = self.inputs[name]
            elif isinstance(self.inputs[name], dict):
                pin_type = self.inputs[name].get('type', 'any')
            
            # Create pin shape based on type
            if pin_type == 'exec':
                # Exec pins are triangles (arrow shape) - white
                pin = QGraphicsPolygonItem(self)
                triangle = QPolygonF([
                    QPointF(-self.node_width/2 - 12, y - 6),
                    QPointF(-self.node_width/2, y),
                    QPointF(-self.node_width/2 - 12, y + 6)
                ])
                pin.setPolygon(triangle)
                pin.setBrush(QBrush(QColor(255, 255, 255)))
                pin.setPen(QPen(QColor(200, 200, 200), 1))
            else:
                # Data pins are circles
                pin = QGraphicsEllipseItem(-self.node_width/2 - 12, y - 6, 12, 12, self)
                pin.setBrush(QBrush(QColor(180, 180, 180)))
            
            pin.setData(0, ("in", name))
            self.input_pins[name] = pin
            label = QGraphicsTextItem(name, self)
            label.setDefaultTextColor(QColor(200, 200, 200))
            label.setFont(QFont("Segoe UI", 9))
            label.setPos(-self.node_width/2 + 10, y - 8)
            self.pin_labels.append(label)
            
            # For composite input/output nodes, add type selector
            tname = getattr(self, 'template_name', None)
            if tname in ('__composite_input__', '__composite_output__') and tname == '__composite_output__':
                self._add_type_selector_widget(name, pin_type or 'any', y)
            # For all other nodes (including composite nodes), create widgets for typed inputs
            # But NOT for exec pins
            if pin_type and pin_type in ('int', 'float', 'string', 'bool'):
                self._create_value_widget(name, pin_type, y)
    
        for idx, name in enumerate(output_defs):
            y = y_offset + idx * spacing
            
            # Get pin type
            pin_type = None
            if isinstance(self.outputs[name], str):
                pin_type = self.outputs[name]
            elif isinstance(self.outputs[name], dict):
                pin_type = self.outputs[name].get('type', 'any')
            
            # Create pin shape based on type
            if pin_type == 'exec':
                # Exec pins are triangles (arrow shape) - white
                pin = QGraphicsPolygonItem(self)
                triangle = QPolygonF([
                    QPointF(self.node_width/2, y - 6),
                    QPointF(self.node_width/2 + 12, y),
                    QPointF(self.node_width/2, y + 6)
                ])
                pin.setPolygon(triangle)
                pin.setBrush(QBrush(QColor(255, 255, 255)))
                pin.setPen(QPen(QColor(200, 200, 200), 1))
            else:
                # Data pins are circles
                pin = QGraphicsEllipseItem(self.node_width/2, y - 6, 12, 12, self)
                pin.setBrush(QBrush(QColor(150, 200, 255)))
            
            pin.setData(0, ("out", name))
            self.output_pins[name] = pin
            label = QGraphicsTextItem(name, self)
            label.setDefaultTextColor(QColor(200, 200, 200))
            label.setFont(QFont("Segoe UI", 9))
            # Calculate width to right-align
            label_rect = label.boundingRect()
            label.setPos(self.node_width/2 - label_rect.width() - 10, y - 8)
            self.pin_labels.append(label)
    
    def _create_value_widget(self, pin_name, pin_type, y_pos):
        """Create a value input widget for an input pin based on its type."""
        widget = None
        if pin_type == 'bool':
            widget = QComboBox()
            widget.addItems(['False', 'True'])
            widget.setCurrentIndex(0)
            widget.setFixedWidth(60)
            widget.currentTextChanged.connect(lambda v: self._on_value_changed(pin_name, v == 'True'))
            if hasattr(self, 'canvas') and self.canvas:
                widget.currentTextChanged.connect(lambda: self.canvas.value_changed.emit())
            self.pin_values[pin_name] = False
        elif pin_type in ('int', 'float'):
            widget = QLineEdit()
            widget.setText('0' if pin_type == 'int' else '0.0')
            widget.setFixedWidth(50)
            widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
            widget.textChanged.connect(lambda v: self._on_value_changed(pin_name, v))
            if hasattr(self, 'canvas') and self.canvas:
                widget.textChanged.connect(lambda: self.canvas.value_changed.emit())
            self.pin_values[pin_name] = 0 if pin_type == 'int' else 0.0
        elif pin_type == 'string':
            widget = QLineEdit()
            widget.setText('')
            widget.setFixedWidth(80)
            widget.setPlaceholderText('text')
            widget.textChanged.connect(lambda v: self._on_value_changed(pin_name, v))
            if hasattr(self, 'canvas') and self.canvas:
                widget.textChanged.connect(lambda: self.canvas.value_changed.emit())
            self.pin_values[pin_name] = ''
        elif pin_type in ('audio', 'image'):
            # Create a container for file picker with browse button
            container = QWidget()
            container.setFixedWidth(100)
            layout = QHBoxLayout(container)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(2)
            
            line_edit = QLineEdit()
            line_edit.setFixedWidth(65)
            line_edit.setPlaceholderText('📁...')
            line_edit.textChanged.connect(lambda v: self._on_value_changed(pin_name, v))
            if hasattr(self, 'canvas') and self.canvas:
                line_edit.textChanged.connect(lambda: self.canvas.value_changed.emit())
            
            browse_btn = QPushButton('...')
            browse_btn.setFixedWidth(24)
            browse_btn.setToolTip('Browse for file')
            
            def browse_file(pt=pin_type, le=line_edit):
                from PyQt6.QtWidgets import QFileDialog
                if pt == 'audio':
                    filter_str = "Audio Files (*.wav *.mp3 *.ogg *.flac);;All Files (*)"
                    title = "Select Audio File"
                else:
                    filter_str = "Image Files (*.png *.jpg *.jpeg *.gif *.bmp);;All Files (*)"
                    title = "Select Image"
                file_path, _ = QFileDialog.getOpenFileName(None, title, "", filter_str)
                if file_path:
                    # Show just filename in the widget
                    import os
                    le.setText(file_path)
                    le.setToolTip(file_path)
            
            browse_btn.clicked.connect(browse_file)
            
            layout.addWidget(line_edit)
            layout.addWidget(browse_btn)
            
            widget = container
            self.pin_values[pin_name] = ''
        
        if widget:
            # Style the widget
            widget.setStyleSheet("""
                QLineEdit, QComboBox {
                    background-color: #2a2a2a;
                    color: #ffffff;
                    border: 1px solid #555;
                    border-radius: 3px;
                    padding: 2px;
                    font-size: 9px;
                }
                QPushButton {
                    background-color: #3a3a3a;
                    color: #fff;
                    border: 1px solid #555;
                    border-radius: 3px;
                    padding: 2px;
                    font-size: 9px;
                }
                QPushButton:hover {
                    background-color: #4a4a4a;
                }
                QComboBox::drop-down {
                    border: none;
                }
                QComboBox::down-arrow {
                    image: none;
                    border-left: 4px solid transparent;
                    border-right: 4px solid transparent;
                    border-top: 4px solid #aaa;
                }
            """)
            
            # Create proxy widget and position it
            proxy = QGraphicsProxyWidget(self)
            proxy.setWidget(widget)
            
            # Position safely inside the box
            if getattr(self, 'is_compact', False):
                proxy.setPos(-15, y_pos - 12)
            else:
                proxy.setPos(0, y_pos - 12)
            self.value_widgets[pin_name] = proxy
    
    def _on_value_changed(self, pin_name, value):
        """Handle value changes from input widgets."""
        pin_type = self.inputs.get(pin_name)
        if isinstance(pin_type, str):
            try:
                if pin_type == 'int':
                    self.pin_values[pin_name] = int(value) if value else 0
                elif pin_type == 'float':
                    self.pin_values[pin_name] = float(value) if value else 0.0
                elif pin_type == 'bool':
                    self.pin_values[pin_name] = value
                elif pin_type == 'string':
                    self.pin_values[pin_name] = value
            except ValueError:
                pass  # Keep previous value on invalid input
    
    def get_input_value(self, pin_name):
        """Get the value for an input pin (either from widget or default)."""
        return self.pin_values.get(pin_name)
    
    def cleanup(self):
        """Detach visuals and effects so the node can be removed safely mid-event."""
        try:
            eff = None
            try:
                eff = self.graphicsEffect()
            except Exception:
                eff = None
            if eff:
                try:
                    self.setGraphicsEffect(None)
                except Exception:
                    pass
        except Exception:
            pass
    
        # Remove pin and label items from scene without touching parent-child relations
        try:
            for pin in list(self.input_pins.values()) + list(self.output_pins.values()):
                try:
                    pin.setParentItem(None)
                    if pin.scene():
                        pin.scene().removeItem(pin)
                except Exception:
                    pass
        except Exception:
            pass
    
        try:
            for label in list(self.pin_labels):
                try:
                    label.setParentItem(None)
                    if label.scene():
                        label.scene().removeItem(label)
                except Exception:
                    pass
        except Exception:
            pass
    
        # Remove value widgets
        try:
            for proxy in list(self.value_widgets.values()):
                try:
                    proxy.setParentItem(None)
                    if proxy.scene():
                        proxy.scene().removeItem(proxy)
                except Exception:
                    pass
        except Exception:
            pass
    
        # Attempt to remove title text item separately
        try:
            if getattr(self, 'title', None):
                try:
                    self.title.setParentItem(None)
                    if self.title.scene():
                        self.title.scene().removeItem(self.title)
                except Exception:
                    pass
        except Exception:
            pass
    
        # clear internal references
        try:
            self.input_pins.clear()
            self.output_pins.clear()
            self.pin_labels.clear()
            self.value_widgets.clear()
        except Exception:
            pass
        # cleanup complete — pins will be recreated when setup_pins is called
    
    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange and self.scene():
            # Snap to grid logic
            grid = 24  # Matches grid spacing in drawBackground
            new_pos = value
            x = round(new_pos.x() / grid) * grid
            y = round(new_pos.y() / grid) * grid
            return QPointF(x, y)
            
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged and hasattr(self, "canvas") and self.canvas:
            self.canvas.update_connections_for_node(self)
            
        return super().itemChange(change, value)
    
    def _add_type_selector_widget(self, pin_name, current_type, y_pos):
        """Add a type selector dropdown for composite I/O nodes."""
        # Initialize external_name if not set
        if not hasattr(self, 'external_name'):
            self.external_name = pin_name
        
        type_combo = QComboBox()
        type_combo.addItems(['any', 'int', 'float', 'string', 'bool'])
        type_combo.setCurrentText(current_type)
        type_combo.setFixedWidth(70)
        type_combo.setStyleSheet("""
            QComboBox {
                background-color: #3a3a3a;
                color: #ffcc00;
                border: 1px solid #666;
                border-radius: 3px;
                padding: 2px 4px;
                font-size: 9px;
                font-weight: bold;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox:hover {
                background-color: #4a4a4a;
            }
        """)
        
        def on_type_changed(new_type):
            # Update node's pin_type attribute
            self.pin_type = new_type
            # Rebuild pins with new type
            tname = getattr(self, 'template_name', None)
            if tname == '__composite_input__':
                pin_key = list(self.output_pins.keys())[0] if self.output_pins else pin_name
                self.outputs = {pin_key: new_type}
                self.setup_pins(self.inputs, self.outputs)
            elif tname == '__composite_output__':
                pin_key = list(self.input_pins.keys())[0] if self.input_pins else pin_name
                self.inputs = {pin_key: new_type}
                self.setup_pins(self.inputs, self.outputs)
            # Update connections
            if hasattr(self, 'canvas') and self.canvas:
                self.canvas.update_connections_for_node(self)
        
        type_combo.currentTextChanged.connect(on_type_changed)
        
        proxy = QGraphicsProxyWidget(self)
        proxy.setWidget(type_combo)
        # Position based on whether it's input or output
        tname = getattr(self, 'template_name', None)
        if tname == '__composite_input__':
            proxy.setPos(-100, y_pos - 8)  # Left side for composite input
        else:
            proxy.setPos(30, y_pos - 8)  # Right side for composite output
        
        if not hasattr(self, 'type_selectors'):
            self.type_selectors = {}
        self.type_selectors[pin_name] = proxy
        
        # Add name editor for external pin name
        name_edit = QLineEdit()
        name_edit.setText(self.external_name)
        name_edit.setPlaceholderText("pin name")
        name_edit.setFixedWidth(80)
        name_edit.setStyleSheet("""
            QLineEdit {
                background-color: #2a2a2a;
                color: #cccccc;
                border: 1px solid #555;
                border-radius: 3px;
                padding: 2px 4px;
                font-size: 9px;
            }
            QLineEdit:hover {
                background-color: #333333;
            }
            QLineEdit:focus {
                border-color: #ffcc00;
            }
        """)
        
        def on_name_changed(new_name):
            if new_name.strip():
                self.external_name = new_name.strip()
        
        name_edit.textChanged.connect(on_name_changed)
        
        name_proxy = QGraphicsProxyWidget(self)
        name_proxy.setWidget(name_edit)
        if tname == '__composite_input__':
            name_proxy.setPos(-100, y_pos + 15)  # Below type selector
        else:
            name_proxy.setPos(30, y_pos + 15)  # Below type selector
        
        if not hasattr(self, 'name_editors'):
            self.name_editors = {}
        self.name_editors[pin_name] = name_proxy
    



class CommentBoxItem(QGraphicsRectItem):
    """A floating comment box to group nodes."""
    def __init__(self, x, y, w, h, title="Comment"):
        super().__init__(0, 0, w, h)
        self.setPos(x, y)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setZValue(-100) # Below nodes
        
        self.setBrush(QBrush(QColor(40, 40, 40, 80)))
        self.setPen(QPen(QColor(255, 255, 255, 60), 1, Qt.PenStyle.DashLine))
        
        self.title_item = QGraphicsTextItem(title, self)
        self.title_item.setDefaultTextColor(QColor(255, 255, 255, 180))
        font = QFont("Segoe UI", 12, QFont.Weight.Bold)
        self.title_item.setFont(font)
        self.title_item.setPos(10, 5)
        
        # Corner resize handle
        self.handle_size = 12
        self.resizing = False
        
    def paint(self, painter, option, widget=None):
        super().paint(painter, option, widget)
        # Draw resize handle
        rect = self.rect()
        painter.setBrush(QColor(100, 100, 100, 150))
        painter.setPen(Qt.PenStyle.NoPen)
        handle_rect = QRectF(rect.right() - self.handle_size, rect.bottom() - self.handle_size, self.handle_size, self.handle_size)
        painter.drawRect(handle_rect)
    
    def mousePressEvent(self, event):
        rect = self.rect()
        if event.pos().x() > rect.right() - self.handle_size and event.pos().y() > rect.bottom() - self.handle_size:
            self.resizing = True
            event.accept()
        else:
            super().mousePressEvent(event)
            
    def mouseMoveEvent(self, event):
        if self.resizing:
            new_w = max(100, event.pos().x())
            new_h = max(60, event.pos().y())
            self.setRect(0, 0, new_w, new_h)
            event.accept()
        else:
            super().mouseMoveEvent(event)
            
    def mouseReleaseEvent(self, event):
        self.resizing = False
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        new_title, ok = QInputDialog.getText(None, "Comment Box", "Edit Text:", text=self.title_item.toPlainText())
        if ok:
            self.title_item.setPlainText(new_title)
        super().mouseDoubleClickEvent(event)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange and self.scene():
            # Snap to grid logic
            grid = 24  # Matches grid spacing in drawBackground
            new_pos = value
            x = round(new_pos.x() / grid) * grid
            y = round(new_pos.y() / grid) * grid
            return QPointF(x, y)
        return super().itemChange(change, value)
