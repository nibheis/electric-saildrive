#!/usr/bin/env python3
"""CAN message logger — writes raw dumps in cansend format."""
import os
import threading
from datetime import datetime
from typing import List, Optional, Tuple

LOGS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")


class CANLogger:
    """Thread-safe logger that records every CAN frame before PGN filtering.

    Output format (one line per frame, cansend compatible):
        18F00400#FFFFFFFF1027FFFF
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active = False
        self._file: Optional[object] = None
        self._path: Optional[str] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> str:
        """Open a new dump file and return its path."""
        with self._lock:
            if self._active:
                return self._path or ""
            os.makedirs(LOGS_DIR, exist_ok=True)
            filename = f"candump_{datetime.now().strftime('%Y%m%d_%H%M%S')}.dump"
            self._path = os.path.join(LOGS_DIR, filename)
            self._file = open(self._path, "w")
            self._active = True
            return self._path

    def stop(self) -> None:
        """Close the current dump file."""
        with self._lock:
            if not self._active:
                return
            self._active = False
            if self._file:
                self._file.close()
                self._file = None
            self._path = None

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def log(self, eid: int, data: bytes) -> None:
        """Write a single frame to the open dump file."""
        with self._lock:
            if not self._active or self._file is None:
                return
            payload = "".join(f"{b:02X}" for b in data)
            self._file.write(f"{eid:08X}#{payload}\n")
            self._file.flush()

    def is_active(self) -> bool:
        with self._lock:
            return self._active

    # ------------------------------------------------------------------
    # File listing
    # ------------------------------------------------------------------

    def list_files(self) -> List[Tuple[str, int, float]]:
        """Return [(filename, size_bytes, mtime), ...] sorted by name."""
        if not os.path.exists(LOGS_DIR):
            return []
        result = []
        for name in sorted(os.listdir(LOGS_DIR)):
            if name.endswith(".dump"):
                path = os.path.join(LOGS_DIR, name)
                st = os.stat(path)
                result.append((name, st.st_size, st.st_mtime))
        return result

    def delete_file(self, filename: str) -> bool:
        """Remove a dump file. Returns True if deleted."""
        path = os.path.join(LOGS_DIR, filename)
        try:
            os.remove(path)
            return True
        except OSError:
            return False

    def file_path(self, filename: str) -> str:
        return os.path.join(LOGS_DIR, filename)
