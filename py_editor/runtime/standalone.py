"""
standalone.py

Headless/Standalone runtime for NodeCanvas.
Boots a scene, attaches logic components, and runs the simulation.
"""
import sys
import os
import time
import json
from pathlib import Path
from PyQt6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QMessageBox
from PyQt6.QtCore import Qt, QTimer

# Add project root to sys.path so 'py_editor' imports work
parent_dir = Path(__file__).resolve().parent.parent.parent
if str(parent_dir) not in sys.path:
    sys.path.insert(0, str(parent_dir))

# Import internal core systems
try:
    from py_editor.ui.scene.scene_view import SceneViewport
    from py_editor.core.simulation_controller import SimulationController
    from py_editor.backends.interpreter import IRBackend, ExecutionContext
    from py_editor.core.node_templates import load_templates, get_all_templates
except ImportError:
    # Fallback for direct script execution
    from py_editor.ui.scene.scene_view import SceneViewport
    from py_editor.core.simulation_controller import SimulationController
    from py_editor.backends.interpreter import IRBackend, ExecutionContext
    from py_editor.core.node_templates import load_templates, get_all_templates

class StandaloneGameWindow(QMainWindow):
    def __init__(self, scene_data: dict):
        super().__init__()
        self.setWindowTitle("NodeCanvas Standalone Runtime")
        self.resize(1280, 720)
        
        # Central Viewport
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout(self.central_widget)
        self.layout.setContentsMargins(0, 0, 0, 0)
        
        self.viewport = SceneViewport(self)
        self.layout.addWidget(self.viewport)
        
        # Simulation Backend
        self.backend = IRBackend()
        self.contexts = {} # Object ID -> List of ExecutionContexts

        # Navigation manager (runtime tasks)
        try:
            from py_editor.core.navigation_manager import get_manager
            self.nav_manager = get_manager()
            self.nav_manager.set_backend(self.backend)
        except Exception:
            self.nav_manager = None
        
        # Load Templates
        load_templates()
        
        # Initialize Scene
        self.viewport.load_scene_data(scene_data)
        
        # Boot Logic Components
        self._boot_logic()
        
        # Start Ticking
        self.timer = QTimer()
        self.timer.timeout.connect(self._tick)
        self.timer.start(16) # 60 FPS target
        
        self.controllers = {} # obj.id -> BaseController
        # _init_controllers is now called via QTimer or initializeGL to ensure GL context
        
        self.start_time = time.time()
        self._last_tick_time = time.time()

    def _boot_logic(self):
        """Find all objects with a logic path and compile them."""
        objects = self.viewport.scene_objects
        templates = get_all_templates()
        
        for obj in objects:
            logic_path = getattr(obj, 'logic_path', None)
            if not logic_path or not Path(logic_path).is_file(): 
                continue
            
            self.contexts[obj.id] = []
            try:
                with open(logic_path, 'r', encoding='utf-8') as f:
                    graph_data = json.load(f)
                
                # Use the new IRBackend compiler
                ir_module = self.backend.canvas_to_ir(graph_data, templates)
                ctx = ExecutionContext()
                ctx.ir_module = ir_module
                ctx.variables['self'] = obj.id
                # Provide a mapping of scene objects for interpreter convenience
                try:
                    ctx.variables['__scene_objects__'] = {so.id: so for so in self.viewport.scene_objects}
                except Exception:
                    ctx.variables['__scene_objects__'] = {}
                
                self.contexts[obj.id].append((ir_module, ctx))
                print(f"[RUNTIME] Booted logic {Path(logic_path).name} on {obj.name}")
                
                # Execute initial pass (OnStart)
                self.backend.execute_ir(ir_module, ctx)
            except Exception as e:
                print(f"[RUNTIME ERROR] Failed to boot {logic_path}: {e}")
                import traceback
                traceback.print_exc()

    def _init_controllers(self):
        """Bind physical controllers to scene objects."""
        from py_editor.core.controller import AIController, PlayerController, AIGPUFishController, AIGPUBirdController
        
        for obj in self.viewport.scene_objects:
            name_lower = obj.name.lower()
            type_lower = obj.obj_type.lower()
            
            # Fix AttributeError: handle logic_path being None
            logic_raw = getattr(obj, "logic_path", "")
            logic_path = (logic_raw or "").lower()
            
            # Explicit Controller Property override
            ctrl_type = getattr(obj, "controller_type", "None")
            
            # Binding Logic
            if ctrl_type == "AI (GPU Fish)" or (ctrl_type == "None" and ("fish" in name_lower or "ai_gpu_fish" in logic_path)):
                ctrl = AIGPUFishController(obj)
                self.controllers[obj.id] = ctrl
                print(f"[RUNTIME] Assigned AIGPUFishController to {obj.name}")
            
            elif ctrl_type == "AI (GPU Bird)" or (ctrl_type == "None" and ("bird" in name_lower or "ai_gpu_bird" in logic_path)):
                ctrl = AIGPUBirdController(obj)
                self.controllers[obj.id] = ctrl
                print(f"[RUNTIME] Assigned AIGPUBirdController to {obj.name}")

            elif ctrl_type == "AI (CPU)" or (ctrl_type == "None" and obj.obj_type == 'fish'):
                ctrl = AIController(obj)
                self.controllers[obj.id] = ctrl
                print(f"[RUNTIME] Assigned AIController to {obj.name}")
            
            elif ctrl_type == "Player" or (ctrl_type == "None" and obj.obj_type == 'player'):
                ctrl = PlayerController(obj)
                self.controllers[obj.id] = ctrl
                print(f"[RUNTIME] Assigned PlayerController to {obj.name}")
        
        # Link flocks for Boids
        all_ais = [c for c in self.controllers.values() if isinstance(c, AIController)]
        for ai in all_ais:
            ai.flock = all_ais

        # Give navigation manager access to controllers so it can drive MoveTo tasks
        try:
            if self.nav_manager:
                self.nav_manager.set_controllers(self.controllers)
        except Exception:
            pass

    def _tick(self):
        now = time.time()
        dt = now - self._last_tick_time
        self._last_tick_time = now
        
        sim_time = now - self.start_time
        
        # 1. Tick physical controllers (Boids, Physics, etc.)
        for ctrl in self.controllers.values():
            try:
                ctrl.update(dt)
            except Exception as e:
                print(f"[RUNTIME] Controller error: {e}")

        # Ensure controller-derived physics values are updated
        for ctrl in self.controllers.values():
            try:
                ctrl.update_physics(dt)
            except Exception:
                pass

        # Let navigation manager advance tasks (moves are applied from controllers)
        try:
            if self.nav_manager:
                self.nav_manager.update(dt)
        except Exception:
            pass

        # Resolve simple collisions after movement
        try:
            from py_editor.core.physics import resolve_collisions, integrate_gravity
            integrate_gravity(self.viewport.scene_objects, dt)
            resolve_collisions(self.viewport.scene_objects, dt)
        except Exception:
            pass
        
        # 2. Tick Logic Components
        for obj_id, ctx_pairs in self.contexts.items():
            for ir_module, ctx in ctx_pairs:
                try:
                    self.backend.execute_ir(ir_module, ctx)
                except Exception:
                    pass
        
        self.viewport.update()

def launch_standalone(scene_data: dict, run_exec: bool = False):
    existing = QApplication.instance()
    app = existing or QApplication(sys.argv if existing is None else [])
    window = StandaloneGameWindow(scene_data)
    window.show()

    # Initialize controllers AFTER showing the window (ensures GL context for GPUBoids)
    window._init_controllers()

    # When invoked as its own process, block on the event loop so the window
    # survives past return. Prior code used `if not QApplication.instance()`,
    # which was always False because we had just created the instance above —
    # the process exited immediately, showing a cmd flash and no window.
    if run_exec:
        sys.exit(app.exec())
    return window

if __name__ == "__main__":
    if len(sys.argv) > 1:
        try:
            with open(sys.argv[1], 'r') as f:
                data = json.load(f)
            from py_editor.core import paths as _ap
            # Project root = directory containing the scene file (cwd passed by launcher).
            _ap.set_project_root(os.getcwd())
        except Exception as e:
            print(f"[STANDALONE] Failed to load scene {sys.argv[1]}: {e}")
            sys.exit(1)
        launch_standalone(data, run_exec=True)
    else:
        print("[STANDALONE] Usage: standalone.py <scene.json>")
        sys.exit(1)
