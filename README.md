# NodeCanvas: Visual Logic & Procedural World-Building

NodeCanvas is an experimental platform designed to bridge the gap between **Visual Logic Programming** and **Real-time 3D Scene Composition**. It provides a development environment (inspired by professional engines) where logic graphs can be used to control simple procedural landscapes, atmospheric effects, and basic actor behaviors.

> [!CAUTION]
> **Experimental Alpha Build**: NodeCanvas is currently in active research and development by a solo developer. It is an experimental sandbox for tackling rendering and orchestration in Python. Many features are incomplete, unoptimized, or highly experimental.
>
> **Current Limitations**:
>
> - Materials are primarily vertex-colored per biome. High-fidelity PBR texture support is still in the pipeline.
>
- Performance can struggle at large scales or with high voxel resolutions (Current Baseline: ~110-120 FPS on Mid-Range HW).
- Physics and collision detection now feature a high-performance **Per-Chunk Voxel Collision** system using vectorized NumPy operations. Real-time sphere-vs-triangle collision is supported for dynamic objects, while GPU-driven agents (Fish/Boids) are exempt to allow for underwater movement.
- Ecosystems (Dense Foliage) and erosion simulations are still being developed.

> [!TIP]
> **Performance Investigation (April 2026)**: A deep-dive into frame timings identified the **Volumetric Clouds (Raymarching)** and **FFT Ocean (CPU-Side Simulation)** as the primary overhead sources. Lowering the `cloud_steps` or `ocean_fft_resolution` can significantly boost FPS.

## ✨ Core Philosophy

Instead of relying solely on heavy C++ engines, NodeCanvas investigates how far we can push Python, Python-bound OpenGL (PyOpenGL), and compute shaders to orchestrate logic, rendering, and procedural terrain components. The logic engine is entirely node-based, allowing you to visually wire data flows and trigger basic environmental events in real-time.

---

## 🚀 Key Features

### 🧩 The NodeCanvas Editor

- **Dockable Workspace**: Customizable UI with Global Settings, real-time FPS logging, and a hierarchy Outliner.
- **Variable Management**: Create and track Complex Types (Vector2/3, Arrays, Maps, Structs). Drag-and-drop variables to the visual canvas to generate Get/Set nodes.
- **Plugin Architecture**: Dynamically load `.json` or `.ncpkg` logic modules.
- **Improved Explorer UX**: Navigation state persistence (folders stay expanded during refreshes) and automated context-aware asset creation.

### 🌍 Real-Time Orchestration

- **Experimental Voxel Planets**: Early implementation of chunk-based voxel planets using adaptive LOD and basic noise layers.
- **Unified Physics**: Per-chunk triangle collision for voxel terrain ensures dynamic objects interact physically with the world surface.
- **Compute Shader Boids**: An experimental test-bed exploring GPU-driven schooling mechanics and indirect instancing.
- **Basic Atmosphere & Weather**: Experimental day-night cycles, simple scattering models, and procedural rain/snow streaming.
- **NEW: Procedural Biome Spawner**: Shader-driven foliage placement (Grass, Rocks, etc.) with dynamic UI property detection.
- **Enhanced: Voxel Water Shader**: Real-time shader-driven waves and rain-impact ripples with vertex displacement.

- **Modular Asset Pipeline**:
  - Material `.material` system with PBR support and automated creation from textures.
  - Drag-and-drop `.prefab` support with automated creation from `.mesh`.
  - Interactive `.shader` file mapping.
  - Native binary `.mesh` conversion with manual rotation bake and normal recalculation pipeline.
  - Spawner system `.spawner` with GPU-driven boids.
  - Controller system `.controller` with AI wandering or direct player control.

Todo:

- Change ocean chunk generation to use a large plane that follows the player.
- [x] Add voxel water (Shader waves, rain ripples, and surging).
- Improve the spawner system to support more than 1000 boids.
- **Work in Progress**: Voxel World Biome Spawning & Dynamic Shader UI.
- **Work in Progress**: Hierarchy Outliner Synchronization.

---

## 🏗 Technical Architecture

For an in-depth breakdown of the Multi-Graph Logic Engine, Compute Shader allocations, and the 3D Compositor pipeline, please read our technical document:
👉 [Read the Architecture Summary](architecture.md)

---

## 🛠️ Getting Started

### Prerequisites

NodeCanvas relies heavily on Python and OpenGL.

```bash
pip install PyQt6 numpy pyopengl
```

### Launching the Editor

Run the main entry point to start the NodeCanvas environment:

```bash
python py_editor/main.py
```

### First Steps in the Sandbox

1. Open the **Outliner**.
2. Right-click and add a **Landscape** (deprecated) or **Voxel World Flat**, **Voxel World Sphere**, **Voxel Water Flat**, or **Voxel Water Round** object.
3. In the **Properties Panel**, set the environment parameters (radius, biome colors, noise scales).
4. Drop a **Weather** primitive into the scene and open the **Logic Canvas** to wire up procedural weather triggers.

## ⚡ Performance Documentation

Recent profiling of the `paintGL` loop identified the following sources of overhead:

| Component | Type | Description | % Frame Time (Approx) |
| :--- | :--- | :--- | :--- |
| **Volumetric Clouds** | GPU | Raymarching with 48+ steps and multi-octave fBm noise per fragment. | ~35-45% |
| **FFT Ocean** | CPU/GPU | 21 `ifft2` calls per frame (3 cascades) on the CPU + high-frequency texture uploads. | ~20-25% |
| **Voxel World** | CPU/GPU | Recursive chunk visibility logic and high draw-call counts for complex LOD states. | ~15-20% |
| **QPainter Overlay** | System | Viewport overlays (logic logs, orientation widget) require a GL context switch. | ~5-10% |

### 🛠 Optimization Tips

- **Reduce Cloud Steps**: In the `Weather` or `Atmosphere` properties, reduce `cloud_steps` from 48 down to 16 or 24 for a drastic FPS boost with minimal visual loss.
- **Lower Ocean Resolution**: Set `ocean_fft_resolution` to 64 instead of 128/256 to reduce CPU-side FFT overhead.
- **Toggle Voxel V-Sync**: Ensure `fmt.setSwapInterval(1)` in `scene_view.py` isn't capping your frame rate if testing on high-refresh monitors.

---

*NodeCanvas is a passion project exploring the outer limits of Python-driven procedural generation and AI tool orchestration.*
