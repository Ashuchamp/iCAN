# iCAN – Receive‑Only CAN Dashboard

Simple desktop dashboard for viewing CAN signals with DBC decoding. Uses python‑can for bus IO, cantools for DBC, PySide6 for UI, and pyqtgraph for plotting.

Note: Transmit functionality has been removed. This app reads from CAN buses and visualizes decoded signals only.

## Quick Start

- Prereqs: Python 3.9+ with `pip`.
- Create a virtualenv and install deps:
  - `python3 -m venv .venv && source .venv/bin/activate`
  - `pip install PySide6 pyqtgraph python-can cantools pyyaml`
- Optional: Install vendor drivers if you plan to use real PCAN hardware (see Vendor Setup below).
- Launch the app from the repo root:
  - `python launcher.py`

## Configure Buses and DBC

- Open File → “Load DBC…” to load your DBC file. Decoding uses cantools; standard (11‑bit) IDs are expected.
- Open Buses → “Configure…” to define up to 3 buses:
  - Interface: `pcan` or `virtual` (python‑can backends).
  - Channel: e.g. `PCAN_USBBUS1` for PCAN, or `vcan0` for the virtual backend (name is arbitrary for virtual).
  - Bitrate: 125k, 250k, 500k, 800k, or 1M.
- Start buses via Buses → “Start Enabled Buses”.

You can also preconfigure via YAML. Create `config.yaml` in the repo root (or set `PCAN_DESKTOP_CONFIG` to a path). Example: `pcan_desktop.yaml.example`.

Keys:
- `buses`: list of `{name, enabled, interface, channel, bitrate}`
- `ui`: `{autostart: true|false, status_interval_ms: number}`
- `db`: `{path: ./your.dbc}`

## Add Panels (Receive Only)

- Receive → Add Value/Gauge/Plot/MultiPlot/LED/Table Panel…
- Pick a bus (or “(any)”), DBC message and signal (for value/gauge/plot/LED). Table does not require a specific signal.
- Dock/resize panels freely. The status bar shows per‑bus FPS and approximate payload load.

Panel types:
- Value: numeric readout for one signal.
- Gauge: numeric + bar visualization.
- Plot: time series for one signal (auto‑range Y, window size configurable).
- MultiPlot: multiple series in one plot (choose several message/signal pairs, optional colors).
- LED: color indicator based on simple rules (`==, >, <, range`).
- Table: live table of frames with cycle time, DLC, and decoded child rows.

## Save and Load Layouts

- File → “Save Layout…” writes a JSON layout (panels + dock state).
- File → “Load Layout…” restores panels and window layout.

## Vendor Setup (Optional)

- PCAN (Peak):
  - Install PCAN drivers and ensure python‑can can open `interface="pcan"` with channels like `PCAN_USBBUS1`.
  - On first start, the app auto‑probes `PCAN_USBBUS1..PCAN_USBBUS8` for BUS1 if configured.
  - Download link for PCAN driver to work with macOS: https://www.mac-can.com/
- Virtual backend:
  - Use `interface="virtual"` in config. This uses python‑can’s in‑process virtual bus.
  - To feed data, run an external sender using python‑can in another process. Example:

```
python - << 'PY'
import time, random, can
bus = can.Bus(interface='virtual', channel='vcan0', bitrate=500000)
while True:
    data = bytes(random.getrandbits(8) for _ in range(8))
    bus.send(can.Message(arbitration_id=0x123, is_extended_id=False, data=data))
    time.sleep(0.1)
PY
```

## Troubleshooting

- No buses running: Configure and start buses; verify drivers for PCAN; for virtual, ensure a separate sender is pushing frames.
- DBC decode errors in console: Check message lengths and that your DBC matches the actual frames. Decoder clamps/pads to expected DLC.
- Extended IDs / CAN FD: Not supported (classic CAN, standard ID, DLC ≤ 8 only).
- Missing YAML parsing: Install `pyyaml` or remove YAML config and configure in the UI.

## Project Layout

- `pcan_desktop/main_window.py`: main UI, menus, bus lifecycle, status bar.
- `pcan_desktop/bus.py`: frame hub and CAN reader threads, DBC decoding.
- `pcan_desktop/panels.py`: dockable panels (Value, Gauge, Plot, MultiPlot, LED, Table).
- `pcan_desktop/dialogs.py`: Add/Edit panel dialogs and bus config dialog.
- `pcan_desktop/models.py`: simple dataclasses for configuration and layout.
- `pcan_desktop/config.py`: optional YAML config loader (`config.yaml`).
- `launcher.py`: entrypoint that starts the Qt app.
- `probe.py`: read the status of buses plugged into laptop
