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
    uniform float sun_size;
    uniform float sun_intensity;
    uniform float time_of_day; // 0.0 to 1.0 (0.5 is noon)
    
    in vec3 v_pos;
    in vec3 v_view_dir;
    
    void main() {
        vec3 dir = normalize(v_pos);
        float h = cam_pos.y;
        
        // --- Day/Night Dynamics (0.5 is Noon, 0.0/1.0 is Midnight) ---
        float sol_angle = (time_of_day - 0.5) * 6.28318;
        float day_ratio = clamp(cos(sol_angle) * 2.0 + 0.5, 0.0, 1.0);
        float night_factor = clamp(-cos(sol_angle) * 2.0 + 0.5, 0.0, 1.0);
        
        // Sun direction
        vec3 sun_dir = normalize(vec3(sin(sol_angle), cos(sol_angle), 0.2));
        
        // --- 1. Zenith-based Sky Grading ---
        float zenith = max(dir.y, 0.0);
        vec3 day_zenith = vec3(0.1, 0.4, 0.9) * sky_density;
        vec3 day_horizon = vec3(0.6, 0.8, 1.0) * sky_density;
        vec3 sunset_horizon = vec3(1.0, 0.4, 0.2) * sky_density;
        
        float sunset_val = clamp(1.0 - abs(cos(sol_angle)), 0.0, 1.0);
        vec3 horizon_color = mix(day_horizon, sunset_horizon, sunset_val);
        vec3 sky_rgb = mix(horizon_color, day_zenith, zenith);
        
        // --- 2. Sun & Mie Scattering (Halo) ---
        float sun_dot = max(dot(dir, sun_dir), 0.0);
        float sun_visible = smoothstep(-0.05, 0.05, sun_dir.y);

        // Realistic sun disk: ~0.5 degree angular diameter.
        // disk_pow=60000 at sun_size=1 matches real-world angular size.
        // User can make it larger (sun_size>1) or smaller (sun_size<1).
        float disk_pow = 60000.0 / max(sun_size * sun_size, 0.001);
        vec3 sun_color = mix(vec3(1.0, 0.85, 0.5), vec3(1.0, 1.0, 0.95), day_ratio);
        vec3 sun_disk = sun_color * pow(sun_dot, disk_pow) * sun_intensity * sun_visible;

        // Inner corona glow
        float corona_pow = 800.0 / max(sun_size, 0.01);
        vec3 sun_corona = sun_color * pow(sun_dot, corona_pow) * sun_intensity * 0.3 * sun_visible;

        // Mie scattering halo (wide glow around sun position)
        float mie_pow = max(4.0 / max(sun_size, 0.1), 1.0);
        vec3 sun_halo = mix(horizon_color, vec3(1.0, 0.9, 0.7), 0.5)
                        * pow(sun_dot, mie_pow) * 1.8 * day_ratio * sun_visible;
        sky_rgb += sun_disk + sun_corona + sun_halo;

        // --- 3. Planetary Transition ---
        float atmosphere_fade = clamp(1.0 - (h / 6500.0), 0.0, 1.0);
        sky_rgb *= atmosphere_fade;
        
        float alpha = mix(1.0, 0.0, night_factor * 0.98); 
        alpha *= atmosphere_fade; 

        gl_FragColor = vec4(sky_rgb, alpha);
    }
    """
    return ShaderProgram(v_src, f_src)

def render_atmosphere(camera_pos, obj, time=0.0):
    global _atmosphere_shader, _atmosphere_sphere
    
    if _atmosphere_shader is None:
        _atmosphere_shader = create_atmosphere_shader()
        
    glDisable(GL_LIGHTING)
    glDisable(GL_DEPTH_TEST)
    glCullFace(GL_FRONT) 
    
    glEnable(GL_BLEND)
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
    
    _atmosphere_shader.use()
    _atmosphere_shader.set_uniform_v3("cam_pos", camera_pos[0], camera_pos[1], camera_pos[2])
    _atmosphere_shader.set_uniform_f("sky_density", getattr(obj, 'sky_density', 1.0))
    _atmosphere_shader.set_uniform_f("sun_size", getattr(obj, 'sun_size', 1.0))
    _atmosphere_shader.set_uniform_f("sun_intensity", getattr(obj, 'sun_intensity', 10.0))
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
    
    glDisable(GL_BLEND)
    glEnable(GL_DEPTH_TEST)
    glEnable(GL_LIGHTING)
    glCullFace(GL_BACK)
