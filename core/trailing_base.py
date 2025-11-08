# trailing_base.py
# Trailing inteligente con:
# - activación por % desde la entrada (activar_pct)
# - buffer/colchón (buffer_pct)
# - umbral mínimo para mover SL (min_mov_sl_pct * entrada)
# - lock opcional cuando la MFE supera cierto % (mfe_pullback_pct / lock_pct)

from typing import Dict

def _cfg_section(cfg, name, plural_fallback=True, default=None):
    if default is None:
        default = {}
    try:
        v = cfg.get(name)
        if isinstance(v, dict):
            return v
        if plural_fallback:
            alt = f"{name}s"
            v = cfg.get(alt)
            if isinstance(v, dict):
                return v
    except Exception:
        pass
    return default


def inicializar(estado_inicial: Dict | None = None) -> Dict:
    """Crea el estado base del trailing."""
    est = {
        "direccion": None,          # "LONG" | "SHORT"
        "precio_entrada": None,
        "sl": None,
        "tp": None,
        "activo": False,
        "high_water": None,         # máximo a favor para LONG
        "low_water": None           # mínimo a favor para SHORT
    }
    if estado_inicial:
        est.update(estado_inicial)
    return est

def preparar_posicion(estado: Dict, side: str, entry: float, cfg: Dict) -> Dict:
    """
    Inicializa datos al abrir una posición.
    No fija SL/TP aquí (el backtest ya los calcula); sólo prepara el estado.
    """
    estado = inicializar(estado)
    estado["direccion"] = "LONG" if side.upper() == "LONG" else "SHORT"
    estado["precio_entrada"] = float(entry)
    # high/low de referencia parte en la entrada
    estado["high_water"] = float(entry)
    estado["low_water"] = float(entry)
    # respeta sl/tp si venían en el estado (no los pisa)
    return estado

def actualizar(estado: Dict, precio_actual: float, cfg: Dict) -> Dict:
    """
    Trailing con umbral y pullback:
    - Activa al alcanzar activar_pct (% desde la entrada).
    - SOLO mueve el SL si el nuevo high/low supera al anterior al menos
      min_mov_sl_pct * entrada.
    - Aplica buffer_pct como colchón.
    - Opcional: lock_pct/mfe_pullback_pct (para “lockear” más cuando hubo MFE grande).
    Devuelve: {"movido": bool, "sl": float|None, "tp": float|None, "activo": bool}
    """
    if estado.get("precio_entrada") is None or estado.get("direccion") is None:
        return {"movido": False, "sl": estado.get("sl"), "tp": estado.get("tp"), "activo": estado.get("activo", False)}

    # --- parámetros desde cfg/trailing (en %)
    tcfg = cfg.get("trailing", {}) if cfg else {}
    activar_pct        = float(tcfg.get("activar_pct", 1.0)) / 100.0   # % de ganancia para activar trailing
    buffer_pct         = float(tcfg.get("buffer_pct", 0.30)) / 100.0   # colchón
    min_mov_sl_pct     = float(tcfg.get("min_mov_sl_pct", 0.10)) / 100.0  # % interpretado como 0.10% (igual que activar_pct)
    mfe_pullback_pct   = float(tcfg.get("mfe_pullback_pct", 0.0)) / 100.0  # opcional
    lock_pct           = float(tcfg.get("lock_pct", 0.0)) / 100.0          # opcional

    direccion   = estado["direccion"]
    entrada     = float(estado["precio_entrada"])
    sl_actual   = estado.get("sl")
    movido      = False

    # Ganancia actual en %
    if direccion == "LONG":
        ganancia_pct = (precio_actual / entrada) - 1.0
    else:
        ganancia_pct = (entrada / precio_actual) - 1.0

    # Activación del trailing
    if not estado.get("activo", False) and ganancia_pct >= activar_pct:
        estado["activo"] = True

    if direccion == "LONG":
        # Nuevo high a favor
        prev_hw = float(estado.get("high_water") or entrada)
        if precio_actual > prev_hw:
            # ¿subió lo suficiente vs el último high? (umbral mínimo)
            if (precio_actual - prev_hw) >= (min_mov_sl_pct * entrada):
                estado["high_water"] = precio_actual
                if estado["activo"]:
                    nuevo_sl = precio_actual * (1.0 - buffer_pct)
                    if (sl_actual is None) or (nuevo_sl > sl_actual):
                        estado["sl"] = nuevo_sl
                        movido = True
        # Pullback/lock opcional si la MFE ya es grande
        if mfe_pullback_pct > 0.0 and ganancia_pct >= mfe_pullback_pct and lock_pct > 0.0:
            lock_price = entrada * (1.0 + lock_pct)
            if (estado.get("sl") or 0.0) < lock_price:
                estado["sl"] = lock_price
                movido = True

    else:  # SHORT
        prev_lw = float(estado.get("low_water") or entrada)
        if precio_actual < prev_lw:
            if (prev_lw - precio_actual) >= (min_mov_sl_pct * entrada):
                estado["low_water"] = precio_actual
                if estado["activo"]:
                    nuevo_sl = precio_actual * (1.0 + buffer_pct)
                    if (sl_actual is None) or (nuevo_sl < sl_actual):
                        estado["sl"] = nuevo_sl
                        movido = True
        if mfe_pullback_pct > 0.0 and ganancia_pct >= mfe_pullback_pct and lock_pct > 0.0:
            lock_price = entrada * (1.0 - lock_pct)
            if (estado.get("sl") or 9e99) > lock_price:
                estado["sl"] = lock_price
                movido = True

    return {"movido": movido, "sl": estado.get("sl"), "tp": estado.get("tp"), "activo": estado.get("activo", False)}
