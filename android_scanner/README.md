# ALASIL سكانر — تطبيق أندرويد

يفتح نفس صفحة المسح `http://IP:8765/?t=alasil` داخل التطبيق مع صلاحية الكاميرا.

## بناء APK من Android Studio
1. ثبّت [Android Studio](https://developer.android.com/studio)
2. File → Open → مجلد `android_scanner`
3. انتظر Gradle Sync
4. Build → Build Bundle(s) / APK(s) → **Build APK(s)**
5. الملف يظهر في: `app/build/outputs/apk/debug/app-debug.apk`

انقل الـ APK للهاتف وثبّته (اسمح بالمصادر غير المعروفة).

## الاستخدام
1. شغّل ALASIL POS على الكمبيوتر
2. اضغط **مسح باركود** (الخادم يعمل على المنفذ 8765)
3. افتح التطبيق → ⚙️ أدخل **IP الكمبيوتر** (من `ipconfig`) والمنفذ `8765` والرمز `alasil`
4. الهاتف والكمبيوتر على نفس الواي فاي
5. اسمح للكاميرا وامسح — المنتج يُضاف في السلة

USB: إن استخدمت ADB reverse اجعل العنوان `127.0.0.1`

لا يمكن توليد ملف APK موقّع من بيئة التطوير الحالية بدون Android SDK؛ افتح المشروع في Android Studio كما فوق.
