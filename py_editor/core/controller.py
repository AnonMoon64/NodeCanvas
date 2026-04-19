"""
controller.py

Base controller class and its derivatives for AI and Player control.
"""
import math
import random

class BaseController:
    """Base class for all object controllers with physics tracking."""
    def __init__(self, owner=None):
        self.owner = owner # Expecting a SceneObject
        self.target = None
        self.speed = 5.0
        self.active = True
        
        self.velocity = [0.0, 0.0, 0.0]
        self.acceleration = [0.0, 0.0, 0.0]
        self.last_pos = list(owner.position) if owner else [0,0,0]

    def update(self, dt):
        """Override this in subclasses."""
        pass

    def _parent(self):
        pid = getattr(self.owner, 'parent_id', None)
        if not pid:
            return None
        scene = getattr(self.owner, '_scene_objects_ref', None)
        if scene is None:
            # Walk up via _parent attribute if the engine linked it.
            return getattr(self.owner, '_parent', None)
        for o in scene:
            if getattr(o, 'id', None) == pid:
                return o
        return None

    def _to_world(self, local_pos):
        """Translate a parent-local position to world space (translation only).
        Rotation/scale on spawners/groups is not currently composed into
        controller updates — keep this cheap and correct for the common case."""
        p = self._parent()
        if p is None:
            return [local_pos[0], local_pos[1], local_pos[2]]
        pp = p.position
        return [local_pos[0] + pp[0], local_pos[1] + pp[1], local_pos[2] + pp[2]]

    def _to_local(self, world_pos):
        p = self._parent()
        if p is None:
            return [world_pos[0], world_pos[1], world_pos[2]]
        pp = p.position
        return [world_pos[0] - pp[0], world_pos[1] - pp[1], world_pos[2] - pp[2]]

    def update_physics(self, dt):
        """Calculate real-time velocity and acceleration for shader uniforms."""
        if self.__class__.__name__ in ("AIGPUFishController", "AIGPUBirdController"):
            return # Skip base physics for GPU-driven agents to avoid fighting
        if not self.owner or dt <= 0: return
        curr = self.owner.position
        new_vel = [(curr[i] - self.last_pos[i]) / dt for i in range(3)]
        
        # Smoothing acceleration
        new_accel = [(new_vel[i] - self.velocity[i]) / dt for i in range(3)]
        self.acceleration = [self.acceleration[i] * 0.9 + new_accel[i] * 0.1 for i in range(3)]
        self.velocity = new_vel
        self.last_pos = list(curr)
        # Sync to owner so shaders / other systems can read it
        try:
            self.owner.velocity = list(self.velocity)
            self.owner.acceleration = list(self.acceleration)
        except Exception:
            pass
        
        # Intensity = Base + Accel contribution
        acc_mag = math.sqrt(sum(a*a for a in self.acceleration))
        intensity = 0.5 + min(acc_mag * 0.1, 2.0)
        
        if 'shader_params' not in self.owner.__dict__:
            self.owner.shader_params = {}
        self.owner.shader_params['intensity'] = intensity

    def move_to(self, target_pos, dt):
        if not self.owner or not self.active: return
        curr = self.owner.position
        dir_vec = [target_pos[i] - curr[i] for i in range(3)]
        dist = math.sqrt(sum(d*d for d in dir_vec))
        if dist > 0.01:
            step = (self.speed * dt)
            norm_dir = [d/dist for d in dir_vec]
            for i in range(3):
                self.owner.position[i] += norm_dir[i] * min(step, dist)
            # Face target
            self.owner.rotation[1] = math.degrees(math.atan2(norm_dir[0], norm_dir[2]))

class AIController(BaseController):
    """Boids-based AI for schooling/flocking fish."""
    def __init__(self, owner=None):
        super().__init__(owner)
        self.wander_timer = 0.0
        self.wander_range = 25.0
        
        # Boid Weights
        self.sep_weight = 1.5
        self.ali_weight = 1.0
        self.coh_weight = 1.0
        self.target_weight = 0.5
        
        self.neighbor_dist = 10.0
        self.flock = [] # Should be populated by simulation manager

    def update(self, dt):
        if not self.owner or not self.active: return
        self.update_physics(dt)
        
        # 1. Boid Forces
        sep = [0.0, 0.0, 0.0]
        ali = [0.0, 0.0, 0.0]
        coh = [0.0, 0.0, 0.0]
        count = 0
        
        my_pos = self.owner.position
        for other in self.flock:
            if other == self: continue
            dist = math.sqrt(sum((my_pos[i] - other.owner.position[i])**2 for i in range(3)))
            if 0 < dist < self.neighbor_dist:
                # Separation
                diff = [(my_pos[i] - other.owner.position[i]) / dist for i in range(3)]
                for i in range(3): sep[i] += diff[i]
                # Alignment
                for i in range(3): ali[i] += other.velocity[i]
                # Cohesion
                for i in range(3): coh[i] += other.owner.position[i]
                count += 1
        
        # 2. Wandering Target
        self.wander_timer -= dt
        if self.wander_timer <= 0:
            self.wander_timer = random.uniform(2.0, 6.0)
            self.target = [
                random.uniform(-self.wander_range, self.wander_range),
                my_pos[1], # Keep height stable
                random.uniform(-self.wander_range, self.wander_range)
            ]
        
        # 3. Combine Steering
        steer = [0.0, 0.0, 0.0]
        if count > 0:
            for i in range(3):
                ali[i] /= count
                coh[i] = (coh[i]/count - my_pos[i])
            # Apply weights
            for i in range(3):
                steer[i] = (sep[i]*self.sep_weight + ali[i]*self.ali_weight + coh[i]*self.coh_weight)
        
        # Add target steering
        if self.target:
            t_dir = [self.target[i] - my_pos[i] for i in range(3)]
            t_dist = math.sqrt(sum(d*d for d in t_dir))
            if t_dist > 0.1:
                for i in range(3): steer[i] += (t_dir[i]/t_dist) * self.target_weight

        # 4. Integrate steering into position
        s_mag = math.sqrt(sum(s*s for s in steer))
        if s_mag > 0.01:
            for i in range(3):
                self.owner.position[i] += (steer[i]/s_mag) * self.speed * dt
            # Rotate towards movement
            self.owner.rotation[1] = math.degrees(math.atan2(steer[0], steer[2]))

class PlayerController(BaseController):
    """Controller that responds to direct input axes."""
    def __init__(self, owner=None):
        super().__init__(owner)
        self.input_axes = [0.0, 0.0] # [Forward/Back, Left/Right]

    def update(self, dt):
        if not self.owner or not self.active: return
        fwd_val = self.input_axes[0]
        side_val = self.input_axes[1]
        
        if abs(fwd_val) > 0.1 or abs(side_val) > 0.1:
            yaw = math.radians(self.owner.rotation[1])
            fwd = [math.sin(yaw), 0, math.cos(yaw)]
            rgt = [math.cos(yaw), 0, -math.sin(yaw)]
            
            for i in range(3):
                self.owner.position[i] += (fwd[i] * fwd_val + rgt[i] * side_val) * self.speed * dt

class AIGPUFishController(AIController):
    """GPU-Accelerated Fish Controller."""
    def __init__(self, owner=None):
        super().__init__(owner)
        self.gpu_idx = -1
        self._registered = False

    def update(self, dt):
        if not self.owner or not self.active: return
        from py_editor.core.boid_system_gpu import GPUBoidManager
        mgr = GPUBoidManager.get_instance()
        
        if not self._registered:
            if not mgr.ssbo_boids: return # Wait for GPU initialization before registering
            vel = [random.uniform(-1, 1) for _ in range(3)]
            # Seed the GPU boid in world space — controllers written after may
            # be parented (e.g. under a spawner), so we resolve the world-space
            # start position here and then keep converting back to parent-local
            # on readback.
            world_start = self._to_world(self.owner.position)
            self.gpu_idx = mgr.add_boid(world_start, vel, boid_type=0.0)
            print(f"[CONTROLLER] Registered {self.owner.name} (GPU ID: {self.gpu_idx})")
            self._registered = True
            self.update_ticks = 0
            self.readback_interval = 1 
            self.last_sync_vel = list(vel)
            self.velocity = list(vel)
            self.acceleration = [0,0,0]
        
        self.update_ticks += 1
        if self.update_ticks % self.readback_interval == 0:
            res = mgr.get_boid_pos_vel(self.gpu_idx)
            if res:
                pos, vel, gpu_intensity = res
                
                # GPU sim operates in world space; the renderer composes this
                # with the parent's transform. Convert back to parent-local so
                # a spawner-parented fish doesn't get translated twice.
                local = self._to_local(pos)
                # Keep schooling fish below the spawner — a spawner sits at
                # the water surface and the shoal should stay submerged. If a
                # parent exists, clamp local Y to <= 0 (beneath the parent).
                if getattr(self.owner, 'parent_id', None):
                    if local[1] > 0.0:
                        local[1] = 0.0
                self.owner.position = local
                
                # Derive Acceleration from Velocity change
                dt_sim = max(dt, 0.001)
                dt_sync = dt_sim * self.readback_interval
                accel = [(vel[i] - self.last_sync_vel[i]) / max(dt_sync, 0.001) for i in range(3)]
                
                # Smoothing / Filter
                self.velocity = [self.velocity[i] * 0.5 + vel[i] * 0.5 for i in range(3)]
                self.acceleration = [self.acceleration[i] * 0.8 + accel[i] * 0.2 for i in range(3)]
                
                self.last_sync_vel = list(vel)
                
                # Sync back to SceneObject for Shaders
                self.owner.velocity = list(self.velocity)
                self.owner.acceleration = list(self.acceleration)
                
                # Rotation: face velocity direction. The fish mesh's forward
                # axis is configured via shader_params (forward_axis=0/1/2 for
                # X/Y/Z, invert_axis=1 flips it to -axis). Compute yaw/pitch
                # accordingly so the mesh's nose actually leads.
                sp = getattr(self.owner, 'shader_params', {}) or {}
                fa = int(float(sp.get('forward_axis', 2.0)))
                inv = float(sp.get('invert_axis', 0.0)) > 0.5
                vx, vy, vz = vel[0], vel[1], vel[2]
                if inv:
                    vx, vy, vz = -vx, -vy, -vz
                if fa == 0:      # forward = ±X
                    fwd_plane = math.sqrt(vy * vy + vz * vz)
                    yaw_deg   = math.degrees(math.atan2(-vz, vx))
                    pitch_deg = math.degrees(math.atan2(vy, fwd_plane))
                elif fa == 1:    # forward = ±Y (uncommon for fish, kept for completeness)
                    fwd_plane = math.sqrt(vx * vx + vz * vz)
                    yaw_deg   = math.degrees(math.atan2(vx, vz))
                    pitch_deg = math.degrees(math.atan2(-vy, fwd_plane))
                else:            # forward = ±Z (fish prefab default)
                    fwd_plane = math.sqrt(vx * vx + vz * vz)
                    if fwd_plane > 0.01:
                        yaw_deg   = math.degrees(math.atan2(vx, vz))
                        pitch_deg = -math.degrees(math.atan2(vy, fwd_plane))
                    else:
                        yaw_deg   = self.owner.rotation[1]
                        pitch_deg = self.owner.rotation[0]
                # Smooth rotation so sharp velocity flips don't spin the mesh
                # 180° between frames (shortest-arc interpolation on yaw).
                dy = ((yaw_deg - self.owner.rotation[1]) + 540.0) % 360.0 - 180.0
                self.owner.rotation[1] += dy * 0.25
                self.owner.rotation[0] += (pitch_deg - self.owner.rotation[0]) * 0.25
                
                # Apply dynamic shader params: intensity amplifies the wiggle;
                # speed drives the swim-cycle phase rate. On sharp turns the
                # acceleration magnitude spikes — push the cycle faster so the
                # tail visibly whips rather than gliding at cruise cadence.
                if 'shader_params' not in self.owner.__dict__:
                    self.owner.shader_params = {}
                sp = self.owner.shader_params
                base_speed = float(sp.get('_base_speed', sp.get('speed', 6.0)))
                sp['_base_speed'] = base_speed
                accel_mag = math.sqrt(sum(a * a for a in self.acceleration))
                # Smooth the speed bump so the shader doesn't strobe — attack
                # fast (0.4), decay slow (0.08).
                target_speed = base_speed + min(accel_mag * 0.25, base_speed * 1.5)
                cur = float(sp.get('speed', base_speed))
                k = 0.4 if target_speed > cur else 0.08
                sp['speed'] = cur + (target_speed - cur) * k
                sp['intensity'] = gpu_intensity
                
                if self.update_ticks % 100 == 0:
                    print(f"[GPU FISH] Sync ID:{self.gpu_idx} Pos:{[round(p,1) for p in pos]} Int:{round(gpu_intensity, 2)}")

class AIGPUBirdController(AIController):
    """GPU-Accelerated Bird Controller."""
    def __init__(self, owner=None):
        super().__init__(owner)
        self.gpu_idx = -1
        self._registered = False

    def update(self, dt):
        if not self.owner or not self.active: return
        from py_editor.core.boid_system_gpu import GPUBoidManager
        mgr = GPUBoidManager.get_instance()
        
        if not self._registered:
            vel = [random.uniform(-1, 1) * 2.0 for _ in range(3)]
            self.gpu_idx = mgr.add_boid(self.owner.position, vel, boid_type=1.0)
            self._registered = True
            self.update_ticks = random.randint(0, 5)
            self.readback_interval = getattr(self, 'readback_interval', 2)
            self.last_sync_vel = [0,0,0]
            
        self.update_ticks += 1
        if self.update_ticks % self.readback_interval == 0:
            res = mgr.get_boid_pos_vel(self.gpu_idx)
            if res:
                pos, vel = res
                self.owner.position = list(pos)
                
                # Physics Readback
                dt_sync = dt * self.readback_interval
                accel = [(vel[i] - self.last_sync_vel[i]) / max(dt_sync, 0.001) for i in range(3)]
                self.velocity = vel
                self.acceleration = accel
                self.last_sync_vel = list(vel)
                
                self.owner.velocity = list(self.velocity)
                self.owner.acceleration = list(self.acceleration)
                
                # Face velocity direction 
                if abs(vel[0]) > 0.01 or abs(vel[2]) > 0.01:
                    self.owner.rotation[1] = math.degrees(math.atan2(vel[0], vel[2]))
                    speed_xz = math.sqrt(vel[0]*vel[0] + vel[2]*vel[2])
                    self.owner.rotation[0] = -math.degrees(math.atan2(vel[1], speed_xz))

                if 'shader_params' not in self.owner.__dict__: self.owner.shader_params = {}
                acc_mag = math.sqrt(sum(a*a for a in self.acceleration))
                self.owner.shader_params['intensity'] = 0.5 + min(acc_mag * 0.1, 2.0)
