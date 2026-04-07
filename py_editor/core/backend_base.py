"""
Backend Base Classes

Defines the abstract interfaces for all backends.
Concrete implementations live in py_editor/backends/
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class BackendBase(ABC):
    """Abstract base class for all backends that consume IR"""
    
    def __init__(self, ir_module):
        self.ir = ir_module
    
    @abstractmethod
    def execute(self) -> Any:
        """Execute/process the IR. Returns result."""
        pass


class InterpreterBackendBase(BackendBase):
    """Base class for interpreter backends that execute IR directly"""
    
    @abstractmethod
    def execute(self) -> Any:
        """Execute the IR and return the result"""
        pass
    
    @abstractmethod
    def step(self) -> Any:
        """Execute one step of the IR (for debugging)"""
        pass


class CodegenBackendBase(BackendBase):
    """Base class for codegen backends that emit source code"""
    
    def __init__(self, ir_module, config: Optional[Dict] = None):
        super().__init__(ir_module)
        self.config = config or {}
    
    @abstractmethod
    def generate(self) -> str:
        """Generate source code from IR. Returns the generated code string."""
        pass
    
    def execute(self) -> str:
        """For codegen backends, execute means generate"""
        return self.generate()
    
    # Common helpers that codegen backends can use
    def _safe_identifier(self, name: str) -> str:
        """Convert a name to a safe identifier for the target language"""
        return ''.join(c if c.isalnum() else '_' for c in name)
    
    def _escape_string(self, s: str) -> str:
        """Escape a string for embedding in generated code"""
        return s.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
