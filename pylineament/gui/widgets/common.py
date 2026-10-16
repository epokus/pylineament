import numpy as np
import pyqtgraph as pg
from PyQt5.QtCore import QRectF, Qt, pyqtSignal
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QGraphicsPathItem

from pylineament.pylineament import hillshade

pg.setConfigOptions(imageAxisOrder='row-major', antialias=True)

_PEN_STYLES = {'solid': Qt.SolidLine, 'dash': Qt.DashLine, 'dot': Qt.DotLine,
               'dash-dot': Qt.DashDotLine}


def make_pen(spec):
    """Cosmetic pen from a line style dict {'color', 'width', 'style'}."""
    pen = pg.mkPen(QColor(spec['color']), width=spec['width'])
    pen.setStyle(_PEN_STYLES.get(spec['style'], Qt.SolidLine))
    pen.setCosmetic(True)
    return pen


def make_brush(color, opacity=1.0):
    c = QColor(color)
    c.setAlphaF(c.alphaF() * opacity)
    return pg.mkBrush(c)


def segments_path(x0, y0, x1, y1):
    """One QPainterPath with independent segments (x0, y0)-(x1, y1)."""
    n = len(x0)
    if n == 0:
        return pg.arrayToQPath(np.zeros(0), np.zeros(0))
    x = np.empty(2 * n)
    y = np.empty(2 * n)
    x[0::2], x[1::2] = x0, x1
    y[0::2], y[1::2] = y0, y1
    return pg.arrayToQPath(x, y, connect='pairs')


def path_item(z=0):
    item = QGraphicsPathItem()
    item.setZValue(z)
    return item


def rects_path(rects):
    x, y = [], []
    for (rx, ry, w, h) in rects:
        x += [rx, rx + w, rx + w, rx, rx]
        y += [ry, ry, ry + h, ry + h, ry]
    if not x:
        return pg.arrayToQPath(np.zeros(0), np.zeros(0))
    conn = np.ones(len(x), bool)
    conn[4::5] = False
    return pg.arrayToQPath(np.array(x), np.array(y), connect=conn)


def display_hillshade(arr, azimuth=315, altitude=45, z_multip=1.0):
    a = np.array(arr, dtype='float64')
    mask = ~np.isfinite(a)
    if mask.all():
        return np.zeros_like(a)
    if mask.any():
        a[mask] = np.nanmin(a)
    hs = hillshade(a, azimuth, altitude, z_multip)
    hs[mask] = np.nan
    return hs


def robust_levels(arr):
    v = arr[np.isfinite(arr)]
    if v.size == 0:
        return 0.0, 1.0
    lo, hi = np.percentile(v, [1, 99])
    return (float(lo), float(hi)) if hi > lo else (float(lo), float(lo) + 1.0)


class MapPlot(pg.PlotWidget):
    """PlotWidget with locked aspect, map-coordinate axes and click / hover signals."""

    clicked = pyqtSignal(float, float)
    hovered = pyqtSignal(float, float)

    def __init__(self, parent=None):
        super().__init__(parent, background='#202124')
        self.setAspectLocked(True)
        self.showGrid(x=False, y=False)
        for ax in ('left', 'bottom'):
            self.getAxis(ax).setTextPen('#c8c8c8')
            self.getAxis(ax).setPen('#808080')
        self.image = pg.ImageItem()
        self.image.setZValue(-10)
        self.addItem(self.image)
        self.scene().sigMouseMoved.connect(self._moved)
        self.scene().sigMouseClicked.connect(self._clicked)

    def set_geographic(self, lat):
        """Lock aspect so that a degree of longitude is drawn shorter than a degree of latitude."""
        ratio = 1.0 / max(np.cos(np.radians(lat)), 0.05) if lat is not None else 1.0
        self.setAspectLocked(True, ratio=ratio)

    def set_image(self, arr, rect, levels=None, lut=None, row0_south=False):
        data = arr if row0_south else arr[::-1]
        if data.ndim == 3:  # RGBA image (already coloured)
            self.image.setLookupTable(None)
            self.image.setImage(np.ascontiguousarray(data), autoLevels=False, levels=(0, 255))
        else:
            self.image.setImage(np.ascontiguousarray(data), autoLevels=False,
                                levels=levels or robust_levels(data))
            self.image.setLookupTable(lut)
        self.image.setRect(QRectF(*rect))

    def _moved(self, pos):
        if self.plotItem.vb.sceneBoundingRect().contains(pos):
            p = self.plotItem.vb.mapSceneToView(pos)
            self.hovered.emit(p.x(), p.y())

    def _clicked(self, ev):
        if ev.button() == 1 and not ev.double():
            p = self.plotItem.vb.mapSceneToView(ev.scenePos())
            self.clicked.emit(p.x(), p.y())


# ------------------------------------------------------------------ elevation palettes
_CUSTOM_PALETTES = {
    # similar to matplotlib's "terrain" (no matplotlib dependency)
    'terrain': [(0.0, (51, 51, 153)), (0.15, (0, 153, 255)), (0.25, (0, 204, 102)),
                (0.5, (255, 255, 153)), (0.75, (128, 92, 84)), (1.0, (255, 255, 255))],
    'hypsometric': [(0.0, (38, 115, 0)), (0.25, (152, 195, 76)), (0.45, (238, 222, 145)),
                    (0.65, (196, 140, 75)), (0.85, (130, 87, 64)), (1.0, (245, 245, 245))],
    'grey': [(0.0, (0, 0, 0)), (1.0, (255, 255, 255))],
}


def palette_lut(name, reverse=False, n=256):
    """(n, 3) uint8 lookup table for an elevation palette."""
    if name in _CUSTOM_PALETTES:
        pos, cols = zip(*_CUSTOM_PALETTES[name])
        cmap = pg.ColorMap(np.array(pos), np.array(cols, dtype=np.ubyte))
    else:
        cmap = pg.colormap.get(name)
    lut = cmap.getLookupTable(0.0, 1.0, n, alpha=False).astype(np.uint8)
    return lut[::-1].copy() if reverse else lut


def colorize(dem, vmin, vmax, lut, hillshade_img=None, hs_opacity=0.0):
    """RGBA uint8 image of the DEM through `lut`, optionally multiplied by a hillshade.

    hs_opacity = 0 gives pure colour; 1 gives colour fully modulated by the hillshade.
    NaN (nodata) cells are transparent.
    """
    d = np.asarray(dem, dtype='float32')
    t = np.clip((d - vmin) / max(vmax - vmin, 1e-12), 0.0, 1.0)
    idx = np.nan_to_num(t * (len(lut) - 1)).astype(np.int32)
    rgb = lut[idx].astype('float32')
    if hillshade_img is not None and hs_opacity > 0:
        shade = np.nan_to_num(np.asarray(hillshade_img, dtype='float32') / 255.0, nan=1.0)
        rgb *= ((1.0 - hs_opacity) + hs_opacity * shade)[..., None]
    out = np.empty(d.shape + (4,), np.uint8)
    out[..., :3] = np.clip(rgb, 0, 255)
    out[..., 3] = np.where(np.isfinite(d), 255, 0)
    return out


def palette_pixmap(name, reverse=False, w=96, h=14):
    """Small gradient swatch for palette selectors."""
    from PyQt5.QtGui import QImage, QPixmap
    lut = palette_lut(name, reverse, w)
    img = np.ascontiguousarray(np.repeat(lut[None, :, :], h, axis=0))
    qimg = QImage(img.data, w, h, 3 * w, QImage.Format_RGB888)
    return QPixmap.fromImage(qimg.copy())
