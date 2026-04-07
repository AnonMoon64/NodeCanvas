"""
Test script for NodeCanvas IR and backend functionality
"""
import sys
from pathlib import Path
parent_dir = Path(__file__).resolve().parent.parent
if str(parent_dir) not in sys.path:
    sys.path.insert(0, str(parent_dir))

from core.ir import IRModule, Value, ValueType
from core.backend import IRBackend

def test_basic_ir():
    """Test basic IR creation and serialization"""
    print("=== Testing Basic IR ===")
    module = IRModule()
    
    # Create some nodes
    const_a = module.add_const_int(5)
    const_b = module.add_const_int(3)
    add_node = module.add_add(const_a, const_b)
    return_node = module.add_return(add_node)
    
    print(f"Created {len(module.nodes)} nodes")
    print(f"Const A: {const_a.id}")
    print(f"Const B: {const_b.id}")
    print(f"Add: {add_node.id}")
    print(f"Return: {return_node.id}")
    
    # Serialize to JSON
    json_str = module.to_json()
    print("\nSerialized IR:")
    print(json_str[:200] + "...")
    
    # Deserialize
    module2 = IRModule.from_json(json_str)
    print(f"\nDeserialized module has {len(module2.nodes)} nodes")
    
    return module

def test_execution():
    """Test IR execution"""
    print("\n=== Testing Execution ===")
    backend = IRBackend()
    
    # Create a simple graph: 10 + 20 = 30
    module = IRModule()
    const_a = module.add_const_int(10)
    const_b = module.add_const_int(20)
    add_node = module.add_add(const_a, const_b)
    return_node = module.add_return(add_node)
    
    print("Graph: 10 + 20")
    
    # Execute
    results = backend.execute_ir(module)
    print(f"Result: {results}")
    
    expected = 30
    actual = results.get('return')
    if actual == expected:
        print(f"✅ Test passed: {actual} == {expected}")
    else:
        print(f"❌ Test failed: {actual} != {expected}")

def test_complex_graph():
    """Test a more complex graph"""
    print("\n=== Testing Complex Graph ===")
    backend = IRBackend()
    
    # Create graph: (5 + 3) * 2 = 16
    module = IRModule()
    const_5 = module.add_const_int(5)
    const_3 = module.add_const_int(3)
    const_2 = module.add_const_int(2)
    add_node = module.add_add(const_5, const_3)
    mul_node = module.add_multiply(add_node, const_2)
    return_node = module.add_return(mul_node)
    
    print("Graph: (5 + 3) * 2")
    
    # Execute
    results = backend.execute_ir(module)
    print(f"Result: {results}")
    
    expected = 16
    actual = results.get('return')
    if actual == expected:
        print(f"✅ Test passed: {actual} == {expected}")
    else:
        print(f"❌ Test failed: {actual} != {expected}")

def test_float_operations():
    """Test float operations"""
    print("\n=== Testing Float Operations ===")
    backend = IRBackend()
    
    # Create graph: 10.5 / 2.0 = 5.25
    module = IRModule()
    const_a = module.add_const_float(10.5)
    const_b = module.add_const_float(2.0)
    div_node = module.add_divide(const_a, const_b)
    return_node = module.add_return(div_node)
    
    print("Graph: 10.5 / 2.0")
    
    # Execute
    results = backend.execute_ir(module)
    print(f"Result: {results}")
    
    expected = 5.25
    actual = results.get('return')
    if abs(actual - expected) < 0.001:
        print(f"✅ Test passed: {actual} ≈ {expected}")
    else:
        print(f"❌ Test failed: {actual} != {expected}")

if __name__ == '__main__':
    print("NodeCanvas IR & Backend Test Suite\n")
    print("=" * 50)
    
    try:
        test_basic_ir()
        test_execution()
        test_complex_graph()
        test_float_operations()
        
        print("\n" + "=" * 50)
        print("All tests completed!")
        
    except Exception as e:
        print(f"\n❌ Error during testing: {e}")
        import traceback
        traceback.print_exc()
