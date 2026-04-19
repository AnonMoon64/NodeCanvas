// -- VERTEX --
#version 120
    
    uniform float time;
    uniform float wave_speed;
    uniform float wave_scale;
    uniform float wave_steepness;
    uniform vec3 grid_origin;
    uniform float grid_chunk_size;
    uniform float time_of_day;
    
    varying vec3 v_normal;
    varying vec3 v_pos;
    varying float v_foam;
    varying vec3 v_view_dir;

    vec3 gerstner(vec3 pos, float wlen, float ampl, float speed, vec2 dir, float steep, float t, inout vec3 tangent, inout vec3 binormal) {
        float k = 2.0 * 3.14159 / wlen;
        float c = sqrt(9.81 / k);
        float phase = k * (dot(dir, pos.xz) - (c * speed * 2.0 * t));
        float a = ampl * wave_scale;
        float s = clamp(steep * wave_steepness * 2.0, 0.0, 1.0);
        
        vec3 d = vec3(0.0);
        d.x = dir.x * (a * s) * cos(phase);
        d.z = dir.y * (a * s) * cos(phase);
        d.y = a * sin(phase);
        
        float wa = k * a;
        tangent += vec3(-dir.x * dir.x * s * wa * sin(phase), dir.x * wa * cos(phase), -dir.x * dir.y * s * wa * sin(phase));
        binormal += vec3(-dir.x * dir.y * s * wa * sin(phase), dir.y * wa * cos(phase), -dir.y * dir.y * s * wa * sin(phase));
        return d;
    }

    void main() {
        vec3 world_p = (gl_Vertex.xyz * grid_chunk_size) + grid_origin;
        vec3 offset = vec3(0.0);
        vec3 tangent = vec3(1.0, 0.0, 0.0);
        vec3 binormal = vec3(0.0, 0.0, 1.0);

        offset += gerstner(world_p, 400.0, 10.0, 0.5, normalize(vec2(1.0, 0.1)), 0.6, time, tangent, binormal);
        offset += gerstner(world_p, 200.0, 6.0,  0.8, normalize(vec2(0.3, 0.9)), 0.7, time, tangent, binormal);

        vec3 displaced = gl_Vertex.xyz;
        displaced.x += offset.x / grid_chunk_size;
        displaced.z += offset.z / grid_chunk_size;
        displaced.y += offset.y;
        
        v_pos = world_p + offset;
        v_normal = normalize(cross(binormal, tangent));
        v_foam = pow(clamp(offset.y*0.1+0.5, 0.0, 1.0), 8.0);

        vec4 eye_pos = gl_ModelViewMatrix * vec4(displaced, 1.0);
        v_view_dir = normalize(-eye_pos.xyz);
        gl_Position = gl_ModelViewProjectionMatrix * vec4(displaced, 1.0);
    }

// -- FRAGMENT --
#version 120
    uniform vec4 ocean_color;
    uniform float ocean_opacity;
    uniform float foam_amount;
    uniform float time_of_day;
    uniform vec3 cam_pos;
    varying vec3 v_normal;
    varying vec3 v_pos;
    varying float v_foam;
    varying vec3 v_view_dir;

    void main() {
        vec3 normal = normalize(v_normal);
        float ndotv = max(dot(normal, v_view_dir), 0.0);
        
        // --- Day/Night Lighting ---
        float day_ratio = max(sin(time_of_day * 3.14159), 0.0);
        vec3 base_water = mix(ocean_color.rgb*0.1, ocean_color.rgb, v_pos.y*0.05+0.5);
        base_water *= day_ratio; // Darken at night
        
        float fresnel = pow(1.0 - ndotv, 4.0);
        // Same fix as the FFT shader — narrow the orange contribution so dawn/dusk
        // doesn't paint every fresnel reflection brown.
        float sunset_t = pow(clamp(1.0 - abs(sin(time_of_day * 3.14159)) * 1.4, 0.0, 1.0), 2.0);
        vec3 sky_ref = mix(vec3(0.7, 0.8, 1.0), vec3(1.0, 0.5, 0.2), sunset_t * 0.5);
        sky_ref *= day_ratio;
        
        vec3 rgb = mix(base_water, sky_ref, fresnel*0.5);
        rgb = mix(rgb, vec3(1.0), v_foam * foam_amount * day_ratio);
        
        float dist = length(v_pos - cam_pos);
        float fog = clamp((dist-1000.0)/800.0, 0.0, 1.0);
        vec3 fog_color = mix(vec3(0.01), vec3(0.05, 0.08, 0.1), day_ratio);
        gl_FragColor = vec4(mix(rgb, fog_color, fog), ocean_opacity);
    }
