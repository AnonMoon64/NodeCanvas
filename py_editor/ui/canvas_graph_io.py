"""
canvas_graph_io.py

Serialisation for LogicEditor: ``load_graph`` rebuilds the scene from a dict,
``export_graph`` produces a JSON-ready dict. Split out of ``canvas.py`` because
these two methods alone were ~265 lines of self-contained node/connection
(de)serialisation logic that never touches input handling, painting, or
clipboard — mixing them in was pure weight on the main canvas file.

LogicEditor inherits from ``GraphIOMixin``; nothing else changes.
"""
from pathlib import Path

from PyQt6.QtWidgets import QComboBox, QLineEdit
from PyQt6.QtCore import QPointF, QTimer

from py_editor.ui.connection_item import ConnectionItem


class GraphIOMixin:
    """Mixin providing ``load_graph`` and ``export_graph`` on ``LogicEditor``.

    Depends on these attributes being present on ``self`` (set up by
    ``LogicEditor.__init__``): ``graph_variables``, ``connections``, ``nodes``,
    ``_scene``, ``next_id``, ``graph_changed``, ``value_changed``.
    """

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
