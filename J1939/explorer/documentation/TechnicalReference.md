# J1939 Explorer — Technical Reference

This document captures implementation details, design decisions, and gotchas so that future work on the app can resume quickly.

---

## 1. Project Layout

```
J1939/explorer/
├── app/
│   ├── __init__.py                # makes app/ a package
│   ├── j1939_can.py               # CAN I/O, parsing, store, decoding
│   ├── explorer.py                # Textual App + 3 screen widgets
│   └── J1939_dictionnary.json     # PGN/SPN dictionary
├── j1939_venv/                    # Python virtual environment
├── pip-compile/                   # Dependency management
│   ├── 00_base.in
│   ├── 01_j1939.in
│   ├── 02_textual.in
│   ├── j1939_venv.requirements.txt
│   └── setup_venv                 # script to sync venv
├── explorer                       # root launcher script
└── log_j1939.py                   # minimal python-can sample
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
self.messages: Dict[int, Dict]   # eid -> {"ts": float, "data": bytes, "hex": str}
self.timestamps_window: deque    # list of (timestamp, eid), pruned to 15 s
```

**Why a deque?**  Allows fast left-popping of stale timestamps while keeping insertion order for rate computation.

**Why only the latest message per EID?**  The UI shows the current snapshot; history is only needed for rates.

### Stats computation (inside lock)
- `rate["1s"]`  = count of timestamps in the last 1 second
- `rate["5s"]`  = count in last 5 seconds / 5.0
- `rate["15s"]` = total deque length / 15.0

---

## 5. Textual Widget Hierarchy

```
ExplorerApp (Screen)
├── CompactHeader (id="header", single line)
├── StatsScreen (Static, id="stats")
│   └── Vertical
│       └── Compact Static labels (updated via .update())
├── MessagesScreen (Static, id="messages")
│   └── Vertical
│       ├── Static ("Messages")
│       ├── DataTable (columns: EID=9, Age=5)
│       ├── Static ("Detail")
│       └── Static (detail text, full width)
├── LiveScreen (Static, id="live")
│   └── DataTable (columns: PGN=7, SPN=8, Value=10)
└── CompactFooter (id="footer", single line)
```

All three screens are siblings in the DOM. Mode switching is done by toggling `display` (CSS display property) on each screen widget — **not** by pushing/popping Textual `Screen` objects.

**Why custom header/footer instead of Textual's built-in?**  The built-in `Header` widget includes a clock and logo that consume ~25 columns. On a 40-column terminal this leaves almost no room for the title. The custom `CompactHeader` and `CompactFooter` are single `Static` lines with minimal text.

### Why `Static` containers instead of `Screen`?
The app uses a single `Screen` with stacked `Static` widgets. This avoids managing a screen stack and keeps the header/footer persistent without re-mounting.

### CompactHeader with coloured state indicators

The header renders as:

```
J1939 | MESSAGES | C | .
```

| Position | Value | Colour | Meaning |
|---|---|---|---|
| 3rd field | `C` | green | CAN bus connected |
| 3rd field | `D` | red | CAN bus disconnected |
| 4th field | `.` | green | Display running (unfrozen) |
| 4th field | `F` | red | Display frozen |

`Text.assemble()` from `rich.text.Text` is used to apply inline colour styles via `update(text)`. The header refreshes every tick (0.5 s) so the connection indicator stays live even when frozen.

**Why single-letter indicators instead of words?**  At 40 columns, full words (`CONN`, `FROZEN`) would push the title off-screen. Two separated letters are readable at a glance.

---

## 6. Threading Model

**Two threads:**
1. **CANThread** (`j1939_can.py`) — daemon thread with an **outer reconnect loop**.
2. **Textual main loop** — runs the TUI, handles input, and fires `_tick()` every 500 ms via `set_interval(0.5, ...)`.

### CANThread reconnect loop with PGN filtering

```python
while not stopped:
    try:
        with can.Bus(...) as bus:
            store.on_connect()          # mark Connected = YES
            while not stopped:
                msg = bus.recv(timeout=0.1)
                if msg:
                    _, _, _, pgn, _ = parse_eid(msg.arbitration_id)
                    if pgn in display_pgns:
                        store.add(...)
                    # else: silently drop the message
    except Exception:
        store.on_disconnect()           # mark Connected = NO
        if stopped.wait(1.0):           # 1 s backoff, interruptible
            return
```

The PGN whitelist is built once at startup by `build_display_pgn_set(dictionary)`, which walks the JSON dictionary and collects PGNs whose top-level `"display"` flag is `true`. If a PGN is missing from the dictionary or has `display: false`, every CAN frame with that PGN is dropped **at the CAN thread level** before it ever reaches `J1939MessageStore`.

**Benefits:**
- **Startup without interface** → `Disconnected`, retries every second until the interface appears.
- **Runtime link drop** → catches `Exception` from `bus.recv()`, marks `Disconnected`, closes the bus context cleanly, then retries.
- **Link recovery** → next iteration of the outer `while` loop opens the bus again and marks `Connected`.
- **Graceful shutdown** → `stop()` sets the `Event`; both the inner read loop and the retry sleep exit immediately.
- **Filtered PGNs don't pollute stats** — dropped messages are invisible to the store, so counts / rates / device lists only reflect the PGNs the user cares about.

**Synchronisation:**  All shared state lives in `J1939MessageStore`, protected by a single lock. The UI only reads; the CAN thread only writes.

**Lifecycle:**
- App creates thread in `on_mount()`.
- App signals stop via `Event` in `on_unmount()` and joins with 1 s timeout.

**Pitfall:**  `python-can`'s `Bus` context manager calls `shutdown()` on exit, but since the bus is created inside the thread, there is no cross-thread shutdown race.

---

## 7. Mode Switching & Bindings

```python
BINDINGS = [
    ("f1", "switch_mode('stats')",    "Stats"),
    ("f2", "switch_mode('messages')",  "Messages"),
    ("f3", "switch_mode('live')",      "Live"),
    ("space", "toggle_freeze",         "Freeze"),
    ("q",  "quit",                     "Quit"),
]
```

`_set_mode(mode)`:
1. Sets `self.explorer_mode = mode`
2. Loops over the three screen widgets and sets `display = (m == mode)`
3. Calls `self._update_header()` which updates the `CompactHeader` text with title + mode + optional `[F]` freeze tag

**Pitfall:**  Do **not** name the attribute `current_mode`.  Textual's `App` base class already defines `current_mode` as a read-only property (used by the built-in screen stack). Using it caused:

```
AttributeError: property 'current_mode' of 'ExplorerApp' object has no setter
```

The fix was to rename the field to `explorer_mode`.

---

## 8. Freeze Toggle (`space`)

A boolean `self._frozen` on `ExplorerApp` gates the `_tick()` method.  When active:
- `_tick()` returns immediately — no screen widgets are refreshed.
- The **CAN thread keeps running** in the background; messages continue to accumulate in `J1939MessageStore`.
- The header shows `F` in red.
- A toast notification confirms the state change (`severity="warning"` for freeze, `"information"` for resume).

### Implementation sketch

```python
def action_toggle_freeze(self):
    self._frozen = not self._frozen
    self._set_mode(self.explorer_mode)  # refresh subtitle
    if self._frozen:
        self.notify("Display frozen", severity="warning")
    else:
        self.notify("Display resumed", severity="information")

def _tick(self):
    if self._frozen:
        return
    ...  # normal refresh logic
```

### Why gate `_tick()` instead of stop the timer?
Stopping the interval timer would require restarting it on unfreeze, which is more complex.  A simple early-return inside `_tick()` achieves the same effect with less state management.

---

## 9. Messages Screen Detail Panel

The `DataTable` uses `cursor_type="row"`.  When the cursor moves, Textual posts a `DataTable.RowHighlighted` message.  The handler is defined **on the parent `MessagesScreen`** (not on the table itself) and looks like this:

```python
def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
    cursor_row = event.cursor_row
    ...
```

Because `MessagesScreen` is the parent in the DOM, it receives the message bubbled up from the table.  The screen maintains `_eid_list` (parallel to table rows) to map `cursor_row` back to the EID.

**Incremental update strategy:**  On every tick:
1. Compare current EID list with previous (`_eids_changed()`).
2. If changed → `_rebuild_table()`: `clear()` + `add_row()`, but remember the previously selected EID and restore the cursor via `move_cursor()` afterward.
3. If unchanged → `_update_ages()`: only call `update_cell_at()` on the Age column, leaving the cursor and selection untouched.

This prevents the `table.clear()` bug where arrow-key navigation would break because the cursor was being destroyed every 0.5 s.

---

## 10. Live Screen — DataTable Columns

```python
table.add_column("PGN",   width=7)
table.add_column("SPN",   width=8)
table.add_column("Value", width=10)
```

The `Desc` (description) column was dropped for width in the 40-column layout. Total data width = ~27 columns, which fits well inside narrow terminals.

Each row represents **one displayable SPN**, not one CAN message.  A single message can produce multiple rows if several SPNs inside it have `"display`: true`.

The table is fully cleared and rebuilt every tick, similar to the Messages table.

---

## 11. SPN Decoding

`decode_spn()` in `j1939_can.py`:

- Reads `spn_spec["bytes"]` to know which byte indices to extract.
- **1 byte:** direct unsigned value.
- **2 bytes:** little-endian (`byte0 | (byte1 << 8)`).
- Formula: `value = raw * per_bit + offset`
- Returns `None` if indices are out of bounds.

**Formatting rule used in the UI:**
- If `abs(val - round(val)) > 0.005` → show 2 decimals (`{:.2f}`)
- Otherwise → show integer (`{:.0f}`)
- Append `unit` string.

This heuristic keeps temperatures like `85.0°C` from showing as `85.00°C` while preserving fractional scales such as `0.03125`.

---

## 12. Dictionary JSON Schema

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
| `unit` | string | Unit suffix (e.g. `"°C"`, `"rpm"`) |
| `per_bit` | float | Scale factor |
| `offset` | float | Zero offset |

**Important:** There are two levels of filtering:

1. **PGN level** — `display: false` on a PGN entry means **the entire CAN message is dropped** by `CANThread` before it reaches the store. The message does not appear in stats, Messages screen, or Live screen.
2. **SPN level** — `display: false` on an SPN entry means only that individual parameter is hidden, but the parent message is still stored and other SPNs within it are still decoded.

`build_display_pgn_set()` computes the PGN whitelist once at startup. Dictionary entries with `"display": false` (or missing `"display"`) are effectively invisible to the app.

---

## 13. CSS Styling

```css
Screen { layout: vertical; width: 100%; height: 100%; }
CompactHeader { height: 1; text-style: bold; }
CompactFooter { height: 1; color: $text-muted; }
```

The remaining space is shared by the three screen widgets, each set to `height: 1fr`.

**Messages layout change:**  Originally used a horizontal split (60%/40%). Switched to a **vertical stack** (table above, detail below) because at 40 columns, a side-by-side layout leaves only ~20-24 columns for each pane — barely enough for the EID column alone.

`.bold` applies bold text-style to headings (replaces `.section_title` to save characters).

**Observation:** In a 40-column terminal, `DataTable` column widths must be tight:
- **Messages**: EID=9, Age=5 → total ~15 columns (including borders)
- **Live**: PGN=7, SPN=8, Value=10 → total ~27 columns

---

## 14. Testing Without Hardware

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
        self._set_mode("live")
        self._update_timer = self.set_interval(0.5, self._tick)
```

---

## 15. Known Limitations & Future Work

| Topic | Current State | Possible Improvement |
|---|---|---|
| **Table rebuild** | Incremental updates with cursor preservation | ✅ Done |
| **Header state** | Old: plain text with `[F]` tag. New: single-letter coloured indicators (`C`/`D` for connection, `.`/`F` for freeze) | ✅ Done |
| **SPN size** | Only 1-byte and 2-byte SPNs supported | Add 3-byte, 4-byte, bit-field decoding |
| **Endianness** | Assumes little-endian | Support big-endian flag in dictionary |
| **CAN interface** | Hard-coded `socketcan` | Make interface type configurable (e.g. `pcan`, `virtual`) |
| **Error handling** | Auto-reconnects with 1 s backoff; only shows `Connected: YES/NO` | Show error banner / last error message in UI |
| **Link resilience** | Reconnect loop works for startup failure and runtime drops | Notify user with toast on link loss / recovery |
| **Data logging** | None | Add optional log-to-file in `CANThread` |
| **Message send** | Read-only only | Could extend with a send panel later |
| **PGN 65262 only** | ET1 + EEC1 defined in checked-in JSON | Expand dictionary as needed |

---

## 16. Quick Reference — Key Classes

| Class | File | Role |
|---|---|---|
| `parse_eid()` | `j1939_can.py` | Unpack 29-bit arbitration_id → `(pri, edp, dp, pgn, sa)` |
| `J1939MessageStore` | `j1939_can.py` | Thread-safe cache + stats |
| `CANThread` | `j1939_can.py` | Background reader from `python-can` |
| `decode_spn()` | `j1939_can.py` | Extract numeric value from payload bytes |
| `build_display_pgn_set()` | `j1939_can.py` | Compile whitelist of displayable PGNs from dictionary |
| `extract_numeric_spns()` | `j1939_can.py` | Build display rows for a given message |
| `StatsScreen` | `explorer.py` | Static widget for statistics |
| `MessagesScreen` | `explorer.py` | DataTable + detail panel |
| `LiveScreen` | `explorer.py` | DataTable of decoded SPNs |
| `ExplorerApp` | `explorer.py` | Top-level Textual app |

---

## 17. Dependency Versions (at time of writing)

- `textual` 8.2.7
- `python-can` 4.6.1
- Python 3.14 (system-provided)
