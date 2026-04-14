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
        
        // --- 1. Round SDF Starfield ---
        // Cellular noise with higher frequency for distant stars
        vec3 static_dir = dir * 400.0;
        vec3 cell = floor(static_dir);
        vec3 frac = fract(static_dir);
        
        float star_val = 0.0;
        vec3 star_rgb = vec3(0.0);
        
        for(float x=-1.; x<=1.; x++) {
            for(float y=-1.; y<=1.; y++) {
                for(float z=-1.; z<=1.; z++) {
                    vec3 neighbor = vec3(x, y, z);
                    vec3 p = cell + neighbor;
                    float h = hash(p);
                    
                    // Reduced base density for a more realistic feel
                    if (h > 1.0 - (0.0015 * star_density)) {
                        vec3 offset = vec3(hash(p+1.0), hash(p+2.0), hash(p+3.0));
                        vec3 pos = neighbor + offset;
                        float d = length(frac - pos);
                        
                        // Smaller, sharper stars for a vast look
                        float size = 0.02 + h * 0.06;
                        float s = smoothstep(size, size-0.02, d);
                        
                        vec3 col = vec3(1.0);
                        if (h > 0.9995) col = vec3(0.7, 0.8, 1.0);
                        else if (h < 0.9985) col = vec3(1.0, 0.9, 0.7);
                        
                        star_rgb += col * s * (h * 4.0);
                    }
                }
            }
        }
        
        // --- 2. Advanced Nebulae ---
        float n1 = noise(dir * 3.0);
        float n2 = noise(dir * 6.0 + n1);
        float neb_v = smoothstep(0.4, 0.8, n2 * 1.3) * nebula_intensity;
        
        vec3 neb_color_1 = vec3(0.05, 0.02, 0.1);
        vec3 neb_color_2 = vec3(0.01, 0.05, 0.04);
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
