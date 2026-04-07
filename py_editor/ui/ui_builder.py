"""
UI Builder Module for NodeCanvas
Visual UI editor with widget palette, canvas, and property inspector
"""

import json
from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QCheckBox,
    QTreeWidget, QTreeWidgetItem, QSplitter, QScrollArea,
    QFrame, QGraphicsView, QGraphicsScene, QGraphicsRectItem,
    QGraphicsProxyWidget, QGroupBox, QFormLayout, QSlider,
    QTextEdit, QListWidget, QListWidgetItem, QColorDialog,
    QMenu, QInputDialog, QMessageBox, QFileDialog, QTabWidget,
    QDialog, QApplication
)
from PyQt6.QtCore import Qt, QRectF, QPointF, pyqtSignal, QMimeData
from PyQt6.QtGui import QColor, QBrush, QPen, QFont, QDrag, QPainter


# Available widget types with default properties
WIDGET_PALETTE = {
    "Containers": {
        "VContainer": {"type": "container", "direction": "vertical", "gap": 8, "padding": 8, "backgroundColor": "#3c3c41", "backgroundImage": ""},
        "HContainer": {"type": "container", "direction": "horizontal", "gap": 8, "padding": 8, "backgroundColor": "#3c3c41", "backgroundImage": ""},
        "Frame": {"type": "frame", "border": True, "padding": 8, "backgroundColor": "#2d2d30", "borderColor": "#555555", "backgroundImage": ""},
    },
    "Input": {
        "Button": {"type": "button", "text": "Button", "buttonId": "", "width": 100, "height": 32, "backgroundColor": "#2d2d30", "textColor": "#e0e0e0", "backgroundImage": ""},
        "TextInput": {"type": "input", "placeholder": "Enter text...", "inputId": "", "width": 150, "height": 28, "backgroundColor": "#2d2d30", "textColor": "#e0e0e0"},
        "Slider": {"type": "slider", "min": 0, "max": 100, "value": 50, "sliderId": "", "width": 150},
        "Checkbox": {"type": "checkbox", "text": "Checkbox", "checked": False, "checkboxId": "", "textColor": "#e0e0e0"},
        "Dropdown": {"type": "dropdown", "items": ["Option 1", "Option 2"], "width": 120, "backgroundColor": "#2d2d30", "textColor": "#e0e0e0"},
    },
    "Display": {
        "Label": {"type": "label", "text": "Label", "fontSize": 12, "textColor": "#e0e0e0", "backgroundImage": ""},
        "Image": {"type": "image", "source": "", "width": 100, "height": 100, "scaleMode": "fit"},
        "ProgressBar": {"type": "progress", "value": 50, "max": 100, "width": 150},
    }
}


class WidgetPaletteItem(QFrame):
    """Draggable widget item in the palette"""
    
    def __init__(self, name, properties, parent=None):
        super().__init__(parent)
        self.widget_name = name
        self.widget_props = properties.copy()
        
        self.setFixedHeight(36)
        self.setStyleSheet("""
            QFrame {
                background-color: #2d2d30;
                border: 1px solid #3e3e42;
                border-radius: 4px;
                padding: 4px;
            }
            QFrame:hover {
                background-color: #3e3e42;
                border-color: #0078d4;
            }
        """)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        
        icon_label = QLabel(self._get_icon())
        icon_label.setStyleSheet("border: none; font-size: 14px;")
        layout.addWidget(icon_label)
        
        name_label = QLabel(name)
        name_label.setStyleSheet("border: none; color: #e0e0e0;")
        layout.addWidget(name_label)
        layout.addStretch()
    
    def _get_icon(self):
        icons = {
            "VContainer": "📦", "HContainer": "📦", "Frame": "🔲",
            "Button": "🔘", "TextInput": "📝", "Slider": "🎚️",
            "Checkbox": "☑️", "Dropdown": "📋",
            "Label": "🏷️", "Image": "🖼️", "ProgressBar": "📊"
        }
        return icons.get(self.widget_name, "📄")
    
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            drag = QDrag(self)
            mime = QMimeData()
            data = json.dumps({
                "widget": self.widget_name,
                "props": self.widget_props
            })
            mime.setText(data)
            drag.setMimeData(mime)
            drag.exec(Qt.DropAction.CopyAction)


class UIWidgetItem(QGraphicsRectItem):
    """Visual representation of a UI widget on the canvas"""
    
    HANDLE_SIZE = 12  # Larger handles for easier clicking
    
    def __init__(self, widget_type, properties, widget_id):
        super().__init__()
        self.widget_type = widget_type
        self.properties = properties.copy()
        self.widget_id = widget_id
        self.selected = False
        self._resizing = False
        self._resize_handle = None
        self._resize_start_rect = None
        self._resize_start_scene_pos = None
        self._resize_start_item_pos = None
        
        # Set size from properties or defaults
        w = self.properties.get('width', 100)
        h = self.properties.get('height', 40)
        self.setRect(0, 0, w, h)
        
        # Visual style
        self.setBrush(QBrush(QColor(45, 45, 48)))
        self.setPen(QPen(QColor(60, 60, 65), 1))
        
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemClipsChildrenToShape)  # Prevent children from drawing outside
        self.setAcceptHoverEvents(True)
        
        # Add embedded widget preview
        self._create_preview()
        
    def layout_children(self):
        """Auto-layout children if this is a container"""
        if self.widget_type not in ('VContainer', 'HContainer', 'Frame'):
            return
            
        children = [c for c in self.childItems() if isinstance(c, UIWidgetItem)]
        if not children:
            return
            
        padding = self.properties.get('padding', 8)
        gap = self.properties.get('gap', 8)
        
        if self.widget_type == 'VContainer':
            # Vertical layout
            # Sort by Y position to maintain user's visual order approx
            children.sort(key=lambda c: c.pos().y())
            
            current_y = padding
            max_w = 0
            
            for child in children:
                child.setPos(padding, current_y)
                current_y += child.rect().height() + gap
                max_w = max(max_w, child.rect().width())
            
            # Auto-fit container
            new_h = current_y - gap + padding
            new_w = max(self.rect().width(), max_w + padding * 2)
            self.setRect(0, 0, new_w, new_h)
            
        elif self.widget_type == 'HContainer':
            # Horizontal layout
            children.sort(key=lambda c: c.pos().x())
            
            current_x = padding
            max_h = 0
            
            for child in children:
                child.setPos(current_x, padding)
                current_x += child.rect().width() + gap
                max_h = max(max_h, child.rect().height())
                
            new_w = current_x - gap + padding
            new_h = max(self.rect().height(), max_h + padding * 2)
            self.setRect(0, 0, new_w, new_h)
            
        self._update_preview_size()
        self.update()
        
    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
             pass
        return super().itemChange(change, value)
    
    def _get_handle_rects(self):
        """Get the resize handle rectangles - positioned OUTSIDE the widget for easier access"""
        r = self.rect()
        s = self.HANDLE_SIZE
        hs = s / 2  # half size for centering
        return {
            # Corner handles - outside corners
            'br': QRectF(r.right() - hs, r.bottom() - hs, s, s),
            'bl': QRectF(r.left() - hs, r.bottom() - hs, s, s),
            'tr': QRectF(r.right() - hs, r.top() - hs, s, s),
            'tl': QRectF(r.left() - hs, r.top() - hs, s, s),
            # Edge handles - centered on edges
            'r': QRectF(r.right() - hs, r.center().y() - hs, s, s),
            'l': QRectF(r.left() - hs, r.center().y() - hs, s, s),
            'b': QRectF(r.center().x() - hs, r.bottom() - hs, s, s),
            't': QRectF(r.center().x() - hs, r.top() - hs, s, s),
        }
    
    def _get_handle_at(self, pos):
        """Check if position is over a resize handle - only at edges/corners"""
        if not self.isSelected():
            return None
        # Expand hit area slightly for easier clicking
        for name, rect in self._get_handle_rects().items():
            expanded = rect.adjusted(-2, -2, 2, 2)
            if expanded.contains(pos):
                return name
        return None
    
    def hoverMoveEvent(self, event):
        handle = self._get_handle_at(event.pos())
        if handle:
            cursors = {
                'br': Qt.CursorShape.SizeFDiagCursor, 'tl': Qt.CursorShape.SizeFDiagCursor,
                'bl': Qt.CursorShape.SizeBDiagCursor, 'tr': Qt.CursorShape.SizeBDiagCursor,
                'r': Qt.CursorShape.SizeHorCursor, 'l': Qt.CursorShape.SizeHorCursor,
                'b': Qt.CursorShape.SizeVerCursor, 't': Qt.CursorShape.SizeVerCursor,
            }
            self.setCursor(cursors.get(handle, Qt.CursorShape.ArrowCursor))
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)
        super().hoverMoveEvent(event)
    
    def mousePressEvent(self, event):
        handle = self._get_handle_at(event.pos())
        if handle and event.button() == Qt.MouseButton.LeftButton:
            self._resizing = True
            self._resize_handle = handle
            self._resize_start_rect = self.rect()
            self._resize_start_scene_pos = event.scenePos()
            self._resize_start_item_pos = self.pos()
            event.accept()
        else:
            super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event):
        if self._resizing:
            self.prepareGeometryChange()  # Notify scene of incoming geometry change
            
            # Calculate delta in scene coordinates
            # Using scene coordinates captures the true mouse movement relative to the scene
            cur_scene_pos = event.scenePos()
            start_scene_pos = self._resize_start_scene_pos
            delta = cur_scene_pos - start_scene_pos
            
            # Start from the original rect and position
            r = QRectF(self._resize_start_rect)
            h = self._resize_handle
            min_size = 20
            
            # Get original pos in parent coordinates
            orig_pos = self._resize_start_item_pos
            
            # Calculate new geometry
            new_left = r.left()
            new_top = r.top()
            new_w = r.width()
            new_h = r.height()
            
            pos_offset_x = 0
            pos_offset_y = 0

            if 'r' in h:
                new_w = max(min_size, r.width() + delta.x())
            
            if 'l' in h:
                # Delta is positive effectively when moving right, negative when moving left
                # Ensure width does not go below min_size
                proposed_width = r.width() - delta.x()
                if proposed_width < min_size:
                    # If shrinking too much, clamp position adjustment to maintain min width
                    # The delta used for position needs to be clamped
                    clamped_delta_x = r.width() - min_size
                    new_w = min_size
                    pos_offset_x = clamped_delta_x
                else:
                    new_w = proposed_width
                    pos_offset_x = delta.x()
            
            if 'b' in h:
                new_h = max(min_size, r.height() + delta.y())
            
            if 't' in h:
                proposed_height = r.height() - delta.y()
                if proposed_height < min_size:
                    clamped_delta_y = r.height() - min_size
                    new_h = min_size
                    pos_offset_y = clamped_delta_y
                else:
                    new_h = proposed_height
                    pos_offset_y = delta.y()
            
            # Apply Changes
            # Update position (only changes for 'l' and 't' resizing)
            self.setPos(orig_pos.x() + pos_offset_x, orig_pos.y() + pos_offset_y)
            
            # Update rect (always 0,0 based for top-left)
            self.setRect(0, 0, new_w, new_h)
            
            # Sync properties
            self.properties['width'] = int(new_w)
            self.properties['height'] = int(new_h)
            
            self._update_preview_size()
            event.accept()
        else:
            super().mouseMoveEvent(event)
    
    def mouseReleaseEvent(self, event):
        if self._resizing:
            self._resizing = False
            self._resize_handle = None
            event.accept()
        else:
            super().mouseReleaseEvent(event)
    
    def _update_preview_size(self):
        """Update the preview widget size after resize"""
        w = int(self.rect().width())
        h = int(self.rect().height())
        
        if hasattr(self, 'preview_widget') and self.preview_widget:
            self.preview_widget.setFixedSize(w, h)
            
        if hasattr(self, 'proxy') and self.proxy:
            self.proxy.setGeometry(QRectF(0, 0, w, h))
            self.proxy.resize(w, h)  # Force resize
            # Ensure proxy stays at origin of the rect item
            self.proxy.setPos(0, 0)
    
    def _get_widget_style(self, widget_type):
        """Get consistent dark style for widgets"""
        # Get custom properties
        bg_color = self.properties.get('backgroundColor')
        text_color = self.properties.get('textColor')
        border_color = self.properties.get('borderColor')
        bg_image = self.properties.get('backgroundImage', '')
        
        base_style = ""
        if bg_image:
            # Use background-image with proper path escaping
            base_style += f"background-image: url('{bg_image}'); "
            base_style += "background-repeat: no-repeat; "
            base_style += "background-position: center; "
            base_style += "background-size: cover; "
        elif bg_color:
            base_style += f"background-color: {bg_color}; "
        else:
            base_style += "background-color: #2d2d30; "
        
        if text_color:
            base_style += f"color: {text_color}; "
        else:
            base_style += "color: #e0e0e0; "
            
        base_style += "border-radius: 3px; "
        
        if widget_type == 'button':
            return f"QPushButton {{ {base_style} border: 1px solid #555; }} QPushButton:hover {{ background-color: #3e3e42; }}"
        elif widget_type == 'input':
            return f"QLineEdit {{ {base_style} border: 1px solid #555; padding: 2px 4px; }}"
        elif widget_type in ('container', 'frame'):
            if not bg_color and not bg_image:
                # Default transparent/dim for containers
                base_style = base_style.replace("background-color: #2d2d30;", "background-color: rgba(60, 60, 65, 100);")
            
            border_style = "1px dashed #888"
            if border_color:
                border_style = f"1px solid {border_color}"
            elif widget_type == 'frame':
                 border_style = "1px solid #555"
            elif widget_type in ('container', 'VContainer', 'HContainer'):
                 border_style = "1px dashed #444"
                 
            return f"""
                QFrame {{
                    {base_style}
                    border: {border_style};
                    border-radius: 4px;
                }}
            """
        return f"* {{ {base_style} border: 1px solid #555; }}"
    
    def update_style(self):
        """Update the style of the preview widget based on current properties"""
        if hasattr(self, 'preview_widget') and self.preview_widget:
            t = self.properties.get('type', 'label')
            self.preview_widget.setStyleSheet(self._get_widget_style(t))
    
    def _refresh_preview(self):
        """Refresh the preview widget with current properties"""
        self.update_style()
        # Update text if applicable
        if hasattr(self, 'preview_widget') and self.preview_widget:
            t = self.properties.get('type', 'label')
            if t in ('button', 'label', 'checkbox'):
                text = self.properties.get('text', '')
                if hasattr(self.preview_widget, 'setText'):
                    self.preview_widget.setText(text)
            elif t == 'image':
                # Reload the image
                from PyQt6.QtGui import QPixmap
                source = self.properties.get('source', '')
                if source and Path(source).exists():
                    pixmap = QPixmap(source)
                    if not pixmap.isNull():
                        w = int(self.rect().width())
                        h = int(self.rect().height())
                        scale_mode = self.properties.get('scaleMode', 'fit')
                        if scale_mode == 'fit':
                            pixmap = pixmap.scaled(w, h, 
                                                  Qt.AspectRatioMode.KeepAspectRatio,
                                                  Qt.TransformationMode.SmoothTransformation)
                        else:
                            pixmap = pixmap.scaled(w, h, 
                                                  Qt.AspectRatioMode.IgnoreAspectRatio,
                                                  Qt.TransformationMode.SmoothTransformation)
                        self.preview_widget.setPixmap(pixmap)
                        self.preview_widget.setStyleSheet("")
                else:
                    self.preview_widget.clear()
                    self.preview_widget.setText("🖼️")
                    self.preview_widget.setStyleSheet("border: 1px dashed #555; color: #888; background: #2d2d30;")
            
    def _create_preview(self):
        """Create a preview widget inside the graphics item"""
        widget = None
        t = self.properties.get('type', 'label')
        
        if t == 'button':
            widget = QPushButton(self.properties.get('text', 'Button'))
        elif t == 'label':
            widget = QLabel(self.properties.get('text', 'Label'))
            widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
        elif t == 'input':
            widget = QLineEdit()
            widget.setPlaceholderText(self.properties.get('placeholder', ''))
        elif t == 'checkbox':
            widget = QCheckBox(self.properties.get('text', 'Checkbox'))
            widget.setChecked(self.properties.get('checked', False))
        elif t == 'slider':
            widget = QSlider(Qt.Orientation.Horizontal)
            widget.setRange(self.properties.get('min', 0), self.properties.get('max', 100))
            widget.setValue(self.properties.get('value', 50))
        elif t == 'dropdown':
            widget = QComboBox()
            widget.addItems(self.properties.get('items', ['Option 1']))
        elif t == 'progress':
            from PyQt6.QtWidgets import QProgressBar
            widget = QProgressBar()
            widget.setMaximum(self.properties.get('max', 100))
            widget.setValue(self.properties.get('value', 50))
        elif t == 'image':
            from PyQt6.QtGui import QPixmap
            widget = QLabel()
            widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
            source = self.properties.get('source', '')
            if source and Path(source).exists():
                pixmap = QPixmap(source)
                if not pixmap.isNull():
                    w = int(self.rect().width())
                    h = int(self.rect().height())
                    scale_mode = self.properties.get('scaleMode', 'fit')
                    if scale_mode == 'fit':
                        pixmap = pixmap.scaled(w, h, 
                                              Qt.AspectRatioMode.KeepAspectRatio,
                                              Qt.TransformationMode.SmoothTransformation)
                    else:
                        pixmap = pixmap.scaled(w, h, 
                                              Qt.AspectRatioMode.IgnoreAspectRatio,
                                              Qt.TransformationMode.SmoothTransformation)
                    widget.setPixmap(pixmap)
            else:
                widget.setText("🖼️")
                widget.setStyleSheet("border: 1px dashed #555; color: #888; background: #2d2d30;")
        elif t in ('container', 'frame'):
            widget = QFrame()
        
        if widget:
            widget.setFixedSize(int(self.rect().width()), int(self.rect().height()))
            widget.setStyleSheet(self._get_widget_style(t))
            # Disable mouse events on the preview widget so we can move/resize the item
            widget.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            proxy = QGraphicsProxyWidget(self)
            proxy.setWidget(widget)
            # Make the proxy not accept mouse events so the QGraphicsRectItem handles them
            try:
                proxy.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
                proxy.setAcceptHoverEvents(False)
                proxy.setEnabled(False)
                # Ensure the proxy is not selectable or movable itself
                proxy.setFlag(QGraphicsProxyWidget.GraphicsItemFlag.ItemIsSelectable, False)
                proxy.setFlag(QGraphicsProxyWidget.GraphicsItemFlag.ItemIsMovable, False)
                proxy.setFlag(QGraphicsProxyWidget.GraphicsItemFlag.ItemSendsGeometryChanges, False)
                # Keep proxy behind potential overlays but above background
                proxy.setZValue(1)
            except Exception:
                # Some PyQt versions may not allow disabling flags - ignore
                pass
            self.preview_widget = widget
            self.proxy = proxy
    
    def paint(self, painter, option, widget=None):
        # Draw selection highlight
        if self.isSelected():
            painter.setPen(QPen(QColor(0, 120, 212), 2))
            painter.drawRect(self.rect().adjusted(-2, -2, 2, 2))
            
            # Draw resize handles
            painter.setBrush(QBrush(QColor(0, 120, 212)))
            for handle_rect in self._get_handle_rects().values():
                painter.drawRect(handle_rect)
                
        super().paint(painter, option, widget)
    
    def itemChange(self, change, value):
        if change == QGraphicsRectItem.GraphicsItemChange.ItemPositionHasChanged:
            # Snap to grid
            grid = 8
            x = round(value.x() / grid) * grid
            y = round(value.y() / grid) * grid
            return QPointF(x, y)
        return super().itemChange(change, value)


class UICanvas(QGraphicsView):
    """Canvas for placing and arranging UI widgets"""
    
    widget_selected = pyqtSignal(object)  # Emits UIWidgetItem or None
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self._scene.setSceneRect(-2000, -2000, 4000, 4000)
        self.setScene(self._scene)
        
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setAcceptDrops(True)
        
        self.widgets = []
        self.next_id = 1
        
        # Form size (for preview window)
        self.form_width = 400
        self.form_height = 300
        
        # Screen management
        self.screens = {"Screen 1": []}  # screen_name -> list of widget data
        self.current_screen = "Screen 1"
        self.screen_order = ["Screen 1"]  # For ordering screens
        
        # Zoom support
        self.zoom_level = 1.0
        self.min_zoom = 0.1
        self.max_zoom = 3.0
        
        # Panning state
        self._is_panning = False
        self._pan_start_pos = None
        
        # Form preview items (stored for resizing)
        self._form_rect = None
        self._form_title = None
        
        # Style
        
        # Style
        self.setStyleSheet("""
            QGraphicsView {
                background-color: #1e1e1e;
                border: 1px solid #333;
            }
        """)
        
        # Draw form preview area
        self._draw_form_preview()
    
    def set_form_size(self, width, height):
        """Set the form preview size"""
        self.form_width = width
        self.form_height = height
        
        # Update the form rect
        if self._form_rect:
            self._form_rect.setRect(-width/2, -height/2, width, height)
        if self._form_title:
            self._form_title.setRect(-width/2, -height/2, width, 30)
        
        self._scene.update()
    
    def _draw_form_preview(self):
        """Draw a preview form/window outline"""
        w, h = self.form_width, self.form_height
        self._form_rect = QGraphicsRectItem(-w/2, -h/2, w, h)
        self._form_rect.setBrush(QBrush(QColor(30, 30, 32)))
        self._form_rect.setPen(QPen(QColor(80, 80, 85), 2))
        self._form_rect.setZValue(-10)
        self._scene.addItem(self._form_rect)
        
        # Title bar
        self._form_title = QGraphicsRectItem(-w/2, -h/2, w, 30)
        self._form_title.setBrush(QBrush(QColor(45, 45, 48)))
        self._form_title.setPen(QPen(Qt.PenStyle.NoPen))
        self._form_title.setZValue(-9)
        self._scene.addItem(self._form_title)
    
    def drawBackground(self, painter, rect):
        super().drawBackground(painter, rect)
        
        # Draw grid
        pen = QPen(QColor(40, 40, 45))
        pen.setWidth(1)
        painter.setPen(pen)
        
        spacing = 24
        left = int(rect.left())
        right = int(rect.right())
        top = int(rect.top())
        bottom = int(rect.bottom())
        
        x = (left // spacing) * spacing
        while x <= right:
            painter.drawLine(x, top, x, bottom)
            x += spacing
        
        y = (top // spacing) * spacing
        while y <= bottom:
            painter.drawLine(left, y, right, y)
            y += spacing
    
    def dragEnterEvent(self, event):
        if event.mimeData().hasText():
            event.acceptProposedAction()
    
    def dragMoveEvent(self, event):
        event.acceptProposedAction()
    
    def dropEvent(self, event):
        try:
            data = json.loads(event.mimeData().text())
            widget_type = data.get('widget', 'Label')
            props = data.get('props', {})
            
            pos = self.mapToScene(event.position().toPoint())
            self.add_widget(widget_type, props, pos)
            event.acceptProposedAction()
        except:
            pass
    
    def add_widget(self, widget_type, properties, pos=None):
        """Add a new widget to the canvas"""
        widget = UIWidgetItem(widget_type, properties, self.next_id)
        self.next_id += 1
        
        if pos:
            # If dropped inside a container, parent it to that container and set local position
            parent_found = None
            # Check selected item first if it's a container (explicit parenting)
            selected = self.scene().selectedItems()
            if selected and isinstance(selected[0], UIWidgetItem) and selected[0].widget_type in ('Frame', 'VContainer', 'HContainer'):
                 if selected[0].sceneBoundingRect().contains(pos):
                     parent_found = selected[0]
            
            # Fallback to geometry check
            if not parent_found:
                for w in reversed(self.widgets):
                    if w.widget_type in ('Frame', 'VContainer', 'HContainer'):
                        # Use scene bounding rect for containment test
                        if w.sceneBoundingRect().contains(pos):
                            parent_found = w
                            break
            
            if parent_found:
                # Map scene pos to parent coordinates
                local = parent_found.mapFromScene(pos)
                widget.setParentItem(parent_found)
                widget.setPos(local)
                
                # Auto-layout if container
                if parent_found.widget_type in ('VContainer', 'HContainer'):
                     # We temporarily set pos, but layout_children will likely move it
                     pass
                
                parent_found.layout_children()
            else:
                widget.setPos(pos)
        
        self._scene.addItem(widget)
        self.widgets.append(widget)
        return widget
    
    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        
        item = self.itemAt(event.position().toPoint())
        if isinstance(item, UIWidgetItem):
            self.widget_selected.emit(item)
        elif isinstance(item, QGraphicsProxyWidget):
            parent = item.parentItem()
            if isinstance(parent, UIWidgetItem):
                self.widget_selected.emit(parent)
        else:
            self.widget_selected.emit(None)
    
    def wheelEvent(self, event):
        """Handle zooming"""
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            zoom_in = 1.15
            zoom_out = 1.0 / zoom_in
            
            if event.angleDelta().y() > 0:
                zoom_factor = zoom_in
            else:
                zoom_factor = zoom_out
                
            new_zoom = self.zoom_level * zoom_factor
            if self.min_zoom <= new_zoom <= self.max_zoom:
                self.scale(zoom_factor, zoom_factor)
                self.zoom_level = new_zoom
            event.accept()
        else:
            super().wheelEvent(event)
            
    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Delete:
            for item in self._scene.selectedItems():
                if isinstance(item, UIWidgetItem):
                    self._scene.removeItem(item)
                    if item in self.widgets:
                        self.widgets.remove(item)
        else:
            super().keyPressEvent(event)
    
    def _save_current_screen(self):
        """Save current widgets to the current screen's data"""
        widgets_data = []
        try:
            from PyQt6 import sip
        except ImportError:
            import sip
        valid_widgets = []
        for widget in self.widgets:
            if sip.isdeleted(widget):
                continue
            
            try:
                parent_id = None
                parent_item = widget.parentItem()
                if parent_item and isinstance(parent_item, UIWidgetItem):
                    # Double check parent isn't deleted
                    if not sip.isdeleted(parent_item):
                        parent_id = parent_item.widget_id
                
                widgets_data.append({
                    "id": widget.widget_id,
                    "type": widget.widget_type,
                    "properties": widget.properties.copy(),
                    "pos": [widget.pos().x(), widget.pos().y()],
                    "parent_id": parent_id
                })
                valid_widgets.append(widget)
            except RuntimeError:
                # C++ object deleted
                continue
                
        # Update our list to remove any dead objects we found
        self.widgets = valid_widgets
        self.screens[self.current_screen] = widgets_data
    
    def _load_screen(self, screen_name):
        """Load widgets from a screen's data"""
        # Clear existing widgets
        for widget in self.widgets[:]:
            self._scene.removeItem(widget)
        self.widgets.clear()
        
        # Load widgets for this screen
        widgets_data = self.screens.get(screen_name, [])
        for wd in widgets_data:
            widget = self.add_widget(
                wd.get("type", "Label"),
                wd.get("properties", {}),
                QPointF(wd["pos"][0], wd["pos"][1]) if "pos" in wd else None
            )
            widget.widget_id = wd.get("id", widget.widget_id)
            self.next_id = max(self.next_id, widget.widget_id + 1)
    
    def switch_screen(self, screen_name):
        """Switch to a different screen"""
        if screen_name not in self.screens:
            return False
        # Save current screen first
        self._save_current_screen()
        # Switch and load new screen
        self.current_screen = screen_name
        self._load_screen(screen_name)
        return True
    
    def add_screen(self, name=None):
        """Add a new screen"""
        if name is None:
            # Generate a unique name
            i = 1
            while f"Screen {i}" in self.screens:
                i += 1
            name = f"Screen {i}"
        
        if name in self.screens:
            return None  # Already exists
        
        # Save current screen first
        self._save_current_screen()
        
        # Create new empty screen
        self.screens[name] = []
        self.screen_order.append(name)
        
        # Switch to the new screen
        self.current_screen = name
        self._load_screen(name)
        
        return name
    
    def rename_screen(self, old_name, new_name):
        """Rename a screen"""
        if old_name not in self.screens or new_name in self.screens:
            return False
        if old_name == new_name:
            return True
        
        # Update screens dict
        self.screens[new_name] = self.screens.pop(old_name)
        
        # Update order
        idx = self.screen_order.index(old_name)
        self.screen_order[idx] = new_name
        
        # Update current screen if needed
        if self.current_screen == old_name:
            self.current_screen = new_name
        
        return True
    
    def delete_screen(self, name):
        """Delete a screen (can't delete last screen)"""
        if len(self.screens) <= 1:
            return False
        if name not in self.screens:
            return False
        
        # Remove from dict and order
        del self.screens[name]
        self.screen_order.remove(name)
        
        # If we deleted current screen, switch to first available
        if self.current_screen == name:
            self.current_screen = self.screen_order[0]
            self._load_screen(self.current_screen)
        
        return True
    
    def move_screen(self, name, direction):
        """Move screen up (-1) or down (+1) in order"""
        if name not in self.screen_order:
            return False
        idx = self.screen_order.index(name)
        new_idx = idx + direction
        if new_idx < 0 or new_idx >= len(self.screen_order):
            return False
        self.screen_order[idx], self.screen_order[new_idx] = self.screen_order[new_idx], self.screen_order[idx]
        return True
    
    def export_ui(self):
        """Export UI definition as JSON (all screens)"""
        # Save current screen first
        self._save_current_screen()
        
        ui_data = {
            "screens": {},
            "screen_order": self.screen_order.copy(),
            "current_screen": self.current_screen,
            "form": {"width": self.form_width, "height": self.form_height}
        }
        
        # Export all screens
        for screen_name, widgets_data in self.screens.items():
            ui_data["screens"][screen_name] = widgets_data
        
        # Also export current screen widgets for backwards compatibility
        ui_data["widgets"] = self.screens.get(self.current_screen, [])
        
        return ui_data
    
    def load_ui(self, ui_data):
        """Load UI from JSON definition (supports both old and new format)"""
        # Clear all screens
        for widget in self.widgets[:]:
            self._scene.removeItem(widget)
        self.widgets.clear()
        self.screens = {}
        self.screen_order = []
        
        # Load form size if present
        form_data = ui_data.get("form", {})
        if form_data:
            self.set_form_size(form_data.get("width", 400), form_data.get("height", 300))
        
        # Check if new multi-screen format
        if "screens" in ui_data:
            self.screens = {name: list(widgets) for name, widgets in ui_data["screens"].items()}
            self.screen_order = ui_data.get("screen_order", list(self.screens.keys()))
            self.current_screen = ui_data.get("current_screen", self.screen_order[0] if self.screen_order else "Main")
        else:
            # Old format - single screen
            self.screens = {"Screen 1": ui_data.get("widgets", [])}
            self.screen_order = ["Screen 1"]
            self.current_screen = "Screen 1"
        
        # Ensure we have at least one screen
        if not self.screens:
            self.screens = {"Screen 1": []}
            self.screen_order = ["Screen 1"]
            self.current_screen = "Screen 1"
        
        # Load the current screen
        self._load_screen(self.current_screen)
        
        # Update next_id based on all screens
        for widgets_data in self.screens.values():
            for wd in widgets_data:
                self.next_id = max(self.next_id, wd.get("id", 0) + 1)


class PropertyEditor(QWidget):
    """Property inspector for selected UI widget"""
    
    property_changed = pyqtSignal(str, object)  # property_name, new_value
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_widget = None
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        
        # Header
        self.header = QLabel("No Selection")
        self.header.setStyleSheet("font-weight: bold; color: #e0e0e0; padding: 8px;")
        layout.addWidget(self.header)
        
        # Scroll area for properties
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; }")
        
        self.props_widget = QWidget()
        self.props_layout = QFormLayout(self.props_widget)
        self.props_layout.setContentsMargins(8, 8, 8, 8)
        scroll.setWidget(self.props_widget)
        layout.addWidget(scroll)
        
        # Screen Size section (at top before widget properties)
        screen_group = QGroupBox("Preview Size")
        screen_layout = QVBoxLayout(screen_group)
        
        screen_row = QHBoxLayout()
        screen_row.addWidget(QLabel("Size:"))
        self.size_combo = QComboBox()
        self.size_combo.addItems([
            "400 x 300 (Default)",
            "640 x 480 (VGA)",
            "800 x 600 (SVGA)",
            "1024 x 768 (XGA)",
            "1280 x 720 (HD)",
            "1920 x 1080 (Full HD)",
            "Custom..."
        ])
        self.size_combo.currentTextChanged.connect(self._on_screen_size_changed)
        screen_row.addWidget(self.size_combo)
        screen_layout.addLayout(screen_row)
        
        layout.addWidget(screen_group)
        
        # Multi-Binding section
        bind_group = QGroupBox("Data Bindings")
        bind_layout = QVBoxLayout(bind_group)
        bind_layout.setSpacing(4)
        
        # Bindings list container
        self.bindings_container = QWidget()
        self.bindings_layout = QVBoxLayout(self.bindings_container)
        self.bindings_layout.setContentsMargins(0, 0, 0, 0)
        self.bindings_layout.setSpacing(4)
        bind_layout.addWidget(self.bindings_container)
        
        # Add binding button
        add_bind_row = QHBoxLayout()
        add_bind_row.addStretch()
        self.add_binding_btn = QPushButton("+ Add Binding")
        self.add_binding_btn.setEnabled(False)
        self.add_binding_btn.clicked.connect(self._add_binding)
        self.add_binding_btn.setStyleSheet("""
            QPushButton {
                background-color: #0e639c;
                color: white;
                border: none;
                border-radius: 3px;
                padding: 4px 12px;
                font-size: 11px;
            }
            QPushButton:hover { background-color: #1177bb; }
            QPushButton:disabled { background-color: #333; color: #666; }
        """)
        add_bind_row.addWidget(self.add_binding_btn)
        bind_layout.addLayout(add_bind_row)
        
        layout.addWidget(bind_group)
        layout.addStretch()
        
        # Store reference to main window (set later)
        self._main_window = None
        
        # Define bindable properties for each widget type
        self.BINDABLE_PROPERTIES = {
            'Button': ['text', 'visibility', 'enabled'],
            'Label': ['text', 'visibility', 'fontSize'],
            'Image': ['source', 'visibility', 'scaleX', 'scaleY', 'posX', 'posY'],
            'TextInput': ['text', 'visibility', 'placeholder', 'enabled'],
            'Checkbox': ['checked', 'visibility', 'text', 'enabled'],
            'Slider': ['value', 'visibility', 'min', 'max', 'enabled'],
            'ProgressBar': ['value', 'visibility', 'max'],
            'Dropdown': ['selectedIndex', 'visibility', 'enabled'],
            'Frame': ['visibility', 'backgroundColor'],
            'VContainer': ['visibility', 'backgroundColor'],
            'HContainer': ['visibility', 'backgroundColor'],
        }
        self.DEFAULT_BINDABLE = ['text', 'visibility']
        self._main_window = None
    
    def _on_screen_size_changed(self, text):
        """Handle screen size selection change"""
        if not self._main_window or not hasattr(self._main_window, 'ui_builder'):
            return
        
        canvas = self._main_window.ui_builder.canvas
        
        if text == "Custom...":
            # Show custom size dialog
            from PyQt6.QtWidgets import QInputDialog
            width, ok1 = QInputDialog.getInt(self, "Width", "Enter width:", 400, 100, 3840)
            if ok1:
                height, ok2 = QInputDialog.getInt(self, "Height", "Enter height:", 300, 100, 2160)
                if ok2:
                    canvas.set_form_size(width, height)
            return
        
        # Parse size from text
        sizes = {
            "400 x 300 (Default)": (400, 300),
            "640 x 480 (VGA)": (640, 480),
            "800 x 600 (SVGA)": (800, 600),
            "1024 x 768 (XGA)": (1024, 768),
            "1280 x 720 (HD)": (1280, 720),
            "1920 x 1080 (Full HD)": (1920, 1080),
        }
        if text in sizes:
            width, height = sizes[text]
            canvas.set_form_size(width, height)
    
    def set_main_window(self, main_window):
        """Set reference to main window for accessing graph variables"""
        self._main_window = main_window
    
    def sync_form_size(self):
        """Sync the size dropdown with the current canvas form size"""
        if not self._main_window or not hasattr(self._main_window, 'ui_builder'):
            return
        
        canvas = self._main_window.ui_builder.canvas
        w, h = canvas.form_width, canvas.form_height
        
        # Find matching preset
        sizes = {
            (400, 300): "400 x 300 (Default)",
            (640, 480): "640 x 480 (VGA)",
            (800, 600): "800 x 600 (SVGA)",
            (1024, 768): "1024 x 768 (XGA)",
            (1280, 720): "1280 x 720 (HD)",
            (1920, 1080): "1920 x 1080 (Full HD)",
        }
        
        # Block signals to avoid triggering callback
        self.size_combo.blockSignals(True)
        if (w, h) in sizes:
            idx = self.size_combo.findText(sizes[(w, h)])
            if idx >= 0:
                self.size_combo.setCurrentIndex(idx)
        else:
            # Custom size - don't change dropdown (leave as is)
            pass
        self.size_combo.blockSignals(False)
    
    def _get_graph_variables(self):
        """Get list of variable names from the graph"""
        variables = []
        if self._main_window and hasattr(self._main_window, 'canvas'):
            try:
                # First, get variables from the graph_variables panel (primary source)
                if hasattr(self._main_window.canvas, 'graph_variables'):
                    for var_name in self._main_window.canvas.graph_variables.keys():
                        if var_name and var_name not in variables:
                            variables.append(var_name)
                
                # Also look for SetVariable/GetVariable nodes as backup
                graph = self._main_window.canvas.export_graph()
                for node_data in graph.get('nodes', []):
                    template = node_data.get('template', '')
                    if template in ('SetVariable', 'GetVariable'):
                        # Get the variable name from values (not widget_values)
                        vals = node_data.get('values', {})
                        var_name = vals.get('name', '')
                        if var_name and var_name not in variables:
                            variables.append(var_name)
            except Exception as e:
                print(f"Error getting variables: {e}")
        return sorted(variables)
    
    def _add_binding(self):
        """Add a new binding to the current widget"""
        if not self.current_widget:
            return
        
        # Get bindable properties for this widget type
        widget_type = self.current_widget.widget_type
        bindable = self.BINDABLE_PROPERTIES.get(widget_type, self.DEFAULT_BINDABLE)
        
        # Initialize bindings list if needed
        if 'bindings' not in self.current_widget.properties:
            self.current_widget.properties['bindings'] = []
        
        # Add a new empty binding
        self.current_widget.properties['bindings'].append({
            'property': bindable[0] if bindable else 'text',
            'variable': ''
        })
        
        # Refresh the bindings UI
        self._refresh_bindings_ui()
    
    def _remove_binding(self, index):
        """Remove a binding at the given index"""
        if not self.current_widget:
            return
        
        bindings = self.current_widget.properties.get('bindings', [])
        if 0 <= index < len(bindings):
            bindings.pop(index)
            self._refresh_bindings_ui()
    
    def _update_binding(self, index, field, value):
        """Update a binding field"""
        if not self.current_widget:
            return
        
        bindings = self.current_widget.properties.get('bindings', [])
        if 0 <= index < len(bindings):
            bindings[index][field] = value
    
    def _refresh_bindings_ui(self):
        """Rebuild the bindings UI based on current widget's bindings"""
        # Clear existing binding rows
        while self.bindings_layout.count():
            item = self.bindings_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        if not self.current_widget:
            return
        
        # Get bindable properties for this widget type
        widget_type = self.current_widget.widget_type
        bindable = self.BINDABLE_PROPERTIES.get(widget_type, self.DEFAULT_BINDABLE)
        
        # Get available variables
        variables = self._get_graph_variables()
        
        # Get current bindings
        bindings = self.current_widget.properties.get('bindings', [])
        
        # Migrate old single binding to new format
        old_binding = self.current_widget.properties.get('binding')
        if old_binding and not bindings:
            bindings = [{'property': 'text', 'variable': old_binding}]
            self.current_widget.properties['bindings'] = bindings
            self.current_widget.properties.pop('binding', None)
        
        for i, binding in enumerate(bindings):
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(4)
            
            # Property selector
            prop_combo = QComboBox()
            prop_combo.addItems(bindable)
            prop_combo.setFixedWidth(80)
            current_prop = binding.get('property', bindable[0] if bindable else 'text')
            idx = prop_combo.findText(current_prop)
            if idx >= 0:
                prop_combo.setCurrentIndex(idx)
            prop_combo.currentTextChanged.connect(lambda val, idx=i: self._update_binding(idx, 'property', val))
            prop_combo.setStyleSheet("QComboBox { font-size: 11px; padding: 2px 4px; }")
            row_layout.addWidget(prop_combo)
            
            # Arrow label
            arrow = QLabel("→")
            arrow.setStyleSheet("color: #888; font-size: 12px;")
            row_layout.addWidget(arrow)
            
            # Variable selector
            var_combo = QComboBox()
            var_combo.setEditable(True)
            var_combo.addItems(variables)
            var_combo.setPlaceholderText("variable...")
            current_var = binding.get('variable', '')
            if current_var:
                idx = var_combo.findText(current_var)
                if idx >= 0:
                    var_combo.setCurrentIndex(idx)
                else:
                    var_combo.setCurrentText(current_var)
            var_combo.currentTextChanged.connect(lambda val, idx=i: self._update_binding(idx, 'variable', val))
            var_combo.setStyleSheet("QComboBox { font-size: 11px; padding: 2px 4px; }")
            row_layout.addWidget(var_combo)
            
            # Remove button
            remove_btn = QPushButton("✕")
            remove_btn.setFixedSize(20, 20)
            remove_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            remove_btn.clicked.connect(lambda checked, idx=i: self._remove_binding(idx))
            remove_btn.setStyleSheet("""
                QPushButton {
                    background: transparent;
                    color: #888;
                    border: none;
                    font-size: 11px;
                }
                QPushButton:hover { color: #f44; }
            """)
            row_layout.addWidget(remove_btn)
            
            self.bindings_layout.addWidget(row)
        
        # Show hint if no bindings
        if not bindings:
            hint = QLabel("No bindings. Click + to add.")
            hint.setStyleSheet("color: #666; font-size: 11px; font-style: italic;")
            self.bindings_layout.addWidget(hint)
    
    def set_widget(self, widget_item):
        """Update property editor for selected widget"""
        self.current_widget = widget_item
        
        # Clear old properties
        while self.props_layout.count():
            item = self.props_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        if not widget_item:
            self.header.setText("No Selection")
            self.add_binding_btn.setEnabled(False)
            self._refresh_bindings_ui()
            return
        
        self.header.setText(f"{widget_item.widget_type} (ID: {widget_item.widget_id})")
        self.add_binding_btn.setEnabled(True)
        
        # Refresh bindings UI
        self._refresh_bindings_ui()
        
        # Add property editors based on widget type
        props = widget_item.properties
        
        for key, value in props.items():
            if key in ('type', 'bindings', 'binding'):
                continue
            
            editor = self._create_editor(key, value)
            if editor:
                self.props_layout.addRow(key.title() + ":", editor)
    
    def _create_editor(self, prop_name, value):
        """Create appropriate editor widget for property type"""
        if isinstance(value, bool):
            cb = QCheckBox()
            cb.setChecked(value)
            cb.toggled.connect(lambda v: self._on_prop_changed(prop_name, v))
            return cb
        elif isinstance(value, int):
            spin = QSpinBox()
            spin.setRange(-9999, 9999)
            spin.setValue(value)
            spin.valueChanged.connect(lambda v: self._on_prop_changed(prop_name, v))
            return spin
        elif isinstance(value, float):
            spin = QDoubleSpinBox()
            spin.setRange(-9999, 9999)
            spin.setValue(value)
            spin.valueChanged.connect(lambda v: self._on_prop_changed(prop_name, v))
            return spin
        elif isinstance(value, str):
            # Check for image properties
            is_image = prop_name.lower() in ('backgroundimage', 'source', 'image')
            
            if is_image:
                return self._create_image_picker(prop_name, value)
            
            # Check for color properties or hex values
            is_color = ('color' in prop_name.lower() or 
                        (value.startswith('#') and len(value) in (7, 9)))
            
            if is_color:
                widget = QWidget()
                layout = QHBoxLayout(widget)
                layout.setContentsMargins(0, 0, 0, 0)
                layout.setSpacing(4)
                
                line_edit = QLineEdit(value)
                line_edit.textChanged.connect(lambda v: self._on_prop_changed(prop_name, v))
                
                btn = QPushButton()
                btn.setFixedSize(24, 24)
                btn.setStyleSheet(f"background-color: {value}; border: 1px solid #555;")
                
                def pick_color():
                    color = QColorDialog.getColor(QColor(value), self, "Pick Color")
                    if color.isValid():
                        hex_color = color.name()
                        line_edit.setText(hex_color)
                        btn.setStyleSheet(f"background-color: {hex_color}; border: 1px solid #555;")
                        self._on_prop_changed(prop_name, hex_color)
                
                btn.clicked.connect(pick_color)
                
                layout.addWidget(btn)
                layout.addWidget(line_edit)
                return widget
            else:
                edit = QLineEdit(value)
                edit.textChanged.connect(lambda v: self._on_prop_changed(prop_name, v))
                return edit
        elif isinstance(value, list):
            edit = QLineEdit(", ".join(str(v) for v in value))
            edit.setPlaceholderText("Comma-separated values")
            edit.textChanged.connect(
                lambda v: self._on_prop_changed(prop_name, [x.strip() for x in v.split(",")])
            )
            return edit
        return None
    
    def _create_image_picker(self, prop_name, current_path):
        """Create an image picker widget with browse button and clear"""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        
        line_edit = QLineEdit(current_path)
        line_edit.setPlaceholderText("Path to image...")
        line_edit.textChanged.connect(lambda v: self._on_image_changed(prop_name, v, preview_label))
        
        # Preview thumbnail
        preview_label = QLabel()
        preview_label.setFixedSize(24, 24)
        preview_label.setStyleSheet("border: 1px solid #555; background: #2d2d30;")
        if current_path:
            self._update_image_preview(preview_label, current_path)
        
        # Browse button
        browse_btn = QPushButton("...")
        browse_btn.setFixedWidth(28)
        browse_btn.setToolTip("Browse for image")
        
        def browse_image():
            file_path, _ = QFileDialog.getOpenFileName(
                self, "Select Image", "",
                "Images (*.png *.jpg *.jpeg *.gif *.bmp *.svg);;All Files (*)"
            )
            if file_path:
                line_edit.setText(file_path)
        
        browse_btn.clicked.connect(browse_image)
        
        # Clear button
        clear_btn = QPushButton("✕")
        clear_btn.setFixedWidth(24)
        clear_btn.setToolTip("Clear image")
        clear_btn.clicked.connect(lambda: line_edit.setText(""))
        
        layout.addWidget(preview_label)
        layout.addWidget(line_edit)
        layout.addWidget(browse_btn)
        layout.addWidget(clear_btn)
        
        return widget
    
    def _on_image_changed(self, prop_name, path, preview_label):
        """Handle image path change"""
        self._on_prop_changed(prop_name, path)
        self._update_image_preview(preview_label, path)
        # Update the widget preview if possible
        if self.current_widget and hasattr(self.current_widget, '_refresh_preview'):
            self.current_widget._refresh_preview()
    
    def _update_image_preview(self, label, path):
        """Update image preview thumbnail"""
        from PyQt6.QtGui import QPixmap
        if path and Path(path).exists():
            pixmap = QPixmap(path)
            if not pixmap.isNull():
                label.setPixmap(pixmap.scaled(24, 24, Qt.AspectRatioMode.KeepAspectRatio, 
                                              Qt.TransformationMode.SmoothTransformation))
                return
        label.clear()
        label.setStyleSheet("border: 1px solid #555; background: #2d2d30;")
    
    def _on_prop_changed(self, prop_name, value):
        if self.current_widget:
            self.current_widget.properties[prop_name] = value
            self.property_changed.emit(prop_name, value)


class ScreenListWidget(QWidget):
    """Screen/Page manager for UI Builder - allows creating and switching between screens"""
    
    screen_changed = pyqtSignal(str)  # Emitted when screen is selected
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.canvas = None  # Set by UIBuilderWidget
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        
        # Header
        header = QLabel("Screens")
        header.setStyleSheet("font-weight: bold; color: #e0e0e0; padding: 4px;")
        layout.addWidget(header)
        
        # Screen list
        self.screen_list = QListWidget()
        self.screen_list.setStyleSheet("""
            QListWidget {
                background-color: #2d2d30;
                border: 1px solid #3e3e42;
                border-radius: 4px;
            }
            QListWidget::item {
                color: #e0e0e0;
                padding: 6px;
                border-bottom: 1px solid #3e3e42;
            }
            QListWidget::item:selected {
                background-color: #0078d4;
            }
            QListWidget::item:hover {
                background-color: #3e3e42;
            }
        """)
        self.screen_list.itemClicked.connect(self._on_screen_clicked)
        self.screen_list.itemDoubleClicked.connect(self._on_double_click_rename)
        self.screen_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.screen_list.customContextMenuRequested.connect(self._show_context_menu)
        layout.addWidget(self.screen_list)
        
        # Buttons
        btn_layout = QHBoxLayout()
        
        add_btn = QPushButton("+")
        add_btn.setFixedWidth(30)
        add_btn.setToolTip("Add new screen")
        add_btn.clicked.connect(self._add_screen)
        btn_layout.addWidget(add_btn)
        
        up_btn = QPushButton("▲")
        up_btn.setFixedWidth(30)
        up_btn.setToolTip("Move screen up")
        up_btn.clicked.connect(lambda: self._move_screen(-1))
        btn_layout.addWidget(up_btn)
        
        down_btn = QPushButton("▼")
        down_btn.setFixedWidth(30)
        down_btn.setToolTip("Move screen down")
        down_btn.clicked.connect(lambda: self._move_screen(1))
        btn_layout.addWidget(down_btn)
        
        delete_btn = QPushButton("🗑")
        delete_btn.setFixedWidth(30)
        delete_btn.setToolTip("Delete selected screen")
        delete_btn.clicked.connect(self._delete_screen)
        btn_layout.addWidget(delete_btn)
        
        btn_layout.addStretch()
        layout.addLayout(btn_layout)
    
    def set_canvas(self, canvas):
        """Set the canvas reference and refresh the list"""
        self.canvas = canvas
        self.refresh_list()
    
    def refresh_list(self):
        """Refresh the screen list from canvas data"""
        if not self.canvas:
            return
        
        self.screen_list.clear()
        for screen_name in self.canvas.screen_order:
            item = QListWidgetItem(screen_name)
            self.screen_list.addItem(item)
            if screen_name == self.canvas.current_screen:
                item.setSelected(True)
                self.screen_list.setCurrentItem(item)
    
    def _on_screen_clicked(self, item):
        """Handle screen selection"""
        if not self.canvas:
            return
        screen_name = item.text()
        if screen_name != self.canvas.current_screen:
            self.canvas.switch_screen(screen_name)
            self.screen_changed.emit(screen_name)
    
    def _add_screen(self):
        """Add a new screen with auto-generated name"""
        if not self.canvas:
            return
        
        # Auto-generate name: Screen 2, Screen 3, etc.
        i = 1
        while f"Screen {i}" in self.canvas.screens:
            i += 1
        name = f"Screen {i}"
        
        self.canvas.add_screen(name)
        self.refresh_list()
        self.screen_changed.emit(name)
    
    def _on_double_click_rename(self, item):
        """Handle double-click to rename screen"""
        if not self.canvas or not item:
            return
        
        old_name = item.text()
        new_name, ok = QInputDialog.getText(self, "Rename Screen", "New name:", text=old_name)
        if ok and new_name.strip() and new_name != old_name:
            new_name = new_name.strip()
            if new_name in self.canvas.screens:
                QMessageBox.warning(self, "Error", f"Screen '{new_name}' already exists")
                return
            self.canvas.rename_screen(old_name, new_name)
            self.refresh_list()
    
    def _rename_screen(self):
        """Rename selected screen (called from context menu)"""
        current_item = self.screen_list.currentItem()
        if current_item:
            self._on_double_click_rename(current_item)
    
    def _move_screen(self, direction):
        """Move screen up or down"""
        if not self.canvas:
            return
        
        current_item = self.screen_list.currentItem()
        if not current_item:
            return
        
        screen_name = current_item.text()
        if self.canvas.move_screen(screen_name, direction):
            self.refresh_list()
    
    def _delete_screen(self):
        """Delete selected screen"""
        if not self.canvas:
            return
        
        current_item = self.screen_list.currentItem()
        if not current_item:
            return
        
        screen_name = current_item.text()
        
        if len(self.canvas.screens) <= 1:
            QMessageBox.warning(self, "Error", "Cannot delete the last screen")
            return
        
        reply = QMessageBox.question(
            self, "Delete Screen",
            f"Delete screen '{screen_name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.canvas.delete_screen(screen_name)
            self.refresh_list()
            self.screen_changed.emit(self.canvas.current_screen)
    
    def _show_context_menu(self, pos):
        """Show context menu for screen list"""
        item = self.screen_list.itemAt(pos)
        if not item:
            return
        
        menu = QMenu(self)
        rename_action = menu.addAction("Rename")
        menu.addSeparator()
        delete_action = menu.addAction("Delete")
        
        action = menu.exec(self.screen_list.mapToGlobal(pos))
        if action == rename_action:
            self._rename_screen()
        elif action == delete_action:
            self._delete_screen()


class WidgetListWidget(QWidget):
    """Widget hierarchy list - shows all widgets on current screen with selection"""
    
    widget_selected = pyqtSignal(object)  # Emits UIWidgetItem when selected
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.canvas = None
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        
        # Header with refresh button
        header_row = QHBoxLayout()
        header = QLabel("Widgets")
        header.setStyleSheet("font-weight: bold; color: #e0e0e0; padding: 4px;")
        header_row.addWidget(header)
        
        refresh_btn = QPushButton("↻")
        refresh_btn.setFixedWidth(28)
        refresh_btn.setToolTip("Refresh widget list")
        refresh_btn.clicked.connect(self.refresh_list)
        header_row.addWidget(refresh_btn)
        
        layout.addLayout(header_row)
        
        # Tree widget for hierarchy
        self.widget_tree = QTreeWidget()
        self.widget_tree.setHeaderLabels(["Widget", "Type", "ID"])
        self.widget_tree.setColumnWidth(0, 120)
        self.widget_tree.setColumnWidth(1, 60)
        self.widget_tree.setColumnWidth(2, 40)
        self.widget_tree.setStyleSheet("""
            QTreeWidget {
                background-color: #252526;
                color: #e0e0e0;
                border: 1px solid #3e3e42;
            }
            QTreeWidget::item:selected {
                background-color: #0078d4;
            }
            QTreeWidget::item:hover {
                background-color: #3e3e42;
            }
        """)
        self.widget_tree.itemClicked.connect(self._on_item_clicked)
        self.widget_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.widget_tree.customContextMenuRequested.connect(self._show_context_menu)
        layout.addWidget(self.widget_tree)
    
    def set_canvas(self, canvas):
        """Set the UI canvas to monitor"""
        self.canvas = canvas
        if canvas:
            # Connect to canvas signals to auto-refresh
            if hasattr(canvas, 'widget_added'):
                canvas.widget_added.connect(self.refresh_list)
            if hasattr(canvas, 'widget_removed'):
                canvas.widget_removed.connect(self.refresh_list)
        self.refresh_list()
    
    def refresh_list(self):
        """Refresh the widget list from the canvas"""
        self.widget_tree.clear()
        
        if not self.canvas:
            return
        
        # Get widgets from current screen
        screen_widgets = self.canvas.screens.get(self.canvas.current_screen, [])
        
        # Also get live items from scene
        widget_items = {}
        for item in self.canvas.scene().items():
            if isinstance(item, UIWidgetItem):
                widget_items[item.widget_id] = item
        
        # Build tree - first pass: create all items
        tree_items = {}
        for item in widget_items.values():
            icon = self._get_icon(item.widget_type)
            name = item.properties.get('text', item.properties.get('buttonId', f'Widget'))
            if not name:
                name = item.widget_type
            
            tree_item = QTreeWidgetItem([f"{icon} {name}", item.widget_type, str(item.widget_id)])
            tree_item.setData(0, Qt.ItemDataRole.UserRole, item)
            tree_items[item.widget_id] = tree_item
        
        # Second pass: build hierarchy
        for wid, tree_item in tree_items.items():
            widget = widget_items.get(wid)
            if widget and hasattr(widget, 'parent_id') and widget.parent_id:
                parent_tree_item = tree_items.get(widget.parent_id)
                if parent_tree_item:
                    parent_tree_item.addChild(tree_item)
                    continue
            # Top-level widget
            self.widget_tree.addTopLevelItem(tree_item)
        
        self.widget_tree.expandAll()
    
    def _get_icon(self, widget_type):
        icons = {
            "VContainer": "📦", "HContainer": "📦", "Frame": "🔲",
            "Button": "🔘", "TextInput": "📝", "Slider": "🎚️",
            "Checkbox": "☑️", "Dropdown": "📋",
            "Label": "🏷️", "Image": "🖼️", "ProgressBar": "📊"
        }
        return icons.get(widget_type, "📄")
    
    def _on_item_clicked(self, item, column):
        """Handle click on widget in list - select it on canvas"""
        widget_item = item.data(0, Qt.ItemDataRole.UserRole)
        if widget_item and self.canvas:
            # Clear other selections
            self.canvas.scene().clearSelection()
            # Select this widget
            widget_item.setSelected(True)
            # Emit signal
            self.widget_selected.emit(widget_item)
    
    def _show_context_menu(self, pos):
        """Show context menu for widget list"""
        item = self.widget_tree.itemAt(pos)
        if not item:
            return
        
        widget_item = item.data(0, Qt.ItemDataRole.UserRole)
        if not widget_item:
            return
        
        menu = QMenu(self)
        select_action = menu.addAction("Select")
        menu.addSeparator()
        bring_front_action = menu.addAction("Bring to Front")
        send_back_action = menu.addAction("Send to Back")
        menu.addSeparator()
        delete_action = menu.addAction("Delete")
        
        action = menu.exec(self.widget_tree.mapToGlobal(pos))
        if action == select_action:
            self._on_item_clicked(item, 0)
        elif action == bring_front_action:
            widget_item.setZValue(widget_item.zValue() + 1)
        elif action == send_back_action:
            widget_item.setZValue(widget_item.zValue() - 1)
        elif action == delete_action:
            if self.canvas:
                self.canvas.scene().removeItem(widget_item)
                self.refresh_list()


class WidgetPaletteWidget(QWidget):
    """Widget Palette for dragging widgets to canvas"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
        
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        
        header = QLabel("Widget Palette")
        header.setStyleSheet("font-weight: bold; color: #e0e0e0; padding: 4px;")
        layout.addWidget(header)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; }")
        
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setSpacing(4)
        
        for category, widgets in WIDGET_PALETTE.items():
            cat_label = QLabel(category)
            cat_label.setStyleSheet("color: #888; font-size: 10px; padding-top: 8px;")
            content_layout.addWidget(cat_label)
            
            for name, props in widgets.items():
                item = WidgetPaletteItem(name, props)
                content_layout.addWidget(item)
        
        content_layout.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll)


class UIBuilderWidget(QWidget):
    """Main UI Builder widget that goes in the UI tab"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
    
    def setup_ui(self):
        # Canvas only - panels moved to docks
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # === Center: Canvas ===
        self.canvas = UICanvas()
        layout.addWidget(self.canvas)
        
        # Toolbar at bottom
        toolbar = QHBoxLayout()
        
        save_btn = QPushButton("Save UI")
        save_btn.clicked.connect(self.save_ui)
        toolbar.addWidget(save_btn)
        
        load_btn = QPushButton("Load UI")
        load_btn.clicked.connect(self.load_ui)
        toolbar.addWidget(load_btn)
        
        toolbar.addStretch()
        
        export_code_btn = QPushButton("Export to Code")
        export_code_btn.clicked.connect(self.export_to_code)
        toolbar.addWidget(export_code_btn)
        
        layout.addLayout(toolbar)
        
        # Main window reference (set later)
        self._main_window = None
    
    def set_main_window(self, main_window):
        """Set reference to main window for accessing graph variables"""
        self._main_window = main_window
    
    def save_ui(self):
        """Save UI definition to JSON file"""
        path, _ = QFileDialog.getSaveFileName(
            self, "Save UI", "", "UI Files (*.ui.json)"
        )
        if path:
            try:
                ui_data = self.canvas.export_ui()
                with open(path, 'w') as f:
                    json.dump(ui_data, f, indent=2)
                QMessageBox.information(self, "Saved", f"UI saved to:\n{path}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save:\n{str(e)}")
    
    def load_ui(self):
        """Load UI definition from JSON file"""
        path, _ = QFileDialog.getOpenFileName(
            self, "Load UI", "", "UI Files (*.ui.json);;All Files (*)"
        )
        if path:
            try:
                with open(path, 'r') as f:
                    ui_data = json.load(f)
                self.canvas.load_ui(ui_data)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to load:\n{str(e)}")
    
    def export_to_code(self):
        """Generate PyQt6 code from UI definition"""
        ui_data = self.canvas.export_ui()
        
        code_lines = [
            '"""Generated UI Code - NodeCanvas"""',
            'from PyQt6.QtWidgets import *',
            'from PyQt6.QtCore import Qt',
            '',
            'class GeneratedUI(QWidget):',
            '    def __init__(self, parent=None):',
            '        super().__init__(parent)',
            '        self.setup_ui()',
            '',
            '    def setup_ui(self):',
            '        self.setWindowTitle("Generated UI")',
            '        self.resize(400, 300)',
            '        ',
        ]
        
        for widget in ui_data.get('widgets', []):
            props = widget.get('properties', {})
            wtype = props.get('type', 'label')
            wid = widget.get('id', 0)
            pos = widget.get('pos', [0, 0])
            
            if wtype == 'button':
                code_lines.append(f'        self.widget_{wid} = QPushButton("{props.get("text", "Button")}", self)')
            elif wtype == 'label':
                code_lines.append(f'        self.widget_{wid} = QLabel("{props.get("text", "Label")}", self)')
            elif wtype == 'input':
                code_lines.append(f'        self.widget_{wid} = QLineEdit(self)')
                code_lines.append(f'        self.widget_{wid}.setPlaceholderText("{props.get("placeholder", "")}")')
            elif wtype == 'checkbox':
                code_lines.append(f'        self.widget_{wid} = QCheckBox("{props.get("text", "Checkbox")}", self)')
            elif wtype == 'slider':
                code_lines.append(f'        self.widget_{wid} = QSlider(Qt.Orientation.Horizontal, self)')
                code_lines.append(f'        self.widget_{wid}.setRange({props.get("min", 0)}, {props.get("max", 100)})')
            elif wtype == 'dropdown':
                code_lines.append(f'        self.widget_{wid} = QComboBox(self)')
                items = props.get('items', [])
                code_lines.append(f'        self.widget_{wid}.addItems({items})')
            else:
                code_lines.append(f'        self.widget_{wid} = QLabel("Unknown", self)')
            
            # Position
            w = props.get('width', 100)
            h = props.get('height', 30)
            code_lines.append(f'        self.widget_{wid}.setGeometry({int(pos[0]+200)}, {int(pos[1]+150)}, {w}, {h})')
            code_lines.append('')
        
        code_lines.extend([
            '',
            'if __name__ == "__main__":',
            '    import sys',
            '    app = QApplication(sys.argv)',
            '    window = GeneratedUI()',
            '    window.show()',
            '    sys.exit(app.exec())',
        ])
        
        code = '\n'.join(code_lines)
        
        # Show in dialog
        from PyQt6.QtWidgets import QDialog, QTextEdit
        dialog = QDialog(self)
        dialog.setWindowTitle("Generated Code")
        dialog.resize(600, 500)
        layout = QVBoxLayout(dialog)
        
        text = QTextEdit()
        text.setPlainText(code)
        text.setFont(QFont("Consolas", 10))
        text.setStyleSheet("background-color: #1e1e1e; color: #d4d4d4;")
        layout.addWidget(text)
        
        btns = QHBoxLayout()
        copy_btn = QPushButton("Copy")
        copy_btn.clicked.connect(lambda: QApplication.clipboard().setText(code))
        btns.addWidget(copy_btn)
        
        save_btn = QPushButton("Save")
        def save():
            path, _ = QFileDialog.getSaveFileName(dialog, "Save", "", "Python (*.py)")
            if path:
                with open(path, 'w') as f:
                    f.write(code)
        save_btn.clicked.connect(save)
        btns.addWidget(save_btn)
        
        btns.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dialog.accept)
        btns.addWidget(close_btn)
        layout.addLayout(btns)
        
        dialog.exec()
    
    def preview_ui(self):
        """Show live preview of the UI"""
        ui_data = self.canvas.export_ui()
        
        preview = QDialog(self)
        preview.setWindowTitle("UI Preview")
        preview.resize(400, 300)
        
        for widget in ui_data.get('widgets', []):
            props = widget.get('properties', {})
            wtype = props.get('type', 'label')
            pos = widget.get('pos', [0, 0])
            
            w = None
            if wtype == 'button':
                w = QPushButton(props.get('text', 'Button'), preview)
            elif wtype == 'label':
                w = QLabel(props.get('text', 'Label'), preview)
            elif wtype == 'input':
                w = QLineEdit(preview)
                w.setPlaceholderText(props.get('placeholder', ''))
            elif wtype == 'checkbox':
                w = QCheckBox(props.get('text', 'Checkbox'), preview)
            elif wtype == 'slider':
                w = QSlider(Qt.Orientation.Horizontal, preview)
                w.setRange(props.get('min', 0), props.get('max', 100))
                w.setValue(props.get('value', 50))
            elif wtype == 'dropdown':
                w = QComboBox(preview)
                w.addItems(props.get('items', ['Option 1']))
            
            if w:
                w.setGeometry(
                    int(pos[0] + 200),
                    int(pos[1] + 150),
                    props.get('width', 100),
                    props.get('height', 30)
                )
        
        preview.exec()
