#!/usr/bin/env python3
"""J1939 Explorer — Terminal app for live CAN bus analysis (40×40)."""
import time
from typing import Any, Dict, List, Optional

from textual.app import App, ComposeResult
from textual.containers import Vertical, Horizontal
from textual.widgets import (
    DataTable,
    Footer,
    Header,
    Static,
)

from .j1939_can import (
    parse_eid,
    J1939MessageStore,
    CANThread,
    load_dictionary,
    DICT_PATH,
    extract_numeric_spns,
)

# ---------------------------------------------------------------------------
# App constants
# ---------------------------------------------------------------------------
MODE_STATS = "stats"
MODE_MESSAGES = "messages"
MODE_LIVE = "live"

# ---------------------------------------------------------------------------
# Stats screen
# ---------------------------------------------------------------------------

class StatsScreen(Static):
    """Screen showing CAN bus activity statistics."""

    def compose(self) -> ComposeResult:
        with Vertical(id="stats_container"):
            yield Static("BUS STATS", id="stats_title", classes="section_title")
            yield Static("Connected:  --", id="stats_connected")
            yield Static("Uptime:     --", id="stats_uptime")
            yield Static("Msgs total: --", id="stats_count")
            yield Static("")
            yield Static("--- Activity ---", id="stats_activity_title", classes="section_title")
            yield Static("1s:  -- msg/s", id="stats_1s")
            yield Static("5s:  -- msg/s", id="stats_5s")
            yield Static("15s: -- msg/s", id="stats_15s")
            yield Static("")
            yield Static("--- Unique values ---", id="stats_unique_title", classes="section_title")
            yield Static("Devices (SA): --", id="stats_devices")
            yield Static("PGNs:         --", id="stats_pgns")

    def update_stats(self, stats: Dict[str, Any]):
        self.query_one("#stats_connected", Static).update(
            "Connected:  YES" if stats.get("connected") else "Connected:  NO"
        )
        self.query_one("#stats_uptime", Static).update(
            f"Uptime:     {int(stats['uptime'])}s"
        )
        self.query_one("#stats_count", Static).update(
            f"Msgs total: {stats['count']}"
        )
        rate = stats.get("rate", {})
        self.query_one("#stats_1s", Static).update(
            f"1s:  {rate.get('1s', 0.0):.1f} msg/s"
        )
        self.query_one("#stats_5s", Static).update(
            f"5s:  {rate.get('5s', 0.0):.1f} msg/s"
        )
        self.query_one("#stats_15s", Static).update(
            f"15s: {rate.get('15s', 0.0):.1f} msg/s"
        )
        self.query_one("#stats_devices", Static).update(
            f"Devices (SA): {stats['devices']}"
        )
        self.query_one("#stats_pgns", Static).update(
            f"PGNs:         {stats['pgns']}"
        )


# ---------------------------------------------------------------------------
# Messages screen
# ---------------------------------------------------------------------------

class MessagesScreen(Static):
    """Screen showing live list of CAN messages + detail panel."""

    _eid_list: List[int] = []
    _last_data_by_eid: Dict[int, Any] = {}

    def compose(self) -> ComposeResult:
        with Horizontal(id="messages_container"):
            with Vertical(id="messages_list_container"):
                yield Static("Messages list", id="messages_list_title", classes="section_title")
                table = DataTable(show_header=True, show_cursor=True, cursor_type="row", zebra_stripes=True)
                table.add_column("EID", width=9)
                table.add_column("Age", width=6)
                yield table
            with Vertical(id="messages_detail_container"):
                yield Static("Message details", id="messages_detail_title", classes="section_title")
                yield Static("Select a message", id="messages_detail_content")

    @property
    def table(self) -> DataTable:
        return self.query_one(DataTable)

    @property
    def detail(self) -> Static:
        return self.query_one("#messages_detail_content", Static)

    def refresh_messages(self, store: J1939MessageStore):
        rows = store.get_all()
        # Build current set of eids
        current_eids = set(eid for eid, _, _, _ in rows)
        # Remove rows that disappeared (should not happen here, but keep clean)
        existing_keys = {rk for rk in self.table.rows}
        old_len = len(self.table.rows)

        # Full rebuild for simplicity in a small grid:
        self.table.clear()
        self._eid_list = []
        self._last_data_by_eid = {}
        now = time.time()
        for eid, ts, hex_str, data_bytes in rows:
            age = now - ts
            age_str = f"{age:.1f}s" if age < 60 else f"{int(age // 60)}m{int(age % 60):02d}s"
            self.table.add_row(f"{eid:08X}", age_str, key=str(eid))
            self._eid_list.append(eid)
            self._last_data_by_eid[eid] = data_bytes

        # If a row exists, show its details automatically
        if self._eid_list:
            self._show_detail_for_row(0)

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        """Show detail when user changes row selection."""
        cursor_row = event.cursor_row
        if 0 <= cursor_row < len(self._eid_list):
            self._show_detail_for_row(cursor_row)

    def _show_detail_for_row(self, row_index: int):
        eid = self._eid_list[row_index]
        data = self._last_data_by_eid.get(eid, b"")
        _, _, _, pgn, sa = parse_eid(eid)
        hex_str = " ".join(f"{b:02X}" for b in data) if data else ""
        lines = [
            f"EID : {eid:08X}",
            f"PGN : {pgn} (0x{pgn:05X})",
            f"SA  : {sa:02X}",
            f"Data: {hex_str}",
        ]
        # SPN decode
        app = self.app
        if isinstance(app, ExplorerApp):
            dictionary = app.dictionary
            spns = extract_numeric_spns(eid, data, dictionary)
            if spns:
                lines.append("")
                lines.append("SPNs:")
                for spn in spns:
                    lines.append(f"  {spn['nickname']} = {spn['value_str']}")
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
        table.add_column("PGN", width=6)
        table.add_column("Desc", width=12)
        table.add_column("SPN", width=8)
        table.add_column("Value", width=12)

    def refresh_live(self, store: J1939MessageStore, dictionary: Dict[str, Any]):
        table = self.query_one("#live_table", DataTable)
        # Build a snapshot of current displayable fields
        snapshot: List[List[str]] = []
        for eid, ts, hex_str, data_bytes in store.get_all():
            _, _, _, pgn, sa = parse_eid(eid)
            spns = extract_numeric_spns(eid, data_bytes, dictionary)
            pgn_str = str(pgn)
            pgndef = dictionary.get(pgn_str, {})
            pgn_nick = pgndef.get("nickname", "")
            pgn_desc = pgndef.get("description", "")[:12]
            for spn in spns:
                snapshot.append([
                    pgn_nick if pgn_nick else f"{pgn}",
                    pgn_desc,
                    spn["nickname"],
                    spn["value_str"],
                ])
        table.clear()
        for row in snapshot:
            table.add_row(*row)


# ---------------------------------------------------------------------------
# Main App
# ---------------------------------------------------------------------------

class ExplorerApp(App):
    """Top-level Textual App for J1939 Explorer."""

    CSS = """
    Screen {
        layout: vertical;
        width: 100%;
        height: 100%;
    }
    Header {
        height: 1;
    }
    Footer {
        height: 1;
    }
    #content {
        width: 100%;
        height: 1fr;
    }
    StatsScreen, MessagesScreen, LiveScreen {
        width: 100%;
        height: 100%;
    }
    .section_title {
        text-style: bold;
    }
    #messages_container {
        width: 100%;
        height: 100%;
    }
    #messages_list_container {
        width: 60%;
        height: 100%;
    }
    #messages_detail_container {
        width: 40%;
        height: 100%;
        padding-left: 1;
    }
    #stats_container {
        padding: 0 1;
    }
    """

    BINDINGS = [
        ("f1", "switch_mode('stats')", "Stats"),
        ("f2", "switch_mode('messages')", "Messages"),
        ("f3", "switch_mode('live')", "Live"),
        ("space", "toggle_freeze", "Freeze"),
        ("q", "quit", "Quit"),
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

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield StatsScreen(id=MODE_STATS)
        yield MessagesScreen(id=MODE_MESSAGES)
        yield LiveScreen(id=MODE_LIVE)
        yield Footer()

    def on_mount(self):
        self.dictionary = load_dictionary(DICT_PATH)
        self.title = "J1939 Explorer"
        self._set_mode(MODE_STATS)
        # Launch CAN bus reader
        self._start_can()
        # Tick every 500ms
        self._update_timer = self.set_interval(0.5, self._tick)

    def on_unmount(self):
        if self.can_thread is not None:
            self.can_thread.stop()
            self.can_thread.join(timeout=1.0)

    def action_switch_mode(self, mode: str):
        self._set_mode(mode)

    def action_toggle_freeze(self):
        self._frozen = not self._frozen
        self._set_mode(self.explorer_mode)
        if self._frozen:
            self.notify("Display frozen", severity="warning")
        else:
            self.notify("Display resumed", severity="information")

    def _set_mode(self, mode: str):
        self.explorer_mode = mode
        for m in (MODE_STATS, MODE_MESSAGES, MODE_LIVE):
            screen = self.query_one(f"#{m}", Static)
            screen.display = (m == mode)
        freeze_tag = " [FROZEN]" if self._frozen else ""
        self.sub_title = f"({mode}){freeze_tag}"

    def _start_can(self):
        self.can_thread = CANThread(channel=self._channel, store=self.store)
        self.can_thread.start()

    def _tick(self):
        if self._frozen:
            return
        mode = self.explorer_mode
        if mode == MODE_STATS:
            self.query_one(f"#{MODE_STATS}", StatsScreen).update_stats(self.store.stats())
        elif mode == MODE_MESSAGES:
            self.query_one(f"#{MODE_MESSAGES}", MessagesScreen).refresh_messages(self.store)
        elif mode == MODE_LIVE:
            self.query_one(f"#{MODE_LIVE}", LiveScreen).refresh_live(self.store, self.dictionary)


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
