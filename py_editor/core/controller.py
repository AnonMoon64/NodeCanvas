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

    def update_physics(self, dt):
        """Calculate real-time velocity and acceleration for shader uniforms."""
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

class AIGPUFishController(BaseController):
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
            vel = [random.uniform(-1, 1) for _ in range(3)]
            self.gpu_idx = mgr.add_boid(self.owner.position, vel, boid_type=0.0)
            self._registered = True
        
        # We don't update position on CPU here to maintain GPU performance.
        # The GPUBoidManager handles the simulation.

class AIGPUBirdController(BaseController):
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
