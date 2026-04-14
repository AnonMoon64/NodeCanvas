import os
import sys
import json
from pathlib import Path

# Add project root to sys.path
ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT))

from py_editor.backends.interpreter import execute_canvas_graph, ExecutionContext
from py_editor.core import node_templates

def run_test(logic_file):
    print(f"--- Running Headless Test: {logic_file} ---")
    
    # Resolve absolute path
    logic_path = Path(logic_file).resolve()
    if not logic_path.exists():
        print(f"Error: Logic file not found at {logic_path}")
        return False
        
    # Load graph data
    with open(logic_path, 'r', encoding='utf-8') as f:
        graph_data = json.load(f)
        
    # Get all node templates
    templates = node_templates.get_all_templates()
    
    # Execute graph
    print(f"Executing {logic_path.name}...")
    
    # We want to capture prints
    ctx = ExecutionContext()
    
    # Simulate OnStart trigger (or just run once)
    from py_editor.backends.interpreter import IRBackend
    backend = IRBackend()
    ir_module = backend.canvas_to_ir(graph_data, templates)
    ir_module.source_path = str(logic_path)
    
    results = backend.execute_ir(ir_module, ctx=ctx)
    
    print("\n--- Execution Finished ---")
    print(f"Final Return Value: {results.get('return')}")
    print("Captured Prints:")
    for p in ctx.prints:
        print(f"  > {p}")
        
    # Assertion for the user's specific test
    final_val = results.get('return')
    if final_val == 95:
        print("\n✅ TEST PASSED: Result is 95")
        return True
    else:
        print(f"\n❌ TEST FAILED: Result is {final_val}, expected 95")
        return False

if __name__ == "__main__":
    # Test path: tests/test.logic
    test_file = ROOT / "tests" / "test.logic"
    success = run_test(str(test_file))
    sys.exit(0 if success else 1)
