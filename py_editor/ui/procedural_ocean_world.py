"""
procedural_ocean_world.py

Renders a animated spherical ocean on a round planet surface.
Uses a GLSL sphere with animated wave normals and Fresnel shading.
"""
from OpenGL.GL import *
from OpenGL.GLU import *
import math
import numpy as np
from .shader_manager import ShaderProgram

_ocean_world_shader = None       # procedural (fbm) shader
_ocean_world_fft_shader = None   # Tessendorf / FFT shader
_ocean_world_sphere_mesh = None  # (vbo, ibo, index_count, vertex_count)
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
    uniform float rain_intensity;

    in vec3 v_world;
    in vec3 v_norm;

    // Fast hash + noise
    float hash(float n) { return fract(sin(n) * 43758.5453); }
    float hash2(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
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
        for (int i = 0; i < 6; i++) { v += a * noise3(p); p *= 2.07; a *= 0.5; }
        return v;
    }

    // Perturbation field derivative via finite diff, gives us smooth wave normals.
    vec3 wave_normal(vec3 dir, float t, float amp) {
        float e = 0.015;
        // Build an orthonormal basis on the sphere for finite-diff.
        vec3 up = abs(dir.y) < 0.95 ? vec3(0,1,0) : vec3(1,0,0);
        vec3 tx = normalize(cross(up, dir));
        vec3 tz = cross(dir, tx);
        vec3 offs = vec3(t*0.3, t*0.2, t*0.15);
        float c  = fbm(dir * 6.0 + offs)
                 + 0.5 * fbm(dir * 14.0 + offs * 1.3)
                 + 0.25 * fbm(dir * 32.0 + offs * 1.7);
        float hx = fbm((dir + tx*e) * 6.0 + offs)
                 + 0.5 * fbm((dir + tx*e) * 14.0 + offs * 1.3)
                 + 0.25 * fbm((dir + tx*e) * 32.0 + offs * 1.7);
        float hz = fbm((dir + tz*e) * 6.0 + offs)
                 + 0.5 * fbm((dir + tz*e) * 14.0 + offs * 1.3)
                 + 0.25 * fbm((dir + tz*e) * 32.0 + offs * 1.7);
        vec3 n = dir - amp * ((hx - c) / e * tx + (hz - c) / e * tz);
        return normalize(n);
    }

    // Rain ripples: sum of expanding rings on the surface.
    float rain_ripples(vec3 dir, float t) {
        float r = 0.0;
        // Sample ripples anchored in a 2D tangent plane (parametrized by yaw/pitch).
        float u = atan(dir.z, dir.x);
        float v = asin(clamp(dir.y, -1.0, 1.0));
        vec2 uv = vec2(u, v) * 28.0;
        for (int i = 0; i < 4; i++) {
            vec2 cell = floor(uv) + float(i) * 13.0;
            vec2 f    = fract(uv) - 0.5;
            float seed = hash2(cell);
            // Time-offset so each cell pulses independently.
            float phase = fract(t * 1.2 + seed);
            float d = length(f);
            // Expanding ring centered on cell, fading as it grows.
            float ring = exp(-pow((d - phase * 0.5) * 22.0, 2.0)) * (1.0 - phase);
            r += ring;
            uv = uv * 1.6 + 3.1;
        }
        return r;
    }

    void main() {
        vec3 dir = normalize(v_norm);
        float t = time * wave_speed;

        // Layered wave normal (includes detail)
        vec3 perturbed = wave_normal(dir, t, wave_intensity * 0.6);

        // Rain ripples perturb the normal further
        if (rain_intensity > 0.001) {
            float e = 0.01;
            vec3 up = abs(dir.y) < 0.95 ? vec3(0,1,0) : vec3(1,0,0);
            vec3 tx = normalize(cross(up, dir));
            vec3 tz = cross(dir, tx);
            float rc = rain_ripples(dir, t);
            float rx = rain_ripples(normalize(dir + tx*e), t);
            float rz = rain_ripples(normalize(dir + tz*e), t);
            float amp = 0.12 * clamp(rain_intensity, 0.0, 2.0);
            perturbed = normalize(perturbed - amp * ((rx - rc) / e * tx + (rz - rc) / e * tz));
        }

        // Sun
        vec3 sun_dir = normalize(vec3(sin(sun_angle), cos(sun_angle), 0.2));
        vec3 view_dir = normalize(cam_pos - v_world);
        vec3 half_dir = normalize(sun_dir + view_dir);

        // Diffuse with deep-water tint
        float NdotL = max(dot(perturbed, sun_dir), 0.0);
        float diffuse = NdotL * 0.6 + 0.25;

        // Specular (narrow & wide lobes) for sun glitter
        float spec_narrow = pow(max(dot(perturbed, half_dir), 0.0), 180.0) * 1.4;
        float spec_wide   = pow(max(dot(perturbed, half_dir), 0.0), 24.0)  * 0.35;
        float spec = spec_narrow + spec_wide;

        // Fresnel + rim
        float VdotN = max(dot(dir, view_dir), 0.0);
        float fresnel = pow(1.0 - VdotN, 5.0);

        // Reflection sky tint for grazing angles
        vec3 sky_tint = mix(vec3(0.55, 0.72, 0.95), vec3(1.0, 0.85, 0.65), clamp(sun_dir.y * 0.5 + 0.5, 0.0, 1.0));

        // Foam (crests + a little high-freq detail)
        float crest = fbm(dir * 6.0 + vec3(t*0.3, t*0.2, t*0.15)) - 0.5;
        float foam = smoothstep(0.32, 0.55, crest + 0.5) * (NdotL * 0.4 + 0.15);
        foam += smoothstep(0.55, 1.0, fbm(dir * 70.0 + vec3(t*0.4))) * 0.15;

        // Subsurface scattering hint at wave peaks
        float sss = max(0.0, crest) * max(0.0, dot(dir, sun_dir)) * 0.35;

        // Deep / shallow tint by crest
        vec3 deep    = ocean_color.rgb * 0.7;
        vec3 shallow = ocean_color.rgb * 1.25 + vec3(0.02, 0.05, 0.07);
        vec3 base    = mix(deep, shallow, clamp(crest + 0.5, 0.0, 1.0));

        vec3 water = base * diffuse
                   + sky_tint * fresnel * 0.8
                   + vec3(1.0) * spec
                   + ocean_color.rgb * sss;
        water = mix(water, vec3(1.0), clamp(foam, 0.0, 1.0));

        float alpha = ocean_color.a;
        gl_FragColor = vec4(water, alpha);
    }
    """
    return ShaderProgram(v_src, f_src)


def _create_ocean_world_fft_shader():
    """Tessendorf/FFT ocean wrapped around a sphere via triplanar displacement."""
    v_src = """
    #version 330 compatibility
    uniform vec3  cam_pos;
    uniform vec3  planet_center;
    uniform float planet_radius;
    uniform float u_wave_scale;      // world units per FFT tile (cascade 0)
    uniform float u_wave_scale_c1;
    uniform float u_wave_scale_c2;
    uniform float u_choppiness;
    uniform float u_cascade1_weight;
    uniform float u_cascade2_weight;

    uniform sampler2D u_displacement_map;
    uniform sampler2D u_displacement_c1;
    uniform sampler2D u_displacement_c2;

    out vec3 v_world;
    out vec3 v_dir;
    out vec2 v_uv0;
    out vec2 v_uv1;
    out vec2 v_uv2;
    out vec3 v_tri_weights;

    // Sample displacement (xyz: world-space xyz displacement, y is height)
    vec3 sampleDisp(vec2 uv, sampler2D tex, float chop) {
        vec4 d = texture(tex, uv);
        return vec3(d.x * chop, d.y, d.z * chop);
    }

    void main() {
        vec3 sphere_n = normalize(gl_Vertex.xyz);
        vec3 w_pos    = planet_center + sphere_n * planet_radius;

        // Triplanar UVs in world space (per-cascade tile sizes)
        vec2 uv_xz0 = w_pos.xz / u_wave_scale;
        vec2 uv_xy0 = w_pos.xy / u_wave_scale;
        vec2 uv_yz0 = w_pos.yz / u_wave_scale;

        vec2 uv_xz1 = w_pos.xz / u_wave_scale_c1;
        vec2 uv_xz2 = w_pos.xz / u_wave_scale_c2;

        // Blend weights: how much each projection contributes based on sphere normal.
        vec3 an = abs(sphere_n);
        an = pow(an, vec3(4.0));
        an /= (an.x + an.y + an.z + 1e-5);

        // Cascade-0 triplanar displacement
        vec3 d_xz = sampleDisp(uv_xz0, u_displacement_map, u_choppiness);
        vec3 d_xy = sampleDisp(uv_xy0, u_displacement_map, u_choppiness);
        vec3 d_yz = sampleDisp(uv_yz0, u_displacement_map, u_choppiness);
        // Each projection uses its own "up": XZ projects vertical onto Y; XY onto Z; YZ onto X.
        vec3 disp0 = an.y * vec3(d_xz.x, d_xz.y, d_xz.z)
                   + an.z * vec3(d_xy.x, d_xy.z, d_xy.y)
                   + an.x * vec3(d_yz.z, d_yz.x, d_yz.y);

        // Cascade 1 & 2 only from XZ projection — subtle extra chop
        vec3 d1 = sampleDisp(uv_xz1, u_displacement_c1, u_choppiness) * u_cascade1_weight;
        vec3 d2 = sampleDisp(uv_xz2, u_displacement_c2, u_choppiness) * u_cascade2_weight;
        disp0 += an.y * (vec3(d1.x, d1.y, d1.z) + vec3(d2.x, d2.y, d2.z));

        // Displace outward along normal (scalar height) + a bit of tangential choppiness
        float height = dot(disp0, sphere_n) * 0.3 + length(disp0) * 0.02;
        vec3 disp_world = sphere_n * height + (disp0 - sphere_n * dot(disp0, sphere_n)) * 0.05;

        vec3 out_world = w_pos + disp_world;
        gl_Position = gl_ModelViewProjectionMatrix * vec4(out_world, 1.0);

        v_world = out_world;
        v_dir = sphere_n;
        v_uv0 = uv_xz0;
        v_uv1 = uv_xz1;
        v_uv2 = uv_xz2;
        v_tri_weights = an;
    }
    """
    f_src = """
    #version 330 compatibility
    uniform vec3  cam_pos;
    uniform float time;
    uniform float sun_angle;
    uniform vec4  ocean_color;
    uniform float rain_intensity;
    uniform float u_fresnel_strength;
    uniform float u_specular_intensity;
    uniform float u_peak_brightness;
    uniform float u_sss_strength;

    uniform sampler2D u_jacobian_map;
    uniform sampler2D u_jacobian_c1;
    uniform sampler2D u_jacobian_c2;
    uniform sampler2D u_displacement_map;

    in vec3 v_world;
    in vec3 v_dir;
    in vec2 v_uv0;
    in vec2 v_uv1;
    in vec2 v_uv2;
    in vec3 v_tri_weights;

    float hash2(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }

    void main() {
        // Reconstruct normal from displacement derivatives (finite diff along XZ projection)
        float e = 0.005;
        float hC = texture(u_displacement_map, v_uv0).y;
        float hR = texture(u_displacement_map, v_uv0 + vec2(e, 0.0)).y;
        float hU = texture(u_displacement_map, v_uv0 + vec2(0.0, e)).y;
        float dx = hR - hC;
        float dz = hU - hC;
        // Transform (dx,dz) onto the local sphere tangent frame
        vec3 up = abs(v_dir.y) < 0.95 ? vec3(0,1,0) : vec3(1,0,0);
        vec3 tx = normalize(cross(up, v_dir));
        vec3 tz = cross(v_dir, tx);
        vec3 n = normalize(v_dir - 3.0 * (dx * tx + dz * tz));

        // Rain ripple perturbation
        if (rain_intensity > 0.001) {
            vec2 ruv = v_uv0 * 40.0;
            float rh = 0.0, rdx = 0.0, rdz = 0.0;
            for (int i = 0; i < 3; i++) {
                vec2 cell = floor(ruv);
                vec2 f    = fract(ruv) - 0.5;
                float s = hash2(cell + float(i)*7.3);
                vec2 jitter = vec2(hash2(cell + 1.7), hash2(cell + 4.1)) - 0.5;
                vec2 p = f - jitter * 0.6;
                float phase = fract(time * 1.5 + s);
                float gate = step(1.0 - clamp(rain_intensity, 0.0, 1.0), s);
                float r = phase * 0.45;
                float d = length(p);
                rh  += exp(-pow((d - r) * 22.0, 2.0)) * (1.0 - phase) * gate;
                float pl = length(p - vec2(0.02, 0.0));
                float pr = length(p + vec2(0.02, 0.0));
                float pd = length(p - vec2(0.0, 0.02));
                float pu = length(p + vec2(0.0, 0.02));
                rdx += (exp(-pow((pl-r)*22.0,2.0)) - exp(-pow((pr-r)*22.0,2.0))) * (1.0 - phase) * gate;
                rdz += (exp(-pow((pd-r)*22.0,2.0)) - exp(-pow((pu-r)*22.0,2.0))) * (1.0 - phase) * gate;
                ruv = ruv * 1.7 + 5.3;
            }
            vec3 rn = normalize(v_dir - 2.0 * (rdx * tx + rdz * tz));
            n = normalize(mix(n, rn, clamp(abs(rh) * rain_intensity * 1.2, 0.0, 0.7)));
        }

        // Foam from jacobian (triplanar-ish, just XZ projection for speed)
        float j0 = texture(u_jacobian_map, v_uv0).r;
        float j1 = texture(u_jacobian_c1,  v_uv1).r;
        float j2 = texture(u_jacobian_c2,  v_uv2).r;
        float jac = min(min(j0, j1), j2);
        float foam = clamp(1.0 - jac, 0.0, 1.0);
        foam = pow(foam, 2.0) * 1.2;

        // Sun
        vec3 sun_dir = normalize(vec3(sin(sun_angle), cos(sun_angle), 0.2));
        vec3 view_dir = normalize(cam_pos - v_world);
        vec3 half_dir = normalize(sun_dir + view_dir);

        float NdotL = max(dot(n, sun_dir), 0.0);
        float diffuse = NdotL * 0.6 + 0.3;

        float sp1 = pow(max(dot(n, half_dir), 0.0), 180.0) * 1.8 * u_specular_intensity;
        float sp2 = pow(max(dot(n, half_dir), 0.0), 28.0)  * 0.4;
        float spec = (sp1 + sp2) * u_peak_brightness;

        float VdotN = max(dot(v_dir, view_dir), 0.0);
        float fresnel = pow(1.0 - VdotN, 5.0) * u_fresnel_strength * 2.5;

        vec3 sky_tint = mix(vec3(0.55, 0.72, 0.95), vec3(1.0, 0.85, 0.65),
                            clamp(sun_dir.y * 0.5 + 0.5, 0.0, 1.0));

        float crest = hC * 0.5 + 0.5;
        vec3 deep    = ocean_color.rgb * 0.55;
        vec3 shallow = ocean_color.rgb * 1.2 + vec3(0.02, 0.06, 0.08);
        vec3 base    = mix(deep, shallow, clamp(crest, 0.0, 1.0));

        float sss = max(0.0, hC) * max(0.0, dot(v_dir, sun_dir)) * u_sss_strength;

        vec3 water = base * diffuse
                   + sky_tint * fresnel
                   + vec3(1.0) * spec
                   + ocean_color.rgb * sss;
        water = mix(water, vec3(1.0), clamp(foam, 0.0, 1.0));

        gl_FragColor = vec4(water, ocean_color.a);
    }
    """
    return ShaderProgram(v_src, f_src)


def _build_sphere_mesh(lat_segs=96, lon_segs=128):
    """Create a tessellated UV sphere VBO+IBO."""
    import numpy as _np
    verts = []
    for i in range(lat_segs + 1):
        phi = math.pi * i / lat_segs
        sy = math.cos(phi)
        r  = math.sin(phi)
        for j in range(lon_segs + 1):
            theta = 2 * math.pi * j / lon_segs
            verts.append((r * math.cos(theta), sy, r * math.sin(theta)))
    verts = _np.array(verts, dtype=_np.float32).flatten()

    indices = []
    for i in range(lat_segs):
        for j in range(lon_segs):
            a = i * (lon_segs + 1) + j
            b = a + 1
            c = a + (lon_segs + 1)
            d = c + 1
            indices.extend([a, c, b])
            indices.extend([b, c, d])
    indices = _np.array(indices, dtype=_np.uint32)

    vbo = glGenBuffers(1)
    glBindBuffer(GL_ARRAY_BUFFER, vbo)
    glBufferData(GL_ARRAY_BUFFER, verts.nbytes, verts, GL_STATIC_DRAW)

    ibo = glGenBuffers(1)
    glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, ibo)
    glBufferData(GL_ELEMENT_ARRAY_BUFFER, indices.nbytes, indices, GL_STATIC_DRAW)

    glBindBuffer(GL_ARRAY_BUFFER, 0)
    glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, 0)
    return (vbo, ibo, len(indices), len(verts) // 3)


def _draw_sphere_vbo():
    global _ocean_world_sphere_mesh
    if _ocean_world_sphere_mesh is None:
        _ocean_world_sphere_mesh = _build_sphere_mesh()
    vbo, ibo, idx_count, _vc = _ocean_world_sphere_mesh
    glEnableClientState(GL_VERTEX_ARRAY)
    glBindBuffer(GL_ARRAY_BUFFER, vbo)
    glVertexPointer(3, GL_FLOAT, 0, None)
    glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, ibo)
    glDrawElements(GL_TRIANGLES, idx_count, GL_UNSIGNED_INT, None)
    glBindBuffer(GL_ARRAY_BUFFER, 0)
    glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, 0)
    glDisableClientState(GL_VERTEX_ARRAY)


def render_ocean_world(camera_pos, obj, elapsed_time, weather_obj=None):
    """Render a spherical ocean — procedural or Tessendorf/FFT based on `ocean_use_fft`."""
    global _ocean_world_shader, _ocean_world_fft_shader

    scale_xyz = getattr(obj, 'scale', [1.0, 1.0, 1.0])
    gizmo_scale = (float(scale_xyz[0]) + float(scale_xyz[1]) + float(scale_xyz[2])) / 3.0
    radius = float(getattr(obj, 'voxel_radius', 0.5)) \
             * float(getattr(obj, 'ocean_world_radius', 0.48)) \
             * gizmo_scale
    color = list(getattr(obj, 'ocean_world_color',
                         getattr(obj, 'material', {}).get('base_color', [0.05, 0.25, 0.6, 0.85])))
    pos = obj.position
    time_of_day = getattr(obj, 'time_of_day', 0.25)
    sun_angle = (time_of_day - 0.5) * 6.28318
    use_fft = bool(getattr(obj, 'ocean_use_fft', False))

    rain_i = 0.0
    if weather_obj is not None:
        rain_i = float(getattr(weather_obj, '_current_intensity', 0.0))
    else:
        rain_i = float(getattr(obj, 'u_rain_intensity', 0.0))

    glEnable(GL_BLEND)
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
    glDisable(GL_CULL_FACE)

    if use_fft:
        # --- Tessendorf FFT path (shared with flat ocean) ----------------
        from .procedural_ocean import FFTOceanWaveGenerator, _fft_generators
        if _ocean_world_fft_shader is None:
            _ocean_world_fft_shader = _create_ocean_world_fft_shader()

        res        = int(getattr(obj, 'ocean_fft_resolution', 128))
        choppiness = float(getattr(obj, 'ocean_wave_choppiness', 1.5))
        intensity  = float(getattr(obj, 'ocean_wave_intensity', 1.0))
        speed      = float(getattr(obj, 'ocean_wave_speed', 1.0))
        adjusted_t = elapsed_time * speed

        # Tile sizes scale with planet radius so cascades look balanced at any scale
        L0 = max(50.0, radius * 1.2)
        L1 = L0 * 0.2
        L2 = L0 * 0.05

        def _get_gen(res_, L_, wind_speed_, wdir_):
            key = (res_, L_)
            if key not in _fft_generators:
                _fft_generators[key] = FFTOceanWaveGenerator(
                    resolution=res_, size=L_, wind_speed=wind_speed_, wind_dir=wdir_)
            return _fft_generators[key]

        gen0 = _get_gen(res, L0, 30.0, (1.0, 0.2))
        gen1 = _get_gen(64, L1, 20.0, (0.6, 0.8))
        gen2 = _get_gen(64, L2, 10.0, (0.2, 1.0))
        gen0.update(adjusted_t, choppiness=choppiness, intensity=intensity)
        gen1.update(adjusted_t, choppiness=choppiness, intensity=intensity)
        gen2.update(adjusted_t, choppiness=choppiness * 0.5, intensity=intensity)
        obj._fft_gen_cascade0 = gen0

        sh = _ocean_world_fft_shader
        sh.use()

        glActiveTexture(GL_TEXTURE0); glBindTexture(GL_TEXTURE_2D, gen0.tex_displacement)
        sh.set_uniform_i("u_displacement_map", 0)
        glActiveTexture(GL_TEXTURE1); glBindTexture(GL_TEXTURE_2D, gen0.tex_jacobian)
        sh.set_uniform_i("u_jacobian_map", 1)
        glActiveTexture(GL_TEXTURE2); glBindTexture(GL_TEXTURE_2D, gen1.tex_displacement)
        sh.set_uniform_i("u_displacement_c1", 2)
        glActiveTexture(GL_TEXTURE3); glBindTexture(GL_TEXTURE_2D, gen1.tex_jacobian)
        sh.set_uniform_i("u_jacobian_c1", 3)
        glActiveTexture(GL_TEXTURE4); glBindTexture(GL_TEXTURE_2D, gen2.tex_displacement)
        sh.set_uniform_i("u_displacement_c2", 4)
        glActiveTexture(GL_TEXTURE5); glBindTexture(GL_TEXTURE_2D, gen2.tex_jacobian)
        sh.set_uniform_i("u_jacobian_c2", 5)

        sh.set_uniform_v3("cam_pos", *camera_pos)
        sh.set_uniform_v3("planet_center", *pos)
        sh.set_uniform_f("planet_radius", radius)
        sh.set_uniform_f("u_wave_scale",    L0)
        sh.set_uniform_f("u_wave_scale_c1", L1)
        sh.set_uniform_f("u_wave_scale_c2", L2)
        sh.set_uniform_f("u_choppiness",    choppiness)
        sh.set_uniform_f("u_cascade1_weight", float(getattr(obj, 'ocean_cascade1_weight', 0.5)))
        sh.set_uniform_f("u_cascade2_weight", float(getattr(obj, 'ocean_cascade2_weight', 0.7)))
        sh.set_uniform_f("time", adjusted_t)
        sh.set_uniform_f("sun_angle", sun_angle)
        sh.set_uniform_v4("ocean_color", *color)
        sh.set_uniform_f("rain_intensity", rain_i)
        sh.set_uniform_f("u_fresnel_strength",   float(getattr(obj, 'ocean_fresnel_strength', 0.3)))
        sh.set_uniform_f("u_specular_intensity", float(getattr(obj, 'ocean_specular_intensity', 1.0)))
        sh.set_uniform_f("u_peak_brightness",    float(getattr(obj, 'ocean_peak_brightness', 1.0)))
        sh.set_uniform_f("u_sss_strength",       float(getattr(obj, 'ocean_sss_strength', 1.0)))

        glPushMatrix()
        _draw_sphere_vbo()
        glPopMatrix()
        sh.stop()
        glActiveTexture(GL_TEXTURE0)
    else:
        # --- Procedural fbm shader path ---------------------------------
        if _ocean_world_shader is None:
            _ocean_world_shader = _create_ocean_world_shader()
        wave_speed     = float(getattr(obj, 'ocean_world_wave_speed', 3.0))
        wave_intensity = float(getattr(obj, 'ocean_world_wave_intensity', 0.015))

        _ocean_world_shader.use()
        _ocean_world_shader.set_uniform_v3("cam_pos", *camera_pos)
        _ocean_world_shader.set_uniform_v3("planet_center", *pos)
        _ocean_world_shader.set_uniform_f("time",           elapsed_time)
        _ocean_world_shader.set_uniform_f("wave_speed",     wave_speed)
        _ocean_world_shader.set_uniform_f("wave_intensity", wave_intensity)
        _ocean_world_shader.set_uniform_f("sun_angle",      sun_angle)
        _ocean_world_shader.set_uniform_v4("ocean_color",   *color)
        _ocean_world_shader.set_uniform_f("rain_intensity", rain_i)

        glPushMatrix()
        glTranslatef(*pos)
        glScalef(radius, radius, radius)
        q = gluNewQuadric()
        gluSphere(q, 1.0, 64, 64)
        gluDeleteQuadric(q)
        glPopMatrix()
        _ocean_world_shader.stop()

    glEnable(GL_CULL_FACE)
    glDisable(GL_BLEND)
