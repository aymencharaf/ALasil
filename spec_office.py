"""مكتب صور الاختصاصات."""
from pathlib import Path
import shutil
from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QColor
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QWidget, QGridLayout, QFileDialog, QMessageBox, QFrame, QLineEdit,
)

import database as db

ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"
SPECDIR = ASSETS / "specs"
SPECDIR.mkdir(parents=True, exist_ok=True)


def resolve_img(path: str) -> Path:
    p = Path(path)
    if p.is_file():
        return p
    for cand in (ASSETS / path, SPECDIR / path, ROOT / path):
        if cand.is_file():
            return cand
    return ASSETS / path


class PhotoOffice(QDialog):
    def __init__(self, spec, parent=None):
        super().__init__(parent)
        self.spec = spec
        self.setWindowTitle(f"مكتب الصور — {spec['name_ar']}")
        self.resize(920, 620)
        lay = QVBoxLayout(self)
        head = QHBoxLayout()
        t = QLabel(f"{spec.get('emoji','')}  مكتب صور اختصاص: {spec['name_ar']}")
        t.setStyleSheet("font-size:18px;font-weight:800;color:#0d3480;")
        add = QPushButton("+ إضافة صور")
        add.setStyleSheet("background:#1e5cff;color:white;border:none;border-radius:10px;padding:8px 14px;font-weight:700;")
        add.clicked.connect(self.add_photos)
        head.addWidget(t); head.addStretch(); head.addWidget(add)
        lay.addLayout(head)
        hint = QLabel("اختر صورة كغلاف، أو احذفها. الملفات تُحفظ داخل assets/specs.")
        hint.setStyleSheet("color:#64748b;")
        lay.addWidget(hint)
        self.scroll = QScrollArea(); self.scroll.setWidgetResizable(True)
        self.host = QWidget()
        self.grid = QGridLayout(self.host)
        self.scroll.setWidget(self.host)
        lay.addWidget(self.scroll)
        self.reload()

    def reload(self):
        while self.grid.count():
            w = self.grid.takeAt(0).widget()
            if w:
                w.deleteLater()
        imgs = db.spec_images(self.spec["id"])
        if not imgs:
            empty = QLabel("لا توجد صور بعد — أضف صوراً من الزر أعلاه")
            empty.setAlignment(Qt.AlignCenter)
            self.grid.addWidget(empty, 0, 0)
            return
        cols = 4
        for i, im in enumerate(imgs):
            self.grid.addWidget(self._card(im), i // cols, i % cols)

    def _card(self, im):
        f = QFrame()
        f.setStyleSheet("QFrame{background:white;border-radius:14px;border:1px solid #e8eef6;}")
        v = QVBoxLayout(f)
        lab = QLabel(); lab.setAlignment(Qt.AlignCenter); lab.setFixedHeight(140)
        pix_path = resolve_img(im["path"])
        if pix_path.is_file():
            lab.setPixmap(QPixmap(str(pix_path)).scaled(180, 130, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            lab.setText("لا صورة")
        v.addWidget(lab)
        v.addWidget(QLabel(im.get("title") or im["path"]))
        r = QHBoxLayout()
        cov = QPushButton("غلاف")
        cov.clicked.connect(lambda: self.set_cover(im["path"]))
        rm = QPushButton("حذف")
        rm.setStyleSheet("color:#b91c1c;")
        rm.clicked.connect(lambda: self.remove(im["id"]))
        r.addWidget(cov); r.addWidget(rm)
        v.addLayout(r)
        return f

    def add_photos(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "اختر صوراً للاختصاص", str(ASSETS),
            "صور (*.png *.jpg *.jpeg *.webp *.bmp)",
        )
        dest = SPECDIR / str(self.spec["id"])
        dest.mkdir(parents=True, exist_ok=True)
        for src in files:
            srcp = Path(src)
            name = datetime.now().strftime("%H%M%S_") + srcp.name
            target = dest / name
            shutil.copy2(srcp, target)
            rel = str(target.relative_to(ROOT)).replace("\\", "/")
            db.add_spec_image(self.spec["id"], rel, srcp.stem)
        if files:
            self.reload()

    def set_cover(self, path):
        db.set_spec_cover(self.spec["id"], path)
        QMessageBox.information(self, "ALASIL", "تم تعيين صورة الغلاف")
        self.spec = db.get_spec(self.spec["id"])

    def remove(self, iid):
        if QMessageBox.question(self, "حذف", "حذف هذه الصورة من المكتب؟") != QMessageBox.Yes:
            return
        db.delete_spec_image(iid)
        self.reload()
