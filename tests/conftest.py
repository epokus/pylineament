import os
import shutil

import numpy as np
import pytest
import rasterio

HERE = os.path.dirname(os.path.abspath(__file__))
EXAMPLE = os.path.join(HERE, '..', 'example')


@pytest.fixture(scope='session')
def dem_path(tmp_path_factory):
    """Local copy of the example DEM (the repo may live on a slow synced drive)."""
    d = tmp_path_factory.mktemp('data')
    p = d / 'e_kal_crop2.tif'
    shutil.copy(os.path.join(EXAMPLE, 'e_kal_crop2.tif'), p)
    return str(p)


@pytest.fixture(scope='session')
def small_dem_path(tmp_path_factory, dem_path):
    """A 300 x 420 crop of the example DEM: fast enough for end-to-end tests."""
    d = tmp_path_factory.mktemp('small')
    p = d / 'small.tif'
    with rasterio.open(dem_path) as ds:
        win = rasterio.windows.Window(300, 200, 420, 300)
        profile = ds.profile | dict(width=420, height=300, transform=ds.window_transform(win))
        with rasterio.open(p, 'w', **profile) as out:
            out.write(ds.read(1, window=win), 1)
    return str(p)


@pytest.fixture(scope='session')
def utm_dem_path(tmp_path_factory, small_dem_path):
    """Same data, labelled with a projected CRS (UTM 50N) to test CRS handling."""
    d = tmp_path_factory.mktemp('utm')
    p = d / 'utm.tif'
    with rasterio.open(small_dem_path) as ds:
        profile = ds.profile | dict(crs='EPSG:32650',
                                    transform=rasterio.Affine(90, 0, 500000, 0, -90, 200000))
        with rasterio.open(p, 'w', **profile) as out:
            out.write(ds.read(1), 1)
    return str(p)


@pytest.fixture(scope='session')
def flat_dem_path(tmp_path_factory):
    d = tmp_path_factory.mktemp('flat')
    p = d / 'flat.tif'
    with rasterio.open(p, 'w', driver='GTiff', width=200, height=150, count=1, dtype='int16',
                       crs='EPSG:4326',
                       transform=rasterio.Affine(0.001, 0, 110, 0, -0.001, 1)) as out:
        out.write(np.full((150, 200), 50, 'int16'), 1)
    return str(p)


def sort_lines(df):
    cols = ['min_x', 'max_x', 'min_y', 'max_y']
    return df[cols].astype(float).sort_values(cols).reset_index(drop=True)
