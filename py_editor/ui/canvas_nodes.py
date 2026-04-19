"""
canvas_nodes.py

Node lifecycle helpers for LogicEditor: AI-driven connection compatibility,
pin-name alias resolution, ``add_connection_by_id``, node-category coloring,
and the widget injection used by const/template nodes. These are the bits that
build or mutate a node's visual state without touching the scene view,
clipboard, or file IO, so they sit cleanly in one mixin.
"""
from PyQt6.QtWidgets import (
    QGraphicsProxyWidget, QLineEdit, QComboBox, QWidget, QHBoxLayout, QLabel,
)
from PyQt6.QtGui import QColor, QLinearGradient, QPen
from PyQt6.QtCore import Qt, QTimer


class NodesMixin:
    """Pin/type helpers, connection by ID, node coloring and embedded widgets."""

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

    def _add_const_value_widget(self, node, template_name):
        """Add a value input widget to a const node"""
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
