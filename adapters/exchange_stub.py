# adapters/exchange_stub.py
from typing import List, Dict

# Memoria de proceso para la demo
_SPIKE_DISPARADO: Dict[str, bool] = {}
_BIAS: Dict[str, Dict] = {}  # {"dir": +1/-1, "ticks": int, "last": float}

def _serie_base(n: int, base: float, paso: float) -> List[dict]:
    velas = []
    c = base
    for i in range(n):
        c += paso  # tendencia suave
        o = c - 0.3
        h = c + 0.7
        l = c - 0.6
        v = 1.0 + (i * 0.05)  # volumen creciente
        velas.append({"open": o, "high": h, "low": l, "close": c, "volume": v})
    return velas

def _aplicar_bias_post_entrada(simbolo: str, velas: List[dict]) -> List[dict]:
    """
    Si el símbolo tiene un sesgo activo (post-entrada), empujamos el último close
    a favor de la dirección por unos ciclos para permitir trailing/TP en demo.
    """
    b = _BIAS.get(simbolo)
    if not b or b.get("ticks", 0) <= 0 or not velas:
        return velas

    last = b.get("last", velas[-1]["close"])
    # empuje de ~+1% o -1% por ciclo
    if b["dir"] > 0:
        c2 = last * 1.01  # a favor (LONG)
    else:
        c2 = last * 0.99  # a favor (SHORT)

    velas[-1] = {
        "open": c2 - 1.0,
        "high": c2 + 1.5,
        "low":  c2 - 1.5,
        "close": c2,
        "volume": max(velas[-1]["volume"], 2.0)  # que no falte volumen
    }

    # actualizar memoria
    b["last"] = c2
    b["ticks"] -= 1
    _BIAS[simbolo] = b
    return velas

def obtener_velas(simbolo: str, tf: str, n: int) -> List[dict]:
    bases = {"ETHUSDT": 5035.0, "BTCUSDT": 96256.0, "SOLUSDT": 150.0}
    pasos = {"ETHUSDT": 0.6,     "BTCUSDT": 1.6,      "SOLUSDT": 0.3}

    base = bases.get(simbolo, 100.0)
    paso = pasos.get(simbolo, 0.5)

    velas = _serie_base(n, base, paso)

    # Spike una sola vez para forzar entrada
    if not _SPIKE_DISPARADO.get(simbolo, False) and len(velas) >= 1:
        last = velas[-1]
        if simbolo == "ETHUSDT":
            # arriba => BUY
            c2 = last["close"] * 1.06
            velas[-1] = {"open": c2 - 1.0, "high": c2 + 1.5, "low": c2 - 1.5, "close": c2, "volume": last["volume"] * 2.5}
            _BIAS[simbolo] = {"dir": +1, "ticks": 5, "last": c2}
        elif simbolo == "BTCUSDT":
            # abajo => SELL
            c2 = last["close"] * 0.94
            velas[-1] = {"open": c2 + 1.0, "high": c2 + 1.5, "low": c2 - 1.5, "close": c2, "volume": last["volume"] * 2.5}
            _BIAS[simbolo] = {"dir": -1, "ticks": 5, "last": c2}
        # SOLUSDT sin spike (control)
        _SPIKE_DISPARADO[simbolo] = True
        return velas

    # Si ya disparó, empujamos unos ciclos a favor para que se vea trailing/TP
    return _aplicar_bias_post_entrada(simbolo, velas)

# --------- NUEVO: hooks de “producción” (stubs) ---------
def obtener_posiciones_abiertas() -> List[Dict]:
    """
    Stub: en real devolvería posiciones del exchange:
    [
      {"symbol": "ETHUSDT", "side": "LONG", "entry_price": 5035.0, "sl": 4984.65, "tp": 5286.75},
      ...
    ]
    """
    return []  # demo: sin posiciones reales

def establecer_sl_tp(simbolo: str, side: str, sl: float, tp: float) -> Dict:
    """
    Stub: en real colocaría/actualizaría SL/TP en el exchange para la posición abierta.
    """
    return {"ok": True, "symbol": simbolo, "side": side, "sl": sl, "tp": tp}

def enviar_orden(tipo: str, qty: float, sl: float, tp: float) -> dict:
    return {"ok": True, "tipo": tipo, "qty": qty, "sl": sl, "tp": tp}
