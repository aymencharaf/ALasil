"""شاشة البيع بالجملة."""
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QScrollArea, QGridLayout, QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QFrame, QDialog, QDoubleSpinBox,
)

import database as db
import receipt as receipt_mod

ROOT = Path(__file__).resolve().parent


class _Qty(QDialog):
    def __init__(self, name, price, unit, minimum, parent=None):
        super().__init__(parent)
        self.setWindowTitle("كمية الجملة")
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(f"{name}\nسعر الجملة: {price:.2f} د.ج / {unit}\nالحد الأدنى: {minimum}"))
        self.spin = QDoubleSpinBox()
        self.spin.setRange(minimum, 1e7)
        self.spin.setValue(minimum)
        self.spin.setDecimals(3)
        self.spin.setSuffix(" " + unit)
        lay.addWidget(self.spin)
        ok = QPushButton("أضف")
        ok.setObjectName("addBtn")
        ok.clicked.connect(self.accept)
        lay.addWidget(ok)


class WholesalePage(QWidget):
    def __init__(self, main):
        super().__init__()
        self.main = main
        self.cart = []
        self.cat_id = 1
        root = QHBoxLayout(self)
        left = QVBoxLayout()
        title = QLabel("البيع بالجملة — أسعار خاصة وكمية دنيا")
        title.setObjectName("pageTitle")
        left.addWidget(title)
        self.search = QLineEdit()
        self.search.setObjectName("search")
        self.search.setPlaceholderText("بحث جملة / باركود...")
        self.search.textChanged.connect(self.reload)
        left.addWidget(self.search)
        self.cat_row = QHBoxLayout()
        left.addLayout(self.cat_row)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.host = QWidget()
        self.grid = QGridLayout(self.host)
        scroll.setWidget(self.host)
        left.addWidget(scroll, 1)
        root.addLayout(left, 1)

        cart = QWidget()
        cart.setObjectName("cartPanel")
        cart.setMinimumWidth(240)
        cart.setMaximumWidth(520)
        cl = QVBoxLayout(cart)
        head = QLabel("سلة الجملة")
        head.setObjectName("cartTitle")
        cl.addWidget(head)
        self.tbl = QTableWidget(0, 4)
        self.tbl.setHorizontalHeaderLabels(["صنف", "ك", "سعر", "مجموع"])
        self.tbl.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        cl.addWidget(self.tbl)
        self.tot = QLabel("0.00 د.ج")
        self.tot.setObjectName("totalBig")
        cl.addWidget(self.tot)
        pay = QPushButton("✓  إتمام بيع جملة")
        pay.setObjectName("payBtn")
        pay.clicked.connect(self.checkout)
        cl.addWidget(pay)
        clr = QPushButton("إلغاء السلة")
        clr.setObjectName("clearBtn")
        clr.clicked.connect(self.clear)
        cl.addWidget(clr)
        root.addWidget(cart, 0)
        self.rebuild_cats()
        self.reload()

    def rebuild_cats(self):
        while self.cat_row.count():
            w = self.cat_row.takeAt(0).widget()
            if w:
                w.deleteLater()
        for c in db.fetch_categories():
            b = QPushButton(c["name_ar"])
            on = c["id"] == self.cat_id
            b.setStyleSheet(
                "background:#2ea44f;color:white;border:1px solid #1f2328;border-radius:4px;padding:8px;font-weight:800;"
                if on else
                "background:#3d434c;color:#e8edf5;border:1px solid #1f2328;border-radius:4px;padding:8px;font-weight:800;"
            )
            b.clicked.connect(lambda _, i=c["id"]: self.set_cat(i))
            self.cat_row.addWidget(b)
        self.cat_row.addStretch()

    def set_cat(self, i):
        self.cat_id = i
        self.rebuild_cats()
        self.reload()

    def _price(self, p):
        wp = p.get("wholesale_price") or 0
        return float(wp) if wp else round(float(p["price"]) * 0.85, 2)

    def reload(self):
        while self.grid.count():
            w = self.grid.takeAt(0).widget()
            if w:
                w.deleteLater()
        items = [
            p for p in db.fetch_products(self.cat_id, self.search.text())
            if float(p.get("wholesale_price") or 0) > 0
        ]
        for i, p in enumerate(items):
            self.grid.addWidget(self._card(p), i // 4, i % 4)

    def _card(self, p):
        f = QFrame()
        f.setObjectName("productCard")
        f.setFixedSize(180, 230)
        v = QVBoxLayout(f)
        img = QLabel()
        img.setAlignment(Qt.AlignCenter)
        img.setFixedHeight(90)
        path = ROOT / "assets" / (p.get("image") or "")
        if p.get("image") and path.exists():
            img.setPixmap(QPixmap(str(path)).scaled(140, 85, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            img.setText(p.get("emoji") or "📦")
            img.setStyleSheet("font-size:40px;")
        v.addWidget(img)
        n = QLabel(p["name_ar"])
        n.setObjectName("pName")
        n.setAlignment(Qt.AlignCenter)
        n.setWordWrap(True)
        v.addWidget(n)
        wp = self._price(p)
        mn = float(p.get("wholesale_min") or 5)
        wu = p.get("wholesale_unit") or p.get("unit") or ""
        pr = QLabel(f"جملة {wp:.2f} د.ج / {wu}\nمن {mn:g}")
        pr.setObjectName("pPrice")
        pr.setAlignment(Qt.AlignCenter)
        v.addWidget(pr)
        add = QPushButton("إضافة جملة")
        add.setObjectName("addBtn")
        add.clicked.connect(lambda _, x=p: self.add(x))
        v.addWidget(add)
        return f

    def add(self, product):
        mn = float(product.get("wholesale_min") or 5)
        wp = self._price(product)
        dlg = _Qty(product["name_ar"], wp, product.get("unit") or "قطعة", mn, self)
        if dlg.exec() != QDialog.Accepted:
            return
        qty = float(dlg.spin.value())
        for it in self.cart:
            if it["id"] == product["id"]:
                it["qty"] += qty
                self.refresh()
                return
        self.cart.append({
            "id": product["id"], "name": product["name_ar"], "price": wp,
            "qty": qty, "unit": product.get("unit") or "قطعة",
        })
        self.refresh()

    def refresh(self):
        self.tbl.setRowCount(len(self.cart))
        tot = 0
        for i, it in enumerate(self.cart):
            line = it["price"] * it["qty"]
            tot += line
            self.tbl.setItem(i, 0, QTableWidgetItem(it["name"]))
            self.tbl.setItem(i, 1, QTableWidgetItem(str(it["qty"])))
            self.tbl.setItem(i, 2, QTableWidgetItem(f"{it['price']:.2f}"))
            self.tbl.setItem(i, 3, QTableWidgetItem(f"{line:.2f}"))
        tax = tot * db.tax_rate()
        self.tot.setText(f"{tot + tax:,.2f} د.ج")

    def clear(self):
        self.cart = []
        self.refresh()

    def checkout(self):
        if not self.cart:
            QMessageBox.information(self, "جملة", "السلة فارغة")
            return
        from main import PayDialog
        sub = sum(i["price"] * i["qty"] for i in self.cart)
        tax = sub * db.tax_rate()
        total = sub + tax
        dlg = PayDialog(total, self.main.lang, self, self.main.current_customer)
        if dlg.exec() != QDialog.Accepted:
            return
        paid, method = dlg.values()
        if method != "credit" and paid + 0.001 < total:
            QMessageBox.warning(self, "جملة", "المبلغ غير كافٍ")
            return
        change = 0.0 if method == "credit" else paid - total
        if method == "credit":
            paid = 0.0
        cid = self.main.current_customer["id"] if self.main.current_customer else None
        try:
            inv = db.save_sale(
                self.main.user["id"], self.cart, sub, 0, tax, total, paid, change, method, "wholesale",
                customer_id=cid,
            )
        except ValueError as e:
            QMessageBox.warning(self, "جملة", str(e))
            return
        if method == "credit" and self.main.current_customer:
            sale, _ = db.get_sale_by_invoice(inv)
            db.add_debt(self.main.current_customer["id"], total, f"جملة {inv}", sale["id"] if sale else None)
        QMessageBox.information(self, "جملة", f"تم بيع الجملة\n{inv}")
        sale, items = db.get_sale_by_invoice(inv)
        receipt_mod.show_and_print(self, sale, items, self.main.user["display_name"], self.main.lang)
        self.clear()
        self.main.refresh_products()
        self.main.refresh_stats()
        self.main.reload_sales_table()
        self.reload()
