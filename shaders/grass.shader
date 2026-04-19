// -- VERTEX --
#version 120
    uniform float time;
    uniform float wind_speed;    // default: 3.5
    uniform float wind_intensity; // default: 0.45
    
    varying vec3 v_normal;
    varying vec2 v_uv;
    varying vec4 v_vcolor;
    varying float v_y_orig;

    void main() {
        vec3 pos = gl_Vertex.xyz;
        v_y_orig = pos.y;
        
        // Pivot check: assume -0.5 is bottom
        float weight = clamp((pos.y + 0.5) * 1.0, 0.0, 1.0);
        // Exponential weight for more 'bend' at the tips
        weight = pow(weight, 1.5);
        
        // Use world-ish coordinates for variety (gl_Vertex works if mesh is small)
        float wave = sin(time * wind_speed + gl_Vertex.x * 2.0 + gl_Vertex.z * 1.5);
        float jitter = sin(time * wind_speed * 2.1 + gl_Vertex.y * 3.0) * 0.2;
        
        pos.x += (wave + jitter) * wind_intensity * weight;
        pos.z += (wave * 0.6 - jitter) * wind_intensity * weight;
        
        // Correct height so it doesn't 'stretch' vertically
        pos.y -= (abs(wave) * wind_intensity * 0.2) * weight;

        v_normal = gl_NormalMatrix * gl_Normal;
        v_uv = gl_MultiTexCoord0.xy;
        v_vcolor = gl_Color;
        gl_Position = gl_ModelViewProjectionMatrix * vec4(pos, 1.0);
    }

// -- FRAGMENT --
#version 120
    uniform sampler2D u_tex0;
    uniform float u_has_tex;
    uniform vec4 base_color;     // default: 0.15, 0.45, 0.1, 1.0
    uniform vec3 sunDir;
    uniform vec3 sunColor;
    uniform vec3 ambientColor;
    
    varying vec3 v_normal;
    varying vec2 v_uv;
    varying vec4 v_vcolor;
    varying float v_y_orig;

    void main() {
        vec3 n = normalize(v_normal);
        vec3 l = normalize(sunDir);
        // Wrap lighting for foliage translucency feel
        float diff = max(dot(n, l) * 0.7 + 0.3, 0.0); 
        
        vec3 albedo = base_color.rgb;
        if (v_vcolor.a > 0.05) {
            albedo *= v_vcolor.rgb;
        }
        
        if (u_has_tex > 0.5) {
            albedo *= texture2D(u_tex0, v_uv).rgb;
        }
        
        // Darken near the base
        float ground_shadow = clamp(v_y_orig + 0.6, 0.3, 1.2);
        albedo *= ground_shadow;
        
        vec3 lit = albedo * diff * sunColor;
        vec3 final = lit + ambientColor * albedo;
        gl_FragColor = vec4(final, base_color.a);
    }

