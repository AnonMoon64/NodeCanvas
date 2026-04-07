"""
Interpreter type system for different NodeCanvas file types.

Each file type (.logic, .anim, .ui) can have specialized interpretation
while sharing the same underlying IR format.
"""
from typing import Dict, Any, Optional, Generator
from enum import Enum
from dataclasses import dataclass
import time


class ExecutionState(Enum):
    """States for graph execution lifecycle"""
    IDLE = "idle"
    RUNNING = "running"
    YIELDED = "yielded"  # Paused, waiting to resume
    FINISHED = "finished"
    ERROR = "error"


@dataclass
class ExecutionResult:
    """Result of a graph execution"""
    state: ExecutionState
    outputs: Dict[str, Any]
    error: Optional[str] = None
    yield_data: Optional[Any] = None  # Data passed with yield


class BaseInterpreter:
    """
    Base interpreter class that all type-specific interpreters inherit from.
    
    Provides:
    - Entry point (on_start/on_enter)
    - Duration phase (tick/update loop)
    - Exit point (on_finish/on_exit)
    - Yield/resume support for async execution
    """
    
    def __init__(self):
        self.state = ExecutionState.IDLE
        self.context = {}
        self.outputs = {}
        self._yield_value = None
    
    def enter(self, inputs: Dict[str, Any]) -> ExecutionResult:
        """
        Entry point - called when graph execution begins.
        Override in subclasses for specific behavior.
        """
        self.state = ExecutionState.RUNNING
        self.context['inputs'] = inputs
        return ExecutionResult(state=self.state, outputs={})
    
    def tick(self, delta_time: float = 0.0) -> ExecutionResult:
        """
        Duration phase - called repeatedly during execution.
        Returns YIELDED to pause, FINISHED to complete.
        """
        # Base implementation finishes immediately
        self.state = ExecutionState.FINISHED
        return ExecutionResult(state=self.state, outputs=self.outputs)
    
    def exit(self) -> ExecutionResult:
        """
        Exit point - called when graph execution ends.
        Cleanup and return final outputs.
        """
        self.state = ExecutionState.IDLE
        return ExecutionResult(state=self.state, outputs=self.outputs)
    
    def yield_execution(self, data: Any = None) -> ExecutionResult:
        """Pause execution with optional data"""
        self.state = ExecutionState.YIELDED
        self._yield_value = data
        return ExecutionResult(
            state=self.state, 
            outputs=self.outputs,
            yield_data=data
        )
    
    def resume(self, data: Any = None) -> ExecutionResult:
        """Resume from yielded state"""
        if self.state != ExecutionState.YIELDED:
            return ExecutionResult(
                state=ExecutionState.ERROR,
                outputs={},
                error="Cannot resume - not in yielded state"
            )
        self.context['resume_data'] = data
        self.state = ExecutionState.RUNNING
        return self.tick()
    
    def finish(self, outputs: Dict[str, Any] = None):
        """Mark execution as finished with outputs"""
        if outputs:
            self.outputs.update(outputs)
        self.state = ExecutionState.FINISHED


class LogicInterpreter(BaseInterpreter):
    """
    Interpreter for .logic files.
    
    Standard execution model:
    - Runs immediately when triggered
    - No duration phase (instant execution)
    - Returns outputs synchronously
    """
    
    def __init__(self, ir_backend=None):
        super().__init__()
        self.ir_backend = ir_backend
    
    def execute(self, ir_module, inputs: Dict[str, Any] = None) -> ExecutionResult:
        """Execute logic graph synchronously"""
        from .interpreter import IRBackend, ExecutionContext
        
        self.enter(inputs or {})
        
        try:
            backend = self.ir_backend or IRBackend()
            
            # Inject inputs into IR module
            if inputs and hasattr(ir_module, 'interface_inputs'):
                ir_module.interface_inputs = inputs
            
            ctx = ExecutionContext()
            results = backend.execute_ir(ir_module, ctx)
            
            self.outputs = results
            self.finish(results)
            
        except Exception as e:
            self.state = ExecutionState.ERROR
            return ExecutionResult(
                state=self.state,
                outputs={},
                error=str(e)
            )
        
        return self.exit()


class AnimInterpreter(BaseInterpreter):
    """
    Interpreter for .anim files.
    
    Timeline-based execution:
    - Has explicit duration (start time → end time)
    - Tick called each frame with delta_time
    - Supports keyframes and interpolation
    - Yields during playback, finishes when timeline completes
    """
    
    def __init__(self):
        super().__init__()
        self.current_time = 0.0
        self.duration = 1.0  # Default 1 second
        self.is_playing = False
        self.loop = False
        self.keyframes = {}  # time -> {property: value}
    
    def set_duration(self, duration: float):
        """Set animation duration in seconds"""
        self.duration = max(0.001, duration)
    
    def set_keyframes(self, keyframes: Dict[float, Dict[str, Any]]):
        """Set keyframes: {time: {property: value}}"""
        self.keyframes = keyframes
    
    def enter(self, inputs: Dict[str, Any]) -> ExecutionResult:
        """Start animation playback"""
        result = super().enter(inputs)
        self.current_time = 0.0
        self.is_playing = True
        
        # Extract duration from inputs if provided
        if 'duration' in inputs:
            self.set_duration(float(inputs['duration']))
        if 'loop' in inputs:
            self.loop = bool(inputs['loop'])
        if 'keyframes' in inputs:
            self.set_keyframes(inputs['keyframes'])
        
        return result
    
    def tick(self, delta_time: float = 0.016) -> ExecutionResult:
        """Advance animation by delta_time seconds"""
        if not self.is_playing:
            return ExecutionResult(state=self.state, outputs=self.outputs)
        
        self.current_time += delta_time
        
        # Calculate progress (0.0 to 1.0)
        progress = min(1.0, self.current_time / self.duration)
        
        # Interpolate values at current time
        self.outputs['progress'] = progress
        self.outputs['current_time'] = self.current_time
        self.outputs['duration'] = self.duration
        
        # Interpolate keyframe values
        interpolated = self._interpolate_keyframes(self.current_time)
        self.outputs.update(interpolated)
        
        # Check if animation complete
        if self.current_time >= self.duration:
            if self.loop:
                self.current_time = 0.0
                return self.yield_execution({'looped': True})
            else:
                self.finish()
                return ExecutionResult(state=self.state, outputs=self.outputs)
        
        # Continue playing - yield to allow frame update
        return self.yield_execution({'progress': progress})
    
    def _interpolate_keyframes(self, time: float) -> Dict[str, Any]:
        """Interpolate keyframe values at given time"""
        result = {}
        
        if not self.keyframes:
            return result
        
        sorted_times = sorted(self.keyframes.keys())
        
        for prop in set(k for kf in self.keyframes.values() for k in kf.keys()):
            # Find surrounding keyframes
            before_time = None
            after_time = None
            
            for t in sorted_times:
                if t <= time:
                    if prop in self.keyframes.get(t, {}):
                        before_time = t
                if t > time and after_time is None:
                    if prop in self.keyframes.get(t, {}):
                        after_time = t
            
            if before_time is not None:
                before_val = self.keyframes[before_time].get(prop)
                
                if after_time is not None:
                    after_val = self.keyframes[after_time].get(prop)
                    # Linear interpolation
                    t = (time - before_time) / (after_time - before_time)
                    
                    if isinstance(before_val, (int, float)) and isinstance(after_val, (int, float)):
                        result[prop] = before_val + (after_val - before_val) * t
                    else:
                        result[prop] = before_val if t < 0.5 else after_val
                else:
                    result[prop] = before_val
        
        return result
    
    def pause(self):
        """Pause animation playback"""
        self.is_playing = False
        return self.yield_execution({'paused': True})
    
    def play(self):
        """Resume animation playback"""
        self.is_playing = True
        self.state = ExecutionState.RUNNING


class UIInterpreter(BaseInterpreter):
    """
    Interpreter for .ui files.
    
    Event-driven execution:
    - Runs in response to UI events (click, change, etc.)
    - Maintains state between events
    - Never truly "finishes" - always ready for next event
    """
    
    def __init__(self):
        super().__init__()
        self.event_handlers = {}  # event_type -> [handlers]
        self.ui_state = {}  # Persistent UI state
        self.pending_events = []
    
    def register_handler(self, event_type: str, handler):
        """Register a handler for an event type"""
        if event_type not in self.event_handlers:
            self.event_handlers[event_type] = []
        self.event_handlers[event_type].append(handler)
    
    def enter(self, inputs: Dict[str, Any]) -> ExecutionResult:
        """Initialize UI state"""
        result = super().enter(inputs)
        self.ui_state = inputs.get('initial_state', {})
        return result
    
    def tick(self, delta_time: float = 0.0) -> ExecutionResult:
        """Process pending events"""
        if not self.pending_events:
            # No events - yield waiting for next event
            return self.yield_execution({'waiting_for_event': True})
        
        # Process one event
        event = self.pending_events.pop(0)
        event_type = event.get('type')
        event_data = event.get('data', {})
        
        # Call registered handlers
        handlers = self.event_handlers.get(event_type, [])
        for handler in handlers:
            try:
                result = handler(event_data, self.ui_state)
                if result:
                    self.ui_state.update(result)
            except Exception as e:
                self.outputs['error'] = str(e)
        
        self.outputs['ui_state'] = self.ui_state.copy()
        self.outputs['last_event'] = event
        
        # Yield - UI interpreter never finishes
        return self.yield_execution({'processed_event': event_type})
    
    def dispatch_event(self, event_type: str, event_data: Dict[str, Any] = None):
        """Queue an event for processing"""
        self.pending_events.append({
            'type': event_type,
            'data': event_data or {},
            'timestamp': time.time()
        })
        
        # If yielded, resume to process event
        if self.state == ExecutionState.YIELDED:
            self.state = ExecutionState.RUNNING
    
    def set_state(self, key: str, value: Any):
        """Set a UI state value"""
        self.ui_state[key] = value
    
    def get_state(self, key: str, default: Any = None) -> Any:
        """Get a UI state value"""
        return self.ui_state.get(key, default)


# Factory function to get the right interpreter for a file type
def get_interpreter(file_type: str) -> BaseInterpreter:
    """
    Get the appropriate interpreter for a file type.
    
    Args:
        file_type: 'logic', 'anim', 'ui', or file extension like '.logic'
    
    Returns:
        Appropriate interpreter instance
    """
    # Normalize file type
    ft = file_type.lower().lstrip('.')
    
    if ft in ('logic', 'json'):
        return LogicInterpreter()
    elif ft == 'anim':
        return AnimInterpreter()
    elif ft == 'ui':
        return UIInterpreter()
    else:
        # Default to logic interpreter
        return LogicInterpreter()


# Convenience function to execute a graph file
def execute_graph_file(file_path: str, inputs: Dict[str, Any] = None) -> ExecutionResult:
    """
    Execute a graph file with the appropriate interpreter.
    
    Args:
        file_path: Path to .logic, .anim, or .ui file
        inputs: Input values for the graph
    
    Returns:
        ExecutionResult with outputs
    """
    import json
    from pathlib import Path
    
    path = Path(file_path)
    ext = path.suffix.lower()
    
    # Load graph data
    with open(path, 'r', encoding='utf-8') as f:
        graph_data = json.load(f)
    
    # Get interpreter
    interpreter = get_interpreter(ext)
    
    # For logic files, use the full execution path
    if isinstance(interpreter, LogicInterpreter):
        from .interpreter import IRBackend
        backend = IRBackend()
        
        # Load templates
        try:
            from py_editor.core.node_templates import get_all_templates
        except:
            from core.node_templates import get_all_templates
        
        templates = get_all_templates()
        ir_module = backend.canvas_to_ir(graph_data, templates)
        
        return interpreter.execute(ir_module, inputs or {})
    
    else:
        # Anim/UI interpreters
        interpreter.enter(inputs or {})
        return interpreter.tick()
