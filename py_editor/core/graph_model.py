"""
GraphModel - Separation of graph data and logic from UI rendering.

This module provides a clean data model for the node graph, independent of
the PyQt6 graphics rendering. The GraphModel owns nodes, connections, and
provides serialization/deserialization.
"""

from typing import Dict, List, Any, Optional, Tuple, Callable
from dataclasses import dataclass, field
import json


@dataclass
class PinDefinition:
    """Definition of an input or output pin"""
    name: str
    type: str = "any"
    default_value: Any = None


@dataclass
class NodeData:
    """Data for a single node in the graph"""
    id: int
    template: str
    pos: Tuple[float, float] = (0.0, 0.0)
    inputs: Dict[str, PinDefinition] = field(default_factory=dict)
    outputs: Dict[str, PinDefinition] = field(default_factory=dict)
    values: Dict[str, Any] = field(default_factory=dict)  # Pin values for unconnected inputs
    composite_graph: Optional[Dict[str, Any]] = None  # For composite nodes
    
    def to_dict(self) -> Dict[str, Any]:
        """Export node to dictionary format"""
        data = {
            "id": self.id,
            "template": self.template,
            "pos": list(self.pos),
        }
        if self.values:
            data["values"] = dict(self.values)
        if self.composite_graph:
            data["composite_graph"] = self.composite_graph
        return data
    
    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'NodeData':
        """Create NodeData from dictionary"""
        pos_list = data.get("pos", [0, 0])
        return NodeData(
            id=data["id"],
            template=data["template"],
            pos=(pos_list[0], pos_list[1]),
            values=data.get("values", {}),
            composite_graph=data.get("composite_graph")
        )


@dataclass
class ConnectionData:
    """Data for a connection between two pins"""
    from_node: int
    from_pin: str
    to_node: int
    to_pin: str
    
    def to_dict(self) -> Dict[str, Any]:
        """Export connection to dictionary format"""
        return {
            "from": self.from_node,
            "from_pin": self.from_pin,
            "to": self.to_node,
            "to_pin": self.to_pin,
        }
    
    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'ConnectionData':
        """Create ConnectionData from dictionary"""
        return ConnectionData(
            from_node=data["from"],
            from_pin=data["from_pin"],
            to_node=data["to"],
            to_pin=data["to_pin"],
        )


class GraphModel:
    """
    Core graph data model.
    
    This class maintains the logical structure of the node graph without
    any UI dependencies. It handles:
    - Node creation, deletion, and lookup
    - Connection management
    - Graph serialization/deserialization
    - Validation of connections
    """
    
    def __init__(self):
        self.nodes: Dict[int, NodeData] = {}
        self.connections: List[ConnectionData] = []
        self._next_id: int = 1
        self._change_callbacks: List[Callable] = []
    
    def add_change_callback(self, callback: Callable):
        """Register a callback to be called when the graph changes"""
        self._change_callbacks.append(callback)
    
    def _notify_change(self):
        """Notify all registered callbacks that the graph has changed"""
        for callback in self._change_callbacks:
            try:
                callback()
            except Exception as e:
                print(f"Error in graph change callback: {e}")
    
    def generate_id(self) -> int:
        """Generate a new unique node ID"""
        new_id = self._next_id
        self._next_id += 1
        return new_id
    
    def add_node(self, template: str, pos: Tuple[float, float] = (0, 0)) -> NodeData:
        """Add a new node to the graph"""
        node = NodeData(
            id=self.generate_id(),
            template=template,
            pos=pos
        )
        self.nodes[node.id] = node
        self._notify_change()
        return node
    
    def remove_node(self, node_id: int):
        """Remove a node and all its connections"""
        if node_id not in self.nodes:
            return
        
        # Remove all connections involving this node
        self.connections = [
            conn for conn in self.connections
            if conn.from_node != node_id and conn.to_node != node_id
        ]
        
        del self.nodes[node_id]
        self._notify_change()
    
    def update_node_position(self, node_id: int, pos: Tuple[float, float]):
        """Update a node's position"""
        if node_id in self.nodes:
            self.nodes[node_id].pos = pos
            # Don't notify change for position updates to avoid excessive callbacks
    
    def update_node_value(self, node_id: int, pin_name: str, value: Any):
        """Update a pin's value for a node"""
        if node_id in self.nodes:
            self.nodes[node_id].values[pin_name] = value
            self._notify_change()
    
    def add_connection(self, from_node: int, from_pin: str, to_node: int, to_pin: str) -> bool:
        """
        Add a connection between two pins.
        Returns True if successful, False if invalid.
        """
        # Validate nodes exist
        if from_node not in self.nodes or to_node not in self.nodes:
            return False
        
        # Check for duplicate connection
        for conn in self.connections:
            if (conn.from_node == from_node and conn.from_pin == from_pin and
                conn.to_node == to_node and conn.to_pin == to_pin):
                return False
        
        # Add the connection
        connection = ConnectionData(from_node, from_pin, to_node, to_pin)
        self.connections.append(connection)
        self._notify_change()
        return True
    
    def remove_connection(self, from_node: int, from_pin: str, to_node: int, to_pin: str):
        """Remove a specific connection"""
        self.connections = [
            conn for conn in self.connections
            if not (conn.from_node == from_node and conn.from_pin == from_pin and
                   conn.to_node == to_node and conn.to_pin == to_pin)
        ]
        self._notify_change()
    
    def get_connections_to_node(self, node_id: int) -> List[ConnectionData]:
        """Get all connections going to a specific node"""
        return [conn for conn in self.connections if conn.to_node == node_id]
    
    def get_connections_from_node(self, node_id: int) -> List[ConnectionData]:
        """Get all connections coming from a specific node"""
        return [conn for conn in self.connections if conn.from_node == node_id]
    
    def clear(self):
        """Clear the entire graph"""
        self.nodes.clear()
        self.connections.clear()
        self._next_id = 1
        self._notify_change()
    
    def export_to_dict(self) -> Dict[str, Any]:
        """Export the entire graph to a dictionary"""
        return {
            "nodes": [node.to_dict() for node in self.nodes.values()],
            "connections": [conn.to_dict() for conn in self.connections]
        }
    
    def import_from_dict(self, data: Dict[str, Any]):
        """Import a graph from a dictionary"""
        self.clear()
        
        # Import nodes
        for node_data in data.get("nodes", []):
            node = NodeData.from_dict(node_data)
            self.nodes[node.id] = node
            # Update next_id to avoid conflicts
            if node.id >= self._next_id:
                self._next_id = node.id + 1
        
        # Import connections
        for conn_data in data.get("connections", []):
            conn = ConnectionData.from_dict(conn_data)
            self.connections.append(conn)
        
        self._notify_change()
    
    def export_to_json(self, filepath: str):
        """Export graph to a JSON file"""
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(self.export_to_dict(), f, indent=2)
    
    def import_from_json(self, filepath: str):
        """Import graph from a JSON file"""
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        self.import_from_dict(data)
