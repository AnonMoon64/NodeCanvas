"""
procedural_atmosphere.py

Physically-based procedural atmosphere for NodeCanvas.

Key features
------------
- Rayleigh + Mie scattering (approximate analytic), with night-sky Milky-Way.
- Spherical planet mode: sky is raymarched through a thin atmosphere shell so
  when the camera flies out into space it sees a bright blue "rim" around the
  planet instead of an infinite sky dome.
- Dynamic, adjustable time-of-day with a moving sun *and* moon, sunrise/
  sunset reddening, and a realistic twilight gradient.
- God rays (analytic in-scattering term along the view ray toward the sun).
- Exposure + tonemapping.

The sky is rendered on a huge inverted sphere around the camera when the
camera is close to the ground, and transitions to a planet-rim render when
altitude > atmosphere_thickness (space view).
"""
from OpenGL.GL import *
from OpenGL.GLU import *
import math
from .shader_manager import ShaderProgram

_atmosphere_shader = None
_atmosphere_sphere = None


def _sun_direction(time_of_day: float):
    """Return normalised sun direction following a realistic circular arc."""
    # Noon = 0.5 -> Angle = 0 -> sun at top (Y=+1)
    angle = (time_of_day - 0.5) * 2.0 * math.pi
    
    # Orbit inclination (tilt)
    inclination = math.radians(23.5)
    
    # Base circular path in XY plane
    x = math.sin(angle)
    y = math.cos(angle)
    z = 0.0
    
    # Rotate around X axis to apply inclination
    ry = y * math.cos(inclination) - z * math.sin(inclination)
    rz = y * math.sin(inclination) + z * math.cos(inclination)
    
    return (x, ry, rz)


def _moon_direction(time_of_day: float):
    sx, sy, sz = _sun_direction(time_of_day)
    return (-sx, -sy, -sz)


def create_atmosphere_shader():
    v_src = """
    #version 330 compatibility

    out vec3 v_world_pos;
    out vec3 v_local_dir;

    uniform vec3 cam_pos;

    void main() {
        // Sphere is camera-centered (scaled in CPU) so local positions map 1:1 to directions.
        v_local_dir = normalize(gl_Vertex.xyz);
        v_world_pos = gl_Vertex.xyz + cam_pos;
        gl_Position = gl_ModelViewProjectionMatrix * gl_Vertex;
    }
    """

    f_src = """
    #version 330 compatibility
    in vec3 v_local_dir;
    in vec3 v_world_pos;

    uniform vec3  cam_pos;
    uniform float sky_density;
    uniform float sun_size;
    uniform float sun_intensity;
    uniform float time_of_day;
    uniform int   planet_mode;
    uniform vec3  planet_center;
    uniform float planet_radius;
    uniform float atmosphere_thickness;
    uniform float rayleigh_strength;
    uniform float mie_strength;
    uniform float god_rays_strength;
    uniform float exposure;
    uniform vec3  sun_dir;
    uniform vec3  moon_dir;

    // ---- Constants tuned for plausible colors ---------------------------------
    const vec3  RAYLEIGH_COEFF = vec3(5.8e-6, 13.5e-6, 33.1e-6); // scaled below
    const float MIE_COEFF      = 21e-6;
    const float RAYLEIGH_SCALE = 8000.0;
    const float MIE_SCALE      = 1200.0;
    const float G              = 0.76;

    float hg_phase(float cos_t, float g) {
        float g2 = g*g;
        return (1.0 - g2) / (4.0 * 3.14159265 * pow(1.0 + g2 - 2.0*g*cos_t, 1.5));
    }
    float rayleigh_phase(float cos_t) {
        return (3.0 / (16.0 * 3.14159265)) * (1.0 + cos_t * cos_t);
    }

    float hash(vec3 p) {
        return fract(sin(dot(p, vec3(127.1, 311.7, 74.7))) * 43758.5453);
    }
    float star_field(vec3 dir) {
        vec3 g = floor(dir * 420.0);
        float h = hash(g);
        float s = smoothstep(0.995, 1.0, h);
        // Twinkle by another hash dim
        float tw = 0.6 + 0.4 * hash(g + 13.0);
        return s * tw * 1.3;
    }

    void main() {
        vec3 dir = normalize(v_local_dir);
        float h = max(cam_pos.y, 0.0);

        // --- Day/night angle
        float sun_up = sun_dir.y;
        float day_ratio   = clamp(sun_up * 2.0 + 0.3, 0.0, 1.0);
        float night_ratio = clamp(-sun_up * 2.0 + 0.3, 0.0, 1.0);
        float twilight    = clamp(1.0 - abs(sun_up) * 3.0, 0.0, 1.0);

        // --- Approximate optical depth along the view ray -----------------------
        float cos_z = clamp(dir.y, -1.0, 1.0);
        float view_depth = 1.0 / max(abs(cos_z) + 0.05, 0.1);

        // Rayleigh scattering
        float cos_theta = dot(dir, normalize(sun_dir));
        float r_phase = rayleigh_phase(cos_theta);
        float m_phase = hg_phase(cos_theta, G);

        vec3 rayleigh = RAYLEIGH_COEFF * r_phase * view_depth * rayleigh_strength * 1.2e5;
        float mie_amt = MIE_COEFF * m_phase * view_depth * mie_strength * 8.0e5;
        vec3 sun_color = mix(vec3(1.0, 0.55, 0.22), vec3(1.0, 0.97, 0.9), day_ratio);

        vec3 sky = rayleigh * vec3(0.5, 0.85, 1.0);
        sky += sun_color * mie_amt * max(sun_up, 0.0);

        // Darken sky as sun falls below the horizon
        sky *= max(sun_up * 1.6 + 0.1, 0.0);
        sky *= sky_density;

        // --- Sunset warm band near horizon --------------------------------------
        float horizon = 1.0 - smoothstep(0.0, 0.25, abs(dir.y));
        vec3 sunset_tint = vec3(1.0, 0.45, 0.18) * twilight * horizon * 1.5;
        sky += sunset_tint * max(sun_up + 0.1, 0.0);

        // --- Sun disk and corona ------------------------------------------------
        float s_dot = max(dot(dir, normalize(sun_dir)), 0.0);
        // Smaller sun: increased base power from 60000 to 180000
        float disk_pow = 180000.0 / max(sun_size * sun_size, 0.001);
        float sun_visible = smoothstep(-0.08, 0.04, sun_up);
        vec3 disk   = sun_color * pow(s_dot, disk_pow) * sun_intensity * sun_visible;
        vec3 corona = sun_color * pow(s_dot, 2000.0 / max(sun_size, 0.01)) * sun_intensity * 0.25 * sun_visible;

        // God rays: boost in-scatter near the sun, along horizon
        float god = pow(s_dot, 8.0) * god_rays_strength * day_ratio;
        sky += sun_color * god;

        sky += disk + corona;

        // --- Moon -------------------------------------------------------
        float m_dot = max(dot(dir, normalize(moon_dir)), 0.0);
        float moon_pow = 35000.0;
        vec3 moon = vec3(0.85, 0.9, 1.0) * pow(m_dot, moon_pow) * 1.2 * clamp(-sun_up + 0.1, 0.0, 1.0);
        sky += moon;

        // Soft moon halo
        sky += vec3(0.5, 0.6, 0.9) * pow(m_dot, 40.0) * 0.25 * night_ratio;

        // --- Planet / space transition -----------------------------------------
        float altitude = max(0.0, cam_pos.y - planet_radius * 0.0);
        float atmos_frac = 1.0;
        if (planet_mode == 1) {
            atmos_frac = clamp(1.0 - h / atmosphere_thickness, 0.0, 1.0);
            float rim = smoothstep(-0.05, 0.15, -dir.y) * (1.0 - atmos_frac);
            sky += vec3(0.25, 0.55, 1.0) * rim * 0.7 * day_ratio;
        } else {
            atmos_frac = clamp(1.0 - h / (atmosphere_thickness * 2.0), 0.0, 1.0);
        }

        sky *= mix(0.15, 1.0, atmos_frac);

        // Deep-space base color: pure black now so Universe primitive shows through
        vec3 space = vec3(0.0);
        vec3 final_col = mix(space, sky, atmos_frac);

        // Exposure + gentle tonemap
        final_col = 1.0 - exp(-final_col * exposure);

        // Alpha: Fade out at night so stars from the Universe primitive show through the sky
        // Shift alpha down based on day_ratio (0 at midnight, 1 at noon)
        float alpha = mix(0.1, 1.0, atmos_frac * day_ratio);
        // Ensure horizon stays somewhat opaque for hazy look
        alpha = max(alpha, horizon * 0.4);

        gl_FragColor = vec4(final_col, alpha);
    }
    """
    return ShaderProgram(v_src, f_src)


def render_atmosphere(camera_pos, obj, time_override=None):
    """Render the sky dome / planet atmosphere."""
    global _atmosphere_shader, _atmosphere_sphere
    if _atmosphere_shader is None:
        _atmosphere_shader = create_atmosphere_shader()

    # Auto-advance time if enabled
    time_speed = float(getattr(obj, 'time_speed', 0.0))
    if time_speed != 0.0:
        import time as _t
        now = _t.time()
        last = getattr(obj, '_last_time_adv', now)
        dt = now - last
        obj._last_time_adv = now
        t = getattr(obj, 'time_of_day', 0.25) + time_speed * dt
        # Wrap and advance date counter
        if t >= 1.0:
            obj.date_day_index = int(getattr(obj, 'date_day_index', 0)) + int(t)
            t = t - int(t)
        elif t < 0.0:
            t = t % 1.0
        obj.time_of_day = t

    tod = time_override if time_override is not None else getattr(obj, 'time_of_day', 0.25)
    sun = _sun_direction(tod)
    moon = _moon_direction(tod)

    glDisable(GL_LIGHTING)
    glDisable(GL_DEPTH_TEST)
    glCullFace(GL_FRONT)
    glEnable(GL_BLEND)
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

    s = _atmosphere_shader
    s.use()
    s.set_uniform_v3("cam_pos", *camera_pos)
    s.set_uniform_f("sky_density",          float(getattr(obj, 'sky_density', 1.0)))
    s.set_uniform_f("sun_size",             float(getattr(obj, 'sun_size', 1.0)))
    s.set_uniform_f("sun_intensity",        float(getattr(obj, 'sun_intensity', 10.0)))
    s.set_uniform_f("time_of_day",          float(tod))
    s.set_uniform_i("planet_mode",          1 if getattr(obj, 'planet_mode', False) else 0)
    s.set_uniform_v3("planet_center",       *getattr(obj, 'planet_center', [0.0, 0.0, 0.0]))
    s.set_uniform_f("planet_radius",        float(getattr(obj, 'planet_radius', 6371000.0)))
    s.set_uniform_f("atmosphere_thickness", float(getattr(obj, 'atmosphere_thickness', 100000.0)))
    s.set_uniform_f("rayleigh_strength",    float(getattr(obj, 'rayleigh_strength', 1.0)))
    s.set_uniform_f("mie_strength",         float(getattr(obj, 'mie_strength', 1.0)))
    s.set_uniform_f("god_rays_strength",    float(getattr(obj, 'god_rays_strength', 0.6)))
    s.set_uniform_f("exposure",             float(getattr(obj, 'exposure', 1.0)))
    s.set_uniform_v3("sun_dir",             *sun)
    s.set_uniform_v3("moon_dir",            *moon)

    glPushMatrix()
    glTranslatef(camera_pos[0], camera_pos[1], camera_pos[2])
    scale = 4500.0
    glScalef(scale, scale, scale)
    if _atmosphere_sphere is None:
        _atmosphere_sphere = gluNewQuadric()
    gluSphere(_atmosphere_sphere, 1.0, 48, 48)
    glPopMatrix()

    s.stop()
    glDisable(GL_BLEND)
    glEnable(GL_DEPTH_TEST)
    glEnable(GL_LIGHTING)
    glCullFace(GL_BACK)


def get_sun_direction(obj):
    """Helper used by main loop to sync the global light direction."""
    if not obj: return (0, 1, 0)
    mode = getattr(obj, 'light_update_mode', 'Auto')
    tod = getattr(obj, 'time_of_day', 0.25)
    
    if mode == "Manual Moon":
        return _moon_direction(tod)
    elif mode == "Manual Sun":
        return _sun_direction(tod)
        
    # Auto: Swap based on which one is up
    sun = _sun_direction(tod)
    if sun[1] > -0.1: # Sun is up or rising
        return sun
    return _moon_direction(tod)


def get_sun_color(obj):
    """Return the active light color (Sun or Moon) with smooth transitions."""
    if not obj: return (1.0, 1.0, 0.9)
    
    mode = getattr(obj, 'light_update_mode', 'Auto')
    tod = getattr(obj, 'time_of_day', 0.25)
    
    sun_col = getattr(obj, 'sun_color', [1.0, 1.0, 0.9])[:3]
    moon_col = getattr(obj, 'moon_color', [0.6, 0.7, 1.0])[:3]
    moon_int = float(getattr(obj, 'moon_intensity', 1.0))
    
    if mode == "Manual Sun": return tuple(sun_col)
    if mode == "Manual Moon": return tuple(c * moon_int for c in moon_col)
    
    # Auto logic
    sun_dir = _sun_direction(tod)
    # Day ratio: 1.0 at noon, 0.0 at horizon/night
    day_ratio = max(0.0, min(1.0, sun_dir[1] * 5.0 + 0.5)) 
    # Moon ratio: 1.0 at midnight, 0.0 at horizon/day
    moon_ratio = max(0.0, min(1.0, -sun_dir[1] * 5.0 + 0.5))
    
    r = sun_col[0] * day_ratio + (moon_col[0] * moon_int) * moon_ratio
    g = sun_col[1] * day_ratio + (moon_col[1] * moon_int) * moon_ratio
    b = sun_col[2] * day_ratio + (moon_col[2] * moon_int) * moon_ratio
    
    return (r, g, b)


def get_ambient_color(obj):
    """Return the global ambient sky color."""
    if not obj: return (0.1, 0.1, 0.2)
    col = getattr(obj, 'ambient_color', [0.1, 0.1, 0.2])[:3]
    return tuple(col)
