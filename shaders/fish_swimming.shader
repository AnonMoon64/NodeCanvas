// -- VERTEX --
#version 120
    uniform float time;
    uniform float speed;
    uniform float freq;
    uniform float intensity;
    
    uniform float yaw_amp;
    uniform float side_amp;
    uniform float roll_amp;
    uniform float flag_amp;
    
    uniform float forward_axis; // 0=X, 1=Y, 2=Z
    uniform float invert_axis;  // 0=Normal, 1=Inverted
    
    varying vec3 v_pos;
    varying vec3 v_normal;
    varying vec2 v_uv;

    mat3 rotate_y(float a) {
        float c = cos(a); float s = sin(a);
        return mat3(c, 0, s, 0, 1, 0, -s, 0, c);
    }
    mat3 rotate_z(float a) {
        float c = cos(a); float s = sin(a);
        return mat3(c, -s, 0, s, c, 0, 0, 0, 1);
    }

    void main() {
        vec3 pos = gl_Vertex.xyz;
        v_uv = gl_MultiTexCoord0.xy;
        
        // 1. Identify "Forward Distance" (0 at head, 1 at tail)
        float d = pos.x;
        if (forward_axis > 0.5 && forward_axis < 1.5) d = pos.y;
        else if (forward_axis > 1.5) d = pos.z;
        
        float dist = d + 0.5; 
        if (invert_axis > 0.5) dist = 0.5 - d;
        
        // ABZU Curve: The head leads, the body follows with a delay.
        float t = time * speed;
        
        // --- 2. Multi-Wave Spine Panning ---
        // Wave A: Large, slow primary body wave (The "Spine")
        float waveA = sin(t - dist * freq);
        
        // Wave B: Faster, smaller tail flick
        float waveB = sin(t * 1.5 - dist * freq * 2.0);
        
        // Wave C: High-frequency fin flutter
        float waveC = sin(t * 3.0 - dist * freq * 4.0);
        
        // Combine weights
        // Head (dist=0) has low amplitude, Tail (dist=1) has high.
        float body_mask = 0.3 + 0.7 * smoothstep(0.0, 1.0, dist);
        float tail_mask = pow(smoothstep(0.4, 1.0, dist), 2.0);
        float fin_mask  = pow(smoothstep(0.7, 1.0, dist), 3.0);
        
        // Compute combined Yaw (Tangent bend)
        float combined_yaw = (waveA * 0.7 * body_mask) + (waveB * 0.3 * tail_mask);
        combined_yaw *= yaw_amp * intensity;
        
        // Compute Side Translation (The "Flag" component, but reduced)
        // In ABZU, translation is less important than the rotation bend.
        float side = waveA * side_amp * intensity * body_mask * 0.5;
        
        // Compute Roll (Banking)
        float roll = cos(t - dist * freq * 0.5) * roll_amp * intensity * body_mask;
        
        // Compute Vert (Vertical fin flutter)
        float vert = waveC * flag_amp * intensity * fin_mask;

        // --- 3. Geometric Bending ---
        // We act like each vertex is part of a spine-segment.
        vec3 local_offset = pos;
        if (forward_axis < 0.5) local_offset.x = 0.0;
        else if (forward_axis < 1.5) local_offset.y = 0.0;
        else local_offset.z = 0.0;
        
        // Rotate the local slice
        mat3 rot = rotate_y(combined_yaw) * rotate_z(roll);
        local_offset = rot * local_offset;
        
        // Reassemble position
        vec3 final_pos = pos;
        if (forward_axis < 0.5) {
            final_pos.y = local_offset.y; 
            final_pos.z = local_offset.z + side; // Body shifts laterally
        } else if (forward_axis < 1.5) {
            final_pos.x = local_offset.x + side;
            final_pos.z = local_offset.z;
        } else {
            final_pos.x = local_offset.x + side;
            final_pos.y = local_offset.y;
        }
        
        v_pos = (gl_ModelViewMatrix * vec4(final_pos, 1.0)).xyz;
        v_normal = gl_NormalMatrix * (rot * gl_Normal); // Normal stays tangent to bend
        gl_Position = gl_ModelViewProjectionMatrix * vec4(final_pos, 1.0);
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
        vec3 v = normalize(-v_pos); // View dir
        
        float diff = max(dot(n, l), 0.0);
        
        // ABZU Technique: Subsurface Scattering (Faked)
        // Light passing through thin fins/edges
        float sss_mask = pow(1.0 - max(dot(n, l), 0.0), 4.0) * pow(max(dot(v, -l), 0.0), 2.0);
        vec3 sss_color = vec3(1.0, 0.8, 0.6) * 0.4; // Warm translucency
        
        // Rim lighting (Edge highlights)
        float rim = pow(1.0 - max(dot(n, v), 0.0), 3.0) * diff;
        
        vec3 albedo = base_color.rgb;
        if (u_has_tex > 0.5) {
            albedo *= texture2D(u_tex0, v_uv).rgb;
        }
        
        // Vertical gradient (ABZÛ often has darker tops, lighter bellies)
        float grad = clamp(v_normal.y * 0.5 + 0.5, 0.0, 1.0);
        albedo *= mix(vec3(0.6, 0.7, 0.8), vec3(1.0), grad);
        
        vec3 lit = albedo * diff * sunColor;
        vec3 final = lit + ambientColor * albedo + sss_color * sss_mask * sunColor + rim * sunColor * 0.5;
        
        // Depth-based fogging/density (Oceanic feel)
        float depth = length(v_pos) * 0.005;
        vec3 water_tint = vec3(0.0, 0.1, 0.2);
        final = mix(final, water_tint, clamp(depth, 0.0, 0.7));
        
        gl_FragColor = vec4(final, base_color.a);
    }
