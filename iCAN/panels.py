from __future__ import annotations
import time
from typing import Dict, Any, List, Optional
from PySide6.QtCore import Qt, Slot, QTimer
from PySide6.QtWidgets import (
    QWidget, QDockWidget, QVBoxLayout, QLabel, QSlider, QHBoxLayout,
    QCheckBox, QPushButton, QMessageBox, QTreeWidget, QTreeWidgetItem, QMenu
)
import pyqtgraph as pg

from .models import PanelConf
from .bus import FrameBus


class BasePanel(QDockWidget):

    def __init__(self, conf: PanelConf, hub: FrameBus):
        super().__init__(conf.title)
        self.conf = conf
        self.hub = hub
        self.setObjectName(conf.panel_id)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._context_menu)

        try:
            self.setMinimumSize(160, 120)
        except Exception:
            pass

    def bus_match(self, bus_name: str) -> bool:
        return (self.conf.bus_name is None) or (bus_name == self.conf.bus_name)

    def msgsig_match(self, msg_name: str, sig_name: str) -> bool:
        if not self.conf.use_dbc:
            return False
        if self.conf.msg_name and self.conf.msg_name != msg_name:
            return False
        if self.conf.sig_name and self.conf.sig_name != sig_name:
            return False
        return True

    def _context_menu(self, pos):
        m = QMenu(self)
        act_edit = m.addAction("Edit Panel…")
        act_remove = m.addAction("Remove Panel")
        act = m.exec(self.mapToGlobal(pos))
        if not act:
            return
        if act == act_edit:
            self._request_edit()
        elif act == act_remove:
            try:
                self.setParent(None)
            except Exception:
                pass

    def _request_edit(self):
        try:
            mw = self.window()
            if hasattr(mw, '_edit_panel'):
                mw._edit_panel(self)
        except Exception:
            pass


class ValuePanel(BasePanel):
    def __init__(self, conf: PanelConf, hub: FrameBus):
        super().__init__(conf, hub)
        w = QWidget(); lay = QVBoxLayout(w)
        self.value_lbl = QLabel("--"); self.value_lbl.setAlignment(Qt.AlignCenter); self.value_lbl.setStyleSheet("font: 700 24px Monospace;")
        self.unit_lbl = QLabel(conf.units); self.unit_lbl.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.value_lbl); lay.addWidget(self.unit_lbl)
        self.setWidget(w)
        hub.sig_signal.connect(self.on_signal)

    @Slot(str, int, str, str, float, float)
    def on_signal(self, bus_name: str, can_id: int, msg_name: str, sig_name: str, value: float, ts: float):
        if not self.bus_match(bus_name): return
        if not self.msgsig_match(msg_name, sig_name): return
        self.value_lbl.setText(f"{value:.3f}")



class GaugePanel(BasePanel):
    def __init__(self, conf: PanelConf, hub: FrameBus):
        super().__init__(conf, hub)
        w = QWidget(); lay = QVBoxLayout(w)
        self.readout = QLabel("--"); self.readout.setAlignment(Qt.AlignCenter)
        self.readout.setStyleSheet("font: 700 24px Monospace;")
        self.slider = QSlider(Qt.Horizontal); self.slider.setEnabled(False)
        self.slider.setMinimum(0); self.slider.setMaximum(1000)
        lay.addWidget(self.readout); lay.addWidget(self.slider)
        self.setWidget(w)
        hub.sig_signal.connect(self.on_signal)

    @Slot(str, int, str, str, float, float)
    def on_signal(self, bus_name: str, can_id: int, msg_name: str, sig_name: str, value: float, ts: float):
        if not self.bus_match(bus_name): return
        if not self.msgsig_match(msg_name, sig_name): return
        self.readout.setText(f"{value:.2f} {self.conf.units}")
        rng = max(1e-9, self.conf.max_val - self.conf.min_val)
        frac = (value - self.conf.min_val) / rng
        self.slider.setValue(int(max(0, min(1, frac)) * 1000))

    # (global DBC decoding handled by FrameBus → hub.sig_signal)


class PlotPanel(BasePanel):
    def __init__(self, conf: PanelConf, hub: FrameBus):
        super().__init__(conf, hub)
        self.plot = pg.PlotWidget()
        self.plot.showGrid(x=True, y=True)
        self.plot.setLabel('left', conf.sig_name or "value")
        self.plot.setLabel('bottom', 'time', units='s')
        pen = {'width': 2}
        if conf.color:
            try:
                pen = pg.mkPen(conf.color, width=2)
            except Exception:
                pen = {'width': 2}
        self.curve = self.plot.plot(pen=pen)
        try:
            self.plot.enableAutoRange(axis='y', enable=True)
            self.plot.setClipToView(True)
            try:
                self.curve.setDownsampling(auto=False)
            except Exception:
                pass
        except Exception:
            pass
        try:
            self.plot.setMinimumSize(120, 100)
        except Exception:
            pass
        self.ts0 = time.monotonic()
        self.x: List[float] = []
        self.y: List[float] = []
        w = QWidget(); lay = QVBoxLayout(w)
        lay.addWidget(self.plot)
        self.setWidget(w)
        hub.sig_signal.connect(self.on_signal)
        self.timer = QTimer(self); self.timer.setInterval(30); self.timer.timeout.connect(self.refresh); self.timer.start()

    def refresh(self):
        win = max(0.5, self.conf.plot_window_s)
        tnow = time.monotonic() - self.ts0
        while self.x and (tnow - self.x[0]) > win:
            self.x.pop(0); self.y.pop(0)
        self.curve.setData(self.x, self.y)
        self.plot.setXRange(max(0, tnow - win), tnow, padding=0)

    @Slot(str, int, str, str, float, float)
    def on_signal(self, bus_name: str, can_id: int, msg_name: str, sig_name: str, value: float, ts: float):
        if not self.bus_match(bus_name): return
        if not self.msgsig_match(msg_name, sig_name): return
        t = ts - self.ts0
        self.x.append(t); self.y.append(value)

    # (global DBC decoding handled by FrameBus -> hub.sig_signal)


class MultiPlotPanel(BasePanel):
    def __init__(self, conf: PanelConf, hub: FrameBus):
        super().__init__(conf, hub)
        self.plot = pg.PlotWidget()
        self.plot.showGrid(x=True, y=True)
        self.plot.setLabel('left', 'value')
        self.plot.setLabel('bottom', 'time', units='s')
        try:
            self.plot.addLegend()
            self.plot.setClipToView(True)
        except Exception:
            pass
        self.ts0 = time.monotonic()
        self.series: Dict[str, Dict[str, Any]] = {}
        for item in (conf.multi_signals or []):
            key = self._key(item)
            color = item.get('color') or None
            pen = pg.mkPen(color, width=2) if color else {'width': 2}
            name = f"{item.get('msg_name','')}:{item.get('sig_name','')}"
            curve = self.plot.plot(pen=pen, name=name)
            try:
                curve.setDownsampling(auto=False)
            except Exception:
                pass
            self.series[key] = {'curve': curve, 'x': [], 'y': [], 'bus': item.get('bus_name'), 'msg': item.get('msg_name'), 'sig': item.get('sig_name')}
        w = QWidget(); lay = QVBoxLayout(w)
        lay.addWidget(self.plot)
        self.setWidget(w)
        hub.sig_signal.connect(self.on_signal)
        self.timer = QTimer(self); self.timer.setInterval(30); self.timer.timeout.connect(self.refresh); self.timer.start()

    def _key(self, it: Dict[str, str]) -> str:
        return f"{it.get('bus_name') or '(any)'}::{it.get('msg_name')}::{it.get('sig_name')}"

    def refresh(self):
        win = max(0.5, self.conf.plot_window_s)
        tnow = time.monotonic() - self.ts0
        for k, d in self.series.items():
            xs, ys = d['x'], d['y']
            while xs and (tnow - xs[0]) > win:
                xs.pop(0); ys.pop(0)
            d['curve'].setData(xs, ys)
        self.plot.setXRange(max(0, tnow - win), tnow, padding=0)

    @Slot(str, int, str, str, float, float)
    def on_signal(self, bus_name: str, can_id: int, msg_name: str, sig_name: str, value: float, ts: float):
        t = ts - self.ts0
        for d in self.series.values():
            if d['bus'] and d['bus'] != bus_name: continue
            if d['msg'] and d['msg'] != msg_name: continue
            if d['sig'] and d['sig'] != sig_name: continue
            d['x'].append(t); d['y'].append(value)


class TablePanel(BasePanel):
    def __init__(self, conf: PanelConf, hub: FrameBus):
        super().__init__(conf, hub)
        self.tree = QTreeWidget()
        self.tree.setColumnCount(5)
        self.tree.setHeaderLabels(["CAN ID", "Message", "Cycle (ms)", "DLC", "Data"])
        self.tree.setUniformRowHeights(True)
        self.tree.setAlternatingRowColors(True)
        self.tree.setSortingEnabled(True)
        self.items_by_id: Dict[int, QTreeWidgetItem] = {}
        self.last_ts: Dict[int, float] = {}
        w = QWidget(); lay = QVBoxLayout(w)
        lay.addWidget(self.tree)
        self.setWidget(w)
        hub.sig_raw.connect(self.on_raw)
        hub.sig_signal.connect(self.on_sig)

    def _bus_ok(self, bus_name: str) -> bool:
        return (self.conf.bus_name is None) or (bus_name == self.conf.bus_name)

    def _fmt_id(self, can_id: int) -> str:
        return f"0x{can_id:03X}"

    @Slot(str, int, bytes, float)
    def on_raw(self, bus_name: str, can_id: int, data: bytes, ts: float):
        if not self._bus_ok(bus_name):
            return
        item = self.items_by_id.get(can_id)
        if item is None:
            item = QTreeWidgetItem(self.tree)
            self.items_by_id[can_id] = item
            item.setExpanded(False)
        prev = self.last_ts.get(can_id)
        cyc_ms = (ts - prev) * 1000.0 if prev else 0.0
        self.last_ts[can_id] = ts
        msg_name = ""
        try:
            if self.hub.dbc:
                m = self.hub.dbc.get_message_by_frame_id(can_id)
                if m:
                    msg_name = m.name
        except Exception:
            pass
        item.setText(0, self._fmt_id(can_id))
        item.setText(1, msg_name)
        item.setText(2, f"{cyc_ms:.1f}")
        item.setText(3, str(len(data)))
        item.setText(4, data.hex(' ').upper())

    @Slot(str, int, str, str, float, float)
    def on_sig(self, bus_name: str, can_id: int, msg_name: str, sig_name: str, value: float, ts: float):
        if not self._bus_ok(bus_name):
            return
        item = self.items_by_id.get(can_id)
        if item is None:
            return
        child = None
        for i in range(item.childCount()):
            it = item.child(i)
            if it.text(1) == sig_name:
                child = it
                break
        if child is None:
            child = QTreeWidgetItem(item)
            child.setText(1, sig_name)
            item.addChild(child)
        child.setText(4, f"{value}")


class LedPanel(BasePanel):
    def __init__(self, conf: PanelConf, hub: FrameBus):
        super().__init__(conf, hub)
        w = QWidget(); lay = QVBoxLayout(w)
        self.lbl = QLabel(conf.title); self.lbl.setAlignment(Qt.AlignCenter)
        self.ind = QLabel("   "); self.ind.setFixedSize(48, 48)
        self.ind.setStyleSheet("border-radius: 24px; background:#666;")
        lay.addWidget(self.lbl); lay.addWidget(self.ind, alignment=Qt.AlignCenter)
        self.setWidget(w)
        self.rules = self._parse_rules(conf.led_rules or [])
        hub.sig_signal.connect(self.on_signal)

    def _parse_rules(self, lines: List[str]):
        rules = []
        for ln in lines:
            try:
                if ln.startswith('=='):
                    v = float(ln[2:].split(':', 1)[0].strip()); c = ln.split(':', 1)[1].strip(); rules.append(('eq', v, c)); continue
                if ln.startswith('>='):
                    v = float(ln[2:].split(':', 1)[0].strip()); c = ln.split(':', 1)[1].strip(); rules.append(('ge', v, c)); continue
                if ln.startswith('<='):
                    v = float(ln[2:].split(':', 1)[0].strip()); c = ln.split(':', 1)[1].strip(); rules.append(('le', v, c)); continue
                if ln.startswith('>'):
                    v = float(ln[1:].split(':', 1)[0].strip()); c = ln.split(':', 1)[1].strip(); rules.append(('gt', v, c)); continue
                if ln.startswith('<'):
                    v = float(ln[1:].split(':', 1)[0].strip()); c = ln.split(':', 1)[1].strip(); rules.append(('lt', v, c)); continue
                if '-' in ln and ':' in ln:
                    rng, c = ln.split(':', 1); a, b = rng.split('-', 1); rules.append(('range', float(a.strip()), float(b.strip()), c.strip())); continue
            except Exception:
                continue
        return rules

    def _color_for(self, value: float) -> Optional[str]:
        for r in self.rules:
            try:
                if r[0] == 'eq' and value == r[1]: return r[2]
                if r[0] == 'ge' and value >= r[1]: return r[2]
                if r[0] == 'le' and value <= r[1]: return r[2]
                if r[0] == 'gt' and value > r[1]: return r[2]
                if r[0] == 'lt' and value < r[1]: return r[2]
                if r[0] == 'range' and r[1] <= value <= r[2]: return r[3]
            except Exception:
                continue
        return None

    @Slot(str, int, str, str, float, float)
    def on_signal(self, bus_name: str, can_id: int, msg_name: str, sig_name: str, value: float, ts: float):
        if not self.bus_match(bus_name): return
        if not self.msgsig_match(msg_name, sig_name): return
        col = self._color_for(value)
        if col:
            self.ind.setStyleSheet(f"border-radius: 24px; background:{col};")
        else:
            self.ind.setStyleSheet("border-radius: 24px; background:#666;")

    # (global DBC decoding handled by FrameBus -> hub.sig_signal)