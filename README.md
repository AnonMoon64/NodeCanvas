# NodeCanvas: Visual Logic & Procedural World-Building

## 🌅 What's New — Dynamic Sky, Weather & Particle Overhaul

- **Volumetric 3D Clouds** (raymarched): fBm+worley density, wind-advected, with
  self-shadowing, HG phase (forward + back scatter), anvil bias near tops, and
  a tunable [bottom, top] slab. Looks correct from below, inside, and above.
- **Spherical-Planet Atmosphere**: the Atmosphere primitive can now wrap onto
  a sphere. Fly up past `atmosphere_thickness` and the sky fades to space
  with a glowing **atmospheric rim**. Rayleigh + Mie scattering, soft sunset
  reddening, **god rays**, a **moon and stars** that appear at night, and an
  **exposure/tonemap** stage. A live `time_speed` property auto-advances
  time of day; crossing midnight increments `date_day_index`.
- **Weather Primitive**: a *global controller* — not a local emitter — that
  drives the particle system to render rain / snow / storm / fog / sandstorm
  *only where the camera is*. Two world modes:
  - **Flat infinite**: weather tiles over an XZ grid that drifts with the
    wind vector.
  - **Spherical**: cells derived from lat/lon on the planet.
  Weather is **procedural**: a `(cell, day, time-bucket, world_seed)` hash
  deterministically picks the weather type and intensity. Manual override is
  available. Weather auto-reads time/date from the Atmosphere primitive (or
  falls back to its internal clock if none exists).
- **Particle System 2.0** — richer, streaming-aware, and flexible enough to
  back every weather effect:
  - New forces: `wind`, `turbulence`, `vortex`, `attractor`, `curl` noise
    (divergence-free eddies), plus gravity/drag.
  - Animated **size/alpha curves** (piecewise-linear LUTs) and per-particle
    velocity stretch (rain strands, sparks).
  - **Distance LOD / streaming**: `stream_radius` gates spawning and
    `cull_radius` kills far particles, making global weather cheap.
  - **Camera-follow spawn discs** so weather emitters trail the player
    automatically — the weather controller only re-registers a new emitter
    when the weather *type* changes.
  - Extra presets: **Rain**, **Snow**, **Fire**, **Smoke**, **Sparks**,
    **Dust**, **Mist**, **Spray** (plus the originals).
- **New Particle Graph Nodes**: `Burst`, `ForceField`, `WeatherControl` — in
  addition to the existing `Emitter`. Drive effects live from logic graphs.
- **Directional Light — Fixed**: the old sun direction was inverted at noon
  and the GL light was never synced to time-of-day. The viewport now drives
  `GL_LIGHT0` from the Atmosphere's live sun direction + color, so meshes and
  primitives darken at night and warm up at sunset. Explicit
  `light_directional` objects override the sun.
- **Ocean Spray Polish**: new preset blends gravity + drag + turbulence with
  a softer droplet curve and stretch option for heavy foam days.
- **Stability & Scale Fixes**:
  - **Metric Scale Standard**: Adopted a strict **1.0 unit = 1.0 meter** standard across all primitives, ensuring logical proportions between human-scale actors (1.8m), ocean waves (1-5m), and hills (60m).
  - **Hardened Viewport UI**: Reinforced the XYZ orientation widget with insulated 2D/3D state management; it remains visible even during complex 3D rendering passes.
  - **Weather Tracking**: Fixed the 'outrun' effect — rain, snow, and storm particles are now physically linked to the camera's world-position reference, ensuring you are always at the heart of the storm.
  - **Dynamic Ocean Ripples**: Optimized ripple dissipation and logic search radii (180m) to provide persistent, trailing impact effects behind the camera.
  - **UI Contextual Power**: Added professional context menus to the File Explorer (New Folder, New Logic) and Variable Panel (Add, Duplicate, Delete) for a faster workspace experience.

---

- **GPU-Accelerated Boids System**: Implemented a high-performance flocking simulation using **Compute Shaders** and **Spatial Partitioning (Uniform Grid)**. Supports up to 30,000 agents (fish and birds) with real-time autonomous schooling behavior.
- **Advanced 4-Layer Procedural Motion**: Integrated sophisticated vertex displacement for aquatic and avian life:
  - **Fish**: Primary Yaw, Side-translation, Roll, and Secondary Yaw (Flag motion).
  - **Birds**: Wing-flap frequency and pitch-modulation based on vertical velocity.
- **Indirect Instanced Rendering**: Dramatically reduced draw calls by utilizing hardware instancing, allowing the GPU to manage thousands of actors with a single command.
- **Unified Shader Architecture**: Added a global `SHADER_REGISTRY` with selectable presets including **Fish Swimming** and **Flag Waving** procedural effects.
- **Batch Editing & Multi-Selection**: Fully implemented Ctrl+Click selection in the viewport with synchronized property inspector updates for simultaneous multi-object transformation.
- **Controller Inheritance Hierarchy**: Established a formal `BaseController` → `AI/PlayerController` inheritance structure in `py_editor/core/controller.py` for structured autonomous behavior development.
- **Stable Logic Engine**: Established a deterministic, one-shot execution model for visual scripting with support for cross-graph `Message` nodes, recursive `CallLogic` sub-graph execution, and reliable template-aware pin mapping for complex data flows.
- **Logic Validation Pipeline**: Added a headless testing suite (`tests/test_logic_run.py`) for validating complex logic flows without UI overhead.
- **Robust Multi-Selection**: Synchronized selection system that resolves object IDs to instances, maintaining stable multi-selection state between the Hierarchy Outliner, Viewport, and Properties Inspector.
- **Ultra Dynamic Atmosphere**: Implemented a high-fidelity scattering model with **Zenith-based Sky Grading**, **Mie halos**, and seamless **Land-to-Space** transitions (sky blue → black starfield).
- **Professional UX**: Implemented a **UE5-style Dockable Workspace**, **Global Settings Dialog**, **Real-time FPS Counter**, and **On-Screen Viewport Logging** for real-time debugging feedback.
- **Plugin & Template Management**: Integrated a comprehensive **Settings** suite for:
  - **Dynamic Node Templates**: Create, edit, and delete custom node definitions in real-time.
  - **Plugin Package Orchestration**: Install `.ncpkg` archives or `.json` packages to expand the node ecosystem.
  - **Autonomous Export**: Package your custom logic nodes and Python modules into distributable plugin archives.
- **Enhanced Variable Workflow**: Redesigned the Variables panel to support a **UE5-inspired workflow**:
  - **Complex Data Support**: Expanded type system supporting **Vector2**, **Vector3**, **Arrays**, **Maps**, **Structs**, and **Enums**.
  - **In-Place Editing**: Double-click to rename, change types, or edit default values directly in the list.
  - **Auto-Naming**: One-click variable creation with intelligent default name generation.
  - **Type-Safe Accessors**: Drag-and-drop variables onto the canvas to instantly create Get/Set nodes with pre-populated references.
- **AI Agent Autonomy & Self-Verification**:
  - **Mandatory Quality Loop**: The AI agent (Atom) now performs static graph validation and reachability analysis before finishing tasks.
  - **Dynamic Simulation Verification**: Atom can "run" logic in a sandbox, inspect logs, and debug its own wiring errors autonomously.
  - **Chain-of-Thought Reasoning**: Explicit thought steps and progress reporting for complex multi-node system generation.
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

- **Encapsulated Logic**: Organize complex behaviors into named graphs (e.g., `Main`, `WeatherSystem`, `ActorAI`).
- **Global Data Bus**: Shared project-wide variables allow different graphs to communicate and synchronize state.
- **Modernized Node UI**: Title labels now **float elegantly above** node bodies, reducing visual clutter and improving graph readability.
- **Node Properties Inspector**: Highly interactive variadic nodes like **SelectInt** and **StringAppend** feature a dedicated Properties panel for dynamic pin management (+/- pins).
- **Inter-Graph Calls**: Use the `CallGraph` node to run sub-logic as functional routines.
- **Node UX Fixes**: Staggered Z-ordering for input widgets prevents dropdowns (Presets/Sources) from being obscured by adjacent sliders or fields.
- **Performance Optimized**: A hardware-accelerated canvas designed to handle hundreds of nodes with zero lag.

### 2. The 3D Scene Compositor

- **PBR Workflow**: Industry-standard Metallic-Roughness workflow for realistic surface properties.

- **Hierarchical Outliner**: Manage complex scenes with deep object nesting and bulk property editing.
- **Integrated Rendering**: Support for Point Lights, Directional Lights, and a **Global Shared OpenGL Context** with **Context-Aware Display List Caching** to ensure seamless material persistence between the Editor and Play Mode.
- **Custom Shader Pipeline**: A flexible shader system with a selectable **Shader Registry**. Includes specialized vertex displacement shaders for **Fish Swimming** (sine-wave wiggling) and **Flag Waving** (cloth-sim approximation) with dynamic, UI-controllable parameters and **Multi-Axis Support** (X, Y, or Z forward).
- **Simulation Stability**: Robust camera possession and **High-Precision Relative Sampling** (0-indexed local clocks) to eliminate floating-point precision loss and ensures a rock-solid world-building experience.
- **Precision Property Editor**: A redesigned inspector with a **Unified Row Layout**, synchronized **PropertySliders**, and **Batch Update Support**. Includes **Per-Object Opacity** controls for fine-tuning transparency.
- **Autonomous Controllers**: Implemented a structured `BaseController` hierarchy allowing for **AI autonomous wandering** or **Direct Player Control** axes, selectable via an explicit **Controller Type** dropdown in the UI.

### 3. Advanced Procedural Landscapes

- **Seamless Discovery Pipeline**: Features a **Dual-Stage Rendering** system that eliminates visual "flashing." New terrain areas appear instantly as **Cached Draft Meshes** (low-poly VRAM previews) and progressively "sharpen" into high-detail geometry.

- **Liquid-Smooth Performance**: Integrated **Dithered Spawning** logic throttles heavy vegetation and object generation to ensure a consistent 60FPS even when flying at high speeds through infinite worlds.
- **GPU-Cached Rendering**: Uses **OpenGL Display Lists** to cache both high-res and draft terrain chunks directly in VRAM, enabling 60FPS+ performance.
- **Vectorized Production**: A high-performance **NumPy-based noise engine** for lightning-fast terrain calculation.
- **Infinite Streaming**: Real-time terrain loading/unloading around the camera with configurable **Loading Radii**.
- **Dynamic Resolution (Detail Level)**: Fine-tune detail from **Low (16x16)** to **Very High (128x128)** per chunk.
- **Smooth Shading**: Integrated per-vertex normal sampling for organic, shaded terrain.
- **GPU-Accelerated Ocean**: A high-fidelity water system powered by **Multi-Cascade FFT Displacement** (1000m, 200m, 50m cascades) and Gerstner "Hero" waves. Includes hardware-accelerated VBO grids and synchronized displacement/normal mapping.
- **Planetary Voxel Engine**: A fully overhauled voxel system for rendering procedural planets from pebble to Earth scale.
  - **Corrected Surface Nets**: Fixed float32/float64 GL upload bug and Perlin lattice truncation bug that caused vertex spikes and screen-filling corruption.
  - **Exposed Resolution Control**: Per-object grid resolution (16–256) lets you trade generation speed for surface detail.
  - **Laplacian Smoothing**: Configurable pass count (0–8) eliminates the blocky voxel look and produces organic terrain.
  - **Multi-Type Noise Layers**: Each layer independently selects from `perlin`, `fbm`, `ridged`, `voronoi`, or `caves` noise. Layers support rename, reorder, save/load JSON presets, and `add`/`subtract`/`multiply` blend modes.
  - **Voxel Biomes**: Same data structure as the Landscape primitive — height/slope ranges, surface color, roughness and metallic per biome, fully editable in the Properties panel.
  - **Unit-Based Adaptive LOD**: Advanced chunked LOD system using fixed unit scales (**1.0u, 4.0u, 16u, 64u**). Distant terrain resolution is aggressively reduced to maintain performance on planetary scales.
  - **Refined Detail Presets**: Default voxel block size updated to **1.0 unit (Medium)** for optimal performance-to-detail ratio on Earth-sized worlds.
  - **Safety Warnings**: Integrated performance warnings in the UI when attempting to disable LOD on large-scale objects.
  - **Ocean World Primitive**: New spherical ocean object (`ocean_world`) renders animated wave normals and Fresnel shading on a planet surface using a custom GLSL shader.
  - **Realistic Sun Disk**: Atmosphere shader rewritten — sun disk uses physically-motivated `disk_pow = 60000 / sun_size²` giving the correct ~0.5° angular diameter at `sun_size=1`. Includes separate inner corona and Mie halo passes.
  - **Improved Clouds**: Domain-warped fBm with 6 octaves, wind drift, top-lit self-shadowing, and wispy edge detail replaces the flat single-quad placeholder.
  - **Outliner Single-Selection Fix**: Single objects now correctly highlight and emit selection events in all cases.

---

## 🔍 Honest State Assessment

As and Alpha-stage development environment, the following areas are currently identified as **Primary Development Focus**:

- **Visual Polish**: The current lighting model uses a dual-pass fixed-function approach. While atmospheric, it lacks advanced shadows and Screen-Space Ambient Occlusion (SSAO).
- **Materials**: Materials are currently vertex-colored per biome; full PBR texture support is in the pipeline.
- **Ocean Surface Fidelity**: Balanced Physically-Based shading system with **Triple-Layer Specular** (Broad Sheen, Tight Glint, Sub-pixel Sparkle) and **Always-on SSS Rim lighting**.
- **Advanced Foam System**: Implemented a 3-layer responsive foam engine:
  - **Jacobian Fold Foam**: Simulates foam at wave breaking points.
  - **Height Whitecaps**: Artist-controlled crest density.
  - **Animated Streaks**: Wind-aligned trails that drag behind moving crests.
  - **Persistent Advection**: CPU-side foam density buffer that advects using water velocity.
  - **Flowmap Panning**: Shader-integrated flowmap technique for high-quality foam and bubble motion.

---

## 🚧 Engineering Roadmap

### Phase 1: Landscape Fidelity (Current)

- [x] **Infinite Streaming**: Multi-threaded async loading.
- [x] **Smooth Normals**: Organic terrain shading.
- [x] **Hardened Persistence**:
  - Centralized **.scene** format for full world serialization.
  - Full persistence for landscape properties (Resolution, Radius, Chunk Size).
  - Integrated **Camera State Persistence** (retains position/rotation on load).
- [ ] **Extreme Performance**:
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

- **Layer 5: Integration (Done)** – Shoreline depth-blending and vertical bias stabilization.
- **Layer 6: VFX (Done)** – Modular, logic-driven ocean spray using high-fidelity instanced particles and refractive droplets.
- **Layer 7: Simulation (Done)** – Does this FFT ocean use Tessendorf simulation? - Future goal to integrate full spectral wave simulation (Spectral FFT).

### 💡 High-Impact Features Pipeline

| **Category** | **Planned Features** |
| :--- | :--- |
| **Ocean** | Underwater Mode, Buoyancy Integration, Wake Trails, Storm/Tide Sliders |
| **World** | Foliage Scatter (Trees/Grass), Road/Path Gen, Dynamic Weather, NPC Pathing |
| **Editor** | Material Node Editor, Terrain Paint-Brushes, Save-able Camera Bookmarks |
| **Atmosphere** | Skybox/Day-Night Cycle (✓), Volumetric Clouds (✓), Rayleigh Scattering (✓), Planet Rim from space (✓) |
| **Weather** | Rain (✓), Snow (✓), Storm (✓), Fog (✓), Sandstorm (✓), Procedural seed-driven selection (✓), Spherical + Flat-Infinite modes (✓), Per-biome bias (planned), Lightning + thunder timing (planned), Soaked-surface wetness buffer (planned) |
| **Particles** | Curl/Vortex/Attractor forces (✓), Velocity-aligned stretch (✓), Streaming LOD (✓), Size/Alpha curves (✓), GPU-backed pool (planned), Collision with landscape/voxel SDF (planned), Decal spawning on hit (planned) |
| **Future Ultra-Dynamic-Sky targets** | Aerial-perspective LUT (in-scattering for distant terrain), Cirrus layer above cumulus, Lightning-lit clouds, Rainbows from sun+rain coincidence, Moon phases driven by `date_day_index`, Seasonal color grading, Auroras at high latitudes in spherical mode |
| **Security** | Sandboxed Execution, Malicious Project Detection, Secure Plugin API |

---

## 🏗 Getting Started

1. **Environment Setup**: Install dependencies via `pip install PyQt6 numpy pyopengl`.
2. **Launch**: Run `python py_editor/main.py`.
3. **Logic Testing**: Run `python tests/test_logic_run.py` to verify the stability of the logic interpreter.
4. **Tutorial**: Add a `Landscape` object from the Outliner, set its type to `Procedural`, and adjust the **Detail Level** in the Properties Panel.

*NodeCanvas is currently an experimental platform for procedural content generation research.*
