# J1939 Explorer

A terminal app for live CAN bus analysis, designed for small terminals (40×40), built with the [Textual](https://textual.textualize.io) Python toolkit.

---

## Files

| Path | Description |
|---|---|
| `app/__init__.py` | Makes `app/` a Python package |
| `app/j1939_can.py` | J1939 parsing, message store, CAN thread, SPN decoding |
| `app/explorer.py` | **Main Textual application** containing all screen widgets |
| `app/J1939_dictionnary.json` | Dictionary of PGN/SPN definitions with nicknames and display flags |
| `app/logger.py` | Thread-safe CAN dump writer (cansend format) |
| `app/config.py` | JSON configuration persistence with defaults |
| `app/configuration.json` | Auto-created user config (iface, bitrate, replay_delay) |
| `explorer` | Root launcher script |

---

## How to Run

Activate the virtual environment first:

```bash
source j1939_venv/bin/activate
```

Then run the explorer (defaults to `can0`):

```bash
python explorer
```

Or specify another CAN interface:

```bash
python explorer can1
```

---

## Keyboard Shortcuts

| Key | Action |
|---|---|
| **F1** | Switch to **Stats** screen |
| **F2** | Switch to **Messages** screen |
| **F3** | Switch to **Live** screen |
| **F4** | Switch to **Logging** screen |
| **F5** | Switch to **Config** screen |
| **Space** | **Freeze** / **Unfreeze** the display |
| **L** | Toggle CAN message **logging** to file |
| **Q** | Quit |

---

## Screens

### 1. Stats (F1)
Presents CAN bus activity statistics:
- Link state (UP / DOWN / UNKNOWN)
- Uptime since start or last clear
- Total messages received
- Bus load percentage (relative to 250 kbps theoretical max)
- Message rates over the last **1 s**, **5 s**, and **15 s**
- Number of unique EIDs, source addresses (SAs), and PGNs
- **Clear** button (red) — resets the store, clears the Messages table, and restarts uptime

### 2. Messages (F2)
Shows a live list of received CAN messages sorted by EID:
- One EID per line: **EID** on the left, **Age** on the right
- Selecting a row displays full details below the table:
  - EID, priority, PGN, description (from dictionary)
  - Destination address (DA) for PDU1 messages (PF < 240)
  - Source address (SA)
  - Raw data bytes (hex)
  - Decoded SPN values (only displayable SPNs from the dictionary)

### 3. Live (F3)
Shows a live view of current decoded data on the CAN bus:
- Columns: **PGN** nickname | **SPN** nickname | **Value** | **Age**
- Only SPNs marked with `"display": true` in the dictionary are shown
- Age is computed from the timestamp of the underlying CAN message

### 4. Logging (F4)
Lists recorded CAN dump files in the `logs/` directory:
- Filename and size (in kB) for each `.dump` file
- **Replay** button — injects the selected dump back into the message store at the configured replay delay
- **Delete** button — removes the selected dump file
- During replay, the header shows `R` (replay mode)

### 5. Config (F5)
Configure socketcan interface settings:
- **Interface** — socketcan interface name (default `can0`)
- **Bitrate** — CAN bitrate in bps (default `250000`)
- **Replay delay** — delay between replayed messages in ms (default `500`)
- **Save** button — writes settings to `configuration.json` only
- **Revert** button — reloads settings from `configuration.json`
- **Set UP** button — brings the interface up (brings down first if necessary)
- **Set DOWN** button — brings the interface down

---

## Architecture

```
┌─────────────────┐     ┌─────────────────────┐     ┌─────────────┐
│   CAN Thread    │────▶│ J1939MessageStore   │◄────│  Textual    │
│  (socketcan)    │     │ (thread-safe cache) │     │    App      │
└─────────────────┘     └─────────────────────┘     └─────────────┘
       │                        ▲                            │
       │                        │                            │
       ▼                        │                            ▼
┌─────────────┐         ┌──────────────┐           ┌─────────────────┐
│  CANLogger  │         │ ReplayThread │           │ 500 ms UI tick  │
│ (cansend    │         │ (dump replay │           │ (Stats/Messages/│
│  format)    │         │  injection)  │           │  Live/Logs tick)│
└─────────────┘         └──────────────┘           └─────────────────┘
```

- **`J1939MessageStore`** — Keeps the latest message per EID and a 15-second rolling timestamp window for rate calculations. All operations are thread-safe.
- **`CANThread`** — Opens a `socketcan` bus using `python-can` and feeds incoming messages into the store. Automatically reconnects with a 1 s backoff if the link goes down or the interface is unavailable. Logs RAW frames before PGN filtering.
- **`CANLogger`** — Thread-safe dump writer that logs every received CAN frame in `cansend` compatible format (e.g. `18F00400#1027FFFF`). Files are named `YYYYMMDD_HHmmss.dump`.
- **`ReplayThread`** — Reads a dump file line by line and injects messages into `J1939MessageStore` at the configured delay, applying the same PGN **allowlist** as live traffic.
- **`ExplorerApp`** — Loads `J1939_dictionnary.json` on startup. Refreshes the active screen every **500 ms** from the shared store.
- **Dictionary filtering** — Two-level filtering:
  - **PGN level** — `display: false` drops the entire CAN message before it reaches the store.
  - **SPN level** — `display: false` hides only that individual parameter, but the message is still stored.
- **Configuration** — Auto-creates `configuration.json` from defaults if missing.

---

## Dependencies

Managed in the `pip-compile/` directory:
- `textual`
- `python-can`

To update the virtual environment after modifying requirements:

```bash
cd pip-compile && ./setup_venv
```

---

## Notes

- The app is **read-only**; it does not send messages on the bus.
- **Freeze** (Space) pauses display updates so you can inspect data without it scrolling away. Background CAN collection continues normally.
- **Auto-reconnect** — If the CAN link drops, the app shows disconnected state, retries every second, and automatically resumes when the link comes back up.
- **Logging** (L key) starts a new dump file in `logs/`. In the Config screen, the **Replay** button injects these dumps back into the store for offline analysis.
- **Set UP / Set DOWN** execute `ip link set {up,down}` via `sudo` and perform link-state validation (reject UNKNOWN interfaces, bring down before bringing up when already UP).
- If the CAN interface is not available at startup, the store remains empty and the UI shows zeros while retrying in the background.
