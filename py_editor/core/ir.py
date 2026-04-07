"""
Python IR module - Language-neutral intermediate representation for NodeCanvas.
Converted from Rust core/src/ir.rs for Python integration.
"""
import json
from typing import Optional, Dict, List, Tuple, Any, Union
from dataclasses import dataclass, field, asdict
from enum import Enum


@dataclass
class NodeId:
    """Simple NodeId for the prototype. Later this can use generational handles."""
    id: int
    
    def __hash__(self):
        return hash(self.id)
    
    def __eq__(self, other):
        if isinstance(other, NodeId):
            return self.id == other.id
        return False
    
    def to_dict(self):
        return self.id
    
    @staticmethod
    def from_dict(data):
        return NodeId(data)


class ValueType(str, Enum):
    """Types for IR values"""
    INT = "int"
    FLOAT = "float"
    BOOL = "bool"
    STRING = "string"


@dataclass
class Value:
    """Generic value type for simple built-in constants and defaults."""
    type: ValueType
    data: Union[int, float, bool, str]
    
    def to_dict(self):
        return {"type": self.type.value, "data": self.data}
    
    @staticmethod
    def from_dict(data):
        vtype = ValueType(data["type"])
        return Value(vtype, data["data"])
    
    @staticmethod
    def int_value(value: int):
        return Value(ValueType.INT, value)
    
    @staticmethod
    def float_value(value: float):
        return Value(ValueType.FLOAT, value)
    
    @staticmethod
    def bool_value(value: bool):
        return Value(ValueType.BOOL, value)
    
    @staticmethod
    def string_value(value: str):
        return Value(ValueType.STRING, value)


@dataclass
class IRNodeKind:
    """Base class for IR node kinds"""
    
    def get_type(self) -> str:
        return self.__class__.__name__
    
    def to_dict(self):
        raise NotImplementedError


@dataclass
class ConstValue(IRNodeKind):
    """Constant with a typed value"""
    value: Value
    
    def to_dict(self):
        return {
            "type": "ConstValue",
            "value": self.value.to_dict()
        }
    
    @staticmethod
    def from_dict(data):
        return ConstValue(Value.from_dict(data["value"]))


@dataclass
class Add(IRNodeKind):
    """Add operation with optional inputs"""
    a: Optional[NodeId] = None
    b: Optional[NodeId] = None
    
    def to_dict(self):
        return {
            "type": "Add",
            "a": self.a.to_dict() if self.a else None,
            "b": self.b.to_dict() if self.b else None
        }
    
    @staticmethod
    def from_dict(data):
        a = NodeId.from_dict(data["a"]) if data.get("a") is not None else None
        b = NodeId.from_dict(data["b"]) if data.get("b") is not None else None
        return Add(a, b)


@dataclass
class Subtract(IRNodeKind):
    """Subtract operation"""
    a: Optional[NodeId] = None
    b: Optional[NodeId] = None
    
    def to_dict(self):
        return {
            "type": "Subtract",
            "a": self.a.to_dict() if self.a else None,
            "b": self.b.to_dict() if self.b else None
        }
    
    @staticmethod
    def from_dict(data):
        a = NodeId.from_dict(data["a"]) if data.get("a") is not None else None
        b = NodeId.from_dict(data["b"]) if data.get("b") is not None else None
        return Subtract(a, b)


@dataclass
class Multiply(IRNodeKind):
    """Multiply operation"""
    a: Optional[NodeId] = None
    b: Optional[NodeId] = None
    
    def to_dict(self):
        return {
            "type": "Multiply",
            "a": self.a.to_dict() if self.a else None,
            "b": self.b.to_dict() if self.b else None
        }
    
    @staticmethod
    def from_dict(data):
        a = NodeId.from_dict(data["a"]) if data.get("a") is not None else None
        b = NodeId.from_dict(data["b"]) if data.get("b") is not None else None
        return Multiply(a, b)


@dataclass
class Divide(IRNodeKind):
    """Divide operation"""
    a: Optional[NodeId] = None
    b: Optional[NodeId] = None
    
    def to_dict(self):
        return {
            "type": "Divide",
            "a": self.a.to_dict() if self.a else None,
            "b": self.b.to_dict() if self.b else None
        }
    
    @staticmethod
    def from_dict(data):
        a = NodeId.from_dict(data["a"]) if data.get("a") is not None else None
        b = NodeId.from_dict(data["b"]) if data.get("b") is not None else None
        return Divide(a, b)


@dataclass
class Return(IRNodeKind):
    """Return node with enabled flag for conditional returns"""
    enabled: Optional[NodeId] = None  # If False, return is skipped
    value: Optional[NodeId] = None
    
    def to_dict(self):
        return {
            "type": "Return",
            "enabled": self.enabled.to_dict() if self.enabled else None,
            "value": self.value.to_dict() if self.value else None
        }
    
    @staticmethod
    def from_dict(data):
        enabled = NodeId.from_dict(data["enabled"]) if data.get("enabled") is not None else None
        value = NodeId.from_dict(data["value"]) if data.get("value") is not None else None
        return Return(enabled, value)


@dataclass
class Print(IRNodeKind):
    """Print/Debug node"""
    value: Optional[NodeId] = None
    label: Optional[NodeId] = None
    
    def to_dict(self):
        return {
            "type": "Print",
            "value": self.value.to_dict() if self.value else None,
            "label": self.label.to_dict() if self.label else None
        }
    
    @staticmethod
    def from_dict(data):
        value = NodeId.from_dict(data["value"]) if data.get("value") is not None else None
        label = NodeId.from_dict(data["label"]) if data.get("label") is not None else None
        return Print(value, label)


@dataclass
class SetVar(IRNodeKind):
    """Set a named variable in execution context"""
    var_name: Optional[NodeId] = None  # Node providing variable name
    value: Optional[NodeId] = None  # Node providing value to store
    
    def to_dict(self):
        return {
            "type": "SetVar",
            "var_name": self.var_name.to_dict() if self.var_name else None,
            "value": self.value.to_dict() if self.value else None
        }
    
    @staticmethod
    def from_dict(data):
        var_name = NodeId.from_dict(data["var_name"]) if data.get("var_name") is not None else None
        value = NodeId.from_dict(data["value"]) if data.get("value") is not None else None
        return SetVar(var_name, value)


@dataclass
class GetVar(IRNodeKind):
    """Get a named variable from execution context"""
    var_name: Optional[NodeId] = None  # Node providing variable name
    
    def to_dict(self):
        return {
            "type": "GetVar",
            "var_name": self.var_name.to_dict() if self.var_name else None
        }
    
    @staticmethod
    def from_dict(data):
        var_name = NodeId.from_dict(data["var_name"]) if data.get("var_name") is not None else None
        return GetVar(var_name)


@dataclass
class Custom(IRNodeKind):
    """Custom node type for extensibility"""
    name: str
    inputs: List[Optional[NodeId]] = field(default_factory=list)
    outputs: int = 1
    defaults: List[Optional[Value]] = field(default_factory=list)
    
    def to_dict(self):
        return {
            "type": "Custom",
            "name": self.name,
            "inputs": [inp.to_dict() if inp else None for inp in self.inputs],
            "outputs": self.outputs,
            "defaults": [d.to_dict() if d else None for d in self.defaults]
        }
    
    @staticmethod
    def from_dict(data):
        inputs = [NodeId.from_dict(i) if i is not None else None for i in data.get("inputs", [])]
        defaults = [Value.from_dict(d) if d is not None else None for d in data.get("defaults", [])]
        return Custom(data["name"], inputs, data.get("outputs", 1), defaults)


# Map for deserializing node kinds
NODE_KIND_MAP = {
    "ConstValue": ConstValue,
    "Add": Add,
    "Subtract": Subtract,
    "Multiply": Multiply,
    "Divide": Divide,
    "Return": Return,
    "Print": Print,
    "SetVar": SetVar,
    "GetVar": GetVar,
    "Custom": Custom,
}


@dataclass
class IRNode:
    """IR node with id and kind"""
    id: NodeId
    kind: IRNodeKind
    
    def to_dict(self):
        return {
            "id": self.id.to_dict(),
            "kind": self.kind.to_dict()
        }
    
    @staticmethod
    def from_dict(data):
        node_id = NodeId.from_dict(data["id"])
        kind_data = data["kind"]
        kind_type = kind_data["type"]
        kind_class = NODE_KIND_MAP.get(kind_type)
        if not kind_class:
            raise ValueError(f"Unknown node kind: {kind_type}")
        kind = kind_class.from_dict(kind_data)
        return IRNode(node_id, kind)


@dataclass
class IRModule:
    """IR module containing nodes and layout information"""
    nodes: List[IRNode] = field(default_factory=list)
    next_id: int = 1
    layout: Dict[int, Tuple[float, float]] = field(default_factory=dict)  # node_id -> (x, y)
    widget_values: Dict[int, Dict[str, Any]] = field(default_factory=dict)  # node_id -> {pin_name -> value}
    event_context: Dict[str, Any] = field(default_factory=dict)  # Context for event-driven execution (e.g., triggered button ID)
    # Map from (dest_node_id, input_index) -> (source_node_id, from_pin_name) for multi-output node connections
    source_pin_map: Dict[Tuple[int, int], Tuple[int, str]] = field(default_factory=dict)
    # Map from (source_node_id, from_pin_name) -> list of target node ids - for flow control nodes like Sequence
    output_connections: Dict[Tuple[int, str], List[int]] = field(default_factory=dict)
    
    def add_const_int(self, value: int) -> NodeId:
        """Add a constant integer node"""
        node_id = NodeId(self.next_id)
        self.next_id += 1
        node = IRNode(node_id, ConstValue(Value.int_value(value)))
        self.nodes.append(node)
        return node_id
    
    def add_const_float(self, value: float) -> NodeId:
        """Add a constant float node"""
        node_id = NodeId(self.next_id)
        self.next_id += 1
        node = IRNode(node_id, ConstValue(Value.float_value(value)))
        self.nodes.append(node)
        return node_id
    
    def add_const_bool(self, value: bool) -> NodeId:
        """Add a constant boolean node"""
        node_id = NodeId(self.next_id)
        self.next_id += 1
        node = IRNode(node_id, ConstValue(Value.bool_value(value)))
        self.nodes.append(node)
        return node_id
    
    def add_const_string(self, value: str) -> NodeId:
        """Add a constant string node"""
        node_id = NodeId(self.next_id)
        self.next_id += 1
        node = IRNode(node_id, ConstValue(Value.string_value(value)))
        self.nodes.append(node)
        return node_id
    
    def add_add(self, a: Optional[NodeId] = None, b: Optional[NodeId] = None) -> NodeId:
        """Add an addition node"""
        node_id = NodeId(self.next_id)
        self.next_id += 1
        node = IRNode(node_id, Add(a, b))
        self.nodes.append(node)
        return node_id
    
    def add_subtract(self, a: Optional[NodeId] = None, b: Optional[NodeId] = None) -> NodeId:
        """Add a subtraction node"""
        node_id = NodeId(self.next_id)
        self.next_id += 1
        node = IRNode(node_id, Subtract(a, b))
        self.nodes.append(node)
        return node_id
    
    def add_multiply(self, a: Optional[NodeId] = None, b: Optional[NodeId] = None) -> NodeId:
        """Add a multiplication node"""
        node_id = NodeId(self.next_id)
        self.next_id += 1
        node = IRNode(node_id, Multiply(a, b))
        self.nodes.append(node)
        return node_id
    
    def add_divide(self, a: Optional[NodeId] = None, b: Optional[NodeId] = None) -> NodeId:
        """Add a division node"""
        node_id = NodeId(self.next_id)
        self.next_id += 1
        node = IRNode(node_id, Divide(a, b))
        self.nodes.append(node)
        return node_id
    
    def add_return(self, enabled: Optional[NodeId] = None, value: Optional[NodeId] = None) -> NodeId:
        """Add a return node with optional enabled flag"""
        node_id = NodeId(self.next_id)
        self.next_id += 1
        node = IRNode(node_id, Return(enabled, value))
        self.nodes.append(node)
        return node_id
    
    def add_print(self, value: Optional[NodeId] = None, label: Optional[NodeId] = None) -> NodeId:
        """Add a print/debug node"""
        node_id = NodeId(self.next_id)
        self.next_id += 1
        node = IRNode(node_id, Print(value, label))
        self.nodes.append(node)
        return node_id
    
    def add_setvar(self, var_name: Optional[NodeId] = None, value: Optional[NodeId] = None) -> NodeId:
        """Add a SetVar node"""
        node_id = NodeId(self.next_id)
        self.next_id += 1
        node = IRNode(node_id, SetVar(var_name, value))
        self.nodes.append(node)
        return node_id
    
    def add_getvar(self, var_name: Optional[NodeId] = None) -> NodeId:
        """Add a GetVar node"""
        node_id = NodeId(self.next_id)
        self.next_id += 1
        node = IRNode(node_id, GetVar(var_name))
        self.nodes.append(node)
        return node_id
    
    def add_custom(self, name: str, inputs: int, outputs: int) -> NodeId:
        """Create a custom node with given number of inputs and outputs"""
        node_id = NodeId(self.next_id)
        self.next_id += 1
        node = IRNode(
            node_id,
            Custom(name, [None] * inputs, outputs, [None] * outputs)
        )
        self.nodes.append(node)
        return node_id
    
    def find_node(self, node_id: NodeId) -> Optional[IRNode]:
        """Find a node by ID"""
        for node in self.nodes:
            if node.id == node_id:
                return node
        return None
    
    def to_dict(self):
        """Serialize to dictionary"""
        return {
            "nodes": [node.to_dict() for node in self.nodes],
            "next_id": self.next_id,
            "layout": {str(k): v for k, v in self.layout.items()}
        }
    
    @staticmethod
    def from_dict(data):
        """Deserialize from dictionary"""
        module = IRModule()
        module.nodes = [IRNode.from_dict(n) for n in data.get("nodes", [])]
        module.next_id = data.get("next_id", 1)
        module.layout = {int(k): tuple(v) for k, v in data.get("layout", {}).items()}
        return module
    
    def to_json(self, pretty: bool = True) -> str:
        """Serialize to JSON string"""
        if pretty:
            return json.dumps(self.to_dict(), indent=2)
        return json.dumps(self.to_dict())
    
    @staticmethod
    def from_json(json_str: str):
        """Deserialize from JSON string"""
        data = json.loads(json_str)
        return IRModule.from_dict(data)
    
    def save_to_file(self, path: str):
        """Save module to file"""
        with open(path, 'w', encoding='utf-8') as f:
            f.write(self.to_json())
    
    @staticmethod
    def load_from_file(path: str):
        """Load module from file"""
        with open(path, 'r', encoding='utf-8') as f:
            return IRModule.from_json(f.read())
