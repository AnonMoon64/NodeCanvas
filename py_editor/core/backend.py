"""
==============================================================================
DEPRECATED - DO NOT USE IN NEW CODE
==============================================================================

This module exists ONLY for backwards compatibility with old import paths.
All new code should import from `py_editor.backends` instead.

Old (deprecated):
    from py_editor.core.backend import IRBackend, PythonBackend

New (correct):
    from py_editor.backends import InterpreterBackend, PythonCodegen, BACKENDS

This file will be REMOVED in version 4.0.0.

==============================================================================
"""

import warnings
warnings.warn(
    "py_editor.core.backend is deprecated. "
    "Import from py_editor.backends instead.",
    DeprecationWarning,
    stacklevel=2
)

# Re-export from the canonical location for backwards compatibility
from py_editor.backends.interpreter import (
    IRBackend,
    InterpreterBackend,
    ExecutionContext,
    execute_canvas_graph,
)

from py_editor.backends.python import (
    PythonCodegen,
    PythonBackend,
)

__all__ = [
    'IRBackend',
    'InterpreterBackend', 
    'ExecutionContext',
    'execute_canvas_graph',
    'PythonBackend',
    'PythonCodegen',
]
