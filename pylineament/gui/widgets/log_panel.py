import html
import time

from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QHBoxLayout, QPushButton, QTextEdit, QVBoxLayout, QWidget

COLORS = {'info': None, 'ok': '#2e7d32', 'warn': '#b26a00', 'error': '#c62828'}


class LogPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.text = QTextEdit()
        self.text.setReadOnly(True)
        self.text.setFont(QFont('Consolas', 9))
        clear = QPushButton('Clear')
        clear.clicked.connect(self.text.clear)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(clear)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.addWidget(self.text)
        lay.addLayout(row)

    def log(self, msg, level='info'):
        stamp = time.strftime('%H:%M:%S')
        body = html.escape(str(msg)).replace('\n', '<br>').replace('  ', '&nbsp;&nbsp;')
        color = COLORS.get(level)
        if color:
            body = f'<span style="color:{color}">{body}</span>'
        self.text.append(f'<span style="color:#888">{stamp}</span> {body}')
        sb = self.text.verticalScrollBar()
        sb.setValue(sb.maximum())
