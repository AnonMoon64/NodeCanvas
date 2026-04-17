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

class LogicEditor(QGraphicsView):
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
    
    def copy_selected(self):
        """Copy selected nodes and their internal connections to system clipboard"""
        selected_nodes = [n for n in self.nodes if n.isSelected()]
        if not selected_nodes:
            print("No nodes selected to copy")
            return
        
        # Build clipboard data
        selected_ids = {n.id for n in selected_nodes}
        nodes_data = []
        connections_data = []
        
        for node in selected_nodes:
            node_data = {
                "id": node.id,
                "template": getattr(node, "template_name", None),
                "title": node.title.toPlainText(),
                "pos": [node.pos().x(), node.pos().y()],
                "inputs": node.inputs,
                "outputs": node.outputs,
                "pin_values": getattr(node, "pin_values", {})
            }
            nodes_data.append(node_data)
        
        # Copy connections that are between selected nodes
        for conn in self.connections:
            if (hasattr(conn, 'from_node') and hasattr(conn, 'to_node') and
                conn.from_node in selected_nodes and conn.to_node in selected_nodes):
                conn_data = {
                    "from_id": conn.from_node.id,
                    "from_pin": getattr(conn, 'from_pin', None),
                    "to_id": conn.to_node.id,
                    "to_pin": getattr(conn, 'to_pin', None)
                }
                connections_data.append(conn_data)
        
        self.clipboard_data = {
            "nodes": nodes_data,
            "connections": connections_data
        }
        
        # Also copy to system clipboard as JSON text (like UE5)
        import json
        clipboard_text = json.dumps(self.clipboard_data, indent=2)
        clipboard = QApplication.clipboard()
        clipboard.setText(clipboard_text)
        
        print(f"Copied {len(nodes_data)} nodes and {len(connections_data)} connections (text format)")
    
    def paste(self):
        """Paste nodes from clipboard (internal or system) with new IDs"""
        # Try to load from system clipboard first (for cross-editor paste)
        clipboard = QApplication.clipboard()
        clipboard_text = clipboard.text()
        
        data_to_paste = None
        
        if clipboard_text:
            try:
                import json
                parsed_data = json.loads(clipboard_text)
                # Validate it looks like our node data format
                if isinstance(parsed_data, dict) and 'nodes' in parsed_data:
                    data_to_paste = parsed_data
                    print("Pasting from system clipboard (text format)")
            except Exception as e:
                print(f"System clipboard doesn't contain valid node data: {e}")
        
        # Fall back to internal clipboard
        if not data_to_paste:
            if not self.clipboard_data:
                print("Clipboard is empty")
                return
            data_to_paste = self.clipboard_data
            print("Pasting from internal clipboard")
        
        # Map old IDs to new IDs
        id_map = {}
        pasted_nodes = []
        
        # Create nodes with new IDs
        for node_data in data_to_paste["nodes"]:
            old_id = node_data["id"]
            template_name = node_data.get("template")
            
            if template_name:
                new_node = self.add_node_from_template(template_name)
            else:
                new_node = self.add_node(node_data.get("title", "Node"))
            
            # Position with offset
            pos = node_data.get("pos", [0, 0])
            new_node.setPos(pos[0] + 50, pos[1] + 50)
            
            # Restore pin values if present
            if "pin_values" in node_data:
                new_node.pin_values = node_data["pin_values"].copy()
            
            id_map[old_id] = new_node
            pasted_nodes.append(new_node)
        
        # Recreate connections
        for conn_data in data_to_paste["connections"]:
            old_from = conn_data["from_id"]
            old_to = conn_data["to_id"]
            
            if old_from in id_map and old_to in id_map:
                new_from = id_map[old_from]
                new_to = id_map[old_to]
                
                conn = ConnectionItem(new_from, new_to, self)
                conn.from_pin = conn_data.get("from_pin")
                conn.to_pin = conn_data.get("to_pin")
                conn.add_to_scene(self._scene)
                self.connections.append(conn)
                try:
                    # Refresh visuals immediately and after the event loop
                    try:
                        self.update_all_connections()
                    except Exception:
                        pass
                    try:
                        QTimer.singleShot(0, self.update_all_connections)
                    except Exception:
                        pass
                except Exception:
                    pass
        
        # Select the pasted nodes
        for node in self.nodes:
            node.setSelected(False)
        for node in pasted_nodes:
            node.setSelected(True)
        
        print(f"Pasted {len(pasted_nodes)} nodes")
    
    def cut_selected(self):
        """Cut selected nodes (copy then delete)"""
        self.copy_selected()
        self.delete_selected()
    
    def delete_selected(self):
        """Delete all selected nodes"""
        selected_nodes = [n for n in self.nodes if n.isSelected()]
        if not selected_nodes:
            print("No nodes selected to delete")
            return
        
        try:
            # Save state for undo
            self.save_state()
            
            # Use the existing safe removal mechanism
            self.mark_nodes_for_removal(list(selected_nodes))
            print(f"Deleted {len(selected_nodes)} node(s)")
        except Exception as e:
            print(f"Error deleting nodes: {e}")
            import traceback
            traceback.print_exc()
            
    def duplicate_selected(self):
        """Duplicate currently selected nodes"""
        self.copy_selected()
        self.paste()
        
    def add_comment_box(self):
        """Add a comment box to group nodes."""
        try:
            from .node_item import CommentBoxItem
        except ImportError:
            try:
                from py_editor.ui.node_item import CommentBoxItem
            except ImportError:
                return

        nodes = [n for n in self.nodes if n.isSelected()]
        if nodes:
            # Wrap selected nodes
            min_x = min(n.pos().x() for n in nodes) - 40
            min_y = min(n.pos().y() for n in nodes) - 60
            max_r = max(n.pos().x() + n.node_width for n in nodes) + 40
            max_b = max(n.pos().y() + n.node_height for n in nodes) + 40
            box = CommentBoxItem(min_x, min_y, max_r - min_x, max_b - min_y)
        else:
            # Place at mouse or center
            scene_pt = self.mapToScene(self.mapFromGlobal(QCursor.pos())) if self.underMouse() else self.mapToScene(self.viewport().rect().center())
            box = CommentBoxItem(scene_pt.x() - 150, scene_pt.y() - 100, 300, 200)
            
        self._scene.addItem(box)
        self.value_changed.emit()
    
    def save_state(self):
        """Save the current graph state to the undo stack"""
        if self._is_undoing:
            return  # Don't save state during undo/redo operations
        
        # Export current graph state
        state = self.export_graph()
        
        # Add to undo stack
        self.undo_stack.append(state)
        
        # Limit stack size
        if len(self.undo_stack) > self.max_undo_stack:
            self.undo_stack.pop(0)
        
        # Clear redo stack when new action is performed
        self.redo_stack.clear()
        
        print(f"State saved (undo stack: {len(self.undo_stack)} items)")
    
    def undo(self):
        """Undo the last action"""
        if not self.undo_stack:
            print("Nothing to undo")
            return
        
        # Save current state to redo stack before undoing
        current_state = self.export_graph()
        self.redo_stack.append(current_state)
        
        # Get the previous state
        previous_state = self.undo_stack.pop()
        
        # Restore the previous state
        self._is_undoing = True
        try:
            self.load_graph(previous_state)
            print(f"Undo performed (undo stack: {len(self.undo_stack)} items)")
        finally:
            self._is_undoing = False
    
    def redo(self):
        """Redo the last undone action"""
        if not self.redo_stack:
            print("Nothing to redo")
            return
        
        # Save current state to undo stack before redoing
        current_state = self.export_graph()
        self.undo_stack.append(current_state)
        
        # Get the next state
        next_state = self.redo_stack.pop()
        
        # Restore the next state
        self._is_undoing = True
        try:
            self.load_graph(next_state)
            print(f"Redo performed (redo stack: {len(self.redo_stack)} items)")
        finally:
            self._is_undoing = False

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
    
    # ------------------------------------------------------------------ #
    # Static helpers for AI-driven connection logic.                    #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _ai_pin_type(node, pin_name: str, direction: str) -> str:
        """Return the type string for a pin ('exec', 'float', 'any', …).

        Returns 'unknown' when no type information is available.
        Direction: 'out' → node.outputs, 'in' → node.inputs.
        """
        pins = getattr(node, 'outputs' if direction == 'out' else 'inputs', {}) or {}
        val  = pins.get(pin_name)
        if val is None:
            return 'unknown'
        if isinstance(val, str):
            return val
        if isinstance(val, dict):
            return val.get('type', 'any')
        return 'unknown'

    @staticmethod
    def _ai_pins_compatible(out_type: str, in_type: str) -> bool:
        """Return True if an output pin of out_type can connect to an input of in_type.

        Hard rules
        ----------
        • exec pins can ONLY connect to exec pins.
        • Data pins (float, int, bool, string, any …) can NEVER connect to exec.
        • 'any' is compatible with everything (except exec↔data cross).
        • int → float is allowed (widening numeric).
        • All other data types must match exactly.
        """
        # Unknown type info → allow (don't block on missing metadata)
        if 'unknown' in (out_type, in_type):
            return True

        # HARD RULE: exec ↔ non-exec is always rejected
        if out_type == 'exec' and in_type != 'exec':
            return False
        if in_type == 'exec' and out_type != 'exec':
            return False

        # 'any' is compatible with any data type (never with exec — blocked above)
        if out_type == 'any' or in_type == 'any':
            return True

        # Numeric widening
        if out_type == 'int' and in_type == 'float':
            return True

        # Exact match
        return out_type == in_type

    # ------------------------------------------------------------------ #
    # Pin-name aliases used by add_connection_by_id.                    #
    # When a caller requests a pin name that doesn't exist on the node, #
    # each alias in the list is tried in order.                         #
    # This handles the legacy exec_in/exec_out naming vs the modern     #
    # single-'exec' naming, plus common shorthand variants.             #
    # ------------------------------------------------------------------ #
    _PIN_OUT_ALIASES = {
        'exec_out': ('exec', 'out', 'then', 'flow', 'done', 'next'),
        'out':      ('exec', 'exec_out', 'then', 'flow', 'done', 'next'),
        'exec':     ('exec_out', 'out', 'then', 'flow', 'done', 'next'),
        'then':     ('exec', 'exec_out', 'out', 'flow', 'done', 'next'),
        'flow':     ('exec', 'exec_out', 'out', 'then', 'done', 'next'),
    }
    _PIN_IN_ALIASES = {
        'exec_in':  ('exec', 'in', 'input', 'enter', 'flow', 'receive'),
        'in':       ('exec', 'exec_in', 'input', 'enter', 'flow'),
        'exec':     ('exec_in', 'in', 'input', 'enter', 'flow'),
        'input':    ('exec', 'exec_in', 'in', 'enter', 'flow'),
        'enter':    ('exec', 'exec_in', 'in', 'input', 'flow'),
    }

    @staticmethod
    def _resolve_pin(pin_dict: dict, requested: str, alias_map: dict):
        """Try `requested` first; if not found try each alias in the map."""
        item = pin_dict.get(requested)
        if item is not None:
            return item, requested
        for alt in alias_map.get(requested.lower(), ()):
            item = pin_dict.get(alt)
            if item is not None:
                return item, alt
        return None, requested

    def add_connection_by_id(self, from_node_id, from_pin, to_node_id, to_pin):
        """Create a connection between nodes by their IDs — used by the AI assistant.

        Performs automatic pin-name alias resolution so that callers using
        legacy names (exec_out/exec_in) connect correctly to nodes that use
        the modern single 'exec' name, and vice-versa.

        Returns True on success, False on failure (matches the bool contract the
        AI tool layer expects).
        """
        from_node = None
        to_node   = None

        for node in self.nodes:
            if getattr(node, 'id', None) == from_node_id:
                from_node = node
            if getattr(node, 'id', None) == to_node_id:
                to_node = node

        if not from_node or not to_node:
            print(f"[AI] Connection failed: could not find nodes "
                  f"{from_node_id} -> {to_node_id}")
            return False

        # Resolve pin names with alias fallback (exec_out↔exec, exec_in↔exec, etc.)
        _fp_item, resolved_fp = self._resolve_pin(
            from_node.output_pins, from_pin, self._PIN_OUT_ALIASES)
        _tp_item, resolved_tp = self._resolve_pin(
            to_node.input_pins, to_pin, self._PIN_IN_ALIASES)

        if _fp_item is None:
            avail_out = list(from_node.output_pins.keys())
            avail_in  = list(to_node.input_pins.keys())
            print(f"[AI] Connection failed: output pin '{from_pin}' not found on node "
                  f"{from_node_id}. Available outputs={avail_out}, inputs={avail_in}")
            return False

        if _tp_item is None:
            avail_in = list(to_node.input_pins.keys())
            print(f"[AI] Connection failed: input pin '{to_pin}' not found on node "
                  f"{to_node_id}. Available inputs={avail_in}")
            return False

        if resolved_fp != from_pin or resolved_tp != to_pin:
            print(f"[AI] Pin alias resolved: '{from_pin}'→'{resolved_fp}', "
                  f"'{to_pin}'→'{resolved_tp}'")

        # Check for duplicate connection
        for existing in self.connections:
            if (getattr(existing.from_node, 'id', None) == from_node_id
                    and existing.from_pin == resolved_fp
                    and getattr(existing.to_node, 'id', None) == to_node_id
                    and existing.to_pin == resolved_tp):
                print(f"[AI] Connection {from_node_id}.{resolved_fp}→"
                      f"{to_node_id}.{resolved_tp} already exists — skipping")
                return True   # treat as success

        # Hard type rule: exec pins can only connect to exec pins; data cannot cross to exec
        out_type = self._ai_pin_type(from_node, resolved_fp, 'out')
        in_type  = self._ai_pin_type(to_node,   resolved_tp, 'in')
        if not self._ai_pins_compatible(out_type, in_type):
            avail_out = list(from_node.output_pins.keys())
            avail_in  = list(to_node.input_pins.keys())
            print(f"[AI] Connection REJECTED (type mismatch): "
                  f"{from_node_id}.{resolved_fp}({out_type}) → "
                  f"{to_node_id}.{resolved_tp}({in_type}). "
                  f"Node {from_node_id} outputs: {avail_out}. "
                  f"Node {to_node_id} inputs: {avail_in}.")
            return False

        # Create the connection — same pattern as load_graph / finish_connection
        try:
            from py_editor.ui.connection_item import ConnectionItem
            conn = ConnectionItem(from_node, to_node, self)
            conn.from_pin = resolved_fp
            conn.to_pin   = resolved_tp
            conn.add_to_scene(self._scene)
            self.connections.append(conn)
            try:
                # Immediate refresh and a deferred refresh in case geometry isn't ready yet
                try:
                    self.update_all_connections()
                except Exception:
                    pass
                try:
                    QTimer.singleShot(0, self.update_all_connections)
                except Exception:
                    pass
            except Exception:
                pass
            self.save_state()
            print(f"[AI] Connected: {from_node_id}.{resolved_fp} → "
                  f"{to_node_id}.{resolved_tp}")
            return True
        except Exception as e:
            print(f"[AI] Connection error: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _apply_node_color(self, node, template):
        """Apply color to node based on its category"""
        if not template:
            return
        
        category = template.get('category', '')
        
        # Define colors for different categories
        category_colors = {
            'Events': (QColor(120, 30, 30), QColor(180, 50, 50)),  # Red for events
            'Flow': (QColor(30, 80, 30), QColor(50, 120, 50)),     # Green for flow
            'Variables': (QColor(80, 60, 30), QColor(140, 100, 40)),  # Orange for variables
            'Math': (QColor(30, 60, 100), QColor(50, 100, 160)),   # Blue for math
            'Debug': (QColor(80, 80, 30), QColor(130, 130, 50)),   # Yellow for debug
        }
        
        if category in category_colors:
            color1, color2 = category_colors[category]
            gradient = QLinearGradient(-120, -48, 120, 48)
            gradient.setColorAt(0, color1)
            gradient.setColorAt(1, color2)
            node.header_color = color1
            # Also set a matching border color
            node.setPen(QPen(color2.lighter(120), 2))

    # create_scene_ref removed (duplicate)
    
    def _add_const_value_widget(self, node, template_name):
        """Add a value input widget to a const node"""
        from PyQt6.QtWidgets import QLineEdit, QComboBox
        from PyQt6.QtCore import Qt
        
        widget = None
        default_value = None
        
        if template_name == 'ConstBool':
            widget = QComboBox()
            widget.addItems(['false', 'true'])
            widget.setCurrentIndex(0)
            widget.setFixedWidth(70)
            default_value = False
            widget.currentTextChanged.connect(lambda v: node.pin_values.update({'value': v == 'true'}))
            widget.currentTextChanged.connect(lambda: self.value_changed.emit())
        elif template_name == 'ConstInt':
            widget = QLineEdit('0')
            widget.setFixedWidth(60)
            widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
            default_value = 0
            def update_int():
                try:
                    node.pin_values['value'] = int(widget.text())
                except ValueError:
                    node.pin_values['value'] = 0
                self.value_changed.emit()
            widget.textChanged.connect(update_int)
        elif template_name == 'ConstFloat':
            widget = QLineEdit('0.0')
            widget.setFixedWidth(60)
            widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
            default_value = 0.0
            def update_float():
                try:
                    node.pin_values['value'] = float(widget.text())
                except ValueError:
                    node.pin_values['value'] = 0.0
                self.value_changed.emit()
            widget.textChanged.connect(update_float)
        elif template_name == 'ConstString':
            widget = QLineEdit('')
            widget.setFixedWidth(90)
            widget.setPlaceholderText('text...')
            default_value = ''
            widget.textChanged.connect(lambda v: node.pin_values.update({'value': v}))
            widget.textChanged.connect(lambda: self.value_changed.emit())
        
        if widget:
            widget.setStyleSheet("""
                QLineEdit, QComboBox {
                    background-color: #2a2a2a;
                    color: #ffffff;
                    border: 1px solid #555;
                    border-radius: 3px;
                    padding: 3px 5px;
                    font-size: 10px;
                }
                QComboBox::drop-down {
                    border: none;
                }
            """)
            
            proxy = QGraphicsProxyWidget(node)
            proxy.setWidget(widget)
            proxy.setPos(-45, 5)  # Center in node
            node.value_widgets['value'] = proxy
            node.pin_values['value'] = default_value
    
    def _add_template_widgets(self, node, widgets_config):
        """Add embedded widgets defined in a node template (channel dropdown, loop toggle, etc.)"""
        from PyQt6.QtWidgets import QComboBox, QCheckBox, QWidget, QHBoxLayout, QLabel, QLineEdit
        from PyQt6.QtCore import Qt
        
        if not widgets_config:
            return
        
        # Node rect is -120,-48 to 120,48
        # Position widgets in the center-bottom area of the node
        # Start Y at 5 (just below center) and stack downward
        base_y = 0
        
        widget_idx = 0
        for widget_name, widget_def in widgets_config.items():
            widget_type = widget_def.get('type', 'dropdown')
            default_val = widget_def.get('default', '')
            
            container = QWidget()
            layout = QHBoxLayout(container)
            layout.setContentsMargins(2, 0, 2, 0)
            layout.setSpacing(4)
            
            # Suppress labels for certain well-known IDs that are reflected in the title
            if widget_name in ("object_id", "graphPath"):
                pass
            else:
                # Shorter label
                short_name = widget_name[:4] if len(widget_name) > 4 else widget_name
                label = QLabel(short_name + ":")
                label.setStyleSheet("color: #aaa; font-size: 8px;")
                layout.addWidget(label)
            
            if widget_type == 'dropdown':
                combo = QComboBox()
                options = widget_def.get('options', [])
                combo.addItems(options)
                if default_val and default_val in options:
                    combo.setCurrentText(default_val)
                combo.setFixedWidth(55)
                combo.currentTextChanged.connect(lambda v, n=widget_name: node.pin_values.update({n: v}))
                if hasattr(self, 'value_changed'):
                    combo.currentTextChanged.connect(lambda: self.value_changed.emit())
                layout.addWidget(combo)
                node.pin_values[widget_name] = default_val
            
            elif widget_type == 'string':
                # String input - editable text field
                line_edit = QLineEdit()
                line_edit.setText(str(default_val))
                line_edit.setFixedWidth(70)
                line_edit.textChanged.connect(lambda v, n=widget_name: node.pin_values.update({n: v}))
                if hasattr(self, 'value_changed'):
                    line_edit.textChanged.connect(lambda: self.value_changed.emit())
                layout.addWidget(line_edit)
                node.pin_values[widget_name] = default_val
            
            container.setFixedSize(110, 18)
            container.setStyleSheet("""
                QWidget { background: transparent; }
                QLabel { background: transparent; border: none; }
                QComboBox {
                    background-color: #2a2a2a;
                    color: #fff;
                    border: 1px solid #555;
                    border-radius: 2px;
                    padding: 1px;
                    font-size: 8px;
                }
                QComboBox::drop-down { border: none; }
                QLineEdit {
                    background-color: #2a2a2a;
                    color: #4fc3f7;
                    border: 1px solid #555;
                    border-radius: 2px;
                    padding: 1px;
                    font-size: 9px;
                }
            """)
            
            proxy = QGraphicsProxyWidget(node)
            proxy.setWidget(container)
            # Position inside node: X centered, Y stacking from center downward
            proxy.setPos(-55, base_y + (widget_idx * 20))
            
            node.value_widgets[widget_name] = proxy
            widget_idx += 1

    def load_graph(self, graph: dict):
        variables = graph.get("variables", {})
        if isinstance(variables, dict):
            self.graph_variables = {
                name: dict(info) if isinstance(info, dict) else {"type": None, "value": info}
                for name, info in variables.items()
            }
        else:
            self.graph_variables = {}

        for conn in list(self.connections):
            try:
                conn.remove()
            except Exception:
                pass
        self.connections.clear()
        for node in list(self.nodes):
            try:
                self._scene.removeItem(node)
            except Exception:
                pass
        self.nodes.clear()

        id_map = {}
        for nd in graph.get("nodes", []):
            nid = nd.get("id")
            tname = nd.get("template")
            pos = nd.get("pos")
            values = nd.get("values", {})  # Load saved values
            if tname:
                node = self.add_node_from_template(
                    tname,
                    pos=QPointF(pos[0], pos[1]) if pos else None,
                )
            else:
                title = nd.get("title") or nd.get("name") or "Node"
                node = self.add_node(title)
                if pos:
                    node.setPos(QPointF(pos[0], pos[1]))
            if nid is not None:
                node.id = nid
                self.next_id = max(self.next_id, nid + 1)
            # Restore pin_type and external_name for composite I/O nodes
            if 'pin_type' in nd:
                node.pin_type = nd['pin_type']
                # Restore external name if saved
                if 'external_name' in nd:
                    node.external_name = nd['external_name']
                # Rebuild pins with correct type
                node_tname = getattr(node, 'template_name', None)
                if node_tname == '__composite_input__':
                    pin_key = list(node.output_pins.keys())[0] if node.output_pins else 'out0'
                    node.outputs = {pin_key: node.pin_type}
                    node.setup_pins(node.inputs, node.outputs)
                elif node_tname == '__composite_output__':
                    pin_key = list(node.input_pins.keys())[0] if node.input_pins else 'in0'
                    node.inputs = {pin_key: node.pin_type}
                    node.setup_pins(node.inputs, node.outputs)
            
            # Restore dynamic outputs for Sequence nodes
            if 'outputs' in nd and tname == 'Sequence':
                node.outputs = nd['outputs']
                node.setup_pins(node.inputs, node.outputs)
            
            # Restore saved values to widgets
            if values and hasattr(node, 'pin_values'):
                print(f"Loading node {nid} with values: {values}")
                node.pin_values.update(values)
                # Update the widget UI to reflect loaded values
                if hasattr(node, 'value_widgets'):
                    for pin_name, value in values.items():
                        proxy_widget = node.value_widgets.get(pin_name)
                        if proxy_widget:
                            # Get the actual widget from the proxy
                            container = proxy_widget.widget()
                            # The container may have a layout with the real widget inside
                            actual_widget = container
                            if hasattr(container, 'layout') and container.layout():
                                layout = container.layout()
                                for i in range(layout.count()):
                                    item = layout.itemAt(i)
                                    if item and item.widget():
                                        w = item.widget()
                                        if isinstance(w, QComboBox) or isinstance(w, QLineEdit):
                                            actual_widget = w
                                            break
                            
                            if isinstance(actual_widget, QComboBox):
                                index = actual_widget.findText(str(value))
                                if index >= 0:
                                    actual_widget.setCurrentIndex(index)
                                else:
                                    # For boolean values
                                    actual_widget.setCurrentIndex(1 if value else 0)
                            elif isinstance(actual_widget, QLineEdit):
                                actual_widget.setText(str(value))
                            print(f"  Restored {pin_name} = {value} to widget")
            
            # Special handling for Reference nodes - restore graph_path and title
            # (outside the if values block to ensure it runs)
            if tname == 'Reference':
                graph_path_value = nd.get('values', {}).get('graphPath') or getattr(node, 'pin_values', {}).get('graphPath')
                if graph_path_value:
                    from pathlib import Path
                    node.graph_path = graph_path_value
                    node.pin_values['graphPath'] = graph_path_value
                    graph_name = Path(graph_path_value).stem
                    # Update QGraphicsTextItem title
                    if hasattr(node, 'title'):
                        node.title.setPlainText(f"Ref: {graph_name}")
                    node.update()
                    print(f"  Restored Reference to {graph_name}")
            
            # Special handling for CallLogic nodes
            if tname == 'CallLogic':
                graph_path_value = nd.get('values', {}).get('graphPath') or getattr(node, 'pin_values', {}).get('graphPath')
                if graph_path_value:
                    from pathlib import Path
                    node.graph_path = graph_path_value
                    node.pin_values['graphPath'] = graph_path_value
                    graph_name = Path(graph_path_value).stem
                    # Update QGraphicsTextItem title
                    if hasattr(node, 'title'):
                        node.title.setPlainText(f"Call: {graph_name}")
                    node.update()
                    print(f"  Restored CallLogic to {graph_name}")
                    
            id_map[nid] = node

        for conn in graph.get("connections", []):
            fr = conn.get("from")
            to = conn.get("to")
            from_pin = conn.get("from_pin")
            to_pin = conn.get("to_pin")
            from_node = id_map.get(fr)
            to_node = id_map.get(to)
            if from_node and to_node:
                connection = ConnectionItem(from_node, to_node, self)
                connection.from_pin = from_pin
                connection.to_pin = to_pin
                connection.add_to_scene(self._scene)
                self.connections.append(connection)
                try:
                    # Refresh visual paths immediately and after the event loop
                    try:
                        self.update_all_connections()
                    except Exception:
                        pass
                    try:
                        QTimer.singleShot(0, self.update_all_connections)
                    except Exception:
                        pass
                except Exception:
                    pass
        self.graph_changed.emit()
        self.value_changed.emit()

    def export_graph(self):
        nodes = []
        for node in self.nodes:
            node_data = {
                "id": node.id,
                "template": getattr(node, "template_name", None),
                "pos": [node.pos().x(), node.pos().y()],
            }
            node_values = {}
            inputs_map = getattr(node, 'inputs', {}) or {}

            if hasattr(node, 'value_widgets') and node.value_widgets:
                for pin_name, proxy in node.value_widgets.items():
                    container = proxy.widget()
                    if not container:
                        continue

                    # Dig into container layout to find actual widget
                    widget = container
                    if hasattr(container, 'layout') and container.layout():
                        layout = container.layout()
                        for i in range(layout.count()):
                            item = layout.itemAt(i)
                            if item and item.widget():
                                w = item.widget()
                                if isinstance(w, QComboBox) or isinstance(w, QLineEdit):
                                    widget = w
                                    break

                    pin_def = inputs_map.get(pin_name)
                    if isinstance(pin_def, dict):
                        pin_type = pin_def.get('type', 'any') or 'any'
                    else:
                        pin_type = pin_def or 'any'

                    if isinstance(widget, QComboBox):
                        if pin_type == 'bool':
                            node_values[pin_name] = bool(widget.currentIndex())
                        else:
                            node_values[pin_name] = widget.currentText()
                    elif isinstance(widget, QLineEdit):
                        text = widget.text()
                        try:
                            if pin_type == 'int':
                                node_values[pin_name] = int(text) if text else 0
                            elif pin_type == 'float':
                                node_values[pin_name] = float(text) if text else 0.0
                            else:
                                node_values[pin_name] = text
                        except ValueError:
                            stored = getattr(node, 'pin_values', {}).get(pin_name)
                            if stored is not None:
                                node_values[pin_name] = stored
                            elif pin_type == 'int':
                                node_values[pin_name] = 0
                            elif pin_type == 'float':
                                node_values[pin_name] = 0.0
                            else:
                                node_values[pin_name] = text
                    else:
                        stored = getattr(node, 'pin_values', {}).get(pin_name)
                        if stored is not None:
                            node_values[pin_name] = stored

            if hasattr(node, 'pin_values'):
                for key, stored_value in node.pin_values.items():
                    if key not in node_values:
                        node_values[key] = stored_value

            if node_values:
                node_data["values"] = node_values
                print(f"Exporting node {node.id} with values: {node_values}")

            # Save pin_type and external_name for composite I/O nodes
            tname = getattr(node, "template_name", None)
            if tname in ('__composite_input__', '__composite_output__'):
                pin_type = getattr(node, 'pin_type', 'any')
                node_data['pin_type'] = pin_type
                if hasattr(node, 'external_name'):
                    node_data['external_name'] = node.external_name
            
            # Save dynamic outputs for Sequence nodes
            if tname == 'Sequence' and hasattr(node, 'outputs'):
                node_data['outputs'] = node.outputs
            
            nodes.append(node_data)
        connections = []
        for conn in self.connections:
            connections.append(
                {
                    "from": getattr(conn.from_node, "id", None),
                    "from_pin": getattr(conn, "from_pin", None),
                    "to": getattr(conn.to_node, "id", None),
                    "to_pin": getattr(conn, "to_pin", None),
                }
            )
        graph_variables = {}
        if isinstance(getattr(self, 'graph_variables', None), dict):
            for name, info in self.graph_variables.items():
                if isinstance(info, dict):
                    graph_variables[name] = {
                        "type": info.get("type"),
                        "value": info.get("value"),
                    }
                else:
                    graph_variables[name] = {"type": None, "value": info}

        return {"nodes": nodes, "connections": connections, "variables": graph_variables}

    def _collect_pin_options(self, nodes, is_input=True):
        options = []
        seen = set()
        for node in nodes:
            pin_dict = node.input_pins if is_input else node.output_pins
            label_prefix = node.title.toPlainText() or f"Node {node.id}"
            for pin_name in pin_dict.keys():
                key = (node.id, pin_name)
                if key in seen:
                    continue
                seen.add(key)
                options.append(
                    {
                        "node": node.id,
                        "pin": pin_name,
                        "label": f"{label_prefix} ({node.id}) - {pin_name}",
                    }
                )
        return options

    def _clear_pending_preview(self, nodes):
        if not self.pending_from:
            return
        primary = self.pending_from[0] if isinstance(self.pending_from, tuple) else self.pending_from
        if primary not in nodes:
            return
        if self.pending_line:
            try:
                self._scene.removeItem(self.pending_line)
            except Exception:
                pass
        self.pending_line = None
        self.pending_from = None

    def _collect_connections_for_nodes(self, nodes):
        to_remove = set()
        for conn in list(self.connections):
            if conn.from_node in nodes or conn.to_node in nodes:
                to_remove.add(conn)
        return to_remove

    def _delete_connections(self, connections):
        # deletion disabled: noop to avoid crashes; leave function for compatibility
        return

    def _perform_node_deletion(self, nodes, error_context):
        # deletion disabled temporarily per user request; function retained for compatibility
        return

    def _queue_node_deletion(self, nodes, error_context):
        # deletion disabled temporarily per user request; function retained for compatibility
        return

    def update_connections_for_node(self, node_item):
        for conn in list(self.connections):
            if getattr(conn, "_removed", False):
                continue
            if conn.from_node is None or conn.to_node is None:
                # ensure stale connections are dropped from scene and list
                try:
                    conn.remove()
                except Exception:
                    pass
                continue
            if conn.from_node is node_item or conn.to_node is node_item:
                conn.update_path()

    def update_all_connections(self):
        """Force an update of all connection visuals and refresh the scene/view."""
        try:
            for conn in list(getattr(self, 'connections', [])):
                try:
                    conn.update_path()
                except Exception:
                    pass
            try:
                if self._scene:
                    self._scene.update()
            except Exception:
                pass
            try:
                self.viewport().update()
            except Exception:
                pass
        except Exception:
            traceback.print_exc()

    def reload_nodes_from_template(self, template_name):
        tmpl = get_template(template_name)
        if not tmpl:
            return
        for node in self.nodes:
            if getattr(node, "template_name", None) == template_name:
                try:
                    # For composite templates, inputs/outputs are stored in the template JSON
                    if tmpl.get('type') == 'composite':
                        node.inputs = tmpl.get('inputs', {}) or {}
                        node.outputs = tmpl.get('outputs', {}) or {}
                        node.composite_graph = tmpl.get('graph')
                        node.process = None
                        node.setup_pins(node.inputs, node.outputs)
                    else:
                        ns = {}
                        exec(tmpl.get("code", ""), {}, ns)
                        node.inputs = (
                            ns.get("inputs", {}) if isinstance(ns.get("inputs", {}), dict) else {}
                        )
                        node.outputs = (
                            ns.get("outputs", {}) if isinstance(ns.get("outputs", {}), dict) else {}
                        )
                        node.process = ns.get("process")
                        node.setup_pins(node.inputs, node.outputs)
                except Exception:
                    pass

    def remove_nodes_by_template(self, template_name):
        """Safely remove all nodes on this canvas that were created from `template_name`.

        This removes associated connections first, calls `cleanup()` on nodes to
        detach visuals, and defers the actual scene removal to the event loop
        to avoid invalidating Qt-owned references mid-event.
        """
        nodes = [n for n in list(self.nodes) if getattr(n, 'template_name', None) == template_name]
        if nodes:
            try:
                print(f"DEBUG: remove_nodes_by_template called for '{template_name}', found {len(nodes)} nodes")
                for n in nodes:
                    try:
                        nid = getattr(n, 'id', None)
                        tname = getattr(n, 'template_name', None)
                        title = getattr(n, 'title', None)
                        ttext = title.toPlainText() if title is not None and getattr(title, 'toPlainText', None) else ''
                        print(f"DEBUG: node id={nid} template={tname} title={ttext} scene={bool(n.scene())}")
                    except Exception:
                        traceback.print_exc()
                self.remove_nodes(nodes)
            except Exception:
                print("ERROR: exception in remove_nodes_by_template")
                traceback.print_exc()

    def remove_nodes(self, nodes):
        """Safely remove the given list of NodeItem instances from this canvas.

        This removes connections first, calls `cleanup()` on nodes to detach
        visuals, and defers scene removal to the event loop to avoid Qt crashes.
        """
        if not nodes:
            return

        # make a stable list
        nodes = list(nodes)

        # clear pending previews that reference these nodes
        try:
            print(f"DEBUG: remove_nodes called with {len(nodes)} nodes")
            for n in nodes:
                try:
                    nid = getattr(n, 'id', None)
                    tname = getattr(n, 'template_name', None)
                    title = getattr(n, 'title', None)
                    ttext = title.toPlainText() if title is not None and getattr(title, 'toPlainText', None) else ''
                    print(f"DEBUG: preparing to remove node id={nid} template={tname} title={ttext} scene={bool(n.scene())}")
                except Exception:
                    traceback.print_exc()
            try:
                self._clear_pending_preview(nodes)
            except Exception:
                print("WARNING: _clear_pending_preview failed")
                traceback.print_exc()
        except Exception:
            print("ERROR: exception while starting remove_nodes")
            traceback.print_exc()

        # collect and remove connections touching these nodes
        try:
            conns = self._collect_connections_for_nodes(nodes)
            print(f"DEBUG: collected {len(conns)} connections touching nodes")
            for c in list(conns):
                try:
                    cid = getattr(c, 'id', None)
                    fn = getattr(c, 'from_node', None)
                    tn = getattr(c, 'to_node', None)
                    print(f"DEBUG: removing connection id={cid} from={getattr(fn,'id',None)} to={getattr(tn,'id',None)}")
                    c.remove()
                except Exception:
                    print("WARNING: connection.remove() raised")
                    try:
                        traceback.print_exc()
                    except Exception:
                        pass
        except Exception:
            print("WARNING: _collect_connections_for_nodes failed")
            traceback.print_exc()

        # call cleanup on nodes
        for node in nodes:
            try:
                print(f"DEBUG: calling cleanup() for node id={getattr(node,'id',None)}")
                if getattr(node, 'cleanup', None):
                    node.cleanup()
            except Exception:
                print(f"WARNING: node.cleanup() raised for id={getattr(node,'id',None)}")
                traceback.print_exc()

        # perform actual scene removals deferred to next event loop turn
        def _do_removal(rem_nodes=list(nodes)):
            try:
                for node in rem_nodes:
                    try:
                        print(f"DEBUG: _do_removal processing node id={getattr(node,'id',None)} scene={bool(getattr(node,'scene',lambda:None)())}")
                    except Exception:
                        pass
                    try:
                        # don't remove the QGraphicsItem from the scene immediately; hide/disable it
                        try:
                            print(f"DEBUG: _do_removal hiding node id={getattr(node,'id',None)} instead of immediate removal")
                            try:
                                node.setVisible(False)
                            except Exception:
                                pass
                            try:
                                node.setEnabled(False)
                            except Exception:
                                pass
                            try:
                                node.setParentItem(None)
                            except Exception:
                                pass
                            # keep a reference so GC doesn't finalize it while Qt may still hold pointers
                            try:
                                self._recently_removed.append(node)
                            except Exception:
                                pass
                        except Exception:
                            print(f"WARNING: _do_removal failed to prepare node id={getattr(node,'id',None)} for deferred removal")
                            traceback.print_exc()
                    except Exception:
                        print(f"WARNING: _do_removal checking node.scene() failed for id={getattr(node,'id',None)}")
                        traceback.print_exc()
                    try:
                        if node in self.nodes:
                            try:
                                self.nodes.remove(node)
                                print(f"DEBUG: _do_removal removed node id={getattr(node,'id',None)} from canvas.nodes")
                            except Exception:
                                print(f"WARNING: _do_removal failed to remove node id={getattr(node,'id',None)} from canvas.nodes")
                                traceback.print_exc()
                    except Exception:
                        pass
                # refresh remaining connections
                for conn in list(getattr(self, 'connections', [])):
                    try:
                        print(f"DEBUG: _do_removal updating connection id={getattr(conn,'id',None)} from={getattr(getattr(conn,'from_node',None),'id',None)} to={getattr(getattr(conn,'to_node',None),'id',None)}")
                        conn.update_path()
                    except Exception:
                        print(f"WARNING: _do_removal failed during conn.update_path id={getattr(conn,'id',None)}")
                        traceback.print_exc()
            except Exception:
                print("ERROR: _do_removal top-level exception")
                traceback.print_exc()
            # schedule final scene removal of recently removed nodes after a short delay
            try:
                self._schedule_final_cleanup()
            except Exception:
                pass

        try:
            if DEBUG_FORCE_IMMEDIATE_REMOVAL:
                print("DEBUG: DEBUG_FORCE_IMMEDIATE_REMOVAL enabled — running _do_removal() synchronously")
                _do_removal()
            else:
                print("DEBUG: scheduling deferred scene removal via QTimer.singleShot(0, ...) ")
                QTimer.singleShot(0, _do_removal)
        except Exception:
            print("WARNING: scheduled removal failed, running immediate removal")
            try:
                _do_removal()
            except Exception:
                print("ERROR: immediate _do_removal failed")
                traceback.print_exc()
    
    def _schedule_final_cleanup(self, delay=200):
        if getattr(self, '_final_cleanup_pending', False):
            return
        self._final_cleanup_pending = True

        def _final():
            try:
                self._final_cleanup_pending = False
                nodes_to_drop = list(getattr(self, '_recently_removed', []))
                try:
                    self._recently_removed.clear()
                except Exception:
                    pass
                for n in nodes_to_drop:
                    try:
                        if getattr(n, 'cleanup', None):
                            try:
                                n.cleanup()
                            except Exception:
                                traceback.print_exc()
                    except Exception:
                        pass
                    # Do not call scene().removeItem() here — defer final removal
                    # to `final_cleanup_now()` which is called at a safe time (app quit).
                    try:
                        pass
                    except Exception:
                        pass
                for conn in list(getattr(self, 'connections', [])):
                    try:
                        conn.update_path()
                    except Exception:
                        pass
            except Exception:
                traceback.print_exc()

        try:
            QTimer.singleShot(delay, _final)
        except Exception:
            _final()

    def mark_nodes_for_removal(self, nodes):
        """Mark nodes for deferred removal without calling cleanup() immediately.

        This hides/disables nodes, removes connections, detaches the items from
        parents, keeps Python references briefly, and schedules final cleanup.
        """
        if not nodes:
            return
        nodes = list(nodes)
        try:
            self._clear_pending_preview(nodes)
        except Exception:
            pass
        try:
            conns = self._collect_connections_for_nodes(nodes)
            for c in list(conns):
                try:
                    c.remove()
                except Exception:
                    traceback.print_exc()
        except Exception:
            traceback.print_exc()

        for node in nodes:
            try:
                try:
                    node.setVisible(False)
                except Exception:
                    pass
                try:
                    node.setEnabled(False)
                except Exception:
                    pass
                try:
                    node.setParentItem(None)
                except Exception:
                    pass
            except Exception:
                traceback.print_exc()
            try:
                if node in self.nodes:
                    try:
                        self.nodes.remove(node)
                    except Exception:
                        traceback.print_exc()
            except Exception:
                pass
            try:
                self._recently_removed.append(node)
            except Exception:
                pass

        try:
            self._schedule_final_cleanup()
        except Exception:
            traceback.print_exc()
    def final_cleanup_now(self):
        """Perform final removal of any recently removed nodes immediately.

        This should be called at application shutdown when it's safe to remove
        QGraphicsItems from scenes without risking Qt lifetime races.
        """
        try:
            nodes_to_drop = list(getattr(self, '_recently_removed', []))
            try:
                self._recently_removed.clear()
            except Exception:
                pass
            for n in nodes_to_drop:
                try:
                    if getattr(n, 'cleanup', None):
                        try:
                            n.cleanup()
                        except Exception:
                            traceback.print_exc()
                except Exception:
                    pass
                try:
                    if n.scene():
                        try:
                            n.scene().removeItem(n)
                        except Exception:
                            traceback.print_exc()
                except Exception:
                    pass
            # refresh remaining connections
            for conn in list(getattr(self, 'connections', [])):
                try:
                    conn.update_path()
                except Exception:
                    pass
        except Exception:
            traceback.print_exc()
    def on_context_menu(self, point):
        # If there's a pending connection, show the node menu for compatible nodes
        if self.pending_from:
            scene_pt = self.mapToScene(point)
            self._show_connection_node_menu(scene_pt, point)
            return
        
        scene_pt = self.mapToScene(point)
        items = self.items(point)
        target_node = None
        for item in items:
            if isinstance(item, NodeItem):
                target_node = item
                break
            parent = item.parentItem()
            if parent and isinstance(parent, NodeItem):
                target_node = parent
                break

        selected_nodes = [i for i in self._scene.selectedItems() if isinstance(i, NodeItem)]

        # --- Scene Reference Logic ---
        has_sel_objs = False
        sel_objs = []
        if not target_node and not selected_nodes:
            if hasattr(self, 'main_window') and self.main_window.scene_editor:
                sel_objs = [o for o in self.main_window.scene_editor.viewport.scene_objects if o.selected]
                has_sel_objs = len(sel_objs) > 0

        if has_sel_objs:
             menu = QMenu()
             for obj in sel_objs:
                  a = menu.addAction(f"Create Reference to {obj.name}")
                  a.triggered.connect(lambda _, o=obj: self._create_scene_object_reference(o.id, o.name, scene_pt))
             menu.addSeparator()
             all_nodes_act = menu.addAction("All Nodes...")
             action = menu.exec(self.mapToGlobal(point))
             if action == all_nodes_act:
                  pass # proceed to search dialog
             else:
                  return # Reference created
        # -----------------------------

        if len(selected_nodes) > 1:
            menu = QMenu()
            copy_action = QAction("Copy (Ctrl+C)", menu)
            paste_action = QAction("Paste (Ctrl+V)", menu)
            duplicate_action = QAction("Duplicate (Ctrl+D)", menu)
            menu.addAction(copy_action)
            menu.addAction(paste_action)
            menu.addAction(duplicate_action)
            menu.addSeparator()
            delete_sel_action = QAction("Delete", menu)
            collapse_action = QAction("Collapse Into Node", menu)
            menu.addAction(delete_sel_action)
            menu.addAction(collapse_action)
            action = menu.exec(self.mapToGlobal(point))
            if action == copy_action:
                self.copy_selected()
                return
            if action == paste_action:
                self.paste()
                return
            if action == duplicate_action:
                self.duplicate_selected()
                return
            if action == delete_sel_action:
                try:
                    # close the menu and let Qt finish menu processing before removing items
                    try:
                        menu.close()
                        QApplication.processEvents()
                    except Exception:
                        pass
                    # defer removal to avoid deleting QGraphicsItems while menu still holds refs
                    try:
                        print("DEBUG: context-menu multi-delete scheduling removal")
                        QTimer.singleShot(0, lambda: self.mark_nodes_for_removal(list(selected_nodes)))
                    except Exception:
                        print("DEBUG: context-menu multi-delete running mark_nodes_for_removal directly")
                        self.mark_nodes_for_removal(list(selected_nodes))
                    print("DEBUG: context-menu multi-delete scheduled/ran removal, returning")
                except Exception:
                    traceback.print_exc()
                return
            if action == collapse_action:
                sel_set = set(selected_nodes)
                nodes_data = [
                    {
                        "id": node.id,
                        "template": getattr(node, "template_name", None),
                        "pos": [node.pos().x(), node.pos().y()],
                    }
                    for node in selected_nodes
                ]
                conn_data = [
                    {
                        "from": conn.from_node.id,
                        "from_pin": getattr(conn, "from_pin", None),
                        "to": conn.to_node.id,
                        "to_pin": getattr(conn, "to_pin", None),
                    }
                    for conn in self.connections
                    if conn.from_node in sel_set and conn.to_node in sel_set
                ]
                inputs = {}
                outputs = {}
                for conn in self.connections:
                    if conn.from_node not in sel_set and conn.to_node in sel_set:
                        node_id = getattr(conn.to_node, "id", None)
                        pin = getattr(conn, "to_pin", None)
                        if node_id is None or pin is None:
                            continue
                        key = pin
                        if key in inputs:
                            key = f"in_{node_id}_{pin}"
                        inputs[key] = {"node": node_id, "pin": pin, "type": "any"}
                    if conn.from_node in sel_set and conn.to_node not in sel_set:
                        node_id = getattr(conn.from_node, "id", None)
                        pin = getattr(conn, "from_pin", None)
                        if node_id is None or pin is None:
                            continue
                        key = pin
                        if key in outputs:
                            key = f"out_{node_id}_{pin}"
                        outputs[key] = {"node": node_id, "pin": pin, "type": "any"}
                try:
                    input_defaults = [
                        {
                            "external": name,
                            "node": info["node"],
                            "pin": info["pin"],
                        }
                        for name, info in inputs.items()
                    ]
                    output_defaults = [
                        {
                            "external": name,
                            "node": info["node"],
                            "pin": info["pin"],
                        }
                        for name, info in outputs.items()
                    ]
                    # auto-prompt for composite name and use detected inputs/outputs
                    try:
                        comp_name, ok = QInputDialog.getText(self, "Composite Name", "Composite name:")
                        if not ok or not comp_name.strip():
                            QMessageBox.warning(None, "Error", "Composite nodes must have a name.")
                        else:
                            comp = {
                                "type": "composite",
                                "name": comp_name.strip(),
                                "graph": {"nodes": nodes_data, "connections": conn_data},
                                "inputs": inputs,
                                "outputs": outputs,
                            }
                            save_template(comp)
                            load_templates()
                    except Exception as err:
                        traceback.print_exc()
                        QMessageBox.warning(None, "Error", f"Failed to save composite: {err}")
                except Exception as err:
                    QMessageBox.warning(
                        None,
                        "Error",
                        f"Failed to save composite: {err}",
                    )

        elif target_node:
            menu = QMenu()
            rename_action = QAction("Rename", menu)
            edit_action = QAction("Edit Node", menu)
            copy_action = QAction("Copy", menu)
            paste_action = QAction("Paste", menu)
            duplicate_action = QAction("Duplicate", menu)
            delete_action = QAction("Delete", menu)
            
            menu.addAction(rename_action)
            menu.addAction(edit_action)
            menu.addSeparator()
            menu.addAction(copy_action)
            menu.addAction(paste_action)
            menu.addAction(duplicate_action)
            menu.addSeparator()
            menu.addAction(delete_action)
            
            # Add "Set Pin Type" for composite I/O nodes
            tname = getattr(target_node, "template_name", None)
            set_type_action = None
            if tname in ('__composite_input__', '__composite_output__'):
                menu.addSeparator()
                set_type_action = QAction("Set Pin Type", menu)
                menu.addAction(set_type_action)
            
            # Add "Add Output" and "Remove Output" for Sequence nodes (dynamic outputs)
            add_output_action = None
            remove_output_action = None
            if tname == 'Sequence':
                menu.addSeparator()
                add_output_action = QAction("Add Output Pin", menu)
                menu.addAction(add_output_action)
                # Only show remove if more than 2 outputs
                if len(target_node.output_pins) > 2:
                    remove_output_action = QAction("Remove Output Pin", menu)
                    menu.addAction(remove_output_action)

            # Variadic Input Logic (SelectInt, StringAppend)
            add_input_action = None
            remove_input_action = None
            is_variadic_node = tname in ('SelectInt', 'StringAppend')
            if is_variadic_node:
                menu.addSeparator()
                add_input_action = QAction("Add Input Pin", menu)
                menu.addAction(add_input_action)
                # Count current dynamic pins
                prefix = 'option' if tname == 'SelectInt' else 'str'
                dyn_pins = [p for p in target_node.inputs if p.startswith(prefix)]
                if len(dyn_pins) > 1:
                    remove_input_action = QAction("Remove Input Pin", menu)
                    menu.addAction(remove_input_action)
            
            # Add "Change Variable" for variable nodes
            change_var_action = None
            if tname in ('GetVariable', 'SetVariable'):
                menu.addSeparator()
                change_var_action = QAction("Change Variable...", menu)
                menu.addAction(change_var_action)
            
            # Add breakpoint toggle for debugging
            menu.addSeparator()
            breakpoint_text = "Remove Breakpoint" if target_node.has_breakpoint else "Add Breakpoint"
            breakpoint_action = QAction(breakpoint_text, menu)
            menu.addAction(breakpoint_action)
            
            action = menu.exec(self.mapToGlobal(point))
            if action == set_type_action and set_type_action:
                try:
                    # Show dialog to pick pin type
                    current_type = getattr(target_node, 'pin_type', 'any')
                    types = ["any", "int", "float", "string", "bool"]
                    new_type, ok = QInputDialog.getItem(self, "Set Pin Type", "Type:", types, types.index(current_type), False)
                    if ok and new_type:
                        target_node.pin_type = new_type
                        # Update the pins with the new type
                        if tname == '__composite_input__':
                            pin_name = list(target_node.output_pins.keys())[0] if target_node.output_pins else 'out0'
                            target_node.outputs = {pin_name: new_type}
                            target_node.setup_pins(target_node.inputs, target_node.outputs)
                        elif tname == '__composite_output__':
                            pin_name = list(target_node.input_pins.keys())[0] if target_node.input_pins else 'in0'
                            target_node.inputs = {pin_name: new_type}
                            target_node.setup_pins(target_node.inputs, target_node.outputs)
                        self.update_connections_for_node(target_node)
                except Exception:
                    traceback.print_exc()
            if action == add_input_action and add_input_action:
                prefix = 'option' if tname == 'SelectInt' else 'str'
                pin_type = 'any' if tname == 'SelectInt' else 'string'
                idx = 0
                while f"{prefix}{idx}" in target_node.inputs:
                    idx += 1
                target_node.inputs[f"{prefix}{idx}"] = pin_type
                target_node.setup_pins(target_node.inputs, target_node.outputs)
                self.update_connections_for_node(target_node)
                self.value_changed.emit()

            if action == remove_input_action and remove_input_action:
                prefix = 'option' if tname == 'SelectInt' else 'str'
                dyn_pins = sorted([p for p in target_node.inputs if p.startswith(prefix)], 
                               key=lambda x: int(x.replace(prefix, '')))
                if dyn_pins:
                    last_pin = dyn_pins[-1]
                    # Disconnect all connections to this pin
                    for conn in list(self.connections):
                        if conn.to_node == target_node and conn.to_pin == last_pin:
                            conn.remove()
                            if conn in self.connections:
                                self.connections.remove(conn)
                    del target_node.inputs[last_pin]
                    target_node.setup_pins(target_node.inputs, target_node.outputs)
                    self.update_connections_for_node(target_node)
                    self.value_changed.emit()

            if action == add_output_action and add_output_action:
                new_pin = f"then{len(target_node.output_pins)}"
                target_node.outputs[new_pin] = "exec"
                target_node.setup_pins(target_node.inputs, target_node.outputs)
                self.update_connections_for_node(target_node)
                self.value_changed.emit()
            
            if action == remove_output_action and remove_output_action:
                # Remove last thenN pin
                pins = sorted([p for p in target_node.outputs if p.startswith('then')], 
                            key=lambda x: int(x.replace('then', '')))
                if pins:
                    last_pin = pins[-1]
                    # disconnect
                    for conn in list(self.connections):
                        if conn.from_node == target_node and conn.from_pin == last_pin:
                            conn.remove()
                            if conn in self.connections:
                                self.connections.remove(conn)
                    del target_node.outputs[last_pin]
                    target_node.setup_pins(target_node.inputs, target_node.outputs)
                    self.update_connections_for_node(target_node)
                    self.value_changed.emit()

            if action == change_var_action and change_var_action:
                vars = list(getattr(self, 'graph_variables', {}).keys())
                if vars:
                    new_var, ok = QInputDialog.getItem(self, "Change Variable", "Select Variable:", vars, 0, False)
                    if ok and new_var:
                        # Find the 'name' input widget and update it
                        if hasattr(target_node, 'value_widgets') and 'name' in target_node.value_widgets:
                            proxy = target_node.value_widgets['name']
                            widget = proxy.widget()
                            if isinstance(widget, QLineEdit):
                                widget.setText(new_var)
                                # Force update of pin_values
                                target_node.pin_values['name'] = new_var
                                self.value_changed.emit()
                else:
                    QMessageBox.information(self, "Change Variable", "No variables defined in graph.")
            if action == duplicate_action:
                self.duplicate_selected()
                return
            if action == copy_action:
                self.copy_selected()
                return
            if action == paste_action:
                self.paste()
                return
            if action == rename_action:
                try:
                    tname = getattr(target_node, "template_name", None)
                    current = target_node.title.toPlainText() if getattr(target_node, 'title', None) else ''
                    new_text, ok = QInputDialog.getText(self, "Rename Node", "Name:", text=current)
                    if ok and new_text and new_text.strip():
                        new_name = new_text.strip()
                        # rename pin on composite IO nodes
                        if tname == '__composite_input__':
                            old_pins = list(target_node.output_pins.keys())
                            old = old_pins[0] if old_pins else None
                            if old:
                                # preserve metadata if present
                                meta = target_node.outputs.get(old, {})
                                target_node.outputs = {new_name: meta}
                            else:
                                target_node.outputs = {new_name: {}}
                            target_node.setup_pins(target_node.inputs, target_node.outputs)
                            # update connections referencing old pin
                            for conn in list(self.connections):
                                if getattr(conn, 'from_node', None) is target_node and getattr(conn, 'from_pin', None) == old:
                                    conn.from_pin = new_name
                                if getattr(conn, 'to_node', None) is target_node and getattr(conn, 'to_pin', None) == old:
                                    conn.to_pin = new_name
                        elif tname == '__composite_output__':
                            old_pins = list(target_node.input_pins.keys())
                            old = old_pins[0] if old_pins else None
                            if old:
                                meta = target_node.inputs.get(old, {})
                                target_node.inputs = {new_name: meta}
                            else:
                                target_node.inputs = {new_name: {}}
                            target_node.setup_pins(target_node.inputs, target_node.outputs)
                            for conn in list(self.connections):
                                if getattr(conn, 'from_node', None) is target_node and getattr(conn, 'from_pin', None) == old:
                                    conn.from_pin = new_name
                                if getattr(conn, 'to_node', None) is target_node and getattr(conn, 'to_pin', None) == old:
                                    conn.to_pin = new_name
                        # update title text
                        try:
                            target_node.title.setPlainText(new_name)
                        except Exception:
                            pass
                        # refresh visuals
                        self.update_connections_for_node(target_node)
                except Exception:
                    traceback.print_exc()
            if action == edit_action:
                tname = getattr(target_node, "template_name", None)
                template = None
                if tname:
                    template = get_template(tname)
                if template and template.get("type") == "composite":
                    CompositeEditorDialog = None
                    # Try multiple import strategies so the dialog loads whether
                    # running as a package or as a script.
                    import sys
                    from pathlib import Path
                    parent_dir = Path(__file__).resolve().parent.parent
                    if str(parent_dir) not in sys.path:
                        sys.path.insert(0, str(parent_dir))
                    
                    for modname in ("py_editor.ui.composite_editor", "ui.composite_editor", "composite_editor"):
                        try:
                            mod = importlib.import_module(modname)
                            CompositeEditorDialog = getattr(mod, "CompositeEditorDialog", None)
                            if CompositeEditorDialog:
                                break
                        except Exception:
                            pass

                    if not CompositeEditorDialog:
                        QMessageBox.warning(
                            None,
                            "Composite Editor Unavailable",
                            "Could not import CompositeEditorDialog. See console for details.",
                        )
                    else:
                        # use the top-level window as parent so the modal dialog behaves correctly
                        parent_window = self.window() if hasattr(self, "window") else None
                        try:
                            dlg = CompositeEditorDialog(parent_window, template=template)
                        except Exception:
                            traceback.print_exc()
                            QMessageBox.critical(
                                None,
                                "Error",
                                "Failed to create composite editor dialog. See console for details.",
                            )
                            dlg = None

                        if dlg:
                            try:
                                if dlg.exec():
                                    try:
                                        load_templates()
                                    except Exception:
                                        traceback.print_exc()
                                    if tname:
                                        self.reload_nodes_from_template(tname)
                            except Exception:
                                traceback.print_exc()
                                QMessageBox.critical(
                                    None,
                                    "Error",
                                    "Composite editor crashed while running. See console for details.",
                                )
                else:
                    dlg = NodeEditorDialog(self, template=template)
                    if dlg.exec():
                        try:
                            load_templates()
                        except Exception:
                            pass
                        if tname:
                            self.reload_nodes_from_template(tname)
            
            # Handle breakpoint toggle
            if action == breakpoint_action:
                is_set = target_node.toggle_breakpoint()
                status = "added" if is_set else "removed"
                print(f"Breakpoint {status} on node {target_node.id}: {target_node.title.toPlainText()}")
            
            # Handle Sequence add/remove output pins
            if action == add_output_action and add_output_action:
                try:
                    # Find next available output number
                    existing_nums = []
                    for pin_name in target_node.output_pins.keys():
                        if pin_name.startswith('then'):
                            try:
                                existing_nums.append(int(pin_name[4:]))
                            except ValueError:
                                pass
                    next_num = max(existing_nums) + 1 if existing_nums else 0
                    new_pin_name = f"then{next_num}"
                    
                    # Add the new output pin
                    target_node.outputs[new_pin_name] = "exec"
                    target_node.setup_pins(target_node.inputs, target_node.outputs)
                    self.update_connections_for_node(target_node)
                    print(f"Added output pin '{new_pin_name}' to Sequence node")
                except Exception:
                    traceback.print_exc()
            
            if action == remove_output_action and remove_output_action:
                try:
                    # Remove the last output pin (highest number)
                    existing_nums = []
                    for pin_name in target_node.output_pins.keys():
                        if pin_name.startswith('then'):
                            try:
                                existing_nums.append(int(pin_name[4:]))
                            except ValueError:
                                pass
                    if existing_nums and len(existing_nums) > 2:
                        last_num = max(existing_nums)
                        last_pin = f"then{last_num}"
                        
                        # Remove any connections to this pin
                        for conn in list(self.connections):
                            if getattr(conn, 'from_node', None) is target_node and getattr(conn, 'from_pin', None) == last_pin:
                                self.remove_connection(conn)
                        
                        # Remove the pin
                        if last_pin in target_node.outputs:
                            del target_node.outputs[last_pin]
                        target_node.setup_pins(target_node.inputs, target_node.outputs)
                        self.update_connections_for_node(target_node)
                        print(f"Removed output pin '{last_pin}' from Sequence node")
                except Exception:
                    traceback.print_exc()
            
            # per-user request: delete action removed to avoid crashes
            if action == delete_action:
                try:
                    try:
                        menu.close()
                        QApplication.processEvents()
                    except Exception:
                        pass
                    try:
                        print(f"DEBUG: context-menu single-delete scheduling mark_nodes_for_removal for node id={getattr(target_node,'id',None)}")
                        QTimer.singleShot(0, lambda: self.mark_nodes_for_removal([target_node]))
                    except Exception:
                        print("DEBUG: context-menu single-delete running mark_nodes_for_removal directly")
                        self.mark_nodes_for_removal([target_node])
                    print("DEBUG: context-menu single-delete scheduled/ran removal, returning")
                except Exception:
                    traceback.print_exc()
                return

        else:
            # Right-clicked on empty space - show add node menu with search
            templates = get_all_templates()
            if not templates:
                return
            
            # Show searchable node menu dialog
            from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLineEdit, QTreeWidget, QTreeWidgetItem
            from PyQt6.QtCore import Qt
            
            dialog = QDialog(self)
            dialog.setWindowTitle("Add Node")
            dialog.setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
            dialog.resize(350, 400)
            # Position dialog at cursor
            dialog.move(self.mapToGlobal(point))
            
            layout = QVBoxLayout(dialog)
            layout.setContentsMargins(8, 8, 8, 8)
            layout.setSpacing(4)
            
            # Search box at top (like UE5 blueprints)
            search_box = QLineEdit(dialog)
            search_box.setPlaceholderText("Search for nodes...")
            search_box.setStyleSheet("""
                QLineEdit {
                    padding: 6px;
                    font-size: 13px;
                    border: 2px solid #555;
                    border-radius: 4px;
                    background-color: #2b2b2b;
                    color: #fff;
                }
                QLineEdit:focus {
                    border-color: #0d7dd1;
                }
            """)
            layout.addWidget(search_box)
            
            # Tree widget for categorized nodes
            tree = QTreeWidget(dialog)
            tree.setHeaderHidden(True)
            tree.setStyleSheet("""
                QTreeWidget {
                    background-color: #2b2b2b;
                    border: 1px solid #555;
                    color: #fff;
                    font-size: 12px;
                }
                QTreeWidget::item {
                    padding: 4px;
                }
                QTreeWidget::item:hover {
                    background-color: #3a3a3a;
                }
                QTreeWidget::item:selected {
                    background-color: #0d7dd1;
                }
            """)
            layout.addWidget(tree)
            
            # Group templates by category
            categories = {}
            for template_name, template in templates.items():
                category = template.get('category', 'Other')
                if category not in categories:
                    categories[category] = []
                display_name = template.get('name', template_name)
                categories[category].append((template_name, display_name))
            
            def populate_tree(filter_text=''):
                tree.clear()
                filter_lower = filter_text.lower()
                has_filter = bool(filter_text.strip())
                
                for category in sorted(categories.keys()):
                    # Filter nodes in this category
                    filtered_nodes = []
                    for template_name, display_name in categories[category]:
                        if not filter_text or filter_lower in display_name.lower() or filter_lower in template_name.lower():
                            filtered_nodes.append((template_name, display_name))
                    
                    # Only show category if it has matching nodes
                    if filtered_nodes:
                        category_item = QTreeWidgetItem([category])
                        category_item.setFlags(category_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
                        category_item.setForeground(0, QColor(150, 150, 150))
                        tree.addTopLevelItem(category_item)
                        
                        for template_name, display_name in sorted(filtered_nodes, key=lambda x: x[1]):
                            node_item = QTreeWidgetItem([display_name])
                            node_item.setData(0, Qt.ItemDataRole.UserRole, template_name)
                            category_item.addChild(node_item)
                        
                        # Expand only if there's a search filter
                        category_item.setExpanded(has_filter)
            
            # Initial population
            populate_tree()
            
            # Connect search box to filter
            search_box.textChanged.connect(populate_tree)
            
            # Handle selection
            selected_template = [None]
            
            def on_item_activated(item, column):
                template_name = item.data(0, Qt.ItemDataRole.UserRole)
                if template_name:
                    selected_template[0] = template_name
                    dialog.accept()
            
            def on_item_double_clicked(item, column):
                on_item_activated(item, column)
            
            tree.itemActivated.connect(on_item_activated)
            tree.itemDoubleClicked.connect(on_item_double_clicked)
            
            # Focus search box immediately
            search_box.setFocus()
            
            # Show dialog
            if dialog.exec() == QDialog.DialogCode.Accepted and selected_template[0]:
                self.add_node_from_template(selected_template[0], pos=scene_pt)

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
    
    def _create_call_logic(self, graph_path, pos):
        """Create a CallLogic node - invoke and return.
        
        Fire-and-forget or request-response, stateless by default.
        Like calling a function.
        """
        node = self.add_node_from_template("CallLogic", pos)
        if node:
             node.graph_path = graph_path
             # Set file widget if it exists
             if 'file' in node.value_widgets:
                  node.value_widgets['file'].widget().setText(graph_path)
             # Update title
             from pathlib import Path
             node.title.setPlainText(f"Call: {Path(graph_path).stem}")
        self.graph_changed.emit()

    def _create_scene_object_reference(self, obj_id, obj_name, pos):
        """Create a 'Scene Reference' node for a specific scene object."""
        node = self.add_node_from_template("Scene Reference", pos)
        if node:
            # Set the values in the internal storage
            node.pin_values["object_id"] = obj_id
            
            # Sync to widgets if they are visible
            if "object_id" in node.value_widgets:
                w = node.value_widgets["object_id"].widget()
                if hasattr(w, 'setText'): w.setText(obj_id)
            
            node.title.setPlainText(f"Ref: {obj_name}")
            
        self.graph_changed.emit()


    def _create_reference(self, graph_path, pos):
        """Create a Reference node - opaque handle.
        
        Represents a running or existing instance.
        Can be passed around and messaged, but NEVER inspected.
        No fields. No peeking. Only asking via Message nodes.
        """
        from pathlib import Path
        
        p = Path(graph_path)
        graph_name = p.stem
        
        # Create a Reference node - outputs ONLY an opaque handle
        node = NodeItem(self.next_id, f"Ref: {graph_name}", canvas=self)
        node.template_name = "Reference"
        node.graph_path = graph_path
        self.next_id += 1
        
        # NO inputs (reference is created, not triggered)
        # Single output: opaque handle
        inputs = {}
        outputs = {"handle": "instance"}
        
        node.inputs = inputs
        node.outputs = outputs
        node.setup_pins(inputs, outputs)
        node.process = None
        
        node.pin_values['graphPath'] = graph_path
        
        node.setToolTip(f"Reference: {graph_name}\n\nOpaque handle - can only be messaged, never inspected.\nPass to Message nodes to invoke entry points.")
        
        node.header_color = QColor("#7E57C2")  # Lighter purple
        
        self._scene.addItem(node)
        node.setPos(pos)
        self.nodes.append(node)
        self.save_state()
        
        print(f"Created Reference: {p.name}")
    
    # Keep old name for compatibility
    _create_graph_reference = _create_call_logic
    
    def _create_variable_accessor(self, var_name, var_type, mode, pos):
        """Create a variable Get or Set accessor node"""
        # Use GetVariable or SetVariable template
        template_name = "GetVariable" if mode == "get" else "SetVariable"
        node = self.add_node_from_template(template_name, pos=pos)
        
        if node:
            # Set the variable name in the node's widget values
            node.pin_values['name'] = var_name
            # Update the widget if it exists
            if hasattr(node, 'value_widgets') and 'name' in node.value_widgets:
                proxy_widget = node.value_widgets['name']
                actual_widget = proxy_widget.widget()
                if hasattr(actual_widget, 'setText'):
                    actual_widget.setText(var_name)
            
            print(f"Created {mode} accessor for variable: {var_name}")
    
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

    def start_connection(self, node_item):
        self.pending_from = node_item
        path_item = QGraphicsPathItem()
        
        # Determine if this is an exec connection for styling
        pin_type = None
        if isinstance(node_item, tuple):
            from_node, from_pin = node_item
            if from_pin and hasattr(from_node, 'outputs') and isinstance(from_node.outputs, dict):
                out_def = from_node.outputs.get(from_pin)
                if isinstance(out_def, str):
                    pin_type = out_def
                elif isinstance(out_def, dict):
                    pin_type = out_def.get('type', 'any')
        
        # Style based on pin type - exec is white and thicker
        if pin_type == 'exec':
            pen = QPen(QColor(255, 255, 255), 4)
        else:
            pen = QPen(QColor(120, 160, 255), 3)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        path_item.setPen(pen)
        self._scene.addItem(path_item)
        self.pending_line = path_item

    def finish_connection(self, node_item):
        if not self.pending_from:
            return
        if isinstance(self.pending_from, tuple):
            from_node, from_pin = self.pending_from
        else:
            from_node, from_pin = (self.pending_from, None)
        if isinstance(node_item, tuple):
            to_node, to_pin = node_item
        else:
            to_node, to_pin = (node_item, None)
        
        # Validate connection types
        if not self._validate_connection_types(from_node, from_pin, to_node, to_pin):
            print(f"Type mismatch: Cannot connect {from_pin} to {to_pin}")
            # Clean up pending line
            if self.pending_line:
                try:
                    self._scene.removeItem(self.pending_line)
                except Exception:
                    pass
            self.pending_line = None
            self.pending_from = None
            return
        
        conn = ConnectionItem(from_node, to_node, self)
        conn.from_pin = from_pin
        conn.to_pin = to_pin
        conn.add_to_scene(self._scene)
        self.connections.append(conn)
        if self.pending_line:
            try:
                self._scene.removeItem(self.pending_line)
            except Exception:
                pass
        self.pending_line = None
        self.pending_from = None
        
        # Save state for undo after creating connection
        self.save_state()
    
    def _validate_connection_types(self, from_node, from_pin, to_node, to_pin):
        """Validate that connection types are compatible"""
        if not from_pin or not to_pin:
            return True  # Allow connections without explicit pins
        
        # Get output type from source node
        from_type = None
        if hasattr(from_node, 'outputs') and isinstance(from_node.outputs, dict):
            from_type = from_node.outputs.get(from_pin)
            if isinstance(from_type, dict):
                from_type = from_type.get('type', 'any')
        
        # Get input type from target node
        to_type = None
        if hasattr(to_node, 'inputs') and isinstance(to_node.inputs, dict):
            to_type = to_node.inputs.get(to_pin)
            if isinstance(to_type, dict):
                to_type = to_type.get('type', 'any')
        
        # No type info means allow connection
        if not from_type or not to_type:
            return True
        
        # 'any' type matches everything
        if from_type == 'any' or to_type == 'any':
            return True
        
        # Exact type match
        if from_type == to_type:
            return True
        
        # Numeric compatibility: int can connect to float
        if from_type == 'int' and to_type == 'float':
            return True
        
        # Object compatibility: string/ID can connect to object input
        if (from_type == 'string' and to_type == 'object') or (from_type == 'object' and to_type == 'string'):
            return True
        
        # Otherwise, types don't match - offer to insert converter
        converter = self._get_converter_for_types(from_type, to_type)
        if converter:
            # Ask user if they want to auto-insert a converter
            from PyQt6.QtWidgets import QMessageBox
            reply = QMessageBox.question(
                self, "Type Mismatch",
                f"Cannot directly connect {from_type} to {to_type}.\n\nInsert a '{converter}' converter node?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                # Store info for after the dialog closes
                self._pending_converter = {
                    'converter': converter,
                    'from_node': from_node,
                    'from_pin': from_pin,
                    'to_node': to_node,
                    'to_pin': to_pin
                }
                # Use a timer to insert after this validation returns
                from PyQt6.QtCore import QTimer
                QTimer.singleShot(0, self._insert_pending_converter)
                return False  # Don't create direct connection
        
        return False
    
    def _get_converter_for_types(self, from_type, to_type):
        """Get the appropriate converter node name for a type conversion"""
        converters = {
            ('float', 'int'): 'ToInt',
            ('float', 'string'): 'ToString',
            ('float', 'bool'): 'ToBool',
            ('int', 'string'): 'ToString',
            ('int', 'bool'): 'ToBool',
            ('string', 'int'): 'ToInt',
            ('string', 'float'): 'ToFloat',
            ('string', 'bool'): 'ToBool',
            ('bool', 'int'): 'ToInt',
            ('bool', 'float'): 'ToFloat',
            ('bool', 'string'): 'ToString',
        }
        return converters.get((from_type, to_type))
    
    def _insert_pending_converter(self):
        """Insert a converter node between mismatched types"""
        if not hasattr(self, '_pending_converter') or not self._pending_converter:
            return
        
        info = self._pending_converter
        self._pending_converter = None
        
        from_node = info['from_node']
        to_node = info['to_node']
        converter_name = info['converter']
        
        # Position the converter between the two nodes
        from_pos = from_node.pos()
        to_pos = to_node.pos()
        mid_x = (from_pos.x() + to_pos.x()) / 2
        mid_y = (from_pos.y() + to_pos.y()) / 2
        
        # Create the converter node
        converter_node = self.add_node_from_template(converter_name, pos=QPointF(mid_x, mid_y))
        if not converter_node:
            return
        
        # Connect from_node -> converter
        conn1 = ConnectionItem(from_node, converter_node, self)
        conn1.from_pin = info['from_pin']
        conn1.to_pin = 'value'  # Converter nodes have 'value' input
        conn1.add_to_scene(self._scene)
        self.connections.append(conn1)
        
        # Connect converter -> to_node
        conn2 = ConnectionItem(converter_node, to_node, self)
        conn2.from_pin = 'result'  # Converter nodes have 'result' output
        conn2.to_pin = info['to_pin']
        conn2.add_to_scene(self._scene)
        self.connections.append(conn2)
        
        self.save_state()
        print(f"Inserted {converter_name} converter between {from_node.title.toPlainText()} and {to_node.title.toPlainText()}")
    
    def _show_connection_node_menu(self, scene_pos, screen_pos):
        """Show a filtered node menu when releasing a connection on empty space"""
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLineEdit, QTreeWidget, QTreeWidgetItem
        from PyQt6.QtCore import Qt
        from py_editor.core.node_templates import get_all_templates
        
        # Get the source pin type
        source_type = None
        source_node = None
        source_pin = None
        if isinstance(self.pending_from, tuple):
            source_node, source_pin = self.pending_from
            if hasattr(source_node, 'outputs') and isinstance(source_node.outputs, dict):
                source_type = source_node.outputs.get(source_pin)
                if isinstance(source_type, dict):
                    source_type = source_type.get('type', 'any')
        
        templates = get_all_templates()
        if not templates:
            self._cancel_pending_connection()
            return
        
        # Create dialog
        dialog = QDialog(self)
        dialog.setWindowTitle("Select Node")
        dialog.setMinimumSize(300, 400)
        dialog.setStyleSheet("""
            QDialog { background: #2b2b2b; }
            QLineEdit { 
                background: #3c3c3c; 
                color: white; 
                border: 1px solid #555; 
                padding: 8px; 
                font-size: 14px;
                border-radius: 4px;
            }
            QTreeWidget { 
                background: #2b2b2b; 
                color: white; 
                border: none; 
            }
            QTreeWidget::item { padding: 4px; }
            QTreeWidget::item:hover { background: #3a3a3a; }
            QTreeWidget::item:selected { background: #0d6efd; }
        """)
        
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(8, 8, 8, 8)
        
        # Search box
        search_box = QLineEdit()
        search_box.setPlaceholderText("Search compatible nodes...")
        layout.addWidget(search_box)
        
        # Tree widget
        tree = QTreeWidget()
        tree.setHeaderHidden(True)
        tree.setRootIsDecorated(True)
        layout.addWidget(tree)
        
        # Build tree with compatible nodes first
        def get_compatible_nodes():
            """Get nodes that can accept the source type as input"""
            compatible = []
            conversion = []
            other = []
            
            for name, template in templates.items():
                if name.startswith('__'):
                    continue
                
                inputs = template.get('inputs', {})
                category = template.get('category', 'Other')
                
                # Check if any input accepts our source type
                is_compatible = False
                is_conversion = category == 'Conversion'
                
                for pin_name, pin_type in inputs.items():
                    if isinstance(pin_type, dict):
                        pin_type = pin_type.get('type', 'any')
                    
                    # Check compatibility
                    if pin_type == 'any' or pin_type == source_type:
                        is_compatible = True
                        break
                    # int -> float is compatible
                    if source_type == 'int' and pin_type == 'float':
                        is_compatible = True
                        break
                
                if is_conversion:
                    conversion.append((name, template))
                elif is_compatible:
                    compatible.append((name, template))
                else:
                    other.append((name, template))
            
            return compatible, conversion, other
        
        compatible, conversion, other = get_compatible_nodes()
        
        def populate_tree(filter_text=""):
            tree.clear()
            filter_lower = filter_text.lower()
            
            # Group by category
            categories = {}
            
            # Add compatible nodes first (marked)
            for name, template in compatible:
                if filter_lower and filter_lower not in name.lower():
                    continue
                cat = "★ Compatible"
                if cat not in categories:
                    categories[cat] = []
                categories[cat].append((name, template))
            
            # Add conversion nodes
            for name, template in conversion:
                if filter_lower and filter_lower not in name.lower():
                    continue
                cat = "⟳ Conversion"
                if cat not in categories:
                    categories[cat] = []
                categories[cat].append((name, template))
            
            # Add other nodes
            for name, template in other:
                if filter_lower and filter_lower not in name.lower():
                    continue
                cat = template.get('category', 'Other')
                if cat not in categories:
                    categories[cat] = []
                categories[cat].append((name, template))
            
            # Create tree items
            for cat in sorted(categories.keys(), key=lambda x: (0 if x.startswith('★') else 1 if x.startswith('⟳') else 2, x)):
                cat_item = QTreeWidgetItem([cat])
                cat_item.setExpanded(cat.startswith('★') or cat.startswith('⟳') or bool(filter_text))
                tree.addTopLevelItem(cat_item)
                
                for name, template in sorted(categories[cat], key=lambda x: x[0]):
                    node_item = QTreeWidgetItem([name])
                    node_item.setData(0, Qt.ItemDataRole.UserRole, (name, template))
                    cat_item.addChild(node_item)
        
        populate_tree()
        search_box.textChanged.connect(populate_tree)
        
        selected_template = [None]
        
        def on_item_double_clicked(item, column):
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if data:
                selected_template[0] = data
                dialog.accept()
        
        def on_item_activated(item, column):
            on_item_double_clicked(item, column)
        
        tree.itemDoubleClicked.connect(on_item_double_clicked)
        tree.itemActivated.connect(on_item_activated)
        
        # Show dialog
        if dialog.exec() and selected_template[0]:
            name, template = selected_template[0]
            # Create the node
            new_node = self.add_node_from_template(name, pos=scene_pos)
            
            if new_node and source_node and source_pin:
                # Find a compatible input pin on the new node
                target_pin = None
                inputs = template.get('inputs', {})
                for pin_name, pin_type in inputs.items():
                    if isinstance(pin_type, dict):
                        pin_type = pin_type.get('type', 'any')
                    if pin_type == 'any' or pin_type == source_type:
                        target_pin = pin_name
                        break
                    if source_type == 'int' and pin_type == 'float':
                        target_pin = pin_name
                        break
                
                # If no exact match, use first input
                if not target_pin and inputs:
                    target_pin = list(inputs.keys())[0]
                
                if target_pin:
                    # Create connection
                    conn = ConnectionItem(source_node, new_node, self)
                    conn.from_pin = source_pin
                    conn.to_pin = target_pin
                    conn.add_to_scene(self._scene)
                    self.connections.append(conn)
                    self.save_state()
        
        # Clean up pending connection
        self._cancel_pending_connection()
    
    def _cancel_pending_connection(self):
        """Cancel the pending connection and clean up"""
        if self.pending_line:
            try:
                self._scene.removeItem(self.pending_line)
            except Exception:
                pass
        self.pending_line = None
        self.pending_from = None
        self._is_connecting = False
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)

    def _collect_internal_input_names(self):
        names = set()
        for node in self.nodes:
            if isinstance(node, NodeItem) and node is not None:
                for n in node.input_pins.keys():
                    names.add(n)
        return sorted(names)

    def _collect_internal_output_names(self):
        names = set()
        for node in self.nodes:
            if isinstance(node, NodeItem) and node is not None:
                for n in node.output_pins.keys():
                    names.add(n)
        return sorted(names)

    def _add_composite_input_node(self, pos):
        # determine pin names: prefer host_template inputs; do NOT infer from internal nodes
        # (automatic inference creates duplicates — only use explicit host template mappings)
        names = []
        if getattr(self, 'host_template', None) and isinstance(self.host_template.get('inputs', None), dict):
            names = list(self.host_template.get('inputs', {}).keys())
        outputs = {n: {} for n in names} if names else { 'out0': {} }
        node = NodeItem(self.next_id, "Composite Input", canvas=self)
        node.template_name = "__composite_input__"
        self.next_id += 1
        node.setup_pins({}, outputs)
        self._scene.addItem(node)
        node.setPos(pos)
        self.nodes.append(node)

    def _add_composite_output_node(self, pos):
        # determine pin names: prefer host_template outputs; do NOT infer from internal nodes
        names = []
        if getattr(self, 'host_template', None) and isinstance(self.host_template.get('outputs', None), dict):
            names = list(self.host_template.get('outputs', {}).keys())
        inputs = {n: {} for n in names} if names else { 'in0': {} }
        node = NodeItem(self.next_id, "Composite Output", canvas=self)
        node.template_name = "__composite_output__"
        self.next_id += 1
        node.setup_pins(inputs, {})
        self._scene.addItem(node)
        node.setPos(pos)
        self.nodes.append(node)


# Backward compatibility alias - deprecated, use LogicEditor instead
CanvasView = LogicEditor
