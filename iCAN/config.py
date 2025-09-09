from __future__ import annotations
import os
from typing import Optional, Dict, Any, List

def _find_config_path() -> Optional[str]:
    # Environment variable wins
    env = os.getenv("PCAN_DESKTOP_CONFIG")
    if env and os.path.isfile(env):
        return env

    for name in ("config.yaml"): 
        p = os.path.join(os.getcwd(), name)
        if os.path.isfile(p):
            return p
    return None

def load_config(path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    try:
        import yaml  # type: ignore
    except Exception:
        # PyYAML not installed; skip
        return None
    cfg_path = path or _find_config_path()
    if not cfg_path:
        return None
    try:
        with open(cfg_path, "r") as f:
            obj = yaml.safe_load(f) or {}
        if not isinstance(obj, dict):
            return None
        return obj
    except Exception:
        return None

