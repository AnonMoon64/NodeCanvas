"""
canvas_composite.py

Composite-graph I/O node management: composite graphs expose pin rows on
their parent node, so the sub-canvas needs special "Composite Input" and
"Composite Output" nodes that mirror those rows. Split out of
``canvas.py`` because these helpers only touch ``host_template`` and pin
name bookkeeping — nothing else in the editor uses them.
"""
from py_editor.ui.node_item import NodeItem


class CompositeMixin:
    """Mixin providing composite input/output node helpers on LogicEditor."""

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
        names = []
        if getattr(self, 'host_template', None) and isinstance(self.host_template.get('inputs', None), dict):
            names = list(self.host_template.get('inputs', {}).keys())
        outputs = {n: {} for n in names} if names else {'out0': {}}
        node = NodeItem(self.next_id, "Composite Input", canvas=self)
        node.template_name = "__composite_input__"
        self.next_id += 1
        node.setup_pins({}, outputs)
        self._scene.addItem(node)
        node.setPos(pos)
        self.nodes.append(node)

    def _add_composite_output_node(self, pos):
        names = []
        if getattr(self, 'host_template', None) and isinstance(self.host_template.get('outputs', None), dict):
            names = list(self.host_template.get('outputs', {}).keys())
        inputs = {n: {} for n in names} if names else {'in0': {}}
        node = NodeItem(self.next_id, "Composite Output", canvas=self)
        node.template_name = "__composite_output__"
        self.next_id += 1
        node.setup_pins(inputs, {})
        self._scene.addItem(node)
        node.setPos(pos)
        self.nodes.append(node)
