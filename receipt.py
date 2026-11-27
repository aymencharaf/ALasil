"""نماذج الفاتورة مع QR يفتح الفاتورة على الهاتف."""
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QSizeF, QMarginsF
from PySide6.QtGui import QPageSize, QPageLayout, QTextDocument
from PySide6.QtPrintSupport import QPrinter, QPrintDialog
from PySide6.QtWidgets import QDialog, QVBoxLayout, QPushButton, QTextBrowser

ASSETS = Path(__file__).resolve().parent / "receipts"
ASSETS.mkdir(exist_ok=True)

TEMPLATES = [
    {"id": "teal", "name": "فواتير Teal", "desc": "رأس تركوازي — Bill To"},
    {"id": "navy", "name": "شركة كحلي", "desc": "شريط كحلي وشارة برتقالية"},
    {"id": "contractor", "name": "مقاولات", "desc": "جدول أصناف مرقّم"},
    {"id": "orange", "name": "برتقالي + QR", "desc": "موجة برتقالية وتوقيع"},
    {"id": "gold", "name": "خدمات ذهبية", "desc": "جدول ذهبي وQR للدفع"},
]


def invoice_public_url(invoice_no: str) -> str:
    try:
        import scanner_server
        ip = scanner_server.lan_ip()
        port = scanner_server.PORT
        return f"http://{ip}:{port}/i/{invoice_no}"
    except Exception:
        return f"http://127.0.0.1:8765/i/{invoice_no}"


def _qr(invoice_no: str) -> str:
    try:
        from qrlib import qr_data_uri
        return qr_data_uri(invoice_public_url(invoice_no), scale=5, border=2)
    except Exception:
        return ""


def _store():
    try:
        import database as db
        return {
            "name": db.get_setting("store_name", "ALASIL POS") or "ALASIL POS",
            "phone": db.get_setting("store_phone", "0550 00 00 00") or "0550 00 00 00",
            "city": db.get_setting("store_city", "الجزائر") or "الجزائر",
        }
    except Exception:
        return {"name": "ALASIL POS", "phone": "0550 00 00 00", "city": "الجزائر"}


def _rows_html(items, cols="name,qty,price,total"):
    out = []
    for i, it in enumerate(items, 1):
        qty = it.get("qty") or 0
        price = float(it.get("price") or 0)
        total = float(it.get("total") or price * qty)
        name = it.get("name") or ""
        if cols == "num":
            out.append(
                f"<tr><td>{i:03d}</td><td>{name}</td><td style='text-align:center'>{qty}</td>"
                f"<td style='text-align:left'>{price:,.2f}</td><td style='text-align:left'>{total:,.2f}</td></tr>"
            )
        else:
            out.append(
                f"<tr><td>{name}</td><td style='text-align:center'>{qty}</td>"
                f"<td style='text-align:left'>{price:,.2f}</td><td style='text-align:left'>{total:,.2f}</td></tr>"
            )
    return "".join(out) or "<tr><td colspan='5' style='text-align:center'>لا توجد بنود</td></tr>"


def _method(sale):
    return {"cash": "نقداً", "card": "بطاقة", "mixed": "مختلط", "credit": "آجل"}.get(
        sale.get("payment_method"), sale.get("payment_method") or "—"
    )


def sample_sale():
    return {
        "invoice_no": "INV-MODEL-001",
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "subtotal": 3245.0,
        "discount": 50.0,
        "tax": 0.0,
        "total": 3195.0,
        "paid": 3195.0,
        "change_due": 0.0,
        "payment_method": "cash",
        "status": "completed",
    }, [
        {"name": "استشارة", "qty": 10, "price": 75, "total": 750},
        {"name": "إدارة مشروع", "qty": 15, "price": 85, "total": 1275},
        {"name": "تحليل بيانات", "qty": 8, "price": 100, "total": 800},
        {"name": "كتابة تقرير", "qty": 6, "price": 70, "total": 420},
    ]


def receipt_html(sale, items, cashier="ALASIL", lang="ar", template="teal"):
    st = _store()
    inv = str(sale.get("invoice_no") or "")
    qr = _qr(inv)
    qr_img = f"<img src='{qr}' width='110' height='110' alt='QR'/>" if qr else ""
    url = invoice_public_url(inv)
    method = _method(sale)
    dzd = "د.ج"
    rows = _rows_html(items)
    rows_n = _rows_html(items, "num")
    tpl = template or "teal"

    if tpl == "navy":
        return f"""
        <html dir="rtl"><body style="margin:0;font-family:Tahoma,sans-serif;background:#fff;color:#1e293b">
        <table width="100%" cellpadding="0" cellspacing="0"><tr>
          <td style="width:70px;background:#0f1f4b">&nbsp;</td>
          <td style="padding:28px 32px">
            <table width="100%"><tr>
              <td>
                <div style="font-size:22px;font-weight:900;color:#0f1f4b">{st['name']}</div>
                <div style="color:#64748b;font-size:12px">{st['city']} · {st['phone']}</div>
                <div style="margin-top:18px;font-size:12px">
                  <b>رقم الفاتورة</b> {inv}<br>
                  <b>التاريخ</b> {sale['created_at']}<br>
                  <b>الكاشير</b> {cashier}
                </div>
              </td>
              <td style="text-align:left">
                <div style="background:#f97316;color:white;display:inline-block;padding:10px 22px;font-weight:900;font-size:22px">INVOICE</div>
                <div style="margin-top:10px">{qr_img}</div>
                <div style="font-size:10px;color:#64748b;max-width:140px">{url}</div>
              </td>
            </tr></table>
            <table width="100%" cellpadding="8" cellspacing="0" style="margin-top:18px;border-collapse:collapse">
              <tr style="background:#0f1f4b;color:#fff"><th>الوصف</th><th>الكمية</th><th>السعر</th><th>المجموع</th></tr>
              {rows}
            </table>
            <table width="280" align="left" style="margin-top:12px">
              <tr><td>المجموع الفرعي</td><td>{sale['subtotal']:.2f}</td></tr>
              <tr><td>الخصم</td><td>{sale['discount']:.2f}</td></tr>
              <tr><td>الضريبة</td><td>{sale['tax']:.2f}</td></tr>
              <tr style="font-size:18px;font-weight:900"><td>الإجمالي</td><td>{sale['total']:.2f} {dzd}</td></tr>
            </table>
            <div style="clear:both;margin-top:40px;font-size:12px;color:#64748b">امسح QR لفتح هذه الفاتورة على الهاتف · طريقة الدفع: {method}</div>
          </td>
        </tr></table>
        </body></html>
        """

    if tpl == "contractor":
        return f"""
        <html dir="rtl"><body style="font-family:Tahoma;margin:28px;color:#0f172a">
          <table width="100%"><tr>
            <td><div style="font-size:36px;font-weight:900;color:#1e3a5f;letter-spacing:2px">INVOICE</div>
                <div>رقم: {inv}<br>التاريخ: {sale['created_at']}</div></td>
            <td style="text-align:left">
              <b>{st['name']}</b><br>{st['city']}<br>{st['phone']}<br>{qr_img}
            </td>
          </tr></table>
          <div style="background:#1e3a5f;color:#fff;padding:8px 12px;margin:16px 0;font-weight:800">بيانات الفاتورة</div>
          <div>الكاشير: {cashier} · الدفع: {method}</div>
          <table width="100%" cellpadding="8" cellspacing="0" style="margin-top:12px;border-collapse:collapse;border:1px solid #cbd5e1">
            <tr style="background:#e2e8f0"><th>#</th><th>الوصف</th><th>كمية</th><th>سعر الوحدة</th><th>المجموع</th></tr>
            {rows_n}
          </table>
          <table width="300" align="left" style="margin-top:10px">
            <tr><td>SUB TOTAL</td><td>{sale['subtotal']:.2f}</td></tr>
            <tr><td>TAX</td><td>{sale['tax']:.2f}</td></tr>
            <tr style="background:#1e3a5f;color:#fff;font-weight:900"><td>TOTAL AMOUNT DUE</td><td>{sale['total']:.2f} {dzd}</td></tr>
          </table>
          <p style="clear:both;font-size:11px;color:#64748b">امسح رمز QR لعرض الفاتورة: {url}</p>
        </body></html>
        """

    if tpl == "orange":
        return f"""
        <html dir="rtl"><body style="font-family:Tahoma;margin:0;color:#333">
          <div style="padding:28px 36px 8px">
            <table width="100%"><tr>
              <td><div style="width:70px;height:70px;border-radius:50%;background:#e85d04;color:#fff;text-align:center;line-height:70px;font-weight:900">Logo</div></td>
              <td style="text-align:center"><div style="font-size:36px;color:#e85d04;font-weight:800">Invoice</div>
                  <div>Number: {inv}</div></td>
              <td style="text-align:left">{qr_img}</td>
            </tr></table>
            <table width="100%" style="margin-top:12px;font-size:13px"><tr>
              <td>من الشركة: <b>{st['name']}</b> — {st['city']}</td>
              <td style="text-align:left">التاريخ: {sale['created_at']}</td>
            </tr></table>
            <table width="100%" cellpadding="10" cellspacing="0" style="margin-top:16px;border-collapse:collapse">
              <tr style="background:#ed7a3a;color:#fff"><th>No</th><th>Item</th><th>Price</th><th>Qty</th><th>Total</th></tr>
              {rows_n}
            </table>
            <table width="100%" style="margin-top:16px"><tr>
              <td>الضريبة: {sale['tax']:.2f}<br>الخصم: {sale['discount']:.2f}<br>الفرعي: {sale['subtotal']:.2f}</td>
              <td style="text-align:left;font-size:22px;font-weight:900;color:#e85d04">Total: {sale['total']:.2f} {dzd}</td>
            </tr></table>
            <p style="font-size:11px;color:#777">امسح QR لفتح الفاتورة على الهاتف</p>
            <div style="text-align:left;margin-top:24px">Signature ____________</div>
          </div>
          <div style="height:18px;background:linear-gradient(90deg,#e85d04,#f4a261);margin-top:20px"></div>
        </body></html>
        """

    if tpl == "gold":
        return f"""
        <html dir="rtl"><body style="font-family:Tahoma;background:#f6f1ea;margin:0;padding:24px;color:#3f3f3f">
          <div style="background:#fff;border-radius:18px;padding:24px;max-width:720px;margin:auto">
            <table width="100%"><tr>
              <td>
                <div style="color:#c9a227;font-size:22px;font-weight:900">Payment Invoice</div>
                <div>No. {inv}</div>
                <div style="margin-top:10px">الكاشير: {cashier}<br>التاريخ: {sale['created_at']}</div>
              </td>
              <td style="text-align:left">
                <div style="width:56px;height:56px;border-radius:50%;background:#1e3a5f;color:#fff;text-align:center;line-height:56px">★</div>
                <b>{st['name']}</b>
              </td>
            </tr></table>
            <table width="100%" cellpadding="10" cellspacing="0" style="margin-top:16px;border-collapse:collapse">
              <tr style="background:#c9a227;color:#fff"><th>الصنف</th><th>كمية</th><th>سعر</th><th>مجموع</th></tr>
              {rows}
            </table>
            <div style="text-align:left;margin-top:12px">
              خصم {sale['discount']:.2f} · ضريبة {sale['tax']:.2f}<br>
              <span style="font-size:22px;font-weight:900;color:#c9a227">المستحق {sale['total']:.2f} {dzd}</span>
            </div>
            <table width="100%" style="margin-top:16px"><tr>
              <td>{qr_img}<div style="font-size:11px;color:#888">امسح للدفع / فتح الفاتورة</div></td>
              <td style="text-align:left;color:#c9a227"><b>{st['name']}</b><br>{st['city']}<br>{st['phone']}<br>الدفع: {method}</td>
            </tr></table>
          </div>
        </body></html>
        """

    # teal (default) — like first image
    return f"""
    <html dir="rtl"><body style="font-family:Tahoma,sans-serif;margin:0;color:#334155">
      <div style="background:#0f766e;color:#fff;padding:22px 28px">
        <table width="100%"><tr>
          <td><div style="font-size:32px;font-weight:900">INVOICE</div>
              <div>Self-employed · {st['name']}</div></td>
          <td style="text-align:left;font-size:13px">{st['phone']}<br>{st['city']}<br>{cashier}</td>
        </tr></table>
      </div>
      <div style="padding:24px 28px">
        <table width="100%"><tr>
          <td>
            <div style="color:#0f766e;font-weight:800">Bill To</div>
            زبون المحل / نقطة البيع<br>الكاشير: {cashier}
          </td>
          <td style="text-align:left">
            <b>Invoice Number</b> {inv}<br>
            <b>Invoice Date</b> {sale['created_at']}<br>
            {qr_img}
            <div style="font-size:10px;color:#64748b">{url}</div>
          </td>
        </tr></table>
        <div style="margin:16px 0 8px;color:#0f766e;font-weight:800">Service Details</div>
        <table width="100%" cellpadding="8" cellspacing="0" style="border-collapse:collapse">
          <tr style="background:#ccfbf1"><th>الوصف</th><th>كمية</th><th>سعر</th><th>المجموع</th></tr>
          {rows}
        </table>
        <table width="260" align="left" style="margin-top:12px">
          <tr><td>Subtotal</td><td>{sale['subtotal']:.2f}</td></tr>
          <tr><td>Tax</td><td>{sale['tax']:.2f}</td></tr>
          <tr style="font-size:18px;font-weight:900;color:#0f766e"><td>Total Amount Due</td><td>{sale['total']:.2f} {dzd}</td></tr>
        </table>
        <div style="clear:both;margin-top:28px;font-size:12px;color:#64748b">
          امسح رمز QR بالهاتف لفتح هذه الفاتورة مباشرة.<br>طريقة الدفع: {method}
        </div>
      </div>
    </body></html>
    """


def show_and_print(parent, sale, items, cashier, lang="ar", template=None):
    import database as db
    tpl = template or db.get_setting("invoice_template", "teal") or "teal"
    html = receipt_html(sale, items, cashier, lang, tpl)
    try:
        (ASSETS / f"{sale['invoice_no']}.html").write_text(html, encoding="utf-8")
    except Exception:
        pass
    dlg = QDialog(parent)
    names = {t["id"]: t["name"] for t in TEMPLATES}
    dlg.setWindowTitle("فاتورة — " + names.get(tpl, tpl))
    dlg.resize(640, 720)
    lay = QVBoxLayout(dlg)
    view = QTextBrowser()
    view.setOpenExternalLinks(True)
    view.setHtml(html)
    lay.addWidget(view)
    btn = QPushButton("🖨  طباعة")
    btn.setStyleSheet("background:#2ea44f;color:white;padding:12px;border-radius:6px;font-weight:800;")

    def do_print():
        printer = QPrinter(QPrinter.HighResolution)
        dlg_p = QPrintDialog(printer, parent)
        if dlg_p.exec() == QPrintDialog.Accepted:
            doc = QTextDocument()
            doc.setHtml(html)
            doc.print_(printer)
        pdf = ASSETS / f"{sale['invoice_no']}.pdf"
        p2 = QPrinter(QPrinter.HighResolution)
        p2.setOutputFormat(QPrinter.PdfFormat)
        p2.setOutputFileName(str(pdf))
        doc2 = QTextDocument()
        doc2.setHtml(html)
        doc2.print_(p2)

    btn.clicked.connect(do_print)
    lay.addWidget(btn)
    close = QPushButton("إغلاق")
    close.clicked.connect(dlg.accept)
    lay.addWidget(close)
    dlg.exec()
    return html
