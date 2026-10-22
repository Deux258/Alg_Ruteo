"""Superficie EGM2008, corredores completos y observación geométrica."""
import math
import numpy as np
import rasterio
from rasterio.features import geometry_mask
from rasterio.windows import from_bounds, Window
from shapely.geometry import Point, LineString, box, mapping
from shapely.ops import unary_union

from core.aerial_data import FWD, INV


class Surface:
    def __init__(self, path, bounds=None):
        self.src = rasterio.open(path)
        if self.src.crs is None or self.src.crs.to_epsg() != 4326:
            self.src.close()
            raise ValueError('DSM requiere EPSG:4326 y datum EGM2008 declarado en manifiesto')
        if self.src.units[0] not in (None, 'm', 'metre', 'meter'):
            self.src.close()
            raise ValueError('Unidades verticales DSM incompatibles')
        window=None
        if bounds is not None:
            from shapely.ops import transform
            wgs=transform(INV,box(*bounds).buffer(500))
            window=from_bounds(*wgs.bounds,self.src.transform).round_offsets().round_lengths()
            window=window.intersection(Window(0,0,self.src.width,self.src.height))
        self.transform=self.src.window_transform(window) if window is not None else self.src.transform
        self.grid = self.src.read(1, masked=True, window=window).astype('float32')
        self.height_px,self.width_px=self.grid.shape
        self.grid = self.grid * self.src.scales[0] + self.src.offsets[0]

    def close(self):
        self.src.close()

    def heights(self, points):
        if not points:
            return []
        lon, lat = INV(np.array([p[0] for p in points]), np.array([p[1] for p in points]))
        rows, cols = rasterio.transform.rowcol(self.transform, lon, lat)
        result = []
        for r, c in zip(rows, cols):
            v = self.grid[r, c] if 0 <= r < self.height_px and 0 <= c < self.width_px else np.ma.masked
            result.append(None if np.ma.is_masked(v) or not math.isfinite(float(v)) else float(v))
        return result

    def height(self, x, y):
        return self.heights([(x, y)])[0]

    def pixels(self, geometry):
        """Todas las celdas tocadas; incluye NoData y cobertura fuera del ráster."""
        from shapely.ops import transform
        wgs = transform(INV, geometry)
        win = from_bounds(*wgs.bounds, self.transform).round_offsets().round_lengths()
        win = Window(win.col_off-1, win.row_off-1, win.width+3, win.height+3)
        complete = win.col_off >= 0 and win.row_off >= 0 and win.col_off+win.width <= self.width_px and win.row_off+win.height <= self.height_px
        try:
            win = win.intersection(Window(0, 0, self.width_px, self.height_px))
        except rasterio.errors.WindowError:
            return np.array([],dtype=float),False
        mask = geometry_mask([mapping(wgs)], out_shape=(int(win.height), int(win.width)),
                             transform=rasterio.windows.transform(win,self.transform), invert=True, all_touched=True)
        grid = self.grid[int(win.row_off):int(win.row_off+win.height), int(win.col_off):int(win.col_off+win.width)]
        samples = grid[mask]
        valid = samples.compressed()
        known = complete and len(valid) == len(samples) and len(valid) > 0 and bool(np.isfinite(valid).all())
        return valid, bool(known)

    def corridor(self, a, b, profile):
        line = LineString([a[:2], b[:2]])
        geometry = line.buffer(profile['corridor_radius_m']) if line.length else Point(a[:2]).buffer(profile['corridor_radius_m'])
        values, known = self.pixels(geometry)
        n = max(1, math.ceil(line.length / profile['sample_step_m']))
        points = [(a[0]+(b[0]-a[0])*i/n, a[1]+(b[1]-a[1])*i/n) for i in range(n+1)]
        heights = self.heights(points)
        known = known and all(h is not None for h in heights)
        # La cota mínima del vuelo frente al máximo de TODA la franja es conservadora.
        clearance = min(a[2], b[2])-float(max(values)) if known else None
        return dict(surface_known=known, clearance_m=clearance,
                    profile_samples=[[i/n,h] for i,h in enumerate(heights)])

    def visible(self, observer, target, profile, obstacles):
        line = LineString([observer[:2], target[:2]])
        if obstacles is not None and not obstacles.is_empty and obstacles.intersects(line):
            return False, True
        n = max(1, math.ceil(line.length/profile['sample_step_m']))
        # Verificar celdas tocadas por cada intervalo; el destino pertenece a la superficie.
        for i in range(n):
            f0, f1 = i/n, (i+1)/n
            p0 = (observer[0]+(target[0]-observer[0])*f0, observer[1]+(target[1]-observer[1])*f0)
            p1 = (observer[0]+(target[0]-observer[0])*f1, observer[1]+(target[1]-observer[1])*f1)
            h = self.heights([p0, p1])
            if any(v is None for v in h):
                return False, False
            # El último punto toca la superficie; no se considera una oclusión por sí mismo.
            if i < n-1 and h[1] > observer[2]+(target[2]-observer[2])*f1+0.25:
                return False, True
        return True, True


def observation(surface, observer, sector, profile, obstacles=None):
    """Integración por celdas recortadas: área, visibilidad y GSD local."""
    h = surface.height(*observer[:2])
    if h is None:
        return dict(known=False, admissible=False, reason='observation_surface_unknown', coverage=0, features=[])
    altitude = observer[2]-h
    width, height = [2*altitude*math.tan(math.radians(fov)/2) for fov in profile['camera_fov_deg']]
    footprint = box(observer[0]-width/2, observer[1]-height/2, observer[0]+width/2, observer[1]+height/2)
    step = profile['observation_cell_m']
    visible, hidden, unknown = [], [], []
    max_gsd = 0.0
    west, south, east, north = sector.bounds
    for x in np.arange(math.floor(west/step)*step, east, step):
        for y in np.arange(math.floor(south/step)*step, north, step):
            tile = sector.intersection(box(x, y, x+step, y+step))
            if tile.is_empty or tile.area == 0:
                continue
            point = tile.representative_point()
            ground = surface.height(point.x, point.y)
            if ground is None:
                unknown.append(tile); continue
            dz = observer[2]-ground
            local_width, local_height = [2*dz*math.tan(math.radians(fov)/2) for fov in profile['camera_fov_deg']]
            in_view = dz > 0 and abs(point.x-observer[0]) <= local_width/2 and abs(point.y-observer[1]) <= local_height/2
            seen, known = surface.visible(observer, (point.x, point.y, ground), profile, obstacles) if in_view else (False, True)
            gsd = max(local_width/profile['camera_pixels'][0], local_height/profile['camera_pixels'][1]) if in_view else 0
            if not known: unknown.append(tile)
            elif seen and gsd <= profile['maximum_gsd_m']:
                visible.append(tile); max_gsd = max(max_gsd, gsd)
            else: hidden.append(tile)
    visible_area = sum(t.area for t in visible)
    coverage = visible_area/sector.area if sector.area else 0
    known = not unknown
    return dict(known=known, admissible=known and coverage >= profile['minimum_coverage'],
                reason=None if known and coverage >= profile['minimum_coverage'] else 'observation_surface_unknown' if not known else 'insufficient_observation',
                coverage=coverage, visible_area_m2=visible_area, sector_area_m2=sector.area,
                unknown_area_m2=sum(t.area for t in unknown), maximum_gsd_m=max_gsd,
                footprint=mapping(footprint), visible=mapping(unary_union(visible)), hidden=mapping(unary_union(hidden)),
                unknown=mapping(unary_union(unknown)))
