"""
shader_manager.py

A robust utility for managing GLSL shaders and GPU programs.
This allows moving procedural logic (like Gerstner waves) from the CPU to the GPU.
"""
from OpenGL.GL import *
from OpenGL.GL.shaders import compileProgram, compileShader
import numpy as np

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

    def set_uniform_matrix4(self, name, mat):
        loc = glGetUniformLocation(self.program, name)
        if loc != -1:
            glUniformMatrix4fv(loc, 1, GL_FALSE, mat)

def create_ocean_shader_fft():
    # VERTEX SHADER: Displacement & UV Pass with scaling
    v_src = """
    #version 330 compatibility
    
    uniform sampler2D u_displacement_map;
    uniform vec3 grid_origin;
    uniform float grid_chunk_size;
    uniform float u_wave_scale;
    uniform float u_choppiness;
    
    out vec3 v_pos;
    out float v_height;
    out vec3 v_view_dir;
    out vec2 v_uv;

    void main() {
        vec3 world_p = (gl_Vertex.xyz * grid_chunk_size) + grid_origin;
        v_uv = (world_p.xz / 1000.0) * u_wave_scale;
        
        vec3 disp = texture(u_displacement_map, v_uv).rgb;
        v_height = disp.y;
        
        // Apply Choppiness to horizontal displacement
        vec3 local_disp = disp;
        local_disp.xz *= u_choppiness; 
        local_disp.xz /= grid_chunk_size;
        
        vec3 displaced_v = gl_Vertex.xyz + local_disp;
        v_pos = world_p + disp;
        
        vec4 eye_pos = gl_ModelViewMatrix * vec4(displaced_v, 1.0);
        v_view_dir = normalize(-eye_pos.xyz);
        
        gl_Position = gl_ModelViewProjectionMatrix * vec4(displaced_v, 1.0);
    }
    """

    # FRAGMENT SHADER: High-detail per-pixel normals & Advanced Bubbly Foam
    f_src = """
    #version 330 compatibility
    
    uniform vec4 ocean_color;
    uniform float ocean_opacity;
    uniform float foam_amount;
    uniform float time;
    uniform vec3 cam_pos;
    uniform sampler2D u_displacement_map;
    uniform sampler2D u_jacobian_map;
    uniform float u_wave_scale;
    uniform float time_of_day;
    
    // Advanced Visuals
    uniform float u_fresnel_strength;
    uniform float u_specular_intensity;
    uniform vec3 u_reflection_tint;
    
    in vec3 v_pos;
    in float v_height;
    in vec3 v_view_dir;
    in vec2 v_uv;

    // Fast procedural bubble noise for advanced foam
    float bubble_noise(vec2 p) {
        vec2 i = floor(p);
        vec2 f = fract(p);
        float a = sin(dot(i, vec2(12.9898, 78.233)) * 43758.5453);
        float b = sin(dot(i + vec2(1.0, 0.0), vec2(12.9898, 78.233)) * 43758.5453);
        float c = sin(dot(i + vec2(0.0, 1.0), vec2(12.9898, 78.233)) * 43758.5453);
        float d = sin(dot(i + vec2(1.0, 1.0), vec2(12.9898, 78.233)) * 43758.5453);
        vec2 u = f*f*(3.0-2.0*f);
        return mix(a, b, u.x) + (c - a)*u.y*(1.0-u.x) + (d - b)*u.x*u.y;
    }

    void main() {
        // High-precision per-pixel normals using resolution-aware sampling
        float d = 1.0 / 128.0; // Matches FFT_SIZE
        float hL = texture(u_displacement_map, v_uv - vec2(d, 0)).y;
        float hR = texture(u_displacement_map, v_uv + vec2(d, 0)).y;
        float hD = texture(u_displacement_map, v_uv - vec2(0, d)).y;
        float hU = texture(u_displacement_map, v_uv + vec2(0, d)).y;
        
        vec3 normal = normalize(vec3(hL - hR, 0.12, hD - hU)); // Tighter ridge definition
        vec3 view_dir = normalize(v_view_dir);
        
        // --- Day/Night Lighting ---
        vec3 sun_dir = normalize(vec3(sin(time_of_day * 6.28), cos(time_of_day * 6.28), 0.2));
        vec3 light_dir = sun_dir;
        float day_ratio = max(sin(time_of_day * 3.14159), 0.0);
        
        // Deep Drama water color (High Contrast)
        float h_norm = clamp(v_height * 0.12 + 0.45, 0.0, 1.0);
        vec3 color_deep = ocean_color.rgb * 0.02;
        vec3 color_shallow = ocean_color.rgb * 1.4;
        vec3 water_rgb = mix(color_deep, color_shallow, h_norm);
        
        // Advanced Foam System
        float jacobian = texture(u_jacobian_map, v_uv).r;
        float jac_mask = clamp(1.0 - jacobian, 0.0, 1.0);
        
        // Smoother procedural bubbles for foam detail
        float bubbles = sin(v_pos.x * 4.0 + time) * cos(v_pos.z * 4.0 - time * 0.5) * 0.5 + 0.5;
        bubbles *= sin(v_pos.x * 20.0 - time * 2.0) * 0.3 + 0.7;
        bubbles = smoothstep(0.5, 0.9, bubbles * jac_mask);
        
        float foam_mask = pow(jac_mask, 3.5) * foam_amount * 4.0;
        foam_mask = clamp(foam_mask + bubbles * foam_amount * 2.0, 0.0, 1.0);
        
        vec3 foam_rgb = vec3(0.9, 0.95, 1.0);
        water_rgb = mix(water_rgb, foam_rgb, foam_mask);
        
        // Sub-Surface Scattering (SSS) - The teal ridge glow from the old version
        float sss = pow(max(dot(view_dir, -light_dir), 0.0), 4.0) * max(v_height * 0.2, 0.0);
        water_rgb += vec3(0.1, 0.7, 0.6) * sss;
        
        // Dual-Layer Specular
        vec3 half_v = normalize(light_dir + view_dir + vec3(1e-5));
        float spec_broad = pow(max(dot(normal, half_v), 0.0), 128.0) * 0.5 * u_specular_intensity;
        float spec_sparkle = pow(max(dot(normal, half_v), 0.0), 4096.0) * 10.0 * u_specular_intensity; // Facet sparkle
        
        // Fresnel Reflection (Configurable)
        float fresnel = pow(1.0 - max(dot(normal, view_dir), 0.0), 5.0) * u_fresnel_strength;
        
        // Dynamic Reflection Tint
        vec3 day_tint = u_reflection_tint;
        vec3 sunset_tint = vec3(1.0, 0.5, 0.3);
        vec3 sky_ref = mix(day_tint, sunset_tint, clamp(1.0 - abs(sin(time_of_day * 3.14159)), 0.0, 1.0));
        sky_ref *= day_ratio; // Darken at night
        
        water_rgb = mix(water_rgb, sky_ref, fresnel); 
        
        vec3 final_rgb = water_rgb + spec_broad + spec_sparkle;
        
        // Distance Fog - Darker to match the old abyss
        float dist = length(v_pos - cam_pos);
        float fog = clamp((dist - 3000.0) / 2000.0, 0.0, 1.0);
        final_rgb = mix(final_rgb, vec3(0.02, 0.04, 0.05), fog);
        
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
        vec3 sky_ref = mix(vec3(0.7, 0.8, 1.0), vec3(1.0, 0.5, 0.2), clamp(1.0 - day_ratio, 0.0, 1.0));
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
