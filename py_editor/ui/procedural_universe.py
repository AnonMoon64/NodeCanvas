"""
procedural_universe.py

A procedural universe background with starfields and nebulae.
Designed to be visible through the atmosphere or in deep space.
"""
from OpenGL.GL import *
from OpenGL.GLU import *
import math
from .shader_manager import ShaderProgram

_universe_shader = None
_universe_sphere = None

def create_universe_shader():
    v_src = """
    #version 330 compatibility
    
    out vec3 v_pos;
    
    void main() {
        v_pos = gl_Vertex.xyz;
        gl_Position = gl_ModelViewProjectionMatrix * gl_Vertex;
    }
    """
    
    f_src = """
    #version 330 compatibility
    
    uniform float star_density;
    uniform float nebula_intensity;
    
    in vec3 v_pos;
    
    // Hash for star placements
    float hash(vec3 p) {
        return fract(sin(dot(p, vec3(127.1, 311.7, 74.7))) * 43758.5453123);
    }
    
    float noise(vec3 p) {
        vec3 i = floor(p); vec3 f = fract(p);
        f = f*f*(3.0-2.0*f);
        return mix(mix(mix(hash(i+vec3(0,0,0)), hash(i+vec3(1,0,0)), f.x),
                       mix(hash(i+vec3(0,1,0)), hash(i+vec3(1,1,0)), f.x), f.y),
                   mix(mix(hash(i+vec3(0,0,1)), hash(i+vec3(1,0,1)), f.x),
                       mix(hash(i+vec3(0,1,1)), hash(i+vec3(1,1,1)), f.x), f.y), f.z);
    }
    
    void main() {
        vec3 dir = normalize(v_pos);
        
        // --- 1. Starfield (Using the optimized hash-cell method) ---
        vec3 g = floor(dir * 450.0);
        float h = hash(g);
        float star_v = 0.0;
        
        // Sharper, varied stars
        if (h > 0.994) {
            float size = 0.6 + 0.4 * hash(g + 13.0);
            float twinkle = 0.7 + 0.3 * sin(hash(g) * 100.0);
            star_v = size * twinkle * star_density;
        }
        
        vec3 star_rgb = vec3(star_v);
        // Add some subtle color variation to stars
        float c_h = hash(g + 71.0);
        if (c_h > 0.7) star_rgb *= vec3(0.8, 0.9, 1.1);
        else if (c_h < 0.3) star_rgb *= vec3(1.1, 0.9, 0.7);

        // --- 2. Advanced Nebulae ---
        float n1 = noise(dir * 2.5);
        float n2 = noise(dir * 5.0 + n1 * 0.5);
        float neb_v = pow(smoothstep(0.35, 0.85, n2 * 1.25), 2.0) * nebula_intensity;
        
        vec3 neb_color_1 = vec3(0.06, 0.02, 0.12); // Deep Purple
        vec3 neb_color_2 = vec3(0.01, 0.06, 0.05); // Cosmic Teal
        vec3 nebula = mix(neb_color_1, neb_color_2, n1) * neb_v;
        
        vec3 final_rgb = star_rgb + nebula;
        gl_FragColor = vec4(final_rgb, 1.0);
    }
    """
    return ShaderProgram(v_src, f_src)

def render_universe(camera_pos, obj):
    global _universe_shader, _universe_sphere
    
    if _universe_shader is None:
        _universe_shader = create_universe_shader()
        
    glDisable(GL_LIGHTING)
    glDisable(GL_DEPTH_TEST)
    glCullFace(GL_FRONT)
    
    _universe_shader.use()
    _universe_shader.set_uniform_f("star_density", getattr(obj, "star_density", 1.0))
    _universe_shader.set_uniform_f("nebula_intensity", getattr(obj, "nebula_intensity", 0.5))
    
    glPushMatrix()
    glTranslatef(camera_pos[0], camera_pos[1], camera_pos[2])
    glScalef(4800, 4800, 4800) # Slightly larger than atmosphere
    
    if _universe_sphere is None:
        _universe_sphere = gluNewQuadric()
    
    # Render with much higher resolution (128x128)
    gluSphere(_universe_sphere, 1.0, 128, 128)
    
    glPopMatrix()
    _universe_shader.stop()
    
    glEnable(GL_DEPTH_TEST)
    glEnable(GL_LIGHTING)
    glCullFace(GL_BACK)
