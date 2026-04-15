"""
procedural_ocean_world.py

Renders a animated spherical ocean on a round planet surface.
Uses a GLSL sphere with animated wave normals and Fresnel shading.
"""
from OpenGL.GL import *
from OpenGL.GLU import *
import math
from .shader_manager import ShaderProgram

_ocean_world_shader = None
_ocean_world_quad = None


def _create_ocean_world_shader():
    v_src = """
    #version 330 compatibility
    out vec3 v_world;
    out vec3 v_norm;
    void main() {
        v_world = gl_Vertex.xyz;
        v_norm  = normalize(gl_Vertex.xyz);
        gl_Position = gl_ModelViewProjectionMatrix * gl_Vertex;
    }
    """
    f_src = """
    #version 330 compatibility
    uniform vec3  cam_pos;
    uniform vec3  planet_center;
    uniform float time;
    uniform float wave_intensity;
    uniform float wave_speed;
    uniform vec4  ocean_color;
    uniform float sun_angle;

    in vec3 v_world;
    in vec3 v_norm;

    // Fast hash + noise
    float hash(float n) { return fract(sin(n) * 43758.5453); }
    float noise3(vec3 p) {
        vec3 i = floor(p); vec3 f = fract(p);
        f = f * f * (3.0 - 2.0 * f);
        float n = i.x + i.y * 57.0 + i.z * 113.0;
        return mix(mix(mix(hash(n),       hash(n+1.0),    f.x),
                       mix(hash(n+57.0),  hash(n+58.0),   f.x), f.y),
                   mix(mix(hash(n+113.0), hash(n+114.0),  f.x),
                       mix(hash(n+170.0), hash(n+171.0),  f.x), f.y), f.z);
    }
    float fbm(vec3 p) {
        float v = 0.0; float a = 0.5;
        for (int i = 0; i < 5; i++) { v += a * noise3(p); p *= 2.1; a *= 0.48; }
        return v;
    }

    void main() {
        vec3 dir = normalize(v_norm);
        float t = time * wave_speed;

        // Animated wave normals on sphere surface
        float wave = fbm(dir * 6.0 + vec3(t * 0.3, t * 0.2, t * 0.15)) - 0.5;
        vec3 perturbed = normalize(dir + wave * wave_intensity * 0.4);

        // Sun
        vec3 sun_dir = normalize(vec3(sin(sun_angle), cos(sun_angle), 0.2));
        vec3 view_dir = normalize(cam_pos - v_world);
        vec3 half_dir = normalize(sun_dir + view_dir);

        // Diffuse
        float NdotL = max(dot(perturbed, sun_dir), 0.0);
        float diffuse = NdotL * 0.6 + 0.2;

        // Specular
        float spec = pow(max(dot(perturbed, half_dir), 0.0), 64.0);

        // Fresnel rim
        float fresnel = pow(1.0 - max(dot(dir, view_dir), 0.0), 4.0) * 0.6;

        // Foam (where wave peaks are high)
        float foam = smoothstep(0.3, 0.5, wave + 0.5) * NdotL * 0.4;

        vec3 water = ocean_color.rgb * diffuse + vec3(1.0) * spec * 0.8 + vec3(fresnel);
        water = mix(water, vec3(1.0), foam);

        float alpha = ocean_color.a;
        gl_FragColor = vec4(water, alpha);
    }
    """
    return ShaderProgram(v_src, f_src)


def render_ocean_world(camera_pos, obj, elapsed_time):
    """Render a spherical ocean centered on obj.position with obj.voxel_radius * ocean_world_radius."""
    global _ocean_world_shader

    if _ocean_world_shader is None:
        _ocean_world_shader = _create_ocean_world_shader()

    radius = float(getattr(obj, 'voxel_radius', 0.5)) * float(getattr(obj, 'ocean_world_radius', 0.48))
    wave_speed     = float(getattr(obj, 'ocean_world_wave_speed', 3.0))
    wave_intensity = float(getattr(obj, 'ocean_world_wave_intensity', 0.015))
    color          = list(getattr(obj, 'ocean_world_color', [0.05, 0.25, 0.6, 0.85]))
    pos            = obj.position

    time_of_day = getattr(obj, 'time_of_day', 0.25)
    sun_angle = (time_of_day - 0.5) * 6.28318

    glEnable(GL_BLEND)
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
    glDisable(GL_CULL_FACE)

    _ocean_world_shader.use()
    _ocean_world_shader.set_uniform_v3("cam_pos", *camera_pos)
    _ocean_world_shader.set_uniform_v3("planet_center", *pos)
    _ocean_world_shader.set_uniform_f("time",           elapsed_time)
    _ocean_world_shader.set_uniform_f("wave_speed",     wave_speed)
    _ocean_world_shader.set_uniform_f("wave_intensity", wave_intensity)
    _ocean_world_shader.set_uniform_f("sun_angle",      sun_angle)
    _ocean_world_shader.set_uniform_v4("ocean_color",   *color)

    glPushMatrix()
    glTranslatef(*pos)
    glScalef(radius, radius, radius)

    q = gluNewQuadric()
    gluSphere(q, 1.0, 48, 48)
    gluDeleteQuadric(q)

    glPopMatrix()
    _ocean_world_shader.stop()

    glEnable(GL_CULL_FACE)
    glDisable(GL_BLEND)
