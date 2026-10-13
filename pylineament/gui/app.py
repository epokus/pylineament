import multiprocessing
import sys
import traceback


def _excepthook(window):
    def hook(etype, value, tb):
        text = ''.join(traceback.format_exception(etype, value, tb))
        sys.__stderr__ and sys.__stderr__.write(text)
        try:
            from PyQt5.QtWidgets import QMessageBox
            window.log.log('Unexpected error:\n' + text, 'error')
            QMessageBox.critical(window, 'Unexpected error', f'{etype.__name__}: {value}\n\n'
                                 'Details are in the log panel.')
        except Exception:
            pass
    return hook


def self_test(dem, out_dir):
    """Headless check of a build: preview (process pool) and full run (multiprocessing pool).

    Writes <out_dir>/self_test.json (a windowed exe has no console) and returns an exit code.
    """
    import json
    import os
    from concurrent.futures import ProcessPoolExecutor

    from . import pipeline
    from .params import Params
    from .raster import RasterInfo

    os.makedirs(out_dir, exist_ok=True)
    report = {'ok': False, 'dem': os.path.abspath(dem), 'frozen': bool(getattr(sys, 'frozen', False))}
    try:
        r = RasterInfo(dem)
        p = Params(n_jobs=2).to_dict()
        ctx = multiprocessing.get_context('spawn')
        with ProcessPoolExecutor(max_workers=1, mp_context=ctx) as ex:
            prev = ex.submit(pipeline.preview_tile, r.path, r.tiles(p['split_size'])[0], p,
                             out_dir).result()
        res = pipeline.run_extraction(r.path, p, os.path.join(out_dir, 'self_test.shp'), r.crs_wkt)
        failed = [t['tile'] for t in res['tiles'] if not t['ok']]
        report.update(preview_lines=prev['n_final'], run_lines=len(res['lines']),
                      tiles=len(res['tiles']), failed_tiles=failed, seconds=round(res['seconds'], 1),
                      ok=not failed and len(res['lines']) > 0)
    except Exception:
        report['error'] = traceback.format_exc()
    with open(os.path.join(out_dir, 'self_test.json'), 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2)
    return 0 if report['ok'] else 1


def main(argv=None):
    multiprocessing.freeze_support()  # required for worker processes in a PyInstaller build
    argv = sys.argv if argv is None else argv
    if len(argv) == 4 and argv[1] == '--self-test':
        return self_test(argv[2], argv[3])

    from PyQt5.QtCore import Qt
    from PyQt5.QtWidgets import QApplication
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication(argv)
    app.setApplicationName('Pylineament')
    app.setOrganizationName('pylineament')
    app.setStyle('Fusion')

    from .main_window import MainWindow
    win = MainWindow()
    sys.excepthook = _excepthook(win)
    win.show()
    if len(argv) > 1:
        win.open_raster(argv[1])
    return app.exec_()


if __name__ == '__main__':
    sys.exit(main())
