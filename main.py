#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ALASIL POS — واجهة نقاط بيع احترافية"""

import sys
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QSize, QLocale, QDate
from PySide6.QtGui import QFont, QColor, QPalette, QIcon, QPixmap, QPainter, QLinearGradient, QShortcut, QKeySequence, QCursor
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QFrame, QScrollArea, QGridLayout, QStackedWidget,
    QTableWidget, QTableWidgetItem, QHeaderView, QDialog, QFormLayout,
    QDoubleSpinBox, QSpinBox, QComboBox, QMessageBox, QSplitter, QSizePolicy, QDateEdit,
    QListWidget, QListWidgetItem, QSlider, QFileDialog, QToolButton, QMenu, QGroupBox, QCheckBox,
    QGraphicsDropShadowEffect, QProgressBar,
)

import database as db
import license as license_mod
from i18n import TEXTS
import receipt as receipt_mod
import scanner_server
from customer_card import CardDialog
from spec_office import PhotoOffice, resolve_img
from erp_pages import AdminHub
from wholesale_page import WholesalePage
from calculator import Calculator

ROOT = Path(__file__).resolve().parent
UI = {"font": 13}


def money(v, lang="ar"):
    s = f"{v:,.2f}"
    return f"{s} د.ج" if lang == "ar" else f"{s} DA"


class ProductCard(QFrame):
    def __init__(self, product, lang, on_add):
        super().__init__()
        self.setObjectName("productCard")
        fs = UI.get("font", 13)
        self.setFixedSize(154 + max(0, fs - 11), 214 + max(0, fs - 11))
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.product = product
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(3)

        img_wrap = QWidget()
        img_wrap.setFixedHeight(86)
        iw = QVBoxLayout(img_wrap)
        iw.setContentsMargins(0, 0, 0, 0)
        img_lab = QLabel()
        img_lab.setAlignment(Qt.AlignCenter)
        img_lab.setFixedHeight(82)
        img_path = ROOT / "assets" / (product.get("image") or "")
        if product.get("image") and img_path.exists():
            pix = QPixmap(str(img_path)).scaled(120, 80, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            img_lab.setPixmap(pix)
        else:
            img_lab.setText(product.get("emoji") or "📦")
            img_lab.setStyleSheet("font-size:40px;")
        iw.addWidget(img_lab)
        lay.addWidget(img_wrap)

        stock = product.get("stock") or 0
        if stock <= 5:
            btxt = f"{int(stock)} فقط" if lang == "ar" else f"{int(stock)}"
            bcol = "#f59e0b"
        else:
            btxt = "متوفر" if lang == "ar" else "Dispo"
            bcol = "#16a34a"
        badge = QLabel(btxt, self)
        badge.setStyleSheet(
            f"background:{bcol};color:white;border-radius:11px;padding:3px 8px;font-size:11px;font-weight:800;"
        )
        badge.adjustSize()
        badge.move(12, 12)
        badge.raise_()

        name = product["name_ar"] if lang == "ar" else product["name_fr"]
        nl = QLabel(name)
        nl.setObjectName("pName")
        nl.setWordWrap(True)
        nl.setAlignment(Qt.AlignCenter)
        lay.addWidget(nl)

        pl = QLabel(f"{product['price']:.2f} د.ج" if lang == "ar" else f"{product['price']:.2f} DA")
        pl.setObjectName("pPrice")
        pl.setAlignment(Qt.AlignCenter)
        lay.addWidget(pl)

        add = QPushButton("🛒  إضافة للسلة" if lang == "ar" else "Ajouter")
        add.setObjectName("addBtn")
        add.setCursor(Qt.PointingHandCursor)
        add.clicked.connect(lambda: on_add(product))
        lay.addWidget(add)


class PayDialog(QDialog):
    def __init__(self, total, lang, parent=None, customer=None):
        super().__init__(parent)
        self.lang = lang
        t = TEXTS[lang]
        self.setWindowTitle(t["pay"])
        self.setLayoutDirection(Qt.RightToLeft if lang == "ar" else Qt.LeftToRight)
        self.setMinimumWidth(380)
        self.method = "cash"
        self.paid = total
        self.customer = customer
        lay = QVBoxLayout(self)
        ttl = QLabel(money(total, lang))
        ttl.setStyleSheet("font-size:28px;font-weight:800;color:#0d3480;")
        ttl.setAlignment(Qt.AlignCenter)
        lay.addWidget(ttl)

        row = QHBoxLayout()
        methods = [("cash", t["cash"]), ("card", t["card"]), ("mixed", t["mixed"])]
        if customer:
            methods.append(("credit", "آجل / دين"))
        for key, lab in methods:
            b = QPushButton(lab)
            b.setCheckable(True)
            b.setChecked(key == "cash")
            b.setStyleSheet("QPushButton{padding:10px;border-radius:10px;background:#e8eef6;font-weight:700;} QPushButton:checked{background:#1e5cff;color:white;}")
            b.clicked.connect(lambda _, k=key: setattr(self, "method", k))
            row.addWidget(b)
        lay.addLayout(row)

        self.spin = QDoubleSpinBox()
        self.spin.setRange(0, 1_000_000)
        self.spin.setDecimals(2)
        self.spin.setValue(total)
        self.spin.setPrefix("")
        self.spin.setSuffix(" د.ج" if lang == "ar" else " DA")
        self.spin.setStyleSheet("font-size:18px;padding:8px;")
        lay.addWidget(QLabel(t["paid"]))
        lay.addWidget(self.spin)

        self.chg = QLabel("")
        self.chg.setAlignment(Qt.AlignCenter)
        self.chg.setStyleSheet("font-size:16px;color:#16a34a;font-weight:700;")
        lay.addWidget(self.chg)
        self.spin.valueChanged.connect(lambda v: self.chg.setText(t["change"] + ": " + money(max(0, v - total), lang)))
        self.spin.valueChanged.emit(self.spin.value())

        ok = QPushButton(t["confirm"])
        ok.setObjectName("payBtn")
        ok.setStyleSheet("background:#22c55e;color:white;border:none;border-radius:12px;padding:12px;font-size:16px;font-weight:800;")
        ok.clicked.connect(self.accept)
        lay.addWidget(ok)

    def values(self):
        return self.spin.value(), self.method


class QtyDialog(QDialog):
    def __init__(self, product, lang="ar", parent=None):
        super().__init__(parent)
        self.setWindowTitle("الكمية")
        unit = product.get("unit") or "قطعة"
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(f"{product.get('name_ar') or product.get('name_fr')}\nالسعر: {product['price']:.2f} د.ج / {unit}"))
        self.spin = QDoubleSpinBox()
        dec = db.unit_is_decimal(unit)
        self.spin.setDecimals(3 if dec else 0)
        self.spin.setRange(0.001 if dec else 1, 1e7)
        self.spin.setSingleStep(0.1 if dec else 1)
        self.spin.setValue(1.0 if not dec else 1.0)
        self.spin.setSuffix("  " + unit)
        self.spin.setStyleSheet("font-size:20px;padding:10px;")
        lay.addWidget(self.spin)
        ok = QPushButton("أضف للسلة")
        ok.setStyleSheet("background:#1e5cff;color:white;padding:10px;border-radius:10px;font-weight:800;")
        ok.clicked.connect(self.accept)
        lay.addWidget(ok)

    def qty(self):
        return float(self.spin.value())


class ActivationWindow(QWidget):
    def __init__(self, on_ok):
        super().__init__()
        self.on_ok = on_ok
        self.setWindowTitle("تفعيل ALASIL POS")
        pal = self.palette()
        pal.setColor(QPalette.Window, QColor("#0a2a6b"))
        self.setAutoFillBackground(True)
        self.setPalette(pal)
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignCenter)
        t = QLabel("تفعيل البرنامج")
        t.setStyleSheet("color:white;font-size:28px;font-weight:800;")
        t.setAlignment(Qt.AlignCenter)
        s = QLabel("أدخل كود التفعيل الذي وصلك من البائع")
        s.setStyleSheet("color:#9bb4e8;")
        s.setAlignment(Qt.AlignCenter)
        self.code = QLineEdit()
        self.code.setPlaceholderText("AL2.XXXXX.XXXXX")
        self.code.setMinimumWidth(420)
        self.code.setStyleSheet("padding:12px;font-size:16px;border-radius:10px;")
        self.err = QLabel("")
        self.err.setStyleSheet("color:#fca5a5;")
        self.err.setAlignment(Qt.AlignCenter)
        mid = QLabel("معرف هذا الجهاز: " + license_mod.machine_id())
        mid.setStyleSheet("color:#7ea0e0;font-size:12px;")
        mid.setAlignment(Qt.AlignCenter)
        btn = QPushButton("تفعيل")
        btn.setStyleSheet("background:#22c55e;color:white;border:none;border-radius:12px;padding:12px 28px;font-weight:800;")
        btn.clicked.connect(self.go)
        lay.addStretch()
        lay.addWidget(t)
        lay.addWidget(s)
        lay.addWidget(self.code, 0, Qt.AlignCenter)
        lay.addWidget(self.err)
        lay.addWidget(btn, 0, Qt.AlignCenter)
        lay.addWidget(mid)
        lay.addStretch()

    def go(self):
        ok, msg = license_mod.activate(self.code.text())
        if ok:
            self.on_ok()
        else:
            self.err.setText(msg)


class LoginWindow(QWidget):
    def __init__(self, on_ok):
        super().__init__()
        self.on_ok = on_ok
        self.setWindowTitle("ALASIL POS — تسجيل الدخول")
        self.resize(900, 600)
        pal = self.palette()
        pal.setColor(QPalette.Window, QColor("#1a1d22"))
        self.setAutoFillBackground(True)
        self.setPalette(pal)
        root = QVBoxLayout(self)
        title = QLabel("ALASIL POS")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("color:#39ff14;font-size:36px;font-weight:900;")
        sub = QLabel("تسجيل دخول المدير أو الموظف")
        sub.setAlignment(Qt.AlignCenter)
        sub.setStyleSheet("color:#c5ccd6;font-size:16px;")
        box = QWidget()
        box.setMaximumWidth(420)
        f = QFormLayout(box)
        self.user_ed = QLineEdit()
        self.user_ed.setPlaceholderText("اسم المستخدم")
        self.pass_ed = QLineEdit()
        self.pass_ed.setPlaceholderText("كلمة السر")
        self.pass_ed.setEchoMode(QLineEdit.Password)
        for w in (self.user_ed, self.pass_ed):
            w.setMinimumHeight(44)
            w.setStyleSheet("background:#3a3f48;color:white;border:1px solid #5b6470;border-radius:8px;padding:10px;font-size:16px;")
        f.addRow("المستخدم", self.user_ed)
        f.addRow("كلمة السر", self.pass_ed)
        self.err = QLabel("")
        self.err.setAlignment(Qt.AlignCenter)
        self.err.setStyleSheet("color:#fca5a5;font-size:15px;")
        btn = QPushButton("دخول")
        btn.setMinimumHeight(48)
        btn.setStyleSheet("background:#2ea44f;color:white;border:none;border-radius:8px;font-size:18px;font-weight:800;")
        btn.clicked.connect(self.try_login)
        self.pass_ed.returnPressed.connect(self.try_login)
        self.user_ed.returnPressed.connect(self.pass_ed.setFocus)
        roles = QHBoxLayout()
        ba = QPushButton("دخول كمدير")
        be = QPushButton("دخول كموظف")
        ba.setStyleSheet("background:#2c5282;color:white;padding:12px;border-radius:8px;font-weight:800;")
        be.setStyleSheet("background:#3d434c;color:white;padding:12px;border-radius:8px;font-weight:800;")
        ba.clicked.connect(lambda: (self.user_ed.setText("admin"), self.pass_ed.clear(), self.pass_ed.setFocus()))
        be.clicked.connect(lambda: (self.user_ed.setText("employe"), self.pass_ed.clear(), self.pass_ed.setFocus()))
        roles.addWidget(ba)
        roles.addWidget(be)
        hint = QLabel("المدير: كل الصفحات\nالموظف: نقطة البيع والجملة والفواتير والعملاء\nأول تشغيل: غيّر كلمة السر الافتراضية فوراً")
        hint.setAlignment(Qt.AlignCenter)
        hint.setStyleSheet("color:#9aa3ad;font-size:14px;")
        root.addStretch()
        root.addWidget(title)
        root.addWidget(sub)
        hl = QHBoxLayout(); hl.addStretch(); hl.addWidget(box); hl.addStretch()
        root.addLayout(hl)
        root.addWidget(self.err)
        bh = QHBoxLayout(); bh.addStretch(); bh.addWidget(btn); bh.addStretch()
        root.addLayout(bh)
        rh = QHBoxLayout(); rh.addStretch(); rh.addLayout(roles); rh.addStretch()
        root.addLayout(rh)
        root.addWidget(hint)
        root.addStretch()

    def try_login(self):
        if db.failed_logins(15) >= 8:
            self.err.setText("الحساب مقفل مؤقتاً — انتظر 15 دقيقة")
            return
        u = self.user_ed.text().strip()
        pw = self.pass_ed.text()
        user = db.authenticate_user(u, pw)
        db.log_login(u, bool(user))
        if user:
            if user.get("must_change_pw"):
                if not self._force_new_password(user):
                    return
            self.on_ok(user)
        else:
            self.err.setText("اسم المستخدم أو كلمة السر غير صحيحة")

    def _force_new_password(self, user):
        dlg = QDialog(self)
        dlg.setWindowTitle("تغيير كلمة السر إلزامي")
        f = QFormLayout(dlg)
        lab = QLabel("لأمان الحساب يجب تعيين كلمة سر جديدة (8 أحرف على الأقل).")
        lab.setWordWrap(True)
        f.addRow(lab)
        a = QLineEdit(); a.setEchoMode(QLineEdit.Password)
        b = QLineEdit(); b.setEchoMode(QLineEdit.Password)
        f.addRow("كلمة السر الجديدة", a)
        f.addRow("تأكيد", b)
        err = QLabel(""); err.setStyleSheet("color:#fca5a5;")
        f.addRow(err)
        ok = QPushButton("حفظ ودخول")
        def go():
            p1, p2 = a.text(), b.text()
            if len(p1) < 8:
                err.setText("8 أحرف على الأقل")
                return
            if p1 != p2:
                err.setText("التأكيد غير مطابق")
                return
            if p1 in ("admin", "emp123", "1234", "0000"):
                err.setText("لا تستخدم كلمة سر افتراضية")
                return
            db.set_user_password(user["id"], p1, must_change=False)
            user["must_change_pw"] = 0
            dlg.accept()
        ok.clicked.connect(go)
        f.addRow(ok)
        return dlg.exec() == QDialog.Accepted

class MainWindow(QMainWindow):
    def __init__(self, user):
        super().__init__()
        self.lang = "ar"
        self.user = db.apply_role_permissions(user)
        self.last_invoice = None
        self.current_customer = None
        self.cart = []  # {id,name,price,qty,emoji}
        self.discount = 0.0
        self.cat_id = 1
        self.setWindowTitle("ALASIL POS 1.0")
        scr = QApplication.primaryScreen()
        geo = scr.availableGeometry() if scr else None
        self.setMinimumSize(640, 480)
        if geo:
            self.resize(max(800, geo.width()), max(560, geo.height()))
        else:
            self.resize(1280, 720)

        self.apply_theme()

        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        self.root_lay = QVBoxLayout(root)
        self.root_lay.setContentsMargins(0, 0, 0, 0)
        self.root_lay.setSpacing(0)

        self.top = QWidget()
        self.top.setObjectName("topBar")
        self.top.setMinimumHeight(56)
        self.top.setMaximumHeight(96)
        self.root_lay.addWidget(self.top)

        self.body = QWidget()
        self.root_lay.addWidget(self.body, 1)

        self.statusBar().showMessage("ALASIL POS")
        self.build_top()
        self.build_body()
        self.apply_theme()
        self.apply_dir()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(1000)
        self.tick()
        self.refresh_products()
        self.refresh_cart()
        self.refresh_stats()
        QShortcut(QKeySequence("F2"), self, activated=self.ask_discount)
        QShortcut(QKeySequence("F3"), self, activated=self.focus_pos_search)
        QShortcut(QKeySequence("F4"), self, activated=self.edit_selected_qty)
        QShortcut(QKeySequence("F8"), self, activated=self.clear_cart)
        QShortcut(QKeySequence("F9"), self, activated=self.do_hold)
        QShortcut(QKeySequence("F10"), self, activated=self.do_pay)
        QShortcut(QKeySequence("F12"), self, activated=lambda: self.do_pay_method("cash"))
        QShortcut(QKeySequence("Delete"), self, activated=self.delete_selected_cart)
        self._calc = None
        self.goto_page(self.first_allowed_page())
        self.scan_url = scanner_server.start()
        self._apply_network()
        self.scan_timer = QTimer(self)
        self.scan_timer.timeout.connect(self.poll_phone_scans)
        self.scan_timer.start(200)

    def apply_theme(self, size=None):
        try:
            size = int(size if size is not None else db.get_setting("font_size", "18") or 18)
        except ValueError:
            size = 18
        if size < 16:
            size = 18
        size = max(16, min(26, size))
        UI["font"] = size
        self.font_size = size
        sm, md, lg = size, size + 3, size + 7
        xl, xxl = size + 12, size + 18
        tpl = (ROOT / "styles.qss").read_text(encoding="utf-8")
        self.setStyleSheet(tpl.format(base=size, sm=sm, md=md, lg=lg, xl=xl, xxl=xxl))
        QApplication.instance().setFont(QFont("Noto Naskh Arabic UI", size))
        if hasattr(self, "top"):
            h = max(56, min(88, 44 + size))
            self.top.setMinimumHeight(h)
            self.top.setMaximumHeight(h)
        for tbl in self.findChildren(QTableWidget):
            tbl.verticalHeader().setDefaultSectionSize(max(40, size + 24))
            f = tbl.font()
            f.setPointSize(size)
            tbl.setFont(f)
        if hasattr(self, "font_preview"):
            self.font_preview.setText(f"معاينة: حجم الخط {size} — ALASIL POS  مرحباً")
        if hasattr(self, "grid") and hasattr(self, "search"):
            self.refresh_products()

    def can(self, key):
        return db.user_can(self.user, key)

    def rebuild_nav_menu(self):
        if not hasattr(self, "nav_menu"):
            return
        self.nav_menu.clear()
        self._nav_actions = []
        for key, page in self._nav_map:
            if not self.can(key):
                continue
            act = self.nav_menu.addAction(self.nav_label(key))
            act.setData(page)
            act.triggered.connect(lambda checked=False, p=page: self.goto_page(p))
            self._nav_actions.append((act, key, page))

    def nav_label(self, key):
        ar = {
            "pos": "نقطة البيع", "wholesale": "الجملة", "products": "المنتجات",
            "cats": "التصنيفات", "sales": "الفواتير", "reports": "التقارير",
            "customers": "عملاء يَدين", "specs": "اختصاصات", "admin": "الإدارة",
            "settings": "الإعدادات",
        }
        fr = {
            "pos": "Caisse", "wholesale": "Gros", "products": "Produits",
            "cats": "Catégories", "sales": "Factures", "reports": "Rapports",
            "customers": "Crédit", "specs": "Métiers", "admin": "Admin",
            "settings": "Paramètres",
        }
        return (ar if self.lang == "ar" else fr).get(key, key)

    def t(self, k):
        return TEXTS[self.lang][k]

    def apply_dir(self):
        d = Qt.RightToLeft if self.lang == "ar" else Qt.LeftToRight
        self.setLayoutDirection(d)
        QApplication.instance().setLayoutDirection(d)

    def build_top(self):
        lay = QHBoxLayout(self.top)
        lay.setContentsMargins(18, 8, 18, 8)
        logo_box = QVBoxLayout()
        logo_box.setSpacing(0)
        logo_row = QHBoxLayout()
        cart_ico = QLabel("🛒")
        cart_ico.setStyleSheet("font-size:26px;color:white;")
        logo = QLabel("ALASIL POS")
        logo.setObjectName("logo")
        logo_row.addWidget(cart_ico)
        logo_row.addWidget(logo)
        logo_box.addLayout(logo_row)
        sub = QLabel("Votre Partenaire Commercial")
        sub.setObjectName("logoSub")
        logo_box.addWidget(sub)
        lay.addLayout(logo_box)

        self._nav_map = [
            ("pos", 0), ("wholesale", 9), ("products", 1), ("cats", 2),
            ("sales", 3), ("reports", 4), ("customers", 5), ("specs", 6), ("admin", 7), ("settings", 8),
        ]
        self.menu_btn = QToolButton()
        self.menu_btn.setText("☰   القائمة")
        self.menu_btn.setPopupMode(QToolButton.InstantPopup)
        self.menu_btn.setStyleSheet(
            "QToolButton{background:#3d434c;color:white;border:1px solid #1f2328;border-radius:4px;"
            "padding:10px 18px;font-weight:800;} QToolButton::menu-indicator{image:none;}"
        )
        self.nav_menu = QMenu(self)
        self.nav_menu.setStyleSheet(
            "QMenu{background:#32363e;color:#e8edf5;border:1px solid #3d434c;padding:6px;}"
            "QMenu::item{padding:10px 28px;} QMenu::item:selected{background:#2c5282;}"
        )
        self._nav_actions = []
        self.menu_btn.setMenu(self.nav_menu)
        self.rebuild_nav_menu()
        lay.addWidget(self.menu_btn)
        self.page_chip = QLabel("نقطة البيع")
        self.page_chip.setStyleSheet("color:white;font-weight:800;padding:4px 10px;")
        lay.addWidget(self.page_chip)

        lay.addStretch()
        self.clock = QLabel()
        self.clock.setObjectName("clock")
        lay.addWidget(self.clock)

        calc_btn = QPushButton("🖩  حاسبة")
        calc_btn.setObjectName("langBtn")
        calc_btn.setCursor(Qt.PointingHandCursor)
        calc_btn.clicked.connect(self.open_calculator)
        lay.addWidget(calc_btn)
        self.calc_btn = calc_btn

        self.btn_ar = QPushButton("🇩🇿  العربية")
        self.btn_fr = QPushButton("🇫🇷  Français")
        for b, lg in ((self.btn_ar, "ar"), (self.btn_fr, "fr")):
            b.setObjectName("langBtn")
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _, x=lg: self.set_lang(x))
            lay.addWidget(b)
        self.btn_ar.setProperty("active", "true")

        role_ar = "مدير" if self.user.get("role") == "admin" else "موظف"
        user = QLabel("👤  " + self.user["display_name"] + "  (" + role_ar + ")\n● متصل")
        user.setObjectName("userChip")
        user.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        lay.addWidget(user)
        self.user_lbl = user

    def build_body(self):
        wrap = QHBoxLayout(self.body)
        wrap.setContentsMargins(0, 0, 0, 0)
        wrap.setSpacing(0)
        self.body.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.pages = QStackedWidget()
        self.pages.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        wrap.addWidget(self.pages, 1)

        self.pos_page = QWidget()
        self.pages.addWidget(self.pos_page)
        self.build_pos(self.pos_page)
        self.pages.addWidget(self.build_products_page())
        self.pages.addWidget(self.build_cats_page())
        self.pages.addWidget(self.build_sales_page())
        self.pages.addWidget(self.build_reports_page())
        self.pages.addWidget(self.build_customers_page())
        self.pages.addWidget(self.build_specs_page())
        self.admin_hub = AdminHub(self)
        self.pages.addWidget(self.admin_hub)
        self.pages.addWidget(self.build_settings_page())
        self.ws_page = WholesalePage(self)
        self.pages.addWidget(self.ws_page)
        self.pages.currentChanged.connect(self.on_page)

        self.cart_panel = QWidget()
        self.cart_panel.setObjectName("cartPanel")
        self.cart_panel.hide()
        self.build_cart()

    def _aronium_btn(self, title, key="", accent="#3a3f48", bar="#6b7380", icon=""):
        b = QPushButton()
        b.setCursor(Qt.PointingHandCursor)
        b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        b.setMinimumSize(72, 64)
        lines = []
        if key:
            lines.append(key)
        if icon:
            lines.append(icon)
        lines.append(title)
        b.setText("\n".join(lines))
        b.setStyleSheet(
            f"QPushButton{{background:{accent};color:#ffffff;border:1px solid #15181c;"
            f"border-top:5px solid {bar};border-radius:6px;padding:8px 4px;"
            f"font-size:15px;font-weight:800;}}"
            f"QPushButton:hover{{background:#4e5664;}}"
            f"QPushButton:pressed{{background:#252830;}}"
        )
        return b

    def build_pos(self, page):
        page.setObjectName("posAronium")
        page.setLayoutDirection(Qt.LeftToRight)
        page.setStyleSheet(
            "QWidget#posAronium{background:#2b2f36;}"
            "QLineEdit#search{background:#3a3f48;color:#ffffff;border:1px solid #5b6470;border-radius:6px;"
            "padding:14px 18px;font-size:18px;font-weight:700;}"
            "QTableWidget#posTicket{background:#2b2f36;color:#ffffff;gridline-color:#4a5160;border:none;font-size:17px;}"
            "QTableWidget#posTicket::item{padding:10px;}"
            "QHeaderView::section{background:#1f2328;color:#ffffff;border:none;padding:12px;font-weight:800;font-size:16px;}"
            "QLabel#emptyPos{color:#dce3ec;font-size:20px;font-weight:700;}"
            "QLabel#sumLabel{color:#b8c0ca;font-size:13px;}"
            "QLabel#sumValue{color:#e8edf5;font-size:13px;}"
            "QLabel#totalBig{color:#39ff14;font-size:42px;font-weight:900;letter-spacing:1px;}"
        )
        page.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        root = QHBoxLayout(page)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        left = QWidget()
        left.setStyleSheet("background:#2b2f36;")
        ll = QVBoxLayout(left)
        ll.setContentsMargins(10, 8, 8, 8)
        ll.setSpacing(6)

        bar = QHBoxLayout()
        scan = QPushButton("▮▮▮")
        scan.setFixedWidth(48)
        scan.setStyleSheet("background:#3a3f48;color:#5dade2;border:none;font-weight:900;")
        scan.clicked.connect(self.open_phone_scanner)
        bar.addWidget(scan)
        self.search = QLineEdit()
        self.search.setObjectName("search")
        self.search.setPlaceholderText("بحث عن منتج بالاسم أو الباركود  (F3)")
        self.search.textChanged.connect(self.refresh_products)
        self.search.returnPressed.connect(self.try_barcode)
        bar.addWidget(self.search, 1)
        ll.addLayout(bar)

        self.cart_title = QLabel("")
        self.cart_title.hide()
        self.cust = QPushButton("👤  عميل")
        self.cust.setCursor(Qt.PointingHandCursor)
        self.cust.setStyleSheet("color:#9ec5fe;background:transparent;border:none;text-align:left;font-weight:700;")
        self.cust.clicked.connect(self.pick_customer)
        ll.addWidget(self.cust)

        self.cart_table = QTableWidget(0, 4)
        self.cart_table.setObjectName("posTicket")
        self.cart_table.setHorizontalHeaderLabels(["اسم المنتج", "الكمية", "السعر", "المبلغ"])
        self.cart_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.cart_table.setColumnWidth(1, 90)
        self.cart_table.setColumnWidth(2, 90)
        self.cart_table.setColumnWidth(3, 100)
        self.cart_table.verticalHeader().setVisible(False)
        self.cart_table.setShowGrid(False)
        self.cart_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.cart_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.empty_lbl = QLabel("لا توجد عناصر\nأضف منتجات بالباركود أو اضغط F3 للبحث")
        self.empty_lbl.setObjectName("emptyPos")
        self.empty_lbl.setAlignment(Qt.AlignCenter)
        self.empty_lbl.setWordWrap(True)
        self.ticket_stack = QStackedWidget()
        self.ticket_stack.addWidget(self.empty_lbl)
        self.ticket_stack.addWidget(self.cart_table)
        ll.addWidget(self.ticket_stack, 1)

        self.sum_box = QWidget()
        sl = QVBoxLayout(self.sum_box)
        sl.setContentsMargins(8, 8, 16, 8)
        self.l_sub, self.v_sub = self._kv(sl, "المجموع الفرعي")
        self.l_disc, self.v_disc = self._kv(sl, "الخصم")
        self.l_tax, self.v_tax = self._kv(sl, "الضريبة")
        tot_row = QHBoxLayout()
        self.l_tot = QLabel("الإجمالي")
        self.l_tot.setStyleSheet("color:#fff;font-size:16px;font-weight:800;")
        self.v_tot = QLabel(money(0, self.lang))
        self.v_tot.setObjectName("totalBig")
        self.v_tot.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.v_tot.setMinimumHeight(64)
        glow = QGraphicsDropShadowEffect(self.v_tot)
        glow.setBlurRadius(28)
        glow.setColor(QColor(57, 255, 20, 220))
        glow.setOffset(0, 0)
        self.v_tot.setGraphicsEffect(glow)
        tot_row.addWidget(self.l_tot)
        tot_row.addStretch()
        tot_row.addWidget(self.v_tot)
        sl.addLayout(tot_row)
        ll.addWidget(self.sum_box)

        # hidden catalog used by F3
        self.cat_row = QHBoxLayout()
        self.grid_host = QWidget()
        self.grid = QGridLayout(self.grid_host)
        self.grid.setSpacing(8)
        self.prod_scroll = QScrollArea()
        self.prod_scroll.setWidgetResizable(True)
        self.prod_scroll.setWidget(self.grid_host)
        self.stat_sales = self._stat_card("مبيعات اليوم", "0")
        self.stat_inv = self._stat_card("عدد الفواتير", "0")
        self.stat_stock = self._stat_card("المنتجات المباعة", "0")
        self.stat_profit = self._stat_card("الأرباح اليومية", "0")
        for w in (self.stat_sales, self.stat_inv, self.stat_stock, self.stat_profit):
            w.hide()
        self.print_btn = QPushButton("طباعة")
        self.ret_btn = QPushButton("إرجاع")
        self.print_btn.hide(); self.ret_btn.hide()

        root.addWidget(left, 1)

        right = QWidget()
        right.setObjectName("posKeys")
        right.setMinimumWidth(200)
        right.setStyleSheet("background:#2a2e35;")
        rg = QGridLayout(right)
        rg.setContentsMargins(10, 10, 10, 10)
        rg.setSpacing(8)

        def tile(r, c, title, key, fn, icon="", bar="#6b7380", accent="#3a3f48", rs=1, cs=1):
            b = self._aronium_btn(title, key, accent, bar, icon)
            b.clicked.connect(fn)
            rg.addWidget(b, r, c, rs, cs)
            return b

        tile(0, 0, "حذف", "Del", self.delete_selected_cart, "✕", "#9aa3ad")
        tile(0, 1, "بحث", "F3", self.focus_pos_search, "🔍", "#5dade2")
        tile(0, 2, "الكمية", "F4", self.edit_selected_qty, "🔢", "#5dade2")
        tile(0, 3, "بيع جديد", "F8", self.clear_cart, "＋", "#5dade2")
        tile(1, 0, "نقداً", "F12", lambda: self.do_pay_method("cash"), "💵", "#2ea44f")
        tile(1, 1, "بطاقة", "", lambda: self.do_pay_method("card"), "💳", "#3b82f6")
        tile(1, 2, "خصم بطاقة", "", lambda: self.do_pay_method("card"), "🏧", "#3b82f6")
        tile(2, 0, "شيك", "", lambda: self.do_pay_method("mixed"), "📄", "#94a3b8")
        tile(2, 1, "قسيمة", "", lambda: self.do_pay_method("mixed"), "🎟", "#94a3b8")
        tile(2, 2, "آجل", "", lambda: self.do_pay_method("credit"), "🧾", "#f59e0b")
        tile(3, 0, "خصم", "F2", self.ask_discount, "%", "#f59e0b", "#3a3f48", 1, 2)
        tile(3, 2, "درج النقود", "", lambda: QMessageBox.information(self, "ALASIL", "تم إرسال أمر فتح درج النقود"), "🖨", "#94a3b8", "#3a3f48", 1, 2)
        self.hold_btn = tile(4, 0, "حفظ", "F9", self.do_hold, "💾", "#94a3b8")
        self.ret_btn = tile(4, 1, "إرجاع", "", self.do_return, "↩", "#f59e0b")
        self.pay_btn = tile(4, 2, "دفع", "F10", self.do_pay, "✓", "#ffffff", "#2ea44f", 1, 2)
        tile(5, 0, "قفل", "", self.lock_pos, "🔒", "#94a3b8")
        tile(5, 1, "تعليق", "F7", self.do_hold, "⏸", "#94a3b8")
        self.clr_btn = tile(5, 2, "إلغاء", "", self.clear_cart, "🗑", "#ffffff", "#c0392b")
        tile(5, 3, "المزيد", "", self.open_pos_more, "⋯", "#94a3b8")
        keys_scroll = QScrollArea()
        keys_scroll.setWidgetResizable(True)
        keys_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        keys_scroll.setFrameShape(QFrame.NoFrame)
        keys_scroll.setWidget(right)
        self.pos_split = QSplitter(Qt.Horizontal)
        self.pos_split.addWidget(left)
        self.pos_split.addWidget(keys_scroll)
        self.pos_split.setStretchFactor(0, 3)
        self.pos_split.setStretchFactor(1, 2)
        self.pos_split.setSizes([900, 420])
        root.addWidget(self.pos_split, 1)
        self.update_cust_label()
        self.rebuild_cats()

    def _stat_card(self, label, value):
        f = QFrame()
        f.setObjectName("statCard")
        l = QVBoxLayout(f)
        l.setContentsMargins(14, 10, 14, 10)
        v = QLabel(value)
        v.setObjectName("statVal")
        lb = QLabel(label)
        lb.setObjectName("statLbl")
        l.addWidget(v)
        l.addWidget(lb)
        f._val, f._lbl = v, lb
        return f

    def rebuild_cats(self):
        while self.cat_row.count():
            w = self.cat_row.takeAt(0).widget()
            if w:
                w.deleteLater()
        icons = {1: "⊞", 2: "🧺", 3: "🥤", 4: "🧴", 5: "👕", 6: "🖥"}
        for c in db.fetch_categories():
            name = c["name_ar"] if self.lang == "ar" else c["name_fr"]
            b = QPushButton(f"{icons.get(c['id'], '•')}\n{name}")
            b.setObjectName("catBtn")
            b.setCursor(Qt.PointingHandCursor)
            on = c["id"] == self.cat_id
            b.setStyleSheet(
                "background:#2ea44f;color:white;border:1px solid #1f2328;border-radius:4px;padding:8px 12px;font-weight:800;"
                if on else
                "background:#3d434c;color:#e8edf5;border:1px solid #1f2328;border-radius:4px;padding:8px 12px;font-weight:800;"
            )
            b.clicked.connect(lambda _, i=c["id"]: self.set_cat(i))
            self.cat_row.addWidget(b)
        self.cat_row.addStretch()

    def set_cat(self, i):
        self.cat_id = i
        self.rebuild_cats()
        self.refresh_products()

    def refresh_products(self):
        while self.grid.count():
            w = self.grid.takeAt(0).widget()
            if w:
                w.deleteLater()
        q = self.search.text()
        items = db.fetch_products(self.cat_id, q)
        avail = 900
        if hasattr(self, "prod_scroll") and self.prod_scroll.width() > 200:
            avail = self.prod_scroll.viewport().width()
        cols = max(3, min(6, avail // 168))
        for i, p in enumerate(items):
            card = ProductCard(p, self.lang, self.add_to_cart)
            self.grid.addWidget(card, i // cols, i % cols, Qt.AlignTop)
        self.grid_host.adjustSize()

    def build_cart(self):
        self.cart_panel.hide()

    def _kv(self, parent, label):
        r = QHBoxLayout()
        a = QLabel(label)
        a.setObjectName("sumLabel")
        b = QLabel(money(0, self.lang))
        b.setObjectName("sumValue")
        r.addWidget(a)
        r.addStretch()
        r.addWidget(b)
        parent.addLayout(r)
        return a, b

    def add_to_cart(self, product, qty=None):
        unit = product.get("unit") or "قطعة"
        if qty is None:
            if db.unit_is_decimal(unit):
                dlg = QtyDialog(product, self.lang, self)
                if dlg.exec() != QDialog.Accepted:
                    return
                qty = dlg.qty()
            else:
                qty = 1.0
        if qty <= 0:
            return
        exp = (product.get("expiry_date") or "").strip()
        if exp:
            try:
                from datetime import date as _d
                ed = _d.fromisoformat(exp[:10])
                if ed < _d.today():
                    if QMessageBox.question(
                        self, "صلاحية", f"المنتج منتهي الصلاحية ({exp}). المتابعة؟"
                    ) != QMessageBox.Yes:
                        return
                elif (ed - _d.today()).days <= 30:
                    QMessageBox.information(self, "صلاحية", f"تنبيه: ينتهي في {exp}")
            except Exception:
                pass
        for it in self.cart:
            if it["id"] == product["id"]:
                it["qty"] += qty
                self.refresh_cart()
                return
        name = product["name_ar"] if self.lang == "ar" else product["name_fr"]
        self.cart.append({
            "id": product["id"], "name": name, "price": product["price"],
            "qty": qty, "emoji": product.get("emoji"), "unit": unit,
        })
        self.refresh_cart()

    def change_qty(self, idx, delta):
        if 0 <= idx < len(self.cart):
            self.cart[idx]["qty"] += delta
            if self.cart[idx]["qty"] <= 0:
                self.cart.pop(idx)
            self.refresh_cart()

    def remove_item(self, idx):
        if 0 <= idx < len(self.cart):
            self.cart.pop(idx)
            self.refresh_cart()

    def cart_totals(self):
        sub = sum(i["price"] * i["qty"] for i in self.cart)
        disc = self.discount
        taxable = max(0, sub - disc)
        tax = taxable * db.tax_rate()
        total = taxable + tax
        return sub, disc, tax, total

    def refresh_cart(self):
        n = len(self.cart)
        if hasattr(self, "ticket_stack"):
            self.ticket_stack.setCurrentIndex(0 if n == 0 else 1)
        else:
            self.empty_lbl.setVisible(n == 0)
            self.cart_table.setVisible(n > 0)
        self.cart_table.setRowCount(n)
        for i, it in enumerate(self.cart):
            qv = it["qty"]
            qtxt = f"{qv:.3f}".rstrip("0").rstrip(".") if abs(qv - int(qv)) > 0.0001 else str(int(qv))
            self.cart_table.setItem(i, 0, QTableWidgetItem(it["name"]))
            self.cart_table.setItem(i, 1, QTableWidgetItem(qtxt))
            self.cart_table.setItem(i, 2, QTableWidgetItem(f"{it['price']:.2f}"))
            self.cart_table.setItem(i, 3, QTableWidgetItem(f"{it['price']*it['qty']:.2f}"))
            self.cart_table.setRowHeight(i, 36)

        sub, disc, tax, total = self.cart_totals()
        self.v_sub.setText(money(sub, self.lang))
        self.v_disc.setText(money(disc, self.lang))
        self.v_tax.setText(money(tax, self.lang))
        self.v_tot.setText(money(total, self.lang))

    def apply_scanned_code(self, code):
        code = (code or "").strip()
        if not code:
            return
        p = db.find_by_barcode(code)
        if p:
            self.add_to_cart(p)
            self.statusBar().showMessage(f"باركود {code} → {p['name_ar']}", 2500)
        else:
            self.search.setText(code)
            self.refresh_products()
            self.statusBar().showMessage(f"غير موجود: {code}", 2500)

    def try_barcode(self):
        code = self.search.text().strip()
        if not code:
            self.open_phone_scanner()
            return
        p = db.find_by_barcode(code)
        self.apply_scanned_code(code)
        if p:
            self.search.clear()

    def poll_phone_scans(self):
        for code in scanner_server.poll_codes():
            self.apply_scanned_code(code)

    def open_phone_scanner(self):
        url = scanner_server.scan_url()
        dlg = QDialog(self)
        dlg.setWindowTitle("الهاتف كقارئ باركود")
        dlg.setMinimumWidth(520)
        lay = QVBoxLayout(dlg)
        t = QLabel("مسح الباركود بكاميرا الهاتف")
        t.setStyleSheet("font-size:16px;font-weight:800;color:#0d3480;")
        lay.addWidget(t)

        usb_box = QLabel(
            "<b>1) كابل USB + كاميرا (أندرويد)</b><br>"
            "• وصّل الهاتف بكابل، فعّل <b>تصحيح USB</b> (خيارات المطوّر).<br>"
            "• اضغط الزر أدناه لربط المنفذ عبر ADB.<br>"
            "• على الهاتف افتح Chrome: <code>http://127.0.0.1:8765/</code><br>"
            "• اسمح للكاميرا وامسح الباركود.<br><br>"
            "<b>أو مشاركة الإنترنت USB:</b> من الهاتف فعّل USB tethering ثم استخدم رابط الواي فاي أدناه "
            "(عنوان يبدأ غالباً بـ 192.168.42).<br><br>"
            "<b>2) تطبيق ماسح HID:</b> تطبيقات تحول الكاميرا إلى لوحة مفاتيح عبر USB — "
            "ضع المؤشر في خانة البحث هنا ثم امسح.<br><br>"
            "<b>3) نفس الواي فاي:</b> الرابط التالي:"
        )
        usb_box.setWordWrap(True)
        usb_box.setTextFormat(Qt.RichText)
        lay.addWidget(usb_box)

        st = QLabel("")
        st.setWordWrap(True)
        usb_btn = QPushButton("ربط الهاتف عبر USB (ADB)")
        usb_btn.setStyleSheet("background:#0d3480;color:white;border:none;border-radius:10px;padding:10px;font-weight:800;")

        def do_adb():
            ok, msg = scanner_server.adb_reverse()
            if ok:
                st.setStyleSheet("color:#15803d;font-weight:700;")
                st.setText("تم الربط. على الهاتف افتح: " + msg)
                usb_url.setText(msg)
                QApplication.clipboard().setText(msg)
            else:
                st.setStyleSheet("color:#b91c1c;")
                st.setText(msg)

        usb_btn.clicked.connect(do_adb)
        lay.addWidget(usb_btn)
        lay.addWidget(st)

        usb_url = QLineEdit("http://127.0.0.1:8765/?t=alasil")
        usb_url.setReadOnly(True)
        lay.addWidget(QLabel("رابط USB (بعد الربط):"))
        lay.addWidget(usb_url)

        lay.addWidget(QLabel("رابط الشبكة / الواي فاي:"))
        url_lbl = QLineEdit(url)
        url_lbl.setReadOnly(True)
        url_lbl.setStyleSheet("font-size:16px;padding:10px;font-weight:800;color:#1e5cff;")
        lay.addWidget(url_lbl)
        extras = scanner_server.usb_tether_ips()
        if extras:
            lay.addWidget(QLabel("عناوين محتملة لـ USB tethering: " + "  |  ".join(
                f"http://{ip}:8765/" for ip in extras
            )))
        row = QHBoxLayout()
        copy = QPushButton("نسخ رابط الواي فاي")
        copy.clicked.connect(lambda: QApplication.clipboard().setText(url))
        openb = QPushButton("تجربة من هذا الجهاز")
        openb.clicked.connect(lambda: __import__("webbrowser").open(url))
        row.addWidget(copy)
        row.addWidget(openb)
        lay.addLayout(row)
        close = QPushButton("حسناً")
        close.clicked.connect(dlg.accept)
        lay.addWidget(close)
        dlg.exec()

    def closeEvent(self, e):
        scanner_server.stop()
        super().closeEvent(e)

    def do_pay(self):
        if not self.cart:
            QMessageBox.information(self, "ALASIL", self.t("no_items"))
            return
        sub, disc, tax, total = self.cart_totals()
        dlg = PayDialog(total, self.lang, self, self.current_customer)
        m0 = getattr(self, "_force_pay_method", None)
        if m0:
            dlg.method = m0
        if dlg.exec() != QDialog.Accepted:
            return
        paid, method = dlg.values()
        if paid + 0.001 < total:
            QMessageBox.warning(self, "ALASIL", self.t("insufficient"))
            return
        if method == "credit":
            c = self.current_customer
            if not c:
                QMessageBox.warning(self, "ALASIL", "اختر عميلاً للبيع بالدين")
                return
            new_debt = float(c.get("debt") or 0) + total
            if new_debt > float(c.get("credit_limit") or 0) + 0.01:
                QMessageBox.warning(self, "ALASIL", "تجاوز سقف الدين لهذا العميل")
                return
            paid, change = 0.0, 0.0
        else:
            change = paid - total
        cid = self.current_customer["id"] if self.current_customer else None
        try:
            inv = db.save_sale(self.user["id"], self.cart, sub, disc, tax, total, paid, change, method, customer_id=cid)
        except ValueError as e:
            QMessageBox.warning(self, "ALASIL", str(e))
            return
        if method == "credit" and self.current_customer:
            sale, _ = db.get_sale_by_invoice(inv)
            db.add_debt(self.current_customer["id"], total, f"فاتورة {inv}", sale["id"] if sale else None)
            self.current_customer = db.get_customer(self.current_customer["id"])
            self.update_cust_label()
        self.last_invoice = inv
        QMessageBox.information(self, self.t("success"), f"{self.t('invoice')}: {inv}\n{self.t('change')}: {money(change, self.lang)}")
        sale, items = db.get_sale_by_invoice(inv)
        receipt_mod.show_and_print(self, sale, items, self.user["display_name"], self.lang)
        self.cart = []
        self.refresh_cart()
        self.refresh_products()
        self.refresh_stats()
        self.reload_sales_table()

    def _apply_network(self):
        import net_sync
        net_sync.configure_client()
        m = net_sync.mode()
        if m == "server":
            try:
                ok, port = net_sync.start_server()
                self.statusBar().showMessage(f"هذا الجهاز خادم الشبكة — المنفذ {port} — أدخل IP هذا الجهاز في الجهاز الآخر")
            except Exception as e:
                self.statusBar().showMessage(f"تعذر تشغيل الخادم: {e}")
        elif m == "client":
            self.statusBar().showMessage("وضع عميل — البيانات من الخادم: " + db.get_setting("net_host", ""))
        else:
            self.statusBar().showMessage("وضع مستقل")

    def open_calculator(self):
        if self._calc is None:
            self._calc = Calculator(self)
        self._calc.show()
        self._calc.raise_()
        self._calc.activateWindow()

    def print_last(self):
        sale, items = (db.get_sale_by_invoice(self.last_invoice) if self.last_invoice else db.last_sale())
        if not sale:
            QMessageBox.information(self, "ALASIL", "لا توجد تذكرة للطباعة")
            return
        receipt_mod.show_and_print(self, sale, items, self.user["display_name"], self.lang)

    def first_allowed_page(self):
        for key, pg in getattr(self, "_nav_map", []):
            if self.can(key):
                return pg
        return 0

    def goto_page(self, p):
        key_for = None
        for key, pg in self._nav_map:
            if pg == p:
                key_for = key
                break
        if key_for and not self.can(key_for):
            QMessageBox.warning(self, "صلاحيات", "ليس لديك صلاحية لفتح هذا القسم. اطلب من المدير تفعيلها.")
            return
        self.pages.setCurrentIndex(p)
        title = "نقطة البيع"
        for key, pg in self._nav_map:
            if pg == p:
                title = self.nav_label(key)
                break
        if hasattr(self, "page_chip"):
            self.page_chip.setText("▸  " + title)
        self.cart_panel.hide()
        if p == 1:
            self.reload_products_table()
        elif p == 2:
            self.reload_cats_table()
        elif p == 3:
            self.reload_sales_table()
        elif p == 4:
            self.reload_reports()
        elif p == 5:
            self.reload_customers()
        elif p == 6:
            self.reload_specs()
        elif p == 7:
            self.admin_hub.refresh_all()
        elif p == 8:
            self.reload_settings()
        elif p == 9:
            self.ws_page.reload()

    def on_page(self, p):
        self.cart_panel.hide()

    def do_return(self):
        self.goto_page(3)

    def focus_pos_search(self):
        self.search.setFocus()
        self.search.selectAll()
        self.open_catalog()

    def open_catalog(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("بحث المنتجات  F3")
        dlg.resize(720, 520)
        lay = QVBoxLayout(dlg)
        cats = QWidget()
        row = QHBoxLayout(cats)
        self._cat_box = row
        for c in db.fetch_categories():
            b = QPushButton(c["name_ar"])
            b.clicked.connect(lambda _, i=c["id"], d=dlg: (self.set_cat(i), None))
            row.addWidget(b)
        row.addStretch()
        lay.addWidget(cats)
        lay.addWidget(self.prod_scroll, 1)
        self.prod_scroll.show()
        self.refresh_products()
        dlg.exec()
        self.prod_scroll.setParent(self.pos_page)
        self.prod_scroll.hide()

    def delete_selected_cart(self):
        r = self.cart_table.currentRow()
        if r < 0 and self.cart:
            r = len(self.cart) - 1
        self.remove_item(r)

    def edit_selected_qty(self):
        r = self.cart_table.currentRow()
        if r < 0 or r >= len(self.cart):
            QMessageBox.information(self, "كمية", "اختر سطراً من التذكرة")
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("الكمية F4")
        f = QFormLayout(dlg)
        sp = QDoubleSpinBox(); sp.setRange(0.001, 1e7); sp.setDecimals(3)
        sp.setValue(float(self.cart[r]["qty"]))
        f.addRow("الكمية", sp)
        ok = QPushButton("موافق"); ok.clicked.connect(dlg.accept); f.addRow(ok)
        if dlg.exec() == QDialog.Accepted:
            self.cart[r]["qty"] = sp.value()
            if self.cart[r]["qty"] <= 0:
                self.cart.pop(r)
            self.refresh_cart()

    def ask_discount(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("خصم F2")
        f = QFormLayout(dlg)
        sp = QDoubleSpinBox(); sp.setRange(0, 1e7); sp.setDecimals(2)
        sp.setValue(float(self.discount or 0))
        f.addRow("قيمة الخصم", sp)
        ok = QPushButton("تطبيق"); ok.clicked.connect(dlg.accept); f.addRow(ok)
        if dlg.exec() == QDialog.Accepted:
            self.discount = sp.value()
            self.refresh_cart()

    def do_pay_method(self, method):
        self._force_pay_method = method
        self.do_pay()
        self._force_pay_method = None

    def lock_pos(self):
        QMessageBox.information(self, "قفل", "تم قفل الصندوق. أدخل PIN من شاشة الدخول للمتابعة.")
        self.close()

    def open_pos_more(self):
        m = QMenu(self)
        m.addAction("حاسبة", self.open_calculator)
        m.addAction("طباعة آخر تذكرة", self.print_last)
        m.addAction("سجل المبيعات", lambda: self.goto_page(3))
        m.addAction("ماسح الهاتف", self.open_phone_scanner)
        m.exec(QCursor.pos())

    def do_hold(self):
        if not self.cart:
            QMessageBox.information(self, "ALASIL", self.t("no_items"))
            return
        db.save_hold(self.user["id"], self.cart, self.discount)
        self.cart = []
        self.refresh_cart()
        QMessageBox.information(self, "ALASIL", self.t("held"))
        self.reload_holds()

    def clear_cart(self):
        self.cart = []
        self.refresh_cart()

    def refresh_stats(self):
        n, s = db.sales_today()
        sold = 0
        try:
            import database as _d
            conn = _d.get_conn()
            row = conn.execute(
                "SELECT COALESCE(SUM(qty),0) q FROM sale_items si JOIN sales sl ON sl.id=si.sale_id WHERE sl.status='completed'"
            ).fetchone()
            sold = int(row[0] if not hasattr(row, "keys") else row["q"])
            conn.close()
        except Exception:
            sold = 0
        try:
            profit = db.profit_report("day").get("net", 0)
        except Exception:
            profit = 0
        self.stat_sales._val.setText(f"{s:,.2f} د.ج")
        self.stat_inv._val.setText(str(n))
        self.stat_stock._val.setText(f"{sold:,}")
        if hasattr(self, "stat_profit"):
            self.stat_profit._val.setText(f"{profit:,.2f} د.ج")

    def build_products_page(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        top = QHBoxLayout()
        title = QLabel(self.t("products"))
        title.setObjectName("pageTitle")
        add = QPushButton("+  " + self.t("add_product"))
        add.setStyleSheet("background:#1e5cff;color:white;border:none;border-radius:12px;padding:8px 16px;font-weight:700;")
        add.clicked.connect(lambda: self.edit_product())
        top.addWidget(title)
        top.addStretch()
        top.addWidget(add)
        lay.addLayout(top)
        self.prod_table = QTableWidget(0, 12)
        self.prod_table.setHorizontalHeaderLabels(
            ["SKU", self.t("barcode"), self.t("name_ar"), self.t("category"),
             "تجزئة", "وحدة", "مخزون",
             "سعر الجملة", "وحدة الجملة", "حد الجملة", "انتهاء الصلاحية", ""]
        )
        self.prod_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.prod_table.setStyleSheet("QTableWidget{background:#2b2f36;color:#dce3ec;border:1px solid #3d434c;} QHeaderView::section{color:#c5ccd6;background:#32363e;padding:6px;}")
        lay.addWidget(self.prod_table)
        self.prod_totals = QLabel()
        self.prod_totals.setWordWrap(True)
        self.prod_totals.setStyleSheet(
            "background:#0d3480;color:white;border-radius:14px;padding:12px 16px;font-weight:800;"
        )
        lay.addWidget(self.prod_totals)
        self.reload_products_table()
        return w

    def reload_products_table(self):
        rows = db.all_products()
        self.prod_table.setRowCount(len(rows))
        for i, p in enumerate(rows):
            lock = "🔒 " if p.get("price_locked", 1) else ""
            exp = (p.get("expiry_date") or "").strip() or "—"
            wp = float(p.get("wholesale_price") or 0)
            wtxt = f"{wp:.2f}" if wp else "—"
            wun = (p.get("wholesale_unit") or p.get("unit") or "—")
            wmn = p.get("wholesale_min") or 0
            vals = [
                p.get("sku") or "", p.get("barcode") or "", p["name_ar"], p.get("cat_ar") or "",
                lock + f"{p['price']:.2f}", p.get("unit") or "", str(p.get("stock") or 0),
                wtxt, wun, str(wmn) if wp else "—", exp,
            ]
            for c, v in enumerate(vals):
                it = QTableWidgetItem(v)
                if c == 10 and p.get("expiry_date"):
                    try:
                        from datetime import date as _d
                        ed = _d.fromisoformat(str(p["expiry_date"])[:10])
                        if ed < _d.today():
                            it.setForeground(QColor("#ef4444"))
                        elif (ed - _d.today()).days <= 30:
                            it.setForeground(QColor("#f59e0b"))
                    except Exception:
                        pass
                self.prod_table.setItem(i, c, it)
            btn = QPushButton("✎")
            btn.clicked.connect(lambda _, x=p: self.edit_product(x))
            self.prod_table.setCellWidget(i, 11, btn)
        n = len(rows)
        active = [p for p in rows if p.get("active", 1)]
        val_sale = sum(float(p.get("price") or 0) * float(p.get("stock") or 0) for p in active)
        val_cost = sum(float(p.get("cost") or 0) * float(p.get("stock") or 0) for p in active)
        sum_prices = sum(float(p.get("price") or 0) for p in active)
        stock_qty = sum(float(p.get("stock") or 0) for p in active)
        if hasattr(self, "prod_totals"):
            self.prod_totals.setText(
                f"المنتجات: {n}   |   مجموع أسعار الوحدات: {sum_prices:,.2f} د.ج   |   "
                f"كمية المخزون: {stock_qty:g}   |   قيمة المخزون بسعر البيع: {val_sale:,.2f} د.ج   |   "
                f"قيمة المخزون بالتكلفة: {val_cost:,.2f} د.ج"
            )

    def edit_product(self, p=None):
        if not self.can("products"):
            QMessageBox.warning(self, "صلاحيات", "الموظف لا يعدّل المنتجات. اطلب من المدير.")
            return
        try:
            self._edit_product_dialog(p)
        except Exception as e:
            QMessageBox.critical(self, "منتج", f"تعذر فتح نافذة المنتج:\n{e}")

    def _edit_product_dialog(self, p=None):
        dlg = QDialog(self)
        dlg.setWindowTitle(self.t("add_product") if not p else "تعديل منتج")
        geo = self.screen().availableGeometry() if self.screen() else None
        if geo:
            dlg.setMinimumSize(min(480, geo.width() - 40), min(360, geo.height() - 40))
            dlg.resize(min(780, geo.width() - 40), min(700, geo.height() - 40))
        else:
            dlg.setMinimumSize(480, 360)
            dlg.resize(720, 600)
        dlg.setModal(True)
        wrap = QVBoxLayout(dlg)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        outer = QVBoxLayout(inner)
        f = QFormLayout()
        outer.addLayout(f)
        sku = QLineEdit("" if not p else str(p.get("sku") or ""))
        bar = QLineEdit("" if not p else str(p.get("barcode") or ""))
        na = QLineEdit("" if not p else str(p.get("name_ar") or ""))
        nf = QLineEdit("" if not p else str(p.get("name_fr") or ""))
        cat = QComboBox()
        try:
            cats = [c for c in db.fetch_categories() if c["id"] != 1]
        except Exception:
            cats = []
        if not cats:
            cat.addItem("عام", 2)
        else:
            for c in cats:
                cat.addItem(c["name_ar"], c["id"])
        if p:
            idx = cat.findData(p.get("category_id"))
            if idx >= 0:
                cat.setCurrentIndex(idx)
        price = QDoubleSpinBox(); price.setRange(0, 1e7); price.setDecimals(2)
        price.setValue(float(p["price"]) if p else 0)
        cost = QDoubleSpinBox(); cost.setRange(0, 1e7); cost.setDecimals(2)
        cost.setValue(float(p.get("cost") or 0) if p else 0)
        stock = QSpinBox(); stock.setRange(0, 10_000_000)
        stock.setValue(int(float(p.get("stock") or 0)) if p else 0)
        unit = QComboBox(); unit.setEditable(True)
        try:
            units = db.list_units()
        except Exception:
            units = []
        if not units:
            for name in ("قطعة", "علبة", "كيس", "كلغ", "عرام", "متر"):
                unit.addItem(name)
        else:
            for u in units:
                unit.addItem(u["name_ar"], u)
        if p and p.get("unit"):
            i = unit.findText(p["unit"])
            if i >= 0:
                unit.setCurrentIndex(i)
            else:
                unit.setEditText(p["unit"])
        else:
            i = unit.findText("قطعة")
            if i >= 0:
                unit.setCurrentIndex(i)
        emoji = QLineEdit(p["emoji"] if p else "📦")
        for lab, wdg in [
            ("SKU", sku), (self.t("barcode"), bar), (self.t("name_ar"), na),
            ("Nom FR", nf), (self.t("category"), cat), ("سعر التجزئة", price),
            (self.t("cost"), cost),
            (self.t("stock"), stock), (self.t("unit"), unit), ("أيقونة", emoji),
        ]:
            f.addRow(lab, wdg)
        exp_on = QCheckBox("لهذا المنتج تاريخ انتهاء صلاحية")
        exp = QDateEdit()
        exp.setCalendarPopup(True)
        exp.setDisplayFormat("yyyy-MM-dd")
        exp.setDate(QDate.currentDate().addMonths(6))
        ed = (p.get("expiry_date") or "").strip() if p else ""
        if ed:
            qd = QDate.fromString(ed[:10], "yyyy-MM-dd")
            if qd.isValid():
                exp.setDate(qd)
                exp_on.setChecked(True)
        exp.setEnabled(exp_on.isChecked())
        exp_on.toggled.connect(exp.setEnabled)
        f.addRow(exp_on)
        f.addRow("تاريخ الانتهاء", exp)

        ws_box = QGroupBox("البيع بالجملة — السعر ووحدة الجملة")
        ws_box.setStyleSheet(
            "QGroupBox{font-weight:800;color:#e8edf5;border:2px solid #2ea44f;"
            "border-radius:10px;margin-top:10px;padding:12px;}"
            "QGroupBox::title{subcontrol-origin:margin;right:12px;padding:0 6px;color:#39ff14;}"
        )
        ws_f = QFormLayout(ws_box)
        ws_on = QCheckBox("تفعيل البيع بالجملة لهذا المنتج")
        wp0 = float(p.get("wholesale_price") or 0) if p else 0
        ws_on.setChecked(bool(p and wp0 > 0) or not p)
        wprice = QDoubleSpinBox(); wprice.setRange(0, 1e7); wprice.setDecimals(2)
        wprice.setSuffix(" د.ج")
        if wp0:
            wprice.setValue(wp0)
        elif p:
            wprice.setValue(round(float(p["price"]) * 0.85, 2))
        wmin = QDoubleSpinBox(); wmin.setRange(0, 1e7); wmin.setDecimals(3)
        wmin.setValue(float(p.get("wholesale_min") or 5) if p else 5)
        wunit = QComboBox(); wunit.setEditable(True)
        for name in ("قطعة", "علبة", "كيس", "كلغ", "عرام", "متر", "كرتون", "صندوق"):
            wunit.addItem(name)
        wu0 = (p.get("wholesale_unit") or p.get("unit") or "قطعة") if p else "قطعة"
        iwu = wunit.findText(wu0)
        if iwu >= 0:
            wunit.setCurrentIndex(iwu)
        else:
            wunit.setEditText(wu0)
        hint = QLabel("وحدة الجملة قد تختلف عن التجزئة (مثلاً قطعة للبيع وكرتون للجملة). إن بقي السعر 0 يُحسب 85٪ من التجزئة.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#9aa3ad;font-size:13px;")
        def fill_ws():
            if ws_on.isChecked() and wprice.value() <= 0 and price.value() > 0:
                wprice.setValue(round(price.value() * 0.85, 2))
            on = ws_on.isChecked()
            wprice.setEnabled(on)
            wmin.setEnabled(on)
            wunit.setEnabled(on)
        ws_on.toggled.connect(fill_ws)
        price.valueChanged.connect(lambda _: fill_ws() if ws_on.isChecked() and not (p and wp0) else None)
        fill_ws()
        ws_f.addRow(ws_on)
        ws_f.addRow("سعر الجملة", wprice)
        ws_f.addRow("وحدة الجملة", wunit)
        ws_f.addRow("الحد الأدنى للكمية", wmin)
        ws_f.addRow(hint)
        outer.addWidget(ws_box)
        is_admin = (self.user.get("role") == "admin")
        locked = bool(p and p.get("price_locked", 1))
        unlock_flag = {"ok": not locked}
        if p and locked:
            for wdg in (price, cost, wprice, wmin):
                wdg.setEnabled(False)
            warn = QLabel("🔒 أسعار هذا المنتج محمية. الموظف لا يغيّرها. المدير يفك القفل بكلمة السر.")
            warn.setWordWrap(True)
            warn.setStyleSheet("color:#b45309;font-weight:700;")
            f.addRow(warn)
            if is_admin:
                ubtn = QPushButton("فك حماية السعر (كلمة سر المدير)")
                def do_unlock():
                    pin_d = QDialog(dlg)
                    pin_d.setWindowTitle("PIN")
                    fl = QFormLayout(pin_d)
                    pe = QLineEdit(); pe.setEchoMode(QLineEdit.Password)
                    fl.addRow("كلمة سر المدير", pe)
                    okb = QPushButton("تأكيد")
                    def chk():
                        u = db.authenticate_user("admin", pe.text())
                        if not u:
                            u = db.authenticate_user(self.user.get("username") or "", pe.text())
                        if u and u.get("role") == "admin":
                            unlock_flag["ok"] = True
                            for wdg in (price, cost, wprice, wmin):
                                wdg.setEnabled(True)
                            pin_d.accept()
                        else:
                            QMessageBox.warning(pin_d, "حماية", "رمز غير صحيح أو ليس مديراً")
                    okb.clicked.connect(chk)
                    fl.addRow(okb)
                    pin_d.exec()
                ubtn.clicked.connect(do_unlock)
                f.addRow(ubtn)
        save = QPushButton(self.t("save"))
        save.setStyleSheet("background:#1e5cff;color:white;padding:8px;border-radius:8px;")

        def go():
            if not na.text().strip():
                QMessageBox.warning(dlg, "منتج", "أدخل اسم المنتج")
                return
            cid = cat.currentData()
            if cid is None and cat.count():
                cid = cat.itemData(0)
            if cid is None:
                cid = 1
            data = {
                "sku": sku.text().strip(), "barcode": bar.text().strip(),
                "name_ar": na.text().strip(), "name_fr": (nf.text().strip() or na.text().strip()),
                "category_id": cid, "price": price.value(), "cost": cost.value(),
                "stock": stock.value(), "unit": unit.currentText().strip() or "قطعة", "emoji": emoji.text() or "📦",
                "wholesale_price": (wprice.value() or round(price.value() * 0.85, 2)) if ws_on.isChecked() else 0,
                "wholesale_min": wmin.value() if ws_on.isChecked() else 0,
                "wholesale_unit": wunit.currentText().strip() if ws_on.isChecked() else "",
                "price_locked": 1,
                "unlock_prices": bool(unlock_flag["ok"] and is_admin),
                "expiry_date": exp.date().toString("yyyy-MM-dd") if exp_on.isChecked() else "",
            }
            if p and locked and not unlock_flag["ok"]:
                data["unlock_prices"] = False
            try:
                db.upsert_product(data, p["id"] if p else None)
            except Exception as err:
                QMessageBox.critical(dlg, "منتج", f"تعذر الحفظ:\n{err}")
                return
            dlg.accept()
            self.reload_products_table()
            self.refresh_products()
            self.refresh_stats()
            self.rebuild_cats()
            QMessageBox.information(self, "منتج", "تم حفظ المنتج")

        save.clicked.connect(go)
        outer.addWidget(save)
        scroll.setWidget(inner)
        wrap.addWidget(scroll, 1)
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()
        dlg.exec()

    def build_sales_page(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        title = QLabel("قسم الفاتورة")
        title.setObjectName("pageTitle")
        lay.addWidget(title)
        lay.addWidget(QLabel("نماذج الفاتورة — اختر النموذج ثم معاينة أو طباعة"))
        tpl_row = QHBoxLayout()
        self.inv_tpl = db.get_setting("invoice_template", "teal") or "teal"
        self._tpl_btns = []
        for t in receipt_mod.TEMPLATES:
            b = QPushButton(t["name"] + "\n" + t["desc"])
            b.setCheckable(True)
            b.setMinimumHeight(64)
            b.setChecked(t["id"] == self.inv_tpl)
            b.clicked.connect(lambda _, i=t["id"]: self.set_invoice_template(i))
            tpl_row.addWidget(b)
            self._tpl_btns.append((t["id"], b))
        lay.addLayout(tpl_row)
        prev = QHBoxLayout()
        pv = QPushButton("معاينة النموذج")
        pv.clicked.connect(self.preview_invoice_template)
        pr = QPushButton("طباعة الفاتورة المحددة بالنموذج")
        pr.clicked.connect(self.print_selected_invoice)
        prev.addWidget(pv)
        prev.addWidget(pr)
        lay.addLayout(prev)
        bar = QHBoxLayout()
        self.inv_search = QLineEdit()
        self.inv_search.setPlaceholderText("بحث رقم فاتورة / تاريخ...")
        self.inv_search.textChanged.connect(self.reload_sales_table)
        bar.addWidget(self.inv_search, 1)
        go_pos = QPushButton("فاتورة بيع جديدة")
        go_pos.clicked.connect(lambda: self.goto_page(0))
        bar.addWidget(go_pos)
        lay.addLayout(bar)
        split = QSplitter(Qt.Horizontal)
        self.sales_table = QTableWidget(0, 8)
        self.sales_table.setHorizontalHeaderLabels(
            [self.t("invoice"), "Date", self.t("total"), self.t("paid"), "الحالة", "طريقة", "طباعة", "إرجاع"]
        )
        self.sales_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.sales_table.setStyleSheet("QTableWidget{background:#2b2f36;color:#dce3ec;border:1px solid #3d434c;} QHeaderView::section{color:#c5ccd6;background:#32363e;padding:6px;}")
        self.sales_table.itemSelectionChanged.connect(self.show_invoice_detail)
        split.addWidget(self.sales_table)
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.addWidget(QLabel("تفاصيل الفاتورة"))
        self.inv_detail = QLabel("اختر فاتورة لعرض البنود")
        self.inv_detail.setWordWrap(True)
        rl.addWidget(self.inv_detail)
        self.inv_items = QTableWidget(0, 4)
        self.inv_items.setHorizontalHeaderLabels(["صنف", "كمية", "سعر", "مجموع"])
        self.inv_items.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        rl.addWidget(self.inv_items, 1)
        split.addWidget(right)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        lay.addWidget(split, 1)
        self.reload_sales_table()
        return w

    def reload_sales_table(self):
        rows = db.recent_sales(200)
        q = (self.inv_search.text().strip() if hasattr(self, "inv_search") else "").lower()
        if q:
            rows = [s for s in rows if q in str(s.get("invoice_no") or "").lower() or q in str(s.get("created_at") or "")]
        self.sales_table.setColumnCount(8)
        self.sales_table.setHorizontalHeaderLabels(
            [self.t("invoice"), "Date", self.t("total"), self.t("paid"), "الحالة", "طريقة", "طباعة", "إرجاع"]
        )
        self.sales_table.setRowCount(len(rows))
        self._sales_rows = rows
        for i, s in enumerate(rows):
            st = {"completed": "مكتمل", "returned": "مرتجع", "held": "معلّق"}.get(s.get("status"), s.get("status"))
            vals = [s["invoice_no"], s["created_at"], f"{s['total']:.2f}", f"{s['paid']:.2f}", st, s["payment_method"] or ""]
            for c, v in enumerate(vals):
                self.sales_table.setItem(i, c, QTableWidgetItem(str(v)))
            pb = QPushButton("🖨")
            pb.clicked.connect(lambda _, inv=s["invoice_no"]: self.print_invoice(inv))
            self.sales_table.setCellWidget(i, 6, pb)
            rb = QPushButton("↩")
            rb.setEnabled(s.get("status") != "returned")
            rb.clicked.connect(lambda _, inv=s["invoice_no"]: self.return_invoice(inv))
            self.sales_table.setCellWidget(i, 7, rb)

    def show_invoice_detail(self):
        r = self.sales_table.currentRow()
        rows = getattr(self, "_sales_rows", [])
        if r < 0 or r >= len(rows):
            return
        inv = rows[r]["invoice_no"]
        sale, items = db.get_sale_by_invoice(inv)
        if not sale:
            return
        self.inv_detail.setText(
            "فاتورة {no}\nالتاريخ: {dt}\nالإجمالي: {tot:.2f} د.ج   المدفوع: {paid:.2f}\nالطريقة: {pm}   الحالة: {st}".format(
                no=sale["invoice_no"], dt=sale["created_at"], tot=sale["total"],
                paid=sale["paid"], pm=sale.get("payment_method") or "—", st=sale.get("status"),
            )
        )
        self.inv_items.setRowCount(len(items or []))
        for i, it in enumerate(items or []):
            for c, v in enumerate([it.get("name"), it.get("qty"), it.get("price"), it.get("total")]):
                self.inv_items.setItem(i, c, QTableWidgetItem(str(v)))

    def set_invoice_template(self, tid):
        self.inv_tpl = tid
        db.set_setting("invoice_template", tid)
        for i, b in self._tpl_btns:
            b.setChecked(i == tid)

    def preview_invoice_template(self):
        sale, items = None, []
        r = self.sales_table.currentRow() if hasattr(self, "sales_table") else -1
        rows = getattr(self, "_sales_rows", [])
        if 0 <= r < len(rows):
            sale, items = db.get_sale_by_invoice(rows[r]["invoice_no"])
        if not sale:
            sale, items = receipt_mod.sample_sale()
        receipt_mod.show_and_print(
            self, sale, items, self.user["display_name"], self.lang, template=self.inv_tpl
        )

    def print_selected_invoice(self):
        r = self.sales_table.currentRow()
        rows = getattr(self, "_sales_rows", [])
        if r < 0 or r >= len(rows):
            QMessageBox.information(self, "فاتورة", "اختر فاتورة من الجدول أو استخدم معاينة النموذج")
            return
        self.print_invoice(rows[r]["invoice_no"])

    def print_invoice(self, inv):
        sale, items = db.get_sale_by_invoice(inv)
        if sale:
            receipt_mod.show_and_print(
                self, sale, items, self.user["display_name"], self.lang,
                template=getattr(self, "inv_tpl", None),
            )

    def return_invoice(self, inv):
        if QMessageBox.question(self, "إرجاع", f"إرجاع الفاتورة {inv} وإعادة المخزون؟") != QMessageBox.Yes:
            return
        if db.return_sale(inv):
            QMessageBox.information(self, "ALASIL", "تم الإرجاع وإعادة الكميات للمخزون")
            self.reload_sales_table()
            self.refresh_products()
            self.refresh_stats()
            self.reload_reports()
        else:
            QMessageBox.warning(self, "ALASIL", "لا يمكن إرجاع هذه الفاتورة")

    def build_cats_page(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        top = QHBoxLayout()
        title = QLabel("التصنيفات")
        title.setObjectName("pageTitle")
        add = QPushButton("+ تصنيف جديد")
        add.setStyleSheet("background:#1e5cff;color:white;border:none;border-radius:12px;padding:8px 16px;font-weight:700;")
        add.clicked.connect(lambda: self.edit_category())
        top.addWidget(title); top.addStretch(); top.addWidget(add)
        lay.addLayout(top)
        self.cat_table = QTableWidget(0, 4)
        self.cat_table.setHorizontalHeaderLabels(["#", "العربية", "Français", ""])
        self.cat_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.cat_table.setStyleSheet("QTableWidget{background:#2b2f36;color:#dce3ec;border:1px solid #3d434c;} QHeaderView::section{color:#c5ccd6;background:#32363e;padding:6px;}")
        lay.addWidget(self.cat_table)
        hint = QLabel("التصنيفات تظهر في شريط نقطة البيع. المنتجات الجديدة تُربط بتصنيف من هنا.")
        hint.setStyleSheet("color:#64748b;")
        lay.addWidget(hint)
        self.reload_cats_table()
        return w

    def reload_cats_table(self):
        rows = db.fetch_categories()
        self.cat_table.setRowCount(len(rows))
        for i, c in enumerate(rows):
            self.cat_table.setItem(i, 0, QTableWidgetItem(str(c["id"])))
            self.cat_table.setItem(i, 1, QTableWidgetItem(c["name_ar"]))
            self.cat_table.setItem(i, 2, QTableWidgetItem(c["name_fr"]))
            box = QWidget()
            h = QHBoxLayout(box); h.setContentsMargins(0, 0, 0, 0)
            e = QPushButton("✎"); e.clicked.connect(lambda _, x=c: self.edit_category(x))
            d = QPushButton("✕"); d.setEnabled(c["id"] != 1)
            d.clicked.connect(lambda _, x=c["id"]: self.del_category(x))
            h.addWidget(e); h.addWidget(d)
            self.cat_table.setCellWidget(i, 3, box)

    def edit_category(self, c=None):
        dlg = QDialog(self); dlg.setWindowTitle("تصنيف"); dlg.setMinimumWidth(340)
        f = QFormLayout(dlg)
        ar = QLineEdit(c["name_ar"] if c else "")
        fr = QLineEdit(c["name_fr"] if c else "")
        col = QLineEdit(c["color"] if c else "#1A4B8C")
        f.addRow("العربية", ar); f.addRow("Français", fr); f.addRow("لون", col)
        s = QPushButton(self.t("save"))
        s.setStyleSheet("background:#1e5cff;color:white;padding:8px;border-radius:8px;")
        def go():
            if not ar.text().strip():
                return
            db.upsert_category(ar.text().strip(), fr.text().strip() or ar.text(), col.text(), c["id"] if c else None)
            dlg.accept()
            self.reload_cats_table()
            self.rebuild_cats()
            self.refresh_products()
            self.reload_products_table()
        s.clicked.connect(go); f.addRow(s); dlg.exec()

    def del_category(self, cid):
        if QMessageBox.question(self, "حذف", "حذف التصنيف؟ المنتجات تُنقل إلى مواد غذائية.") != QMessageBox.Yes:
            return
        db.delete_category(cid)
        if self.cat_id == cid:
            self.cat_id = 1
        self.reload_cats_table()
        self.rebuild_cats()
        self.refresh_products()
        self.reload_products_table()

    def build_reports_page(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        self.rep_title = QLabel(self.t("reports"))
        self.rep_title.setObjectName("pageTitle")
        lay.addWidget(self.rep_title)
        self.rep_summary = QLabel()
        self.rep_summary.setWordWrap(True)
        self.rep_summary.setStyleSheet("background:#32363e;border-radius:4px;padding:16px;color:#e8edf5;font-size:14px;")
        lay.addWidget(self.rep_summary)
        self.rep_cat = QTableWidget(0, 3)
        self.rep_cat.setHorizontalHeaderLabels(["التصنيف", "المبيعات", "عدد الأسطر"])
        self.rep_cat.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.rep_cat.setStyleSheet("QTableWidget{background:#2b2f36;color:#dce3ec;border:1px solid #3d434c;} QHeaderView::section{color:#c5ccd6;background:#32363e;padding:6px;}")
        lay.addWidget(self.rep_cat)
        self.rep_low = QTableWidget(0, 3)
        self.rep_low.setHorizontalHeaderLabels(["منتج ناقص", "المخزون", "سعر"])
        self.rep_low.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.rep_low.setStyleSheet("QTableWidget{background:#2b2f36;color:#dce3ec;border:1px solid #3d434c;} QHeaderView::section{color:#c5ccd6;background:#32363e;padding:6px;}")
        lay.addWidget(self.rep_low)
        return w

    def reload_reports(self):
        r = db.report_overview()
        pay = "، ".join(f"{x.get('payment_method')}: {x['s']:.0f} ({x['n']})" for x in r["by_pay"]) or "—"
        self.rep_summary.setText(
            f"<b>اليوم:</b> {r['today_n']} فاتورة — {r['today_s']:,.2f} د.ج<br>"
            f"<b>كل المبيعات:</b> {r['all_n']} — {r['all_s']:,.2f} د.ج<br>"
            f"<b>حسب الدفع:</b> {pay}"
        )
        self.rep_cat.setRowCount(len(r["by_cat"]))
        for i, x in enumerate(r["by_cat"]):
            self.rep_cat.setItem(i, 0, QTableWidgetItem(x["name_ar"]))
            self.rep_cat.setItem(i, 1, QTableWidgetItem(f"{x['s']:.2f}"))
            self.rep_cat.setItem(i, 2, QTableWidgetItem(str(x["n"])))
        self.rep_low.setRowCount(len(r["low"]))
        for i, p in enumerate(r["low"]):
            self.rep_low.setItem(i, 0, QTableWidgetItem(p["name_ar"]))
            self.rep_low.setItem(i, 1, QTableWidgetItem(str(p["stock"])))
            self.rep_low.setItem(i, 2, QTableWidgetItem(f"{p['price']:.2f}"))

    def _settings_group(self, title):
        g = QGroupBox(title)
        g.setStyleSheet(
            "QGroupBox{background:white;border:1px solid #d5e4f7;border-radius:14px;margin-top:12px;"
            "padding:16px 12px 12px 12px;font-weight:800;color:#0d3480;}"
            "QGroupBox::title{subcontrol-origin: margin; right: 16px; padding: 0 8px;}"
        )
        return g

    def build_settings_page(self):
        w = QWidget()
        outer = QVBoxLayout(w)
        title = QLabel(self.t("settings"))
        title.setObjectName("pageTitle")
        outer.addWidget(title)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setSpacing(10)

        g1 = self._settings_group("1) بيانات المتجر")
        f1 = QFormLayout(g1)
        self.set_store = QLineEdit()
        self.set_phone = QLineEdit()
        self.set_city = QLineEdit()
        self.set_tax = QDoubleSpinBox(); self.set_tax.setRange(0, 50); self.set_tax.setSuffix(" %")
        f1.addRow("اسم المتجر", self.set_store)
        f1.addRow("الهاتف", self.set_phone)
        f1.addRow("المدينة", self.set_city)
        f1.addRow("نسبة الضريبة", self.set_tax)
        lay.addWidget(g1)

        g2 = self._settings_group("2) ربط جهازين (شبكة)")
        f2 = QFormLayout(g2)
        self.net_mode = QComboBox()
        self.net_mode.addItems(["مستقل (جهاز واحد)", "خادم (يستقبل الجهاز الآخر)", "عميل (يتصل بالخادم)"])
        self.net_host = QLineEdit()
        self.net_host.setPlaceholderText("IP الخادم مثل 192.168.1.20")
        self.net_port = QSpinBox(); self.net_port.setRange(1024, 65535); self.net_port.setValue(9876)
        self.net_pw = QLineEdit(); self.net_pw.setEchoMode(QLineEdit.Password)
        self.net_pw.setPlaceholderText("كلمة سر الشبكة بين الجهازين")
        f2.addRow("الوضع", self.net_mode)
        f2.addRow("عنوان الخادم", self.net_host)
        f2.addRow("المنفذ", self.net_port)
        f2.addRow("كلمة سر الشبكة", self.net_pw)
        lay.addWidget(g2)

        g3 = self._settings_group("3) العرض وحجم الخط")
        v3 = QVBoxLayout(g3)
        rowf = QHBoxLayout()
        self.font_slider = QSlider(Qt.Horizontal)
        self.font_slider.setRange(15, 26)
        self.font_slider.setValue(int(db.get_setting("font_size", "16") or 16))
        self.font_slider.setTickPosition(QSlider.TicksBelow)
        self.font_slider.setTickInterval(1)
        self.font_val = QLabel(str(self.font_slider.value()))
        self.font_val.setMinimumWidth(36)
        self.font_slider.valueChanged.connect(self.on_font_slide)
        rowf.addWidget(QLabel("صغير"))
        rowf.addWidget(self.font_slider, 1)
        rowf.addWidget(QLabel("كبير"))
        rowf.addWidget(self.font_val)
        v3.addLayout(rowf)
        self.font_preview = QLabel("معاينة: حجم الخط — ALASIL POS  مرحباً")
        self.font_preview.setStyleSheet("background:#32363e;border-radius:4px;padding:14px;color:#e8edf5;")
        v3.addWidget(self.font_preview)
        lay.addWidget(g3)

        g4 = self._settings_group("4) وحدات القياس")
        v4 = QVBoxLayout(g4)
        self.unit_table = QTableWidget(0, 4)
        self.unit_table.setHorizontalHeaderLabels(["العربية", "Français", "كسور؟", "حذف"])
        self.unit_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.unit_table.setMinimumHeight(140)
        self.unit_table.setMaximumHeight(200)
        v4.addWidget(self.unit_table)
        urow = QHBoxLayout()
        self.new_unit_ar = QLineEdit(); self.new_unit_ar.setPlaceholderText("وحدة جديدة مثلاً: دزينة")
        self.new_unit_fr = QLineEdit(); self.new_unit_fr.setPlaceholderText("FR")
        self.new_unit_dec = QComboBox(); self.new_unit_dec.addItems(["عدد صحيح", "كسور (وزن/طول)"])
        ub = QPushButton("إضافة وحدة")
        ub.clicked.connect(self.add_unit)
        urow.addWidget(self.new_unit_ar); urow.addWidget(self.new_unit_fr); urow.addWidget(self.new_unit_dec); urow.addWidget(ub)
        v4.addLayout(urow)
        lay.addWidget(g4)

        g5 = self._settings_group("5) الحساب والترخيص")
        v5 = QVBoxLayout(g5)
        pin_row = QHBoxLayout()
        self.new_pin = QLineEdit(); self.new_pin.setEchoMode(QLineEdit.Password); self.new_pin.setPlaceholderText("كلمة سر جديدة")
        pinb = QPushButton("تغيير كلمة السر")
        pinb.clicked.connect(self.change_pin)
        pin_row.addWidget(self.new_pin); pin_row.addWidget(pinb)
        v5.addLayout(pin_row)
        self.lic_lbl = QLabel()
        self.lic_lbl.setWordWrap(True)
        self.lic_lbl.setStyleSheet("background:#32363e;border-radius:4px;padding:12px;color:#e8edf5;")
        v5.addWidget(self.lic_lbl)
        lay.addWidget(g5)

        g6 = self._settings_group("6) الفواتير المعلّقة")
        v6 = QVBoxLayout(g6)
        self.hold_table = QTableWidget(0, 3)
        self.hold_table.setHorizontalHeaderLabels(["#", "الوقت", "استعادة"])
        self.hold_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.hold_table.setMinimumHeight(120)
        v6.addWidget(self.hold_table)
        lay.addWidget(g6)

        is_admin = bool(
            self.user
            and (
                self.user.get("role") == "admin"
                or self.user.get("username") == "admin"
            )
        )
        if is_admin and db.is_demo_mode():
            self.clear_demo_group = self._settings_group("7) ????? ???????? ?????????")
            demo_layout = QVBoxLayout(self.clear_demo_group)

            demo_info = QLabel(
                "??? ????? ?????? ??????? ????? ??? ?????? ?????? ??????? ????????. "
                "????? ????? ????? ??????? ?????. ?????? ???? ???????? ????????."
            )
            demo_info.setWordWrap(True)
            demo_layout.addWidget(demo_info)

            self.clear_demo_button = QPushButton(
                "??? ???????? ????????? ?????? ?? ????"
            )
            self.clear_demo_button.setStyleSheet(
                "background:#dc2626;color:white;border:none;"
                "border-radius:10px;padding:12px;font-weight:800;"
            )
            self.clear_demo_button.clicked.connect(self.clear_demo_data)
            demo_layout.addWidget(self.clear_demo_button)

            lay.addWidget(self.clear_demo_group)

        save = QPushButton("حفظ كل الإعدادات")
        save.setStyleSheet("background:#22c55e;color:white;border:none;border-radius:12px;padding:12px;font-weight:800;")
        save.clicked.connect(self.save_settings)
        lay.addWidget(save)
        lay.addStretch()
        scroll.setWidget(inner)
        outer.addWidget(scroll, 1)
        return w


    def clear_demo_data(self):
        is_admin = bool(
            self.user
            and (
                self.user.get("role") == "admin"
                or self.user.get("username") == "admin"
            )
        )
        if not is_admin:
            QMessageBox.warning(self, "ALASIL POS", "??? ??????? ????? ?????? ???.")
            return

        if not db.is_demo_mode():
            if hasattr(self, "clear_demo_group"):
                self.clear_demo_group.hide()
            QMessageBox.information(
                self, "ALASIL POS",
                "????? ???????? ?? ??? ???????? ?? ????? ????? ?????."
            )
            return

        answer = QMessageBox.question(
            self,
            "????? ??? ???????? ?????????",
            "?? ???? ??? ???????? ????????? ?????? ?? ?????\n\n"
            "?????? ???? ???????? ???????? ??? ?????.\n"
            "???? ???????? ??????? ?????????? ???????? ?????? ????????.\n"
            "?? ???? ??????? ??? ??????? ???? ?????? ?????? ????????.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return

        try:
            admin_id = self.user.get("id")
            if admin_id is None:
                raise PermissionError("???? ????? ???? ?????? ??????.")

            backup_path = db.clear_demo_data(admin_id)

            if hasattr(self, "clear_demo_group"):
                self.clear_demo_group.hide()

            QMessageBox.information(
                self,
                "?? ??? ???????? ?????????",
                "?? ??? ???????? ????????? ?????.\n"
                "???? ?????? ?????????? ???????? ??????.\n\n"
                f"?????? ??????????:\n{backup_path}\n\n"
                "????? ????? ????? ???????? ?????? ???? ???????."
            )
        except Exception as exc:
            QMessageBox.critical(
                self,
                "??? ????? ?????",
                f"?? ????? ????? ?????.\n\n{exc}"
            )

    def on_font_slide(self, v):
        self.font_val.setText(str(v))
        self.apply_theme(v)

    def reload_settings(self):
        self.set_store.setText(db.get_setting("store_name"))
        self.set_phone.setText(db.get_setting("store_phone"))
        self.set_city.setText(db.get_setting("store_city"))
        try:
            self.set_tax.setValue(db.tax_rate() * 100)
        except Exception:
            self.set_tax.setValue(19)
        m = db.get_setting("net_mode", "local")
        self.net_mode.setCurrentIndex({"local": 0, "server": 1, "client": 2}.get(m, 0))
        self.net_host.setText(db.get_setting("net_host", ""))
        try:
            self.net_port.setValue(int(db.get_setting("net_port", "9876") or 9876))
        except ValueError:
            self.net_port.setValue(9876)
        self.net_pw.setText(db.get_setting("net_password", "123456"))
        try:
            fs = int(db.get_setting("font_size", "13") or 13)
        except ValueError:
            fs = 13
        self.font_slider.blockSignals(True)
        self.font_slider.setValue(fs)
        self.font_slider.blockSignals(False)
        self.font_val.setText(str(fs))
        self.reload_holds()
        self.reload_units_table()
        rec = license_mod.current_license()
        if rec.get("valid") or rec.get("expired") or rec.get("mismatch") or rec.get("tampered"):
            self.lic_lbl.setText(
                f"الترخيص: {'ساري' if rec.get('valid') else 'غير ساري'} — "
                f"ينتهي: {rec.get('expiry')} — الزبون: {rec.get('name') or '—'}"
            )
        else:
            self.lic_lbl.setText("لا يوجد ترخيص مفعّل")

    def reload_units_table(self):
        if not hasattr(self, "unit_table"):
            return
        rows = db.list_units()
        self.unit_table.setRowCount(len(rows))
        for i, u in enumerate(rows):
            self.unit_table.setItem(i, 0, QTableWidgetItem(u["name_ar"]))
            self.unit_table.setItem(i, 1, QTableWidgetItem(u["name_fr"]))
            self.unit_table.setItem(i, 2, QTableWidgetItem("نعم" if u["decimal"] else "لا"))
            b = QPushButton("✕")
            b.clicked.connect(lambda _, x=u["id"]: (db.delete_unit(x), self.reload_units_table()))
            self.unit_table.setCellWidget(i, 3, b)

    def add_unit(self):
        ar = self.new_unit_ar.text().strip()
        if not ar:
            return
        dec = 1 if self.new_unit_dec.currentIndex() == 1 else 0
        db.upsert_unit(ar, self.new_unit_fr.text().strip() or ar, dec)
        self.new_unit_ar.clear(); self.new_unit_fr.clear()
        self.reload_units_table()

    def reload_holds(self):
        if not hasattr(self, "hold_table"):
            return
        rows = db.list_holds()
        self.hold_table.setRowCount(len(rows))
        for i, h in enumerate(rows):
            self.hold_table.setItem(i, 0, QTableWidgetItem(str(h["id"])))
            self.hold_table.setItem(i, 1, QTableWidgetItem(h["created_at"]))
            b = QPushButton("استعادة")
            b.clicked.connect(lambda _, x=h["id"]: self.restore_hold(x))
            self.hold_table.setCellWidget(i, 2, b)

    def restore_hold(self, hid):
        data = db.pop_hold(hid)
        if not data:
            return
        self.cart = data.get("items") or []
        self.discount = data.get("discount") or 0
        self.refresh_cart()
        self.goto_page(0)
        QMessageBox.information(self, "ALASIL", "تمت استعادة السلة")

    def save_settings(self):
        db.set_setting("store_name", self.set_store.text())
        db.set_setting("store_phone", self.set_phone.text())
        db.set_setting("store_city", self.set_city.text())
        db.set_setting("tax_rate", str(self.set_tax.value() / 100.0))
        db.set_setting("font_size", str(self.font_slider.value()))
        modes = ["local", "server", "client"]
        db.set_setting("net_mode", modes[self.net_mode.currentIndex()])
        db.set_setting("net_host", self.net_host.text().strip())
        db.set_setting("net_port", str(self.net_port.value()))
        db.set_setting("net_password", self.net_pw.text().strip() or "123456")
        self.apply_theme(self.font_slider.value())
        self._apply_network()
        self.l_tax.setText(f"الضريبة {self.set_tax.value():.0f}%" if self.lang == "ar" else f"TVA {self.set_tax.value():.0f}%")
        self.refresh_cart()
        QMessageBox.information(self, "ALASIL", "تم حفظ الإعدادات — الضريبة تُطبَّق على الفواتير الجديدة")

    def update_cust_label(self):
        if self.current_customer:
            c = self.current_customer
            self.cust.setText(f"👤  {c['name']}  •  دين {float(c.get('debt') or 0):,.0f} د.ج")
        else:
            self.cust.setText("👤  " + self.t("customer") + " (اضغط للاختيار)")

    def pick_customer(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("اختيار عميل يَدين")
        dlg.setMinimumSize(420, 420)
        lay = QVBoxLayout(dlg)
        s = QLineEdit(); s.setPlaceholderText("بحث بالاسم / الهاتف / الرمز")
        lst = QListWidget()
        lay.addWidget(s); lay.addWidget(lst)

        def fill():
            lst.clear()
            for c in db.list_customers(s.text()):
                it = QListWidgetItem(f"{c['code']} — {c['name']}  |  دين {c['debt']:.0f} / سقف {c['credit_limit']:.0f}")
                it.setData(Qt.UserRole, c["id"])
                lst.addItem(it)
        s.textChanged.connect(fill)
        fill()
        clr = QPushButton("زبون عام (بدون دين)")
        clr.clicked.connect(lambda: (setattr(self, "current_customer", None), self.update_cust_label(), dlg.accept()))
        lay.addWidget(clr)
        def choose():
            it = lst.currentItem()
            if not it:
                return
            self.current_customer = db.get_customer(it.data(Qt.UserRole))
            self.update_cust_label()
            dlg.accept()
        lst.itemDoubleClicked.connect(lambda _: choose())
        ok = QPushButton("اختيار")
        ok.clicked.connect(choose)
        lay.addWidget(ok)
        dlg.exec()

    def build_customers_page(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        top = QHBoxLayout()
        title = QLabel("عملاء يَدين")
        title.setObjectName("pageTitle")
        add = QPushButton("+ إنشاء بطاقة عميل")
        add.setStyleSheet("background:#1e5cff;color:white;border:none;border-radius:12px;padding:8px 16px;font-weight:700;")
        add.clicked.connect(lambda: self.edit_customer())
        self.c_search = QLineEdit(); self.c_search.setPlaceholderText("بحث عن عميل...")
        self.c_search.textChanged.connect(self.reload_customers)
        top.addWidget(title); top.addWidget(self.c_search, 1); top.addWidget(add)
        lay.addLayout(top)
        self.cust_table = QTableWidget(0, 8)
        self.cust_table.setHorizontalHeaderLabels(
            ["الرمز", "الاسم", "الهاتف", "الدين", "السقف", "بطاقة QR", "تسديد", "تعديل"]
        )
        self.cust_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.cust_table.setStyleSheet("QTableWidget{background:#2b2f36;color:#dce3ec;border:1px solid #3d434c;} QHeaderView::section{color:#c5ccd6;background:#32363e;padding:6px;}")
        lay.addWidget(self.cust_table)
        self.led_table = QTableWidget(0, 4)
        self.led_table.setHorizontalHeaderLabels(["التاريخ", "نوع", "المبلغ", "ملاحظة"])
        self.led_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.led_table.setStyleSheet("QTableWidget{background:#2b2f36;color:#dce3ec;border:1px solid #3d434c;} QHeaderView::section{color:#c5ccd6;background:#32363e;padding:6px;}")
        lay.addWidget(QLabel("حركة آخر عميل محدد"))
        lay.addWidget(self.led_table)
        self.reload_customers()
        return w

    def reload_customers(self):
        if not hasattr(self, "cust_table"):
            return
        q = self.c_search.text() if hasattr(self, "c_search") else ""
        rows = db.list_customers(q)
        self.cust_table.setRowCount(len(rows))
        for i, c in enumerate(rows):
            vals = [c["code"], c["name"], c["phone"], f"{c['debt']:.2f}", f"{c['credit_limit']:.2f}"]
            for col, v in enumerate(vals):
                self.cust_table.setItem(i, col, QTableWidgetItem(str(v)))
            bq = QPushButton("بطاقة QR")
            bq.clicked.connect(lambda _, x=c["id"]: self.show_card(x))
            self.cust_table.setCellWidget(i, 5, bq)
            bp = QPushButton("تسديد")
            bp.clicked.connect(lambda _, x=c["id"]: self.pay_customer(x))
            self.cust_table.setCellWidget(i, 6, bp)
            be = QPushButton("✎")
            be.clicked.connect(lambda _, x=c: self.edit_customer(x))
            self.cust_table.setCellWidget(i, 7, be)

    def show_card(self, cid):
        c = db.get_customer(cid)
        if c:
            self._load_ledger(cid)
            CardDialog(c, self).exec()

    def _load_ledger(self, cid):
        rows = db.customer_ledger(cid)
        self.led_table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            kind = "دين" if r["kind"] == "debit" else "تسديد"
            for col, v in enumerate([r["created_at"], kind, f"{r['amount']:.2f}", r["note"] or ""]):
                self.led_table.setItem(i, col, QTableWidgetItem(v))

    def pay_customer(self, cid):
        c = db.get_customer(cid)
        if not c:
            return
        self._load_ledger(cid)
        dlg = QDialog(self); dlg.setWindowTitle("تسديد دين"); dlg.setMinimumWidth(320)
        f = QFormLayout(dlg)
        f.addRow(QLabel(f"{c['name']} — المتبقي {c['debt']:.2f} د.ج"))
        sp = QDoubleSpinBox(); sp.setRange(0, 1e9); sp.setValue(float(c["debt"] or 0))
        f.addRow("المبلغ", sp)
        ok = QPushButton("تأكيد التسديد")
        def go():
            db.pay_debt(cid, sp.value())
            dlg.accept()
            self.reload_customers()
            if self.current_customer and self.current_customer["id"] == cid:
                self.current_customer = db.get_customer(cid)
                self.update_cust_label()
            QMessageBox.information(self, "ALASIL", "تم تسديد المبلغ")
        ok.clicked.connect(go); f.addRow(ok); dlg.exec()

    def edit_customer(self, c=None):
        dlg = QDialog(self)
        dlg.setWindowTitle("بطاقة عميل يَدين")
        dlg.setMinimumWidth(440)
        f = QFormLayout(dlg)
        name = QLineEdit(c["name"] if c else "")
        phone = QLineEdit(c["phone"] if c else "")
        nid = QLineEdit(c["national_id"] if c else "")
        addr = QLineEdit(c["address"] if c else "")
        city = QLineEdit(c["city"] if c else db.get_setting("store_city", "سطيف"))
        lim = QDoubleSpinBox(); lim.setRange(0, 1e9); lim.setValue(c["credit_limit"] if c else 10000)
        notes = QLineEdit(c["notes"] if c else "")
        for lab, wdg in [
            ("الاسم الكامل", name), ("الهاتف", phone), ("رقم التعريف", nid),
            ("العنوان", addr), ("المدينة", city), ("سقف الدين", lim), ("ملاحظات", notes),
        ]:
            f.addRow(lab, wdg)
        save = QPushButton("حفظ وإصدار البطاقة")
        save.setStyleSheet("background:#1e5cff;color:white;padding:10px;border-radius:8px;font-weight:800;")
        def go():
            if not name.text().strip():
                QMessageBox.warning(dlg, "ALASIL", "أدخل اسم العميل")
                return
            data = {
                "name": name.text().strip(), "phone": phone.text().strip(),
                "national_id": nid.text().strip(), "address": addr.text().strip(),
                "city": city.text().strip(), "credit_limit": lim.value(),
                "notes": notes.text().strip(),
            }
            cid = db.upsert_customer(data, c["id"] if c else None)
            self.reload_customers()
            dlg.accept()
            self.show_card(cid)
        save.clicked.connect(go)
        f.addRow(save)
        dlg.exec()

    def build_specs_page(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        top = QHBoxLayout()
        title = QLabel("اختصاصات المتجر")
        title.setObjectName("pageTitle")
        add = QPushButton("+ اختصاص جديد")
        add.setStyleSheet("background:#1e5cff;color:white;border:none;border-radius:12px;padding:8px 16px;font-weight:700;")
        add.clicked.connect(lambda: self.edit_spec())
        top.addWidget(title); top.addStretch(); top.addWidget(add)
        lay.addLayout(top)
        hint = QLabel("كل اختصاص له مكتب صور خاص (غلاف + معرض). مثال: خرداوات، ملابس، مواد غذائية…")
        hint.setStyleSheet("color:#64748b;")
        lay.addWidget(hint)
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        self.specs_host = QWidget()
        self.specs_grid = QGridLayout(self.specs_host)
        self.specs_grid.setSpacing(14)
        scroll.setWidget(self.specs_host)
        lay.addWidget(scroll)
        self.reload_specs()
        return w

    def reload_specs(self):
        if not hasattr(self, "specs_grid"):
            return
        while self.specs_grid.count():
            w = self.specs_grid.takeAt(0).widget()
            if w:
                w.deleteLater()
        specs = db.list_specs()
        cols = 4
        for i, s in enumerate(specs):
            self.specs_grid.addWidget(self._spec_card(s), i // cols, i % cols)

    def _spec_card(self, s):
        f = QFrame()
        f.setObjectName("productCard")
        f.setFixedSize(210, 250)
        v = QVBoxLayout(f)
        cover = QLabel(); cover.setAlignment(Qt.AlignCenter); cover.setFixedHeight(110)
        cover.setStyleSheet(f"background:{s.get('color') or '#0d3480'};border-radius:12px;color:white;font-size:36px;")
        p = resolve_img(s.get("cover") or "")
        if p.is_file():
            cover.setPixmap(QPixmap(str(p)).scaled(190, 105, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation))
        else:
            cover.setText(s.get("emoji") or "🏪")
        v.addWidget(cover)
        n = QLabel(f"{s.get('emoji','')}  {s['name_ar']}")
        n.setStyleSheet("font-weight:800;color:#e8edf5;")
        v.addWidget(n)
        d = QLabel(s.get("notes") or s.get("name_fr") or "")
        d.setStyleSheet("color:#64748b;")
        d.setWordWrap(True)
        v.addWidget(d)
        nimg = len(db.spec_images(s["id"]))
        v.addWidget(QLabel(f"🖼  {nimg} صورة في المكتب"))
        row = QHBoxLayout()
        office = QPushButton("مكتب الصور")
        office.setCursor(Qt.PointingHandCursor)
        office.setStyleSheet("background:#1e5cff;color:white;border:none;border-radius:10px;padding:6px;font-weight:700;")
        office.clicked.connect(lambda _, x=s: self.open_photo_office(x))
        ed = QPushButton("✎")
        ed.clicked.connect(lambda _, x=s: self.edit_spec(x))
        row.addWidget(office, 1); row.addWidget(ed)
        v.addLayout(row)
        return f

    def open_photo_office(self, spec):
        PhotoOffice(spec, self).exec()
        self.reload_specs()

    def edit_spec(self, s=None):
        dlg = QDialog(self)
        dlg.setWindowTitle("اختصاص")
        dlg.setMinimumWidth(400)
        f = QFormLayout(dlg)
        ar = QLineEdit(s["name_ar"] if s else "")
        fr = QLineEdit(s["name_fr"] if s else "")
        em = QLineEdit(s["emoji"] if s else "🏪")
        col = QLineEdit(s["color"] if s else "#1A4B8C")
        notes = QLineEdit(s["notes"] if s else "")
        f.addRow("الاسم عربي", ar)
        f.addRow("Nom FR", fr)
        f.addRow("أيقونة", em)
        f.addRow("لون", col)
        f.addRow("وصف", notes)
        save = QPushButton(self.t("save"))
        save.setStyleSheet("background:#1e5cff;color:white;padding:8px;border-radius:8px;")
        def go():
            if not ar.text().strip():
                return
            db.upsert_spec({
                "name_ar": ar.text().strip(), "name_fr": fr.text().strip() or ar.text(),
                "emoji": em.text() or "🏪", "color": col.text(), "notes": notes.text(),
            }, s["id"] if s else None)
            dlg.accept()
            self.reload_specs()
        save.clicked.connect(go)
        f.addRow(save)
        if s:
            rm = QPushButton("حذف الاختصاص")
            rm.setStyleSheet("color:#b91c1c;")
            rm.clicked.connect(lambda: (db.delete_spec(s["id"]), dlg.accept(), self.reload_specs()))
            f.addRow(rm)
        dlg.exec()

    def change_pin(self):
        pin = self.new_pin.text().strip()
        if len(pin) < 8:
            QMessageBox.warning(self, "ALASIL", "أدخل 8 أحرف على الأقل")
            return
        db.set_user_password(self.user["id"], pin, must_change=False)
        self.new_pin.clear()
        QMessageBox.information(self, "ALASIL", "تم تغيير كلمة السر")

    def set_lang(self, lg):
        self.lang = lg
        self.apply_dir()
        self.btn_ar.setProperty("active", "true" if lg == "ar" else "false")
        self.btn_fr.setProperty("active", "true" if lg == "fr" else "false")
        self.btn_ar.setStyleSheet("background:#2ea44f;color:white;border:none;border-radius:4px;padding:6px 14px;font-weight:700;" if lg == "ar" else "background:#3d434c;color:#e8edf5;border:none;border-radius:4px;padding:6px 14px;font-weight:700;")
        self.btn_fr.setStyleSheet("background:#2ea44f;color:white;border:none;border-radius:4px;padding:6px 14px;font-weight:700;" if lg == "fr" else "background:#3d434c;color:#e8edf5;border:none;border-radius:4px;padding:6px 14px;font-weight:700;")
        # refresh labels
        self.search.setPlaceholderText(self.t("search"))
        self.cart_title.setText(self.t("cart"))
        self.update_cust_label()
        self.empty_lbl.setText(self.t("empty"))
        self.l_sub.setText(self.t("subtotal"))
        self.l_disc.setText(self.t("discount"))
        self.l_tax.setText(self.t("tax"))
        self.l_tot.setText(self.t("total"))
        self.pay_btn.setText("F10\n✓\n" + (self.t("pay") if hasattr(self, "t") else "دفع"))
        self.hold_btn.setText("F9\n💾\nحفظ")
        self.clr_btn.setText("🗑\nإلغاء")
        self.menu_btn.setText("☰   القائمة" if lg == "ar" else "☰  Menu")
        self.rebuild_nav_menu()
        cur = self.pages.currentIndex() if hasattr(self, "pages") else 0
        for key, pg in self._nav_map:
            if pg == cur:
                self.page_chip.setText("▸  " + self.nav_label(key))
                break
        self.stat_sales._lbl.setText(self.t("today_sales"))
        self.stat_inv._lbl.setText(self.t("today_count"))
        self.stat_stock._lbl.setText(self.t("stock"))
        self.user_lbl.setText("●  " + self.user["display_name"] + "   |   " + self.t("online"))
        self.print_btn.setText("🖨\n" + ("طباعة F9" if lg == "ar" else "Print F9"))
        self.ret_btn.setText("↩\nإرجاع")
        self.rebuild_cats()
        self.refresh_products()
        self.refresh_cart()
        self.refresh_stats()
        self.tick()

    def showEvent(self, e):
        super().showEvent(e)
        QTimer.singleShot(0, self._relayout)
        QTimer.singleShot(80, self._relayout)
        QTimer.singleShot(250, self._relayout)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if getattr(self, "_laid", False):
            QTimer.singleShot(40, self._relayout)

    def _relayout(self):
        self._laid = True
        try:
            self.root_lay.activate()
        except Exception:
            pass
        if hasattr(self, "pages"):
            self.pages.updateGeometry()
            cw = self.pages.currentWidget()
            if cw:
                cw.show()
                lay = cw.layout()
                if lay:
                    lay.activate()
                cw.updateGeometry()
        w = max(self.width(), 640)
        last = getattr(self, "_last_w", 0)
        if hasattr(self, "pos_split") and abs(w - last) > 48:
            self._last_w = w
            total = self.pages.width() if self.pages.width() > 200 else w
            frac = 0.46 if w < 1024 else 0.36 if w < 1600 else 0.32
            k = max(200, min(int(total * 0.5), int(total * frac)))
            self.pos_split.setSizes([max(280, total - k), k])
        if hasattr(self, "ticket_stack"):
            self.ticket_stack.update()
        self.refresh_cart()
        self.update()

    def tick(self):
        now = datetime.now()
        if self.lang == "ar":
            days = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]
            months = ["يناير", "فبراير", "مارس", "أبريل", "ماي", "يونيو", "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]
            txt = f"📅  {days[now.weekday()]} {now.day} {months[now.month-1]} {now.year}   ⏱  {now.strftime('%H:%M:%S')}"
        else:
            txt = now.strftime("📅  %A %d %B %Y    ⏱  %H:%M:%S")
        self.clock.setText(txt)


class SplashWindow(QWidget):
    STEPS = [
        (8, "تحضير بيئة التشغيل..."),
        (22, "تجميع ملفات البرنامج..."),
        (40, "تحميل قاعدة البيانات..."),
        (58, "تهيئة النماذج والفواتير..."),
        (74, "تشغيل خدمات الشبكة والماسح..."),
        (88, "تجهيز واجهة نقطة البيع..."),
        (100, "البرنامج جاهز للعمل"),
    ]

    def __init__(self, on_ready):
        super().__init__()
        self.on_ready = on_ready
        self.setWindowTitle("ALASIL POS")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        pal = self.palette()
        pal.setColor(QPalette.Window, QColor("#12151a"))
        self.setAutoFillBackground(True)
        self.setPalette(pal)
        self.resize(640, 380)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(40, 36, 40, 36)
        logo = QLabel("ALASIL POS")
        logo.setAlignment(Qt.AlignCenter)
        logo.setStyleSheet("color:#39ff14;font-size:42px;font-weight:900;")
        sub = QLabel("نظام نقاط البيع — جاري التجميع")
        sub.setAlignment(Qt.AlignCenter)
        sub.setStyleSheet("color:#c5ccd6;font-size:16px;")
        self.msg = QLabel("بدء التشغيل...")
        self.msg.setAlignment(Qt.AlignCenter)
        self.msg.setStyleSheet("color:#9aa3ad;font-size:14px;padding-top:18px;")
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        self.bar.setTextVisible(True)
        self.bar.setFormat("%p%")
        self.bar.setMinimumHeight(22)
        self.bar.setStyleSheet(
            "QProgressBar{background:#2a2e35;border:1px solid #3d434c;border-radius:8px;"
            "color:#fff;font-weight:800;text-align:center;}"
            "QProgressBar::chunk{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            "stop:0 #16a34a, stop:1 #39ff14);border-radius:7px;}"
        )
        lay.addStretch()
        lay.addWidget(logo)
        lay.addWidget(sub)
        lay.addWidget(self.msg)
        lay.addWidget(self.bar)
        lay.addStretch()
        self._i = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(90)

    def _tick(self):
        target, text = self.STEPS[min(self._i, len(self.STEPS) - 1)]
        v = self.bar.value()
        if v < target:
            self.bar.setValue(min(target, v + 2))
            self.msg.setText(text)
            if self.bar.value() in (22, 40):
                try:
                    db.init_db()
                except Exception:
                    pass
            return
        if self._i < len(self.STEPS) - 1:
            self._i += 1
            return
        self._timer.stop()
        QTimer.singleShot(350, self._done)

    def _done(self):
        self.close()
        self.on_ready()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("ALASIL POS")
    try:
        app.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )
    except Exception:
        pass
    font = QFont("Segoe UI", 10)
    app.setFont(font)
    holder = {"win": None, "login": None, "act": None, "splash": None}

    def start(user):
        lg = holder.get("login")
        if lg:
            lg.hide()
        w = MainWindow(user)
        holder["win"] = w
        w.showMaximized()
        w.raise_()
        w.activateWindow()
        QTimer.singleShot(30, w._relayout)
        QTimer.singleShot(200, w._relayout)
        if lg:
            lg.close()

    def after_login(user):
        if license_mod.is_activated():
            start(user)
            return
        if user.get("role") != "admin":
            QMessageBox.warning(None, "تفعيل", "البرنامج غير مفعّل. سجّل دخول المدير (admin) لتفعيل الترخيص.")
            return
        def after_act():
            if holder.get("act"):
                holder["act"].close()
            start(user)
        act = ActivationWindow(after_act)
        holder["act"] = act
        if holder.get("login"):
            holder["login"].hide()
        act.showMaximized()

    def after_splash():
        try:
            db.init_db()
        except Exception:
            pass
        login = LoginWindow(after_login)
        holder["login"] = login
        login.showMaximized()

    splash = SplashWindow(after_splash)
    holder["splash"] = splash
    splash.show()
    qr = splash.frameGeometry()
    cp = QApplication.primaryScreen().availableGeometry().center()
    qr.moveCenter(cp)
    splash.move(qr.topLeft())
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
