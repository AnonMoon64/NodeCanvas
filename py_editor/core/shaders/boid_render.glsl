#version 430 core

/* 
 * OPTIMIZATION NOTE:
 * Indirect Instance Rendering.
 * Thousands of boids are drawn with a single GPU command.
 * Positions and orientations are read from the simulation SSBO,
 * avoiding the bottleneck of per-object CPU updates or uniform updates.
 */

layout(location = 0) in vec3 pos;
layout(location = 1) in vec3 normal;

struct Boid {
    vec4 pos; // xyz=position, w=intensity
    vec4 vel; // xyz=velocity, w=type (0=fish, 1=bird)
};

layout(std430, binding = 0) buffer BoidBuffer {
    Boid boids[];
};

uniform mat4 projection;
uniform mat4 view;
uniform float time;

out vec3 v_normal;
out vec3 v_color;

void main() {
    Boid b = boids[gl_InstanceID];
    vec3 bPos = b.pos.xyz;
    vec3 bVel = b.vel.xyz;
    float type = b.vel.w;
    float intensity = b.pos.w;

    // Orientation
    vec3 fwd = normalize(bVel);
    vec3 up = vec3(0, 1, 0);
    if (abs(fwd.y) > 0.99) up = vec3(1, 0, 0);
    vec3 rgt = normalize(cross(up, fwd));
    up = cross(fwd, rgt);
    mat3 rot = mat3(rgt, up, fwd);

    vec3 v = pos;
    // Procedural Tweaks
    if (type < 0.5) {
        // FISH: 4-layer motion (Yaw, Side, Roll, Flag)
        float d = v.z + 0.5; // X-axis was spine in previous turned, but let's assume Z-scale for boid mesh
        float mask = smoothstep(0.0, 1.0, d);
        
        // 1. Yaw
        float yaw = sin(time * 8.0) * 0.1 * intensity;
        v = mat3(cos(yaw), 0, sin(yaw), 0, 1, 0, -sin(yaw), 0, cos(yaw)) * v;
        
        // 2. Side-to-side
        v.x += sin(time * 12.0 - d * 5.0) * 0.05 * mask * intensity;
        
        // 3. Roll
        float roll = sin(time * 10.0 - d * 4.0) * 0.1 * mask * intensity;
        v = mat3(1, 0, 0, 0, cos(roll), -sin(roll), 0, sin(roll), cos(roll)) * v;

        // 4. Secondary Yaw (Flag)
        float flag = sin(time * 15.0 - d * 6.0) * 0.05 * mask * intensity;
        v = mat3(cos(flag), 0, sin(flag), 0, 1, 0, -sin(flag), 0, cos(flag)) * v;
        
        v_color = vec3(0.3, 0.6, 0.8);
    } else {
        // BIRD: 4-layer motion (Flap, Sway, Bank, Tail)
        float wings = abs(v.x);
        float freq = 20.0;
        float flap_mask = smoothstep(0.1, 1.0, wings);
        
        // 1. Primary Wing Flap
        float flap = sin(time * freq) * (wings * 1.5) * intensity;
        v.y += flap;
        
        // 2. Wing-tip Lag (Secondary motion)
        float tip_lag = sin(time * freq - wings * 2.0) * 0.3 * intensity;
        v.y += tip_lag * flap_mask;

        // 3. Banking & Roll (Est. from lateral velocity)
        // We look at the relation between world-up and local-right
        float bank = sin(time * 5.0) * 0.05 * intensity; // Subtle sway
        v = mat3(cos(bank), -sin(bank), 0, sin(bank), cos(bank), 0, 0, 0, 1) * v;
        
        // 4. Pitch & Tail Bob
        float pitch = -fwd.y * 0.5 + sin(time * freq) * 0.05 * intensity;
        v = mat3(1, 0, 0, 0, cos(pitch), -sin(pitch), 0, sin(pitch), cos(pitch)) * v;
        
        v_color = vec3(0.8, 0.4, 0.2);
    }

    vec3 worldPos = rot * v + bPos;
    v_normal = rot * normal;
    
    gl_Position = projection * view * vec4(worldPos, 1.0);
}
