// -- VERTEX --
#version 330 compatibility
    layout(location = 0) in vec3 pos;
    layout(location = 2) in vec3 norm;
    layout(location = 8) in vec2 uv;
    
    uniform mat4 gl_ModelViewProjectionMatrix;
    uniform mat4 gl_ModelViewMatrix;
    uniform mat3 gl_NormalMatrix;
    uniform vec2 u_tiling;
    
    out vec3 v_world_pos;
    out vec3 v_normal;
    out vec2 v_uv;
    out mat3 v_tbn;

    void main() {
        v_world_pos = (gl_ModelViewMatrix * vec4(pos, 1.0)).xyz;
        v_normal = normalize(gl_NormalMatrix * norm);
        v_uv = uv * u_tiling;
        
        // Calculate TBN matrix for normal mapping
        vec3 tangent = normalize(gl_NormalMatrix * vec3(1.0, 0.0, 0.0));
        vec3 bitangent = cross(v_normal, tangent);
        v_tbn = mat3(tangent, bitangent, v_normal);
        
        gl_Position = gl_ModelViewProjectionMatrix * vec4(pos, 1.0);
    }

// -- FRAGMENT --
#version 330 compatibility
    
    uniform sampler2D albedoMap;
    uniform sampler2D normalMap;
    uniform sampler2D metallicMap;
    uniform sampler2D roughnessMap;
    uniform sampler2D aoMap;
    
    uniform vec4 u_base_color;
    uniform float u_metallic;
    uniform float u_roughness;
    uniform vec3 sunDir;
    uniform vec3 sunColor;
    uniform vec3 ambientColor;
    uniform vec3 cam_pos;
    
    uniform bool hasAlbedo;
    uniform bool hasNormal;
    uniform bool hasMetallic;
    uniform bool hasRoughness;
    uniform bool hasAO;

    in vec3 v_world_pos;
    in vec3 v_normal;
    in vec2 v_uv;
    in mat3 v_tbn;

    const float PI = 3.14159265359;

    // PBR Functions
    float DistributionGGX(vec3 N, vec3 H, float roughness) {
        float a = roughness*roughness;
        float a2 = a*a;
        float NdotH = max(dot(N, H), 0.0);
        float NdotH2 = NdotH*NdotH;
        float num = a2;
        float denom = (NdotH2 * (a2 - 1.0) + 1.0);
        denom = PI * denom * denom;
        return num / denom;
    }

    float GeometrySchlickGGX(float NdotV, float roughness) {
        float r = (roughness + 1.0);
        float k = (r*r) / 8.0;
        float num = NdotV;
        float denom = NdotV * (1.0 - k) + k;
        return num / denom;
    }

    float GeometrySmith(vec3 N, vec3 V, vec3 L, float roughness) {
        float NdotV = max(dot(N, V), 0.0);
        float NdotL = max(dot(N, L), 0.0);
        float ggx2 = GeometrySchlickGGX(NdotV, roughness);
        float ggx1 = GeometrySchlickGGX(NdotL, roughness);
        return ggx1 * ggx2;
    }

    vec3 fresnelSchlick(float cosTheta, vec3 F0) {
        return F0 + (1.0 - F0) * pow(clamp(1.0 - cosTheta, 0.0, 1.0), 5.0);
    }

    void main() {
        vec3 N = normalize(v_normal);
        if (hasNormal) {
            vec3 map_normal = texture(normalMap, v_uv).rgb * 2.0 - 1.0;
            N = normalize(v_tbn * map_normal);
        }
        
        vec3 V = normalize(cam_pos - v_world_pos);
        vec3 L = normalize(sunDir);
        vec3 H = normalize(V + L);

        vec3 albedo = hasAlbedo ? texture(albedoMap, v_uv).rgb * u_base_color.rgb : u_base_color.rgb;
        float metallic = hasMetallic ? texture(metallicMap, v_uv).r : u_metallic;
        float roughness = hasRoughness ? texture(roughnessMap, v_uv).r : u_roughness;
        float ao = hasAO ? texture(aoMap, v_uv).r : 1.0;

        vec3 F0 = vec3(0.04); 
        F0 = mix(F0, albedo, metallic);

        // Reflectance equation
        float NDF = DistributionGGX(N, H, roughness);   
        float G   = GeometrySmith(N, V, L, roughness);      
        vec3 F    = fresnelSchlick(max(dot(H, V), 0.0), F0);
           
        vec3 numerator    = NDF * G * F; 
        float denominator = 4.0 * max(dot(N, V), 0.0) * max(dot(N, L), 0.0) + 0.0001;
        vec3 specular = numerator / denominator;
        
        vec3 kS = F;
        vec3 kD = vec3(1.0) - kS;
        kD *= 1.0 - metallic;	  

        float NdotL = max(dot(N, L), 0.0);        

        vec3 ambient = ambientColor * albedo * ao;
        vec3 radiance = sunColor * 3.0; // Scaled radiance from unified sun

        vec3 result = (kD * albedo / PI + specular) * radiance * NdotL;
        result += ambient;

        // Tone mapping & Gamma correction
        result = result / (result + vec3(1.0));
        result = pow(result, vec3(1.0/2.2));

        gl_FragColor = vec4(result, u_base_color.a);
    }
