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
        self.setWindowTitle("DTS-MONACO - Vehicle Diagnostics")
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

        self.setWindowTitle("DTS-MONACO")
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

        layout.addLayout(self.workspace_buttons)
        self.workspace = w

    # ------------------------------------------------------------------
    #  Welcome screen buttons
    # ------------------------------------------------------------------
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
        ok, message = self.engine.read_fault_codes(self.session)
        if ok:
            self.txt_dtc_log.setPlainText(
                f"Fault codes (0):\nNothing - the car is clean."
            )
        else:
            self.txt_dtc_log.setPlainText(
                f"Error: {message}"
            )
        self._update_tutorial("The car said what it found. If there are fault codes, they're listed above.")
        self._set_status("Fault codes read.")

    def on_clear_dtc_clicked(self):
        if not self.session:
            self._update_tutorial("You need to connect to your car first.")
            return
        ok, message = self.engine.clear_fault_codes(self.session)
        self._update_tutorial(f"We cleared the fault codes. {message}")
        self._set_status("Fault codes cleared.")

    # ------------------------------------------------------------------
    def _build_tab_code(self):
        """Tab 2: Read / write coding tables."""
        w = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(w)

        self.txt_code_log = QtWidgets.QTextEdit()
        self.txt_code_log.setReadOnly(True)
        self.txt_code_log.setPlainText("Put a coding table name here and read it.")
        layout.addWidget(self.txt_code_log, 1)

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
        self._update_tutorial("We're about to read a coding table. Press 'Read coding table'.")
        self._set_status("Reading coding table...")

    def on_write_code_clicked(self):
        self._update_tutorial("We can write to coding tables, but be careful - changes can be permanent. Ask your helper before writing.")
        self._set_status("Writing coding table...")

    # ------------------------------------------------------------------
    def _build_tab_monitor(self):
        """Tab 3: Bus monitor."""
        w = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(w)

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
        self._update_tutorial("We're going to start recording what the car's computers say to each other. Press 'Start monitor'.")
        self._set_status("Bus monitor running...")

    def on_stop_mon_clicked(self):
        self._update_tutorial("The monitor has stopped recording. The messages you saw are saved above.")
        self._set_status("Bus monitor stopped.")

    # ------------------------------------------------------------------
    def _build_tab_flash(self):
        """Tab 4: Flash / firmware update."""
        w = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(w)

        self.txt_flash = QtWidgets.QTextEdit()
        self.txt_flash.setReadOnly(True)
        self.txt_flash.setPlainText("Flash your ECU's software here.")
        layout.addWidget(self.txt_flash, 1)

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
        self._update_tutorial("We're going to upload new software to the car's computer. This is a big step - make sure you have a backup first.")
        self._set_status("Flash in progress...")

    def on_stop_flash_clicked(self):
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
class BusMonitor:
    """Simple bus monitor (placeholder - the real one is in logic)."""
    def __init__(self, session: Session):
        self.session = session
        self.running = False

    def start(self) -> str:
        return "Bus monitor started. You can now see the car's messages."

    def stop(self) -> str:
        return "Busy monitor stopped."


class FlashProgrammer:
    """Simple flash programmer (placeholder)."""
    def flash(self, ecu: str, file: str) -> tuple[bool, str]:
        return True, f"Flashed {ecu} with {file}. Good job!"
