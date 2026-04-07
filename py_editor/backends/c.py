"""
C Codegen Backend

Generates C code from IR with SDL2 audio support.
This is the canonical location for CCodegen.
"""

from .codegen_common import CBackend as CCodegen, CodeGenConfig

__all__ = ['CCodegen', 'CodeGenConfig']
