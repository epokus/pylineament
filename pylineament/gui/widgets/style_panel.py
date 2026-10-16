import copy

from PyQt5.QtCore import QSize, pyqtSignal
from PyQt5.QtGui import QColor, QIcon
from PyQt5.QtWidgets import (QCheckBox, QColorDialog, QComboBox, QFormLayout, QGridLayout,
                             QGroupBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget)

from ..style import (LINE_LAYERS, LINE_STYLES, PALETTES, POINT_MODES, POINT_SYMBOLS, default_style,
                     merge_style)
from .common import palette_pixmap
from .spinbox import DoubleSpinBox


class ColorButton(QPushButton):
    """Button showing a colour swatch; opens a colour dialog (with transparency) when clicked."""

    changed = pyqtSignal(str)

    def __init__(self, color='#ffffff', parent=None):
        super().__init__(parent)
        self.setFixedWidth(64)
        self.clicked.connect(self._pick)
        self.set_color(color)

    def color(self):
        return self._color

    def set_color(self, color):
        self._color = color
        c = QColor(color)
        self.setStyleSheet(f'background-color: {c.name()}; border: 1px solid #555; '
                           'min-height: 18px;')
        self.setToolTip(f'{color} (opacity {c.alphaF():.0%})')

    def _pick(self):
        c = QColorDialog.getColor(QColor(self._color), self, 'Choose colour',
                                  QColorDialog.ShowAlphaChannel)
        if c.isValid():
            name = c.name(QColor.HexArgb) if c.alpha() < 255 else c.name()
            self.set_color(name)
            self.changed.emit(name)


class StylePanel(QWidget):
    """Colours, widths and symbols of every line and point layer."""

    changed = pyqtSignal(object)  # style dict
    range_requested = pyqtSignal(str)  # 'auto' (2-98 %) or 'full' (min-max of the DEM)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._quiet = False
        self._style = default_style()
        self._rows = {}

        topo_box = QGroupBox('Topography (elevation backgrounds)')
        tf = QFormLayout(topo_box)
        self.palette = QComboBox()
        self.palette.setIconSize(QSize(96, 14))
        for k, v in PALETTES.items():
            self.palette.addItem(QIcon(palette_pixmap(k)), v, k)
        self.reverse = QCheckBox('Reverse palette')
        self.vmin = DoubleSpinBox()
        self.vmax = DoubleSpinBox()
        for sb in (self.vmin, self.vmax):
            sb.setRange(-12000.0, 12000.0)
            sb.setDecimals(2)
            sb.setSingleStep(10.0)
            sb.setKeyboardTracking(False)
        auto = QPushButton('Auto (2–98 %)')
        auto.setToolTip('Stretch the palette over the 2nd–98th percentile of the DEM')
        auto.clicked.connect(lambda: self.range_requested.emit('auto'))
        full = QPushButton('Full range')
        full.setToolTip('Stretch the palette over the minimum–maximum of the DEM')
        full.clicked.connect(lambda: self.range_requested.emit('full'))
        range_buttons = QHBoxLayout()
        range_buttons.addWidget(auto)
        range_buttons.addWidget(full)
        self.hs_opacity = DoubleSpinBox()
        self.hs_opacity.setRange(0.0, 1.0)
        self.hs_opacity.setSingleStep(0.05)
        self.hs_opacity.setDecimals(2)
        self.hs_opacity.setToolTip('Strength of the hillshade in the "Elevation + hillshade" and '
                                   '"Tile DEM + hillshade" backgrounds (0 = colour only).')
        self.palette.currentIndexChanged.connect(lambda _i: self._emit())
        self.reverse.toggled.connect(lambda _v: self._emit())
        self.vmin.valueChanged.connect(lambda _v: self._emit('vmin'))
        self.vmax.valueChanged.connect(lambda _v: self._emit('vmax'))
        self.hs_opacity.valueChanged.connect(lambda _v: self._emit())
        tf.addRow('Palette', self.palette)
        tf.addRow('', self.reverse)
        tf.addRow('Minimum', self.vmin)
        tf.addRow('Maximum', self.vmax)
        tf.addRow('', range_buttons)
        tf.addRow('Hillshade overlay', self.hs_opacity)

        lines_box = QGroupBox('Lines')
        grid = QGridLayout(lines_box)
        for col, text in enumerate(['Layer', 'Colour', 'Width', 'Style']):
            head = QLabel(f'<b>{text}</b>')
            grid.addWidget(head, 0, col)
        for row, (key, (label, view, *_)) in enumerate(LINE_LAYERS.items(), start=1):
            lab = QLabel(f'{label}<br><span style="color:#888">{view}</span>')
            color = ColorButton()
            color.changed.connect(lambda _c: self._emit())
            width = DoubleSpinBox()
            width.setRange(0.5, 10.0)
            width.setSingleStep(0.5)
            width.setDecimals(1)
            width.valueChanged.connect(lambda _v: self._emit())
            style = QComboBox()
            style.addItems(LINE_STYLES)
            style.currentIndexChanged.connect(lambda _i: self._emit())
            for col, w in enumerate((lab, color, width, style)):
                grid.addWidget(w, row, col)
            self._rows[key] = (color, width, style)

        pts_box = QGroupBox('Edge points (tile preview)')
        form = QFormLayout(pts_box)
        self.symbol = QComboBox()
        for k, v in POINT_SYMBOLS.items():
            self.symbol.addItem(v, k)
        self.size = DoubleSpinBox()
        self.size.setRange(1.0, 20.0)
        self.size.setSingleStep(0.5)
        self.size.setDecimals(1)
        self.opacity = DoubleSpinBox()
        self.opacity.setRange(0.05, 1.0)
        self.opacity.setSingleStep(0.05)
        self.opacity.setDecimals(2)
        self.mode = QComboBox()
        for k, v in POINT_MODES.items():
            self.mode.addItem(v, k)
        self.point_color = ColorButton()
        self.symbol.currentIndexChanged.connect(lambda _i: self._emit())
        self.size.valueChanged.connect(lambda _v: self._emit())
        self.opacity.valueChanged.connect(lambda _v: self._emit())
        self.mode.currentIndexChanged.connect(lambda _i: self._emit())
        self.point_color.changed.connect(lambda _c: self._emit())
        form.addRow('Symbol', self.symbol)
        form.addRow('Size (px)', self.size)
        form.addRow('Opacity', self.opacity)
        form.addRow('Colour', self.mode)
        form.addRow('Single colour', self.point_color)

        reset = QPushButton('Reset styles')
        reset.clicked.connect(lambda: self.set_style(default_style(), emit=True))

        lay = QVBoxLayout(self)
        lay.addWidget(topo_box)
        lay.addWidget(lines_box)
        lay.addWidget(pts_box)
        lay.addWidget(reset)
        lay.addStretch()
        self.set_style(self._style)

    def current_style(self):
        return copy.deepcopy(self._style)

    def set_style(self, style, emit=False):
        self._style = merge_style(style)
        self._quiet = True
        try:
            for key, (color, width, st) in self._rows.items():
                spec = self._style[key]
                color.set_color(spec['color'])
                width.setValue(spec['width'])
                st.setCurrentText(spec['style'])
            p = self._style['points']
            self.symbol.setCurrentIndex(self.symbol.findData(p['symbol']))
            self.size.setValue(p['size'])
            self.opacity.setValue(p['opacity'])
            self.mode.setCurrentIndex(self.mode.findData(p['mode']))
            self.point_color.set_color(p['color'])
            self.point_color.setEnabled(p['mode'] == 'single')
            t = self._style['topo']
            self.palette.setCurrentIndex(self.palette.findData(t['palette']))
            self.reverse.setChecked(t['reverse'])
            self.vmin.setValue(t['vmin'])
            self.vmax.setValue(t['vmax'])
            self.hs_opacity.setValue(t['hs_opacity'])
        finally:
            self._quiet = False
        if emit:
            self.changed.emit(self.current_style())

    def _emit(self, source=None):
        if self._quiet:
            return
        for key, (color, width, st) in self._rows.items():
            self._style[key] = {'color': color.color(), 'width': width.value(),
                                'style': st.currentText()}
        self._style['points'] = {'symbol': self.symbol.currentData(), 'size': self.size.value(),
                                 'opacity': self.opacity.value(), 'mode': self.mode.currentData(),
                                 'color': self.point_color.color()}
        self.point_color.setEnabled(self.mode.currentData() == 'single')
        vmin, vmax = self.vmin.value(), self.vmax.value()
        if vmax <= vmin:  # keep a valid range: push the other bound
            self._quiet = True
            if source == 'vmax':
                vmin = vmax - 1.0
                self.vmin.setValue(vmin)
            else:
                vmax = vmin + 1.0
                self.vmax.setValue(vmax)
            self._quiet = False
        self._style['topo'] = {'palette': self.palette.currentData(),
                               'reverse': self.reverse.isChecked(), 'vmin': vmin, 'vmax': vmax,
                               'hs_opacity': self.hs_opacity.value()}
        self.changed.emit(self.current_style())

    def set_topo_range(self, vmin, vmax):
        """Set the elevation range (e.g. after opening a DEM) and emit the new style."""
        self._quiet = True
        self.vmin.setValue(vmin)
        self.vmax.setValue(vmax)
        self._quiet = False
        self._emit()
