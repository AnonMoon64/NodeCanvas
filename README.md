# NodeCanvas: Visual Logic & Procedural World-Building

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
* **Simulation Stability**: Robust camera possession and **High-Precision Relative Sampling** (0-indexed local clocks) to eliminate floating-point precision loss and ensures a rock-solid world-building experience.
* **High-Fidelity Ocean Engine**: An infinite sea surface powered by **Enhanced Gerstner Wave Shaders** with XYZ displacement, physical normals, and **Jacobian-based Soft Foam**. Featuring high-gloss specular glints and Fresnel reflections for a premium 60FPS aesthetic.
* **Precision Property Editor**: A redesigned inspector with a **Unified Row Layout** and synchronized **PropertySliders**, providing gesture control and decimal precision without UI overlap.

### 3. Advanced Procedural Landscapes
* **Seamless Discovery Pipeline**: Features a **Dual-Stage Rendering** system that eliminates visual "flashing." New terrain areas appear instantly as **Cached Draft Meshes** (low-poly VRAM previews) and progressively "sharpen" into high-detail geometry.
*   **Liquid-Smooth Performance**: Integrated **Dithered Spawning** logic throttles heavy vegetation and object generation to ensure a consistent 60FPS even when flying at high speeds through infinite worlds.
* **GPU-Cached Rendering**: Uses **OpenGL Display Lists** to cache both high-res and draft terrain chunks directly in VRAM, enabling 60FPS+ performance.
* **Vectorized Production**: A high-performance **NumPy-based noise engine** for lightning-fast terrain calculation.
* **Infinite Streaming**: Real-time terrain loading/unloading around the camera with configurable **Loading Radii**.
* **Dynamic Resolution (Detail Level)**: Fine-tune detail from **Low (16x16)** to **Very High (128x128)** per chunk.
* **Smooth Shading**: Integrated per-vertex normal sampling for organic, shaded terrain.
* **GPU-Accelerated Ocean**: A full real-time water system powered by **Gerstner Wave Shaders** and static GPU VBO grids for infinite, fluid-animated seas.

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
- [/] **GPU-Accelerated Rendering**: Migrating the CPU-bound mesh generation to vertex/compute shaders.
- [ ] **Physics Integration**: Rigid body support for spawned actors on slopes.
- [ ] **Atmospheric Scattering**: Volumetric clouds and Rayleigh/Mie scattering for the skybox.

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

---

## 🏗 Getting Started

1. **Environment Setup**: Install dependencies via `pip install PyQt6 numpy pyopengl`.
2. **Launch**: Run `python py_editor/main.py`.
3. **Tutorial**: Add a `Landscape` object from the Outliner, set its type to `Procedural`, and adjust the **Detail Level** in the Properties Panel.

*NodeCanvas is currently an experimental platform for procedural content generation research.*
