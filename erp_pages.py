"""أقسام الإدارة: مشتريات، موردون، مصاريف، صندوق، مخزون، موظفون، أرباح، نسخ، تقارير، أمان."""
from datetime import datetime
from pathlib import Path
import shutil

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QListWidget,
    QStackedWidget, QTableWidget, QTableWidgetItem, QHeaderView, QFormLayout,
    QLineEdit, QDoubleSpinBox, QComboBox, QMessageBox, QDialog, QFileDialog,
    QSpinBox, QTextEdit, QCheckBox, QScrollArea,
)

import database as db

ROOT = Path(__file__).resolve().parent
BACKUPS = ROOT / "backups"
BACKUPS.mkdir(exist_ok=True)
TBL = "QTableWidget{background:#2b2f36;color:#dce3ec;border:1px solid #3d434c;} QHeaderView::section{color:#c5ccd6;background:#32363e;padding:6px;}"


def _table(cols, headers):
    t = QTableWidget(0, cols)
    t.setHorizontalHeaderLabels(headers)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    t.setStyleSheet(TBL)
    return t


def _fill(t, rows, keys):
    t.setRowCount(len(rows))
    for i, r in enumerate(rows):
        for c, k in enumerate(keys):
            t.setItem(i, c, QTableWidgetItem(str(r.get(k, "") if not isinstance(k, tuple) else k[1](r))))


class AdminHub(QWidget):
    def __init__(self, main):
        super().__init__()
        self.main = main
        lay = QHBoxLayout(self)
        self.menu = QListWidget()
        self.menu.setMinimumWidth(140)
        self.menu.setMaximumWidth(260)
        self.menu.setStyleSheet("QListWidget{background:#1f2328;color:#e8edf5;border:1px solid #3d434c;font-weight:700;padding:8px;} QListWidget::item{padding:10px;} QListWidget::item:selected{background:#2c5282;}")
        items = [
            "1. المشتريات", "2. الموردون", "3. المصاريف", "4. الصندوق",
            "5. المخزون المتقدم", "6. الموظفون", "7. الأرباح",
            "8. النسخ الاحتياطي", "9. التقارير المتقدمة", "10. الأمان",
            "11. الزكاة",
        ]
        for x in items:
            self.menu.addItem(x)
        lay.addWidget(self.menu)
        self.stack = QStackedWidget()
        lay.addWidget(self.stack, 1)
        self.stack.addWidget(self._purchases())
        self.stack.addWidget(self._suppliers())
        self.stack.addWidget(self._expenses())
        self.stack.addWidget(self._cash())
        self.stack.addWidget(self._stock())
        self.stack.addWidget(self._users())
        self.stack.addWidget(self._profit())
        self.stack.addWidget(self._backup())
        self.stack.addWidget(self._reports())
        self.stack.addWidget(self._security())
        self.stack.addWidget(self._zakat())
        self.menu.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.menu.setCurrentRow(0)

    def refresh_all(self):
        self.reload_pur()
        self.reload_sup()
        self.reload_exp()
        self.reload_cash()
        self.reload_stk()
        self.reload_usr()
        self.reload_profit()
        self.reload_bak()
        self.reload_rep()
        self.reload_sec()
        if hasattr(self, "zk_lbl"):
            self.reload_zakat()

    # --- purchases ---
    def _purchases(self):
        w = QWidget(); v = QVBoxLayout(w)
        v.addWidget(QLabel("فواتير الشراء — تزيد المخزون وتحدّث التكلفة"))
        btn = QPushButton("+ فاتورة شراء")
        btn.setStyleSheet("background:#1e5cff;color:white;padding:8px;border-radius:10px;font-weight:800;")
        btn.clicked.connect(self.new_purchase)
        v.addWidget(btn)
        self.pur_t = _table(6, ["فاتورة", "مورد", "تاريخ", "الإجمالي", "مدفوع", "حالة"])
        v.addWidget(self.pur_t)
        self.reload_pur()
        return w

    def reload_pur(self):
        rows = db.list_purchases()
        self.pur_t.setRowCount(len(rows))
        for i, r in enumerate(rows):
            for c, k in enumerate(["invoice_no", "supplier", "created_at", "total", "paid", "status"]):
                self.pur_t.setItem(i, c, QTableWidgetItem(str(r.get(k) or "")))

    def new_purchase(self):
        dlg = QDialog(self); dlg.setWindowTitle("شراء"); dlg.setMinimumWidth(480)
        f = QFormLayout(dlg)
        sup = QComboBox()
        for s in db.list_suppliers():
            sup.addItem(s["name"], s["id"])
        prod = QComboBox()
        for p in db.all_products():
            prod.addItem(f"{p['name_ar']} (مخزون {p['stock']})", p)
        qty = QDoubleSpinBox(); qty.setRange(0.001, 1e7); qty.setValue(1)
        cost = QDoubleSpinBox(); cost.setRange(0, 1e9)
        paid = QDoubleSpinBox(); paid.setRange(0, 1e9)
        items = []
        lst = QLabel("لا أصناف")
        def add_line():
            p = prod.currentData()
            if not p:
                return
            items.append({"id": p["id"], "name": p["name_ar"], "qty": qty.value(), "cost": cost.value()})
            lst.setText("\n".join(f"{i['name']} × {i['qty']} @ {i['cost']}" for i in items))
        addb = QPushButton("أضف للصنف")
        addb.clicked.connect(add_line)
        save = QPushButton("حفظ الفاتورة")
        def go():
            if not items:
                return
            db.save_purchase(sup.currentData(), items, paid.value())
            dlg.accept()
            self.reload_pur()
            self.main.refresh_products()
            self.main.refresh_stats()
            QMessageBox.information(self, "ALASIL", "تم استلام الشراء وتحديث المخزون")
        save.clicked.connect(go)
        f.addRow("المورد", sup)
        f.addRow("منتج", prod)
        f.addRow("كمية", qty)
        f.addRow("تكلفة الوحدة", cost)
        f.addRow(addb)
        f.addRow(lst)
        f.addRow("المدفوع الآن", paid)
        f.addRow(save)
        dlg.exec()

    # --- suppliers ---
    def _suppliers(self):
        w = QWidget(); v = QVBoxLayout(w)
        v.addWidget(QLabel("الموردون — الديون والمدفوعات"))
        add = QPushButton("+ مورد")
        add.clicked.connect(self.edit_sup)
        v.addWidget(add)
        self.sup_t = _table(5, ["الاسم", "هاتف", "عنوان", "دين", ""])
        v.addWidget(self.sup_t)
        self.reload_sup()
        return w

    def reload_sup(self):
        rows = db.list_suppliers()
        self.sup_t.setRowCount(len(rows))
        for i, r in enumerate(rows):
            for c, k in enumerate(["name", "phone", "address", "debt"]):
                self.sup_t.setItem(i, c, QTableWidgetItem(str(r.get(k) or "")))
            b = QPushButton("تسديد")
            b.clicked.connect(lambda _, x=r: self.pay_sup(x))
            self.sup_t.setCellWidget(i, 4, b)

    def edit_sup(self):
        dlg = QDialog(self); f = QFormLayout(dlg)
        n, p, a = QLineEdit(), QLineEdit(), QLineEdit()
        f.addRow("الاسم", n); f.addRow("هاتف", p); f.addRow("عنوان", a)
        s = QPushButton("حفظ")
        s.clicked.connect(lambda: (db.upsert_supplier({"name": n.text(), "phone": p.text(), "address": a.text()}), dlg.accept(), self.reload_sup()))
        f.addRow(s); dlg.exec()

    def pay_sup(self, r):
        dlg = QDialog(self); f = QFormLayout(dlg)
        sp = QDoubleSpinBox(); sp.setRange(0, 1e9); sp.setValue(float(r["debt"] or 0))
        f.addRow(f"دين {r['name']}", sp)
        ok = QPushButton("تأكيد")
        ok.clicked.connect(lambda: (db.add_supplier_pay(r["id"], sp.value()), dlg.accept(), self.reload_sup()))
        f.addRow(ok); dlg.exec()

    # --- expenses ---
    def _expenses(self):
        w = QWidget(); v = QVBoxLayout(w)
        v.addWidget(QLabel("المصاريف: إيجار، كهرباء، نقل، أجور…"))
        row = QHBoxLayout()
        self.ex_cat = QComboBox(); self.ex_cat.addItems(["إيجار", "كهرباء", "ماء", "نقل", "أجور", "صيانة", "أخرى"])
        self.ex_cat.setEditable(True)
        self.ex_amt = QDoubleSpinBox(); self.ex_amt.setRange(0, 1e9)
        self.ex_note = QLineEdit(); self.ex_note.setPlaceholderText("ملاحظة")
        b = QPushButton("تسجيل مصروف")
        b.clicked.connect(self.add_exp)
        row.addWidget(self.ex_cat); row.addWidget(self.ex_amt); row.addWidget(self.ex_note); row.addWidget(b)
        v.addLayout(row)
        self.ex_t = _table(4, ["تاريخ", "نوع", "مبلغ", "ملاحظة"])
        v.addWidget(self.ex_t)
        self.reload_exp()
        return w

    def add_exp(self):
        db.add_expense(self.ex_cat.currentText(), self.ex_amt.value(), self.ex_note.text())
        self.reload_exp()

    def reload_exp(self):
        rows = db.list_expenses()
        self.ex_t.setRowCount(len(rows))
        for i, r in enumerate(rows):
            for c, k in enumerate(["created_at", "category", "amount", "note"]):
                self.ex_t.setItem(i, c, QTableWidgetItem(str(r.get(k) or "")))

    # --- cash ---
    def _cash(self):
        w = QWidget(); v = QVBoxLayout(w)
        self.cash_st = QLabel()
        v.addWidget(self.cash_st)
        row = QHBoxLayout()
        self.cash_open = QDoubleSpinBox(); self.cash_open.setRange(0, 1e9)
        o = QPushButton("فتح الصندوق / الوردية")
        o.clicked.connect(lambda: (db.open_session(self.main.user["id"], self.cash_open.value()), self.reload_cash()))
        c = QPushButton("إغلاق الصندوق")
        c.clicked.connect(lambda: (db.close_session(self.cash_open.value()), self.reload_cash()))
        row.addWidget(QLabel("المبلغ")); row.addWidget(self.cash_open); row.addWidget(o); row.addWidget(c)
        v.addLayout(row)
        row2 = QHBoxLayout()
        self.mv_amt = QDoubleSpinBox(); self.mv_amt.setRange(0, 1e9)
        self.mv_note = QLineEdit(); self.mv_note.setPlaceholderText("بيان الحركة")
        inn = QPushButton("دخل نقدي")
        inn.clicked.connect(lambda: (db.cash_move("in", self.mv_amt.value(), self.mv_note.text(), self.main.user["id"]), self.reload_cash()))
        out = QPushButton("خرج نقدي")
        out.clicked.connect(lambda: (db.cash_move("out", self.mv_amt.value(), self.mv_note.text(), self.main.user["id"]), self.reload_cash()))
        row2.addWidget(self.mv_amt); row2.addWidget(self.mv_note); row2.addWidget(inn); row2.addWidget(out)
        v.addLayout(row2)
        self.cash_t = _table(5, ["#", "فتح", "إغلاق", "افتتاح", "حالة"])
        self.mv_t = _table(4, ["وقت", "نوع", "مبلغ", "ملاحظة"])
        v.addWidget(self.cash_t); v.addWidget(self.mv_t)
        self.reload_cash()
        return w

    def reload_cash(self):
        ses = db.current_session()
        self.cash_st.setText("الوردية مفتوحة: " + ses["opened_at"] if ses else "لا توجد وردية مفتوحة")
        rows = db.list_sessions()
        self.cash_t.setRowCount(len(rows))
        for i, r in enumerate(rows):
            vals = [r["id"], r["opened_at"], r.get("closed_at") or "", r["open_amount"], r["status"]]
            for c, v in enumerate(vals):
                self.cash_t.setItem(i, c, QTableWidgetItem(str(v)))
        mvs = db.list_cash_moves()
        self.mv_t.setRowCount(len(mvs))
        for i, r in enumerate(mvs):
            for c, k in enumerate(["created_at", "kind", "amount", "note"]):
                self.mv_t.setItem(i, c, QTableWidgetItem(str(r.get(k) or "")))

    # --- stock ---
    def _stock(self):
        w = QWidget(); v = QVBoxLayout(w)
        v.addWidget(QLabel("الجرد / التسوية / تنبيه النواقص"))
        row = QHBoxLayout()
        self.st_prod = QComboBox()
        for p in db.all_products():
            self.st_prod.addItem(f"{p['name_ar']} ({p['stock']})", p["id"])
        self.st_qty = QDoubleSpinBox(); self.st_qty.setRange(-1e7, 1e7)
        self.st_note = QLineEdit(); self.st_note.setPlaceholderText("سبب التسوية / الجرد")
        b = QPushButton("تطبيق حركة مخزون")
        b.clicked.connect(lambda: (db.stock_adjust(self.st_prod.currentData(), self.st_qty.value(), self.st_note.text() or "تسوية"), self.reload_stk(), self.main.refresh_products()))
        row.addWidget(self.st_prod); row.addWidget(self.st_qty); row.addWidget(self.st_note); row.addWidget(b)
        v.addLayout(row)
        v.addWidget(QLabel("تنبيه مخزون منخفض"))
        self.low_t = _table(3, ["منتج", "مخزون", "تكلفة"])
        self.mvst = _table(5, ["وقت", "منتج", "نوع", "كمية", "ملاحظة"])
        v.addWidget(self.low_t); v.addWidget(self.mvst)
        self.reload_stk()
        return w

    def reload_stk(self):
        lows = db.low_stock(8)
        self.low_t.setRowCount(len(lows))
        for i, p in enumerate(lows):
            self.low_t.setItem(i, 0, QTableWidgetItem(p["name_ar"]))
            self.low_t.setItem(i, 1, QTableWidgetItem(str(p["stock"])))
            self.low_t.setItem(i, 2, QTableWidgetItem(str(p.get("cost") or 0)))
        mvs = db.list_stock_moves()
        self.mvst.setRowCount(len(mvs))
        for i, r in enumerate(mvs):
            for c, k in enumerate(["created_at", "name_ar", "kind", "qty", "note"]):
                self.mvst.setItem(i, c, QTableWidgetItem(str(r.get(k) or "")))

    PERMS = [
        ("pos", "نقطة البيع"),
        ("wholesale", "الجملة"),
        ("products", "المنتجات"),
        ("cats", "التصنيفات"),
        ("sales", "المبيعات"),
        ("reports", "التقارير"),
        ("customers", "عملاء يَدين"),
        ("specs", "اختصاصات"),
        ("admin", "الإدارة (مشتريات/صندوق/مخزون…)"),
        ("settings", "الإعدادات"),
    ]

    def _users(self):
        w = QWidget(); v = QVBoxLayout(w)
        v.addWidget(QLabel("المدير والموظفون — الصلاحيات التفصيلية"))
        hint = QLabel("المدير يتجاوز كل القيود. الموظف يرى في القائمة فقط ما يُفعَّل له.")
        hint.setStyleSheet("color:#64748b;")
        v.addWidget(hint)
        add = QPushButton("+ موظف جديد")
        add.setStyleSheet("background:#1e5cff;color:white;border:none;border-radius:10px;padding:8px;font-weight:800;")
        add.clicked.connect(lambda: self.edit_user())
        v.addWidget(add)
        self.usr_t = _table(8, ["دخول", "الاسم", "هاتف", "دور", "راتب", "حالة", "صلاحيات", ""])
        v.addWidget(self.usr_t)
        self.reload_usr()
        return w

    def reload_usr(self):
        rows = db.list_users_full()
        self.usr_t.setRowCount(len(rows))
        for i, r in enumerate(rows):
            vals = [
                r.get("username"), r.get("display_name"), r.get("phone") or "",
                "مدير" if r.get("role") == "admin" else "موظف",
                f"{float(r.get('salary') or 0):.0f}",
                "نشط" if r.get("active", 1) else "موقوف",
                r.get("permissions") or "",
            ]
            for c, v in enumerate(vals):
                self.usr_t.setItem(i, c, QTableWidgetItem(str(v)))
            box = QWidget(); h = QHBoxLayout(box); h.setContentsMargins(0, 0, 0, 0)
            e = QPushButton("تعديل")
            e.clicked.connect(lambda _, x=r: self.edit_user(x))
            d = QPushButton("إيقاف")
            d.setEnabled(r.get("role") != "admin")
            d.clicked.connect(lambda _, x=r["id"]: (db.deactivate_user(x), self.reload_usr()))
            h.addWidget(e); h.addWidget(d)
            self.usr_t.setCellWidget(i, 7, box)

    def edit_user(self, user=None):
        dlg = QDialog(self)
        dlg.setWindowTitle("بطاقة موظف / مدير")
        dlg.setMinimumWidth(480)
        f = QFormLayout(dlg)
        u = QLineEdit(user["username"] if user else "")
        n = QLineEdit(user["display_name"] if user else "")
        phone = QLineEdit((user.get("phone") or "") if user else "")
        pin = QLineEdit(); pin.setEchoMode(QLineEdit.Password)
        pin.setPlaceholderText("اتركه فارغاً لعدم التغيير" if user else "كلمة السر")
        role = QComboBox(); role.addItems(["موظف كاشير", "مدير النظام"])
        if user and user.get("role") == "admin":
            role.setCurrentIndex(1)
        sal = QDoubleSpinBox(); sal.setRange(0, 1e9)
        sal.setValue(float(user.get("salary") or 0) if user else 0)
        hire = QLineEdit((user.get("hire_date") or "") if user else "")
        hire.setPlaceholderText("تاريخ التوظيف YYYY-MM-DD")
        active = QCheckBox("الحساب نشط")
        active.setChecked(bool(user.get("active", 1)) if user else True)
        f.addRow("اسم الدخول", u)
        f.addRow("الاسم الظاهر", n)
        f.addRow("الهاتف", phone)
        f.addRow("كلمة السر", pin)
        f.addRow("الصفة", role)
        f.addRow("الراتب", sal)
        f.addRow("تاريخ التوظيف", hire)
        f.addRow(active)
        f.addRow(QLabel("صلاحيات الصفحات:"))
        checks = {}
        current = set()
        if user:
            p = user.get("permissions") or ""
            if p == "all" or user.get("role") == "admin":
                current = {k for k, _ in self.PERMS}
            else:
                current = {x.strip() for x in p.split(",") if x.strip()}
        for key, lab in self.PERMS:
            cb = QCheckBox(lab)
            cb.setChecked(key in current or (not user and key == "pos"))
            checks[key] = cb
            f.addRow(cb)

        def go():
            if not u.text().strip() or not n.text().strip():
                QMessageBox.warning(dlg, "ALASIL", "أدخل اسم الدخول والاسم الظاهر")
                return
            is_admin = role.currentIndex() == 1
            perms = "all" if is_admin else ",".join(k for k, c in checks.items() if c.isChecked()) or "pos"
            data = {
                "username": u.text().strip(),
                "display_name": n.text().strip(),
                "password": pin.text().strip(),
                "role": "admin" if is_admin else "cashier",
                "permissions": perms,
                "phone": phone.text().strip(),
                "salary": sal.value(),
                "active": 1 if active.isChecked() else 0,
                "hire_date": hire.text().strip(),
            }
            db.upsert_user(data, user["id"] if user else None)
            dlg.accept()
            self.reload_usr()
            if hasattr(self.main, "rebuild_nav_menu"):
                self.main.rebuild_nav_menu()
            QMessageBox.information(self, "ALASIL", "تم حفظ الموظف والصلاحيات")

        s = QPushButton("حفظ")
        s.setStyleSheet("background:#22c55e;color:white;padding:10px;border-radius:10px;font-weight:800;")
        s.clicked.connect(go)
        f.addRow(s)
        dlg.exec()

    # --- profit ---
    def _profit(self):
        w = QWidget(); v = QVBoxLayout(w)
        v.addWidget(QLabel("الربح الحقيقي = المبيعات − تكلفة الشراء − المصاريف"))
        row = QHBoxLayout()
        for lab, per in (("اليوم", "day"), ("هذا الشهر", "month"), ("هذه السنة", "year")):
            b = QPushButton(lab)
            b.clicked.connect(lambda _, p=per: self.show_profit(p))
            row.addWidget(b)
        v.addLayout(row)
        self.pr_lbl = QLabel()
        self.pr_lbl.setStyleSheet("background:#32363e;border-radius:4px;padding:16px;color:#e8edf5;font-size:15px;")
        v.addWidget(self.pr_lbl)
        v.addStretch()
        self.reload_profit()
        return w

    def show_profit(self, period):
        r = db.profit_report(period)
        self.pr_lbl.setText(
            f"<b>المبيعات:</b> {r['sales']:,.2f} د.ج<br>"
            f"<b>تكلفة البضاعة:</b> {r['costs']:,.2f}<br>"
            f"<b>مجمل الربح:</b> {r['gross']:,.2f}<br>"
            f"<b>المصاريف:</b> {r['expenses']:,.2f}<br>"
            f"<b>صافي الربح:</b> {r['net']:,.2f} د.ج"
        )

    def reload_profit(self):
        self.show_profit("day")

    # --- backup ---
    def _backup(self):
        w = QWidget(); v = QVBoxLayout(w)
        v.addWidget(QLabel("نسخ احتياطي لقاعدة البيانات واستعادة"))
        b1 = QPushButton("إنشاء نسخة الآن")
        b1.clicked.connect(self.do_backup)
        b2 = QPushButton("استعادة من ملف…")
        b2.clicked.connect(self.do_restore)
        v.addWidget(b1); v.addWidget(b2)
        self.bak_t = _table(2, ["ملف", "حجم"])
        v.addWidget(self.bak_t)
        self.reload_bak()
        return w

    def do_backup(self):
        dest = BACKUPS / f"alasil_{datetime.now():%Y%m%d_%H%M%S}.db"
        try:
            db.backup_db(dest)
            QMessageBox.information(self, "ALASIL", f"تم الحفظ والتحقق:\n{dest}")
        except Exception as e:
            QMessageBox.critical(self, "ALASIL", str(e))
        self.reload_bak()

    def do_restore(self):
        path, _ = QFileDialog.getOpenFileName(self, "استعادة", str(BACKUPS), "DB (*.db)")
        if not path:
            return
        if QMessageBox.question(self, "استعادة", "سيتم استبدال البيانات الحالية. متابعة؟") != QMessageBox.Yes:
            return
        try:
            db.restore_db(path)
            QMessageBox.information(self, "ALASIL", "تمت الاستعادة — أعد تشغيل البرنامج")
        except Exception as e:
            QMessageBox.critical(self, "ALASIL", str(e))

    def reload_bak(self):
        files = sorted(BACKUPS.glob("*.db"), reverse=True)
        self.bak_t.setRowCount(len(files))
        for i, p in enumerate(files):
            self.bak_t.setItem(i, 0, QTableWidgetItem(p.name))
            self.bak_t.setItem(i, 1, QTableWidgetItem(f"{p.stat().st_size/1024:.1f} ك.ب"))

    # --- reports ---
    def _reports(self):
        w = QWidget(); v = QVBoxLayout(w)
        v.addWidget(QLabel("تقارير يومية / شهرية / سنوية"))
        self.rep_box = QTextEdit(); self.rep_box.setReadOnly(True)
        v.addWidget(self.rep_box)
        self.reload_rep()
        return w

    def reload_rep(self):
        lines = []
        for title, p in (("اليوم", "day"), ("الشهر", "month"), ("السنة", "year")):
            r = db.profit_report(p)
            lines.append(f"=== {title} ===\nمبيعات {r['sales']:,.2f} | تكلفة {r['costs']:,.2f} | مصاريف {r['expenses']:,.2f} | صافي {r['net']:,.2f}\n")
        n, s = db.sales_today()
        lines.append(f"فواتير اليوم: {n} — {s:,.2f} د.ج")
        self.rep_box.setPlainText("\n".join(lines))

    # --- security ---
    def _security(self):
        w = QWidget(); v = QVBoxLayout(w)
        v.addWidget(QLabel("الأمان: الترخيص، محاولات الدخول، ربط الجهاز"))
        self.sec_lbl = QLabel()
        self.sec_lbl.setWordWrap(True)
        self.sec_lbl.setStyleSheet("background:#32363e;border-radius:4px;padding:14px;color:#e8edf5;")
        v.addWidget(self.sec_lbl)
        v.addStretch()
        self.reload_sec()
        return w

    def reload_sec(self):
        import license as lic
        rec = lic.current_license()
        fails = db.failed_logins(60)
        txt = f"معرف الجهاز: {lic.machine_id()}\n"
        txt += f"محاولات دخول فاشلة (آخر ساعة): {fails}\n"
        if rec.get("valid") or rec.get("expired") or rec.get("mismatch") or rec.get("tampered"):
            status = "ساري" if rec.get("valid") else "غير ساري"
            customer = rec.get("customer") or rec.get("name") or "—"
            expiry = rec.get("expiry") or "—"
            if rec.get("expired"):
                status = "منتهي الصلاحية"
            elif rec.get("mismatch"):
                status = "غير مطابق للجهاز"
            elif rec.get("tampered"):
                status = "بيانات الترخيص غير سليمة"
            txt += f"العميل: {customer}\n"
            txt += f"حالة الترخيص: {status}\n"
            txt += f"تاريخ الانتهاء: {expiry}\n"
        else:
            txt += "لا ترخيص محفوظ\n"
        txt += "حماية الترخيص: Ed25519 — المفتاح الخاص محفوظ لدى صاحب البرنامج."
        self.sec_lbl.setText(txt)

    def _zakat(self):
        w = QWidget()
        v = QVBoxLayout(w)
        t = QLabel("حساب الزكاة تلقائياً (عروض التجارة 2.5٪)")
        t.setObjectName("pageTitle")
        v.addWidget(t)
        note = QLabel(
            "الأصل الزكوي = قيمة المخزون + النقد في الصندوق + ديون العملاء − ديون الموردين.\n"
            "النصاب ≈ 85 غراماً من الذهب. إذا بلغ الأصل النصاب وحال عليه الحول تُخرج 2.5٪.\n"
            "هذا تقدير محاسبي؛ راجع أهل العلم لفتواك."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color:#475569;")
        v.addWidget(note)
        form = QFormLayout()
        self.zk_gold = QDoubleSpinBox()
        self.zk_gold.setRange(0, 1e7)
        self.zk_gold.setSuffix(" د.ج / غرام")
        try:
            self.zk_gold.setValue(float(db.get_setting("zakat_gold_gram", "15000") or 15000))
        except Exception:
            self.zk_gold.setValue(15000)
        self.zk_cash = QDoubleSpinBox()
        self.zk_cash.setRange(0, 1e12)
        self.zk_cash.setSuffix(" د.ج")
        self.zk_sale = QCheckBox("تقييم المخزون بسعر البيع بدل التكلفة")
        form.addRow("سعر غرام الذهب", self.zk_gold)
        form.addRow("نقد إضافي (خزنة/بنك) غير الصندوق", self.zk_cash)
        form.addRow(self.zk_sale)
        v.addLayout(form)
        calc = QPushButton("احتساب الزكاة الآن")
        calc.setStyleSheet("background:#1e5cff;color:white;border:none;border-radius:10px;padding:10px;font-weight:800;")
        calc.clicked.connect(self.reload_zakat)
        v.addWidget(calc)
        self.zk_lbl = QLabel()
        self.zk_lbl.setWordWrap(True)
        self.zk_lbl.setStyleSheet("background:#32363e;border-radius:4px;padding:16px;color:#e8edf5;font-size:15px;")
        v.addWidget(self.zk_lbl)
        pay = QPushButton("تسجيل إخراج الزكاة كمصروف")
        pay.clicked.connect(self.pay_zakat)
        v.addWidget(pay)
        v.addStretch()
        self.reload_zakat()
        return w

    def reload_zakat(self):
        if not hasattr(self, "zk_lbl"):
            return
        gold = self.zk_gold.value()
        db.set_setting("zakat_gold_gram", str(gold))
        r = db.zakat_calc(gold, self.zk_cash.value(), self.zk_sale.isChecked())
        status = (
            f"<span style='color:#15803d;font-weight:800'>تجب الزكاة: {r['zakat']:,.2f} د.ج</span>"
            if r["due"]
            else "<span style='color:#b45309;font-weight:800'>لم يبلغ النصاب — لا زكاة على هذا التقدير</span>"
        )
        self.zk_lbl.setText(
            f"{status}<br><br>"
            f"المخزون: {r['inventory']:,.2f} د.ج<br>"
            f"النقد (صندوق + إضافي): {r['cash']:,.2f}<br>"
            f"ديون العملاء (لك): {r['receivables']:,.2f}<br>"
            f"ديون الموردين (عليك): {r['payables']:,.2f}<br>"
            f"<b>وعاء الزكاة:</b> {r['base']:,.2f} د.ج<br>"
            f"النصاب (85غ × سعر الذهب): {r['nisab']:,.2f} د.ج<br>"
            f"النسبة: 2.5٪<br>"
            f"<b style='font-size:20px'>المبلغ المستحق: {r['zakat']:,.2f} د.ج</b>"
        )
        self._last_zakat = r["zakat"]

    def pay_zakat(self):
        amt = getattr(self, "_last_zakat", 0) or 0
        if amt <= 0:
            QMessageBox.information(self, "زكاة", "لا يوجد مبلغ مستحق حسب الاحتساب الحالي")
            return
        db.add_expense("زكاة", amt, "إخراج زكاة عروض التجارة")
        QMessageBox.information(self, "زكاة", f"سُجّل إخراج {amt:,.2f} د.ج في المصاريف")
        self.reload_exp()
