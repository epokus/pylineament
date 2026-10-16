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
    assert p.tile_kwargs()['azimuths'] == list(sig['azimuths'].default) == [0, 30, 60, 90, 120, 150]


def test_param_json_roundtrip(tmp_path):
    p = Params(eps=2.5, thresh=12, line_fit='tls', n_jobs=2)
    f = tmp_path / 'p.json'
    p.save(f)
    assert Params.load(f) == p


@pytest.mark.parametrize('bad', [dict(eps=0), dict(thresh=1.5), dict(line_fit='x'),
                                 dict(split_size=10)])
def test_param_validation(bad):
    with pytest.raises(ValueError):
        Params.from_dict(Params().to_dict() | bad)


def test_param_to_python_is_valid():
    code = Params(line_fit='tls').to_python(r'C:\data\dem.tif', 'out.shp')
    compile(code, '<params>', 'exec')
    assert "line_fit='tls'" in code


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

@pytest.mark.parametrize('line_fit, azimuths', [('ols', 6), ('tls', 6), ('ols', 12)])
def test_run_matches_dem_to_shp(dem_path, tmp_path, monkeypatch, line_fit, azimuths):
    p = Params(line_fit=line_fit, azimuths=azimuths, n_jobs=4)
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


# ---------------------------------------------------------------- azimuths

def test_six_azimuths_default_and_v101_reproduction(dem_path, tmp_path):
    """6 azimuths (default) vs the 12 of v1.0.1 on the whole example DEM."""
    t6 = pipeline.run_extraction(dem_path, Params(n_jobs=4).to_dict())
    t12 = pipeline.run_extraction(dem_path, Params(azimuths=12, n_jobs=4).to_dict())
    assert set(t6['lines']['quad']) <= set(range(6))
    # v1.0.1 (12 azimuths, OLS, defaults) gave 2495 lines on this DEM
    assert len(t12['lines']) == 2495
    # dropping the duplicate half changes ~0.1 % of the lines
    assert abs(len(t6['lines']) - len(t12['lines'])) <= 0.005 * len(t12['lines'])


def test_azimuth_pairs_give_identical_edges(dem_path):
    """The reason 6 azimuths suffice: at altitude 0, az and az + 180 mirror the hillshade."""
    from skimage.filters import prewitt
    _, dem, _, _ = ln.read_raster(dem_path)
    dem = dem[:300, :300].astype(float)
    for az in range(0, 180, 30):
        a = prewitt(ln.hillshade(dem, az, 0, 1))
        b = prewitt(ln.hillshade(dem, az + 180, 0, 1))
        assert np.allclose(a, b, atol=1e-9)


def test_azimuths_param_validation():
    with pytest.raises(ValueError):
        Params.from_dict(Params().to_dict() | {'azimuths': 8})
    assert Params.from_dict(Params().to_dict() | {'azimuths': '12'}).azimuths == 12
    assert 'azimuths=[0, 30, 60, 90, 120, 150]' in Params().to_python()


# ---------------------------------------------------------------- line fit names

def test_tls_name_and_pca_alias(dem_path):
    _, dem, _, _ = ln.read_raster(dem_path)
    c, _, _ = ln.extract_lineament_points(dem[:300, :300])
    tls = ln.convert_points_to_line(c, line_fit='tls')
    pca = ln.convert_points_to_line(c, line_fit='pca')       # old name, same method
    ols = ln.convert_points_to_line(c, line_fit='ols')
    assert len(tls) > 0 and tls.equals(pca) and not tls.equals(ols)
    with pytest.raises(ValueError):
        ln.convert_points_to_line(c, line_fit='principal')
    # saved GUI parameter files with the old name still load
    assert Params.from_dict(Params().to_dict() | {'line_fit': 'pca'}).line_fit == 'tls'
