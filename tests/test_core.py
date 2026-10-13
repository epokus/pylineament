import glob
import inspect
import os
import threading

import numpy as np
import pandas as pd
import pytest
import rasterio

import pylineament as ln
from pylineament.gui import pipeline
from pylineament.gui.params import Params
from pylineament.gui.raster import RasterInfo

from conftest import sort_lines


# ---------------------------------------------------------------- params

def test_param_defaults_match_library():
    sig = inspect.signature(ln.dem_to_shp).parameters
    p = Params()
    for name in ['eps', 'thresh', 'min_dist', 'seg_len', 'split_size', 'z_multip',
                 'downscale', 'line_fit']:
        assert getattr(p, name) == sig[name].default, name


def test_param_json_roundtrip(tmp_path):
    p = Params(eps=2.5, thresh=12, line_fit='pca', n_jobs=2)
    f = tmp_path / 'p.json'
    p.save(f)
    assert Params.load(f) == p


@pytest.mark.parametrize('bad', [dict(eps=0), dict(thresh=1.5), dict(line_fit='x'),
                                 dict(split_size=10)])
def test_param_validation(bad):
    with pytest.raises(ValueError):
        Params.from_dict(Params().to_dict() | bad)


def test_param_to_python_is_valid():
    code = Params(line_fit='pca').to_python(r'C:\data\dem.tif', 'out.shp')
    compile(code, '<params>', 'exec')
    assert "line_fit='pca'" in code


# ---------------------------------------------------------------- raster

@pytest.mark.parametrize('size', [100, 333, 500, 2000])
def test_tile_grid_matches_library(dem_path, size):
    regions, *_ = ln.read_raster(dem_path, split_size=size)
    tiles = RasterInfo(dem_path).tiles(size)
    lib = regions[['L', 'R', 'B', 'T']].values.astype(int)
    ours = np.array([[t.c0, t.c1, t.r0, t.r1] for t in tiles])
    assert np.array_equal(lib, ours)


def test_raster_info(dem_path):
    r = RasterInfo(dem_path)
    assert (r.height, r.width) == (855, 1054)
    assert r.is_geographic and r.crs_label() == 'EPSG:4326'
    x, y, w, h = r.map_rect()
    assert np.allclose([x, y + h], [r.bounds[0], r.bounds[3]])
    t = r.tiles(500)[3]
    cx, cy = r.tile_rect(t)[0] + 1e-6, r.tile_rect(t)[1] + 1e-6
    assert r.tile_at(r.tiles(500), cx, cy).n == 3


# ---------------------------------------------------------------- tiles / preview

def test_write_tile_matches_image_splitting(dem_path, tmp_path):
    lib_dir = tmp_path / 'lib'
    lib_dir.mkdir()
    ln.image_splitting(dem_path, 500, str(lib_dir))
    r = RasterInfo(dem_path)
    for t in r.tiles(500):
        ours = pipeline.write_tile(dem_path, t, str(tmp_path / f'ours_{t.n}.tiff'))
        with rasterio.open(lib_dir / f'{t.n:04d}.tiff') as a, rasterio.open(ours) as b:
            assert a.transform == b.transform
            assert a.crs == b.crs
            assert np.array_equal(a.read(1), b.read(1))


def test_preview_equals_dem_to_line(dem_path, tmp_path):
    r = RasterInfo(dem_path)
    t = r.tiles(500)[0]
    p = Params()
    res = pipeline.preview_tile(dem_path, t, p.to_dict(), str(tmp_path))

    tile_file = pipeline.write_tile(dem_path, t, str(tmp_path / 'tile.tiff'))
    _, _, lines, *_ = ln.dem_to_line(tile_file, **p.tile_kwargs())
    assert res['n_final'] == len(lines) > 0
    assert np.allclose(sort_lines(res['final_lines']), sort_lines(lines))

    x, y, w, h = r.tile_rect(t)
    pts = np.vstack([xy for _, xy in res['points']])
    pad = 2 * r.resx
    assert (pts[:, 0] >= x - pad).all() and (pts[:, 0] <= x + w + pad).all()
    assert (pts[:, 1] >= y - pad).all() and (pts[:, 1] <= y + h + pad).all()


# ---------------------------------------------------------------- full run

@pytest.mark.parametrize('line_fit', ['ols', 'pca'])
def test_run_matches_dem_to_shp(dem_path, tmp_path, monkeypatch, line_fit):
    p = Params(line_fit=line_fit, n_jobs=4)
    res = pipeline.run_extraction(dem_path, p.to_dict())

    monkeypatch.chdir(tmp_path)
    lib = ln.dem_to_shp(dem_path, tempfolder=str(tmp_path / 'temp'), save_to_file=False,
                        n_jobs=4, split_size=p.split_size,
                        **p.tile_kwargs())
    assert len(res['lines']) == len(lib) > 0
    assert np.allclose(sort_lines(res['lines']), sort_lines(lib))
    assert all(t['ok'] for t in res['tiles'])


def test_shapefile_uses_raster_crs(utm_dem_path, tmp_path):
    import fiona
    r = RasterInfo(utm_dem_path)
    out = str(tmp_path / 'utm_lines.shp')
    res = pipeline.run_extraction(utm_dem_path, Params(n_jobs=2).to_dict(), out, r.crs_wkt)
    with fiona.open(out) as shp:
        assert len(shp) == len(res['lines']) > 0
        assert rasterio.crs.CRS.from_wkt(shp.crs_wkt).to_epsg() == 32650


def test_flat_dem_gives_empty_result(flat_dem_path, tmp_path):
    out = str(tmp_path / 'flat.shp')
    res = pipeline.run_extraction(flat_dem_path, Params(n_jobs=1).to_dict(), out)
    assert len(res['lines']) == 0
    assert os.path.exists(out)


def test_cancel_cleans_up(dem_path, tmp_path, monkeypatch):
    import tempfile
    monkeypatch.setattr(tempfile, 'tempdir', str(tmp_path))
    ev = threading.Event()

    def progress(done, total, r):
        if done >= 1:
            ev.set()

    with pytest.raises(pipeline.Cancelled):
        pipeline.run_extraction(dem_path, Params(split_size=200, n_jobs=2).to_dict(),
                                progress=progress, cancel=ev)
    assert glob.glob(str(tmp_path / 'pylineament_*')) == []


def test_keep_intermediate(small_dem_path, tmp_path):
    keep = str(tmp_path / 'inter')
    res = pipeline.run_extraction(small_dem_path, Params(n_jobs=1).to_dict(), keep_dir=keep)
    assert res['workdir'] == keep and glob.glob(keep + '/*.tiff')
    with pytest.raises(FileExistsError):
        pipeline.run_extraction(small_dem_path, Params(n_jobs=1).to_dict(), keep_dir=keep)


def test_failing_tile_is_reported(small_dem_path, monkeypatch):
    res = pipeline.run_extraction(small_dem_path, Params(n_jobs=1, split_size=200).to_dict()
                                  | {'thresh': 'not-a-number'})
    failed = [t for t in res['tiles'] if not t['ok']]
    assert failed and 'Traceback' in failed[0]['error']
    assert len(res['tiles']) == 6  # the other tiles still ran


def test_line_stats():
    df = pd.DataFrame({'min_x': [0, 0], 'max_x': [0, 1], 'min_y': [0, 0], 'max_y': [1, 1]})
    az, length = pipeline.line_stats(df, geographic=False)
    assert np.allclose(az, [0, 45]) and np.allclose(length, [1, np.sqrt(2)])
    az, length = pipeline.line_stats(df, geographic=True)
    assert np.isclose(length[0], 111.2, atol=0.1)
