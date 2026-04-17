"""
procedural_clouds.py

Volumetric, raymarched 3D clouds for NodeCanvas.

Implementation notes
--------------------
- Rendered as a full-screen-aligned quad (relative to the camera) large
  enough to cover the sky dome.
- Each fragment casts a short ray through a spherical shell of
  [cloud_layer_bottom, cloud_layer_top] meters.
- Density field is a worley + fBm combo with a coverage remap. The wind
  vector animates the base field; detail noise adds wispy edges.
- Lighting samples a few steps toward the sun for self-shadowing.
- The sun direction / color is taken from the Atmosphere primitive.
"""
from OpenGL.GL import *
from OpenGL.GLU import *
import math
from .shader_manager import ShaderProgram
from .procedural_atmosphere import _sun_direction

_cloud_shader = None


def create_cloud_shader():
    v_src = """
    #version 330 compatibility
    uniform vec3 cam_pos;
    uniform float sky_size;

    out vec3 v_dir;

    void main() {
        // Build a camera-centered inverted sphere — fragments give us ray dirs.
        vec3 p = gl_Vertex.xyz * sky_size + cam_pos;
        v_dir = normalize(gl_Vertex.xyz);
        gl_Position = gl_ModelViewProjectionMatrix * vec4(p, 1.0);
    }
    """

    f_src = """
    #version 330 compatibility
    in vec3 v_dir;

    uniform vec3 cam_pos;
    uniform vec3 sun_dir;
    uniform vec3 sun_color;
    uniform float time_of_day;
    uniform float cloud_coverage;
    uniform float cloud_absorption;
    uniform float cloud_anvil;
    uniform vec3  cloud_wind;
    uniform float layer_bottom;
    uniform float layer_top;
    uniform int   cloud_steps;
    uniform float elapsed;

    float hash3(vec3 p) {
        p = fract(p * vec3(127.1, 311.7, 74.7));
        p += dot(p, p + 19.19);
        return fract(p.x * p.y * p.z);
    }
    float noise3(vec3 p) {
        vec3 i = floor(p); vec3 f = fract(p);
        f = f*f*(3.0 - 2.0*f);
        float n000 = hash3(i);
        float n100 = hash3(i + vec3(1,0,0));
        float n010 = hash3(i + vec3(0,1,0));
        float n110 = hash3(i + vec3(1,1,0));
        float n001 = hash3(i + vec3(0,0,1));
        float n101 = hash3(i + vec3(1,0,1));
        float n011 = hash3(i + vec3(0,1,1));
        float n111 = hash3(i + vec3(1,1,1));
        return mix(mix(mix(n000, n100, f.x), mix(n010, n110, f.x), f.y),
                   mix(mix(n001, n101, f.x), mix(n011, n111, f.x), f.y), f.z);
    }
    float fbm3(vec3 p) {
        float v = 0.0, a = 0.5;
        for (int i = 0; i < 5; ++i) { v += a * noise3(p); p *= 2.03; a *= 0.5; }
        return v;
    }

    // Signed distance to a horizontal slab
    float slab(float y) {
        float t = smoothstep(layer_bottom, layer_bottom + 80.0, y)
                * (1.0 - smoothstep(layer_top - 120.0, layer_top, y));
        return t;
    }

    float cloud_density(vec3 p) {
        float height_frac = clamp((p.y - layer_bottom) / max(layer_top - layer_bottom, 1.0), 0.0, 1.0);

        // Advection by wind (mostly horizontal)
        vec3 pw = p + cloud_wind * elapsed;

        // Base shape
        vec3 q = pw * 0.00025;
        float base = fbm3(q);
        base = base * 1.5 - 0.2;

        // Detail
        float detail = fbm3(pw * 0.001 + vec3(12.0));
        base -= detail * 0.2 * (1.0 - height_frac);

        // Coverage remap
        float cov = cloud_coverage;
        float d = smoothstep(1.0 - cov, 1.0 - cov + 0.18, base);

        // Anvil flattening at top — wider at upper height
        float anvil = mix(1.0, 1.0 + cloud_anvil * height_frac, smoothstep(0.5, 1.0, height_frac));
        d *= anvil;

        // Slab mask keeps clouds in the layer
        d *= slab(p.y);

        return clamp(d, 0.0, 1.0);
    }

    // Henyey-Greenstein phase function
    float hg(float c, float g) {
        float g2 = g*g;
        return (1.0 - g2) / (4.0 * 3.14159265 * pow(1.0 + g2 - 2.0 * g * c, 1.5));
    }

    // Short shadow march toward the sun
    float light_march(vec3 p, vec3 ld) {
        float T = 1.0;
        float step = (layer_top - layer_bottom) * 0.12;
        for (int i = 0; i < 5; ++i) {
            p += ld * step;
            float d = cloud_density(p);
            T *= exp(-d * step * 0.0015 * cloud_absorption);
            if (T < 0.02) break;
        }
        return T;
    }

    void main() {
        vec3 ro = cam_pos;
        vec3 rd = normalize(v_dir);

        // Find the two intersections with the slab layer
        float tB = (layer_bottom - ro.y) / max(abs(rd.y), 1e-3) * sign(rd.y);
        float tT = (layer_top    - ro.y) / max(abs(rd.y), 1e-3) * sign(rd.y);
        float t_near = min(tB, tT);
        float t_far  = max(tB, tT);
        if (t_far < 0.0) { gl_FragColor = vec4(0.0); return; }
        t_near = max(t_near, 0.0);

        // Clamp so we don't march forever toward horizon
        t_far = min(t_far, t_near + 22000.0);

        float length_t = max(t_far - t_near, 0.0);
        int steps = max(cloud_steps, 8);
        float dt = length_t / float(steps);
        if (dt <= 0.0) { gl_FragColor = vec4(0.0); return; }

        vec3 pos = ro + rd * (t_near + dt * 0.5);

        vec3 ld = normalize(sun_dir);
        float cos_t = dot(rd, ld);
        float phase = mix(hg(cos_t, 0.2), hg(cos_t, 0.85), 0.5);

        vec3 accum = vec3(0.0);
        float trans = 1.0;

        for (int i = 0; i < 128; ++i) {
            if (i >= steps) break;
            float d = cloud_density(pos);
            if (d > 0.001) {
                float T_light = light_march(pos, ld);
                vec3 sun_energy = sun_color * (T_light * phase * 6.0);
                // Ambient from sky above & darker below
                float h = clamp((pos.y - layer_bottom) / max(layer_top - layer_bottom, 1.0), 0.0, 1.0);
                vec3 amb = mix(vec3(0.12, 0.14, 0.22), vec3(0.7, 0.8, 1.0), h);
                vec3 L = sun_energy + amb;

                float absorb = d * dt * 0.0012 * cloud_absorption;
                float T_step = exp(-absorb);
                accum += trans * (1.0 - T_step) * L;
                trans *= T_step;
                if (trans < 0.02) break;
            }
            pos += rd * dt;
        }

        // Ground fog when camera is below clouds and looking down
        float alpha = 1.0 - trans;
        // Horizon fade
        float horizon_fade = smoothstep(-0.2, 0.05, rd.y);
        alpha *= horizon_fade;

        // Color grade for night
        float day = clamp(ld.y * 2.0 + 0.3, 0.0, 1.0);
        accum = mix(accum * vec3(0.25, 0.28, 0.45), accum, day);

        gl_FragColor = vec4(accum, alpha);
    }
    """
    return ShaderProgram(v_src, f_src)


_cloud_sphere = None


def render_clouds(camera_pos, obj, time_of_day=0.25):
    global _cloud_shader, _cloud_sphere
    if _cloud_shader is None:
        _cloud_shader = create_cloud_shader()
    if _cloud_sphere is None:
        _cloud_sphere = gluNewQuadric()

    import time as _t
    elapsed = _t.time() % 100000.0

    # Sun direction from the atmosphere object if present on `obj`
    sun = _sun_direction(time_of_day)
    # Sun color
    day = max(0.0, min(1.0, sun[1] * 2.0 + 0.3))
    twi = max(0.0, min(1.0, 1.0 - abs(sun[1]) * 3.0))
    sun_color = (1.0 * (day + twi), 0.97 * day + 0.55 * twi, 0.9 * day + 0.22 * twi)

    layer_bottom = float(getattr(obj, 'cloud_layer_bottom', 900.0))
    layer_top    = float(getattr(obj, 'cloud_layer_top', 2200.0))
    coverage     = float(getattr(obj, 'cloud_coverage', getattr(obj, 'cloud_density', 0.5)))
    absorption   = float(getattr(obj, 'cloud_absorption', 0.8))
    anvil        = float(getattr(obj, 'cloud_anvil', 0.3))
    wind         = getattr(obj, 'cloud_wind', [6.0, 0.0, 2.0])
    steps        = int(getattr(obj, 'cloud_steps', 48))

    glEnable(GL_BLEND)
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
    glDisable(GL_LIGHTING)
    glDepthMask(GL_FALSE)
    glDisable(GL_CULL_FACE)

    s = _cloud_shader
    s.use()
    s.set_uniform_v3("cam_pos", *camera_pos)
    s.set_uniform_v3("sun_dir", *sun)
    s.set_uniform_v3("sun_color", *sun_color)
    s.set_uniform_f("time_of_day", float(time_of_day))
    s.set_uniform_f("cloud_coverage", coverage)
    s.set_uniform_f("cloud_absorption", absorption)
    s.set_uniform_f("cloud_anvil", anvil)
    s.set_uniform_v3("cloud_wind", *wind)
    s.set_uniform_f("layer_bottom", layer_bottom)
    s.set_uniform_f("layer_top", layer_top)
    s.set_uniform_i("cloud_steps", steps)
    s.set_uniform_f("sky_size", 4000.0)
    s.set_uniform_f("elapsed", elapsed)

    glPushMatrix()
    glTranslatef(camera_pos[0], camera_pos[1], camera_pos[2])
    glScalef(4000.0, 4000.0, 4000.0)
    glCullFace(GL_FRONT)
    gluSphere(_cloud_sphere, 1.0, 32, 32)
    glCullFace(GL_BACK)
    glPopMatrix()

    s.stop()
    glDepthMask(GL_TRUE)
    glEnable(GL_CULL_FACE)
    glDisable(GL_BLEND)
    glEnable(GL_LIGHTING)
