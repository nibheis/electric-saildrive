#!/usr/bin/env python3
"""J1939 Explorer — Terminal app for live CAN bus analysis (40×40)."""
import os
import subprocess
import threading
import time
from typing import Any, Dict, List, Optional

from rich.text import Text

from textual.app import App, ComposeResult
from textual.containers import Vertical, Horizontal
from textual.events import Key
from textual.widgets import DataTable, Static, Input, Button

from .j1939_can import (
    parse_eid,
    J1939MessageStore,
    CANThread,
    load_dictionary,
    DICT_PATH,
    build_display_pgn_set,
    extract_numeric_spns,
    decode_spn,
    spn_display_value,
)
from .config import load_config, save_config
from .logger import CANLogger, LOGS_DIR

# ---------------------------------------------------------------------------
# App constants
# ---------------------------------------------------------------------------
MODE_STATS = "stats"
MODE_MESSAGES = "messages"
MODE_LIVE = "live"
MODE_CONFIG = "config"
MODE_LOGS = "logs"

# ---------------------------------------------------------------------------
# Compact header (replaces Textual Header widget)
# ---------------------------------------------------------------------------

class CompactHeader(Static):
    """Single line header with colored state letters."""

    def update_header(
        self, title: str, mode: str, connected: bool, frozen: bool, logging_active: bool
    ):
        conn_char = "C" if connected else "D"
        conn_style = "green" if connected else "red"
        freeze_char = "." if not frozen else "F"
        freeze_style = "green" if not frozen else "red"
        log_char = "L" if logging_active else "."
        log_style = "green" if logging_active else "red"
        text = Text.assemble(
            f"{title} | {mode.upper()} | ",
            (conn_char, conn_style),
            " | ",
            (freeze_char, freeze_style),
            " | ",
            (log_char, log_style),
        )
        self.update(text)

# ---------------------------------------------------------------------------
# Compact footer (replaces Textual Footer widget)
# ---------------------------------------------------------------------------

class CompactFooter(Static):
    """Single line footer with short key bindings (keys in green)."""

    def compose(self) -> ComposeResult:
        text = Text.assemble(
            ("F1", "green"), ":S ",
            ("F2", "green"), ":M ",
            ("F3", "green"), ":L ",
            ("F4", "green"), ":Log ",
            ("F5", "green"), ":Cfg ",
            ("Spc", "green"), ":Frz ",
            ("Q", "green"), ":Qt",
        )
        yield Static(text)

# ---------------------------------------------------------------------------
# Stats screen (tight layout for 40 cols)
# ---------------------------------------------------------------------------

class StatsScreen(Static):
    """Screen showing CAN bus activity statistics."""

    def compose(self) -> ComposeResult:
        with Vertical(id="stats_container"):
            yield Static("-- CAN Bus Stats --", classes="bold")
            yield Static("Con: --", id="stats_connected")
            yield Static("Up : --", id="stats_uptime")
            yield Static("Tot: --", id="stats_total")
            yield Static("Load: --", id="stats_bus_load")
            yield Static("")
            yield Static("-- Activity --", classes="bold")
            yield Static("1s : --", id="stats_1s")
            yield Static("5s : --", id="stats_5s")
            yield Static("15s: --", id="stats_15s")
            yield Static("")
            yield Static("-- Unique --", classes="bold")
            yield Static("EID: --", id="stats_count")
            yield Static("SA : --", id="stats_devices")
            yield Static("PGN: --", id="stats_pgns")

    def update_stats(self, stats: Dict[str, Any]):
        self.query_one("#stats_connected", Static).update(
            f"Con: {'YES' if stats.get('connected') else 'NO'}"
        )
        self.query_one("#stats_uptime", Static).update(
            f"Up : {int(stats['uptime'])}s"
        )
        self.query_one("#stats_total", Static).update(
            f"Tot: {stats['total']}"
        )
        self.query_one("#stats_bus_load", Static).update(
            f"Load:{stats['bus_load']:.1f}%"
        )
        rate = stats.get("rate", {})
        self.query_one("#stats_1s", Static).update(
            f"1s : {rate.get('1s', 0.0):.1f} msg/s"
        )
        self.query_one("#stats_5s", Static).update(
            f"5s : {rate.get('5s', 0.0):.1f} msg/s"
        )
        self.query_one("#stats_15s", Static).update(
            f"15s: {rate.get('15s', 0.0):.1f} msg/s"
        )
        self.query_one("#stats_count", Static).update(
            f"EID: {stats['count']}"
        )
        self.query_one("#stats_devices", Static).update(
            f"SA : {stats['devices']}"
        )
        self.query_one("#stats_pgns", Static).update(
            f"PGN: {stats['pgns']}"
        )


# ---------------------------------------------------------------------------
# Messages screen (vertical stack for small width)
# ---------------------------------------------------------------------------

class MessagesScreen(Static):
    """Screen showing live list of CAN messages + detail panel.
    Layout: table on top, detail below (full width, vertical stack).
    Uses incremental updates to avoid breaking keyboard cursor navigation.
    """

    _eid_list: List[int] = []
    _last_data_by_eid: Dict[int, Any] = {}

    def compose(self) -> ComposeResult:
        with Vertical(id="messages_vertical_container"):
            yield Static("Messages", classes="bold")
            table = DataTable(show_header=True, show_cursor=True, cursor_type="row", zebra_stripes=True)
            table.add_column("EID", width=9)
            table.add_column("Age", width=5)
            yield table
            yield Static("Detail", classes="bold")
            yield Static("Select a message", id="messages_detail_content")

    @property
    def table(self) -> DataTable:
        return self.query_one(DataTable)

    @property
    def detail(self) -> Static:
        return self.query_one("#messages_detail_content", Static)

    def _eids_changed(self, current_rows: List[tuple]) -> bool:
        """Return True if the set or order of EIDs differs from last refresh."""
        if len(current_rows) != len(self._eid_list):
            return True
        for i, (eid, _, _, _) in enumerate(current_rows):
            if eid != self._eid_list[i]:
                return True
        return False

    def _rebuild_table(self, current_rows: List[tuple], now: float):
        """Full clear+rebuild. Remember selected EID and restore cursor after."""
        # remember which EID was selected (if any)
        selected_eid = None
        if self._eid_list and self.table.cursor_row is not None:
            idx = self.table.cursor_row
            if 0 <= idx < len(self._eid_list):
                selected_eid = self._eid_list[idx]

        self.table.clear()
        self._eid_list = []
        self._last_data_by_eid = {}

        for eid, ts, hex_str, data_bytes in current_rows:
            age = now - ts
            age_str = f"{age:.0f}s" if age < 60 else f"{int(age//60)}m"
            self.table.add_row(f"{eid:08X}", age_str, key=str(eid))
            self._eid_list.append(eid)
            self._last_data_by_eid[eid] = data_bytes

        # restore cursor position by EID, or stay at last row
        if selected_eid is not None and selected_eid in self._last_data_by_eid:
            for new_idx, eid in enumerate(self._eid_list):
                if eid == selected_eid:
                    c = max(0, min(new_idx, len(self._eid_list) - 1))
                    self.table.move_cursor(row=c, animate=False)
                    self._show_detail_for_row(c)
                    break
        elif self._eid_list:
            last = len(self._eid_list) - 1
            self.table.move_cursor(row=last, animate=False)
            self._show_detail_for_row(last)

    def _update_ages(self, current_rows: List[tuple], now: float):
        """Only update the Age column in-place; preserve cursor & selection."""
        for row_idx, (eid, ts, hex_str, data_bytes) in enumerate(current_rows):
            # keep data fresh for detail panel
            self._last_data_by_eid[eid] = data_bytes
            age = now - ts
            age_str = f"{age:.0f}s" if age < 60 else f"{int(age//60)}m"
            from textual.coordinate import Coordinate
            self.table.update_cell_at(Coordinate(row=row_idx, column=1), age_str)
        # Also refresh the detail panel for the currently selected row
        cursor = self.table.cursor_row
        if cursor is not None and 0 <= cursor < len(self._eid_list):
            self._show_detail_for_row(cursor)

    def refresh_messages(self, store: J1939MessageStore):
        rows = store.get_all()
        now = time.time()

        if self._eids_changed(rows):
            self._rebuild_table(rows, now)
        else:
            self._update_ages(rows, now)

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        cursor_row = event.cursor_row
        if 0 <= cursor_row < len(self._eid_list):
            self._show_detail_for_row(cursor_row)

    def _show_detail_for_row(self, row_index: int):
        eid = self._eid_list[row_index]
        data = self._last_data_by_eid.get(eid, b"")
        priority, _, _, pgn, sa = parse_eid(eid)
        hex_str = " ".join(f"{b:02X}" for b in data) if data else ""
        lines = [
            f"EID : {eid:08X}",
            f"PRIO: {priority}",
            f"PGN : 0x{pgn:05X} ({pgn})",
        ]
        app = self.app
        if isinstance(app, ExplorerApp):
            pgndef = app.dictionary.get(str(pgn), {})
            description = pgndef.get("description", "")
            if description:
                lines.append(f"{description}")
        # DA only meaningful for PDU1 (PF < 240); otherwise skip
        pf = (eid >> 16) & 0xFF
        if pf < 240:
            da = (eid >> 8) & 0xFF
            lines.append(f"DA  : {da:02X}")
        lines.extend([
            f"SA  : {sa:02X}",
            f"Data: {hex_str}",
        ])
        if isinstance(app, ExplorerApp):
            spns = extract_numeric_spns(eid, data, app.dictionary)
            if spns:
                lines.append("")
                for spn in spns:
                    lines.append(f"{spn['nickname']}={spn['value_str']}")
        self.detail.update("\n".join(lines))


# ---------------------------------------------------------------------------
# Live screen
# ---------------------------------------------------------------------------

class LiveScreen(Static):
    """Screen showing live data values."""

    def compose(self) -> ComposeResult:
        yield DataTable(show_header=True, show_cursor=False, zebra_stripes=True, id="live_table")

    def on_mount(self):
        table = self.query_one("#live_table", DataTable)
        table.add_column("PGN", width=7)
        table.add_column("SPN", width=8)
        table.add_column("Value", width=10)
        table.add_column("Age", width=5)

    def refresh_live(self, store: J1939MessageStore, dictionary: Dict[str, Any]):
        table = self.query_one("#live_table", DataTable)
        now = time.time()
        snapshot: List[List[str]] = []
        for pgn_str, pgndef in dictionary.items():
            if not pgndef.get("display", True):
                continue
            pgn = int(pgn_str)
            pgn_nick = pgndef.get("nickname", "")
            data_bytes, ts = store.get_latest_data_and_ts_for_pgn(pgn)
            spns = pgndef.get("spns", {})
            for spn_id, spn_spec in spns.items():
                if not spn_spec.get("display", True):
                    continue
                val = decode_spn(data_bytes if data_bytes else b"", spn_spec) if data_bytes is not None else None
                value_str = spn_display_value(spn_spec, val)
                if ts is not None:
                    age = now - ts
                    age_str = f"{age:.0f}s" if age < 60 else f"{int(age//60)}m"
                else:
                    age_str = "--"
                snapshot.append([
                    pgn_nick if pgn_nick else f"{pgn}",
                    spn_spec.get("nickname", spn_id),
                    value_str,
                    age_str,
                ])
        table.clear()
        for row in snapshot:
            table.add_row(*row)


# ---------------------------------------------------------------------------
# Config screen
# ---------------------------------------------------------------------------

class ConfigScreen(Static):
    """Screen to configure socketcan interface and bitrate.
    Uses a compact vertical layout for 40-column terminals.
    """

    _config: Dict[str, Any] = {}

    def compose(self) -> ComposeResult:
        with Vertical(id="config_container"):
            yield Static("-- Interface Status --", classes="bold")
            yield Static("Status: --", id="config_interface_status")
            yield Static("")
            yield Static("-- Settings --", classes="bold")
            yield Static("Iface: can0", id="config_iface_value")
            yield Static("Bitrt: 250000", id="config_bitrate_value")
            yield Static("Delay: 500ms", id="config_delay_value")
            yield Static("-- Edit --", classes="bold")
            yield Input(
                placeholder="Interface",
                id="config_iface_input",
            )
            yield Input(
                placeholder="Bitrate (bps)",
                id="config_bitrate_input",
            )
            yield Input(
                placeholder="Replay delay (ms)",
                id="config_delay_input",
            )
            yield Static("")
            yield Button("Apply", id="config_apply_btn", variant="primary")
            yield Button("Revert", id="config_revert_btn", variant="default")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "config_apply_btn":
            self.apply_config()
        elif event.button.id == "config_revert_btn":
            self.revert_config()

    def refresh_config(self, config: Dict[str, Any]):
        self._config = config
        self.query_one("#config_iface_input", Input).value = str(
            config.get("socketcan_interface", "can0")
        )
        self.query_one("#config_bitrate_input", Input).value = str(
            config.get("can_bitrate", 250000)
        )
        self.query_one("#config_delay_input", Input).value = str(
            config.get("replay_delay", 500)
        )
        self.query_one("#config_iface_value", Static).update(
            f"Iface: {config.get('socketcan_interface', 'can0')}"
        )
        self.query_one("#config_bitrate_value", Static).update(
            f"Bitrt: {config.get('can_bitrate', 250000)}"
        )
        self.query_one("#config_delay_value", Static).update(
            f"Delay: {config.get('replay_delay', 500)}ms"
        )
        self._update_status()

    def _check_interface(self) -> str:
        iface = self._config.get("socketcan_interface", "can0")
        try:
            result = subprocess.run(
                ["ip", "link", "show", iface],
                capture_output=True, text=True, timeout=2
            )
            if result.returncode == 0:
                return "UP" if "state UP" in result.stdout else "DOWN"
        except Exception:
            pass
        return "UNKNOWN"

    def _update_status(self):
        status = self._check_interface()
        self.query_one("#config_interface_status", Static).update(
            f"Status: {status}"
        )

    def apply_config(self):
        iface = self.query_one("#config_iface_input", Input).value.strip()
        bitrate_str = self.query_one("#config_bitrate_input", Input).value.strip()
        delay_str = self.query_one("#config_delay_input", Input).value.strip()
        try:
            bitrate = int(bitrate_str)
            delay = int(delay_str)
        except ValueError:
            if self.app:
                self.app.notify("Invalid numeric value", severity="error", timeout=2)
            return
        self._config["socketcan_interface"] = iface
        self._config["can_bitrate"] = bitrate
        self._config["replay_delay"] = delay
        try:
            subprocess.run(["sudo", "ip", "link", "set", "down", iface], check=True)
            subprocess.run(
                ["sudo", "ip", "link", "set", iface, "type", "can", "bitrate", str(bitrate)],
                check=True,
            )
            subprocess.run(["sudo", "ip", "link", "set", "up", iface], check=True)
        except subprocess.CalledProcessError as exc:
            if self.app:
                self.app.notify(f"Interface error: {exc}", severity="error", timeout=3)
            return
        save_config(self._config)
        self.query_one("#config_iface_value", Static).update(f"Iface: {iface}")
        self.query_one("#config_bitrate_value", Static).update(f"Bitrt: {bitrate}")
        self.query_one("#config_delay_value", Static).update(f"Delay: {delay}ms")
        if self.app:
            self.app.notify("Settings applied", severity="information", timeout=2)
        self._update_status()

    def revert_config(self):
        new_config = load_config()
        self._config = new_config
        self.query_one("#config_iface_input", Input).value = str(
            new_config.get("socketcan_interface", "can0")
        )
        self.query_one("#config_bitrate_input", Input).value = str(
            new_config.get("can_bitrate", 250000)
        )
        self.query_one("#config_delay_input", Input).value = str(
            new_config.get("replay_delay", 500)
        )
        self.query_one("#config_iface_value", Static).update(
            f"Iface: {new_config.get('socketcan_interface', 'can0')}"
        )
        self.query_one("#config_bitrate_value", Static).update(
            f"Bitrt: {new_config.get('can_bitrate', 250000)}"
        )
        self.query_one("#config_delay_value", Static).update(
            f"Delay: {new_config.get('replay_delay', 500)}ms"
        )
        self._update_status()
        if self.app:
            self.app.notify("Settings reverted", severity="information", timeout=2)


# ---------------------------------------------------------------------------
# Replay thread
# ---------------------------------------------------------------------------

class ReplayThread(threading.Thread):
    """Background thread that reads a dump file and injects messages."""

    def __init__(
        self,
        filepath: str,
        store: J1939MessageStore,
        delay_ms: int = 500,
        on_done: Optional[Any] = None,
    ):
        super().__init__(daemon=True)
        self.filepath = filepath
        self.store = store
        self.delay_ms = delay_ms
        self._stop = threading.Event()
        self._on_done = on_done

    def run(self):
        try:
            with open(self.filepath, "r") as f:
                lines = [line.strip() for line in f if line.strip()]
        except OSError:
            if self._on_done:
                self._on_done()
            return
        delay_s = self.delay_ms / 1000.0
        for line in lines:
            if self._stop.is_set():
                break
            try:
                eid_str, payload_hex = line.split("#", 1)
                eid = int(eid_str, 16)
                data = bytes.fromhex(payload_hex)
                self.store.add(eid, data)
            except (ValueError, IndexError):
                continue
            if self._stop.wait(delay_s):
                break
        if self._on_done:
            self._on_done()

    def stop(self):
        self._stop.set()


# ---------------------------------------------------------------------------
# Logging screen
# ---------------------------------------------------------------------------

class LoggingScreen(Static):
    """Screen showing log files and replay controls."""

    _file_list: List[str] = []
    _file_sizes: List[int] = []

    def compose(self) -> ComposeResult:
        with Vertical(id="logs_container"):
            yield Static("-- Log Files --", classes="bold")
            yield DataTable(
                show_header=False, show_cursor=True, cursor_type="row",
                zebra_stripes=True, id="logs_table"
            )
            yield Static("")
            with Horizontal(id="logs_buttons"):
                yield Button("Replay", id="logs_replay_btn", variant="primary")
                yield Button("Delete", id="logs_delete_btn", variant="error")

    def on_mount(self):
        table = self.query_one("#logs_table", DataTable)
        table.add_column("File", width=22)
        table.add_column("Size", width=8)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        app = self.app
        if not isinstance(app, ExplorerApp):
            return
        if event.button.id == "logs_replay_btn":
            app._replay_selected_log()
        elif event.button.id == "logs_delete_btn":
            app._delete_selected_log()

    @property
    def table(self) -> DataTable:
        return self.query_one("#logs_table", DataTable)

    def _needs_rebuild(self, current_files: List[tuple]) -> bool:
        if len(current_files) != len(self._file_list):
            return True
        for i, (name, size, _) in enumerate(current_files):
            if name != self._file_list[i] or size != self._file_sizes[i]:
                return True
        return False

    def _rebuild_table(self, current_files: List[tuple]):
        # Remember selection
        selected = None
        if self._file_list and self.table.cursor_row is not None:
            idx = self.table.cursor_row
            if 0 <= idx < len(self._file_list):
                selected = self._file_list[idx]

        self.table.clear()
        self._file_list = []
        self._file_sizes = []
        for name, size, _mtime in current_files:
            size_kb = size / 1024
            self.table.add_row(name, f"{size_kb:.1f}kB", key=name)
            self._file_list.append(name)
            self._file_sizes.append(size)

        # Restore cursor by filename
        if selected is not None and selected in self._file_list:
            for i, n in enumerate(self._file_list):
                if n == selected:
                    self.table.move_cursor(row=i, animate=False)
                    break
        elif self._file_list:
            self.table.move_cursor(row=0, animate=False)

    def _update_sizes(self, current_files: List[tuple]):
        """Update Size column in-place without touching cursor."""
        from textual.coordinate import Coordinate
        for i, (name, size, _) in enumerate(current_files):
            if i >= len(self._file_list) or name != self._file_list[i]:
                break
            size_kb = size / 1024
            self.table.update_cell_at(
                Coordinate(row=i, column=1),
                f"{size_kb:.1f}kB"
            )
            self._file_sizes[i] = size

    def refresh_files(self):
        files = CANLogger().list_files()
        if self._needs_rebuild(files):
            self._rebuild_table(files)
        else:
            self._update_sizes(files)

    def selected_file(self) -> Optional[str]:
        cursor = self.table.cursor_row
        if cursor is not None and 0 <= cursor < len(self._file_list):
            return self._file_list[cursor]
        return None


# ---------------------------------------------------------------------------
# Main App
# ---------------------------------------------------------------------------

class ExplorerApp(App):
    """Top-level Textual App for J1939 Explorer (40×40)."""

    CSS = """
    Screen {
        layout: vertical;
        width: 100%;
        height: 100%;
    }
    CompactHeader {
        height: 1;
        text-style: bold;
        background: white;
        color: black;
    }
    CompactFooter {
        height: 1;
        background: white;
        color: black;
    }
    StatsScreen, MessagesScreen, LiveScreen, ConfigScreen, LoggingScreen {
        width: 100%;
        height: 1fr;
    }
    .bold {
        text-style: bold;
    }
    #messages_vertical_container {
        width: 100%;
        height: 100%;
    }
    #stats_container {
        padding: 0 1;
    }
    #config_container {
        padding: 0 1;
    }
    #logs_container {
        padding: 0 1;
    }
    #logs_table {
        width: 100%;
        height: 1fr;
    }
    #logs_buttons {
        height: auto;
    }
    """

    BINDINGS = [
        ("f1", "switch_mode('stats')", ""),
        ("f2", "switch_mode('messages')", ""),
        ("f3", "switch_mode('live')", ""),
        ("f4", "switch_mode('logs')", ""),
        ("f5", "switch_mode('config')", ""),
        ("space", "toggle_freeze", ""),
        ("l", "toggle_logging", ""),
    ]

    def __init__(self, channel: str = "can0", **kwargs):
        super().__init__(**kwargs)
        self._channel = channel
        self.explorer_mode: str = MODE_STATS
        self.dictionary: Dict[str, Any] = {}
        self.store = J1939MessageStore()
        self.can_thread: Optional[CANThread] = None
        self._update_timer = None
        self._frozen: bool = False
        self._display_pgns: set = set()
        self._config: Dict[str, Any] = {}
        self._can_logger = CANLogger()
        self._replay_thread: Optional[ReplayThread] = None
        self._replay_active = False

    def compose(self) -> ComposeResult:
        yield CompactHeader(id="header")
        yield StatsScreen(id=MODE_STATS)
        yield MessagesScreen(id=MODE_MESSAGES)
        yield LiveScreen(id=MODE_LIVE)
        yield ConfigScreen(id=MODE_CONFIG)
        yield LoggingScreen(id=MODE_LOGS)
        yield CompactFooter(id="footer")

    def on_mount(self):
        self.dictionary = load_dictionary(DICT_PATH)
        self._display_pgns = build_display_pgn_set(self.dictionary)
        self._config = load_config()
        self.title = "J1939"
        self._set_mode(MODE_STATS)
        self._start_can()
        self._update_timer = self.set_interval(0.5, self._tick)

    def on_unmount(self):
        if self._can_logger.is_active():
            self._can_logger.stop()
        if self.can_thread is not None:
            self.can_thread.stop()
            self.can_thread.join(timeout=1.0)

    def on_key(self, event: Key) -> None:
        if event.key == "q":
            event.stop()
            self.exit()

    def action_switch_mode(self, mode: str):
        self._set_mode(mode)

    def action_toggle_freeze(self):
        self._frozen = not self._frozen
        self._update_header()
        if self._frozen:
            self.notify("Frozen", severity="warning", timeout=1)
        else:
            self.notify("Resumed", severity="information", timeout=1)

    def action_toggle_logging(self):
        if self._can_logger.is_active():
            self._can_logger.stop()
            self.notify("Logging stopped", severity="information", timeout=1)
        else:
            path = self._can_logger.start()
            self.notify(f"Logging to {os.path.basename(path)}", severity="information", timeout=2)
        self._update_header()

    def _set_mode(self, mode: str):
        self.explorer_mode = mode
        for m in (MODE_STATS, MODE_MESSAGES, MODE_LIVE, MODE_CONFIG, MODE_LOGS):
            screen = self.query_one(f"#{m}", Static)
            screen.display = (m == mode)
        # Restore focus to the DataTable when returning to Messages screen
        if mode == MODE_MESSAGES:
            messages_screen = self.query_one(f"#{MODE_MESSAGES}", MessagesScreen)
            messages_screen.table.focus()
        elif mode == MODE_CONFIG:
            config_screen = self.query_one(f"#{MODE_CONFIG}", ConfigScreen)
            config_screen.refresh_config(self._config)
            iface_input = config_screen.query_one("#config_iface_input", Input)
            iface_input.focus()
        elif mode == MODE_LOGS:
            logs_screen = self.query_one(f"#{MODE_LOGS}", LoggingScreen)
            logs_screen.refresh_files()
            if logs_screen._file_list:
                logs_screen.table.focus()
        self._update_header()

    def _update_header(self):
        header = self.query_one("#header", CompactHeader)
        stats = self.store.stats()
        # During replay, force connection indicator to 'R' (green)
        connected = True if self._replay_active else stats["connected"]
        header.update_header(
            self.title,
            self.explorer_mode,
            connected,
            self._frozen,
            self._can_logger.is_active(),
        )

    def _start_can(self):
        self.can_thread = CANThread(
            channel=self._channel,
            store=self.store,
            display_pgns=self._display_pgns,
            logger=self._can_logger,
        )
        self.can_thread.start()

    def _tick(self):
        if not self._frozen:
            mode = self.explorer_mode
            if mode == MODE_STATS:
                self.query_one(f"#{MODE_STATS}", StatsScreen).update_stats(self.store.stats())
            elif mode == MODE_MESSAGES:
                self.query_one(f"#{MODE_MESSAGES}", MessagesScreen).refresh_messages(self.store)
            elif mode == MODE_LIVE:
                self.query_one(f"#{MODE_LIVE}", LiveScreen).refresh_live(self.store, self.dictionary)
            elif mode == MODE_LOGS:
                self.query_one(f"#{MODE_LOGS}", LoggingScreen).refresh_files()
        self._update_header()

    # --- replay / delete from logging screen ---

    def _replay_selected_log(self):
        logs_screen = self.query_one(f"#{MODE_LOGS}", LoggingScreen)
        filename = logs_screen.selected_file()
        if not filename:
            self.notify("No file selected", severity="warning", timeout=1)
            return
        filepath = CANLogger().file_path(filename)
        # Bring socketcan down before replay
        iface = self._config.get("socketcan_interface", "can0")
        try:
            subprocess.run(["sudo", "ip", "link", "set", "down", iface], check=True)
        except subprocess.CalledProcessError:
            pass
        # Mark replay active (shows 'R' in header)
        self._replay_active = True
        self._update_header()
        self.notify(f"Replaying {filename}...", severity="information", timeout=2)

        def on_replay_done():
            self._replay_active = False
            self._update_header()
            self.notify("Replay done", severity="information", timeout=1)

        delay_ms = self._config.get("replay_delay", 500)
        self._replay_thread = ReplayThread(
            filepath, self.store, delay_ms=delay_ms, on_done=on_replay_done
        )
        self._replay_thread.start()

    def _delete_selected_log(self):
        logs_screen = self.query_one(f"#{MODE_LOGS}", LoggingScreen)
        filename = logs_screen.selected_file()
        if not filename:
            self.notify("No file selected", severity="warning", timeout=1)
            return
        if CANLogger().delete_file(filename):
            logs_screen.refresh_files()
            self.notify(f"Deleted {filename}", severity="information", timeout=1)
        else:
            self.notify("Delete failed", severity="error", timeout=1)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    import sys
    channel = sys.argv[1] if len(sys.argv) > 1 else "can0"
    app = ExplorerApp(channel=channel)
    app.run(inline=False)


if __name__ == "__main__":
    main()
