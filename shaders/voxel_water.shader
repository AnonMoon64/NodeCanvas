// -- VERTEX --
#version 120

uniform float u_time;
uniform vec3  u_objPos;
uniform int   u_planetMode;
uniform vec3  u_planetCenter;
uniform float u_planetRadius;
uniform float u_water_speed;
uniform float u_water_surge;

varying vec3 v_normal;
varying vec3 v_world_pos;
varying vec4 v_vcolor;

void main() {
    // HARDENED NORMAL: Use gl_Normal but prevent zero-length artifacts
    v_normal = gl_NormalMatrix * (gl_Normal + vec3(0.0001));
    
    // Voxel chunks are LOCAL relative to obj.position (u_objPos)
    vec3 world_v = gl_Vertex.xyz + u_objPos;
    float time = u_time * u_water_speed;
    
    // Vertex displacement: Realistic choppy waves
    vec4 displaced_v = gl_Vertex;
    
    // Camera-relative world space for high precision at large coordinates
    // (Prevents the "jitter artifacts" at high X/Z values)
    vec3 rel_v = gl_Vertex.xyz; // Since gl_Vertex is chunk-local relative to obj_pos
    
    // Multi-octave wave sum to break uniformity (using rel_v for precision)
    // Mixed X/Z frequencies create more organic, non-axial waves
    float w1 = sin(rel_v.x * 0.17 + rel_v.z * 0.11 + time * 1.2) * 0.35;
    float w2 = cos(rel_v.z * 0.19 - rel_v.x * 0.08 + time * 1.0) * 0.25;
    float w3 = sin(rel_v.x * 0.43 + rel_v.z * 0.37 + time * 2.1) * 0.12;
    float w4 = cos(rel_v.x * 0.71 - rel_v.z * 0.63 + time * 2.7) * 0.06;
    float wave = (w1 + w2 + w3 + w4) * u_water_surge;
    
    if (u_planetMode == 1) {
        vec3 to_surface = world_v - u_planetCenter;
        vec3 dir = normalize(to_surface + vec3(0.0001));
        displaced_v.xyz += (dir * wave);
        v_world_pos = world_v + (dir * wave);
    } else {
        displaced_v.y += wave;
        v_world_pos = world_v + vec3(0, wave, 0);
    }
    
    v_vcolor = gl_Color;
    gl_Position = gl_ModelViewProjectionMatrix * displaced_v;
}

// -- FRAGMENT --
#version 120
uniform float u_time;
uniform float u_water_speed;
uniform float u_rain_intensity;
uniform float u_rain_time;
uniform vec4  base_color;
uniform vec3  sunDir;
uniform vec3  sunColor;
uniform vec3  ambientColor;
uniform vec3  cam_pos;
uniform vec4  shallow_color;
uniform int   u_planetMode;
uniform vec3  u_planetCenter;
uniform vec3  u_objPos;

varying vec3 v_normal;
varying vec3 v_world_pos;
varying vec4 v_vcolor;

float hash(vec2 p) {
    return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453123);
}

// Procedural ripple function for rain
float get_ripples(vec2 uv, float time) {
    float ripples = 0.0;
    for(int i = 0; i < 3; i++) {
        vec2 cell = floor(uv + hash(vec2(float(i))) * 10.0);
        vec2 pos = fract(uv + hash(vec2(float(i))) * 10.0) - 0.5;
        float h = hash(cell);
        
        float t = fract(time * 0.5 + h);
        float dist = length(pos);
        float ripple = sin(dist * 40.0 - t * 20.0) * exp(-dist * 8.0) * (1.0 - t);
        ripples += max(0.0, ripple);
    }
    return ripples;
}

void main() {
    vec3 n_base = normalize(v_normal);
    vec3 l_dir = normalize(sunDir);
    vec3 v_dir = normalize(cam_pos - v_world_pos);
    
    // High-precision local coordinate for fragment effects
    vec3 rel_v = v_world_pos - u_objPos;
    
    // Fragment Normal Perturbation: Multi-layered for organic silk look
    float time = u_time * (u_water_speed + 1.0) * 1.5;
    float dx = 0.17 * 0.35 * cos(rel_v.x * 0.17 + rel_v.z * 0.11 + time) +
               0.43 * 0.12 * cos(rel_v.x * 0.43 + rel_v.z * 0.37 + time * 2.1);
    float dz = 0.11 * 0.35 * cos(rel_v.x * 0.17 + rel_v.z * 0.11 + time) +
               0.19 * 0.25 * sin(rel_v.z * 0.19 - rel_v.x * 0.08 + time);
               
    // Break the grid even further with secondary high-freq noise
    dx += 0.1 * sin(rel_v.x * 5.0 + time * 3.0);
    dz += 0.1 * cos(rel_v.z * 5.5 - time * 2.5);
    
    vec3 wave_n = normalize(vec3(-dx, 1.2, -dz));
    if (u_planetMode == 1) {
        vec3 up = normalize(v_world_pos - u_planetCenter + vec3(0.0001));
        wave_n = normalize(up + vec3(-dx * 0.2, 0, -dz * 0.2));
    }
    
    // Add rain ripples to normal
    if (u_rain_intensity > 0.01) {
        float rips = get_ripples(rel_v.xz * 1.0, u_rain_time);
        wave_n.xz += rips * u_rain_intensity * 0.8;
        wave_n = normalize(wave_n + vec3(0.0001));
    }

    // Colors: Deep and Shallow Blue blending
    vec3 n_final = normalize(mix(n_base, wave_n, 0.8));
    
    // Fresnel transparency
    float fresnel = pow(1.0 - max(dot(n_final, v_dir), 0.0), 3.5);
    
    float shimmer = sin(rel_v.x * 5.0 + u_time * 2.0) * cos(rel_v.z * 5.0 - u_time * 1.5) * 0.05;
    vec3 deep = base_color.rgb;
    vec3 shallow = shallow_color.rgb;
    vec3 albedo = mix(deep, shallow, fresnel * 0.8 + shimmer);
    
    float diff = max(dot(n_final, l_dir), 0.4);
    vec3 final_rgb = albedo * diff * sunColor + ambientColor * albedo;
    
    // Specular highlight
    vec3 r_vec = reflect(-l_dir, n_final);
    float spec = pow(max(dot(r_vec, v_dir), 0.0), 128.0);
    final_rgb += sunColor * spec * 0.7;

    float alpha = clamp(base_color.a + fresnel * 0.4, 0.0, 1.0);
    gl_FragColor = vec4(final_rgb, alpha);
}
