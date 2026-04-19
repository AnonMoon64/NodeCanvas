// -- VERTEX --
#version 120
    varying vec3 v_normal;
    varying vec2 v_uv;
    varying vec4 v_vcolor;
    void main() {
        v_normal = gl_NormalMatrix * gl_Normal;
        v_uv = gl_MultiTexCoord0.xy;
        v_vcolor = gl_Color;
        gl_Position = ftransform();
    }

// -- FRAGMENT --
#version 120
    uniform sampler2D u_tex0;
    uniform float u_has_tex;
    uniform vec4 base_color; // default: 1.0, 1.0, 1.0, 1.0
    uniform vec3 sunDir;
    uniform vec3 sunColor;
    uniform vec3 ambientColor;
    varying vec3 v_normal;
    varying vec2 v_uv;
    varying vec4 v_vcolor;
    void main() {
        vec3 n = normalize(v_normal);
        vec3 l = normalize(sunDir);
        float diff = max(dot(n, l), 0.0);
        
        vec3 albedo = base_color.rgb;
        if (v_vcolor.a > 0.05) {
            albedo *= v_vcolor.rgb;
        }
        if (u_has_tex > 0.5) {
            albedo *= texture2D(u_tex0, v_uv).rgb;
        }
        
        vec3 lit = albedo * diff * sunColor;
        vec3 final = lit + ambientColor * albedo;
        gl_FragColor = vec4(final, base_color.a);
    }
