"""Simple Windows GUI - the "caveman-friendly" interface.

This is the ONLY part of the tool the user normally sees. It is deliberately:
  - Big buttons with simple labels
  - A step-by-step tutorial that explains what to do
  - Short, plain-English status messages (no jargon)
  - One thing at a time

We use PySide6 (Qt) because it looks like a proper Windows app and is
easy to design around.
"""

from __future__ import annotations

from pathlib import Path
from PySide6 import QtCore, QtGui, QtWidgets

from ..config import Settings, default_project
from ..explain import ELI5
from ..logic.engine import LogicEngine, Session
from ..hardware.base import CanHardwareAdapter, HardwareInfo, HardwareError
from ..hardware.pt3gvci import Pt3gVciAdapter, VirtualAdapter
from ..hardware.usb_dongle import UsbDongleAdapter
from ..data.smr_d import CodingTable
from ..logic.flashing import BusMonitor, FlashProgrammer


# =====================================================================
#  The main window
# =====================================================================
class SimpleWindow(QtWidgets.QWidget):
    """A single-window, single-purpose interface. No clutter."""

    def __init__(self, settings: Settings | None = None):
        super().__init__()
        self.settings = settings or Settings()
        self.eli5 = ELI5()
        self.engine = LogicEngine()
        self.session: Session | None = None
        self.monitor: BusMonitor | None = None
        self.flash_programmer: FlashProgrammer | None = None
        self._build_ui()

    # ------------------------------------------------------------------
    def _build_ui(self):
        """Create the window, panels, buttons, and tutorial."""
        self.setWindowTitle("DTS-Monaco - Vehicle Diagnostics")
        self.setFixedSize(self.settings.window_width, self.settings.window_height)

        # Main layout
        main = QtWidgets.QVBoxLayout(self)

        # --- Welcome / Home screen (shown until the user starts) ---
        self.welcome = QtWidgets.QWidget()
        self._build_welcome()
        main.addWidget(self.welcome)

        # --- The "real" workspace (hidden until the user wants it) ---
        self.workspace = QtWidgets.QWidget()
        self._build_workspace()
        self.workspace.hide()

        main.addWidget(self.workspace)

        # --- Bottom status bar (simple, friendly) ---
        self.status_bar = QtWidgets.QToolBar()
        self.status_label = QtWidgets.QLabel("Ready.")
        self.status_bar.addWidget(self.status_label)
        self.status_bar.setMovable(False)
        main.addLayout(self.status_bar.layout()) if False else main.addWidget(self.status_label)

        # --- Tutorial tooltip target (a small box at the bottom) ---
        self.tutorial_box = QtWidgets.QLabel("")
        self.tutorial_box.setStyleSheet(
            "background-color: #FFF8E1; border: 1px solid #FFD54F; "
            "padding: 12px; border-radius: 6px; font-size: 14px;"
        )
        main.addWidget(self.tutorial_box)

        self.show()

    # ------------------------------------------------------------------
    def _build_welcome(self):
        """The home screen - friendly, big buttons, no jargon."""
        w = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(w)
        layout.setSpacing(20)
        layout.setContentsMargins(40, 40, 40, 40)

        # Title
        title = QtWidgets.QLabel("DTS-MONACO")
        title.setStyleSheet("font-size: 32px; font-weight: bold; color: #1a237e;")
        title.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        # Subtitle
        subtitle = QtWidgets.QLabel("A safe, free tool for talking to your car's computers.")
        subtitle.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        # Welcome box (the ELI5 one)
        welcome_text = QtWidgets.QLabel(
            "This tool lets you talk to your car's computers (ECUs) using a simple, safe interface. "
            "It can read fault codes, read and write car settings, and more - but it changes nothing "
            "until you tell it to. Always keep a backup of important files."
        )
        welcome_text.setStyleSheet("font-size: 16px; color: #333;")
        welcome_text.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        # Buttons - one action at a time
        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addStretch()

        # Top button (most important)
        self.btn_connect = QtWidgets.QPushButton("1. Connect to my car")
        self.btn_connect.setObjectName("primary")
        self.btn_connect.clicked.connect(self.on_connect_clicked)
        btn_row.addWidget(self.btn_connect)

        btn_row.addStretch()

        # Bottom row
        self.btn_tutorial = QtWidgets.QPushButton("How does this work? (tutorial)")
        self.btn_tutorial.clicked.connect(self.on_tutorial_clicked)
        self.btn_basics = QtWidgets.QPushButton("Start with the basics")
        self.btn_basics.clicked.connect(self.on_basics_clicked)

        btn_row.addWidget(self.btn_tutorial)
        btn_row.addWidget(self.btn_basics)

        layout.addWidget(title)
        layout.addSpacing(10)
        layout.addWidget(subtitle)
        layout.addSpacing(10)
        layout.addWidget(welcome_text)
        layout.addSpacing(20)
        layout.addLayout(btn_row)
        layout.addStretch()

        self.welcome = w

    # ------------------------------------------------------------------
    def _build_workspace(self):
        """The main workspace - a simple step-by-step wizard style."""
        w = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(w)

        # Step title
        self.step_title = QtWidgets.QLabel("Choose what you want to do")
        self.step_title.setStyleSheet("font-size: 20px; font-weight: bold; color: #1a237e;")

        # Tabs (one tab per operation, like a simple wizard)
        self.tabs = QtWidgets.QTabWidget()

        # Tab 1: Read fault codes
        self.tab_dtc = QtWidgets.QWidget()
        self._build_tab_dtc()
        self.tabs.addTab(self.tab_dtc, "Read fault codes (check for problems)")

        # Tab 2: Read / write coding tables
        self.tab_code = QtWidgets.QWidget()
        self._build_tab_code()
        self.tabs.addTab(self.tab_code, "Read / write car settings")

        # Tab 3: USB monitor (bus monitor)
        self.tab_mon = QtWidgets.QWidget()
        self._build_tab_monitor()
        self.tabs.addTab(self.tab_mon, "Watch the car talk (bus monitor)")

        # Tab 4: Flash
        self.tab_flash = QtWidgets.QWidget()
        self._build_tab_flash()
        self.tabs.addTab(self.tab_flash, "Flash / update ECU software")

        layout.addWidget(self.step_title)
        layout.addWidget(self.tabs)

        # Common buttons row
        self.workspace_buttons = QtWidgets.QHBoxLayout()
        self.workspace_buttons.addStretch()

        self.btn_back = QtWidgets.QPushButton("< Back")
        self.btn_back.clicked.connect(self.on_back_clicked)
        self.workspace_buttons.addWidget(self.btn_back)

        self.workspace_buttons.addStretch()

        self.btn_done = QtWidgets.QPushButton("Done")
        self.btn_done.clicked.connect(self.on_done_clicked)
        self.workspace_buttons.addWidget(self.btn_done)

        self.btn_calc = QtWidgets.QPushButton("⊞")
        self.btn_calc.setFixedSize(34, 34)
        self.btn_calc.setToolTip("Open the calculator")
        self.btn_calc.clicked.connect(self._toggle_calc)
        self.workspace_buttons.addWidget(self.btn_calc)

        self._calc_dock: CalculatorDrawer | None = None
        self._calc_open = False

        layout.addLayout(self.workspace_buttons)
        self.workspace = w

    # ------------------------------------------------------------------
    #  Drawer calculator (iOS-style sidebar)
    # ------------------------------------------------------------------
    def _toggle_calc(self):
        """Open or close the calculator drawer."""
        if self._calc_dock is None:
            self._calc_dock = CalculatorDrawer(parent=self, dark=self.settings.dark_mode)
            self._sync_calc_geometry()
            self._calc_dock.setWindowFlags(
                QtCore.Qt.FramelessWindowHint | QtCore.Qt.WindowStaysOnTopHint
            )
            self._calc_dock.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground)
        if self._calc_dock.isVisible():
            self._hide_calc()
        else:
            self._show_calc()

    def _show_calc(self):
        self._calc_dock.show()
        self._calc_open = True
        self.btn_calc.setText("−")
        self.btn_calc.setToolTip("Close the calculator")

    def _hide_calc(self):
        self._calc_dock.hide()
        self._calc_open = False
        self.btn_calc.setText("⊞")
        self.btn_calc.setToolTip("Open the calculator")

    def _sync_calc_geometry(self):
        """Position the drawer against the right edge of the window."""
        if self._calc_dock is None:
            return
        width = self.settings.window_width
        height = self.settings.window_height
        calc_width = self._calc_dock.width()
        self._calc_dock.setGeometry(width - calc_width, 0, calc_width, height)

    # ------------------------------------------------------------------
    #  Tutorial / message helpers
    # ------------------------------------------------------------------
    def _update_tutorial(self, text: str):
        """Update the tutorial message box (bottom of window)."""
        self.tutorial_box.setText(text)
        self.tutorial_box.repaint()

    def _set_status(self, message: str):
        """Update the status bar at the bottom."""
        self.status_label.setText(message)

    # ------------------------------------------------------------------
    #  Helper: format captured bus monitor frames for the log
    # ------------------------------------------------------------------
    def _monitor_summary(self) -> str:
        """Short human-friendly summary of the captured bus frames."""
        if self.monitor is None or not self.monitor.messages:
            return "No frames captured yet."
        lines = [f"{len(self.monitor.messages)} frames captured."]
        for msg in self.monitor.messages[-5:]:
            frame = msg["frame"]
            lines.append(f"  {msg['timestamp']:.3f}s  {frame[:16]}…")
        return "\n".join(lines)
    def on_connect_clicked(self):
        """Step 1: Connect to the car."""
        adapter = self.engine.new_session(adapter=VirtualAdapter()).adapter
        self.session = self.engine.new_session(
            ecu_name="unknown ECU",
            adapter=adapter,
        )
        # Switch to the tab for reading fault codes
        self.tabs.setCurrentWidget(self.tab_dtc)
        self.step_title.setText("Step 1: Read the fault codes")
        self._update_tutorial("Let's read the car's fault codes. Press 'Read fault codes' below.")
        self._set_status("Connected. Ready to read.")

    def on_tutorial_clicked(self):
        """Show the tutorial."""
        self._update_tutorial(
            "The tutorial has 4 steps:\n\n"
            "1. Read fault codes - see what problems the car has found\n"
            "2. Read / write settings - change car settings (like a digital menu)\n"
            "3. Watch the car talk - see every message on the car's network\n"
            "4. Flash - update the car's computer software\n\n"
            "Click 'Done' when you're ready."
        )

    def on_basics_clicked(self):
        """Simple starter explanation."""
        self._update_tutorial(
            "Let's go slow. We'll start with something simple:\n\n"
            "'Read fault codes' means asking the car, 'What problems have you had today?'\n\n"
            "The car will reply with a list of numbers (fault codes). Each number tells a story.\n\n"
            "Click 'Read fault codes' in the tab above to start."
        )

    # ------------------------------------------------------------------
    def on_back_clicked(self):
        """Go back to the welcome screen."""
        self.workspace.hide()
        self.welcome.show()
        self._update_tutorial("You're back at the start. Here you can:\n- Connect to your car\n- Read the tutorial\n- Start with the basics")
        self._set_status("Ready.")

    def on_done_clicked(self):
        """Close the app."""
        self.close()

    # ------------------------------------------------------------------
    def _build_tab_dtc(self):
        """Tab 1: Read fault codes."""
        w = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(w)

        self.txt_dtc_log = QtWidgets.QTextEdit()
        self.txt_dtc_log.setReadOnly(True)
        self.txt_dtc_log.setPlainText("Waiting to read fault codes...")
        layout.addWidget(self.txt_dtc_log, 1)

        btn_row = QtWidgets.QHBoxLayout()
        self.btn_read_dtc = QtWidgets.QPushButton("Read fault codes")
        self.btn_read_dtc.clicked.connect(self.on_read_dtc_clicked)
        btn_row.addWidget(self.btn_read_dtc)
        btn_row.addStretch()
        self.btn_clear_dtc = QtWidgets.QPushButton("Clear fault codes")
        self.btn_clear_dtc.clicked.connect(self.on_clear_dtc_clicked)
        btn_row.addWidget(self.btn_clear_dtc)
        layout.addLayout(btn_row)

        w.setLayout(layout)
        self.tab_dtc = w

    def on_read_dtc_clicked(self):
        if not self.session:
            self._update_tutorial("You need to connect to your car first. Press '1. Connect to my car'.")
            return
        codes, message = self.engine.read_fault_codes(self.session)
        self.txt_dtc_log.setPlainText(message or "No fault codes found. The car is clean.")
        self._update_tutorial(self.eli5.explain_read("fault codes"))
        self._set_status("Fault codes read.")

    def on_clear_dtc_clicked(self):
        if not self.session:
            self._update_tutorial("You need to connect to your car first.")
            return
        ok, message = self.engine.clear_fault_codes(self.session)
        self.txt_dtc_log.setPlainText(message)
        self._update_tutorial(self.eli5.explain_step("clear", "the car's fault codes"))
        self._set_status("Fault codes cleared.")

    # ------------------------------------------------------------------
    def _build_tab_code(self):
        """Tab 2: Read / write coding tables."""
        w = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(w)
        layout.setSpacing(10)

        # Log
        self.txt_code_log = QtWidgets.QTextEdit()
        self.txt_code_log.setReadOnly(True)
        self.txt_code_log.setPlainText("Read a coding table to see its bytes above.")
        layout.addWidget(self.txt_code_log, 1)

        # Table identifier
        row = QtWidgets.QHBoxLayout()
        self.lbl_code_table = QtWidgets.QLabel("Coding table (decimal or hex ID):")
        self.txt_code_table = QtWidgets.QLineEdit()
        self.txt_code_table.setPlaceholderText("e.g. 0x2001 or 8193")
        row.addWidget(self.lbl_code_table)
        row.addWidget(self.txt_code_table)
        layout.addLayout(row)

        # Value to write
        row2 = QtWidgets.QHBoxLayout()
        self.lbl_code_value = QtWidgets.QLabel("Value (hex bytes):")
        self.txt_code_value = QtWidgets.QLineEdit()
        self.txt_code_value.setPlaceholderText("e.g. 01 02 03")
        row2.addWidget(self.lbl_code_value)
        row2.addWidget(self.txt_code_value)
        layout.addLayout(row2)

        # Buttons
        btn_row = QtWidgets.QHBoxLayout()
        self.btn_read_code = QtWidgets.QPushButton("Read coding table")
        self.btn_read_code.clicked.connect(self.on_read_code_clicked)
        btn_row.addWidget(self.btn_read_code)
        btn_row.addStretch()
        self.btn_write_code = QtWidgets.QPushButton("Write coding table")
        self.btn_write_code.clicked.connect(self.on_write_code_clicked)
        btn_row.addWidget(self.btn_write_code)
        layout.addLayout(btn_row)

        w.setLayout(layout)
        self.tab_code = w

    def on_read_code_clicked(self):
        if not self.session:
            self._update_tutorial("Connect to your car first. Press '1. Connect to my car'.")
            return
        table_id_text = self.txt_code_table.text().strip()
        if not table_id_text:
            self._update_tutorial("Type a coding table ID, then press 'Read coding table'.")
            return
        try:
            table_id = int(table_id_text, 0)
        except ValueError:
            self._update_tutorial("That table ID doesn't look right. Use decimal or hex (like 0x2001).")
            return
        table = CodingTable(table_id=table_id, table_name="user table", size=4, data_type="U8")
        self._set_status("Reading coding table...")
        payload, message = self.engine.read_coding_table(self.session, table)
        if payload is None:
            self.txt_code_log.setPlainText(f"Error: {message}")
        else:
            self.txt_code_log.setPlainText(f"Read {len(payload)} bytes: {payload.hex(' ')}")
        self._update_tutorial(self.eli5.explain_read(f"coding table 0x{table_id:x}"))
        self._set_status("Coding table read.")

    def on_write_code_clicked(self):
        if not self.session:
            self._update_tutorial("Connect to your car first. Press '1. Connect to my car'.")
            return
        table_id_text = self.txt_code_table.text().strip()
        value_text = self.txt_code_value.text().strip()
        if not table_id_text:
            self._update_tutorial("Type a coding table ID, then press 'Write coding table'.")
            return
        if not value_text:
            self._update_tutorial("Type a value to write, then press 'Write coding table'.")
            return
        try:
            table_id = int(table_id_text, 0)
        except ValueError:
            self._update_tutorial("That table ID doesn't look right. Use decimal or hex (like 0x2001).")
            return
        try:
            value = bytes.fromhex(value_text.replace(" ", ""))
        except ValueError:
            self._update_tutorial("That value isn't valid hex. Use pairs of hex digits (like 01 02 03).")
            return
        table = CodingTable(table_id=table_id, table_name="user table", size=len(value), data_type="U8")
        self._set_status("Writing coding table...")
        ok, message = self.engine.write_coding_table(self.session, table, value)
        self.txt_code_log.setPlainText("OK" if ok else f"Error: {message}")
        self._update_tutorial(self.eli5.explain_write(f"coding table 0x{table_id:x}", value.hex(" ")))
        self._set_status("Coding table written.")

    # ------------------------------------------------------------------
    def _build_tab_monitor(self):
        """Tab 3: Bus monitor."""
        w = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(w)
        layout.setSpacing(10)

        self.txt_monitor = QtWidgets.QTextEdit()
        self.txt_monitor.setReadOnly(True)
        self.txt_monitor.setPlainText("Bus monitor not running.\nPress 'Start' to watch the car's network.")
        layout.addWidget(self.txt_monitor, 1)

        btn_row = QtWidgets.QHBoxLayout()
        self.btn_start_mon = QtWidgets.QPushButton("Start monitor")
        self.btn_start_mon.clicked.connect(self.on_start_mon_clicked)
        btn_row.addWidget(self.btn_start_mon)
        btn_row.addStretch()
        self.btn_stop_mon = QtWidgets.QPushButton("Stop monitor")
        self.btn_stop_mon.clicked.connect(self.on_stop_mon_clicked)
        btn_row.addWidget(self.btn_stop_mon)
        layout.addLayout(btn_row)

        w.setLayout(layout)
        self.tab_mon = w

    def on_start_mon_clicked(self):
        if not self.session:
            self._update_tutorial("Connect to your car first. Press '1. Connect to my car'.")
            return
        if self.monitor is None:
            self.monitor = BusMonitor(self.session)
        self._set_status("Starting bus monitor...")
        result = self.monitor.start()
        self.txt_monitor.setPlainText(result + "\n\n" + self._monitor_summary())
        self._update_tutorial(self.eli5.explain_monitor("start"))
        self._set_status("Bus monitor running...")

    def on_stop_mon_clicked(self):
        if self.monitor is None:
            self._update_tutorial("The bus monitor isn't running.")
            return
        self._set_status("Stopping bus monitor...")
        result = self.monitor.stop()
        self.txt_monitor.setPlainText(result + "\n\n" + self._monitor_summary())
        self._update_tutorial(self.eli5.explain_monitor("stop"))
        self._set_status("Bus monitor stopped.")

    # ------------------------------------------------------------------
    def _build_tab_flash(self):
        """Tab 4: Flash / firmware update."""
        w = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(w)
        layout.setSpacing(10)

        self.txt_flash = QtWidgets.QTextEdit()
        self.txt_flash.setReadOnly(True)
        self.txt_flash.setPlainText("Flash your ECU's software here.")
        layout.addWidget(self.txt_flash, 1)

        row = QtWidgets.QHBoxLayout()
        self.lbl_flash_file = QtWidgets.QLabel("Firmware file:")
        self.txt_flash_file = QtWidgets.QLineEdit()
        self.txt_flash_file.setPlaceholderText("e.g. C:\\firmware.bin")
        row.addWidget(self.lbl_flash_file)
        row.addWidget(self.txt_flash_file)
        layout.addLayout(row)

        btn_row = QtWidgets.QHBoxLayout()
        self.btn_flash = QtWidgets.QPushButton("Flash ECU")
        self.btn_flash.clicked.connect(self.on_flash_clicked)
        btn_row.addWidget(self.btn_flash)
        btn_row.addStretch()
        self.btn_stop_flash = QtWidgets.QPushButton("Stop flash")
        self.btn_stop_flash.clicked.connect(self.on_stop_flash_clicked)
        btn_row.addWidget(self.btn_stop_flash)
        layout.addLayout(btn_row)

        w.setLayout(layout)
        self.tab_flash = w

    def on_flash_clicked(self):
        if not self.session:
            self._update_tutorial("Connect to your car first. You can't flash without a connection.")
            return
        file_path = self.txt_flash_file.text().strip()
        if not file_path:
            self._update_tutorial("Choose a firmware file to flash, then press 'Flash ECU'.")
            return
        self._set_status("Preparing flash...")
        self.flash_programmer = self.flash_programmer or FlashProgrammer(self.session)
        self.flash_programmer.start_job(ecu_name=self.session.ecu_name, file_path=file_path)
        ok, message = self.flash_programmer.run()
        self.txt_flash.setPlainText("OK" if ok else f"Error: {message}")
        self._update_tutorial(self.eli5.explain_flash(self.session.ecu_name, file_path))
        self._set_status("Flash in progress...")

    def on_stop_flash_clicked(self):
        if self.flash_programmer is None:
            self._update_tutorial("There is no flash job running.")
            return
        self._set_status("Stopping flash...")
        message = self.flash_programmer.abort()
        self.txt_flash.setPlainText(message)
        self._update_tutorial("The flash upload has been stopped. The car is safe.")
        self._set_status("Flash stopped.")

    # ------------------------------------------------------------------
    #  Tutorial / message helpers
    # ------------------------------------------------------------------
    def _update_tutorial(self, text: str):
        """Update the tutorial message box (bottom of window)."""
        self.tutorial_box.setText(text)
        self.tutorial_box.repaint()

    def _set_status(self, message: str):
        """Update the status bar at the bottom."""
        self.status_label.setText(message)

    # ------------------------------------------------------------------
    def show(self):
        self.welcome.show()
        self.workspace.hide()
        super().show()

    # ------------------------------------------------------------------
    def start(self):
        """Start the app (Qt event loop)."""
        self.show()
        self.raise_()
        self.activateWindow()


# =====================================================================
#  Supporting classes wrapped together
# =====================================================================
# BusMonitor and FlashProgrammer are imported from dts_monaco.logic.flashing
# (see the module-level imports above).


class CalculatorDrawer(QtWidgets.QWidget):
    """iOS-style calculator drawer - a rounded panel with a clean button
    grid, shown as a sidebar from the right side of the window."""

    _BUTTONS = [
        ("C", 0, 0, 1, "func"),
        ("±", 0, 1, 1, "func"),
        ("%", 0, 2, 1, "func"),
        ("÷", 0, 3, 1, "op"),
        ("7", 1, 0, 1, "digit"),
        ("8", 1, 1, 1, "digit"),
        ("9", 1, 2, 1, "digit"),
        ("×", 1, 3, 1, "op"),
        ("4", 2, 0, 1, "digit"),
        ("5", 2, 1, 1, "digit"),
        ("6", 2, 2, 1, "digit"),
        ("−", 2, 3, 1, "op"),
        ("1", 3, 0, 1, "digit"),
        ("2", 3, 1, 1, "digit"),
        ("3", 3, 2, 1, "digit"),
        ("+", 3, 3, 1, "op"),
        ("0", 4, 0, 2, "digit"),
        (".", 4, 2, 1, "digit"),
        ("=", 4, 3, 1, "eq"),
    ]

    def __init__(self, parent: QtWidgets.QWidget | None = None, dark: bool = True):
        super().__init__(parent)
        self.dark = dark
        self._current = "0"
        self._pending_operator: str | None = None
        self._waiting = False
        self._last_value = 0.0
        self.setFixedWidth(300)
        self._build_ui()

    def _style_sheet(self) -> str:
        if self.dark:
            return (
                "QWidget { background-color: #1c1c1e; }\n"
                "QPushButton { color: #ffffff; border: none; border-radius: 14px; "
                "padding: 14px 0; font-size: 20px; min-width: 0; }\n"
                "QPushButton:focus { background-color: #58585c; }\n"
                "QPushButton#eq { background-color: #ff9500; color: #1c1c1e; }\n"
                "QPushButton#op { background-color: #ff9500; color: #1c1c1e; }\n"
                "QPushButton#func { background-color: #333336; }\n"
                "QPushButton#digit { background-color: #333336; }\n"
            )
        return (
            "QWidget { background-color: #ffffff; }\n"
            "QPushButton { color: #1c1c1e; border: none; border-radius: 14px; "
            "padding: 14px 0; font-size: 20px; min-width: 0; }\n"
            "QPushButton:focus { background-color: #bfbfbf; }\n"
            "QPushButton#eq { background-color: #ff9500; color: #ffffff; }\n"
            "QPushButton#op { background-color: #ff9500; color: #ffffff; }\n"
            "QPushButton#func { background-color: #dcdcdc; }\n"
            "QPushButton#digit { background-color: #dcdcdc; }\n"
        )

    def _build_ui(self):
        # Transparent base so the main window shows through the sides
        self.setStyleSheet("QWidget { background-color: transparent; }")

        card = QtWidgets.QWidget()
        card.setStyleSheet(
            "QWidget { background-color: #1c1c1e; border-radius: 16px; }"
            if self.dark
            else "QWidget { background-color: #ffffff; border-radius: 16px; }"
        )
        layout = QtWidgets.QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # Header with a close button
        header = QtWidgets.QHBoxLayout()
        self.hdr_label = QtWidgets.QLabel("Calculator")
        self.hdr_label.setStyleSheet("color: #8e8e8e; font-size: 16px;")
        header.addWidget(self.hdr_label)
        header.addStretch()
        self.btn_close = QtWidgets.QPushButton("×")
        self.btn_close.setFixedSize(28, 28)
        self.btn_close.setStyleSheet("color: #8e8e8e; font-size: 18px;")
        self.btn_close.clicked.connect(self.close)
        header.addWidget(self.btn_close)
        layout.addLayout(header)

        # Display
        self.display = QtWidgets.QLabel("0")
        self.display.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter
        )
        self.display.setStyleSheet("color: #ffffff; font-size: 32px; padding: 8px;")
        layout.addWidget(self.display)

        # Clean rounded button grid
        grid = QtWidgets.QGridLayout()
        grid.setSpacing(8)
        for text, row, col, colspan, kind in self._BUTTONS:
            btn = QtWidgets.QPushButton(text)
            btn.setProperty("kind", kind)
            btn.setSizePolicy(
                QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding
            )
            btn.setStyleSheet(self._style_sheet())
            if kind == "digit":
                btn.clicked.connect(lambda checked, t=text: self._on_digit(t))
            elif kind == "op":
                btn.clicked.connect(lambda checked, t=text: self._on_operator(t))
            elif kind == "func":
                if text == "C":
                    btn.clicked.connect(lambda: self._on_clear())
                elif text == "±":
                    btn.clicked.connect(lambda: self._on_toggle_sign())
                elif text == "%":
                    btn.clicked.connect(lambda: self._on_percent())
            elif kind == "eq":
                btn.clicked.connect(lambda: self._on_equal())
            grid.addWidget(btn, row, col, 1, colspan)
        layout.addLayout(grid)

        # Subtle drop shadow
        try:
            shadow = QtWidgets.QGraphicsDropShadowEffect()
            shadow.setBlurRadius(14)
            shadow.setOffset(0, 4)
            shadow.setColor(QtGui.QColor(0, 0, 0, 60))
            card.setGraphicsEffect(shadow)
        except Exception:
            pass

        self.setLayout(QtWidgets.QVBoxLayout(self))
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.layout().addWidget(card)

    # --- calculator interaction logic ---
    def _on_digit(self, text: str):
        if self._waiting:
            self._current = text
            self._waiting = False
        else:
            if self._current in ("0", ""):
                self._current = text
            else:
                self._current += text
        self._refresh_display()

    def _on_decimal(self):
        if self._waiting:
            self._current = "0."
            self._waiting = False
        elif "." in self._current:
            return
        else:
            self._current += "."
        self._refresh_display()

    def _on_operator(self, op: str):
        self._pending_operator = op
        self._waiting = True
        try:
            self._last_value = float(self._current)
        except ValueError:
            self._last_value = 0.0

    def _on_equal(self):
        if self._pending_operator is None:
            return
        try:
            right = float(self._current)
            left = self._last_value
        except ValueError:
            return
        result = None
        if self._pending_operator == "+":
            result = left + right
        elif self._pending_operator == "−":
            result = left - right
        elif self._pending_operator == "×":
            result = left * right
        elif self._pending_operator == "÷":
            if right == 0:
                self._current = "Error"
                self._refresh_display()
                self._pending_operator = None
                return
            result = left / right
        self._current = self._format_number(result)
        self._refresh_display()
        self._pending_operator = None
        self._last_value = result

    def _on_clear(self):
        self._current = "0"
        self._pending_operator = None
        self._last_value = 0.0
        self._waiting = False
        self._refresh_display()

    def _on_toggle_sign(self):
        if self._current in ("0", "Error"):
            return
        self._current = self._current[1:] if self._current.startswith("-") else "-" + self._current
        self._refresh_display()

    def _on_percent(self):
        try:
            self._current = self._format_number(float(self._current) / 100.0)
        except ValueError:
            return
        self._refresh_display()

    @staticmethod
    def _format_number(value: float) -> str:
        if value.is_integer():
            return str(int(value))
        return f"{value:.6g}"

    def _refresh_display(self):
        try:
            value = float(self._current)
            if value.is_integer():
                text = str(int(value))
            else:
                text = f"{value:.6g}"
        except ValueError:
            text = self._current
        self.display.setText(text)
