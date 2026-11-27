import sys
import json
import base64
import re
from pathlib import Path
from datetime import date
from getpass import getpass

from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QLineEdit, QPushButton,
    QVBoxLayout, QHBoxLayout, QSpinBox, QComboBox,
    QMessageBox, QInputDialog
)
from PySide6.QtCore import Qt

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def app_folder():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def private_key_path():
    folder = app_folder()

    candidates = [
        folder / "license_private.pem",
        folder / "ALASIL ACTIV" / "license_private.pem",
        folder.parent / "ALASIL ACTIV" / "license_private.pem",
    ]

    for path in candidates:
        if path.exists():
            return path

    return candidates[0]


def b64url(data):
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


class LicenseGenerator(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ALASIL - Ed25519 License Generator")
        self.setMinimumWidth(480)

        layout = QVBoxLayout(self)

        title = QLabel("ALASIL License Generator")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size:22px;font-weight:bold;padding:12px")
        layout.addWidget(title)

        layout.addWidget(QLabel("اسم العميل"))
        self.customer = QLineEdit()
        self.customer.setPlaceholderText("Customer name")
        layout.addWidget(self.customer)

        layout.addWidget(QLabel("معرف الجهاز Machine ID"))
        self.machine = QLineEdit()
        self.machine.setPlaceholderText("16 characters, e.g. A1B2C3D4E5F60718")
        layout.addWidget(self.machine)

        layout.addWidget(QLabel("مدة الترخيص"))
        self.period = QComboBox()
        self.period.addItem("30 يوم", 30)
        self.period.addItem("90 يوم", 90)
        self.period.addItem("365 يوم", 365)
        self.period.addItem("730 يوم", 730)
        self.period.addItem("مدى الحياة", 0)
        self.period.addItem("مدة مخصصة", -1)
        layout.addWidget(self.period)

        self.custom_days = QSpinBox()
        self.custom_days.setRange(1, 36500)
        self.custom_days.setValue(30)
        self.custom_days.setEnabled(False)
        layout.addWidget(self.custom_days)

        self.period.currentIndexChanged.connect(self.period_changed)

        self.generate_button = QPushButton("إنشاء رمز التفعيل")
        self.generate_button.clicked.connect(self.generate)
        layout.addWidget(self.generate_button)

        layout.addWidget(QLabel("رمز التفعيل الناتج"))
        self.output = QLineEdit()
        self.output.setReadOnly(True)
        self.output.setPlaceholderText("AL2 token")
        layout.addWidget(self.output)

        buttons = QHBoxLayout()
        copy_button = QPushButton("نسخ الرمز")
        copy_button.clicked.connect(self.copy_token)
        buttons.addWidget(copy_button)

        clear_button = QPushButton("مسح")
        clear_button.clicked.connect(self.clear)
        buttons.addWidget(clear_button)

        layout.addLayout(buttons)

        self.status = QLabel("يجب إدخال Machine ID الخاص بجهاز العميل.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

    def period_changed(self):
        self.custom_days.setEnabled(self.period.currentData() == -1)

    def generate(self):
        customer = self.customer.text().strip()
        machine = self.machine.text().strip().upper()

        if not customer:
            QMessageBox.warning(self, "تنبيه", "أدخل اسم العميل.")
            return

        if not re.fullmatch(r"[0-9A-F]{16}", machine):
            QMessageBox.warning(
                self, "تنبيه",
                "أدخل Machine ID صحيحاً مكوناً من 16 خانة Hex."
            )
            return

        days = self.period.currentData()
        if days == -1:
            days = self.custom_days.value()

        path = private_key_path()
        if not path.exists():
            QMessageBox.critical(
                self, "المفتاح الخاص غير موجود",
                f"لم يتم العثور على الملف:\n{path}"
            )
            return

        password, ok = QInputDialog.getText(
            self,
            "كلمة مرور المفتاح الخاص",
            "أدخل كلمة مرور license_private.pem:",
            QLineEdit.Password
        )

        if not ok:
            return

        try:
            private_key = serialization.load_pem_private_key(
                path.read_bytes(),
                password=password.encode("utf-8")
            )

            if not isinstance(private_key, Ed25519PrivateKey):
                raise ValueError("المفتاح الخاص ليس Ed25519")

            payload = {
                "v": 2,
                "customer": customer,
                "machine": machine,
                "issued": date.today().isoformat(),
                "days": int(days),
            }

            payload_bytes = json.dumps(
                payload,
                ensure_ascii=False,
                separators=(",", ":")
            ).encode("utf-8")

            signature = private_key.sign(payload_bytes)

            token = (
                "AL2."
                + b64url(payload_bytes)
                + "."
                + b64url(signature)
            )

            self.output.setText(token)
            QApplication.clipboard().setText(token)
            self.status.setText(
                "تم إنشاء الترخيص ونسخه إلى الحافظة بنجاح."
            )

            QMessageBox.information(
                self, "نجاح",
                "تم إنشاء رمز التفعيل ونسخه إلى الحافظة."
            )

        except Exception as exc:
            QMessageBox.critical(
                self, "خطأ",
                "تعذر إنشاء الترخيص.\n"
                "تحقق من كلمة المرور وملف المفتاح الخاص.\n\n"
                + str(exc)
            )

    def copy_token(self):
        token = self.output.text().strip()
        if not token:
            QMessageBox.warning(self, "تنبيه", "لا يوجد رمز لنسخه.")
            return

        QApplication.clipboard().setText(token)
        QMessageBox.information(self, "نسخ", "تم نسخ الرمز.")

    def clear(self):
        self.customer.clear()
        self.machine.clear()
        self.output.clear()
        self.status.setText("تم مسح الحقول.")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = LicenseGenerator()
    window.show()
    sys.exit(app.exec())
