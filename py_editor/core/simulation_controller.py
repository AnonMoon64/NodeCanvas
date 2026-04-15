from PyQt6.QtCore import QObject, QTimer, pyqtSignal
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
        self._timer.start()
        self.state_changed.emit(True)

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
        # In a high-quality engine, _tick would only run 'OnTick' nodes.
        # To avoid 'repeating bullshit', we only execute if scheduled or for specific triggers.
        # For now, we'll keep it simple but ensure it's not spamming the console.
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
            self.backend.execute_ir(self.ir_module, self.ctx)
        except Exception as e:
            print(f"Simulation Error: {e}")
            self.stop()
