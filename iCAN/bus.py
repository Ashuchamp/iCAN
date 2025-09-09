from __future__ import annotations
import time
from typing import Dict, Optional
from PySide6.QtCore import QObject, Signal, Slot, QThread, QTimer, Qt
import can
import cantools


class FrameBus(QObject):
    """Thread-safe hub that receives frames from N buses and emits decoded signal updates."""
    sig_raw = Signal(str, int, bytes, float)  # bus_name, can_id, data, ts
    sig_signal = Signal(str, int, str, str, float, float)  # bus_name, can_id, msg_name, sig_name, value, ts

    def __init__(self):
        super().__init__()
        self.dbc: Optional[cantools.database.Database] = None
        self._msg_by_id: Dict[int, cantools.database.Message] = {}

    def load_dbc(self, path: str):
        self.dbc = cantools.database.load_file(path)
        self._msg_by_id = {m.frame_id: m for m in self.dbc.messages}

    @Slot(str, int, bytes, float)
    def on_frame(self, bus_name: str, can_id: int, data: bytes, ts: float):
        self.sig_raw.emit(bus_name, can_id, data, ts)
        if not self.dbc:
            return
        msg = self._msg_by_id.get(can_id)
        if not msg:
            return
        try:
            d = data
            try:
                exp_len = int(getattr(msg, 'length', 8) or 8)
                if len(d) < exp_len:
                    d = d + bytes(exp_len - len(d))
                elif len(d) > exp_len:
                    d = d[:exp_len]
            except Exception:
                pass
            decoded = msg.decode(d, decode_choices=False, scaling=True)
            for sig_name, val in decoded.items():
                self.sig_signal.emit(bus_name, can_id, msg.name, sig_name, float(val), ts)
        except Exception as e:
            print(f"[DBC decode error] bus={bus_name} id=0x{can_id:X} dlc={len(data)} -> {e}")


class BusReader(QThread):
    """Reader thread for a single python-can Bus."""
    sig_frame = Signal(str, int, bytes, float)  # bus_name, can_id, data, ts
    sig_stat = Signal(str, int, bool)  # bus_name, dlc, is_error

    def __init__(self, bus_name: str, bus: can.BusABC):
        super().__init__()
        self.bus_name = bus_name
        self.bus = bus
        self.running = True

    def run(self):
        while self.running:
            try:
                msg = self.bus.recv(timeout=0.01)
                if msg is None:
                    continue
                ts = time.monotonic()
                self.sig_frame.emit(self.bus_name, msg.arbitration_id, bytes(msg.data), ts)
                try:
                    is_err = bool(getattr(msg, 'is_error_frame', False))
                except Exception:
                    is_err = False
                self.sig_stat.emit(self.bus_name, len(msg.data), is_err)
            except Exception:
                time.sleep(0.05)

    def stop(self):
        self.running = False