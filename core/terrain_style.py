"""Continuous DSM lighting for display only; original XYZ and palette are unchanged."""
import numpy as np


class TerrainLighting:
    """Prepare mesh lighting once, then color any number of geographic batches."""

    def __init__(self, mesh):
        self.width, self.height = mesh['width'], mesh['height']
        self.xs, self.ys = np.asarray(mesh['x']), np.asarray(mesh['y'])
        zs = np.asarray([np.nan if z is None else z for z in mesh['elevations']])
        grid_x, grid_y = np.meshgrid(self.xs, self.ys)
        vertices = np.column_stack((grid_x.ravel(), grid_y.ravel(), zs))
        normals = np.zeros_like(vertices)
        ids = np.arange(self.width * self.height).reshape((self.height, self.width))
        if self.width > 1 and self.height > 1:
            a, b = ids[:-1, :-1].ravel(), ids[:-1, 1:].ravel()
            c, d = ids[1:, :-1].ravel(), ids[1:, 1:].ravel()
            faces = np.concatenate((np.column_stack((a, b, c)), np.column_stack((b, d, c))))
            faces = faces[np.isfinite(vertices[faces]).all(axis=(1, 2))]
            vectors = np.cross(vertices[faces[:, 1]] - vertices[faces[:, 0]],
                               vertices[faces[:, 2]] - vertices[faces[:, 0]])
            for corner in range(3):
                np.add.at(normals, faces[:, corner], vectors)
        length = np.linalg.norm(normals, axis=1)
        self.lighting = .68 + .32 * np.abs((normals @ np.array([-.35, -.35, .87])) /
                                         np.where(length == 0, 1, length))

    def colors(self, positions, base_color=None):
        """Return uint8 RGB; supplied categorical colors retain their palette."""
        positions = np.asarray(positions, dtype=np.float64).reshape((-1, 3))
        if not len(positions):
            return np.empty((0, 3), dtype=np.uint8)
        width, height, xs, ys, lighting = self.width, self.height, self.xs, self.ys, self.lighting
        if width < 2 or height < 2:
            shade = np.full(len(positions), .68 + .32 * .87)
        else:
            fx = np.clip((positions[:, 0] - xs[0]) / (xs[1] - xs[0]), 0, width - 1)
            fy = np.clip((positions[:, 1] - ys[0]) / (ys[1] - ys[0]), 0, height - 1)
            ix, iy = np.minimum(fx.astype(int), width - 2), np.minimum(fy.astype(int), height - 2)
            tx, ty = fx - ix, fy - iy
            a, b, c, d = iy * width + ix, iy * width + ix + 1, (iy + 1) * width + ix, (iy + 1) * width + ix + 1
            shade = np.where(tx + ty <= 1,
                             (1 - tx - ty) * lighting[a] + tx * lighting[b] + ty * lighting[c],
                             (1 - ty) * lighting[b] + (tx + ty - 1) * lighting[d] + (1 - tx) * lighting[c])
        z = positions[:, 2]
        palette = np.column_stack((.59 + z / 10000, .63 + z / 12000, np.full(len(z), .48))) if base_color is None else np.broadcast_to(np.asarray(base_color), (len(z), 3))
        return np.clip(np.floor(palette * shade[:, None] * 255 + .5), 0, 255).astype(np.uint8)


def terrain_vertex_colors(mesh, positions, base_color=None):
    """Return uint8 RGB for local-XY/absolute-Z vertices, including clipped vertices.

    Normals are area-weighted over valid faces of the ORIGINAL mesh, before any
    commune clipping. Barycentric interpolation therefore gives identical colors
    to shared boundary vertices. No face is made across an unknown elevation.
    """
    return TerrainLighting(mesh).colors(positions, base_color)
