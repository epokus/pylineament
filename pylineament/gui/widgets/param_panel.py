from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (QAbstractSpinBox, QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout,
                             QHBoxLayout, QLabel, QPushButton, QSpinBox, QVBoxLayout, QWidget)

from ..params import LINE_FITS, SPECS, Params

# parameters that change the tile preview (n_jobs and keep_intermediate only affect a full run)
PREVIEW_PARAMS = {'split_size', 'downscale', 'z_multip', 'eps', 'thresh', 'min_dist', 'seg_len',
                  'line_fit'}


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
                ed = QSpinBox()
                ed.valueChanged.connect(lambda _v, n=name: self._emit(n))
            else:
                ed = QDoubleSpinBox()
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
               'v1.0.1) regresses row on column and biases azimuths towards E-W; PCA fits the '
               'principal axis and is orientation-independent.')
        self.line_fit.setToolTip(tip)
        self.line_fit.currentIndexChanged.connect(lambda _i: self._emit('line_fit'))
        lab = QLabel('Line fit')
        lab.setToolTip(tip)
        form.addRow(lab, self.line_fit)

    def _emit(self, name):
        if not self._quiet:
            self.changed.emit(name)

    def params(self):
        d = {n: ed.value() for n, ed in self._editors.items()}
        d['line_fit'] = self.line_fit.currentData()
        d['keep_intermediate'] = self.keep.isChecked()
        return Params.from_dict(d)

    def set_params(self, p, emit=False):
        self._quiet = True
        try:
            for n, ed in self._editors.items():
                ed.setValue(getattr(p, n))
            self.line_fit.setCurrentIndex(self.line_fit.findData(p.line_fit))
            self.keep.setChecked(p.keep_intermediate)
        finally:
            self._quiet = False
        if emit:
            self.changed.emit('*')

    def set_locked(self, locked):
        for w in list(self._editors.values()) + [self.line_fit, self.keep]:
            w.setEnabled(not locked)
