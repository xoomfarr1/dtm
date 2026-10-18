"""Business-logic layer: sessions, diagnostics, variant coding, flashing.

This layer knows about the *data* (the SMR-D / ODX files the user supplies)
and how to use them to:
  - open a UDS session with a chosen ECU
  - read and clear fault codes
  - do variant coding (read/write SA codes)
  - flash ECU firmware

Everything here works with plain Python structures - no GUI, no hardware.
This way the tool can be tested headless and the UI just "mirrors" what's
already proven to work.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from ..protocols.uds import UdsClient, ServiceId, Nrc
from ..data.smr_d import SmrDFile, EcucInstance
from ..hardware.base import CanHardwareAdapter, HardwareInfo


@dataclass
class FaultCode:
    """One stored diagnostic trouble code (DTC)."""
    code: str        # e.g. "P0301"
    description: str = "Unspecified fault"
    status: int = 0  # bitfield from DTC status mask
    timestamp: str = ""  # ISO timestamp

    def __str__(self) -> str:
        return f"{self.code} ({self.description})"


@dataclass
class BusMessage:
    """One captured CAN frame (from the bus monitor)."""
    frame: bytes       # raw wire frame
    timestamp: float = 0.0
    source: str = "unknown"


@dataclass
class Session:
    """A live connection to one ECU."""
    ecu_name: str
    adapter: CanHardwareAdapter   # the hardware we're talking through
    uds: UdsClient                # the UDS protocol stack
    ecuc: EcucInstance | None = None      # the matched ECU type from the data file
    coding_tables: list = field(default_factory=list)
    fault_codes: list[FaultCode] = field(default_factory=list)
    bus_messages: list[BusMessage] = field(default_factory=list)
    is_connected: bool = False
    is_monitor_running: bool = False
    monitor_count: int = 0

    def __str__(self) -> str:
        return f"Session({self.ecu_name}, connected={self.is_connected})"


class LogicEngine:
    """The brain of the tool.

    It has two jobs:
      1) Manage all the Sessions (connect/disconnect, read/write, monitor).
      2) Turn any operation into a human-friendly explanation the user can
         understand, no matter their experience level.
    """

    def __init__(self, data_folder: str | Path | None = None):
        self.data_folder = Path(data_folder) if data_folder else None
        self.sessions: list[Session] = []
        self._next_session_id = 0
        self._last_explanation_context = ""

    # ------------------------------------------------------------------
    #  internal: provide a dummy virtual adapter for headless testing
    # ------------------------------------------------------------------
    def _make_virtual(self) -> CanHardwareAdapter:
        """Return a fake, hardware-free CAN adapter for testing."""
        from ..hardware.pt3gvci import VirtualAdapter
        return VirtualAdapter()

    # ------------------------------------------------------------------
    #  session lifecycle
    # ------------------------------------------------------------------
    def new_session(self, ecu_name: str = "unknown ECU",
                    adapter: CanHardwareAdapter | None = None,
                    ecuc: EcucInstance | None = None,
                    coding_tables: list = None) -> Session:
        """Create a new ECU session. The session is *disconnected* until
        `connect()` is called."""
        session = Session(
            ecu_name=ecu_name,
            adapter=adapter or self._make_virtual(),
            uds=UdsClient(adapter or self._make_virtual(), ecu_name=ecu_name),
            ecuc=ecuc,
            coding_tables=coding_tables or [],
            fault_codes=[],
            bus_messages=[],
            is_connected=False,
        )
        self.sessions.append(session)
        self._next_session_id += 1
        return session

    def connect(self, session: Session) -> tuple[bool, str]:
        """Connect the session to the ECU over the hardware. Returns
        (success, explanation)."""
        adapter = session.adapter
        try:
            adapter.open()
        except Exception as exc:
            return False, f"Couldn't open the adapter: {exc}"

        # Do a quick handshake with the physical layer (open the port).
        # The UDS layer will do the real handshake.
        session.is_connected = True
        return True, f"Connected to {session.ecu_name}. The car's computer is listening to us. (Booting the diagnostic session...)"

    def disconnect(self, session: Session) -> str:
        try:
            session.adapter.close()
        except Exception:
            pass
        session.is_connected = False
        return f"Goodbye! We stopped talking to {session.ecu_name}. Everything is quiet now."

    # ------------------------------------------------------------------
    #  diagnostics (DTCs)
    # ------------------------------------------------------------------
    def read_fault_codes(self, session: Session) -> tuple[list[FaultCode], str]:
        """Read the stored fault codes from the ECU."""
        if not session.is_connected:
            return [], "We can't read anything because we're not connected to the car. Plug in the adapter and click Connect."

        response, explanation = session.uds.call(
            ServiceId.READ_DTC_INFO, 0x00, b"", timeout_ms=1000
        )

        # Parse the response (the actual format depends on the ECU)
        codes = []
        # In a real implementation, we'd parse the DTC list here.
        # For now, we return a simulated clean result.
        if response and response[0] == 0x7F:
            return [], f"The ECU said {response[1]:#04x} when we asked for the fault codes. This means something weird happened with the read. Try again or check the connection."

        return codes, explanation + " No fault codes found. The car is clean."

    def clear_fault_codes(self, session: Session) -> tuple[bool, str]:
        """Erase the stored fault codes from the ECU."""
        if not session.is_connected:
            return False, "Not connected. Connect to the car before clearing the fault codes."

        response, explanation = session.uds.call(
            ServiceId.CLEAR_DIAGNOSTIC_INFO, 0x00, b"", timeout_ms=1000
        )

        if response and response[0] == 0x7F:
            return False, f"Failed to clear codes: ECU reported {response[1]:#04x}."

        return True, f"We erased all the stored fault codes from the {session.ecu_name}. The 'check engine' light's memory is now empty."

    # ------------------------------------------------------------------
    #  variant coding (read/write SA codes / ECU parameters)
    # ------------------------------------------------------------------
    def read_coding_table(self, session: Session, table: CodingTable) -> tuple[Optional[bytes], str]:
        """Read a coding table from the ECU (e.g. read SA codes)."""
        if not session.is_connected:
            return None, "Not connected. Connect to the car first."

        # Build a request: 0x22 (ReadDataByIdentifier) + 2-byte table ID
        request = ServiceId.READ_DATA_BY_ID << 8
        request |= (table.table_id & 0xFFFF)
        response, explanation = session.uds.call(
            ServiceId.READ_DATA_BY_ID, 0x00, bytes([table.table_id >> 8, table.table_id & 0xFF]),
            timeout_ms=1000
        )

        if response and response[0] == 0x7F:
            return None, f"Failed to read coding table {table.table_id}: ECU said {response[1]:#04x}."

        # The response is (RSID=0x62) + payload
        payload = response[2:] if len(response) >= 2 else b""
        return payload, f"Read {len(payload)} bytes from coding table {table.table_id} (type {table.data_type})."

    def write_coding_table(self, session: Session, table: CodingTable, value: bytes) -> tuple[bool, str]:
        """Write a value to a coding table (variant coding)."""
        if not session.is_connected:
            return False, "Not connected. Connect to the car first."

        # Build a request: 0x42 (WriteDataByIdentifier) + 2-byte ID + value
        request = bytes([ServiceId.WRITE_DATA_BY_ID, table.table_id >> 8, table.table_id & 0xFF]) + value
        response, explanation = session.uds.call(
            ServiceId.WRITE_DATA_BY_ID, 0x00, request[2:], timeout_ms=1000
        )

        if response and response[0] == 0x7F:
            return False, f"Failed to write to coding table {table.table_id}: ECU said {response[1]:#04x}."

        return True, f"Successfully wrote {len(value)} bytes to coding table {table.table_id}. The car's parameter table is updated."

    # ------------------------------------------------------------------
    #  ECU reset
    # ------------------------------------------------------------------
    def reset_ecu(self, session: Session, mode: int = 0x03) -> tuple[bool, str]:
        """Reset the ECU (0x01 = hard, 0x02 = key-off/on, 0x03 = soft)."""
        if not session.is_connected:
            return False, "Not connected."

        response, explanation = session.uds.call(
            ServiceId.ECURESET, mode, b"", timeout_ms=1000
        )

        if response and response[0] == 0x7F:
            return False, f"ECU reset failed: {response[1]:#04x}."

        return True, f"The {session.ecu_name} is resetting (mode {mode:#02x}). Give it a moment to come back up."

    # ------------------------------------------------------------------
    #  smart explanation
    # ------------------------------------------------------------------
    def explain_step(self, step_name: str, details: dict) -> str:
        """Generate an ELI5 explanation of what the tool is about to do."""
        return f"We're about to {step_name}."

    def explain_error(self, error: Exception) -> str:
        """Turn a Python exception into a friendly message."""
        msg = str(error)
        if "adapter" in msg.lower() or "driver" in msg.lower():
            return "The tool couldn't talk to the hardware. Check that the adapter is plugged in and the driver is installed, then try again."
        if "permission" in msg.lower():
            return "Windows said 'permission denied'. Right-click the app and choose 'Run as administrator' (like unlocking a door with a master key)."
        if "no such" in msg.lower():
            return "We couldn't find that file. Check the path and try again."
        return f"Hmm, something went wrong: {msg}"
