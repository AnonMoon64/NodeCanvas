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
    
    float hash(vec2 p) {
        return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453123);
    }
    
    float noise(vec2 p) {
        vec2 i = floor(p); vec2 f = fract(p);
        vec2 u = f*f*(3.0-2.0*f);
        return mix(mix(hash(i + vec2(0,0)), hash(i + vec2(1,0)), u.x),
                   mix(hash(i + vec2(0,1)), hash(i + vec2(1,1)), u.x), u.y);
    }
    
    float fbm(vec2 p) {
        float f = 0.0;
        f += 0.5000 * noise(p); p *= 2.02;
        f += 0.2500 * noise(p); p *= 2.03;
        f += 0.1250 * noise(p); p *= 2.01;
        f += 0.0625 * noise(p);
        return f;
    }
    
    void main() {
        vec2 uv = v_world_pos.xz * 0.0001; // Tiled world coordinates
        uv += time_of_day * 0.05; // Wind movement
        
        float density = fbm(uv);
        density = smoothstep(0.4, 0.8, density * cloud_density);
        
        // --- Lighting ---
        float sol_angle = (time_of_day - 0.5) * 6.28318;
        float day_ratio = clamp(cos(sol_angle) * 2.0 + 0.5, 0.0, 1.0);
        float sunset_val = clamp(1.0 - abs(cos(sol_angle)), 0.0, 1.0);
        
        vec3 day_color = vec3(1.0);
        vec3 sunset_color = vec3(1.0, 0.5, 0.3);
        vec3 night_color = vec3(0.05, 0.05, 0.1);
        
        vec3 cloud_rgb = mix(day_color, sunset_color, sunset_val);
        cloud_rgb = mix(night_color, cloud_rgb, day_ratio);
        
        // --- Distance Fading ---
        float dist = length(v_world_pos - cam_pos);
        float fade = 1.0 - smoothstep(10000.0, 20000.0, dist);
        
        // Fly-through fade (transparent when camera is inside/close to layer)
        float h_diff = abs(cam_pos.y - v_world_pos.y);
        float h_fade = smoothstep(0.0, 500.0, h_diff);
        
        gl_FragColor = vec4(cloud_rgb, density * fade * h_fade);
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
