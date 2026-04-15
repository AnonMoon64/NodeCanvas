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
from PyQt6.QtGui import QPainterPath, QPen, QBrush, QColor, QPainter, QFont, QAction, QLinearGradient, QPolygonF
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



class ConnectionItem(QGraphicsPathItem):
    def __init__(self, from_node, to_node, canvas_view, pin_type=None):
        super().__init__()
        self.from_node = from_node
        self.to_node = to_node
        self.canvas = canvas_view
        self._removed = False
        self.from_pin = None
        self.to_pin = None
        self.pin_type = pin_type
        
        # Style based on pin type - exec connections are white and thicker
        if pin_type == 'exec':
            pen = QPen(QColor(255, 255, 255), 4)
        else:
            pen = QPen(QColor(120, 160, 255), 3)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        self.setPen(pen)
        self.setZValue(-1)
        
        # Add delete button (small X marker on the line)
        self.delete_marker = QGraphicsEllipseItem(-6, -6, 12, 12, self)
        self.delete_marker.setBrush(QBrush(QColor(40, 45, 55, 200)))
        self.delete_marker.setPen(QPen(QColor(80, 120, 190), 1))
        self.delete_marker.setZValue(5)
        self.delete_marker.setCursor(Qt.CursorShape.PointingHandCursor)
        
        # Draw X using lines
        from PyQt6.QtWidgets import QGraphicsLineItem
        x_line1 = QGraphicsLineItem(-3, -3, 3, 3, self.delete_marker)
        x_line1.setPen(QPen(QColor(150, 160, 180), 1.5))
        x_line2 = QGraphicsLineItem(-3, 3, 3, -3, self.delete_marker)
        x_line2.setPen(QPen(QColor(150, 160, 180), 1.5))

    def _update_style_from_pin(self):
        """Update connection style based on pin type (exec vs data)"""
        if not self.from_pin or not self.from_node:
            return
        # Get the output type from from_node
        pin_type = None
        if hasattr(self.from_node, 'outputs') and isinstance(self.from_node.outputs, dict):
            out_def = self.from_node.outputs.get(self.from_pin)
            if isinstance(out_def, str):
                pin_type = out_def
            elif isinstance(out_def, dict):
                pin_type = out_def.get('type', 'any')
        
        # Update pen based on type
        if pin_type == 'exec':
            pen = QPen(QColor(255, 255, 255), 4)
        else:
            pen = QPen(QColor(120, 160, 255), 3)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        self.setPen(pen)

    def add_to_scene(self, scene):
        self._update_style_from_pin()  # Apply exec/data style before adding
        # Add to scene first so pin scene-geometry is available immediately.
        scene.addItem(self)

        # Try an immediate path update; schedule a deferred update to
        # ensure geometry is correct after Qt finishes pending layout.
        try:
            self.update_path()
        except Exception:
            traceback.print_exc()

        # Ensure the view repaints. If a canvas reference exists, ask it
        # to refresh connections for the endpoints and update the viewport.
        try:
            if self.canvas:
                try:
                    if hasattr(self.canvas, 'update_connections_for_node'):
                        try:
                            self.canvas.update_connections_for_node(self.from_node)
                        except Exception:
                            pass
                        try:
                            self.canvas.update_connections_for_node(self.to_node)
                        except Exception:
                            pass
                except Exception:
                    pass
                try:
                    self.canvas.viewport().update()
                except Exception:
                    pass
        except Exception:
            pass

        try:
            QTimer.singleShot(0, self.update_path)
        except Exception:
            pass

    def _pin_center(self, node, pin_name, is_output):
        if node is None:
            return None
        # if the node has already been removed from the scene, we cannot anchor
        try:
            if not node.scene():
                return None
        except Exception:
            return None
        pin_dict = node.output_pins if is_output else node.input_pins
        pin_item = None
        if pin_name and pin_dict:
            pin_item = pin_dict.get(pin_name)
        
        if pin_item:
            # Use mapToScene with the center of the local bounding rect.
            # This is more robust than sceneBoundingRect() when items are newly 
            # added or the scene index hasn't updated yet.
            try:
                return pin_item.mapToScene(pin_item.boundingRect().center())
            except Exception:
                pass

        # if no explicit pin, only use a fallback when node is alive in scene
        fallback_x = 126 if is_output else -126
        try:
            return node.scenePos() + QPointF(fallback_x, 0)
        except Exception:
            return None

    def update_path(self):
        if self._removed:
            return
        # if either node endpoint was deleted or cleared, remove the connection
        if not self.from_node or not self.to_node:
            try:
                if self.scene():
                    self.scene().removeItem(self)
            except Exception:
                pass
            return

        try:
            start = self._pin_center(self.from_node, self.from_pin, True)
            end = self._pin_center(self.to_node, self.to_pin, False)
        except Exception:
            print(f"WARNING: update_path pin center calculation failed for conn id={getattr(self,'id',None)}")
            traceback.print_exc()
            start = None
            end = None
        # if either endpoint is missing (node removed) drop the connection safely
        if start is None or end is None:
            try:
                print(f"DEBUG: connection endpoint missing, removing connection id={getattr(self,'id',None)} from_scene={bool(self.scene())}")
                if self.scene():
                    self.scene().removeItem(self)
            except Exception:
                print("WARNING: failed to remove connection from scene in update_path")
                traceback.print_exc()
            return
        path = QPainterPath()
        path.moveTo(start)
        
        # Improved Bezier calculation with horizontal tangents
        dx = end.x() - start.x()
        dy = end.y() - start.y()
        
        # Adaptive curvature: use a fixed control point distance, or proportional to distance
        # Ensuring at least some horizontal extension before curving
        ctrl_dist = max(abs(dx) * 0.5, 50)
        
        # If moving backwards (right to left), increase loop size
        if dx < 0:
            ctrl_dist = max(abs(dx) * 0.5, 150)
            
        c1 = start + QPointF(ctrl_dist, 0)
        c2 = end - QPointF(ctrl_dist, 0)
        
        path.cubicTo(c1, c2, end)
        try:
            # Inform Qt that the item's geometry is about to change so the
            # scene can update its spatial index and repaint correctly.
            try:
                self.prepareGeometryChange()
            except Exception:
                pass
            self.setPath(path)
        except Exception:
            traceback.print_exc()
        # Force an immediate update of this item and the scene so the
        # freshly-created connection is visible without moving nodes.
        try:
            self.update()
            if self.scene():
                try:
                    self.scene().update()
                except Exception:
                    pass
            if self.canvas:
                try:
                    self.canvas.viewport().update()
                except Exception:
                    pass
        except Exception:
            pass
        
        # Position delete marker at midpoint of connection
        if hasattr(self, 'delete_marker'):
            # compute midpoint between start and end
            try:
                mid = QPointF((start.x() + end.x()) / 2.0, (start.y() + end.y()) / 2.0)
                self.delete_marker.setPos(mid)
            except Exception:
                # Fallback: place marker near end
                try:
                    self.delete_marker.setPos(end)
                except Exception:
                    pass

    def mousePressEvent(self, event):
        """Handle click on delete marker"""
        if hasattr(self, 'delete_marker'):
            # Check if click is on the delete marker
            marker_rect = self.delete_marker.sceneBoundingRect()
            if marker_rect.contains(event.scenePos()):
                self.remove()
                event.accept()
                return
        super().mousePressEvent(event)

    def remove(self):
        if self._removed:
            return
        self._removed = True
        try:
            print(f"DEBUG: ConnectionItem.remove() called id={getattr(self,'id',None)} scene={bool(self.scene())}")
            if self.scene():
                try:
                    self.scene().removeItem(self)
                except Exception:
                    print("WARNING: scene.removeItem failed for connection")
                    traceback.print_exc()
        except Exception:
            print("WARNING: ConnectionItem.remove() encountered error while checking scene")
            traceback.print_exc()
        # clear refs to avoid any lingering pointer use
        self.from_node = None
        self.to_node = None
        self.from_pin = None
        self.to_pin = None
        # remove self from canvas connections list if present
        try:
            if self.canvas and hasattr(self.canvas, "connections") and self in self.canvas.connections:
                self.canvas.connections.remove(self)
        except Exception:
            pass


