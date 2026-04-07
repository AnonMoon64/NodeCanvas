"""
NodeCanvas Backends Package

All backends that consume IR live here.
The core/ directory defines types and base classes.
This directory contains concrete implementations.

Architecture:
    Nodes (graph JSON) → IR → Backends
                              ├── InterpreterBackend (executes in editor)
                              ├── PythonCodegen (emits .py)
                              ├── CCodegen (emits .c)
                              ├── CppCodegen (emits .cpp)
                              └── WasmCodegen (emits .c for Emscripten)

Interpreter Types (by file extension):
    .logic → LogicInterpreter (instant execution)
    .anim  → AnimInterpreter (timeline-based with keyframes)
    .ui    → UIInterpreter (event-driven, persistent state)

Build System:
    BuildSystem creates deployable packages with:
    - Composite node inlining
    - Asset bundling (audio, images)
    - Python GUI wrapper that loads backend

Usage:
    from py_editor.backends import BACKENDS
    backend = BACKENDS['python'](ir_module, config)
    code = backend.generate()
    
    # Use type-specific interpreters
    from py_editor.backends import get_interpreter, execute_graph_file
    interpreter = get_interpreter('.logic')
    result = interpreter.execute(ir_module, inputs)
    
    # Full build with GUI wrapper
    from py_editor.backends import BuildSystem, BuildConfig
    config = BuildConfig(target='python', output_dir='./build')
    builder = BuildSystem(config)
    builder.build(ir_module, ui_data=ui_data)
"""

# Import concrete backends from their canonical locations
from .interpreter import InterpreterBackend, IRBackend, ExecutionContext, execute_canvas_graph
from .python import PythonCodegen, PythonBackend
from .c import CCodegen
from .cpp import CppCodegen
from .wasm import WasmCodegen
from .codegen_common import CodeGenConfig

# Interpreter types for different file formats
from .interpreters import (
    ExecutionState,
    ExecutionResult,
    BaseInterpreter,
    LogicInterpreter,
    AnimInterpreter,
    UIInterpreter,
    get_interpreter,
    execute_graph_file,
)

# Build system
from .build_system import BuildSystem, BuildConfig, AssetCollector, CompositeInliner, build_app

# Registry for easy access
BACKENDS = {
    'interpreter': InterpreterBackend,
    'python': PythonCodegen,
    'c': CCodegen,
    'cpp': CppCodegen,
    'wasm': WasmCodegen,
}

# Interpreter types by file extension
INTERPRETERS = {
    'logic': LogicInterpreter,
    'anim': AnimInterpreter,
    'ui': UIInterpreter,
    'json': LogicInterpreter,  # Legacy support
}

__all__ = [
    'BACKENDS',
    'INTERPRETERS',
    'InterpreterBackend',
    'IRBackend',
    'ExecutionContext',
    'execute_canvas_graph',
    'PythonCodegen',
    'PythonBackend',
    'CCodegen',
    'CppCodegen',
    'WasmCodegen',
    'CodeGenConfig',
    # Interpreter types
    'ExecutionState',
    'ExecutionResult',
    'BaseInterpreter',
    'LogicInterpreter',
    'AnimInterpreter',
    'UIInterpreter',
    'get_interpreter',
    'execute_graph_file',
    # Build system
    'BuildSystem',
    'BuildConfig',
    'AssetCollector',
    'CompositeInliner',
    'build_app',
]
