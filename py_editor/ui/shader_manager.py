"""
shader_manager.py

A robust utility for managing GLSL shaders and GPU programs.
This allows moving procedural logic (like Gerstner waves) from the CPU to the GPU.
"""
from OpenGL.GL import *
from OpenGL.GL.shaders import compileProgram, compileShader
import numpy as np

def create_standard_shader():
    v_src = """
    #version 120
    varying vec3 v_normal;
    void main() {
        v_normal = gl_NormalMatrix * gl_Normal;
        gl_Position = ftransform();
    }
    """
    f_src = """
    #version 120
    uniform vec4 base_color;
    uniform vec3 sunDir;
    varying vec3 v_normal;
    void main() {
        vec3 n = normalize(v_normal);
        vec3 l = normalize(sunDir);
        float diff = max(dot(n, l), 0.2);
        gl_FragColor = vec4(base_color.rgb * diff, base_color.a);
    }
    """
    return ShaderProgram(v_src, f_src)

def create_fish_shader():
    v_src = """
    #version 120
    uniform float time;
    uniform float speed;
    uniform float freq;
    uniform float intensity;
    
    uniform float yaw_amp;
    uniform float side_amp;
    uniform float roll_amp;
    uniform float flag_amp;
    
    uniform float forward_axis; // 0=X, 1=Y, 2=Z
    uniform float invert_axis;  // 0=Normal, 1=Inverted
    
    varying vec3 v_pos;
    varying vec3 v_normal;

    mat3 rotate_y(float a) {
        float c = cos(a); float s = sin(a);
        return mat3(c, 0, s, 0, 1, 0, -s, 0, c);
    }
    mat3 rotate_z(float a) {
        float c = cos(a); float s = sin(a);
        return mat3(c, -s, 0, s, c, 0, 0, 0, 1);
    }

    void main() {
        vec3 pos = gl_Vertex.xyz;
        
        // 1. Identify "Forward Distance" (0 at head, 1 at tail)
        float d = pos.x;
        if (forward_axis > 0.5 && forward_axis < 1.5) d = pos.y;
        else if (forward_axis > 1.5) d = pos.z;
        
        float dist = d + 0.5; 
        if (invert_axis > 0.5) dist = 0.5 - d;
        
        // Mask: Head stays still (0), Tail wiggles fully (1)
        float mask = smoothstep(0.0, 1.0, dist);
        float t = time * speed;
        
        // --- 2. Calculate Motion Components ---
        // Primary Yaw (Large body swing)
        float yaw = sin(t - dist * freq) * yaw_amp * intensity * mask;
        
        // Secondary Yaw (Tail flag/flicker - higher freq)
        float flag = sin(t * 1.5 - dist * freq * 2.0) * flag_amp * intensity * pow(mask, 2.0);
        
        // Roll (Subtle bank)
        float roll = cos(t - dist * freq) * roll_amp * intensity * mask;
        
        // Side Translation
        float side = sin(t - dist * freq) * side_amp * intensity * mask;

        // --- 3. Apply Transformations ---
        // We transform the vertex relative to its forward position (d)
        // Extract local offsets (e.g. if X is forward, offsets are Y and Z)
        vec3 local_offset = pos;
        if (forward_axis < 0.5) local_offset.x = 0.0;
        else if (forward_axis < 1.5) local_offset.y = 0.0;
        else local_offset.z = 0.0;
        
        // Rotate the local slice (keeps fins on body)
        mat3 rot = rotate_y(yaw + flag) * rotate_z(roll);
        local_offset = rot * local_offset;
        
        // Reassemble position
        vec3 final_pos = pos;
        if (forward_axis < 0.5) {
            final_pos.y = local_offset.y;
            final_pos.z = local_offset.z + side; // Add lateral shift
        } else if (forward_axis < 1.5) {
            final_pos.x = local_offset.x + side;
            final_pos.z = local_offset.z;
        } else {
            final_pos.x = local_offset.x + side;
            final_pos.y = local_offset.y;
        }
        
        v_pos = (gl_ModelViewMatrix * vec4(final_pos, 1.0)).xyz;
        v_normal = gl_NormalMatrix * (rot * gl_Normal); // Rotate normal too
        gl_Position = gl_ModelViewProjectionMatrix * vec4(final_pos, 1.0);
    }
    """
    f_src = """
    #version 120
    uniform vec4 base_color;
    uniform vec3 sunDir;
    varying vec3 v_pos;
    varying vec3 v_normal;

    void main() {
        vec3 n = normalize(v_normal);
        vec3 l = normalize(sunDir);
        float diff = max(dot(n, l), 0.2);
        gl_FragColor = vec4(base_color.rgb * diff, base_color.a);
    }
    """
    return ShaderProgram(v_src, f_src)

def create_flag_shader():
    v_src = """
    #version 120
    uniform float time;
    uniform float wave_speed;
    uniform float wave_amplitude;
    uniform float invert_axis;
    
    varying vec3 v_pos;
    varying vec3 v_normal;

    void main() {
        vec3 pos = gl_Vertex.xyz;
        float d = pos.x;
        if (invert_axis > 0.5) d = -pos.x;
        
        float wave = sin(d * 2.0 + time * wave_speed) * cos(pos.z * 1.5 + time * wave_speed * 0.8);
        pos.y += wave * wave_amplitude * (d + 0.5); 
        
        v_pos = (gl_ModelViewMatrix * vec4(pos, 1.0)).xyz;
        v_normal = gl_NormalMatrix * gl_Normal;
        gl_Position = gl_ModelViewProjectionMatrix * vec4(pos, 1.0);
    }
    """
    f_src = """
    #version 120
    uniform vec4 base_color;
    uniform vec3 sunDir;
    varying vec3 v_pos;
    varying vec3 v_normal;

    void main() {
        vec3 n = normalize(v_normal);
        vec3 l = normalize(sunDir);
        float diff = max(dot(n, l), 0.2);
        gl_FragColor = vec4(base_color.rgb * diff, base_color.a);
    }
    """
    return ShaderProgram(v_src, f_src)

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

def create_ocean_shader_fft():
    # VERTEX SHADER: 3-cascade displacement + Gerstner hero waves
    v_src = """
    #version 330 compatibility

    uniform sampler2D u_displacement_map;  // Cascade 0: large swells  (L=1000)
    uniform sampler2D u_displacement_c1;   // Cascade 1: medium chop   (L=200)
    uniform sampler2D u_displacement_c2;   // Cascade 2: small ripples (L=50)
    uniform vec3  grid_origin;
    uniform float grid_chunk_size;
    uniform float u_wave_scale;
    uniform float u_choppiness;
    uniform float u_cascade1_weight;
    uniform float u_cascade2_weight;
    uniform float time;
    uniform vec3  cam_pos;

    // Gerstner hero waves (up to 3 artist-controlled swell waves)
    uniform int   u_hero_count;
    uniform float u_hero_amp[3];
    uniform float u_hero_wlen[3];
    uniform float u_hero_dir[3];   // radians
    uniform float u_hero_steep[3];

    out vec3  v_pos;
    out float v_height;
    out vec3  v_view_dir;
    out vec2  v_uv;

    vec3 gerstner_hero(vec3 wp, float amp, float wlen, float dir_angle, float steep) {
        float k     = 6.28318 / max(wlen, 0.01);
        float c     = sqrt(9.81 / k);
        vec2  d     = vec2(cos(dir_angle), sin(dir_angle));
        float phase = k * (dot(d, wp.xz) - c * time);
        float s     = clamp(steep, 0.0, 0.99);
        return vec3(d.x * amp * s * cos(phase),
                    amp * sin(phase),
                    d.y * amp * s * cos(phase));
    }

    void main() {
        vec3 world_p = (gl_Vertex.xyz * grid_chunk_size) + grid_origin;

        // Cascade UV sets. Each cascade is rotated so their tiling axes don't align —
        // aligned tiling at cascade-2's ~50m period was showing as horizontal "strip" bands.
        v_uv     = (world_p.xz / 1000.0) * u_wave_scale;
        // cascade-1: rotate ~37°, cascade-2: rotate ~-61°
        mat2 rot1 = mat2( 0.7986, 0.6018, -0.6018, 0.7986);
        mat2 rot2 = mat2( 0.4848,-0.8746,  0.8746, 0.4848);
        vec2 uv1 = (rot1 * v_uv) * 5.0;   // /200 equivalent
        vec2 uv2 = (rot2 * v_uv) * 20.0;  // /50  equivalent

        // --- Cascade displacements ---
        // Large cascade: full XZ (drives main swell shape).
        // The mesh samples at ~7.8m spacing while the cascade-0 texture has 3.9m cells —
        // that's a 2× Nyquist violation, which produces visible aliased "ribbon strip"
        // artifacts that scale with intensity. A 5-tap box filter low-passes the texture
        // to stay below the mesh Nyquist limit.
        float td = 1.0 / 256.0;  // one texel in cascade-0 UV space
        vec3 disp0 = texture(u_displacement_map, v_uv).rgb * 0.5
                   + texture(u_displacement_map, v_uv + vec2( td, 0.0)).rgb * 0.125
                   + texture(u_displacement_map, v_uv + vec2(-td, 0.0)).rgb * 0.125
                   + texture(u_displacement_map, v_uv + vec2(0.0,  td)).rgb * 0.125
                   + texture(u_displacement_map, v_uv + vec2(0.0, -td)).rgb * 0.125;
        vec3 disp1 = texture(u_displacement_c1,  uv1).rgb * u_cascade1_weight;
        vec3 disp2 = texture(u_displacement_c2,  uv2).rgb * u_cascade2_weight;

        // Small cascades contribute mainly to height/normals, NOT to horizontal folding
        // Full XZ from them would cause high-frequency vertex crossing
        disp1.xz *= 0.25;
        disp2.xz *= 0.05;

        vec3 fft_disp = disp0 + disp1 + disp2;

        // --- Gerstner hero waves ---
        vec3 hero = vec3(0.0);
        if (u_hero_count > 0) hero += gerstner_hero(world_p, u_hero_amp[0], u_hero_wlen[0], u_hero_dir[0], u_hero_steep[0]);
        if (u_hero_count > 1) hero += gerstner_hero(world_p, u_hero_amp[1], u_hero_wlen[1], u_hero_dir[1], u_hero_steep[1]);
        if (u_hero_count > 2) hero += gerstner_hero(world_p, u_hero_amp[2], u_hero_wlen[2], u_hero_dir[2], u_hero_steep[2]);

        v_height = fft_disp.y + hero.y;
        v_pos    = world_p + fft_disp + hero;

        // --- Vertex displacement ---
        // XZ: FFT gets choppiness scaling; hero uses raw horizontal (steepness already controls it)
        // Both divide by grid_chunk_size to convert world-metres → local [-1,1] space
        float inv_chunk = 1.0 / grid_chunk_size;
        vec3 displaced_v = gl_Vertex.xyz;
        displaced_v.xz  += fft_disp.xz * u_choppiness * inv_chunk;
        displaced_v.xz  += hero.xz * inv_chunk;
        displaced_v.y   += fft_disp.y + hero.y;

        // Soft-limit XZ so vertices can never cross their neighbours (prevents tearing).
        // Hard clamp() makes adjacent saturated verts collapse to identical positions, which
        // shows up as flat ribbon/strip artifacts. tanh() gives smooth saturation instead.
        float max_disp = (2.0 / 255.0) * 0.55;
        vec2 d_xz      = displaced_v.xz - gl_Vertex.xz;
        d_xz           = max_disp * tanh(d_xz / max(max_disp, 1e-6));
        displaced_v.xz = gl_Vertex.xz + d_xz;

        vec4 eye_pos = gl_ModelViewMatrix * vec4(displaced_v, 1.0);
        v_view_dir   = normalize(-eye_pos.xyz);

        gl_Position = gl_ModelViewProjectionMatrix * vec4(displaced_v, 1.0);
    }
    """

    # FRAGMENT SHADER: Multi-cascade normals/foam, peak glow, SSS, specular
    f_src = """
    #version 330 compatibility

    uniform vec4  ocean_color;
    uniform float ocean_opacity;
    uniform float foam_amount;
    uniform float time;
    uniform vec3  cam_pos;

    // Cascade displacement + jacobian textures
    uniform sampler2D u_displacement_map;
    uniform sampler2D u_displacement_c1;
    uniform sampler2D u_displacement_c2;
    uniform sampler2D u_jacobian_map;
    uniform sampler2D u_jacobian_c1;
    uniform sampler2D u_jacobian_c2;
    uniform sampler2D u_velocity_map;
    uniform sampler2D u_foam_advected;
    uniform sampler2D u_ripple_map;
    uniform float u_wave_scale;
    uniform float u_cascade1_weight;
    uniform float u_cascade2_weight;
    uniform float time_of_day;

    // Advanced Visuals
    uniform float u_fresnel_strength;
    uniform float u_specular_intensity;
    uniform vec3  u_reflection_tint;
    uniform float u_peak_brightness;
    uniform float u_sss_strength;

    // Rain splash / ripple controls
    uniform float u_rain_intensity;       // 0..1 (from Weather primitive)
    uniform float u_rain_time;            // seconds (drives ripple animation)

    // Foam layer controls
    uniform float u_foam_jacobian;        // jacobian break foam intensity
    uniform float u_foam_whitecap;        // height whitecap foam intensity
    uniform float u_foam_whitecap_thresh; // height threshold for whitecaps (0-1)
    uniform float u_foam_streak;          // streak trail intensity
    uniform float u_foam_streak_speed;    // how fast streak trails move
    uniform float u_flow_scale;           // scale for converting displacement -> flow UV advection
    uniform float u_foam_sharpness;       // jacobian foam sharpness exponent
    uniform float u_detail_strength;      // 4th-pass micro-detail normal weight

    in vec3  v_pos;
    in float v_height;
    in vec3  v_view_dir;
    in vec2  v_uv;

    // --- Foam Utilities ---
    vec2 hash2(vec2 p) {
        return fract(sin(vec2(dot(p, vec2(127.1, 311.7)), dot(p, vec2(269.5, 183.3)))) * 43758.5453);
    }
    
    float bubble_noise(vec2 p, float t) {
        vec2 i = floor(p);
        vec2 f = fract(p);
        float dist = 1.0;
        for(int y=-1; y<=1; y++) {
            for(int x=-1; x<=1; x++) {
                vec2 g = vec2(float(x), float(y));
                vec2 o = hash2(i + g);
                o = 0.5 + 0.5 * sin(t + 6.28 * o);
                vec2 r = g + o - f;
                dist = min(dist, dot(r, r));
            }
        }
        return sqrt(dist);
    }

    void main() {
        // Cascade UVs derived from cascade-0 UV — must match the rotations used in the
        // vertex shader so per-pixel normals line up with the displaced geometry.
        mat2 rot1 = mat2( 0.7986, 0.6018, -0.6018, 0.7986);
        mat2 rot2 = mat2( 0.4848,-0.8746,  0.8746, 0.4848);
        vec2 uv1 = (rot1 * v_uv) * 5.0;
        vec2 uv2 = (rot2 * v_uv) * 20.0;
        vec2 uv3 = uv2 * 4.0;   // 4th micro-detail pass (×80 total scale)

        // --- Multi-cascade per-pixel normals ---
        // Smaller cascades contribute proportionally more to surface detail
        float d0 = 1.0 / 128.0;
        float d1 = 1.0 / 64.0;
        float hL  = texture(u_displacement_map, v_uv - vec2(d0, 0.0)).y;
        float hR  = texture(u_displacement_map, v_uv + vec2(d0, 0.0)).y;
        float hD  = texture(u_displacement_map, v_uv - vec2(0.0, d0)).y;
        float hU  = texture(u_displacement_map, v_uv + vec2(0.0, d0)).y;

        float hL1 = texture(u_displacement_c1, uv1 - vec2(d1, 0.0)).y * u_cascade1_weight;
        float hR1 = texture(u_displacement_c1, uv1 + vec2(d1, 0.0)).y * u_cascade1_weight;
        float hD1 = texture(u_displacement_c1, uv1 - vec2(0.0, d1)).y * u_cascade1_weight;
        float hU1 = texture(u_displacement_c1, uv1 + vec2(0.0, d1)).y * u_cascade1_weight;

        float hL2 = texture(u_displacement_c2, uv2 - vec2(d1, 0.0)).y * u_cascade2_weight;
        float hR2 = texture(u_displacement_c2, uv2 + vec2(d1, 0.0)).y * u_cascade2_weight;
        float hD2 = texture(u_displacement_c2, uv2 - vec2(0.0, d1)).y * u_cascade2_weight;
        float hU2 = texture(u_displacement_c2, uv2 + vec2(0.0, d1)).y * u_cascade2_weight;

        // 4th pass: reuse cascade-2 texture at ×4 UV — adds fine surface crispness (not bumps)
        float hL3 = texture(u_displacement_c2, uv3 - vec2(d1, 0.0)).y * u_cascade2_weight * u_detail_strength;
        float hR3 = texture(u_displacement_c2, uv3 + vec2(d1, 0.0)).y * u_cascade2_weight * u_detail_strength;
        float hD3 = texture(u_displacement_c2, uv3 - vec2(0.0, d1)).y * u_cascade2_weight * u_detail_strength;
        float hU3 = texture(u_displacement_c2, uv3 + vec2(0.0, d1)).y * u_cascade2_weight * u_detail_strength;

        // --- Normals: 4-level cascade. Y=0.12 (was 0.06) — the very-low Y was amplifying
        // small finite-difference errors into harsh dark/bright strips at glancing angles.
        vec3 normal = normalize(vec3(
            (hL - hR) + (hL1 - hR1) * 4.0 + (hL2 - hR2) * 12.0 + (hL3 - hR3) * 23.0,
            0.12,
            (hD - hU) + (hD1 - hU1) * 4.0 + (hD2 - hU2) * 12.0 + (hD3 - hU3) * 23.0
        ));
        vec3 view_dir = normalize(v_view_dir);
        
        // --- Modular Ripples (Impacts from logic) ---
        float dyn_rip = texture(u_ripple_map, v_uv).r;
        if (dyn_rip > 0.005) {
            // Sample neighbors for normal perturbation
            float d2 = 0.5/128.0;
            float rL = texture(u_ripple_map, v_uv - vec2(d2, 0.0)).r;
            float rR = texture(u_ripple_map, v_uv + vec2(d2, 0.0)).r;
            float rD = texture(u_ripple_map, v_uv - vec2(0.0, d2)).r;
            float rU = texture(u_ripple_map, v_uv + vec2(0.0, d2)).r;
            
            // Sharpened normal for clearer ripple highlights
            vec3 ripple_n = normalize(vec3(rL - rR, 0.05, rD - rU));
            // Mix the normal using a safe lerp-like approach
            normal = normalize(mix(normal, ripple_n, dyn_rip * 0.7));
        }

        // --- Rain Ripples (procedural, driven by u_rain_intensity) ----
        // Sum a few scales of expanding ring cells. Each cell spawns a ripple at a
        // random phase; the ring radius grows with phase and fades as it ages.
        float _splash_foam = dyn_rip * 0.5;
        if (u_rain_intensity > 0.001) {
            vec2 ruv = v_uv * 180.0;
            float rain_h = 0.0;
            float rain_dx = 0.0;
            float rain_dz = 0.0;
            for (int i = 0; i < 3; i++) {
                vec2 cell = floor(ruv);
                vec2 f    = fract(ruv) - 0.5;
                // Hash per-cell seed & random jitter inside the cell
                float s  = fract(sin(dot(cell, vec2(127.1, 311.7)) + float(i)*7.3) * 43758.5453);
                vec2 jitter = vec2(
                    fract(sin(s * 91.13) * 47453.0) - 0.5,
                    fract(sin(s * 17.77) * 51331.0) - 0.5
                ) * 0.6;
                vec2 p = f - jitter;
                float phase = fract(u_rain_time * 1.6 + s);
                float d = length(p);
                // Gate on rain intensity — sparse rings at low intensity
                float density_gate = step(1.0 - clamp(u_rain_intensity, 0.0, 1.0), s);
                float ring_r = phase * 0.45;
                float ring = exp(-pow((d - ring_r) * 22.0, 2.0)) * (1.0 - phase) * density_gate;
                rain_h += ring;
                // finite-diff along axes for normal perturbation
                float pl = length(p - vec2(0.02, 0.0));
                float pr = length(p + vec2(0.02, 0.0));
                float pd = length(p - vec2(0.0, 0.02));
                float pu = length(p + vec2(0.0, 0.02));
                rain_dx += (exp(-pow((pl - ring_r)*22.0,2.0)) - exp(-pow((pr - ring_r)*22.0,2.0))) * (1.0 - phase) * density_gate;
                rain_dz += (exp(-pow((pd - ring_r)*22.0,2.0)) - exp(-pow((pu - ring_r)*22.0,2.0))) * (1.0 - phase) * density_gate;
                ruv = ruv * 1.7 + 5.3;
            }
            float amp = clamp(u_rain_intensity, 0.0, 2.0);
            vec3 rain_n = normalize(vec3(rain_dx, 0.06, rain_dz));
            normal = normalize(mix(normal, rain_n, clamp(abs(rain_h) * amp * 1.2, 0.0, 0.75)));
            _splash_foam += clamp(rain_h * amp, 0.0, 1.0) * 0.35;
        }

        // --- Day/Night Lighting ---
        vec3  sun_dir   = normalize(vec3(sin(time_of_day * 6.28), cos(time_of_day * 6.28), 0.2));
        vec3  light_dir = sun_dir;
        float day_ratio = max(sin(time_of_day * 3.14159), 0.0);

        // --- Base Water Color (SoT: rich teal-inky blue, not flat navy) ---
        float h_norm    = clamp(v_height * 0.04 + 0.55, 0.0, 1.0);
        // Deep = dark teal-black (middle ground between rich teal and flat navy)
        vec3 color_deep = mix(vec3(0.005, 0.04, 0.08), ocean_color.rgb * 0.38, 0.45);
        // Shallow = bright teal-cyan (SoT's glowing crest color)
        vec3 color_shal = mix(vec3(0.04, 0.30, 0.42), ocean_color.rgb, 0.55) * 1.15;
        vec3 water_rgb  = mix(color_deep, color_shal, pow(h_norm, 1.3));

        // --- Ambient sky bounce — the key to "wet" look ---
        // Even in shadow, ocean always reflects some sky. SoT water is NEVER flat matte.
        vec3 sky_amb_day   = mix(vec3(0.07, 0.18, 0.32), vec3(0.18, 0.35, 0.52), h_norm);
        vec3 sky_amb_night = vec3(0.03, 0.07, 0.16);
        water_rgb += mix(sky_amb_night, sky_amb_day, day_ratio) * 0.25;

        // --- Directional Diffuse ---
        // Min 0.38 middle ground — keeps shadows from going pure black
        float NdotL   = dot(normal, light_dir);
        float diffuse  = mix(0.38, 1.0, clamp(NdotL * 0.5 + 0.5, 0.0, 1.0));
        diffuse = mix(0.47, diffuse, day_ratio);
        water_rgb *= diffuse;

        // --- SoT Foam System (three layers) ---
        // 1. Jacobian fold foam — where waves break
        float jac0   = texture(u_jacobian_map, v_uv).r;
        float jac1   = texture(u_jacobian_c1,  uv1).r;
        float jac2   = texture(u_jacobian_c2,  uv2).r;
        float jmask0 = clamp(1.0 - jac0, 0.0, 1.0);
        float jmask1 = clamp(1.0 - jac1, 0.0, 1.0) * u_cascade1_weight;
        float jmask2 = clamp(1.0 - jac2, 0.0, 1.0) * u_cascade2_weight;
        float jac_mask = clamp(jmask0 * 0.6 + jmask1 * 0.25 + jmask2 * 0.15, 0.0, 1.0);

        // 2. Height whitecap foam — thick caps on tall crests (SoT hallmark)
        float wc_thresh  = mix(0.60, 0.90, u_foam_whitecap_thresh);
        float crest_foam = smoothstep(wc_thresh, 1.0, h_norm);
        float churn = sin(v_pos.x * 0.018 + time * 0.4) * cos(v_pos.z * 0.014 - time * 0.3);
        crest_foam  *= smoothstep(-0.2, 0.6, churn);

        // 3. Animated streak foam — panned using flowmap technique based on velocity
        float s_speed  = u_foam_streak_speed * 0.1;
        vec2 local_flow = texture(u_velocity_map, v_uv).rg * u_flow_scale;
        
        float phase0 = fract(time * 0.5);
        float phase1 = fract(time * 0.5 + 0.5);
        float f_weight = abs(0.5 - phase0) * 2.0;

        vec2 uv_adv0 = v_uv - local_flow * phase0 * s_speed;
        vec2 uv_adv1 = v_uv - local_flow * phase1 * s_speed;
        
        float streak0_a = clamp(1.0 - texture(u_jacobian_map, uv_adv0).r, 0.0, 1.0);
        float streak0_b = clamp(1.0 - texture(u_jacobian_map, uv_adv0 * 1.7 + 0.13).r, 0.0, 1.0);
        float streak1_a = clamp(1.0 - texture(u_jacobian_map, uv_adv1).r, 0.0, 1.0);
        float streak1_b = clamp(1.0 - texture(u_jacobian_map, uv_adv1 * 1.7 + 0.13).r, 0.0, 1.0);
        
        float streaks = mix(pow(streak0_a, 8.0) * 0.30 + pow(streak0_b, 10.0) * 0.18,
                            pow(streak1_a, 8.0) * 0.30 + pow(streak1_b, 10.0) * 0.18,
                            f_weight);

        // 4. Cellular Bubble Detail + Persistent Advected Foam Buffer (Flowmap)
        // Secondary GPU-side flowmap advection on top of the CPU-side persistent advection.
        float foam_p0 = fract(time * 0.4);
        float foam_p1 = fract(time * 0.4 + 0.5);
        float foam_w  = abs(0.5 - foam_p0) * 2.0;
        
        float foam_samp0 = texture(u_foam_advected, v_uv - local_flow * foam_p0).r;
        float foam_samp1 = texture(u_foam_advected, v_uv - local_flow * foam_p1).r;
        float foam_adv   = mix(foam_samp0, foam_samp1, foam_w);
        
        // Tighter tiling for bubbles, also panned slightly by flow
        vec2 uv_bubbles = v_pos.xz * 35.0 - local_flow * time * 50.0;
        float b_dist = bubble_noise(uv_bubbles, time * 0.6);
        float bubble_rims = smoothstep(0.04, 0.12, b_dist); // The "walls" (1.0 = wall)
        float bubbles = (1.0 - smoothstep(0.0, 0.08, b_dist)) * jac_mask; // Interior seeds

        // Per-layer foam mask driven by individual sliders
        float jac_sharp = max(u_foam_sharpness, 0.5);
        float foam_mask = clamp(
            pow(jac_mask, jac_sharp)  * foam_amount * u_foam_jacobian  * 4.5 +
            crest_foam                * foam_amount * u_foam_whitecap   * 3.5 +
            streaks                   * foam_amount * u_foam_streak      * 2.5 +
            bubbles                   * foam_amount * u_foam_jacobian    * 1.5 +
            foam_adv                  * foam_amount * 2.0,
            0.0, 1.0);
            
        // Reduce solidness: bubble centers are more transparent than rims
        foam_mask *= mix(0.4, 1.0, bubble_rims);

        // Foam color is modulated by bubble rims — interiors are more transparent/teal
        // This stops it from looking like a "white layer"
        vec3 foam_base = vec3(0.96, 0.98, 0.97);
        vec3 bubble_color = mix(vec3(0.02, 0.38, 0.35), foam_base, bubble_rims); 
        vec3 foam_lit = bubble_color * mix(0.80, 1.0, diffuse);
        
        water_rgb = mix(water_rgb, foam_lit, foam_mask);

        // --- SoT Sub-Surface Scattering ---
        float sss_h    = clamp(v_height * 0.12, 0.0, 1.0);
        // Always-on teal rim SSS: wave faces glow cyan even without direct sun
        float sss_rim  = pow(max(1.0 - dot(view_dir, normal), 0.0), 2.5) * sss_h;
        water_rgb += vec3(0.01, 0.36, 0.30) * sss_rim * 0.15 * u_sss_strength;
        // Directional back-lit SSS (sun shining through wave tips)
        float sss_back = max(-NdotL, 0.0);
        float sss_view = pow(max(dot(view_dir, light_dir), 0.0), 2.0);
        float sss      = sss_back * sss_view * sss_h;
        water_rgb += vec3(0.0, 0.65, 0.55) * sss * u_sss_strength * 1.4 * day_ratio;

        // --- Wave Crest Peak Brightness ---
        float crest = smoothstep(0.72, 1.0, h_norm) * clamp(NdotL * 0.5 + 0.5, 0.0, 1.0);
        water_rgb  += vec3(0.55, 0.85, 0.80) * crest * u_peak_brightness * 0.45;

        // --- Triple-Layer Specular (wet glass look) ---
        vec3  half_v       = normalize(light_dir + view_dir + vec3(1e-5));
        float NdotH        = max(dot(normal, half_v), 0.0);
        // Broad wet sheen covers most of the wave face
        float spec_broad   = pow(NdotH,   62.0) * 1.4  * u_specular_intensity * day_ratio;
        // Tight glint — smaller bright highlight
        float spec_tight   = pow(NdotH,  350.0) * 7.0  * u_specular_intensity * day_ratio;
        // Sub-pixel sparkle — ocean glitter
        float spec_sparkle = pow(NdotH, 3000.0) * 18.0 * u_specular_intensity * day_ratio;

        // --- Fresnel Reflection (stronger = wetter) ---
        float NdotV   = max(dot(normal, view_dir), 0.0);
        float fresnel = pow(1.0 - NdotV, 3.5) * u_fresnel_strength;
        // Minimum fresnel so glancing water always shows sky (key "wet" cue)
        fresnel = max(fresnel, pow(1.0 - NdotV, 1.2) * 0.06);

        // --- Sky Reflection Tint ---
        // The orange sunrise/sunset reflection was bleeding into all glancing-angle
        // reflections at any non-noon time-of-day. Fresnel is strongest at the horizon
        // and on wave back-slopes, so that orange showed as brown "claws" and "plates"
        // wrapping every wave. Narrow the orange band so it only kicks in within ~10%
        // of true sunrise/sunset (time_of_day ~0/1) and stays subtle even then.
        float sunset_t = pow(clamp(1.0 - abs(sin(time_of_day * 3.14159)) * 1.4, 0.0, 1.0), 2.0);
        vec3  sky_ref = mix(u_reflection_tint, vec3(1.0, 0.60, 0.28), sunset_t * 0.5);
        // Night sky: middle ground blue-black reflection
        sky_ref = mix(vec3(0.04, 0.075, 0.16), sky_ref, day_ratio);
        water_rgb = mix(water_rgb, sky_ref, fresnel);

        vec3 final_rgb = water_rgb + spec_broad + spec_tight + spec_sparkle;

        // --- Atmospheric Horizon Haze (SoT: rich blue-teal at all times) ---
        float hdist     = length(v_pos.xz - cam_pos.xz);
        float haze      = clamp((hdist - 300.0) / 650.0, 0.0, 1.0);
        haze            = pow(haze, 1.2);
        vec3 haze_day   = mix(ocean_color.rgb * 0.55, vec3(0.38, 0.58, 0.82), 0.55);
        // Night haze: visible dark blue, not near-black
        vec3 haze_night = mix(vec3(0.04, 0.09, 0.20), ocean_color.rgb * 0.25, 0.5);
        vec3 haze_color = mix(haze_night, haze_day, day_ratio);
        final_rgb = mix(final_rgb, haze_color, haze * 0.85);

        gl_FragColor = vec4(final_rgb, ocean_opacity);
    }
    """
    return ShaderProgram(v_src, f_src)

def create_ocean_shader_gerstner():
    # Legacy Gerstner Wave Shader (#version 120)
    v_src = """
    #version 120
    
    uniform float time;
    uniform float wave_speed;
    uniform float wave_scale;
    uniform float wave_steepness;
    uniform vec3 grid_origin;
    uniform float grid_chunk_size;
    uniform float time_of_day;
    
    varying vec3 v_normal;
    varying vec3 v_pos;
    varying float v_foam;
    varying vec3 v_view_dir;

    vec3 gerstner(vec3 pos, float wlen, float ampl, float speed, vec2 dir, float steep, float t, inout vec3 tangent, inout vec3 binormal) {
        float k = 2.0 * 3.14159 / wlen;
        float c = sqrt(9.81 / k);
        float phase = k * (dot(dir, pos.xz) - (c * speed * 2.0 * t));
        float a = ampl * wave_scale;
        float s = clamp(steep * wave_steepness * 2.0, 0.0, 1.0);
        
        vec3 d = vec3(0.0);
        d.x = dir.x * (a * s) * cos(phase);
        d.z = dir.y * (a * s) * cos(phase);
        d.y = a * sin(phase);
        
        float wa = k * a;
        tangent += vec3(-dir.x * dir.x * s * wa * sin(phase), dir.x * wa * cos(phase), -dir.x * dir.y * s * wa * sin(phase));
        binormal += vec3(-dir.x * dir.y * s * wa * sin(phase), dir.y * wa * cos(phase), -dir.y * dir.y * s * wa * sin(phase));
        return d;
    }

    void main() {
        vec3 world_p = (gl_Vertex.xyz * grid_chunk_size) + grid_origin;
        vec3 offset = vec3(0.0);
        vec3 tangent = vec3(1.0, 0.0, 0.0);
        vec3 binormal = vec3(0.0, 0.0, 1.0);

        offset += gerstner(world_p, 400.0, 10.0, 0.5, normalize(vec2(1.0, 0.1)), 0.6, time, tangent, binormal);
        offset += gerstner(world_p, 200.0, 6.0,  0.8, normalize(vec2(0.3, 0.9)), 0.7, time, tangent, binormal);

        vec3 displaced = gl_Vertex.xyz;
        displaced.x += offset.x / grid_chunk_size;
        displaced.z += offset.z / grid_chunk_size;
        displaced.y += offset.y;
        
        v_pos = world_p + offset;
        v_normal = normalize(cross(binormal, tangent));
        v_foam = pow(clamp(offset.y*0.1+0.5, 0.0, 1.0), 8.0);

        vec4 eye_pos = gl_ModelViewMatrix * vec4(displaced, 1.0);
        v_view_dir = normalize(-eye_pos.xyz);
        gl_Position = gl_ModelViewProjectionMatrix * vec4(displaced, 1.0);
    }
    """
    f_src = """
    #version 120
    uniform vec4 ocean_color;
    uniform float ocean_opacity;
    uniform float foam_amount;
    uniform float time_of_day;
    uniform vec3 cam_pos;
    varying vec3 v_normal;
    varying vec3 v_pos;
    varying float v_foam;
    varying vec3 v_view_dir;

    void main() {
        vec3 normal = normalize(v_normal);
        float ndotv = max(dot(normal, v_view_dir), 0.0);
        
        // --- Day/Night Lighting ---
        float day_ratio = max(sin(time_of_day * 3.14159), 0.0);
        vec3 base_water = mix(ocean_color.rgb*0.1, ocean_color.rgb, v_pos.y*0.05+0.5);
        base_water *= day_ratio; // Darken at night
        
        float fresnel = pow(1.0 - ndotv, 4.0);
        // Same fix as the FFT shader — narrow the orange contribution so dawn/dusk
        // doesn't paint every fresnel reflection brown.
        float sunset_t = pow(clamp(1.0 - abs(sin(time_of_day * 3.14159)) * 1.4, 0.0, 1.0), 2.0);
        vec3 sky_ref = mix(vec3(0.7, 0.8, 1.0), vec3(1.0, 0.5, 0.2), sunset_t * 0.5);
        sky_ref *= day_ratio;
        
        vec3 rgb = mix(base_water, sky_ref, fresnel*0.5);
        rgb = mix(rgb, vec3(1.0), v_foam * foam_amount * day_ratio);
        
        float dist = length(v_pos - cam_pos);
        float fog = clamp((dist-1000.0)/800.0, 0.0, 1.0);
        vec3 fog_color = mix(vec3(0.01), vec3(0.05, 0.08, 0.1), day_ratio);
        gl_FragColor = vec4(mix(rgb, fog_color, fog), ocean_opacity);
    }
    """
    return ShaderProgram(v_src, f_src)

def create_pbr_shader():
    v_src = """
    #version 330 compatibility
    layout(location = 0) in vec3 pos;
    layout(location = 2) in vec3 norm;
    layout(location = 8) in vec2 uv;
    
    uniform mat4 gl_ModelViewProjectionMatrix;
    uniform mat4 gl_ModelViewMatrix;
    uniform mat3 gl_NormalMatrix;
    uniform vec2 u_tiling;
    
    out vec3 v_world_pos;
    out vec3 v_normal;
    out vec2 v_uv;
    out mat3 v_tbn;

    void main() {
        v_world_pos = (gl_ModelViewMatrix * vec4(pos, 1.0)).xyz;
        v_normal = normalize(gl_NormalMatrix * norm);
        v_uv = uv * u_tiling;
        
        // Calculate TBN matrix for normal mapping
        vec3 tangent = normalize(gl_NormalMatrix * vec3(1.0, 0.0, 0.0));
        vec3 bitangent = cross(v_normal, tangent);
        v_tbn = mat3(tangent, bitangent, v_normal);
        
        gl_Position = gl_ModelViewProjectionMatrix * vec4(pos, 1.0);
    }
    """
    f_src = """
    #version 330 compatibility
    
    uniform sampler2D albedoMap;
    uniform sampler2D normalMap;
    uniform sampler2D metallicMap;
    uniform sampler2D roughnessMap;
    uniform sampler2D aoMap;
    
    uniform vec4 u_base_color;
    uniform float u_metallic;
    uniform float u_roughness;
    uniform vec3 sunDir;
    uniform vec3 cam_pos;
    
    uniform bool hasAlbedo;
    uniform bool hasNormal;
    uniform bool hasMetallic;
    uniform bool hasRoughness;
    uniform bool hasAO;

    in vec3 v_world_pos;
    in vec3 v_normal;
    in vec2 v_uv;
    in mat3 v_tbn;

    const float PI = 3.14159265359;

    // PBR Functions
    float DistributionGGX(vec3 N, vec3 H, float roughness) {
        float a = roughness*roughness;
        float a2 = a*a;
        float NdotH = max(dot(N, H), 0.0);
        float NdotH2 = NdotH*NdotH;
        float num = a2;
        float denom = (NdotH2 * (a2 - 1.0) + 1.0);
        denom = PI * denom * denom;
        return num / denom;
    }

    float GeometrySchlickGGX(float NdotV, float roughness) {
        float r = (roughness + 1.0);
        float k = (r*r) / 8.0;
        float num = NdotV;
        float denom = NdotV * (1.0 - k) + k;
        return num / denom;
    }

    float GeometrySmith(vec3 N, vec3 V, vec3 L, float roughness) {
        float NdotV = max(dot(N, V), 0.0);
        float NdotL = max(dot(N, L), 0.0);
        float ggx2 = GeometrySchlickGGX(NdotV, roughness);
        float ggx1 = GeometrySchlickGGX(NdotL, roughness);
        return ggx1 * ggx2;
    }

    vec3 fresnelSchlick(float cosTheta, vec3 F0) {
        return F0 + (1.0 - F0) * pow(clamp(1.0 - cosTheta, 0.0, 1.0), 5.0);
    }

    void main() {
        vec3 N = normalize(v_normal);
        if (hasNormal) {
            vec3 map_normal = texture(normalMap, v_uv).rgb * 2.0 - 1.0;
            N = normalize(v_tbn * map_normal);
        }
        
        vec3 V = normalize(cam_pos - v_world_pos);
        vec3 L = normalize(sunDir);
        vec3 H = normalize(V + L);

        vec3 albedo = hasAlbedo ? texture(albedoMap, v_uv).rgb * u_base_color.rgb : u_base_color.rgb;
        float metallic = hasMetallic ? texture(metallicMap, v_uv).r : u_metallic;
        float roughness = hasRoughness ? texture(roughnessMap, v_uv).r : u_roughness;
        float ao = hasAO ? texture(aoMap, v_uv).r : 1.0;

        vec3 F0 = vec3(0.04); 
        F0 = mix(F0, albedo, metallic);

        // Reflectance equation
        float NDF = DistributionGGX(N, H, roughness);   
        float G   = GeometrySmith(N, V, L, roughness);      
        vec3 F    = fresnelSchlick(max(dot(H, V), 0.0), F0);
           
        vec3 numerator    = NDF * G * F; 
        float denominator = 4.0 * max(dot(N, V), 0.0) * max(dot(N, L), 0.0) + 0.0001;
        vec3 specular = numerator / denominator;
        
        vec3 kS = F;
        vec3 kD = vec3(1.0) - kS;
        kD *= 1.0 - metallic;	  

        float NdotL = max(dot(N, L), 0.0);        

        vec3 ambient = vec3(0.03) * albedo * ao;
        vec3 radiance = vec3(2.5, 2.3, 2.1); // Direct sunlight radiance approx

        vec3 result = (kD * albedo / PI + specular) * radiance * NdotL;
        result += ambient;

        // Tone mapping & Gamma correction
        result = result / (result + vec3(1.0));
        result = pow(result, vec3(1.0/2.2));

        gl_FragColor = vec4(result, u_base_color.a);
    }
    """
    return ShaderProgram(v_src, f_src)

# --- Global Shader Registry & Cache ---
SHADER_REGISTRY = {
    "Standard": create_standard_shader,
    "Fish Swimming": create_fish_shader,
    "Flag Waving": create_flag_shader,
    "Ocean (FFT)": create_ocean_shader_fft,
    "Ocean (Gerstner)": create_ocean_shader_gerstner,
    "PBR Material": create_pbr_shader
}

_SHADER_CACHE = {}

def get_shader(name):
    """Retrieve a compiled shader from the cache or compile a new one."""
    if name in _SHADER_CACHE:
        return _SHADER_CACHE[name]
    
    print(f"[SHADER MANAGER] Initializing shader: {name}")
    if name in SHADER_REGISTRY:
        prog = SHADER_REGISTRY[name]()
    else:
        prog = create_standard_shader()
    
    _SHADER_CACHE[name] = prog
    return prog
