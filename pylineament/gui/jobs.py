"""Background execution: tile preview in a persistent worker process, full extraction in a pool."""

import multiprocessing
import shutil
import tempfile
import threading
import traceback
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool

from PyQt5.QtCore import QObject, pyqtSignal

from . import pipeline


class PreviewRunner(QObject):
    """Runs pipeline.preview_tile in one reusable worker process.

    Only the latest request matters: while a preview is computing, newer requests replace each
    other in a single pending slot, and results of superseded requests are dropped.
    """

    started = pyqtSignal(int)
    finished = pyqtSignal(int, object)
    failed = pyqtSignal(int, str)
    _done = pyqtSignal(int, object, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._executor = None
        self._workdir = tempfile.mkdtemp(prefix='pylineament_preview_')
        self._seq = 0
        self._running = None
        self._pending = None
        self._done.connect(self._on_done)

    @property
    def busy(self):
        return self._running is not None

    def request(self, src, tile, params):
        self._seq += 1
        job = (self._seq, src, tile, dict(params))
        if self._running is None:
            self._submit(job)
        else:
            self._pending = job
        return self._seq

    def _submit(self, job):
        seq, src, tile, params = job
        if self._executor is None:
            self._executor = ProcessPoolExecutor(max_workers=1,
                                                 mp_context=multiprocessing.get_context('spawn'))
        self._running = seq
        self.started.emit(seq)
        try:
            fut = self._executor.submit(pipeline.preview_tile, src, tile, params, self._workdir)
        except (BrokenProcessPool, RuntimeError):
            self._executor = None
            self._running = None
            self.failed.emit(seq, traceback.format_exc())
            return

        def callback(f, seq=seq):
            try:
                self._done.emit(seq, f.result(), '')
            except BrokenProcessPool:
                self._done.emit(seq, None, 'The preview worker process crashed.\n'
                                           + traceback.format_exc())
            except Exception:
                self._done.emit(seq, None, traceback.format_exc())

        fut.add_done_callback(callback)

    def _on_done(self, seq, result, error):
        self._running = None
        if error and 'worker process crashed' in error:
            self._executor = None
        if seq == self._seq:
            if error:
                self.failed.emit(seq, error)
            else:
                self.finished.emit(seq, result)
        if self._pending is not None:
            job, self._pending = self._pending, None
            self._submit(job)

    def shutdown(self):
        self._pending = None
        if self._executor is not None:
            self._executor.shutdown(wait=False, cancel_futures=True)
            self._executor = None
        shutil.rmtree(self._workdir, ignore_errors=True)


class ExtractionRunner(QObject):
    """Runs pipeline.run_extraction on a driver thread and reports through Qt signals."""

    stage = pyqtSignal(str)
    progress = pyqtSignal(int, int, object)
    finished = pyqtSignal(object)
    failed = pyqtSignal(str)
    cancelled = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thread = None
        self._cancel = threading.Event()

    @property
    def running(self):
        return self._thread is not None and self._thread.is_alive()

    def start(self, src, params, out_path, crs_wkt=None, keep_dir=None):
        if self.running:
            raise RuntimeError('an extraction is already running')
        self._cancel.clear()
        self._thread = threading.Thread(target=self._run, daemon=True,
                                        args=(src, dict(params), out_path, crs_wkt, keep_dir))
        self._thread.start()

    def _run(self, src, params, out_path, crs_wkt, keep_dir):
        try:
            res = pipeline.run_extraction(src, params, out_path, crs_wkt, keep_dir,
                                          progress=lambda d, t, r: self.progress.emit(d, t, r),
                                          cancel=self._cancel, log=self.stage.emit)
        except pipeline.Cancelled:
            self.cancelled.emit()
        except Exception:
            self.failed.emit(traceback.format_exc())
        else:
            self.finished.emit(res)

    def cancel(self):
        self._cancel.set()

    def wait(self, timeout=None):
        if self._thread is not None:
            self._thread.join(timeout)
        return not self.running
