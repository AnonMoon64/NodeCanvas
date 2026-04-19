"""
canvas_factories.py

Specialised node-creation helpers used by the context menu and drag-drop
handlers: CallLogic, Scene Reference, Reference (opaque handle), and
variable Get/Set accessors. Split out of ``canvas.py`` because these
builders each do bespoke widget seeding / title rewriting that doesn't
belong in the generic ``add_node_from_template`` path.
"""
from pathlib import Path

from PyQt6.QtGui import QColor

from py_editor.ui.node_item import NodeItem


class FactoriesMixin:
    """Mixin providing specialised node-creation helpers on LogicEditor."""

    def _create_call_logic(self, graph_path, pos):
        """Create a CallLogic node - invoke and return."""
        node = self.add_node_from_template("CallLogic", pos)
        if node:
            node.graph_path = graph_path
            if 'file' in node.value_widgets:
                node.value_widgets['file'].widget().setText(graph_path)
            node.title.setPlainText(f"Call: {Path(graph_path).stem}")
        self.graph_changed.emit()

    def _create_scene_object_reference(self, obj_id, obj_name, pos):
        """Create a 'Scene Reference' node for a specific scene object."""
        node = self.add_node_from_template("Scene Reference", pos)
        if node:
            node.pin_values["object_id"] = obj_id

            if "object_id" in node.value_widgets:
                w = node.value_widgets["object_id"].widget()
                if hasattr(w, 'setText'):
                    w.setText(obj_id)

            node.title.setPlainText(f"Ref: {obj_name}")

        self.graph_changed.emit()

    def _create_reference(self, graph_path, pos):
        """Create a Reference node - opaque handle."""
        p = Path(graph_path)
        graph_name = p.stem

        node = NodeItem(self.next_id, f"Ref: {graph_name}", canvas=self)
        node.template_name = "Reference"
        node.graph_path = graph_path
        self.next_id += 1

        inputs = {}
        outputs = {"handle": "instance"}

        node.inputs = inputs
        node.outputs = outputs
        node.setup_pins(inputs, outputs)
        node.process = None

        node.pin_values['graphPath'] = graph_path

        node.setToolTip(f"Reference: {graph_name}\n\nOpaque handle - can only be messaged, never inspected.\nPass to Message nodes to invoke entry points.")

        node.header_color = QColor("#7E57C2")

        self._scene.addItem(node)
        node.setPos(pos)
        self.nodes.append(node)
        self.save_state()

        print(f"Created Reference: {p.name}")

    _create_graph_reference = _create_call_logic

    def _create_variable_accessor(self, var_name, var_type, mode, pos):
        """Create a variable Get or Set accessor node"""
        template_name = "GetVariable" if mode == "get" else "SetVariable"
        node = self.add_node_from_template(template_name, pos=pos)

        if node:
            node.pin_values['name'] = var_name
            if hasattr(node, 'value_widgets') and 'name' in node.value_widgets:
                proxy_widget = node.value_widgets['name']
                actual_widget = proxy_widget.widget()
                if hasattr(actual_widget, 'setText'):
                    actual_widget.setText(var_name)

            print(f"Created {mode} accessor for variable: {var_name}")
