#!/usr/bin/env python3
"""J1939 Explorer - A terminal app to analyse live CAN J1939 data."""
import json
import os
import struct
import threading
import time
from collections import defaultdict, deque
from typing import Dict, Any, List, Optional, Set

try:
    import can
except ImportError:
    can = None


# ---------------------------------------------------------------------------
# J1939 utilities
# ---------------------------------------------------------------------------

def parse_eid(arbitration_id: int) -> tuple[int, int, int, int, int]:
    """Unpack 29-bit J1939 EID into priority, EDP, DP, PGN, SA.
    EID layout: pri(3) + R(1) + EDP(1) + DP(1) + PF(8) + PS(8) + SA(8)
    PGN = EDP + DP + PF + PS when PF >= 240 (broadcast)
    PGN = EDP + DP + PF + 0x00   when PF < 240 (dest addr specific)
    """
    priority = (arbitration_id >> 26) & 0x07
    e_dp = (arbitration_id >> 25) & 0x01    # Extended Data Page
    dp     = (arbitration_id >> 24) & 0x01
    pf     = (arbitration_id >> 16) & 0xFF
    ps     = (arbitration_id >>  8) & 0xFF
    sa     = arbitration_id & 0xFF

    if pf >= 240:
        pgn = (e_dp << 16) | (dp << 15) | (pf << 8) | ps
    else:
        pgn = (e_dp << 16) | (dp << 15) | (pf << 8)

    return priority, e_dp, dp, pgn, sa


# ---------------------------------------------------------------------------
# Dictionary loading
# ---------------------------------------------------------------------------

def load_dictionary(path: str) -> Dict[str, Any]:
    """Load J1939_dictionnary.json."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_display_pgn_set(dictionary: Dict[str, Any]) -> Set[int]:
    """Return set of displayable PGN integers from dictionary entries."""
    result = set()
    for pgn_str, pgndef in dictionary.items():
        if pgndef.get("display", False):
            result.add(int(pgn_str))
    return result


# ---------------------------------------------------------------------------
# Message store
# ---------------------------------------------------------------------------

class J1939MessageStore:
    """Thread-safe store for latest J1939 messages by arbitration_id."""

    def __init__(self):
        self._lock = threading.Lock()
        self.messages: Dict[int, Dict[str, Any]] = {}  # eid -> {ts, data, last_hex}
        self.timestamps_window = deque()  # (ts, eid)
        self._start = time.time()
        self._bus_connected = False

    def on_connect(self):
        with self._lock:
            self._bus_connected = True

    def on_disconnect(self):
        with self._lock:
            self._bus_connected = False

    def add(self, eid: int, data: bytes):
        t = time.time()
        hex_str = " ".join(f"{b:02X}" for b in data)
        with self._lock:
            self.messages[eid] = {"ts": t, "data": data, "hex": hex_str}
            self.timestamps_window.append((t, eid))
            # prune old timestamps > 15s
            cutoff = t - 15.0
            while self.timestamps_window and self.timestamps_window[0][0] < cutoff:
                self.timestamps_window.popleft()

    # ---- read helpers (acquire lock at call site) ----
    def get_latest(self, eid: int) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self.messages.get(eid)

    def get_all(self) -> List[tuple[int, float, str, bytes]]:
        """Return list of (eid, ts, hex, data_bytes) sorted by eid."""
        with self._lock:
            return sorted(
                [(eid, v["ts"], v["hex"], v["data"]) for eid, v in self.messages.items()],
                key=lambda x: x[0],
            )

    def get_latest_data_for_pgn(self, pgn: int) -> Optional[bytes]:
        """Return the latest payload for any EID matching the given PGN, or None."""
        with self._lock:
            # Iterate most-recent-first (store is a dict, iterate existing is fine)
            for eid, v in self.messages.items():
                _, _, _, msg_pgn, _ = parse_eid(eid)
                if msg_pgn == pgn:
                    return v["data"]
            return None

    def stats(self) -> Dict[str, Any]:
        """Return stats dict."""
        with self._lock:
            now = time.time()
            msgs_per_sec = {"1s": 0.0, "5s": 0.0, "15s": 0.0}

            cnt_1 = sum(1 for ts, _ in self.timestamps_window if now - ts <= 1.0)
            cnt_5 = sum(1 for ts, _ in self.timestamps_window if now - ts <= 5.0)
            cnt_15 = len(self.timestamps_window)

            msgs_per_sec["1s"] = float(cnt_1)
            msgs_per_sec["5s"] = float(cnt_5) / 5.0
            msgs_per_sec["15s"] = float(cnt_15) / 15.0

            # unique devices = SA, unique PGNs
            unique_sa = set()
            unique_pgn = set()
            for eid in self.messages:
                _, _, _, pgn, sa = parse_eid(eid)
                unique_sa.add(sa)
                unique_pgn.add(pgn)

            return {
                "connected": self._bus_connected,
                "uptime": now - self._start,
                "count": len(self.messages),
                "rate": msgs_per_sec,
                "devices": len(unique_sa),
                "pgns": len(unique_pgn),
            }


# ---------------------------------------------------------------------------
# CAN thread
# ---------------------------------------------------------------------------

class CANThread(threading.Thread):
    """Background thread reading from socketcan and storing displayable messages."""

    def __init__(
        self,
        channel: str = "can0",
        store: Optional[J1939MessageStore] = None,
        display_pgns: Optional[Set[int]] = None,
    ):
        super().__init__(daemon=True)
        self.channel = channel
        self.store = store or J1939MessageStore()
        self.display_pgns = display_pgns or set()
        self._stop = threading.Event()

    def run(self):
        if can is None:
            self.store.on_disconnect()
            return
        while not self._stop.is_set():
            try:
                with can.Bus(
                    interface="socketcan",
                    channel=self.channel,
                    receive_own_messages=False,
                ) as bus:
                    self.store.on_connect()
                    while not self._stop.is_set():
                        msg = bus.recv(timeout=0.1)
                        if msg is not None:
                            _, _, _, pgn, _ = parse_eid(msg.arbitration_id)
                            if self.display_pgns and pgn not in self.display_pgns:
                                continue
                            self.store.add(msg.arbitration_id, msg.data)
            except Exception:
                self.store.on_disconnect()
                if self._stop.wait(1.0):
                    return

    def stop(self):
        self._stop.set()


# ---------------------------------------------------------------------------
# Decoding helpers
# ---------------------------------------------------------------------------

def decode_spn(data: bytes, spn_spec: Dict[str, Any]) -> Optional[float]:
    """Decode a single SPN from the CAN payload."""
    byte_indices = spn_spec.get("bytes", [])
    if not byte_indices:
        return None
    if len(byte_indices) == 1:
        idx = byte_indices[0]
        if idx < 0 or idx >= len(data):
            return None
        raw = data[idx]
        val = raw * spn_spec.get("per_bit", 1.0) + spn_spec.get("offset", 0.0)
    elif len(byte_indices) == 2:
        idx0, idx1 = byte_indices[0], byte_indices[1]
        if idx0 < 0 or idx1 < 0 or idx0 >= len(data) or idx1 >= len(data):
            return None
        # little endian assumed
        raw = data[idx0] | (data[idx1] << 8)
        val = raw * spn_spec.get("per_bit", 1.0) + spn_spec.get("offset", 0.0)
    else:
        return None
    return val


def spn_display_value(spn_spec: Dict[str, Any], val: Optional[float]) -> str:
    if val is None:
        return "n/a"
    unit = spn_spec.get("unit", "")
    fmt = "{:.2f}" if abs(val - round(val)) > 0.005 else "{:.0f}"
    return f"{fmt.format(val)} {unit}"


# ---------------------------------------------------------------------------
# CSV / fallback live data parser (numeric heuristic)
# ---------------------------------------------------------------------------

def extract_numeric_spns(eid: int, data: bytes, dictionary: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return list of {name, value_str, unit} for displayable SPNs.

    Skips the PGN entirely if its top-level ``display`` flag is false.
    """
    _, _, _, pgn, _ = parse_eid(eid)
    pgn_str = str(pgn)
    results = []
    if pgn_str in dictionary:
        pgndef = dictionary[pgn_str]
        # Respect PGN-level display flag --- skip the whole message if false
        if not pgndef.get("display", True):
            return results
        spns = pgndef.get("spns", {})
        for spn_id, spn_spec in spns.items():
            if not spn_spec.get("display", True):
                continue
            val = decode_spn(data, spn_spec)
            if val is not None:
                unit = spn_spec.get("unit", "")
                fmt = "{:.2f}" if abs(val - round(val)) > 0.005 else "{:.0f}"
                raw_val = val
                value_str = f"{fmt.format(val)} {unit}"
                label = f"{spn_spec.get('nickname', spn_id)} ({spn_spec.get('description', '')})"
                results.append({
                    "spn_id": spn_id,
                    "nickname": spn_spec.get("nickname", spn_id),
                    "description": spn_spec.get("description", ""),
                    "value": raw_val,
                    "value_str": value_str,
                    "unit": unit,
                })
    return results


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DICT_PATH = os.path.join(os.path.dirname(__file__), "J1939_dictionnary.json")
