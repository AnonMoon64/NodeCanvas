import json
from pathlib import Path
from PyQt6.QtCore import QObject, QTimer, pyqtSignal
from py_editor.core.node_templates import get_all_templates
from py_editor.backends.interpreter import execute_canvas_graph, ExecutionContext, InterpreterBackend

class SimulationController(QObject):
    """Manages the execution lifecycle of a logic graph."""
    state_changed = pyqtSignal(bool) # is_running
    stepped = pyqtSignal(int) # ir_node_id
    
    def __init__(self, main_window):
        super().__init__(main_window)
        self.main_window = main_window
        self.is_running = False
        self.is_paused = False
        self.ctx = None
        self.contexts = {}  # Per-object logic contexts: obj_id -> [(ir_module, ctx), ...]
        self.backend = InterpreterBackend()
        self.logger = None # Callback for live prints
        
        # Simulation Timer
        self._timer = QTimer()
        self._timer.timeout.connect(self._tick)
        self._timer.setInterval(100) # 10Hz for logic ticks
        self._last_tick_time = None
        # Navigation manager (optional)
        try:
            from py_editor.core.navigation_manager import get_manager
            self._nav_manager = get_manager()
            # Set backend so manager can call into interpreter when needed
            try:
                self._nav_manager.set_backend(self.backend)
            except Exception:
                pass
        except Exception:
            self._nav_manager = None

    def start(self, graph_data, templates, variables):
        self.is_running = True
        self.is_paused = False
        self.ctx = ExecutionContext()
        # Hook live logger
        if self.logger:
            self.ctx.logger_callback = self.logger
        # Pre-populate variables
        self.ctx.variables = {name: info['value'] for name, info in variables.items()}
        
        # Initial compilation
        self.ir_module = self.backend.canvas_to_ir(graph_data, templates)
        self._last_tick_time = None
        # Boot per-object logic when running inside the SceneEditor (editor viewport)
        try:
            from pathlib import Path
            import json
            self.contexts = {}
            viewport = getattr(self.main_window, 'viewport', None)
            if viewport and hasattr(viewport, 'scene_objects'):
                for obj in viewport.scene_objects:
                    # Support both logic_path (legacy) and logic_list (modular)
                    logics = getattr(obj, 'logic_list', [])
                    legacy_path = getattr(obj, 'logic_path', None)
                    if legacy_path and legacy_path not in logics:
                        logics = [legacy_path] + logics
                    
                    # RUNTIME MIGRATION: Ensure all oceans have the spray logic
                    if obj.obj_type == 'ocean':
                        default_spray = "py_editor/nodes/graphs/OceanSpray.logic"
                        if default_spray not in logics:
                            print(f"[SIM] Migration: Injecting spray logic into {obj.name}")
                            logics.append(default_spray)
                            obj.logic_list = logics
                    
                    if not logics:
                        continue

                    for logic_path in logics:
                        try:
                            p = Path(logic_path)
                            if not p.is_file():
                                print(f"[SIM] Logic file not found: {logic_path}")
                                continue
                            with open(p, 'r', encoding='utf-8') as f:
                                graph = json.load(f)
                            ir_mod = self.backend.canvas_to_ir(graph, templates)
                            obj_ctx = ExecutionContext()
                            obj_ctx.ir_module = ir_mod
                            obj_ctx.variables['self'] = obj.id
                            try:
                                obj_ctx.variables['__scene_objects__'] = {so.id: so for so in viewport.scene_objects}
                            except Exception:
                                obj_ctx.variables['__scene_objects__'] = {}
                            self.contexts.setdefault(obj.id, []).append((ir_mod, obj_ctx))
                            # Run initial pass (OnStart)
                            self.backend.execute_ir(ir_mod, obj_ctx)
                            print(f"[SIM] Booted logic {p.name} on {obj.name}")
                        except Exception as e:
                            import traceback
                            traceback.print_exc()
                            print(f"[SIM] Failed to boot logic for {getattr(obj, 'name', obj)}: {e}")
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"[SIM] Simulation startup fatal error: {e}")
        self._timer.start()
        self.state_changed.emit(True)

    def refresh(self, templates=None):
        """Re-scans the scene for objects and updates logic contexts without stopping the timer."""
        if not self.is_running:
            return
            
        # Log removed
        templates = templates or get_all_templates()
        viewport = getattr(self.main_window, 'viewport', None)
        if not viewport or not hasattr(viewport, 'scene_objects'):
            return

        # Scans for new objects or updated logic_lists
        for obj in viewport.scene_objects:
            logics = getattr(obj, 'logic_list', [])
            if not logics and obj.obj_type == 'ocean':
                logics = ["py_editor/nodes/graphs/OceanSpray.logic"]
                obj.logic_list = logics

            if not logics:
                # Clear existing contexts if logic was removed (e.g. stopped raining)
                if obj.id in self.contexts:
                    del self.contexts[obj.id]
                continue

            # Determine if we need to boot or re-boot logic
            existing_contexts = self.contexts.get(obj.id, [])
            if not existing_contexts:
                needs_boot = True
            else:
                # Basic check: do we have the right number of modules?
                needs_boot = len(existing_contexts) < len(logics)

            if needs_boot:
                # Clear stale if any
                self.contexts[obj.id] = []
                for logic_path in logics:
                    try:
                        p = Path(logic_path)
                        if not p.is_file(): continue
                        with open(p, 'r', encoding='utf-8') as f:
                            graph = json.load(f)
                        ir_mod = self.backend.canvas_to_ir(graph, templates)
                        obj_ctx = ExecutionContext()
                        obj_ctx.ir_module = ir_mod
                        obj_ctx.variables['self'] = obj.id
                        obj_ctx.variables['__scene_objects__'] = {so.id: so for so in viewport.scene_objects}
                        self.contexts.setdefault(obj.id, []).append((ir_mod, obj_ctx))
                        self.backend.execute_ir(ir_mod, obj_ctx)
                        print(f"[SIM] Live-Booted logic {p.name} on {obj.name}")
                    except Exception as e:
                        print(f"[SIM] Failed to live-boot logic for {obj.name}: {e}")
            else:
                # Update scene object map for existing contexts
                for ir_mod, obj_ctx in self.contexts[obj.id]:
                    obj_ctx.variables['__scene_objects__'] = {so.id: so for so in viewport.scene_objects}

    def stop(self):
        self.is_running = False
        self._timer.stop()
        self.state_changed.emit(False)

    def pause(self, val):
        self.is_paused = val

    def step(self):
        if not self.ir_module: return
        # Execute one step
        self.backend.execute_ir_step(self.ir_module, self.ctx)
        # Notify UI to highlight or print
        self.stepped.emit(self.ctx.paused_at or 0)

    def run_once(self, graph_data, templates, variables):
        """Execute the graph exactly once and stop."""
        self.ctx = ExecutionContext()
        # Hook live logger
        if self.logger:
            self.ctx.logger_callback = self.logger
        # Reset triggered nodes so OnStart fires fresh
        self.ctx.triggered_nodes = set()
        self.ctx.variables = {name: info['value'] for name, info in variables.items()}
        ir_module = self.backend.canvas_to_ir(graph_data, templates)
        try:
            results = self.backend.execute_ir(ir_module, self.ctx)
            # print("[SIM] One-shot execution complete.")
            return results
        except Exception as e:
            print(f"[SIM ERROR] {e}")
            return {"error": str(e)}

    def _tick(self):
        if self.is_paused: return
        if not hasattr(self, '_tick_count'): self._tick_count = 0
        self._tick_count += 1
        
        # Periodically refresh to catch logic_list changes (e.g. Weather transitions)
        if self._tick_count % 60 == 0:
            self.refresh()
            
        import time
        now = time.time()
        if self._last_tick_time is None:
            self._last_tick_time = now
        dt = now - self._last_tick_time
        self._last_tick_time = now

        # Let nav manager advance tasks if controllers were attached
        try:
            if getattr(self, '_nav_manager', None):
                try:
                    self._nav_manager.update(dt)
                except Exception:
                    pass
        except Exception:
            pass

        try:
            # Prepare event context for this tick
            event_ctx = {"delta_time": dt}
            self.backend.module.event_context = event_ctx
            
            # Extract live camera position for spatial nodes
            cam_pos = (0,0,0)
            viewport = getattr(self.main_window, 'viewport', None)
            if viewport: cam_pos = tuple(viewport._cam3d.pos)
            self.ctx.variables['camera_pos'] = cam_pos
            
            # Execute global graph
            self.backend.execute_ir(self.ir_module, self.ctx)
            # Execute any per-object logic contexts (if present)
            for oid, ctx_pairs in list(getattr(self, 'contexts', {}).items()):
                for ir_mod, obj_ctx in list(ctx_pairs):
                    try:
                        obj_ctx.variables['camera_pos'] = cam_pos
                        # Link camera to object for spatial emitters (e.g. rain following player)
                        viewport = getattr(self.main_window, 'viewport', None)
                        if viewport:
                            scene_map = getattr(viewport, 'scene_map', {})
                            target_obj = scene_map.get(oid)
                            if target_obj:
                                target_obj._cam_pos_ref = cam_pos
                        
                        self.backend.execute_ir(ir_mod, obj_ctx)
                    except Exception as e:
                        print(f"[SIM] Error executing object logic for {oid}: {e}")
        except Exception as e:
            print(f"Simulation Error: {e}")
            self.stop()
