import sqlite3
import secrets
from pathlib import Path
from datetime import datetime

import security as sec

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "alasil.db"
DEMO_DB_PATH = ROOT / "alasil_demo.db"


def set_db_path(path):
    global DB_PATH
    DB_PATH = Path(path)


def get_conn():
    conn = sqlite3.connect(str(DB_PATH), timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout=8000")
    try:
        conn.execute("PRAGMA journal_mode=WAL")
    except sqlite3.Error:
        pass
    return conn


def integrity_ok(path=None):
    p = path or DB_PATH
    c = sqlite3.connect(str(p), timeout=10)
    try:
        r = c.execute("PRAGMA integrity_check").fetchone()
        return bool(r and r[0] == "ok"), (r[0] if r else "fail")
    finally:
        c.close()


def backup_db(dest):
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    src = get_conn()
    dst = sqlite3.connect(str(dest))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    ok, msg = integrity_ok(dest)
    if not ok:
        try:
            dest.unlink()
        except OSError:
            pass
        raise RuntimeError(f"النسخة تالفة: {msg}")
    return dest


def init_db():
    db_was_new = (not DB_PATH.exists()) or DB_PATH.stat().st_size == 0
    conn = get_conn()
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            display_name TEXT NOT NULL,
            pin TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'cashier'
        );
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY,
            name_ar TEXT NOT NULL,
            name_fr TEXT NOT NULL,
            color TEXT NOT NULL DEFAULT '#1A4B8C',
            sort_order INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY,
            sku TEXT,
            barcode TEXT,
            name_ar TEXT NOT NULL,
            name_fr TEXT NOT NULL,
            category_id INTEGER REFERENCES categories(id),
            price REAL NOT NULL,
            cost REAL DEFAULT 0,
            stock INTEGER DEFAULT 0,
            unit TEXT DEFAULT 'قطعة',
            emoji TEXT DEFAULT '📦',
            active INTEGER DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS sales (
            id INTEGER PRIMARY KEY,
            invoice_no TEXT UNIQUE,
            created_at TEXT NOT NULL,
            user_id INTEGER,
            subtotal REAL,
            discount REAL DEFAULT 0,
            tax REAL DEFAULT 0,
            total REAL,
            paid REAL,
            change_due REAL,
            payment_method TEXT,
            status TEXT DEFAULT 'completed'
        );
        CREATE TABLE IF NOT EXISTS sale_items (
            id INTEGER PRIMARY KEY,
            sale_id INTEGER REFERENCES sales(id) ON DELETE CASCADE,
            product_id INTEGER,
            name TEXT,
            qty REAL,
            price REAL,
            total REAL
        );
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        );
        CREATE TABLE IF NOT EXISTS holds (
            id INTEGER PRIMARY KEY,
            created_at TEXT,
            user_id INTEGER,
            payload TEXT
        );
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY,
            code TEXT UNIQUE,
            name TEXT NOT NULL,
            phone TEXT DEFAULT '',
            national_id TEXT DEFAULT '',
            address TEXT DEFAULT '',
            city TEXT DEFAULT '',
            credit_limit REAL DEFAULT 10000,
            debt REAL DEFAULT 0,
            notes TEXT DEFAULT '',
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS customer_ledger (
            id INTEGER PRIMARY KEY,
            customer_id INTEGER REFERENCES customers(id),
            created_at TEXT,
            kind TEXT,
            amount REAL,
            note TEXT,
            sale_id INTEGER
        );
        """
    )
    cols = [r[1] for r in cur.execute("PRAGMA table_info(products)").fetchall()]
    if "image" not in cols:
        cur.execute("ALTER TABLE products ADD COLUMN image TEXT DEFAULT ''")
    if "wholesale_price" not in cols:
        cur.execute("ALTER TABLE products ADD COLUMN wholesale_price REAL DEFAULT 0")
        cur.execute("UPDATE products SET wholesale_price = ROUND(price * 0.85, 2) WHERE wholesale_price IS NULL OR wholesale_price=0")
    if "wholesale_min" not in cols:
        cur.execute("ALTER TABLE products ADD COLUMN wholesale_min REAL DEFAULT 5")
    if "price_locked" not in cols:
        cur.execute("ALTER TABLE products ADD COLUMN price_locked INTEGER DEFAULT 1")
        cur.execute("UPDATE products SET price_locked=1")
    if "expiry_date" not in cols:
        cur.execute("ALTER TABLE products ADD COLUMN expiry_date TEXT DEFAULT ''")
    if "wholesale_unit" not in cols:
        cur.execute("ALTER TABLE products ADD COLUMN wholesale_unit TEXT DEFAULT ''")
    icols = [r[1] for r in cur.execute("PRAGMA table_info(sale_items)").fetchall()]
    if "cost" not in icols:
        cur.execute("ALTER TABLE sale_items ADD COLUMN cost REAL DEFAULT 0")
        cur.execute(
            """UPDATE sale_items SET cost = COALESCE(
                 (SELECT p.cost FROM products p WHERE p.id = sale_items.product_id), 0)
               WHERE COALESCE(cost,0)=0"""
        )
    scols = [r[1] for r in cur.execute("PRAGMA table_info(sales)").fetchall()]
    if "channel" not in scols:
        cur.execute("ALTER TABLE sales ADD COLUMN channel TEXT DEFAULT 'retail'")
    if "customer_id" not in scols:
        cur.execute("ALTER TABLE sales ADD COLUMN customer_id INTEGER")
    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE IF NOT EXISTS holds (id INTEGER PRIMARY KEY, created_at TEXT, user_id INTEGER, payload TEXT);
        """
    )
    state = cur.execute("SELECT value FROM settings WHERE key='demo_mode'").fetchone()
    if state is None:
        seed_demo = db_was_new
        cur.execute(
            "INSERT INTO settings (key, value) VALUES ('demo_mode', ?)",
            ("1" if seed_demo else "0",),
        )
    else:
        seed_demo = str(state[0]) == "1"

    defaults = {
        "store_name": "ALASIL POS",
        "store_phone": "0550 00 00 00",
        "store_city": "الجزائر",
        "tax_rate": "0.19",
        "currency": "د.ج",
        "font_size": "16",
        "net_mode": "local",
        "net_port": "9876",
        "net_host": "",
        "invoice_template": "teal",
    }
    for k, v in defaults.items():
        cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?,?)", (k, v))
    row = cur.execute("SELECT value FROM settings WHERE key='net_password'").fetchone()
    if not row or row[0] in ("", "123456"):
        cur.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES ('net_password', ?)",
            (secrets.token_urlsafe(12),),
        )
    row = cur.execute("SELECT value FROM settings WHERE key='scan_token'").fetchone()
    if not row or row[0] in ("", "alasil"):
        cur.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES ('scan_token', ?)",
            (secrets.token_urlsafe(18),),
        )
    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY,
            code TEXT UNIQUE,
            name TEXT NOT NULL,
            phone TEXT DEFAULT '',
            national_id TEXT DEFAULT '',
            address TEXT DEFAULT '',
            city TEXT DEFAULT '',
            credit_limit REAL DEFAULT 10000,
            debt REAL DEFAULT 0,
            notes TEXT DEFAULT '',
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS customer_ledger (
            id INTEGER PRIMARY KEY,
            customer_id INTEGER REFERENCES customers(id),
            created_at TEXT,
            kind TEXT,
            amount REAL,
            note TEXT,
            sale_id INTEGER
        );
        """
    )
    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS specializations (
            id INTEGER PRIMARY KEY,
            name_ar TEXT NOT NULL,
            name_fr TEXT NOT NULL,
            emoji TEXT DEFAULT '🏪',
            cover TEXT DEFAULT '',
            color TEXT DEFAULT '#1A4B8C',
            notes TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS spec_images (
            id INTEGER PRIMARY KEY,
            spec_id INTEGER REFERENCES specializations(id) ON DELETE CASCADE,
            path TEXT NOT NULL,
            title TEXT DEFAULT '',
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS units (
            id INTEGER PRIMARY KEY,
            name_ar TEXT UNIQUE NOT NULL,
            name_fr TEXT NOT NULL,
            decimal INTEGER DEFAULT 0
        );
        """
    )
    cur.execute(
        """CREATE TABLE IF NOT EXISTS units (
            id INTEGER PRIMARY KEY,
            name_ar TEXT UNIQUE NOT NULL,
            name_fr TEXT NOT NULL,
            decimal INTEGER DEFAULT 0
        )"""
    )
    if seed_demo and cur.execute("SELECT COUNT(*) FROM units").fetchone()[0] == 0:
        cur.executemany(
            "INSERT INTO units (name_ar, name_fr, decimal) VALUES (?,?,?)",
            [
                ("قطعة", "Pièce", 0),
                ("علبة", "Boîte", 0),
                ("كيس", "Sachet", 0),
                ("عرام", "Gramme", 1),
                ("كلغ", "Kilogramme", 1),
                ("متر", "Mètre", 1),
                ("لتر", "Litre", 1),
                ("قارورة", "Bouteille", 0),
            ],
        )
    if seed_demo and cur.execute("SELECT COUNT(*) FROM specializations").fetchone()[0] == 0:
        specs = [
            ("خرداوات", "Quincaillerie", "🔧", "chips.png", "#b45309", "مسامير، أدوات، معدات"),
            ("ملابس", "Vêtements", "👕", "chips.png", "#7c3aed", "ألبسة رجالية ونسائية"),
            ("مواد غذائية", "Alimentaire", "🛒", "rice.png", "#0e7c66", "مواد غذائية جافة"),
            ("مشروبات", "Boissons", "🥤", "pepsi.png", "#1e6fba", "مشروبات غازية وعصائر"),
            ("منظفات", "Entretien", "🧴", "oil.png", "#5b4b8a", "تنظيف المنزل"),
            ("أجهزة", "Électronique", "🎧", "cola.png", "#334155", "إلكترونيات وشواحن"),
            ("مخبزة", "Boulangerie", "🍞", "biscuits.png", "#c2410c", "خبز وحلويات"),
            ("خضروات", "Légumes", "🍅", "pasta.png", "#15803d", "خضر وفواكه"),
            ("أدوات مدرسية", "Scolaire", "📚", "sugar.png", "#0369a1", "قرطاسية"),
            ("صيدلية", "Pharmacie", "💊", "water.png", "#0f766e", "أدوية ومستحضرات"),
        ]
        cur.executemany(
            "INSERT INTO specializations (name_ar,name_fr,emoji,cover,color,notes) VALUES (?,?,?,?,?,?)",
            specs,
        )
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # صور أولية من مجلد الأصول
        samples = {
            3: ["rice.png", "sugar.png", "oil.png", "pasta.png"],
            4: ["pepsi.png", "water.png", "cola.png", "coffee.png"],
            1: ["chips.png", "oil.png"],
            2: ["chips.png"],
            7: ["biscuits.png", "sugar.png"],
        }
        for sid, files in samples.items():
            for fn in files:
                cur.execute(
                    "INSERT INTO spec_images (spec_id, path, title, created_at) VALUES (?,?,?,?)",
                    (sid, fn, fn, now),
                )
    if seed_demo and cur.execute("SELECT COUNT(*) FROM customers").fetchone()[0] == 0:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cur.execute(
            """INSERT INTO customers (code,name,phone,national_id,address,city,credit_limit,debt,notes,created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            ("C-0001", "أحمد بن علي", "0550123456", "100200300", "حي 500 مسكن", "سطيف", 20000, 0, "زبون تجريبي", now),
        )
    if cur.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
        cur.execute(
            "INSERT INTO users (username, display_name, pin, role) VALUES (?,?,?,?)",
            ("admin", "مدير النظام", "", "admin"),
        )
        cur.execute(
            "INSERT INTO users (username, display_name, pin, role) VALUES (?,?,?,?)",
            ("employe", "موظف", "", "cashier"),
        )

    if seed_demo and cur.execute("SELECT COUNT(*) FROM categories").fetchone()[0] == 0:
        cats = [
            ("الكل", "Tous", "#1A4B8C", 0),
            ("مواد غذائية", "Alimentaire", "#0E7C66", 1),
            ("مشروبات", "Boissons", "#1E6FBA", 2),
            ("منظفات", "Entretien", "#5B4B8A", 3),
            ("ملابس", "Vêtements", "#B45309", 4),
            ("أجهزة", "Électronique", "#334155", 5),
        ]
        cur.executemany(
            "INSERT INTO categories (name_ar, name_fr, color, sort_order) VALUES (?,?,?,?)",
            cats,
        )

        products = [
            ("P001", "6130001", "بيبسي 33cl", "Pepsi 33cl", 3, 50, 30, 80, "علبة", "🥤", "pepsi.png"),
            ("P002", "6130002", "ماء معدني 1.5L", "Eau minérale 1.5L", 3, 30, 15, 200, "قارورة", "💧", "water.png"),
            ("P003", "6130003", "شيبس ليز", "Chips Lays", 2, 100, 55, 40, "كيس", "🥔", "chips.png"),
            ("P004", "6130004", "بسكويت", "Biscuits", 2, 80, 40, 50, "علبة", "🍪", "biscuits.png"),
            ("P005", "6130005", "زيت المائدة 1L", "Huile de table 1L", 2, 450, 320, 3, "قارورة", "🫒", "oil.png"),
            ("P006", "6130006", "سكر 1kg", "Sucre 1kg", 2, 160, 110, 70, "كيس", "🍬", "sugar.png"),
            ("P007", "6130007", "أرز 1kg", "Riz 1kg", 2, 280, 190, 45, "كيس", "🍚", "rice.png"),
            ("P008", "6130008", "مكرونة 500g", "Pâtes 500g", 2, 90, 50, 60, "كيس", "🍝", "pasta.png"),
            ("P009", "6130009", "كولا 2ل", "Cola 2L", 3, 130, 80, 90, "قارورة", "🥤", "cola.png"),
            ("P010", "6130010", "قهوة مطحونة 250غ", "Café moulu 250g", 3, 420, 280, 28, "علبة", "☕", "coffee.png"),
            ("P011", "6130011", "شاي أخضر 200غ", "Thé vert 200g", 3, 280, 170, 40, "علبة", "🍵", "coffee.png"),
            ("P012", "6130012", "منظف أرضيات 2ل", "Nettoyant sol 2L", 4, 210, 130, 33, "قارورة", "🧴", "oil.png"),
            ("P013", "6130013", "صابون غسيل 5كغ", "Lessive 5kg", 4, 890, 620, 18, "كيس", "🧺", "sugar.png"),
            ("P014", "6130014", "سائل جلي 750مل", "Liquide vaisselle", 4, 95, 55, 60, "قارورة", "🧽", "oil.png"),
            ("P015", "6130015", "تيشيرت قطن", "T-shirt coton", 5, 1200, 650, 25, "قطعة", "👕", "chips.png"),
            ("P016", "6130016", "جينز رجالي", "Jean homme", 5, 2800, 1600, 14, "قطعة", "👖", "chips.png"),
            ("P017", "6130017", "سماعة بلوتوث", "Casque Bluetooth", 6, 4500, 2800, 12, "قطعة", "🎧", "cola.png"),
            ("P018", "6130018", "شاحن سريع", "Chargeur rapide", 6, 950, 480, 30, "قطعة", "🔌", "cola.png"),
            ("P019", "6130019", "حليب كامل 1ل", "Lait entier 1L", 2, 145, 110, 80, "علبة", "🥛", "water.png"),
            ("P020", "6130020", "خبز طازج", "Pain frais", 2, 20, 8, 120, "رغيف", "🍞", "biscuits.png"),
        ]
        cur.executemany(
            """INSERT INTO products
               (sku, barcode, name_ar, name_fr, category_id, price, cost, stock, unit, emoji, image)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            products,
        )
    mapping = {
        "6130001": "pepsi.png", "6130002": "water.png", "6130003": "chips.png",
        "6130004": "biscuits.png", "6130005": "oil.png", "6130006": "sugar.png",
        "6130007": "rice.png", "6130008": "pasta.png", "6130009": "cola.png",
        "6130010": "coffee.png",
    }
    for code, img in mapping.items():
        cur.execute(
            "UPDATE products SET image=? WHERE barcode=? AND (image IS NULL OR image='')",
            (img, code),
        )
    ensure_erp(cur, seed_demo=seed_demo)
    _install_demo_guards(cur)
    conn.commit()
    conn.close()



def _install_demo_guards(cur):
    """Disable demo cleanup after the first real data modification."""
    row = cur.execute(
        "SELECT value FROM settings WHERE key='demo_mode'"
    ).fetchone()
    if not row or str(row[0]) != "1":
        return

    tables = (
        "products", "categories", "sales", "sale_items",
        "customers", "customer_ledger", "holds",
        "suppliers", "purchases", "purchase_items",
        "expenses", "cash_sessions", "cash_moves",
        "stock_moves", "units", "specializations", "spec_images",
    )
    for table in tables:
        for action in ("INSERT", "UPDATE", "DELETE"):
            trigger = f"alasil_demo_guard_{table}_{action.lower()}"
            cur.execute(f"""
                CREATE TRIGGER IF NOT EXISTS "{trigger}"
                AFTER {action} ON "{table}"
                WHEN (
                    SELECT value FROM settings WHERE key='demo_mode'
                ) = '1'
                BEGIN
                    UPDATE settings SET value='0'
                    WHERE key='demo_mode';
                END
            """)


def is_demo_mode():
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT value FROM settings WHERE key='demo_mode'"
        ).fetchone()
        return bool(row and str(row[0]) == "1")
    finally:
        conn.close()


def clear_demo_data(admin_user_id):
    """Clear demo records only; preserve users, settings, units and license."""
    conn = get_conn()
    try:
        user = conn.execute(
            "SELECT id, username, role FROM users WHERE id=?",
            (admin_user_id,),
        ).fetchone()
        if not user or (user["role"] != "admin" and user["username"] != "admin"):
            raise PermissionError("??? ??????? ????? ?????? ???.")

        state = conn.execute(
            "SELECT value FROM settings WHERE key='demo_mode'"
        ).fetchone()
        if not state or str(state[0]) != "1":
            raise PermissionError("????? ???????? ?? ??? ???????? ?? ????? ?????.")
    finally:
        conn.close()

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = DB_PATH.parent / "backups" / f"alasil_demo_before_clear_{stamp}.db"
    backup_db(backup_path)

    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")

        user = conn.execute(
            "SELECT id, username, role FROM users WHERE id=?",
            (admin_user_id,),
        ).fetchone()
        state = conn.execute(
            "SELECT value FROM settings WHERE key='demo_mode'"
        ).fetchone()

        if not user or (user["role"] != "admin" and user["username"] != "admin"):
            raise PermissionError("???? ?????? ?? ?????? ??????.")
        if not state or str(state[0]) != "1":
            raise PermissionError("????? ???????? ?? ??? ???????? ?? ????? ?????.")

        tables = (
            "sale_items", "sales", "customer_ledger", "customers",
            "purchase_items", "purchases", "cash_moves", "cash_sessions",
            "stock_moves", "holds", "products", "categories",
            "spec_images", "specializations", "suppliers", "expenses",
            "login_attempts",
        )
        for table in tables:
            conn.execute(f'DELETE FROM "{table}"')

        conn.execute(
            "UPDATE settings SET value='0' WHERE key='demo_mode'"
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    ok, message = integrity_ok()
    if not ok:
        raise RuntimeError(f"??? ??? ????? ???????? ??? ???????: {message}")

    return backup_path


def scan_token():
    t = get_setting("scan_token", "")
    if not t or t == "alasil":
        t = secrets.token_urlsafe(18)
        set_setting("scan_token", t)
    return t


def ensure_erp(cur, seed_demo=False):
    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS suppliers (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            phone TEXT DEFAULT '',
            address TEXT DEFAULT '',
            debt REAL DEFAULT 0,
            notes TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS purchases (
            id INTEGER PRIMARY KEY,
            invoice_no TEXT,
            supplier_id INTEGER,
            created_at TEXT,
            total REAL,
            paid REAL,
            status TEXT DEFAULT 'received'
        );
        CREATE TABLE IF NOT EXISTS purchase_items (
            id INTEGER PRIMARY KEY,
            purchase_id INTEGER,
            product_id INTEGER,
            name TEXT,
            qty REAL,
            cost REAL,
            total REAL
        );
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY,
            created_at TEXT,
            category TEXT,
            amount REAL,
            note TEXT
        );
        CREATE TABLE IF NOT EXISTS cash_sessions (
            id INTEGER PRIMARY KEY,
            opened_at TEXT,
            closed_at TEXT,
            user_id INTEGER,
            open_amount REAL,
            close_amount REAL,
            status TEXT DEFAULT 'open'
        );
        CREATE TABLE IF NOT EXISTS cash_moves (
            id INTEGER PRIMARY KEY,
            session_id INTEGER,
            created_at TEXT,
            kind TEXT,
            amount REAL,
            note TEXT
        );
        CREATE TABLE IF NOT EXISTS stock_moves (
            id INTEGER PRIMARY KEY,
            created_at TEXT,
            product_id INTEGER,
            kind TEXT,
            qty REAL,
            note TEXT
        );
        CREATE TABLE IF NOT EXISTS login_attempts (
            id INTEGER PRIMARY KEY,
            created_at TEXT,
            pin TEXT,
            ok INTEGER
        );
        """
    )
    cols = [r[1] for r in cur.execute("PRAGMA table_info(users)").fetchall()]
    if "permissions" not in cols:
        cur.execute("ALTER TABLE users ADD COLUMN permissions TEXT DEFAULT 'all'")
    for col, spec in (
        ("phone", "TEXT DEFAULT ''"),
        ("salary", "REAL DEFAULT 0"),
        ("active", "INTEGER DEFAULT 1"),
        ("hire_date", "TEXT DEFAULT ''"),
    ):
        if col not in cols:
            try:
                cur.execute(f"ALTER TABLE users ADD COLUMN {col} {spec}")
            except Exception:
                pass
    ucols = [r[1] for r in cur.execute("PRAGMA table_info(users)").fetchall()]
    if "password" not in ucols:
        try:
            cur.execute("ALTER TABLE users ADD COLUMN password TEXT DEFAULT ''")
        except Exception:
            pass
    ucols = [r[1] for r in cur.execute("PRAGMA table_info(users)").fetchall()]
    if "must_change_pw" not in ucols:
        try:
            cur.execute("ALTER TABLE users ADD COLUMN must_change_pw INTEGER DEFAULT 0")
        except Exception:
            pass
    cur.execute("UPDATE users SET permissions='all' WHERE role='admin' AND (permissions IS NULL OR permissions='' OR permissions='pos')")
    if cur.execute("SELECT id FROM users WHERE username='admin'").fetchone() is None:
        cur.execute(
            "INSERT INTO users (username, display_name, pin, role, permissions, password, active, must_change_pw) VALUES (?,?,?,?,?,?,1,1)",
            ("admin", "مدير النظام", "", "admin", "all", sec.hash_password("admin")),
        )
    else:
        cur.execute("UPDATE users SET role='admin', permissions='all', active=1 WHERE username='admin'")
        prow = cur.execute("SELECT password FROM users WHERE username='admin'").fetchone()
        apw = prow[0] if prow else ""
        if not apw:
            cur.execute(
                "UPDATE users SET password=?, must_change_pw=1 WHERE username='admin'",
                (sec.hash_password("admin"),),
            )
    if cur.execute("SELECT id FROM users WHERE username='employe'").fetchone() is None:
        cur.execute(
            "INSERT INTO users (username, display_name, pin, role, permissions, password, active, must_change_pw) VALUES (?,?,?,?,?,?,1,1)",
            ("employe", "موظف", "", "cashier", "pos,sales,wholesale,customers", sec.hash_password("emp123")),
        )
    else:
        cur.execute("UPDATE users SET role='cashier', active=1 WHERE username='employe'")
        cur.execute(
            "UPDATE users SET permissions='pos,sales,wholesale,customers' WHERE username='employe' "
            "AND (permissions IS NULL OR permissions='' OR permissions='all')"
        )
        prow = cur.execute("SELECT password FROM users WHERE username='employe'").fetchone()
        epw = prow[0] if prow else ""
        if not epw:
            cur.execute(
                "UPDATE users SET password=?, must_change_pw=1 WHERE username='employe'",
                (sec.hash_password("emp123"),),
            )
    for row in cur.execute("SELECT id, password FROM users").fetchall():
        pw = row["password"] if "password" in row.keys() else row[1]
        uid = row["id"] if "id" in row.keys() else row[0]
        if pw and not sec.is_hashed(str(pw)):
            cur.execute(
                "UPDATE users SET password=?, must_change_pw=1 WHERE id=?",
                (sec.hash_password(str(pw)), uid),
            )
    if seed_demo and cur.execute("SELECT COUNT(*) FROM suppliers").fetchone()[0] == 0:
        cur.execute(
            "INSERT INTO suppliers (name, phone, address, debt, notes) VALUES (?,?,?,?,?)",
            ("مؤونة سطيف", "0551111222", "سطيف", 0, "مورد تجريبي"),
        )
    if seed_demo and cur.execute("SELECT COUNT(*) FROM expenses").fetchone()[0] == 0:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cur.executemany(
            "INSERT INTO expenses (created_at, category, amount, note) VALUES (?,?,?,?)",
            [
                (now, "إيجار", 40000, "شهر"),
                (now, "كهرباء", 8000, ""),
            ],
        )


def fetch_categories():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM categories ORDER BY sort_order").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def fetch_products(category_id=None, query=""):
    conn = get_conn()
    sql = "SELECT p.*, c.name_ar AS cat_ar FROM products p LEFT JOIN categories c ON c.id=p.category_id WHERE p.active=1"
    params = []
    if category_id and int(category_id) != 1:
        sql += " AND p.category_id=?"
        params.append(int(category_id))
    if query:
        q = f"%{query.strip()}%"
        sql += " AND (p.name_ar LIKE ? OR p.name_fr LIKE ? OR p.barcode LIKE ? OR p.sku LIKE ?)"
        params.extend([q, q, q, q])
    sql += " ORDER BY p.name_ar"
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def find_by_barcode(code):
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM products WHERE barcode=? AND active=1", (code.strip(),)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def _ensure_session_conn(conn, user_id=1):
    row = conn.execute(
        "SELECT * FROM cash_sessions WHERE status='open' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if row:
        return row["id"]
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cur = conn.execute(
        "INSERT INTO cash_sessions (opened_at, user_id, open_amount, status) VALUES (?,?,?, 'open')",
        (now, user_id, 0),
    )
    return cur.lastrowid


def _cash_on_conn(conn, kind, amount, note, user_id=1):
    amount = float(amount or 0)
    if amount <= 0:
        return
    sid = _ensure_session_conn(conn, user_id)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        "INSERT INTO cash_moves (session_id, created_at, kind, amount, note) VALUES (?,?,?,?,?)",
        (sid, now, kind, amount, note),
    )


def save_sale(user_id, items, subtotal, discount, tax, total, paid, change, method, channel="retail", customer_id=None):
    conn = get_conn()
    cur = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    prefix = "WS-" if channel == "wholesale" else "INV-"
    try:
        cur.execute("BEGIN IMMEDIATE")
        cur.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('invoice_seq','0')")
        cur.execute("UPDATE settings SET value = CAST(COALESCE(value,'0') AS INTEGER)+1 WHERE key='invoice_seq'")
        n = int(cur.execute("SELECT value FROM settings WHERE key='invoice_seq'").fetchone()[0])
        invoice = f"{prefix}{n:08d}"
        for it in items:
            prow = cur.execute(
                "SELECT name_ar, stock, cost FROM products WHERE id=?", (it["id"],)
            ).fetchone()
            if not prow:
                raise ValueError("منتج غير موجود")
            avail = float(prow["stock"] or 0)
            qty = float(it["qty"])
            if avail + 1e-9 < qty:
                raise ValueError(f"مخزون غير كافٍ: {prow['name_ar']} (المتوفر {avail:g})")
        cur.execute(
            """INSERT INTO sales (invoice_no, created_at, user_id, subtotal, discount, tax, total, paid, change_due, payment_method, channel, customer_id)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (invoice, now, user_id, subtotal, discount, tax, total, paid, change, method, channel, customer_id),
        )
        sale_id = cur.lastrowid
        for it in items:
            prow = cur.execute("SELECT cost FROM products WHERE id=?", (it["id"],)).fetchone()
            unit_cost = float(prow["cost"] or 0) if prow else float(it.get("cost") or 0)
            cur.execute(
                "INSERT INTO sale_items (sale_id, product_id, name, qty, price, total, cost) VALUES (?,?,?,?,?,?,?)",
                (sale_id, it["id"], it["name"], it["qty"], it["price"], it["qty"] * it["price"], unit_cost),
            )
            cur.execute("UPDATE products SET stock = stock - ? WHERE id=?", (it["qty"], it["id"]))
            cur.execute(
                "INSERT INTO stock_moves (created_at, product_id, kind, qty, note) VALUES (?,?,?,?,?)",
                (now, it["id"], "بيع", -float(it["qty"]), invoice),
            )
        if method in ("cash", "mixed") and float(paid or 0) > 0:
            _cash_on_conn(conn, "in", paid, f"بيع {invoice}", user_id)
        conn.commit()
    except Exception:
        conn.rollback()
        conn.close()
        raise
    conn.close()
    return invoice


def sales_today():
    conn = get_conn()
    today = datetime.now().strftime("%Y-%m-%d")
    row = conn.execute(
        "SELECT COUNT(*) n, COALESCE(SUM(total),0) s FROM sales WHERE date(created_at)=? AND status='completed'",
        (today,),
    ).fetchone()
    conn.close()
    return int(row["n"]), float(row["s"])


def recent_sales(limit=50):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM sales ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def all_products():
    conn = get_conn()
    rows = conn.execute(
        "SELECT p.*, c.name_ar AS cat_ar FROM products p LEFT JOIN categories c ON c.id=p.category_id ORDER BY p.id"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def upsert_product(data, pid=None):
    conn = get_conn()
    cur = conn.cursor()
    wp = data.get("wholesale_price")
    if wp is None:
        wp = round(float(data["price"]) * 0.85, 2)
    wmin = data.get("wholesale_min", 5)
    locked = int(data.get("price_locked", 1))
    if pid:
        old = conn.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
        if old and old["price_locked"] and not data.get("unlock_prices"):
            data["price"] = old["price"]
            data["cost"] = old["cost"]
            wp = old["wholesale_price"] if old["wholesale_price"] is not None else wp
            wmin = old["wholesale_min"] if old["wholesale_min"] is not None else wmin
            locked = 1
    if pid:
        cur.execute(
            """UPDATE products SET sku=?, barcode=?, name_ar=?, name_fr=?, category_id=?,
               price=?, cost=?, stock=?, unit=?, emoji=?, wholesale_price=?, wholesale_min=?, price_locked=?, expiry_date=?, wholesale_unit=? WHERE id=?""",
            (
                data["sku"], data["barcode"], data["name_ar"], data["name_fr"],
                data["category_id"], data["price"], data["cost"], data["stock"],
                data["unit"], data["emoji"], wp, wmin, locked, data.get("expiry_date") or "", data.get("wholesale_unit") or data.get("unit") or "قطعة", pid,
            ),
        )
    else:
        cur.execute(
            """INSERT INTO products (sku, barcode, name_ar, name_fr, category_id, price, cost, stock, unit, emoji, wholesale_price, wholesale_min, price_locked, expiry_date, wholesale_unit)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                data["sku"], data["barcode"], data["name_ar"], data["name_fr"],
                data["category_id"], data["price"], data["cost"], data["stock"],
                data["unit"], data["emoji"], wp, wmin, 1, data.get("expiry_date") or "", data.get("wholesale_unit") or data.get("unit") or "قطعة",
            ),
        )
    conn.commit()
    conn.close()


def delete_product(pid):
    conn = get_conn()
    conn.execute("UPDATE products SET active=0 WHERE id=?", (pid,))
    conn.commit()
    conn.close()


def authenticate_pin(pin):
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE pin=? AND COALESCE(active,1)=1 AND pin!=''", (pin,)).fetchone()
    conn.close()
    return dict(row) if row else None


ADMIN_PERMS = "all"
EMPLOYEE_PERMS = "pos,sales,wholesale,customers"


def apply_role_permissions(user):
    if not user:
        return user
    u = dict(user)
    name = (u.get("username") or "").strip().lower()
    if name == "admin" or u.get("role") == "admin":
        u["role"] = "admin"
        u["permissions"] = ADMIN_PERMS
    else:
        u["role"] = u.get("role") or "cashier"
        p = (u.get("permissions") or "").strip()
        if not p or p == "all":
            u["permissions"] = EMPLOYEE_PERMS
    return u


def authenticate_user(username, password):
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM users WHERE username=? AND COALESCE(active,1)=1",
        ((username or "").strip(),),
    ).fetchone()
    conn.close()
    if not row:
        return None
    u = dict(row)
    stored = u.get("password") or ""
    plain = password or ""
    ok = False
    if sec.is_hashed(stored):
        ok = sec.verify_password(plain, stored)
    elif stored and stored == plain:
        ok = True
        set_user_password(u["id"], plain, must_change=True)
        u["must_change_pw"] = 1
    if not ok:
        return None
    u.pop("password", None)
    u.pop("pin", None)
    return apply_role_permissions(u)


def set_user_password(uid, plain, must_change=False):
    q(
        "UPDATE users SET password=?, must_change_pw=? WHERE id=?",
        (sec.hash_password(plain), 1 if must_change else 0, uid),
        commit=True,
    )


def get_sale_by_invoice(invoice):
    conn = get_conn()
    sale = conn.execute("SELECT * FROM sales WHERE invoice_no=?", (invoice,)).fetchone()
    if not sale:
        conn.close()
        return None, []
    items = conn.execute("SELECT * FROM sale_items WHERE sale_id=?", (sale["id"],)).fetchall()
    conn.close()
    return dict(sale), [dict(i) for i in items]


def last_sale():
    conn = get_conn()
    sale = conn.execute("SELECT * FROM sales ORDER BY id DESC LIMIT 1").fetchone()
    if not sale:
        conn.close()
        return None, []
    items = conn.execute("SELECT * FROM sale_items WHERE sale_id=?", (sale["id"],)).fetchall()
    conn.close()
    return dict(sale), [dict(i) for i in items]


def get_setting(key, default=""):
    conn = get_conn()
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else default


def set_setting(key, value):
    conn = get_conn()
    conn.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, str(value)))
    conn.commit()
    conn.close()


def tax_rate():
    try:
        return float(get_setting("tax_rate", "0.19"))
    except ValueError:
        return 0.19


def upsert_category(name_ar, name_fr, color="#1A4B8C", cid=None):
    conn = get_conn()
    cur = conn.cursor()
    if cid:
        cur.execute("UPDATE categories SET name_ar=?, name_fr=?, color=? WHERE id=?", (name_ar, name_fr, color, cid))
    else:
        mx = cur.execute("SELECT COALESCE(MAX(sort_order),0)+1 FROM categories").fetchone()[0]
        cur.execute(
            "INSERT INTO categories (name_ar, name_fr, color, sort_order) VALUES (?,?,?,?)",
            (name_ar, name_fr, color, mx),
        )
    conn.commit()
    conn.close()


def delete_category(cid):
    if int(cid) == 1:
        return False
    conn = get_conn()
    conn.execute("UPDATE products SET category_id=2 WHERE category_id=?", (cid,))
    conn.execute("DELETE FROM categories WHERE id=?", (cid,))
    conn.commit()
    conn.close()
    return True


def return_sale(invoice):
    conn = get_conn()
    sale = conn.execute("SELECT * FROM sales WHERE invoice_no=?", (invoice,)).fetchone()
    if not sale or sale["status"] == "returned":
        conn.close()
        return False
    items = conn.execute("SELECT * FROM sale_items WHERE sale_id=?", (sale["id"],)).fetchall()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for it in items:
        if it["product_id"]:
            conn.execute("UPDATE products SET stock = stock + ? WHERE id=?", (it["qty"], it["product_id"]))
            conn.execute(
                "INSERT INTO stock_moves (created_at, product_id, kind, qty, note) VALUES (?,?,?,?,?)",
                (now, it["product_id"], "إرجاع", float(it["qty"]), invoice),
            )
    conn.execute("UPDATE sales SET status='returned' WHERE id=?", (sale["id"],))
    paid = float(sale["paid"] or 0)
    method = sale["payment_method"] or ""
    if method in ("cash", "mixed") and paid > 0:
        _cash_on_conn(conn, "out", paid, f"إرجاع {invoice}", sale["user_id"] or 1)
    cid = sale["customer_id"] if "customer_id" in sale.keys() else None
    if cid and method == "credit":
        amt = float(sale["total"] or 0)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn.execute("UPDATE customers SET debt = debt - ? WHERE id=?", (amt, cid))
        conn.execute(
            "INSERT INTO customer_ledger (customer_id, created_at, kind, amount, note, sale_id) VALUES (?,?,?,?,?,?)",
            (cid, now, "payment", -amt, f"إلغاء دين {invoice}", sale["id"]),
        )
    conn.commit()
    conn.close()
    return True


def save_hold(user_id, items, discount):
    import json
    conn = get_conn()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO holds (created_at, user_id, payload) VALUES (?,?,?)",
        (now, user_id, json.dumps({"items": items, "discount": discount}, ensure_ascii=False)),
    )
    hid = cur.lastrowid
    conn.commit()
    conn.close()
    return hid


def list_holds():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM holds ORDER BY id DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def pop_hold(hid):
    import json
    conn = get_conn()
    row = conn.execute("SELECT * FROM holds WHERE id=?", (hid,)).fetchone()
    if not row:
        conn.close()
        return None
    conn.execute("DELETE FROM holds WHERE id=?", (hid,))
    conn.commit()
    conn.close()
    return json.loads(row["payload"])


def report_overview():
    conn = get_conn()
    today = datetime.now().strftime("%Y-%m-%d")
    t = conn.execute(
        "SELECT COUNT(*) n, COALESCE(SUM(total),0) s FROM sales WHERE date(created_at)=? AND status='completed'",
        (today,),
    ).fetchone()
    allr = conn.execute(
        "SELECT COUNT(*) n, COALESCE(SUM(total),0) s FROM sales WHERE status='completed'"
    ).fetchone()
    by_pay = conn.execute(
        "SELECT payment_method, COUNT(*) n, COALESCE(SUM(total),0) s FROM sales WHERE status='completed' GROUP BY payment_method"
    ).fetchall()
    by_cat = conn.execute(
        """SELECT c.name_ar, COALESCE(SUM(si.total),0) s, COUNT(*) n
           FROM sale_items si
           JOIN products p ON p.id=si.product_id
           JOIN categories c ON c.id=p.category_id
           JOIN sales sl ON sl.id=si.sale_id AND sl.status='completed'
           GROUP BY c.id ORDER BY s DESC"""
    ).fetchall()
    low = conn.execute("SELECT * FROM products WHERE active=1 AND stock<=5 ORDER BY stock").fetchall()
    conn.close()
    return {
        "today_n": t["n"], "today_s": t["s"],
        "all_n": allr["n"], "all_s": allr["s"],
        "by_pay": [dict(r) for r in by_pay],
        "by_cat": [dict(r) for r in by_cat],
        "low": [dict(r) for r in low],
    }


def list_users():
    conn = get_conn()
    rows = conn.execute("SELECT id, username, display_name, role FROM users").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_user_pin(uid, pin):
    conn = get_conn()
    conn.execute("UPDATE users SET pin=? WHERE id=?", (pin, uid))
    conn.commit()
    conn.close()


def next_customer_code():
    conn = get_conn()
    n = conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0] + 1
    conn.close()
    return f"C-{n:04d}"


def list_customers(q=""):
    conn = get_conn()
    if q:
        like = f"%{q}%"
        rows = conn.execute(
            "SELECT * FROM customers WHERE name LIKE ? OR phone LIKE ? OR code LIKE ? ORDER BY id DESC",
            (like, like, like),
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM customers ORDER BY id DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_customer(cid):
    conn = get_conn()
    row = conn.execute("SELECT * FROM customers WHERE id=?", (cid,)).fetchone()
    conn.close()
    return dict(row) if row else None


def upsert_customer(data, cid=None):
    conn = get_conn()
    cur = conn.cursor()
    if cid:
        cur.execute(
            """UPDATE customers SET name=?, phone=?, national_id=?, address=?, city=?,
               credit_limit=?, notes=? WHERE id=?""",
            (data["name"], data["phone"], data["national_id"], data["address"],
             data["city"], data["credit_limit"], data["notes"], cid),
        )
        nid = cid
    else:
        code = data.get("code") or next_customer_code()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cur.execute(
            """INSERT INTO customers (code,name,phone,national_id,address,city,credit_limit,debt,notes,created_at)
               VALUES (?,?,?,?,?,?,?,0,?,?)""",
            (code, data["name"], data["phone"], data["national_id"], data["address"],
             data["city"], data["credit_limit"], data["notes"], now),
        )
        nid = cur.lastrowid
    conn.commit()
    conn.close()
    return nid


def add_debt(customer_id, amount, note="", sale_id=None):
    conn = get_conn()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute("UPDATE customers SET debt = debt + ? WHERE id=?", (amount, customer_id))
    conn.execute(
        "INSERT INTO customer_ledger (customer_id, created_at, kind, amount, note, sale_id) VALUES (?,?,?,?,?,?)",
        (customer_id, now, "debit" if amount >= 0 else "payment", amount, note, sale_id),
    )
    conn.commit()
    conn.close()


def pay_debt(customer_id, amount, note="تسديد"):
    add_debt(customer_id, -abs(amount), note)
    if float(amount or 0) > 0:
        conn = get_conn()
        _cash_on_conn(conn, "in", abs(amount), f"تسديد عميل #{customer_id} {note}", 1)
        conn.commit()
        conn.close()


def customer_ledger(cid):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM customer_ledger WHERE customer_id=? ORDER BY id DESC LIMIT 80", (cid,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def customer_payload(c):
    return (
        f"ALASIL|{c.get('code')}|{c.get('name')}|{c.get('phone')}|"
        f"{c.get('national_id')}|{c.get('address')}|{c.get('city')}|"
        f"LIM={c.get('credit_limit')}|DEBT={c.get('debt')}|ID={c.get('id')}"
    )


def list_specs():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM specializations ORDER BY id").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_spec(sid):
    conn = get_conn()
    row = conn.execute("SELECT * FROM specializations WHERE id=?", (sid,)).fetchone()
    conn.close()
    return dict(row) if row else None


def upsert_spec(data, sid=None):
    conn = get_conn()
    cur = conn.cursor()
    if sid:
        cur.execute(
            "UPDATE specializations SET name_ar=?, name_fr=?, emoji=?, color=?, notes=? WHERE id=?",
            (data["name_ar"], data["name_fr"], data["emoji"], data["color"], data["notes"], sid),
        )
        nid = sid
    else:
        cur.execute(
            "INSERT INTO specializations (name_ar,name_fr,emoji,cover,color,notes) VALUES (?,?,?,?,?,?)",
            (data["name_ar"], data["name_fr"], data.get("emoji") or "🏪", data.get("cover") or "",
             data.get("color") or "#1A4B8C", data.get("notes") or ""),
        )
        nid = cur.lastrowid
    conn.commit()
    conn.close()
    return nid


def delete_spec(sid):
    conn = get_conn()
    conn.execute("DELETE FROM spec_images WHERE spec_id=?", (sid,))
    conn.execute("DELETE FROM specializations WHERE id=?", (sid,))
    conn.commit()
    conn.close()


def spec_images(sid):
    conn = get_conn()
    rows = conn.execute("SELECT * FROM spec_images WHERE spec_id=? ORDER BY id DESC", (sid,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_spec_image(sid, path, title=""):
    conn = get_conn()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        "INSERT INTO spec_images (spec_id, path, title, created_at) VALUES (?,?,?,?)",
        (sid, path, title, now),
    )
    conn.commit()
    conn.close()


def delete_spec_image(iid):
    conn = get_conn()
    conn.execute("DELETE FROM spec_images WHERE id=?", (iid,))
    conn.commit()
    conn.close()


def set_spec_cover(sid, path):
    conn = get_conn()
    conn.execute("UPDATE specializations SET cover=? WHERE id=?", (path, sid))
    conn.commit()
    conn.close()


def list_units():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM units ORDER BY id").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def upsert_unit(name_ar, name_fr, decimal=0, uid=None):
    conn = get_conn()
    if uid:
        conn.execute("UPDATE units SET name_ar=?, name_fr=?, decimal=? WHERE id=?", (name_ar, name_fr, int(decimal), uid))
    else:
        conn.execute("INSERT OR IGNORE INTO units (name_ar, name_fr, decimal) VALUES (?,?,?)", (name_ar, name_fr, int(decimal)))
    conn.commit()
    conn.close()


def delete_unit(uid):
    conn = get_conn()
    conn.execute("DELETE FROM units WHERE id=?", (uid,))
    conn.commit()
    conn.close()


def unit_is_decimal(name):
    conn = get_conn()
    row = conn.execute("SELECT decimal FROM units WHERE name_ar=?", (name or "",)).fetchone()
    conn.close()
    if row:
        return bool(row["decimal"])
    return (name or "") in ("عرام", "غرام", "كلغ", "كغ", "متر", "لتر")


def get_product(pid):
    conn = get_conn()
    row = conn.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
    conn.close()
    return dict(row) if row else None


def q(sql, params=(), one=False, commit=False):
    conn = get_conn()
    cur = conn.execute(sql, params)
    if commit:
        conn.commit()
        lid = cur.lastrowid
        conn.close()
        return lid
    rows = cur.fetchall()
    conn.close()
    if one:
        return dict(rows[0]) if rows else None
    return [dict(r) for r in rows]


def list_suppliers():
    return q("SELECT * FROM suppliers ORDER BY id DESC")


def upsert_supplier(data, sid=None):
    if sid:
        q("UPDATE suppliers SET name=?, phone=?, address=?, notes=? WHERE id=?",
          (data["name"], data["phone"], data["address"], data.get("notes", ""), sid), commit=True)
        return sid
    return q("INSERT INTO suppliers (name, phone, address, debt, notes) VALUES (?,?,?,0,?)",
             (data["name"], data["phone"], data["address"], data.get("notes", "")), commit=True)


def add_supplier_pay(sid, amount, note="تسديد"):
    q("UPDATE suppliers SET debt = debt - ? WHERE id=?", (amount, sid), commit=True)
    if float(amount or 0) > 0:
        conn = get_conn()
        _cash_on_conn(conn, "out", amount, f"تسديد مورد #{sid} {note}", 1)
        conn.commit()
        conn.close()
    return True


def list_purchases():
    return q(
        """SELECT p.*, s.name AS supplier FROM purchases p
           LEFT JOIN suppliers s ON s.id=p.supplier_id ORDER BY p.id DESC LIMIT 100"""
    )


def save_purchase(supplier_id, items, paid):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    total = sum(i["qty"] * i["cost"] for i in items)
    inv = "PUR-" + datetime.now().strftime("%Y%m%d%H%M%S")
    pid = q(
        "INSERT INTO purchases (invoice_no, supplier_id, created_at, total, paid, status) VALUES (?,?,?,?,?,?)",
        (inv, supplier_id, now, total, paid, "received"), commit=True,
    )
    conn = get_conn()
    for it in items:
        conn.execute(
            "INSERT INTO purchase_items (purchase_id, product_id, name, qty, cost, total) VALUES (?,?,?,?,?,?)",
            (pid, it["id"], it["name"], it["qty"], it["cost"], it["qty"] * it["cost"]),
        )
        conn.execute("UPDATE products SET stock = stock + ?, cost=? WHERE id=?", (it["qty"], it["cost"], it["id"]))
        conn.execute(
            "INSERT INTO stock_moves (created_at, product_id, kind, qty, note) VALUES (?,?,?,?,?)",
            (now, it["id"], "شراء", it["qty"], inv),
        )
    rest = total - paid
    if rest > 0 and supplier_id:
        conn.execute("UPDATE suppliers SET debt = debt + ? WHERE id=?", (rest, supplier_id))
    if float(paid or 0) > 0:
        _cash_on_conn(conn, "out", paid, f"شراء {inv}", 1)
    conn.commit()
    conn.close()
    return inv


def list_expenses():
    return q("SELECT * FROM expenses ORDER BY id DESC LIMIT 200")


def add_expense(category, amount, note=""):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    eid = q("INSERT INTO expenses (created_at, category, amount, note) VALUES (?,?,?,?)",
            (now, category, amount, note), commit=True)
    if float(amount or 0) > 0:
        conn = get_conn()
        _cash_on_conn(conn, "out", amount, f"مصروف: {category} {note}", 1)
        conn.commit()
        conn.close()
    return eid


def open_session(user_id, amount):
    open_one = q("SELECT * FROM cash_sessions WHERE status='open'", one=True)
    if open_one:
        return open_one["id"]
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return q(
        "INSERT INTO cash_sessions (opened_at, user_id, open_amount, status) VALUES (?,?,?, 'open')",
        (now, user_id, amount), commit=True,
    )


def current_session():
    return q("SELECT * FROM cash_sessions WHERE status='open' ORDER BY id DESC", one=True)


def cash_move(kind, amount, note="", user_id=1):
    ses = current_session()
    if not ses:
        open_session(user_id, 0)
        ses = current_session()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return q(
        "INSERT INTO cash_moves (session_id, created_at, kind, amount, note) VALUES (?,?,?,?,?)",
        (ses["id"], now, kind, amount, note), commit=True,
    )


def close_session(close_amount):
    ses = current_session()
    if not ses:
        return False
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    q("UPDATE cash_sessions SET closed_at=?, close_amount=?, status='closed' WHERE id=?",
      (now, close_amount, ses["id"]), commit=True)
    return True


def list_sessions():
    return q("SELECT * FROM cash_sessions ORDER BY id DESC LIMIT 50")


def list_cash_moves():
    return q("SELECT * FROM cash_moves ORDER BY id DESC LIMIT 80")


def stock_adjust(product_id, qty, note, kind="تسوية"):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_conn()
    row = conn.execute("SELECT stock, name_ar FROM products WHERE id=?", (product_id,)).fetchone()
    if not row:
        conn.close()
        raise ValueError("منتج غير موجود")
    new_stock = float(row["stock"] or 0) + float(qty)
    if new_stock < -1e-9:
        conn.close()
        raise ValueError(f"لا يمكن أن يصبح المخزون سالباً: {row['name_ar']}")
    conn.execute("UPDATE products SET stock = stock + ? WHERE id=?", (qty, product_id))
    conn.execute(
        "INSERT INTO stock_moves (created_at, product_id, kind, qty, note) VALUES (?,?,?,?,?)",
        (now, product_id, kind, qty, note),
    )
    conn.commit()
    conn.close()


def restore_db(src):
    src = Path(src)
    ok, msg = integrity_ok(src)
    if not ok:
        raise RuntimeError(f"الملف المصدر تالف: {msg}")
    dest = DB_PATH
    tmp = dest.with_suffix(".restore.tmp")
    shutil = __import__("shutil")
    shutil.copy2(src, tmp)
    ok2, msg2 = integrity_ok(tmp)
    if not ok2:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(msg2)
    bak = dest.with_suffix(".before_restore.db")
    if dest.exists():
        shutil.copy2(dest, bak)
    shutil.copy2(tmp, dest)
    tmp.unlink(missing_ok=True)
    return dest


def list_stock_moves():
    return q(
        """SELECT m.*, p.name_ar FROM stock_moves m LEFT JOIN products p ON p.id=m.product_id
           ORDER BY m.id DESC LIMIT 120"""
    )


def low_stock(limit=10):
    return q("SELECT * FROM products WHERE active=1 AND stock<=? ORDER BY stock", (limit,))


def profit_report(period="day"):
    conn = get_conn()
    if period == "day":
        where = "date(sl.created_at)=date('now','localtime')"
    elif period == "month":
        where = "strftime('%Y-%m', sl.created_at)=strftime('%Y-%m','now','localtime')"
    else:
        where = "strftime('%Y', sl.created_at)=strftime('%Y','now','localtime')"
    sales = conn.execute(
        f"""SELECT COALESCE(SUM(subtotal - COALESCE(discount,0)),0)
            FROM sales sl WHERE sl.status='completed' AND {where}"""
    ).fetchone()[0]
    costs = conn.execute(
        f"""SELECT COALESCE(SUM(si.qty * COALESCE(NULLIF(si.cost,0), p.cost, 0)),0)
            FROM sale_items si
            JOIN sales sl ON sl.id=si.sale_id AND sl.status='completed'
            LEFT JOIN products p ON p.id=si.product_id
            WHERE {where}"""
    ).fetchone()[0]
    exp = conn.execute(
        f"SELECT COALESCE(SUM(amount),0) FROM expenses WHERE {where.replace('sl.created_at','created_at')}"
    ).fetchone()[0]
    conn.close()
    sales, costs = float(sales or 0), float(costs or 0)
    return {"sales": sales, "costs": costs, "gross": sales - costs, "expenses": float(exp), "net": sales - costs - float(exp)}


def zakat_calc(gold_price_per_gram=0, extra_cash=0, use_sale_price=False):
    """زكاة عروض التجارة: (مخزون + نقد + ديون العملاء − ديون الموردين) × 2.5٪ إذا بلغ النصاب."""
    conn = get_conn()
    if use_sale_price:
        inv = conn.execute("SELECT COALESCE(SUM(stock * price),0) v FROM products WHERE active=1").fetchone()[0]
    else:
        inv = conn.execute("SELECT COALESCE(SUM(stock * COALESCE(cost,0)),0) v FROM products WHERE active=1").fetchone()[0]
    recv = conn.execute("SELECT COALESCE(SUM(debt),0) v FROM customers").fetchone()[0]
    pay = conn.execute("SELECT COALESCE(SUM(debt),0) v FROM suppliers").fetchone()[0]
    cash_row = conn.execute(
        "SELECT COALESCE(SUM(CASE WHEN kind='in' THEN amount ELSE -amount END),0) v FROM cash_moves"
    ).fetchone()
    ses = conn.execute("SELECT * FROM cash_sessions WHERE status='open' ORDER BY id DESC LIMIT 1").fetchone()
    cash_moves = float(cash_row[0] or 0)
    open_amt = float(ses["open_amount"] if ses else 0)
    conn.close()
    cash = open_amt + cash_moves + float(extra_cash or 0)
    if cash < 0:
        cash = 0
    inventory = float(inv or 0)
    receivables = float(recv or 0)
    payables = float(pay or 0)
    base = inventory + cash + receivables - payables
    if base < 0:
        base = 0
    nisab = float(gold_price_per_gram or 0) * 85.0  # نصاب الذهب ≈ 85 غراماً
    due = base >= nisab and nisab > 0
    amount = round(base * 0.025, 2) if due else 0.0
    return {
        "inventory": inventory,
        "cash": cash,
        "receivables": receivables,
        "payables": payables,
        "base": base,
        "nisab": nisab,
        "rate": 0.025,
        "due": due,
        "zakat": amount,
    }


def list_users_full():
    return q("SELECT * FROM users ORDER BY role, id")


def get_user(uid):
    return q("SELECT * FROM users WHERE id=?", (uid,), one=True)


def user_can(user, perm):
    if not user:
        return False
    if not user.get("active", 1):
        return False
    user = apply_role_permissions(user)
    if user.get("role") == "admin" or (user.get("username") or "").lower() == "admin":
        return True
    p = (user.get("permissions") or "")
    if p == "all":
        return True
    parts = {x.strip() for x in p.replace(";", ",").split(",") if x.strip()}
    return perm in parts or "all" in parts


def upsert_user(data, uid=None):
    if uid:
        q(
            """UPDATE users SET username=?, display_name=?, role=?, permissions=?,
               phone=?, salary=?, active=?, hire_date=? WHERE id=?""",
            (
                data["username"], data["display_name"], data["role"], data["permissions"],
                data.get("phone", ""), data.get("salary", 0), data.get("active", 1),
                data.get("hire_date", ""), uid,
            ),
            commit=True,
        )
        pw = data.get("password") or data.get("pin")
        if pw:
            set_user_password(uid, pw, must_change=False)
        return uid
    pw = data.get("password") or data.get("pin") or secrets.token_urlsafe(8)
    return q(
        """INSERT INTO users (username, display_name, pin, role, permissions, phone, salary, active, hire_date, password, must_change_pw)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (
            data["username"], data["display_name"], "",
            data["role"], data["permissions"], data.get("phone", ""),
            data.get("salary", 0), data.get("active", 1), data.get("hire_date", ""),
            sec.hash_password(pw), 1 if not data.get("password") else 0,
        ),
        commit=True,
    )


def deactivate_user(uid):
    q("UPDATE users SET active=0 WHERE id=?", (uid,), commit=True)


def log_login(pin, ok):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    q("INSERT INTO login_attempts (created_at, pin, ok) VALUES (?,?,?)",
      (now, pin[-2:].rjust(2, "*") if pin else "", int(ok)), commit=True)


def _networked(fn):
    def wrap(*args, **kwargs):
        import net_sync
        if net_sync.is_client():
            return net_sync.rpc(fn.__name__, list(args), kwargs)
        return fn(*args, **kwargs)
    wrap.__name__ = fn.__name__
    wrap.__doc__ = fn.__doc__
    return wrap


def failed_logins(minutes=15):
    row = q(
        "SELECT COUNT(*) n FROM login_attempts WHERE ok=0 AND created_at >= datetime('now','localtime',?)",
        (f"-{int(minutes)} minutes",), one=True,
    )
    return int(row["n"]) if row else 0


_NET_FUNCS = [
    "fetch_categories", "fetch_products", "find_by_barcode", "save_sale",
    "sales_today", "recent_sales", "all_products", "upsert_product", "delete_product",
    "authenticate_pin", "get_sale_by_invoice", "last_sale", "tax_rate",
    "upsert_category", "delete_category", "return_sale", "save_hold", "list_holds",
    "pop_hold", "report_overview", "list_customers", "get_customer", "upsert_customer",
    "add_debt", "pay_debt", "customer_ledger", "list_specs", "get_spec", "upsert_spec",
    "list_units", "list_suppliers", "upsert_supplier", "add_supplier_pay",
    "list_purchases", "save_purchase", "list_expenses", "add_expense",
    "open_session", "current_session", "cash_move", "close_session", "list_sessions",
    "list_cash_moves", "stock_adjust", "list_stock_moves", "low_stock", "profit_report",
    "list_users_full", "upsert_user", "deactivate_user", "get_user",
]
for _n in _NET_FUNCS:
    if _n in globals():
        globals()[_n] = _networked(globals()[_n])
