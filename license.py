import base64
import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path
import os
import uuid

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

ROOT = Path(__file__).resolve().parent
APP_DIR = Path(os.getenv("APPDATA", str(Path.home()))) / "ALASIL"
LICENSE_FILE = APP_DIR / "license.json"

_PUBLIC_KEY_B64 = "0tM8wUGcJztZiBLGVFnKr3jszKCBbtcKPZWM2iWH7iA="


def machine_id():
    raw = f"{uuid.getnode()}|{Path.home()}"
    import hashlib
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16].upper()


def _b64decode(value):
    value += "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value.encode("ascii"))


def _verify_token(token):
    try:
        parts = token.strip().split(".")
        if len(parts) != 3 or parts[0] != "AL2":
            return None, "صيغة الترخيص غير صحيحة"

        payload_bytes = _b64decode(parts[1])
        signature = _b64decode(parts[2])

        public_bytes = base64.b64decode(_PUBLIC_KEY_B64)
        public_key = Ed25519PublicKey.from_public_bytes(public_bytes)
        public_key.verify(signature, payload_bytes)

        payload = json.loads(payload_bytes.decode("utf-8"))

        if payload.get("v") != 2:
            return None, "إصدار الترخيص غير مدعوم"

        customer = str(payload.get("customer", "")).strip()
        machine = str(payload.get("machine", "")).strip().upper()
        issued_text = str(payload.get("issued", "")).strip()
        days = payload.get("days")

        if not customer:
            return None, "اسم العميل غير موجود"

        if not re.fullmatch(r"[0-9A-F]{16}", machine):
            return None, "معرف الجهاز داخل الترخيص غير صحيح"

        if not isinstance(days, int) or isinstance(days, bool) or days < 0:
            return None, "مدة الترخيص غير صحيحة"

        issued = date.fromisoformat(issued_text)
        today = date.today()

        if issued > today:
            return None, "License issue date cannot be in the future."

        expiry = None if days == 0 else issued + timedelta(days=days)

        return {
            "valid": True,
            "name": customer,
            "customer": customer,
            "machine": machine,
            "issued": issued.isoformat(),
            "days": days,
            "expiry": expiry.isoformat() if expiry else "Lifetime",
            "expired": bool(expiry and today > expiry),
            "mismatch": machine != machine_id(),
            "tampered": False,
        }, None

    except Exception:
        return None, "فشل التحقق من توقيع الترخيص أو بياناته"


def activate(key):
    try:
        record, error = _verify_token(key)

        if error or not record:
            return False, error or "الترخيص غير صالح"

        if record["mismatch"]:
            return False, "هذا الترخيص مخصص لجهاز آخر"

        if record["expired"]:
            return False, "انتهت مدة الترخيص"

        APP_DIR.mkdir(parents=True, exist_ok=True)

        temp_file = LICENSE_FILE.with_suffix(".tmp")
        temp_file.write_text(
            json.dumps({"token": key.strip()}, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        temp_file.replace(LICENSE_FILE)

        return True, "تم تفعيل ALASIL بنجاح"

    except Exception as exc:
        return False, f"تعذر حفظ الترخيص: {exc}"


def current_license():
    empty = {
        "valid": False,
        "name": "",
        "customer": "",
        "machine": "",
        "issued": "",
        "days": 0,
        "expiry": "",
        "expired": False,
        "mismatch": False,
        "tampered": False,
    }

    try:
        if not LICENSE_FILE.exists():
            return empty

        data = json.loads(LICENSE_FILE.read_text(encoding="utf-8"))
        token = data.get("token", "")
        record, error = _verify_token(token)

        if error or not record:
            empty["tampered"] = True
            return empty

        if record["mismatch"] or record["expired"]:
            record["valid"] = False
        else:
            record["valid"] = True

        return record

    except Exception:
        empty["tampered"] = True
        return empty


def is_activated():
    record = current_license()
    return bool(record.get("valid"))
