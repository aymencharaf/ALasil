"""خادم محلي لجعل الهاتف قارئ باركود للكاشير."""
from __future__ import annotations

import json
import queue
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

PORT = 8765
TOKEN = ""
SCAN_QUEUE: queue.Queue[str] = queue.Queue()

SCAN_HTML = r"""<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1"/>
<title>ALASIL — قارئ باركود</title>
<style>
  *{box-sizing:border-box}
  body{margin:0;font-family:Tahoma,sans-serif;background:#071a4a;color:#fff;text-align:center}
  h1{margin:14px 0 4px;font-size:22px}
  p{color:#9bb4e8;margin:0 16px 12px}
  #video,#view{width:100%;max-width:420px;border-radius:16px;background:#000}
  .ok{color:#4ade80;min-height:28px;font-weight:700}
  input{width:90%;max-width:360px;padding:12px;border:none;border-radius:12px;font-size:16px;margin:8px}
  button{background:#1e5cff;color:#fff;border:none;border-radius:12px;padding:12px 20px;font-weight:800;margin:6px}
  button.g{background:#22c55e}
</style>
</head>
<body>
  <h1>ALASIL POS</h1>
  <p>وجّه الكاميرا نحو الباركود — يُرسل تلقائياً للكاشير</p>
  <video id="video" playsinline autoplay muted></video>
  <canvas id="view" style="display:none"></canvas>
  <div class="ok" id="status">جاري تشغيل الكاميرا…</div>
  <div>
    <input id="manual" placeholder="أو اكتب الباركود هنا" inputmode="numeric"/>
    <br/>
    <button class="g" id="send">إرسال</button>
  </div>
<script>
const TOKEN = "TOKEN_PLACE";
const video = document.getElementById('video');
const status = document.getElementById('status');
let last = "", lastAt = 0;

async function postCode(code){
  code = (code||'').trim();
  if(!code) return;
  const now = Date.now();
  if(code === last && now-lastAt < 1500) return;
  last = code; lastAt = now;
  status.textContent = 'تم الإرسال: ' + code;
  try{
    await fetch('/scan?token='+TOKEN, {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({code})
    });
    if(navigator.vibrate) navigator.vibrate(80);
  }catch(e){ status.textContent = 'تعذر الاتصال بالكاشير'; }
}

document.getElementById('send').onclick = () => {
  postCode(document.getElementById('manual').value);
  document.getElementById('manual').value='';
};
document.getElementById('manual').addEventListener('keydown', e=>{
  if(e.key==='Enter') document.getElementById('send').click();
});

async function start(){
  try{
    const stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: { ideal: 'environment' } }, audio:false
    });
    video.srcObject = stream;
    await video.play();
    status.textContent = 'الكاميرا جاهزة — امسح المنتج';
    if('BarcodeDetector' in window){
      const det = new BarcodeDetector({formats:['ean_13','ean_8','code_128','code_39','upc_a','upc_e','qr_code']});
      const loop = async () => {
        try{
          const codes = await det.detect(video);
          if(codes && codes[0]) postCode(codes[0].rawValue);
        }catch(_){}
        requestAnimationFrame(loop);
      };
      loop();
    } else {
      status.textContent = 'المتصفح لا يدعم القراءة التلقائية. اكتب الباركود أو استخدم Chrome على أندرويد.';
    }
  }catch(e){
    status.textContent = 'اسمح للكاميرا من إعدادات المتصفح. إن لم تعمل: اكتب الباركود يدوياً.';
  }
}
start();
</script>
</body></html>
"""


def lan_ip() -> str:
    ip = "127.0.0.1"
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
    except OSError:
        pass
    return ip


def scan_url() -> str:
    return f"http://{lan_ip()}:{PORT}/?t={TOKEN}"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        return

    def _ok(self, body: bytes, ctype="text/html; charset=utf-8"):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/scan.html"):
            html = SCAN_HTML.replace("TOKEN_PLACE", TOKEN or "")
            self._ok(html.encode("utf-8"))
        elif path == "/ping":
            self._ok(b'{"ok":true}', "application/json")
        elif path.startswith("/i/"):
            inv = path[3:].strip().split("?")[0]
            try:
                import database as db
                import receipt as receipt_mod
                sale, items = db.get_sale_by_invoice(inv)
                if not sale:
                    self.send_error(404)
                    return
                cashier = "ALASIL"
                try:
                    u = db.get_user(sale.get("user_id"))
                    if u:
                        cashier = u.get("display_name") or cashier
                except Exception:
                    pass
                tpl = db.get_setting("invoice_template", "teal") or "teal"
                html = receipt_mod.receipt_html(sale, items, cashier, "ar", tpl)
                self._ok(html.encode("utf-8"))
            except Exception as e:
                self._ok(f"<h1>خطأ</h1><p>{e}</p>".encode("utf-8"))
        else:
            self.send_error(404)

    def do_POST(self):
        u = urlparse(self.path)
        qs = parse_qs(u.query)
        if u.path != "/scan":
            self.send_error(404)
            return
        if qs.get("token", [""])[0] != TOKEN:
            self.send_error(403)
            return
        n = int(self.headers.get("Content-Length", "0") or 0)
        raw = self.rfile.read(n) if n else b"{}"
        try:
            data = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            data = {}
        code = str(data.get("code") or data.get("barcode") or "").strip()
        if code:
            SCAN_QUEUE.put(code)
        self._ok(b'{"ok":true}', "application/json")


_server = None
_thread = None


def start():
    global _server, _thread, TOKEN
    try:
        import database as db
        TOKEN = db.scan_token()
    except Exception:
        TOKEN = TOKEN or "local"
    if _thread and _thread.is_alive():
        return scan_url()
    _server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    _thread = threading.Thread(target=_server.serve_forever, daemon=True)
    _thread.start()
    return scan_url()


def stop():
    global _server
    if _server:
        _server.shutdown()
        _server = None


def adb_available():
    import shutil
    return shutil.which("adb") is not None


def adb_devices():
    import subprocess
    if not adb_available():
        return []
    try:
        out = subprocess.check_output(["adb", "devices"], text=True, timeout=8)
    except Exception:
        return []
    lines = [ln.strip() for ln in out.splitlines()[1:] if ln.strip()]
    return [ln for ln in lines if "device" in ln and "offline" not in ln]


def adb_reverse():
    """يربط منفذ الهاتف 8765 بمنفذ البرنامج عبر USB (ADB)."""
    import subprocess
    if not adb_available():
        return False, "ADB غير مثبت. ثبّت Android Platform Tools ثم أعد المحاولة."
    devs = adb_devices()
    if not devs:
        return False, "لا يوجد هاتف. فعّل تصحيح USB واقبل الرسالة على الهاتف."
    try:
        subprocess.check_output(
            ["adb", "reverse", f"tcp:{PORT}", f"tcp:{PORT}"],
            text=True, timeout=8,
        )
    except Exception as e:
        return False, f"فشل الربط: {e}"
    return True, f"http://127.0.0.1:{PORT}/?t={TOKEN}"


def usb_tether_ips():
    """عناوين شائعة عند تفعيل مشاركة الإنترنت عبر USB."""
    ips = []
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            ip = info[4][0]
            if ip.startswith(("192.168.42.", "192.168.43.", "192.168.137.", "192.168.0.", "192.168.1.")):
                if ip not in ips:
                    ips.append(ip)
    except OSError:
        pass
    return ips


def poll_codes():
    out = []
    while True:
        try:
            out.append(SCAN_QUEUE.get_nowait())
        except queue.Empty:
            break
    return out
