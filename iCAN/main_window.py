from __future__ import annotations
import time, json, base64, random
from typing import Dict, Optional, List
import os
from PySide6.QtCore import QTimer, QByteArray, Qt
from PySide6.QtWidgets import QMainWindow, QLabel, QFileDialog, QMessageBox, QToolBar, QTabBar, QDockWidget, QDialog
from PySide6.QtGui import QAction
import can
import pyqtgraph as pg

from .models import APP_TITLE, DEFAULT_LAYOUT_FILE, BusConf, LayoutState, PanelConf
from .bus import FrameBus, BusReader
from .panels import (
    BasePanel, ValuePanel, GaugePanel, PlotPanel, MultiPlotPanel, TablePanel,
    LedPanel,
)
from .dialogs import PanelConfigDialog, MultiPlotConfigDialog, BusConfigDialog
from .config import load_config


class Main(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(1280, 800)

        self.hub = FrameBus()
        # Defaults; overridden by YAML config
        self.buses_conf: Dict[str, BusConf] = {
            "BUS1": BusConf(enabled=True, interface="pcan", channel="PCAN_USBBUS1", bitrate=500000, name="BUS1"),
            "BUS2": BusConf(enabled=False, interface="virtual", channel="vcan1", bitrate=500000, name="BUS2"),
            "BUS3": BusConf(enabled=False, interface="virtual", channel="vcan2", bitrate=500000, name="BUS3"),
        }
        self.bus_objs: Dict[str, can.BusABC] = {}
        self.readers: List[BusReader] = []
        self._dash_states: Dict[int, Optional[LayoutState]] = {0: None}

        self.hint = QLabel("Use File → Load DBC, Buses → Configure/Start, and View/Receive → Add Panel.\nDock, save layout, and go!")
        self.hint.setAlignment(Qt.AlignCenter)
        self.setCentralWidget(self.hint)

        # Allow multiple rows/columns of dock widgets (more panels side-by-side)
        try:
            self.setDockNestingEnabled(True)
            from PySide6.QtWidgets import QMainWindow as _QMW
            self.setDockOptions(self.dockOptions() | _QMW.AllowNestedDocks | _QMW.AllowTabbedDocks)
        except Exception:
            pass

        self._make_menus()
        self.hub.sig_raw.connect(lambda *_: None)

        self._dbc_path: Optional[str] = None

        # Load YAML config if present
        self._cfg = load_config()
        if self._cfg:
            # Buses
            buses = self._cfg.get('buses')
            if isinstance(buses, list) and buses:
                bc_map: Dict[str, BusConf] = {}
                for i, b in enumerate(buses):
                    try:
                        name = str(b.get('name') or f"BUS{i+1}")
                        bc_map[name] = BusConf(
                            enabled=bool(b.get('enabled', False)),
                            interface=str(b.get('interface', 'pcan')),
                            channel=str(b.get('channel', 'PCAN_USBBUS1')),
                            bitrate=int(b.get('bitrate', 500000)),
                            name=name,
                        )
                    except Exception:
                        continue
                if bc_map:
                    self.buses_conf = bc_map
            # DBC path auto-load
            db = self._cfg.get('db', {}) if isinstance(self._cfg.get('db'), dict) else {}
            dbc_path = db.get('path')
            if dbc_path and os.path.isfile(dbc_path):
                try:
                    self.hub.load_dbc(dbc_path)
                    self._dbc_path = dbc_path
                except Exception:
                    pass

        # Status bar
        self.status_lbl = QLabel("")
        self.statusBar().addPermanentWidget(self.status_lbl, 1)
        self._bus_stats: Dict[str, Dict[str, float]] = {}

        # Status interval from config if available
        _status_interval_ms = 1000
        try:
            if self._cfg and isinstance(self._cfg.get('ui'), dict):
                _status_interval_ms = int(self._cfg['ui'].get('status_interval_ms', 1000))
        except Exception:
            pass
        self._status_timer = QTimer(self); self._status_timer.setInterval(_status_interval_ms)
        self._status_timer.timeout.connect(self._refresh_status); self._status_timer.start()

        # Controlled autostart
        _auto = True
        try:
            if self._cfg and isinstance(self._cfg.get('ui'), dict):
                _auto = bool(self._cfg['ui'].get('autostart', True))
        except Exception:
            pass
        if _auto:
            QTimer.singleShot(0, self._autostart_buses)

    # Tabs logic
    def _capture_layout_state(self) -> LayoutState:
        state = self.saveState()
        return LayoutState(buses=list(self.buses_conf.values()), panels=self._collect_panels(), dock_state_b64=base64.b64encode(bytes(state)).decode("ascii"))

    def _apply_layout_state(self, layout: Optional[LayoutState]):
        for dw in self.findChildren(QDockWidget): dw.setParent(None)
        if layout is None:
            try:
                if self.hint: self.hint.show()
            except Exception:
                pass
            return
        self.buses_conf = {b.name: b for b in layout.buses}
        for p in layout.panels: self._add_panel_from_conf(p)
        if layout.dock_state_b64:
            try:
                ba = QByteArray(base64.b64decode(layout.dock_state_b64)); self.restoreState(ba)
            except Exception: pass

    def _on_tab_changed(self, idx: int):
        prev = getattr(self, '_current_tab_idx', 0)
        if prev in self._dash_states:
            self._dash_states[prev] = self._capture_layout_state()
        self._apply_layout_state(self._dash_states.get(idx))
        self._current_tab_idx = idx

    def _add_tab(self):
        idx = self.tabbar.addTab(f"Dashboard {self.tabbar.count()+1}")
        self._dash_states[idx] = None
        self.tabbar.setCurrentIndex(idx)

    def _on_tab_close(self, idx: int):
        if self.tabbar.count() == 1: return
        self._dash_states.pop(idx, None); self.tabbar.removeTab(idx)

    def _rename_current_tab(self):
        from PySide6.QtWidgets import QInputDialog
        idx = self.tabbar.currentIndex();
        if idx < 0: return
        text, ok = QInputDialog.getText(self, "Rename Dashboard", "New name:", text=self.tabbar.tabText(idx))
        if ok and text.strip(): self.tabbar.setTabText(idx, text.strip())

    # Menus
    def _make_menus(self):
        m_file = self.menuBar().addMenu("&File")
        act_load_dbc = QAction("Load &DBC…", self); act_load_dbc.triggered.connect(self.load_dbc)
        act_save_layout = QAction("&Save Layout", self); act_save_layout.triggered.connect(self.save_layout)
        act_load_layout = QAction("&Load Layout", self); act_load_layout.triggered.connect(self.load_layout)
        act_quit = QAction("&Quit", self); act_quit.triggered.connect(self.close)
        m_file.addAction(act_load_dbc); m_file.addSeparator(); m_file.addAction(act_save_layout); m_file.addAction(act_load_layout); m_file.addSeparator(); m_file.addAction(act_quit)

        m_bus = self.menuBar().addMenu("&Buses")
        act_cfg = QAction("&Configure…", self); act_cfg.triggered.connect(self.configure_buses)
        act_start = QAction("&Start Enabled Buses", self); act_start.triggered.connect(self.start_buses)
        act_stop = QAction("S&top Buses", self); act_stop.triggered.connect(self.stop_buses)
        m_bus.addAction(act_cfg); m_bus.addAction(act_start); m_bus.addAction(act_stop)

        m_rx = self.menuBar().addMenu("&Receive")
        for t in ["value", "gauge", "plot", "multiplot", "led", "table"]:
            ac = QAction(f"Add {t.title()} Panel…", self); ac.triggered.connect(lambda _, tt=t: self.add_panel(tt)); m_rx.addAction(ac)

        self.tabbar = QTabBar(movable=True, tabsClosable=True)
        self.tabbar.setExpanding(False)
        self.tabbar.addTab("Dashboard 1")
        self._current_tab_idx = 0
        self.tabbar.currentChanged.connect(self._on_tab_changed)
        self.tabbar.tabCloseRequested.connect(self._on_tab_close)
        tb = QToolBar("Dashboards"); tb.addWidget(QLabel(" Dashboards: "))
        tb.addWidget(self.tabbar); self.addToolBar(tb)

        m_dash = self.menuBar().addMenu("&Dashboards")
        act_add_tab = QAction("&Add Tab", self); act_add_tab.triggered.connect(self._add_tab)
        act_rename_tab = QAction("&Rename Current Tab", self); act_rename_tab.triggered.connect(self._rename_current_tab)
        act_del_tab = QAction("&Delete Current Tab", self); act_del_tab.triggered.connect(lambda: self._on_tab_close(self.tabbar.currentIndex()))
        m_dash.addAction(act_add_tab); m_dash.addAction(act_rename_tab); m_dash.addAction(act_del_tab)

    # DBC
    def load_dbc(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open DBC", "", "DBC Files (*.dbc)")
        if not path: return
        try:
            self.hub.load_dbc(path); self._dbc_path = path
            QMessageBox.information(self, "DBC", f"Loaded: {path}")
        except Exception as e:
            QMessageBox.critical(self, "DBC Error", f"Failed to load DBC:\n{e}")

    # Buses
    def configure_buses(self):
        dlg = BusConfigDialog(self, self.buses_conf)
        if dlg.exec() == QDialog.Accepted:
            self.buses_conf = dlg.result_buses()

    def start_buses(self):
        self.stop_buses(); errs = []
        for key, bc in self.buses_conf.items():
            if not bc.enabled: continue
            try:
                if bc.interface == "virtual": bus = can.Bus(interface="virtual", channel=bc.channel, bitrate=bc.bitrate)
                else: bus = can.Bus(interface="pcan", channel=bc.channel, bitrate=bc.bitrate)
                self.bus_objs[bc.name] = bus
                reader = BusReader(bc.name, bus)
                reader.sig_frame.connect(self.hub.on_frame)
                reader.sig_stat.connect(self._on_stat_frame)
                reader.start(); self.readers.append(reader)
            except Exception as e:
                errs.append(f"{bc.name}: {e}")
        if errs:
            print("[Buses] Errors starting buses:\n" + "\n".join(errs)); QMessageBox.warning(self, "Bus Errors", "\n".join(errs))
        else:
            print(f"[Buses] Started: {', '.join(self.bus_objs.keys()) or 'none'}"); QMessageBox.information(self, "Buses", "Started.")

    def stop_buses(self):
        for r in self.readers: r.stop(); r.wait(500)
        self.readers.clear()
        for _, b in list(self.bus_objs.items()):
            try: b.shutdown()
            except Exception: pass
        self.bus_objs.clear()

    def _autostart_buses(self):
        b1 = self.buses_conf.get("BUS1")
        if b1 and b1.enabled and b1.interface == "pcan":
            try:
                test_bus = can.Bus(interface="pcan", channel=b1.channel, bitrate=b1.bitrate); test_bus.shutdown()
            except Exception:
                for i in range(1, 9):
                    ch = f"PCAN_USBBUS{i}"
                    try:
                        test_bus = can.Bus(interface="pcan", channel=ch, bitrate=b1.bitrate); test_bus.shutdown()
                        self.buses_conf["BUS1"] = BusConf(enabled=True, interface="pcan", channel=ch, bitrate=b1.bitrate, name="BUS1")
                        print(f"[Buses] Auto-selected available PCAN channel for BUS1: {ch}"); break
                    except Exception: continue
        self.start_buses()

    # Mock transmit functionality removed

    # Panels
    def add_panel(self, panel_type: str):
        if panel_type == "multiplot": dlg = MultiPlotConfigDialog(self, self.bus_objs, self.hub.dbc)
        else: dlg = PanelConfigDialog(self, self.bus_objs, self.hub.dbc, panel_type)
        if dlg.exec() != QDialog.Accepted: return
        pid = f"{panel_type}_{int(time.time()*1000)%1_000_000}"; conf = dlg.get_panel_conf(pid)
        if not conf: return
        self._add_panel_from_conf(conf)

    def _add_panel_from_conf(self, conf: PanelConf):
        panel = self._create_panel(conf)
        if not panel: return
        try:
            if self.hint and self.hint.isVisible(): self.hint.hide()
        except Exception: pass
        self.addDockWidget(Qt.RightDockWidgetArea, panel)
        # Try to distribute all right-area docks evenly horizontally
        try:
            self._distribute_right_docks()
        except Exception:
            pass

    def _create_panel(self, conf: PanelConf) -> Optional[BasePanel]:
        try:
            if conf.panel_type == "value": return ValuePanel(conf, self.hub)
            if conf.panel_type == "gauge": return GaugePanel(conf, self.hub)
            if conf.panel_type == "plot": return PlotPanel(conf, self.hub)
            if conf.panel_type == "multiplot": return MultiPlotPanel(conf, self.hub)
            if conf.panel_type == "table": return TablePanel(conf, self.hub)
            if conf.panel_type == "led": return LedPanel(conf, self.hub)
        except Exception:
            import traceback; traceback.print_exc(); QMessageBox.critical(self, "Panel Error", "Failed to create panel; see console.")
        return None

    def _edit_panel(self, panel: BasePanel):
        conf = panel.conf
        if conf.panel_type == 'multiplot': dlg = MultiPlotConfigDialog(self, self.bus_objs, self.hub.dbc, existing=conf)
        else: dlg = PanelConfigDialog(self, self.bus_objs, self.hub.dbc, conf.panel_type, existing=conf)
        if dlg.exec() != QDialog.Accepted: return
        new_conf = dlg.get_panel_conf(conf.panel_id)
        if not new_conf: return
        area = self.dockWidgetArea(panel)
        try: panel.setParent(None)
        except Exception: pass
        new_panel = self._create_panel(new_conf)
        if new_panel: self.addDockWidget(area, new_panel)
        try:
            self._distribute_right_docks()
        except Exception:
            pass

    # Layout save/load
    def _collect_panels(self) -> List[PanelConf]:
        out: List[PanelConf] = []
        for dw in self.findChildren(QDockWidget):
            if not isinstance(dw, BasePanel): continue
            out.append(dw.conf)
        return out

    def _distribute_right_docks(self):
        """Resize all right-area docks to share horizontal space evenly."""
        docks = []
        for dw in self.findChildren(QDockWidget):
            if self.dockWidgetArea(dw) == Qt.RightDockWidgetArea:
                docks.append(dw)
        if len(docks) >= 2:
            sizes = [1] * len(docks)
            self.resizeDocks(docks, sizes, Qt.Horizontal)

    def save_layout(self):
        from dataclasses import asdict
        fn, _ = QFileDialog.getSaveFileName(self, "Save Layout", DEFAULT_LAYOUT_FILE, "JSON (*.json)")
        if not fn: return
        state = self.saveState()
        layout = LayoutState(buses=list(self.buses_conf.values()), panels=self._collect_panels(), dock_state_b64=base64.b64encode(bytes(state)).decode("ascii"))
        with open(fn, "w") as f: json.dump(asdict(layout), f, indent=2)
        QMessageBox.information(self, "Layout", f"Saved to {fn}")

    def load_layout(self):
        fn, _ = QFileDialog.getOpenFileName(self, "Load Layout", "", "JSON (*.json)")
        if not fn: return
        try:
            with open(fn, "r") as f: obj = json.load(f)
            self.buses_conf = {b['name']: BusConf(**b) for b in obj['buses']}
            for dw in self.findChildren(QDockWidget): dw.setParent(None)
            for p in obj['panels']:
                conf = PanelConf(**p); self._add_panel_from_conf(conf)
            ba = QByteArray(base64.b64decode(obj.get('dock_state_b64', ""))); self.restoreState(ba)
            QMessageBox.information(self, "Layout", f"Loaded from {fn}")
        except Exception as e:
            QMessageBox.critical(self, "Layout Error", f"Failed to load:\n{e}")

    # Status helpers
    def _on_stat_frame(self, bus_name: str, dlc: int, is_error: bool):
        st = self._bus_stats.setdefault(bus_name, {'frames': 0, 'bytes': 0, 'errors': 0})
        st['frames'] += 1; st['bytes'] += max(0, int(dlc));
        if is_error: st['errors'] += 1

    def _refresh_status(self):
        parts = []
        for bname in sorted(self.bus_objs.keys()):
            st = self._bus_stats.setdefault(bname, {'frames': 0, 'bytes': 0, 'errors': 0})
            frames = st.get('frames', 0); bytes_ = st.get('bytes', 0); errors = st.get('errors', 0)
            st['frames'] = 0; st['bytes'] = 0; st['errors'] = 0
            fps = float(frames); bps_payload = float(bytes_) * 8.0
            bitrate = 500000
            try:
                if bname in self.buses_conf: bitrate = int(self.buses_conf[bname].bitrate)
            except Exception: pass
            load_pct = min(100.0, (bps_payload / max(1.0, bitrate)) * 100.0)
            if load_pct > 50.0 or fps > 150: status = 'HEAVY'
            elif load_pct < 5.0 and fps < 10: status = 'LIGHT'
            else: status = 'MOD'
            parts.append(f"{bname}: {status} | FPS {fps:.0f} | Load~{load_pct:.1f}% | Err/s {float(errors):.0f}")
        self.status_lbl.setText('   |   '.join(parts) if parts else 'No buses running')

    def closeEvent(self, ev):
        try: self.stop_buses()
        except Exception: pass
        ev.accept()
