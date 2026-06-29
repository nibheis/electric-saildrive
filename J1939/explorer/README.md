# J1939 Explorer

A terminal app for live CAN bus analysis, designed for small terminals (40×40), built with the [Textual](https://textual.textualize.io) Python toolkit.

---

## Files

| Path | Description |
|---|---|
| `app/__init__.py` | Makes `app/` a Python package |
| `app/j1939_can.py` | J1939 parsing, message store, CAN thread, SPN decoding |
| `app/explorer.py` | **Main Textual application** containing `StatsScreen`, `MessagesScreen`, `LiveScreen`, and `ExplorerApp` |
| `app/J1939_dictionnary.json` | Dictionary of PGN/SPN definitions with nicknames and display flags |
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
| **F1** | Switch to **Stats** mode |
| **F2** | Switch to **Messages** mode |
| **F3** | Switch to **Live** mode |
| **Space** | **Freeze** / **Unfreeze** the display |
| **Q**  | Quit |

---

## Modes

### 1. Stats
Presents CAN bus activity statistics:
- Connection status & uptime
- Message rates over the last **1 s**, **5 s**, and **15 s**
- Number of unique devices on the bus (identified from the SA field of the EID)
- Number of unique PGNs observed

### 2. Messages
Shows a live list of received CAN messages sorted by EID:
- One EID per line: **EID** on the left, **Age** on the right
- Selecting a row displays full details on the right panel:
  - EID, PGN, SA
  - Raw data bytes
  - Decoded SPN values (from the dictionary)

### 3. Live
Shows a live view of current decoded data on the CAN bus:
- Columns: **PGN** nickname | **Description** | **SPN** nickname | **Value**
- Only SPNs marked with `"display": true` in the dictionary are shown

---

## Architecture

```
┌─────────────────┐     ┌─────────────────────┐     ┌─────────────┐
│   CAN Thread    │────▶│ J1939MessageStore   │────▶│  Textual    │
│  (socketcan)    │     │ (thread-safe cache) │     │    App      │
└─────────────────┘     └─────────────────────┘     └─────────────┘
                              │                            │
                              ▼                            ▼
                        ┌─────────────┐              ┌─────────────┐
                        │ 15 s window │              │ 500 ms tick │
                        │  (rates)    │              │ (UI refresh)│
                        └─────────────┘              └─────────────┘
```

- **`J1939MessageStore`** — Keeps the latest message per EID and a 15-second rolling timestamp window for rate calculations. All operations are thread-safe.
- **`CANThread`** — Opens a `socketcan` bus using `python-can` and feeds incoming messages into the store.
- **`ExplorerApp`** — Loads `J1939_dictionnary.json` on startup. Refreshes the active screen every **500 ms** from the shared store.
- **Dictionary filtering** — Only SPNs with `"display": true` are rendered in the **Messages** and **Live** screens.

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
- If the CAN interface is not available, the store remains empty and the UI shows zeros.
