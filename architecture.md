# NodeCanvas Architecture

NodeCanvas is built on a modular "Separated Pipeline" architecture designed to cleanly divide visual scripting logic from the experimental 3D rendering compositor.

## 1. The Multi-Graph Logic Engine

- **Encapsulated Logic**: Organize behaviors into named graphs (e.g., `Main`, `WeatherSystem`, `ActorAI`).
- **Global Data Bus**: Shared project-wide variables allow different graphs to communicate and synchronize state.
- **Node UI**: Title labels float above node bodies to improve graph readability.
- **Node Properties Inspector**: Variadic nodes like **SelectInt** and **StringAppend** feature a dedicated Properties panel for dynamic pin management (+/- pins).
- **Inter-Graph Calls**: Use the `CallGraph` node to run sub-logic as functional routines.
- **Node UX**: Staggered Z-ordering for input widgets prevents dropdowns from being obscured by adjacent sliders or fields.
- **Canvas Rendering**: Hardware-accelerated canvas capable of handling basic to moderate node graphs.

## 2. The 3D Scene Compositor

- **Basic PBR Workflow**: Standard Metallic-Roughness properties (texture mapping is currently rudimentary and pending a full overhaul).
- **Hierarchical Outliner**: Manage scenes with object nesting and property editing.
- **Integrated Rendering**: Support for Point Lights, Directional Lights, and a **Global Shared OpenGL Context** to maintain material persistence between Editor and Play Mode.
- **Custom Shader Pipeline**: A flexible shader system with dynamic `.shader` file loading. Includes specialized vertex displacement shaders for **Fish Swimming** (sine-wave wiggling) and **Flag Waving** (cloth-sim approximation) with dynamic, UI-controllable parameters.
- **Simulation**: Basic camera possession and **Relative Sampling** (0-indexed local clocks) to help mitigate floating-point precision loss during execution.
- **Property Editor**: A unified row layout with synchronized sliders and batch update support. Includes **Per-Object Opacity** controls for transparency.
- **Autonomous Controllers**: A `BaseController` hierarchy allowing for simple **AI wandering** or **Direct Player Control**, selectable via the UI.

## 3. Compute & Procedural Generation

- **Dual-Stage Rendering**: Uses extremely low-poly "draft" generation before sharpening into higher-detail meshes to reduce severe pop-in.
- **Dithered Spawning**: Basic logic to throttle heavy vegetation and object generation over multiple frames, attempting to stabilize framerates during movement.
- **GPU-Cached Rendering**: Uses **OpenGL Display Lists** to cache terrain chunks directly in VRAM.
- **NumPy-Based Noise**: Uses vectorized operations in NumPy to speed up Python's otherwise slow procedural terrain calculations.
- **Chunk Streaming**: Real-time terrain loading/unloading around the camera based on an arbitrary loading radius.
- **Dynamic Resolution**: Trade detail for performance, scaling from 16x16 to 128x128 per chunk.
- **Experimental GPU Ocean**: A work-in-progress water system exploring FFT Displacement and Gerstner waves, implemented via custom GLSL shaders.
- **Experimental Voxel Planets**: Initial attempts at a chunk-based voxel system with dynamic resolution. Designed to overcome the limitations of flat planes, supporting small-to-medium planetoids with unit-based adaptive LOD.
  - **Laplacian Smoothing**: Configurable pass count (0–8) to help hide the blocky geometry underneath.
- **Compute Shader Boids**: An experimental test-bed exploring simple flocking simulations (Separation, Alignment, Cohesion) and Indirect Instancing pipelines offloaded to GPU compute units.
