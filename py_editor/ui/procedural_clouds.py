from OpenGL.GL import *
from OpenGL.GLU import *
import math
import time
from .shader_manager import ShaderProgram

_cloud_shader = None
_cloud_vbo = None

def create_cloud_shader():
    v_src = """
    #version 330 compatibility
    
    uniform vec3 grid_origin;
    uniform float cloud_height;
    uniform float cloud_size;
    
    out vec3 v_world_pos;
    out vec2 v_uv;
    
    void main() {
        // Create a large world-space plane
        vec3 world_pos = vec3(gl_Vertex.x * cloud_size, cloud_height, gl_Vertex.z * cloud_size) + grid_origin;
        v_world_pos = world_pos;
        v_uv = gl_Vertex.xz * 0.5 + 0.5;
        
        gl_Position = gl_ModelViewProjectionMatrix * vec4(world_pos, 1.0);
    }
    """
    
    f_src = """
    #version 330 compatibility

    uniform vec3 cam_pos;
    uniform float time_of_day;
    uniform float cloud_density;

    in vec3 v_world_pos;
    in vec2 v_uv;

    // ---- Noise helpers ----
    float hash21(vec2 p) {
        p = fract(p * vec2(127.1, 311.7));
        p += dot(p, p + 19.19);
        return fract(p.x * p.y);
    }
    float hash31(vec3 p) {
        p = fract(p * vec3(127.1, 311.7, 74.7));
        p += dot(p, p + 19.19);
        return fract(p.x * p.y + p.z);
    }
    float noise2(vec2 p) {
        vec2 i = floor(p); vec2 f = fract(p);
        vec2 u = f * f * (3.0 - 2.0 * f);
        return mix(mix(hash21(i + vec2(0,0)), hash21(i + vec2(1,0)), u.x),
                   mix(hash21(i + vec2(0,1)), hash21(i + vec2(1,1)), u.x), u.y);
    }
    // Multi-octave fBm with warp for more realistic clumping
    float fbm(vec2 p) {
        float v = 0.0, a = 0.5;
        vec2 shift = vec2(100.0);
        for (int i = 0; i < 6; i++) {
            v += a * noise2(p);
            p  = p * 2.1 + shift;
            a *= 0.5;
        }
        return v;
    }
    // Domain-warped cloud: gives lumpy, cumulus-like shapes
    float cloud_shape(vec2 p) {
        // First pass: large structure
        vec2 q = vec2(fbm(p), fbm(p + vec2(1.7, 9.2)));
        // Second pass: detail warped by q
        vec2 r = vec2(fbm(p + 1.0 * q + vec2(1.7, 9.2)),
                      fbm(p + 1.0 * q + vec2(8.3, 2.8)));
        return fbm(p + 1.0 * r);
    }

    void main() {
        float sol_angle  = (time_of_day - 0.5) * 6.28318;
        float day_ratio  = clamp(cos(sol_angle) * 2.0 + 0.5, 0.0, 1.0);
        float sunset_val = clamp(1.0 - abs(cos(sol_angle)), 0.0, 1.0);

        // Slow wind drift
        float wind_speed = 0.012;
        vec2 uv = v_world_pos.xz * 0.000045;
        uv += vec2(time_of_day * wind_speed, time_of_day * wind_speed * 0.4);

        float shape = cloud_shape(uv);
        // Sharpen: remap to get distinct cloud/clear-sky boundary
        float threshold = mix(0.52, 0.42, cloud_density);
        float raw = smoothstep(threshold, threshold + 0.18, shape);

        // Soften edges with a second fbm for wispy details
        float detail = fbm(uv * 3.0 + vec2(42.1, 7.3));
        raw = clamp(raw + (detail - 0.5) * 0.12, 0.0, 1.0);

        // ---- Lighting ----
        // Top-lit: brighter on top, darker base (fake self-shadowing)
        float self_shadow = clamp(1.0 - shape * 0.6, 0.0, 1.0);

        vec3 day_top    = vec3(1.0, 1.0, 1.0);
        vec3 day_base   = vec3(0.72, 0.75, 0.82);
        vec3 sunset_top = vec3(1.0, 0.65, 0.35);
        vec3 sunset_base= vec3(0.6,  0.3,  0.2);
        vec3 night_col  = vec3(0.08, 0.08, 0.15);

        vec3 cloud_top  = mix(day_top,  sunset_top,  sunset_val);
        vec3 cloud_base = mix(day_base, sunset_base, sunset_val);
        vec3 cloud_rgb  = mix(cloud_base, cloud_top, self_shadow);
        cloud_rgb = mix(night_col, cloud_rgb, day_ratio);

        // ---- Fading ----
        float dist     = length(v_world_pos - cam_pos);
        float dist_fade = 1.0 - smoothstep(12000.0, 22000.0, dist);
        float h_diff   = abs(cam_pos.y - v_world_pos.y);
        float h_fade   = smoothstep(0.0, 600.0, h_diff);

        gl_FragColor = vec4(cloud_rgb, raw * dist_fade * h_fade);
    }
    """
    return ShaderProgram(v_src, f_src)

def render_clouds(camera_pos, obj, time_of_day=0.25):
    global _cloud_shader, _cloud_vbo
    
    if _cloud_shader is None:
        _cloud_shader = create_cloud_shader()
    
    density = getattr(obj, 'cloud_density', 0.5)
    height = getattr(obj, 'cloud_height', 4000.0)
    
    glEnable(GL_BLEND)
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
    glDisable(GL_LIGHTING)
    
    # We want clouds to be visible from both sides for flying above/below
    glDisable(GL_CULL_FACE)
    
    _cloud_shader.use()
    
    # Snap grid origin to camera for infinite appearance
    snap = 1000.0
    follow_x = (camera_pos[0] // snap) * snap
    follow_z = (camera_pos[2] // snap) * snap
    
    _cloud_shader.set_uniform_v3("grid_origin", follow_x, 0, follow_z)
    _cloud_shader.set_uniform_v3("cam_pos", *camera_pos)
    _cloud_shader.set_uniform_f("cloud_height", height)
    _cloud_shader.set_uniform_f("cloud_size", 40000.0) # Massive plane
    _cloud_shader.set_uniform_f("time_of_day", time_of_day)
    _cloud_shader.set_uniform_f("cloud_density", density)
    
    # Draw a simple unit quad and scale in shader
    glBegin(GL_QUADS)
    glVertex3f(-1, 0, -1)
    glVertex3f(1, 0, -1)
    glVertex3f(1, 0, 1)
    glVertex3f(-1, 0, 1)
    glEnd()
    
    _cloud_shader.stop()
    glEnable(GL_CULL_FACE)
    glDisable(GL_BLEND)
    glEnable(GL_LIGHTING)
