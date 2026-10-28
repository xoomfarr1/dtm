"""PySide6 GUI for the dts-monaco license-key generator."""

from __future__ import annotations

import sys

from PySide6 import QtWidgets

from .keygen import generate_key, get_hardware_id, parse_key, verify_key


class KeygenWindow(QtWidgets.QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("DTS-Monaco License Keygen")
        self.resize(640, 420)

        layout = QtWidgets.QVBoxLayout(self)

        form = QtWidgets.QFormLayout()
        self.edition = QtWidgets.QLineEdit("pro")
        self.days = QtWidgets.QSpinBox()
        self.days.setRange(0, 36500)
        self.days.setValue(365)
        self.name = QtWidgets.QLineEdit()
        self.hwid = QtWidgets.QLineEdit(get_hardware_id())
        form.addRow("Edition", self.edition)
        form.addRow("Days (0 = never)", self.days)
        form.addRow("Name", self.name)
        form.addRow("Hardware ID", self.hwid)
        layout.addLayout(form)

        btns = QtWidgets.QHBoxLayout()
        self.gen_btn = QtWidgets.QPushButton("Generate")
        self.verify_btn = QtWidgets.QPushButton("Verify")
        self.copy_btn = QtWidgets.QPushButton("Copy")
        btns.addWidget(self.gen_btn)
        btns.addWidget(self.verify_btn)
        btns.addWidget(self.copy_btn)
        layout.addLayout(btns)

        self.key_box = QtWidgets.QPlainTextEdit()
        self.key_box.setReadOnly(True)
        layout.addWidget(self.key_box)

        self.status = QtWidgets.QLabel("")
        layout.addWidget(self.status)

        self.gen_btn.clicked.connect(self.on_generate)
        self.verify_btn.clicked.connect(self.on_verify)
        self.copy_btn.clicked.connect(self.on_copy)

    def on_generate(self) -> None:
        key = generate_key(
            edition=self.edition.text().strip() or "pro",
            days=self.days.value(),
            name=self.name.text().strip(),
            hardware_id=self.hwid.text().strip() or None,
        )
        self.key_box.setPlainText(key)
        self.status.setText("Generated.")

    def on_verify(self) -> None:
        key = self.key_box.toPlainText().strip()
        ok = verify_key(key, hardware_id=self.hwid.text().strip() or None)
        lic = parse_key(key)
        if ok:
            self.status.setText(f"VALID: {lic.edition} / {lic.name} / {lic.hardware_id}")
        else:
            self.status.setText("INVALID or hardware mismatch or expired.")

    def on_copy(self) -> None:
        QtWidgets.QApplication.clipboard().setText(self.key_box.toPlainText().strip())
        self.status.setText("Copied to clipboard.")


def main(argv=None) -> int:
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv if argv is None else argv)
    w = KeygenWindow()
    w.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
