# save as probe_pcan_channels.py
import can

candidates = [f"PCAN_USBBUS{i}" for i in range(1, 9)]  # try 1..8
for ch in candidates:
    try:
        bus = can.Bus(interface="pcan", channel=ch, bitrate=500000)
        print("OK  :", ch)
        bus.shutdown()
    except Exception as e:
        print("NO  :", ch, f"-> {e.__class__.__name__}: {e}")
