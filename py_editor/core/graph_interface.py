"""
Graph Interface Schema

Defines the public interface of a graph when used as a callable node.
When you drag a .logic/.anim/.ui file into a graph, this interface
determines what ports are exposed.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional
from pathlib import Path
import json


@dataclass
class PinDefinition:
    """Definition of an input or output pin"""
    name: str
    pin_type: str  # "exec", "int", "float", "string", "bool", "any"
    description: str = ""
    default: Any = None
    
    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "type": self.pin_type,
            "description": self.description,
            "default": self.default,
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "PinDefinition":
        return cls(
            name=data.get("name", ""),
            pin_type=data.get("type", "any"),
            description=data.get("description", ""),
            default=data.get("default"),
        )


@dataclass
class GraphInterface:
    """
    Public interface of a graph when used as a callable node.
    
    This is what external graphs see when they reference this graph.
    It does NOT expose internals - only declared inputs/outputs.
    """
    name: str
    graph_type: str  # "logic", "anim", "ui"
    
    # Declared ports
    inputs: Dict[str, PinDefinition] = field(default_factory=dict)
    outputs: Dict[str, PinDefinition] = field(default_factory=dict)
    
    # Execution lifecycle
    entry_points: List[str] = field(default_factory=lambda: ["exec"])
    exit_points: List[str] = field(default_factory=lambda: ["exec"])
    
    # Metadata
    file_path: str = ""
    description: str = ""
    version: str = "1.0"
    
    def to_dict(self) -> Dict:
        return {
            "interface": {
                "name": self.name,
                "type": self.graph_type,
                "description": self.description,
                "version": self.version,
                "inputs": {k: v.to_dict() for k, v in self.inputs.items()},
                "outputs": {k: v.to_dict() for k, v in self.outputs.items()},
                "entry_points": self.entry_points,
                "exit_points": self.exit_points,
            }
        }
    
    @classmethod
    def from_dict(cls, data: Dict, file_path: str = "") -> "GraphInterface":
        """Parse interface from graph data"""
        iface = data.get("interface", {})
        
        inputs = {}
        for name, pin_data in iface.get("inputs", {}).items():
            if isinstance(pin_data, dict):
                inputs[name] = PinDefinition.from_dict({**pin_data, "name": name})
            else:
                inputs[name] = PinDefinition(name=name, pin_type=str(pin_data))
        
        outputs = {}
        for name, pin_data in iface.get("outputs", {}).items():
            if isinstance(pin_data, dict):
                outputs[name] = PinDefinition.from_dict({**pin_data, "name": name})
            else:
                outputs[name] = PinDefinition(name=name, pin_type=str(pin_data))
        
        return cls(
            name=iface.get("name", Path(file_path).stem if file_path else "Unnamed"),
            graph_type=iface.get("type", cls._infer_type(file_path)),
            inputs=inputs,
            outputs=outputs,
            entry_points=iface.get("entry_points", ["exec"]),
            exit_points=iface.get("exit_points", ["exec"]),
            file_path=file_path,
            description=iface.get("description", ""),
            version=iface.get("version", "1.0"),
        )
    
    @classmethod
    def _infer_type(cls, file_path: str) -> str:
        """Infer graph type from file extension"""
        if not file_path:
            return "logic"
        ext = Path(file_path).suffix.lower()
        if ext == ".anim":
            return "anim"
        elif ext == ".ui":
            return "ui"
        return "logic"
    
    @classmethod
    def from_file(cls, file_path: str) -> "GraphInterface":
        """Load interface from a graph file"""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Graph file not found: {file_path}")
        
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        return cls.from_dict(data, str(path))
    
    @classmethod
    def extract_from_graph(cls, graph_data: Dict, file_path: str = "") -> "GraphInterface":
        """
        Extract interface from a graph that doesn't have explicit interface declaration.
        
        Looks for special nodes:
        - InterfaceInput nodes → become inputs
        - InterfaceOutput nodes → become outputs
        - OnStart/OnComplete nodes → become entry/exit points
        """
        inputs = {}
        outputs = {}
        entry_points = []
        exit_points = []
        
        # Check if explicit interface exists
        if "interface" in graph_data:
            return cls.from_dict(graph_data, file_path)
        
        # Otherwise, scan for interface nodes
        nodes = graph_data.get("nodes", [])
        
        for node in nodes:
            template = node.get("template", "")
            widget_vals = node.get("widgetValues", {})
            
            # Interface input nodes define inputs
            if template in ("InterfaceInput", "GraphInput", "__interface_input__"):
                name = widget_vals.get("name", f"input_{node.get('id', 0)}")
                pin_type = widget_vals.get("type", "any")
                inputs[name] = PinDefinition(
                    name=name,
                    pin_type=pin_type,
                    description=widget_vals.get("description", ""),
                    default=widget_vals.get("default"),
                )
            
            # Interface output nodes define outputs
            elif template in ("InterfaceOutput", "GraphOutput", "__interface_output__"):
                name = widget_vals.get("name", f"output_{node.get('id', 0)}")
                pin_type = widget_vals.get("type", "any")
                outputs[name] = PinDefinition(
                    name=name,
                    pin_type=pin_type,
                    description=widget_vals.get("description", ""),
                )
            
            # Entry point nodes
            elif template in ("OnStart", "OnTick", "OnEvent"):
                entry_points.append(template)
            
            # Exit point nodes  
            elif template in ("Return", "OnComplete", "Exit"):
                exit_points.append(template)
        
        # Default entry/exit if none found
        if not entry_points:
            entry_points = ["exec"]
        if not exit_points:
            exit_points = ["exec"]
        
        # Always add exec input for triggering
        if "exec" not in inputs:
            inputs = {"exec": PinDefinition("exec", "exec", "Trigger execution"), **inputs}
        if "exec" not in outputs:
            outputs = {"exec": PinDefinition("exec", "exec", "Fires on completion"), **outputs}
        
        return cls(
            name=Path(file_path).stem if file_path else "Unnamed",
            graph_type=cls._infer_type(file_path),
            inputs=inputs,
            outputs=outputs,
            entry_points=entry_points,
            exit_points=exit_points,
            file_path=file_path,
        )


def load_graph_interface(file_path: str) -> GraphInterface:
    """
    Load a graph file and extract its public interface.
    
    This is what gets called when you drag a .logic file into a graph.
    """
    path = Path(file_path)
    
    # Check extension
    valid_extensions = {".logic", ".anim", ".ui", ".json"}
    if path.suffix.lower() not in valid_extensions:
        raise ValueError(f"Invalid graph file type: {path.suffix}")
    
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    return GraphInterface.extract_from_graph(data, str(path))


__all__ = [
    'PinDefinition',
    'GraphInterface', 
    'load_graph_interface',
]
