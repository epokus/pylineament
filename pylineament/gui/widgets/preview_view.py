import numpy as np
import pyqtgraph as pg
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel,
                             QPushButton, QVBoxLayout, QWidget)
from skimage.filters import prewitt

from ..style import default_style, point_colors
from .common import (MapPlot, colorize, display_hillshade, make_brush, make_pen, palette_lut,
                     path_item, robust_levels, segments_path)

AZIMUTHS = list(range(0, 360, 30))  # largest azimuth set (v1.0.1); one scatter layer each
DEFAULT_AZIMUTHS = [0, 30, 60, 90, 120, 150]
BACKGROUNDS = ['Tile DEM', 'Tile DEM + hillshade', 'Hillshade (algorithm)', 'Prewitt magnitude',
               'Prewitt cut-off (>100)']
NO_LINES = 'No line extracted, try fine-tuning the parameters (see How to use > Troubleshooting).'


class PreviewView(QWidget):
    """Tile preview: what extract_lineament_points / convert_points_to_line / reduce_lines produce.

    Layers are built once per preview result; the checkboxes only change their visibility.
    """

    tile_requested = pyqtSignal(int)
    preview_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.result = None
        self.z_multip = 1.0
        self.style_ = default_style()

        self.tile = QComboBox()
        self.tile.setMinimumContentsLength(28)
        self.tile.setMaxVisibleItems(25)
        self.tile.currentIndexChanged.connect(self._tile_changed)
        self.background = QComboBox()
        self.background.addItems(BACKGROUNDS)
        self.background.setCurrentText('Hillshade (algorithm)')
        self.background.currentIndexChanged.connect(self._draw_background)
        self.azimuth = QComboBox()
        self._azimuths = None
        self._set_azimuths(DEFAULT_AZIMUTHS)
        self.azimuth.setToolTip('Hillshade azimuth (altitude 0°) used by the algorithm. '
                                'Points are coloured by the azimuth that detected them.')
        self.azimuth.currentIndexChanged.connect(self._azimuth_changed)

        self.show_points = QCheckBox('Edge points')
        self.show_points.setChecked(True)
        self.only_az = QCheckBox('this azimuth only')
        self.only_az.setChecked(True)
        self.show_raw = QCheckBox('Fitted lines')
        self.show_final = QCheckBox('Final lines')
        self.show_final.setChecked(True)
        self.auto = QCheckBox('Auto preview')
        self.auto.setChecked(False)
        self.auto.setToolTip('When on, the preview recomputes automatically whenever the tile or a '
                             'parameter changes. Off by default: press Preview (F5) instead.')
        for cb in (self.show_points, self.only_az, self.show_raw, self.show_final):
            cb.toggled.connect(self._update_visibility)
        refresh = QPushButton('Preview (F5)')
        refresh.clicked.connect(self.preview_requested)

        bar = QGridLayout()
        bar.addWidget(QLabel('Tile'), 0, 0)
        bar.addWidget(self.tile, 0, 1, 1, 3)
        bar.addWidget(QLabel('Background'), 0, 4)
        bar.addWidget(self.background, 0, 5)
        bar.addWidget(QLabel('Azimuth'), 0, 6)
        bar.addWidget(self.azimuth, 0, 7)
        bar.addWidget(self.auto, 0, 8)
        bar.addWidget(refresh, 0, 9)
        bar.addWidget(self.show_points, 1, 0, 1, 2)
        bar.addWidget(self.only_az, 1, 2, 1, 2)
        bar.addWidget(self.show_raw, 1, 4)
        bar.addWidget(self.show_final, 1, 5)
        bar.setColumnStretch(10, 1)

        self.legend = QLabel()
        self.legend.setTextFormat(Qt.RichText)
        self.stats = QLabel('No preview yet')
        self.stats.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.warning = QLabel('')
        self.warning.setStyleSheet('color: #d62728; font-weight: bold;')
        self.warning.setVisible(False)

        # reminder shown when the parameters or tile differ from the displayed preview
        self.stale_banner = QFrame()
        self.stale_banner.setObjectName('stale')
        self.stale_banner.setStyleSheet(
            '#stale { background: #fff3cd; border: 1px solid #f0ad4e; border-radius: 3px; }'
            '#stale QLabel { color: #7a5300; font-weight: bold; }')
        self.stale_text = QLabel()
        self.stale_button = QPushButton('Refresh preview (F5)')
        self.stale_button.clicked.connect(self.preview_requested)
        bl = QHBoxLayout(self.stale_banner)
        bl.setContentsMargins(8, 3, 8, 3)
        bl.addWidget(self.stale_text, 1)
        bl.addWidget(self.stale_button)
        self.stale_banner.setVisible(False)

        self.plot = MapPlot()
        self.scatter = [pg.ScatterPlotItem(pen=None, pxMode=True) for _ in AZIMUTHS]
        for s in self.scatter:
            s.setZValue(1)
            self.plot.addItem(s, ignoreBounds=True)
        self.raw = path_item(2)
        self.final = path_item(3)
        self.plot.addItem(self.raw, ignoreBounds=True)
        self.plot.addItem(self.final, ignoreBounds=True)
        self.busy = pg.TextItem('', color='#ffffff', fill=pg.mkBrush(0, 0, 0, 160), anchor=(0, 0))
        self.busy.setZValue(10)
        self.busy.setVisible(False)
        self.plot.addItem(self.busy, ignoreBounds=True)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addLayout(bar)
        lay.addWidget(self.stale_banner)
        lay.addWidget(self.plot)
        bottom = QHBoxLayout()
        bottom.addWidget(self.stats)
        bottom.addStretch()
        bottom.addWidget(self.legend)
        lay.addLayout(bottom)
        lay.addWidget(self.warning)
        self.apply_style(self.style_)

    # ----------------------------------------------------------------- public
    def set_tiles(self, tiles):
        self.tile.blockSignals(True)
        self.tile.clear()
        for t in tiles:
            self.tile.addItem(f'Tile {t.n}   (cols {t.c0}–{t.c1}, rows {t.r0}–{t.r1})', t.n)
        self.tile.blockSignals(False)

    def set_tile(self, n):
        self.tile.blockSignals(True)
        self.tile.setCurrentIndex(self.tile.findData(n))
        self.tile.blockSignals(False)

    def set_banner(self, kind, pending=False, shown=None, current=None):
        """Reminder above the plot.

        kind: None (hidden), 'none' (no preview computed yet), 'tile' (the displayed preview is of
        another tile) or 'stale' (parameters changed since the displayed preview).
        `pending` means a preview is already computing.
        """
        if kind is None:
            self.stale_banner.setVisible(False)
            return
        if pending:
            text = '⟳  Computing the preview for this tile…'
        elif kind == 'none':
            text = ('ℹ  No preview yet. Press Preview (F5) to extract the lineaments of this tile '
                    'with the current parameters.')
        elif kind == 'tile':
            text = (f'ℹ  This preview shows tile {shown}. Press Preview (F5) to extract the '
                    f'lineaments of tile {current}.')
        else:
            text = ('⚠  Parameters or tile changed since this preview was computed. Refresh the '
                    'preview to see their effect.')
        self.stale_text.setText(text)
        self.stale_button.setText('Refresh preview (F5)' if kind == 'stale' else 'Preview tile (F5)')
        self.stale_button.setVisible(not pending)
        self.stale_banner.setVisible(True)

    def set_busy(self, text):
        self.busy.setText(text)
        self.busy.setVisible(bool(text))
        if text:
            r = self.plot.plotItem.vb.viewRect()
            self.busy.setPos(r.left(), r.bottom())

    def clear(self):
        self.result = None
        self.plot.image.clear()
        self._build_layers()
        self.stats.setText('No preview yet')
        self.warning.setVisible(False)

    def _set_azimuths(self, azimuths):
        """Azimuth selector and legend for the azimuth set of the displayed preview."""
        azimuths = list(azimuths)
        if azimuths == self._azimuths:
            return
        self._azimuths = azimuths
        current = self.azimuth.currentData()
        self.azimuth.blockSignals(True)
        self.azimuth.clear()
        for a in azimuths:
            self.azimuth.addItem(f'{a}°', a)
        i = self.azimuth.findData(current)
        self.azimuth.setCurrentIndex(max(i, 0))
        self.azimuth.blockSignals(False)
        if hasattr(self, 'legend'):
            self.apply_style(self.style_)

    def show_result(self, result, z_multip):
        new_tile = self.result is None or self.result['tile'].n != result['tile'].n
        self._set_azimuths(result.get('azimuths', AZIMUTHS))
        self.result = result
        self.z_multip = z_multip
        self._draw_background()
        self._build_layers()
        r = result
        self.stats.setText(
            f"Tile {r['tile'].n}: {r['n_points']} edge points in {r['n_clusters']} clusters → "
            f"{r['n_raw']} fitted lines → <b>{r['n_final']} final lines</b> ({r['seconds']:.1f} s)")
        notes = [n for n in ((NO_LINES if r['n_final'] == 0 else ''), r['note']) if n]
        self.warning.setText('   '.join(notes))
        self.warning.setVisible(bool(notes))
        if new_tile:
            self.plot.autoRange()

    def apply_style(self, style):
        topo_changed = style.get('topo') != self.style_.get('topo')
        self.style_ = style
        if topo_changed and self.background.currentText().startswith('Tile DEM'):
            self._draw_background()
        self.raw.setPen(make_pen(style['fitted']))
        self.final.setPen(make_pen(style['final']))
        p = style['points']
        colors = point_colors(p)
        for s, c in zip(self.scatter, colors):
            s.setSymbol(p['symbol'])
            s.setSize(p['size'])
            s.setBrush(make_brush(c, p['opacity']))
        if p['mode'] == 'single':
            self.legend.setText(f'Edge points: <span style="color:{p["color"]}">&#9632;</span>')
        else:
            self.legend.setText('Azimuth colours: ' + ' '.join(
                f'<span style="color:{c}">&#9632;</span>{a}°'
                for a, c in zip(self._azimuths, colors)))
        self._repaint()

    # ---------------------------------------------------------------- drawing
    def _tile_changed(self, index):
        n = self.tile.itemData(index)
        if n is not None:
            self.tile_requested.emit(n)

    def _azimuth_changed(self):
        self._draw_background()
        self._update_visibility()

    def _draw_background(self):
        if self.result is None:
            return
        dem = self.result['dem']
        south = self.result['row0_south']
        mode = self.background.currentText()
        az = self.azimuth.currentData()
        levels = None
        if mode.startswith('Tile DEM'):
            t = self.style_['topo']
            shade = None
            if mode == 'Tile DEM + hillshade':
                # display hillshade lit from the north-west in map orientation
                north_up = dem[::-1] if south else dem
                shade = display_hillshade(north_up, 315, 45, 1.0)
                shade = shade[::-1] if south else shade
            img = colorize(dem, t['vmin'], t['vmax'], palette_lut(t['palette'], t['reverse']),
                           shade, t['hs_opacity'])
        else:
            img = display_hillshade(dem, az, 0, self.z_multip)
            if mode.startswith('Prewitt'):
                img = prewitt(np.nan_to_num(img))
                if 'cut-off' in mode:
                    img = (img > 100).astype('float32')
                    levels = (0.0, 1.0)
            else:
                levels = robust_levels(img)
        self.plot.set_image(img, self.result['rect'], levels=levels, row0_south=south)
        self._repaint()

    def _build_layers(self):
        """Load the result into the layer items (once per preview)."""
        r = self.result
        p = self.style_['points']
        colors = point_colors(p)
        by_quad = {}
        if r is not None:
            for quad, xy in r['points']:
                by_quad.setdefault(quad % len(self.scatter), []).append(xy)
        for i, s in enumerate(self.scatter):
            xy = np.vstack(by_quad[i]) if i in by_quad else np.zeros((0, 2))
            s.setData(x=xy[:, 0], y=xy[:, 1], symbol=p['symbol'], size=p['size'],
                      brush=make_brush(colors[i], p['opacity']), pen=None)
        if r is not None:
            x0, y0, x1, y1 = r['raw_lines'].T
            self.raw.setPath(segments_path(x0, y0, x1, y1))
            f = r['final_lines']
            self.final.setPath(segments_path(f['min_x'].values, f['min_y'].values,
                                             f['max_x'].values, f['max_y'].values))
        else:
            self.raw.setPath(segments_path([], [], [], []))
            self.final.setPath(segments_path([], [], [], []))
        self._update_visibility()

    def _update_visibility(self):
        az = self.azimuth.currentIndex()
        only = self.only_az.isChecked()
        self.only_az.setEnabled(self.show_points.isChecked())
        for i, s in enumerate(self.scatter):
            s.setVisible(self.show_points.isChecked() and (not only or i == az))
        self.raw.setVisible(self.show_raw.isChecked())
        self.final.setVisible(self.show_final.isChecked())
        self._repaint()

    def _repaint(self):
        # full repaint: partial updates of large cosmetic-pen paths can be skipped by Qt
        self.plot.viewport().update()
