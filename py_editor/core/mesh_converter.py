import struct
import numpy as np
from pathlib import Path
import shutil
import tempfile
import subprocess
import os
import textwrap

class MeshConverter:
    """Utility to convert 3D model formats (OBJ) into a custom binary .mesh format."""
    
    @staticmethod
    def obj_to_mesh(obj_path: str, output_path: str):
        """Parse OBJ and export to NCMS binary format."""
        vertices = []
        normals = []
        uvs = []
        
        # Face data as (v_idx, vt_idx, vn_idx)
        faces = []
        
        with open(obj_path, 'r') as f:
            for line in f:
                parts = line.split()
                if not parts: continue
                
                if parts[0] == 'v':
                    vertices.append([float(parts[1]), float(parts[2]), float(parts[3])])
                elif parts[0] == 'vn':
                    normals.append([float(parts[1]), float(parts[2]), float(parts[3])])
                elif parts[0] == 'vt':
                    uvs.append([float(parts[1]), float(parts[2])])
                elif parts[0] == 'f':
                    face = []
                    for vert_str in parts[1:]:
                        v_parts = vert_str.split('/')
                        # indices in OBJ are 1-based
                        v_idx = int(v_parts[0]) - 1
                        vt_idx = int(v_parts[1]) - 1 if len(v_parts) > 1 and v_parts[1] else -1
                        vn_idx = int(v_parts[2]) - 1 if len(v_parts) > 2 and v_parts[2] else -1
                        face.append((v_idx, vt_idx, vn_idx))
                    
                    # Simple triangulation for N-gons
                    for i in range(1, len(face) - 1):
                        faces.append([face[0], face[i], face[i+1]])

        # Process uniqueness to build interleaved vertex buffer
        unique_verts = {}
        final_vertices = []
        final_indices = []
        
        for face in faces:
            for vert_tuple in face:
                if vert_tuple not in unique_verts:
                    v_idx, vt_idx, vn_idx = vert_tuple
                    pos = vertices[v_idx]
                    norm = normals[vn_idx] if vn_idx != -1 else [0, 1, 0]
                    uv = uvs[vt_idx] if vt_idx != -1 else [0, 0]
                    
                    # Interleaved: px, py, pz, nx, ny, nz, u, v
                    new_idx = len(final_vertices) // 8
                    unique_verts[vert_tuple] = new_idx
                    final_vertices.extend([pos[0], pos[1], pos[2], norm[0], norm[1], norm[2], uv[0], uv[1]])
                
                final_indices.append(unique_verts[vert_tuple])

        # Write Binary
        with open(output_path, 'wb') as f:
            # Header: Magic(4B), Version(4B), VCount(4B), ICount(4B)
            f.write(b'NCMS')
            f.write(struct.pack('I', 1)) 
            f.write(struct.pack('I', len(final_vertices) // 8))
            f.write(struct.pack('I', len(final_indices)))
            
            # Data
            f.write(struct.pack(f'{len(final_vertices)}f', *final_vertices))
            f.write(struct.pack(f'{len(final_indices)}I', *final_indices))
            
        print(f"[CONVERTER] Exported {output_path} ({len(final_vertices)//8} verts, {len(final_indices)} indices)")

    @staticmethod
    def load_material_sidecar(mesh_path: str) -> dict:
        """Return the first PBR map dict from a .material sidecar, or {} if none.

        The sidecar is written next to the .mesh file with the same stem and
        a .material extension.  The returned dict maps slot names
        (albedo, normal, metallic, roughness, ao, displacement) to file paths.
        """
        import json as _json
        mat_path = Path(mesh_path).with_suffix('.material')
        if not mat_path.exists():
            return {}
        try:
            data = _json.loads(mat_path.read_text(encoding='utf-8'))
            mats = data.get('materials', [])
            if mats:
                return mats[0].get('pbr_maps', {})
        except Exception:
            pass
        return {}

    @staticmethod
    def load_mesh(mesh_path: str):
        """Load binary NCMS mesh into numpy arrays."""
        with open(mesh_path, 'rb') as f:
            magic = f.read(4)
            if magic != b'NCMS':
                raise ValueError("Not a valid NodeCanvas Mesh file.")
            
            version = struct.unpack('I', f.read(4))[0]
            v_count = struct.unpack('I', f.read(4))[0]
            i_count = struct.unpack('I', f.read(4))[0]
            
            v_data = np.frombuffer(f.read(v_count * 8 * 4), dtype=np.float32)
            i_data = np.frombuffer(f.read(i_count * 4), dtype=np.uint32)
            
            return v_data, i_data

    @staticmethod
    def fbx_to_mesh(fbx_path: str, output_path: str, blender_exe: str = None):
        """Pure-Python FBX -> NCMS `.mesh` converter (ASCII-FBX only).

        This parser supports ASCII FBX files and extracts vertex positions,
        polygon indices and basic material/texture references. Binary FBX
        files are not supported by this pure-Python implementation; please
        export ASCII FBX or use OBJ if you encounter a binary FBX.
        """
        import re
        import json

        fbx_path = str(fbx_path)
        output_path = str(output_path)
        fbx_dir = os.path.dirname(fbx_path)

        # Read file as text (try utf-8, then latin-1)
        raw = open(fbx_path, 'rb').read()
        try:
            text = raw.decode('utf-8')
        except Exception:
            try:
                text = raw.decode('latin-1')
            except Exception:
                raise RuntimeError('FBX appears to be binary or not decodable; pure-Python converter supports ASCII FBX only. Export ASCII or use OBJ.')

        # Helper to extract a {...} block following a label occurrence
        def _extract_block_after(label):
            idx = text.find(label)
            if idx == -1:
                return None
            brace = text.find('{', idx)
            if brace == -1:
                return None
            depth = 1
            i = brace + 1
            start = i
            while i < len(text) and depth > 0:
                c = text[i]
                if c == '{': depth += 1
                elif c == '}': depth -= 1
                i += 1
            return text[start:i-1]

        # Parse vertex positions
        verts_block = _extract_block_after('Vertices')
        if not verts_block:
            raise RuntimeError('ASCII FBX parser: no "Vertices" block found. Ensure FBX is ASCII.')

        num_regex = re.compile(r'[-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?')
        vert_nums = num_regex.findall(verts_block)
        verts_f = [float(x) for x in vert_nums]
        if len(verts_f) % 3 != 0:
            raise RuntimeError('Parsed vertex count is not a multiple of 3')
        verts = [verts_f[i:i+3] for i in range(0, len(verts_f), 3)]

        # Parse polygon vertex index list
        pvi_block = _extract_block_after('PolygonVertexIndex')
        if not pvi_block:
            raise RuntimeError('ASCII FBX parser: no "PolygonVertexIndex" block found.')
        pvi_ints = [int(x) for x in re.findall(r'-?\d+', pvi_block)]

        # Build polygons (negative value marks polygon end: index = -v-1)
        polygons = []
        cur = []
        for v in pvi_ints:
            if v >= 0:
                cur.append(v)
            else:
                cur.append(-v - 1)
                if len(cur) >= 3:
                    polygons.append(cur)
                cur = []

        # Triangulate polygons (fan triangulation)
        tri_indices = []
        for poly in polygons:
            for i in range(1, len(poly) - 1):
                tri_indices.extend([poly[0], poly[i], poly[i+1]])

        if not tri_indices:
            raise RuntimeError('No triangles produced from FBX polygon data.')

        # Compute per-vertex normals by accumulating face normals
        import math as _math
        import numpy as _np

        v_count = len(verts)
        pos_arr = _np.array(verts, dtype=_np.float32)
        normals_acc = _np.zeros((v_count, 3), dtype=_np.float32)

        for i in range(0, len(tri_indices), 3):
            a, b, c = tri_indices[i], tri_indices[i+1], tri_indices[i+2]
            pa = pos_arr[a]; pb = pos_arr[b]; pc = pos_arr[c]
            e1 = pb - pa
            e2 = pc - pa
            n = _np.cross(e1, e2)
            norm = _np.linalg.norm(n)
            if norm > 1e-9:
                n = n / norm
                normals_acc[a] += n
                normals_acc[b] += n
                normals_acc[c] += n

        # Normalize accumulated normals
        for i in range(v_count):
            ln = _np.linalg.norm(normals_acc[i])
            if ln > 1e-6:
                normals_acc[i] = normals_acc[i] / ln
            else:
                normals_acc[i] = _np.array([0.0, 1.0, 0.0], dtype=_np.float32)

        # Build compact vertex list only for used vertex indices
        used = sorted(set(tri_indices))
        idx_map = {orig: idx for idx, orig in enumerate(used)}
        final_vertices = []
        for orig in used:
            p = pos_arr[orig].tolist()
            n = normals_acc[orig].tolist()
            # Interleaved: px,py,pz,nx,ny,nz,u,v  (u,v zero for now)
            final_vertices.extend([p[0], p[1], p[2], n[0], n[1], n[2], 0.0, 0.0])

        final_indices = [_ for x in tri_indices for _ in ([idx_map[x]])]

        # Write NCMS binary
        with open(output_path, 'wb') as f:
            f.write(b'NCMS')
            f.write(struct.pack('I', 1))
            f.write(struct.pack('I', len(final_vertices) // 8))
            f.write(struct.pack('I', len(final_indices)))
            f.write(struct.pack(f'{len(final_vertices)}f', *final_vertices))
            f.write(struct.pack(f'{len(final_indices)}I', *final_indices))

        print(f"[CONVERTER] Exported {output_path} ({len(final_vertices)//8} verts, {len(final_indices)} indices) [ASCII-FBX]")

        # Extract simple material / texture info and write a .mat sidecar JSON
        materials = {}
        textures = {}
        # Material definitions: Material: <id>, "Material::Name"
        for m in re.finditer(r'Material:\s*(-?\d+),\s*"([^"]+)"', text):
            mid, mname = m.groups()
            materials[int(mid)] = mname.split('::')[-1]

        # Texture blocks: Texture: <id>, "Name" { ... FileName: "..." ... }
        for t in re.finditer(r'Texture:\s*(-?\d+),\s*"([^"]+)"', text):
            tid = int(t.group(1))
            # extract block after this occurrence
            block = _extract_block_after(t.group(0))
            if not block:
                # fallback: try find FileName after position
                block_search_start = t.end()
                block = text[block_search_start: block_search_start + 512]
            fn_match = re.search(r'FileName:\s*"([^"]+)"', block)
            if fn_match:
                textures[tid] = os.path.normpath(os.path.join(fbx_dir, fn_match.group(1)))

        # Connections: C: "OP" or "OO" , src, dst
        mat_map = {}
        for c in re.finditer(r'C:\s*"([^"]+)",\s*(-?\d+),\s*(-?\d+)', text):
            ctype, a, b = c.groups()
            a = int(a); b = int(b)
            # texture -> material (OP) or texture -> material (OO)
            if a in textures and b in materials:
                mat_map.setdefault(b, []).append(textures[a])
            # material -> model (OO) etc ignored for now

        # Build materials list
        mat_list = []
        if materials:
            for mid, name in materials.items():
                mat_list.append({
                    'name': name,
                    'textures': mat_map.get(mid, [])
                })
        elif textures:
            # No material nodes, but textures exist: create a default material
            mat_list.append({'name': 'Default', 'textures': list(textures.values())})

        if mat_list:
            # Write .material sidecar (NodeCanvas native material format, JSON)
            mat_path = str(Path(output_path).with_suffix('.material'))
            try:
                # Classify textures by Megascans naming convention so the engine
                # can auto-populate PBR slots when the mesh is first loaded.
                _suffix_map = {
                    'albedo':      ['albedo', 'basecolor', 'diffuse', 'color', 'col'],
                    'normal':      ['normal', 'nrm', 'norm'],
                    'metallic':    ['metallic', 'metalness', 'metal'],
                    'roughness':   ['roughness', 'rough', 'gloss'],
                    'ao':          ['ao', 'ambientocclusion', 'occlusion'],
                    'displacement':['displacement', 'height', 'disp', 'bump'],
                }
                for mat_entry in mat_list:
                    pbr = {}
                    for tex_path in mat_entry.get('textures', []):
                        stem = Path(tex_path).stem.lower()
                        for slot, keywords in _suffix_map.items():
                            if any(kw in stem for kw in keywords):
                                pbr.setdefault(slot, tex_path)
                                break
                    mat_entry['pbr_maps'] = pbr

                with open(mat_path, 'w', encoding='utf-8') as mf:
                    json.dump({'materials': mat_list}, mf, indent=2)
                print(f"[CONVERTER] Wrote material sidecar: {mat_path}")
            except Exception:
                pass
