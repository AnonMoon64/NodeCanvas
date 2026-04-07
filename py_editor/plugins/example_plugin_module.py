"""
Example plugin module for NodeCanvas

This module provides custom Python functions for plugin nodes.

Function naming convention:
- process_NodeName(*inputs) - Specific function for a node
- process(node_name, *inputs) - Generic handler for all nodes in package
"""

def process_FormatString(template, value):
    """Format a string with a value"""
    if template is None:
        template = "{}"
    if value is None:
        value = ""
    try:
        return str(template).format(value)
    except:
        return str(template) + str(value)

def process_RandomNumber(min_val, max_val):
    """Generate a random number between min and max"""
    import random
    min_v = min_val if min_val is not None else 0.0
    max_v = max_val if max_val is not None else 1.0
    return random.uniform(min_v, max_v)

def process_ListLength(items):
    """Get the length of a list (passed as string representation)"""
    if items is None:
        return 0
    if isinstance(items, (list, tuple)):
        return len(items)
    # Try to parse string representation
    try:
        import ast
        parsed = ast.literal_eval(str(items))
        if isinstance(parsed, (list, tuple)):
            return len(parsed)
    except:
        pass
    return len(str(items).split(','))

# Generic processor that can handle any node
def process(node_name, *inputs):
    """
    Generic process function that handles nodes based on their name
    This is called if no specific process_NodeName function exists
    """
    # You can add fallback logic here
    print(f"Generic processor called for {node_name} with inputs: {inputs}")
    return inputs[0] if inputs else None
