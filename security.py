"""تجزئة كلمات المرور (bcrypt) بدون تخزين النص الأصلي."""
from __future__ import annotations

import bcrypt

PREFIX = "$2"


def hash_password(plain: str) -> str:
    pw = (plain or "").encode("utf-8")
    if len(pw) > 72:
        pw = pw[:72]
    return bcrypt.hashpw(pw, bcrypt.gensalt(rounds=12)).decode("ascii")


def is_hashed(value: str) -> bool:
    v = value or ""
    return v.startswith("$2a$") or v.startswith("$2b$") or v.startswith("$2y$")


def verify_password(plain: str, stored: str) -> bool:
    if not stored:
        return False
    if not is_hashed(stored):
        return False
    try:
        return bcrypt.checkpw((plain or "").encode("utf-8")[:72], stored.encode("ascii"))
    except Exception:
        return False
