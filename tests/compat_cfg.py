# -*- coding: utf-8 -*-
from pathlib import Path
import json

def load_settings(root: Path) -> dict:
    cfg_path = root / "config" / "settings.json"
    with open(cfg_path, "r", encoding="utf-8") as f:
        return json.load(f)

def snapshot_for_runner(cfg: dict) -> dict:
    def _as_float(v, default):
        try:
            if v is None: return float(default)
            if isinstance(v, (int, float)): return float(v)
            s = str(v).strip().replace(",", ".")
            return float(s) if s else float(default)
        except Exception:
            return float(default)

    # Relación (R objetivo)
    relacion = _as_float(
        cfg.get("risk", {}).get("relacion") or cfg.get("strategy", {}).get("relacion"),
        3.0
    )

    # Parciales (acepta varias variantes de nombres)
    p = cfg.get("partials") or cfg.get("parcial") or {}
    take_pct = p.get("qty_value", p.get("fraction", 0.5))
    take_pct = _as_float(take_pct, 0.5)
    if take_pct > 1.0:
        take_pct = take_pct / 100.0

    at_R = _as_float(p.get("trigger_R", p.get("at_R", 1.0)), 1.0)
    tp_mul = _as_float(p.get("tp_r_multiple", 1.0), 1.0)

    paso_pct = (tp_mul / max(relacion, 1e-9)) * at_R if relacion else 0.0
    target = relacion

    return {
        "take_pct": take_pct,
        "relacion": relacion,
        "at_R": at_R,
        "paso_pct": paso_pct,
        "target": target,
    }
