import pyqtgraph as pg
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QCheckBox, QComboBox, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ..style import default_style
from .common import (MapPlot, display_hillshade, make_pen, path_item, rects_path, robust_levels,
                     segments_path)

MAX_LABELS = 400


class MapView(QWidget):
    """Overview of the whole raster: background, tile grid, selected tile and extracted lines."""

    tile_clicked = pyqtSignal(float, float)
    hovered = pyqtSignal(float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.raster = None
        self._labels = []
        self._bg_cache = {}

        self.background = QComboBox()
        self.background.addItems(['Hillshade', 'Elevation'])
        self.background.currentIndexChanged.connect(self._draw_background)
        self.show_grid = QCheckBox('Tile grid')
        self.show_grid.setChecked(True)
        self.show_grid.toggled.connect(self._toggle_grid)
        self.show_preview = QCheckBox('Show preview lines')
        self.show_preview.setChecked(True)
        self.show_preview.setToolTip('Final lines of the last tile preview')
        self.show_preview.toggled.connect(self._update_visibility)
        self.show_lines = QCheckBox('Extracted lineaments')
        self.show_lines.setChecked(True)
        self.show_lines.setToolTip('Result of the last full extraction')
        self.show_lines.toggled.connect(self._update_visibility)
        self.info = QLabel('')
        self.stale = QLabel('⚠ preview lines out of date')
        self.stale.setToolTip('Parameters changed since the last tile preview. Refresh the '
                              'preview (F5) to update the preview lines.')
        self.stale.setStyleSheet('color: #c77700; font-weight: bold;')
        self.stale.setVisible(False)

        bar = QHBoxLayout()
        bar.addWidget(QLabel('Background'))
        bar.addWidget(self.background)
        bar.addSpacing(12)
        bar.addWidget(self.show_grid)
        bar.addWidget(self.show_preview)
        bar.addWidget(self.show_lines)
        bar.addSpacing(12)
        bar.addWidget(self.stale)
        bar.addStretch()
        bar.addWidget(self.info)

        self.plot = MapPlot()
        self.plot.clicked.connect(self.tile_clicked)
        self.plot.hovered.connect(self.hovered)
        self.grid = path_item(1)
        self.selected = path_item(4)
        self.lines = path_item(2)
        self.preview_lines = path_item(3)
        for it in (self.grid, self.selected, self.lines, self.preview_lines):
            self.plot.addItem(it, ignoreBounds=True)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addLayout(bar)
        lay.addWidget(self.plot)

        self.placeholder = pg.TextItem('Open a DEM (File > Open, Ctrl+O, or drop a file here).\n'
                                       'New here? See the How to use tab (F1).',
                                       color='#c8c8c8', anchor=(0.5, 0.5))
        self.plot.addItem(self.placeholder, ignoreBounds=True)
        self.apply_style(default_style())

    # ------------------------------------------------------------------ raster
    def set_raster(self, raster):
        self.raster = raster
        self._bg_cache = {}
        self.plot.removeItem(self.placeholder)
        self.plot.set_geographic(None)
        if raster.is_geographic:
            x, y, w, h = raster.map_rect()
            self.plot.set_geographic(y + h / 2)
        self.clear_lines()
        self.clear_preview_lines()
        self._draw_background()
        self.plot.autoRange()

    def _draw_background(self):
        if self.raster is None:
            return
        mode = self.background.currentText()
        if mode not in self._bg_cache:
            d = self.raster.display
            if mode == 'Hillshade':
                img = display_hillshade(d, 315, 45, 1.0)
                lut = None
                levels = (0.0, 255.0)
            else:
                img = d
                lut = pg.colormap.get('viridis').getLookupTable(nPts=256)
                levels = robust_levels(d)
            self._bg_cache[mode] = (img, levels, lut)
        img, levels, lut = self._bg_cache[mode]
        self.plot.set_image(img, self.raster.map_rect(), levels=levels, lut=lut)

    # ------------------------------------------------------------------- grid
    def set_tiles(self, tiles):
        for lab in self._labels:
            self.plot.removeItem(lab)
        self._labels = []
        rects = [self.raster.tile_rect(t) for t in tiles]
        self.grid.setPath(rects_path(rects))
        if len(tiles) <= MAX_LABELS:
            for t, (x, y, w, h) in zip(tiles, rects):
                lab = pg.TextItem(str(t.n), color='#ffd400', anchor=(0.5, 0.5),
                                  fill=pg.mkBrush(0, 0, 0, 110))
                lab.setFont(QFont('Segoe UI', 10, QFont.Bold))
                lab.setPos(x + w / 2, y + h / 2)
                lab.setZValue(1)
                lab.setVisible(self.show_grid.isChecked())
                self.plot.addItem(lab, ignoreBounds=True)
                self._labels.append(lab)
        self.info.setText(f'{len(tiles)} tiles')

    def _toggle_grid(self, on):
        self.grid.setVisible(on)
        for lab in self._labels:
            lab.setVisible(on)
        self.plot.viewport().update()

    def set_selected(self, tile):
        self.selected.setPath(rects_path([self.raster.tile_rect(tile)] if tile else []))

    # ------------------------------------------------------------------ lines
    def set_lines(self, lines):
        self.lines.setPath(_lines_path(lines))
        self._update_visibility()

    def clear_lines(self):
        self.lines.setPath(segments_path([], [], [], []))
        self.plot.viewport().update()

    def set_preview_lines(self, lines):
        self.preview_lines.setPath(_lines_path(lines))
        self._update_visibility()

    def clear_preview_lines(self):
        self.preview_lines.setPath(segments_path([], [], [], []))
        self.plot.viewport().update()

    def set_preview_stale(self, stale):
        self.stale.setVisible(stale)

    def _update_visibility(self):
        self.lines.setVisible(self.show_lines.isChecked())
        self.preview_lines.setVisible(self.show_preview.isChecked())
        self.plot.viewport().update()

    # ------------------------------------------------------------------ style
    def apply_style(self, style):
        self.grid.setPen(make_pen(style['grid']))
        self.selected.setPen(make_pen(style['selected']))
        self.lines.setPen(make_pen(style['result']))
        self.preview_lines.setPen(make_pen(style['preview_overview']))
        self.plot.viewport().update()


def _lines_path(lines):
    return segments_path(lines['min_x'].values, lines['min_y'].values,
                         lines['max_x'].values, lines['max_y'].values)
