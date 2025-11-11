# core/trailing_base.py
# Trailing + Breakeven con API compatible con core.loop()
# Lee parámetros desde CFG["trailing"]

def _cfg_get(cfg: dict, name: str, default):
    try:
        v = (cfg or {}).get("trailing", {})
        return v.get(name, default)
    except Exception:
        return default

def inicializar(cfg: dict):
    """
    Devuelve el estado base del trailing:
    - activo: si el trailing está habilitado
    - rr_trigger: R donde pasamos a BE (ej. 1.0)
    - rr_distance: distancia del SL en R (ej. 0.5)
    - min_mov_sl_pct: mínimo % de movimiento para notificar/aplicar
    - buffer_pct: buffer opcional
    """
    return {
        "activo": bool(_cfg_get(cfg, "enabled", True)),
        "rr_trigger": float(_cfg_get(cfg, "trigger_R", 1.0)),   # R para BE
        "rr_distance": float(_cfg_get(cfg, "distance_R", 0.5)), # R de trailing
        "min_mov_sl_pct": float(_cfg_get(cfg, "min_mov_sl_pct", 0.05)),
        "buffer_pct": float(_cfg_get(cfg, "buffer_pct", 0.0)),
        # runtime:
        "side": None,
        "entry": None,
        "stop": None,
        "peak": None,
        "be_moved": False,
        "sl": None,  # último SL candidato
        "tp": None,  # opcional si querés calcular TP por config
        "ultimo_sl_notificado": None,
        "ultimo_ts_notif": 0.0,
    }

def preparar_posicion(state: dict, side: str, entry: float, cfg: dict):
    """
    Setea datos de la posición: side ('LONG'/'SHORT'), precio de entrada y SL inicial
    (derivado de la R implícita: entry-stop).
    """
    s = dict(state or {})
    sd = side.upper().strip()
    s["side"] = "LONG" if sd.startswith("LONG") or sd.startswith("BUY") else "SHORT"
    s["entry"] = float(entry)

    # SL inicial desde CFG riesgo.stop_pct
    stop_pct = float(((cfg or {}).get("riesgo", {}) or {}).get("stop_pct", 2.0)) / 100.0
    if s["side"] == "LONG":
        s["stop"] = float(entry) * (1.0 - stop_pct)
    else:
        s["stop"] = float(entry) * (1.0 + stop_pct)

    s["peak"] = float(entry)
    s["be_moved"] = False
    s["sl"] = None
    s["tp"] = None
    return s

def _rr_now(side: str, entry: float, stop: float, price: float) -> float:
    risk = abs(entry - stop)
    if risk <= 0:
        return 0.0
    if side == "LONG":
        return (price - entry) / risk
    else:
        return (entry - price) / risk

def actualizar(state: dict, price: float, cfg: dict):
    """
    Actualiza el trailing/BE y devuelve un dict:
      {"activo": bool, "sl": float|None, "tp": float|None, "movido": bool}
    """
    if not state or not state.get("activo", True):
        return {"activo": False, "sl": None, "tp": None, "movido": False}

    side  = state["side"]
    entry = float(state["entry"])
    stop0 = float(state["stop"])
    rr_trigger  = float(state.get("rr_trigger", 1.0))
    rr_distance = float(state.get("rr_distance", 0.5))

    moved = False
    sl = state.get("sl", None)  # último SL candidato
    tp = state.get("tp", None)

    # BE si alcanza rr_trigger
    rr = _rr_now(side, entry, stop0, float(price))
    if rr >= rr_trigger and not state.get("be_moved", False):
        new_sl = entry
        if side == "LONG":
            if new_sl > stop0:
                stop0 = new_sl
                moved = True
        else:
            if new_sl < stop0:
                stop0 = new_sl
                moved = True
        state["be_moved"] = True
        sl = stop0

    # Si no movimos a BE, no trailing todavía
    if not state.get("be_moved", False):
        state["sl"] = sl
        state["stop"] = stop0
        return {"activo": True, "sl": sl, "tp": tp, "movido": moved}

    # Trailing luego de BE
    risk = abs(entry - stop0 if state["be_moved"] else entry - state["stop"])
    base_risk = abs(entry - state["stop"])
    if base_risk <= 0:
        state["sl"] = sl
        return {"activo": True, "sl": sl, "tp": tp, "movido": moved}

    if side == "LONG":
        state["peak"] = max(float(state.get("peak", entry)), float(price))
        new_sl = state["peak"] - (rr_distance * base_risk)
        # monotónico (no retroceder SL)
        if sl is None or new_sl > float(sl):
            sl = new_sl
            moved = True
    else:
        state["peak"] = min(float(state.get("peak", entry)), float(price))
        new_sl = state["peak"] + (rr_distance * base_risk)
        if sl is None or new_sl < float(sl):
            sl = new_sl
            moved = True

    state["sl"] = sl
    state["stop"] = stop0
    return {"activo": True, "sl": sl, "tp": tp, "movido": moved}
