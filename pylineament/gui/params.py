"""Extraction parameters: defaults, ranges, validation and serialisation (Qt-free)."""

import json
import os
from dataclasses import dataclass, asdict, fields


def default_n_jobs():
    return max(1, (os.cpu_count() or 2) - 1)


# name -> (label, min, max, step, decimals, tooltip); decimals None means integer
SPECS = {
    'split_size': ('Tile size (px)', 100, 5000, 50, None,
                   'Side length of the square tiles the DEM is split into. Tiles do not overlap, '
                   'so lineaments are cut at tile edges.'),
    'downscale':  ('Resample factor', 0.1, 4.0, 0.1, 4,
                   'Passed to raster_resize(factor=...). 1 = native resolution, '
                   '0.5 = half resolution (about 4x faster), 2 = upsampled.'),
    'z_multip':   ('Z multiplier', 0.001, 1000.0, 0.1, 4,
                   'Vertical exaggeration used for the hillshades. The gradient is computed in '
                   'pixel units, so the effective exaggeration is z_multip x cell size.'),
    'eps':        ('DBSCAN eps (px)', 0.5, 20.0, 0.1, 4,
                   'Neighbour distance used to cluster edge points. On the pixel grid, '
                   '1.0-1.4 connects only direct neighbours.'),
    'thresh':     ('Min cluster size', 3, 5000, 1, None,
                   'Clusters with this many edge points or fewer are discarded. '
                   'Higher values keep only long, continuous features.'),
    'min_dist':   ('Merge distance (px)', 1, 500, 1, None,
                   'Distance used by reduce_lines to merge nearby line segments.'),
    'seg_len':    ('Segment length (px)', 1, 500, 1, None,
                   'Lines are rebuilt from segments of this length; output lengths are '
                   'multiples of it.'),
    'n_jobs':     ('Worker processes', 1, max(1, os.cpu_count() or 1), 1, None,
                   'Number of processes used for the full extraction.'),
}

LINE_FITS = {
    'ols': 'OLS (v1.0.1 behaviour)',
    'pca': 'PCA / total least squares (orientation-unbiased)',
}


@dataclass
class Params:
    split_size: int = 500
    downscale: float = 1.0
    z_multip: float = 1.0
    eps: float = 1.2
    thresh: int = 40
    min_dist: int = 10
    seg_len: int = 10
    line_fit: str = 'ols'
    n_jobs: int = 0  # 0 means default_n_jobs()
    keep_intermediate: bool = False

    def __post_init__(self):
        if not self.n_jobs:
            self.n_jobs = default_n_jobs()

    def validate(self):
        """Raise ValueError if any value is outside its allowed range."""
        for name, (label, lo, hi, _, decimals, _) in SPECS.items():
            v = getattr(self, name)
            if decimals is None and int(v) != v:
                raise ValueError(f'{label} must be an integer, got {v}')
            if not lo <= v <= hi:
                raise ValueError(f'{label} must be between {lo} and {hi}, got {v}')
        if self.line_fit not in LINE_FITS:
            raise ValueError(f'line_fit must be one of {list(LINE_FITS)}, got {self.line_fit!r}')
        return self

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, d):
        names = {f.name for f in fields(cls)}
        unknown = set(d) - names
        if unknown:
            raise ValueError(f'unknown parameters: {sorted(unknown)}')
        p = cls(**d)
        for name, spec in SPECS.items():
            if spec[4] is None:
                setattr(p, name, int(getattr(p, name)))
            else:
                setattr(p, name, float(getattr(p, name)))
        return p.validate()

    def save(self, path):
        with open(path, 'w', encoding='utf-8') as f:
            json.dump({'pylineament_params': 1, **self.to_dict()}, f, indent=2)

    @classmethod
    def load(cls, path):
        with open(path, encoding='utf-8') as f:
            d = json.load(f)
        d.pop('pylineament_params', None)
        return cls.from_dict(d)

    def tile_kwargs(self):
        """Keyword arguments shared by dem_to_line / dem_to_shp."""
        return dict(eps=self.eps, thresh=self.thresh, min_dist=self.min_dist,
                    seg_len=self.seg_len, z_multip=self.z_multip,
                    downscale=self.downscale, line_fit=self.line_fit)

    def to_python(self, im_path='dem.tif', shp_name=None):
        """Equivalent notebook call, for reproducibility."""
        args = [repr(im_path).replace('\\\\', '/')]
        if shp_name:
            args.append(f'shp_name={shp_name!r}'.replace('\\\\', '/'))
        args.append(f'split_size={self.split_size}')
        for k, v in self.tile_kwargs().items():
            args.append(f'{k}={v!r}')
        args.append(f'n_jobs={self.n_jobs}')
        body = ',\n                     '.join(args)
        return f'import pylineament as ln\nlines = ln.dem_to_shp({body})\n'
