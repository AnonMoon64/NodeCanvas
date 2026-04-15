# NodeCanvas: Visual Logic & Procedural World-Building

- **GPU-Accelerated Boids System**: Implemented a high-performance flocking simulation using **Compute Shaders** and **Spatial Partitioning (Uniform Grid)**. Supports up to 30,000 agents (fish and birds) with real-time autonomous schooling behavior.
- **Advanced 4-Layer Procedural Motion**: Integrated sophisticated vertex displacement for aquatic and avian life:
  - **Fish**: Primary Yaw, Side-translation, Roll, and Secondary Yaw (Flag motion).
  - **Birds**: Wing-flap frequency and pitch-modulation based on vertical velocity.
- **Indirect Instanced Rendering**: Dramatically reduced draw calls by utilizing hardware instancing, allowing the GPU to manage thousands of actors with a single command.
- **Unified Shader Architecture**: Added a global `SHADER_REGISTRY` with selectable presets including **Fish Swimming** and **Flag Waving** procedural effects.
- **Batch Editing & Multi-Selection**: Fully implemented Ctrl+Click selection in the viewport with synchronized property inspector updates for simultaneous multi-object transformation.
- **Controller Inheritance Hierarchy**: Established a formal `BaseController` → `AI/PlayerController` inheritance structure in `py_editor/core/controller.py` for structured autonomous behavior development.
- **Modular Refactor (Stable)**: Codebase fully transitioned to a modular orchestrator model.
- **Stable Logic Engine**: Established a deterministic, one-shot execution model for visual scripting with support for cross-graph `Message` nodes and `Custom Events`.
- **Logic Validation Pipeline**: Added a headless testing suite (`tests/test_logic_run.py`) for validating complex logic flows without UI overhead.
- **Ultra Dynamic Atmosphere**: Implemented a high-fidelity scattering model with **Zenith-based Sky Grading**, **Mie halos**, and seamless **Land-to-Space** transitions (sky blue → black starfield).
- **Professional UX**: Implemented a **UE5-style Dockable Workspace** and **On-Screen Viewport Logging** for real-time debugging feedback.
- **Enhanced Navigation**: Restored full **WASD + Mouse-look (RMB)** flight controls in the 3D viewport, including a real-time **Camera Speed Overlay**.
- **Custom Mesh System**: Integrated a high-performance **binary .mesh format (NCMS)** with a native **OBJ conversion pipeline**. Models are optimized for fast GPU loading and render with custom textures.
- **Persistence 1.0**: Full `.scene` serialization implemented. Save and Load your procedural environments instantly.
- **AI Agent Tool Stability**: Implemented a thread-safe multi-threaded bridge for AI agent tool execution. This ensures all AI-generated nodes and connections are immediately visible and correctly indexed by the QGraphicsScene.

> [!CAUTION]
> **Experimental Alpha Build**: This project is in active development. Features listed below are in various stages of completion. NodeCanvas is currently an experimental platform for procedural content generation research and real-time world orchestration.

NodeCanvas is a high-performance orchestration platform designed to bridge the gap between **Visual Logic Programming** and **Real-time 3D Scene Composition**. It provides a unified environment where logic graphs can drive complex procedural landscapes, lighting systems, and actor behaviors.

---

## 🏗 Core Architecture

NodeCanvas is built on a modular "Separated Pipeline" architecture:

### 1. The Multi-Graph Logic Engine
* **Encapsulated Logic**: Organize complex behaviors into named graphs (e.g., `Main`, `WeatherSystem`, `ActorAI`).
* **Global Data Bus**: Shared project-wide variables allow different graphs to communicate and synchronize state.
* **Inter-Graph Calls**: Use the `CallGraph` node to run sub-logic as functional routines.
* **Performance Optimized**: A hardware-accelerated canvas designed to handle hundreds of nodes with zero lag.

### 2. The 3D Scene Compositor
* **PBR Workflow**: Industry-standard Metallic-Roughness workflow for realistic surface properties.
* **Hierarchical Outliner**: Manage complex scenes with deep object nesting and bulk property editing.
* **Integrated Rendering**: Support for Point Lights, Directional Lights, and a **Global Shared OpenGL Context** with **Context-Aware Display List Caching** to ensure seamless material persistence between the Editor and Play Mode.
* **Custom Shader Pipeline**: A flexible shader system with a selectable **Shader Registry**. Includes specialized vertex displacement shaders for **Fish Swimming** (sine-wave wiggling) and **Flag Waving** (cloth-sim approximation) with dynamic, UI-controllable parameters and **Multi-Axis Support** (X, Y, or Z forward).
* **Simulation Stability**: Robust camera possession and **High-Precision Relative Sampling** (0-indexed local clocks) to eliminate floating-point precision loss and ensures a rock-solid world-building experience.
* **Precision Property Editor**: A redesigned inspector with a **Unified Row Layout**, synchronized **PropertySliders**, and **Batch Update Support**. Includes **Per-Object Opacity** controls for fine-tuning transparency.
* **Autonomous Controllers**: Implemented a structured `BaseController` hierarchy allowing for **AI autonomous wandering** or **Direct Player Control** axes, selectable via an explicit **Controller Type** dropdown in the UI.

### 3. Advanced Procedural Landscapes
* **Seamless Discovery Pipeline**: Features a **Dual-Stage Rendering** system that eliminates visual "flashing." New terrain areas appear instantly as **Cached Draft Meshes** (low-poly VRAM previews) and progressively "sharpen" into high-detail geometry.
*   **Liquid-Smooth Performance**: Integrated **Dithered Spawning** logic throttles heavy vegetation and object generation to ensure a consistent 60FPS even when flying at high speeds through infinite worlds.
* **GPU-Cached Rendering**: Uses **OpenGL Display Lists** to cache both high-res and draft terrain chunks directly in VRAM, enabling 60FPS+ performance.
* **Vectorized Production**: A high-performance **NumPy-based noise engine** for lightning-fast terrain calculation.
* **Infinite Streaming**: Real-time terrain loading/unloading around the camera with configurable **Loading Radii**.
* **Dynamic Resolution (Detail Level)**: Fine-tune detail from **Low (16x16)** to **Very High (128x128)** per chunk.
* **Smooth Shading**: Integrated per-vertex normal sampling for organic, shaded terrain.
* **GPU-Accelerated Ocean**: A full real-time water system powered by **Gerstner Wave Shaders** and static GPU VBO grids for infinite, fluid-animated seas. Includes **Double-Sided Rendering** for seamless underwater viewing.
* **Planetary Voxel Engine**: A fully overhauled voxel system for rendering procedural planets from pebble to Earth scale.
  - **Corrected Surface Nets**: Fixed float32/float64 GL upload bug and Perlin lattice truncation bug that caused vertex spikes and screen-filling corruption.
  - **Exposed Resolution Control**: Per-object grid resolution (16–256) lets you trade generation speed for surface detail.
  - **Laplacian Smoothing**: Configurable pass count (0–8) eliminates the blocky voxel look and produces organic terrain.
  - **Multi-Type Noise Layers**: Each layer independently selects from `perlin`, `fbm`, `ridged`, `voronoi`, or `caves` noise. Layers support rename, reorder, save/load JSON presets, and `add`/`subtract`/`multiply` blend modes.
  - **Voxel Biomes**: Same data structure as the Landscape primitive — height/slope ranges, surface color, roughness and metallic per biome, fully editable in the Properties panel.
  - **Ocean World Primitive**: New spherical ocean object (`ocean_world`) renders animated wave normals and Fresnel shading on a planet surface using a custom GLSL shader.
  - **Realistic Sun Disk**: Atmosphere shader rewritten — sun disk uses physically-motivated `disk_pow = 60000 / sun_size²` giving the correct ~0.5° angular diameter at `sun_size=1`. Includes separate inner corona and Mie halo passes.
  - **Improved Clouds**: Domain-warped fBm with 6 octaves, wind drift, top-lit self-shadowing, and wispy edge detail replaces the flat single-quad placeholder.
  - **Outliner Single-Selection Fix**: Single objects now correctly highlight and emit selection events in all cases.

---

## 🔍 Honest State Assessment

As and Alpha-stage development environment, the following areas are currently identified as **Primary Development Focus**:

*   **Visual Polish**: The current lighting model uses a dual-pass fixed-function approach. While atmospheric, it lacks advanced shadows and Screen-Space Ambient Occlusion (SSAO).
*   **Materials**: Materials are currently vertex-colored per biome; full PBR texture support is in the pipeline.
*   **Ocean Foam**: The current foam system is a visual placeholder. It effectively simulates surface brightness/crests but lacks the "bubbly" volumetric detail and physically-based bubble noise required for production-grade realism. A complete overhaul is planned.

---

## 🚧 Engineering Roadmap

### Phase 1: Landscape Fidelity (Current)
- [x] **Infinite Streaming**: Multi-threaded async loading.
- [x] **Smooth Normals**: Organic terrain shading.
- [x] **Hardened Persistence**: 
  - Centralized **.scene** format for full world serialization.
  - Full persistence for landscape properties (Resolution, Radius, Chunk Size).
  - Integrated **Camera State Persistence** (retains position/rotation on load).
- [x] **Extreme Performance**:
  - **Quad-Chunk Discovery**: Optimized spawner processes multiple areas per tick.
  - **Billboard Correction**: Fixed invalid OpenGL states for flickering-free vegetation.
  - **VRAM Caching**: Optimized display lists for consistent 60FPS exploration.
- [x] **Advanced Blending**: Explicit layer weighting and post-process ocean flattening for geologic realism.
- [x] **GPU-Accelerated Ocean**: Real-time Gerstner wave simulation on the GPU.
- [x] **Advanced Smoothing**: User-configurable 0-1 smoothing slider for sanding off mountain peaks.
- [ ] **Advanced Biome Blending**: Smooth transitions between differing terrain types.

### Phase 2: Generation & Simulation
- [ ] **Erosion Simulation**: Hydraulic and thermal erosion for realistic mountain profiles.
- [ ] **Temperature + Humidity Simulation**: Dynamic climate maps that respond to latitude and elevation.
- [ ] **Dense Foliage & Ecosystems**: GPU-accelerated rendering for thousands of trees/bushes.

### Phase 3: Infrastructure & Physics
- [x] **GPU-Accelerated Rendering**: Migrating the CPU-bound mesh generation to vertex/compute shaders.
- [x] **High-Performance Swarms**: Integrated **Compute-Shader Boids** (Separation, Alignment, Cohesion) with **Indirect Instancing**.
- [x] **Custom Mesh Pipeline**: Native **.obj to .mesh** binary conversion and hardware-accelerated model rendering.
- [x] **Atmospheric Scattering**: Volumetric clouds and Rayleigh/Mie scattering with Zenith-based grading and land-to-space transitions.
- [ ] **Physics Integration**: Rigid body support for spawned actors on slopes.

### Phase 4: Security & Ecosystem (Long-Term)
- [ ] **Sandboxed Logic Execution**: implementing a secure environment for visual script execution to prevent arbitrary code execution from untrusted projects.
- [ ] **Secure Asset Registry**: Establishing a verified pipeline for sharing logic graphs and procedural assets.
- [ ] **Encrypted Serialization**: Optional encryption for .scene and .logic files to protect proprietary procedural algorithms.

---

---

## 🎯 Project Vision & Roadmap

The current focus is on creating a photorealistic, physically-based world environment. We are building this in layers to ensure stability and performance at every step.

### 🌊 The Ocean Roadmap
*   **Layer 1: Motion (Done)** – Wave speed, height, and Gerstner-based direction blending.
*   **Layer 2: Surface (Done)** – Shorter-crested Gerstner peaks, reflection tints, and animated foam.
*   **Layer 3: Integration (In Progress)** – Shoreline depth-blending and vertical bias stabilization.

### 💡 High-Impact Features Pipeline

| **Category** | **Planned Features** |
| :--- | :--- |
| **Ocean** | Underwater Mode, Buoyancy Integration, Wake Trails, Storm/Tide Sliders |
| **World** | Foliage Scatter (Trees/Grass), Road/Path Gen, Dynamic Weather, NPC Pathing |
| **Editor** | Material Node Editor, Terrain Paint-Brushes, Save-able Camera Bookmarks |
| **Atmosphere** | Skybox/Day-Night Cycle, Volumetric Clouds, Rayleigh Scattering |
| **Security** | Sandboxed Execution, Malicious Project Detection, Secure Plugin API |

---

## 🏗 Getting Started

1. **Environment Setup**: Install dependencies via `pip install PyQt6 numpy pyopengl`.
2. **Launch**: Run `python py_editor/main.py`.
3. **Logic Testing**: Run `python tests/test_logic_run.py` to verify the stability of the logic interpreter.
4. **Tutorial**: Add a `Landscape` object from the Outliner, set its type to `Procedural`, and adjust the **Detail Level** in the Properties Panel.

*NodeCanvas is currently an experimental platform for procedural content generation research.*
