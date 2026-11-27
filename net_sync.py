"""ربط جهازين: خادم + عميل بكلمة سر عبر الشبكة المحلية."""
from __future__ import annotations

import hashlib
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

import database as db

PORT_DEFAULT = 9876
_server = None
_thread = None
_client = {"on": False, "host": "", "port": PORT_DEFAULT, "password": ""}

ALLOWED_RPC = {
    "fetch_categories", "fetch_products", "find_by_barcode", "save_sale",
    "sales_today", "recent_sales", "all_products", "upsert_product", "delete_product",
    "get_sale_by_invoice", "last_sale", "tax_rate",
    "upsert_category", "delete_category", "return_sale", "save_hold", "list_holds",
    "pop_hold", "report_overview", "list_customers", "get_customer", "upsert_customer",
    "add_debt", "pay_debt", "customer_ledger", "list_specs", "get_spec", "upsert_spec",
    "list_units", "list_suppliers", "upsert_supplier", "add_supplier_pay",
    "list_purchases", "save_purchase", "list_expenses", "add_expense",
    "open_session", "current_session", "cash_move", "close_session", "list_sessions",
    "list_cash_moves", "stock_adjust", "list_stock_moves", "low_stock", "profit_report",
    "get_setting",
}
BLOCK = {"get_conn", "q", "init_db", "ensure_erp", "ensure", "authenticate_user",
         "upsert_user", "deactivate_user", "set_user_password", "set_setting"}


def _hash(pw: str) -> str:
    return hashlib.sha256(("alasil-net|" + (pw or "")).encode("utf-8")).hexdigest()


def password() -> str:
    return db.get_setting("net_password", "123456")


def mode() -> str:
    return db.get_setting("net_mode", "local")  # local | server | client


def is_client() -> bool:
    return mode() == "client"


def configure_client():
    _client["on"] = is_client()
    _client["host"] = db.get_setting("net_host", "192.168.1.10")
    try:
        _client["port"] = int(db.get_setting("net_port", str(PORT_DEFAULT)))
    except ValueError:
        _client["port"] = PORT_DEFAULT
    _client["password"] = password()


def rpc(fn: str, args=None, kwargs=None):
    configure_client()
    payload = json.dumps({
        "fn": fn,
        "args": args or [],
        "kwargs": kwargs or {},
        "password": _hash(_client["password"]),
    }).encode("utf-8")
    url = f"http://{_client['host']}:{_client['port']}/rpc"
    req = Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(req, timeout=12) as r:
            data = json.loads(r.read().decode("utf-8"))
    except HTTPError as e:
        raise RuntimeError(f"رفض الخادم ({e.code})") from e
    except URLError as e:
        raise RuntimeError(f"تعذر الاتصال بالخادم {_client['host']}:{_client['port']} — {e.reason}") from e
    if not data.get("ok"):
        raise RuntimeError(data.get("error") or "خطأ شبكة")
    return data.get("result")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        return

    def _send(self, code, obj):
        raw = json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path.startswith("/ping"):
            self._send(200, {"ok": True, "app": "ALASIL", "mode": "server"})
        else:
            self._send(404, {"ok": False})

    def do_POST(self):
        if self.path != "/rpc":
            self._send(404, {"ok": False})
            return
        n = int(self.headers.get("Content-Length", "0") or 0)
        try:
            body = json.loads(self.rfile.read(n).decode("utf-8") or "{}")
        except json.JSONDecodeError:
            self._send(400, {"ok": False, "error": "JSON"})
            return
        if body.get("password") != _hash(password()):
            self._send(403, {"ok": False, "error": "كلمة سر الشبكة غير صحيحة"})
            return
        fn = str(body.get("fn") or "")
        if fn in BLOCK or fn not in ALLOWED_RPC or ".." in fn or not fn.isidentifier():
            self._send(403, {"ok": False, "error": "دالة غير مسموحة"})
            return
        func = getattr(db, fn, None)
        if not callable(func):
            self._send(404, {"ok": False, "error": "غير موجودة"})
            return
        try:
            args = body.get("args") or []
            kwargs = body.get("kwargs") or {}
            result = func(*args, **kwargs)
            self._send(200, {"ok": True, "result": result})
        except Exception as e:
            self._send(500, {"ok": False, "error": str(e)})


def start_server():
    global _server, _thread
    if _thread and _thread.is_alive():
        return True, int(db.get_setting("net_port", str(PORT_DEFAULT)))
    port = int(db.get_setting("net_port", str(PORT_DEFAULT)) or PORT_DEFAULT)
    _server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    _thread = threading.Thread(target=_server.serve_forever, daemon=True)
    _thread.start()
    return True, port


def stop_server():
    global _server
    if _server:
        _server.shutdown()
        _server = None
