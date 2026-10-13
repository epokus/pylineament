"""Pylineament graphical user interface.

Kept import-light: worker processes import ``pylineament.gui.pipeline`` and must not load Qt.
"""


def main():
    from .app import main as _main
    return _main()
