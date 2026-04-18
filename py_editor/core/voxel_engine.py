"""
voxel_engine.py

Smooth Voxel Terrain using Surface Nets with interpolated vertex placement.
Vertices are moved to the actual zero-crossing (not the cell centroid) which
eliminates the Minecraft blocky appearance at any resolution.
"""
import numpy as np
import time

from py_editor.core.voxel_engine_flat import generate_flat_density
from py_editor.core.voxel_engine_round import generate_round_density


class VoxelEngine:
    """Generates smooth organic meshes from voxel density grids."""

    _PERLIN_GRADS = np.array([
        [1, 1, 0], [-1, 1, 0], [1, -1, 0], [-1, -1, 0],
        [1, 0, 1], [-1, 0, 1], [1, 0, -1], [-1, 0, -1],
        [0, 1, 1], [0, -1, 1], [0, 1, -1], [0, -1, -1],
    ], dtype=np.float32)

    # ------------------------------------------------------------------ #
    #  Noise generators                                                    #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _perlin_3d(x, y, z, seed=123):
        """Vectorized 3D Perlin noise — output roughly in [-1, 1]."""
        x = np.asarray(x, dtype=np.float32)
        y = np.asarray(y, dtype=np.float32)
        z = np.asarray(z, dtype=np.float32)
        x, y, z = np.broadcast_arrays(x, y, z)

        def fade(t):
            return t * t * t * (t * (t * 6.0 - 15.0) + 10.0)

        X = np.floor(x).astype(np.int64)
        Y = np.floor(y).astype(np.int64)
        Z = np.floor(z).astype(np.int64)
        xf, yf, zf = x - X, y - Y, z - Z

        g = VoxelEngine._PERLIN_GRADS

        def grad(ix, iy, iz):
            h = (ix * 127 + iy * 311 + iz * 743 + seed) & 0xFFFF
            return g[h % 12]

        g000 = grad(X,     Y,     Z    )
        g100 = grad(X + 1, Y,     Z    )
        g010 = grad(X,     Y + 1, Z    )
        g110 = grad(X + 1, Y + 1, Z    )
        g001 = grad(X,     Y,     Z + 1)
        g101 = grad(X + 1, Y,     Z + 1)
        g011 = grad(X,     Y + 1, Z + 1)
        g111 = grad(X + 1, Y + 1, Z + 1)

        def dot(g_, dx, dy, dz):
            return g_[..., 0] * dx + g_[..., 1] * dy + g_[..., 2] * dz

        n000 = dot(g000, xf,     yf,     zf    )
        n100 = dot(g100, xf - 1, yf,     zf    )
        n010 = dot(g010, xf,     yf - 1, zf    )
        n110 = dot(g110, xf - 1, yf - 1, zf    )
        n001 = dot(g001, xf,     yf,     zf - 1)
        n101 = dot(g101, xf - 1, yf,     zf - 1)
        n011 = dot(g011, xf,     yf - 1, zf - 1)
        n111 = dot(g111, xf - 1, yf - 1, zf - 1)

        u, v, w = fade(xf), fade(yf), fade(zf)
        x1 = n000 + u * (n100 - n000)
        x2 = n010 + u * (n110 - n010)
        y1 = x1   + v * (x2   - x1  )
        x3 = n001 + u * (n101 - n001)
        x4 = n011 + u * (n111 - n011)
        y2 = x3   + v * (x4   - x3  )
        return (y1 + w * (y2 - y1)).astype(np.float32)

    @staticmethod
    def _fbm(x, y, z, seed=123, octaves=5):
        """Fractional Brownian Motion — layered detail noise."""
        out = np.zeros_like(x, dtype=np.float32)
        amp, freq = 1.0, 1.0
        norm = 0.0
        for i in range(octaves):
            out  += VoxelEngine._perlin_3d(x * freq, y * freq, z * freq,
                                           seed=seed + i * 7) * amp
            norm += amp
            amp  *= 0.5
            freq *= 2.1
        return (out / norm).astype(np.float32)

    @staticmethod
    def _ridged(x, y, z, seed=123):
        """Ridged noise — sharpened for high-contrast mountain peaks."""
        v = (1.0 - np.abs(VoxelEngine._perlin_3d(x, y, z, seed=seed)))
        # Squaring the result creates much sharper peaks and broader valleys,
        # which reads as 'mountains' rather than 'sand dunes'.
        return (v * v * 2.0 - 1.2).astype(np.float32)

    @staticmethod
    def _voronoi(x, y, z, seed=123):
        """Cellular/Voronoi — returns normalised distance to nearest lattice point."""
        x = np.asarray(x, dtype=np.float32)
        y = np.asarray(y, dtype=np.float32)
        z = np.asarray(z, dtype=np.float32)
        x, y, z = np.broadcast_arrays(x, y, z)
        Xi = np.floor(x).astype(np.int64)
        Yi = np.floor(y).astype(np.int64)
        Zi = np.floor(z).astype(np.int64)
        mn = np.full(x.shape, 1e9, dtype=np.float32)
        for di in range(-1, 2):
            for dj in range(-1, 2):
                for dk in range(-1, 2):
                    nx_, ny_, nz_ = Xi + di, Yi + dj, Zi + dk
                    h = (nx_ * 127 + ny_ * 311 + nz_ * 743 + seed) & 0xFFFF
                    rx = ((h * 3501) & 0xFFFF) / 65535.0
                    ry = ((h * 7489) & 0xFFFF) / 65535.0
                    rz = ((h * 5003) & 0xFFFF) / 65535.0
                    d = np.sqrt((x - (nx_ + rx))**2 +
                                (y - (ny_ + ry))**2 +
                                (z - (nz_ + rz))**2)
                    mn = np.minimum(mn, d)
        return ((mn - 0.5) * 2.0).astype(np.float32)

    @staticmethod
    def _caves(x, y, z, seed=123):
        """Two perpendicular noise fields multiplied — produces tunnel channels."""
        a = VoxelEngine._perlin_3d(x,        y,        z,        seed=seed)
        b = VoxelEngine._perlin_3d(x * 0.7,  y * 1.3,  z * 0.9,  seed=seed + 31)
        return (-(1.0 - np.abs(a)) * (1.0 - np.abs(b))).astype(np.float32)

    @staticmethod
    def _layer_noise(NX, NY, NZ, layer, base_seed):
        """Dispatch the correct noise function for a layer."""
        ntype = layer.get('noise_type', 'perlin')
        freq  = float(layer.get('freq', 1.0))
        amp   = float(layer.get('amp',  0.1))
        seed  = int(layer.get('seed', base_seed))
        lx, ly, lz = NX * freq, NY * freq, NZ * freq
        if   ntype == 'fbm':    val = VoxelEngine._fbm(lx, ly, lz, seed=seed)
        elif ntype == 'ridged': val = VoxelEngine._ridged(lx, ly, lz, seed=seed)
        elif ntype == 'voronoi':val = VoxelEngine._voronoi(lx, ly, lz, seed=seed)
        elif ntype == 'caves':  val = VoxelEngine._caves(lx, ly, lz, seed=seed)
        else:                   val = VoxelEngine._perlin_3d(lx, ly, lz, seed=seed)
        return (val * amp).astype(np.float32)

    @staticmethod
    def _cellular_caves(x, y, z, seed=123):
        """Ridged-noise cave field: values near 0 mark cave interior.

        Returns a positive 'carve strength' in [0, 1], where 1 = solid cave
        interior to be carved out, 0 = untouched rock. Unlike the old voronoi
        intersection — which produced stalagmite-like floating spikes — this
        builds Minecraft-style tunnel networks by intersecting two independent
        ridged-noise fields and taking the portion that's close to the ridge.
        """
        # Ridged noise: 1 - |perlin|. Values near 1 follow thin curvy ridges.
        r1 = 1.0 - np.abs(VoxelEngine._perlin_3d(x,        y,        z,        seed=seed))
        r2 = 1.0 - np.abs(VoxelEngine._perlin_3d(x * 1.3,  y * 1.7,  z * 1.1,  seed=seed + 41))
        r3 = 1.0 - np.abs(VoxelEngine._perlin_3d(x * 0.5,  y * 0.5,  z * 0.5,  seed=seed + 77))
        # Intersection (min) gives thin 1-D curves where all three agree →
        # tube-shaped tunnel networks. Large scale (r3) gates which regions
        # have caves so the world isn't Swiss-cheesed uniformly.
        base = np.minimum(r1, r2)
        gate = np.clip((r3 - 0.55) * 4.0, 0.0, 1.0)
        tunnels = np.clip((base - 0.78) * 12.0, 0.0, 1.0) * gate
        return tunnels.astype(np.float32)

    # ------------------------------------------------------------------ #
    #  Smoothing                                                           #
    # ------------------------------------------------------------------ #

    @staticmethod
    def smooth_grid(grid, iterations=1):
        """
        Gaussian-like 3D grid smoothing — much more effective than simple
        Laplacian because it properly blends density across cell boundaries.
        Each iteration applies a separable 1-2-1 kernel in all three axes.
        """
        if iterations <= 0:
            return grid
        # Normalised 1-2-1 kernel
        k = np.array([0.25, 0.50, 0.25], dtype=np.float32)
        g = grid.copy().astype(np.float32)
        for _ in range(iterations):
            # Separable convolution along each axis using padded roll
            for axis in range(3):
                p = np.pad(g, [(1,1) if i == axis else (0,0) for i in range(3)],
                           mode='edge')
                if axis == 0:
                    g = p[:-2] * k[0] + p[1:-1] * k[1] + p[2:] * k[2]
                elif axis == 1:
                    g = p[:, :-2] * k[0] + p[:, 1:-1] * k[1] + p[:, 2:] * k[2]
                else:
                    g = p[:, :, :-2] * k[0] + p[:, :, 1:-1] * k[1] + p[:, :, 2:] * k[2]
        return g.astype(np.float32)

    # ------------------------------------------------------------------ #
    #  Density grid                                                        #
    # ------------------------------------------------------------------ #

    @staticmethod
    def generate_density_grid(resolution=64, seed=123, mode="Round", radius=0.5,
                              layers=None, features=None, center=(0, 0, 0),
                              min_p=None, max_p=None, gen_params=None):
        """Generate a float32 density grid. Positive = inside surface."""
        res = int(resolution)
        if min_p is None:
            min_p = np.array([-1, -1, -1], dtype=np.float32)
        if max_p is None:
            max_p = np.array([ 1,  1,  1], dtype=np.float32)

        x = np.linspace(min_p[0], max_p[0], res, dtype=np.float32)
        y = np.linspace(min_p[1], max_p[1], res, dtype=np.float32)
        z = np.linspace(min_p[2], max_p[2], res, dtype=np.float32)
        X, Y, Z = np.meshgrid(x, y, z, indexing='ij')

        LX = (X - center[0]).astype(np.float32)
        LY = (Y - center[1]).astype(np.float32)
        LZ = (Z - center[2]).astype(np.float32)

        # Normalised coords: [-1, 1] within the radius, scale-invariant
        inv_r = np.float32(1.0 / (float(radius) + 1e-6))
        NX, NY, NZ = LX * inv_r, LY * inv_r, LZ * inv_r

        # Dispatch to the per-mode generator. Both take the same prepared
        # coords and the shared noise helpers on VoxelEngine.
        gen = generate_round_density if mode == "Round" else generate_flat_density
        return gen(
            NX, NY, NZ, LX, LY, LZ,
            resolution=res, seed=seed, radius=float(radius),
            layers=layers, features=features, center=center,
            perlin_3d=VoxelEngine._perlin_3d,
            layer_noise=VoxelEngine._layer_noise,
            cellular_caves=VoxelEngine._cellular_caves,
            gen_params=gen_params or {},
        )

    # ------------------------------------------------------------------ #
    #  Surface Nets — interpolated vertex placement                        #
    # ------------------------------------------------------------------ #

    @staticmethod
    def surface_nets(grid, threshold=0.0, pad=True):
        """
        Surface Nets extraction with gradient-based vertex interpolation.

        Vertices are placed at the actual density zero-crossing (via a single
        Newton step from the cell centroid) rather than the centroid itself.
        This eliminates the blocky / Minecraft staircase appearance and gives
        organic terrain at any resolution.
        """
        # 1. Pad with 'outside' so surface closes at grid boundaries (for standalone objects)
        if pad:
            padded = np.pad(grid, 1, mode='constant', constant_values=-1.0).astype(np.float32)
        else:
            padded = grid.astype(np.float32)

        nx, ny, nz = padded.shape
        signs = (padded > threshold).astype(np.int8)

        # 2. Find active cells
        s = [
            signs[:-1, :-1, :-1], signs[1:, :-1, :-1],
            signs[:-1,  1:, :-1], signs[1:,  1:, :-1],
            signs[:-1, :-1,  1:], signs[1:, :-1,  1:],
            signs[:-1,  1:,  1:], signs[1:,  1:,  1:],
        ]
        active_mask = np.zeros_like(s[0], dtype=bool)
        for i in range(1, 8):
            active_mask |= (s[0] != s[i])

        active_coords = np.argwhere(active_mask)
        if len(active_coords) == 0:
            return (np.array([], dtype=np.float32),
                    np.array([], dtype=np.uint32),
                    np.array([], dtype=np.float32))

        N = len(active_coords)
        ci = active_coords[:, 0].astype(np.int32)
        cj = active_coords[:, 1].astype(np.int32)
        ck = active_coords[:, 2].astype(np.int32)

        # 3. Density at all 8 corners
        d000 = padded[ci,     cj,     ck    ]
        d100 = padded[ci + 1, cj,     ck    ]
        d010 = padded[ci,     cj + 1, ck    ]
        d110 = padded[ci + 1, cj + 1, ck    ]
        d001 = padded[ci,     cj,     ck + 1]
        d101 = padded[ci + 1, cj,     ck + 1]
        d011 = padded[ci,     cj + 1, ck + 1]
        d111 = padded[ci + 1, cj + 1, ck + 1]

        # 4. Gradient at cell centroid (from corner differences, 6-tap)
        # These are proportional to the true gradient — magnitude doesn't matter
        # for the Newton step direction, only the normalised direction.
        gx = ((d100 + d110 + d101 + d111) - (d000 + d010 + d001 + d011)) * 0.25
        gy = ((d010 + d110 + d011 + d111) - (d000 + d100 + d001 + d101)) * 0.25
        gz = ((d001 + d101 + d011 + d111) - (d000 + d100 + d010 + d110)) * 0.25
        d_avg = (d000 + d100 + d010 + d110 + d001 + d101 + d011 + d111) * 0.125
        g_sq  = gx * gx + gy * gy + gz * gz + np.float32(1e-8)

        # 5. Newton step: move from cell centroid toward the zero crossing.
        #    new = centroid - d_avg * (gradient / |gradient|^2)
        #    Clamp the offset to ±0.5 cells to stay inside the cube.
        step   = d_avg / g_sq          # scalar per cell
        ox     = np.clip(-step * gx, -0.49, 0.49).astype(np.float32)
        oy     = np.clip(-step * gy, -0.49, 0.49).astype(np.float32)
        oz     = np.clip(-step * gz, -0.49, 0.49).astype(np.float32)

        # 6. Convert to normalised space [-0.5, 0.5]
        #    Normalise over the logical grid range.
        n_cells = float(nx - 2) if pad else float(nx - 1)
        c_off   = 1.0 if pad else 0.0
        
        verts = np.empty((N, 3), dtype=np.float32)
        verts[:, 0] = (ci - c_off + 0.5 + ox) / n_cells - 0.5
        verts[:, 1] = (cj - c_off + 0.5 + oy) / n_cells - 0.5
        verts[:, 2] = (ck - c_off + 0.5 + oz) / n_cells - 0.5
        verts = np.nan_to_num(verts)

        # 7. Index map
        cell_to_idx = np.full((nx - 1, ny - 1, nz - 1), -1, dtype=np.int32)
        cell_to_idx[active_mask] = np.arange(N)

        # 8. Normals — gradient direction at each vertex
        #    Normalise gx/gy/gz (already computed above).
        g_len = np.sqrt(g_sq).reshape(-1, 1)
        v_norms = np.stack([-gx / g_len[:, 0],
                             -gy / g_len[:, 0],
                             -gz / g_len[:, 0]], axis=1).astype(np.float32)
        v_norms = np.nan_to_num(v_norms)

        # 9. Quads (two triangles each) via edge-crossing connectivity
        indices = []

        def _faces(cross_mask, axis):
            ei, ej, ek = np.where(cross_mask)
            if len(ei) == 0:
                return
            if axis == 0:
                j_g, k_g = ej + 1, ek + 1
                v1 = cell_to_idx[ei, j_g,     k_g    ]
                v2 = cell_to_idx[ei, j_g - 1, k_g    ]
                v3 = cell_to_idx[ei, j_g,     k_g - 1]
                v4 = cell_to_idx[ei, j_g - 1, k_g - 1]
                flip = signs[ei, j_g, k_g] == 1
            elif axis == 1:
                i_g, k_g = ei + 1, ek + 1
                v1 = cell_to_idx[i_g,     ej, k_g    ]
                v2 = cell_to_idx[i_g - 1, ej, k_g    ]
                v3 = cell_to_idx[i_g,     ej, k_g - 1]
                v4 = cell_to_idx[i_g - 1, ej, k_g - 1]
                flip = signs[i_g, ej, k_g] == 0
            else:
                i_g, j_g = ei + 1, ej + 1
                v1 = cell_to_idx[i_g,     j_g,     ek]
                v2 = cell_to_idx[i_g - 1, j_g,     ek]
                v3 = cell_to_idx[i_g,     j_g - 1, ek]
                v4 = cell_to_idx[i_g - 1, j_g - 1, ek]
                flip = signs[i_g, j_g, ek] == 1

            valid = (v1 >= 0) & (v2 >= 0) & (v3 >= 0) & (v4 >= 0)
            if not np.any(valid):
                return
            v1, v2, v3, v4 = v1[valid], v2[valid], v3[valid], v4[valid]
            flip = flip[valid]
            q = np.empty((len(v1), 6), dtype=np.uint32)
            q[ flip] = np.column_stack([v1[ flip], v2[ flip], v3[ flip],
                                        v2[ flip], v4[ flip], v3[ flip]])
            q[~flip] = np.column_stack([v1[~flip], v3[~flip], v2[~flip],
                                        v2[~flip], v3[~flip], v4[~flip]])
            indices.extend(q.flatten())

        _faces(signs[:-1, 1:-1, 1:-1] != signs[1:,  1:-1, 1:-1], 0)
        _faces(signs[1:-1, :-1, 1:-1] != signs[1:-1, 1:,  1:-1], 1)
        _faces(signs[1:-1, 1:-1, :-1] != signs[1:-1, 1:-1, 1: ], 2)

        return (verts.astype(np.float32),
                np.array(indices, dtype=np.uint32),
                v_norms.astype(np.float32))

    @staticmethod
    def blocky_mesh(grid, threshold=0.0):
        """Generate a blocky cube-based mesh from a density grid.

        Vectorised with numpy — only faces on the boundary between solid and
        empty cells are emitted.  Produces verts in normalised [-0.5, 0.5]^3
        to match `surface_nets` output convention.

        For a 47³ chunk the old Python-loop version did ~625K work items in
        pure Python; this version runs in a handful of numpy array ops and is
        typically 50-100× faster.
        """
        if grid.size == 0:
            return (np.array([], dtype=np.float32),
                    np.array([], dtype=np.uint32),
                    np.array([], dtype=np.float32))

        nx, ny, nz = grid.shape
        solid = grid > threshold
        if not solid.any():
            return (np.array([], dtype=np.float32),
                    np.array([], dtype=np.uint32),
                    np.array([], dtype=np.float32))

        # Pad with False on all sides so "out of bounds" counts as empty ⇒
        # boundary faces on the grid edges are emitted correctly.
        padded = np.pad(solid, 1, mode='constant', constant_values=False)

        # Face masks: one axis at a time.  For each axis, a face exists where
        # a solid cell is adjacent to an empty cell.  We produce two masks
        # per axis (positive-normal and negative-normal faces).
        # Indexing: padded[1:-1, 1:-1, 1:-1] == original solid grid.
        s = padded[1:-1, 1:-1, 1:-1]

        # -X face: solid cell with empty neighbour in -X direction
        mask_nx = s & ~padded[:-2,  1:-1, 1:-1]
        mask_px = s & ~padded[2:,   1:-1, 1:-1]
        mask_ny = s & ~padded[1:-1, :-2,  1:-1]
        mask_py = s & ~padded[1:-1, 2:,   1:-1]
        mask_nz = s & ~padded[1:-1, 1:-1, :-2]
        mask_pz = s & ~padded[1:-1, 1:-1, 2:]

        half_x = np.float32(0.5 / nx)
        half_y = np.float32(0.5 / ny)
        half_z = np.float32(0.5 / nz)
        inv_nx = np.float32(1.0 / nx)
        inv_ny = np.float32(1.0 / ny)
        inv_nz = np.float32(1.0 / nz)

        all_verts   = []
        all_norms   = []
        all_indices = []
        vert_offset = 0

        def _emit_face(mask, corner_offsets, normal):
            """Emit one quad (two triangles) for every cell where mask is True.
            corner_offsets: 4 (dx, dy, dz) tuples in units of ±half_{x,y,z}.
            """
            nonlocal vert_offset
            ii, jj, kk = np.where(mask)
            n = ii.size
            if n == 0:
                return
            # Cell centres in normalised [-0.5, 0.5] space
            cx = (ii.astype(np.float32) + 0.5) * inv_nx - 0.5
            cy = (jj.astype(np.float32) + 0.5) * inv_ny - 0.5
            cz = (kk.astype(np.float32) + 0.5) * inv_nz - 0.5

            quad_verts = np.empty((n, 4, 3), dtype=np.float32)
            for ci, (dx, dy, dz) in enumerate(corner_offsets):
                quad_verts[:, ci, 0] = cx + dx * half_x
                quad_verts[:, ci, 1] = cy + dy * half_y
                quad_verts[:, ci, 2] = cz + dz * half_z
            all_verts.append(quad_verts.reshape(-1, 3))
            all_norms.append(np.tile(np.asarray(normal, dtype=np.float32),
                                     (n * 4, 1)))

            # Two triangles per quad: (0,1,2) and (0,2,3), using per-quad offsets
            base = vert_offset + np.arange(n, dtype=np.uint32) * 4
            tris = np.stack([
                base,     base + 1, base + 2,
                base,     base + 2, base + 3,
            ], axis=1).reshape(-1)
            all_indices.append(tris)
            vert_offset += n * 4

        # Corner offsets (x,y,z) in units of (half_x, half_y, half_z).
        # Match the CCW winding of the original blocky_mesh faces.
        _emit_face(mask_nx, [(-1,-1,-1), (-1, 1,-1), (-1, 1, 1), (-1,-1, 1)],
                   (-1.0, 0.0, 0.0))
        _emit_face(mask_px, [( 1,-1,-1), ( 1,-1, 1), ( 1, 1, 1), ( 1, 1,-1)],
                   ( 1.0, 0.0, 0.0))
        _emit_face(mask_ny, [(-1,-1,-1), (-1,-1, 1), ( 1,-1, 1), ( 1,-1,-1)],
                   ( 0.0,-1.0, 0.0))
        _emit_face(mask_py, [(-1, 1,-1), ( 1, 1,-1), ( 1, 1, 1), (-1, 1, 1)],
                   ( 0.0, 1.0, 0.0))
        _emit_face(mask_nz, [(-1,-1,-1), ( 1,-1,-1), ( 1, 1,-1), (-1, 1,-1)],
                   ( 0.0, 0.0,-1.0))
        _emit_face(mask_pz, [(-1,-1, 1), (-1, 1, 1), ( 1, 1, 1), ( 1,-1, 1)],
                   ( 0.0, 0.0, 1.0))

        if not all_verts:
            return (np.array([], dtype=np.float32),
                    np.array([], dtype=np.uint32),
                    np.array([], dtype=np.float32))

        verts_np = np.concatenate(all_verts, axis=0).astype(np.float32)
        norms_np = np.concatenate(all_norms, axis=0).astype(np.float32)
        idx_np   = np.concatenate(all_indices).astype(np.uint32)
        return verts_np, idx_np, norms_np


def main():
    start = time.time()
    g = VoxelEngine.generate_density_grid(resolution=64)
    g = VoxelEngine.smooth_grid(g, iterations=2)
    v, idx, n = VoxelEngine.surface_nets(g)
    print(f"Generated in {time.time()-start:.3f}s  verts={len(v)}  tris={len(idx)//3}")


if __name__ == "__main__":
    main()
