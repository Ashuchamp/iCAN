from __future__ import annotations
from typing import Dict, Optional, Any, List
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QComboBox, QLineEdit, QDoubleSpinBox, QSpinBox,
    QCheckBox, QLabel, QWidget, QHBoxLayout, QDialogButtonBox, QGroupBox, QColorDialog, QPushButton,
    QPlainTextEdit
)
import cantools

from .models import PanelConf, BusConf
from .bus import FrameBus


PANEL_TYPES = ["plot", "multiplot", "gauge", "value", "led", "table"]


class PanelConfigDialog(QDialog):
    def __init__(self, parent, buses: Dict[str, Any], dbc: Optional[cantools.database.Database], default_type="value", existing: Optional[PanelConf]=None):
        super().__init__(parent)
        self.setWindowTitle("Add Panel")
        self.dbc = dbc
        self.buses = buses
        self.type_cb = QComboBox(); self.type_cb.addItems(PANEL_TYPES); self.type_cb.setCurrentText(default_type)
        self.title_le = QLineEdit(default_type.title())
        self.bus_cb = QComboBox(); self.bus_cb.addItem("(any)")
        for bname in buses.keys(): self.bus_cb.addItem(bname)
        self.use_dbc_chk = QCheckBox("Bind to DBC signal"); self.use_dbc_chk.setChecked(True if dbc else False); self.use_dbc_chk.setEnabled(bool(dbc))
        self.msg_cb = QComboBox(); self.sig_cb = QComboBox()
        self.units_le = QLineEdit("")
        self.color_le = QLineEdit("")
        self.color_btn = QPushButton("Pick…"); self.color_btn.clicked.connect(self._pick_color)
        self.led_rules = QPlainTextEdit(); self.led_rules.setPlaceholderText("Examples:\n==42:#00FF00\n>=80:#FF0000\n10-20:#FFFF00")
        self.min_d = QDoubleSpinBox(); self.min_d.setRange(-1e12, 1e12); self.min_d.setValue(0.0)
        self.max_d = QDoubleSpinBox(); self.max_d.setRange(-1e12, 1e12); self.max_d.setValue(100.0)
        self.plot_win = QDoubleSpinBox(); self.plot_win.setRange(0.5, 300.0); self.plot_win.setValue(10.0)
        form = QFormLayout()

        # Keep references to labels/fields to toggle visibility by type
        self._rows: Dict[str, tuple] = {}
        def add_row(key: str, label_text: str, field_widget: QWidget):
            lab = QLabel(label_text)
            form.addRow(lab, field_widget)
            self._rows[key] = (lab, field_widget)

        add_row("type", "Type:", self.type_cb)
        add_row("title", "Title:", self.title_le)
        add_row("bus", "Bus:", self.bus_cb)

        # DBC bind checkbox as standalone row
        form.addRow(self.use_dbc_chk)
        self._rows["use_dbc"] = (self.use_dbc_chk, self.use_dbc_chk)
        add_row("msg", "Message:", self.msg_cb)
        add_row("sig", "Signal:", self.sig_cb)
        add_row("units", "Units:", self.units_le)
        _rowc = QHBoxLayout(); _wrapc = QWidget(); _wrapc.setLayout(_rowc)
        _rowc.addWidget(self.color_le); _rowc.addWidget(self.color_btn)

        # store wrapper as field
        lab_color = QLabel("Line Color (plot):")
        form.addRow(lab_color, _wrapc)
        self._rows["color"] = (lab_color, _wrapc)
        add_row("min", "Min:", self.min_d)
        add_row("max", "Max:", self.max_d)
        add_row("plotwin", "Plot Window (s):", self.plot_win)
        add_row("led_rules", "LED Rules:", self.led_rules)
        v = QVBoxLayout(self)
        v.addLayout(form)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        v.addWidget(btns)
        btns.accepted.connect(self.accept); btns.rejected.connect(self.reject)
        self.use_dbc_chk.toggled.connect(self._refresh_msg_sig)
        self.type_cb.currentTextChanged.connect(self._type_changed)
        self._populate_dbc()
        self._refresh_msg_sig(True if self.dbc else False)
        self._sync_visibility()
        if existing:
            self._apply_existing(existing)
            self._sync_visibility()

    def _type_changed(self, _):
        self._sync_visibility()

    def _populate_dbc(self):
        self.msg_cb.clear(); self.sig_cb.clear()
        if not self.dbc:
            return
        names = [m.name for m in self.dbc.messages]
        self.msg_cb.addItems(["(choose)"] + names)

    def _refresh_msg_sig(self, on: bool):
        self.msg_cb.setEnabled(on); self.sig_cb.setEnabled(on)
        if on and self.dbc:
            self.sig_cb.clear(); msg_name = self.msg_cb.currentText()
            if msg_name and msg_name != "(choose)":
                msg = self.dbc.get_message_by_name(msg_name)
                self.sig_cb.addItems([s.name for s in msg.signals])
        self.msg_cb.currentTextChanged.connect(lambda _: self._refresh_msg_sig(True))


    def _pick_color(self):
        col = QColorDialog.getColor()
        if col.isValid(): self.color_le.setText(col.name())

    def _set_row_visible(self, key: str, visible: bool):
        pair = self._rows.get(key)
        if not pair:
            return
        lab, field = pair
        lab.setVisible(visible)
        field.setVisible(visible)

    def _sync_visibility(self):
        t = self.type_cb.currentText()
        # Which sections apply
        is_plot = (t == "plot")
        is_led = (t == "led")
        is_rx = t in ("value", "gauge", "plot", "led", "table")
        is_tx = False
        uses_minmax = t in ("slider", "gauge", "value", "plot")
        uses_units = t in ("slider", "gauge", "value", "plot")
        uses_plotwin = t in ("plot",)
        # DBC bind visibility for rx widgets except table; requires a global DBC
        show_dbc = (t in ("value", "gauge", "plot", "led")) and bool(self.dbc)
        # Apply row visibility
        self._set_row_visible("units", uses_units)
        self._set_row_visible("min", uses_minmax)
        self._set_row_visible("max", uses_minmax)
        self._set_row_visible("plotwin", uses_plotwin)
        self._set_row_visible("color", is_plot)
        self._set_row_visible("led_rules", is_led)
        # Bus always relevant
        self._set_row_visible("bus", True)
        # DBC rows
        self.use_dbc_chk.setVisible(show_dbc)
        self._set_row_visible("msg", show_dbc)
        self._set_row_visible("sig", show_dbc)
        # No TX group

    def _apply_existing(self, conf: PanelConf):
        try:
            self.type_cb.setCurrentText(conf.panel_type)
            self.title_le.setText(conf.title)
            self.bus_cb.setCurrentText(conf.bus_name or "(any)")
            self.use_dbc_chk.setChecked(conf.use_dbc)
            if conf.use_dbc and conf.msg_name:
                # Ensure messages list is from the global DBC
                if self.dbc:
                    self.msg_cb.clear(); self.msg_cb.addItems(["(choose)"] + [m.name for m in self.dbc.messages])
                self.msg_cb.setCurrentText(conf.msg_name)
                self._refresh_msg_sig(True)
                if conf.sig_name:
                    self.sig_cb.setCurrentText(conf.sig_name)
            self.units_le.setText(conf.units or "")
            self.min_d.setValue(conf.min_val); self.max_d.setValue(conf.max_val)
            self.plot_win.setValue(conf.plot_window_s)
            if conf.color: self.color_le.setText(conf.color)
            try:
                self.led_rules.setPlainText("\n".join(conf.led_rules or []))
            except Exception:
                pass
        except Exception:
            pass

    def get_panel_conf(self, panel_id: str) -> Optional[PanelConf]:
        t = self.type_cb.currentText()
        # Special case: table panel doesn't bind to one message/signal
        if t == 'table':
            use_dbc = False
            msg_name = None
            sig_name = None
        else:
            use_dbc = self.use_dbc_chk.isChecked() and bool(self.dbc)
            msg_name = self.msg_cb.currentText() if use_dbc and self.msg_cb.currentText() != "(choose)" else None
            sig_name = self.sig_cb.currentText() if use_dbc and self.sig_cb.currentText() else None
        bus_name = self.bus_cb.currentText();
        if bus_name == "(any)": bus_name = None
        conf = PanelConf(
            panel_id=panel_id,
            panel_type=t,
            title=self.title_le.text() or "Panel",
            bus_name=bus_name,
            use_dbc=use_dbc,
            msg_name=msg_name,
            sig_name=sig_name,
            color=(self.color_le.text().strip() or None),
            units=self.units_le.text().strip(),
            min_val=self.min_d.value(),
            max_val=self.max_d.value(),
            plot_window_s=self.plot_win.value(),
            tx=None,
            led_rules=[ln.strip() for ln in self.led_rules.toPlainText().splitlines() if ln.strip()]
        )
        # No transmit binding
        return conf


class MultiPlotConfigDialog(QDialog):
    def __init__(self, parent, buses: Dict[str, Any], dbc: Optional[cantools.database.Database], existing: Optional[PanelConf]=None):
        super().__init__(parent)
        self.setWindowTitle("Add Multi-Plot Panel")
        self.buses = buses
        self.dbc = dbc
        self.rows: List[Dict[str, Any]] = []
        v = QVBoxLayout(self)
        self.title_le = QLineEdit("MultiPlot")
        self.plot_win = QDoubleSpinBox(); self.plot_win.setRange(0.5, 300.0); self.plot_win.setValue(10.0)
        form = QFormLayout(); form.addRow("Title:", self.title_le); form.addRow("Plot Window (s):", self.plot_win)
        v.addLayout(form)
        self.rows_box = QVBoxLayout(); v.addLayout(self.rows_box)
        btn_row = QHBoxLayout(); self.btn_add = QPushButton("Add Signal"); self.btn_add.clicked.connect(self._add_row)
        btn_row.addWidget(self.btn_add); v.addLayout(btn_row)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel); v.addWidget(btns)
        btns.accepted.connect(self.accept); btns.rejected.connect(self.reject)
        if existing and existing.multi_signals:
            for it in existing.multi_signals:
                self._add_row_prefill(it)
        else:
            self._add_row()

    def _add_row(self):
        roww = QWidget(); row = QHBoxLayout(roww)
        bus_cb = QComboBox(); bus_cb.addItem("(any)");
        for bname in self.buses.keys(): bus_cb.addItem(bname)
        msg_cb = QComboBox(); sig_cb = QComboBox(); color_le = QLineEdit(""); color_btn = QPushButton("Pick…")
        def pick():
            col = QColorDialog.getColor();
            if col.isValid(): color_le.setText(col.name())
        color_btn.clicked.connect(pick)
        if self.dbc:
            names = [m.name for m in self.dbc.messages]
            msg_cb.addItems(["(choose)"] + names)
            def on_msg_change(_):
                sig_cb.clear(); name = msg_cb.currentText()
                if name and name != "(choose)":
                    msg = self.dbc.get_message_by_name(name)
                    sig_cb.addItems([s.name for s in msg.signals])
            msg_cb.currentTextChanged.connect(on_msg_change); on_msg_change("")
        rm_btn = QPushButton("Remove")
        row.addWidget(QLabel("Bus:")); row.addWidget(bus_cb)
        row.addWidget(QLabel("Msg:")); row.addWidget(msg_cb)
        row.addWidget(QLabel("Sig:")); row.addWidget(sig_cb)
        row.addWidget(QLabel("Color:")); row.addWidget(color_le); row.addWidget(color_btn)
        row.addWidget(rm_btn)
        self.rows_box.addWidget(roww)
        rec = {'bus': bus_cb, 'msg': msg_cb, 'sig': sig_cb, 'color': color_le, 'roww': roww}
        self.rows.append(rec)
        def remove():
            try:
                self.rows_box.removeWidget(roww); roww.setParent(None); self.rows.remove(rec)
            except Exception:
                pass
        rm_btn.clicked.connect(remove)

    def _add_row_prefill(self, item: Dict[str, str]):
        self._add_row(); rec = self.rows[-1]
        try:
            rec['bus'].setCurrentText(item.get('bus_name') or "(any)")
            if self.dbc and item.get('msg_name'):
                rec['msg'].setCurrentText(item['msg_name'])
                try:
                    rec['msg'].currentTextChanged.emit(rec['msg'].currentText())
                except Exception:
                    pass
            if item.get('sig_name'):
                rec['sig'].setCurrentText(item['sig_name'])
            rec['color'].setText(item.get('color') or "")
        except Exception:
            pass

    def get_panel_conf(self, panel_id: str) -> Optional[PanelConf]:
        items: List[Dict[str, str]] = []
        for r in self.rows:
            bus = r['bus'].currentText(); bus = None if bus == "(any)" else bus
            msg = r['msg'].currentText() if r['msg'].currentText() != "(choose)" else None
            sig = r['sig'].currentText() or None
            if not msg or not sig: continue
            items.append({'bus_name': bus or '', 'msg_name': msg, 'sig_name': sig, 'color': r['color'].text().strip()})
        if not items:
            return None
        norm_items = []
        for it in items:
            norm_items.append({'bus_name': it['bus_name'] or None, 'msg_name': it['msg_name'], 'sig_name': it['sig_name'], 'color': it['color'] or None})
        return PanelConf(panel_id=panel_id, panel_type='multiplot', title=self.title_le.text().strip() or 'MultiPlot', use_dbc=True, plot_window_s=self.plot_win.value(), multi_signals=norm_items)


class BusConfigDialog(QDialog):
    def __init__(self, parent, buses: Dict[str, BusConf]):
        super().__init__(parent)
        self.setWindowTitle("Configure Buses (up to 3)")
        self.widgets: Dict[str, Dict[str, Any]] = {}
        v = QVBoxLayout(self)
        for key in ["BUS1", "BUS2", "BUS3"]:
            group = QGroupBox(key); form = QFormLayout(group)
            enabled = QCheckBox("Enabled"); enabled.setChecked(buses[key].enabled)
            iface = QComboBox(); iface.addItems(["virtual", "pcan"]); iface.setCurrentText(buses[key].interface)
            chan = QLineEdit(buses[key].channel)
            rate = QComboBox(); rate.addItems(["125000","250000","500000","800000","1000000"]); rate.setCurrentText(str(buses[key].bitrate))
            form.addRow(enabled); form.addRow("Interface:", iface); form.addRow("Channel:", chan); form.addRow("Bitrate:", rate)
            v.addWidget(group); self.widgets[key] = dict(enabled=enabled, iface=iface, chan=chan, rate=rate)
        btns = QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel); v.addWidget(btns)
        btns.accepted.connect(self.accept); btns.rejected.connect(self.reject)

    def result_buses(self) -> Dict[str, BusConf]:
        out: Dict[str, BusConf] = {}
        for key, w in self.widgets.items():
            out[key] = BusConf(enabled=w['enabled'].isChecked(), interface=w['iface'].currentText(), channel=w['chan'].text().strip(), bitrate=int(w['rate'].currentText()), name=key)
        return out
