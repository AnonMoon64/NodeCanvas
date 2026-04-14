"""
standalone.py

Headless/Standalone runtime for NodeCanvas.
Boots a scene, attaches logic components, and runs the simulation.
"""
import sys
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
        
        self.start_time = time.time()

    def _boot_logic(self):
        """Find all objects with a logic path and compile them."""
        objects = self.viewport.scene_objects
        templates = get_all_templates()
        
        for obj in objects:
            logic_path = getattr(obj, 'logic_path', None)
            if not logic_path: continue
            
            self.contexts[obj.id] = []
            if not Path(logic_path).exists():
                print(f"[RUNTIME] Logic file not found: {logic_path}")
                continue
            
            try:
                with open(logic_path, 'r', encoding='utf-8') as f:
                    graph_data = json.load(f)
                
                # Use the new IRBackend compiler
                ir_module = self.backend.canvas_to_ir(graph_data, templates)
                ctx = ExecutionContext()
                ctx.ir_module = ir_module
                ctx.variables['self'] = obj.id
                
                self.contexts[obj.id].append((ir_module, ctx))
                print(f"[RUNTIME] Booted logic {Path(logic_path).name} on {obj.name}")
                
                # Execute initial pass (OnStart)
                self.backend.execute_ir(ir_module, ctx)
            except Exception as e:
                print(f"[RUNTIME ERROR] Failed to boot {logic_path}: {e}")
                import traceback
                traceback.print_exc()

    def _tick(self):
        dt = 0.016
        sim_time = time.time() - self.start_time
        
        # 1. Update Viewport (Animation/Physics) - uses internal _tick
        # No explicit call needed as viewport has its own QTimer
        
        # 2. Tick Logic Components
        for obj_id, ctx_pairs in self.contexts.items():
            for ir_module, ctx in ctx_pairs:
                # Execute the full graph once.
                # In a real engine, we'd trigger an 'OnTick' entry point here.
                # For now, we reuse the existing one-pass logic.
                try:
                    self.backend.execute_ir(ir_module, ctx)
                except Exception:
                    pass
        
        self.viewport.update()

def launch_standalone(scene_data: dict):
    app = QApplication.instance() or QApplication([])
    window = StandaloneGameWindow(scene_data)
    window.show()
    if not QApplication.instance():
        sys.exit(app.exec())
    return window

if __name__ == "__main__":
    import json
    if len(sys.argv) > 1:
        with open(sys.argv[1], 'r') as f:
            data = json.load(f)
        launch_standalone(data)
