from OpenGL.GL import *
import math
import numpy as np
import time
from .shader_manager import create_ocean_shader_fft, create_ocean_shader_gerstner

_ocean_vbo = None
_ocean_ibo = None
_ocean_index_count = 0
_ocean_shader_fft = None
_ocean_shader_gerstner = None

# FFT State caches (Resolution -> Generator)
_fft_generators = {}

class FFTOceanWaveGenerator:
    """Optimized CPU-side FFT wave simulation."""
    def __init__(self, resolution=128, size=1000.0, wind_speed=30.0, wind_dir=(1.0, 0.0)):
        self.N = resolution
        self.L = size
        self.wind_speed = wind_speed
        self.wind_dir = np.array(wind_dir) / np.linalg.norm(wind_dir)
        
        # Grid parameters
        self.n = np.fft.fftfreq(self.N) * self.N
        self.kx = 2.0 * np.pi * self.n / self.L
        self.kz = 2.0 * np.pi * self.n[:, np.newaxis] / self.L
        self.k_mag = np.sqrt(self.kx**2 + self.kz**2)
        self.k_mag[0, 0] = 0.0001
        
        # Initial Spectrum
        self.h0 = self._init_spectrum()
        self.h0_conj = np.conj(np.roll(np.roll(self.h0[::-1, ::-1], 1, axis=0), 1, axis=1))

        # Pre-allocate buffers for massive speedup
        self.disp_data = np.zeros((self.N, self.N, 4), dtype=np.float32)

        # GL Textures
        self.tex_displacement = glGenTextures(1)
        self.tex_jacobian = glGenTextures(1)
        self._init_textures()

    def _init_spectrum(self):
        # Multi-scale spectrum for variety (Large swells + tiny ripples)
        A = 1.0 
        
        # Wind alignment dot product
        dot = (self.kx * self.wind_dir[0] + self.kz * self.wind_dir[1]) / (self.k_mag + 0.001)
        wind_factor = 0.5 + 0.5 * (dot**2)
        
        # Swell component (low freq)
        ph_swell = A / (self.k_mag**3.2 + 0.0001)
        # Ripple component (high freq) - Restored for sharpness/drama
        ph_ripple = (A * 3.0) / (self.k_mag**1.5 + 0.1)
        
        ph = (ph_swell + ph_ripple) * wind_factor
        
        # Gaussian noise
        xi_r = np.random.normal(size=(self.N, self.N))
        xi_i = np.random.normal(size=(self.N, self.N))
        return (1.0 / np.sqrt(2.0)) * (xi_r + 1j * xi_i) * np.sqrt(ph)

    def _init_textures(self):
        for tex in [self.tex_displacement, self.tex_jacobian]:
            glBindTexture(GL_TEXTURE_2D, tex)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_REPEAT)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_REPEAT)
        glBindTexture(GL_TEXTURE_2D, 0)

    def update(self, t, choppiness=1.5, intensity=1.0):
        # 1. Omega & Phase
        w = np.sqrt(9.81 * self.k_mag)
        ex = np.exp(1j * w * t)
        h = self.h0 * ex + self.h0_conj * np.conj(ex)
        
        # Synthesis scale: Recalibrated for 'Storm' headroom
        # 0.0006 gives us ~5-8m waves at intensity 2.0
        s = self.N * self.N * 0.0006 * intensity
        
        # 3. FFT Transforms (Heights & Displacements)
        dy = np.real(np.fft.ifft2(h)) * s
        dx = np.real(np.fft.ifft2(1j * (self.kx / (self.k_mag + 0.01)) * h)) * s
        dz = np.real(np.fft.ifft2(1j * (self.kz / (self.k_mag + 0.01)) * h)) * s
        
        # 5. Jacobian proxy
        dgx = np.real(np.fft.ifft2(- (self.kx**2 / (self.k_mag + 0.01)) * h)) * s
        dgz = np.real(np.fft.ifft2(- (self.kz**2 / (self.k_mag + 0.01)) * h)) * s
        jacobian = 1.0 + choppiness * (dgx + dgz)
        
        # Dashboard Height Range
        if not hasattr(self, '_last_print') or time.time() - self._last_print > 1.0:
            print(f"[FFT OPTIMIZED] Res: {self.N} Height: {np.min(dy):.2f}m to {np.max(dy):.2f}m (Scale: {s:.1f})")
            self._last_print = time.time()

        # 6. Optimized Upload
        self.disp_data[..., 0] = dx
        self.disp_data[..., 1] = dy
        self.disp_data[..., 2] = dz
        self.disp_data[..., 3] = 1.0
        
        glBindTexture(GL_TEXTURE_2D, self.tex_displacement)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA32F, self.N, self.N, 0, GL_RGBA, GL_FLOAT, self.disp_data)
        
        jac_data = jacobian.astype(np.float32)
        glBindTexture(GL_TEXTURE_2D, self.tex_jacobian)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_R32F, self.N, self.N, 0, GL_RED, GL_FLOAT, jac_data)
        glBindTexture(GL_TEXTURE_2D, 0)

def init_ocean_gpu():
    global _ocean_vbo, _ocean_ibo, _ocean_index_count, _ocean_shader_fft, _ocean_shader_gerstner
    
    # 1. Initialize Geometry
    if _ocean_vbo is None:
        try:
            _init_geometry()
        except Exception as e:
            print(f"[OCEAN GEOM ERROR] {e}")

    # 2. Initialize Shaders
    if _ocean_shader_fft is None or not _ocean_shader_fft.program:
        try:
            _ocean_shader_fft = create_ocean_shader_fft()
        except Exception as e:
            print(f"[OCEAN FFT SHADER ERROR] {e}")

    if _ocean_shader_gerstner is None or not _ocean_shader_gerstner.program:
        try:
            _ocean_shader_gerstner = create_ocean_shader_gerstner()
        except Exception as e:
            print(f"[OCEAN GERSTNER SHADER ERROR] {e}")

def _init_geometry():
    global _ocean_vbo, _ocean_ibo, _ocean_index_count
    res = 256
    size = 2.0
    x = np.linspace(-size/2, size/2, res)
    z = np.linspace(-size/2, size/2, res)
    X, Z = np.meshgrid(x, z)
    
    # Vertices (X, 0, Z)
    vertices = np.stack([X, np.zeros_like(X), Z], axis=-1).astype(np.float32).flatten()
    _ocean_vbo_count = len(vertices) // 3
    
    # Generate Indices for GL_TRIANGLES
    indices = []
    for r in range(res - 1):
        for c in range(res - 1):
            i1 = r * res + c
            i2 = r * res + (c + 1)
            i3 = (r + 1) * res + c
            i4 = (r + 1) * res + (c + 1)
            # Two triangles per grid cell (CCW winding)
            indices.extend([i1, i3, i2])
            indices.extend([i2, i3, i4])
    
    indices = np.array(indices, dtype=np.uint32)
    _ocean_index_count = len(indices)
    
    # Generate VBO
    _ocean_vbo = glGenBuffers(1)
    glBindBuffer(GL_ARRAY_BUFFER, _ocean_vbo)
    glBufferData(GL_ARRAY_BUFFER, vertices.nbytes, vertices, GL_STATIC_DRAW)
    
    # Generate IBO
    _ocean_ibo = glGenBuffers(1)
    glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, _ocean_ibo)
    glBufferData(GL_ELEMENT_ARRAY_BUFFER, indices.nbytes, indices, GL_STATIC_DRAW)
    
    glBindBuffer(GL_ARRAY_BUFFER, 0)
    glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, 0)

def render_ocean_gpu(camera_pos, obj, sim_time=0.0):
    """Render the ocean surface following the camera, choosing between FFT or Gerstner."""
    global _ocean_vbo, _ocean_shader_fft, _ocean_shader_gerstner, _fft_generators
    use_fft = getattr(obj, 'ocean_use_fft', True)
    
    # Parameters
    level = getattr(obj, 'landscape_ocean_level', 0.0)
    color = obj.material.get('base_color', [0.0, 0.2, 0.5, 1.0])
    opacity = obj.material.get('opacity', 0.8)
    foam = getattr(obj, 'ocean_foam_amount', 0.5)
    chunk_size = 2000.0 
    
    # Wiring Sliders
    speed = getattr(obj, 'ocean_wave_speed', 1.0)
    scale = getattr(obj, 'ocean_wave_scale', 1.0)
    adjusted_time = sim_time * speed

    # 1. Simulator Update (Only if FFT enabled)
    gen = None
    if use_fft:
        res = getattr(obj, 'ocean_fft_resolution', 128)
        if res not in _fft_generators:
            _fft_generators[res] = FFTOceanWaveGenerator(resolution=res)
        gen = _fft_generators[res]
        choppiness = getattr(obj, 'ocean_wave_choppiness', 1.5)
        intensity = getattr(obj, 'ocean_wave_intensity', 1.0)
        gen.update(adjusted_time, choppiness=choppiness, intensity=intensity)
    
    # Ensure resources ready
    if _ocean_vbo is None or _ocean_shader_fft is None: 
        init_ocean_gpu()
    
    # Select Shader
    shader = _ocean_shader_fft if use_fft else _ocean_shader_gerstner
    if not shader or not shader.program: return

    # Transform & Snapping
    grid_snap = 10.0
    follow_x = (camera_pos[0] // grid_snap) * grid_snap
    follow_z = (camera_pos[2] // grid_snap) * grid_snap

    # Rendering Setup
    glEnable(GL_DEPTH_TEST)
    glDepthFunc(GL_LESS)
    glDepthMask(GL_TRUE)
    
    # Back-face Culling is critical for ocean surfaces
    glEnable(GL_CULL_FACE)
    glCullFace(GL_BACK)

    # Conditional Blending
    if opacity < 0.99:
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glDepthMask(GL_FALSE) # Disable depth write for transparency sorting
    else:
        glDisable(GL_BLEND)
    
    try:
        shader.use()
        
        if use_fft and gen:
            glActiveTexture(GL_TEXTURE0)
            glBindTexture(GL_TEXTURE_2D, gen.tex_displacement)
            shader.set_uniform_i("u_displacement_map", 0)
            
            glActiveTexture(GL_TEXTURE1)
            glBindTexture(GL_TEXTURE_2D, gen.tex_jacobian)
            shader.set_uniform_i("u_jacobian_map", 1)
            
            # Combine Choppiness and Steepness for maximum control in FFT mode
            total_choppiness = getattr(obj, 'ocean_wave_choppiness', 1.5) + getattr(obj, 'ocean_wave_steepness', 0.0)
            shader.set_uniform_f("u_choppiness", total_choppiness)
            shader.set_uniform_f("u_wave_scale", scale)
        else:
            # Gerstner Uniforms
            shader.set_uniform_f("wave_speed", speed)
            shader.set_uniform_f("wave_scale", scale)
            shader.set_uniform_f("wave_steepness", getattr(obj, 'ocean_wave_steepness', 0.5))
        
        # Shared Uniforms
        shader.set_uniform_f("time", adjusted_time)
        shader.set_uniform_f("foam_amount", foam)
        shader.set_uniform_f("ocean_opacity", opacity)
        shader.set_uniform_v4("ocean_color", *color)
        shader.set_uniform_v3("grid_origin", follow_x, level, follow_z)
        shader.set_uniform_v3("cam_pos", *camera_pos)
        shader.set_uniform_f("grid_chunk_size", chunk_size)
        
    except Exception as e:
        print(f"[OCEAN SHADER ERROR] {e}")
        glUseProgram(0)
    
    glEnable(GL_DEPTH_TEST)
    if opacity < 0.99: glDepthMask(GL_FALSE)
    else: glDepthMask(GL_TRUE)
    
    glPushMatrix()
    obj_pos = getattr(obj, 'position', [0,0,0])
    glTranslatef(follow_x - obj_pos[0], level - obj_pos[1] + 0.15, follow_z - obj_pos[2])
    glScalef(chunk_size, 1.0, chunk_size)
    
    # Render VBO
    glEnableClientState(GL_VERTEX_ARRAY)
    glBindBuffer(GL_ARRAY_BUFFER, _ocean_vbo)
    glVertexPointer(3, GL_FLOAT, 0, None)
    glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, _ocean_ibo)
    glDrawElements(GL_TRIANGLES, _ocean_index_count, GL_UNSIGNED_INT, None)
    
    glBindBuffer(GL_ARRAY_BUFFER, 0)
    glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, 0)
    glDisableClientState(GL_VERTEX_ARRAY)
    glPopMatrix()
    
    shader.stop()
    glDepthMask(GL_TRUE)
    glDisable(GL_BLEND)
    glActiveTexture(GL_TEXTURE0)
