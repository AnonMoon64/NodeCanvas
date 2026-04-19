// -- VERTEX --
#version 330 compatibility

    uniform sampler2D u_displacement_map;  // Cascade 0: large swells  (L=1000)
    uniform sampler2D u_displacement_c1;   // Cascade 1: medium chop   (L=200)
    uniform sampler2D u_displacement_c2;   // Cascade 2: small ripples (L=50)
    uniform vec3  grid_origin;
    uniform float grid_chunk_size;
    uniform float u_wave_scale;
    uniform float u_choppiness;
    uniform float u_cascade1_weight;
    uniform float u_cascade2_weight;
    uniform float time;
    uniform vec3  cam_pos;

    // Gerstner hero waves (up to 3 artist-controlled swell waves)
    uniform int   u_hero_count;
    uniform float u_hero_amp[3];
    uniform float u_hero_wlen[3];
    uniform float u_hero_dir[3];   // radians
    uniform float u_hero_steep[3];

    out vec3  v_pos;
    out float v_height;
    out vec3  v_view_dir;
    out vec2  v_uv;

    vec3 gerstner_hero(vec3 wp, float amp, float wlen, float dir_angle, float steep) {
        float k     = 6.28318 / max(wlen, 0.01);
        float c     = sqrt(9.81 / k);
        vec2  d     = vec2(cos(dir_angle), sin(dir_angle));
        float phase = k * (dot(d, wp.xz) - c * time);
        float s     = clamp(steep, 0.0, 0.99);
        return vec3(d.x * amp * s * cos(phase),
                    amp * sin(phase),
                    d.y * amp * s * cos(phase));
    }

    void main() {
        vec3 world_p = (gl_Vertex.xyz * grid_chunk_size) + grid_origin;

        // Cascade UV sets. Each cascade is rotated so their tiling axes don't align —
        // aligned tiling at cascade-2's ~50m period was showing as horizontal "strip" bands.
        v_uv     = (world_p.xz / 1000.0) * u_wave_scale;
        // cascade-1: rotate ~37°, cascade-2: rotate ~-61°
        mat2 rot1 = mat2( 0.7986, 0.6018, -0.6018, 0.7986);
        mat2 rot2 = mat2( 0.4848,-0.8746,  0.8746, 0.4848);
        vec2 uv1 = (rot1 * v_uv) * 5.0;   // /200 equivalent
        vec2 uv2 = (rot2 * v_uv) * 20.0;  // /50  equivalent

        // --- Cascade displacements ---
        // Large cascade: full XZ (drives main swell shape).
        // The mesh samples at ~7.8m spacing while the cascade-0 texture has 3.9m cells —
        // that's a 2× Nyquist violation, which produces visible aliased "ribbon strip"
        // artifacts that scale with intensity. A 5-tap box filter low-passes the texture
        // to stay below the mesh Nyquist limit.
        float td = 1.0 / 256.0;  // one texel in cascade-0 UV space
        vec3 disp0 = texture(u_displacement_map, v_uv).rgb * 0.5
                   + texture(u_displacement_map, v_uv + vec2( td, 0.0)).rgb * 0.125
                   + texture(u_displacement_map, v_uv + vec2(-td, 0.0)).rgb * 0.125
                   + texture(u_displacement_map, v_uv + vec2(0.0,  td)).rgb * 0.125
                   + texture(u_displacement_map, v_uv + vec2(0.0, -td)).rgb * 0.125;
        vec3 disp1 = texture(u_displacement_c1,  uv1).rgb * u_cascade1_weight;
        vec3 disp2 = texture(u_displacement_c2,  uv2).rgb * u_cascade2_weight;

        // Small cascades contribute mainly to height/normals, NOT to horizontal folding
        // Full XZ from them would cause high-frequency vertex crossing
        disp1.xz *= 0.25;
        disp2.xz *= 0.05;

        vec3 fft_disp = disp0 + disp1 + disp2;

        // --- Gerstner hero waves ---
        vec3 hero = vec3(0.0);
        if (u_hero_count > 0) hero += gerstner_hero(world_p, u_hero_amp[0], u_hero_wlen[0], u_hero_dir[0], u_hero_steep[0]);
        if (u_hero_count > 1) hero += gerstner_hero(world_p, u_hero_amp[1], u_hero_wlen[1], u_hero_dir[1], u_hero_steep[1]);
        if (u_hero_count > 2) hero += gerstner_hero(world_p, u_hero_amp[2], u_hero_wlen[2], u_hero_dir[2], u_hero_steep[2]);

        v_height = fft_disp.y + hero.y;
        v_pos    = world_p + fft_disp + hero;

        // --- Vertex displacement ---
        // XZ: FFT gets choppiness scaling; hero uses raw horizontal (steepness already controls it)
        // Both divide by grid_chunk_size to convert world-metres → local [-1,1] space
        float inv_chunk = 1.0 / grid_chunk_size;
        vec3 displaced_v = gl_Vertex.xyz;
        displaced_v.xz  += fft_disp.xz * u_choppiness * inv_chunk;
        displaced_v.xz  += hero.xz * inv_chunk;
        displaced_v.y   += fft_disp.y + hero.y;

        // Soft-limit XZ so vertices can never cross their neighbours (prevents tearing).
        // Hard clamp() makes adjacent saturated verts collapse to identical positions, which
        // shows up as flat ribbon/strip artifacts. tanh() gives smooth saturation instead.
        float max_disp = (2.0 / 255.0) * 0.55;
        vec2 d_xz      = displaced_v.xz - gl_Vertex.xz;
        d_xz           = max_disp * tanh(d_xz / max(max_disp, 1e-6));
        displaced_v.xz = gl_Vertex.xz + d_xz;

        vec4 eye_pos = gl_ModelViewMatrix * vec4(displaced_v, 1.0);
        v_view_dir   = normalize(-eye_pos.xyz);

        gl_Position = gl_ModelViewProjectionMatrix * vec4(displaced_v, 1.0);
    }

// -- FRAGMENT --
#version 330 compatibility

    uniform vec4  ocean_color;
    uniform float ocean_opacity;
    uniform float foam_amount;
    uniform float time;
    uniform vec3  cam_pos;

    // Cascade displacement + jacobian textures
    uniform sampler2D u_displacement_map;
    uniform sampler2D u_displacement_c1;
    uniform sampler2D u_displacement_c2;
    uniform sampler2D u_jacobian_map;
    uniform sampler2D u_jacobian_c1;
    uniform sampler2D u_jacobian_c2;
    uniform sampler2D u_velocity_map;
    uniform sampler2D u_foam_advected;
    uniform sampler2D u_ripple_map;
    uniform float u_wave_scale;
    uniform float u_cascade1_weight;
    uniform float u_cascade2_weight;
    uniform float time_of_day;
    uniform vec3  sunDir;
    uniform vec3  sunColor;
    uniform vec3  ambientColor;

    uniform int   u_is_underwater;
    uniform vec3  u_underwater_tint;

    // Advanced Visuals
    uniform float u_fresnel_strength;
    uniform float u_specular_intensity;
    uniform vec3  u_reflection_tint;
    uniform float u_peak_brightness;
    uniform float u_sss_strength;

    // Rain splash / ripple controls
    uniform float u_rain_intensity;       // 0..1 (from Weather primitive)
    uniform float u_rain_time;            // seconds (drives ripple animation)

    // Foam layer controls
    uniform float u_foam_jacobian;        // jacobian break foam intensity
    uniform float u_foam_whitecap;        // height whitecap foam intensity
    uniform float u_foam_whitecap_thresh; // height threshold for whitecaps (0-1)
    uniform float u_foam_streak;          // streak trail intensity
    uniform float u_foam_streak_speed;    // how fast streak trails move
    uniform float u_flow_scale;           // scale for converting displacement -> flow UV advection
    uniform float u_foam_sharpness;       // jacobian foam sharpness exponent
    uniform float u_detail_strength;      // 4th-pass micro-detail normal weight

    in vec3  v_pos;
    in float v_height;
    in vec3  v_view_dir;
    in vec2  v_uv;

    // --- Foam Utilities ---
    vec2 hash2(vec2 p) {
        return fract(sin(vec2(dot(p, vec2(127.1, 311.7)), dot(p, vec2(269.5, 183.3)))) * 43758.5453);
    }
    
    float bubble_noise(vec2 p, float t) {
        vec2 i = floor(p);
        vec2 f = fract(p);
        float dist = 1.0;
        for(int y=-1; y<=1; y++) {
            for(int x=-1; x<=1; x++) {
                vec2 g = vec2(float(x), float(y));
                vec2 o = hash2(i + g);
                o = 0.5 + 0.5 * sin(t + 6.28 * o);
                vec2 r = g + o - f;
                dist = min(dist, dot(r, r));
            }
        }
        return sqrt(dist);
    }

    void main() {
        // Cascade UVs derived from cascade-0 UV — must match the rotations used in the
        // vertex shader so per-pixel normals line up with the displaced geometry.
        mat2 rot1 = mat2( 0.7986, 0.6018, -0.6018, 0.7986);
        mat2 rot2 = mat2( 0.4848,-0.8746,  0.8746, 0.4848);
        vec2 uv1 = (rot1 * v_uv) * 5.0;
        vec2 uv2 = (rot2 * v_uv) * 20.0;
        vec2 uv3 = uv2 * 4.0;   // 4th micro-detail pass (×80 total scale)

        // --- Multi-cascade per-pixel normals ---
        // Smaller cascades contribute proportionally more to surface detail
        float d0 = 1.0 / 128.0;
        float d1 = 1.0 / 64.0;
        float hL  = texture(u_displacement_map, v_uv - vec2(d0, 0.0)).y;
        float hR  = texture(u_displacement_map, v_uv + vec2(d0, 0.0)).y;
        float hD  = texture(u_displacement_map, v_uv - vec2(0.0, d0)).y;
        float hU  = texture(u_displacement_map, v_uv + vec2(0.0, d0)).y;

        float hL1 = texture(u_displacement_c1, uv1 - vec2(d1, 0.0)).y * u_cascade1_weight;
        float hR1 = texture(u_displacement_c1, uv1 + vec2(d1, 0.0)).y * u_cascade1_weight;
        float hD1 = texture(u_displacement_c1, uv1 - vec2(0.0, d1)).y * u_cascade1_weight;
        float hU1 = texture(u_displacement_c1, uv1 + vec2(0.0, d1)).y * u_cascade1_weight;

        float hL2 = texture(u_displacement_c2, uv2 - vec2(d1, 0.0)).y * u_cascade2_weight;
        float hR2 = texture(u_displacement_c2, uv2 + vec2(d1, 0.0)).y * u_cascade2_weight;
        float hD2 = texture(u_displacement_c2, uv2 - vec2(0.0, d1)).y * u_cascade2_weight;
        float hU2 = texture(u_displacement_c2, uv2 + vec2(0.0, d1)).y * u_cascade2_weight;

        // 4th pass: reuse cascade-2 texture at ×4 UV — adds fine surface crispness (not bumps)
        float hL3 = texture(u_displacement_c2, uv3 - vec2(d1, 0.0)).y * u_cascade2_weight * u_detail_strength;
        float hR3 = texture(u_displacement_c2, uv3 + vec2(d1, 0.0)).y * u_cascade2_weight * u_detail_strength;
        float hD3 = texture(u_displacement_c2, uv3 - vec2(0.0, d1)).y * u_cascade2_weight * u_detail_strength;
        float hU3 = texture(u_displacement_c2, uv3 + vec2(0.0, d1)).y * u_cascade2_weight * u_detail_strength;

        // --- Normals: 4-level cascade. Y=0.12 (was 0.06) — the very-low Y was amplifying
        // small finite-difference errors into harsh dark/bright strips at glancing angles.
        vec3 normal = normalize(vec3(
            (hL - hR) + (hL1 - hR1) * 4.0 + (hL2 - hR2) * 12.0 + (hL3 - hR3) * 23.0,
            0.12,
            (hD - hU) + (hD1 - hU1) * 4.0 + (hD2 - hU2) * 12.0 + (hD3 - hU3) * 23.0
        ));
        vec3 view_dir = normalize(v_view_dir);
        
        // --- Modular Ripples (Impacts from logic) ---
        float dyn_rip = texture(u_ripple_map, v_uv).r;
        if (dyn_rip > 0.005) {
            // Sample neighbors for normal perturbation
            float d2 = 0.5/128.0;
            float rL = texture(u_ripple_map, v_uv - vec2(d2, 0.0)).r;
            float rR = texture(u_ripple_map, v_uv + vec2(d2, 0.0)).r;
            float rD = texture(u_ripple_map, v_uv - vec2(0.0, d2)).r;
            float rU = texture(u_ripple_map, v_uv + vec2(0.0, d2)).r;
            
            // Sharpened normal for clearer ripple highlights
            vec3 ripple_n = normalize(vec3(rL - rR, 0.05, rD - rU));
            // Mix the normal using a safe lerp-like approach
            normal = normalize(mix(normal, ripple_n, dyn_rip * 0.7));
        }

        // --- Rain Ripples (procedural, driven by u_rain_intensity) ----
        // Sum a few scales of expanding ring cells. Each cell spawns a ripple at a
        // random phase; the ring radius grows with phase and fades as it ages.
        float _splash_foam = dyn_rip * 0.5;
        if (u_rain_intensity > 0.001) {
            vec2 ruv = v_uv * 180.0;
            float rain_h = 0.0;
            float rain_dx = 0.0;
            float rain_dz = 0.0;
            for (int i = 0; i < 3; i++) {
                vec2 cell = floor(ruv);
                vec2 f    = fract(ruv) - 0.5;
                // Hash per-cell seed & random jitter inside the cell
                float s  = fract(sin(dot(cell, vec2(127.1, 311.7)) + float(i)*7.3) * 43758.5453);
                vec2 jitter = vec2(
                    fract(sin(s * 91.13) * 47453.0) - 0.5,
                    fract(sin(s * 17.77) * 51331.0) - 0.5
                ) * 0.6;
                vec2 p = f - jitter;
                float phase = fract(u_rain_time * 1.6 + s);
                float d = length(p);
                // Gate on rain intensity — sparse rings at low intensity
                float density_gate = step(1.0 - clamp(u_rain_intensity, 0.0, 1.0), s);
                float ring_r = phase * 0.45;
                float ring = exp(-pow((d - ring_r) * 22.0, 2.0)) * (1.0 - phase) * density_gate;
                rain_h += ring;
                // finite-diff along axes for normal perturbation
                float pl = length(p - vec2(0.02, 0.0));
                float pr = length(p + vec2(0.02, 0.0));
                float pd = length(p - vec2(0.0, 0.02));
                float pu = length(p + vec2(0.0, 0.02));
                rain_dx += (exp(-pow((pl - ring_r)*22.0,2.0)) - exp(-pow((pr - ring_r)*22.0,2.0))) * (1.0 - phase) * density_gate;
                rain_dz += (exp(-pow((pd - ring_r)*22.0,2.0)) - exp(-pow((pu - ring_r)*22.0,2.0))) * (1.0 - phase) * density_gate;
                ruv = ruv * 1.7 + 5.3;
            }
            float amp = clamp(u_rain_intensity, 0.0, 2.0);
            vec3 rain_n = normalize(vec3(rain_dx, 0.06, rain_dz));
            normal = normalize(mix(normal, rain_n, clamp(abs(rain_h) * amp * 1.2, 0.0, 0.75)));
            _splash_foam += clamp(rain_h * amp, 0.0, 1.0) * 0.35;
        }

        // --- Day/Night Lighting (Unified) ---
        vec3  light_dir = normalize(sunDir);
        float day_ratio = max(0.0, min(1.0, light_dir.y * 5.0 + 0.5));

        // --- Base Water Color (SoT: rich teal-inky blue, not flat navy) ---
        float h_norm    = clamp(v_height * 0.04 + 0.55, 0.0, 1.0);
        // Deep = dark teal-black (middle ground between rich teal and flat navy)
        vec3 color_deep = mix(vec3(0.005, 0.04, 0.08), ocean_color.rgb * 0.38, 0.45);
        // Shallow = bright teal-cyan (SoT's glowing crest color)
        vec3 color_shal = mix(vec3(0.04, 0.30, 0.42), ocean_color.rgb, 0.55) * 1.15;
        vec3 water_rgb  = mix(color_deep, color_shal, pow(h_norm, 1.3));

        // --- Ambient sky bounce — the key to "wet" look ---
        // Even in shadow, ocean always reflects some sky. SoT water is NEVER flat matte.
        vec3 sky_amb_day   = mix(vec3(0.07, 0.18, 0.32), vec3(0.18, 0.35, 0.52), h_norm);
        vec3 sky_amb_night = ambientColor;
        water_rgb += mix(sky_amb_night, sky_amb_day, day_ratio) * 0.25;

        // --- Directional Diffuse ---
        // Min 0.38 middle ground — keeps shadows from going pure black
        float NdotL   = dot(normal, light_dir);
        float diffuse  = mix(0.38, 1.0, clamp(NdotL * 0.5 + 0.5, 0.0, 1.0));
        diffuse = mix(0.47, diffuse, day_ratio);
        water_rgb *= (diffuse * sunColor);

        // --- SoT Foam System (three layers) ---
        // 1. Jacobian fold foam — where waves break
        float jac0   = texture(u_jacobian_map, v_uv).r;
        float jac1   = texture(u_jacobian_c1,  uv1).r;
        float jac2   = texture(u_jacobian_c2,  uv2).r;
        float jmask0 = clamp(1.0 - jac0, 0.0, 1.0);
        float jmask1 = clamp(1.0 - jac1, 0.0, 1.0) * u_cascade1_weight;
        float jmask2 = clamp(1.0 - jac2, 0.0, 1.0) * u_cascade2_weight;
        float jac_mask = clamp(jmask0 * 0.6 + jmask1 * 0.25 + jmask2 * 0.15, 0.0, 1.0);

        // 2. Height whitecap foam — thick caps on tall crests (SoT hallmark)
        float wc_thresh  = mix(0.60, 0.90, u_foam_whitecap_thresh);
        float crest_foam = smoothstep(wc_thresh, 1.0, h_norm);
        float churn = sin(v_pos.x * 0.018 + time * 0.4) * cos(v_pos.z * 0.014 - time * 0.3);
        crest_foam  *= smoothstep(-0.2, 0.6, churn);

        // 3. Animated streak foam — panned using flowmap technique based on velocity
        float s_speed  = u_foam_streak_speed * 0.1;
        vec2 local_flow = texture(u_velocity_map, v_uv).rg * u_flow_scale;
        
        float phase0 = fract(time * 0.5);
        float phase1 = fract(time * 0.5 + 0.5);
        float f_weight = abs(0.5 - phase0) * 2.0;

        vec2 uv_adv0 = v_uv - local_flow * phase0 * s_speed;
        vec2 uv_adv1 = v_uv - local_flow * phase1 * s_speed;
        
        float streak0_a = clamp(1.0 - texture(u_jacobian_map, uv_adv0).r, 0.0, 1.0);
        float streak0_b = clamp(1.0 - texture(u_jacobian_map, uv_adv0 * 1.7 + 0.13).r, 0.0, 1.0);
        float streak1_a = clamp(1.0 - texture(u_jacobian_map, uv_adv1).r, 0.0, 1.0);
        float streak1_b = clamp(1.0 - texture(u_jacobian_map, uv_adv1 * 1.7 + 0.13).r, 0.0, 1.0);
        
        float streaks = mix(pow(streak0_a, 8.0) * 0.30 + pow(streak0_b, 10.0) * 0.18,
                            pow(streak1_a, 8.0) * 0.30 + pow(streak1_b, 10.0) * 0.18,
                            f_weight);

        // 4. Cellular Bubble Detail + Persistent Advected Foam Buffer (Flowmap)
        // Secondary GPU-side flowmap advection on top of the CPU-side persistent advection.
        float foam_p0 = fract(time * 0.4);
        float foam_p1 = fract(time * 0.4 + 0.5);
        float foam_w  = abs(0.5 - foam_p0) * 2.0;
        
        float foam_samp0 = texture(u_foam_advected, v_uv - local_flow * foam_p0).r;
        float foam_samp1 = texture(u_foam_advected, v_uv - local_flow * foam_p1).r;
        float foam_adv   = mix(foam_samp0, foam_samp1, foam_w);
        
        // Tighter tiling for bubbles, also panned slightly by flow
        vec2 uv_bubbles = v_pos.xz * 35.0 - local_flow * time * 50.0;
        float b_dist = bubble_noise(uv_bubbles, time * 0.6);
        float bubble_rims = smoothstep(0.04, 0.12, b_dist); // The "walls" (1.0 = wall)
        float bubbles = (1.0 - smoothstep(0.0, 0.08, b_dist)) * jac_mask; // Interior seeds

        // Per-layer foam mask driven by individual sliders
        float jac_sharp = max(u_foam_sharpness, 0.5);
        float foam_mask = clamp(
            pow(jac_mask, jac_sharp)  * foam_amount * u_foam_jacobian  * 4.5 +
            crest_foam                * foam_amount * u_foam_whitecap   * 3.5 +
            streaks                   * foam_amount * u_foam_streak      * 2.5 +
            bubbles                   * foam_amount * u_foam_jacobian    * 1.5 +
            foam_adv                  * foam_amount * 2.0,
            0.0, 1.0);
            
        // Reduce solidness: bubble centers are more transparent than rims
        foam_mask *= mix(0.4, 1.0, bubble_rims);

        // Foam color is modulated by bubble rims — interiors are more transparent/teal
        // This stops it from looking like a "white layer"
        vec3 foam_base = vec3(0.96, 0.98, 0.97);
        vec3 bubble_color = mix(vec3(0.02, 0.38, 0.35), foam_base, bubble_rims); 
        vec3 foam_lit = bubble_color * mix(0.80, 1.0, diffuse);
        
        water_rgb = mix(water_rgb, foam_lit, foam_mask);

        // --- SoT Sub-Surface Scattering ---
        float sss_h    = clamp(v_height * 0.12, 0.0, 1.0);
        // Always-on teal rim SSS: wave faces glow cyan even without direct sun
        float sss_rim  = pow(max(1.0 - dot(view_dir, normal), 0.0), 2.5) * sss_h;
        water_rgb += vec3(0.01, 0.36, 0.30) * sss_rim * 0.15 * u_sss_strength;
        // Directional back-lit SSS (sun shining through wave tips)
        float sss_back = max(-NdotL, 0.0);
        float sss_view = pow(max(dot(view_dir, light_dir), 0.0), 2.0);
        float sss      = sss_back * sss_view * sss_h;
        water_rgb += vec3(0.0, 0.65, 0.55) * sss * u_sss_strength * 1.4 * day_ratio;

        // --- Wave Crest Peak Brightness ---
        float crest = smoothstep(0.72, 1.0, h_norm) * clamp(NdotL * 0.5 + 0.5, 0.0, 1.0);
        water_rgb  += vec3(0.55, 0.85, 0.80) * crest * u_peak_brightness * 0.45;

        // --- Triple-Layer Specular (wet glass look) ---
        vec3  half_v       = normalize(light_dir + view_dir + vec3(1e-5));
        float NdotH        = max(dot(normal, half_v), 0.0);
        // Broad wet sheen covers most of the wave face
        float spec_broad   = pow(NdotH,   62.0) * 1.4  * u_specular_intensity * day_ratio;
        // Tight glint — smaller bright highlight
        float spec_tight   = pow(NdotH,  350.0) * 7.0  * u_specular_intensity * day_ratio;
        // Sub-pixel sparkle — ocean glitter
        float spec_sparkle = pow(NdotH, 3000.0) * 18.0 * u_specular_intensity * day_ratio;

        // --- Fresnel Reflection (stronger = wetter) ---
        float NdotV   = max(dot(normal, view_dir), 0.0);
        float fresnel = pow(1.0 - NdotV, 3.5) * u_fresnel_strength;
        // Minimum fresnel so glancing water always shows sky (key "wet" cue)
        fresnel = max(fresnel, pow(1.0 - NdotV, 1.2) * 0.06);

        // --- Sky Reflection Tint ---
        // The orange sunrise/sunset reflection was bleeding into all glancing-angle
        // reflections at any non-noon time-of-day. Fresnel is strongest at the horizon
        // and on wave back-slopes, so that orange showed as brown "claws" and "plates"
        // wrapping every wave. Narrow the orange band so it only kicks in within ~10%
        // of true sunrise/sunset (time_of_day ~0/1) and stays subtle even then.
        float sunset_t = pow(clamp(1.0 - abs(sin(time_of_day * 3.14159)) * 1.4, 0.0, 1.0), 2.0);
        vec3  sky_ref = mix(u_reflection_tint, vec3(1.0, 0.60, 0.28), sunset_t * 0.5);
        // Night sky: middle ground blue-black reflection
        sky_ref = mix(vec3(0.04, 0.075, 0.16), sky_ref, day_ratio);
        water_rgb = mix(water_rgb, sky_ref, fresnel);

        vec3 final_rgb = water_rgb + spec_broad + spec_tight + spec_sparkle;

        // --- Atmospheric Horizon Haze (SoT: rich blue-teal at all times) ---
        float hdist     = length(v_pos.xz - cam_pos.xz);
        float haze      = clamp((hdist - 300.0) / 650.0, 0.0, 1.0);
        haze            = pow(haze, 1.2);
        vec3 haze_day   = mix(ocean_color.rgb * 0.55, vec3(0.38, 0.58, 0.82), 0.55);
        // Night haze: visible dark blue, not near-black
        vec3 haze_night = mix(vec3(0.04, 0.09, 0.20), ocean_color.rgb * 0.25, 0.5);
        vec3 haze_color = mix(haze_night, haze_day, day_ratio);
        final_rgb = mix(final_rgb, haze_color, haze * 0.85);

        float final_alpha = ocean_opacity;
        if (u_is_underwater > 0) {
            // Apply deep-sea scattering fog
            float water_fog = clamp(hdist * 0.002, 0.0, 1.0);
            final_rgb = mix(final_rgb, u_underwater_tint * 0.05, water_fog);
            final_rgb *= u_underwater_tint * 1.5;
            
            // From below, we want some transparency to see the sun/sky distorted through the surface
            final_alpha = mix(ocean_opacity, 0.6, 0.5);
        }

        gl_FragColor = vec4(final_rgb, final_alpha);
    }
