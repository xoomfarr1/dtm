"""Bus logger: permanent storage for captured bus frames.

Every CAN frame the bus monitor sees is saved here, along with a
timestamp, so the user can review it later. We use SQLite because it's
fast, reliable, and the data is easy to query.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

# SQLite database location
DB_FILE = Path(__file__).parent.parent / "data" / "bus_monitor.db"


class BusLogger:
    """Stores bus frames in a local SQLite database.

    The user's bus monitor calls `log_frame()` for each frame; when the
    user wants to review, we query the database.
    """

    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or DB_FILE
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self) -> None:
        """Create the tables if they don't exist."""
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS bus_frames (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    source TEXT NOT NULL,
                    frame_hex TEXT NOT NULL,
                    ecu_name TEXT
                )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_frames_time ON bus_frames(timestamp)")
            conn.commit()
            conn.close()

    def log_frame(self, session: Session, frame: bytes, timestamp: float) -> int:
        """Store one frame and return its ID."""
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO bus_frames (timestamp, source, frame_hex, ecu_name) "
                "VALUES (?, ?, ?, ?)",
                (timestamp, "unknown", frame.hex(), session.ecu_name)
            )
            conn.commit()
            frame_id = cur.lastrowid
            conn.close()
            return frame_id

    def get_frames(self, limit: int = 1000, offset: int = 0) -> list[dict]:
        """Return the most recent frames."""
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute(
                "SELECT id, timestamp, source, frame_hex, ecu_name "
                "FROM bus_frames ORDER BY id DESC LIMIT ? OFFSET ?",
                (limit, offset)
            )
            rows = cur.fetchall()
            conn.close()
            return [dict(r) for r in rows]

    def get_frame_count(self) -> int:
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM bus_frames")
            count = cur.fetchone()[0]
            conn.close()
            return count

    def clear(self) -> int:
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            cur.execute("DELETE FROM bus_frames")
            conn.commit()
            count = cur.rowcount
            conn.close()
            return count
