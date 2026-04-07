"""
Test Print node functionality
"""
import sys
from pathlib import Path
parent_dir = Path(__file__).resolve().parent.parent
if str(parent_dir) not in sys.path:
    sys.path.insert(0, str(parent_dir))

from core.ir import IRModule
from core.backend import IRBackend

def test_print_node():
    """Test Print node with different inputs"""
    print("=== Testing Print Node ===\n")
    
    backend = IRBackend()
    
    # Test 1: Print a constant value
    print("Test 1: Print constant")
    module = IRModule()
    const = module.add_const_int(42)
    print_node = module.add_print(const, None)
    
    results = backend.execute_ir(module)
    print(f"Expected output above: 42\n")
    
    # Test 2: Print with label
    print("Test 2: Print with label")
    module2 = IRModule()
    value = module2.add_const_float(3.14159)
    label = module2.add_const_string("PI")
    print_node2 = module2.add_print(value, label)
    
    results2 = backend.execute_ir(module2)
    print(f"Expected output above: [PI] 3.14159\n")
    
    # Test 3: Print result of calculation
    print("Test 3: Print calculation result")
    module3 = IRModule()
    a = module3.add_const_int(10)
    b = module3.add_const_int(5)
    add = module3.add_add(a, b)
    label3 = module3.add_const_string("Sum")
    print_node3 = module3.add_print(add, label3)
    return_node = module3.add_return(add)
    
    results3 = backend.execute_ir(module3)
    print(f"Expected output above: [Sum] 15")
    print(f"Return value: {results3.get('return')}\n")
    
    print("✅ All Print node tests completed!")

if __name__ == '__main__':
    test_print_node()
