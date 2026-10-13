"""Raster metadata, display image and tile grid (Qt-free).

Conventions follow pylineament.image_splitting so that what is drawn matches what is extracted:
pixel (col, row) has map coordinates (x0 + col*resx, y_top - row*resy). Non-georeferenced images
(left == 0 and top == 0) get y = -row, as image_splitting does with ``bottom = -bottom``.
"""

import os
import warnings
from dataclasses import dataclass

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.errors import NotGeoreferencedWarning
from rasterio.windows import Window

MAX_DISPLAY = 4000  # long side of the decimated overview image


def split_ranges(n, size):
    """Same split as pylineament.read_raster / image_splitting (keeps their last-tile rule)."""
    if n <= size:
        return np.array([[0, n]])
    s = np.c_[np.arange(0, n - size, size), np.arange(0, n - size, size) + size]
    return np.vstack([s, [s[-1, -1], n]])


@dataclass
class Tile:
    n: int
    c0: int  # first column (library L)
    c1: int  # end column   (library R)
    r0: int  # first row    (library B)
    r1: int  # end row      (library T)

    @property
    def shape(self):
        return self.r1 - self.r0, self.c1 - self.c0


class RasterInfo:
    def __init__(self, path):
        self.path = os.path.abspath(path)
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', NotGeoreferencedWarning)
            with rasterio.open(self.path) as ds:
                self.height, self.width = ds.height, ds.width
                self.count = ds.count
                self.dtype = ds.dtypes[0]
                self.nodata = ds.nodata
                self.crs = ds.crs
                self.bounds = tuple(ds.bounds)
                step = max(1, int(np.ceil(max(self.height, self.width) / MAX_DISPLAY)))
                self.display_step = step
                out_shape = (int(np.ceil(self.height / step)), int(np.ceil(self.width / step)))
                disp = ds.read(1, out_shape=out_shape,
                               resampling=Resampling.nearest).astype('float32')

        if self.nodata is not None:
            disp[disp == self.nodata] = np.nan
        self.display = disp  # row 0 = first raster row (north for georeferenced data)

        left, bottom, right, top = self.bounds
        self.georeferenced = not (left == 0.0 and top == 0.0)
        if not self.georeferenced:
            bottom = -bottom
        self.x0, self.y_top = left, top
        self.resx = (right - left) / self.width
        self.resy = (top - bottom) / self.height

    # ----------------------------------------------------------------- metadata
    @property
    def name(self):
        return os.path.basename(self.path)

    @property
    def is_geographic(self):
        return bool(self.crs is not None and self.crs.is_geographic)

    @property
    def crs_wkt(self):
        return self.crs.to_wkt() if self.crs is not None else None

    def crs_label(self):
        if self.crs is None:
            return 'none (pixel coordinates)'
        epsg = self.crs.to_epsg()
        return f'EPSG:{epsg}' if epsg else self.crs.to_string()[:60]

    def units(self):
        if self.crs is None:
            return 'px'
        if self.crs.is_geographic:
            return 'deg'
        u = self.crs.linear_units or ''
        return 'm' if u.lower() in ('metre', 'meter', 'm') else u

    def summary(self):
        return {
            'File': self.name,
            'Size': f'{self.width} x {self.height} px, {self.count} band(s), {self.dtype}',
            'CRS': self.crs_label(),
            'Pixel size': f'{self.resx:.6g} x {self.resy:.6g} {self.units()}',
            'Extent': f'x {self.x0:.6g} .. {self.x0 + self.width * self.resx:.6g}, '
                      f'y {self.y_top - self.height * self.resy:.6g} .. {self.y_top:.6g}',
            'NoData': str(self.nodata),
        }

    # ------------------------------------------------------------- coordinates
    def map_rect(self):
        """(x, y, w, h) of the whole raster with y = bottom edge."""
        h = self.height * self.resy
        return self.x0, self.y_top - h, self.width * self.resx, h

    def tile_rect(self, t):
        x = self.x0 + t.c0 * self.resx
        y = self.y_top - t.r1 * self.resy
        return x, y, (t.c1 - t.c0) * self.resx, (t.r1 - t.r0) * self.resy

    def pixel_at(self, x, y):
        """(col, row) of map coordinate, or None if outside."""
        col = int(np.floor((x - self.x0) / self.resx))
        row = int(np.floor((self.y_top - y) / self.resy))
        if 0 <= col < self.width and 0 <= row < self.height:
            return col, row
        return None

    def value_at(self, x, y):
        p = self.pixel_at(x, y)
        if p is None:
            return None
        v = self.display[p[1] // self.display_step, p[0] // self.display_step]
        return None if np.isnan(v) else float(v)

    # -------------------------------------------------------------------- tiles
    def tiles(self, size):
        v = split_ranges(self.height, size)  # rows
        h = split_ranges(self.width, size)   # cols
        # same ordering as the library: column blocks outer, row blocks inner
        return [Tile(n, int(c[0]), int(c[1]), int(r[0]), int(r[1]))
                for n, (c, r) in enumerate((c, r) for c in h for r in v)]

    def tile_at(self, tiles, x, y):
        p = self.pixel_at(x, y)
        if p is None:
            return None
        col, row = p
        for t in tiles:
            if t.c0 <= col < t.c1 and t.r0 <= row < t.r1:
                return t
        return None

    def read_tile(self, t):
        with rasterio.open(self.path) as ds:
            return ds.read(1, window=Window.from_slices((t.r0, t.r1), (t.c0, t.c1)))
