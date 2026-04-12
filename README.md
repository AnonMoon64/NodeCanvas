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
* **Integrated Rendering**: Support for Point Lights, Directional Lights, and dynamic camera possess systems.

### 3. Advanced Procedural Landscapes
* **Multi-Threaded Streaming**: Asynchronous background generation pipeline ensures zero frame-stutters during world exploration.
* **GPU-Cached Rendering**: Uses **OpenGL Display Lists** to cache terrain chunks directly in VRAM, enabling 60FPS+ performance.
* **Vectorized Production**: A high-performance **NumPy-based noise engine** for lightning-fast terrain calculation.
* **Infinite Streaming**: Real-time terrain loading/unloading around the camera with configurable **Loading Radii**.
* **Dynamic Resolution (Detail Level)**: Fine-tune detail from **Low (16x16)** to **Very High (128x128)** per chunk.
* **Smooth Shading**: Integrated per-vertex normal sampling for organic, shaded terrain.

---

## 🔍 Honest State Assessment

As and Alpha-stage development environment, the following areas are currently identified as **Primary Development Focus**:

*   **Visual Polish**: The current lighting model uses a dual-pass fixed-function approach. While atmospheric, it lacks advanced shadows and Screen-Space Ambient Occlusion (SSAO).
*   **Materials**: Materials are currently vertex-colored per biome; full PBR texture support is in the pipeline.

---

## 🚧 Engineering Roadmap

### Phase 1: Landscape Fidelity (Current)
- [x] **Infinite Streaming**: Multi-threaded async loading.
- [x] **Smooth Normals**: Organic terrain shading.
- [x] **Detail Levels**: User-configurable grid resolution.
- [x] **High-Performance Procedural Engine**:
  - Vectorized noise generation using NumPy.
  - Multi-threaded asynchronous chunk streaming.
  - GPU-accelerated Display List caching.
  - **Advanced Blending**: Explicit layer weighting and post-process ocean flattening for geologic realism.
- [ ] **Advanced Biome Blending**: Smooth transitions between differing terrain types.

### Phase 2: Generation & Simulation
- [ ] **Erosion Simulation**: Hydraulic and thermal erosion for realistic mountain profiles.
- [ ] **Temperature + Humidity Simulation**: Dynamic climate maps that respond to latitude and elevation.
- [ ] **Dense Foliage & Ecosystems**: GPU-accelerated rendering for thousands of trees/bushes.

### Phase 3: Infrastructure & Physics
- [ ] **GPU-Accelerated Rendering**: Migrating the CPU-bound mesh generation to compute shaders.
- [ ] **Physics Integration**: Rigid body support for spawned actors on slopes.
- [ ] **Atmospheric Scattering**: Volumetric clouds and Rayleigh/Mie scattering for the skybox.

---

## 🏗 Getting Started

1. **Environment Setup**: Install dependencies via `pip install PySide6 numpy pyopengl`.
2. **Launch**: Run `python py_editor/main.py`.
3. **Tutorial**: Add a `Landscape` object from the Outliner, set its type to `Procedural`, and adjust the **Detail Level** in the Properties Panel.

*NodeCanvas is currently an experimental platform for procedural content generation research.*
