"""
WASM Codegen Backend

Generates C code for Emscripten/WebAssembly compilation.
This is the canonical location for WasmCodegen.
"""

from .codegen_common import WasmBackend as WasmCodegen, CodeGenConfig

__all__ = ['WasmCodegen', 'CodeGenConfig']
