"""
canvas_connections.py

Pin-to-pin connection handling for LogicEditor: start/finish the dragging
rubber band, validate types, offer an auto-inserted converter node, and
the "drop on empty space" dialog that lets the user pick a compatible
node to spawn and auto-wire. Split out of ``canvas.py`` because these
~400 lines are entirely concerned with a single interaction (creating
connections) and never touch painting, serialisation, or removal.
"""
from PyQt6.QtWidgets import QGraphicsPathItem, QGraphicsView
from PyQt6.QtGui import QPen, QColor
from PyQt6.QtCore import Qt, QPointF, QTimer

from py_editor.ui.connection_item import ConnectionItem


class ConnectionsMixin:
    """Mixin providing connection creation/validation on LogicEditor."""

    def start_connection(self, node_item):
        self.pending_from = node_item
        path_item = QGraphicsPathItem()

        pin_type = None
        if isinstance(node_item, tuple):
            from_node, from_pin = node_item
            if from_pin and hasattr(from_node, 'outputs') and isinstance(from_node.outputs, dict):
                out_def = from_node.outputs.get(from_pin)
                if isinstance(out_def, str):
                    pin_type = out_def
                elif isinstance(out_def, dict):
                    pin_type = out_def.get('type', 'any')

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

        if not self._validate_connection_types(from_node, from_pin, to_node, to_pin):
            print(f"Type mismatch: Cannot connect {from_pin} to {to_pin}")
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

        self.save_state()

    def _validate_connection_types(self, from_node, from_pin, to_node, to_pin):
        """Validate that connection types are compatible"""
        if not from_pin or not to_pin:
            return True

        from_type = None
        if hasattr(from_node, 'outputs') and isinstance(from_node.outputs, dict):
            from_type = from_node.outputs.get(from_pin)
            if isinstance(from_type, dict):
                from_type = from_type.get('type', 'any')

        to_type = None
        if hasattr(to_node, 'inputs') and isinstance(to_node.inputs, dict):
            to_type = to_node.inputs.get(to_pin)
            if isinstance(to_type, dict):
                to_type = to_type.get('type', 'any')

        if not from_type or not to_type:
            return True

        if from_type == 'any' or to_type == 'any':
            return True

        if from_type == to_type:
            return True

        if from_type == 'int' and to_type == 'float':
            return True

        if (from_type == 'string' and to_type == 'object') or (from_type == 'object' and to_type == 'string'):
            return True

        converter = self._get_converter_for_types(from_type, to_type)
        if converter:
            from PyQt6.QtWidgets import QMessageBox
            reply = QMessageBox.question(
                self, "Type Mismatch",
                f"Cannot directly connect {from_type} to {to_type}.\n\nInsert a '{converter}' converter node?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._pending_converter = {
                    'converter': converter,
                    'from_node': from_node,
                    'from_pin': from_pin,
                    'to_node': to_node,
                    'to_pin': to_pin
                }
                QTimer.singleShot(0, self._insert_pending_converter)
                return False

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

        from_pos = from_node.pos()
        to_pos = to_node.pos()
        mid_x = (from_pos.x() + to_pos.x()) / 2
        mid_y = (from_pos.y() + to_pos.y()) / 2

        converter_node = self.add_node_from_template(converter_name, pos=QPointF(mid_x, mid_y))
        if not converter_node:
            return

        conn1 = ConnectionItem(from_node, converter_node, self)
        conn1.from_pin = info['from_pin']
        conn1.to_pin = 'value'
        conn1.add_to_scene(self._scene)
        self.connections.append(conn1)

        conn2 = ConnectionItem(converter_node, to_node, self)
        conn2.from_pin = 'result'
        conn2.to_pin = info['to_pin']
        conn2.add_to_scene(self._scene)
        self.connections.append(conn2)

        self.save_state()
        print(f"Inserted {converter_name} converter between {from_node.title.toPlainText()} and {to_node.title.toPlainText()}")

    def _show_connection_node_menu(self, scene_pos, screen_pos):
        """Show a filtered node menu when releasing a connection on empty space"""
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLineEdit, QTreeWidget, QTreeWidgetItem
        from py_editor.core.node_templates import get_all_templates

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

        search_box = QLineEdit()
        search_box.setPlaceholderText("Search compatible nodes...")
        layout.addWidget(search_box)

        tree = QTreeWidget()
        tree.setHeaderHidden(True)
        tree.setRootIsDecorated(True)
        layout.addWidget(tree)

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

                is_compatible = False
                is_conversion = category == 'Conversion'

                for pin_name, pin_type in inputs.items():
                    if isinstance(pin_type, dict):
                        pin_type = pin_type.get('type', 'any')

                    if pin_type == 'any' or pin_type == source_type:
                        is_compatible = True
                        break
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

            categories = {}

            for name, template in compatible:
                if filter_lower and filter_lower not in name.lower():
                    continue
                cat = "\u2605 Compatible"
                if cat not in categories:
                    categories[cat] = []
                categories[cat].append((name, template))

            for name, template in conversion:
                if filter_lower and filter_lower not in name.lower():
                    continue
                cat = "\u27f3 Conversion"
                if cat not in categories:
                    categories[cat] = []
                categories[cat].append((name, template))

            for name, template in other:
                if filter_lower and filter_lower not in name.lower():
                    continue
                cat = template.get('category', 'Other')
                if cat not in categories:
                    categories[cat] = []
                categories[cat].append((name, template))

            for cat in sorted(categories.keys(), key=lambda x: (0 if x.startswith('\u2605') else 1 if x.startswith('\u27f3') else 2, x)):
                cat_item = QTreeWidgetItem([cat])
                cat_item.setExpanded(cat.startswith('\u2605') or cat.startswith('\u27f3') or bool(filter_text))
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

        if dialog.exec() and selected_template[0]:
            name, template = selected_template[0]
            new_node = self.add_node_from_template(name, pos=scene_pos)

            if new_node and source_node and source_pin:
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

                if not target_pin and inputs:
                    target_pin = list(inputs.keys())[0]

                if target_pin:
                    conn = ConnectionItem(source_node, new_node, self)
                    conn.from_pin = source_pin
                    conn.to_pin = target_pin
                    conn.add_to_scene(self._scene)
                    self.connections.append(conn)
                    self.save_state()

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
