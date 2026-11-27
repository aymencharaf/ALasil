"""حاسبة نقطة البيع."""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QDialog, QVBoxLayout, QGridLayout, QPushButton, QLabel, QWidget


class Calculator(QDialog):
    result_ready = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("حاسبة — ALASIL")
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        self.setMinimumSize(320, 440)
        self.setLayoutDirection(Qt.LeftToRight)
        self._acc = None
        self._op = None
        self._fresh = True
        self._text = "0"

        self.setStyleSheet("""
            QDialog { background: #071a4a; }
            QLabel#disp {
              background: #061433; color: #ffffff; border-radius: 14px;
              padding: 16px; font-size: 28px; font-weight: 800;
            }
            QPushButton#k {
              background: rgba(255,255,255,0.12); color: white; border: none;
              border-radius: 12px; font-size: 20px; font-weight: 800; min-height: 52px;
            }
            QPushButton#k:hover { background: rgba(255,255,255,0.22); }
            QPushButton#op { background: #1e5cff; color: white; border: none; border-radius: 12px; font-size: 20px; font-weight: 800; min-height: 52px; }
            QPushButton#eq { background: #22c55e; color: white; border: none; border-radius: 12px; font-size: 20px; font-weight: 800; min-height: 52px; }
            QPushButton#cl { background: #ef4444; color: white; border: none; border-radius: 12px; font-size: 18px; font-weight: 800; min-height: 52px; }
        """)

        lay = QVBoxLayout(self)
        self.disp = QLabel("0")
        self.disp.setObjectName("disp")
        self.disp.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.disp.setMinimumHeight(72)
        lay.addWidget(self.disp)

        grid = QGridLayout()
        grid.setSpacing(8)
        keys = [
            ("C", 0, 0, "cl"), ("CE", 0, 1, "cl"), ("%", 0, 2, "op"), ("÷", 0, 3, "op"),
            ("7", 1, 0, "k"), ("8", 1, 1, "k"), ("9", 1, 2, "k"), ("×", 1, 3, "op"),
            ("4", 2, 0, "k"), ("5", 2, 1, "k"), ("6", 2, 2, "k"), ("−", 2, 3, "op"),
            ("1", 3, 0, "k"), ("2", 3, 1, "k"), ("3", 3, 2, "k"), ("+", 3, 3, "op"),
            ("0", 4, 0, "k"), (".", 4, 1, "k"), ("±", 4, 2, "k"), ("=", 4, 3, "eq"),
        ]
        for lab, r, c, kind in keys:
            b = QPushButton(lab)
            b.setObjectName(kind)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _, x=lab: self.press(x))
            grid.addWidget(b, r, c)
        lay.addLayout(grid)
        hint = QLabel("F8 لفتح الحاسبة  •  يمكنك الكتابة من لوحة المفاتيح")
        hint.setStyleSheet("color:#9bb4e8;font-size:11px;")
        hint.setAlignment(Qt.AlignCenter)
        lay.addWidget(hint)

    def _show(self):
        t = self._text
        if len(t) > 16:
            t = t[:16]
        self.disp.setText(t)

    def _num(self):
        try:
            return Decimal(self._text)
        except InvalidOperation:
            return Decimal("0")

    def _apply(self):
        if self._acc is None or self._op is None:
            self._acc = self._num()
            return
        a, b = self._acc, self._num()
        try:
            if self._op == "+":
                a = a + b
            elif self._op == "−":
                a = a - b
            elif self._op == "×":
                a = a * b
            elif self._op == "÷":
                a = a / b if b != 0 else Decimal("0")
        except InvalidOperation:
            a = Decimal("0")
        a = a.quantize(Decimal("0.0000001"), rounding=ROUND_HALF_UP)
        self._acc = a
        s = format(a, "f").rstrip("0").rstrip(".")
        self._text = s if s else "0"

    def press(self, k):
        if k in "0123456789":
            if self._fresh or self._text == "0":
                self._text = k
            else:
                self._text += k
            self._fresh = False
        elif k == ".":
            if self._fresh:
                self._text = "0."
                self._fresh = False
            elif "." not in self._text:
                self._text += "."
        elif k == "C":
            self._acc = None
            self._op = None
            self._text = "0"
            self._fresh = True
        elif k == "CE":
            self._text = "0"
            self._fresh = True
        elif k == "±":
            if self._text.startswith("-"):
                self._text = self._text[1:]
            elif self._text != "0":
                self._text = "-" + self._text
        elif k == "%":
            v = self._num() / Decimal("100")
            self._text = format(v, "f").rstrip("0").rstrip(".") or "0"
        elif k in ("+", "−", "×", "÷"):
            self._apply()
            self._op = k
            self._fresh = True
            self._text = format(self._acc, "f").rstrip("0").rstrip(".") or "0"
        elif k == "=":
            self._apply()
            self._op = None
            self._fresh = True
            try:
                self.result_ready.emit(float(self._acc or 0))
            except Exception:
                pass
        self._show()

    def keyPressEvent(self, e):
        m = {
            Qt.Key_0: "0", Qt.Key_1: "1", Qt.Key_2: "2", Qt.Key_3: "3", Qt.Key_4: "4",
            Qt.Key_5: "5", Qt.Key_6: "6", Qt.Key_7: "7", Qt.Key_8: "8", Qt.Key_9: "9",
            Qt.Key_Plus: "+", Qt.Key_Minus: "−", Qt.Key_Asterisk: "×", Qt.Key_Slash: "÷",
            Qt.Key_Enter: "=", Qt.Key_Return: "=", Qt.Key_Period: ".", Qt.Key_Comma: ".",
            Qt.Key_Escape: "C", Qt.Key_Backspace: "CE", Qt.Key_Percent: "%",
        }
        if e.key() in m:
            self.press(m[e.key()])
        else:
            super().keyPressEvent(e)
