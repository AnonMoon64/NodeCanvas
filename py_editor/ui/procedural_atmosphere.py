"""
procedural_atmosphere.py

A high-fidelity procedural atmosphere primitive for NodeCanvas.
Handles land-to-space transitions, scattering, and cloud layers.
"""
from OpenGL.GL import *
from OpenGL.GLU import *
import math
import time
from .shader_manager import ShaderProgram

_atmosphere_shader = None
_atmosphere_sphere = None

def create_atmosphere_shader():
    v_src = """
    #version 330 compatibility
    
    out vec3 v_pos;
    out vec3 v_view_dir;
    
    void main() {
        v_pos = gl_Vertex.xyz;
        vec4 eye_pos = gl_ModelViewMatrix * gl_Vertex;
        v_view_dir = normalize(-eye_pos.xyz);
        gl_Position = gl_ModelViewProjectionMatrix * gl_Vertex;
    }
    """
    
    f_src = """
    #version 330 compatibility
    
    uniform vec3 cam_pos;
    uniform float sky_density;
    uniform float cloud_density;
    uniform float time_of_day; // 0.0 to 1.0 (0.5 is noon)
    
    in vec3 v_pos;
    in vec3 v_view_dir;
    
    // Simple hash for clouds
    float hash(vec2 p) {
        return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453123);
    }
    
    float noise(vec2 p) {
        vec2 i = floor(p);
        vec2 f = fract(p);
        vec2 u = f*f*(3.0-2.0*f);
        return mix(mix(hash(i + vec2(0,0)), hash(i + vec2(1,0)), u.x),
                   mix(hash(i + vec2(0,1)), hash(i + vec2(1,1)), u.x), u.y);
    }
    
    void main() {
        vec3 dir = normalize(v_pos);
        float h = cam_pos.y;
        
        // Rayleigh Scattering approximation
        vec3 sun_dir = normalize(vec3(sin(time_of_day * 6.28), cos(time_of_day * 6.28), 0.2));
        float sun_limit = max(dot(dir, sun_dir), 0.0);
        
        // Altitude transition (Blue -> Black)
        float alt_factor = clamp((h - 500.0) / 2000.0, 0.0, 1.0);
        vec3 sky_color = mix(vec3(0.3, 0.6, 1.0), vec3(0.01, 0.02, 0.05), alt_factor);
        
        // Sun Glow
        vec3 sun_glow = vec3(1.0, 0.9, 0.7) * pow(sun_limit, 100.0) * 2.0;
        sky_color += sun_glow * (1.0 - alt_factor);
        
        // Atmospheric haze near horizon
        float horizon = 1.0 - max(dir.y, 0.0);
        sky_color = mix(sky_color, vec3(0.7, 0.8, 0.9), pow(horizon, 8.0) * 0.5 * (1.0 - alt_factor));
        
        // Procedural Clouds
        float cloud_val = noise(dir.xz * 10.0 / (dir.y + 0.1) + time_of_day * 0.1);
        cloud_val += noise(dir.xz * 25.0 / (dir.y + 0.1)) * 0.5;
        float clouds = smoothstep(0.5, 0.8, cloud_val * cloud_density * max(dir.y, 0.0));
        
        sky_color = mix(sky_color, vec3(1.0), clouds * (1.0 - alt_factor));
        
        gl_FragColor = vec4(sky_color, 1.0);
    }
    """
    return ShaderProgram(v_src, f_src)

def render_atmosphere(camera_pos, obj, time=0.0):
    global _atmosphere_shader, _atmosphere_sphere
    
    if _atmosphere_shader is None:
        _atmosphere_shader = create_atmosphere_shader()
        
    glDisable(GL_LIGHTING)
    glDisable(GL_DEPTH_TEST)
    glCullFace(GL_FRONT) # Show inside of sphere
    
    _atmosphere_shader.use()
    _atmosphere_shader.set_uniform_v3("cam_pos", camera_pos[0], camera_pos[1], camera_pos[2])
    _atmosphere_shader.set_uniform_f("sky_density", getattr(obj, 'sky_density', 1.0))
    _atmosphere_shader.set_uniform_f("cloud_density", getattr(obj, 'cloud_density', 0.5))
    _atmosphere_shader.set_uniform_f("time_of_day", getattr(obj, 'time_of_day', 0.25))
    
    # Large inverted sphere
    glPushMatrix()
    glTranslatef(camera_pos[0], camera_pos[1], camera_pos[2])
    glScalef(4500, 4500, 4500)
    
    # Drawing simple GLU sphere for the sky
    if _atmosphere_sphere is None:
        _atmosphere_sphere = gluNewQuadric()
    gluSphere(_atmosphere_sphere, 1.0, 32, 32)
    
    glPopMatrix()
    _atmosphere_shader.stop()
    
    glEnable(GL_DEPTH_TEST)
    glEnable(GL_LIGHTING)
    glCullFace(GL_BACK)
