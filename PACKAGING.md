# تغليف ALASIL لويندوز

## التشغيل
```
cd alasil_pos
pip install -r requirements.txt
python main.py
```

## بناء exe (على ويندوز)
```
pip install pyinstaller
pyinstaller --noconfirm --windowed --name ALASIL --add-data "styles.qss;." --add-data "assets;assets" main.py
```
لا تضع `license.key` أو `license_gen.py` في حزمة الزبون.

مولّد التراخيص: شغّل `python license_gen.py` عند البائع فقط، أو ابنِ exe منفصلاً:
```
pyinstaller --noconfirm --windowed --name ALASIL_Keys license_gen.py
```

## قاعدة البيانات
- الوضع: SQLite WAL + busy_timeout.
- النسخ الاحتياطي من ERP يستخدم `sqlite3.backup` ثم `PRAGMA integrity_check`.
- لا تنسخ الملف يدوياً أثناء التشغيل إن أمكن؛ استخدم شاشة النسخ الاحتياطي.

## شاشات
الواجهة تتكيف مع حجم النافذة (تخطيط مرن). حجم الخط الافتراضي ≥ 15 من الإعدادات.
