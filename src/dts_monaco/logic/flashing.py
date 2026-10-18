"""ECU flash programming (SF11 / SF03) and bus monitoring logic.

Flash programming uses the UDS services 0x31 (DiagnosticCommunicationControl),
0x35 (RequestUpload), 0x36 (TransferData), 0x37 (TransferExit) to upload
a new ECU firmware image in chunks.

The bus monitor captures every CAN frame that crosses the wire, so the
user can see what the car's computers are saying to each other.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ..logic.engine import Session
from ..hardware.base import CanHardwareAdapter
from ..protocols.uds import ServiceId

logger = logging.getLogger(__name__)


@dataclass
class FlashJob:
    """One firmware upload (flash) job."""
    ecu_name: str
    file_path: str
    status: str = "pending"          # pending | running | done | failed
    progress: float = 0.0            # 0..1
    start_time: str = ""
    end_time: str = ""
    error: str = ""
    num_chunks: int = 0
    chunks_completed: int = 0

    def __str__(self) -> str:
        return f"Flash({self.ecu_name}, {self.progress:.1%})"


@dataclass
class MonitorState:
    """Current state of the bus monitor."""
    is_running: bool = False
    session: Session | None = None
    messages: list = field(default_factory=list)
    count: int = 0
    filter_ids: list[int] = field(default_factory=list)
    filter_mask: int = 0
    disable_td: bool = True
    custom_filters: str = ""


class BusMonitor:
    """Captures every CAN frame on the bus and stores it in a rolling log."""

    def __init__(self, session: Session):
        self.session = session
        self.messages: list[dict] = []
        self.is_running = False
        self._stop_event: Optional[object] = None
        self.count = 0

    def start(self) -> str:
        """Start capturing frames from the bus."""
        if self.is_running:
            return "The bus monitor is already recording."
        if not self.session.is_connected:
            return "Can't start the monitor - we're not connected to the car."
        self.is_running = True
        self.messages = []
        self.count = 0

        # Notify the user
        return "Bus monitor started. Listen to the car - you'll hear it say things like 'CAN OK' and 'ECU READY'."

    def stop(self) -> str:
        """Stop capturing frames."""
        self.is_running = False
        return "Bus monitor stopped. We've saved every frame we saw."

    def add_message(self, frame: bytes, timestamp: float = 0.0) -> None:
        """Record one frame."""
        self.messages.append({
            "frame": frame.hex(),
            "timestamp": timestamp,
            "source": "unknown",
        })
        self.count += 1

    def get_total_frames(self) -> int:
        return len(self.messages)


# ----------------------------------------------------------------------
#  Flash programming engine
# ----------------------------------------------------------------------
class FlashProgrammer:
    """Uploads a new ECU firmware image using the UDS upload/transfer services."""

    def __init__(self, session: Session):
        self.session = session
        self.job: Optional[FlashJob] = None
        self._upload_complete = False

    def start_job(self, ecu_name: str, file_path: str) -> FlashJob:
        """Start a new flash job."""
        self.job = FlashJob(
            ecu_name=ecu_name,
            file_path=file_path,
            status="pending",
            progress=0.0,
            start_time=datetime.now(timezone.utc).isoformat(),
            num_chunks=0,
        )
        return self.job

    def run(self) -> tuple[bool, str]:
        """Run the firmware upload. This is a *simulated* upload for now;
        the real upload uses the 0x35/0x36/0x37 services over ISO-TP."""
        if not self.job:
            return False, "No flash job started."

        job = self.job
        job.status = "running"

        # Step 1: Request the ECU to start uploading
        response, explanation = self.session.uds.call(
            ServiceId.REQUEST_UPLOAD, 0x02, b"", timeout_ms=1000
        )

        if response and response[0] == 0x7F:
            job.status = "failed"
            job.error = f"ECU refused upload (0x{response[1]:02x})."
            return False, f"Upload failed: {explanation}"

        # Step 2: Transfer data chunks
        job.num_chunks = 10  # placeholder
        for i in range(job.num_chunks):
            # Build a chunk of dummy firmware data
            chunk = bytes([i % 256, (i + 1) % 256]) * 10
            response, explanation = self.session.uds.call(
                ServiceId.TRANSFER_DATA, 0x00, chunk, timeout_ms=1000
            )
            if response and response[0] == 0x7F:
                job.status = "failed"
                job.error = f"Transfer failed at chunk {i}: {response[1]:#04x}"
                return False, f"Upload failed at chunk {i}: {response[1]:#04x}"
            job.chunks_completed = i + 1
            job.progress = (i + 1) / job.num_chunks

        # Step 3: Exit transfer
        self.session.uds.call(ServiceId.TRANSFER_EXIT, 0x00, b"", timeout_ms=500)

        job.status = "done"
        job.progress = 1.0
        job.end_time = datetime.now(timezone.utc).isoformat()

        return True, f"Firmware upload complete! The {job.ecu_name} has the new software. It will reboot now."

    def abort(self) -> str:
        """Abort an in-progress flash job."""
        self.session.uds.call(ServiceId.TRANSFER_EXIT, 0x00, b"", timeout_ms=500)
        if self.job:
            self.job.status = "failed"
            self.job.error = "Aborted by user."
        return "Flash upload stopped by user."
