"""Processing steps used by the GUI (Qt-free; functions run in worker processes).

Everything here calls the library functions in ``pylineament.pylineament`` so that GUI output is the
same as ``dem_to_shp`` output for the same parameters.
"""

import glob
import multiprocessing
import os
import shutil
import tempfile
import time
import traceback
import uuid
import warnings

import numpy as np
import pandas as pd
import rasterio
from rasterio.errors import NotGeoreferencedWarning
from rasterio.windows import Window

from pylineament.pylineament import (
    read_raster, raster_resize, extract_lineament_points, convert_points_to_line,
    reduce_lines, image_splitting, dem_to_line, merge_lines_csv_to_shp,
)

LINE_COLUMNS = ['quad', 'group', 'min_x', 'max_x', 'min_y', 'max_y', 'L', 'deg', 'length', 'crs']

warnings.filterwarnings('ignore', category=NotGeoreferencedWarning)


class Cancelled(Exception):
    pass


def _is_empty_concat(exc):
    # reduce_lines raises this when every fitted line is axis-parallel or degenerate
    return isinstance(exc, ValueError) and 'No objects to concatenate' in str(exc)


# --------------------------------------------------------------------------- tiles

def write_tile(src, tile, path):
    """Write one tile exactly as image_splitting does (flipped rows, bottom-up transform)."""
    with rasterio.open(src) as ds:
        left, bottom, right, top = list(ds.bounds)
        if (left == 0.0) and (top == 0.0):
            bottom = -bottom
        resX = (right - left) / ds.width
        resY = (top - bottom) / ds.height
        l = left + tile.c0 * resX
        b = top - tile.r1 * resY
        transform = (rasterio.Affine.translation(l - resX / 2, b - resY / 2)
                     * rasterio.Affine.scale(resX, resY))
        Z = ds.read(1, window=Window.from_slices((tile.r0, tile.r1), (tile.c0, tile.c1)))
        Z = Z.astype('float')[::-1]
        with rasterio.open(path, 'w', driver='GTiff', height=Z.shape[0], width=Z.shape[1],
                           count=1, dtype=Z.dtype, crs=ds.crs, transform=transform) as out:
            out.write(Z, 1)
    return path


def pixel_to_map(x, y, extent, shape):
    """Same mapping as reduce_lines: tile pixel (x=col, y=row) -> map coordinates."""
    left, right, top, bot = extent
    xm = (np.asarray(x, float) / shape[1]) * (right - left) + left
    ym = -(np.asarray(y, float) / shape[0]) * (bot - top) + bot
    return xm, ym


# ------------------------------------------------------------------------- preview

def preview_tile(src, tile, params, workdir):
    """Run the dem_to_line steps on one tile and keep the intermediates for display.

    ``params`` is a dict from Params.to_dict(). Returns a picklable dict.
    """
    t0 = time.perf_counter()
    path = os.path.join(workdir, f'preview_{uuid.uuid4().hex}.tiff')
    write_tile(src, tile, path)
    try:
        _, dem, extent, crs = read_raster(path)
    finally:
        os.remove(path)

    dem = raster_resize(dem, factor=params['downscale'])
    container, _, _ = extract_lineament_points(dem, eps=params['eps'], thresh=params['thresh'],
                                               z_multip=params['z_multip'])
    raw = convert_points_to_line(container, line_fit=params['line_fit'])

    final = pd.DataFrame(columns=LINE_COLUMNS[:-1])
    note = ''
    if len(raw) > 0:
        try:
            _, _, final = reduce_lines(raw.copy(), extent=extent, dem_shape=dem.shape,
                                       min_dist=params['min_dist'], seg_len=params['seg_len'])
        except ValueError as e:
            if not _is_empty_concat(e):
                raise
            note = 'all fitted lines were degenerate; dem_to_line would fail on this tile'

    points = []
    n_clusters = 0
    for df in container:
        if len(df) == 0:
            continue
        xm, ym = pixel_to_map(df['X'].values, df['Y'].values, extent, dem.shape)
        points.append((int(df['quad'].iloc[0]), np.c_[xm, ym]))
        n_clusters += df['GROUP'].nunique()

    raw_xy = np.zeros((0, 4))
    if len(raw):
        x0, y0 = pixel_to_map(raw['min_x'].values, raw['min_y'].values, extent, dem.shape)
        x1, y1 = pixel_to_map(raw['max_x'].values, raw['max_y'].values, extent, dem.shape)
        raw_xy = np.c_[x0, y0, x1, y1]

    # tile image in map coordinates: row i is at y = bot + i*dy (dy > 0 means row 0 is south)
    left, right, top, bot = extent
    xs, ys = pixel_to_map([0, dem.shape[1]], [0, dem.shape[0]], extent, dem.shape)
    return {
        'tile': tile,
        'dem': dem.astype('float32'),
        'rect': (float(min(xs)), float(min(ys)), float(abs(xs[1] - xs[0])), float(abs(ys[1] - ys[0]))),
        'row0_south': bool(ys[1] > ys[0]),
        'points': points,
        'raw_lines': raw_xy,
        'final_lines': final[['min_x', 'max_x', 'min_y', 'max_y', 'length', 'deg']].reset_index(drop=True),
        'n_points': int(sum(len(p) for _, p in points)),
        'n_clusters': int(n_clusters),
        'n_raw': int(len(raw)),
        'n_final': int(len(final)),
        'seconds': time.perf_counter() - t0,
        'note': note,
    }


# --------------------------------------------------------------------- full run

def run_tile(args):
    """Worker: dem_to_line on one tile file, as dem_to_shp does. Never raises."""
    tile_path, tmpdir, params = args
    t0 = time.perf_counter()
    name = os.path.basename(tile_path)
    try:
        _, _, lines, *_ = dem_to_line(tile_path, tmpdir, params['eps'], params['thresh'],
                                      params['min_dist'], params['seg_len'], params['z_multip'],
                                      params['downscale'], True, params['line_fit'])
        return dict(tile=name, ok=True, n_lines=len(lines), seconds=time.perf_counter() - t0, error='')
    except Exception as e:
        if _is_empty_concat(e):
            return dict(tile=name, ok=True, n_lines=0, seconds=time.perf_counter() - t0,
                        error='degenerate lines only (skipped)')
        return dict(tile=name, ok=False, n_lines=0, seconds=time.perf_counter() - t0,
                    error=traceback.format_exc())


def merge_results(tmpdir):
    """merge_lines_csv_to_shp without writing; empty DataFrame if no tile produced lines."""
    if not glob.glob(f'{tmpdir}/*.csv'):
        return pd.DataFrame(columns=LINE_COLUMNS)
    return merge_lines_csv_to_shp(tempfolder=tmpdir, shppath=None, save_to_file=False)


def write_shapefile(lines, path, crs_wkt=None):
    """Same schema and geometry as merge_lines_csv_to_shp, but with the raster's real CRS."""
    import fiona
    schema = {'geometry': 'LineString',
              'properties': [('quad', 'int'), ('group', 'int'), ('deg', 'float'),
                             ('min_x', 'float'), ('max_x', 'float'), ('min_y', 'float'),
                             ('max_y', 'float'), ('length', 'float')]}
    kw = {'crs_wkt': crs_wkt} if crs_wkt else {}
    with fiona.open(path, mode='w', driver='ESRI Shapefile', schema=schema, **kw) as shp:
        for r in lines.itertuples(index=False):
            shp.write({
                'geometry': {'type': 'LineString',
                             'coordinates': [(r.min_x, r.min_y), (r.max_x, r.max_y)]},
                'properties': {'quad': int(r.quad), 'group': int(r.group), 'deg': float(r.deg),
                               'min_x': float(r.min_x), 'max_x': float(r.max_x),
                               'min_y': float(r.min_y), 'max_y': float(r.max_y),
                               'length': float(r.length)}})


def run_extraction(src, params, out_path=None, crs_wkt=None, keep_dir=None,
                   progress=None, cancel=None, log=None):
    """Full extraction with progress and cancellation.

    params   : dict from Params.to_dict()
    out_path : shapefile path, or None to skip writing
    keep_dir : folder for intermediate files to keep; None uses a private temp dir that is removed
    progress : callable(done, total, tile_result)
    cancel   : threading.Event-like object with is_set()
    log      : callable(str)
    Returns dict(lines=DataFrame, tiles=[tile results], seconds=float, workdir=str|None).
    """
    log = log or (lambda s: None)
    t0 = time.perf_counter()
    if keep_dir:
        if os.path.isdir(keep_dir) and os.listdir(keep_dir):
            raise FileExistsError(f'intermediate folder is not empty: {keep_dir}')
        os.makedirs(keep_dir, exist_ok=True)
        workdir = keep_dir
    else:
        workdir = tempfile.mkdtemp(prefix='pylineament_')
    pool = None
    try:
        log(f'Splitting into tiles of {params["split_size"]} px ...')
        image_splitting(im_path=os.path.normpath(src), split_size=params['split_size'],
                        tempfolder=workdir)
        tiles = sorted(glob.glob(os.path.join(workdir, '*.tiff')))
        total = len(tiles)
        log(f'{total} tiles; extracting with {params["n_jobs"]} worker process(es) ...')
        if progress:
            progress(0, total, None)

        results = []
        n_jobs = max(1, min(params['n_jobs'], total))
        pool = multiprocessing.get_context('spawn').Pool(n_jobs)
        it = pool.imap_unordered(run_tile, [(os.path.normpath(t), os.path.normpath(workdir), params)
                                            for t in tiles])
        while len(results) < total:
            if cancel is not None and cancel.is_set():
                raise Cancelled()
            try:
                r = it.next(timeout=0.2)
            except multiprocessing.TimeoutError:
                continue
            results.append(r)
            if progress:
                progress(len(results), total, r)
        pool.close()
        pool.join()
        pool = None

        if cancel is not None and cancel.is_set():
            raise Cancelled()
        log('Merging tile results ...')
        lines = merge_results(workdir)
        if out_path:
            write_shapefile(lines, out_path, crs_wkt)
            log(f'Wrote {len(lines)} lineaments to {out_path}')
        return dict(lines=lines, tiles=results, seconds=time.perf_counter() - t0,
                    workdir=workdir if keep_dir else None)
    finally:
        if pool is not None:
            pool.terminate()
            pool.join()
        if not keep_dir:
            shutil.rmtree(workdir, ignore_errors=True)


# ------------------------------------------------------------------- statistics

def line_stats(lines, geographic):
    """Per-line azimuth (0-180, clockwise from north) and length in km (None if unknown units)."""
    if len(lines) == 0:
        return np.zeros(0), np.zeros(0)
    x0, x1 = lines['min_x'].values.astype(float), lines['max_x'].values.astype(float)
    y0, y1 = lines['min_y'].values.astype(float), lines['max_y'].values.astype(float)
    dx, dy = x1 - x0, y1 - y0
    if geographic:
        lat = np.radians((y0 + y1) / 2)
        dx = dx * np.cos(lat)
        # haversine
        p0, p1 = np.radians(y0), np.radians(y1)
        dl = np.radians(x1 - x0)
        a = np.sin((p1 - p0) / 2) ** 2 + np.cos(p0) * np.cos(p1) * np.sin(dl / 2) ** 2
        length = 2 * 6371.0088 * np.arcsin(np.sqrt(a))
    else:
        length = np.hypot(dx, dy)
    az = np.degrees(np.arctan2(dx, dy)) % 180.0
    return az, length
