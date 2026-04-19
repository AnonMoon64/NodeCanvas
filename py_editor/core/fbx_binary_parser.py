import struct
import zlib
import os

class FBXNode:
    def __init__(self, name):
        self.name = name
        self.properties = []
        self.children = []

    def get_child(self, name):
        for c in self.children:
            if c.name == name: return c
        return None

    def find_recursive(self, name):
        """Depth-first search for a node by name."""
        if self.name == name: return self
        for c in self.children:
            res = c.find_recursive(name)
            if res: return res
        return None

class FBXBinaryReader:
    """Minimalistic Binary FBX parser for extracting Mesh geometry."""
    
    @staticmethod
    def read_file(filepath):
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"FBX file not found: {filepath}")
            
        with open(filepath, 'rb') as f:
            header = f.read(27)
            if not header.startswith(b'Kaydara FBX Binary'):
                raise ValueError("Not a binary FBX file")
            
            version = struct.unpack('I', header[23:27])[0]
            nodes = []
            while True:
                node = FBXBinaryReader._read_node(f, version)
                if node is None: break
                nodes.append(node)
            return nodes

    @staticmethod
    def _read_node(f, version):
        if version >= 7500:
            bytes_raw = f.read(24)
            if not bytes_raw or len(bytes_raw) < 24: return None
            end_offset, num_props, props_len = struct.unpack('QQQ', bytes_raw)
        else:
            bytes_raw = f.read(12)
            if not bytes_raw or len(bytes_raw) < 12: return None
            end_offset, num_props, props_len = struct.unpack('III', bytes_raw)
        
        name_len = struct.unpack('B', f.read(1))[0]
        if end_offset == 0: return None
            
        name = f.read(name_len).decode('ascii', errors='ignore')
        node = FBXNode(name)
        
        # Read properties
        for _ in range(num_props):
            node.properties.append(FBXBinaryReader._read_property(f))
        
        # Read nested nodes
        while f.tell() < end_offset:
            child = FBXBinaryReader._read_node(f, version)
            if child:
                node.children.append(child)
            else:
                break # Null node sentinel
                
        f.seek(end_offset)
        return node

    @staticmethod
    def _read_property(f):
        ptype = f.read(1).decode('ascii', errors='ignore')
        if ptype == 'I': return struct.unpack('<i', f.read(4))[0]
        if ptype == 'D': return struct.unpack('<d', f.read(8))[0]
        if ptype == 'L': return struct.unpack('<q', f.read(8))[0]
        if ptype == 'F': return struct.unpack('<f', f.read(4))[0]
        if ptype == 'S':
            length = struct.unpack('<I', f.read(4))[0]
            return f.read(length).decode('utf-8', errors='ignore')
        if ptype == 'R':
            length = struct.unpack('<I', f.read(4))[0]
            return f.read(length)
        
        # Array types (i, d, f, l, b, c)
        if ptype.lower() in 'idflbc':
            length = struct.unpack('<I', f.read(4))[0]
            encoding = struct.unpack('<I', f.read(4))[0] # 0=raw, 1=zlib
            comp_len = struct.unpack('<I', f.read(4))[0]
            
            data = f.read(comp_len)
            if encoding == 1:
                data = zlib.decompress(data)
                
            fmt_map = {'i': 'i', 'd': 'd', 'f': 'f', 'l': 'q', 'b': '?', 'c': 'b'}
            fmt = fmt_map.get(ptype.lower(), 'f')
            expected_size = length * struct.calcsize(fmt)
            if len(data) != expected_size:
                # Adjust length for malformed or version-specific property arrays
                length = len(data) // struct.calcsize(fmt)

            return list(struct.unpack(f'<{length}{fmt}', data[:length * struct.calcsize(fmt)]))
        
        return None

    @staticmethod
    def get_mesh_data(nodes):
        """Extract vertices and indices from parsed nodes."""
        # Find 'Objects' -> 'Geometry' -> 'Vertices' and 'PolygonVertexIndex'
        objects = None
        for n in nodes:
            if n.name == 'Objects': 
                objects = n
                break
        if not objects: return None, None, None
        
        meshes = []
        for child in objects.children:
            if child.name == 'Geometry':
                v_node = child.get_child('Vertices')
                i_node = child.get_child('PolygonVertexIndex')
                if v_node and i_node:
                    verts = v_node.properties[0] if v_node.properties else []
                    indices = i_node.properties[0] if i_node.properties else []
                    
                    # Extract normals if available
                    normals = []
                    n_node = child.find_recursive('Normals')
                    if n_node and n_node.properties:
                        normals = n_node.properties[0]
                        
                    meshes.append({
                        'vertices': verts,
                        'indices': indices,
                        'normals': normals
                    })
        
        return meshes
