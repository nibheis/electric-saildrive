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
├── Header (show_clock=True)
├── StatsScreen (Static, id="stats")
│   └── Vertical
│       └── Static labels (updated via .update())
├── MessagesScreen (Static, id="messages")
│   └── Horizontal
│       ├── Vertical (60% width)
│       │   └── DataTable (columns: EID, Age)
│       └── Vertical (40% width)
│           └── Static (detail text)
├── LiveScreen (Static, id="live")
│   └── DataTable (columns: PGN, Desc, SPN, Value)
└── Footer
```

All three screens are siblings in the DOM. Mode switching is done by toggling `display` (CSS display property) on each screen widget — **not** by pushing/popping Textual `Screen` objects.

### Why `Static` containers instead of `Screen`?
The app uses a single `Screen` with stacked `Static` widgets. This avoids managing a screen stack and keeps the header/footer persistent without re-mounting.

---

## 6. Threading Model

**Two threads:**
1. **CANThread** (`j1939_can.py`) — daemon thread with an **outer reconnect loop**.
2. **Textual main loop** — runs the TUI, handles input, and fires `_tick()` every 500 ms via `set_interval(0.5, ...)`.

### CANThread reconnect loop

```python
while not stopped:
    try:
        with can.Bus(...) as bus:
            store.on_connect()          # mark Connected = YES
            while not stopped:
                msg = bus.recv(timeout=0.1)
                if msg:
                    store.add(...)
    except Exception:
        store.on_disconnect()           # mark Connected = NO
        if stopped.wait(1.0):           # 1 s backoff, interruptible
            return
```

**Benefits:**
- **Startup without interface** → `Disconnected`, retries every second until the interface appears.
- **Runtime link drop** → catches `Exception` from `bus.recv()`, marks `Disconnected`, closes the bus context cleanly, then retries.
- **Link recovery** → next iteration of the outer `while` loop opens the bus again and marks `Connected`.
- **Graceful shutdown** → `stop()` sets the `Event`; both the inner read loop and the retry sleep exit immediately.

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
3. Updates `self.sub_title` so the Header shows the current mode

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
- The header subtitle shows `[FROZEN]` (e.g. `(stats) [FROZEN]`).
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

**Rebuilding strategy:**  On every tick, the table is `clear()`ed and rebuilt.  For a 40×40 terminal this is trivial; if scaling to thousands of EIDs, consider incremental updates.

---

## 10. Live Screen — DataTable Columns

```python
table.add_column("PGN",   width=6)
table.add_column("Desc",  width=12)
table.add_column("SPN",   width=8)
table.add_column("Value", width=12)
```

Each row represents **one displayable SPN**, not one CAN message.  A single message can produce multiple rows if several SPNs inside it have `"display": true`.

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

**Important:** The app only processes SPNs where `display == true`.  Non-display SPNs are still part of the dictionary for documentation but are skipped by `extract_numeric_spns()`.

---

## 13. CSS Styling

```css
Screen { layout: vertical; width: 100%; height: 100%; }
Header { height: 1; }
Footer { height: 1; }
```

The remaining space is shared by the three `Static` screens.  Widths are percentages:
- Messages list: 60%
- Messages detail: 40%

`.section_title` applies bold text-style to headings.

**Observation:** In a 40-column terminal, `DataTable` column widths must be tight.  Current widths (`EID=9`, `Age=6`) fit exactly within the left pane.

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
| **Table rebuild** | Full clear+rebuild every tick | Incremental row updates for large bus loads |
| **SPN size** | Only 1-byte and 2-byte SPNs supported | Add 3-byte, 4-byte, bit-field decoding |
| **Endianness** | Assumes little-endian | Support big-endian flag in dictionary |
| **CAN interface** | Hard-coded `socketcan` | Make interface type configurable (e.g. `pcan`, `virtual`) |
| **Error handling** | Auto-reconnects with 1 s backoff; only shows `Connected: YES/NO` | Show error banner / last error message in UI |
| **Link resilience** | Reconnect loop works for startup failure and runtime drops | Notify user with toast on link loss / recovery |
| **Data logging** | None | Add optional log-to-file in `CANThread` |
| **Message send** | Read-only only | Could extend with a send panel later |
| **PGN 65262 only** | ET1 is the only defined PGN in the checked-in JSON | Expand dictionary as needed |

---

## 16. Quick Reference — Key Classes

| Class | File | Role |
|---|---|---|
| `parse_eid()` | `j1939_can.py` | Unpack 29-bit arbitration_id → `(pri, edp, dp, pgn, sa)` |
| `J1939MessageStore` | `j1939_can.py` | Thread-safe cache + stats |
| `CANThread` | `j1939_can.py` | Background reader from `python-can` |
| `decode_spn()` | `j1939_can.py` | Extract numeric value from payload bytes |
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
