import copy

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (QColorDialog, QComboBox, QDoubleSpinBox, QFormLayout, QGridLayout,
                             QGroupBox, QLabel, QPushButton, QVBoxLayout, QWidget)

from ..style import (LINE_LAYERS, LINE_STYLES, POINT_MODES, POINT_SYMBOLS, default_style,
                     merge_style)


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

    def __init__(self, parent=None):
        super().__init__(parent)
        self._quiet = False
        self._style = default_style()
        self._rows = {}

        lines_box = QGroupBox('Lines')
        grid = QGridLayout(lines_box)
        for col, text in enumerate(['Layer', 'Colour', 'Width', 'Style']):
            head = QLabel(f'<b>{text}</b>')
            grid.addWidget(head, 0, col)
        for row, (key, (label, view, *_)) in enumerate(LINE_LAYERS.items(), start=1):
            lab = QLabel(f'{label}<br><span style="color:#888">{view}</span>')
            color = ColorButton()
            color.changed.connect(lambda _c: self._emit())
            width = QDoubleSpinBox()
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
        self.size = QDoubleSpinBox()
        self.size.setRange(1.0, 20.0)
        self.size.setSingleStep(0.5)
        self.size.setDecimals(1)
        self.opacity = QDoubleSpinBox()
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
        finally:
            self._quiet = False
        if emit:
            self.changed.emit(self.current_style())

    def _emit(self):
        if self._quiet:
            return
        for key, (color, width, st) in self._rows.items():
            self._style[key] = {'color': color.color(), 'width': width.value(),
                                'style': st.currentText()}
        self._style['points'] = {'symbol': self.symbol.currentData(), 'size': self.size.value(),
                                 'opacity': self.opacity.value(), 'mode': self.mode.currentData(),
                                 'color': self.point_color.color()}
        self.point_color.setEnabled(self.mode.currentData() == 'single')
        self.changed.emit(self.current_style())
