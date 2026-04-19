"""
shader_manager.py

A robust utility for managing GLSL shaders and GPU programs.
This reads custom .shader files (which contain both vertex and fragment programs)
from disk, compiles them, and caches them.
"""
from OpenGL.GL import *
from OpenGL.GL.shaders import compileProgram, compileShader
import numpy as np
import os
from pathlib import Path
import re

class ShaderProgram:
    def __init__(self, vertex_source, fragment_source):
        self.program = None
        try:
            self.program = compileProgram(
                compileShader(vertex_source, GL_VERTEX_SHADER),
                compileShader(fragment_source, GL_FRAGMENT_SHADER)
            )
            print("[SHADER] Successfully compiled and linked shader program.")
        except Exception as e:
            print(f"[SHADER ERROR] Shader compilation failed:\n{e}")

    def use(self):
        if self.program:
            glUseProgram(self.program)

    def stop(self):
        glUseProgram(0)

    def set_uniform_i(self, name, value):
        loc = glGetUniformLocation(self.program, name)
        if loc != -1:
            glUniform1i(loc, int(value))

    def set_uniform_f(self, name, value):
        loc = glGetUniformLocation(self.program, name)
        if loc != -1:
            glUniform1f(loc, value)

    def set_uniform_v3(self, name, x, y, z):
        loc = glGetUniformLocation(self.program, name)
        if loc != -1:
            glUniform3f(loc, x, y, z)

    def set_uniform_v4(self, name, x, y, z, w):
        loc = glGetUniformLocation(self.program, name)
        if loc != -1:
            glUniform4f(loc, x, y, z, w)

    def set_uniform_f_array(self, name, values):
        for i, v in enumerate(values):
            loc = glGetUniformLocation(self.program, f"{name}[{i}]")
            if loc != -1:
                glUniform1f(loc, float(v))

    def set_uniform_matrix4(self, name, mat):
        loc = glGetUniformLocation(self.program, name)
        if loc != -1:
            glUniformMatrix4fv(loc, 1, GL_FALSE, mat)

# --- Global Registries ---
_SHADER_CACHE = {}
_TEXTURE_CACHE = {}

def get_texture(path):
    """Load and cache a GL texture from disk."""
    if not path: return 0
    if path in _TEXTURE_CACHE: return _TEXTURE_CACHE[path]
    
    try:
        from PyQt6.QtGui import QImage
        img = QImage(path)
        if img.isNull(): return 0
        
        img = img.convertToFormat(QImage.Format.Format_RGBA8888).mirrored()
        w, h = img.width(), img.height()
        ptr = img.bits()
        ptr.setsize(img.sizeInBytes())
        
        tex = glGenTextures(1)
        glBindTexture(GL_TEXTURE_2D, tex)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, w, h, 0, GL_RGBA, GL_UNSIGNED_BYTE, ptr.asstring())
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR_MIPMAP_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glGenerateMipmap(GL_TEXTURE_2D)
        
        _TEXTURE_CACHE[path] = tex
        return tex
    except Exception as e:
        print(f"[SHADER MANAGER] Texture load error: {e}")
        return 0

def get_shader(name_or_path):
    """Retrieve a compiled shader from the cache or compile a new one from a .shader file."""
    if not name_or_path:
        return None

    if name_or_path in _SHADER_CACHE:
        return _SHADER_CACHE[name_or_path]
    
    # Fallback map for legacy hardcoded presets to maintain backwards compatibility
    fallback_map = {
        "Standard": "standard.shader",
        "Grass": "grass.shader",
        "grass.shader": "grass.shader",
        "Fish Swimming": "fish_swimming.shader",
        "Flag Waving": "flag_waving.shader",
        "Ocean (FFT)": "ocean_fft.shader",
        "Ocean (Gerstner)": "ocean_gerstner.shader",
        "PBR Material": "pbr_material.shader"
    }

    file_to_load = name_or_path
    
    # 1. Check fallback map
    from py_editor.core import paths as _ap
    project_root = _ap.get_project_root()
    core_shaders_dir = project_root / "shaders"

    if name_or_path in fallback_map:
        file_to_load = str(core_shaders_dir / fallback_map[name_or_path])
    
    # 2. If it's a relative filename, try current shaders directory
    if not os.path.isabs(file_to_load):
        # Try project-relative shaders/
        potential_path = core_shaders_dir / file_to_load
        if potential_path.exists():
            file_to_load = str(potential_path)
        else:
            # Try app-relative shaders/ (near this file)
            app_shaders_dir = Path(__file__).parent.parent.parent / "shaders"
            potential_path = app_shaders_dir / file_to_load
            if potential_path.exists():
                file_to_load = str(potential_path)

    if not os.path.exists(file_to_load):
        # 3. Last ditch effort: if it's an absolute path pointing to the root, 
        # but the file isn't there, try injecting /shaders/
        p = Path(file_to_load)
        if p.parent == project_root or p.parent == Path(__file__).parent.parent.parent:
            alt_path = p.parent / "shaders" / p.name
            if alt_path.exists():
                file_to_load = str(alt_path)

    if not os.path.exists(file_to_load):
        print(f"[SHADER MANAGER] Warning: Shader file not found: {file_to_load}")
        print(f"    (Checked project shaders: {core_shaders_dir})")
        return None
        
    print(f"[SHADER MANAGER] Initializing shader from: {file_to_load}")
    try:
        with open(file_to_load, 'r', encoding='utf-8') as f:
            content = f.read()

        parts = content.split("// -- FRAGMENT --")
        if len(parts) == 2:
            v_src = parts[0].replace("// -- VERTEX --", "").strip()
            f_src = parts[1].strip()
            prog = ShaderProgram(v_src, f_src)
            _SHADER_CACHE[name_or_path] = prog
            return prog
        else:
            print(f"[SHADER ERROR] Invalid format in {file_to_load}. Missing // -- FRAGMENT --")
            return None
    except Exception as e:
        print(f"[SHADER ERROR] Failed to load {file_to_load}: {e}")
        return None

def get_shader_list():
    """Returns a list of available shader names (presets + files in root shaders/)."""
    presets = ["Standard", "Fish Swimming", "Flag Waving", "Ocean (FFT)", "Ocean (Gerstner)", "PBR Material"]
    
    # Also add any .shader files in the root shaders/ directory
    try:
        core_shaders_dir = Path(__file__).parent.parent.parent / "shaders"
        if core_shaders_dir.exists():
            for f in core_shaders_dir.glob("*.shader"):
                if f.stem not in presets:
                    presets.append(f.name)
    except:
        pass
        
    return presets

def get_shader_params(name_or_path):
    """Parses a .shader file and returns a list of user-tweakable uniforms.
    
    Returns a list of dicts: {'name': str, 'type': str, 'default': float/list}
    """
    # 1. Resolve Path (Duplicate logic from get_shader but without cache)
    fallback_map = {
        "Standard": "standard.shader", "Grass": "grass.shader", "grass.shader": "grass.shader",
        "Fish Swimming": "fish_swimming.shader", "Flag Waving": "flag_waving.shader",
        "Ocean (FFT)": "ocean_fft.shader", "Ocean (Gerstner)": "ocean_gerstner.shader",
        "PBR Material": "pbr_material.shader"
    }
    file_to_load = name_or_path
    from py_editor.core import paths as _ap
    project_root = _ap.get_project_root()
    core_shaders_dir = project_root / "shaders"

    if name_or_path in fallback_map:
        file_to_load = str(core_shaders_dir / fallback_map[name_or_path])
    
    if not os.path.isabs(file_to_load):
        potential_path = core_shaders_dir / file_to_load
        if potential_path.exists():
            file_to_load = str(potential_path)
        else:
            app_shaders_dir = Path(__file__).parent.parent.parent / "shaders"
            potential_path = app_shaders_dir / file_to_load
            if potential_path.exists():
                file_to_load = str(potential_path)

    if not os.path.exists(file_to_load):
        return []

    params = []
    try:
        with open(file_to_load, 'r', encoding='utf-8') as f:
            content = f.read()

        # Regular expression for uniforms: uniform type name; // default: val
        # Matches: uniform float intensity; // default: 0.5
        # Also handles simple vec3/vec4
        pattern = r"uniform\s+(float|vec3|vec4)\s+([a-zA-Z0-9_]+)\s*;\s*(?://\s*default:\s*([0-9.,\s-]+))?"
        matches = re.finditer(pattern, content)
        
        # Avoid built-ins
        exclude = {'time', 'u_time', 'sunDir', 'sunColor', 'ambientColor', 'base_color', 'u_base_color', 'cam_pos'}
        
        for m in matches:
            u_type, u_name, u_def = m.groups()
            if u_name in exclude: continue
            
            d_val = 0.0
            if u_def:
                try:
                    if u_type == 'float': d_val = float(u_def.strip())
                    else: d_val = [float(x.strip()) for x in u_def.split(',')]
                except: pass
            else:
                if u_type == 'vec3': d_val = [1.0, 1.0, 1.0]
                elif u_type == 'vec4': d_val = [1.0, 1.0, 1.0, 1.0]
                
            params.append({
                'name': u_name,
                'type': u_type,
                'default': d_val
            })
    except Exception as e:
        print(f"[SHADER MANAGER] Param parse error: {e}")
        
    return params
