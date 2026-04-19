// -- VERTEX --
#version 120
    uniform float time;
    uniform float wave_speed;
    uniform float wave_amplitude;
    uniform float invert_axis;
    
    varying vec3 v_pos;
    varying vec3 v_normal;
    varying vec2 v_uv;

    void main() {
        vec3 pos = gl_Vertex.xyz;
        v_uv = gl_MultiTexCoord0.xy;
        float d = pos.x;
        if (invert_axis > 0.5) d = -pos.x;
        
        float wave = sin(d * 2.0 + time * wave_speed) * cos(pos.z * 1.5 + time * wave_speed * 0.8);
        pos.y += wave * wave_amplitude * (d + 0.5); 
        
        v_pos = (gl_ModelViewMatrix * vec4(pos, 1.0)).xyz;
        v_normal = gl_NormalMatrix * gl_Normal;
        gl_Position = gl_ModelViewProjectionMatrix * vec4(pos, 1.0);
    }

// -- FRAGMENT --
#version 120
    uniform sampler2D u_tex0;
    uniform float u_has_tex;
    uniform vec4 base_color;
    uniform vec3 sunDir;
    uniform vec3 sunColor;
    uniform vec3 ambientColor;
    varying vec3 v_pos;
    varying vec3 v_normal;
    varying vec2 v_uv;

    void main() {
        vec3 n = normalize(v_normal);
        vec3 l = normalize(sunDir);
        float diff = max(dot(n, l), 0.0);
        
        vec3 albedo = base_color.rgb;
        if (u_has_tex > 0.5) {
            albedo *= texture2D(u_tex0, v_uv).rgb;
        }
        
        vec3 lit = albedo * diff * sunColor;
        vec3 final = lit + ambientColor * albedo;
        gl_FragColor = vec4(final, base_color.a);
    }
