# NodeCanvas Plugin System

## Overview
NodeCanvas supports a flexible plugin system that allows you to extend the node editor with custom nodes. Plugins can be distributed in two formats:

### 1. JSON Package Format (.json)
A single JSON file containing multiple node definitions.

**Example Structure:**
```json
{
  "package_name": "My Utilities",
  "description": "A collection of utility nodes",
  "author": "Your Name",
  "version": "1.0",
  "nodes": [
    {
      "name": "NodeName1",
      "description": "What this node does",
      "category": "My Category",
      "inputs": {
        "input1": {"type": "float"},
        "input2": {"type": "string"}
      },
      "outputs": {
        "result": {"type": "float"}
      },
      "code": "def process(input1, input2):\n    return input1 * 2"
    },
    {
      "name": "NodeName2",
      ...
    }
  ]
}
```

### 2. Archive Format (.ncpkg)
A ZIP archive containing multiple individual node JSON files. Each file follows the standard node template format.

**Creating an .ncpkg file:**
1. Create individual node JSON files (one per node)
2. Compress them into a ZIP file
3. Rename the .zip extension to .ncpkg

**Individual node format:**
```json
{
  "name": "MyNode",
  "description": "Description here",
  "category": "My Category",
  "inputs": {
    "input1": {"type": "float"}
  },
  "outputs": {
    "result": {"type": "float"}
  },
  "code": "def process(input1):\n    return input1 * 2"
}
```

## Node Definition

### Supported Input/Output Types
- `int` - Integer numbers
- `float` - Floating point numbers
- `string` - Text strings
- `bool` - Boolean (True/False)
- `any` - Any type

### Code Function
The `code` field must define a `process()` function that:
- Takes parameters matching the input names
- Returns a single value (or tuple for multiple outputs)
- Handles None values gracefully

**Example:**
```python
def process(value, multiplier):
    if value is None:
        return 0.0
    mult = multiplier if multiplier is not None else 1.0
    return value * mult
```

## Installing Plugins

### Via Settings Dialog
1. Open **Settings** → **Plugins** tab
2. Click **Add Plugin...**
3. Select your .json or .ncpkg file
4. Plugin will be installed to `py_editor/plugins/`
5. Nodes will appear in the node menu under their category

### Manual Installation
Copy your .json or .ncpkg file directly to:
```
NodeCanvas/py_editor/plugins/
```
Restart the application or click **Refresh** in Settings.

## Example Plugins Included

### String Utilities (StringUtilities.json)
- **StringLength** - Get string length
- **Concatenate** - Join two strings
- **ToUpperCase** - Convert to uppercase
- **ToLowerCase** - Convert to lowercase
- **StringReplace** - Replace substring
- **StringSplit** - Split by delimiter

### Math Utilities (MathUtilities.json)
- **Clamp** - Clamp value between min/max
- **Lerp** - Linear interpolation
- **Abs** - Absolute value
- **Power** - Raise to power
- **SquareRoot** - Square root
- **Round** - Round to decimals

## Best Practices

1. **Package Organization**: Group related nodes into a single package
2. **Descriptive Names**: Use clear, descriptive node names
3. **Categories**: Choose appropriate categories for organization
4. **Error Handling**: Always handle None inputs in your code
5. **Documentation**: Include good descriptions for nodes and packages
6. **Version Control**: Include version numbers in packages

## Sharing Plugins

To share your plugin:
1. Export your .json package or .ncpkg archive
2. Share the single file with others
3. They can install it via Settings → Plugins → Add Plugin

## Plugin Metadata

For JSON packages, you can include:
- `package_name` - Display name (required)
- `description` - What the package does
- `author` - Your name
- `version` - Version number (e.g., "1.0")

For .ncpkg archives, create a `package.json` in the root with metadata:
```json
{
  "name": "My Plugin Pack",
  "description": "Collection of nodes",
  "author": "Your Name",
  "version": "1.0"
}
```
