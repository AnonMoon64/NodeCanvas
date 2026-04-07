"""
C++ Codegen Backend

Generates C++ code from IR with SDL2 audio support.
This is the canonical location for CppCodegen.
"""

from .codegen_common import CppBackend as CppCodegen, CodeGenConfig

__all__ = ['CppCodegen', 'CodeGenConfig']
