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
    
    in vec3 v_pos;
    
    float hash(vec3 p) {
        return fract(sin(dot(p, vec3(127.1, 311.7, 74.7))) * 43758.5453123);
    }
    
    void main() {
        vec3 dir = normalize(v_pos);
        
        // Starfield
        float stars = pow(hash(floor(dir * 200.0)), 50.0) * 2.0;
        stars += pow(hash(floor(dir * 500.0)), 100.0) * 5.0;
        
        // Nebula noise (very simple)
        float neb = hash(floor(dir * 5.0)) * 0.1;
        vec3 neb_color = vec3(0.1, 0.05, 0.2) * neb;
        
        vec3 final_color = vec3(stars) + neb_color;
        
        gl_FragColor = vec4(final_color, 1.0);
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
    
    glPushMatrix()
    glTranslatef(camera_pos[0], camera_pos[1], camera_pos[2])
    glScalef(4800, 4800, 4800) # Slightly larger than atmosphere
    
    if _universe_sphere is None:
        _universe_sphere = gluNewQuadric()
    gluSphere(_universe_sphere, 1.0, 24, 24)
    
    glPopMatrix()
    _universe_shader.stop()
    
    glEnable(GL_DEPTH_TEST)
    glEnable(GL_LIGHTING)
    glCullFace(GL_BACK)
