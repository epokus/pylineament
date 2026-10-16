"""Offscreen GUI smoke tests (pytest-qt). Screenshots go to $PYLIN_SHOTS if set."""

import os

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('QT_QPA_FONTDIR', os.path.join(os.environ.get('WINDIR', 'C:/Windows'), 'Fonts'))

from PyQt5.QtCore import QSettings  # noqa: E402
from PyQt5.QtWidgets import QFileDialog, QMessageBox  # noqa: E402

from pylineament.gui.main_window import MainWindow  # noqa: E402

SHOTS = os.environ.get('PYLIN_SHOTS')


def shot(win, name):
    if SHOTS:
        os.makedirs(SHOTS, exist_ok=True)
        win.grab().save(os.path.join(SHOTS, f'{name}.png'))


@pytest.fixture
def win(qtbot, tmp_path):
    settings = QSettings(str(tmp_path / 'settings.ini'), QSettings.IniFormat)
    w = MainWindow(settings=settings)
    w.resize(1500, 950)
    w.show()
    yield w
    w.runner.cancel()
    assert w.runner.wait(30), 'extraction thread did not stop'
    w.close()
    w.deleteLater()


def wait_preview(qtbot, win, timeout=120_000):
    with qtbot.waitSignal(win.preview_runner.finished, timeout=timeout) as blocker:
        pass
    return blocker.args[1]


def test_open_preview_run(qtbot, win, dem_path, tmp_path, monkeypatch):
    shot(win, '00_empty')
    win.open_raster(dem_path)
    with qtbot.waitSignal(win.preview_runner.finished, timeout=180_000) as blocker:
        win.request_preview()
    res = blocker.args[1]
    assert win.raster is not None and len(win.tiles) == 6
    assert res['tile'].n == win.tile.n and res['n_final'] > 0
    win.tabs.setCurrentWidget(win.map)
    shot(win, '01_overview')
    win.tabs.setCurrentWidget(win.preview)
    win.preview.show_raw.setChecked(True)
    shot(win, '02_preview')

    # changing the tile size updates the grid and re-previews
    win.params_panel._editors['split_size'].setValue(300)
    assert len(win.tiles) == len(win.raster.tiles(300)) == 12

    # full run with the save dialog answered automatically
    out = str(tmp_path / 'out' / 'lines.shp')
    os.makedirs(os.path.dirname(out))
    monkeypatch.setattr(QFileDialog, 'getSaveFileName', lambda *a, **k: (out, ''))
    with qtbot.waitSignal(win.runner.finished, timeout=600_000):
        win.run_extraction()
        assert win.runner.running and not win.act_run.isEnabled()
    assert os.path.exists(out) and os.path.exists(out.replace('.shp', '_params.json'))
    assert win.result is not None and len(win.result['lines']) > 0
    assert win.act_run.isEnabled()
    shot(win, '03_results')
    win.tabs.setCurrentWidget(win.map)
    shot(win, '04_overview_lines')


def test_cancelled_save_dialog_does_nothing(qtbot, win, small_dem_path, monkeypatch):
    win.open_raster(small_dem_path)
    monkeypatch.setattr(QFileDialog, 'getSaveFileName', lambda *a, **k: ('', ''))
    win.run_extraction()
    assert not win.runner.running


def test_cancel_run(qtbot, win, dem_path, tmp_path, monkeypatch):
    win.open_raster(dem_path)
    win.params_panel._editors['split_size'].setValue(150)
    out = str(tmp_path / 'c.shp')
    monkeypatch.setattr(QFileDialog, 'getSaveFileName', lambda *a, **k: (out, ''))
    with qtbot.waitSignal(win.runner.cancelled, timeout=120_000):
        win.run_extraction()
        qtbot.waitSignal(win.runner.progress, timeout=60_000).wait()
        win.cancel_run()
    assert not os.path.exists(out)
    assert win.act_run.isEnabled()


def test_bad_file_shows_error(qtbot, win, tmp_path, monkeypatch):
    bad = tmp_path / 'bad.tif'
    bad.write_text('not a raster')
    shown = []
    monkeypatch.setattr(QMessageBox, 'critical', lambda *a, **k: shown.append(a))
    win.open_raster(str(bad))
    assert shown and win.raster is None


def test_non_georeferenced_image(qtbot, win):
    jpeg = os.path.join(os.path.dirname(__file__), '..', 'example', 'sedstrat.jpeg')
    win.open_raster(jpeg)
    with qtbot.waitSignal(win.preview_runner.finished, timeout=180_000) as blocker:
        win.request_preview()
    assert not win.raster.georeferenced
    x, y, w, h = win.raster.tile_rect(win.tile)
    pts = [xy for _, xy in blocker.args[1]['points']]
    if pts:
        import numpy as np
        pts = np.vstack(pts)
        assert (pts[:, 1] <= y + h + 2).all() and (pts[:, 1] >= y - 2).all()
    win.tabs.setCurrentWidget(win.preview)
    shot(win, '05_jpeg_preview')


# ------------------------------------------------------------------ feedback round 2

@pytest.fixture(scope='module')
def preview_result(tmp_path_factory, small_dem_path):
    from pylineament.gui import pipeline
    from pylineament.gui.params import Params
    from pylineament.gui.raster import RasterInfo
    r = RasterInfo(small_dem_path)
    return pipeline.preview_tile(small_dem_path, r.tiles(500)[0], Params().to_dict(),
                                 str(tmp_path_factory.mktemp('prev')))


def loaded(win, path, result):
    """Window with a raster and a preview result, without waiting for the worker."""
    win.preview.auto.setChecked(False)
    win.open_raster(path)
    win._preview_done(0, result)
    return win


def test_layer_checkboxes_are_instant_and_reliable(qtbot, win, small_dem_path, preview_result):
    import time
    loaded(win, small_dem_path, preview_result)
    pv = win.preview
    pv.only_az.setChecked(False)
    assert preview_result['n_final'] > 0
    for _ in range(3):
        for box, items in ((pv.show_points, pv.scatter), (pv.show_raw, [pv.raw]),
                           (pv.show_final, [pv.final])):
            for state in (False, True):
                t = time.perf_counter()
                box.setChecked(state)
                assert time.perf_counter() - t < 0.05
                assert all(it.isVisible() == state for it in items)
    # 'this azimuth only' shows exactly one azimuth layer
    pv.only_az.setChecked(True)
    pv.azimuth.setCurrentIndex(3)
    assert [s.isVisible() for s in pv.scatter] == [i == 3 for i in range(12)]


def test_tile_selector_is_dropdown(qtbot, win, dem_path, preview_result):
    from PyQt5.QtWidgets import QComboBox
    loaded(win, dem_path, preview_result)
    assert isinstance(win.preview.tile, QComboBox)
    assert win.preview.tile.count() == len(win.tiles) == 6
    win.preview.tile.setCurrentIndex(4)
    assert win.tile.n == 4 and win.preview.tile.currentData() == 4


def test_preview_lines_on_overview(qtbot, win, small_dem_path, preview_result):
    loaded(win, small_dem_path, preview_result)
    m = win.map
    assert not m.preview_lines.path().isEmpty() and m.preview_lines.isVisible()
    m.show_preview.setChecked(False)
    assert not m.preview_lines.isVisible()
    m.show_preview.setChecked(True)
    assert m.preview_lines.isVisible()


def test_no_lines_warning(qtbot, win, small_dem_path, preview_result):
    import pandas as pd
    loaded(win, small_dem_path, preview_result)
    assert win.preview.warning.isHidden()
    empty = dict(preview_result, n_final=0, n_raw=0, raw_lines=preview_result['raw_lines'][:0],
                 final_lines=pd.DataFrame(columns=preview_result['final_lines'].columns))
    win._preview_done(1, empty)
    assert not win.preview.warning.isHidden()
    assert 'No line extracted' in win.preview.warning.text()


def test_float_parameters_have_four_decimals(win):
    for name in ('downscale', 'z_multip', 'eps'):
        assert win.params_panel._editors[name].decimals() == 4


def test_style_tab_applies_and_persists(qtbot, win, small_dem_path, preview_result, tmp_path):
    from PyQt5.QtGui import QColor
    loaded(win, small_dem_path, preview_result)
    assert win.side_tabs.tabText(1) == 'Style'
    sp = win.style_panel
    color, width, style = sp._rows['final']
    color.set_color('#00ff00')
    color.changed.emit('#00ff00')
    width.setValue(4.0)
    sp.mode.setCurrentIndex(sp.mode.findData('single'))
    sp.size.setValue(6.0)
    pen = win.preview.final.pen()
    assert pen.color() == QColor('#00ff00') and pen.widthF() == 4.0
    assert win.preview.scatter[0].opts['size'] == 6.0
    color, *_ = sp._rows['preview_overview']
    color.set_color('#123456')
    color.changed.emit('#123456')
    assert win.map.preview_lines.pen().color() == QColor('#123456')
    # remembered by a new window using the same settings
    win.close()
    w2 = MainWindow(settings=win.settings)
    assert w2.style_panel.current_style()['final']['color'] == '#00ff00'
    assert w2.preview.final.pen().widthF() == 4.0
    w2.preview_runner.shutdown()
    w2.close()


def test_merge_style_ignores_bad_values():
    from pylineament.gui.style import default_style, merge_style
    s = merge_style({'final': {'width': 'x', 'style': 'zigzag'}, 'points': {'symbol': '?'},
                     'unknown': 1})
    assert s == default_style()


def test_help_tab(win):
    titles = [win.tabs.tabText(i) for i in range(win.tabs.count())]
    assert 'How to use' in titles
    text = win.help.toPlainText()
    for label in ('Quick start', 'Min cluster size', 'Troubleshooting', 'No line extracted'):
        assert label in text


def test_stale_preview_reminder_manual(qtbot, win, small_dem_path, preview_result):
    loaded(win, small_dem_path, preview_result)          # auto preview is off here
    pv = win.preview
    assert pv.stale_banner.isHidden() and win.map.stale.isHidden()
    win.params_panel._editors['thresh'].setValue(55)
    assert not pv.stale_banner.isHidden() and not pv.stale_button.isHidden()
    assert 'Refresh' in pv.stale_text.text() or 'changed' in pv.stale_text.text()
    assert not win.map.stale.isHidden()
    assert win.tabs.tabText(1).endswith('●')
    # changing back to the previewed value removes the reminder
    win.params_panel._editors['thresh'].setValue(40)
    assert pv.stale_banner.isHidden() and win.tabs.tabText(1) == 'Tile preview'
    # parameters that do not affect the preview do not trigger it
    win.params_panel._editors['n_jobs'].setValue(1)
    win.params_panel.keep.setChecked(True)
    assert pv.stale_banner.isHidden()


def test_stale_preview_reminder_refresh(qtbot, win, small_dem_path, preview_result):
    loaded(win, small_dem_path, preview_result)
    win.params_panel._editors['eps'].setValue(1.5)
    assert not win.preview.stale_banner.isHidden()
    with qtbot.waitSignal(win.preview_runner.finished, timeout=180_000):
        win.preview.stale_button.click()
        # while computing, the banner says so and hides the button
        assert not win.preview.stale_banner.isHidden() and win.preview.stale_button.isHidden()
    assert win.preview.stale_banner.isHidden() and win.map.stale.isHidden()


def test_stale_preview_reminder_auto(qtbot, win, small_dem_path, preview_result):
    loaded(win, small_dem_path, preview_result)
    win.params_panel._editors['seg_len'].setValue(12)
    assert not win.preview.stale_banner.isHidden()
    with qtbot.waitSignal(win.preview_runner.finished, timeout=180_000):
        win.preview.auto.setChecked(True)               # re-enabling refreshes at once
        assert 'Computing' in win.preview.stale_text.text()
    assert win.preview.stale_banner.isHidden()


# ------------------------------------------------------------------ feedback round 3

def test_open_does_not_extract(qtbot, win, dem_path):
    assert not win.preview.auto.isChecked()            # auto preview off by default
    win.open_raster(dem_path)
    qtbot.wait(300)
    assert not win.preview_runner.busy and not win._preview_timer.isActive()
    assert win.preview.result is None
    assert not win.preview.stale_banner.isHidden()
    assert 'No preview yet' in win.preview.stale_text.text()
    # selecting another tile does not extract either
    win.preview.tile.setCurrentIndex(3)
    qtbot.wait(300)
    assert not win.preview_runner.busy


def test_banner_names_other_tile(qtbot, win, dem_path, preview_result):
    loaded(win, dem_path, preview_result)               # preview of tile 0 of the small DEM
    win.preview.tile.setCurrentIndex(4)
    assert 'tile 4' in win.preview.stale_text.text()


def test_topography_range_and_palette(qtbot, win, dem_path):
    import numpy as np
    win.open_raster(dem_path)
    t = win.style_panel.current_style()['topo']
    v = win.raster.display[np.isfinite(win.raster.display)]
    lo, hi = np.percentile(v, [2, 98])
    assert abs(t['vmin'] - lo) < 0.01 and abs(t['vmax'] - hi) < 0.01
    m = win.map
    assert m.background.currentText() == 'Elevation + hillshade' and m.legend.isVisible()
    img1 = m.plot.image.image.copy()
    assert img1.ndim == 3 and img1.shape[2] == 4
    sp = win.style_panel
    sp.palette.setCurrentIndex(sp.palette.findData('viridis'))
    img2 = m.plot.image.image.copy()
    assert not np.array_equal(img1, img2)
    # min/max: full range and manual values
    sp.range_requested.emit('full')
    t = sp.current_style()['topo']
    assert abs(t['vmin'] - v.min()) < 0.01 and abs(t['vmax'] - v.max()) < 0.01
    sp.vmax.setValue(t['vmin'] - 5)                   # invalid range is corrected
    t = sp.current_style()['topo']
    assert t['vmax'] > t['vmin']
    # overlay strength changes the shaded background, not the plain elevation one
    sp.hs_opacity.setValue(0.0)
    shaded0 = m.plot.image.image.copy()
    m.background.setCurrentText('Elevation')
    assert np.array_equal(m.plot.image.image, shaded0)
    m.background.setCurrentText('Hillshade')
    assert m.plot.image.image.ndim == 2 and not m.legend.isVisible()


def test_preview_dem_backgrounds(qtbot, win, small_dem_path, preview_result):
    loaded(win, small_dem_path, preview_result)
    pv = win.preview
    for name in ('Tile DEM', 'Tile DEM + hillshade'):
        pv.background.setCurrentText(name)
        assert pv.plot.image.image.ndim == 3
    before = pv.plot.image.image.copy()
    win.style_panel.reverse.setChecked(True)
    assert not (pv.plot.image.image == before).all()


def test_no_stray_busy_badge(win):
    assert not win.preview.busy.isVisible()


@pytest.mark.parametrize('name, keys, expected', [
    ('eps', '2.5', 2.5), ('z_multip', '3', 3.0), ('downscale', '0.5', 0.5),
    ('thresh', '55', 55), ('n_jobs', '4', 4), ('split_size', '300', 300)])
def test_click_and_type_replaces_value(qtbot, win, name, keys, expected):
    from PyQt5.QtCore import QPoint, Qt
    ed = win.params_panel._editors[name]
    le = ed.lineEdit()
    qtbot.mouseClick(le, Qt.LeftButton, pos=QPoint(le.width() - 3, le.height() // 2))
    qtbot.wait(30)
    qtbot.keyClicks(le, keys)
    qtbot.keyClick(le, Qt.Key_Return)
    assert ed.value() == expected


def test_decimal_point_independent_of_region(win):
    ed = win.params_panel._editors['eps']
    assert ed.locale().decimalPoint() == '.'
    assert ed.textFromValue(1.25) == '1.2500'



def test_azimuths_parameter_in_gui(qtbot, win, small_dem_path, preview_result):
    loaded(win, small_dem_path, preview_result)
    pp = win.params_panel
    assert pp.params().azimuths == 6
    assert win.preview.azimuth.count() == 6 and preview_result['azimuths'] == [0, 30, 60, 90, 120, 150]
    pp.azimuths.setCurrentIndex(pp.azimuths.findData(12))
    assert pp.params().azimuths == 12
    assert not win.preview.stale_banner.isHidden()      # azimuths change the preview
    twelve = dict(preview_result, azimuths=list(range(0, 360, 30)))
    win._preview_done(5, twelve)
    assert win.preview.azimuth.count() == 12
