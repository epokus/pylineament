import json
import os
import time

from PyQt5.QtCore import QSettings, Qt, QTimer
from PyQt5.QtGui import QIcon, QKeySequence
from PyQt5.QtWidgets import (QAction, QApplication, QDockWidget, QFileDialog, QFormLayout,
                             QGroupBox, QLabel, QMainWindow, QMessageBox, QProgressBar,
                             QPushButton, QScrollArea, QStyle, QTabWidget, QVBoxLayout, QWidget)

from .jobs import ExtractionRunner, PreviewRunner
from .params import Params
from .raster import RasterInfo
from .style import merge_style
from .widgets.help_view import HelpView
from .widgets.log_panel import LogPanel
from .widgets.map_view import MapView
from .widgets.param_panel import PREVIEW_PARAMS, ParamPanel
from .widgets.preview_view import PreviewView
from .widgets.results_panel import ResultsPanel
from .widgets.style_panel import StylePanel

RASTER_FILTER = 'Rasters (*.tif *.tiff *.jpg *.jpeg *.png);;GeoTIFF (*.tif *.tiff);;All files (*)'
RASTER_EXT = ('.tif', '.tiff', '.jpg', '.jpeg', '.png')
MAX_RECENT = 8
ICON = os.path.join(os.path.dirname(__file__), 'icon.ico')


class MainWindow(QMainWindow):
    def __init__(self, settings=None):
        super().__init__()
        self.setWindowTitle('Pylineament – geological lineament extraction')
        if os.path.exists(ICON):
            self.setWindowIcon(QIcon(ICON))
        self.setAcceptDrops(True)
        self.settings = settings or QSettings('pylineament', 'pylineament-gui')

        self.raster = None
        self.tiles = []
        self.tile = None
        self.result = None
        self.out_path = None
        self._run_started = 0.0

        self.preview_runner = PreviewRunner(self)
        self.preview_runner.started.connect(lambda _s: self.preview.set_busy('computing preview…'))
        self._shown_key = None     # (tile, preview parameters) of the displayed preview
        self._request_keys = {}    # preview request id -> key
        self.preview_runner.finished.connect(self._preview_done)
        self.preview_runner.failed.connect(self._preview_failed)

        self.runner = ExtractionRunner(self)
        self.runner.stage.connect(lambda s: self.log.log(s))
        self.runner.progress.connect(self._run_progress)
        self.runner.finished.connect(self._run_finished)
        self.runner.failed.connect(self._run_failed)
        self.runner.cancelled.connect(self._run_cancelled)

        self._preview_timer = QTimer(self, singleShot=True, interval=500)
        self._preview_timer.timeout.connect(self.request_preview)
        self.preview_runner.failed.connect(lambda *_: self._update_stale())

        self._build_ui()
        self._build_actions()
        self._restore_settings()
        self._update_actions()

    # ================================================================== UI
    def _build_ui(self):
        # left: raster info + parameters
        self.info_box = QGroupBox('Raster')
        self.info_form = QFormLayout(self.info_box)
        self.info_labels = {}
        for key in ['File', 'Size', 'CRS', 'Pixel size', 'Extent', 'NoData']:
            lab = QLabel('–')
            lab.setWordWrap(True)
            lab.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self.info_form.addRow(key, lab)
            self.info_labels[key] = lab

        self.params_panel = ParamPanel()
        self.params_panel.changed.connect(self._param_changed)
        self.params_panel.save_requested.connect(self.save_params)
        self.params_panel.load_requested.connect(self.load_params)
        pbox = QGroupBox('Parameters')
        QVBoxLayout(pbox).addWidget(self.params_panel)

        self.run_button = QPushButton('Run extraction…')
        self.run_button.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
        self.run_button.setMinimumHeight(34)
        self.run_button.clicked.connect(self.run_extraction)

        left = QWidget()
        ll = QVBoxLayout(left)
        ll.addWidget(self.info_box)
        ll.addWidget(pbox)
        ll.addWidget(self.run_button)
        ll.addStretch()
        self.style_panel = StylePanel()
        self.style_panel.changed.connect(self._style_changed)

        self.side_tabs = QTabWidget()
        for widget, title in ((left, 'Setup'), (self.style_panel, 'Style')):
            scroll = QScrollArea()
            scroll.setWidget(widget)
            scroll.setWidgetResizable(True)
            self.side_tabs.addTab(scroll, title)
        self.side_tabs.setMinimumWidth(390)
        side = QDockWidget('Controls', self)
        side.setObjectName('setup_dock')
        side.setWidget(self.side_tabs)
        side.setTitleBarWidget(QWidget())
        side.setFeatures(QDockWidget.NoDockWidgetFeatures)
        self.addDockWidget(Qt.LeftDockWidgetArea, side)

        # centre: tabs
        self.map = MapView()
        self.map.tile_clicked.connect(self._map_clicked)
        self.map.hovered.connect(self._hover)
        self.preview = PreviewView()
        self.preview.tile_requested.connect(self._preview_tile_spin)
        self.preview.preview_requested.connect(self.request_preview)
        self.preview.auto.toggled.connect(self._auto_preview_toggled)
        self.preview.plot.hovered.connect(self._hover)
        self.results = ResultsPanel()
        self.results.export_csv_requested.connect(self.export_csv)
        self.tabs = QTabWidget()
        self.tabs.addTab(self.map, 'Overview')
        self.tabs.addTab(self.preview, 'Tile preview')
        self.tabs.addTab(self.results, 'Results')
        self.help = HelpView()
        self.tabs.addTab(self.help, 'How to use')
        self.setCentralWidget(self.tabs)

        # bottom: log
        self.log = LogPanel()
        self.log_dock = QDockWidget('Log', self)
        self.log_dock.setObjectName('log_dock')
        self.log_dock.setWidget(self.log)
        self.addDockWidget(Qt.BottomDockWidgetArea, self.log_dock)
        self.resizeDocks([self.log_dock], [150], Qt.Vertical)

        # status bar
        self.cursor_label = QLabel('')
        self.status_label = QLabel('Ready')
        self.status_label.setMinimumWidth(320)
        self.progress = QProgressBar()
        self.progress.setMaximumWidth(220)
        self.progress.setFormat('%v / %m tiles')
        self.progress.setVisible(False)
        self.eta_label = QLabel('')
        sb = self.statusBar()
        sb.addWidget(self.cursor_label, 1)
        sb.addPermanentWidget(self.status_label)
        sb.addPermanentWidget(self.progress)
        sb.addPermanentWidget(self.eta_label)

    def _build_actions(self):
        st = self.style()
        a = self.act_open = QAction(st.standardIcon(QStyle.SP_DialogOpenButton), '&Open DEM…', self)
        a.setShortcut(QKeySequence.Open)
        a.triggered.connect(self.open_dialog)
        a = self.act_preview = QAction(st.standardIcon(QStyle.SP_BrowserReload), '&Preview tile', self)
        a.setShortcut('F5')
        a.triggered.connect(self.request_preview)
        a = self.act_run = QAction(st.standardIcon(QStyle.SP_MediaPlay), '&Run extraction…', self)
        a.setShortcut('Ctrl+R')
        a.triggered.connect(self.run_extraction)
        a = self.act_cancel = QAction(st.standardIcon(QStyle.SP_MediaStop), '&Cancel run', self)
        a.setShortcut('Esc')
        a.triggered.connect(self.cancel_run)
        a = self.act_export = QAction('Export lineaments as &CSV…', self)
        a.triggered.connect(self.export_csv)
        a = self.act_quit = QAction('&Quit', self)
        a.setShortcut(QKeySequence.Quit)
        a.triggered.connect(self.close)

        m = self.menuBar().addMenu('&File')
        m.addAction(self.act_open)
        self.recent_menu = m.addMenu('Open &recent')
        m.addSeparator()
        m.addAction(self.act_export)
        m.addSeparator()
        m.addAction(self.act_quit)

        m = self.menuBar().addMenu('&Parameters')
        m.addAction('&Reset to defaults', lambda: self.params_panel.set_params(Params(), emit=True))
        m.addAction('&Load…', self.load_params)
        m.addAction('&Save…', self.save_params)
        m.addAction('&Copy as Python', self.copy_python)

        m = self.menuBar().addMenu('&Run')
        for a in (self.act_preview, self.act_run, self.act_cancel):
            m.addAction(a)

        m = self.menuBar().addMenu('&View')
        m.addAction(self.log_dock.toggleViewAction())

        m = self.menuBar().addMenu('&Help')
        a = m.addAction('&How to use', lambda: self.tabs.setCurrentWidget(self.help))
        a.setShortcut('F1')
        m.addAction('&About', self.about)

        tb = self.addToolBar('Main')
        tb.setObjectName('main_toolbar')
        tb.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        for a in (self.act_open, self.act_preview, self.act_run, self.act_cancel):
            tb.addAction(a)

    def _update_actions(self):
        has = self.raster is not None
        running = self.runner.running
        self.act_preview.setEnabled(has)
        self.act_run.setEnabled(has and not running)
        self.run_button.setEnabled(has and not running)
        self.act_cancel.setEnabled(running)
        self.act_open.setEnabled(not running)
        self.recent_menu.setEnabled(not running)
        self.act_export.setEnabled(self.result is not None and len(self.result['lines']) > 0)
        self.params_panel.set_locked(running)

    # ============================================================ settings
    def _restore_settings(self):
        geo = self.settings.value('geometry')
        if geo is not None:
            self.restoreGeometry(geo)
        else:
            self.resize(1400, 900)
        state = self.settings.value('state')
        if state is not None:
            self.restoreState(state)
        try:
            d = self.settings.value('params')
            if d:
                self.params_panel.set_params(Params.from_dict(dict(d)))
        except Exception:
            pass
        try:
            style = json.loads(self.settings.value('style') or '{}')
        except (TypeError, ValueError):
            style = {}
        self.style_panel.set_style(merge_style(style), emit=True)
        self._refresh_recent()

    def _save_settings(self):
        self.settings.setValue('geometry', self.saveGeometry())
        self.settings.setValue('state', self.saveState())
        self.settings.setValue('params', self.params_panel.params().to_dict())
        self.settings.setValue('style', json.dumps(self.style_panel.current_style()))

    def _style_changed(self, style):
        self.map.apply_style(style)
        self.preview.apply_style(style)
        self.settings.setValue('style', json.dumps(style))

    def _recent(self):
        v = self.settings.value('recent') or []
        return [v] if isinstance(v, str) else list(v)

    def _refresh_recent(self):
        self.recent_menu.clear()
        files = [f for f in self._recent() if os.path.exists(f)]
        for f in files:
            self.recent_menu.addAction(f, lambda f=f: self.open_raster(f))
        self.recent_menu.setEnabled(bool(files))

    def _last_dir(self):
        return self.settings.value('last_dir') or os.path.expanduser('~')

    # ================================================================ open
    def open_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Open DEM', self._last_dir(), RASTER_FILTER)
        if path:
            self.open_raster(path)

    def open_raster(self, path):
        if self.runner.running:
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            raster = RasterInfo(path)
        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.log.log(f'Could not open {path}: {e}', 'error')
            QMessageBox.critical(self, 'Open DEM', f'Could not open\n{path}\n\n{e}')
            return
        QApplication.restoreOverrideCursor()

        self.raster = raster
        self.result = None
        self._shown_key = None
        self.results.clear()
        self.preview.clear()
        self.settings.setValue('last_dir', os.path.dirname(raster.path))
        recent = [raster.path] + [f for f in self._recent() if f != raster.path]
        self.settings.setValue('recent', recent[:MAX_RECENT])
        self._refresh_recent()

        for k, v in raster.summary().items():
            self.info_labels[k].setText(v)
        self.map.set_raster(raster)
        self._update_tiles(keep_center=False)
        self.tabs.setCurrentWidget(self.map)
        self.log.log(f'Opened {raster.path} ({raster.width} x {raster.height} px, '
                     f'{raster.crs_label()})', 'ok')
        if not raster.georeferenced:
            self.log.log('Image is not georeferenced: coordinates are pixels (y = -row).', 'warn')
        self._update_actions()
        self._schedule_preview(immediate=True)

    # =============================================================== tiles
    def _update_tiles(self, keep_center=True):
        size = self.params_panel.params().split_size
        center = None
        if keep_center and self.tile is not None:
            x, y, w, h = self.raster.tile_rect(self.tile)
            center = (x + w / 2, y + h / 2)
        self.tiles = self.raster.tiles(size)
        self.map.set_tiles(self.tiles)
        self.preview.set_tiles(self.tiles)
        if center is None:
            x, y, w, h = self.raster.map_rect()
            center = (x + w / 2, y + h / 2)
        self._select_tile(self.raster.tile_at(self.tiles, *center) or self.tiles[0], preview=False)

    def _select_tile(self, tile, preview=True):
        self.tile = tile
        self.map.set_selected(tile)
        self.preview.set_tile(tile.n)
        if preview:
            self._schedule_preview(immediate=True)
        self._update_stale()

    def _map_clicked(self, x, y):
        if self.raster is None:
            return
        t = self.raster.tile_at(self.tiles, x, y)
        if t is not None:
            self._select_tile(t)
            self.tabs.setCurrentWidget(self.preview)

    def _preview_tile_spin(self, n):
        if 0 <= n < len(self.tiles):
            self._select_tile(self.tiles[n])

    def _hover(self, x, y):
        if self.raster is None:
            return
        v = self.raster.value_at(x, y)
        t = self.raster.tile_at(self.tiles, x, y)
        txt = f'x = {x:.6g}   y = {y:.6g}'
        if v is not None:
            txt += f'   z = {v:.6g}'
        if t is not None:
            txt += f'   tile {t.n}'
        self.cursor_label.setText(txt)

    # ============================================================ params
    def _param_changed(self, name):
        if self.raster is None:
            return
        if name in ('split_size', '*'):
            self._update_tiles()
        if name in PREVIEW_PARAMS or name == '*':
            self._schedule_preview()
        self._update_stale()

    def save_params(self):
        path, _ = QFileDialog.getSaveFileName(self, 'Save parameters', self._last_dir(),
                                              'Parameters (*.json)')
        if path:
            self.params_panel.params().save(path)
            self.log.log(f'Parameters saved to {path}')

    def load_params(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Load parameters', self._last_dir(),
                                              'Parameters (*.json)')
        if not path:
            return
        try:
            p = Params.load(path)
        except Exception as e:
            QMessageBox.warning(self, 'Load parameters', f'Invalid parameter file:\n{e}')
            return
        self.params_panel.set_params(p, emit=True)
        self.log.log(f'Parameters loaded from {path}')

    def copy_python(self):
        src = self.raster.path if self.raster else 'dem.tif'
        code = self.params_panel.params().to_python(src, self.out_path)
        QApplication.clipboard().setText(code)
        self.log.log('Copied to clipboard:\n' + code)

    # =========================================================== preview
    def _schedule_preview(self, immediate=False):
        if self.raster is None or not self.preview.auto.isChecked():
            return
        self.preview.set_busy('parameters changed…')
        self._preview_timer.start(50 if immediate else 500)

    def _auto_preview_toggled(self, on):
        if on and self._shown_key != self._preview_key():
            self._schedule_preview(immediate=True)
        self._update_stale()

    def request_preview(self):
        if self.raster is None or self.tile is None:
            return
        self._preview_timer.stop()
        seq = self.preview_runner.request(self.raster.path, self.tile,
                                          self.params_panel.params().to_dict())
        self._request_keys[seq] = self._preview_key()
        self.status_label.setText(f'Previewing tile {self.tile.n}…')
        self._update_stale()

    def _preview_key(self):
        p = self.params_panel.params().to_dict()
        return (self.tile.n if self.tile else None, tuple(p[k] for k in sorted(PREVIEW_PARAMS)))

    def _update_stale(self):
        """Remind the user when the displayed preview no longer matches tile + parameters."""
        stale = self.preview.result is not None and self._shown_key != self._preview_key()
        pending = bool(stale and (self.preview_runner.busy or self._preview_timer.isActive()))
        self.preview.set_stale(stale, pending)
        self.map.set_preview_stale(stale)
        self.tabs.setTabText(self.tabs.indexOf(self.preview),
                             'Tile preview ●' if stale else 'Tile preview')
        self.act_preview.setText('&Refresh preview (out of date)' if stale else '&Preview tile')

    def _preview_done(self, _seq, result):
        self.preview.set_busy('')
        self._shown_key = self._request_keys.pop(_seq, None) or self._preview_key()
        self._request_keys = {k: v for k, v in self._request_keys.items() if k > _seq}
        self.preview.show_result(result, self.params_panel.params().z_multip)
        self.map.set_preview_lines(result['final_lines'])
        self._update_stale()
        if result['n_final'] == 0:
            self.log.log(f"Preview tile {result['tile'].n}: no line extracted, try fine-tuning "
                         'the parameters.', 'warn')
        self.status_label.setText(f"Preview tile {result['tile'].n}: {result['n_final']} lines, "
                                  f"{result['seconds']:.1f} s")

    def _preview_failed(self, _seq, error):
        self.preview.set_busy('preview failed – see log')
        self.status_label.setText('Preview failed')
        self.log.log('Preview failed:\n' + error, 'error')

    # =============================================================== run
    def run_extraction(self):
        if self.raster is None or self.runner.running:
            return
        stem = os.path.splitext(self.raster.name)[0]
        default = os.path.join(os.path.dirname(self.raster.path), f'{stem}_lineaments.shp')
        path, _ = QFileDialog.getSaveFileName(self, 'Save lineaments as', default,
                                              'Shapefile (*.shp)')
        if not path:
            return
        if not path.lower().endswith('.shp'):
            path += '.shp'
        params = self.params_panel.params()
        keep_dir = None
        if params.keep_intermediate:
            keep_dir = os.path.splitext(path)[0] + '_intermediate'
            if os.path.isdir(keep_dir) and os.listdir(keep_dir):
                QMessageBox.warning(self, 'Run extraction',
                                    f'The folder for intermediate files is not empty:\n{keep_dir}'
                                    '\n\nChoose another output name or empty the folder.')
                return

        self.out_path = path
        self.result = None
        self.map.clear_lines()
        self.results.clear()
        self._run_started = time.perf_counter()
        self.progress.setRange(0, 0)
        self.progress.setVisible(True)
        self.eta_label.setText('')
        self.status_label.setText('Running…')
        self.log.log(f'Run started: {self.raster.path} → {path}\n'
                     + params.to_python(self.raster.path, path), 'ok')
        self._run_params = params
        self.runner.start(self.raster.path, params.to_dict(), path, self.raster.crs_wkt, keep_dir)
        self._update_actions()

    def cancel_run(self):
        if self.runner.running:
            self.runner.cancel()
            self.status_label.setText('Cancelling…')
            self.log.log('Cancelling…', 'warn')

    def _run_progress(self, done, total, tile_result):
        self.progress.setRange(0, total)
        self.progress.setValue(done)
        if tile_result is not None:
            if not tile_result['ok']:
                self.log.log(f"Tile {tile_result['tile']} failed:\n{tile_result['error']}", 'error')
            elif tile_result['error']:
                self.log.log(f"Tile {tile_result['tile']}: {tile_result['error']}", 'warn')
        if done:
            el = time.perf_counter() - self._run_started
            eta = el / done * (total - done)
            self.eta_label.setText(f'{_fmt(el)} elapsed, ETA {_fmt(eta)}')

    def _run_finished(self, res):
        self.progress.setVisible(False)
        self.eta_label.setText('')
        self.result = res
        lines = res['lines']
        params_file = os.path.splitext(self.out_path)[0] + '_params.json'
        try:
            self._run_params.save(params_file)
        except OSError as e:
            self.log.log(f'Could not write {params_file}: {e}', 'warn')
        failed = [t for t in res['tiles'] if not t['ok']]
        self.log.log(f"Run finished: {len(lines)} lineaments, {len(res['tiles'])} tiles"
                     f"{f', {len(failed)} failed' if failed else ''}, {res['seconds']:.1f} s. "
                     f'Parameters saved to {params_file}', 'warn' if failed else 'ok')
        if res.get('workdir'):
            self.log.log(f"Intermediate files kept in {res['workdir']}")
        self.status_label.setText(f'{len(lines)} lineaments extracted')
        self.map.set_lines(lines)
        self.results.set_result(res, self.raster, self._run_params, self.out_path)
        self.tabs.setCurrentWidget(self.results)
        self._update_actions()
        QApplication.alert(self)

    def _run_failed(self, error):
        self.progress.setVisible(False)
        self.eta_label.setText('')
        self.status_label.setText('Run failed')
        self.log.log('Run failed:\n' + error, 'error')
        self._update_actions()
        QMessageBox.critical(self, 'Run extraction', 'The extraction failed.\n\n'
                             + error.strip().splitlines()[-1] + '\n\nSee the log for details.')

    def _run_cancelled(self):
        self.progress.setVisible(False)
        self.eta_label.setText('')
        self.status_label.setText('Run cancelled')
        self.log.log('Run cancelled; workers stopped and temporary files removed.', 'warn')
        self._update_actions()

    def export_csv(self):
        if not self.result or len(self.result['lines']) == 0:
            return
        default = os.path.splitext(self.out_path or 'lineaments.shp')[0] + '.csv'
        path, _ = QFileDialog.getSaveFileName(self, 'Export CSV', default, 'CSV (*.csv)')
        if path:
            self.result['lines'].to_csv(path, index=False)
            self.log.log(f'Exported {len(self.result["lines"])} lineaments to {path}', 'ok')

    # ============================================================== misc
    def about(self):
        from importlib.metadata import PackageNotFoundError, version
        try:
            v = version('pylineament')
        except PackageNotFoundError:
            v = 'dev'
        QMessageBox.about(self, 'About Pylineament',
                          f'<b>Pylineament</b> {v}<br>Geological lineament extraction from DEMs.'
                          '<br><a href="https://github.com/epokus/pylineament">'
                          'github.com/epokus/pylineament</a>')

    def dragEnterEvent(self, e):
        urls = e.mimeData().urls()
        if (urls and urls[0].isLocalFile() and urls[0].toLocalFile().lower().endswith(RASTER_EXT)
                and not self.runner.running):
            e.acceptProposedAction()

    def dropEvent(self, e):
        self.open_raster(e.mimeData().urls()[0].toLocalFile())

    def closeEvent(self, e):
        if self.runner.running:
            ans = QMessageBox.question(self, 'Quit', 'An extraction is running. Cancel it and quit?')
            if ans != QMessageBox.Yes:
                e.ignore()
                return
            self.runner.cancel()
            self.runner.wait(15)
        self.preview_runner.shutdown()
        self._save_settings()
        e.accept()


def _fmt(s):
    s = int(round(s))
    return f'{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}' if s >= 3600 else f'{s // 60}:{s % 60:02d}'
