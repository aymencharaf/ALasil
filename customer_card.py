"""بطاقة أمان للعميل مع QR."""
from pathlib import Path

from PySide6.QtCore import Qt, QRect, QRectF
from PySide6.QtGui import (
    QPainter, QColor, QFont, QLinearGradient, QPixmap, QPen, QPainterPath, QImage,
)
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QHBoxLayout, QFileDialog
from PySide6.QtPrintSupport import QPrinter, QPrintDialog

import qrlib
import database as db

CARDS = Path(__file__).resolve().parent / "cards"
CARDS.mkdir(exist_ok=True)

W, H = 1012, 638  # نسبة بطاقة ائتمان تقريباً


def render_card(customer: dict) -> QPixmap:
    pm = QPixmap(W, H)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)

    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, W, H), 36, 36)
    g = QLinearGradient(0, 0, W, H)
    g.setColorAt(0, QColor("#071a4a"))
    g.setColorAt(0.45, QColor("#0d3480"))
    g.setColorAt(1, QColor("#1e5cff"))
    p.fillPath(path, g)

    # شريحة ذهبية
    chip = QPainterPath()
    chip.addRoundedRect(QRectF(56, 168, 92, 70), 8, 8)
    p.fillPath(chip, QColor("#e8c872"))
    p.setPen(QPen(QColor("#c9a227"), 2))
    p.drawRoundedRect(QRectF(70, 180, 64, 46), 4, 4)

    p.setPen(QColor("white"))
    p.setFont(QFont("Segoe UI", 22, QFont.Black))
    p.drawText(56, 70, "ALASIL POS")
    p.setFont(QFont("Tahoma", 12))
    p.setPen(QColor("#b8c9f0"))
    p.drawText(56, 100, "بطاقة عميل يَدين  •  CREDIT CUSTOMER")

    p.setPen(QColor("#7ea0e0"))
    p.setFont(QFont("Consolas", 16, QFont.Bold))
    p.drawText(56, 140, customer.get("code") or "")

    p.setPen(QColor("white"))
    p.setFont(QFont("Tahoma", 26, QFont.Bold))
    p.drawText(56, 290, customer.get("name") or "")

    p.setFont(QFont("Tahoma", 13))
    p.setPen(QColor("#dbe7ff"))
    lines = [
        f"الهاتف: {customer.get('phone') or '—'}",
        f"رقم التعريف: {customer.get('national_id') or '—'}",
        f"العنوان: {customer.get('address') or '—'}  —  {customer.get('city') or ''}",
        f"سقف الدين: {float(customer.get('credit_limit') or 0):,.0f} د.ج",
        f"الدين الحالي: {float(customer.get('debt') or 0):,.0f} د.ج",
    ]
    y = 330
    for ln in lines:
        p.drawText(56, y, ln)
        y += 32

    p.setFont(QFont("Tahoma", 10))
    p.setPen(QColor("#9bb4e8"))
    p.drawText(56, H - 36, db.get_setting("store_name", "ALASIL") + "  •  " + db.get_setting("store_city", ""))

    payload = db.customer_payload(customer)
    qimg = qrlib.qr_image(payload, scale=6, border=2)
    qr = QPixmap.fromImage(qimg)
    box = 260
    qr = qr.scaled(box, box, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    p.fillRect(W - box - 70, 90, box + 24, box + 70, QColor(255, 255, 255, 230))
    p.drawPixmap(W - box - 58, 102, qr)
    p.setPen(QColor("#0d3480"))
    p.setFont(QFont("Tahoma", 10, QFont.Bold))
    p.drawText(QRect(W - box - 70, 90 + box + 28, box + 24, 28), Qt.AlignCenter, "امسح للتحقق")

    p.end()
    return pm


class CardDialog(QDialog):
    def __init__(self, customer, parent=None):
        super().__init__(parent)
        self.customer = customer
        self.setWindowTitle("بطاقة أمان العميل")
        self.pix = render_card(customer)
        lay = QVBoxLayout(self)
        lab = QLabel()
        lab.setPixmap(self.pix.scaled(760, 480, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        lab.setAlignment(Qt.AlignCenter)
        lay.addWidget(lab)
        row = QHBoxLayout()
        s = QPushButton("حفظ صورة PNG")
        s.clicked.connect(self.save)
        pr = QPushButton("طباعة البطاقة")
        pr.clicked.connect(self.print_card)
        row.addWidget(s)
        row.addWidget(pr)
        lay.addLayout(row)

    def save(self):
        path = CARDS / f"{self.customer.get('code')}.png"
        self.pix.save(str(path), "PNG")
        dest, _ = QFileDialog.getSaveFileName(self, "حفظ", str(path), "PNG (*.png)")
        if dest:
            self.pix.save(dest, "PNG")

    def print_card(self):
        printer = QPrinter(QPrinter.HighResolution)
        dlg = QPrintDialog(printer, self)
        if dlg.exec() == QPrintDialog.Accepted:
            qp = QPainter(printer)
            r = printer.pageRect(QPrinter.DevicePixel)
            pix = self.pix
            pix = pix.scaled(int(r.width() * 0.9), int(r.height() * 0.5), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            qp.drawPixmap(int(r.x() + 40), int(r.y() + 40), pix)
            qp.end()
