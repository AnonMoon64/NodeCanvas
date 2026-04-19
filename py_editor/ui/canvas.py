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
from PyQt6.QtGui import QPainterPath, QPen, QBrush, QColor, QPainter, QFont, QAction, QLinearGradient, QPolygonF, QCursor
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



from py_editor.ui.node_item import NodeItem
from py_editor.ui.composite_pins import CompositePinRow, CompositePinSection
from py_editor.ui.connection_item import ConnectionItem
from py_editor.ui.canvas_graph_io import GraphIOMixin
from py_editor.ui.canvas_clipboard import ClipboardMixin
from py_editor.ui.canvas_nodes import NodesMixin
from py_editor.ui.canvas_removal import RemovalMixin
from py_editor.ui.canvas_connections import ConnectionsMixin
from py_editor.ui.canvas_composite import CompositeMixin
from py_editor.ui.canvas_factories import FactoriesMixin
from py_editor.ui.canvas_context_menu import ContextMenuMixin

class LogicEditor(GraphIOMixin, ClipboardMixin, NodesMixin, RemovalMixin,
                  ConnectionsMixin, CompositeMixin, FactoriesMixin,
                  ContextMenuMixin, QGraphicsView):
    """Main node graph editor view (formerly CanvasView)"""
    # Signal emitted when any value widget changes
    value_changed = pyqtSignal()
    # Signal emitted when graph structure changes (nodes added/removed)
    graph_changed = pyqtSignal()
    
    def __init__(self, parent=None, is_subcanvas=False, host_template=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setRenderHints(self.renderHints() | QPainter.RenderHint.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)  # Enable rubber band selection
        self.setViewportUpdateMode(
            QGraphicsView.ViewportUpdateMode.FullViewportUpdate
        )
        # Disable background caching to prevent visual artifacts/ghosting during movement
        self.setCacheMode(QGraphicsView.CacheModeFlag.CacheNone)
        
        # Set a very large scene rect for effectively infinite canvas
        self.setSceneRect(-100000, -100000, 200000, 200000)
        self.centerOn(0, 0)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        
        # Panning state
        self._is_panning = False
        self._pan_start_pos = None
        self._is_connecting = False  # Track if we're drawing a connection
        self.nodes = []
        self.connections = []
        # hold references to recently removed nodes to avoid immediate GC
        self._recently_removed = []
        self.next_id = 1
        self.pending_line = None
        self.pending_from = None
        self.graph_variables = {}  # Graph-level variables {name: {type, value}}
        # Context menu is handled manually in mouseReleaseEvent for right-clicks
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        
        # Enable drag and drop for variables
        self.setAcceptDrops(True)
        # composite editing mode flags
        self.is_subcanvas = bool(is_subcanvas)
        # Simulation State
        from py_editor.core.simulation_controller import SimulationController
        from py_editor.core.node_templates import get_all_templates
        self.sim = SimulationController(self)
        self._templates_cache = get_all_templates()
        
        # clipboard for copy/paste
        self.clipboard_data = None
        
        # Undo/Redo system
        self.undo_stack = []
        self.redo_stack = []
        self.max_undo_stack = 50  # Limit undo history
        self._is_undoing = False  # Flag to prevent recording during undo/redo
        
        # Zoom settings
        self.zoom_level = 1.0
        self.min_zoom = 0.1
        self.max_zoom = 3.0
        
        # Coordinate display label
        self.coord_label = QLabel(self)
        self.coord_label.setStyleSheet("""
            QLabel {
                background-color: rgba(30, 30, 30, 200);
                color: #aaa;
                padding: 4px 8px;
                border-radius: 3px;
                font-size: 10px;
                font-family: monospace;
            }
        """)
        self.coord_label.setText("X: 0, Y: 0 | Zoom: 100%")
        self.coord_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.coord_label.setFixedHeight(24)
        self._update_coord_label_position()
        
        # Enable mouse tracking for coordinate updates
        self.setMouseTracking(True)

    def run_graph(self):
        """Execute the logic graph exactly once and show result popup."""
        from PyQt6.QtWidgets import QMessageBox
        data = self.export_graph()
        results = self.sim.run_once(data, self._templates_cache, self.graph_variables)
        
        if results:
            ret_val = results.get('return', 'None')
            prints = results.get('prints', [])
            msg = f"<b>Return Value:</b> {ret_val}<br><br>"
            if prints:
                msg += "<b>Prints:</b><br>" + "<br>".join([f"• {p}" for p in prints])
            else:
                msg += "<i>No prints captured.</i>"
            
            QMessageBox.information(self, "Logic Execution Results", msg)
        print("[CANVAS] One-shot logic execution complete.")

    def step_graph(self):
        """Single-step the logic execution"""
        if not self.sim.is_running:
            data = self.export_graph()
            self.sim.start(data, self._templates_cache, self.graph_variables)
            self.sim.pause(True)
        
        self.sim.step()
        print("Stepped logic.")

    def keyPressEvent(self, event):
        """Handle keyboard shortcuts"""
        # Escape key cancels pending connection
        if event.key() == Qt.Key.Key_Escape:
            if self.pending_from:
                if self.pending_line:
                    try:
                        self._scene.removeItem(self.pending_line)
                    except Exception:
                        pass
                self.pending_line = None
                self.pending_from = None
                self._is_connecting = False
                self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
                event.accept()
                return
        
        # Delete key removes selected nodes
        if event.key() == Qt.Key.Key_Delete or event.key() == Qt.Key.Key_Backspace:
            focus_item = self.scene().focusItem()
            if focus_item and hasattr(focus_item, 'widget'):
                super().keyPressEvent(event)
                return
            self.delete_selected()
            event.accept()
            return
        
        if event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            if event.key() == Qt.Key.Key_C:
                self.copy_selected()
                event.accept()
                return
            elif event.key() == Qt.Key.Key_V:
                self.paste()
                event.accept()
                return
            elif event.key() == Qt.Key.Key_X:
                self.cut_selected()
                event.accept()
                return
            elif event.key() == Qt.Key.Key_Z:
                self.undo()
                event.accept()
                return
            elif event.key() == Qt.Key.Key_Y:
                self.redo()
                event.accept()
                return
            elif event.key() == Qt.Key.Key_D:
                self.duplicate_selected()
                event.accept()
                return
        
        if event.key() == Qt.Key.Key_C and event.modifiers() == Qt.NoModifier:
            self.add_comment_box()
            event.accept()
            return
        
        super().keyPressEvent(event)
    
    # Clipboard/undo/redo moved to ClipboardMixin (canvas_clipboard.py)

    def _dispatch_context_menu(self, point):
        try:
            self.on_context_menu(point)
        except Exception:
            traceback.print_exc()

    def drawBackground(self, painter, rect):
        painter.fillRect(rect, QColor(18, 18, 20))
        
        # Calculate grid spacing based on zoom level (LOD)
        # Base spacing is 24
        scale = self.transform().m11()
        base_spacing = 24
        
        # Determine step based on scale
        step = 1
        if scale < 0.5:
            step = 2  # Every 2nd line
        if scale < 0.25:
            step = 5  # Every 5th line
            
        spacing = base_spacing * step
        
        # Draw grid
        pen = QPen(QColor(40, 40, 45))
        pen.setWidth(0)  # Cosmetic pen
        painter.setPen(pen)
        
        left = int(rect.left())
        right = int(rect.right())
        top = int(rect.top())
        bottom = int(rect.bottom())
        
        # Snap starting points to grid
        first_x = left - (left % spacing)
        first_y = top - (top % spacing)
        
        # Vertical lines
        x = first_x
        while x <= right:
            painter.drawLine(x, top, x, bottom)
            x += spacing
            
        # Horizontal lines
        y = first_y
        while y <= bottom:
            painter.drawLine(left, y, right, y)
            y += spacing

    def add_node(self, title="Node"):
        node = NodeItem(self.next_id, title, canvas=self)
        self.next_id += 1
        self._scene.addItem(node)
        self.nodes.append(node)
        return node

    def add_node_from_template(self, template_name, pos=None):
        tmpl = get_template(template_name)
        node = NodeItem(self.next_id, template_name, canvas=self)
        node.template_name = template_name
        if tmpl and "category" in tmpl:
            node.category = tmpl["category"]
        self.next_id += 1
        if tmpl and tmpl.get("type") == "composite":
            # Get inputs/outputs with pin types from composite template
            inputs_map = tmpl.get("inputs", {}) or {}
            outputs_map = tmpl.get("outputs", {}) or {}
            
            # Convert map format to simple pin definitions with types
            # Inputs on the composite node are for receiving data (should create widgets)
            node.inputs = {}
            node.outputs = {}
            
            for pin_name, pin_info in inputs_map.items():
                if isinstance(pin_info, dict):
                    # Dict format: {"type": "float", "node": 5, "pin": "out0"}
                    pin_type = pin_info.get('type', 'any')
                    node.inputs[pin_name] = pin_type
                elif isinstance(pin_info, str):
                    # String format (already normalized): "float"
                    node.inputs[pin_name] = pin_info
                else:
                    node.inputs[pin_name] = 'any'
            
            for pin_name, pin_info in outputs_map.items():
                if isinstance(pin_info, dict):
                    # Dict format: {"type": "float", "node": 3, "pin": "in0"}
                    pin_type = pin_info.get('type', 'any')
                    node.outputs[pin_name] = pin_type
                elif isinstance(pin_info, str):
                    # String format (already normalized): "float"
                    node.outputs[pin_name] = pin_info
                else:
                    node.outputs[pin_name] = 'any'
            
            node.composite_graph = tmpl.get("graph")
            # Setup pins will create widgets for int/float/string/bool input types
            node.setup_pins(node.inputs, node.outputs)
            node.process = None
        else:
            ns = {}
            code = tmpl.get("code", "") if tmpl else ""
            
            # Check if it's a plugin/core node with direct inputs/outputs defined in JSON
            node_type = tmpl.get("type", "base") if tmpl else "base"
            has_io_defined = tmpl and ("inputs" in tmpl or "outputs" in tmpl)
            
            if tmpl and node_type in ("plugin", "core") and has_io_defined:
                node.inputs = tmpl.get("inputs", {}) or {}
                node.outputs = tmpl.get("outputs", {}) or {}
                node.process = None
                node.setup_pins(node.inputs, node.outputs)
            else:
                try:
                    exec(code, {}, ns)
                    node.inputs = (
                        ns.get("inputs", {}) if isinstance(ns.get("inputs", {}), dict) else {}
                    )
                    node.outputs = (
                        ns.get("outputs", {}) if isinstance(ns.get("outputs", {}), dict) else {}
                    )
                    node.process = ns.get("process")
                    node.setup_pins(node.inputs, node.outputs)
                except Exception:
                    node.process = None
                    node.inputs = {}
                    node.outputs = {}
                    node.setup_pins({}, {})
        
        # Add value widget for const nodes
        if template_name in ['ConstInt', 'ConstFloat', 'ConstBool', 'ConstString']:
            self._add_const_value_widget(node, template_name)
        
        # Add embedded widgets from template definition
        if tmpl and 'widgets' in tmpl:
            self._add_template_widgets(node, tmpl['widgets'])
        
        self._scene.addItem(node)
        if pos:
            node.setPos(pos)
        self.nodes.append(node)
        
        # Ensure fresh rendering immediately
        node.update()
        self._scene.update()
        
        # Apply category-based coloring
        self._apply_node_color(node, tmpl)
        
        # Save state for undo after adding node
        self.save_state()
        
        return node
    
    def add_node_from_palette(self, node_type, x=0, y=0):
        """Add a node by type at a specific position - used by AI assistant"""
        from PyQt6.QtCore import QPointF
        node = self.add_node_from_template(node_type, QPointF(x, y))
        return node
    
    # _ai_pin*, _resolve_pin, add_connection_by_id, _apply_node_color, _add_const_value_widget, _add_template_widgets moved to NodesMixin (canvas_nodes.py)
    # load_graph / export_graph moved to GraphIOMixin (canvas_graph_io.py)
    # --- Node removal methods moved to canvas_removal.RemovalMixin ---

    # --- on_context_menu moved to canvas_context_menu.ContextMenuMixin ---

    def mousePressEvent(self, event):
        # Middle mouse button for panning (also supported)
        if event.button() == Qt.MouseButton.MiddleButton:
            self._is_panning = True
            self._pan_start_pos = event.pos()
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return

        # Right mouse button - start potential pan (will decide on release if drag or context menu)
        if event.button() == Qt.MouseButton.RightButton:
            self._rmb_press_pos = event.pos()
            self._rmb_did_drag = False
            self._is_panning = True
            self._pan_start_pos = event.pos()
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        
        if event.button() == Qt.MouseButton.LeftButton:
            hits = self.items(event.pos())
            hit_pin = None
            for item in hits:
                # Check for both ellipse (data pins) and polygon (exec pins)
                if isinstance(item, (QGraphicsEllipseItem, QGraphicsPolygonItem)):
                    hit_pin = item
                    break
            if hit_pin:
                # Clicking on a pin - disable rubber band and start connection
                self.setDragMode(QGraphicsView.DragMode.NoDrag)
                self._is_connecting = True
                parent = hit_pin.parentItem()
                if parent and isinstance(parent, NodeItem):
                    pin_data = hit_pin.data(0)
                    if pin_data:
                        kind, pin_name = pin_data
                    else:
                        kind, pin_name = ("unknown", None)
                    if kind == "out":
                        self.start_connection((parent, pin_name))
                        event.accept()
                        return
                    elif kind == "in" and self.pending_from:
                        self.finish_connection((parent, pin_name))
                        event.accept()
                        return
            else:
                # Not clicking on a pin
                if self.pending_from:
                    # Left-click on empty space cancels the pending connection
                    self._cancel_pending_connection()
                    event.accept()
                    return
                # Check if clicking on empty space (not on a node)
                hit_node = False
                for item in hits:
                    if isinstance(item, NodeItem):
                        hit_node = True
                        break
                if not hit_node:
                    # Clicking on empty space - enable rubber band selection
                    self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        # Handle panning with middle or right mouse button
        if self._is_panning and self._pan_start_pos:
            delta = event.pos() - self._pan_start_pos
            self._pan_start_pos = event.pos()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            # Mark that we actually dragged during RMB pan
            if event.buttons() & Qt.MouseButton.RightButton:
                if delta.manhattanLength() > 3:
                    self._rmb_did_drag = True
            event.accept()
            return
        
        # Update coordinate display
        scene_pt = self.mapToScene(event.pos())
        self.coord_label.setText(f"X: {int(scene_pt.x())}, Y: {int(scene_pt.y())} | Zoom: {int(self.zoom_level * 100)}%")
        
        # Handle connection drawing
        if self.pending_line and self.pending_from:
            # Highlight pin under cursor logic
            current_highlight = None
            hits = self.items(event.pos())
            for item in hits:
                # Check for both ellipse (data pins) and polygon (exec pins)
                if isinstance(item, (QGraphicsEllipseItem, QGraphicsPolygonItem)) and item.data(0):
                    # Found a pin
                    current_highlight = item
                    break
            
            # Manage highlight state
            if getattr(self, '_last_highlighted_pin', None) != current_highlight:
                # Restore previous
                if getattr(self, '_last_highlighted_pin', None):
                    last = self._last_highlighted_pin
                    try:
                        # Restore original color based on pin type
                        data = last.data(0)
                        if data:
                            kind = data[0]
                            # Check if it's an exec pin (polygon)
                            if isinstance(last, QGraphicsPolygonItem):
                                last.setBrush(QBrush(QColor(255, 255, 255)))  # White for exec
                            elif kind == 'in':
                                last.setBrush(QBrush(QColor(180, 180, 180)))  # Gray for input
                            else:
                                last.setBrush(QBrush(QColor(150, 200, 255)))  # Blue for output
                    except Exception:
                        pass
                
                # Apply new highlight
                if current_highlight:
                    try:
                        current_highlight.setBrush(QBrush(QColor(255, 220, 50)))  # Yellow glow
                    except Exception:
                        pass
                self._last_highlighted_pin = current_highlight

            path = QPainterPath()
            if isinstance(self.pending_from, tuple):
                node, pin_name = self.pending_from
                pin_item = node.output_pins.get(pin_name)
                if pin_item:
                    start = pin_item.sceneBoundingRect().center()
                else:
                    start = node.scenePos() + QPointF(126, 0)
            else:
                start = self.pending_from.scenePos() + QPointF(126, 0)
            
            path.moveTo(start)
            
            # Use same Bezier logic as ConnectionItem
            dx = scene_pt.x() - start.x()
            ctrl_dist = max(abs(dx) * 0.5, 50)
            if dx < 0:
                ctrl_dist = max(abs(dx) * 0.5, 150)
                
            c1 = start + QPointF(ctrl_dist, 0)
            c2 = scene_pt - QPointF(ctrl_dist, 0)
            path.cubicTo(c1, c2, scene_pt)
            self.pending_line.setPath(path)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def dragEnterEvent(self, event):
        """Accept variable, graph file, and scene object drags"""
        mime = event.mimeData()
        if mime.hasText():
            text = mime.text()
            if text.startswith("variable:") or text.startswith("scene_object:") or text.startswith("logic:"):
                event.acceptProposedAction()
                return
        
        if mime.hasFormat("application/x-nodecanvas-graph") or mime.hasFormat("application/x-nodecanvas-scene-object"):
            event.acceptProposedAction()
    
    def dragMoveEvent(self, event):
        """Accept drag move"""
        mime = event.mimeData()
        if mime.hasText():
            text = mime.text()
            if text.startswith("variable:") or text.startswith("scene_object:") or text.startswith("logic:"):
                event.acceptProposedAction()
                return
        
        if mime.hasFormat("application/x-nodecanvas-graph") or mime.hasFormat("application/x-nodecanvas-scene-object"):
            event.acceptProposedAction()

    def dropEvent(self, event):
        """Handle variable drop, graph file drop, or scene object drop"""
        # Handle formats first for priority
        mime = event.mimeData()
        
        # Handle Scene Object drops (Priority)
        if mime.hasFormat("application/x-nodecanvas-scene-object"):
            data_str = mime.data("application/x-nodecanvas-scene-object").data().decode('utf-8')
            if data_str.startswith("scene_object:"):
                parts = data_str.split(":")
                if len(parts) >= 3:
                    obj_id = parts[1]
                    obj_name = parts[2]
                    drop_pos = self.mapToScene(event.position().toPoint())
                    self._create_scene_object_reference(obj_id, obj_name, drop_pos)
                    event.acceptProposedAction()
                    return

        # Handle graph file drops
        if mime.hasFormat("application/x-nodecanvas-graph"):
            graph_path = mime.data("application/x-nodecanvas-graph").data().decode('utf-8')
            drop_pos = self.mapToScene(event.position().toPoint())
            
            from PyQt6.QtWidgets import QMenu
            menu = QMenu()
            call_action = menu.addAction("📞 Call Logic (invoke and return)")
            ref_action = menu.addAction("🔗 Create Reference (opaque handle)")
            menu.addSeparator()
            cancel_action = menu.addAction("Cancel")
            
            action = menu.exec(self.mapToGlobal(event.position().toPoint()))
            
            if action == call_action:
                self._create_call_logic(graph_path, drop_pos)
            elif action == ref_action:
                self._create_reference(graph_path, drop_pos)
            
            event.acceptProposedAction()
            return

        # Handle text-based drops (variables or logic paths)
        if mime.hasText():
            text = mime.text()
            
            # Text-based scene object fallback
            if text.startswith("scene_object:"):
                parts = text.split(":")
                if len(parts) >= 3:
                    obj_id = parts[1]
                    obj_name = parts[2]
                    drop_pos = self.mapToScene(event.position().toPoint())
                    self._create_scene_object_reference(obj_id, obj_name, drop_pos)
                    event.acceptProposedAction()
                    return

            # Variable drops
            if text.startswith("variable:"):
                parts = text.split(":")
                if len(parts) >= 2:
                    var_name = parts[1]
                    var_type = parts[2] if len(parts) >= 3 else "any"
                    drop_pos = self.mapToScene(event.position().toPoint())
                    
                    from PyQt6.QtWidgets import QMenu
                    menu = QMenu(self)
                    get_action = menu.addAction("Get Variable")
                    set_action = menu.addAction("Set Variable")
                    
                    action = menu.exec(self.mapToGlobal(event.position().toPoint()))
                    
                    if action == get_action:
                        self._create_variable_accessor(var_name, var_type, "get", drop_pos)
                    elif action == set_action:
                        self._create_variable_accessor(var_name, var_type, "set", drop_pos)
                    
                    event.acceptProposedAction()
                    return

            # Logic path drops (prefixed or raw)
            if text.startswith("logic:"):
                graph_path = text[6:]
                drop_pos = self.mapToScene(event.position().toPoint())
                self._create_call_logic(graph_path, drop_pos)
                event.acceptProposedAction()
                return
    
    # --- Node factory helpers moved to canvas_factories.FactoriesMixin ---

    def wheelEvent(self, event):
        """Handle mouse wheel for zooming (always), Ctrl+wheel also zooms"""
        # Calculate zoom factor
        zoom_in_factor = 1.15
        zoom_out_factor = 1 / zoom_in_factor
        
        delta = event.angleDelta().y()
        if delta == 0:
            event.accept()
            return

        if delta > 0:
            zoom_factor = zoom_in_factor
        else:
            zoom_factor = zoom_out_factor
        new_zoom = self.zoom_level * zoom_factor
        
        # Clamp zoom level
        if new_zoom < self.min_zoom or new_zoom > self.max_zoom:
            event.accept()
            return
        
        # Zoom centered on cursor position
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.scale(zoom_factor, zoom_factor)
        self.zoom_level = new_zoom
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        
        # Update coordinate display
        scene_pt = self.mapToScene(event.position().toPoint())
        self.coord_label.setText(f"X: {int(scene_pt.x())}, Y: {int(scene_pt.y())} | Zoom: {int(self.zoom_level * 100)}%")
        
        event.accept()

    def resizeEvent(self, event):
        """Update coordinate label position on resize"""
        super().resizeEvent(event)
        self._update_coord_label_position()
    
    def _update_coord_label_position(self):
        """Position the coordinate label at bottom-right corner"""
        width = self.width()
        height = self.height()
        label_width = 200
        self.coord_label.setFixedWidth(label_width)
        self.coord_label.move(width - label_width - 10, height - 34)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            self._is_panning = False
            self._pan_start_pos = None
            self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
            self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
            return

        if event.button() == Qt.MouseButton.RightButton:
            self._is_panning = False
            self._pan_start_pos = None
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
            # Only show context menu if we didn't drag
            if not getattr(self, '_rmb_did_drag', False):
                self._dispatch_context_menu(event.pos())
            self._rmb_did_drag = False
            self._rmb_press_pos = None
            event.accept()
            return
        
        if event.button() == Qt.MouseButton.LeftButton:
            if self._is_connecting:
                self._is_connecting = False
                self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
                
                # Drag & Drop Support
                hit_pin = None
                for item in self.items(event.pos()):
                    if isinstance(item, (QGraphicsEllipseItem, QGraphicsPolygonItem)) and item.data(0):
                        hit_pin = item
                        break
                        
                if hit_pin:
                    parent = hit_pin.parentItem()
                    if parent and isinstance(parent, NodeItem) and self.pending_from:
                        pin_data = hit_pin.data(0)
                        if pin_data and pin_data[0] == "in":
                            self.finish_connection((parent, pin_data[1]))
                            event.accept()
                            return
                            
                # Cleanup orphaned lines efficiently
                if self.pending_line and self.pending_line.path().length() > 20:
                    self._cancel_pending_connection()
        
        super().mouseReleaseEvent(event)

    # --- Connection methods moved to canvas_connections.ConnectionsMixin ---


    # --- Composite I/O helpers moved to canvas_composite.CompositeMixin ---



# Backward compatibility alias - deprecated, use LogicEditor instead
CanvasView = LogicEditor
