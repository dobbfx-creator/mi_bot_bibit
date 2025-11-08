# utils/settings.py
import json, pathlib
from dataclasses import dataclass, fields
from typing import Any, Dict, Tuple, Type, TypeVar
from utils.logging_ex import get_logger
LOG = get_logger("settings")

@dataclass
class Partials:
    enabled: bool
    fraction: float
    at_R: float
    tp_r_multiple: float
    sl_r_multiple: float

# --- Compatibilidad Partials: NUEVO <-> LEGADO + filtro de campos no soportados ---
T = TypeVar("T")

def _compat_partials_cfg(p: Dict) -> Dict:
    """
    Acepta NUEVO:
      - trigger_mode='R_multiple' + trigger_R
      - qty_mode='percent_of_open' + qty_value
    y lo traduce a LEGADO:
      - at_R
      - fraction
    Además permite dejar tp_r_multiple y sl_r_multiple tal cual.
    """
    if not p:
        return {}
    p = dict(p)  # copia defensiva

    # Mapear NUEVO -> LEGADO
    trigger_mode = str(p.get("trigger_mode") or "").strip().lower()
    trigger_R    = p.get("trigger_R", None)
    if trigger_mode == "r_multiple" and trigger_R is not None:
        try:
            p["at_R"] = float(trigger_R)
        except Exception:
            pass

    qty_mode  = str(p.get("qty_mode") or "").strip().lower()
    qty_value = p.get("qty_value", None)
    if qty_mode == "percent_of_open" and qty_value is not None:
        try:
            frac = float(qty_value) / 100.0
            p["fraction"] = max(0.0, min(1.0, frac))
        except Exception:
            pass

    return p

def _coerce_to_dataclass(cls: Type[T], data: Dict) -> T:
    """
    Filtra 'data' para que solo entren campos válidos del dataclass 'cls'.
    Evita TypeError por kwargs desconocidos.
    """
    allowed = {f.name for f in fields(cls)}
    cleaned = {k: v for k, v in (data or {}).items() if k in allowed}
    return cls(**cleaned)

def _first_present(d: Dict[str, Any], *keys, default=None):
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return default

def load_settings(path: str|pathlib.Path) -> Tuple[Dict[str,Any], Partials]:
    p = pathlib.Path(path)
    cfg = json.loads(p.read_text(encoding="utf-8"))

    # Normalizar “partials” / “parcial”
    raw_partials = _first_present(cfg, "partials", "parcial", default={})
    if "parcial" in cfg and "partials" not in cfg:
        LOG.warning("Se encontró 'parcial' (singular). Normalizando a 'partials'.")

    # Defaults seguros (LEGADO)
    def_g = {
        "enabled": True,
        "fraction": 0.5,
        "at_R": 0.5,
        "tp_r_multiple": 3.0,
        "sl_r_multiple": 1.0,
    }

    # Merge con config del usuario
    merged = {**def_g, **raw_partials}

    # Compat NUEVO -> LEGADO (no rompe si ya viene en legado)
    merged = _compat_partials_cfg(merged)

    # Validaciones (sobre LEGADO ya resuelto)
    errs = []
    try:
        if not (0 < float(merged["fraction"]) <= 1):
            errs.append("partials.fraction debe estar en (0,1].")
    except Exception:
        errs.append("partials.fraction inválido.")
    try:
        if float(merged["at_R"]) <= 0:
            errs.append("partials.at_R debe ser > 0.")
    except Exception:
        errs.append("partials.at_R inválido.")
    try:
        if float(merged["tp_r_multiple"]) <= 0 or float(merged["sl_r_multiple"]) <= 0:
            errs.append("partials.tp_r_multiple y sl_r_multiple deben ser > 0.")
    except Exception:
        errs.append("partials.tp_r_multiple/sl_r_multiple inválidos.")
    if errs:
        for e in errs:
            LOG.error("CONFIG ERROR: %s", e)
        raise ValueError("Settings inválidos: " + "; ".join(errs))

    # Construir dataclass de forma segura (filtrando campos extra)
    parts = _coerce_to_dataclass(Partials, merged)

    return cfg, parts
