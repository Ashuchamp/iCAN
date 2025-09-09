from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Optional, Any, List

APP_TITLE = "iCAN"
DEFAULT_LAYOUT_FILE = "dashboard_layout.json"


@dataclass
class BusConf:
    enabled: bool = False
    interface: str = "virtual"   # "pcan" or "virtual"
    channel: str = "vcan0"       # e.g. PCAN_USBBUS1 or vcan0
    bitrate: int = 500000
    name: str = "BUS1"           # Friendly name


@dataclass
class PanelConf:
    panel_id: str
    panel_type: str  # "plot"|"multiplot"|"gauge"|"value"|"table"|"led"
    title: str
    # Subscription (for reading/display):
    bus_name: Optional[str] = None
    use_dbc: bool = True
    msg_name: Optional[str] = None
    sig_name: Optional[str] = None
    # Plot style (for plot panel)
    color: Optional[str] = None
    # Display options:
    units: str = ""
    min_val: float = 0.0
    max_val: float = 100.0
    # Plot options:
    plot_window_s: float = 10.0
    # Multi-plot selections: list of {bus_name,msg_name,sig_name,color}
    multi_signals: List[Dict[str, str]] = field(default_factory=list)
    # LED rules (only for LED panel)
    led_rules: List[str] = field(default_factory=list)


@dataclass
class LayoutState:
    buses: List[BusConf]
    panels: List[PanelConf]
    dock_state_b64: str = ""   # Qt saveState serialized to base64
