# J1939 Explorer — Technical Reference

This document captures implementation details, design decisions, and gotchas so that future work on the app can resume quickly.

---

## 1. Project Layout

```
J1939/explorer/
├── app/
│   ├── __init__.py                # makes app/ a package
│   ├── j1939_can.py               # CAN I/O, parsing, store, decoding
│   ├── explorer.py                # Textual App + 5 screen widgets + ReplayThread
│   ├── logger.py                  # CANLogger — thread-safe dump writer
│   ├── config.py                  # JSON configuration persistence
│   └── J1939_dictionnary.json     # PGN/SPN dictionary
├── logs/                          # CAN dump files (.dump)
│   └── YYYYMMDD_HHmmss.dump
├── j1939_venv/                    # Python virtual environment
├── pip-compile/                   # Dependency management
│   ├── 00_base.in
│   ├── 01_j1939.in
│   ├── 02_textual.in
│   ├── j1939_venv.requirements.txt
│   └── setup_venv                 # script to sync venv
├── explorer                       # root launcher script
├── log_j1939.py                   # minimal python-can sample
└── configuration.json             # auto-created user config (iface, bitrate, delay)
```

**Important:** `app/` is imported as a package. When running tests, set `PYTHONPATH=.` or run via the launcher.

---

## 2. Virtual Environment & Dependencies

- **textual** (in `02_textual.in`)
- **python-can** (in `01_j1939.in`)
- **pip-tools** (in `00_base.in`)

To add a new dependency, create a new `.in` file in `pip-compile/` and run `./setup_venv`.

Do **not** `pip install` directly into `j1939_venv` without updating the `.in` files.

---

## 3. J1939 EID Parsing

The 29-bit extended identifier layout used by `parse_eid()` in `j1939_can.py`:

```
Bits 28-26 : Priority (3 bits)
Bit  25    : Extended Data Page (EDP)
Bit  24    : Data Page (DP)
Bits 23-16 : PDU Format (PF)
Bits 15-8  : PDU Specific (PS)
Bits 7-0   : Source Address (SA)
```

**PGN calculation:**
- If `PF >= 240` (broadcast): `PGN = (EDP << 16) | (DP << 15) | (PF << 8) | PS`
- If `PF < 240` (destination specific): `PGN = (EDP << 16) | (DP << 15) | (PF << 8)`

Source address = last byte (`SA`). Unique device count = cardinality of all observed SAs.

---

## 4. Data Model — `J1939MessageStore`

Thread-safe store using `threading.Lock()`.

```python
self.messages: Dict[int, Dict[str, Any]]   # eid -> {"ts": float, "data": bytes, "hex": str}
self.timestamps_window: deque              # list of (timestamp, eid), pruned to 15 s
self._total_messages: int                  # monotonic counter since start / clear
self._bus_connected: bool                  # set by CANThread on_connect/on_disconnect
self._start: float                         # start time (reset by clear_all)
```

**Why a deque?**  Allows fast left-popping of stale timestamps while keeping insertion order for rate computation.

**Why only the latest message per EID?**  The UI shows the current snapshot; history is only needed for rates.

### Stats computation (inside lock)
- `total`         = monotonic counter of all accepted CAN frames since start
- `count`         = number of unique EIDs currently in the store
- `rate["1s"]`   = count of timestamps in the last 1 second
- `rate["5s"]`   = count in last 5 seconds / 5.0
- `rate["15s"]`  = total deque length / 15.0
- `bus_load`     = 1-second rate as a percentage of theoretical 250 kbps bus capacity
  - Worst-case frame with stuff bits ≈ 160 µs → max ~7812 msg/s
  - `bus_load = (rate_1s / 7812) * 100.0`, capped at 100%
- `devices`       = number of unique SAs observed
- `pgns`          = number of unique PGNs observed

### Additional methods
- `clear_all()` — resets messages, timestamps, counter, and restart time
- `check_link_status(iface)` — runs `ip link show` to return `UP`/`DOWN`/`UNKNOWN`
- `get_latest_data_and_ts_for_pgn(pgn)` — returns `(data_bytes, timestamp)` for the latest EID matching the PGN

---

## 5. Textual Widget Hierarchy

```
ExplorerApp (Screen)
├── CompactHeader (id="header", single line)
├── StatsScreen (Static, id="stats")
│   └── Vertical
│       ├── Static labels (updated via .update())
│       └── Horizontal
│           └── Button "Clear" (id="stats_clear_btn", variant="error")
├── MessagesScreen (Static, id="messages")
│   └── Vertical (id="messages_vertical_container")
│       ├── DataTable (columns: EID=9, Age=5)
│       ├── Static "Message details" (classes="section_header")
│       └── Static (detail text, id="messages_detail_content")
├── LiveScreen (Static, id="live")
│   └── DataTable (id="live_table", columns: PGN=7, SPN=8, Value=10, Age=5)
├── ConfigScreen (Static, id="config")
│   └── Vertical (id="config_container")
│       ├── Static "Interface" / "Status: --"
│       ├── Static "Settings" / current values
│       ├── Static "Edit"
│       ├── Input (iface)
│       ├── Input (bitrate)
│       ├── Input (delay)
│       ├── Horizontal (row1): Button Save / Button Revert
│       └── Horizontal (row2): Button Set UP / Button Set DOWN
├── LoggingScreen (Static, id="logs")
│   └── Vertical (id="logs_container")
│       ├── DataTable (columns: File=22, Size=8)
│       └── Horizontal: Button Replay / Button Delete
└── CompactFooter (id="footer", single line)
```

All five screens are siblings in the DOM. Mode switching is done by toggling `display` (CSS display property) on each screen widget — **not** by pushing/popping Textual `Screen` objects.

**Why custom header/footer instead of Textual's built-in?**  The built-in `Header` widget includes a clock and logo that consume ~25 columns. On a 40-column terminal this leaves almost no room for the title. The custom `CompactHeader` and `CompactFooter` are single `Static` lines with minimal text.

### Why `Static` containers instead of `Screen`?
The app uses a single `Screen` with stacked `Static` widgets. This avoids managing a screen stack and keeps the header/footer persistent without re-mounting.

### CompactHeader with coloured state indicators

The header renders as:

```
J1939 | MESSAGES | C | . | L
```

| Position | Value | Colour | Meaning |
|---|---|---|---|
| 3rd field | `C` | green | CAN bus connected |
| 3rd field | `D` | red | CAN bus disconnected |
| 3rd field | `R` | green | Replay active (overrides C/D during replay) |
| 4th field | `.` | green | Display running (unfrozen) |
| 4th field | `F` | red | Display frozen |
| 5th field | `L` | green | Logging active |
| 5th field | `.` | red | Logging idle |

`Text.assemble()` from `rich.text.Text` is used to apply inline colour styles via `update(text)`. The header refreshes every tick (0.5 s) so the connection indicator stays live even when frozen.

**Why single-letter indicators instead of words?**  At 40 columns, full words (`CONN`, `FROZEN`, `LOG`) would push the title off-screen. Single letters are readable at a glance.

### CompactFooter

```
F1:S F2:M F3:L F4:Log F5:Cfg Spc:Frz Q:Qt
```

Keys rendered in green via `Text.assemble()`. Background is white with black text via CSS.

---

## 6. Threading Model

**Three threads:**
1. **CANThread** (`j1939_can.py`) — daemon thread with an **outer reconnect loop**.
2. **ReplayThread** (`explorer.py`) — daemon thread that reads a dump file and injects messages into the store.
3. **Textual main loop** — runs the TUI, handles input, and fires `_tick()` every 500 ms via `set_interval(0.5, ...)`.

### CANThread reconnect loop with PGN filtering

```python
while not stopped:
    try:
        with can.Bus(...) as bus:
            store.on_connect()          # mark Connected = YES
            while not stopped:
                msg = bus.recv(timeout=0.1)
                if msg:
                    # Log RAW before filtering
                    if logger:
                        logger.log(msg.arbitration_id, msg.data)
                    _, _, _, pgn, _ = parse_eid(msg.arbitration_id)
                    if display_pgns and pgn not in display_pgns:
                        continue
                    store.add(...)
    except Exception:
        store.on_disconnect()           # mark Connected = NO
        if stopped.wait(1.0):           # 1 s backoff, interruptible
            return
```

The PGN **allowlist** is built once at startup by `build_display_pgn_set(dictionary)`, which walks the JSON dictionary and collects PGNs whose top-level `"display"` flag is `true`. If a PGN is missing from the dictionary or has `display: false`, every CAN frame with that PGN is dropped **at the CAN thread level** before it ever reaches `J1939MessageStore`.

**Benefits:**
- **Startup without interface** → `Disconnected`, retries every second until the interface appears.
- **Runtime link drop** → catches `Exception` from `bus.recv()`, marks `Disconnected`, closes the bus context cleanly, then retries.
- **Link recovery** → next iteration of the outer `while` loop opens the bus again and marks `Connected`.
- **Graceful shutdown** → `stop()` sets the `Event`; both the inner read loop and the retry sleep exit immediately.
- **Filtered PGNs don't pollute stats** — dropped messages are invisible to the store, so counts / rates / device lists only reflect the PGNs the user cares about.
- **RAW logging before filter** — logger gets all frames regardless of `display_pgns`, so dumps contain complete traffic.

**Synchronisation:**  All shared state lives in `J1939MessageStore`, protected by a single lock. The UI only reads; the CAN thread only writes.

**Lifecycle:**
- App creates thread in `on_mount()`.
- App signals stop via `Event` in `on_unmount()` and joins with 1 s timeout.

**Pitfall:**  `python-can`'s `Bus` context manager calls `shutdown()` on exit, but since the bus is created inside the thread, there is no cross-thread shutdown race.

### ReplayThread

```python
for line in lines:
    if stopped:
        break
    eid, data = parse_cansend_line(line)
    # Apply same PGN filtering as live CAN thread
    if display_pgns and pgn not in display_pgns:
        continue
    store.add(eid, data)
    sleep(delay_s)
on_done()          # callback to mark replay finished in UI
```

The `on_done` callback sets `self._replay_active = False` in the main app, switches the header back from `R` to `C`/`D`, and posts a "Replay done" notification.

---

## 7. CANLogger — Dump Writer

`CANLogger` (in `logger.py`) is a thread-safe logger that writes every received CAN frame in `cansend` compatible format:

```
18F00400#1027FFFF
```

Format: `{EID:08X}#{payload_hex}\n`

**Key design choices:**
- **Thread-safe** via `threading.Lock()` around all methods.
- **Lazy file creation** — `start()` creates `logs/YYYYMMDD_HHmmss.dump`.
- **All frames logged** — `CANThread` calls `logger.log()` **before** PGN filtering, so dumps contain complete traffic.
- **File management** — `list_files()`, `delete_file(filename)`, and `file_path(filename)` for the Logging screen.
- **Lifecycle** — `start()` returns path; `stop()` closes file. App calls `stop()` in `on_unmount()` if active.

---

## 8. Mode Switching & Bindings

```python
BINDINGS = [
    ("f1", "switch_mode('stats')",    ""),
    ("f2", "switch_mode('messages')",  ""),
    ("f3", "switch_mode('live')",      ""),
    ("f4", "switch_mode('logs')",      ""),
    ("f5", "switch_mode('config')",    ""),
    ("space", "toggle_freeze",         ""),
    ("l", "toggle_logging",            ""),
]
```

Note: Bindings have empty labels because the footer is a custom `CompactFooter` widget, not the built-in Textual footer.

`_set_mode(mode)`:
1. Sets `self.explorer_mode = mode`
2. Loops over the five screen widgets and sets `display = (m == mode)`
3. Special focus handling:
   - **Messages** → focuses the DataTable
   - **Config** → calls `refresh_config()` and focuses the interface Input
   - **Logs** → calls `refresh_files()` and focuses the DataTable if files exist
4. Calls `self._update_header()`

**Pitfall:**  Do **not** name the attribute `current_mode`.  Textual's `App` base class already defines `current_mode` as a read-only property (used by the built-in screen stack). Using it caused:

```
AttributeError: property 'current_mode' of 'ExplorerApp' object has no setter
```

The fix was to rename the field to `explorer_mode`.

---

## 9. App-Level Key Handler for Quit

Textual 8.2.7 `Binding("q", "quit", "", priority=True)` does **not** bypass `Input` widgets when focused (character keys are consumed by the focused widget before the action fires).

**Fix:** Override `on_key(event)` at the app level:

```python
def on_key(self, event: Key) -> None:
    if event.key == "q":
        event.stop()
        self.exit()
```

This intercepts `q` globally, including when focused in Config screen Inputs.

---

## 10. Freeze Toggle (`space`)

A boolean `self._frozen` on `ExplorerApp` gates the `_tick()` method.  When active:
- `_tick()` skips screen refresh logic but still calls `_update_header()`.
- The **CAN thread keeps running** in the background; messages continue to accumulate in `J1939MessageStore`.
- A notification toast confirms the state change (`severity="warning"` for freeze, `"information"` for resume).

### Implementation sketch

```python
def action_toggle_freeze(self):
    self._frozen = not self._frozen
    self._update_header()
    ...

def _tick(self):
    if not self._frozen:
        # refresh active screen
    self._update_header()
```

### Why gate `_tick()` instead of stop the timer?
Stopping the interval timer would require restarting it on unfreeze, which is more complex.  A simple early-return inside `_tick()` achieves the same effect with less state management while keeping the header live.

---

## 11. Messages Screen Detail Panel

The `DataTable` uses `cursor_type="row"`.  When the cursor moves, Textual posts a `DataTable.RowHighlighted` message.  The handler is defined **on the parent `MessagesScreen`** (not on the table itself) and looks like this:

```python
def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
    cursor_row = event.cursor_row
    ...
```

Because `MessagesScreen` is the parent in the DOM, it receives the message bubbled up from the table.  The screen maintains `_eid_list` (parallel to table rows) to map `cursor_row` back to the EID and `_last_data_by_eid` to cache payload bytes for the detail panel without re-parsing the store.

**Incremental update strategy:**  On every tick:
1. Compare current EID list with previous (`_eids_changed()`).
2. If changed → `_rebuild_table()`: `clear()` + `add_row()`, but remember the previously selected EID and restore the cursor via `move_cursor()` afterward.
3. If unchanged → `_update_ages()`: only call `update_cell_at()` on the Age column, leaving the cursor and selection untouched.

This prevents the `table.clear()` bug where arrow-key navigation would break because the cursor was being destroyed every 0.5 s.

---

## 12. Live Screen — DataTable Columns

```python
table.add_column("PGN",   width=7)
table.add_column("SPN",   width=8)
table.add_column("Value", width=10)
table.add_column("Age",   width=5)
```

The `Desc` (description) column was dropped for width in the 40-column layout. Total data width = ~32 columns (including borders), which fits inside a narrow terminal.

Each row represents **one displayable SPN**, not one CAN message.  A single message can produce multiple rows if several SPNs inside it have `"display": true`.

**Age column** shows how long ago the underlying CAN message was received:
- Computed as `now - message_ts` from `J1939MessageStore`
- Format: `<N>s` if < 60 s, else `<N>m`
- If the PGN has never been seen → `"--"`
- The store's `get_latest_data_and_ts_for_pgn()` returns both payload and timestamp in one lookup.

The table is fully cleared and rebuilt every tick, similar to the Messages table.

---

## 13. Logging Screen — File List with Incremental Sizes

Same incremental update strategy as MessagesScreen:

- `_needs_rebuild()` — compares `len()` and individual `(name, size)` tuples against cached `_file_list` / `_file_sizes`.
- `_rebuild_table()` — full clear + add, with cursor restoration by filename.
- `_update_sizes()` — calls `update_cell_at()` on the Size column only when filenames match and only sizes differ.

This prevents cursor loss when a log file is actively growing (e.g. during logging).

---

## 14. Config Screen

### Layout (vertical stack for 40 columns)

```
 Interface
Status: UP

 Settings
Iface: can0
Bitrt: 250000
Delay: 500ms

 Edit
[Interface         ]
[Bitrate (bps)     ]
[Replay delay (ms) ]

[Save   ] [Revert  ]
[Set UP ] [Set DOWN]
```

### Save button behavior
Save **only writes JSON** (`configuration.json`). It does **not** touch the network interface. This separates configuration persistence from network operations.

### Set UP behavior (with link-state validation)
1. Check link status via `ip link show`.
2. If `UNKNOWN` → reject (interface does not exist).
3. If `UP` → bring it `DOWN` first.
4. Apply bitrate: `ip link set {iface} type can bitrate {bitrate}`.
5. Bring `UP`: `ip link set up {iface}`.
6. All operations require `sudo`.

### Set DOWN behavior (with link-state validation)
1. Check link status.
2. If `UNKNOWN` → reject.
3. If `DOWN` → warn and skip.
4. If `UP` → `sudo ip link set down {iface}`.

### Revert button
Reloads `configuration.json` and restores the input fields.

---

## 15. SPN Decoding

`decode_spn()` in `j1939_can.py`:

- Reads `spn_spec["bytes"]` to know which byte indices to extract.
- **1 byte:** direct unsigned value.
- **2 bytes:** little-endian (`byte0 | (byte1 << 8)`).
- **4 bytes:** little-endian (`byte0 | (byte1 << 8) | (byte2 << 16) | (byte3 << 24)`).
- All lengths validate that each listed index is within the payload bounds.
- Formula: `value = raw * per_bit + offset`
- Returns `None` if indices are out of bounds or the length is unsupported.

**Formatting rule used in the UI (`spn_display_value()`):**
- If `unit == "RAW"` → display the value as `0xNNNN` hex, zero-padded to the byte count
  (e.g. bytes 0-1 containing `0xEA 0xFE` → `0xFEEA`).
- Otherwise, numeric formatting applies:
  - If `abs(val - round(val)) > 0.005` → show 2 decimals (`{:.2f}`)
  - Otherwise → show integer (`{:.0f}`)
  - Append `unit` string.

This heuristic keeps temperatures like `85.0°C` from showing as `85.00°C` while preserving fractional scales such as `0.03125`.

**Why hex reversal for RAW?**  `decode_spn()` already interprets the listed bytes as little-endian, so the numeric value `0xFEEA` naturally represents `[0xEA, 0xFE]`. `_format_raw_hex()` just prints that value back as hex with correct width (`0xFEEA` for 2 bytes, `0x0012C0` for 3 bytes, etc.).

---

## 16. Dictionary JSON Schema

`J1939_dictionnary.json` is loaded once at startup by `load_dictionary()`.

Top-level keys are **PGN strings** (decimal, e.g. `"65262"`).

Each PGN object:

| Field | Type | Purpose |
|---|---|---|
| `nickname` | string | Short display name (e.g. `"ET1"`) |
| `description` | string | Human-readable description |
| `display` | boolean | Whether this PGN group is shown |
| `spns` | object | Map of SPN ID → SPN spec |

Each SPN spec:

| Field | Type | Purpose |
|---|---|---|
| `nickname` | string | Short name (e.g. `"MT"`) |
| `description` | string | Long description |
| `display` | boolean | Whether this SPN appears in UI |
| `bytes` | list[int] | Byte indices in the CAN payload |
| `unit` | string | Unit suffix (e.g. `"°C"`, `"rpm"`). Special value `"RAW"` → display as `0xNNNN` hex instead of a formatted number. |
| `per_bit` | float | Scale factor |
| `offset` | float | Zero offset |

**Important:** There are two levels of filtering:

1. **PGN level** — `display: false` on a PGN entry means **the entire CAN message is dropped** by `CANThread` before it reaches the store. The message does not appear in stats, Messages screen, or Live screen.
2. **SPN level** — `display: false` on an SPN entry means only that individual parameter is hidden, but the parent message is still stored and other SPNs within it are still decoded.

`build_display_pgn_set()` computes the PGN **allowlist** once at startup. Dictionary entries with `"display": false` (or missing `"display"`) are effectively invisible to the app.

---

## 17. CSS Styling

```css
Screen { layout: vertical; width: 100%; height: 100%; }
CompactHeader { height: 1; text-style: bold; background: white; color: black; }
CompactFooter { height: 1; background: white; color: black; }
StatsScreen, MessagesScreen, LiveScreen, ConfigScreen, LoggingScreen {
    width: 100%; height: 1fr;
}
.bold { text-style: bold; }
.section_header { text-style: bold; background: grey; color: white; }
#messages_vertical_container { width: 100%; height: 100%; }
#stats_container { padding: 0 1; }
#config_container { padding: 0 1; }
#logs_container { padding: 0 1; }
#logs_table { width: 100%; height: 1fr; }
```

The remaining space is shared by the five screen widgets, each set to `height: 1fr`.

**Messages layout change:**  Originally used a horizontal split (60%/40%). Switched to a **vertical stack** (table above, detail below) because at 40 columns, a side-by-side layout leaves only ~20-24 columns for each pane — barely enough for the EID column alone.

**Observation:** In a 40-column terminal, `DataTable` column widths must be tight:
- **Messages**: EID=9, Age=5 → total ~15 columns (including borders)
- **Live**: PGN=7, SPN=8, Value=10, Age=5 → total ~32 columns

---

## 18. Configuration Persistence

`config.py` provides `load_config()` and `save_config()` for JSON persistence.

```python
DEFAULTS = {
    "socketcan_interface": "can0",
    "can_bitrate": 250000,
    "replay_delay": 500,
}
```

- Auto-creates `configuration.json` from defaults if missing.
- Merges missing keys into existing configs (backwards-compatible).
- Saved by ConfigScreen's **Save** button.
- Reloaded by ConfigScreen's **Revert** button.
- `replay_delay` controls the injection speed in **Logging** screen replay.

---

## 19. Testing Without Hardware

Because the app relies on `socketcan`, running on a machine without a CAN interface will simply show empty stats.  To test UI logic:

1. Create a `J1939MessageStore` instance.
2. Inject messages manually via `store.add(eid, data_bytes)` from a background thread.
3. Subclass `ExplorerApp`, override `on_mount()` to skip `_start_can()` and point `self.store` at the injected store.

Example pattern (see commit history for `verify_live.py`):

```python
class TestApp(ExplorerApp):
    def on_mount(self):
        self.store = my_injected_store
        self.dictionary = my_test_dict
        self._display_pgns = build_display_pgn_set(self.dictionary)
        self._config = load_config()
        self.explorer_mode = "live"
        self.query_one("#stats").display = False
        self.query_one("#messages").display = False
        self.query_one("#live").display = True
        self._update_timer = self.set_interval(0.5, self._tick)
```

---

## 20. Known Limitations & Future Work

| Topic | Current State | Possible Improvement |
|---|---|---|
| **Table rebuild** | Incremental updates with cursor preservation | ✅ Done |
| **Header state** | Coloured indicators: C/D/R for connection, .F for freeze, L/. for log | ✅ Done |
| **SPN size** | 1, 2, and 4-byte little-endian SPNs supported | Add 3-byte and bit-field decoding |
| **Endianness** | Assumes little-endian | Support big-endian flag in dictionary |
| **CAN interface** | Hard-coded `socketcan` | Make interface type configurable (e.g. `pcan`, `virtual`) |
| **Error handling** | Auto-reconnects with 1 s backoff; notifications for errors | Show last error message in Config screen |
| **Link resilience** | Reconnect loop works for startup failure and runtime drops | ✅ Done |
| **Data logging** | CANLogger writes cansend-format `.dump` files | ✅ Done |
| **Replay** | ReplayThread injects dump files at configurable delay | ✅ Done |
| **Message send** | Read-only only | Could extend with a send panel later |
| **PGN dictionary** | ET1 (65262), EEC1 (61444), Hours (65253), Request (59904) defined | Expand dictionary as needed |
| **Config management** | JSON persistence with Save/Revert | ✅ Done |
| **Link manipulation** | Set UP/DOWN with link-state checks | ✅ Done |

---

## 21. Quick Reference — Key Classes

| Class / Function | File | Role |
|---|---|---|
| `parse_eid()` | `j1939_can.py` | Unpack 29-bit arbitration_id → `(pri, edp, dp, pgn, sa)` |
| `J1939MessageStore` | `j1939_can.py` | Thread-safe cache + stats |
| `CANThread` | `j1939_can.py` | Background reader from `python-can` |
| `decode_spn()` | `j1939_can.py` | Extract numeric value from payload bytes |
| `build_display_pgn_set()` | `j1939_can.py` | Compile **allowlist** of displayable PGNs from dictionary |
| `get_latest_data_and_ts_for_pgn()` | `j1939_can.py` | Return latest payload + timestamp for a PGN |
| `extract_numeric_spns()` | `j1939_can.py` | Build display rows for a given message |
| `spn_display_value()` | `j1939_can.py` | Format SPN value with unit/RAW/decimal heuristic |
| `CANLogger` | `logger.py` | Thread-safe dump writer + file management |
| `load_config()` / `save_config()` | `config.py` | JSON configuration persistence |
| `CompactHeader` | `explorer.py` | Custom single-line header with state colours |
| `CompactFooter` | `explorer.py` | Custom single-line footer with key bindings |
| `StatsScreen` | `explorer.py` | Static widget for statistics + Clear button |
| `MessagesScreen` | `explorer.py` | DataTable + incremental detail panel |
| `LiveScreen` | `explorer.py` | DataTable of decoded SPNs |
| `ConfigScreen` | `explorer.py` | Input fields + Save/Revert/Set UP/Set DOWN |
| `LoggingScreen` | `explorer.py` | File list + Replay/Delete buttons |
| `ReplayThread` | `explorer.py` | Background dump replay with PGN filtering |
| `ExplorerApp` | `explorer.py` | Top-level Textual app |

---

## 22. Dependency Versions (at time of writing)

- `textual` 8.2.7
- `python-can` 4.6.1
- Python 3.14 (system-provided)
