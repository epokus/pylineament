# PyInstaller spec for the Pylineament GUI (one-file, windowed Windows executable).
#
#   pip install -e .[dev] pyinstaller
#   pyinstaller pylineament.spec
#
# The executable is written to dist/pylineament-<version>.exe. Verify a build with
#   dist/pylineament-<version>.exe --self-test example/e_kal_crop2.tif <out_dir>
# which writes <out_dir>/self_test.json.

import os
import tomllib

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = os.path.abspath(SPECPATH)
with open(os.path.join(ROOT, 'pyproject.toml'), 'rb') as f:
    VERSION = tomllib.load(f)['project']['version']

hiddenimports = (
    ['pylineament', 'pylineament.gui', 'pylineament.gui.pipeline', 'fiona',
     'sklearn.cluster', 'sklearn.neighbors', 'sklearn.linear_model', 'skimage.filters',
     'skimage.transform']
    + collect_submodules('rasterio')
)
datas = (
    [(os.path.join(ROOT, 'pylineament', 'gui', 'icon.ico'), 'pylineament/gui')]
    + collect_data_files('rasterio')
    + collect_data_files('fiona')
    + collect_data_files('pyqtgraph', includes=['colors/maps/*'])
)
excludes = ['tkinter', 'matplotlib', 'IPython', 'jupyter', 'jupyterlab', 'notebook',
            'ipykernel', 'pytest', 'pytestqt', 'PyQt5.QtWebEngineWidgets', 'PyQt5.QtWebEngine',
            'PyQt5.QtWebEngineCore', 'PyQt5.QtQml', 'PyQt5.QtQuick', 'PyQt5.QtMultimedia',
            'PyQt5.QtBluetooth', 'PyQt5.QtSql', 'PyQt5.QtTest', 'powerlaw', 'psutil']

a = Analysis(
    [os.path.join(ROOT, 'pylineament', 'gui', '__main__.py')],
    pathex=[ROOT],
    hiddenimports=hiddenimports,
    datas=datas,
    excludes=excludes,
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name=f'pylineament-{VERSION}',
    icon=os.path.join(ROOT, 'icon.ico'),
    console=False,
    upx=False,
    runtime_tmpdir=None,
)
