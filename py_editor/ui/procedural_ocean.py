from OpenGL.GL import *
import math
import numpy as np
import time
from .shader_manager import get_shader

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
        self.tex_velocity = glGenTextures(1)
        self._init_textures()

        # Persistent foam buffer for advection
        self.foam_buffer = np.zeros((self.N, self.N), dtype=np.float32)
        self.tex_foam_advected = glGenTextures(1)
        glBindTexture(GL_TEXTURE_2D, self.tex_foam_advected)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_REPEAT)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_REPEAT)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_R32F, self.N, self.N, 0, GL_RED, GL_FLOAT, None)
        glBindTexture(GL_TEXTURE_2D, 0)
        
        # Ripple buffer (dynamic impacts from logic)
        self.ripple_buffer = np.zeros((self.N, self.N), dtype=np.float32)
        self.ripple_queue = [] # List of (u, v, strength)
        self.tex_ripple = glGenTextures(1)
        glBindTexture(GL_TEXTURE_2D, self.tex_ripple)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_REPEAT)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_REPEAT)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_R32F, self.N, self.N, 0, GL_RED, GL_FLOAT, None)
        glBindTexture(GL_TEXTURE_2D, 0)
        
        self.last_t = time.time()

    def _init_spectrum(self):
        # Multi-scale spectrum for variety (Large swells + tiny ripples)
        A = 1.0 
        
        # Wind alignment dot product. The original 0.5 + 0.5*dot² bias was strong enough
        # that waves stayed visibly coherent along the wind axis, producing parallel ridge
        # strips from one direction. 0.75 + 0.25*dot² gives a much more isotropic field
        # while still favouring the wind direction.
        dot = (self.kx * self.wind_dir[0] + self.kz * self.wind_dir[1]) / (self.k_mag + 0.001)
        wind_factor = 0.75 + 0.25 * (dot**2)
        
        # Swell component (Significant reduction for metric coherence)
        ph_swell = (A * 0.08) / (self.k_mag**2.5 + 0.0001)
        # Ripple component (high freq)
        ph_ripple = (A * 0.4) / (self.k_mag**1.5 + 0.1)
        
        ph = (ph_swell + ph_ripple) * wind_factor
        
        # Gaussian noise
        xi_r = np.random.normal(size=(self.N, self.N))
        xi_i = np.random.normal(size=(self.N, self.N))
        return (1.0 / np.sqrt(2.0)) * (xi_r + 1j * xi_i) * np.sqrt(ph)

    def _init_textures(self):
        # Displacement
        glBindTexture(GL_TEXTURE_2D, self.tex_displacement)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_REPEAT)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_REPEAT)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA32F, self.N, self.N, 0, GL_RGBA, GL_FLOAT, None)
        
        # Jacobian
        glBindTexture(GL_TEXTURE_2D, self.tex_jacobian)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_REPEAT)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_REPEAT)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_R32F, self.N, self.N, 0, GL_RED, GL_FLOAT, None)
        
        # Velocity
        glBindTexture(GL_TEXTURE_2D, self.tex_velocity)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_REPEAT)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_REPEAT)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RG32F, self.N, self.N, 0, GL_RG, GL_FLOAT, None)
        
        glBindTexture(GL_TEXTURE_2D, 0)

    def update(self, wave_time, choppiness=1.5, intensity=1.0):
        # 1. Omega & Phase
        w = np.sqrt(9.81 * self.k_mag)
        ex = np.exp(1j * w * wave_time)
        h = self.h0 * ex + self.h0_conj * np.conj(ex)
        
        # Synthesis scale: Recalibrated for 'Storm' headroom
        # 0.0006 gives us ~5-8m waves at intensity 2.0
        s = self.N * self.N * 0.0006 * intensity
        
        # 3. FFT Transforms (Heights & Displacements)
        self.last_dy = np.real(np.fft.ifft2(h)) * s
        dy = self.last_dy
        dx = np.real(np.fft.ifft2(1j * (self.kx / (self.k_mag + 0.01)) * h)) * s
        dz = np.real(np.fft.ifft2(1j * (self.kz / (self.k_mag + 0.01)) * h)) * s
        
        # 3.5 Calculate dt for physical time step
        dt = time.time() - getattr(self, 'last_t', time.time())
        self.last_t = time.time()
        dt = max(0.001, min(dt, 0.1)) # Clamp for stability

        # 4. Velocity calculation (dh/dt)
        # Approximate using backward differences to save 2 expensive IFFTs
        if not hasattr(self, 'last_dx'):
            self.last_dx = dx
            self.last_dz = dz
            
        vx = (dx - self.last_dx) / dt
        vz = (dz - self.last_dz) / dt
        
        self.last_dx = dx
        self.last_dz = dz
        
        # 5. Jacobian proxy
        dgx = np.real(np.fft.ifft2(- (self.kx**2 / (self.k_mag + 0.01)) * h)) * s
        dgz = np.real(np.fft.ifft2(- (self.kz**2 / (self.k_mag + 0.01)) * h)) * s
        jacobian = 1.0 + choppiness * (dgx + dgz)
        
        # 6. Persistent Foam Advection (CPU-side) & Ripples
        # Dissipate existing ripples (lower decay for better visibility)
        ripple_decay = float(np.exp(-1.8 * dt))
        self.ripple_buffer *= ripple_decay
        
        # Add new impacts from queue
        while self.ripple_queue:
            u, v, strength = self.ripple_queue.pop(0)
            ix, iz = int(u * self.N) % self.N, int(v * self.N) % self.N
            r = max(1, int(self.N * 0.02))
            
            # Vectorized ripple splatting
            y_grid, x_grid = np.ogrid[-r:r+1, -r:r+1]
            mask = x_grid**2 + y_grid**2 <= r**2
            
            # Map indices with wrap-around
            iz_idx = (iz + y_grid) % self.N
            ix_idx = (ix + x_grid) % self.N
            
            dist = np.sqrt(x_grid**2 + y_grid**2)
            falloff = 1.0 - (dist / r)
            
            # Apply splat mask
            splat = np.zeros_like(mask, dtype=np.float32)
            splat[mask] = strength * falloff[mask] * 5.0
            
            self.ripple_buffer[iz_idx, ix_idx] += splat
        
        self.ripple_buffer = np.clip(self.ripple_buffer, 0.0, 1.0)

        # Simple velocity-based advection (grid shift)
        # To avoid scipy dependency, we use a simple roll-based approximation or 
        # just accept memoryless foam if we can't find a fast way.
        # But let's try a simple vectorized shift.
        avg_vx = np.mean(vx)
        avg_vz = np.mean(vz)
        shift_x = int(avg_vx * dt * self.N / self.L)
        shift_z = int(avg_vz * dt * self.N / self.L)
        self.foam_buffer = np.roll(np.roll(self.foam_buffer, shift_x, axis=1), shift_z, axis=0)
        self.ripple_buffer = np.roll(np.roll(self.ripple_buffer, shift_x, axis=1), shift_z, axis=0)
        
        # Add new foam where waves break (low jacobian)
        new_foam = np.clip((1.0 - jacobian) - 0.5, 0.0, 1.0) * 25.0 * dt
        self.foam_buffer += new_foam
        
        foam_decay = float(np.exp(-0.5 * dt)) # Dissipation
        self.foam_buffer *= foam_decay
        self.foam_buffer = np.clip(self.foam_buffer, 0.0, 1.0)

        # 7. Optimized Upload
        self.disp_data[..., 0] = dx
        self.disp_data[..., 1] = dy
        self.disp_data[..., 2] = dz
        self.disp_data[..., 3] = 1.0
        
        # Upload Foam
        glBindTexture(GL_TEXTURE_2D, self.tex_foam_advected)
        glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, self.N, self.N, GL_RED, GL_FLOAT, self.foam_buffer.astype(np.float32))
        
        # Upload Ripples
        glBindTexture(GL_TEXTURE_2D, self.tex_ripple)
        glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, self.N, self.N, GL_RED, GL_FLOAT, self.ripple_buffer.astype(np.float32))
        
        # Displacement
        glBindTexture(GL_TEXTURE_2D, self.tex_displacement)
        glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, self.N, self.N, GL_RGBA, GL_FLOAT, self.disp_data)
        
        # Jacobian
        jac_data = jacobian.astype(np.float32)
        glBindTexture(GL_TEXTURE_2D, self.tex_jacobian)
        glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, self.N, self.N, GL_RED, GL_FLOAT, jac_data)
        
        # Velocity
        vel_data = np.stack([vx, vz], axis=-1).astype(np.float32)
        glBindTexture(GL_TEXTURE_2D, self.tex_velocity)
        glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, self.N, self.N, GL_RG, GL_FLOAT, vel_data)
        
        glBindTexture(GL_TEXTURE_2D, 0)

        # Keep CPU copy so spawn sources (e.g. ocean foam particles) can sample it
        self.last_dy = dy
        self.last_jacobian_cpu = jac_data

    def get_height_at(self, world_x, world_z):
        """Sample height at world coordinates (bilinear interpolation)."""
        u = (world_x / self.L) % 1.0
        v = (world_z / self.L) % 1.0
        if u < 0: u += 1.0
        if v < 0: v += 1.0
        if not hasattr(self, 'last_dy'): return 0.0
        
        fx = u * (self.N - 1)
        fz = v * (self.N - 1)
        ix1 = int(fx); ix2 = (ix1 + 1) % self.N
        iz1 = int(fz); iz2 = (iz1 + 1) % self.N
        tx = fx - ix1; tz = fz - iz1
        
        h11 = self.last_dy[iz1, ix1]
        h21 = self.last_dy[iz1, ix2]
        h12 = self.last_dy[iz2, ix1]
        h22 = self.last_dy[iz2, ix2]
        
        return (1-tz)*( (1-tx)*h11 + tx*h21 ) + tz*( (1-tx)*h12 + tx*h22 )

def init_ocean_gpu():
    global _ocean_vbo, _ocean_ibo, _ocean_index_count, _ocean_shader_fft, _ocean_shader_gerstner
    
    # 1. Initialize Geometry
    if _ocean_vbo is None:
        try:
            _init_geometry()
        except Exception as e:
            print(f"[OCEAN GEOM ERROR] {e}")

    # 2. Initialize Shaders
    # 2. Initialize Shaders (cached inside shader_manager automatically)
    if _ocean_shader_fft is None:
        _ocean_shader_fft = get_shader("Ocean (FFT)")
    if _ocean_shader_gerstner is None:
        _ocean_shader_gerstner = get_shader("Ocean (Gerstner)")

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

def add_ocean_ripple(obj, world_pos, strength=1.0):
    """Adds a physical ripple impact to the ocean at world_pos."""
    if world_pos is None or not hasattr(world_pos, '__getitem__') or len(world_pos) < 3:
        return
    gen = getattr(obj, '_fft_gen_cascade0', None)
    if gen is None: return
    
    print(f"DEBUG: add_ocean_ripple internal received {world_pos}")
    # Map world to 0..1 UV — matching the shader v_uv = world_p.xz / 1000.0
    # No chunk offset needed as v_uv is global/tiling.
    u = (world_pos[0] / gen.L) % 1.0
    v = (world_pos[2] / gen.L) % 1.0
    gen.ripple_queue.append((u, v, strength))

def render_ocean_gpu(camera_pos, obj, sim_time=0.0, weather_obj=None):
    """Render the ocean surface following the camera, choosing between FFT or Gerstner."""
    global _ocean_vbo, _ocean_shader_fft, _ocean_shader_gerstner, _fft_generators
    use_fft = getattr(obj, 'ocean_use_fft', True)

    # Parameters
    level = getattr(obj, 'landscape_ocean_level', 0.0)
    color = obj.material.get('base_color', [0.0, 0.2, 0.5, 1.0])
    # Default opaque. With opacity<1 the scene grid (and anything else behind the ocean)
    # alpha-blends through every pixel, which shows up as flat translucent "panels"
    # wherever the depth complexity changes — the artifacts the user has been chasing.
    opacity = obj.material.get('opacity', 1.0)
    foam = getattr(obj, 'ocean_foam_amount', 0.5)
    chunk_size = 2000.0

    # Wiring Sliders
    speed = getattr(obj, 'ocean_wave_speed', 1.0)
    scale = getattr(obj, 'ocean_wave_scale', 1.0)
    adjusted_time = sim_time * speed

    from .procedural_atmosphere import get_sun_direction, get_sun_color, get_ambient_color
    atmo = next((o for o in obj.scene_ref.scene_objects if o.obj_type == 'atmosphere' and o.active), None) if hasattr(obj, 'scene_ref') else None
    sun_dir = get_sun_direction(atmo)
    sun_col = get_sun_color(atmo)
    amb_col = get_ambient_color(atmo)
    ti_day  = getattr(atmo, 'time_of_day', 0.5) if atmo else 0.5

    # 1. Cascade simulator updates (three FFT generators at different domain sizes)
    gen = gen1 = gen2 = None
    if use_fft:
        res        = getattr(obj, 'ocean_fft_resolution', 128)
        choppiness = getattr(obj, 'ocean_wave_choppiness', 1.5)
        intensity  = getattr(obj, 'ocean_wave_intensity', 1.0)

        # Cascade 0 — large swells (L=1000, primary wind direction)
        key0 = (res, 1000.0)
        if key0 not in _fft_generators:
            _fft_generators[key0] = FFTOceanWaveGenerator(resolution=res, size=1000.0, wind_speed=30.0, wind_dir=(1.0, 0.2))
        gen = _fft_generators[key0]
        gen.update(adjusted_time, choppiness=choppiness, intensity=intensity)
        obj._fft_gen_cascade0 = gen

        # Cascade 1 — medium chop (diagonal wind breaks up the banding)
        key1 = (64, 200.0)
        if key1 not in _fft_generators:
            _fft_generators[key1] = FFTOceanWaveGenerator(resolution=64, size=200.0, wind_speed=20.0, wind_dir=(0.6, 0.8))
        gen1 = _fft_generators[key1]
        gen1.update(adjusted_time, choppiness=choppiness, intensity=intensity)

        # Cascade 2 — small ripples (cross-wind adds surface chaos)
        key2 = (64, 50.0)
        if key2 not in _fft_generators:
            _fft_generators[key2] = FFTOceanWaveGenerator(resolution=64, size=50.0, wind_speed=10.0, wind_dir=(0.2, 1.0))
        gen2 = _fft_generators[key2]
        gen2.update(adjusted_time, choppiness=choppiness * 0.5, intensity=intensity)

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

    # Stash references on the object so attached particle systems / .logic nodes can
    # access the live cascade-0 jacobian buffer and the camera-snapped grid origin.
    obj._last_grid_origin = (follow_x, level, follow_z)

    # 2. Determine if underwater for seamless rendering
    # We sample the main FFT cascade to check camera elevation vs wave height
    is_underwater = False
    if use_fft and gen:
        # Check height at camera
        h_wave = gen.get_height_at(camera_pos[0], camera_pos[2])
        # Include hero waves for precision (Gerstner on CPU)
        hero_h = 0.0
        hero_count = int(getattr(obj, 'ocean_hero_count', 0))
        if hero_count > 0:
            hero_amps   = [getattr(obj, f'ocean_hero_amp_{i}',   [4.0, 3.0, 2.0][i]) for i in range(3)]
            hero_wlens  = [getattr(obj, f'ocean_hero_wlen_{i}',  [350.0, 180.0, 90.0][i]) for i in range(3)]
            hero_dirs   = [math.radians(getattr(obj, f'ocean_hero_dir_{i}', [25.0, 70.0, 140.0][i])) for i in range(3)]
            for i in range(min(3, hero_count)):
                k = 6.28318 / max(hero_wlens[i], 0.01)
                c = math.sqrt(9.81 / k)
                d = [math.cos(hero_dirs[i]), math.sin(hero_dirs[i])]
                phase = k * (d[0]*camera_pos[0] + d[1]*camera_pos[2] - c*adjusted_time)
                hero_h += hero_amps[i] * math.sin(phase)
        
        if camera_pos[1] < (level + h_wave + hero_h):
            is_underwater = True

    # Rendering Setup
    glEnable(GL_DEPTH_TEST)
    glDepthFunc(GL_LESS)
    glDepthMask(GL_TRUE)
    try: glDisable(GL_FOG)
    except Exception: pass
    
    # Aggressively reset state to prevent leakage from other shaders (e.g. Fish)
    glUseProgram(0)
    for i in range(16):
        try: glDisableVertexAttribArray(i)
        except Exception: pass

    # Seamless Underwater Handling:
    # 1. Flip culling so we see the surface from below
    # 2. When underwater, we don't cull BACK, we cull FRONT (or just disable)
    glEnable(GL_CULL_FACE)
    if is_underwater:
        glCullFace(GL_FRONT)
    else:
        glCullFace(GL_BACK)

    # Conditional Blending.
    # Keep depth-writes ON even when blending — turning them off causes back-facing wave
    # crests behind front-facing ones to alpha-blend in arbitrary order, which shows up as
    # large flat translucent "panels" sticking through the surface. The ocean is a single
    # mesh that should always occlude itself; we only want the alpha for fade-to-distance.
    if opacity < 0.99:
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glDepthMask(GL_TRUE)
    else:
        glDisable(GL_BLEND)

    try:
        shader.use()

        if use_fft and gen:
            # Bind 6 textures: 3 displacement + 3 jacobian (one per cascade)
            glActiveTexture(GL_TEXTURE0)
            glBindTexture(GL_TEXTURE_2D, gen.tex_displacement)
            shader.set_uniform_i("u_displacement_map", 0)

            glActiveTexture(GL_TEXTURE1)
            glBindTexture(GL_TEXTURE_2D, gen.tex_jacobian)
            shader.set_uniform_i("u_jacobian_map", 1)

            glActiveTexture(GL_TEXTURE2)
            glBindTexture(GL_TEXTURE_2D, gen1.tex_displacement if gen1 else gen.tex_displacement)
            shader.set_uniform_i("u_displacement_c1", 2)

            glActiveTexture(GL_TEXTURE3)
            glBindTexture(GL_TEXTURE_2D, gen1.tex_jacobian if gen1 else gen.tex_jacobian)
            shader.set_uniform_i("u_jacobian_c1", 3)

            glActiveTexture(GL_TEXTURE4)
            glBindTexture(GL_TEXTURE_2D, gen2.tex_displacement if gen2 else gen.tex_displacement)
            shader.set_uniform_i("u_displacement_c2", 4)

            glActiveTexture(GL_TEXTURE5)
            glBindTexture(GL_TEXTURE_2D, gen2.tex_jacobian if gen2 else gen.tex_jacobian)
            shader.set_uniform_i("u_jacobian_c2", 5)

            # New: Velocity and Advected Foam
            glActiveTexture(GL_TEXTURE6)
            glBindTexture(GL_TEXTURE_2D, gen.tex_velocity)
            shader.set_uniform_i("u_velocity_map", 6)

            glActiveTexture(GL_TEXTURE7)
            glBindTexture(GL_TEXTURE_2D, gen.tex_foam_advected)
            shader.set_uniform_i("u_foam_advected", 7)
            
            glActiveTexture(GL_TEXTURE8)
            glBindTexture(GL_TEXTURE_2D, gen.tex_ripple)
            shader.set_uniform_i("u_ripple_map", 8)

            # Cascade blend weights
            shader.set_uniform_f("u_cascade1_weight", getattr(obj, 'ocean_cascade1_weight', 0.5))
            shader.set_uniform_f("u_cascade2_weight", getattr(obj, 'ocean_cascade2_weight', 0.7))

            total_choppiness = getattr(obj, 'ocean_wave_choppiness', 1.5) + getattr(obj, 'ocean_wave_steepness', 0.0)
            shader.set_uniform_f("u_choppiness", total_choppiness)
            shader.set_uniform_f("u_wave_scale", scale)

            # Gerstner hero waves
            hero_count = int(getattr(obj, 'ocean_hero_count', 1))
            shader.set_uniform_i("u_hero_count", hero_count)
            # Defaults spread across different directions to avoid banding
            hero_amps   = [getattr(obj, f'ocean_hero_amp_{i}',   [4.0, 3.0, 2.0][i]) for i in range(3)]
            hero_wlens  = [getattr(obj, f'ocean_hero_wlen_{i}',  [350.0, 180.0, 90.0][i]) for i in range(3)]
            hero_dirs   = [math.radians(getattr(obj, f'ocean_hero_dir_{i}', [25.0, 70.0, 140.0][i])) for i in range(3)]
            hero_steeps = [getattr(obj, f'ocean_hero_steep_{i}', [0.25, 0.35, 0.5][i]) for i in range(3)]
            shader.set_uniform_f_array("u_hero_amp",   hero_amps)
            shader.set_uniform_f_array("u_hero_wlen",  hero_wlens)
            shader.set_uniform_f_array("u_hero_dir",   hero_dirs)
            shader.set_uniform_f_array("u_hero_steep", hero_steeps)

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
        shader.set_uniform_v3("sunDir", *sun_dir)
        shader.set_uniform_v3("sunColor", *sun_col)
        shader.set_uniform_v3("ambientColor", *amb_col)
        shader.set_uniform_f("time_of_day", float(ti_day))

        # Advanced Visuals
        shader.set_uniform_f("u_fresnel_strength",  getattr(obj, 'ocean_fresnel_strength', 0.3))
        shader.set_uniform_f("u_specular_intensity", getattr(obj, 'ocean_specular_intensity', 1.0))
        shader.set_uniform_f("u_peak_brightness",   getattr(obj, 'ocean_peak_brightness', 1.0))
        shader.set_uniform_f("u_sss_strength",      getattr(obj, 'ocean_sss_strength', 1.0))
        tint = getattr(obj, 'ocean_reflection_tint', [0.5, 0.7, 1.0, 1.0])
        shader.set_uniform_v3("u_reflection_tint", tint[0], tint[1], tint[2])

        # Foam layer controls
        shader.set_uniform_f("u_foam_jacobian",        getattr(obj, 'ocean_foam_jacobian',        1.0))
        shader.set_uniform_f("u_foam_whitecap",        getattr(obj, 'ocean_foam_whitecap',        1.0))
        shader.set_uniform_f("u_foam_whitecap_thresh", getattr(obj, 'ocean_foam_whitecap_thresh', 0.5))
        shader.set_uniform_f("u_foam_streak",          getattr(obj, 'ocean_foam_streak',          1.0))
        shader.set_uniform_f("u_foam_streak_speed",    getattr(obj, 'ocean_foam_streak_speed',    1.5))
        # Flow advection scale (tunes how much horizontal displacement advects foam UVs)
        shader.set_uniform_f("u_flow_scale",           getattr(obj, 'ocean_flow_scale',          0.02))
        shader.set_uniform_f("u_foam_sharpness",       getattr(obj, 'ocean_foam_sharpness',       2.5))
        shader.set_uniform_f("u_detail_strength",      getattr(obj, 'ocean_detail_strength',      0.7))

        # Rain ripple controls
        ri = 0.0
        if weather_obj:
            # Use the live intensity from the weather driver
            ri = float(getattr(weather_obj, '_current_intensity', 0.0))
        else:
            # Fallback to manual slider on the ocean object itself
            ri = float(getattr(obj, 'u_rain_intensity', 0.0))
            
        shader.set_uniform_f("u_rain_intensity",       ri)
        shader.set_uniform_f("u_rain_time",            float(sim_time))
        
        # Underwater uniforms
        shader.set_uniform_i("u_is_underwater",        int(is_underwater))
        u_tint = getattr(obj, 'ocean_underwater_tint', [0.0, 0.4, 0.6])
        shader.set_uniform_v3("u_underwater_tint",     *u_tint)

    except Exception as e:
        import traceback
        print(f"[OCEAN SHADER ERROR] {e}")
        traceback.print_exc()
        glUseProgram(0)
    
    glEnable(GL_DEPTH_TEST)
    if opacity < 0.99: glDepthMask(GL_FALSE)
    else: glDepthMask(GL_TRUE)
    
    glPushMatrix()
    obj_pos = getattr(obj, 'position', [0,0,0])
    glTranslatef(follow_x - obj_pos[0], level - obj_pos[1] + 0.15, follow_z - obj_pos[2])
    glScalef(chunk_size, 1.0, chunk_size)
    
    # Render geometry
    glColor4f(1.0, 1.0, 1.0, 1.0)
    glBindBuffer(GL_ARRAY_BUFFER, _ocean_vbo)
    
    # Enable legacy vertex array
    glEnableClientState(GL_VERTEX_ARRAY)
    glVertexPointer(3, GL_FLOAT, 0, None)
    
    # Modern attribute 0 (gl_Vertex) might be enabled by meshes; 
    # we need it to point to our VBO too if the shader is modern.
    glEnableVertexAttribArray(0)
    glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, 0, None)

    glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, _ocean_ibo)
    glDrawElements(GL_TRIANGLES, _ocean_index_count, GL_UNSIGNED_INT, None)
    
    # Cleanup vertex state
    glDisableVertexAttribArray(0)
    glDisableClientState(GL_VERTEX_ARRAY)
    glBindBuffer(GL_ARRAY_BUFFER, 0)
    glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, 0)
    glPopMatrix()
    
    shader.stop()
    glCullFace(GL_BACK) # Reset cull face state
    glDepthMask(GL_TRUE)
    glActiveTexture(GL_TEXTURE0)
