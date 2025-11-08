# core/estado.py
from __future__ import annotations
import json
from pathlib import Path
from typing import Dict, Any

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT.joinpath("data")
DATA_DIR.mkdir(parents=True, exist_ok=True)
ESTADO_PATH = DATA_DIR.joinpath("estado.json")

ESTADO_DEF = {
    "pares": {},          # { "ETHUSDT": {posicion_abierta, direccion, entrada_precio, sl_pct, tp_pct, trailing, qty, entradas} }
    "ordenes_24h": 0
}

def cargar_estado() -> Dict[str, Any]:
    try:
        if not ESTADO_PATH.exists():
            return ESTADO_DEF.copy()
        data = json.loads(ESTADO_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return ESTADO_DEF.copy()
        # saneo mínimo
        data.setdefault("pares", {})
        data.setdefault("ordenes_24h", 0)
        return data
    except Exception:
        return ESTADO_DEF.copy()

def guardar_estado(estado: Dict[str, Any]) -> None:
    try:
        ESTADO_PATH.write_text(json.dumps(estado, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        # último recurso: no rompas el bot por persistencia
        pass
