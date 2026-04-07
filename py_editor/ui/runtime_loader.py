from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QComboBox, QCheckBox, QSlider, QProgressBar,
    QFrame, QLayout, QDialog, QScrollArea, QStackedWidget
)
from PyQt6.QtCore import Qt, QRect
from functools import partial

class RuntimeUILoader:
    @staticmethod
    def load_ui(ui_data, parent=None, on_button_click=None, on_slider_changed=None, 
                on_checkbox_changed=None, on_text_changed=None, variables=None):
        """
        Construct a live QWidget hierarchy from UI Builder JSON data.
        Returns a QWidget (the root container).
        Supports multiple screens that can be switched.
        
        Args:
            ui_data: The exported UI data from UICanvas (with optional screens)
            parent: Parent widget
            on_button_click: Callback function(button_id: str, button_name: str) called when buttons are clicked
            on_slider_changed: Callback function(slider_id: str, value: int) called when sliders change
            on_checkbox_changed: Callback function(checkbox_id: str, checked: bool) called when checkboxes change
            on_text_changed: Callback function(input_id: str, text: str) called when text inputs change
            variables: Dict of variable_name -> value for data binding
        """
        # Create a custom styled dialog that matches the canvas preview
        root = PreviewDialog(parent)
        
        # Get form size from UI data or use default
        form_data = ui_data.get("form", {})
        form_width = form_data.get("width", 400)
        form_height = form_data.get("height", 300)
        root.resize(form_width, form_height)
        
        # Store variables for binding
        root._variables = variables or {}
        root._bound_widgets = {}  # var_name -> list of (widget, prop_name)
        
        # Store callbacks on root for access
        root._callbacks = {
            'button': on_button_click,
            'slider': on_slider_changed,
            'checkbox': on_checkbox_changed,
            'text': on_text_changed
        }
        
        # Determine screen structure
        if "screens" in ui_data:
            # New multi-screen format
            screens = ui_data["screens"]
            screen_order = ui_data.get("screen_order", list(screens.keys()))
            current_screen = ui_data.get("current_screen", screen_order[0] if screen_order else "Main")
        else:
            # Old single-screen format
            screens = {"Main": ui_data.get("widgets", [])}
            screen_order = ["Main"]
            current_screen = "Main"
        
        # Store screen info for switching
        root._screens = screens
        root._screen_order = screen_order
        root._current_screen = current_screen
        root._screen_widgets = {}  # screen_name -> list of widgets
        
        # Create widgets for each screen
        for screen_name, widgets_data in screens.items():
            screen_widgets = RuntimeUILoader._create_screen_widgets(
                root, widgets_data,
                on_button_click, on_slider_changed, on_checkbox_changed, on_text_changed
            )
            root._screen_widgets[screen_name] = screen_widgets
            
            # Hide all screens except current
            for w in screen_widgets:
                if screen_name == current_screen:
                    w.show()
                else:
                    w.hide()
        
        # Add screen switch method to root
        def switch_screen(screen_name):
            if screen_name not in root._screen_widgets:
                return False
            # Hide all screens
            for sname, widgets in root._screen_widgets.items():
                for w in widgets:
                    w.hide()
            # Show target screen
            for w in root._screen_widgets[screen_name]:
                w.show()
            root._current_screen = screen_name
            return True
        
        root.switch_screen = switch_screen
        
        # Add method to update a variable and refresh bound widgets
        def update_variable(var_name, value):
            root._variables[var_name] = value
            if var_name in root._bound_widgets:
                for widget, w_type, bind_prop in root._bound_widgets[var_name]:
                    RuntimeUILoader._apply_binding(widget, w_type, bind_prop, value)
        
        root.update_variable = update_variable
        
        return root
    
    @staticmethod
    def _apply_binding(widget, w_type, bind_property, value):
        """Apply a variable value to a specific widget property"""
        prop = bind_property.lower()
        try:
            # Handle visibility binding (works for all widget types)
            if prop == 'visibility':
                widget.setVisible(bool(value))
                return
            
            # Handle enabled binding (works for most widget types)
            if prop == 'enabled':
                widget.setEnabled(bool(value))
                return
            
            # Handle position bindings
            if prop == 'posx':
                if isinstance(value, (int, float)):
                    widget.move(int(value), widget.y())
                return
            if prop == 'posy':
                if isinstance(value, (int, float)):
                    widget.move(widget.x(), int(value))
                return
            
            # Handle scale bindings (for images/labels with pixmaps)
            if prop in ('scalex', 'scaley'):
                # Store scale factors on widget for combined application
                if not hasattr(widget, '_scale_x'):
                    widget._scale_x = 1.0
                if not hasattr(widget, '_scale_y'):
                    widget._scale_y = 1.0
                
                if prop == 'scalex':
                    widget._scale_x = float(value) if isinstance(value, (int, float)) else 1.0
                else:
                    widget._scale_y = float(value) if isinstance(value, (int, float)) else 1.0
                
                # Apply scale by resizing
                if hasattr(widget, '_original_size'):
                    ow, oh = widget._original_size
                    new_w = int(ow * widget._scale_x)
                    new_h = int(oh * widget._scale_y)
                    widget.setFixedSize(new_w, new_h)
                return
            
            # Handle text binding
            if prop == 'text':
                if hasattr(widget, 'setText'):
                    widget.setText(str(value) if value is not None else "")
                return
            
            # Handle source/image binding (for Image widgets)
            if prop == 'source':
                from PyQt6.QtGui import QPixmap
                from pathlib import Path
                if hasattr(widget, 'setPixmap') and isinstance(value, str) and Path(value).exists():
                    pixmap = QPixmap(value)
                    if not pixmap.isNull():
                        widget.setPixmap(pixmap.scaled(widget.width(), widget.height(),
                                                       Qt.AspectRatioMode.KeepAspectRatio,
                                                       Qt.TransformationMode.SmoothTransformation))
                return
            
            # Handle checked binding (for checkboxes)
            if prop == 'checked':
                if hasattr(widget, 'setChecked'):
                    widget.setChecked(bool(value))
                return
            
            # Handle value binding (for sliders, progress bars)
            if prop == 'value':
                if hasattr(widget, 'setValue') and isinstance(value, (int, float)):
                    widget.setValue(int(value))
                return
            
            # Handle min/max bindings
            if prop == 'min':
                if hasattr(widget, 'setMinimum') and isinstance(value, (int, float)):
                    widget.setMinimum(int(value))
                return
            if prop == 'max':
                if hasattr(widget, 'setMaximum') and isinstance(value, (int, float)):
                    widget.setMaximum(int(value))
                return
            
            # Handle fontSize binding
            if prop == 'fontsize':
                if isinstance(value, (int, float)):
                    font = widget.font()
                    font.setPointSize(int(value))
                    widget.setFont(font)
                return
            
            # Handle backgroundColor binding
            if prop == 'backgroundcolor':
                if isinstance(value, str):
                    widget.setStyleSheet(f"background-color: {value};")
                return
            
            # Handle selectedIndex binding (for dropdowns)
            if prop == 'selectedindex':
                if hasattr(widget, 'setCurrentIndex') and isinstance(value, int):
                    widget.setCurrentIndex(value)
                return
            
            # Handle placeholder binding
            if prop == 'placeholder':
                if hasattr(widget, 'setPlaceholderText'):
                    widget.setPlaceholderText(str(value) if value is not None else "")
                return
                
        except Exception as e:
            print(f"Error applying binding {bind_property} to {w_type}: {e}")

    @staticmethod
    def _create_screen_widgets(root, widgets_data, on_button_click, on_slider_changed, 
                                on_checkbox_changed, on_text_changed):
        """Create widgets for a single screen and return the top-level widgets list"""
        widgets_map = {}
        data_map = {}
        top_level_widgets = []
        
        # Get form size from root for proper coordinate mapping
        # The canvas uses (0,0) as center, so offset by half the form size
        form_width = root.width()
        form_height = root.height()
        OFFSET_X = form_width // 2
        OFFSET_Y = form_height // 2
        
        # 1. Create all widgets
        for wd in widgets_data:
            w_id = wd["id"]
            w_type = wd["type"]
            props = wd.get("properties", {})
            
            widget = RuntimeUILoader._create_widget(
                w_type, props, w_id, 
                on_button_click, on_slider_changed, on_checkbox_changed, on_text_changed
            )
            if widget:
                RuntimeUILoader._apply_style(widget, props, w_type)
                widgets_map[w_id] = widget
                data_map[w_id] = wd
                
                # Store original size for scale bindings
                widget._original_size = (widget.width(), widget.height())
                
                # Handle new multi-binding format
                bindings = props.get('bindings', [])
                
                # Backward compatibility: convert old single binding to new format
                old_binding = props.get('binding')
                if old_binding and not bindings:
                    bindings = [{'property': 'text', 'variable': old_binding}]
                
                # Process all bindings
                for bind_info in bindings:
                    var_name = bind_info.get('variable', '')
                    bind_prop = bind_info.get('property', 'text')
                    
                    if var_name and var_name != '(none)' and hasattr(root, '_variables'):
                        var_value = root._variables.get(var_name)
                        if var_value is not None:
                            RuntimeUILoader._apply_binding(widget, w_type, bind_prop, var_value)
                        
                        # Register for updates
                        if var_name not in root._bound_widgets:
                            root._bound_widgets[var_name] = []
                        root._bound_widgets[var_name].append((widget, w_type, bind_prop))
        
        # 2. Build hierarchy
        for w_id, widget in widgets_map.items():
            wd = data_map[w_id]
            parent_id = wd.get("parent_id")
            raw_pos = wd.get("pos", [0, 0])
            
            if parent_id and parent_id in widgets_map:
                parent_widget = widgets_map[parent_id]
                parent_data = data_map[parent_id]
                
                # If parent is a container with layout
                if parent_data["type"] == "VContainer":
                     if not parent_widget.layout():
                        layout = QVBoxLayout(parent_widget)
                        layout.setSpacing(parent_data.get("properties", {}).get("gap", 8))
                        layout.setContentsMargins(
                            parent_data.get("properties", {}).get("padding", 8),
                            parent_data.get("properties", {}).get("padding", 8),
                            parent_data.get("properties", {}).get("padding", 8),
                            parent_data.get("properties", {}).get("padding", 8)
                        )
                     parent_widget.layout().addWidget(widget)
                     
                elif parent_data["type"] == "HContainer":
                    if not parent_widget.layout():
                        layout = QHBoxLayout(parent_widget)
                        layout.setSpacing(parent_data.get("properties", {}).get("gap", 8))
                        layout.setContentsMargins(
                            parent_data.get("properties", {}).get("padding", 8),
                            parent_data.get("properties", {}).get("padding", 8),
                            parent_data.get("properties", {}).get("padding", 8),
                            parent_data.get("properties", {}).get("padding", 8)
                        )
                    parent_widget.layout().addWidget(widget)
                else:
                    # Absolute parenting (Frame or nesting)
                    widget.setParent(parent_widget)
                    widget.move(int(raw_pos[0]), int(raw_pos[1]))
            else:
                # Top level - add to canvas root
                widget.setParent(root.canvas_area)
                x = int(raw_pos[0] + OFFSET_X)
                y = int(raw_pos[1] + OFFSET_Y)
                widget.move(x, y)
                top_level_widgets.append(widget)
        
        return top_level_widgets

    @staticmethod
    def _create_widget(w_type, props, widget_id=None, on_button_click=None, 
                       on_slider_changed=None, on_checkbox_changed=None, on_text_changed=None):
        # Normalize type to lowercase for case-insensitive matching if needed, 
        # but UI builder exports "Button", "Label" etc (Keys from WIDGET_PALETTE)
        # The 'type' property INSIDE the palette dict is lowercase 'button', 
        # but UIWidgetItem uses the palette Key as its widget_type.
        
        wt = w_type.lower()
        
        if wt == "button":
            button_text = props.get("text", "Button")
            # Use buttonId property if set, otherwise fall back to widget ID, or button text
            button_id = props.get("buttonId", "")
            if not button_id and widget_id is not None:
                button_id = str(widget_id)
            if not button_id:
                button_id = button_text
            print(f"Creating button: id='{button_id}', text='{button_text}', callback={on_button_click}")
            w = QPushButton(button_text)
            # IMPORTANT: Disable auto-default behavior so button clicks don't close the dialog
            w.setAutoDefault(False)
            w.setDefault(False)
            # Connect button click to callback if provided
            if on_button_click:
                # Use partial to capture button_id and button_text
                print(f"  Connecting button click to callback")
                w.clicked.connect(partial(on_button_click, button_id, button_text))
        elif wt == "label":
            w = QLabel(props.get("text", "Label"))
            w.setAlignment(Qt.AlignmentFlag.AlignCenter)
        elif wt == "textinput" or wt == "input":
            w = QLineEdit()
            w.setPlaceholderText(props.get("placeholder", ""))
            # Connect text changed to callback if provided
            if on_text_changed:
                input_id = props.get("inputId", "")
                if not input_id and widget_id is not None:
                    input_id = str(widget_id)
                if not input_id:
                    input_id = "input"
                w.textChanged.connect(partial(on_text_changed, input_id))
        elif wt == "checkbox":
            w = QCheckBox(props.get("text", "Checkbox"))
            w.setChecked(props.get("checked", False))
            # Connect checkbox state changed to callback if provided
            if on_checkbox_changed:
                checkbox_id = props.get("checkboxId", "")
                if not checkbox_id and widget_id is not None:
                    checkbox_id = str(widget_id)
                if not checkbox_id:
                    checkbox_id = "checkbox"
                w.stateChanged.connect(lambda state, cid=checkbox_id: on_checkbox_changed(cid, state == 2))
        elif wt == "slider":
            w = QSlider(Qt.Orientation.Horizontal)
            w.setRange(props.get("min", 0), props.get("max", 100))
            w.setValue(props.get("value", 50))
            # Connect slider value changed to callback if provided
            if on_slider_changed:
                slider_id = props.get("sliderId", "")
                if not slider_id and widget_id is not None:
                    slider_id = str(widget_id)
                if not slider_id:
                    slider_id = "slider"
                w.valueChanged.connect(partial(on_slider_changed, slider_id))
        elif wt == "dropdown":
            w = QComboBox()
            w.addItems(props.get("items", []))
        elif wt in ("vcontainer", "hcontainer", "frame", "container"):
            w = QFrame()
        elif wt == "progressbar": # Palette key is ProgressBar
            from PyQt6.QtWidgets import QProgressBar
            w = QProgressBar()
            w.setMaximum(props.get("max", 100))
            w.setValue(props.get("value", 50))
        elif wt == "image":
            from PyQt6.QtGui import QPixmap
            from pathlib import Path
            w = QLabel()
            w.setAlignment(Qt.AlignmentFlag.AlignCenter)
            source = props.get("source", "")
            if source and Path(source).exists():
                pixmap = QPixmap(source)
                if not pixmap.isNull():
                    # Scale to fit widget size
                    width = props.get("width", 100)
                    height = props.get("height", 100)
                    scale_mode = props.get("scaleMode", "fit")
                    if scale_mode == "fit":
                        pixmap = pixmap.scaled(width, height, 
                                              Qt.AspectRatioMode.KeepAspectRatio,
                                              Qt.TransformationMode.SmoothTransformation)
                    elif scale_mode == "fill":
                        pixmap = pixmap.scaled(width, height, 
                                              Qt.AspectRatioMode.IgnoreAspectRatio,
                                              Qt.TransformationMode.SmoothTransformation)
                    w.setPixmap(pixmap)
            else:
                w.setText("🖼️")
                w.setStyleSheet("border: 1px dashed #555; color: #888;")
        else:
            w = QLabel(f"Unknown: {w_type}")
            
        w.setFixedSize(props.get("width", 100), props.get("height", 40))
        return w

    @staticmethod
    def _apply_style(widget, props, w_type):
        bg = props.get("backgroundColor", "#2d2d30")
        fg = props.get("textColor", "#e0e0e0") 
        border = props.get("borderColor")
        bg_image = props.get("backgroundImage", "")
        
        wt = w_type.lower()
        
        # Build background style
        bg_style = ""
        if bg_image:
            from pathlib import Path
            if Path(bg_image).exists():
                bg_style = f"background-image: url('{bg_image}'); background-repeat: no-repeat; background-position: center; "
            else:
                bg_style = f"background-color: {bg}; "
        else:
            bg_style = f"background-color: {bg}; "
        
        # Special styling for buttons with hover/pressed states
        if wt == "button":
            if bg_image:
                widget.setStyleSheet(f"""
                    QPushButton {{
                        {bg_style}
                        color: {fg};
                        border: 1px solid #555;
                        border-radius: 4px;
                        padding: 4px 8px;
                    }}
                    QPushButton:hover {{
                        border-color: #0078d4;
                    }}
                    QPushButton:pressed {{
                        border-color: #0078d4;
                    }}
                """)
            else:
                widget.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {bg};
                        color: {fg};
                        border: 1px solid #555;
                        border-radius: 4px;
                        padding: 4px 8px;
                    }}
                    QPushButton:hover {{
                        background-color: #3e3e42;
                        border-color: #0078d4;
                    }}
                    QPushButton:pressed {{
                        background-color: #0078d4;
                        border-color: #0078d4;
                    }}
                """)
            widget.setCursor(Qt.CursorShape.PointingHandCursor)
            return
        
        style = bg_style
        if fg: style += f"color: {fg};"
        
        if wt in ("vcontainer", "hcontainer", "frame"):
             if border: style += f"border: 1px solid {border};"
             else: style += "border: 1px dashed #555;" if wt != "frame" else "border: 1px solid #555;"
             style += "border-radius: 4px;"
             
        widget.setStyleSheet(style)


class PreviewDialog(QDialog):
    """Draggable frameless dialog to simulate the UI Builder form"""
    def __init__(self, parent=None):
        super().__init__(parent)
        # Use Dialog type instead of Window to prevent app from closing when this closes
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        # Don't delete on close - just hide
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.resize(400, 300)
        
        # Main layout (for the border frame)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Window Frame
        self.frame = QFrame()
        self.frame.setStyleSheet("""
            QFrame {
                background-color: #1e1e1e;
                border: 1px solid #444;
                border-radius: 5px;
            }
        """)
        layout.addWidget(self.frame)
        
        # We generally expect fixed size, but let's allow basic resizing
        # The 'header' and 'canvas_area' need to be inside self.frame
        
        # Canvas Area: Full size of the frame, underneath everything else
        self.canvas_area = QWidget(self.frame)
        self.canvas_area.setGeometry(0, 0, 400, 300)
        self.canvas_area.setStyleSheet("background: transparent; border: none;")
        
        # Header (Visual only, behind controls if controls are placed there)
        # We make it a child of frame so it sits at (0,0)
        # But we want user widgets to be able to sit ON TOP of it.
        # User widgets are added to self.canvas_area.
        # If we put header in canvas_area ? No, header is part of window chrome.
        
        self.header_bar = QFrame(self.frame)
        self.header_bar.setGeometry(0, 0, 400, 30)
        self.header_bar.setStyleSheet("""
            QFrame {
                background-color: #2d2d30;
                border-bottom: 1px solid #333;
                border-top-left-radius: 5px;
                border-top-right-radius: 5px;
            }
        """)
        
        # Title Label
        self.title_label = QLabel("UI Preview", self.header_bar)
        self.title_label.setStyleSheet("color: #aaa; font-weight: bold; border: none; background: transparent;")
        self.title_label.move(10, 6)
        
        # Close Button
        self.close_btn = QPushButton("✕", self.header_bar)
        self.close_btn.setGeometry(370, 3, 24, 24)
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_btn.setStyleSheet("""
            QPushButton {
                color: #aaa;
                background: transparent;
                border: none;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #c42b1c;
                color: white;
            }
        """)
        self.close_btn.clicked.connect(self.close)
        
        # Stack order:
        # 1. frame background (from style)
        # 2. header_bar (at top)
        # 3. canvas_area (full size, transparent) -> User widgets go here
        
        # We want canvas_area to be ON TOP of header_bar so user widgets cover the header?
        # Yes, if the user placed a widget there, they intend it to be visible.
        self.canvas_area.raise_()
        
        # But wait, if canvas_area is on top, and it's full size, it might block mouse clicks to close_btn?
        # self.canvas_area has no background, so it passes mouse events? 
        # Only if WA_TransparentForMouseEvents is set, but then child widgets won't get events.
        # Standard QWidget catches mouse events if it has a background. With "background: transparent", it *might* pass through.
        # Actually in Qt, a transparent widget still consumes mouse events if it's not WA_TransparentForMouseEvents.
        
        # Correct approach:
        # Put Close button in a separate widget that is ALWAYS on huge top (z-value).
        # Or, just let the user cover the close button if they really want to (it's their UI).
        # But for 'Preview' UX, the close button should probably remain usable.
        # Let's keep Close Button on top of everything.
        self.close_btn.setParent(self.frame)
        self.close_btn.raise_()
        
        self.old_pos = None

    def resizeEvent(self, event):
        # Keep internal widgets sized to frame
        w = self.width()
        h = self.height()
        if hasattr(self, 'frame'):
             # Layout handles frame size, but we need to update children of frame
             pass 
        if hasattr(self, 'header_bar'):
            self.header_bar.resize(w, 30)
        if hasattr(self, 'canvas_area'):
            self.canvas_area.resize(w, h)
        if hasattr(self, 'close_btn'):
            self.close_btn.move(w - 30, 3)
        super().resizeEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.old_pos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event):
        if self.old_pos:
            delta = event.globalPosition().toPoint() - self.old_pos
            self.move(self.pos() + delta)
            self.old_pos = event.globalPosition().toPoint()

    def mouseReleaseEvent(self, event):
        self.old_pos = None
