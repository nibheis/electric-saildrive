#!/usr/bin/env python3
"""J1939 Explorer — Terminal app for live CAN bus analysis (40×40)."""
import time
from typing import Any, Dict, List, Optional

from rich.text import Text

from textual.app import App, ComposeResult
from textual.containers import Vertical, Horizontal
from textual.widgets import DataTable, Static

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

# ---------------------------------------------------------------------------
# App constants
# ---------------------------------------------------------------------------
MODE_STATS = "stats"
MODE_MESSAGES = "messages"
MODE_LIVE = "live"

# ---------------------------------------------------------------------------
# Compact header (replaces Textual Header widget)
# ---------------------------------------------------------------------------

class CompactHeader(Static):
    """Single line header with colored state letters."""

    def update_header(self, title: str, mode: str, connected: bool, frozen: bool):
        conn_char = "C" if connected else "D"
        conn_style = "green" if connected else "red"
        freeze_char = "." if not frozen else "F"
        freeze_style = "green" if not frozen else "red"
        text = Text.assemble(
            f"{title} | {mode.upper()} | ",
            (conn_char, conn_style),
            " | ",
            (freeze_char, freeze_style),
        )
        self.update(text)

# ---------------------------------------------------------------------------
# Compact footer (replaces Textual Footer widget)
# ---------------------------------------------------------------------------

class CompactFooter(Static):
    """Single line footer with short key bindings."""

    def compose(self) -> ComposeResult:
        yield Static("F1:S F2:M F3:L Spc:Frz Q:Qt")

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
            f"1s : {rate.get('1s', 0.0):.1f}"
        )
        self.query_one("#stats_5s", Static).update(
            f"5s : {rate.get('5s', 0.0):.1f}"
        )
        self.query_one("#stats_15s", Static).update(
            f"15s: {rate.get('15s', 0.0):.1f}"
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
    StatsScreen, MessagesScreen, LiveScreen {
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
    """

    BINDINGS = [
        ("f1", "switch_mode('stats')", ""),
        ("f2", "switch_mode('messages')", ""),
        ("f3", "switch_mode('live')", ""),
        ("space", "toggle_freeze", ""),
        ("q", "quit", ""),
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

    def compose(self) -> ComposeResult:
        yield CompactHeader(id="header")
        yield StatsScreen(id=MODE_STATS)
        yield MessagesScreen(id=MODE_MESSAGES)
        yield LiveScreen(id=MODE_LIVE)
        yield CompactFooter(id="footer")

    def on_mount(self):
        self.dictionary = load_dictionary(DICT_PATH)
        self._display_pgns = build_display_pgn_set(self.dictionary)
        self.title = "J1939"
        self._set_mode(MODE_STATS)
        self._start_can()
        self._update_timer = self.set_interval(0.5, self._tick)

    def on_unmount(self):
        if self.can_thread is not None:
            self.can_thread.stop()
            self.can_thread.join(timeout=1.0)

    def action_switch_mode(self, mode: str):
        self._set_mode(mode)

    def action_toggle_freeze(self):
        self._frozen = not self._frozen
        self._update_header()
        if self._frozen:
            self.notify("Frozen", severity="warning", timeout=1)
        else:
            self.notify("Resumed", severity="information", timeout=1)

    def _set_mode(self, mode: str):
        self.explorer_mode = mode
        for m in (MODE_STATS, MODE_MESSAGES, MODE_LIVE):
            screen = self.query_one(f"#{m}", Static)
            screen.display = (m == mode)
        # Restore focus to the DataTable when returning to Messages screen
        if mode == MODE_MESSAGES:
            messages_screen = self.query_one(f"#{MODE_MESSAGES}", MessagesScreen)
            messages_screen.table.focus()
        self._update_header()

    def _update_header(self):
        header = self.query_one("#header", CompactHeader)
        stats = self.store.stats()
        header.update_header(
            self.title, self.explorer_mode, stats["connected"], self._frozen
        )

    def _start_can(self):
        self.can_thread = CANThread(
            channel=self._channel,
            store=self.store,
            display_pgns=self._display_pgns,
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
        self._update_header()


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
