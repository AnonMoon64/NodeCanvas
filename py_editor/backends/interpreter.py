"""
Backend execution system for NodeCanvas.
Converts canvas graphs to IR and executes them.
"""
from typing import Dict, Any, Optional, List
from pathlib import Path
import traceback

import sys
from pathlib import Path as PathLib

# Add parent directory to path for imports
if __name__ == '__main__' or 'py_editor' not in sys.modules:
    parent_dir = PathLib(__file__).resolve().parent.parent
    if str(parent_dir) not in sys.path:
        sys.path.insert(0, str(parent_dir))

try:
    from py_editor.core.ir import (
        IRModule, NodeId, Value, ValueType,
        ConstValue, Add, Subtract, Multiply, Divide, Return, Print, SetVar, GetVar, Custom
    )
except:
    try:
        from .ir import (
            IRModule, NodeId, Value, ValueType,
            ConstValue, Add, Subtract, Multiply, Divide, Return, Print, SetVar, GetVar, Custom
        )
    except:
        from core.ir import (
            IRModule, NodeId, Value, ValueType,
            ConstValue, Add, Subtract, Multiply, Divide, Return, Print, SetVar, GetVar, Custom
        )


class ExecutionContext:
    """Context for executing an IR graph"""
    
    def __init__(self):
        self.values: Dict[int, Any] = {}  # NodeId.id -> computed value
        self.errors: Dict[int, str] = {}  # NodeId.id -> error message
        self.ir_module: Optional[IRModule] = None
        self.variables: Dict[str, Any] = {}  # Variable name -> value storage
        
        # Step execution support
        self.step_mode: bool = False  # Whether to execute step-by-step
        self.breakpoints: set = set()  # Set of IR node IDs with breakpoints
        self.paused_at: Optional[int] = None  # IR node ID where execution is paused
        self.execution_order: List = []  # Track execution order for replay
    
    def set_value(self, node_id: NodeId, value: Any):
        """Store computed value for a node"""
        self.values[node_id.id] = value
    
    def get_value(self, node_id: NodeId) -> Any:
        """Retrieve computed value for a node"""
        return self.values.get(node_id.id)
    
    def has_value(self, node_id: NodeId) -> bool:
        """Check if a node has been computed"""
        return node_id.id in self.values
    
    def set_error(self, node_id: NodeId, error: str):
        """Store error message for a node"""
        self.errors[node_id.id] = error
    
    def get_error(self, node_id: NodeId) -> Optional[str]:
        """Retrieve error message for a node"""
        return self.errors.get(node_id.id)
    
    def has_error(self, node_id: NodeId) -> bool:
        """Check if a node has an error"""
        return node_id.id in self.errors


class IRBackend:
    """Backend for converting canvas graphs to IR and executing them"""
    
    def __init__(self):
        self.module = IRModule()
        self.canvas_to_ir_map: Dict[int, int] = {}  # canvas node ID -> IR node ID

    @staticmethod
    def _coerce_pin_value(value, pin_type: Optional[str]):
        """Convert widget/default values to the correct type for composite inputs."""
        if value is None or pin_type is None:
            return value
        try:
            if pin_type == 'int':
                if isinstance(value, bool):
                    return int(value)
                if isinstance(value, (int, float)):
                    return int(value)
                return int(str(value).strip())
            if pin_type == 'float':
                if isinstance(value, bool):
                    return float(value)
                if isinstance(value, (int, float)):
                    return float(value)
                return float(str(value).strip())
            if pin_type == 'bool':
                if isinstance(value, bool):
                    return value
                if isinstance(value, (int, float)):
                    return value != 0
                text = str(value).strip().lower()
                return text in ('true', '1', 'yes', 'on')
            if pin_type == 'string':
                return str(value)
        except Exception:
            pass
        return value
    
    def canvas_to_ir(self, canvas_graph: dict, node_templates: dict) -> IRModule:
        """
        Convert a canvas graph to IR module.
        
        Args:
            canvas_graph: Graph data from canvas.export_graph()
            node_templates: Map of template name -> template data
        
        Returns:
            IRModule with nodes and connections
        """
        self.module = IRModule()
        
        # Map canvas node ID -> IR NodeId
        node_map: Dict[int, NodeId] = {}
        self.canvas_to_ir_map.clear()
        
        # First pass: create all nodes
        for canvas_node in canvas_graph.get('nodes', []):
            canvas_id = canvas_node['id']
            template_name = canvas_node.get('template')
            pos = canvas_node.get('pos', [0, 0])
            values = canvas_node.get('values', {})  # Get input values from canvas
            
            # Debug: Show what values we're getting
            if values:
                print(f"Creating {template_name} node with values: {values}")
            
            # Create IR node with values
            ir_node_id = self._create_ir_node(template_name, node_templates, values)
            if ir_node_id:
                node_map[canvas_id] = ir_node_id
                node_map[str(canvas_id)] = ir_node_id
                # Store mapping from canvas ID to IR ID
                self.canvas_to_ir_map[canvas_id] = ir_node_id.id
                # Store layout info
                self.module.layout[ir_node_id.id] = (pos[0], pos[1])
                # Store widget values for nodes that aren't constants
                if values and template_name not in ['ConstInt', 'ConstFloat', 'ConstBool', 'ConstString']:
                    self.module.widget_values[ir_node_id.id] = values
        
        # Second pass: connect nodes based on connections
        connections = canvas_graph.get('connections', [])
        self._apply_connections(connections, node_map, node_templates)
        
        return self.module
    
    def _create_ir_node(self, template_name: Optional[str], node_templates: dict, values: dict = None) -> Optional[NodeId]:
        """Create an IR node from a template"""
        if not template_name:
            return None
        
        if values is None:
            values = {}
        
        # Handle constant nodes - use values from canvas if available
        if template_name == 'ConstInt':
            val = values.get('value', 0)
            # Convert to int if needed
            if isinstance(val, str):
                try:
                    val = int(val)
                except ValueError:
                    val = 0
            return self.module.add_const_int(val)
        elif template_name == 'ConstFloat':
            val = values.get('value', 0.0)
            # Convert to float if needed
            if isinstance(val, str):
                try:
                    val = float(val)
                except ValueError:
                    val = 0.0
            return self.module.add_const_float(val)
        elif template_name == 'ConstBool':
            val = values.get('value', False)
            # Convert to bool if needed
            if isinstance(val, str):
                val = val.lower() in ('true', '1', 'yes')
            return self.module.add_const_bool(bool(val))
        elif template_name == 'ConstString':
            val = values.get('value', '')
            return self.module.add_const_string(str(val))
        
        # Handle operation nodes
        elif template_name == 'Add':
            return self.module.add_add()
        elif template_name == 'Subtract':
            return self.module.add_subtract()
        elif template_name == 'Multiply':
            return self.module.add_multiply()
        elif template_name == 'Divide':
            return self.module.add_divide()
        elif template_name == 'Return':
            return self.module.add_return()
        elif template_name == 'Print':
            return self.module.add_print()
        elif template_name == 'SetVariable':
            return self.module.add_setvar()
        elif template_name == 'GetVariable':
            return self.module.add_getvar()
        
        # Handle custom nodes (including composites)
        else:
            template = node_templates.get(template_name)
            if template:
                inputs = len(template.get('inputs', {}))
                outputs = len(template.get('outputs', {}))
                node_id = self.module.add_custom(template_name, inputs, outputs)
                # Store template reference for composite execution
                if template.get('type') == 'composite':
                    if not hasattr(self.module, 'composite_templates'):
                        self.module.composite_templates = {}
                    self.module.composite_templates[node_id.id] = template
                return node_id
        
        return None
    
    def _apply_connections(self, connections: List[dict], node_map: Dict[int, NodeId], 
                          node_templates: dict):
        """Apply connections to IR nodes"""
        
        print(f"\nApplying {len(connections)} connections:")
        for conn in connections:
            print(f"  {conn.get('from')} ({conn.get('from_pin')}) -> {conn.get('to')} ({conn.get('to_pin')})")
        
        # Group connections by target node (to_id) and normalize id types
        connections_by_target: Dict[int, List[dict]] = {}
        def _to_int(val):
            try:
                return int(val)
            except Exception:
                return val

        normalized_connections = []
        for conn in connections:
            nconn = dict(conn)
            nconn['_from_int'] = _to_int(conn.get('from'))
            nconn['_to_int'] = _to_int(conn.get('to'))
            normalized_connections.append(nconn)

        for conn in normalized_connections:
            to_id = conn.get('_to_int')
            if to_id not in connections_by_target:
                connections_by_target[to_id] = []
            connections_by_target[to_id].append(conn)

        # Also track connections BY SOURCE (from_id, from_pin) -> list of to_ids
        # This is needed for flow control nodes like Sequence
        for conn in normalized_connections:
            from_id = conn.get('_from_int')
            from_pin = conn.get('from_pin', '')
            to_id = conn.get('_to_int')
            
            # Get the IR node ID for from_id
            from_ir_id = node_map.get(from_id)
            to_ir_id = node_map.get(to_id)
            
            if from_ir_id and to_ir_id:
                key = (from_ir_id.id, from_pin)
                if key not in self.module.output_connections:
                    self.module.output_connections[key] = []
                if to_ir_id.id not in self.module.output_connections[key]:
                    self.module.output_connections[key].append(to_ir_id.id)
        def _lookup_ir(node_id_value):
            if node_id_value is None:
                return None
            if node_id_value in node_map:
                return node_map.get(node_id_value)
            # Try string/int fallback
            try:
                alt = str(int(node_id_value))
                if alt in node_map:
                    return node_map[alt]
            except Exception:
                pass
            alt = str(node_id_value)
            return node_map.get(alt)
        
        # Update each node with its input connections
        for canvas_id, ir_node_id in node_map.items():
            node = self.module.find_node(ir_node_id)
            if not node:
                continue
            
            # Get connections targeting this node (canvas IDs may be int or str)
            target_conns = connections_by_target.get(canvas_id, [])
            if not target_conns:
                target_conns = connections_by_target.get(str(canvas_id), [])
            if not target_conns:
                try:
                    target_conns = connections_by_target.get(int(canvas_id), [])
                except Exception:
                    target_conns = []
            if not target_conns:
                int_id = _to_int(canvas_id)
                alt_conns = [c for c in normalized_connections if c.get('_to_int') == int_id]
                if alt_conns:
                    print(f"DEBUG found alternate connections for canvas node {canvas_id}: {alt_conns}")
                    target_conns = alt_conns
            if target_conns:
                print(f"DEBUG connections for canvas node {canvas_id}: {target_conns}")
            
            # Update node kind based on connections
            kind = node.kind
            if isinstance(kind, (Add, Subtract, Multiply, Divide)):
                # Binary operations
                for conn in target_conns:
                    to_pin = conn.get('to_pin')
                    from_id = conn.get('_from_int') if '_from_int' in conn else conn.get('from')
                    from_ir_id = _lookup_ir(from_id)
                    
                    if to_pin == 'a' and from_ir_id:
                        kind.a = from_ir_id
                    elif to_pin == 'b' and from_ir_id:
                        kind.b = from_ir_id
            
            elif isinstance(kind, Return):
                # Return node with enabled and value inputs
                for conn in target_conns:
                    to_pin = conn.get('to_pin')
                    from_id = conn.get('_from_int') if '_from_int' in conn else conn.get('from')
                    from_ir_id = _lookup_ir(from_id)
                    from_pin = conn.get('from_pin')
                    print(f"DEBUG Return connection: to_pin={to_pin}, from_id={from_id}, from_ir_id={from_ir_id}, from_pin={from_pin}")
                    if to_pin == 'enabled' and from_ir_id:
                        kind.enabled = from_ir_id
                        if from_pin:
                            self.module.source_pin_map[(ir_node_id.id, 0)] = (from_ir_id.id, from_pin)
                    elif to_pin == 'value' and from_ir_id:
                        kind.value = from_ir_id
                        # Store source pin info for multi-output nodes
                        if from_pin:
                            self.module.source_pin_map[(ir_node_id.id, 1)] = (from_ir_id.id, from_pin)
            
            elif isinstance(kind, Print):
                # Print node
                for conn in target_conns:
                    to_pin = conn.get('to_pin')
                    from_id = conn.get('_from_int') if '_from_int' in conn else conn.get('from')
                    from_ir_id = _lookup_ir(from_id)
                    from_pin = conn.get('from_pin')
                    
                    if to_pin == 'value' and from_ir_id:
                        kind.value = from_ir_id
                        # Store source pin info for multi-output nodes
                        if from_pin:
                            self.module.source_pin_map[(ir_node_id.id, 0)] = (from_ir_id.id, from_pin)
                    elif to_pin == 'label' and from_ir_id:
                        kind.label = from_ir_id
                        if from_pin:
                            self.module.source_pin_map[(ir_node_id.id, 1)] = (from_ir_id.id, from_pin)
            
            elif isinstance(kind, SetVar):
                # SetVariable node
                print(f"DEBUG SetVar: canvas_id={canvas_id}, looking for connections in connections_by_target")
                print(f"  connections_by_target keys: {list(connections_by_target.keys())}")
                if target_conns:
                    print(f"  target_conns for this node: {target_conns}")
                else:
                    print(f"  No connections found for canvas node {canvas_id}")
                for conn in target_conns:
                    to_pin = conn.get('to_pin')
                    from_id = conn.get('_from_int') if '_from_int' in conn else conn.get('from')
                    from_pin = conn.get('from_pin')
                    from_ir_id = _lookup_ir(from_id)
                    print(f"DEBUG SetVar connection: to_pin={to_pin}, from_pin={from_pin}, from_id={from_id}, from_ir_id={from_ir_id}, node_map keys={list(node_map.keys())}")

                    # Accept explicit name/value pin connections
                    if (to_pin == 'name' or (to_pin in (None, '', 'name') and from_pin in ('name',))) and from_ir_id:
                        kind.var_name = from_ir_id
                        continue

                    # Accept value connections even if the to_pin is empty or generic
                    if (to_pin == 'value' or to_pin in (None, '', 'value', 'output') or from_pin in ('result', 'out', 'value')) and from_ir_id:
                        kind.value = from_ir_id
                        continue

                # Fallback: if value still not set, try any connection's from id mapped to IR
                if not getattr(kind, 'value', None):
                    for conn in target_conns:
                        from_id = conn.get('_from_int') if '_from_int' in conn else conn.get('from')
                        from_ir_id = _lookup_ir(from_id)
                        if from_ir_id:
                            kind.value = from_ir_id
                            print(f"DEBUG SetVar fallback assigned value from {from_id} -> {from_ir_id}")
                            break
            
            elif isinstance(kind, GetVar):
                # GetVariable node
                for conn in target_conns:
                    to_pin = conn.get('to_pin')
                    from_id = conn.get('_from_int') if '_from_int' in conn else conn.get('from')
                    from_ir_id = _lookup_ir(from_id)
                    
                    if to_pin == 'name' and from_ir_id:
                        kind.var_name = from_ir_id
            
            elif isinstance(kind, Custom):
                # Custom nodes (including composites and composite I/O nodes)
                # For composite I/O nodes, they have dynamic pin names based on renaming
                # We need to handle them specially
                if kind.name in ('__composite_input__', '__composite_output__'):
                    # These nodes have a single pin that can be renamed
                    # Just set the first connection as the only input
                    kind.inputs = []
                    for conn in target_conns:
                        from_id = conn.get('_from_int') if '_from_int' in conn else conn.get('from')
                        from_ir_id = _lookup_ir(from_id)
                        from_pin = conn.get('from_pin')
                        if from_ir_id:
                            kind.inputs.append(from_ir_id)
                            # Store source pin info for multi-output nodes
                            if from_pin:
                                self.module.source_pin_map[(ir_node_id.id, 0)] = (from_ir_id.id, from_pin)
                            break  # Only one input for I/O nodes
                else:
                    # Regular custom nodes - map connections to the inputs list by pin name
                    template = node_templates.get(kind.name)
                    if template:
                        input_pins = list(template.get('inputs', {}).keys())
                        # Initialize inputs list with None for each input pin
                        kind.inputs = [None] * len(input_pins)
                        
                        for conn in target_conns:
                            to_pin = conn.get('to_pin')
                            from_id = conn.get('_from_int') if '_from_int' in conn else conn.get('from')
                            from_ir_id = _lookup_ir(from_id)
                            from_pin = conn.get('from_pin')
                            
                            # Find the index of this pin in the inputs
                            if to_pin in input_pins and from_ir_id:
                                pin_index = input_pins.index(to_pin)
                                kind.inputs[pin_index] = from_ir_id
                                # Store source pin info for multi-output nodes
                                if from_pin:
                                    self.module.source_pin_map[(ir_node_id.id, pin_index)] = (from_ir_id.id, from_pin)
        
        # Debug: Show what nodes look like after connections
        print("\nNodes after applying connections:")
        for node in self.module.nodes:
            kind = node.kind
            if isinstance(kind, Add):
                print(f"  Add node {node.id.id}: a={kind.a}, b={kind.b}")
            elif isinstance(kind, ConstValue):
                print(f"  Const node {node.id.id}: value={kind.value.data}")
            elif isinstance(kind, Print):
                print(f"  Print node {node.id.id}: value={kind.value}, label={kind.label}")
            elif isinstance(kind, Return):
                print(f"  Return node {node.id.id}: value={kind.value}")
    
    def execute_ir(self, ir_module: IRModule, ctx: Optional[ExecutionContext] = None, breakpoints: set = None) -> Dict[str, Any]:
        """
        Execute an IR module.
        
        Args:
            ir_module: The IR module to execute
            ctx: Optional execution context for debugging/step execution
            breakpoints: Set of IR node IDs to stop execution at
        
        Returns:
            Dictionary of execution results
        """
        if ctx is None:
            ctx = ExecutionContext()
        if breakpoints is None:
            breakpoints = set()
        
        ctx.ir_module = ir_module
        
        # Topological sort to determine execution order
        sorted_nodes = self._topological_sort(ir_module)

        # Debug: print module state before execution
        try:
            comp_keys = list(getattr(ir_module, 'composite_templates', {}).keys())
        except Exception:
            comp_keys = None
        print(f"EXECUTE_IR: nodes={[n.id.id for n in ir_module.nodes]} kinds={[n.kind.__class__.__name__ for n in ir_module.nodes]} composite_templates_keys={comp_keys}")
        print(f"EXECUTE_IR: widget_values keys={list(ir_module.widget_values.keys())} ctx.variables={ctx.variables}")
        
        # Execute nodes in order
        results = {}
        
        # First pass: identify loop nodes and their body nodes
        loop_nodes = {}  # loop_node_id -> (loop_type, list of body node ids)
        for node in sorted_nodes:
            if isinstance(node.kind, Custom) and node.kind.name in ('ForEachLoop', 'ForLoop', 'WhileLoop'):
                # Find all nodes downstream of this loop until we hit Return
                body_nodes = self._find_loop_body_nodes(node, sorted_nodes, ir_module)
                loop_nodes[node.id.id] = (node.kind.name, body_nodes)
                print(f"{node.kind.name} node {node.id.id} has body nodes: {[n.id.id for n in body_nodes]}")
        
        # Identify Sequence and Branch nodes and their output pin branches
        sequence_nodes = {}  # sequence_node_id -> {pin_name: [target_node_ids]}
        branch_nodes_map = {} # branch_node_id -> {pin_name: [target_node_ids]}
        for node in sorted_nodes:
            if isinstance(node.kind, Custom):
                if node.kind.name == 'Sequence':
                    branches = self._find_sequence_branches(node, ir_module)
                    sequence_nodes[node.id.id] = branches
                    print(f"Sequence node {node.id.id} has branches: {branches}")
                elif node.kind.name == 'Branch':
                    branches = self._find_sequence_branches(node, ir_module)
                    branch_nodes_map[node.id.id] = branches
                    print(f"Branch node {node.id.id} has downstream paths: {branches}")
        
        # Execute nodes, handling loops specially
        executed_nodes = set()
        i = 0
        while i < len(sorted_nodes):
            node = sorted_nodes[i]
            
            # Skip if already executed (e.g., as part of a loop body)
            if node.id.id in executed_nodes:
                i += 1
                continue
            
            # Check if this node has a breakpoint
            if node.id.id in breakpoints:
                print(f"Breakpoint hit at node {node.id.id}")
                results['_breakpoint_hit'] = node.id.id
                break
            
            try:
                # Special handling for loop nodes (ForEachLoop, ForLoop, WhileLoop)
                if node.id.id in loop_nodes:
                    loop_type, body_nodes = loop_nodes[node.id.id]
                    loop_result = self._execute_loop(node, loop_type, body_nodes, ctx, ir_module)
                    if loop_result is not None:
                        results['return'] = loop_result
                        # Mark all loop body nodes as executed
                        for body_node in body_nodes:
                            executed_nodes.add(body_node.id.id)
                    executed_nodes.add(node.id.id)
                    i += 1
                    continue
                
                # Special handling for Sequence nodes - execute branches in order
                if node.id.id in sequence_nodes:
                    self._execute_sequence(node, sequence_nodes[node.id.id], ctx, ir_module, executed_nodes, sorted_nodes, results)
                    executed_nodes.add(node.id.id)
                    i += 1
                    continue
                
                # Special handling for Branch nodes - execute only the taken branch
                if node.id.id in branch_nodes_map:
                    self._execute_branch(node, branch_nodes_map[node.id.id], ctx, ir_module, executed_nodes, sorted_nodes, results)
                    executed_nodes.add(node.id.id)
                    i += 1
                    continue
                
                # Check if this node is part of a loop body (skip - will be executed by loop)
                is_in_loop_body = False
                for loop_id, loop_data in loop_nodes.items():
                    loop_type, body_nodes_list = loop_data
                    if any(bn.id.id == node.id.id for bn in body_nodes_list):
                        is_in_loop_body = True
                        break
                if is_in_loop_body:
                    i += 1
                    continue
                
                result = self._execute_node(node, ctx)
                ctx.set_value(node.id, result)
                executed_nodes.add(node.id.id)
                
                # Debug: Show what each node computed
                print(f"Node {node.id.id} ({node.kind.__class__.__name__}): {result}")
                
                # Collect results from the executed node
                self._collect_node_results(node, result, results, ir_module)
            except Exception as e:
                error_msg = f"Error executing node {node.id.id}: {e}"
                print(error_msg)
                traceback.print_exc()
                ctx.set_error(node.id, str(e))
        
        # Add errors to results if any occurred
        if ctx.errors:
            results['_node_errors'] = dict(ctx.errors)
        
        # Add all computed values for hover inspection
        if ctx.values:
            results['_computed_values'] = dict(ctx.values)
        
        return results
    
    def execute_ir_step(self, ir_module: IRModule, ctx: Optional[ExecutionContext] = None) -> tuple:
        """
        Execute IR step-by-step. Returns (context, node, result, is_complete).
        
        Args:
            ir_module: The IR module to execute
            ctx: Existing execution context (None to start fresh)
        
        Returns:
            Tuple of (context, current_node, result, is_complete)
        """
        
        # Initialize context if needed
        if ctx is None:
            ctx = ExecutionContext()
            ctx.ir_module = ir_module
            ctx.step_mode = True
            # Get execution order
            sorted_nodes = self._topological_sort(ir_module)
            ctx.execution_order = sorted_nodes
        
        # Check if execution is complete
        if not ctx.execution_order:
            return (ctx, None, None, True)
        
        # Get next node to execute
        node = ctx.execution_order[0]
        
        # Check for breakpoint
        if node.id.id in ctx.breakpoints:
            ctx.paused_at = node.id.id
            return (ctx, node, None, False)
        
        try:
            result = self._execute_node(node, ctx)
            ctx.set_value(node.id, result)
            
            # Store results for return nodes (only if enabled)
            results = {}
            if isinstance(node.kind, Return):
                if result != '__RETURN_DISABLED__':
                    results['return'] = result
            
            # Remove executed node from order
            ctx.execution_order.pop(0)
            
            # Check if complete
            is_complete = len(ctx.execution_order) == 0
            
            return (ctx, node, result, is_complete)
            
        except Exception as e:
            ctx.set_error(node.id, str(e))
            ctx.execution_order.pop(0)
            return (ctx, node, None, len(ctx.execution_order) == 0)
    
    def _find_loop_body_nodes(self, loop_node, sorted_nodes, ir_module):
        """Find all nodes that are part of a loop's body (downstream of loop, up to and including Return)"""
        body_nodes = []
        loop_node_idx = None
        
        # Find the loop node's position in sorted order
        for i, node in enumerate(sorted_nodes):
            if node.id.id == loop_node.id.id:
                loop_node_idx = i
                break
        
        if loop_node_idx is None:
            return body_nodes
        
        # Find all nodes that depend (directly or indirectly) on the loop node
        loop_outputs = set()
        loop_outputs.add(loop_node.id.id)
        
        # Iterate through sorted nodes after the loop
        for i in range(loop_node_idx + 1, len(sorted_nodes)):
            node = sorted_nodes[i]
            deps = self._get_dependencies(node)
            
            # Check if this node depends on any node in the loop body
            depends_on_loop = False
            for dep in deps:
                if dep and dep.id in loop_outputs:
                    depends_on_loop = True
                    break
            
            if depends_on_loop:
                body_nodes.append(node)
                loop_outputs.add(node.id.id)
                
                # If this is a Return node, stop - it's the end of the loop body
                if isinstance(node.kind, Return):
                    break
        
        return body_nodes
    
    def _execute_loop(self, loop_node, loop_type, body_nodes, ctx, ir_module):
        """Execute a loop node (ForEachLoop, ForLoop, or WhileLoop) with its body nodes"""
        kind = loop_node.kind
        widget_vals = self.module.widget_values.get(loop_node.id.id, {})
        
        if loop_type == 'ForEachLoop':
            return self._execute_foreach_loop(loop_node, kind, widget_vals, body_nodes, ctx)
        elif loop_type == 'ForLoop':
            return self._execute_for_loop(loop_node, kind, widget_vals, body_nodes, ctx)
        elif loop_type == 'WhileLoop':
            return self._execute_while_loop(loop_node, kind, widget_vals, body_nodes, ctx)
        else:
            print(f"Unknown loop type: {loop_type}")
            return None
    
    def _execute_foreach_loop(self, loop_node, kind, widget_vals, body_nodes, ctx):
        """Execute a ForEachLoop node"""
        # Get the list input
        input_list = None
        if kind.inputs and len(kind.inputs) > 0 and kind.inputs[0]:
            input_list = ctx.get_value(kind.inputs[0])
        if input_list is None:
            input_list = widget_vals.get('list', [])
        
        if not isinstance(input_list, (list, tuple)):
            print(f"ForEachLoop: input is not a list: {input_list}")
            return None
        
        print(f"ForEachLoop: iterating over {len(input_list)} items")
        
        for index, item in enumerate(input_list):
            print(f"  Loop iteration {index}: item = {item}")
            loop_output = (item, index, index == len(input_list) - 1)
            ctx.set_value(loop_node.id, loop_output)
            
            result = self._execute_loop_body(body_nodes, ctx)
            if result is not None:
                return result
        
        print(f"ForEachLoop: completed all {len(input_list)} iterations")
        return None
    
    def _execute_for_loop(self, loop_node, kind, widget_vals, body_nodes, ctx):
        """Execute a ForLoop node with start, end, step"""
        # Get loop parameters
        start = widget_vals.get('start', 0)
        end = widget_vals.get('end', 10)
        step = widget_vals.get('step', 1)
        
        # Get from connected inputs if available
        if kind.inputs:
            if len(kind.inputs) > 0 and kind.inputs[0]:
                start = ctx.get_value(kind.inputs[0]) or start
            if len(kind.inputs) > 1 and kind.inputs[1]:
                end = ctx.get_value(kind.inputs[1]) or end
            if len(kind.inputs) > 2 and kind.inputs[2]:
                step = ctx.get_value(kind.inputs[2]) or step
        
        # Ensure valid values
        start = int(start) if isinstance(start, (int, float)) else 0
        end = int(end) if isinstance(end, (int, float)) else 10
        step = int(step) if isinstance(step, (int, float)) else 1
        if step == 0:
            step = 1  # Prevent infinite loop
        
        print(f"ForLoop: iterating from {start} to {end} with step {step}")
        
        # Calculate iteration count for safety
        if step > 0:
            indices = range(start, end, step)
        else:
            indices = range(start, end, step)
        
        for index in indices:
            print(f"  ForLoop iteration: index = {index}")
            loop_output = (index, index == list(indices)[-1] if indices else True)
            ctx.set_value(loop_node.id, loop_output)
            
            result = self._execute_loop_body(body_nodes, ctx)
            if result is not None:
                return result
        
        print(f"ForLoop: completed all iterations")
        return None
    
    def _execute_while_loop(self, loop_node, kind, widget_vals, body_nodes, ctx):
        """Execute a WhileLoop node with condition and safety limit"""
        # Get max iterations (safety limit)
        max_iterations = widget_vals.get('max_iterations', 10000)
        if kind.inputs and len(kind.inputs) > 1 and kind.inputs[1]:
            max_val = ctx.get_value(kind.inputs[1])
            if isinstance(max_val, (int, float)):
                max_iterations = int(max_val)
        
        max_iterations = max(1, min(max_iterations, 100000))  # Clamp between 1 and 100000
        
        print(f"WhileLoop: starting with max_iterations = {max_iterations}")
        
        iteration = 0
        while iteration < max_iterations:
            # Re-evaluate condition each iteration
            condition = False
            if kind.inputs and len(kind.inputs) > 0 and kind.inputs[0]:
                condition = bool(ctx.get_value(kind.inputs[0]))
            else:
                condition = bool(widget_vals.get('condition', False))
            
            if not condition:
                print(f"  WhileLoop: condition false at iteration {iteration}, exiting")
                break
            
            print(f"  WhileLoop iteration {iteration}")
            loop_output = (iteration, False)
            ctx.set_value(loop_node.id, loop_output)
            
            result = self._execute_loop_body(body_nodes, ctx)
            if result is not None:
                return result
            
            iteration += 1
        
        if iteration >= max_iterations:
            print(f"WhileLoop: SAFETY LIMIT reached at {max_iterations} iterations!")
        else:
            print(f"WhileLoop: completed after {iteration} iterations")
        
        return None
    
    def _execute_loop_body(self, body_nodes, ctx):
        """Execute loop body nodes and return early if Return is enabled"""
        for body_node in body_nodes:
            try:
                result = self._execute_node(body_node, ctx)
                ctx.set_value(body_node.id, result)
                print(f"    Body node {body_node.id.id} ({body_node.kind.__class__.__name__}): {result}")
                
                if isinstance(body_node.kind, Return):
                    if result != '__RETURN_DISABLED__':
                        print(f"  Loop: Return enabled, breaking with value: {result}")
                        return result
                    else:
                        print(f"  Loop: Return disabled, continuing...")
            except Exception as e:
                print(f"    Error in body node {body_node.id.id}: {e}")
                traceback.print_exc()
        return None
    
    def _execute_logic_reference(self, node, kind, widget_vals, ctx):
        """
        Execute an external graph as a function call.
        
        This is the core of graph composability - a graph can call another
        graph as if it were a function, with explicit entry and exit.
        
        Args:
            node: The LogicReference node
            kind: Node kind (Custom)
            widget_vals: Widget values including graphPath
            ctx: Execution context
            
        Returns:
            The result from the subgraph's InterfaceOutput nodes
        """
        import json
        from pathlib import Path as PathLib
        
        # Get graph path from widget or connected input
        graph_path = widget_vals.get('graphPath', '')
        if not graph_path and kind.inputs:
            # Check for connected graphPath input
            for i, inp in enumerate(kind.inputs):
                if inp:
                    potential_path = ctx.get_value(inp)
                    if isinstance(potential_path, str) and potential_path:
                        graph_path = potential_path
                        break
        
        if not graph_path:
            print(f"LogicReference: No graph path specified")
            return None
        
        # Resolve path
        path = PathLib(graph_path)
        if not path.is_absolute():
            # Try relative to current graph's directory
            current_graph_path = getattr(self.module, 'source_path', '')
            if current_graph_path:
                path = PathLib(current_graph_path).parent / graph_path
        
        if not path.exists():
            print(f"LogicReference: Graph file not found: {path}")
            return None
        
        print(f"LogicReference: Loading and executing '{path}'")
        
        try:
            # Load the external graph
            with open(path, 'r', encoding='utf-8') as f:
                subgraph_data = json.load(f)
            
            # Get interface from the loaded graph
            try:
                from py_editor.core.graph_interface import GraphInterface
                interface = GraphInterface.extract_from_graph(subgraph_data, str(path))
            except ImportError:
                interface = None
            
            # Collect input values from dynamic pins
            # The LogicReference node has dynamic pins matching the subgraph interface
            input_values = {}
            if interface:
                for input_name, pin_def in interface.inputs.items():
                    if input_name == 'exec':
                        continue  # Skip exec pin
                    # Look for value in widget_vals or connected inputs
                    if input_name in widget_vals:
                        input_values[input_name] = widget_vals[input_name]
            
            # Also check connected inputs (dynamic pins are added after standard ones)
            if kind.inputs:
                input_idx = 1  # Skip exec input at index 0
                if interface:
                    for input_name, pin_def in interface.inputs.items():
                        if input_name == 'exec':
                            continue
                        if input_idx < len(kind.inputs) and kind.inputs[input_idx]:
                            input_values[input_name] = ctx.get_value(kind.inputs[input_idx])
                        input_idx += 1
            
            # Load node templates for subgraph
            try:
                from py_editor.core import node_templates
                templates = node_templates.get_all_templates()
            except:
                templates = {}
            
            # Create new backend for subgraph execution
            sub_backend = IRBackend()
            sub_ir = sub_backend.canvas_to_ir(subgraph_data, templates)
            
            # Inject input values into the subgraph module
            sub_ir.interface_inputs = input_values
            sub_ir.interface_outputs = {}
            sub_ir.source_path = str(path)
            
            # Copy event context to subgraph
            sub_ir.event_context = getattr(self.module, 'event_context', {})
            
            # Execute the subgraph
            sub_ctx = ExecutionContext()
            sub_ctx.variables = dict(ctx.variables)  # Copy parent variables
            
            results = sub_backend.execute_ir(sub_ir, ctx=sub_ctx)
            
            # Get outputs from the subgraph
            outputs = getattr(sub_ir, 'interface_outputs', {})
            
            print(f"LogicReference: Subgraph completed with outputs: {outputs}")
            
            # Return tuple of outputs or single value
            if len(outputs) == 0:
                return None
            elif len(outputs) == 1:
                return list(outputs.values())[0]
            else:
                return outputs
            
        except Exception as e:
            print(f"LogicReference: Error executing subgraph: {e}")
            traceback.print_exc()
            return None
    
    def _find_sequence_branches(self, sequence_node, ir_module):
        """Find all nodes connected to each output pin of a Sequence node"""
        branches = {}  # pin_name -> list of target node ids
        
        # Get output connections from the Sequence node
        for (source_id, from_pin), target_ids in ir_module.output_connections.items():
            if source_id == sequence_node.id.id:
                if from_pin not in branches:
                    branches[from_pin] = []
                branches[from_pin].extend(target_ids)
        
        return branches
    
    def _find_branch_nodes(self, start_node_id, ir_module, sorted_nodes):
        """Find all nodes in a branch starting from a node, following data flow"""
        branch_nodes = []
        visited = set()
        
        # Create a map of node_id -> IRNode
        node_by_id = {node.id.id: node for node in sorted_nodes}
        
        # Build adjacency list for forward traversal (node -> nodes that depend on it)
        forward_deps = {}  # node_id -> list of node_ids that depend on it
        for node in sorted_nodes:
            deps = self._get_dependencies(node)
            for dep in deps:
                if dep:
                    if dep.id not in forward_deps:
                        forward_deps[dep.id] = []
                    forward_deps[dep.id].append(node.id.id)
        
        # BFS to find all reachable nodes from start
        queue = [start_node_id]
        while queue:
            node_id = queue.pop(0)
            if node_id in visited:
                continue
            visited.add(node_id)
            
            if node_id in node_by_id:
                branch_nodes.append(node_by_id[node_id])
            
            # Add nodes that depend on this node
            for dep_id in forward_deps.get(node_id, []):
                if dep_id not in visited:
                    queue.append(dep_id)
        
        # Sort by topological order
        sorted_order = {node.id.id: idx for idx, node in enumerate(sorted_nodes)}
        branch_nodes.sort(key=lambda n: sorted_order.get(n.id.id, 0))
        
        return branch_nodes
    
    def _collect_node_results(self, node, result, results, ir_module):
        """Helper to collect results if node is Return or composite output"""
        if isinstance(node.kind, Return):
            if result != '__RETURN_DISABLED__':
                results['return'] = result
            else:
                print(f"  Return node {node.id.id} is disabled, skipping")
        elif isinstance(node.kind, Custom) and node.kind.name == '__composite_output__':
            composite_templates = getattr(ir_module, 'composite_templates', {})
            if result is not None:
                results['output'] = result
                for parent_node in ir_module.nodes:
                    if isinstance(parent_node.kind, Custom):
                        parent_template = composite_templates.get(parent_node.id.id)
                        if parent_template and parent_template.get('type') == 'composite':
                            output_map = parent_template.get('outputs', {})
                            for ext_name, output_info in output_map.items():
                                if output_info.get('node') == node.id.id:
                                    results[ext_name] = result
                                    break

    def _execute_sequence(self, sequence_node, branches, ctx, ir_module, executed_nodes, sorted_nodes, results):
        """Execute a Sequence node's branches in order (then0, then1, then2, ...)"""
        print(f"Sequence node {sequence_node.id.id}: executing branches in order")
        
        # Sort branch names to ensure proper order (then0, then1, then2, ...)
        sorted_pins = sorted(branches.keys(), key=lambda x: int(x[4:]) if x.startswith('then') and x[4:].isdigit() else 999)
        
        for pin_name in sorted_pins:
            target_ids = branches.get(pin_name, [])
            print(f"  Branch '{pin_name}': targets = {target_ids}")
            
            # For each directly connected node, find and execute all downstream nodes
            for target_id in target_ids:
                branch_nodes = self._find_branch_nodes(target_id, ir_module, sorted_nodes)
                print(f"    Executing branch starting at {target_id}: {[n.id.id for n in branch_nodes]}")
                
                for branch_node in branch_nodes:
                    if branch_node.id.id in executed_nodes:
                        print(f"      Skipping already executed node {branch_node.id.id}")
                        continue
                    
                    try:
                        result = self._execute_node(branch_node, ctx)
                        ctx.set_value(branch_node.id, result)
                        executed_nodes.add(branch_node.id.id)
                        print(f"      Node {branch_node.id.id} ({branch_node.kind.__class__.__name__}): {result}")
                        self._collect_node_results(branch_node, result, results, ir_module)
                    except Exception as e:
                        print(f"      Error in branch node {branch_node.id.id}: {e}")
                        traceback.print_exc()
        
        print(f"Sequence node {sequence_node.id.id}: completed all branches")
    
    def _execute_branch(self, branch_node, paths, ctx, ir_module, executed_nodes, sorted_nodes, results):
        """Execute a Branch node and follow only the taken path"""
        # Execute the Branch node itself to evaluate condition
        result = self._execute_node(branch_node, ctx)
        ctx.set_value(branch_node.id, result)
        
        taken_pin = result[0] if isinstance(result, tuple) else None
        print(f"Branch node {branch_node.id.id}: condition evaluated to {taken_pin}")
        
        # Mark the un-taken paths as executed so the main loop skips them
        for pin_name, target_ids in paths.items():
            if pin_name != taken_pin:
                for target_id in target_ids:
                    untaken_nodes = self._find_branch_nodes(target_id, ir_module, sorted_nodes)
                    for n in untaken_nodes:
                        executed_nodes.add(n.id.id)
                        print(f"  Skipping untaken branch node {n.id.id} ({n.kind.__class__.__name__})")
                        
        # Execute the taken path nodes
        if taken_pin and taken_pin in paths:
            target_ids = paths[taken_pin]
            for target_id in target_ids:
                taken_nodes = self._find_branch_nodes(target_id, ir_module, sorted_nodes)
                for n in taken_nodes:
                    if n.id.id in executed_nodes:
                        continue
                    try:
                        res = self._execute_node(n, ctx)
                        ctx.set_value(n.id, res)
                        executed_nodes.add(n.id.id)
                        print(f"      Node {n.id.id} ({n.kind.__class__.__name__}): {res}")
                        self._collect_node_results(n, res, results, ir_module)
                    except Exception as e:
                        print(f"      Error in branch node {n.id.id}: {e}")
                        traceback.print_exc()
        
        print(f"Branch node {branch_node.id.id}: completed")

    def _topological_sort(self, ir_module: IRModule) -> List:
        """Topologically sort nodes for execution order"""
        from collections import deque
        
        # Build dependency graph
        in_degree = {}
        adjacency = {}
        
        for node in ir_module.nodes:
            in_degree[node.id.id] = 0
            adjacency[node.id.id] = []
        
        # Count dependencies
        for node in ir_module.nodes:
            deps = self._get_dependencies(node)
            for dep in deps:
                if dep and dep.id in adjacency:
                    adjacency[dep.id].append(node.id.id)
                    in_degree[node.id.id] += 1

        # Debug: show dependencies and adjacency/in_degree maps
        try:
            deps_map = {node.id.id: [d.id for d in self._get_dependencies(node)] for node in ir_module.nodes}
        except Exception:
            deps_map = None
        print(f"TOPO_SORT: deps_map={deps_map}")
        print(f"TOPO_SORT: adjacency={adjacency}")
        print(f"TOPO_SORT: in_degree={in_degree}")
        
        # Start with nodes that have no dependencies
        queue = deque([node for node in ir_module.nodes if in_degree[node.id.id] == 0])
        sorted_nodes = []
        
        while queue:
            node = queue.popleft()
            sorted_nodes.append(node)
            
            # Reduce in-degree for dependent nodes
            for neighbor_id in adjacency[node.id.id]:
                in_degree[neighbor_id] -= 1
                if in_degree[neighbor_id] == 0:
                    # Find the node and add to queue
                    neighbor_node = ir_module.find_node(NodeId(neighbor_id))
                    if neighbor_node:
                        queue.append(neighbor_node)
        
        # If we didn't sort all nodes, there's a cycle
        if len(sorted_nodes) != len(ir_module.nodes):
            print("Warning: Cycle detected in graph, some nodes may not execute")
        
        print(f"TOPO_SORT: final sorted_nodes order={[n.id.id for n in sorted_nodes]}")
        return sorted_nodes
    
    def _get_dependencies(self, node) -> List[Optional[NodeId]]:
        """Get node IDs that this node depends on"""
        kind = node.kind
        deps = []
        
        if isinstance(kind, (Add, Subtract, Multiply, Divide)):
            deps.extend([kind.a, kind.b])
        elif isinstance(kind, Return):
            deps.append(kind.value)
        elif isinstance(kind, Print):
            deps.extend([kind.value, kind.label])
        elif isinstance(kind, SetVar):
            deps.extend([kind.var_name, kind.value])
        elif isinstance(kind, GetVar):
            deps.append(kind.var_name)
        elif isinstance(kind, Custom):
            # Custom nodes depend on all their inputs
            if hasattr(kind, 'inputs') and kind.inputs:
                deps.extend(kind.inputs)
        
        return [d for d in deps if d is not None]
    
    def _get_value_with_pin_extraction(self, source_id: NodeId, dest_node_id: int, input_idx: int, ctx: ExecutionContext) -> Any:
        """Get a value from a source node, extracting the right output if it's a multi-output node."""
        value = ctx.get_value(source_id)
        
        # Check if this comes from a multi-output node
        source_pin_info = self.module.source_pin_map.get((dest_node_id, input_idx))
        if source_pin_info and isinstance(value, tuple):
            source_node_id, from_pin_name = source_pin_info
            # Find the source node template to get output pin order
            source_node = next((n for n in self.module.nodes if n.id.id == source_node_id), None)
            if source_node and isinstance(source_node.kind, Custom):
                try:
                    from py_editor.core import node_templates
                except:
                    try:
                        from ..core import node_templates
                    except:
                        from core import node_templates
                source_template = node_templates.get_template(source_node.kind.name)
                if source_template:
                    output_pins = list(source_template.get('outputs', {}).keys())
                    if from_pin_name in output_pins:
                        output_idx = output_pins.index(from_pin_name)
                        if output_idx < len(value):
                            extracted = value[output_idx]
                            print(f"Extracted output '{from_pin_name}' (idx {output_idx}) from multi-output node: {extracted}")
                            return extracted
        return value
    
    def _execute_node(self, node, ctx: ExecutionContext) -> Any:
        """Execute a single node"""
        kind = node.kind
        
        # Debug: trace kind type before isinstance checks
        print(f"_execute_node ENTER: node.id={node.id.id} kind_class={kind.__class__.__name__} kind_module={kind.__class__.__module__}")
        print(f"  isinstance(kind, Custom)={isinstance(kind, Custom)} Custom_module={Custom.__module__}")
        
        # Get widget values for this node (if any)
        widget_vals = self.module.widget_values.get(node.id.id, {})
        
        # Constant values
        if isinstance(kind, ConstValue):
            return kind.value.data
        
        # Custom nodes (including composites)
        elif isinstance(kind, Custom):
            # Debug: report custom node execution entry
            try:
                composite_keys = list(getattr(self.module, 'composite_templates', {}).keys())
            except Exception:
                composite_keys = None
            print(f"Custom node execute ENTRY: name={kind.name} node.id={node.id.id} composite_templates_keys={composite_keys}")
            
            # Handle LogicReference - execute external graph as function call
            if kind.name == 'LogicReference':
                return self._execute_logic_reference(node, kind, widget_vals, ctx)
            
            # Handle InterfaceInput - get value from caller's input
            elif kind.name == 'InterfaceInput':
                input_name = widget_vals.get('name', 'input1')
                interface_inputs = getattr(self.module, 'interface_inputs', {})
                if input_name in interface_inputs:
                    return interface_inputs[input_name]
                return widget_vals.get('default', None)
            
            # Handle InterfaceOutput - capture value for return to caller
            elif kind.name == 'InterfaceOutput':
                output_name = widget_vals.get('name', 'output1')
                value = None
                if kind.inputs and kind.inputs[0]:
                    value = ctx.get_value(kind.inputs[0])
                interface_outputs = getattr(self.module, 'interface_outputs', {})
                interface_outputs[output_name] = value
                self.module.interface_outputs = interface_outputs
                print(f"InterfaceOutput '{output_name}' = {value}")
                return value
            
            # Handle UI Event nodes specially
            event_context = getattr(self.module, 'event_context', {})
            
            if kind.name == 'OnUIButtonPressed':
                # Check if this event node matches the triggered button
                triggered_button_id = event_context.get('triggered_button_id', '')
                triggered_button_name = event_context.get('triggered_button_name', '')
                node_button_id = widget_vals.get('buttonId', '')
                
                # If node has empty buttonId, match ANY button (wildcard)
                # Otherwise require exact match by ID or name
                if not node_button_id:
                    is_triggered = bool(triggered_button_id or triggered_button_name)
                else:
                    is_triggered = (node_button_id == triggered_button_id or 
                                   node_button_id == triggered_button_name)
                
                print(f"OnUIButtonPressed check: node_button_id='{node_button_id}' triggered_id='{triggered_button_id}' triggered_name='{triggered_button_name}' -> {is_triggered}")
                return is_triggered
            
            elif kind.name == 'OnUISliderChanged':
                # Check if this event node matches the triggered slider
                triggered_slider_id = event_context.get('triggered_slider_id', '')
                slider_value = event_context.get('slider_value', 0)
                node_slider_id = widget_vals.get('sliderId', '')
                
                # If node has empty sliderId, match ANY slider (wildcard)
                if not node_slider_id:
                    is_triggered = bool(triggered_slider_id)
                else:
                    is_triggered = (node_slider_id == triggered_slider_id)
                    
                print(f"OnUISliderChanged check: node_slider_id='{node_slider_id}' triggered_id='{triggered_slider_id}' -> {is_triggered}, value={slider_value}")
                
                # Return tuple (is_triggered, value) for multi-output
                return (is_triggered, slider_value if is_triggered else 0)
            
            elif kind.name == 'OnUICheckboxChanged':
                # Check if this event node matches the triggered checkbox
                triggered_checkbox_id = event_context.get('triggered_checkbox_id', '')
                checkbox_checked = event_context.get('checkbox_checked', False)
                node_checkbox_id = widget_vals.get('checkboxId', '')
                
                # If node has empty checkboxId, match ANY checkbox (wildcard)
                if not node_checkbox_id:
                    is_triggered = bool(triggered_checkbox_id)
                else:
                    is_triggered = (node_checkbox_id == triggered_checkbox_id)
                    
                print(f"OnUICheckboxChanged check: node_checkbox_id='{node_checkbox_id}' triggered_id='{triggered_checkbox_id}' -> {is_triggered}, checked={checkbox_checked}")
                
                return (is_triggered, checkbox_checked if is_triggered else False)
            
            elif kind.name == 'OnUITextChanged':
                # Check if this event node matches the triggered text input
                triggered_input_id = event_context.get('triggered_input_id', '')
                input_text = event_context.get('input_text', '')
                node_input_id = widget_vals.get('inputId', '')
                
                # If node has empty inputId, match ANY text input (wildcard)
                if not node_input_id:
                    is_triggered = bool(triggered_input_id)
                else:
                    is_triggered = (node_input_id == triggered_input_id)
                    
                print(f"OnUITextChanged check: node_input_id='{node_input_id}' triggered_id='{triggered_input_id}' -> {is_triggered}, text='{input_text}'")
                
                return (is_triggered, input_text if is_triggered else '')
            
            elif kind.name == 'SetUIScreen':
                # Screen switch node - returns the screen name to switch to
                screen_name = widget_vals.get('screenName', '')
                if not screen_name:
                    # Check if connected via input
                    if kind.inputs:
                        screen_name = ctx.get_value(kind.inputs[0]) if kind.inputs[0] else ''
                print(f"SetUIScreen: switching to screen '{screen_name}'")
                # Store screen switch request in event context for the UI to handle
                event_context['switch_to_screen'] = screen_name
                return screen_name
            
            elif kind.name == 'PlaySound':
                # Get file_path from connected input
                file_path = ''
                if kind.inputs:
                    file_path = ctx.get_value(kind.inputs[0]) if kind.inputs[0] else ''
                if not file_path:
                    file_path = widget_vals.get('file_path', '')
                
                # Get channel and loop from widget values
                channel = widget_vals.get('channel', 'Effect')
                # Handle legacy integer channel values
                if isinstance(channel, int):
                    int_to_channel = {0: 'Music', 1: 'Effect', 2: 'Voice', 3: 'UI', 
                                     4: 'Ambient', 5: 'Custom1', 6: 'Custom2', 7: 'Custom3'}
                    channel = int_to_channel.get(channel, 'Effect')
                
                loop_val = widget_vals.get('loop', 'No')
                loop = (loop_val == 'Yes' or loop_val == True)
                
                print(f"PlaySound: file='{file_path}' channel='{channel}' loop={loop}")
                
                # Actually play the sound
                try:
                    from py_editor.backends.audio_runtime import play_sound
                    play_sound(file_path, channel, loop)
                except Exception as e:
                    print(f"PlaySound error: {e}")
                
                return ('exec_out',)
            
            elif kind.name == 'StopSound':
                # Get channel from widget values
                channel = widget_vals.get('channel', 'All')
                
                print(f"StopSound: channel='{channel}'")
                
                # Actually stop the sound
                try:
                    from py_editor.backends.audio_runtime import stop_sound
                    stop_sound(channel)
                except Exception as e:
                    print(f"StopSound error: {e}")
                
                return ('exec_out',)
            
            # Check if this is a composite node
            composite_templates = getattr(self.module, 'composite_templates', {})
            template = composite_templates.get(node.id.id)
            print(f"  composite template lookup -> {bool(template)}")
            
            # Handle special composite I/O nodes
            if kind.name == '__composite_input__':
                # This is a composite input node - return the injected input value
                injected_value = widget_vals.get('__input_value')
                print(f"Composite input node {node.id.id} returning: {injected_value}")
                return injected_value
            elif kind.name == '__composite_output__':
                # This is a composite output node - return its input value
                if kind.inputs:
                    output_value = ctx.get_value(kind.inputs[0])
                    print(f"Composite output node {node.id.id} returning: {output_value}")
                    return output_value
                return None
            
            elif template and template.get('type') == 'composite':
                print(f"  Entering composite execution for template '{template.get('name', kind.name)}'")
                # Execute composite by recursively executing its internal graph
                internal_graph = template.get('graph')
                if internal_graph:
                    # Build input values from connections
                    input_mapping = template.get('inputs', {})  # external_name -> {node: id, pin: name}
                    output_mapping = template.get('outputs', {})
                    
                    # Get input values from connected nodes
                    input_values = {}
                    input_mapping_list = list(input_mapping.items())
                    for idx, input_id in enumerate(kind.inputs):
                        if idx < len(input_mapping_list):
                            external_name, input_info = input_mapping_list[idx]
                            if isinstance(input_info, dict):
                                pin_type = input_info.get('type')
                                default_value = input_info.get('default')
                            else:
                                pin_type = input_info if isinstance(input_info, str) else None
                                default_value = None
                            if input_id:
                                value = ctx.get_value(input_id)
                            else:
                                # Check widget values for this pin
                                value = widget_vals.get(external_name)
                                if value is None:
                                    value = default_value
                            value = self._coerce_pin_value(value, pin_type)
                            input_values[external_name] = value
                    
                    print(f"Executing composite '{kind.name}' with inputs: {input_values}")
                    print(f"Input mapping: {input_mapping}")
                    print(f"Output mapping: {output_mapping}")
                    
                    # Execute the internal graph
                    try:
                        # Import node_templates to pass to canvas_to_ir
                        try:
                            from py_editor.core import node_templates
                        except:
                            try:
                                from ..core import node_templates
                            except:
                                from core import node_templates
                        
                        # Create a new backend for the composite's internal graph
                        composite_backend = IRBackend()
                        templates_dict = node_templates.get_all_templates()
                        
                        # Convert internal graph to IR
                        internal_ir = composite_backend.canvas_to_ir(internal_graph, templates_dict)
                        print(f"  internal_ir.nodes ids={[n.id.id for n in internal_ir.nodes]} kinds={[n.kind.__class__.__name__ for n in internal_ir.nodes]}")
                        print(f"  composite_backend.canvas_to_ir_map={composite_backend.canvas_to_ir_map}")
                        print(f"  internal_ir.widget_values keys={list(internal_ir.widget_values.keys())}")
                        
                        # Inject input values into the internal graph's input nodes
                        # Find __composite_input__ nodes and set their values
                        # Use the canvas_to_ir_map to find the correct IR node IDs
                        for ir_node in internal_ir.nodes:
                            if isinstance(ir_node.kind, Custom) and ir_node.kind.name == '__composite_input__':
                                # Find the canvas ID that maps to this IR node
                                canvas_id = None
                                for cid, irid in composite_backend.canvas_to_ir_map.items():
                                    if irid == ir_node.id.id:
                                        canvas_id = cid
                                        break
                                
                                if canvas_id is not None:
                                    # Now find the external name for this canvas_id in the input mapping
                                    for ext_name, input_info in input_mapping.items():
                                        if input_info.get('node') == canvas_id:
                                            # This input node should output the external input value
                                            coerced = input_values.get(ext_name)
                                            print(f"  Mapping external input '{ext_name}' -> internal canvas node {canvas_id} (ir {ir_node.id.id}) value={coerced}")
                                            internal_ir.widget_values[ir_node.id.id] = {'__input_value': coerced}
                        
                        # Execute the internal graph
                        composite_ctx = ExecutionContext()
                        composite_ctx.ir_module = internal_ir
                        
                        # Execute all internal nodes
                        sorted_internal = composite_backend._topological_sort(internal_ir)
                        for internal_node in sorted_internal:
                            try:
                                internal_result = composite_backend._execute_node(internal_node, composite_ctx)
                                composite_ctx.set_value(internal_node.id, internal_result)
                                print(f"  Internal node {internal_node.id.id} ({internal_node.kind.__class__.__name__}): {internal_result}")
                            except Exception as e:
                                print(f"Error in internal node {internal_node.id.id}: {e}")

                        print(f"  After internal execution composite_ctx.values={composite_ctx.values}")
                        
                        # Find the output value from __composite_output__ nodes
                        # Match the output node ID from the output mapping
                        output_values = {}
                        for ext_output_name, output_info in output_mapping.items():
                            output_node_id = output_info.get('node')
                            if output_node_id:
                                # Map canvas output node ID to internal IR node ID
                                ir_output_id = composite_backend.canvas_to_ir_map.get(output_node_id)
                                if ir_output_id is None:
                                    # Try string/int variations
                                    try:
                                        ir_output_id = composite_backend.canvas_to_ir_map.get(int(output_node_id))
                                    except Exception:
                                        ir_output_id = None
                                if ir_output_id is None:
                                    # As a fallback, search the map values for a match
                                    for cid, irid in composite_backend.canvas_to_ir_map.items():
                                        if cid == output_node_id:
                                            ir_output_id = irid
                                            break
                                # Get the value computed by this output node
                                if ir_output_id is not None:
                                    output_value = composite_ctx.values.get(ir_output_id)
                                else:
                                    output_value = None
                                output_values[ext_output_name] = output_value
                                print(f"Composite output '{ext_output_name}' from canvas node {output_node_id} -> ir {ir_output_id}: {output_value}")
                        
                        # For single-output composites, return the first output value
                        if len(output_values) == 1:
                            result = list(output_values.values())[0]
                        elif output_values:
                            # Multiple outputs - return as dict
                            result = output_values
                        else:
                            result = None
                        
                        print(f"Composite '{kind.name}' returning: {result}")
                        return result
                    except Exception as e:
                        print(f"Error executing composite {kind.name}: {e}")
                        traceback.print_exc()
                        return None
            
            # Non-composite custom nodes: execute via their process function
            try:
                # Get the node template
                try:
                    from py_editor.core import node_templates
                except:
                    try:
                        from ..core import node_templates
                    except:
                        from core import node_templates
                
                template = node_templates.get_template(kind.name)
                # Determine expected input names from the template (if present)
                inputs_def = template.get('inputs', {}) if template else {}
                input_names = list(inputs_def.keys())

                # Collect input values (either connected values or widget values)
                input_values = []
                for idx, input_id in enumerate(kind.inputs):
                    if input_id:
                        value = self._get_value_with_pin_extraction(input_id, node.id.id, idx, ctx)
                    elif idx < len(input_names):
                        # Use widget value if available
                        pin_name = input_names[idx]
                        value = widget_vals.get(pin_name)
                    else:
                        value = None
                    input_values.append(value)

                print(f"Custom node '{kind.name}' inputs_def={input_names} input_values={input_values} widget_vals={widget_vals}")

                # Try plugin module first — plugin modules should be honored even when
                # nodes do not provide inline `code` in their JSON templates.
                plugin_module = node_templates.get_node_module(kind.name)
                if plugin_module:
                    func_name = f"process_{kind.name}"
                    if hasattr(plugin_module, func_name):
                        func = getattr(plugin_module, func_name)
                        result = func(*input_values)
                        print(f"Custom node {kind.name} executed via plugin module: {input_values} -> {result}")
                        return result
                    elif hasattr(plugin_module, 'process'):
                        result = plugin_module.process(kind.name, *input_values)
                        print(f"Custom node {kind.name} executed via plugin module: {input_values} -> {result}")
                        return result

                # ===== SPECIAL: CallLogic - execute target graph and return result =====
                if kind.name == 'CallLogic':
                    graph_path = widget_vals.get('graphPath')
                    if graph_path:
                        print(f"CallLogic executing target: {graph_path}")
                        try:
                            import json
                            from pathlib import Path
                            
                            # Load target graph
                            with open(graph_path, 'r', encoding='utf-8') as f:
                                target_graph = json.load(f)
                            
                            # Create a new backend for the subgraph
                            sub_backend = IRBackend()
                            sub_ir = sub_backend.canvas_to_ir(target_graph, node_templates.get_all_templates())
                            
                            # Execute the subgraph in a new context
                            sub_ctx = ExecutionContext()
                            sub_ctx.variables = dict(ctx.variables)  # Share variables
                            
                            result = sub_backend.execute_ir(sub_ir, sub_ctx)
                            
                            print(f"CallLogic '{Path(graph_path).stem}' returned: {result}")
                            
                            # Return the result - it's from the Return node inside
                            if isinstance(result, dict) and 'return' in result:
                                return result['return']
                            return result
                            
                        except Exception as e:
                            print(f"Error executing CallLogic target '{graph_path}': {e}")
                            traceback.print_exc()
                            return None
                    else:
                        print(f"CallLogic has no graphPath set")
                        return None

                # ===== SPECIAL: Message - invoke custom event (self or external) =====
                if kind.name == 'Message':
                    # Input order: exec(0), target(1), payload(2)
                    # Skip exec at index 0, target is at index 1
                    target = input_values[1] if len(input_values) > 1 else None
                    event_name = widget_vals.get('event', 'MyEvent')
                    payload = input_values[2] if len(input_values) > 2 else None
                    
                    # Filter out exec signals that may have leaked through
                    if isinstance(target, str) and target in ('exec_out', 'exec'):
                        target = None
                    
                    print(f"Message: target={target}, event={event_name}, payload={payload}")
                    
                    # Determine graph path
                    graph_path = None
                    is_self = False
                    
                    if target is None or target == '' or (isinstance(target, str) and target.lower() == 'self'):
                        # Self invocation - use current graph
                        graph_path = ctx.variables.get('__current_graph_path__')
                        is_self = True
                        print(f"Message: invoking on SELF ({graph_path})")
                    elif isinstance(target, dict) and 'graphPath' in target:
                        # External reference handle
                        graph_path = target['graphPath']
                    elif isinstance(target, str):
                        # Direct path string
                        graph_path = target
                    
                    if graph_path:
                        try:
                            import json
                            from pathlib import Path
                            
                            # Load target graph
                            with open(graph_path, 'r', encoding='utf-8') as f:
                                target_graph = json.load(f)
                            
                            # Create a new backend for the subgraph
                            sub_backend = IRBackend()
                            sub_ir = sub_backend.canvas_to_ir(target_graph, node_templates.get_all_templates())
                            
                            # Execute the subgraph with event context
                            sub_ctx = ExecutionContext()
                            
                            # Load the TARGET graph's defined variables first
                            target_vars = target_graph.get('variables', {})
                            for var_name, var_info in target_vars.items():
                                if isinstance(var_info, dict):
                                    sub_ctx.variables[var_name] = var_info.get('value')
                                else:
                                    sub_ctx.variables[var_name] = var_info
                            
                            # Add message context
                            sub_ctx.variables['__event__'] = event_name
                            sub_ctx.variables['__payload__'] = payload
                            sub_ctx.variables['__current_graph_path__'] = graph_path
                            
                            print(f"Message: loaded target variables: {list(sub_ctx.variables.keys())}")
                            
                            result = sub_backend.execute_ir(sub_ir, sub_ctx)
                            
                            print(f"Message '{event_name}' returned: {result}")
                            return result.get('return') if isinstance(result, dict) else result
                            
                        except Exception as e:
                            print(f"Error invoking event '{event_name}': {e}")
                            traceback.print_exc()
                            return None
                    else:
                        if is_self:
                            print(f"Message: self invocation but no __current_graph_path__ set")
                        else:
                            print(f"Message: invalid target {target}")
                    return None

                # ===== SPECIAL: Reference - return opaque handle =====
                if kind.name == 'Reference':
                    graph_path = widget_vals.get('graphPath')
                    # Return an opaque handle (dict with path, not the data)
                    return {'graphPath': graph_path, '__type__': 'instance'}

                # ===== ANIMATION NODES =====
                
                # Play - starts an animation on a target
                if kind.name == 'Play':
                    target = input_values[1] if len(input_values) > 1 else None
                    anim_name = widget_vals.get('animation', 'idle')
                    loop_mode = widget_vals.get('loop', 'once')
                    speed = input_values[2] if len(input_values) > 2 else 1.0
                    
                    # Store animation state in context
                    if target:
                        anim_state = ctx.variables.setdefault('__anim_states__', {})
                        target_id = str(target.get('graphPath', id(target))) if isinstance(target, dict) else str(target)
                        anim_state[target_id] = {
                            'animation': anim_name,
                            'loop': loop_mode,
                            'speed': speed,
                            'time': 0.0,
                            'playing': True
                        }
                        print(f"Animation: Play '{anim_name}' on {target_id} (loop={loop_mode}, speed={speed})")
                    return ('exec_out',)
                
                # Stop - stops animation on a target
                if kind.name == 'Stop':
                    target = input_values[1] if len(input_values) > 1 else None
                    
                    if target:
                        anim_state = ctx.variables.get('__anim_states__', {})
                        target_id = str(target.get('graphPath', id(target))) if isinstance(target, dict) else str(target)
                        if target_id in anim_state:
                            anim_state[target_id]['playing'] = False
                        print(f"Animation: Stop on {target_id}")
                    return ('exec_out',)
                
                # Blend - blends between two animations
                if kind.name == 'Blend':
                    target = input_values[1] if len(input_values) > 1 else None
                    weight = input_values[2] if len(input_values) > 2 else 0.5
                    animA = widget_vals.get('animA', 'idle')
                    animB = widget_vals.get('animB', 'walk')
                    
                    if target:
                        anim_state = ctx.variables.setdefault('__anim_states__', {})
                        target_id = str(target.get('graphPath', id(target))) if isinstance(target, dict) else str(target)
                        anim_state[target_id] = {
                            'animation': f"blend({animA},{animB})",
                            'animA': animA,
                            'animB': animB,
                            'weight': weight,
                            'playing': True
                        }
                        print(f"Animation: Blend {animA} -> {animB} (weight={weight}) on {target_id}")
                    return ('exec_out',)
                
                # OnTick - animation event that receives delta time
                if kind.name == 'OnTick':
                    dt = ctx.variables.get('__delta_time__', 0.016)
                    print(f"Animation: OnTick dt={dt}")
                    return ('exec_out', dt)
                
                # OnFinished - animation completion event
                if kind.name == 'OnFinished':
                    anim_name = ctx.variables.get('__finished_animation__', '')
                    print(f"Animation: OnFinished '{anim_name}'")
                    return ('exec_out', anim_name)
                
                # OnLoop - animation loop event
                if kind.name == 'OnLoop':
                    loop_count = ctx.variables.get('__loop_count__', 0)
                    print(f"Animation: OnLoop count={loop_count}")
                    return ('exec_out', loop_count)


                # If a template provides inline `code`, fall back to executing it
                if template and template.get('code'):
                    try:
                        code = template.get('code')
                        local_vars = {}
                        import math
                        import random
                        globals_dict = {
                            '__builtins__': __builtins__,
                            'math': math,
                            'random': random,
                        }
                        exec(code, globals_dict, local_vars)
                        if 'process' in local_vars:
                            result = local_vars['process'](*input_values)
                            print(f"Custom node {kind.name} executed: {input_values} -> {result}")
                            return result
                    except Exception:
                        print(f"Error executing inline code for custom node {kind.name}")
                        traceback.print_exc()
            except Exception as e:
                print(f"Error executing custom node {kind.name}: {e}")
                traceback.print_exc()
            
            return None
        
        # Binary operations
        elif isinstance(kind, Add):
            # Use connected value if available, otherwise use widget value
            a = ctx.get_value(kind.a) if kind.a else widget_vals.get('a', 0)
            b = ctx.get_value(kind.b) if kind.b else widget_vals.get('b', 0)
            return a + b
        
        elif isinstance(kind, Subtract):
            a = ctx.get_value(kind.a) if kind.a else widget_vals.get('a', 0)
            b = ctx.get_value(kind.b) if kind.b else widget_vals.get('b', 0)
            return a - b
        
        elif isinstance(kind, Multiply):
            a = ctx.get_value(kind.a) if kind.a else widget_vals.get('a', 1)
            b = ctx.get_value(kind.b) if kind.b else widget_vals.get('b', 1)
            return a * b
        
        elif isinstance(kind, Divide):
            a = ctx.get_value(kind.a) if kind.a else widget_vals.get('a', 0)
            b = ctx.get_value(kind.b) if kind.b else widget_vals.get('b', 1)
            if b == 0:
                return float('inf')
            return a / b
        
        # Print (debug output) - passes value through
        elif isinstance(kind, Print):
            value = self._get_value_with_pin_extraction(kind.value, node.id.id, 0, ctx) if kind.value else None
            # For Print nodes, check if label comes from widget_values
            label_value = None
            if kind.label:
                label_value = self._get_value_with_pin_extraction(kind.label, node.id.id, 1, ctx)
            # If no label from connections, check widget values
            if not label_value:
                widget_vals = self.module.widget_values.get(node.id.id, {})
                label_value = widget_vals.get('label', '')
            label = str(label_value) if label_value else ""
            prefix = f"[{label}] " if label else ""
            output_text = f"{prefix}{value}"
            print(output_text)  # Print immediately to console like UE5
            return value  # Pass the value through so it can be used by other nodes
        
        # Return - only returns if enabled
        elif isinstance(kind, Return):
            # Check enabled flag - default to True if not connected
            enabled = True
            if kind.enabled:
                enabled = self._get_value_with_pin_extraction(kind.enabled, node.id.id, 0, ctx)
            else:
                # Check widget value for enabled
                enabled = widget_vals.get('enabled', True)
            
            # Only return value if enabled
            if enabled:
                if kind.value:
                    return self._get_value_with_pin_extraction(kind.value, node.id.id, 1, ctx)
                return widget_vals.get('value')
            # Return special marker to indicate disabled return
            return '__RETURN_DISABLED__'
        
        # SetVar - store value in variables dict
        elif isinstance(kind, SetVar):
            var_name = ctx.get_value(kind.var_name) if kind.var_name else widget_vals.get('name', '')
            value = ctx.get_value(kind.value) if kind.value else widget_vals.get('value')
            print(f"SetVariable debug: kind.var_name={kind.var_name}, widget_vals={widget_vals}, var_name={var_name}, value={value}")
            if var_name:
                ctx.variables[str(var_name)] = value
                print(f"SetVariable: {var_name} = {value}")
                print(f"  Variables dict now: {ctx.variables}")
            return value  # Pass value through
        
        # GetVar - retrieve value from variables dict
        elif isinstance(kind, GetVar):
            var_name = ctx.get_value(kind.var_name) if kind.var_name else widget_vals.get('name', '')
            print(f"GetVariable debug: kind.var_name={kind.var_name}, widget_vals={widget_vals}, var_name={var_name}")
            print(f"  Available variables: {ctx.variables}")
            value = ctx.variables.get(str(var_name))
            # Handle variable storage format - extract 'value' if stored as {type, value}
            if isinstance(value, dict) and 'type' in value and 'value' in value:
                value = value['value']
            print(f"GetVariable: {var_name} -> {value}")
            return value
        
        return None


def execute_canvas_graph(canvas_graph: dict, node_templates: dict, canvas_breakpoints: set = None, graph_variables: dict = None) -> Dict[str, Any]:
    """
    High-level function to execute a canvas graph.
    
    Args:
        canvas_graph: Graph data from canvas.export_graph()
        node_templates: Map of template name -> template data
        canvas_breakpoints: Set of canvas node IDs that have breakpoints
        graph_variables: Dict of variable_name -> default_value for graph-level variables
    
    Returns:
        Dictionary of execution results including '_canvas_to_ir_map' and '_node_errors'
    """
    backend = IRBackend()
    ir_module = backend.canvas_to_ir(canvas_graph, node_templates)
    
    # Convert canvas breakpoints to IR node IDs
    ir_breakpoints = set()
    if canvas_breakpoints:
        for canvas_id in canvas_breakpoints:
            ir_id = backend.canvas_to_ir_map.get(canvas_id)
            if ir_id is not None:
                ir_breakpoints.add(ir_id)
    
    # Create execution context with graph variables
    ctx = ExecutionContext()
    if graph_variables:
        # Extract just the values from the graph_variables dict
        # graph_variables format: {var_name: {'type': 'int', 'value': 42}}
        ctx.variables = {name: info['value'] for name, info in graph_variables.items()}
    
    results = backend.execute_ir(ir_module, ctx=ctx, breakpoints=ir_breakpoints)
    # Add the mapping from canvas IDs to IR IDs
    results['_canvas_to_ir_map'] = backend.canvas_to_ir_map
    return results


# Alias for backwards compatibility
InterpreterBackend = IRBackend

__all__ = ['IRBackend', 'InterpreterBackend', 'ExecutionContext', 'execute_canvas_graph']

