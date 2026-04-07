"""
Core logic for NodeCanvas - IR types and template management.

NOTE: ExecutionContext and IRBackend have moved to py_editor.backends.
They are re-exported here for backwards compatibility but will be removed.
"""

from .ir import (
    NodeId,
    Value,
    ValueType,
    IRNodeKind,
    ConstValue,
    Add,
    Subtract,
    Multiply,
    Divide,
    Return,
    Print,
    Custom,
    SetVar,
    GetVar,
    IRNode,
    IRModule,
)
from .node_templates import (
    load_templates,
    list_templates,
    get_template,
    get_all_templates,
    save_template,
    delete_template,
    save_graph,
)
from .graph_interface import (
    PinDefinition,
    GraphInterface,
    load_graph_interface,
)


def __getattr__(name):
    """Lazy import for backwards compatibility - avoids circular imports"""
    if name in ('ExecutionContext', 'IRBackend'):
        import warnings
        warnings.warn(
            f"Importing {name} from py_editor.core is deprecated. "
            f"Use py_editor.backends.{name} instead.",
            DeprecationWarning,
            stacklevel=2
        )
        from py_editor.backends.interpreter import ExecutionContext, IRBackend
        return ExecutionContext if name == 'ExecutionContext' else IRBackend
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    # IR types
    'NodeId',
    'Value',
    'ValueType',
    'IRNodeKind',
    'ConstValue',
    'Add',
    'Subtract',
    'Multiply',
    'Divide',
    'Return',
    'Print',
    'Custom',
    'SetVar',
    'GetVar',
    'IRNode',
    'IRModule',
    # Templates
    'load_templates',
    'list_templates',
    'get_template',
    'get_all_templates',
    'save_template',
    'delete_template',
    'save_graph',
    # Graph interface
    'PinDefinition',
    'GraphInterface',
    'load_graph_interface',
    # Deprecated - use py_editor.backends
    'ExecutionContext',
    'IRBackend',
]
