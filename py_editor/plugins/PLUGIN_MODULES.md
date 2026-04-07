# Creating Self-Contained Plugin Packages (.ncpkg)

## Overview
NodeCanvas plugin packages (.ncpkg) are ZIP archives that can include:
1. **Node JSON definitions** - Define node inputs/outputs/metadata
2. **Python modules** - Provide custom execution logic
3. **Package metadata** - Package name, description, version, author

This makes plugins **fully self-contained** and shareable.

## Package Structure

```
MyPlugin.ncpkg (ZIP archive)
├── package.json          # Package metadata (optional)
├── nodes/
│   ├── MyNode1.json     # Node definitions
│   ├── MyNode2.json
│   └── MyNode3.json
└── modules/
    └── plugin.py         # Python module with execution functions
```

## Creating a Plugin Package

### Method 1: Using the Export Tab (Recommended)

1. Open **Settings → Export Package** tab
2. Fill in package information:
   - Package Name
   - Description
   - Author
   - Version
3. Select nodes to include from the list
4. **Optional**: Browse for a Python module (.py file)
5. Click **Export as .ncpkg**

### Method 2: Manual Creation

1. Create a folder with your nodes and module
2. Zip the contents
3. Rename `.zip` to `.ncpkg`

## Python Module Format

Your Python module should define functions for node execution:

### Option 1: Specific Functions (Recommended)
```python
def process_NodeName(input1, input2, ...):
    """Process function for a specific node"""
    # Your logic here
    return result
```

Example:
```python
def process_FormatString(template, value):
    """Format a string with a value"""
    if template is None:
        template = "{}"
    return str(template).format(value)

def process_RandomNumber(min_val, max_val):
    """Generate random number"""
    import random
    return random.uniform(min_val or 0, max_val or 1)
```

### Option 2: Generic Handler
```python
def process(node_name, *inputs):
    """Handle all nodes in package"""
    if node_name == "MyNode1":
        return inputs[0] * 2
    elif node_name == "MyNode2":
        return inputs[0] + inputs[1]
    # ...
```

### Option 3: Inline Code (Fallback)
If no Python module is provided, nodes use the `code` field in their JSON:
```json
{
  "name": "MyNode",
  "code": "def process(a, b):\n    return a + b"
}
```

## Execution Priority

The backend executes nodes in this order:
1. **Plugin module function**: `process_NodeName()` from `.ncpkg/modules/`
2. **Generic module handler**: `process(node_name, ...)` from `.ncpkg/modules/`
3. **Inline code**: `code` field in node JSON definition

## Benefits of Python Modules

✅ **Better organization** - Separate logic from definitions
✅ **Code reuse** - Share utilities across nodes
✅ **Import libraries** - Use any Python library
✅ **Better debugging** - Full Python IDE support
✅ **Self-contained** - Everything in one .ncpkg file
✅ **Easy sharing** - Single file to distribute

## Example Nodes with Module

### FormatString Node (JSON)
```json
{
  "name": "FormatString",
  "description": "Format a string with a value using Python format syntax",
  "category": "Advanced String",
  "inputs": {
    "template": {"type": "string"},
    "value": {"type": "any"}
  },
  "outputs": {
    "result": {"type": "string"}
  }
}
```

### RandomNumber Node (JSON)
```json
{
  "name": "RandomNumber",
  "description": "Generate a random number between min and max",
  "category": "Advanced Math",
  "inputs": {
    "min": {"type": "float"},
    "max": {"type": "float"}
  },
  "outputs": {
    "result": {"type": "float"}
  }
}
```

## Testing Your Plugin

1. Create nodes in NodeCanvas editor
2. Export via **Settings → Export Package**
3. Include your Python module
4. Remove and reinstall via **Settings → Plugins**
5. Create a test graph and run

## Advanced Features

### Using External Libraries
```python
def process_HTTPRequest(url):
    import requests
    response = requests.get(url)
    return response.text
```

### Shared Utilities
```python
# Helper function
def clamp(value, min_val, max_val):
    return max(min_val, min(max_val, value))

def process_ClampedAdd(a, b, min_val, max_val):
    result = (a or 0) + (b or 0)
    return clamp(result, min_val or 0, max_val or 100)
```

### State Management
```python
_cache = {}

def process_CachedValue(key, value):
    if value is not None:
        _cache[key] = value
    return _cache.get(key)
```

## Plugin Module Location

When installed, modules are extracted to:
```
py_editor/.plugin_cache/PackageName/plugin.py
```

They are loaded once when NodeCanvas starts and reused for all executions.

## Best Practices

1. **Name your module** `plugin.py` for auto-detection
2. **Handle None inputs** - Always check for None
3. **Document functions** - Use docstrings
4. **Error handling** - Use try/except blocks
5. **Type checking** - Validate input types
6. **Test thoroughly** - Test all edge cases

## Troubleshooting

**Module not loading?**
- Check console for import errors
- Ensure module is in `modules/` folder
- Name it `plugin.py` or specify in archive

**Function not called?**
- Function name must match: `process_NodeName`
- Or use generic `process(node_name, *inputs)`
- Check console for "executed via plugin module" messages

**Import errors?**
- Ensure required libraries are installed
- Use try/except for optional imports
