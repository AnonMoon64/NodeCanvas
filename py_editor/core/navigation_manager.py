"""
navigation_manager.py

Lightweight navigation task manager used by the runtime and interpreter.

It stores active MoveTo tasks registered by the interpreter and advances
them each tick by driving the object's controller. When a task completes
or fails it triggers the connected exec-pin branch via the IRBackend's
trigger_output helper.

This is intentionally small and engine-agnostic: the runtime must call
`NavigationManager.get_manager().set_backend(...)` and
`NavigationManager.get_manager().set_controllers(...)` during init.
"""
import time
import math
from typing import Dict, Any


class NavigationManager:
    def __init__(self):
        self.backend = None
        self.controllers = {}  # owner_id -> controller instance
        self.tasks: Dict[int, Dict[str, Any]] = {}
        self._next_task_id = 1

    def set_backend(self, backend):
        self.backend = backend

    def set_controllers(self, controllers: Dict[str, Any]):
        self.controllers = controllers or {}

    def add_task(self, ir_module, ctx, source_node_id, owner_id, target_pos, speed=5.0, acceptable_distance=0.5, on_complete_pin='onComplete', on_failed_pin='onFailed'):
        tid = self._next_task_id
        self._next_task_id += 1
        task = {
            'id': tid,
            'owner_id': owner_id,
            'target_pos': tuple(target_pos) if target_pos is not None else None,
            'speed': float(speed) if speed is not None else 5.0,
            'acceptable_distance': float(acceptable_distance) if acceptable_distance is not None else 0.5,
            'ir_module': ir_module,
            'ctx': ctx,
            'source_node_id': source_node_id,
            'on_complete_pin': on_complete_pin,
            'on_failed_pin': on_failed_pin,
            'created_at': time.time(),
            'status': 'active'
        }
        self.tasks[tid] = task
        return tid

    def remove_task(self, tid):
        if tid in self.tasks:
            del self.tasks[tid]

    def update(self, dt: float):
        """Advance all active navigation tasks by dt seconds.

        This will call the controller's `move_to` helper and detect arrival.
        When a task finishes it triggers the connected exec branch via
        IRBackend.trigger_output.
        """
        to_complete = []
        to_fail = []

        for tid, task in list(self.tasks.items()):
            if task['status'] != 'active':
                continue

            owner_id = task['owner_id']
            ctrl = self.controllers.get(owner_id)
            if ctrl is None:
                # No controller bound for this object; fail the task
                to_fail.append((tid, 'no_controller'))
                continue

            target = task['target_pos']
            if target is None:
                to_fail.append((tid, 'no_target'))
                continue

            # Drive the controller towards the target
            try:
                # Prefer a specialised move_to(dt) if available
                if hasattr(ctrl, 'move_to'):
                    ctrl.move_to(target, dt)
                else:
                    # Fallback - nudge position directly
                    curr = ctrl.owner.position
                    dirv = [target[i] - curr[i] for i in range(3)]
                    dist = math.sqrt(sum(d*d for d in dirv))
                    if dist > 1e-6:
                        step = min(task['speed'] * dt, dist)
                        nd = [d/dist for d in dirv]
                        for i in range(3):
                            ctrl.owner.position[i] += nd[i] * step
            except Exception:
                to_fail.append((tid, 'controller_error'))
                continue

            # Check arrival
            owner_pos = getattr(ctrl.owner, 'position', None)
            if owner_pos is None:
                to_fail.append((tid, 'no_owner_pos'))
                continue

            dist_now = math.sqrt(sum((owner_pos[i] - task['target_pos'][i])**2 for i in range(3)))
            if dist_now <= task['acceptable_distance']:
                to_complete.append(tid)

        # Trigger completions and failures after iteration to avoid mutation during loop
        for tid in to_complete:
            task = self.tasks.get(tid)
            if not task:
                continue
            try:
                if self.backend:
                    # Trigger the on_complete branch connected to the MoveTo node
                    self.backend.trigger_output(task['ir_module'], task['ctx'], task['source_node_id'], task['on_complete_pin'])
            except Exception:
                pass
            self.remove_task(tid)

        for tid, reason in to_fail:
            task = self.tasks.get(tid)
            if not task:
                continue
            try:
                if self.backend:
                    self.backend.trigger_output(task['ir_module'], task['ctx'], task['source_node_id'], task['on_failed_pin'])
            except Exception:
                pass
            self.remove_task(tid)


# Module-level singleton
_manager = None

def get_manager():
    global _manager
    if _manager is None:
        _manager = NavigationManager()
    return _manager
