# NodeCanvas - Visual Scripting & Scene Editor

A visual node-based programming environment inspired by Unreal Engine Blueprints. Build logic flows, design UIs, and execute graphs with a modern, intuitive interface.

## 🎯 What is NodeCanvas?

NodeCanvas is a **visual scripting system** that lets you create programs by connecting nodes instead of writing code. Think Unreal Blueprints, Blender nodes, or TouchDesigner - but built as a standalone, extensible platform.

### Why Visual Nodes?

- **Intuitive**: See your logic flow visually
- **Rapid Prototyping**: Drag, connect, test - no compile cycles
- **Composable**: Build complex systems from simple building blocks
- **Debuggable**: See data flow through your graph in real-time
- **UI Design**: Build interactive UIs with the visual UI Builder

---

## ✨ V2 Features (Current Release)

NodeCanvas V2 is a **fully functional visual programming environment** with the following capabilities:

### 🔧 Core Features

- **Visual Node Editor**
  - Drag-and-drop node creation with searchable menu
  - Smooth panning (middle mouse) and zooming (scroll wheel)
  - Multi-node selection with rubber band (drag select)
  - Connection validation with type checking
  - Always-visible connection delete markers
  - **Exec pins** (white) for execution flow control
  - **Data pins** (blue) for value connections

- **Node Types**
  - **Math**: Add, Subtract, Multiply, Divide, Lerp, InverseLerp, Abs, Floor, Ceil, Round
  - **Math (Vectors/Colors)**: MakeVector2/3, BreakVector2/3, MakeColor, BreakColor
  - **Value**: ConstInt, ConstFloat, ConstBool, ConstString
  - **Comparison**: Equal, GreaterThan, LessThan
  - **Flow Control**: Branch, Sequence, Select, Return, Delay, ForLoop, ForEachLoop, WhileLoop
  - **Events**: OnStart, Event_Tick
  - **Time**: Timer, SetTimer, ClearTimer, Timeline
  - **UI Events**: OnUIButtonPressed, OnUISliderChanged, OnUICheckboxChanged, OnUITextChanged
  - **UI Actions**: SetUIScreen, SetUIText, SetUIProgress, SetUIVisibility
  - **Variables**: GetVariable, SetVariable
  - **Collections**: CreateStruct, StructGet/Set, ListFindByField, ListFilter, ListSort, etc.
  - **Audio**: PlaySound, StopSound (with multi-channel support)
  - **Conversion**: ToInt, ToFloat, ToBool, ToString
  - **Debug**: Print
  - **Composite**: User-defined reusable sub-graphs

- **Execution Flow System (UE5-Style)**
  - White exec pins for controlling execution order
  - Event nodes trigger execution chains
  - Branch nodes for conditional flow
  - Sequence nodes for multiple execution paths
  - Delay and Timer for timed execution
  - **Loop Nodes** for iteration:
    - `ForLoop` - Traditional counting loop (start, end, step)
    - `ForEachLoop` - Iterate over list items
    - `WhileLoop` - Condition-based loop with safety limit

- **Composite Nodes**
  - Collapse multiple nodes into reusable components
  - Custom input/output pins
  - Nested execution support
  - Composite editor for internal graph editing

- **Execution Engine**
  - IR (Intermediate Representation) backend
  - Topological sort for dependency resolution
  - Recursive composite node execution
  - Error tracking with visual feedback (red borders + error badges)

- **Code Generation (Multi-Language)**
  - Export to **Python** with pygame audio runtime
  - Export to **C** with SDL2 audio
  - Export to **C++** with SDL2 audio
  - Export to **WebAssembly (WASM)** via Emscripten
  - Export to **Rust** code
  - **UI Integration** - Combine logic with PyQt6 UI from UI Builder
  - **Build System**:
    - Python → EXE via PyInstaller
    - C/C++ → Native binary via GCC/Clang/MSVC
    - WASM → Web app via Emscripten

- **Plugin System**
  - **JSON Packages** (`.json`): Multiple nodes in one file
  - **Archive Packages** (`.ncpkg`): ZIP-based plugin format with Python modules
  - Plugin module execution priority system
  - Built-in example plugins (MathUtilities, StringUtilities)

- **Editing Features**
  - Copy/Paste (Ctrl+C/V) - works with system clipboard as JSON
  - Cut (Ctrl+X)
  - Undo/Redo (Ctrl+Z/Y) with 50-level history
  - Node renaming and property editing
  - Template-based node creation system

- **File Management**
  - Save/Load graphs as JSON
  - Export/Import graph data
  - Template library system
  - VS Code-style workspace explorer
  - **Robust Path Resolution**: Automatically resolves absolute paths from different machines by searching relative to the current graph or workspace.

- **UI/UX**
  - Dark theme optimized for long sessions
  - Grid background for alignment
  - Coordinate and zoom display
  - Context menus for quick actions
  - Tabbed interface: **Logic**, **Viewport**, **Anim**

- **Viewport Tab (Scene Editor)**
  - OpenGL-powered 2D/3D viewport embedded via `QOpenGLWidget`
  - **Premium 3-Way Splitter Layout**: [Explorer | Viewport | Properties] structure matches professional DCC tools.
  - **High-Fidelity Tabbed Modes**: **3D** (perspective), **2D** (orthographic), **Pure** (logic-only), and **UI** (inline UI Builder) integrated as consistent tabs.
  - **Advanced Material System (PBR)**:
    - Dedicated **Material Editor** panel for editing `.material` JSON files.
    - Support for **Base Color**, **Roughness**, **Metallic**, and **Emissive** properties.
    - **Presets**: High-quality presets (Plastic, Glass, Metal, Green Glow) for rapid prototyping.
    - **Drag-and-Drop**: Drag `.material` files from the explorer directly onto objects in the viewport.
  - **Explorer Panel** (left sidebar):
    - **Primitives**: 3D (Cube, Sphere, Cylinder, Plane, Cone) and 2D (Rect, Circle, Sprite) drag-and-drop.
    - **Project Files**: Full folder tree with asset filtering and **Create Material** context menu.
    - **Outline**: Unified scene hierarchy with selection and reparenting support.
  - **Properties Panel** (right sidebar):
    - Dedicated transform section (Pos/Rot/Scale).
    - **Inline Material Editor**: Quick access to material settings when an object is selected.
  - **Transform Gizmos** (Premium UE5-Style):
    - **Move**: RGB axis arrows with planar handles and stabilized translation.
    - **Rotate**: Visual rotation rings with Absolute Rigid Parenting (no drift).
    - **Scale**: Proportional scaling with screen-space uniform handles.
    - **Screen-Space Proximity Picking**: Effortless grabbing of handles regardless of camera distance.
  - **Navigation**: UE5-style fly camera (RMB + WASD), orbit, pan, and scroll-zoom.
  - **Context Menus**: Right-click objects for Delete/Rename; right-click Explorer for Create Material.
  - Pixel-accurate picking and ray-plane intersections for precise object manipulation.

### 📁 File Types

NodeCanvas uses semantic file extensions:

| Extension | Purpose | Interpreter |
|-----------|---------|-------------|
| `.logic` | Standard node graphs | LogicInterpreter (instant) |
| `.anim` | Animation timelines | AnimInterpreter (keyframes) |
| `.ui` | UI layout definitions | UIInterpreter (event-driven) |
| `.json` | Legacy support | LogicInterpreter |

**Save/Load** automatically selects the appropriate file type based on current tab.

### 🔷 LogicEditor (formerly CanvasView)

The main graph editor class has been renamed to `LogicEditor`:

```python
from py_editor.ui import LogicEditor, CanvasView  # Both work, CanvasView is alias

# New code should use:
editor = LogicEditor()
```

---

## 🎨 UI Builder

NodeCanvas includes a powerful **visual UI Builder** for creating interactive interfaces:

### UI Builder Features

- **Widget Palette**: Drag and drop UI components
- **Visual Canvas**: WYSIWYG UI design with form preview
- **Property Editor**: Edit widget properties, colors, bindings
- **Multi-Screen Support**: Create multiple UI screens
- **Live Preview**: Test your UI in a runtime preview window

### Available Widgets

| Category | Widgets |
|----------|---------|
| **Containers** | VContainer, HContainer, Frame |
| **Input** | Button, TextInput, Slider, Checkbox, Dropdown |
| **Display** | Label, Image, ProgressBar |

### Widget Properties

- **Positioning**: X, Y, Width, Height
- **Styling**: Background color, text color, border color
- **Background Images**: Set images for buttons, labels, frames
- **Screen Sizes**: Preset sizes (VGA to Full HD) or custom

### Multi-Property Data Binding

Each widget supports **multiple data bindings** - bind different widget properties to different variables:

| Property | Description | Variable Type |
|----------|-------------|---------------|
| `text` | Widget text content | string |
| `visibility` | Show/hide widget | bool |
| `enabled` | Enable/disable widget | bool |
| `source` | Image source path (Image widgets) | string (path) |
| `scaleX` / `scaleY` | Widget scale factor | float |
| `posX` / `posY` | Widget position | float |
| `value` | Slider/progress value | int/float |
| `min` / `max` | Slider/progress range | int/float |
| `fontSize` | Text font size | int |
| `backgroundColor` | Widget background color | string (hex) |
| `checked` | Checkbox state | bool |
| `selectedIndex` | Dropdown selection | int |
| `placeholder` | Input placeholder text | string |

**How to Add Bindings:**

1. Select a widget in the UI Builder
2. In the Properties panel, find "Data Bindings"
3. Click **"+ Add Binding"**
4. Choose a **property** (e.g., visibility) from the first dropdown
5. Choose or type a **variable name** in the second dropdown
6. Add more bindings as needed (e.g., bind both `text` and `visibility`)
7. Click **✕** to remove a binding

**Example: Dynamic Image with Visibility Control**

- Add an Image widget
- Add binding: `source` → `currentImage` (changes what image is shown)
- Add binding: `visibility` → `showImage` (bool to show/hide)
- Add binding: `scaleX` → `imageScale` (float to resize)

### UI Event Nodes

These trigger when the user interacts with the UI:

| Event Node | Trigger | Outputs |
|------------|---------|---------|
| `OnUIButtonPressed` | Button clicked | exec_out |
| `OnUISliderChanged` | Slider value changed | exec_out, value (int) |
| `OnUICheckboxChanged` | Checkbox toggled | exec_out, checked (bool) |
| `OnUITextChanged` | Text input changed | exec_out, text (string) |

### UI Action Nodes

These modify UI widgets at runtime:

| Action Node | Description |
|-------------|-------------|
| `SetUIScreen` | Switch to a different screen |
| `SetUIText` | Update text of Label, Button, or TextInput |
| `SetUIProgress` | Update ProgressBar value/max |
| `SetUIVisibility` | Show or hide any widget |

### Example: Interactive Counter

1. Add a `Label` widget (text: "0")
2. Add two `Button` widgets ("+1" and "-1")
3. Create an `int` variable called "counter"
4. Bind the Label to "counter" variable
5. Create `OnUIButtonPressed` nodes for each button
6. Connect to `SetVariable` nodes to increment/decrement
7. Run preview - buttons update the label!

---

### Examples: To be added

- Platformer starter
- RPG inventory starter
- Calculator UI starter
- Tower defense starter
- Dialogue system starter

---

## 🤖 AI Assistant

NodeCanvas includes an integrated **AI assistant**: WIP

### Assistant Features

- **Visual Scripting Help**: Ask how to create node graphs
- **UI Building Guidance**: Get help designing interfaces
- **Node Creation**: Learn how to make custom nodes
- **Debugging Assistance**: Get help fixing graph issues

### Setup

1. Get an API key from [OpenAI](https://platform.openai.com)
2. Add it to the `.env` file in the project root:

   ```
   OPENAI_API_KEY=your-actual-api-key-here
   OPENAI_MODEL=gpt-4o-mini
   ```

3. The status indicator turns green when connected

### Using Assistant

- Type your question in the chat input
- Click "Send" to get a response
- Chat history is maintained during the session

---

## 🗂️ Explorer (VSCode-style)

The left sidebar features a **file explorer**:

### Explorer Sections

- **PROJECT FILES**: Browse workspace files with icons
  - Double-click `.json` files to load graphs
  - Right-click for context menu (New File, New Folder, Delete, Rename)
  - Automatic filtering of `.git`, `__pycache__`, etc.
  
- **OPEN GRAPHS**: Track currently open graphs

- **OUTLINE**: View nodes in current graph

### Collapsible Sections

Each section can be collapsed/expanded by clicking the header arrow (▼/▶), just like VS Code.

---

## 🎛️ Variable System (UE5-Style)

NodeCanvas features a powerful **UE5-style variable panel** for managing graph variables:

### Variable Panel Features

- **Drag-and-Drop Variables**: Drag variables from the panel onto the canvas to create Get/Set nodes
- **Auto-Naming**: New variables automatically get sequential names (NewVar, NewVar_1, NewVar_2...)
- **Type Memory**: Remembers your last-used type for faster workflow
- **Inline Editing**: Double-click any field to edit in place:
  - **Name column**: Rename variables instantly
  - **Type column**: Change variable type with dropdown

### Supported Variable Types

| Type | Description | Editor |
|------|-------------|--------|
| `int` | Integer numbers | Spin box (-999999 to 999999) |
| `float` | Decimal numbers | Double spin box with 4 decimals |
| `string` | Text values | Text input field |
| `bool` | True/False | Checkbox toggle |
| `vector2` | 2D coordinates | X, Y spin boxes |
| `vector3` | 3D coordinates | X, Y, Z spin boxes |
| `color` | RGB color | Color picker dialog |
| `image` | Image file path | File picker (png, jpg, gif, bmp, webp) |
| `audio` | Audio file path | File picker (wav, mp3, ogg, flac) |
| `list` | Dynamic arrays | List editor with type-aware items |
| `dict` | Key-value maps | Dictionary editor |
| `struct` | Custom data types | Struct editor with typed fields |

### Complex Type Editing

**Structs** - Create custom data structures:

- Add fields with name, type, and value
- Support all types including nested structs
- Define game entities like `{name: string, health: int, attack: int}`

**Lists** - Dynamic arrays with any element type:

- `List<int>` - List of integers
- `List<struct>` - List of custom structs (perfect for game data!)
- `List<vector3>` - List of 3D positions
- Proper editors for each element type

**Nested Types**:

- `List<struct>` with complex struct definitions
- `Dict<list>` for complex mappings
- Unlimited nesting depth

### Game Development Example

Create an enemy list for a game:

1. Add variable → Type: `list` → Element Type: `struct`
2. Click value to open List Editor
3. Click **+ Add** to add an enemy
4. Define struct fields:
   - `name` (string) = "Goblin"
   - `health` (int) = 50
   - `attack` (int) = 10
   - `position` (vector3) = (100, 0, 50)
5. Add more enemies to the list
6. Use `ListFindByField` node to find enemies by name

---

## 🧩 Collection & Struct Nodes

NodeCanvas includes powerful nodes for working with complex data:

### Struct Nodes

| Node | Description |
|------|-------------|
| `CreateStruct` | Create a struct with a single field |
| `MakeStruct2/3/4` | Create structs with 2-4 typed fields |
| `StructGet` | Get a field value from a struct |
| `StructSet` | Set a field value in a struct |
| `StructHasField` | Check if a struct has a field |
| `StructFields` | Get list of all field names |

### List Nodes

| Node | Description |
|------|-------------|
| `ListFindByField` | Find first item where field matches value |
| `ListFilterByField` | Get all items where field matches value |
| `ListSortByField` | Sort list by a field (ascending/descending) |
| `ListUpdateByField` | Update items where field matches |
| `ListRemoveByField` | Remove items where field matches |
| `ListSum` | Sum all numbers in a list |
| `ListSumField` | Sum a specific field across structs |
| `ListMaxField` | Get max value of a field |
| `ListMinField` | Get min value of a field |
| `ListGetField` | Extract a field from all items |
| `ListFirst` / `ListLast` | Get first/last item |
| `ListReverse` | Reverse list order |
| `ListSlice` | Get a portion of the list |
| `ListJoin` | Join list items into a string |

---

## � Audio Nodes

NodeCanvas provides audio playback nodes with multi-channel support:

### Audio Node Types

| Node | Description |
|------|-------------|
| `PlaySound` | Play an audio file on a channel |
| `StopSound` | Stop audio on a channel (or all) |

### PlaySound

| Input/Widget | Type | Description |
|--------------|------|-------------|
| `exec_in` | exec | Execution input |
| `file_path` | string | Path to audio file - connect an **audio variable** |
| `channel` | dropdown | **Music**, **Effect**, **Voice**, **UI**, **Ambient**, **Custom1-3** |
| `loop` | dropdown | **No** / **Yes** |

### StopSound

| Input/Widget | Type | Description |
|--------------|------|-------------|
| `exec_in` | exec | Execution input |
| `channel` | dropdown | **All**, **Music**, **Effect**, **Voice**, **UI**, **Ambient**, **Custom1-3** |

### Audio Channels

Use named channels to organize your sounds:

- **Music** - Background music tracks
- **Effect** - Sound effects (explosions, footsteps)
- **Voice** - Voice lines and dialogue
- **UI** - UI feedback sounds (clicks, hovers)
- **Ambient** - Environmental/ambient sounds
- **Custom1/2/3** - Additional channels for your needs

---

## �📁 Project Structure

```text
NodeCanvas/
├── py_editor/                # Main application package
│   ├── ui/                   # UI components (Canvas, Dialogs)
│   ├── core/                 # Core logic (IR, Backend, Templates)
│   ├── nodes/                # Node definitions
│   │   ├── base/            # Built-in node templates (JSON)
│   │   ├── composite/       # User-created composite nodes
│   │   └── graphs/          # Saved graph files
│   ├── plugins/             # Plugin packages (.json and .ncpkg)
│   └── tests/               # Test suite
├── assets/                   # Static assets
└── requirements.txt          # Python dependencies
```

---

## 🔌 Plugin System

NodeCanvas supports extensible plugins in two formats:

- **JSON Packages** (`.json`): Single file with multiple node definitions
- **Archive Packages** (`.ncpkg`): ZIP archives with nodes + Python modules

**Installing Plugins:**

1. Open **Settings → Plugins** tab
2. Click **Add Plugin...**
3. Select your `.json` or `.ncpkg` file
4. Nodes appear in the node menu under their category

**Included Plugins:**

- **MathUtilities**: Clamp, Lerp, Abs, Power, SquareRoot, Round
- **StringUtilities**: StringLength, Concatenate, ToUpperCase, ToLowerCase, StringReplace, StringSplit

See [plugins/README.md](py_editor/plugins/README.md) for creating custom plugins.

---

## 🚀 Getting Started

### Installation

```bash
# Clone the repository
git clone https://github.com/AnonMoon64/NodeCanvas.git
cd NodeCanvas

# Install dependencies
pip install -r requirements.txt

# Run the application
python -m py_editor.main
```

### Requirements

- Python 3.8+
- PyQt6
- See `requirements.txt` for full list

### Quick Start

1. **Add Nodes**: Right-click on canvas → Search for node type → Enter
2. **Connect Nodes**: Click output pin → drag → click input pin
3. **Set Values**: Click on input pins to enter constant values
4. **Execute**: Click "Run Graph" button to execute
5. **Debug**: Use Print nodes to see intermediate values

### Using Variables

1. **Create Variable**: Click **+ Add Variable** in the Variables panel
2. **Set Type**: Double-click the type column to change type
3. **Set Value**: Double-click the value column to edit
4. **Use in Graph**: Drag the variable onto the canvas
5. **Get vs Set**: Choose "Get" to read or "Set" to write

---

## 🗺️ Roadmap

### 📅 V3: Extended Libraries & Advanced Nodes (Planned)

#### Built-in Libraries

- Commenting system
- Math library (trigonometry, vectors, matrices)
- Custom MQTT library in C
- Custom crypto library in C
- String manipulation library
- File I/O library
- HTTP/API library

#### Advanced Node Types

- State machine nodes

### 📅 V4: Multi-Graph Projects & Collaboration (Future)

#### Project System

- Multiple graphs per project
- Graph-to-graph communication
- Event bus architecture

#### Collaboration Features

- Version control integration
- Graph diffing and merging

#### Plugin Marketplace

- Community node packs
- Template libraries
- Pre-built systems (game logic, UI kits, etc.)

---

## 🛠️ Architecture

### IR (Intermediate Representation)

NodeCanvas uses a language-neutral IR inspired by compiler design:

```python
# Canvas Graph → IR Module → Execution
graph = canvas.export_graph()
ir_module = backend.canvas_to_ir(graph, templates)
results = backend.execute_ir(ir_module)
```

This separation allows:

- Backend logic independent of UI
- Easy code generation targets
- Optimization passes on IR
- Testing without UI

### Node Templates

Nodes are defined as JSON templates:

```json
{
  "type": "base",
  "name": "Add",
  "category": "Math",
  "inputs": {
    "a": "float",
    "b": "float"
  },
  "outputs": {
    "result": "float"
  }
}
```

### Composite Nodes

Composites are sub-graphs saved as templates. They can be nested recursively, allowing complex reusable components.

---

## 🎨 Usage Examples

### Example 1: Simple Calculator

1. Add two `ConstInt` nodes with values `5` and `10`
2. Add an `Add` node
3. Connect the const nodes to the Add node's inputs
4. Add a `Print` node and connect the Add result
5. Run → See "15" in the output dialog

### Example 2: Composite Node

1. Select multiple nodes
2. Right-click → "Collapse Into Node"
3. Name it (e.g., "Calculate Average")
4. The selected nodes become a reusable composite
5. Use it anywhere like a normal node

### Example 3: Game Enemy System

1. Create a `list` variable with element type `struct`
2. Add enemies with fields: name (string), health (int), attack (int)
3. Use `ListFindByField` to find enemy by name
4. Use `ListFilterByField` to get all enemies with health > 0
5. Use `ListSortByField` to sort by attack power

### Example 4: Copy/Paste Between Projects

1. Select nodes in one graph
2. Ctrl+C to copy
3. Paste into text editor - see JSON
4. Copy JSON from text editor
5. Switch to another NodeCanvas instance
6. Ctrl+V - nodes appear with connections intact

---

## 🏗️ Architecture

NodeCanvas follows a clean, minimal pipeline:

```
Nodes (UI Graph) → IR (Intermediate Representation) → Backends
```

### Pipeline Overview

| Stage | Description |
|-------|-------------|
| **Nodes** | Visual graph you edit in the canvas |
| **IR** | Language-agnostic representation of logic & flow |
| **Backends** | Consume IR to interpret or generate code |

### Project Structure

```
py_editor/
  core/                         # Types + interfaces
    ir.py                       # IR types
    backend_base.py             # Abstract base classes
    graph_model.py              # Graph data model
    node_templates.py           # Template loading
    
  backends/                     # All backend implementations
    __init__.py                 # BACKENDS registry
    interpreter.py              # InterpreterBackend - executes in editor
    python.py                   # PythonCodegen - emits .py
    c.py                        # CCodegen - emits .c with SDL2
    cpp.py                      # CppCodegen - emits .cpp with SDL2
    wasm.py                     # WasmCodegen - emits .c for Emscripten
    codegen_common.py           # Shared C/C++/WASM helpers
    audio_runtime.py            # pygame audio for interpreter
    
  nodes/                        # Node definitions (JSON)
  ui/                           # UI components 
  plugins/                      # Plugin packages
```

### Usage

```python
from py_editor.backends import BACKENDS, InterpreterBackend, PythonCodegen, CodeGenConfig

# Via registry
backend = BACKENDS['python'](ir_module, "my_graph")
code = backend.generate()

# Interpret IR directly (live preview, Play button)
interpreter = InterpreterBackend()
result = interpreter.execute_ir(ir_module)

# Generate standalone Python code
codegen = PythonCodegen(ir_module, "my_graph")
python_code = codegen.generate()

# Generate C code with SDL2 audio
from py_editor.backends import CCodegen
config = CodeGenConfig(include_audio=True, variables=my_vars)
c_codegen = CCodegen(ir_module, config)
c_code = c_codegen.generate()
```

### Type-Specific Interpreters

Different file types use different execution models:

```python
from py_editor.backends import get_interpreter, execute_graph_file, INTERPRETERS

# Get interpreter by file type
interpreter = get_interpreter('.anim')  # Returns AnimInterpreter

# Execute a graph file directly
result = execute_graph_file('my_animation.anim', {'duration': 2.0})

# Access interpreter registry
print(INTERPRETERS)  # {'logic': LogicInterpreter, 'anim': AnimInterpreter, 'ui': UIInterpreter}
```

**Interpreter Types:**

| Interpreter | File Type | Execution Model |
|-------------|-----------|-----------------|
| `LogicInterpreter` | `.logic`, `.json` | Instant execution, returns immediately |
| `AnimInterpreter` | `.anim` | Timeline-based, yields each frame, supports keyframes |
| `UIInterpreter` | `.ui` | Event-driven, persistent state, never finishes |

**Yield/Finish Lifecycle:**

```python
# All interpreters support:
result = interpreter.enter(inputs)     # Start execution
result = interpreter.tick(delta_time)  # Advance (returns YIELDED or FINISHED)
result = interpreter.exit()            # Cleanup

# For async execution:
if result.state == ExecutionState.YIELDED:
    # Paused - call tick() again later
    pass
elif result.state == ExecutionState.FINISHED:
    # Complete - get outputs
    outputs = result.outputs
```

### Build System

The build system creates deployable packages with:

- **Composite node inlining** - Flattens composite nodes for codegen
- **Asset bundling** - Collects audio/images and copies to build folder
- **GUI wrapper** - Python/PyQt6 GUI that loads the compiled backend

```python
from py_editor.backends import BuildSystem, BuildConfig

config = BuildConfig(
    target='python',    # 'python', 'c', 'cpp', or 'wasm'
    output_dir='./build',
    app_name='my_app',
    include_gui=True,   # Generate PyQt6 wrapper
    include_assets=True # Bundle audio/images
)

builder = BuildSystem(config)
builder.build(ir_module, ui_data=ui_data, variables=variables)
```

**Build Output:**

```
my_app/
  main.py              # Entry point
  backend/
    logic.py           # Generated code (or .dll/.so for C/C++)
  gui/
    main_window.py     # PyQt6 UI
  assets/
    audio/             # Bundled audio files
    images/            # Bundled images
```

**Architecture:**

- Python GUI wraps ALL backends (consistent look)
- C/C++ backends compile to DLL/SO, loaded via ctypes
- WASM generates Emscripten-compatible C + HTML

---

## 🤝 Contributing

Contributions welcome! Areas that need help:

- More built-in node types
- Better error messages
- Performance optimization
- Documentation and tutorials
- Bug fixes

---

## 📄 License

MIT License - see LICENSE file for details

---

## 🙏 Acknowledgments

Inspired by:

- Unreal Engine Blueprints
- VSCode
- Blender Geometry Nodes

---

## 📞 Contact

- GitHub: [@AnonMoon64](https://github.com/AnonMoon64)
- Issues: [GitHub Issues](https://github.com/AnonMoon64/NodeCanvas/issues)

---

**Built with Python & PyQt6** | **Visual Programming for Everyone** | **NodeCanvas V3.0**
