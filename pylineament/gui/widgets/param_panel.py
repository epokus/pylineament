from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (QAbstractSpinBox, QCheckBox, QComboBox, QFormLayout,
                             QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget)

from ..params import AZIMUTH_SETS, LINE_FITS, SPECS, Params
from .spinbox import DoubleSpinBox, SpinBox

# parameters that change the tile preview (n_jobs and keep_intermediate only affect a full run)
PREVIEW_PARAMS = {'split_size', 'downscale', 'z_multip', 'eps', 'thresh', 'min_dist', 'seg_len',
                  'line_fit', 'azimuths'}


class ParamPanel(QWidget):
    changed = pyqtSignal(str)          # name of the parameter that changed
    save_requested = pyqtSignal()
    load_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._editors = {}
        self._quiet = False

        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        for name, (label, lo, hi, step, decimals, tip) in SPECS.items():
            if decimals is None:
                ed = SpinBox()
                ed.valueChanged.connect(lambda _v, n=name: self._emit(n))
            else:
                ed = DoubleSpinBox()
                ed.setDecimals(decimals)
                ed.setStepType(QAbstractSpinBox.AdaptiveDecimalStepType)
                ed.valueChanged.connect(lambda _v, n=name: self._emit(n))
            ed.setRange(lo, hi)
            ed.setSingleStep(step)
            ed.setKeyboardTracking(False)  # emit when editing is finished, not on every keystroke
            ed.setToolTip(tip)
            lab = QLabel(label)
            lab.setToolTip(tip)
            form.addRow(lab, ed)
            self._editors[name] = ed
            if name == 'seg_len':
                self._add_line_fit(form)
                self._add_azimuths(form)

        self.keep = QCheckBox('Keep intermediate files')
        self.keep.setToolTip('Keep the tile GeoTIFFs and per-tile CSVs in a folder next to the '
                             'output shapefile.')
        self.keep.toggled.connect(lambda _v: self._emit('keep_intermediate'))

        reset = QPushButton('Reset')
        reset.setToolTip('Restore the library defaults')
        reset.clicked.connect(lambda: self.set_params(Params(), emit=True))
        save = QPushButton('Save…')
        save.clicked.connect(self.save_requested)
        load = QPushButton('Load…')
        load.clicked.connect(self.load_requested)
        buttons = QHBoxLayout()
        for b in (reset, save, load):
            buttons.addWidget(b)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addLayout(form)
        lay.addWidget(self.keep)
        lay.addLayout(buttons)
        self.set_params(Params())

    def _add_line_fit(self, form):
        self.line_fit = QComboBox()
        for key, text in LINE_FITS.items():
            self.line_fit.addItem(text, key)
        tip = ('How a straight line is fitted to each cluster of edge points. OLS (default, '
               'v1.0.1) regresses row on column and biases azimuths towards E-W; TLS (total least '
               'squares) fits the '
               'principal axis and is orientation-independent.')
        self.line_fit.setToolTip(tip)
        self.line_fit.currentIndexChanged.connect(lambda _i: self._emit('line_fit'))
        lab = QLabel('Line fit')
        lab.setToolTip(tip)
        form.addRow(lab, self.line_fit)

    def _add_azimuths(self, form):
        self.azimuths = QComboBox()
        for n, (_, text) in AZIMUTH_SETS.items():
            self.azimuths.addItem(text, n)
        tip = ('Hillshade illumination directions. With the light at the horizon, azimuths az and '
               'az + 180° give identical edges, so 6 directions (0–150°) cover every orientation '
               'and run about twice as fast. 12 (0–330°) reproduces v1.0.1 exactly; results '
               'differ by about 0.1 % of the lines.')
        self.azimuths.setToolTip(tip)
        self.azimuths.currentIndexChanged.connect(lambda _i: self._emit('azimuths'))
        lab = QLabel('Azimuths')
        lab.setToolTip(tip)
        form.addRow(lab, self.azimuths)

    def _emit(self, name):
        if not self._quiet:
            self.changed.emit(name)

    def params(self):
        d = {n: ed.value() for n, ed in self._editors.items()}
        d['line_fit'] = self.line_fit.currentData()
        d['azimuths'] = self.azimuths.currentData()
        d['keep_intermediate'] = self.keep.isChecked()
        return Params.from_dict(d)

    def set_params(self, p, emit=False):
        self._quiet = True
        try:
            for n, ed in self._editors.items():
                ed.setValue(getattr(p, n))
            self.line_fit.setCurrentIndex(self.line_fit.findData(p.line_fit))
            self.azimuths.setCurrentIndex(self.azimuths.findData(p.azimuths))
            self.keep.setChecked(p.keep_intermediate)
        finally:
            self._quiet = False
        if emit:
            self.changed.emit('*')

    def set_locked(self, locked):
        for w in list(self._editors.values()) + [self.line_fit, self.azimuths, self.keep]:
            w.setEnabled(not locked)
