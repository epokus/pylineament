import os

import numpy as np
import pyqtgraph as pg
from PyQt5.QtCore import Qt, QUrl, pyqtSignal
from PyQt5.QtGui import QDesktopServices, QPainterPath, QPolygonF
from PyQt5.QtCore import QPointF
from PyQt5.QtWidgets import (QFormLayout, QGroupBox, QHBoxLayout, QLabel, QPushButton,
                             QVBoxLayout, QWidget, QGraphicsPathItem)

from ..pipeline import line_stats

ROSE_BIN = 10  # degrees


class ResultsPanel(QWidget):
    export_csv_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.out_path = None

        self.summary = QFormLayout()
        self._fields = {}
        for key in ['Output', 'Lineaments', 'Total length', 'Mean length', 'Median length',
                    'Tiles', 'Run time', 'Parameters']:
            lab = QLabel('–')
            lab.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self.summary.addRow(key, lab)
            self._fields[key] = lab

        self.open_folder = QPushButton('Open output folder')
        self.open_folder.clicked.connect(self._open_folder)
        self.export_csv = QPushButton('Export CSV…')
        self.export_csv.clicked.connect(self.export_csv_requested)
        for b in (self.open_folder, self.export_csv):
            b.setEnabled(False)

        box = QGroupBox('Summary')
        bl = QVBoxLayout(box)
        bl.addLayout(self.summary)
        row = QHBoxLayout()
        row.addWidget(self.open_folder)
        row.addWidget(self.export_csv)
        row.addStretch()
        bl.addLayout(row)
        bl.addStretch()

        self.rose = pg.PlotWidget(background='w', title='Rose diagram (azimuth, 10° bins)')
        self.rose.setAspectLocked(True)
        self.rose.hideAxis('left')
        self.rose.hideAxis('bottom')
        self.rose.setMouseEnabled(False, False)
        self.hist = pg.PlotWidget(background='w', title='Length distribution')
        self.hist.setLabel('left', 'count')
        self.hist.setMouseEnabled(False, False)

        lay = QHBoxLayout(self)
        lay.addWidget(box, 1)
        lay.addWidget(self.rose, 1)
        lay.addWidget(self.hist, 1)
        self.clear()

    def clear(self):
        for lab in self._fields.values():
            lab.setText('–')
        self.rose.clear()
        self.hist.clear()
        self.out_path = None
        for b in (self.open_folder, self.export_csv):
            b.setEnabled(False)

    def set_result(self, res, raster, params, out_path):
        self.clear()
        self.out_path = out_path
        lines = res['lines']
        az, length = line_stats(lines, raster.is_geographic)
        units = 'km' if raster.is_geographic else raster.units()
        if units == 'm':
            length, units = length / 1000.0, 'km'
        f = self._fields
        f['Output'].setText(os.path.basename(out_path) if out_path else '(not saved)')
        f['Output'].setToolTip(out_path or '')
        f['Lineaments'].setText(str(len(lines)))
        if len(lines):
            f['Total length'].setText(f'{length.sum():,.2f} {units}')
            f['Mean length'].setText(f'{length.mean():,.3f} {units}')
            f['Median length'].setText(f'{np.median(length):,.3f} {units}')
        failed = [t for t in res['tiles'] if not t['ok']]
        f['Tiles'].setText(f"{len(res['tiles'])} processed"
                           + (f', <span style="color:#d62728">{len(failed)} failed (see log)</span>'
                              if failed else ''))
        f['Run time'].setText(f"{res['seconds']:.1f} s")
        items = [f'{k}={v}' for k, v in params.to_dict().items()]
        f['Parameters'].setText('\n'.join(', '.join(items[i:i + 3]) for i in range(0, len(items), 3)))
        self.open_folder.setEnabled(bool(out_path))
        self.export_csv.setEnabled(len(lines) > 0)
        self._draw_rose(az)
        self._draw_hist(length, units)

    def _draw_rose(self, az):
        if len(az) == 0:
            return
        bins = np.arange(0, 180 + ROSE_BIN, ROSE_BIN)
        counts, _ = np.histogram(az, bins=bins)
        rmax = counts.max() or 1
        path = QPainterPath()
        for i, c in enumerate(counts):
            if c == 0:
                continue
            r = c / rmax
            for offset in (0, 180):  # lineaments are axial: draw both directions
                a0 = np.radians(bins[i] + offset)
                a1 = np.radians(bins[i + 1] + offset)
                t = np.linspace(a0, a1, 8)
                pts = [QPointF(0, 0)] + [QPointF(r * np.sin(a), r * np.cos(a)) for a in t]
                path.addPolygon(QPolygonF(pts))
                path.closeSubpath()
        item = QGraphicsPathItem(path)
        item.setPen(pg.mkPen('#8b1a1a', width=1))
        item.setBrush(pg.mkBrush('#e0525288'))
        for frac in (0.25, 0.5, 0.75, 1.0):
            circle = pg.QtWidgets.QGraphicsEllipseItem(-frac, -frac, 2 * frac, 2 * frac)
            circle.setPen(pg.mkPen('#c0c0c0', width=1))
            self.rose.addItem(circle)
        self.rose.addItem(pg.PlotDataItem([-1, 1], [0, 0], pen=pg.mkPen('#c0c0c0')))
        self.rose.addItem(pg.PlotDataItem([0, 0], [-1, 1], pen=pg.mkPen('#c0c0c0')))
        for text, x, y in (('N', 0, 1.12), ('E', 1.12, 0), ('S', 0, -1.12), ('W', -1.12, 0)):
            lab = pg.TextItem(text, color='#404040', anchor=(0.5, 0.5))
            lab.setPos(x, y)
            self.rose.addItem(lab)
        self.rose.addItem(item)
        mx = pg.TextItem(f'outer ring = {rmax}', color='#606060', anchor=(1, 1))
        mx.setPos(1.2, -1.2)
        self.rose.addItem(mx)
        self.rose.setRange(xRange=(-1.25, 1.25), yRange=(-1.25, 1.25), padding=0)

    def _draw_hist(self, length, units):
        if len(length) == 0:
            return
        counts, edges = np.histogram(length, bins=min(40, max(5, len(length) // 5)))
        self.hist.addItem(pg.BarGraphItem(x0=edges[:-1], x1=edges[1:], height=counts,
                                          brush='#4a90d9', pen=pg.mkPen('#2a5d8f')))
        self.hist.setLabel('bottom', f'length ({units})')

    def _open_folder(self):
        if self.out_path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(self.out_path)))
